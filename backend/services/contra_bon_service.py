"""FASE G-7 — KONTRABON ADVANCED (siklus tukar faktur supplier).

MASALAH NYATA
-------------
Supplier tekstil tidak ditagih per surat jalan. Mereka datang **sekali per siklus**
(mis. tiap Selasa) membawa setumpuk faktur, lalu terjadi ritual **tukar faktur**: faktur
supplier ditukar dengan **tanda terima** dari kami dan pembayarannya dijadwalkan.
Sebelum fase ini sistem hanya bisa membayar **per `vendor_bill`** (12 faktur = 12 transaksi
kas), tidak bisa menjawab *"penerimaan barang mana yang belum ditagih?"*, dan seluruh
potongan (retur beli, uang muka, denda supplier, selisih 3-way) hidup di luar sistem.

DESAIN
------
Satu dokumen **kontrabon** bernomor `<ENT>/CB-#####` per supplier per siklus:

    draft ──submit──> submitted ──verify──> verified ──approve──> approved
                                                                      │
                              disputed <──dispute──┘        schedule ─┘
                                                                      ↓
                                                            scheduled_payment ──pay──> paid

* **3-way match diverifikasi ulang** memakai mesin yang sudah ada
  (`vendor_bill_service.evaluate_match`) plus **dua ambang toleransi dari Pusat
  Pengaturan** (persen DAN rupiah — lihat `config_catalog_contrabon.py`).
* Selisih di luar toleransi **wajib keputusan berlabel** (terima / potong / sengketakan)
  dengan `reason_code` dari taksonomi G-1 → tidak ada selisih yang diterima diam-diam.
* **Potongan menunjuk dokumen NYATA.** Yang jurnalnya sudah ada (retur beli `ap_credit`)
  TIDAK dijurnal ulang; ia diterapkan sebagai **pelunasan non-kas** pada faktur sehingga
  subledger `vendor_bills` menyusul buku besar yang sudah lebih dulu berkurang.
* Potongan klaim makloon (`potong_bon`) **sudah** memotong `vendor_bills.grand_total` di
  Fase D → di sini ia hanya **ditampilkan** dan ditolak bila dicoba dipotong lagi.
* Pembayaran = **satu** `cash_transactions` (`ref_type="contra_bon"`) → otomatis jadi
  kandidat di Rekonsiliasi Bank G-8; tersedia juga jalur balik "bayar dari baris mutasi".

INVARIAN (dijaga `scripts/verify_data_integrity.py` lapisan `contrabon`)
-----------------------------------------------------------------------
* **INV-CB-01** satu faktur hanya boleh di satu kontrabon belum `cancelled`; Σ
  `applied_amount` atas satu faktur ≤ `grand_total`-nya.
* **INV-CB-02** `net_payable == Σ bills.applied_amount − Σ deductions.amount` (≥ 0) dan
  kontrabon `paid` → `Σ payments.amount == net_payable`.
* **INV-CB-03** pengecualian 3-way di luar toleransi wajib punya keputusan berlabel
  sebelum status melewati `verified`.
* **INV-CB-04** satu dokumen potongan hanya boleh dipakai di satu kontrabon belum
  `cancelled`; potongan makloon yang sudah menempel di faktur tidak boleh jadi potongan.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from core_utils import DEFAULT_ENTITY_ID, new_id, next_doc_number, now_iso, rupiah, safe_doc
from db import db
from services import gl_service
from services.config_resolver import value_of
from services.vendor_bill_service import already_billed_map, bill_financials

COLL = "contra_bons"
REASON_DOC_TYPE = "contra_bon"          # `amendment_reasons.applies_to` (taksonomi G-1)
EPS = 0.01

STATUSES = ("draft", "submitted", "verified", "approved", "scheduled_payment",
            "paid", "disputed", "cancelled")
STATUS_LABEL = {
    "draft": "Draf",
    "submitted": "Diajukan",
    "verified": "Terverifikasi",
    "approved": "Disetujui",
    "scheduled_payment": "Dijadwalkan bayar",
    "paid": "Sudah dibayar",
    "disputed": "Sengketa",
    "cancelled": "Dibatalkan",
}
# Status yang masih "memegang" faktur & dokumen potongan (INV-CB-01/04).
HOLDING_STATUSES = tuple(s for s in STATUSES if s != "cancelled")
# Status yang masih menunggu tindakan manusia (dipakai SLA & pengingat).
PENDING_STATUSES = ("draft", "submitted", "verified", "approved", "scheduled_payment")

CFG_KEYS = (
    "contra_bon.qty_tolerance_percent", "contra_bon.value_tolerance_rupiah",
    "contra_bon.require_reason_out_of_tolerance", "contra_bon.approval_threshold_rupiah",
    "contra_bon.approval_role", "contra_bon.high_value_approval_role",
    "contra_bon.reminder_days_before", "contra_bon.unbilled_gr_age_days",
    "contra_bon.verify_sla_days", "contra_bon.block_pay_before_approval",
)

# ── Jenis potongan (SATU sumber kebenaran; dipakai backend & layar) ───────────
#   posts_gl=False → jurnalnya SUDAH ada di dokumen sumber, jangan dijurnal ulang.
DEDUCTION_KINDS: Tuple[Dict[str, Any], ...] = (
    {"kind": "purchase_return", "label": "Retur beli (nota debit)",
     "help": "Barang dikembalikan ke supplier dan supplier setuju memotong tagihan. "
             "Jurnalnya sudah dibuat saat retur disetujui, jadi di sini hanya diterapkan "
             "sebagai pelunasan non-kas pada faktur.",
     "needs_ref": True, "ref_type": "purchase_return", "posts_gl": False,
     "reason_required": False, "default_reason": "cb_return_credit"},
    {"kind": "supplier_advance", "label": "Uang muka / titipan ke supplier",
     "help": "Uang muka yang pernah dibayarkan (mis. kelebihan bayar Fase G-3) dipakai "
             "memotong tagihan siklus ini.",
     "needs_ref": True, "ref_type": "cash_transaction", "posts_gl": True,
     "reason_required": False, "default_reason": "supplier_advance"},
    {"kind": "supplier_penalty", "label": "Denda keterlambatan supplier",
     "help": "Supplier terlambat mengirim dan kesepakatannya dipotong dari tagihan.",
     "needs_ref": False, "ref_type": "", "posts_gl": True,
     "reason_required": True, "default_reason": "cb_supplier_late"},
    {"kind": "match_variance", "label": "Selisih 3-way match (barang tak diterima)",
     "help": "Faktur menagih lebih dari barang yang benar-benar diterima dan supplier "
             "setuju dipotong. Mengurangi akun GR/IR (barang diterima belum ditagih).",
     "needs_ref": False, "ref_type": "", "posts_gl": True,
     "reason_required": True, "default_reason": "cb_qty_shortfall"},
    {"kind": "other_agreed", "label": "Potongan lain (disepakati)",
     "help": "Potongan di luar empat jenis di atas yang disepakati bersama supplier. "
             "Wajib alasan supaya bisa dibaca auditor.",
     "needs_ref": False, "ref_type": "", "posts_gl": True,
     "reason_required": True, "default_reason": "cb_other_agreed"},
)
KIND_MAP = {d["kind"]: d for d in DEDUCTION_KINDS}

EXCEPTION_ACTIONS = (
    {"action": "accept", "label": "Terima selisihnya (tetap dibayar)",
     "help": "Selisih diakui benar (mis. harga naik sudah disepakati) sehingga tagihan "
             "dibayar penuh."},
    {"action": "deduct", "label": "Potong dari tagihan",
     "help": "Selisih dipotong dari nilai yang dibayarkan; sistem membuat potongan "
             "'Selisih 3-way match' berikut jurnalnya."},
    {"action": "dispute", "label": "Sengketakan ke supplier",
     "help": "Kontrabon ditahan berstatus Sengketa sampai supplier mengoreksi fakturnya."},
)


class ContraBonError(ValueError):
    """Kesalahan kontrabon dengan pesan SIAP TAMPIL ke pengguna (Bahasa Indonesia)."""


def _round(n: Any) -> float:
    return round(float(n or 0), 2)


def _rp(v: Any) -> str:
    """Alias tipis ke `core_utils.rupiah` — satu sumber format uang untuk seluruh backend."""
    return rupiah(v)


# ═════════════════════════════════════════════════════════════════════════════
#  KONFIGURASI (Pusat Pengaturan — tidak ada angka sihir di kode)
# ═════════════════════════════════════════════════════════════════════════════
async def policy(entity_id: str = "") -> Dict[str, Any]:
    ctx = {"entity_id": entity_id or ""}
    raw = {k.split(".", 1)[1]: await value_of(k, ctx) for k in CFG_KEYS}
    return {
        "qty_tolerance_percent": float(raw.get("qty_tolerance_percent") or 0),
        "value_tolerance_rupiah": float(raw.get("value_tolerance_rupiah") or 0),
        "require_reason": bool(raw.get("require_reason_out_of_tolerance")),
        "approval_threshold": float(raw.get("approval_threshold_rupiah") or 0),
        "approval_role": str(raw.get("approval_role") or "manager").lower(),
        "high_value_role": str(raw.get("high_value_approval_role") or "admin").lower(),
        "reminder_days_before": int(raw.get("reminder_days_before") or 0),
        "unbilled_gr_age_days": int(raw.get("unbilled_gr_age_days") or 0),
        "verify_sla_days": int(raw.get("verify_sla_days") or 2),
        "block_pay_before_approval": bool(raw.get("block_pay_before_approval")),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  LABEL ALASAN (taksonomi G-1 — bisa ditambah admin, bukan enum keras)
# ═════════════════════════════════════════════════════════════════════════════
async def reasons() -> List[Dict[str, Any]]:
    from services.amendment_service import ensure_reasons
    await ensure_reasons()
    rows = await db.amendment_reasons.find(
        {"applies_to": REASON_DOC_TYPE, "status": {"$ne": "inactive"}}, {"_id": 0}
    ).sort("label", 1).to_list(100)
    return [safe_doc(r) for r in rows]


async def _reason_or_fail(code: str, what: str = "keputusan") -> Dict[str, Any]:
    """Label alasan WAJIB ada, aktif, dan memang untuk kontrabon.

    Pesan penolakan menyebut **nama label**, bukan kode mentah — pelajaran
    `KN-G9-REASON-MISMATCH`: kode teknis di layar membuat petugas memilih sembarang.
    """
    code = (code or "").strip()
    if not code:
        valid = ", ".join(f"\u201c{r['label']}\u201d" for r in (await reasons())[:6])
        raise ContraBonError(
            f"Alasan {what} wajib dipilih — keputusan atas uang harus berlabel supaya bisa "
            f"dibaca auditor. Pilihan yang berlaku: {valid}.")
    row = await db.amendment_reasons.find_one({"code": code}, {"_id": 0})
    if not row or row.get("status") == "inactive":
        raise ContraBonError(f"Label alasan '{code}' tidak ada / tidak aktif.")
    if REASON_DOC_TYPE not in (row.get("applies_to") or []):
        valid = ", ".join(f"\u201c{r['label']}\u201d" for r in (await reasons())[:6])
        raise ContraBonError(
            f"Label alasan \u201c{row.get('label', code)}\u201d bukan untuk kontrabon. "
            f"Pilihan yang berlaku: {valid}.")
    return safe_doc(row)


# ═════════════════════════════════════════════════════════════════════════════
#  3-WAY MATCH BERTOLERANSI (PO ↔ penerimaan ↔ faktur supplier)
# ═════════════════════════════════════════════════════════════════════════════
def _pct(actual: float, base: float) -> float:
    if base <= 0:
        return 0.0
    return round((actual - base) / base * 100.0, 2)


def evaluate_bill_exceptions(bill: Dict[str, Any], po: Optional[Dict[str, Any]],
                             pol: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pengecualian 3-way pada SATU faktur, memakai **dua** ambang toleransi.

    Sebuah selisih baru dianggap pengecualian bila melewati ambang **persen** DAN ambang
    **rupiah** (lihat catatan desain di `config_catalog_contrabon.py`). PURE — tak
    menyentuh DB, supaya bisa diuji tanpa database.
    """
    if not po:
        return []
    qty_tol = float(pol.get("qty_tolerance_percent") or 0)
    val_tol = float(pol.get("value_tolerance_rupiah") or 0)
    po_items = {it.get("product_id"): it for it in (po.get("items") or [])}
    out: List[Dict[str, Any]] = []
    for it in (bill.get("items") or []):
        pid = it.get("product_id")
        po_it = po_items.get(pid) or {}
        billed = _round(it.get("billed_qty", it.get("quantity", 0)))
        received = _round(po_it.get("received_qty", 0))
        price = _round(it.get("price", 0))
        po_price = _round(po_it.get("po_price", po_it.get("price", 0)))
        name = it.get("product_name") or po_it.get("product_name") or pid
        sku = it.get("sku") or po_it.get("sku", "")

        # (1) menagih lebih banyak dari yang diterima
        qty_diff = round(billed - received, 4)
        if qty_diff > 0:
            pct = abs(_pct(billed, received)) if received > 0 else 100.0
            value = _round(qty_diff * price)
            if pct > qty_tol + 1e-6 and value > val_tol + EPS:
                out.append({
                    "key": f"{bill['id']}:{pid}:qty",
                    "bill_id": bill["id"], "bill_number": bill.get("bill_number", ""),
                    "product_id": pid, "sku": sku, "product_name": name,
                    "type": "qty_over_billed",
                    "billed_qty": billed, "received_qty": received,
                    "qty_diff": qty_diff, "variance_percent": pct, "amount": value,
                    "detail": (f"Ditagih {billed:g} {it.get('unit', '')} padahal diterima "
                               f"{received:g} — selisih {qty_diff:g} senilai {_rp(value)} "
                               f"({pct:g}% > toleransi {qty_tol:g}%)"),
                })
        # (2) harga faktur menyimpang dari harga PO
        if po_price > 0 and abs(price - po_price) > EPS:
            pct = abs(_pct(price, po_price))
            value = _round(abs(price - po_price) * billed)
            if pct > qty_tol + 1e-6 and value > val_tol + EPS:
                out.append({
                    "key": f"{bill['id']}:{pid}:price",
                    "bill_id": bill["id"], "bill_number": bill.get("bill_number", ""),
                    "product_id": pid, "sku": sku, "product_name": name,
                    "type": "price_variance",
                    "bill_price": price, "po_price": po_price,
                    "variance_percent": pct, "amount": value,
                    "detail": (f"Harga faktur {_rp(price)} vs harga PO {_rp(po_price)} — "
                               f"selisih {pct:g}% senilai {_rp(value)} "
                               f"(toleransi {qty_tol:g}% / {_rp(val_tol)})"),
                })
    return out


