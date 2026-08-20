"""
Sub-fase 1.11 — Returns & Barang Sisa
Service: buat return, proses penyesuaian stok saat approved.

Alur:
  Sales/Admin buat Return (draft/pending) → attach bukti foto →
  Manager/Admin approve → stock_adjusted (rolls baru + rebuild_balance).
Jenis return: retur | bs (Barang Sisa) | penggantian
"""
import logging
import re
from typing import Any, Dict, List
from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from core_utils import now_iso, new_id, rupiah, next_doc_number
from services.roll_service import rebuild_balance
from services import gl_service
from services import costing_service
from services import return_policy_service as rps
from services import return_state as st
from services import qc_inspection_service as qc
from services import grade_service   # Fase A · PS-09 — SSOT perubahan grade roll
from services import movement_label_service as _mlabel   # E5.3/E-9 — nama singkat badan usaha
import domain_registry as _dr        # Fase A · PS-02 — snapshot domain roll
from services.customer_service import order_payment_method, NON_AR_METHODS

_log = logging.getLogger(__name__)



# R2 — rekomendasi outcome dari grade 4-point (A baik → refund; B turun mutu →
#   store_credit/regrade; C rusak → nego/reject). Kondisi 'damaged' menajamkan ke reject.
GRADE_TO_OUTCOME = {"A": st.OUTCOME_REFUND, "B": st.OUTCOME_STORE_CREDIT, "C": st.OUTCOME_NEGO}


def _recommend_outcome(grade: str, condition: str = "ok") -> str:
    if condition == "damaged" and grade in ("C", ""):
        return st.OUTCOME_REJECT
    return GRADE_TO_OUTCOME.get(grade, st.OUTCOME_REFUND)

# F3 — jenis retur/RMA yang valid (berbasis SO). komplain/garansi = aftersales.
VALID_RETURN_TYPES = {"retur", "bs", "penggantian", "komplain", "garansi"}

# R1-06 — status retur yang qty-nya DIHITUNG terhadap batas retur (barang benar-benar
#   keluar dari sisi customer / dalam proses). rejected & cancelled TIDAK dihitung.
RETURN_ACTIVE_STATUSES = {
    "draft", "pending_approval", "approved", "inspecting", "inspected",
    "refund_settled", "credit_settled", "nego_settled",
}
_RET_EPS = 0.01


# ─── R1-06: batas kuantitas retur (tak boleh > terkirim/terjual, akumulatif) ──

async def _returnable_by_product(order_id: str) -> Dict[str, float]:
    """Kuantitas maksimum yang boleh diretur per produk untuk sebuah order.
    Basis = qty TERKIRIM (Σ outbound wms_tasks.shipped_qty) bila ada tracking
    pengiriman; bila belum ada (0), fallback ke qty TERJUAL (Σ order line quantity).
    Mencegah retur > yang benar-benar keluar/terjual (R1-06)."""
    order = await db.sales_orders.find_one({"id": order_id}, {"_id": 0, "items": 1}) or {}
    sold: Dict[str, float] = {}
    for it in order.get("items", []):
        pid = it.get("product_id")
        if pid:
            sold[pid] = sold.get(pid, 0.0) + float(it.get("quantity", 0) or 0)
    shipped: Dict[str, float] = {}
    async for t in db.wms_tasks.find(
            {"order_id": order_id, "flow_type": "outbound"},
            {"_id": 0, "product_id": 1, "shipped_qty": 1}):
        pid = t.get("product_id")
        if pid:
            shipped[pid] = shipped.get(pid, 0.0) + float(t.get("shipped_qty", 0) or 0)
    returnable: Dict[str, float] = {}
    for pid, sq in sold.items():
        s = round(shipped.get(pid, 0.0), 2)
        returnable[pid] = s if s > 0 else round(sq, 2)
    # Edge: produk yang terkirim tapi tak ada di baris order → batasi ke terkirim.
    for pid, s in shipped.items():
        if pid not in returnable and s > 0:
            returnable[pid] = round(s, 2)
    return returnable


async def _already_returned_by_product(order_id: str, exclude_id: str = "") -> Dict[str, float]:
    """Σ quantity_returned per produk dari retur AKTIF (non-rejected) untuk order,
    kecuali dokumen `exclude_id` (dipakai saat re-check approve dokumen itu sendiri)."""
    agg: Dict[str, float] = {}
    async for r in db.sales_returns.find(
            {"order_id": order_id, "status": {"$in": list(RETURN_ACTIVE_STATUSES)}},
            {"_id": 0, "id": 1, "items": 1}):
        if exclude_id and r.get("id") == exclude_id:
            continue
        for it in r.get("items", []):
            pid = it.get("product_id")
            if pid:
                agg[pid] = agg.get(pid, 0.0) + float(it.get("quantity_returned", 0) or 0)
    return agg


async def assert_return_within_limits(order_id: str, items: List[Dict],
                                      exclude_id: str = "") -> None:
    """R1-06 — pastikan (retur sebelumnya + retur ini) per produk TIDAK melebihi
    batas (terkirim bila ada, else terjual). Raise ValueError bila dilanggar."""
    returnable = await _returnable_by_product(order_id)
    already = await _already_returned_by_product(order_id, exclude_id)
    for it in items:
        pid = it.get("product_id")
        req = float(it.get("quantity_returned", 0) or 0)
        if not pid or req <= 0:
            continue
        cap = returnable.get(pid, 0.0)
        prev = already.get(pid, 0.0)
        if prev + req > cap + _RET_EPS:
            name = it.get("product_name", pid)
            remaining = max(round(cap - prev, 2), 0.0)
            raise ValueError(
                f"Retur melebihi batas untuk '{name}': diminta {req:g}, sudah diretur {prev:g}, "
                f"maksimum (terkirim/terjual) {cap:g}. Sisa yang bisa diretur: {remaining:g}."
            )


# ─── ID generator ───────────────────────────────────────────────────────────

async def next_return_number() -> str:
    """Generate SRET-XXXXX auto-increment."""
    last = await db.sales_returns.find_one(
        {"number": {"$regex": r"^SRET-"}},
        sort=[("number", -1)]
    )
    if last and last.get("number"):
        m = re.search(r"(\d+)$", last["number"])
        n = int(m.group(1)) + 1 if m else 1
    else:
        n = 1
    return f"SRET-{n:05d}"


async def next_credit_note_number() -> str:
    """F3 — Generate CN-XXXXX auto-increment (Credit Note / Nota Kredit)."""
    last = await db.credit_notes.find_one(
        {"number": {"$regex": r"^CN-"}}, sort=[("number", -1)])
    if last and last.get("number"):
        m = re.search(r"(\d+)$", last["number"])
        n = int(m.group(1)) + 1 if m else 1
    else:
        n = 1
    return f"CN-{n:05d}"


