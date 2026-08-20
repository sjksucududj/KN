"""FASE G-2 — **RENCANA PEMBAYARAN FLEKSIBEL** (`payment_plans`).

MASALAH NYATA PEMILIK
---------------------
Term pembayaran di sistem hanya kode kaku (`NET30`). Kenyataan lapangan jauh lebih cair:

  * "DP 15% + 6× cicilan bulanan"
  * "DP 30% + pelunasan 45 hari"
  * milestone: 30% saat PO, 40% saat kirim, 30% saat terima barang

Karena tidak ada tempat menyimpan jadwal itu, penagihan mengandalkan ingatan orang dan
laporan Umur Piutang tidak pernah tahu kapan sebenarnya uang dijanjikan masuk.

DESAIN
------
Satu dokumen **Rencana Pembayaran** per dokumen sumber (SO), bernomor (`<ENT>/RPB-#####`)
sehingga bisa dicetak, ditelusuri (FASE G-4 `refs[]`), dan diaudit. Template hanya
**titik awal** — barisnya bisa diubah bebas.

Baris (`lines[]`):
    seq · kind (dp|installment|retention|milestone) · label · basis (percent|amount) ·
    percent · amount · due_rule (net_days|monthly|weekly|fixed_date) · due_date ·
    status (open|partial|paid) · paid_amount

INVARIAN
--------
* **INV-PAY-01** Σ `lines[].amount` == nilai dokumen (toleransi `payment.plan_tolerance_rupiah`).
* **INV-PAY-02** `paid_amount` per baris tidak melebihi nominal baris, dan Σ terbayar pada
  rencana == pembayaran yang benar-benar tercatat di dokumen sumber (tidak ada uang hantu).

Pembayaran TIDAK dicatat dua kali: SSOT tetap `sales_orders.payments[]`. Rencana pembayaran
hanya **mengalokasikan** total terbayar itu ke barisnya secara berurutan (waterfall), sehingga
angka di jadwal tidak mungkin berbeda dari kas yang benar-benar masuk.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from core_utils import new_id, next_doc_number, now_iso, safe_doc, rupiah
from db import db
from services.config_resolver import resolve

COLL = "payment_plans"
EPS = 0.01

MODES = ("dp_installment", "milestone", "net", "custom")
KINDS = ("dp", "installment", "retention", "milestone")
DUE_RULES = ("net_days", "monthly", "weekly", "fixed_date")
LINE_STATUSES = ("open", "partial", "paid")
PLAN_STATUSES = ("active", "closed", "void")

MODE_LABEL = {
    "dp_installment": "DP + Cicilan",
    "milestone": "Milestone (tahap pekerjaan)",
    "net": "Sekali bayar (NET)",
    "custom": "Bebas / campuran",
}
KIND_LABEL = {
    "dp": "Uang Muka (DP)",
    "installment": "Cicilan",
    "retention": "Retensi",
    "milestone": "Milestone",
}


class PlanError(ValueError):
    """Kesalahan rencana pembayaran dengan pesan siap tampil (Bahasa Indonesia)."""


# ── Kebijakan (registry FASE G-0 — tidak ada angka hardcode) ───────────────
async def plan_policy(entity_id: str = "", customer_id: str = "") -> Dict[str, Any]:
    ctx = {"entity_id": entity_id or "", "customer_id": customer_id or ""}

    async def val(key: str) -> Any:
        return (await resolve(key, ctx))["value"]

    return {
        "required_above_amount": float(await val("payment.plan_required_above_amount") or 0),
        "tolerance": float(await val("payment.plan_tolerance_rupiah") or 1),
        "dp_percent": float(await val("payment.default_dp_percent") or 0),
        "installments": int(await val("payment.default_installments") or 1),
        "interval": str(await val("payment.default_installment_interval") or "monthly"),
    }


# ── Util tanggal ───────────────────────────────────────────────────────────
def _d(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    txt = str(value or "")[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt[: len(fmt) - 2 if "T" in fmt else 10], fmt).replace(
                tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _add_months(base: datetime, months: int) -> datetime:
    """Tambah bulan tanpa dependensi eksternal; tanggal 31 diaman-kan ke akhir bulan."""
    y = base.year + (base.month - 1 + months) // 12
    m = (base.month - 1 + months) % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return base.replace(year=y, month=m, day=min(base.day, last))


def due_from_rule(base_date: Any, rule: str, seq_index: int = 0, net_days: int = 0,
                  fixed_date: str = "", interval: str = "monthly") -> str:
    """Hitung tanggal jatuh tempo satu baris (deterministik & bisa diaudit)."""
    base = _d(base_date)
    if rule == "fixed_date" and fixed_date:
        return str(fixed_date)[:10]
    if rule == "net_days":
        return (base + timedelta(days=int(net_days or 0))).date().isoformat()
    if rule == "weekly":
        return (base + timedelta(weeks=max(1, seq_index))).date().isoformat()
    if rule == "monthly":
        return _add_months(base, max(1, seq_index)).date().isoformat()
    return base.date().isoformat()


# ── Pembentuk baris dari template (titik AWAL, bukan penjara) ─────────────
def build_lines(mode: str, total: float, *, base_date: Any, policy: Dict[str, Any],
                dp_percent: Optional[float] = None, installments: Optional[int] = None,
                interval: Optional[str] = None, net_days: int = 30,
                milestones: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Hasilkan `lines[]` yang Σ-nya PASTI sama dengan `total` (sisa pembulatan ke baris akhir)."""
    total = round(float(total or 0), 2)
    if total <= 0:
        raise PlanError("Nilai dokumen belum ada — rencana pembayaran tidak bisa dibentuk.")
    itv = (interval or policy["interval"] or "monthly").lower()
    lines: List[Dict[str, Any]] = []

    def add(kind: str, label: str, amount: float, rule: str, seq_index: int,
            percent: float = 0.0, fixed: str = "", basis: str = "amount") -> None:
        lines.append({
            "seq": len(lines) + 1, "kind": kind, "label": label,
            "basis": basis, "percent": round(float(percent or 0), 4),
            "amount": round(float(amount or 0), 2),
            "due_rule": rule,
            "due_date": due_from_rule(base_date, rule, seq_index, net_days, fixed, itv),
            "status": "open", "paid_amount": 0.0,
        })

    if mode == "net":
        add("installment", f"Pelunasan NET {int(net_days)} hari", total, "net_days", 0,
            percent=100.0, basis="percent")
    elif mode == "dp_installment":
        pct = float(dp_percent if dp_percent is not None else policy["dp_percent"])
        n = int(installments if installments is not None else policy["installments"])
        n = max(1, n)
        dp_amount = round(total * pct / 100.0, 2)
        if dp_amount > 0:
            add("dp", f"Uang Muka (DP) {pct:g}%", dp_amount, "net_days", 0,
                percent=pct, basis="percent")
        rest = round(total - dp_amount, 2)
        each = round(rest / n, 2)
        for i in range(n):
            amt = each if i < n - 1 else round(rest - each * (n - 1), 2)
            add("installment", f"Cicilan {i + 1}/{n}", amt,
                "monthly" if itv == "monthly" else "weekly", i + 1)
    elif mode == "milestone":
        ms = milestones or [{"label": "Saat pesanan disetujui", "percent": 30, "offset_days": 0},
                            {"label": "Saat barang dikirim", "percent": 40, "offset_days": 14},
                            {"label": "Saat barang diterima", "percent": 30, "offset_days": 30}]
        acc = 0.0
        for i, m in enumerate(ms):
            pct = float(m.get("percent") or 0)
            amt = round(total * pct / 100.0, 2) if i < len(ms) - 1 else round(total - acc, 2)
            acc = round(acc + amt, 2)
            add("milestone", str(m.get("label") or f"Milestone {i + 1}"), amt, "net_days",
                i, percent=pct, basis="percent")
            lines[-1]["due_date"] = due_from_rule(
                base_date, "net_days", i, int(m.get("offset_days") or 0))
    else:  # custom → satu baris penuh sebagai titik awal untuk diubah user
        add("installment", "Pembayaran 1", total, "net_days", 0, percent=100.0, basis="percent")

    # Kunci: Σ baris HARUS = total. Sisa pembulatan dibebankan ke baris terakhir.
    diff = round(total - sum(l["amount"] for l in lines), 2)
    if abs(diff) > 0 and lines:
        lines[-1]["amount"] = round(lines[-1]["amount"] + diff, 2)
    return lines


