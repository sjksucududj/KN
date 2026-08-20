"""FASE G-1 — **FONDASI AMANDEMEN**: tidak ada lagi perubahan angka secara diam-diam.

MASALAH YANG DISELESAIKAN
-------------------------
Sebelum ini ada dua ekstrem yang sama-sama buruk:

1. Dokumen finansial **tidak bisa dikoreksi sama sekali** lewat aplikasi
   (`PATCH /api/sales-orders/{id}` hanya mengizinkan `sales_name`, `shipment_policy`,
   `notes`). Akibatnya koreksi nyata dikerjakan di luar sistem — lewat WhatsApp, atau
   lebih buruk, langsung di database.
2. Kalau field uang dibuka begitu saja, angka bisa berubah **tanpa jejak**: tidak ada
   alasan, tidak ada penyetuju, tidak ada dampak yang tercatat.

Fase ini membuka jalan tengah yang aman:

    KOREKSI = DOKUMEN AMANDEMEN BERNOMOR
      label alasan  +  dampak (Rp & %)  +  persetujuan berbasis dampak
      +  jejak dua arah (refs)  +  audit  +  ledger append-only

DUA CARA MENERAPKAN (dipilih otomatis, dapat dikonfigurasi)
-----------------------------------------------------------
* `re_derive`   — dokumen **belum terbit** (belum difakturkan/dibayar): nilai dihitung
                  ulang memakai mesin harga yang sama dengan pembuatan order, snapshot
                  sebelum-sesudah disimpan.
* `credit_note` / `debit_note` — dokumen **sudah terbit**: angkanya TIDAK PERNAH diubah.
                  Selisihnya diterbitkan sebagai nota yang tertaut ke dokumen asal
                  (aturan repo #7 — ledger append-only, koreksi lewat nota/reversal).

Seluruh ambang ada di registry FASE G-0 (`config_catalog_finance.py`) sehingga admin
bisa mengubahnya dari Pusat Pengaturan tanpa deploy — permintaan eksplisit pemilik
*"jangan hardcode aturan"*.
"""
from typing import Any, Dict, List, Optional, Tuple

from core_utils import new_id, next_doc_number, now_iso, safe_doc, timeline_entry, rupiah
from db import db
from services import config_service
from services.config_resolver import resolve

AMD_COLL = "doc_amendments"
REASON_COLL = "amendment_reasons"

# Field baris dokumen yang boleh dikoreksi lewat amandemen.
EDITABLE_FIELDS = {"quantity", "price", "discount_percent"}
FIELD_LABEL = {
    "quantity": "Jumlah", "price": "Harga satuan", "discount_percent": "Diskon baris (%)",
    "order_discount_percent": "Diskon pesanan (%)",
}