async def _create_credit_note_and_post_gl(
    ret: Dict[str, Any],
    items: List[Dict] = None,
    post_stock: bool = True,
    settlement_type: str = None,
    refund_account_code: str = "",
) -> Dict[str, Any]:
    """F3/R1 — buat Credit Note dari sales_return + posting GL reversal (idempotent).

    Parameter (R1):
      items          : subset item yang diselesaikan (partial/reject) — default semua item.
      post_stock     : True → barang kembali ke stok (COGS reversal + roll masuk); False → nego (tanpa gerak stok).
      settlement_type: "cash" (refund tunai) | "ar" (pengurang piutang) | "store_credit" | "nego".
                       None → deteksi dari metode bayar order.

    Nilai retur dari harga item SO asli; HPP dari avg unit_cost roll.
    Bila return sudah punya credit_note_id → kembalikan yang ada (idempotent)."""
    if ret.get("credit_note_id"):
        existing = await db.credit_notes.find_one({"id": ret["credit_note_id"]}, {"_id": 0})
        if existing:
            return existing

    order = await db.sales_orders.find_one({"id": ret["order_id"]}, {"_id": 0}) or {}
    price_by_pid: Dict[str, float] = {}
    for it in order.get("items", []):
        price_by_pid[it.get("product_id")] = float(it.get("price", it.get("unit_price", 0)) or 0)

    eid = ret.get("entity_id", "")
    src_items = items if items is not None else ret.get("items", [])
    lines: List[Dict[str, Any]] = []
    net = 0.0
    cogs = 0.0
    for item in src_items:
        pid = item.get("product_id")
        qty = float(item.get("quantity_returned", 0) or 0)
        if qty <= 0:
            continue
        unit_price = price_by_pid.get(pid, 0.0)
        line_net = round(qty * unit_price, 2)
        unit_cost = await gl_service._avg_unit_cost(pid, eid)
        net += line_net
        # COGS reversal hanya bila barang benar-benar masuk stok (post_stock) & kondisi bukan rusak.
        if post_stock and item.get("condition", "ok") != "damaged":
            cogs += qty * unit_cost
        lines.append({"product_id": pid, "product_name": item.get("product_name", ""),
                      "quantity": round(qty, 2), "unit": item.get("unit", "meter"),
                      "unit_price": unit_price, "line_total": line_net,
                      "reason": item.get("reason", ""), "condition": item.get("condition", "ok")})

    net = round(net, 2)
    cogs = round(cogs, 2)
    ppn_rate = float(order.get("ppn_rate", 0) or 0)
    # F-10 — pakai RASIO PPN efektif dari order asal (dukung DPP Nilai Lain 11/12;
    # sekaligus fix bug lama net × ppn_rate tanpa /100)
    order_ppn = float(order.get("ppn_amount", 0) or 0)
    order_net = round(float(order.get("grand_total", 0) or 0) - order_ppn, 2)
    eff_frac = (order_ppn / order_net) if (order_ppn > 0 and order_net > 0) else 0.0
    has_ppn = eff_frac > 0 and net > 0
    ppn = round(net * eff_frac, 2) if has_ppn else 0.0
    gross = round(net + ppn, 2)

    # Tentukan penyelesaian & flag kas.
    if settlement_type:
        settlement = settlement_type
    else:
        settlement = "cash" if order_payment_method(order) in NON_AR_METHODS else "ar"
    is_cash = settlement == "cash"

    cn_number = await next_credit_note_number()
    now = now_iso()
    cn = {
        "id": new_id("cn"), "number": cn_number,
        "return_id": ret["id"], "return_number": ret.get("number", ""),
        "order_id": ret["order_id"], "order_number": ret.get("order_number", ""),
        "customer_id": ret.get("customer_id"), "customer_name": ret.get("customer_name", ""),
        "entity_id": eid, "return_type": ret.get("return_type", "retur"),
        "lines": lines, "net_amount": net, "ppn_rate": ppn_rate, "ppn_amount": ppn,
        "gross_amount": gross, "cogs_amount": cogs,
        "settlement": settlement,   # cash | ar | store_credit | nego
        "refund_account_code": (refund_account_code or "1-1100") if settlement == "cash" else "",
        "outcome": ret.get("outcome", ""),
        "status": "posted", "created_by": ret.get("settled_by") or ret.get("approved_by", "system"),
        "created_at": now, "updated_at": now,
    }
    await db.credit_notes.insert_one(dict(cn))

    je = None
    try:
        je = await gl_service.post_sales_return(
            ret, return_net=net, return_ppn=ppn, return_cogs=cogs,
            is_cash=is_cash, settlement=settlement,
            cash_account_code=(refund_account_code or "") if is_cash else "",
            credit_note_number=cn_number)
    except Exception:  # noqa: BLE001 — GL best-effort, CN tetap tercatat
        je = None
    if je:
        await db.credit_notes.update_one({"id": cn["id"]}, {"$set": {"journal_entry_id": je.get("id")}})
        cn["journal_entry_id"] = je.get("id")

    await db.sales_returns.update_one(
        {"id": ret["id"]},
        {"$set": {"credit_note_id": cn["id"], "credit_note_number": cn_number,
                  "credit_note_amount": gross, "updated_at": now}})
    # FASE G-4 / E-9 — TAUTAN DI TITIK LAHIR. Nota kredit retur dulu hanya tertaut
    # lewat backfill `doc_refs_service.backfill()` yang jalan saat seed, jadi nota
    # kredit yang lahir di produksi menjadi **dokumen yatim** sampai seed berikutnya
    # (terbukti memerah INV-REF-01: "credit_note CN-00001 tanpa induk hidup").
    # Nota kredit adalah bagian rantai retur; jejaknya harus hidup sejak detik ia terbit.
    try:
        from services import doc_refs_service as _refs
        if ret.get("order_id"):
            await _refs.safe_link(("credit_note", cn["id"]),
                                  ("sales_order", ret["order_id"]), "corrects",
                                  note="Nota kredit atas retur pesanan ini")
        await _refs.safe_link(("credit_note", cn["id"]),
                              ("sales_return", ret["id"]), "issued_by",
                              note="Diterbitkan oleh retur pelanggan")
    except Exception as exc:  # noqa: BLE001 — jejak, bukan syarat sahnya nota kredit
        _log.warning("tautan nota kredit %s gagal: %s", cn_number, exc)
    return cn


# ─── CREATE ─────────────────────────────────────────────────────────────────

async def create_return(
    order_id: str,
    return_type: str,
    items: List[Dict],
    notes: str,
    entity_id: str,
    created_by: str,
    submit_now: bool = False,
) -> Dict[str, Any]:
    """
    Buat dokumen sales_return.
    items: [{product_id, product_name, quantity_returned, unit, reason, condition}]
    """
    order = await db.sales_orders.find_one({"id": order_id})
    if not order:
        raise ValueError(f"Pesanan {order_id} tidak ditemukan")

    # F3 — validasi jenis retur (RMA): retur | bs | penggantian | komplain | garansi
    if return_type not in VALID_RETURN_TYPES:
        raise ValueError(
            f"Jenis retur '{return_type}' tidak valid. Pilihan: {', '.join(sorted(VALID_RETURN_TYPES))}")

    # Resolve entity from order bila tidak diberikan
    if not entity_id:
        entity_id = order.get("entity_id", "")

    # R1-06 — batasi qty retur: (retur aktif sebelumnya + retur ini) ≤ terkirim/terjual per produk.
    await assert_return_within_limits(order_id, items)

    number = await next_return_number()
    now = now_iso()
    status = "pending_approval" if submit_now else "draft"

    # R0 — snapshot kebijakan retur jual + deadline (auditable; best-effort, tak menggagalkan create).
    policy_snapshot: Dict[str, Any] = {}
    return_deadline = ""
    policy_eligibility: Dict[str, Any] = {}
    try:
        elig = await rps.check_sales_return_eligibility(order, return_type=return_type)
        policy_snapshot = elig.get("policy", {}) or {}
        return_deadline = elig.get("deadline", "") or ""
        policy_eligibility = {
            "eligible": elig.get("eligible"),
            "within_window": elig.get("within_window"),
            "blocked": elig.get("blocked"),
            "reference_date": elig.get("reference_date"),
            "window_days": elig.get("window_days"),
            "days_remaining": elig.get("days_remaining"),
            "require_inspection": elig.get("require_inspection"),
            "supplier_linked": elig.get("supplier_linked"),
            "warnings": elig.get("warnings", []),
        }
    except Exception:  # noqa: BLE001 — resolusi policy tak boleh menggagalkan pembuatan retur
        policy_snapshot, return_deadline, policy_eligibility = {}, "", {}

    # R1 — inisialisasi field lifecycle per item (outcome & inspeksi diisi kemudian).
    norm_items: List[Dict[str, Any]] = []
    for it in items:
        d = dict(it)
        d.setdefault("condition", "ok")
        d["settle_outcome"] = ""           # refund|store_credit|nego|reject (diisi saat settle)
        d["settled_qty"] = 0.0
        d["replacement_qty"] = 0.0          # sisa kirim-ulang (penggantian)
        d["inspection"] = {}                # grade/kondisi/disposisi (diisi R2)
        # FASE U — dua satuan: jumlah roll DIHITUNG dari roll yang benar-benar
        # dikembalikan (`roll_ids`), bukan diketik ulang; kalau kosong → None ("—").
        _rolls = await _dual.rolls_of_ids(d.get("roll_ids"))
        d["qty_rolls"] = _rolls if _rolls is not None else (
            None if d.get("qty_rolls") in (None, "") else int(d["qty_rolls"]))
        norm_items.append(d)
    # FASE L — snapshot lini kerja MD di setiap baris + turunan kepala dokumen.
    # Diambil dari baris SO bila ada (retur adalah pembalik dokumen itu), kalau tidak
    # dari master produk. Retur harus jatuh ke papan lini yang sama dengan penjualannya.
    _so_lines = {str((i or {}).get("product_id") or ""): str((i or {}).get("line_code") or "")
                 for i in (order.get("items") or [])}
    for d in norm_items:
        snap = str(_so_lines.get(str(d.get("product_id") or "")) or "").strip().lower()
        if snap:
            d["line_code"] = snap
    from services import line_scope as _lines
    _missing = [d for d in norm_items if not str(d.get("line_code") or "").strip()]
    if _missing:
        await _lines.stamp_items_from_db(db, _missing)
    line_codes = _lines.codes_from_items(norm_items)

    doc = {
        "id":           new_id("sret"),
        "number":       number,
        "order_id":     order_id,
        "order_number": order.get("number", order_id),
        "customer_id":  order.get("customer_id"),
        "customer_name":order.get("customer_name", ""),
        "entity_id":    entity_id,
        "return_type":  return_type,    # retur | bs | penggantian | komplain | garansi
        "status":       status,
        "items":        norm_items,
        "line_codes":   line_codes,     # FASE L — turunan baris (chip penyaring lini)
        "notes":        notes,
        "attachments":  [],
        "stock_adjusted": False,
        # ── R0 — Return Policy snapshot & deadline ──
        "policy_snapshot":    policy_snapshot,
        "return_deadline":    return_deadline,
        "policy_eligibility": policy_eligibility,
        # ── R1 — State machine + outcome ──
        "outcome":            "",         # refund|store_credit|nego|reject (final saat settle)
        "inspection_status":  "pending",  # pending|in_progress|done
        "inspection":         {},         # ringkasan hasil inspeksi (R2)
        "settlement":         {},         # ringkasan finansial saat settle
        "created_by":   created_by,
        "approved_by":  None,
        "approved_at":  None,
        "inspected_by": None,
        "inspected_at": None,
        "settled_by":   None,
        "settled_at":   None,
        "rejected_by":  None,
        "rejected_at":  None,
        "reject_reason":None,
        "created_at":   now,
        "updated_at":   now,
    }
    await db.sales_returns.insert_one(doc)
    doc.pop("_id", None)
    # FASE G-4 — retur menaut ke pesanan yang dibaliknya (dua arah).
    from services import doc_refs_service as _refs
    if doc.get("order_id"):
        await _refs.safe_link(("sales_return", doc["id"]), ("sales_order", doc["order_id"]),
                              "reverses", note="retur atas pesanan")
    return doc