def recompute(cb: Dict[str, Any]) -> Dict[str, Any]:
    """Hitung ulang total & ringkasan match dari isi dokumen. PURE."""
    bills_total = _round(sum(_round(b.get("applied_amount")) for b in (cb.get("bills") or [])))
    ded_total = _round(sum(_round(d.get("amount")) for d in (cb.get("deductions") or [])))
    paid_total = _round(sum(_round(p.get("amount")) for p in (cb.get("payments") or [])))
    net = _round(bills_total - ded_total)
    decided = {d.get("exception_key") for d in (cb.get("decisions") or []) if d.get("exception_key")}
    exceptions = [e for b in (cb.get("bills") or [])
                  for e in ((b.get("match") or {}).get("exceptions") or [])]
    pending = [e for e in exceptions if e.get("key") not in decided]
    cb["totals"] = {
        "bills_total": bills_total, "deductions_total": ded_total,
        "net_payable": net, "paid_total": paid_total,
        "outstanding": _round(max(net - paid_total, 0.0)),
    }
    cb["match_summary"] = {
        "status": "needs_decision" if pending else "matched",
        "exceptions_count": len(exceptions),
        "pending_count": len(pending),
        "pending_keys": [e.get("key") for e in pending],
        "exceptions_value": _round(sum(_round(e.get("amount")) for e in exceptions)),
    }
    return cb


def _sla(cb: Dict[str, Any], pol: Dict[str, Any]) -> Dict[str, Any]:
    """Umur & keterlambatan (SLA verifikasi) — kalimat manusia dibuat di layar."""
    if cb.get("status") not in PENDING_STATUSES:
        return {"age_days": 0.0, "overdue": False, "sla_days": pol.get("verify_sla_days", 2)}
    base = cb.get("submitted_at") or cb.get("created_at") or now_iso()
    try:
        started = datetime.fromisoformat(str(base).replace("Z", "+00:00"))
    except ValueError:
        started = datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    age = round((datetime.now(timezone.utc) - started).total_seconds() / 86400.0, 2)
    sla = int(pol.get("verify_sla_days") or 2)
    return {"age_days": age, "sla_days": sla, "overdue": age > sla}