# Label alasan bawaan. Sengaja MINIM & bisa ditambah/dinonaktifkan admin lewat API —
# daftar ini hanya bibit awal, bukan aturan permanen.
DEFAULT_REASONS: List[Dict[str, Any]] = [
    {"code": "data_entry_error", "label": "Salah entri data",
     "help": "Angka yang masuk memang keliru diketik. Koreksi mengembalikan ke nilai benar.",
     "affects_master": False},
    {"code": "price_correction", "label": "Koreksi harga",
     "help": "Harga yang dipakai bukan harga yang disepakati.",
     "affects_master": False},
    {"code": "customer_negotiation", "label": "Negosiasi pelanggan",
     "help": "Pelanggan meminta penyesuaian dan disetujui secara komersial.",
     "affects_master": False},
    {"code": "qty_adjustment", "label": "Perubahan jumlah pesanan",
     "help": "Pelanggan menambah/mengurangi jumlah setelah pesanan dibuat.",
     "affects_master": False},
    {"code": "discount_grant", "label": "Pemberian diskon tambahan",
     "help": "Diskon di luar skema standar, mis. kompensasi keterlambatan.",
     "affects_master": False},
    {"code": "master_price_update", "label": "Harga master berubah",
     "help": "Harga acuan produk diperbarui dan dokumen terbuka ikut disesuaikan.",
     "affects_master": True},
    # FASE G-2 — label alasan untuk keputusan DENDA keterlambatan (bisa ditambah admin).
    {"code": "penalty_waiver", "label": "Pembebasan denda (kebijaksanaan manajemen)",
     "help": "Denda dibebaskan sebagai kebijaksanaan komersial agar hubungan dagang terjaga.",
     "affects_master": False, "applies_to": ["penalty"]},
    {"code": "penalty_negotiation", "label": "Negosiasi denda dengan pelanggan",
     "help": "Nominal denda disepakati lebih rendah setelah pembicaraan dengan pelanggan.",
     "affects_master": False, "applies_to": ["penalty"]},
    {"code": "late_due_to_us", "label": "Keterlambatan karena pihak kami",
     "help": "Pembayaran terlambat karena dokumen/tagihan dari kami terlambat sampai.",
     "affects_master": False, "applies_to": ["penalty"]},
    # FASE G-3 — label alasan untuk keputusan SELISIH PEMBAYARAN (lebih/kurang bayar).
    {"code": "rounding_diff", "label": "Pembulatan / biaya transfer",
     "help": "Selisih receh karena pembulatan nominal atau biaya transfer bank yang "
             "dipotong pihak bank. Masih di dalam toleransi yang diizinkan admin.",
     "affects_master": False, "applies_to": ["payment_variance"]},
    {"code": "bank_charge", "label": "Dipotong biaya bank",
     "help": "Pelanggan mentransfer penuh tetapi bank memotong biaya kirim sehingga uang "
             "yang sampai lebih kecil.",
     "affects_master": False, "applies_to": ["payment_variance", "finance_case"]},
    {"code": "partial_payment_agreed", "label": "Bayar sebagian (disepakati)",
     "help": "Pelanggan hanya mampu membayar sebagian dan sisanya disepakati tetap ditagih "
             "atau dijadwalkan ulang.",
     "affects_master": False, "applies_to": ["payment_variance"]},
    {"code": "term_extension", "label": "Perpanjangan tempo disepakati",
     "help": "Sisa tagihan dijadwalkan ulang ke tanggal baru atas kesepakatan bersama.",
     "affects_master": False, "applies_to": ["payment_variance"]},
    {"code": "uncollectible_small", "label": "Sisa kecil tak layak ditagih",
     "help": "Sisa piutang terlalu kecil dibanding biaya menagihnya, diputus dihapus.",
     "affects_master": False, "applies_to": ["payment_variance"]},
    {"code": "customer_overtransfer", "label": "Pelanggan transfer berlebih",
     "help": "Uang yang masuk lebih besar dari tagihan — perlu diputus jadi deposit, "
             "dialokasikan ke pesanan lain, atau dikembalikan.",
     "affects_master": False, "applies_to": ["payment_variance"]},
    {"code": "customer_refund_request", "label": "Pelanggan minta dana dikembalikan",
     "help": "Kelebihan bayar diminta kembali oleh pelanggan (kas keluar).",
     "affects_master": False, "applies_to": ["payment_variance", "finance_case"]},
    {"code": "supplier_discount", "label": "Potongan dari supplier",
     "help": "Supplier menyetujui sisa tagihan tidak perlu dibayar (potongan/pembulatan).",
     "affects_master": False, "applies_to": ["payment_variance"]},
    {"code": "supplier_advance", "label": "Uang muka / titipan ke supplier",
     "help": "Kelebihan bayar ke supplier disepakati menjadi uang muka yang dipotongkan "
             "pada tagihan atau kontrabon berikutnya.",
     "affects_master": False, "applies_to": ["payment_variance", "finance_case", "contra_bon"]},
    # FASE G-7 — label alasan untuk KONTRABON (keputusan selisih 3-way & potongan).
    {"code": "cb_return_credit", "label": "Potongan retur beli (nota debit)",
     "help": "Barang sudah dikembalikan dan supplier setuju nilainya dipotong dari tagihan "
             "siklus ini. Jurnalnya sudah lahir saat retur disetujui.",
     "affects_master": False, "applies_to": ["contra_bon"]},
    {"code": "cb_supplier_late", "label": "Denda keterlambatan supplier",
     "help": "Supplier terlambat mengirim melewati kesepakatan dan dendanya dipotong dari "
             "tagihan.",
     "affects_master": False, "applies_to": ["contra_bon"]},
    {"code": "cb_qty_shortfall", "label": "Barang kurang dari yang ditagih",
     "help": "Faktur menagih lebih banyak daripada barang yang benar-benar diterima gudang, "
             "dan supplier setuju selisihnya dipotong.",
     "affects_master": False, "applies_to": ["contra_bon"]},
    {"code": "cb_price_agreed", "label": "Selisih harga sudah disepakati",
     "help": "Harga di faktur berbeda dari harga PO tetapi memang sudah disepakati bersama "
             "(mis. penyesuaian bahan baku), jadi tetap dibayar penuh.",
     "affects_master": False, "applies_to": ["contra_bon"]},
    {"code": "cb_invoice_wrong", "label": "Faktur supplier keliru — minta koreksi",
     "help": "Fakturnya sendiri salah (jumlah/harga/nomor PO), jadi kontrabon ditahan sampai "
             "supplier menerbitkan faktur pengganti.",
     "affects_master": False, "applies_to": ["contra_bon"]},
    {"code": "cb_other_agreed", "label": "Potongan lain yang disepakati",
     "help": "Potongan di luar jenis baku yang disetujui kedua pihak; catat kesepakatannya "
             "di keterangan supaya bisa dibaca auditor.",
     "affects_master": False, "applies_to": ["contra_bon"]},
    # FASE G-9 — label alasan untuk penyelesaian KASUS KEUANGAN (Pusat Kasus Keuangan).
    {"code": "case_wrong_account", "label": "Salah rekening tujuan",
     "help": "Pelanggan mentransfer ke rekening perusahaan yang bukan tujuan, sehingga "
             "dananya perlu dipindah-bukukan ke rekening yang benar.",
     "affects_master": False, "applies_to": ["finance_case"]},
    {"code": "case_employee_account", "label": "Masuk rekening pribadi karyawan",
     "help": "Uang perusahaan sempat dipegang karyawan karena pelanggan mentransfer ke "
             "rekening pribadinya; wajib diakui sebagai piutang karyawan lalu disetorkan.",
     "affects_master": False, "applies_to": ["finance_case"]},
    {"code": "case_identified_owner", "label": "Pemilik dana ketemu",
     "help": "Dana yang tadinya tak dikenal akhirnya terbukti milik pelanggan tertentu "
             "sehingga bisa dialokasikan ke pesanannya.",
     "affects_master": False, "applies_to": ["finance_case"]},
    {"code": "case_third_party_payer", "label": "Dibayar pihak ketiga atas nama pelanggan",
     "help": "Transfer datang dari nama orang/PT lain, dan pelanggan memberi bukti bahwa "
             "pembayaran itu memang atas namanya.",
     "affects_master": False, "applies_to": ["finance_case"]},
    {"code": "case_duplicate_payment", "label": "Terbukti bayar dua kali",
     "help": "Pembayaran yang sama masuk dua kali; kelebihannya dikembalikan atau dipakai "
             "untuk pesanan lain.",
     "affects_master": False, "applies_to": ["finance_case"]},
    {"code": "case_wrong_invoice", "label": "Menempel di pesanan yang salah",
     "help": "Pembayaran tercatat melunasi pesanan yang bukan tujuan pelanggan sehingga "
             "alokasinya dipindahkan.",
     "affects_master": False, "applies_to": ["finance_case"]},
    {"code": "case_cheque_bounced", "label": "Cek / giro ditolak bank",
     "help": "Bank menolak pencairan cek/giro sehingga pembayaran yang sudah dicatat harus "
             "dibatalkan dan piutang hidup kembali.",
     "affects_master": False, "applies_to": ["finance_case"]},
    {"code": "case_wrong_entity", "label": "Masuk ke PT yang salah",
     "help": "Uang diterima PT lain dalam grup, padahal tagihannya milik PT ini; "
             "diselesaikan lewat settlement antar entitas.",
     "affects_master": False, "applies_to": ["finance_case"]},
    {"code": "case_unidentified_returned", "label": "Dana tak dikenal dikembalikan",
     "help": "Sampai batas waktu pemilik dana tidak ditemukan, sehingga uangnya "
             "dikembalikan ke pengirim.",
     "affects_master": False, "applies_to": ["finance_case"]},
]