# ─── R1 — APPROVE (manager) : pending_approval → approved ───────────────────

async def approve_return(return_id: str, approved_by: str, notes: str = "") -> Dict[str, Any]:
    """Manager approve retur jual (R1). TIDAK menyesuaikan stok/finance di sini —
    stok & Credit Note dilakukan saat **settle** setelah inspeksi (R2/R5).
    Transisi: pending_approval → approved."""
    ret = await db.sales_returns.find_one({"id": return_id})
    if not ret:
        raise ValueError(f"Return {return_id} tidak ditemukan")
    st.assert_transition(ret["status"], st.APPROVED)
    # R1-06 — re-check batas saat approve (defense-in-depth).
    await assert_return_within_limits(ret["order_id"], ret.get("items", []), exclude_id=ret["id"])
    now = now_iso()
    await db.sales_returns.update_one(
        {"id": return_id},
        {"$set": {"status": st.APPROVED, "approved_by": approved_by, "approved_at": now,
                  "approval_notes": notes, "updated_at": now}})
    ret = await db.sales_returns.find_one({"id": return_id})
    ret.pop("_id", None)
    return ret


# ─── R1 — INSPECT : approved → inspecting → inspected ────────────────────────

async def start_inspection(return_id: str, actor: str) -> Dict[str, Any]:
    """Mulai inspeksi (WAJIB — keputusan #3). Transisi: approved → inspecting.
    Detail grading 4-point diisi di R2 via complete_inspection."""
    ret = await db.sales_returns.find_one({"id": return_id})
    if not ret:
        raise ValueError(f"Return {return_id} tidak ditemukan")
    st.assert_transition(ret["status"], st.INSPECTING)
    now = now_iso()
    await db.sales_returns.update_one(
        {"id": return_id},
        {"$set": {"status": st.INSPECTING, "inspection_status": "in_progress",
                  "inspection_started_by": actor, "inspection_started_at": now, "updated_at": now}})
    ret = await db.sales_returns.find_one({"id": return_id})
    ret.pop("_id", None)
    return ret


async def complete_inspection(return_id: str, actor: str,
                              inspections: List[Dict] = None, notes: str = "") -> Dict[str, Any]:
    """Selesaikan inspeksi (R2 — unified 4-point). Transisi: inspecting → inspected.

    `inspections`: [{index|product_id, defects[{point_value,count}], grade?, condition,
                     disposition, recommended_outcome?, accepted_qty, gsm_actual, width_actual}].
    Bila `defects` diisi → grade dihitung via engine 4-point (reuse qc_inspection_service);
    kalau tidak, pakai `grade` manual. `recommended_outcome` diturunkan dari grade (bisa dioverride)."""
    ret = await db.sales_returns.find_one({"id": return_id})
    if not ret:
        raise ValueError(f"Return {return_id} tidak ditemukan")
    st.assert_transition(ret["status"], st.INSPECTED)
    inspections = inspections or []
    th = await qc.grade_thresholds(ret.get("entity_id"))
    by_idx: Dict[int, Dict] = {}
    by_pid: Dict[str, Dict] = {}
    for insp in inspections:
        if insp.get("index", -1) is not None and int(insp.get("index", -1)) >= 0:
            by_idx[int(insp["index"])] = insp
        if insp.get("product_id"):
            by_pid[insp["product_id"]] = insp

    items = ret.get("items", [])
    grades: List[str] = []
    total_points = 0.0
    for i, it in enumerate(items):
        insp = by_idx.get(i) or by_pid.get(it.get("product_id")) or {}
        if not insp:
            continue
        defects = insp.get("defects") or []
        norm_defects = [{"point_value": int(d.get("point_value", 0) or 0),
                         "count": int(d.get("count", 0) or 0), "note": d.get("note", "")}
                        for d in defects if int(d.get("point_value", 0) or 0) in qc.VALID_POINTS
                        and int(d.get("count", 0) or 0) > 0]
        if norm_defects:
            points = qc.compute_points(norm_defects)
            grade = qc.grade_from_points(points, th)
        else:
            points = 0.0
            grade = insp.get("grade") or "A"
        condition = insp.get("condition", it.get("condition", "ok"))
        rec = insp.get("recommended_outcome") or _recommend_outcome(grade, condition)
        it["condition"] = condition
        it["inspection"] = {
            "points": points, "grade": grade, "defects": norm_defects,
            "condition": condition, "disposition": insp.get("disposition", ""),
            "recommended_outcome": rec,
            "accepted_qty": round(float(insp.get("accepted_qty", it.get("quantity_returned", 0)) or 0), 2),
            "gsm_actual": insp.get("gsm_actual"), "width_actual": insp.get("width_actual"),
            "thresholds": th, "notes": insp.get("note", insp.get("notes", "")),
            "inspected_by": actor, "inspected_at": now_iso(),
        }
        grades.append(grade)
        total_points += points

    now = now_iso()
    # Grade & rekomendasi ringkas dokumen = terburuk (paling berisiko) dari semua item.
    worst_grade = "C" if "C" in grades else ("B" if "B" in grades else ("A" if grades else ""))
    worst_cond = "damaged" if any((it.get("condition") == "damaged") for it in items) else "ok"
    summary = {
        "grades": grades, "worst_grade": worst_grade, "total_points": round(total_points, 2),
        "recommended_outcome": _recommend_outcome(worst_grade, worst_cond) if grades else "",
        "thresholds": th, "notes": notes, "inspected_by": actor, "inspected_at": now,
    }
    await db.sales_returns.update_one(
        {"id": return_id},
        {"$set": {"status": st.INSPECTED, "inspection_status": "done", "items": items,
                  "inspection": summary, "inspected_by": actor, "inspected_at": now,
                  "updated_at": now}})
    ret = await db.sales_returns.find_one({"id": return_id})
    ret.pop("_id", None)
    return ret


# ─── R1 — SETTLE : inspected → refund/credit/nego settled ───────────────────