# ── Validasi ───────────────────────────────────────────────────────────────
def _normalize_lines(raw: List[Dict[str, Any]], total: float) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, r in enumerate(raw or []):
        kind = str(r.get("kind") or "installment")
        if kind not in KINDS:
            raise PlanError(f"Jenis baris '{kind}' tidak dikenal.")
        rule = str(r.get("due_rule") or "fixed_date")
        if rule not in DUE_RULES:
            raise PlanError(f"Aturan jatuh tempo '{rule}' tidak dikenal.")
        basis = "percent" if str(r.get("basis") or "amount") == "percent" else "amount"
        percent = round(float(r.get("percent") or 0), 4)
        amount = round(float(r.get("amount") or 0), 2)
        if basis == "percent" and percent > 0 and amount <= 0:
            amount = round(float(total) * percent / 100.0, 2)
        if amount <= 0:
            raise PlanError(f"Baris ke-{i + 1} ('{r.get('label') or kind}') bernilai 0 — "
                            "isi nominal atau persennya.")
        out.append({
            "seq": i + 1, "kind": kind, "label": str(r.get("label") or KIND_LABEL[kind]),
            "basis": basis, "percent": percent, "amount": amount,
            "due_rule": rule, "due_date": str(r.get("due_date") or "")[:10],
            "status": str(r.get("status") or "open"),
            "paid_amount": round(float(r.get("paid_amount") or 0), 2),
        })
    if not out:
        raise PlanError("Rencana pembayaran harus punya minimal satu baris.")
    return out