class AmendmentError(ValueError):
    """Kesalahan yang pesannya SIAP TAMPIL ke user (Bahasa Indonesia)."""


# ── Label alasan (configurable) ─────────────────────────────────────────────
async def ensure_reasons() -> None:
    """Pasang label alasan bawaan bila belum ada (idempotent, aman dipanggil ulang).

    **Perluasan taksonomi ikut sampai ke basis data yang sudah jalan.** Dulu fungsi ini
    hanya memakai `$setOnInsert`, sehingga saat sebuah label lama dipakai domain BARU
    (mis. FASE G-9 memakai `bank_charge` & `customer_refund_request` untuk kasus keuangan)
    dokumen yang sudah ada tidak pernah diperbarui — akibatnya penyelesaian kasus ditolak
    dengan pesan *"label alasan bukan untuk kasus keuangan"* padahal kodenya sudah benar.
    Kini `applies_to` di-`$addToSet` supaya domain baru menempel, sementara `label`/`help`
    TIDAK ditimpa (admin boleh menyunting kalimatnya sendiri).
    """
    for row in DEFAULT_REASONS:
        applies = row.get("applies_to") or ["sales_order"]
        await db[REASON_COLL].update_one(
            {"code": row["code"]},
            {"$setOnInsert": {
                "id": new_id("amr"), "code": row["code"], "label": row["label"],
                "help": row["help"],
                "affects_master": row["affects_master"], "status": "active",
                "created_at": now_iso(), "updated_at": now_iso(),
            },
             "$addToSet": {"applies_to": {"$each": list(applies)}}},
            upsert=True,
        )


async def list_reasons(doc_type: str = "", include_inactive: bool = False) -> List[Dict[str, Any]]:
    await ensure_reasons()
    flt: Dict[str, Any] = {} if include_inactive else {"status": "active"}
    if doc_type:
        flt["applies_to"] = doc_type
    rows = await db[REASON_COLL].find(flt, {"_id": 0}).sort("label", 1).to_list(500)
    return [safe_doc(r) for r in rows]