async def _source_roll_provenance(order_id: str, product_id: str) -> Dict[str, Any]:
    """E9.5 — jejak ASAL barang yang dulu dikirim ke pelanggan untuk baris ini.

    CACAT YANG DITUTUP: roll hasil retur pelanggan dibuat TANPA `supplier_id`,
    `po_id`, `po_number`, `supplier_invoice_no`. Akibatnya begitu barang itu kembali
    ke badan usaha pemasok internalnya, badan usaha itu **tidak bisa menemukannya**
    sebagai kandidat retur ke supplier aslinya (`build_returnable_rolls` menyaring
    per supplier/PO) — jejak "kain ini dulu dibeli dari Toba Craft lewat PO-00005"
    hilang begitu saja. Silsilah LOT memang tersimpan, tetapi jalur retur beli
    membaca FIELD ROLL, bukan silsilah lot.

    Juga diwarisi: penanda bahwa barangnya berasal dari **pembelian internal**
    (`cost_basis.interco_purchase`) — inilah yang membuat rambu E9.3 bisa berbunyi.

    Dan **riwayat perolehan** (`acquired_history[]`) ikut diwarisi. Roll retur adalah
    roll BARU, jadi tanpa pewarisan ini rantai perolehannya mulai dari nol: satu-satunya
    catatan yang tersisa adalah "via: return". Padahal pertanyaan manusianya justru
    "kain ini dulu masuk lewat GRN/PO mana?" — dan dua pembaca nyata menjawabnya dari
    riwayat itu (`purchase_return_service.build_returnable_rolls` &
    `routers/product_traceability`, yang mencari `acquired_history.ref_id`/`.po_id`).
    """
    rolls = await db.inventory_rolls.find(
        {"reserved_ref.id": order_id, "reserved_ref.type": "sales_order",
         "product_id": product_id}, {"_id": 0}).to_list(1000)
    # Roll yang benar-benar berjalan ke pelanggan lebih dipercaya daripada sisa reservasi.
    rolls.sort(key=lambda r: (0 if r.get("shipped_at") else 1,
                              str(r.get("shipped_at") or r.get("updated_at") or "")),
               reverse=False)
    prov: Dict[str, Any] = {}
    src_ids: List[str] = []
    hist: List[Dict[str, Any]] = []
    seen: set = set()
    for r in rolls:
        src_ids.append(r.get("id", ""))
        for fld in ("supplier_id", "supplier_name", "po_id", "po_number",
                    "supplier_invoice_no", "received_date", "dye_lot", "supplier_lot"):
            if not prov.get(fld) and r.get(fld):
                prov[fld] = r[fld]
        cb = r.get("cost_basis") or {}
        if cb.get("source") == "interco_purchase" and not prov.get("origin_interco_pair_id"):
            prov["origin_interco_pair_id"] = cb.get("interco_pair_id", "")
            prov["origin_interco_number"] = cb.get("interco_number", "")
        # PO bisa hanya tercatat di `acquired`/`acquired_history` (mis. roll hasil GRN
        # yang sudah berpindah kepemilikan). `via` penerimaan gudang bernilai
        # **"inbound"** (lihat `inbound_receiving`); daftar lama hanya menyebut
        # grn/goods_receipt/purchase sehingga cadangan ini tak pernah berbunyi.
        for acq in list(r.get("acquired_history") or []) + [r.get("acquired") or {}]:
            if not acq.get("via"):
                continue
            if (acq.get("via") in ("inbound", "grn", "goods_receipt", "purchase")
                    and not prov.get("po_id")):
                prov["po_id"] = acq.get("po_id") or acq.get("ref_id") or ""
            key = (acq.get("via"), acq.get("ref_id", ""), acq.get("date", ""))
            if key in seen:
                continue
            seen.add(key)
            # Nama singkat saja (E5.3): jejak boleh dibaca, identitas teknis badan
            # usaha lawan tidak boleh ikut menempel di dokumen roll.
            _own_name = acq.get("owner_entity_name") or await _mlabel.short_name_of(
                acq.get("owner_entity_id") or r.get("owner_entity_id", ""))
            hist.append({**{k: v for k, v in acq.items() if k != "owner_entity_id"},
                         "owner_entity_name": _own_name,
                         "inherited_from_roll_id": r.get("id", ""),
                         "inherited_at": now_iso()})
    if src_ids:
        prov["source_roll_ids"] = src_ids[:50]
    if hist:
        # Urut kronologis; batas 20 langkah sama dengan `execute_ownership_transfer`.
        hist.sort(key=lambda h: str(h.get("date") or ""))
        prov["acquired_history"] = hist[-20:]
    return prov


async def _restock_returned_items(ret: Dict[str, Any], items: List[Dict], now: str,
                                  warehouse_id: str = "", owner_entity_id: str = "") -> None:
    """R2 — buat rolls masuk **QUARANTINE** (bukan langsung available) + movement + rebuild.
    Roll retur harus disetujui/di-release dulu (keputusan #4). Grade dari hasil inspeksi.
    R3 — `warehouse_id` (lokasi fisik) & `owner_entity_id` (kepemilikan) TERPISAH (SSOT).
      Default bila kosong: warehouse=outbound SO, owner=entity dokumen retur.
    Idempotent via flag ret.stock_adjusted (dicek pemanggil)."""
    warehouse_id = warehouse_id or await _resolve_return_warehouse(ret["order_id"])
    owner_entity_id = owner_entity_id or ret["entity_id"]
    combos: set = set()
    for item in items:
        qty = float(item.get("quantity_returned", 0) or 0)
        if qty <= 0:
            continue
        product_id = item["product_id"]
        condition = item.get("condition", "ok")
        insp = item.get("inspection") or {}
        grade = insp.get("grade") or item.get("grade") or "A"
        # R2/R5 — nilai roll = WAC produk (0 bila damaged, konsisten dgn COGS reversal CN)
        #   agar subledger persediaan rekonsiliasi dengan GL 1-1300 (anti INV-GL-DRIFT).
        #   WAC diambil dari entitas PEMILIK (owner) tujuan.
        # R5.5 — simpan pecahan basis: unit_cost = WAC penuh (base+landed), base_unit_cost = komponen
        #   dasar → memungkinkan audit/label "incl. landed" tanpa mengubah nilai total (GL-safe).
        if condition == "damaged":
            avg_cost, base_cost = 0.0, 0.0
        else:
            _w = await costing_service.wac_for_product(product_id, entity_id=owner_entity_id or None)
            avg_cost = float(_w.get("wac") or 0)
            base_cost = float(_w.get("wac_base") or avg_cost)
        # FASE C (D-10) — retur masuk = batch tersendiri: 1 lot per nomor retur × produk
        from services import lot_service as _lots
        _rtn_lot = await _lots.resolve_or_create(
            product_id=product_id, owner_entity_id=owner_entity_id,
            warehouse_id=warehouse_id, lot_code=f"RTN-{ret['number']}",
            source="return",
            source_ref={"type": "sales_return", "id": ret["id"], "number": ret["number"]},
            status="karantina", actor="Retur Jual")
        # E9.5 — jejak asal barang diwariskan dari roll yang DULU dikirim ke pelanggan.
        prov = await _source_roll_provenance(ret.get("order_id", ""), product_id)
        product_doc = await db.products.find_one({"id": product_id}, {"_id": 0}) or {}
        # INV-ROLL-01 — nama kanonik nomor roll adalah `roll_no` (dipakai SEMUA layar,
        # CSV, pencarian, label, dan 6 pembuat roll lainnya). Baris ini dulu menulis
        # `roll_number` — nama yang hanya hidup di sini — sehingga roll hasil retur
        # tampil TANPA nomor di Daftar Roll & ekspor CSV, dan tak bisa dicari. Drift-nya
        # bertahan lama karena ia punya pembacanya sendiri (`ReturnQuarantinePanel` +
        # dua service memakai `roll_no or roll_number`), jadi satu layar tampak benar
        # sementara layar lain kosong. Nomornya kini dari sequence bersama (`RTN-NNNNN`,
        # deletion-safe) — bukan potongan id produk yang dulu menghasilkan
        # "RTN-00003-ntai" (4 huruf terakhir `prod_e9_demo_rantai`).
        roll = {
            "id": new_id("roll"), "product_id": product_id, "warehouse_id": warehouse_id,
            "owner_entity_id": owner_entity_id,
            "roll_no": await next_doc_number("inventory_rolls", "roll_no", "RTN-",
                                             scheme="shared"),
            "unit": item.get("unit") or product_doc.get("base_unit") or "meter",
            "length": round(qty, 2), "length_initial": round(qty, 2), "length_remaining": round(qty, 2),
            "status": "quarantine", "qc_status": "pending_release",
            "origin_type": "return", "origin_ref": ret["id"], "return_id": ret["id"],
            "condition": condition, "grade": grade, "defects": insp.get("defects", []),
            # Fase A · PS-02 — snapshot domain produk (INV-DOMAIN-05)
            **_dr.roll_domain_snapshot(product_doc),
            "inspection": insp, "unit_cost": round(avg_cost, 2), "base_unit_cost": round(base_cost, 2),
            "landed_cost_total": round(max(avg_cost - base_cost, 0.0) * round(qty, 2), 2),
            "earmarked_for": None, "committed_to": None, "reserved_ref": None,
            "lot": _rtn_lot["lot_number"], "lot_id": _rtn_lot["id"],
            "acquired": {"via": "return", "ref_id": ret["id"], "date": now},
            **prov,
            "created_at": now, "updated_at": now,
        }
        await db.inventory_rolls.insert_one(roll)
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": product_id, "warehouse_id": warehouse_id,
            "owner_entity_id": owner_entity_id,
            # Nama kanonik buku mutasi adalah `movement_type` (dipakai layar Mutasi,
            # laporan, dan POC). Baris retur dulu HANYA menulis `type`, jadi mutasinya
            # muncul tanpa jenis — label kosong di layar dan pembanding/pengurut
            # jenis mutasi ikut pecah. `type` dipertahankan demi data lama.
            "type": "return_quarantine_in", "movement_type": "return_quarantine_in",
            "direction": "in",
            "quantity": round(qty, 2), "unit": item.get("unit", "meter"), "roll_id": roll["id"],
 # FASE U — satu baris mutasi menunjuk SATU roll fisik.
 "qty_rolls": (1 if roll["id"] else None),
            "ref_type": "sales_return", "ref_id": ret["id"],
            "notes": f"Retur {ret['number']} → karantina (grade {grade}) @ {warehouse_id} · owner {owner_entity_id}",
            "source_document": ret["id"], "timestamp": now, "lot": roll["lot"],
            "lot_id": _rtn_lot["id"],
        })
        combos.add((product_id, warehouse_id, owner_entity_id))
    for (pid, wid, eid) in combos:
        await rebuild_balance(pid, wid, eid)