def check_total(lines: List[Dict[str, Any]], total: float, tolerance: float) -> Tuple[bool, float]:
    diff = round(float(total) - sum(float(l["amount"]) for l in lines), 2)
    return abs(diff) <= float(tolerance) + 0.0001, diff


# ── Dokumen sumber ─────────────────────────────────────────────────────────
async def _load_source(doc_type: str, doc_id: str) -> Dict[str, Any]:
    if doc_type != "sales_order":
        raise PlanError(f"Jenis dokumen '{doc_type}' belum didukung rencana pembayaran.")
    row = await db.sales_orders.find_one({"id": doc_id}, {"_id": 0})
    if not row:
        raise PlanError("Dokumen sumber tidak ditemukan.")
    return safe_doc(row)


def source_total(order: Dict[str, Any]) -> float:
    for k in ("grand_total", "total_amount", "amount"):
        if order.get(k) not in (None, ""):
            return round(float(order[k]), 2)
    return 0.0


def source_paid(order: Dict[str, Any]) -> float:
    pays = order.get("payments") or []
    if pays:
        return round(sum(float(p.get("amount") or 0) for p in pays), 2)
    return round(float(order.get("paid_total") or 0), 2)


# ── CRUD ───────────────────────────────────────────────────────────────────
async def get_active(doc_type: str, doc_id: str) -> Optional[Dict[str, Any]]:
    row = await db[COLL].find_one({"doc_type": doc_type, "doc_id": doc_id,
                                   "status": {"$ne": "void"}}, {"_id": 0},
                                  sort=[("created_at", -1)])
    return safe_doc(row) if row else None


async def get(plan_id: str) -> Optional[Dict[str, Any]]:
    row = await db[COLL].find_one({"id": plan_id}, {"_id": 0})
    return safe_doc(row) if row else None