async def upsert_reason(payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    code = (payload.get("code") or "").strip()
    if not code:
        raise AmendmentError("Kode label alasan wajib diisi.")
    if not (payload.get("label") or "").strip():
        raise AmendmentError("Nama label alasan wajib diisi.")
    now = now_iso()
    doc = {
        "code": code, "label": payload["label"].strip(), "help": payload.get("help", ""),
        "applies_to": payload.get("applies_to") or ["sales_order"],
        "affects_master": bool(payload.get("affects_master")),
        "status": payload.get("status") or "active",
        "updated_at": now, "updated_by": actor,
    }
    await db[REASON_COLL].update_one(
        {"code": code},
        {"$set": doc, "$setOnInsert": {"id": new_id("amr"), "created_at": now}},
        upsert=True,
    )
    return safe_doc(await db[REASON_COLL].find_one({"code": code}, {"_id": 0}))


# ── Kebijakan (dibaca dari registry FASE G-0) ───────────────────────────────
async def _cfg(key: str, entity_id: str = "") -> Any:
    res = await resolve(key, {"entity_id": entity_id or ""})
    return res["value"]


async def policy_snapshot(entity_id: str = "") -> Dict[str, Any]:
    """Rekam ambang yang BERLAKU SAAT ITU, supaya keputusan bisa diaudit ulang nanti."""
    return {
        "approval_threshold_amount": float(await _cfg("amendment.approval_threshold_amount", entity_id)),
        "approval_threshold_pct": float(await _cfg("amendment.approval_threshold_pct", entity_id)),
        "approver_role": str(await _cfg("amendment.approver_role", entity_id)),
        "admin_approval_above": float(await _cfg("amendment.admin_approval_above", entity_id)),
        "dual_control": bool(await _cfg("amendment.dual_control", entity_id)),
        "require_note_above": float(await _cfg("amendment.require_note_above", entity_id)),
        "issued_doc_policy": str(await _cfg("amendment.issued_doc_policy", entity_id)),
        "captured_at": now_iso(),
    }


# ── Dokumen sumber ───────────────────────────────────────────────────────────
async def _load_order(doc_id: str) -> Dict[str, Any]:
    order = safe_doc(await db.sales_orders.find_one({"id": doc_id}, {"_id": 0}))
    if not order:
        raise AmendmentError("Pesanan tidak ditemukan.")
    return order


async def is_issued(order: Dict[str, Any]) -> Tuple[bool, str]:
    """Apakah dokumen sudah 'terbit' sehingga angkanya tidak boleh diubah lagi?

    Terbit = sudah ada Faktur Pajak aktif, ATAU sudah dibayar (sebagian/penuh),
    ATAU sudah masuk tahap penyelesaian. Alasannya dikembalikan agar bisa
    ditampilkan ke user (bukan penolakan tanpa penjelasan).
    """
    inv = await db.tax_invoices.find_one(
        {"order_id": order["id"], "status": {"$ne": "cancelled"}}, {"_id": 0, "number": 1})
    if inv:
        return True, f"sudah terbit Faktur Pajak {inv.get('number', '')}".strip()
    if float(order.get("paid_total", 0) or 0) > 0 or order.get("payment_status") in {"paid", "partial"}:
        return True, "sudah ada pembayaran masuk"
    if order.get("status") in {"delivered", "completed", "closed"}:
        return True, f"pesanan sudah berstatus '{order.get('status')}'"
    return False, ""


def _apply_changes(items: List[Dict[str, Any]], changes: List[Dict[str, Any]]
                   ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Terapkan perubahan ke SALINAN item; kembalikan (item_baru, diff_terbaca)."""
    new_items = [dict(it) for it in items]
    by_pid = {it.get("product_id"): it for it in new_items}
    diff: List[Dict[str, Any]] = []
    for ch in changes:
        pid = ch.get("product_id")
        field = ch.get("field")
        if field not in EDITABLE_FIELDS:
            raise AmendmentError(
                f"Field '{field}' tidak bisa dikoreksi lewat amandemen "
                f"(yang boleh: {', '.join(sorted(EDITABLE_FIELDS))}).")
        item = by_pid.get(pid)
        if not item:
            raise AmendmentError(f"Baris produk '{pid}' tidak ada di pesanan ini.")
        old = float(item.get(field, 0) or 0)
        new = float(ch.get("to", 0) or 0)
        if new < 0:
            raise AmendmentError(f"{FIELD_LABEL.get(field, field)} tidak boleh negatif.")
        if field == "quantity" and new <= 0:
            raise AmendmentError("Jumlah harus lebih dari nol. Untuk membatalkan baris, "
                                 "gunakan pembatalan pesanan atau retur.")
        if abs(old - new) < 0.0001:
            continue
        item[field] = new
        diff.append({
            "product_id": pid,
            "product_name": item.get("product_name") or item.get("sku") or pid,
            "field": field, "label": FIELD_LABEL.get(field, field),
            "from": old, "to": new,
        })
    return new_items, diff


async def _reason_or_fail(reason_code: str, doc_type: str) -> Dict[str, Any]:
    await ensure_reasons()
    reason = safe_doc(await db[REASON_COLL].find_one(
        {"code": reason_code, "status": "active"}, {"_id": 0}))
    if not reason:
        raise AmendmentError(
            "Label alasan wajib dipilih dan harus yang masih aktif. "
            "Admin bisa menambah label baru di Pusat Amandemen.")
    if reason.get("applies_to") and doc_type not in reason["applies_to"]:
        raise AmendmentError(f"Label alasan '{reason['label']}' tidak berlaku untuk {doc_type}.")
    return reason


def evaluate_policy(delta: float, base_amount: float, policy: Dict[str, Any],
                    issued: bool) -> Dict[str, Any]:
    """Tentukan: perlu approval? oleh siapa? diterapkan dengan cara apa?

    Membaca ambang dari `policy` (snapshot registry) — TIDAK ada angka hardcode di sini,
    sehingga aturannya benar-benar bisa diubah admin tanpa deploy.
    """
    abs_delta = abs(round(delta, 2))
    pct = (abs_delta / base_amount * 100.0) if base_amount else 0.0

    over_amount = abs_delta >= policy["approval_threshold_amount"] > 0
    over_pct = pct >= policy["approval_threshold_pct"] > 0
    requires_approval = bool(over_amount or over_pct)

    required_role = policy["approver_role"]
    if abs_delta >= policy["admin_approval_above"] > 0:
        required_role = "admin"
        requires_approval = True

    if issued and policy["issued_doc_policy"] == "note_only":
        method = "credit_note" if delta < 0 else "debit_note"
    else:
        method = "re_derive"

    reasons: List[str] = []
    if over_amount:
        reasons.append(
            f"Dampak {rupiah(abs_delta)} mencapai ambang Rp "
            f"{policy['approval_threshold_amount']:,.0f}".replace(",", "."))
    if over_pct:
        reasons.append(
            f"Dampak {pct:.2f}% mencapai ambang {policy['approval_threshold_pct']}%")
    if required_role == "admin" and abs_delta >= policy["admin_approval_above"] > 0:
        reasons.append(
            f"Dampak {rupiah(abs_delta)} di atas batas admin Rp "
            f"{policy['admin_approval_above']:,.0f}".replace(",", "."))
    if not reasons:
        reasons.append("Dampak di bawah semua ambang — boleh langsung diterapkan.")

    return {
        "requires_approval": requires_approval,
        "required_role": required_role if requires_approval else "",
        "method": method,
        "delta_pct": round(pct, 4),
        "explain": reasons,
    }


# ── Pratinjau (tanpa menyimpan apa pun) ─────────────────────────────────────
async def preview(doc_type: str, doc_id: str, changes: List[Dict[str, Any]],
                  reason_code: str = "",
                  order_discount_percent: Optional[float] = None) -> Dict[str, Any]:
    if doc_type != "sales_order":
        raise AmendmentError(f"Jenis dokumen '{doc_type}' belum didukung amandemen.")
    order = await _load_order(doc_id)
    entity_id = order.get("entity_id") or ""
    policy = await policy_snapshot(entity_id)
    issued, issued_reason = await is_issued(order)

    new_items, diff = _apply_changes(order.get("items") or [], changes)
    disc = (float(order.get("order_discount_percent", 0) or 0)
            if order_discount_percent is None else float(order_discount_percent))
    if order_discount_percent is not None and abs(
            disc - float(order.get("order_discount_percent", 0) or 0)) > 0.0001:
        diff.append({"product_id": "", "product_name": "Pesanan",
                     "field": "order_discount_percent",
                     "label": FIELD_LABEL["order_discount_percent"],
                     "from": float(order.get("order_discount_percent", 0) or 0), "to": disc})

    if not diff:
        raise AmendmentError("Tidak ada perubahan yang diusulkan.")

    priced = await config_service.compute_order_pricing(
        new_items, entity_id=entity_id, order_discount_percent=disc)

    before = float(order.get("grand_total", 0) or 0)
    after = float(priced.get("grand_total", 0) or 0)
    delta = round(after - before, 2)

    # Kejujuran mesin: perubahan yang TIDAK berdampak harus dikatakan, bukan diterima
    # diam-diam lalu "berhasil" tanpa efek apa pun (itu bentuk lain tombol palsu).
    if abs(delta) < 0.01:
        settings = await config_service.get_effective_settings(entity_id)
        sales_cfg = (settings or {}).get("sales", {}) or {}
        touched = {c["field"] for c in diff}
        if "discount_percent" in touched and not sales_cfg.get("allow_item_discount", True):
            raise AmendmentError(
                "Diskon per baris sedang DINONAKTIFKAN, jadi perubahan ini tidak akan "
                "mengubah nilai dokumen sama sekali. Aktifkan dulu 'Boleh memberi diskon "
                "per baris' di Pusat Pengaturan → Harga, Diskon & Komisi, atau koreksi "
                "harga satuannya langsung.")
        if "order_discount_percent" in touched and not sales_cfg.get("allow_order_discount", True):
            raise AmendmentError(
                "Diskon tingkat pesanan sedang DINONAKTIFKAN, jadi perubahan ini tidak "
                "berdampak. Aktifkan dulu di Pusat Pengaturan → Harga, Diskon & Komisi.")
        raise AmendmentError(
            "Perubahan ini tidak mengubah nilai dokumen sama sekali — tidak ada yang "
            "perlu diamandemen.")

    verdict = evaluate_policy(delta, before, policy, issued)

    return {
        "doc_type": doc_type, "doc_id": doc_id,
        "doc_number": order.get("number", ""), "entity_id": entity_id,
        "reason_code": reason_code,
        "issued": issued, "issued_reason": issued_reason,
        "changes": diff,
        "before": {"grand_total": before,
                   "total_amount": float(order.get("total_amount", 0) or 0),
                   "ppn_amount": float(order.get("ppn_amount", 0) or 0)},
        "after": {"grand_total": after,
                  "total_amount": float(priced.get("total_amount", 0) or 0),
                  "ppn_amount": float(priced.get("ppn_amount", 0) or 0)},
        "impact": {"amount_before": before, "amount_after": after,
                   "delta": delta, "delta_pct": verdict["delta_pct"]},
        "policy": policy,
        "requires_approval": verdict["requires_approval"],
        "required_role": verdict["required_role"],
        "method": verdict["method"],
        "method_label": {
            "re_derive": "Dokumen dihitung ulang (belum terbit)",
            "credit_note": "Terbit Nota Kredit (nilai turun) — dokumen asal tidak diubah",
            "debit_note": "Terbit Nota Debit (nilai naik) — dokumen asal tidak diubah",
        }[verdict["method"]],
        "explain": verdict["explain"],
        "_priced": priced, "_new_items": new_items, "_order_discount_percent": disc,
    }


# ── Usul ─────────────────────────────────────────────────────────────────────
async def propose(doc_type: str, doc_id: str, reason_code: str,
                  changes: List[Dict[str, Any]], actor: Dict[str, Any],
                  note: str = "", attachments: Optional[List[Dict[str, Any]]] = None,
                  order_discount_percent: Optional[float] = None) -> Dict[str, Any]:
    reason = await _reason_or_fail(reason_code, doc_type)
    pv = await preview(doc_type, doc_id, changes, reason_code, order_discount_percent)
    policy = pv["policy"]
    abs_delta = abs(pv["impact"]["delta"])

    if policy["require_note_above"] > 0 and abs_delta >= policy["require_note_above"] \
            and not (note or "").strip():
        raise AmendmentError(
            f"Koreksi sebesar {rupiah(abs_delta)} wajib disertai penjelasan tertulis "
            f"(ambang {rupiah(policy['require_note_above'])}).")

    entity_id = pv["entity_id"]
    number = await next_doc_number(AMD_COLL, "number", "AMD-", entity_id=entity_id or None)
    now = now_iso()
    amd: Dict[str, Any] = {
        "id": new_id("amd"), "number": number, "entity_id": entity_id,
        "doc_type": doc_type, "doc_id": doc_id, "doc_number": pv["doc_number"],
        "reason_code": reason_code, "reason_label": reason["label"],
        "affects_master": bool(reason.get("affects_master")),
        "note": (note or "").strip(), "attachments": attachments or [],
        "changes": pv["changes"], "before": pv["before"], "after": pv["after"],
        "impact": pv["impact"], "method": pv["method"], "method_label": pv["method_label"],
        "issued": pv["issued"], "issued_reason": pv["issued_reason"],
        "policy_snapshot": policy, "explain": pv["explain"],
        "requires_approval": pv["requires_approval"],
        "required_role": pv["required_role"],
        "status": "pending_approval" if pv["requires_approval"] else "approved",
        "proposed_by": actor.get("name", ""), "proposed_by_id": actor.get("id", ""),
        "proposed_at": now,
        "decided_by": "", "decided_by_id": "", "decided_at": "", "decision_note": "",
        "applied_at": "", "result_refs": [],
        "refs": [],   # FASE G-4 — ditulis DUA ARAH lewat services/doc_refs_service
        "payload": {"items": pv["_new_items"],
                    "order_discount_percent": pv["_order_discount_percent"]},
        "created_at": now, "updated_at": now,
    }
    await db[AMD_COLL].insert_one(dict(amd))
    # Tautkan amandemen ↔ dokumen yang diamandemen SEJAK DIUSULKAN (bukan setelah
    # disetujui): usulan yang masih menunggu pun harus terlihat saat menelusuri
    # dokumennya, dan relasi tidak boleh pernah berada dalam keadaan satu arah.
    from services import doc_refs_service as _refs
    await _refs.safe_link(("doc_amendment", amd["id"]), (doc_type, doc_id),
                          "amends", note=reason["label"])

    if not pv["requires_approval"]:
        # Dampak di bawah semua ambang → langsung diterapkan, TETAP dengan dokumen
        # amandemen bernomor + alasan + jejak. "Cepat" bukan berarti "senyap".
        amd = await _apply(amd, actor, auto=True)
    else:
        await _notify_approvers(amd)
    return safe_doc(await db[AMD_COLL].find_one({"id": amd["id"]}, {"_id": 0}))


# ── Putusan ──────────────────────────────────────────────────────────────────
async def decide(amd_id: str, action: str, actor: Dict[str, Any],
                 note: str = "") -> Dict[str, Any]:
    amd = safe_doc(await db[AMD_COLL].find_one({"id": amd_id}, {"_id": 0}))
    if not amd:
        raise AmendmentError("Amandemen tidak ditemukan.")
    if amd["status"] != "pending_approval":
        raise AmendmentError(
            f"Amandemen {amd['number']} sudah berstatus '{amd['status']}' — "
            "tidak bisa diputus dua kali.")

    policy = amd.get("policy_snapshot") or await policy_snapshot(amd.get("entity_id", ""))
    role = actor.get("role") or ""
    need = amd.get("required_role") or policy["approver_role"]
    if role != "admin" and role != need:
        raise AmendmentError(
            f"Amandemen ini harus diputus oleh {need}. Peran Anda: {role or 'tidak dikenal'}.")
    if policy.get("dual_control") and actor.get("id") and actor["id"] == amd.get("proposed_by_id"):
        raise AmendmentError(
            "Kontrol ganda aktif: pengusul tidak boleh menyetujui usulannya sendiri. "
            "Minta rekan dengan wewenang yang sama untuk memutus.")

    now = now_iso()
    if action == "reject":
        await db[AMD_COLL].update_one({"id": amd_id}, {"$set": {
            "status": "rejected", "decided_by": actor.get("name", ""),
            "decided_by_id": actor.get("id", ""), "decided_at": now,
            "decision_note": note, "updated_at": now}})
        await _close_approval_notice(amd_id, "ditolak", actor)
        return safe_doc(await db[AMD_COLL].find_one({"id": amd_id}, {"_id": 0}))

    if action != "approve":
        raise AmendmentError("Aksi harus 'approve' atau 'reject'.")

    await db[AMD_COLL].update_one({"id": amd_id}, {"$set": {
        "status": "approved", "decided_by": actor.get("name", ""),
        "decided_by_id": actor.get("id", ""), "decided_at": now,
        "decision_note": note, "updated_at": now}})
    amd = safe_doc(await db[AMD_COLL].find_one({"id": amd_id}, {"_id": 0}))
    amd = await _apply(amd, actor, auto=False)
    await _close_approval_notice(amd_id, "disetujui", actor)
    return safe_doc(await db[AMD_COLL].find_one({"id": amd["id"]}, {"_id": 0}))


# ── Penerapan ────────────────────────────────────────────────────────────────
async def _apply(amd: Dict[str, Any], actor: Dict[str, Any], auto: bool) -> Dict[str, Any]:
    if amd["method"] == "re_derive":
        refs = await _apply_re_derive(amd, actor)
    else:
        refs = await _apply_note(amd, actor)

    now = now_iso()
    await db[AMD_COLL].update_one({"id": amd["id"]}, {"$set": {
        "status": "auto_applied" if auto else "applied",
        "applied_at": now, "result_refs": refs, "updated_at": now,
        "refs": (amd.get("refs") or []) + refs,
    }})
    return safe_doc(await db[AMD_COLL].find_one({"id": amd["id"]}, {"_id": 0}))


async def _apply_re_derive(amd: Dict[str, Any], actor: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Dokumen belum terbit → hitung ulang memakai mesin harga yang sama."""
    order = await _load_order(amd["doc_id"])
    payload = amd.get("payload") or {}
    priced = await config_service.compute_order_pricing(
        payload.get("items") or order.get("items") or [],
        entity_id=order.get("entity_id") or "",
        order_discount_percent=float(payload.get("order_discount_percent", 0) or 0))

    patch: Dict[str, Any] = {k: v for k, v in priced.items() if k != "settings"}
    patch["order_discount_percent"] = float(payload.get("order_discount_percent", 0) or 0)
    patch["updated_at"] = now_iso()
    patch["last_amendment_id"] = amd["id"]
    patch["last_amendment_number"] = amd["number"]

    await db.sales_orders.update_one({"id": order["id"]}, {
        "$set": patch,
        "$inc": {"amendment_count": 1},
        "$push": {
            "timeline": timeline_entry(
                "amended", f"Amandemen {amd['number']} diterapkan — {amd['reason_label']}",
                actor.get("name", ""),
                f"{rupiah(amd['impact']['amount_before'])} → Rp "
                f"{amd['impact']['amount_after']:,.0f}".replace(",", ".")),
            # Jejak dua arah ditulis lewat LAYANAN PUSAT (services/doc_refs_service)
            # agar dedupe, kosakata relasi, dan sakelar admin berlaku sama untuk semua
            # dokumen — lihat pemanggilan `safe_link` di bawah.
        },
    })
    from services import doc_refs_service as _refs
    await _refs.safe_link(("doc_amendment", amd["id"]), ("sales_order", order["id"]),
                          "amends", note=amd["reason_label"])
    return [{"rel": "applied_to", "doc_type": "sales_order", "doc_id": order["id"],
             "doc_number": order.get("number", ""), "note": "dihitung ulang"}]


async def _apply_note(amd: Dict[str, Any], actor: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Dokumen sudah terbit → TERBITKAN NOTA. Dokumen asal TIDAK disentuh angkanya."""
    order = await _load_order(amd["doc_id"])
    entity_id = order.get("entity_id") or ""
    kind = "credit_note" if amd["method"] == "credit_note" else "debit_note"
    prefix = "CN-" if kind == "credit_note" else "DN-"
    number = await next_doc_number("credit_notes", "number", prefix,
                                   entity_id=entity_id or None)

    delta = float(amd["impact"]["delta"])
    gross = round(abs(delta), 2)
    before = amd["before"]
    after = amd["after"]
    ppn_delta = round(abs(float(after.get("ppn_amount", 0) or 0)
                          - float(before.get("ppn_amount", 0) or 0)), 2)
    net = round(gross - ppn_delta, 2)

    now = now_iso()
    note_doc = {
        "id": new_id("cn" if kind == "credit_note" else "dn"), "number": number,
        "kind": kind, "source": "amendment",
        "amendment_id": amd["id"], "amendment_number": amd["number"],
        "order_id": order["id"], "order_number": order.get("number", ""),
        "customer_id": order.get("customer_id"), "customer_name": order.get("customer_name", ""),
        "entity_id": entity_id,
        "reason_code": amd["reason_code"], "reason_label": amd["reason_label"],
        "note": amd.get("note", ""),
        "lines": [{"product_id": c.get("product_id"), "product_name": c.get("product_name"),
                   "field": c.get("field"), "from": c.get("from"), "to": c.get("to")}
                  for c in amd.get("changes") or []],
        "net_amount": net, "ppn_amount": ppn_delta, "gross_amount": gross,
        "direction": "decrease" if delta < 0 else "increase",
        "status": "issued",
        "created_by": actor.get("name", ""), "created_at": now, "updated_at": now,
        "refs": [],   # ditulis lewat services/doc_refs_service (dua arah) setelah insert
    }
    await db.credit_notes.insert_one(dict(note_doc))

    # Dokumen asal HANYA menerima jejak — nominalnya sengaja tidak diubah sama sekali.
    await db.sales_orders.update_one({"id": order["id"]}, {
        "$inc": {"amendment_count": 1},
        "$set": {"last_amendment_id": amd["id"], "last_amendment_number": amd["number"],
                 "updated_at": now},
        "$push": {
            "timeline": timeline_entry(
                "amended_by_note",
                f"{'Nota Kredit' if kind == 'credit_note' else 'Nota Debit'} {number} "
                f"diterbitkan — {amd['reason_label']}",
                actor.get("name", ""),
                f"{rupiah(gross)} (dokumen asal tidak diubah)"),
        },
    })
    # FASE G-4 — nota koreksi WAJIB menyebut dokumen yang dikoreksi DAN amandemen
    # yang menerbitkannya; keduanya dua arah supaya bisa ditelusuri dari sisi mana pun.
    # Nota Kredit & Nota Debit berbagi koleksi `credit_notes` → doc_type kanonik di
    # peta relasi juga satu (`credit_note`); memakai "debit_note" akan membuat tautan
    # ditolak diam-diam dan surat lahir tanpa jejak.
    from services import doc_refs_service as _refs
    _rt = "credit_note"
    await _refs.safe_link((_rt, note_doc["id"]), ("sales_order", order["id"]),
                          "corrects", note=amd["reason_label"])
    await _refs.safe_link((_rt, note_doc["id"]), ("doc_amendment", amd["id"]),
                          "issued_by", note=amd["reason_label"])
    await _refs.safe_link(("doc_amendment", amd["id"]), ("sales_order", order["id"]),
                          "amends", note=amd["reason_label"])
    return [{"rel": "issued", "doc_type": kind, "doc_id": note_doc["id"],
             "doc_number": number, "note": f"{rupiah(gross)}"}]


async def _close_approval_notice(amd_id: str, outcome: str, actor: Dict[str, Any]) -> None:
    """Padamkan notifikasi 'menunggu persetujuan' setelah amandemen diputus.

    Tanpa ini lonceng penyetuju tetap menampilkan permintaan yang sudah selesai.
    Best-effort: kegagalan notifikasi tidak boleh membatalkan keputusan.
    """
    try:
        from services import notification_service as ns
        await ns.resolve_action("amendment", amd_id, outcome=outcome,
                                actor=actor.get("name", ""))
    except Exception:  # noqa: BLE001
        return


# ── Notifikasi ke penyetuju ─────────────────────────────────────────────────
async def _notify_approvers(amd: Dict[str, Any]) -> None:
    try:
        from services import notification_service as ns
    except Exception:  # noqa: BLE001 — notifikasi best-effort, jangan gagalkan usulan
        return
    role = amd.get("required_role") or "manager"
    delta = abs(float(amd["impact"]["delta"]))
    try:
        await ns.create_notification(
            notif_type="amendment_approval",
            title=f"Amandemen {amd['number']} menunggu persetujuan",
            body=(f"{amd['doc_number']} — {amd['reason_label']} · dampak "
                  f"{rupiah(delta)}"),
            severity="warning",
            recipient_role=role,
            entity_id=amd.get("entity_id") or None,
            # `link` dipakai Notification Center untuk melompat ke Pusat Amandemen.
            link="amendments",
            ref=amd["id"],
            action_type="amendment", action_id=amd["id"], action_role=role,
        )
    except Exception:  # noqa: BLE001
        return


# ── Query ────────────────────────────────────────────────────────────────────
async def list_amendments(flt: Dict[str, Any], limit: int = 200) -> List[Dict[str, Any]]:
    rows = await db[AMD_COLL].find(flt, {"_id": 0}).sort("proposed_at", -1).to_list(limit)
    return [safe_doc(r) for r in rows]


async def get_amendment(amd_id: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db[AMD_COLL].find_one({"id": amd_id}, {"_id": 0}))


async def stats(flt: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db[AMD_COLL].find(flt, {"_id": 0, "status": 1, "impact": 1}).to_list(5000)
    out = {"total": len(rows), "pending_approval": 0, "approved": 0, "applied": 0,
           "auto_applied": 0, "rejected": 0, "impact_total": 0.0}
    for r in rows:
        out[r.get("status", "")] = out.get(r.get("status", ""), 0) + 1
        if r.get("status") in {"applied", "auto_applied"}:
            out["impact_total"] += abs(float((r.get("impact") or {}).get("delta", 0) or 0))
    out["impact_total"] = round(out["impact_total"], 2)
    return out


async def notes_for_order(order_id: str) -> List[Dict[str, Any]]:
    rows = await db.credit_notes.find(
        {"order_id": order_id, "source": "amendment"}, {"_id": 0}).to_list(500)
    return [safe_doc(r) for r in rows]