async def get_return_quarantine_rolls(return_id: str) -> List[Dict[str, Any]]:
    """Roll hasil retur (karantina/released/scrap) + enrich R3: nama owner-entity & gudang (lokasi)."""
    rolls = await db.inventory_rolls.find(
        {"return_id": return_id, "origin_type": "return"}, {"_id": 0}).to_list(500)
    if not rolls:
        return rolls
    ent_ids = {r.get("owner_entity_id") for r in rolls if r.get("owner_entity_id")}
    wh_ids = {r.get("warehouse_id") for r in rolls if r.get("warehouse_id")}
    pid_ids = {r.get("product_id") for r in rolls if r.get("product_id")}
    ents = {e["id"]: e async for e in db.business_entities.find(
        {"id": {"$in": list(ent_ids)}}, {"_id": 0, "id": 1, "short_name": 1, "legal_name": 1})}
    whs = {w["id"]: w async for w in db.warehouses.find(
        {"id": {"$in": list(wh_ids)}}, {"_id": 0, "id": 1, "name": 1, "code": 1})}
    prods = {p["id"]: p async for p in db.products.find(
        {"id": {"$in": list(pid_ids)}}, {"_id": 0, "id": 1, "name": 1, "sku": 1})}
    for r in rolls:
        e = ents.get(r.get("owner_entity_id"), {})
        w = whs.get(r.get("warehouse_id"), {})
        p = prods.get(r.get("product_id"), {})
        r["owner_entity_name"] = e.get("short_name") or e.get("legal_name") or r.get("owner_entity_id", "")
        r["warehouse_name"] = w.get("name") or w.get("code") or r.get("warehouse_id", "")
        r["product_name"] = p.get("name") or r.get("product_id", "")
        r["sku"] = p.get("sku", "")
        # E9.3 — kalau barangnya berasal dari pembelian internal, layar WAJIB tahu:
        # tombol "Pindah Kepemilikan" harus mati dan menuntun ke Retur Antar-PT.
        # DIHITUNG SEBELUM `cost_basis` di bawah ditimpa menjadi label teks.
        r["interco_origin"] = await interco_origin_of_roll(r)
        r["ownership_transfer_blocked"] = bool(r["interco_origin"])
        # R5.5 — basis valuasi roll: unit_cost = base_unit_cost + landed cost (freight/duty/handling).
        _uc = float(r.get("unit_cost") or 0)
        _base = float(r.get("base_unit_cost") or 0) or _uc
        r["landed_per_unit"] = round(max(_uc - _base, 0.0), 2)
        r["landed_included"] = r["landed_per_unit"] > 0.005
        r["cost_basis"] = "wac_landed" if r["landed_included"] else "wac"
    return rolls


async def release_quarantine(return_id: str, actor: str,
                             decisions: List[Dict] = None, notes: str = "") -> Dict[str, Any]:
    """Keputusan #4 — approve/release roll karantina hasil retur.
    action per roll: 'release' → available (grade final), 'scrap' → damaged (keluar available).
    Tanpa `decisions` → release semua roll karantina return apa adanya. Rebuild balance."""
    rolls = await get_return_quarantine_rolls(return_id)
    q_rolls = [r for r in rolls if r.get("status") == "quarantine"]
    if not q_rolls:
        raise ValueError("Tidak ada roll karantina untuk retur ini")
    _ret_doc = await db.sales_returns.find_one({"id": return_id}, {"_id": 0, "number": 1}) or {}
    ret_number = _ret_doc.get("number", return_id)
    dmap = {d.get("roll_id"): d for d in (decisions or []) if d.get("roll_id")}
    now = now_iso()
    combos: set = set()
    released, scrapped, regraded = 0, 0, 0
    writeoff_total = 0.0
    writeoff_jes: List[Dict[str, Any]] = []
    for r in q_rolls:
        d = dmap.get(r["id"], {})
        action = d.get("action", "release")
        if action == "scrap":
            new_status = "damaged"; scrapped += 1
        else:
            new_status = "available"; released += 1
        old_grade = r.get("grade") or "A"
        # Fase A · PS-09/D-01 — grade hasil release WAJIB nilai enum resmi.
        raw_grade = d.get("grade") or old_grade
        grade = grade_service.normalize_or_raise(raw_grade, "Grade release karantina")
        # R3 — regrade (mis. A→B) saat release. Rekam asal grade utk audit (revaluasi nilai = R5).
        roll_set = {"status": new_status, "qc_status": "released", "grade": grade,
                    "released_by": actor, "released_at": now, "updated_at": now}
        regrade_note = ""
        if grade != old_grade:
            regraded += 1
            roll_set["regraded_from"] = old_grade
            roll_set["regraded_at"] = now
            regrade_note = f" · regrade {old_grade}→{grade}"
            # PS-09 — jejak perubahan grade (before → after) di roll.
            roll_set["grade_source"] = "quarantine_release"
            roll_set["grade_updated_at"] = now
            grade_hist_entry = grade_service.history_entry(
                old_grade, grade, "quarantine_release",
                f"Release karantina retur {ret_number}",
                {"name": actor}, {"roll_no": r.get("roll_no", "")})
        else:
            grade_hist_entry = None
        # R5.1 — WRITE-OFF GL saat scrap: roll keluar subledger fisik (→damaged) → posting
        #   Dr 5-9500 / Cr 1-1300 sebesar nilai subledger roll (anti INV-GL-DRIFT). Idempotent per roll.
        wo_note = ""
        if action == "scrap":
            qty_wo = float(r.get("length_remaining", r.get("length", 0)) or 0)
            unit_cost = float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
            wo_amount = round(qty_wo * unit_cost, 2)
            if wo_amount > 0.01:
                je = await gl_service.post_inventory_writeoff(
                    roll_id=r["id"], entity_id=r.get("owner_entity_id", ""),
                    amount=wo_amount, reason=notes or "scrap retur",
                    label=f"{r.get('roll_number') or r['id']} (retur {ret_number})")
                if je:
                    roll_set["writeoff_je_id"] = je.get("id")
                    roll_set["writeoff_je_number"] = je.get("number")
                    roll_set["writeoff_amount"] = wo_amount
                    roll_set["writeoff_at"] = now
                    writeoff_total = round(writeoff_total + wo_amount, 2)
                    writeoff_jes.append({"roll_id": r["id"], "je_id": je.get("id"),
                                         "je_number": je.get("number"), "amount": wo_amount})
                    wo_note = f" · write-off {je.get('number')} {rupiah(wo_amount)}"
                else:
                    # sudah pernah diposting (idempotent) — tetap tandai untuk UI
                    prior = await db.journal_entries.find_one(
                        {"source_type": "inventory_writeoff", "source_id": r["id"]},
                        {"_id": 0, "id": 1, "number": 1})
                    if prior:
                        roll_set["writeoff_je_id"] = prior.get("id")
                        roll_set["writeoff_je_number"] = prior.get("number")
                        roll_set["writeoff_amount"] = wo_amount
        _roll_update: Dict[str, Any] = {"$set": roll_set}
        if grade_hist_entry:
            _roll_update["$push"] = {"grade_history": grade_hist_entry}
        await db.inventory_rolls.update_one({"id": r["id"]}, _roll_update)
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": r["product_id"], "warehouse_id": r["warehouse_id"],
            "owner_entity_id": r["owner_entity_id"],
            "type": "quarantine_release" if new_status == "available" else "quarantine_scrap",
            "movement_type": ("quarantine_release" if new_status == "available"
                              else "quarantine_scrap"),
            "direction": "internal", "quantity": round(float(r.get("length_remaining", r.get("length", 0)) or 0), 2),
            "unit": "meter", "roll_id": r["id"],
 # FASE U — satu baris mutasi menunjuk SATU roll fisik.
 "qty_rolls": (1 if r["id"] else None), "ref_type": "sales_return", "ref_id": return_id,
            "notes": f"Release karantina retur → {new_status} (grade {grade}){regrade_note}{wo_note}",
            "source_document": return_id, "timestamp": now,
        })
        combos.add((r["product_id"], r["warehouse_id"], r["owner_entity_id"]))
    for (pid, wid, eid) in combos:
        await rebuild_balance(pid, wid, eid)
    await db.sales_returns.update_one(
        {"id": return_id},
        {"$set": {"quarantine_released": True, "quarantine_released_by": actor,
                  "quarantine_released_at": now, "quarantine_release_notes": notes,
                  "updated_at": now}})
    ret = await db.sales_returns.find_one({"id": return_id})
    ret.pop("_id", None)
    ret["_release_summary"] = {"released": released, "scrapped": scrapped, "regraded": regraded,
                               "writeoff_total": writeoff_total, "writeoff_jes": writeoff_jes}
    return ret


# ─── R3 — CROSS-ENTITY: pindah kepemilikan roll retur (GL-safe, reuse inter-co) ──