async def decorate(cb: Dict[str, Any], pol: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cb = recompute(dict(cb))
    pol = pol or await policy(cb.get("entity_id", ""))
    cb["status_label"] = STATUS_LABEL.get(cb.get("status", ""), cb.get("status", ""))
    cb["sla"] = _sla(cb, pol)
    cb["policy_snapshot_live"] = {
        "qty_tolerance_percent": pol["qty_tolerance_percent"],
        "value_tolerance_rupiah": pol["value_tolerance_rupiah"],
        "approval_threshold": pol["approval_threshold"],
        "approval_role": pol["approval_role"],
        "high_value_role": pol["high_value_role"],
    }
    return safe_doc(cb)


# ═════════════════════════════════════════════════════════════════════════════
#  KETERSEDIAAN: faktur & dokumen potongan yang belum terpakai
# ═════════════════════════════════════════════════════════════════════════════
async def occupied_bills(exclude_cb_id: str = "") -> Dict[str, str]:
    """{bill_id: nomor kontrabon} untuk faktur yang sudah dipegang kontrabon lain."""
    q: Dict[str, Any] = {"status": {"$in": list(HOLDING_STATUSES)}}
    if exclude_cb_id:
        q["id"] = {"$ne": exclude_cb_id}
    out: Dict[str, str] = {}
    async for cb in db[COLL].find(q, {"_id": 0, "number": 1, "bills": 1}):
        for b in (cb.get("bills") or []):
            out[b.get("bill_id")] = cb.get("number", "")
    return out


async def used_deduction_refs(exclude_cb_id: str = "") -> Dict[str, Dict[str, Any]]:
    """{ref_id: {kontrabon, amount}} untuk dokumen potongan yang sudah dipakai."""
    q: Dict[str, Any] = {"status": {"$in": list(HOLDING_STATUSES)}}
    if exclude_cb_id:
        q["id"] = {"$ne": exclude_cb_id}
    out: Dict[str, Dict[str, Any]] = {}
    async for cb in db[COLL].find(q, {"_id": 0, "number": 1, "deductions": 1}):
        for d in (cb.get("deductions") or []):
            if d.get("ref_id"):
                row = out.setdefault(d["ref_id"], {"number": cb.get("number", ""), "amount": 0.0})
                row["amount"] = _round(row["amount"] + _round(d.get("amount")))
    return out


async def _scope_q(entity_ids: Optional[List[str]], field: str = "entity_id") -> Dict[str, Any]:
    if entity_ids is None:
        return {}
    return {field: {"$in": list(entity_ids)}}


async def billable_bills(supplier_id: str, entity_id: str,
                         exclude_cb_id: str = "") -> List[Dict[str, Any]]:
    """Faktur supplier yang sudah diakui (posted) & masih ada sisa hutang."""
    taken = await occupied_bills(exclude_cb_id)
    q = {"supplier_id": supplier_id, "status": "posted"}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    rows = await db.vendor_bills.find(q, {"_id": 0}).sort("bill_date", 1).to_list(500)
    out = []
    for b in rows:
        fin = bill_financials(b)
        if fin["outstanding"] <= EPS or b["id"] in taken:
            continue
        out.append({
            "bill_id": b["id"], "bill_number": b.get("bill_number", ""),
            "supplier_invoice_no": b.get("supplier_invoice_no", ""),
            "po_id": b.get("po_id", ""), "po_number": b.get("po_number", ""),
            "bill_date": b.get("bill_date", ""), "due_date": b.get("due_date", ""),
            "grand_total": fin["grand_total"], "amount_paid": fin["amount_paid"],
            "outstanding": fin["outstanding"],
            "match_status": b.get("match_status", ""),
            "claim_deduction": _round(b.get("claim_deduction")),
            "entity_id": b.get("entity_id", ""),
        })
    return out


async def available_credits(supplier_id: str, entity_id: str,
                            exclude_cb_id: str = "") -> Dict[str, List[Dict[str, Any]]]:
    """Dokumen potongan yang BOLEH dipakai: retur beli `ap_credit` + uang muka supplier."""
    used = await used_deduction_refs(exclude_cb_id)
    ent_q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        ent_q["entity_id"] = entity_id

    # (1) Retur beli yang disetujui dengan konsekuensi potong hutang (nota debit).
    returns: List[Dict[str, Any]] = []
    async for r in db.purchase_returns.find(
            {"supplier_id": supplier_id, "status": "approved",
             "supplier_outcome": "ap_credit", **ent_q}, {"_id": 0}):
        total = _round(r.get("total_amount"))
        spent = _round((used.get(r["id"]) or {}).get("amount"))
        if total - spent <= EPS:
            continue
        returns.append({
            "kind": "purchase_return", "ref_id": r["id"],
            "ref_number": r.get("debit_note_number") or r.get("number", ""),
            "label": f"Nota debit {r.get('debit_note_number') or r.get('number', '')}",
            "po_number": r.get("po_number", ""),
            "date": r.get("approved_at") or r.get("created_at", ""),
            "amount": _round(total - spent), "total_amount": total,
            "reason": r.get("reason", ""),
        })

    # (2) Uang muka supplier (kelebihan bayar Fase G-3) yang belum dipakai.
    advances: List[Dict[str, Any]] = []
    bill_ids = [b["id"] async for b in db.vendor_bills.find(
        {"supplier_id": supplier_id}, {"_id": 0, "id": 1})]
    if bill_ids:
        async for t in db.cash_transactions.find(
                {"ref_type": "ap_advance", "ref_id": {"$in": bill_ids},
                 "status": {"$ne": "void"}}, {"_id": 0}):
            total = _round(t.get("amount"))
            spent = _round((used.get(t["id"]) or {}).get("amount"))
            if total - spent <= EPS:
                continue
            advances.append({
                "kind": "supplier_advance", "ref_id": t["id"],
                "ref_number": t.get("number", ""),
                "label": f"Uang muka {t.get('number', '')}",
                "date": t.get("txn_date", ""),
                "amount": _round(total - spent), "total_amount": total,
                "reason": t.get("description", ""),
            })
    return {"purchase_returns": returns, "supplier_advances": advances}


# ═════════════════════════════════════════════════════════════════════════════
#  GR BELUM DITAGIH (barang sudah masuk, faktur supplier belum datang)
# ═════════════════════════════════════════════════════════════════════════════
async def unbilled_receipts(entity_ids: Optional[List[str]] = None, supplier_id: str = "",
                            entity_id: str = "") -> Dict[str, Any]:
    """Nilai penerimaan barang yang belum tertagih, per PO (US3).

    Sumbernya PO + `received_qty` per baris (yang diisi jalur penerimaan gudang) dikurangi
    qty yang sudah ditagih (`already_billed_map`). Tidak butuh koleksi baru — GRN memang
    hidup sebagai `wms_tasks` (`flow_type=inbound`).
    """
    pol = await policy(entity_id)
    q: Dict[str, Any] = {"status": {"$nin": ["draft", "waiting_approval", "rejected", "cancelled"]}}
    if supplier_id:
        q["supplier_id"] = supplier_id
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    elif entity_ids is not None:
        q["entity_id"] = {"$in": list(entity_ids)}
    rows: List[Dict[str, Any]] = []
    total_value = 0.0
    pos = await db.purchase_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(400)
    for po in pos:
        billed = await already_billed_map(po["id"])
        items: List[Dict[str, Any]] = []
        po_value = 0.0
        for it in (po.get("items") or []):
            pid = it.get("product_id")
            received = _round(it.get("received_qty"))
            done = _round(billed.get(pid, 0))
            pending = round(received - done, 4)
            if pending <= 0.0001:
                continue
            price = _round(it.get("price"))
            value = _round(pending * price)
            po_value += value
            items.append({
                "product_id": pid, "sku": it.get("sku", ""),
                "product_name": it.get("product_name", ""),
                "unit": it.get("unit", ""), "received_qty": received,
                "billed_qty": done, "unbilled_qty": pending, "price": price,
                "unbilled_value": value,
            })
        if not items:
            continue
        # Penerimaan terakhir (untuk umur tertunggak) dari tugas gudang inbound PO ini.
        last = await db.wms_tasks.find_one(
            {"po_id": po["id"], "flow_type": "inbound"},
            {"_id": 0, "id": 1, "completed_at": 1, "updated_at": 1, "created_at": 1},
            sort=[("updated_at", -1)])
        ref = (last or {}).get("completed_at") or (last or {}).get("updated_at") \
            or po.get("updated_at") or po.get("created_at") or ""
        age = 0
        try:
            d = datetime.fromisoformat(str(ref).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - d).days
        except ValueError:
            age = 0
        total_value += po_value
        rows.append({
            "po_id": po["id"], "po_number": po.get("po_number", ""),
            "supplier_id": po.get("supplier_id", ""), "supplier_name": po.get("supplier_name", ""),
            "entity_id": po.get("entity_id", ""), "po_status": po.get("status", ""),
            "grn_task_id": (last or {}).get("id", ""),
            "last_receipt_at": ref, "age_days": age,
            "overdue": age > int(pol["unbilled_gr_age_days"] or 0),
            "unbilled_value": _round(po_value), "items": items,
        })
    rows.sort(key=lambda r: (-r["age_days"], -r["unbilled_value"]))
    return {
        "rows": rows, "total_value": _round(total_value), "po_count": len(rows),
        "overdue_count": sum(1 for r in rows if r["overdue"]),
        "age_threshold_days": int(pol["unbilled_gr_age_days"] or 0),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  RAKIT KANDIDAT (layar "Buat Kontrabon")
# ═════════════════════════════════════════════════════════════════════════════
async def _term_days(supplier: Dict[str, Any], entity_id: str = "") -> int:
    code = supplier.get("payment_term_code") or ""
    if not code:
        return 0
    # FASE E-4 (E4.3) — syarat bayar berlapis: override badan usaha menang atas global.
    from services import entity_master_service as ems
    term = await ems.resolve_row("payment-terms", code, entity_id)
    return int((term or {}).get("net_days", 0) or 0)


async def prepare(supplier_id: str, entity_id: str, exclude_cb_id: str = "") -> Dict[str, Any]:
    sup = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not sup:
        raise ContraBonError("Supplier tidak ditemukan.")
    ent = entity_id or sup.get("entity_id") or DEFAULT_ENTITY_ID
    bills = await billable_bills(supplier_id, ent, exclude_cb_id)
    credits = await available_credits(supplier_id, ent, exclude_cb_id)
    gr = await unbilled_receipts(None, supplier_id=supplier_id, entity_id=ent)
    days = await _term_days(sup, ent)
    today = date.today()
    attached = [
        {"bill_id": b["bill_id"], "bill_number": b["bill_number"],
         "amount": b["claim_deduction"],
         "note": "Potongan klaim makloon sudah menempel di faktur (Fase D) — tidak boleh "
                 "dipotong lagi di kontrabon."}
        for b in bills if b["claim_deduction"] > EPS
    ]
    return {
        "supplier": {"id": sup["id"], "code": sup.get("code", ""), "name": sup.get("name", ""),
                     "npwp": sup.get("npwp", ""),
                     "payment_term_code": sup.get("payment_term_code", ""),
                     "invoice_exchange": sup.get("invoice_exchange") or {"mode": "none"}},
        "entity_id": ent,
        "bills": bills,
        "bills_total": _round(sum(b["outstanding"] for b in bills)),
        "credits": credits,
        "credits_total": _round(sum(c["amount"] for c in
                                    credits["purchase_returns"] + credits["supplier_advances"])),
        "makloon_attached": attached,
        "unbilled_receipts": {"total_value": gr["total_value"], "po_count": gr["po_count"],
                              "overdue_count": gr["overdue_count"], "rows": gr["rows"][:20]},
        "suggested": {"cycle_date": today.isoformat(),
                      "due_date": (today + timedelta(days=days or 0)).isoformat(),
                      "term_days": days},
        "deduction_kinds": list(DEDUCTION_KINDS),
        "policy": await policy(ent),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  SIKLUS
# ═════════════════════════════════════════════════════════════════════════════
async def _get(cb_id: str, entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cb = await db[COLL].find_one({"id": cb_id}, {"_id": 0})
    if not cb:
        raise ContraBonError("Kontrabon tidak ditemukan.")
    if entity_ids is not None:
        ent = cb.get("entity_id") or ""
        if ent and ent != "all" and ent not in entity_ids:
            from fastapi import HTTPException
            raise HTTPException(status_code=403,
                                detail="Kontrabon milik entitas (PT) lain — tidak berwenang.")
    return cb


def _tl(event: str, label: str, actor: str, note: str = "") -> Dict[str, Any]:
    return {"at": now_iso(), "event": event, "label": label, "actor": actor, "note": note}


async def _save(cb: Dict[str, Any]) -> Dict[str, Any]:
    recompute(cb)
    cb["updated_at"] = now_iso()
    await db[COLL].update_one({"id": cb["id"]}, {"$set": {
        k: v for k, v in cb.items() if k not in ("id", "_id")}})
    return cb


async def _bill_match(bill: Dict[str, Any], pol: Dict[str, Any]) -> Dict[str, Any]:
    po = await db.purchase_orders.find_one({"id": bill.get("po_id")}, {"_id": 0}) \
        if bill.get("po_id") else None
    exc = evaluate_bill_exceptions(bill, po, pol)
    return {"status": "needs_decision" if exc else "matched", "exceptions": exc,
            "po_status": (po or {}).get("status", ""),
            "evaluated_at": now_iso()}


async def create(payload: Dict[str, Any], actor: Dict[str, Any],
                 entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    supplier_id = (payload.get("supplier_id") or "").strip()
    sup = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not sup:
        raise ContraBonError("Supplier wajib dipilih.")
    picks = payload.get("bills") or []
    if not picks:
        raise ContraBonError(
            "Pilih minimal satu tagihan supplier — kontrabon adalah gabungan faktur satu siklus.")
    entity_id = payload.get("entity_id") or sup.get("entity_id") or DEFAULT_ENTITY_ID
    if entity_ids is not None and entity_id not in entity_ids and entity_id != "all":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Tidak berwenang membuat kontrabon di PT ini.")
    pol = await policy(entity_id)
    taken = await occupied_bills()

    bills: List[Dict[str, Any]] = []
    po_ids: Set[str] = set()
    for p in picks:
        bid = p.get("bill_id") if isinstance(p, dict) else getattr(p, "bill_id", "")
        want = p.get("applied_amount") if isinstance(p, dict) else getattr(p, "applied_amount", None)
        bill = await db.vendor_bills.find_one({"id": bid}, {"_id": 0})
        if not bill:
            raise ContraBonError(f"Tagihan supplier '{bid}' tidak ditemukan.")
        if bill.get("supplier_id") != supplier_id:
            raise ContraBonError(
                f"Tagihan {bill.get('bill_number')} milik supplier lain — satu kontrabon hanya "
                "untuk satu supplier.")
        if (bill.get("entity_id") or "") != entity_id:
            raise ContraBonError(
                f"Tagihan {bill.get('bill_number')} milik PT lain — kontrabon tidak boleh "
                "mencampur buku dua entitas.")
        if bill.get("status") != "posted":
            raise ContraBonError(
                f"Tagihan {bill.get('bill_number')} berstatus "
                f"'{bill.get('status')}' — hanya tagihan yang sudah diakui (posted) bisa "
                "masuk kontrabon.")
        if bid in taken:
            raise ContraBonError(
                f"Tagihan {bill.get('bill_number')} sudah ada di kontrabon {taken[bid]} — "
                "satu faktur tidak boleh masuk dua kontrabon.")
        fin = bill_financials(bill)
        applied = _round(want) if want not in (None, "") else fin["outstanding"]
        if applied <= EPS:
            raise ContraBonError(f"Nilai yang dikontrabonkan untuk {bill.get('bill_number')} harus > 0.")
        if applied > fin["outstanding"] + EPS:
            raise ContraBonError(
                f"Nilai {_rp(applied)} melebihi sisa hutang {bill.get('bill_number')} "
                f"({_rp(fin['outstanding'])}).")
        match = await _bill_match(bill, pol)
        if bill.get("po_id"):
            po_ids.add(bill["po_id"])
        bills.append({
            "bill_id": bill["id"], "bill_number": bill.get("bill_number", ""),
            "supplier_invoice_no": bill.get("supplier_invoice_no", ""),
            "po_id": bill.get("po_id", ""), "po_number": bill.get("po_number", ""),
            "bill_date": bill.get("bill_date", ""), "due_date": bill.get("due_date", ""),
            "grand_total": fin["grand_total"], "outstanding_at_pick": fin["outstanding"],
            "applied_amount": applied, "settled_amount": 0.0,
            "claim_deduction_info": _round(bill.get("claim_deduction")),
            "match": match,
        })

    today = date.today()
    number = await next_doc_number(COLL, "number", "CB-", entity_id=entity_id)
    doc: Dict[str, Any] = {
        "id": new_id("cbn"), "number": number, "entity_id": entity_id,
        "supplier_id": supplier_id, "supplier_name": sup.get("name", ""),
        "supplier_code": sup.get("code", ""), "supplier_npwp": sup.get("npwp", ""),
        "supplier_pic": payload.get("supplier_pic") or sup.get("pic_name", ""),
        "cycle_date": payload.get("cycle_date") or today.isoformat(),
        "due_date": payload.get("due_date")
        or (today + timedelta(days=await _term_days(sup, entity_id))).isoformat(),
        "payment_term_code": sup.get("payment_term_code", ""),
        "status": "draft",
        "bills": bills, "deductions": [], "decisions": [], "payments": [],
        "schedule": {"planned_payment_date": "", "method": "transfer",
                     "bank_account_id": "", "notes": ""},
        "policy_snapshot": {
            "qty_tolerance_percent": pol["qty_tolerance_percent"],
            "value_tolerance_rupiah": pol["value_tolerance_rupiah"],
            "approval_threshold": pol["approval_threshold"],
            "approval_role": pol["approval_role"],
            "high_value_role": pol["high_value_role"],
            "require_reason": pol["require_reason"],
        },
        "notes": payload.get("notes", ""),
        "created_by": actor.get("name", ""), "created_by_id": actor.get("id", ""),
        "created_at": now_iso(), "updated_at": now_iso(),
        "submitted_at": "", "submitted_by": "",
        "verified_at": "", "verified_by": "",
        "approved_at": "", "approved_by": "",
        "paid_at": "", "disputed_at": "", "dispute_reason_code": "",
        "cancelled_at": "", "cancel_note": "",
        "timeline": [_tl("dibuat", "Kontrabon dibuat", actor.get("name", ""),
                         f"{len(bills)} tagihan · {_rp(sum(b['applied_amount'] for b in bills))}")],
    }
    recompute(doc)
    await db[COLL].insert_one(dict(doc))

    # FASE G-4 — relasi dua arah: kontrabon ↔ tagihan ↔ PO.
    from services import doc_refs_service as refs
    for b in bills:
        await refs.safe_link(("contra_bon", doc["id"]), ("vendor_bill", b["bill_id"]),
                             "settles", note="digabung dalam kontrabon")
    for pid in po_ids:
        await refs.safe_link(("contra_bon", doc["id"]), ("purchase_order", pid),
                             "parent", note="PO yang ditagih di kontrabon")
    if payload.get("submit_now"):
        return await submit(doc["id"], actor, entity_ids)
    return await decorate(doc, pol)


async def add_deduction(cb_id: str, payload: Dict[str, Any], actor: Dict[str, Any],
                        entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cb = await _get(cb_id, entity_ids)
    if cb["status"] not in ("draft", "submitted", "disputed"):
        raise ContraBonError(
            f"Kontrabon berstatus '{STATUS_LABEL.get(cb['status'], cb['status'])}' tidak bisa "
            "ditambah potongan. Potongan hanya boleh sebelum verifikasi.")
    kind = (payload.get("kind") or "").strip()
    # Potongan klaim makloon SUDAH menempel di faktur (Fase D) → tolak, jangan dobel.
    # Diperiksa SEBELUM pencarian jenis supaya pesannya menjelaskan SEBABNYA, bukan
    # sekadar "jenis tidak dikenal".
    if kind in ("makloon_claim", "makloon_potong_bon"):
        raise ContraBonError(
            "Potongan klaim makloon sudah menempel di faktur jasanya (Fase D) sehingga tidak "
            "boleh dipotong lagi di kontrabon — nilainya sudah tampil sebagai informasi.")
    spec = KIND_MAP.get(kind)
    if not spec:
        valid = ", ".join(f"\u201c{d['label']}\u201d" for d in DEDUCTION_KINDS)
        raise ContraBonError(f"Jenis potongan tidak dikenal. Pilihan: {valid}.")
    ref_id = (payload.get("ref_id") or "").strip()
    amount = payload.get("amount")
    note = payload.get("note", "")
    ref_number = ""
    reason_code = (payload.get("reason_code") or "").strip()
    if not reason_code:
        if spec.get("reason_required"):
            # Potongan bernominal bebas WAJIB berlabel: tanpa ini "potongan lain" jadi
            # pintu belakang untuk mengurangi tagihan tanpa jejak yang bisa dibaca auditor.
            await _reason_or_fail("", f"potongan \u201c{spec['label']}\u201d")
        reason_code = spec["default_reason"]
    # Label alasan diperiksa untuk SEMUA jenis potongan (juga yang berlabel otomatis) —
    # sekaligus memastikan taksonomi G-1 sudah terpasang di basis data.
    await _reason_or_fail(reason_code, "potongan")

    if spec["needs_ref"]:
        if not ref_id:
            raise ContraBonError(
                f"Potongan \u201c{spec['label']}\u201d wajib menunjuk dokumen sumbernya.")
        # Dokumen yang sama tidak boleh dipotong dua kali — TERMASUK di kontrabon ini
        # sendiri (celah yang ketemu saat POC pertama dijalankan: penjaga hanya melihat
        # kontrabon LAIN, sehingga satu nota debit bisa dipotong berulang di satu dokumen).
        mine = [d for d in (cb.get("deductions") or []) if d.get("ref_id") == ref_id]
        if mine:
            raise ContraBonError(
                f"Dokumen itu sudah menjadi potongan di kontrabon ini "
                f"({_rp(sum(_round(d.get('amount')) for d in mine))}) — satu nota/uang muka "
                "tidak boleh dipotong dua kali.")
        used = await used_deduction_refs(exclude_cb_id=cb_id)
        if ref_id in used:
            raise ContraBonError(
                f"Dokumen itu sudah dipakai sebagai potongan di kontrabon "
                f"{used[ref_id]['number']} — satu nota/uang muka tidak boleh dipotong dua kali.")
        avail = await available_credits(cb["supplier_id"], cb["entity_id"], exclude_cb_id=cb_id)
        pool = {c["ref_id"]: c for c in avail["purchase_returns"] + avail["supplier_advances"]}
        src = pool.get(ref_id)
        if not src:
            raise ContraBonError(
                "Dokumen potongan tidak tersedia untuk supplier/PT ini (mungkin sudah terpakai, "
                "belum disetujui, atau konsekuensinya bukan potong hutang).")
        if src["kind"] != kind:
            raise ContraBonError(
                f"Dokumen itu berjenis \u201c{KIND_MAP[src['kind']]['label']}\u201d, bukan "
                f"\u201c{spec['label']}\u201d.")
        ref_number = src["ref_number"]
        amount = _round(amount) if amount not in (None, "") else src["amount"]
        if amount > src["amount"] + EPS:
            raise ContraBonError(
                f"Potongan {_rp(amount)} melebihi sisa nilai dokumen {ref_number} "
                f"({_rp(src['amount'])}).")
    else:
        amount = _round(amount)

    amount = _round(amount)
    if amount <= EPS:
        raise ContraBonError("Nilai potongan harus lebih besar dari nol.")
    if kind == "match_variance":
        bill_id = (payload.get("bill_id") or "").strip()
        if not bill_id or bill_id not in {b["bill_id"] for b in cb.get("bills", [])}:
            raise ContraBonError(
                "Potongan selisih 3-way wajib menunjuk tagihan yang selisihnya dipotong.")

    recompute(cb)
    room = _round(cb["totals"]["bills_total"] - cb["totals"]["deductions_total"])
    if amount > room + EPS:
        raise ContraBonError(
            f"Total potongan {_rp(cb['totals']['deductions_total'] + amount)} melebihi nilai "
            f"tagihan {_rp(cb['totals']['bills_total'])} — nilai bersih kontrabon tidak boleh "
            "negatif. Sisa ruang potongan: " + _rp(room) + ".")

    ded = {
        "id": new_id("cbd"), "kind": kind, "label": spec["label"],
        "ref_type": spec["ref_type"], "ref_id": ref_id, "ref_number": ref_number,
        "bill_id": payload.get("bill_id", ""), "exception_key": payload.get("exception_key", ""),
        "amount": amount, "reason_code": reason_code, "note": note,
        "posts_gl": bool(spec["posts_gl"]), "gl_journal_id": "", "applied_at": "",
        "added_by": actor.get("name", ""), "added_at": now_iso(),
    }
    cb.setdefault("deductions", []).append(ded)
    cb.setdefault("timeline", []).append(_tl(
        "potongan", f"Potongan ditambah: {spec['label']}", actor.get("name", ""),
        f"{_rp(amount)}" + (f" · {ref_number}" if ref_number else "")))
    await _save(cb)
    if ref_id and spec["ref_type"] == "purchase_return":
        from services import doc_refs_service as refs
        await refs.safe_link(("contra_bon", cb["id"]), ("purchase_return", ref_id),
                             "related", note="potongan retur beli di kontrabon")
    return await decorate(cb)


async def remove_deduction(cb_id: str, ded_id: str, actor: Dict[str, Any],
                           entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cb = await _get(cb_id, entity_ids)
    if cb["status"] not in ("draft", "submitted", "disputed"):
        raise ContraBonError("Potongan hanya bisa dihapus sebelum kontrabon diverifikasi.")
    keep = [d for d in (cb.get("deductions") or []) if d.get("id") != ded_id]
    if len(keep) == len(cb.get("deductions") or []):
        raise ContraBonError("Potongan tidak ditemukan.")
    gone = next(d for d in cb["deductions"] if d.get("id") == ded_id)
    if gone.get("applied_at"):
        raise ContraBonError("Potongan sudah diterapkan ke pembukuan — tidak bisa dihapus.")
    cb["deductions"] = keep
    cb.setdefault("timeline", []).append(_tl(
        "potongan_hapus", f"Potongan dihapus: {gone.get('label', '')}", actor.get("name", ""),
        _rp(gone.get("amount"))))
    await _save(cb)
    return await decorate(cb)


async def decide(cb_id: str, payload: Dict[str, Any], actor: Dict[str, Any],
                 entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Keputusan BERLABEL atas satu pengecualian 3-way (INV-CB-03)."""
    cb = await _get(cb_id, entity_ids)
    if cb["status"] not in ("draft", "submitted", "disputed"):
        raise ContraBonError("Keputusan selisih hanya bisa diambil sebelum verifikasi.")
    key = (payload.get("exception_key") or "").strip()
    action = (payload.get("action") or "").strip()
    if action not in {a["action"] for a in EXCEPTION_ACTIONS}:
        valid = ", ".join(f"\u201c{a['label']}\u201d" for a in EXCEPTION_ACTIONS)
        raise ContraBonError(f"Tindakan tidak dikenal. Pilihan: {valid}.")
    exc = None
    for b in cb.get("bills", []):
        for e in ((b.get("match") or {}).get("exceptions") or []):
            if e.get("key") == key:
                exc = e
                break
    if not exc:
        raise ContraBonError("Pengecualian 3-way tidak ditemukan (mungkin sudah hilang setelah "
                            "toleransi diubah). Muat ulang kontrabonnya.")
    already = {d.get("exception_key") for d in (cb.get("decisions") or [])}
    if key in already:
        raise ContraBonError("Selisih ini sudah diputus. Hapus keputusannya dulu bila ingin ganti.")
    reason = await _reason_or_fail(payload.get("reason_code", ""), "keputusan selisih")
    amount = _round(payload.get("amount")) if payload.get("amount") not in (None, "") \
        else _round(exc.get("amount"))

    cb.setdefault("decisions", []).append({
        "at": now_iso(), "by": actor.get("name", ""), "by_id": actor.get("id", ""),
        "exception_key": key, "bill_id": exc.get("bill_id", ""),
        "action": action, "reason_code": reason["code"], "reason_label": reason.get("label", ""),
        "amount": amount, "note": payload.get("note", ""),
        "exception_detail": exc.get("detail", ""),
    })
    label = next(a["label"] for a in EXCEPTION_ACTIONS if a["action"] == action)
    cb.setdefault("timeline", []).append(_tl(
        "keputusan", f"Selisih diputus: {label}", actor.get("name", ""),
        f"{exc.get('detail', '')} · alasan: {reason.get('label', '')}"))
    await _save(cb)

    if action == "deduct":
        return await add_deduction(cb["id"], {
            "kind": "match_variance", "bill_id": exc.get("bill_id", ""),
            "exception_key": key, "amount": amount, "reason_code": reason["code"],
            "note": payload.get("note") or exc.get("detail", ""),
        }, actor, entity_ids)
    if action == "dispute":
        return await dispute(cb["id"], {"reason_code": reason["code"],
                                        "note": payload.get("note") or exc.get("detail", "")},
                             actor, entity_ids)
    return await decorate(cb)


async def submit(cb_id: str, actor: Dict[str, Any],
                 entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cb = await _get(cb_id, entity_ids)
    if cb["status"] not in ("draft", "disputed"):
        raise ContraBonError(
            f"Kontrabon berstatus '{STATUS_LABEL.get(cb['status'], cb['status'])}' tidak bisa "
            "diajukan lagi.")
    if not cb.get("bills"):
        raise ContraBonError("Kontrabon tanpa tagihan tidak bisa diajukan.")
    cb["status"] = "submitted"
    cb["submitted_at"] = now_iso()
    cb["submitted_by"] = actor.get("name", "")
    cb.setdefault("timeline", []).append(_tl("diajukan", "Diajukan untuk verifikasi",
                                             actor.get("name", "")))
    await _save(cb)
    return await decorate(cb)


async def verify(cb_id: str, actor: Dict[str, Any],
                 entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Jalankan ulang 3-way match; selisih di luar toleransi wajib sudah diputus."""
    cb = await _get(cb_id, entity_ids)
    if cb["status"] != "submitted":
        raise ContraBonError(
            f"Verifikasi hanya untuk kontrabon berstatus 'Diajukan' (sekarang: "
            f"{STATUS_LABEL.get(cb['status'], cb['status'])}).")
    pol = await policy(cb.get("entity_id", ""))
    for b in cb.get("bills", []):
        bill = await db.vendor_bills.find_one({"id": b["bill_id"]}, {"_id": 0})
        if not bill:
            raise ContraBonError(f"Tagihan {b.get('bill_number')} sudah tidak ada.")
        if bill.get("status") not in ("posted", "paid"):
            raise ContraBonError(
                f"Tagihan {b.get('bill_number')} berubah status menjadi "
                f"'{bill.get('status')}' — keluarkan dari kontrabon lalu ulangi.")
        b["match"] = await _bill_match(bill, pol)
        b["claim_deduction_info"] = _round(bill.get("claim_deduction"))
    recompute(cb)
    pending = cb["match_summary"]["pending_count"]
    if pending and pol["require_reason"]:
        keys = cb["match_summary"]["pending_keys"]
        details = []
        for b in cb.get("bills", []):
            for e in ((b.get("match") or {}).get("exceptions") or []):
                if e.get("key") in keys:
                    details.append(f"{e.get('bill_number')} · {e.get('product_name')}: "
                                   f"{e.get('detail')}")
        raise ContraBonError(
            f"Masih ada {pending} selisih 3-way di luar toleransi yang belum diputus. "
            "Setiap selisih wajib diputus berlabel (terima / potong / sengketakan) sebelum "
            "kontrabon bisa diverifikasi. Rinciannya: " + " | ".join(details[:5]))
    cb["status"] = "verified"
    cb["verified_at"] = now_iso()
    cb["verified_by"] = actor.get("name", "")
    cb["verified_by_id"] = actor.get("id", "")
    cb.setdefault("timeline", []).append(_tl(
        "diverifikasi", "3-way match diverifikasi", actor.get("name", ""),
        f"{cb['match_summary']['exceptions_count']} selisih · "
        f"toleransi {pol['qty_tolerance_percent']:g}% / {_rp(pol['value_tolerance_rupiah'])}"))
    await _save(cb)
    return await decorate(cb, pol)


def role_rank(role: str) -> int:
    return {"warehouse": 1, "sales": 1, "manager": 2, "admin": 3}.get((role or "").lower(), 0)


async def approve(cb_id: str, actor: Dict[str, Any],
                  entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cb = await _get(cb_id, entity_ids)
    if cb["status"] != "verified":
        raise ContraBonError(
            f"Persetujuan hanya untuk kontrabon 'Terverifikasi' (sekarang: "
            f"{STATUS_LABEL.get(cb['status'], cb['status'])}).")
    pol = await policy(cb.get("entity_id", ""))
    recompute(cb)
    net = cb["totals"]["net_payable"]
    need = pol["high_value_role"] if net >= pol["approval_threshold"] > 0 else pol["approval_role"]
    if role_rank(actor.get("role")) < role_rank(need):
        raise ContraBonError(
            f"Kontrabon {_rp(net)} butuh persetujuan peran minimal '{need}'"
            + (f" (di atas ambang {_rp(pol['approval_threshold'])})"
               if net >= pol["approval_threshold"] > 0 else "")
            + f". Peran Anda: '{actor.get('role')}'.")
    if cb.get("created_by_id") and cb["created_by_id"] == actor.get("id"):
        raise ContraBonError(
            "Pemisahan tugas: pembuat kontrabon tidak boleh menyetujui kontrabon sendiri.")
    cb["status"] = "approved"
    cb["approved_at"] = now_iso()
    cb["approved_by"] = actor.get("name", "")
    cb["approved_by_id"] = actor.get("id", "")
    cb["approved_role"] = actor.get("role", "")
    cb.setdefault("timeline", []).append(_tl(
        "disetujui", "Kontrabon disetujui", actor.get("name", ""),
        f"{_rp(net)} · peran {actor.get('role')}"))
    await _save(cb)
    return await decorate(cb, pol)


async def schedule(cb_id: str, payload: Dict[str, Any], actor: Dict[str, Any],
                   entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cb = await _get(cb_id, entity_ids)
    if cb["status"] not in ("approved", "scheduled_payment"):
        raise ContraBonError("Penjadwalan pembayaran hanya untuk kontrabon yang sudah disetujui.")
    when = (payload.get("planned_payment_date") or "").strip()
    if not when:
        raise ContraBonError("Tanggal rencana pembayaran wajib diisi.")
    cb["schedule"] = {
        "planned_payment_date": when,
        "method": payload.get("method") or "transfer",
        "bank_account_id": payload.get("bank_account_id", ""),
        "notes": payload.get("notes", ""),
    }
    cb["status"] = "scheduled_payment"
    cb.setdefault("timeline", []).append(_tl(
        "dijadwalkan", "Pembayaran dijadwalkan", actor.get("name", ""),
        f"{when} · {payload.get('method') or 'transfer'}"))
    await _save(cb)
    return await decorate(cb)


async def dispute(cb_id: str, payload: Dict[str, Any], actor: Dict[str, Any],
                  entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cb = await _get(cb_id, entity_ids)
    if cb["status"] not in ("submitted", "verified", "approved", "scheduled_payment"):
        raise ContraBonError("Hanya kontrabon berjalan yang bisa disengketakan.")
    if _round(cb.get("totals", {}).get("paid_total")) > EPS:
        raise ContraBonError("Kontrabon yang sudah ada pembayaran tidak bisa disengketakan — "
                             "buat kasus keuangan bila uangnya perlu dikoreksi.")
    reason = await _reason_or_fail(payload.get("reason_code", ""), "sengketa")
    cb["status"] = "disputed"
    cb["disputed_at"] = now_iso()
    cb["dispute_reason_code"] = reason["code"]
    cb["dispute_note"] = payload.get("note", "")
    cb.setdefault("timeline", []).append(_tl(
        "sengketa", "Kontrabon disengketakan", actor.get("name", ""),
        f"{reason.get('label', '')} · {payload.get('note', '')}"))
    await _save(cb)
    return await decorate(cb)


async def cancel(cb_id: str, payload: Dict[str, Any], actor: Dict[str, Any],
                 entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cb = await _get(cb_id, entity_ids)
    if _round(cb.get("totals", {}).get("paid_total")) > EPS:
        raise ContraBonError("Kontrabon yang sudah dibayar tidak bisa dibatalkan.")
    if cb["status"] not in ("draft", "submitted", "verified", "disputed"):
        raise ContraBonError(
            f"Kontrabon berstatus '{STATUS_LABEL.get(cb['status'], cb['status'])}' tidak bisa "
            "dibatalkan.")
    cb["status"] = "cancelled"
    cb["cancelled_at"] = now_iso()
    cb["cancel_note"] = payload.get("note", "")
    cb.setdefault("timeline", []).append(_tl("dibatalkan", "Kontrabon dibatalkan",
                                             actor.get("name", ""), payload.get("note", "")))
    await _save(cb)
    return await decorate(cb)


# ═════════════════════════════════════════════════════════════════════════════
#  PEMBAYARAN (satu kas keluar untuk banyak faktur + potongan non-kas)
# ═════════════════════════════════════════════════════════════════════════════
async def _apply_deductions(cb: Dict[str, Any], actor: Dict[str, Any]) -> float:
    """Terapkan potongan SEKALI: jurnal untuk yang butuh, lalu kembalikan totalnya.

    Potongan `purchase_return` TIDAK dijurnal ulang — `Dr 2-1100 / Cr 1-1300` sudah
    diposting saat retur disetujui. Kalau dijurnal lagi, Hutang berkurang dua kali.
    """
    total = 0.0
    for d in (cb.get("deductions") or []):
        amount = _round(d.get("amount"))
        total = _round(total + amount)
        if d.get("applied_at"):
            continue
        if d.get("posts_gl"):
            je = await gl_service.post_contra_bon_deduction(
                cb_id=cb["id"], deduction_id=d["id"], entity_id=cb.get("entity_id", ""),
                kind=d["kind"], amount=amount,
                label=f"{cb.get('number')} · {d.get('ref_number') or d.get('label', '')}")
            d["gl_journal_id"] = (je or {}).get("id", "")
        d["applied_at"] = now_iso()
        d["applied_by"] = actor.get("name", "")
    return total


async def _settle_bills(cb: Dict[str, Any], amount: float, actor: Dict[str, Any],
                        source: str, cash_txn: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Alokasikan `amount` ke sisa `applied_amount` faktur (urut tanggal faktur).

    Setiap faktur menerima entri `payments[]` sehingga **subledger hutang** ikut turun —
    inilah yang membuat GL dan daftar hutang kembali rekonsiliasi.
    """
    left = _round(amount)
    touched: List[Dict[str, Any]] = []
    for b in cb.get("bills", []):
        if left <= EPS:
            break
        room = _round(_round(b.get("applied_amount")) - _round(b.get("settled_amount")))
        if room <= EPS:
            continue
        take = _round(min(room, left))
        left = _round(left - take)
        b["settled_amount"] = _round(_round(b.get("settled_amount")) + take)
        entry = {
            "id": new_id("pay"), "amount": take,
            "method": "kontrabon" if source == "cash" else f"kontrabon:{source}",
            "cash_txn_id": (cash_txn or {}).get("id", ""),
            "cash_txn_number": (cash_txn or {}).get("number", ""),
            "cash_type": (cash_txn or {}).get("cash_type", ""),
            "contra_bon_id": cb["id"], "contra_bon_number": cb.get("number", ""),
            "notes": (f"Pelunasan lewat kontrabon {cb.get('number')}"
                      + ("" if source == "cash" else " (potongan non-kas)")),
            "paid_by": actor.get("name", ""), "paid_at": now_iso(),
        }
        bill = await db.vendor_bills.find_one({"id": b["bill_id"]}, {"_id": 0})
        if not bill:
            continue
        grand = _round(bill.get("grand_total"))
        new_paid = _round(_round(bill.get("amount_paid")) + take)
        sets: Dict[str, Any] = {"amount_paid": new_paid, "updated_at": now_iso()}
        if new_paid + EPS >= grand:
            sets["status"] = "paid"
        await db.vendor_bills.update_one({"id": b["bill_id"]}, {
            "$set": sets,
            "$push": {"payments": entry,
                      "timeline": {"at": now_iso(), "event": "paid",
                                   "label": "Pelunasan lewat kontrabon",
                                   "actor": actor.get("name", ""),
                                   "note": f"{_rp(take)} · {cb.get('number')}"
                                           + ("" if source == "cash" else " (potongan)")}}})
        touched.append({"bill_id": b["bill_id"], "bill_number": b.get("bill_number", ""),
                        "amount": take, "source": source})
    if left > EPS:
        raise ContraBonError(
            f"Sisa {_rp(left)} tidak bisa dialokasikan — nilai yang dibayar melebihi sisa "
            "tagihan di kontrabon ini.")
    return touched


async def pay(cb_id: str, payload: Dict[str, Any], actor: Dict[str, Any],
              entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cb = await _get(cb_id, entity_ids)
    pol = await policy(cb.get("entity_id", ""))
    allowed = ("approved", "scheduled_payment") if pol["block_pay_before_approval"] \
        else ("verified", "approved", "scheduled_payment")
    if cb["status"] not in allowed:
        raise ContraBonError(
            f"Kontrabon berstatus '{STATUS_LABEL.get(cb['status'], cb['status'])}' belum bisa "
            "dibayar. " + ("Wajib disetujui lebih dulu (kebijakan Pusat Pengaturan)."
                           if pol["block_pay_before_approval"] else
                           "Verifikasi 3-way match dulu."))
    recompute(cb)
    outstanding = cb["totals"]["outstanding"]
    first_payment = not (cb.get("payments") or [])
    amount = _round(payload.get("amount")) if payload.get("amount") not in (None, "") \
        else outstanding
    if amount < 0:
        raise ContraBonError("Nominal pembayaran tidak boleh negatif.")
    if amount > outstanding + EPS:
        raise ContraBonError(
            f"Nominal {_rp(amount)} melebihi sisa bersih kontrabon ({_rp(outstanding)}).")
    if amount <= EPS and outstanding > EPS:
        raise ContraBonError("Nominal pembayaran harus lebih besar dari nol.")

    # (1) Potongan diterapkan SEKALI, pada pembayaran pertama.
    ded_total = 0.0
    ded_alloc: List[Dict[str, Any]] = []
    if first_payment:
        ded_total = await _apply_deductions(cb, actor)
        if ded_total > EPS:
            ded_alloc = await _settle_bills(cb, ded_total, actor, source="deduction")

    # (2) Kas keluar — SATU transaksi untuk seluruh faktur (inilah inti kontrabon).
    cash_doc = None
    cash_alloc: List[Dict[str, Any]] = []
    if amount > EPS:
        cash_type = payload.get("cash_type") or "kas_besar"
        # FASE E-7 (E7.4) — pembayaran kontrabon adalah uang SATU badan usaha
        # (kontrabonnya milik satu PT), jadi tidak lagi ditulis ke kas grup.
        from services.cash_entity_service import resolve_owner
        cash_entity = resolve_owner(cb.get("entity_id"), DEFAULT_ENTITY_ID,
                                    what="Kas keluar kontrabon")
        cash_doc = {
            "id": new_id("cash"),
            "number": await next_doc_number("cash_transactions", "number", "CASH-",
                                            entity_id=cash_entity),
            "cash_type": cash_type, "direction": "out", "amount": amount,
            "category": "pembelian",
            "description": (f"Pembayaran kontrabon {cb.get('number')} — "
                            f"{cb.get('supplier_name', '')} "
                            f"({len(cb.get('bills') or [])} faktur, "
                            f"{payload.get('method') or 'transfer'})"),
            "entity_id": cash_entity, "ref_type": "contra_bon", "ref_id": cb["id"],
            "ref_number": cb.get("number", ""),
            "owner_entity_id": cb.get("entity_id") or DEFAULT_ENTITY_ID,
            "account_id": payload.get("bank_account_id", ""),
            "counterparty_name": cb.get("supplier_name", ""),
            "txn_date": payload.get("paid_at") or now_iso(), "status": "posted",
            "created_by": actor.get("name", ""), "created_at": now_iso(), "updated_at": now_iso(),
        }
        await db.cash_transactions.insert_one(dict(cash_doc))
        await gl_service.post_cash_transaction(cash_doc)
        cash_alloc = await _settle_bills(cb, amount, actor, source="cash", cash_txn=cash_doc)
        cb.setdefault("payments", []).append({
            "id": new_id("cbp"), "amount": amount,
            "method": payload.get("method") or "transfer",
            "cash_type": cash_type, "cash_txn_id": cash_doc["id"],
            "cash_txn_number": cash_doc["number"],
            "bank_account_id": payload.get("bank_account_id", ""),
            "bank_line_id": payload.get("bank_line_id", ""),
            "notes": payload.get("notes", ""),
            "paid_by": actor.get("name", ""), "paid_at": cash_doc["txn_date"],
            "allocations": cash_alloc,
        })

    recompute(cb)
    if cb["totals"]["outstanding"] <= EPS:
        cb["status"] = "paid"
        cb["paid_at"] = now_iso()
    cb.setdefault("timeline", []).append(_tl(
        "dibayar", "Pembayaran dicatat", actor.get("name", ""),
        f"{_rp(amount)}"
        + (f" + potongan {_rp(ded_total)}" if ded_total > EPS else "")
        + (f" · kas {cash_doc['number']}" if cash_doc else " · tanpa kas (habis dipotong)")))
    await _save(cb)

    # Ringkasan PO ikut disegarkan supaya layar PO tidak berbohong soal 'sudah ditagih'.
    from services.vendor_bill_service import sync_po_billing
    for pid in {b.get("po_id") for b in cb.get("bills", []) if b.get("po_id")}:
        await sync_po_billing(pid)
    if cash_doc:
        from services import doc_refs_service as refs
        await refs.safe_link(("contra_bon", cb["id"]), ("cash_transaction", cash_doc["id"]),
                             "settles", note="pembayaran kontrabon")
    out = await decorate(cb, pol)
    out["payment_result"] = {
        "cash_transaction": safe_doc(cash_doc) if cash_doc else None,
        "cash_allocations": cash_alloc, "deduction_allocations": ded_alloc,
        "deductions_applied": _round(ded_total),
    }
    return out


async def pay_from_bank_line(cb_id: str, line_id: str, actor: Dict[str, Any],
                             entity_ids: Optional[List[str]] = None,
                             payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """FASE G-8 ↔ G-7 — bayar kontrabon LANGSUNG dari baris mutasi bank keluar.

    Alurnya sengaja dibalik dari kebiasaan: petugas melihat uang keluar di rekening,
    lalu menunjuk kontrabon mana yang dilunasinya. Sistem membuat transaksi kasnya,
    membayar kontrabon, lalu **menautkan** barisnya (rekonsiliasi langsung beres).
    """
    from services import bank_recon_service as bank
    payload = dict(payload or {})
    ln = await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0})
    if not ln:
        raise ContraBonError("Baris mutasi bank tidak ditemukan.")
    if entity_ids is not None:
        ent = ln.get("entity_id") or ""
        if ent and ent != "all" and ent not in entity_ids:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Mutasi bank milik entitas (PT) lain.")
    if ln.get("status") == "matched":
        raise ContraBonError("Baris mutasi itu sudah tertaut ke transaksi lain. Lepaskan dulu.")
    if ln.get("status") == "holding":
        raise ContraBonError("Baris mutasi berstatus titipan dana — batalkan titipannya dulu.")
    if str(ln.get("direction") or "").lower() not in ("out", "debit", "dr"):
        raise ContraBonError("Hanya mutasi dana KELUAR yang bisa dipakai membayar kontrabon.")
    acc = await db.bank_accounts.find_one({"id": ln.get("bank_account_id")}, {"_id": 0}) or {}
    res = await pay(cb_id, {
        "amount": _round(ln.get("amount")),
        "method": payload.get("method") or "transfer",
        "cash_type": acc.get("cash_type") or "kas_besar",
        "bank_account_id": ln.get("bank_account_id", ""),
        "paid_at": ln.get("stmt_date") or now_iso(),
        "bank_line_id": line_id,
        "notes": payload.get("notes") or f"Dari mutasi bank {ln.get('description', '')[:60]}",
    }, actor, entity_ids)
    txn = (res.get("payment_result") or {}).get("cash_transaction") or {}
    if txn.get("id"):
        matched = await bank.manual_match(line_id, txn["id"], actor.get("name", ""), entity_ids)
        res["bank_line"] = matched
    return res


# ═════════════════════════════════════════════════════════════════════════════
#  DAFTAR, RINGKASAN, KANDIDAT BANK
# ═════════════════════════════════════════════════════════════════════════════
async def list_contra_bons(entity_ids: Optional[List[str]] = None, entity_id: str = "",
                           status: str = "", supplier_id: str = "",
                           q: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    flt: Dict[str, Any] = {}
    if status and status != "all":
        flt["status"] = status
    if supplier_id:
        flt["supplier_id"] = supplier_id
    if entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    elif entity_ids is not None:
        flt["entity_id"] = {"$in": list(entity_ids)}
    if q:
        flt["$or"] = [{"number": {"$regex": q, "$options": "i"}},
                      {"supplier_name": {"$regex": q, "$options": "i"}}]
    rows = await db[COLL].find(flt, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return [await decorate(r) for r in rows]


async def status_counts(entity_ids: Optional[List[str]] = None,
                        entity_id: str = "") -> Dict[str, int]:
    match: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        match["entity_id"] = entity_id
    elif entity_ids is not None:
        match["entity_id"] = {"$in": list(entity_ids)}
    agg = await db[COLL].aggregate([
        {"$match": match}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(50)
    counts = {r["_id"]: int(r["n"]) for r in agg if r.get("_id")}
    counts["all"] = sum(counts.values())
    return counts


async def summary(entity_ids: Optional[List[str]] = None, entity_id: str = "") -> Dict[str, Any]:
    """KPI layar Kontrabon — semuanya dihitung dari dokumen, bukan angka hafalan."""
    rows = await list_contra_bons(entity_ids, entity_id, limit=500)
    pol = await policy(entity_id)
    waiting = [r for r in rows if r["status"] in ("submitted", "verified")]
    scheduled = [r for r in rows if r["status"] == "scheduled_payment"]
    disputed = [r for r in rows if r["status"] == "disputed"]
    overdue = [r for r in rows if (r.get("sla") or {}).get("overdue")]
    gr = await unbilled_receipts(entity_ids, entity_id=entity_id)
    due_soon = []
    today = date.today()
    for r in scheduled:
        when = (r.get("schedule") or {}).get("planned_payment_date") or ""
        try:
            d = date.fromisoformat(str(when)[:10])
        except ValueError:
            continue
        if (d - today).days <= 7:
            due_soon.append(r)
    return {
        "waiting_count": len(waiting),
        "waiting_value": _round(sum(r["totals"]["net_payable"] for r in waiting)),
        "scheduled_count": len(scheduled),
        "scheduled_value": _round(sum(r["totals"]["outstanding"] for r in scheduled)),
        "due_soon_count": len(due_soon),
        "due_soon_value": _round(sum(r["totals"]["outstanding"] for r in due_soon)),
        "disputed_count": len(disputed),
        "disputed_value": _round(sum(r["totals"]["net_payable"] for r in disputed)),
        "overdue_count": len(overdue),
        "unbilled_gr_value": gr["total_value"],
        "unbilled_gr_po_count": gr["po_count"],
        "unbilled_gr_overdue": gr["overdue_count"],
        "sla_days": pol["verify_sla_days"],
    }


async def bank_line_candidates(line_id: str, entity_ids: Optional[List[str]] = None,
                               limit: int = 8) -> Dict[str, Any]:
    """Kontrabon yang PANTAS dilunasi oleh satu baris mutasi keluar (untuk modal G-8)."""
    ln = await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0})
    if not ln:
        raise ContraBonError("Baris mutasi bank tidak ditemukan.")
    amount = _round(ln.get("amount"))
    rows = await list_contra_bons(entity_ids, status="", limit=300)
    cands = []
    for r in rows:
        if r["status"] not in ("approved", "scheduled_payment"):
            continue
        out = r["totals"]["outstanding"]
        if out <= EPS:
            continue
        diff = _round(abs(out - amount))
        exact = diff <= EPS
        cands.append({
            "id": r["id"], "number": r["number"], "supplier_name": r.get("supplier_name", ""),
            "status": r["status"], "status_label": r["status_label"],
            "outstanding": out, "amount_diff": diff, "exact": exact,
            "planned_payment_date": (r.get("schedule") or {}).get("planned_payment_date", ""),
            "bills_count": len(r.get("bills") or []),
        })
    cands.sort(key=lambda c: (not c["exact"], c["amount_diff"]))
    return {"line": safe_doc(ln), "candidates": cands[:limit], "line_amount": amount}