async def preview(doc_type: str, doc_id: str, mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Pratinjau baris dari template TANPA menyimpan apa pun."""
    order = await _load_source(doc_type, doc_id)
    policy = await plan_policy(order.get("entity_id") or "", order.get("customer_id") or "")
    total = source_total(order)
    lines = build_lines(mode if mode in MODES else "custom", total,
                        base_date=order.get("created_at") or now_iso(), policy=policy,
                        dp_percent=params.get("dp_percent"),
                        installments=params.get("installments"),
                        interval=params.get("interval"),
                        net_days=int(params.get("net_days") or 30),
                        milestones=params.get("milestones"))
    okay, diff = check_total(lines, total, policy["tolerance"])
    return {"doc_type": doc_type, "doc_id": doc_id, "doc_number": order.get("number", ""),
            "mode": mode, "mode_label": MODE_LABEL.get(mode, mode), "total": total,
            "lines": lines, "balanced": okay, "difference": diff,
            "tolerance": policy["tolerance"], "policy": policy}


async def create_plan(doc_type: str, doc_id: str, payload: Dict[str, Any],
                      actor: Dict[str, Any]) -> Dict[str, Any]:
    order = await _load_source(doc_type, doc_id)
    entity_id = order.get("entity_id") or ""
    policy = await plan_policy(entity_id, order.get("customer_id") or "")
    total = source_total(order)
    mode = str(payload.get("mode") or "custom")
    if mode not in MODES:
        raise PlanError(f"Mode rencana '{mode}' tidak dikenal.")

    raw_lines = payload.get("lines")
    if raw_lines:
        lines = _normalize_lines(raw_lines, total)
    else:
        lines = build_lines(mode, total, base_date=order.get("created_at") or now_iso(),
                            policy=policy, dp_percent=payload.get("dp_percent"),
                            installments=payload.get("installments"),
                            interval=payload.get("interval"),
                            net_days=int(payload.get("net_days") or 30),
                            milestones=payload.get("milestones"))
    okay, diff = check_total(lines, total, policy["tolerance"])
    if not okay:
        raise PlanError(
            f"Jumlah seluruh baris belum sama dengan nilai dokumen (selisih {rupiah(diff)}). "
            f"Toleransi yang berlaku {rupiah(policy['tolerance'])}.")

    # Satu rencana aktif per dokumen: yang lama di-void (jejaknya tetap ada).
    old = await get_active(doc_type, doc_id)
    if old:
        await db[COLL].update_one({"id": old["id"]}, {"$set": {
            "status": "void", "void_reason": "diganti rencana baru",
            "voided_by": actor.get("name", ""), "updated_at": now_iso()}})

    now = now_iso()
    number = await next_doc_number(COLL, "number", "RPB-", entity_id=entity_id or None)
    penalty_cfg = payload.get("penalty") or {}
    plan = {
        "id": new_id("pyp"), "number": number, "entity_id": entity_id,
        "doc_type": doc_type, "doc_id": doc_id, "doc_number": order.get("number", ""),
        "customer_id": order.get("customer_id", ""), "customer_name": order.get("customer_name", ""),
        "mode": mode, "mode_label": MODE_LABEL.get(mode, mode),
        "total_amount": total, "lines": lines,
        "penalty": {
            "mode": str(penalty_cfg.get("mode") or ""),      # kosong = ikut kebijakan global
            "grace_days": penalty_cfg.get("grace_days"),
            "rate_pct_per_month": penalty_cfg.get("rate_pct_per_month"),
            "base": penalty_cfg.get("base") or "",
            "cap_pct": penalty_cfg.get("cap_pct"),
        },
        "note": str(payload.get("note") or ""),
        "status": "active",
        "created_by": actor.get("name", ""), "created_at": now, "updated_at": now,
        "replaces_plan_id": old["id"] if old else "",
        "refs": [],
        "explain": [
            f"Nilai dokumen {order.get('number', '')} = {rupiah(total)}",
            f"Mode {MODE_LABEL.get(mode, mode)} · {len(lines)} baris",
            f"Toleransi pembulatan {rupiah(policy['tolerance'])} (Pusat Pengaturan)",
        ],
    }
    await db[COLL].insert_one(dict(plan))
    # FASE G-4 — rencana pembayaran adalah DOKUMEN: menaut dokumen sumbernya dua arah.
    from services import doc_refs_service as _refs
    await _refs.safe_link(("payment_plan", plan["id"]), (doc_type, doc_id), "parent",
                          note="jadwal pembayaran dokumen ini")
    return await recompute_paid(plan["id"])


async def update_plan(plan_id: str, payload: Dict[str, Any],
                      actor: Dict[str, Any]) -> Dict[str, Any]:
    plan = await get(plan_id)
    if not plan:
        raise PlanError("Rencana pembayaran tidak ditemukan.")
    if plan["status"] == "void":
        raise PlanError("Rencana pembayaran sudah dibatalkan — buat rencana baru.")
    order = await _load_source(plan["doc_type"], plan["doc_id"])
    policy = await plan_policy(plan.get("entity_id") or "", plan.get("customer_id") or "")
    total = source_total(order)

    set_doc: Dict[str, Any] = {"updated_at": now_iso(), "total_amount": total,
                               "updated_by": actor.get("name", "")}
    if payload.get("mode"):
        if payload["mode"] not in MODES:
            raise PlanError(f"Mode rencana '{payload['mode']}' tidak dikenal.")
        set_doc["mode"] = payload["mode"]
        set_doc["mode_label"] = MODE_LABEL.get(payload["mode"], payload["mode"])
    if payload.get("lines") is not None:
        lines = _normalize_lines(payload["lines"], total)
        okay, diff = check_total(lines, total, policy["tolerance"])
        if not okay:
            raise PlanError(
                f"Jumlah seluruh baris belum sama dengan nilai dokumen (selisih {rupiah(diff)})."
                .replace(",", "."))
        set_doc["lines"] = lines
    if payload.get("penalty") is not None:
        p = payload["penalty"] or {}
        set_doc["penalty"] = {
            "mode": str(p.get("mode") or ""), "grace_days": p.get("grace_days"),
            "rate_pct_per_month": p.get("rate_pct_per_month"),
            "base": p.get("base") or "", "cap_pct": p.get("cap_pct"),
        }
    if payload.get("note") is not None:
        set_doc["note"] = str(payload["note"])
    await db[COLL].update_one({"id": plan_id}, {"$set": set_doc})
    return await recompute_paid(plan_id)


async def void_plan(plan_id: str, reason: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    plan = await get(plan_id)
    if not plan:
        raise PlanError("Rencana pembayaran tidak ditemukan.")
    if not (reason or "").strip():
        raise PlanError("Alasan pembatalan rencana wajib diisi.")
    await db[COLL].update_one({"id": plan_id}, {"$set": {
        "status": "void", "void_reason": reason.strip(),
        "voided_by": actor.get("name", ""), "voided_at": now_iso(),
        "updated_at": now_iso()}})
    return await get(plan_id)


# ── Alokasi pembayaran (derivasi, bukan pembukuan kedua) ──────────────────
async def _receipt_line_targets(doc_type: str, doc_id: str) -> Dict[int, float]:
    """FASE G-3 — pembayaran yang SENGAJA ditujukan ke baris jadwal tertentu.

    Kwitansi bisa menyebut `allocations[].plan_line_seq` (mis. pelanggan bilang
    "ini untuk cicilan ke-3"). Nominal itu dipasang lebih dulu ke barisnya, sisanya
    baru mengalir berurutan (waterfall). Karena angkanya tetap DITURUNKAN dari
    kwitansi yang benar-benar ada, jadwal tidak bisa bercerita beda dengan kas.
    """
    if doc_type != "sales_order":
        return {}
    out: Dict[int, float] = {}
    async for r in db.ar_receipts.find(
            {"status": {"$ne": "void"}, "allocations.order_id": doc_id},
            {"_id": 0, "allocations": 1}):
        for al in r.get("allocations") or []:
            if al.get("order_id") != doc_id:
                continue
            seq = al.get("plan_line_seq")
            try:
                seq = int(seq or 0)
            except (TypeError, ValueError):
                seq = 0
            if seq <= 0:
                continue
            out[seq] = round(out.get(seq, 0.0) + float(al.get("applied") or 0), 2)
    return out


async def recompute_paid(plan_id: str) -> Dict[str, Any]:
    """Alokasikan total pembayaran dokumen sumber ke baris.

    Urutan: (1) pembayaran yang MENYEBUT baris tujuan (`plan_line_seq` pada kwitansi),
    (2) sisanya berurutan (waterfall) ke baris terlama. Disebut ulang setiap kali
    kwitansi masuk/void. Karena angkanya DITURUNKAN dari `payments[]`, jadwal tidak
    mungkin bercerita beda dengan kas yang benar-benar masuk.
    """
    plan = await get(plan_id)
    if not plan:
        raise PlanError("Rencana pembayaran tidak ditemukan.")
    order = await _load_source(plan["doc_type"], plan["doc_id"])
    plan_total = round(float(plan["total_amount"] or 0), 2)
    budget = min(round(source_paid(order), 2), plan_total)
    targets = await _receipt_line_targets(plan["doc_type"], plan["doc_id"])

    lines = [dict(l) for l in (plan.get("lines") or [])]
    for line in lines:
        line["paid_amount"] = 0.0
        line["targeted_amount"] = 0.0

    remaining = budget
    # (1) pembayaran yang menunjuk baris tertentu
    for line in lines:
        want = round(float(targets.get(int(line.get("seq") or 0), 0.0)), 2)
        if want <= 0 or remaining <= EPS:
            continue
        take = min(want, round(float(line.get("amount") or 0), 2), remaining)
        if take <= 0:
            continue
        line["paid_amount"] = round(take, 2)
        line["targeted_amount"] = round(take, 2)
        remaining = round(remaining - take, 2)
    # (2) sisanya waterfall ke kapasitas yang masih terbuka
    for line in lines:
        if remaining <= EPS:
            break
        cap = round(float(line.get("amount") or 0) - float(line.get("paid_amount") or 0), 2)
        if cap <= 0:
            continue
        take = min(cap, remaining)
        line["paid_amount"] = round(float(line["paid_amount"]) + take, 2)
        remaining = round(remaining - take, 2)
    for line in lines:
        amt = round(float(line.get("amount") or 0), 2)
        paid = round(float(line.get("paid_amount") or 0), 2)
        line["status"] = "paid" if paid >= amt - EPS else ("partial" if paid > EPS else "open")

    total_paid = round(sum(l["paid_amount"] for l in lines), 2)
    status = plan["status"]
    if status != "void":
        status = "closed" if total_paid >= plan_total - EPS else "active"
    await db[COLL].update_one({"id": plan_id}, {"$set": {
        "lines": lines, "paid_total": total_paid,
        "outstanding": round(plan_total - total_paid, 2),
        "status": status, "updated_at": now_iso()}})
    return await get(plan_id)


async def reschedule_line(plan_id: str, seq: int, amount: float, new_due_date: str,
                          *, reason_label: str = "", note: str = "",
                          actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """FASE G-3 — sisa KURANG bayar dijadikan tempo baru (tanpa mengubah Σ rencana).

    Dua perilaku, dipilih otomatis supaya jadwalnya tetap jujur:
      * seluruh baris belum dibayar → cukup **geser tanggal** baris itu;
      * baris sudah terbayar sebagian → baris dipecah: bagian yang sudah dibayar tetap
        di baris asal, sisanya menjadi **baris baru** dengan tempo baru.

    Σ `lines[].amount` TIDAK berubah, jadi INV-PAY-01 tetap hijau.
    """
    plan = await get(plan_id)
    if not plan:
        raise PlanError("Rencana pembayaran tidak ditemukan.")
    if plan.get("status") == "void":
        raise PlanError("Rencana pembayaran sudah dibatalkan — buat rencana baru.")
    day = str(new_due_date or "")[:10]
    if not day:
        raise PlanError("Tanggal jatuh tempo baru wajib diisi.")
    amt = round(float(amount or 0), 2)
    if amt <= 0:
        raise PlanError("Nominal yang dijadwalkan ulang harus lebih dari nol.")

    lines = [dict(l) for l in (plan.get("lines") or [])]
    idx = next((i for i, l in enumerate(lines) if int(l.get("seq") or 0) == int(seq)), -1)
    if idx < 0:
        raise PlanError(f"Baris jadwal ke-{seq} tidak ditemukan pada rencana ini.")
    target = lines[idx]
    line_amount = round(float(target.get("amount") or 0), 2)
    line_paid = round(float(target.get("paid_amount") or 0), 2)
    unpaid = round(line_amount - line_paid, 2)
    if amt > unpaid + EPS:
        raise PlanError(
            f"Nominal {rupiah(amt)} melebihi sisa baris '{target.get('label')}' "
            f"({rupiah(unpaid)}).")

    old_due = str(target.get("due_date") or "")[:10]
    if line_paid <= EPS and abs(amt - line_amount) <= EPS:
        target["due_rule"] = "fixed_date"
        target["due_date"] = day
        moved_label = target.get("label", "")
        action = "digeser"
    else:
        target["amount"] = round(line_amount - amt, 2)
        base_label = str(target.get("label") or "Cicilan")
        new_line = {
            "seq": 0, "kind": target.get("kind") or "installment",
            "label": f"Sisa {base_label} (tempo baru)",
            "basis": "amount", "percent": 0.0, "amount": amt,
            "due_rule": "fixed_date", "due_date": day,
            "status": "open", "paid_amount": 0.0,
        }
        lines.insert(idx + 1, new_line)
        moved_label = new_line["label"]
        action = "dipecah"
    for i, l in enumerate(lines):
        l["seq"] = i + 1

    policy = await plan_policy(plan.get("entity_id") or "", plan.get("customer_id") or "")
    order = await _load_source(plan["doc_type"], plan["doc_id"])
    okay, diff = check_total(lines, source_total(order), policy["tolerance"])
    if not okay:
        raise PlanError(
            f"Penjadwalan ulang membuat jumlah baris tidak lagi pas (selisih {rupiah(diff)})."
            .replace(",", "."))

    history = list(plan.get("history") or [])
    history.append({
        "at": now_iso(), "by": (actor or {}).get("name", "system"),
        "action": f"reschedule:{action}", "line_seq": int(seq),
        "amount": amt, "from_due": old_due, "to_due": day,
        "reason_label": reason_label, "note": note,
    })
    await db[COLL].update_one({"id": plan_id}, {"$set": {
        "lines": lines, "history": history, "updated_at": now_iso(),
        "updated_by": (actor or {}).get("name", "")}})
    await db[COLL].update_one({"id": plan_id}, {"$push": {"explain": (
        f"Sisa {rupiah(amt)} pada '{moved_label}' {action} ke tempo {day}"
        + (f" · alasan: {reason_label}" if reason_label else "")).replace(",", ".")}})
    return await recompute_paid(plan_id)


async def recompute_for_doc(doc_type: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """Dipanggil dari jalur kwitansi (`ar_receipt_service`) — best-effort."""
    plan = await get_active(doc_type, doc_id)
    if not plan:
        return None
    return await recompute_paid(plan["id"])


# ── Pembacaan untuk UI & job ──────────────────────────────────────────────
def overdue_lines(plan: Dict[str, Any], today: Optional[str] = None) -> List[Dict[str, Any]]:
    day = (today or now_iso())[:10]
    out = []
    for line in plan.get("lines") or []:
        if line.get("status") == "paid":
            continue
        due = str(line.get("due_date") or "")[:10]
        if due and due < day:
            out.append(line)
    return out


def next_due(plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    open_lines = [l for l in (plan.get("lines") or []) if l.get("status") != "paid"]
    open_lines.sort(key=lambda l: str(l.get("due_date") or "9999"))
    return open_lines[0] if open_lines else None


def due_lines(plan: Dict[str, Any], today: Optional[str] = None) -> List[Dict[str, Any]]:
    """FASE G-3 — baris yang SUDAH jatuh tempo (termasuk hari ini) & belum lunas.

    Inilah "alokasi jatuh tempo" yang dipakai menghitung selisih pembayaran:
    `delta = uang masuk − Σ sisa baris yang sudah jatuh tempo`.
    """
    day = (today or now_iso())[:10]
    out = []
    for line in plan.get("lines") or []:
        if line.get("status") == "paid":
            continue
        due = str(line.get("due_date") or "")[:10]
        if due and due <= day:
            out.append(line)
    out.sort(key=lambda l: (str(l.get("due_date") or "9999"), int(l.get("seq") or 0)))
    return out


def due_now_amount(plan: Dict[str, Any], today: Optional[str] = None) -> float:
    """Σ sisa baris yang sudah jatuh tempo (0 bila belum ada yang jatuh tempo)."""
    return round(sum(round(float(l.get("amount") or 0) - float(l.get("paid_amount") or 0), 2)
                     for l in due_lines(plan, today)), 2)


async def list_plans(entity_id: str = "", status: str = "", q: str = "",
                     limit: int = 100) -> List[Dict[str, Any]]:
    flt: Dict[str, Any] = {}
    # FASE E-0 (L2) — `entity_id` boleh berupa dict `{"$in": [...]}` dari
    # `entity_scope.scope_value()` sehingga isolasi ditegakkan di lapisan query.
    if isinstance(entity_id, dict):
        flt["entity_id"] = entity_id
    elif entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    if status:
        flt["status"] = status
    if q:
        import re as _re
        rx = _re.compile(_re.escape(q), _re.I)
        flt["$or"] = [{"number": rx}, {"doc_number": rx}, {"customer_name": rx}]
    rows = await db[COLL].find(flt, {"_id": 0}).sort("created_at", -1).to_list(int(limit))
    out = []
    for r in rows:
        r = safe_doc(r)
        nd = next_due(r)
        r["next_due_date"] = (nd or {}).get("due_date", "")
        r["next_due_amount"] = round(float((nd or {}).get("amount", 0) or 0)
                                     - float((nd or {}).get("paid_amount", 0) or 0), 2)
        r["overdue_count"] = len(overdue_lines(r))
        out.append(r)
    return out


async def needs_plan(order: Dict[str, Any]) -> bool:
    """Apakah pesanan ini WAJIB punya rencana pembayaran menurut kebijakan admin?"""
    policy = await plan_policy(order.get("entity_id") or "", order.get("customer_id") or "")
    limit = float(policy["required_above_amount"] or 0)
    if limit <= 0:
        return False
    if source_total(order) < limit:
        return False
    return not await get_active("sales_order", order.get("id", ""))