async def interco_origin_of_roll(roll: Dict[str, Any]) -> Dict[str, Any]:
    """E9.3 — apakah roll ini berasal dari **pembelian internal antar-PT**?

    Dua sumber penanda: jejak yang diwarisi roll retur (`origin_interco_pair_id`,
    E9.5) dan penilaian ulang roll saat barang antar-PT diterima
    (`cost_basis.source == "interco_purchase"`).
    """
    pair_id = (roll.get("origin_interco_pair_id") or "").strip()
    number = (roll.get("origin_interco_number") or "").strip()
    if not pair_id:
        cb = roll.get("cost_basis") or {}
        if isinstance(cb, dict) and cb.get("source") == "interco_purchase":
            pair_id = (cb.get("interco_pair_id") or "").strip()
            number = (cb.get("interco_number") or "").strip()
    if not pair_id:
        return {}
    seller = await db.interco_transactions.find_one(
        {"pair_id": pair_id, "role": "seller"},
        {"_id": 0, "id": 1, "number": 1, "status": 1, "seller_entity_id": 1,
         "seller_entity_name": 1, "buyer_entity_id": 1, "buyer_entity_name": 1}) or {}
    buyer = await db.interco_transactions.find_one(
        {"pair_id": pair_id, "role": "buyer"}, {"_id": 0, "id": 1, "number": 1}) or {}
    return {
        "pair_id": pair_id,
        "interco_id": seller.get("id", ""),
        "number": number or seller.get("number", ""),
        "buyer_doc_number": buyer.get("number", ""),
        "status": seller.get("status", ""),
        "seller_entity_id": seller.get("seller_entity_id", ""),
        "seller_entity_name": seller.get("seller_entity_name", ""),
        "buyer_entity_id": seller.get("buyer_entity_id", ""),
        "buyer_entity_name": seller.get("buyer_entity_name", ""),
    }


async def transfer_return_roll_ownership(return_id: str, roll_id: str,
                                         dest_entity_id: str, actor: str, notes: str = "") -> Dict[str, Any]:
    """R3 §I — pindahkan KEPEMILIKAN roll retur ke entitas lain (lokasi fisik TETAP).
    Reuse engine transfer antar-PT: `execute_ownership_transfer` (owner src→dst, movement
    ownership_transfer_out/in, rebuild balance) + `gl_service.post_intercompany_transfer`
    (Dr IC-AR/Cr Persediaan @src; Dr Persediaan/Cr IC-AP @dst, at-cost, idempotent).
    Syarat: roll milik retur ini, sudah `available` (di-release dari karantina), owner ≠ tujuan.

    FASE E-9 (E9.3) — **jalur ini DITOLAK bila barangnya berasal dari pembelian
    internal antar-PT.** Alasannya bukan selera: jalur at-cost tidak memperbarui
    `returned_qty` transaksi asal (barang yang sama bisa diretur dua kali), tidak
    membalik PPN, memindahkan uang di HARGA POKOK sehingga saldo pasangan PT tidak
    akan pernah nol, dan tidak memperbarui eliminasi margin di konsolidasi (laba grup
    tetap kembung). Untuk peristiwa itu sudah ada satu jalan yang benar — **Retur
    Antar-PT** — lengkap dengan dokumen kembar, alasan wajib, dan dual-control.
    """
    from services.roll_service import execute_ownership_transfer
    ret = await db.sales_returns.find_one({"id": return_id})
    if not ret:
        raise ValueError(f"Return {return_id} tidak ditemukan")
    roll = await db.inventory_rolls.find_one(
        {"id": roll_id, "return_id": return_id, "origin_type": "return"}, {"_id": 0})
    if not roll:
        raise ValueError("Roll retur tidak ditemukan untuk dokumen ini")
    src = roll.get("owner_entity_id") or ""
    if not dest_entity_id:
        raise ValueError("Entitas tujuan wajib diisi")
    if dest_entity_id == src:
        raise ValueError("Entitas tujuan harus berbeda dari pemilik saat ini")
    dst_ent = await db.business_entities.find_one({"id": dest_entity_id}, {"_id": 0})
    if not dst_ent:
        raise ValueError(f"Entitas tujuan {dest_entity_id} tidak ditemukan")
    if roll.get("status") != "available":
        raise ValueError(
            "Hanya roll 'available' (sudah di-release dari karantina) yang bisa dipindah kepemilikannya.")
    # E9.3 — rambu SATU JALAN untuk satu peristiwa.
    ic = await interco_origin_of_roll(roll)
    if ic:
        raise ValueError(
            f"Barang ini berasal dari pembelian internal {ic.get('number') or ic.get('pair_id')} "
            f"({ic.get('seller_entity_name') or 'badan usaha lain'} → "
            f"{ic.get('buyer_entity_name') or 'badan usaha ini'}), jadi pengembaliannya "
            f"WAJIB lewat Retur Antar-PT — bukan pindah kepemilikan harga pokok. "
            f"Hanya jalur Retur Antar-PT yang memperbarui jumlah yang sudah diretur pada "
            f"transaksi asal (supaya barang yang sama tidak bisa diretur dua kali), "
            f"membalik PPN, mengecilkan saldo utang/piutang antar-PT, dan memperbarui "
            f"eliminasi margin di laporan konsolidasi. Buka Antar Entitas → Retur Antar-PT "
            f"atas dokumen {ic.get('number') or ''}, lalu pilih roll retur ini.")

    now = now_iso()
    transfer_id = new_id("xfer")
    qty = round(float(roll.get("length_remaining", roll.get("length", 0)) or 0), 2)
    # Reservasi roll SPESIFIK ini untuk transfer (agar execute_ownership_transfer memindah tepat roll ini).
    upd = await db.inventory_rolls.update_one(
        {"id": roll_id, "status": "available"},
        {"$set": {"status": "reserved", "reserved_ref": {"type": "transfer", "id": transfer_id},
                  "updated_at": now}})
    if upd.modified_count != 1:
        raise ValueError("Roll berubah status saat memulai transfer. Coba lagi.")

    transfer = {
        "id": transfer_id,
        "code": f"RTNX-{ret['number'][-5:]}-{roll_id[-4:]}",
        "transfer_kind": "inter_entity",
        "entity_id": src,   # FASE E-0 (L14)
        "source_entity_id": src, "dest_entity_id": dest_entity_id,
        "source_warehouse_id": roll.get("warehouse_id", ""),
        "dest_warehouse_id": roll.get("warehouse_id", ""),   # lokasi fisik tetap
        "status": "completed",
        "items": [{"product_id": roll["product_id"], "qty": qty, "quantity": qty}],
        "origin_sales_return_id": return_id, "origin_roll_id": roll_id,
        "notes": notes, "requested_by": actor,
        "approved_by": actor, "approved_at": now,
        "created_by": actor, "created_at": now, "updated_at": now,
    }
    try:
        moved = await execute_ownership_transfer(transfer)
        je = await gl_service.post_intercompany_transfer(transfer)
    except Exception:
        # rollback reservasi bila gagal
        await db.inventory_rolls.update_one(
            {"id": roll_id, "reserved_ref.id": transfer_id},
            {"$set": {"status": "available", "reserved_ref": None, "updated_at": now_iso()}})
        raise
    transfer["ownership_moved"] = moved
    transfer["je_intercompany"] = je
    from services import line_scope as _lines            # FASE L
    await _lines.stamp_doc(db, transfer)
    await db.warehouse_transfers.insert_one(dict(transfer))
    await db.sales_returns.update_one(
        {"id": return_id},
        {"$push": {"ownership_transfers": {
            "transfer_id": transfer_id, "code": transfer["code"], "roll_id": roll_id,
            "from_entity": src, "to_entity": dest_entity_id, "qty": qty,
            "je_posted": je.get("posted"), "je_total": je.get("total", 0), "at": now}},
         "$set": {"updated_at": now}})
    updated_roll = await db.inventory_rolls.find_one({"id": roll_id}, {"_id": 0})
    return {"transfer_id": transfer_id, "code": transfer["code"], "from_entity": src,
            "to_entity": dest_entity_id, "qty": qty, "moved": moved, "je": je, "roll": updated_roll}


async def settle_return(return_id: str, actor: str, outcome: str,
                        item_decisions: List[Dict] = None, notes: str = "",
                        return_warehouse_id: str = "", refund_account_code: str = "") -> Dict[str, Any]:
    """Selesaikan retur dengan salah satu outcome finansial (R1):
      refund       → Credit Note + refund (tunai/AR) + barang masuk stok → refund_settled
      store_credit → Credit Note (potong bon) + barang masuk stok → credit_settled (ledger saldo di R5)
      nego         → Credit Note diskon TANPA gerak stok → nego_settled

    R3 — `return_warehouse_id`: LOKASI fisik gudang penerimaan (owner TETAP = entity SO agar
      COGS-reversal & subledger persediaan rekonsiliasi di satu entitas; perubahan kepemilikan
      lintas-entitas via transfer inter-entity yang GL-balanced). Default cerdas bila kosong.

    Partial per item/roll: `item_decisions` = [{index|product_id, outcome, settle_qty}].
      - item outcome "reject" → item dikecualikan dari penyelesaian (sisa bisa dikirim-ulang).
      - settle_qty (-1 = penuh) membatasi qty yang diselesaikan.
    Idempotent: bila sudah settled dgn outcome sama → kembalikan dokumen apa adanya."""
    ret = await db.sales_returns.find_one({"id": return_id})
    if not ret:
        raise ValueError(f"Return {return_id} tidak ditemukan")
    if outcome not in st.SETTLE_OUTCOMES:
        raise ValueError(
            f"Outcome settle tidak valid: '{outcome}'. Pilihan: {', '.join(sorted(st.SETTLE_OUTCOMES))} "
            "(gunakan endpoint reject untuk menolak).")

    target = st.state_for_outcome(outcome)
    # Idempotency: sudah di state target dengan outcome sama.
    if ret["status"] == target and ret.get("outcome") == outcome:
        ret.pop("_id", None)
        return ret
    st.assert_transition(ret["status"], target)

    # Bangun keputusan per item (partial/reject).
    decisions = item_decisions or []
    d_by_idx: Dict[int, Dict] = {}
    d_by_pid: Dict[str, Dict] = {}
    for d in decisions:
        if d.get("index", -1) is not None and int(d.get("index", -1)) >= 0:
            d_by_idx[int(d["index"])] = d
        if d.get("product_id"):
            d_by_pid[d["product_id"]] = d

    items = ret.get("items", [])
    effective: List[Dict] = []
    for i, it in enumerate(items):
        d = d_by_idx.get(i) or d_by_pid.get(it.get("product_id")) or {}
        item_outcome = d.get("outcome") or outcome
        full_qty = float(it.get("quantity_returned", 0) or 0)
        sq = d.get("settle_qty", -1)
        try:
            sq = float(sq)
        except (ValueError, TypeError):
            sq = -1
        qty = full_qty if sq < 0 else max(0.0, min(sq, full_qty))
        it["settle_outcome"] = item_outcome
        it["settled_qty"] = round(qty, 2)
        if item_outcome == st.OUTCOME_REJECT or qty <= 0:
            continue
        effective.append({**it, "quantity_returned": qty})

    now = now_iso()
    settlement: Dict[str, Any] = {"outcome": outcome, "settled_at": now, "settled_by": actor}
    cn_fields: Dict[str, Any] = {}

    if effective:
        post_stock = outcome in (st.OUTCOME_REFUND, st.OUTCOME_STORE_CREDIT)
        settlement_type = None if outcome == st.OUTCOME_REFUND else \
            ("store_credit" if outcome == st.OUTCOME_STORE_CREDIT else "nego")
        # R3 — tujuan penerimaan: LOKASI dipilih user; OWNER tetap = entity SO (GL-safe).
        dest_warehouse = return_warehouse_id or await _resolve_return_warehouse(ret["order_id"])
        dest_owner = ret.get("entity_id", "")
        # tandai outcome + tujuan di dokumen agar CN & audit mencatatnya
        await db.sales_returns.update_one({"id": return_id}, {"$set": {
            "outcome": outcome,
            "return_warehouse_id": dest_warehouse,
            "return_owner_entity_id": dest_owner}})
        ret["outcome"] = outcome
        # Barang masuk stok (refund/store_credit) — idempotent via stock_adjusted.
        if post_stock and not ret.get("stock_adjusted"):
            await _restock_returned_items(ret, effective, now,
                                          warehouse_id=dest_warehouse, owner_entity_id=dest_owner)
        try:
            cn = await _create_credit_note_and_post_gl(
                ret, items=effective, post_stock=post_stock, settlement_type=settlement_type,
                refund_account_code=refund_account_code)
            cn_fields = {"credit_note_id": cn["id"], "credit_note_number": cn["number"],
                         "credit_note_amount": cn["gross_amount"]}
            settlement.update({"credit_note_number": cn["number"], "gross_amount": cn["gross_amount"],
                               "net_amount": cn.get("net_amount", 0), "settlement": cn.get("settlement", "")})
            # R5.3 — refund TUNAI: catat mutasi kas keluar (buku kas/bank) + akun terpilih.
            if cn.get("settlement") == "cash" and float(cn.get("gross_amount", 0) or 0) > 0:
                try:
                    from services import cash_ledger
                    acc = refund_account_code or "1-1100"
                    ctxn = await cash_ledger.record_return_cash(
                        direction="out", amount=cn["gross_amount"], account_code=acc,
                        category="Refund Retur Jual",
                        description=f"Refund tunai retur {ret.get('number', '')} → {ret.get('customer_name', '')}",
                        entity_id=ret.get("entity_id", ""), ref_type="sales_return", ref_id=ret["id"],
                        journal_entry_id=cn.get("journal_entry_id", ""), created_by=actor)
                    if ctxn:
                        settlement["cash_txn_id"] = ctxn.get("id")
                        settlement["cash_txn_number"] = ctxn.get("number")
                        settlement["refund_account_code"] = acc
                except Exception as e:  # noqa: BLE001
                    import logging
                    logging.getLogger("cash.refund").exception(
                        "Gagal catat kas refund retur %s: %s", return_id, e)
            if outcome == st.OUTCOME_STORE_CREDIT:
                # R5.2 — terbitkan saldo store credit ke ledger pelanggan (idempotent).
                settlement["store_credit_amount"] = cn["gross_amount"]
                try:
                    from services import store_credit_service as _sc
                    sc_entry = await _sc.issue(
                        customer_id=ret.get("customer_id"), entity_id=ret.get("entity_id", ""),
                        amount=cn["gross_amount"], ref_type="sales_return", ref_id=ret["id"],
                        ref_number=cn["number"], actor=actor, je_id=cn.get("journal_entry_id", ""),
                        customer_name=ret.get("customer_name", ""))
                    if sc_entry:
                        settlement["store_credit_ledger_id"] = sc_entry.get("id")
                        settlement["store_credit_balance_after"] = sc_entry.get("balance_after")
                except Exception as e:  # noqa: BLE001
                    import logging
                    logging.getLogger("store_credit").exception(
                        "Gagal terbitkan store credit retur %s: %s", return_id, e)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger("gl.sales_return").exception(
                "Gagal Credit Note/GL settle retur %s: %s", return_id, e)

    update = {
        "status": target, "outcome": outcome, "items": items,
        "settlement": settlement, "settled_by": actor, "settled_at": now,
        "settle_notes": notes, "updated_at": now,
    }
    if outcome in (st.OUTCOME_REFUND, st.OUTCOME_STORE_CREDIT) and effective:
        update["stock_adjusted"] = True
    update.update(cn_fields)
    await db.sales_returns.update_one({"id": return_id}, {"$set": update})
    ret = await db.sales_returns.find_one({"id": return_id})
    ret.pop("_id", None)
    return ret


# ─── R5.4 — REVERSAL / KOREKSI settle (settled → cancelled, GL-safe & append-only) ──

async def reverse_settlement(return_id: str, actor: str, reason: str = "") -> Dict[str, Any]:
    """R5.4 — Batalkan/koreksi penyelesaian retur jual yang salah, aman terhadap integritas GL.

    Membalik: JE sales_return (revenue/PPN/piutang/kas/store-credit + HPP/persediaan), menghapus
    roll restock (kembalikan subledger sesuai GL yang dibalik), void cash refund, void entri ledger
    store credit `issue`, void Credit Note; retur → `cancelled` (append-only, history utuh).

    Guard ketat agar tak merusak data hilir:
      - hanya dari state settled; belum pernah di-reversal (idempotent);
      - karantina belum dilepas & roll retur masih utuh di karantina (tak dikomit/dipesan/terpakai);
      - bila outcome store_credit → saldo terbit belum dipakai.
    """
    ret = await db.sales_returns.find_one({"id": return_id})
    if not ret:
        raise ValueError(f"Return {return_id} tidak ditemukan")
    ret.pop("_id", None)
    status = ret.get("status")
    # Idempotent: sudah dibatalkan/di-reversal.
    if ret.get("reversed") or status == st.CANCELLED:
        return ret
    if status not in st.SETTLED_STATES:
        raise ValueError(
            f"Hanya retur yang sudah diselesaikan (settled) yang bisa di-reversal. Status saat ini: '{status}'.")

    outcome = ret.get("outcome", "")
    now = now_iso()

    # ── GUARDS ────────────────────────────────────────────────────────────────
    if ret.get("quarantine_released"):
        raise ValueError(
            "Roll retur sudah dilepas dari karantina (release/scrap). Reversal otomatis tidak aman — "
            "lakukan koreksi manual di jurnal.")
    rolls = await db.inventory_rolls.find(
        {"return_id": return_id, "origin_type": "return"}, {"_id": 0}).to_list(500)
    for r in rolls:
        rlabel = r.get("roll_no") or r.get("id")
        if r.get("status") != "quarantine":
            raise ValueError(f"Roll {rlabel} sudah tidak di karantina (status '{r.get('status')}'). Reversal dibatalkan.")
        if r.get("committed_to") or r.get("reserved_ref") or r.get("earmarked_for"):
            raise ValueError(f"Roll {rlabel} sudah dipesan/dikomit ke transaksi lain. Reversal dibatalkan.")
        if round(float(r.get("length_remaining", 0) or 0), 2) != round(float(r.get("length", 0) or 0), 2):
            raise ValueError(f"Roll {rlabel} sudah terpakai sebagian. Reversal dibatalkan.")

    from services import store_credit_service as _sc
    if outcome == st.OUTCOME_STORE_CREDIT:
        sc_info = await _sc.issued_from_return(return_id)
        if sc_info.get("has_issue") and not sc_info.get("fully_available"):
            raise ValueError(
                f"Store credit dari retur ini sudah dipakai sebagian (saldo {rupiah(sc_info.get('balance', 0))} "
                f"< terbit {rupiah(sc_info.get('issued', 0))}). Batalkan pemakaian store credit-nya lebih dulu.")

    # ── ACTIONS (idempotent) ────────────────────────────────────────────────
    # a) Balik JE sales_return (revenue+PPN+piutang/kas/store-credit + HPP/persediaan).
    rev_jes = await gl_service.reverse_document(
        "sales_return", return_id, reason=reason or "Pembatalan/koreksi retur jual", actor_name=actor)

    # b) Hapus roll restock + catat movement keluar + rebuild balance (subledger ikut GL yang dibalik).
    combos: set = set()
    for r in rolls:
        await db.inventory_rolls.delete_one({"id": r["id"]})
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": r.get("product_id"),
            "warehouse_id": r.get("warehouse_id"), "owner_entity_id": r.get("owner_entity_id"),
            "type": "return_reversal_out", "movement_type": "return_reversal_out",
            "direction": "out",
            "quantity": round(float(r.get("length_remaining", r.get("length", 0)) or 0), 2),
            "unit": "meter", "roll_id": r["id"],
 # FASE U — satu baris mutasi menunjuk SATU roll fisik.
 "qty_rolls": (1 if r["id"] else None), "ref_type": "sales_return", "ref_id": return_id,
            "notes": f"Reversal retur {ret.get('number', return_id)} — roll {r.get('roll_number') or r['id']} dibatalkan",
            "source_document": return_id, "timestamp": now,
        })
        if r.get("product_id") and r.get("warehouse_id"):
            combos.add((r["product_id"], r["warehouse_id"], r.get("owner_entity_id", "")))
    for (pid, wid, eid) in combos:
        await rebuild_balance(pid, wid, eid)

    # c) Void cash refund (buku kas) bila ada.
    await db.cash_transactions.update_many(
        {"ref_type": "sales_return", "ref_id": return_id, "status": {"$ne": "void"}},
        {"$set": {"status": "void", "voided_by": actor, "void_reason": reason,
                  "updated_at": now}})

    # d) Void entri ledger store credit `issue` (GL 2-1450 sudah dibalik di langkah a).
    if outcome == st.OUTCOME_STORE_CREDIT:
        await _sc.void_issue_entry(return_id=return_id, reason=reason, actor=actor)

    # e) Void Credit Note.
    await db.credit_notes.update_many(
        {"return_id": return_id, "status": {"$ne": "void"}},
        {"$set": {"status": "void", "reversed": True, "reversed_at": now,
                  "reversal_reason": reason, "updated_at": now}})

    # f) Retur → cancelled + metadata reversal (append-only).
    st.assert_transition(status, st.CANCELLED)
    update = {
        "status": st.CANCELLED, "reversed": True, "reversed_by": actor, "reversed_at": now,
        "reversal_reason": reason, "reversal_je_ids": [j.get("id") for j in rev_jes],
        "stock_adjusted": False, "updated_at": now,
    }
    await db.sales_returns.update_one({"id": return_id}, {"$set": update})
    ret = await db.sales_returns.find_one({"id": return_id})
    ret.pop("_id", None)
    ret["_reversal_summary"] = {"reversal_jes": len(rev_jes), "rolls_removed": len(rolls),
                                "outcome": outcome}
    return ret


# ─── R5.4b — REVERSAL WRITE-OFF (un-scrap) roll retur karantina ──────────────

async def reverse_writeoff(return_id: str, actor: str, roll_ids: List[str] = None,
                           reason: str = "", restore_status: str = "available") -> Dict[str, Any]:
    """R5.4b — Batalkan write-off (scrap) roll retur & KEMBALIKAN roll fisik ke stok.

    Untuk tiap roll `damaged` hasil scrap (punya `writeoff_je_id`) milik retur ini:
      a) balik jurnal write-off (source_type='inventory_writeoff') → Dr 1-1300 / Cr 5-9500
         (nilai persediaan GL dipulihkan),
      b) roll dipulihkan: status damaged → `restore_status` (default 'available'), length utuh
         (scrap tak mengurangi length), tandai writeoff_reversed=True,
      c) catat movement `writeoff_reversal` (masuk) + rebuild_balance segmen.

    Append-only & idempotent (roll yg sudah writeoff_reversed dilewati; reverse JE idempotent).
    """
    ret = await db.sales_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError(f"Return {return_id} tidak ditemukan")
    q = {"return_id": return_id, "origin_type": "return", "status": "damaged"}
    scrapped = await db.inventory_rolls.find(q, {"_id": 0}).to_list(500)
    if roll_ids:
        want = set(roll_ids)
        scrapped = [r for r in scrapped if r.get("id") in want]
    targets = [r for r in scrapped if r.get("writeoff_je_id") and not r.get("writeoff_reversed")]
    if not targets:
        raise ValueError(
            "Tidak ada roll write-off (scrap) yang bisa dibatalkan untuk retur ini "
            "(hanya roll ber-status 'damaged' dengan jurnal write-off & belum dibalik).")

    now = now_iso()
    combos: set = set()
    detail: List[Dict[str, Any]] = []
    total = 0.0
    for r in targets:
        rid = r["id"]
        rev = await gl_service.reverse_document(
            "inventory_writeoff", rid,
            reason=reason or "Batalkan write-off (un-scrap) roll retur", actor_name=actor)
        rev_je = rev[0] if rev else {}
        qty = round(float(r.get("length_remaining", r.get("length", 0)) or 0), 2)
        await db.inventory_rolls.update_one({"id": rid}, {"$set": {
            "status": restore_status, "qc_status": "released",
            "writeoff_reversed": True, "writeoff_reversed_at": now, "writeoff_reversed_by": actor,
            "writeoff_reversal_reason": reason,
            "writeoff_reversal_je_id": rev_je.get("id", ""),
            "writeoff_reversal_je_number": rev_je.get("number", ""),
            "unscrapped_from": "damaged", "updated_at": now}})
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": r.get("product_id"),
            "warehouse_id": r.get("warehouse_id"), "owner_entity_id": r.get("owner_entity_id"),
            "type": "writeoff_reversal", "movement_type": "writeoff_reversal", "direction": "in",
            "quantity": qty, "unit": "meter", "roll_id": rid,
 # FASE U — satu baris mutasi menunjuk SATU roll fisik.
 "qty_rolls": (1 if rid else None),
            "ref_type": "sales_return", "ref_id": return_id, "source_document": return_id,
            "notes": f"Batalkan write-off (un-scrap) roll {r.get('roll_no') or rid} — "
                     f"kembali ke stok ({restore_status})",
            "timestamp": now})
        total = round(total + float(r.get("writeoff_amount", 0) or 0), 2)
        detail.append({"roll_id": rid, "roll_no": r.get("roll_no", ""),
                       "reversal_je": rev_je.get("number", ""),
                       "amount": float(r.get("writeoff_amount", 0) or 0)})
        if r.get("product_id") and r.get("warehouse_id"):
            combos.add((r["product_id"], r["warehouse_id"], r.get("owner_entity_id", "")))
    for (pid, wid, eid) in combos:
        await rebuild_balance(pid, wid, eid)

    ret = await db.sales_returns.find_one({"id": return_id})
    ret.pop("_id", None)
    ret["_writeoff_reversal_summary"] = {"rolls": len(detail), "amount": total, "detail": detail}
    return ret


# ─── REJECT : (pending_approval|approved|inspecting|inspected) → rejected ────

async def reject_return(return_id: str, rejected_by: str, reason: str) -> Dict[str, Any]:
    ret = await db.sales_returns.find_one({"id": return_id})
    if not ret:
        raise ValueError(f"Return {return_id} tidak ditemukan")
    st.assert_transition(ret["status"], st.REJECTED)
    now = now_iso()
    await db.sales_returns.update_one(
        {"id": return_id},
        {"$set": {"status": st.REJECTED, "outcome": st.OUTCOME_REJECT,
                  "rejected_by": rejected_by, "rejected_at": now,
                  "reject_reason": reason, "updated_at": now}})
    ret = await db.sales_returns.find_one({"id": return_id})
    ret.pop("_id", None)
    return ret


# ─── HELPER: resolve warehouse ───────────────────────────────────────────────

async def _resolve_return_warehouse(order_id: str) -> str:
    """Cari warehouse dari outbound task atau fallback ke gudang pertama."""
    task = await db.wms_tasks.find_one(
        {"order_id": order_id, "type": "outbound"},
        sort=[("created_at", -1)]
    )
    if task and task.get("warehouse_id"):
        return task["warehouse_id"]

    wh = await db.warehouses.find_one({}, sort=[("created_at", 1)])
    return wh["id"] if wh else "wh_default"
