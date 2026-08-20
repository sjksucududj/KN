"""F4 — SSOT Status SO 2-level: STAGE (induk, linear) + SUB-STATUS (anak, kontekstual).

Prinsip (KEPUTUSAN OWNER §2):
- STAGE linear: Reserved → Approved → Confirmed → Picked → Shipped → Delivered (+ Cancelled).
- SUB-STATUS: alasan "kenapa berhenti di sini" (boleh kosong / >1).
- ADDITIVE & TIDAK MENGUBAH transisi: `status` lama tetap SSOT transisi; `stage`+`sub_status`
  adalah field TURUNAN dari `status` + konteks (backorder, approval). Aman & idempotent.

Perubahan kunci: `menunggu_stok` (backorder yang SUDAH di-approve) ada di stage **APPROVED**,
bukan Confirmed — order naik ke Confirmed hanya saat stok benar-benar siap.
"""
from typing import Any, Dict, List, Tuple

# Stage (induk)
STAGE_RESERVED = "Reserved"
STAGE_APPROVED = "Approved"
STAGE_CONFIRMED = "Confirmed"
STAGE_PICKED = "Picked"
STAGE_SHIPPED = "Shipped"
STAGE_DELIVERED = "Delivered"
STAGE_CANCELLED = "Cancelled"

# Urutan linear (untuk timeline & perbandingan progres). Cancelled di luar jalur.
STAGE_FLOW: List[str] = [
    STAGE_RESERVED, STAGE_APPROVED, STAGE_CONFIRMED,
    STAGE_PICKED, STAGE_SHIPPED, STAGE_DELIVERED,
]
VALID_STAGES = set(STAGE_FLOW) | {STAGE_CANCELLED}


def _approval_subs(order: Dict[str, Any]) -> List[str]:
    """Sub-status alasan approval. F4 (fondasi): approval berbasis NILAI.
    F5 akan merinci harga/kredit/nilai lewat `pending_approvals`."""
    subs: List[str] = []
    for pa in (order.get("pending_approvals") or []):
        if pa.get("status") == "pending":
            t = pa.get("type")
            subs.append({
                "nilai": "menunggu_approval_nilai",
                "kredit": "menunggu_approval_kredit",
                "special_price": "menunggu_approval_harga",
            }.get(t, "menunggu_approval_nilai"))
    if not subs and order.get("required_approval_role"):
        subs.append("menunggu_approval_nilai")
    return subs or ["menunggu_validasi"]


def derive_stage_substatus(order: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Petakan `status` (+ konteks) → (stage, [sub_status]). Pure function."""
    o = order or {}
    status = o.get("status") or "reserved"
    has_bo = bool(o.get("has_backorder")) or bool(o.get("backorders"))
    appr_required = bool(o.get("approval_required"))

    if status == "cancelled":
        return STAGE_CANCELLED, ["dibatalkan"]
    if status == "expired":
        return STAGE_CANCELLED, ["kedaluwarsa"]
    if status in ("done", "delivered"):
        return STAGE_DELIVERED, []
    if status == "shipped":
        return STAGE_SHIPPED, []
    if status == "partially_shipped":
        return STAGE_SHIPPED, ["sebagian_dikirim"]
    if status == "picked":
        return STAGE_PICKED, ["siap_kirim"]
    if status == "partially_picked":
        return STAGE_PICKED, ["sebagian_dipick"]
    if status == "confirmed":
        return STAGE_CONFIRMED, ["siap_pick"]
    if status == "approved":
        # Backorder yang sudah di-approve BERHENTI di Approved (menunggu_stok).
        return (STAGE_APPROVED, ["menunggu_stok"]) if has_bo else (STAGE_APPROVED, ["siap_confirm"])
    if status == "waiting_approval":
        return STAGE_RESERVED, _approval_subs(o)
    if status == "waiting_stock":
        # Pure backorder pra-approval — masih di Reserved.
        return STAGE_RESERVED, ["menunggu_stok"]
    if status in ("reserved", "draft"):
        # F5 — bila ada pending_approvals (harga/kredit/nilai) → tampilkan alasannya.
        if any(p.get("status") == "pending" for p in (o.get("pending_approvals") or [])):
            return STAGE_RESERVED, _approval_subs(o)
        return (STAGE_RESERVED, ["menunggu_validasi"]) if appr_required else (STAGE_RESERVED, ["siap_disahkan"])
    # fallback aman
    return STAGE_RESERVED, []


def stage_fields(order: Dict[str, Any]) -> Dict[str, Any]:
    """Kembalikan dict `{stage, sub_status}` untuk di-$set ke dokumen SO."""
    stage, sub = derive_stage_substatus(order)
    return {"stage": stage, "sub_status": sub}


def stage_index(stage: str) -> int:
    try:
        return STAGE_FLOW.index(stage)
    except ValueError:
        return -1


# Label manusiawi (dipakai juga sebagai referensi FE / dokumentasi).
SUBSTATUS_LABELS: Dict[str, str] = {
    "menunggu_validasi": "Menunggu validasi admin",
    "menunggu_approval_nilai": "Menunggu approval nilai",
    "menunggu_approval_kredit": "Menunggu approval kredit",
    "menunggu_approval_harga": "Menunggu approval harga khusus",
    "siap_disahkan": "Siap disahkan",
    "menunggu_stok": "Menunggu stok (backorder)",
    "siap_confirm": "Stok siap — bisa di-confirm",
    "siap_pick": "Siap pick (gudang)",
    "sedang_pick": "Sedang dipick",
    "sebagian_dipick": "Sebagian dipick",
    "siap_kirim": "Siap kirim",
    "sebagian_dikirim": "Sebagian dikirim",
    "dibatalkan": "Dibatalkan",
    "kedaluwarsa": "Kedaluwarsa",
}


async def backfill_so_status(database) -> Dict[str, int]:
    """Backfill `stage`+`sub_status` ke SEMUA sales_orders (idempotent, additive).
    Tidak menyentuh `status`. Return statistik {updated, total, invalid}."""
    orders = await database.sales_orders.find(
        {}, {"_id": 0, "id": 1, "status": 1, "has_backorder": 1, "backorders": 1,
             "approval_required": 1, "required_approval_role": 1, "pending_approvals": 1}
    ).to_list(100000)
    updated = 0
    invalid = 0
    for o in orders:
        sf = stage_fields(o)
        if sf["stage"] not in VALID_STAGES:
            invalid += 1
            continue
        await database.sales_orders.update_one({"id": o["id"]}, {"$set": sf})
        updated += 1
    return {"updated": updated, "total": len(orders), "invalid": invalid}


def allowed_action_hint(status: str) -> str:
    """Bug poin 14 — petunjuk aksi relevan per status (dipakai pesan 409 yang memandu)."""
    return {
        "draft": "Pesan ulang / reservasi stok terlebih dulu sebelum diajukan.",
        "reserved": "Ajukan untuk persetujuan (Submit), atau lepas reservasi/batalkan.",
        "waiting_approval": "Menunggu persetujuan admin/manager — setujui atau tolak dari Pusat Persetujuan.",
        "waiting_stock": "Pesanan menunggu stok (backorder). Akan otomatis lanjut saat barang masuk.",
        "approved": "Confirm pesanan saat stok siap untuk membuat tugas gudang (outbound).",
        "confirmed": "Proses pengambilan barang (pick) di gudang.",
        "partially_picked": "Lanjutkan pick sisa barang, lalu kirim.",
        "picked": "Kirim barang (dispatch) untuk membuat Surat Jalan.",
        "partially_shipped": "Lanjutkan pengiriman sisa barang.",
        "shipped": "Tandai diterima customer untuk menyelesaikan pesanan.",
        "done": "Pesanan sudah selesai (terkirim & diterima).",
        "cancelled": "Pesanan sudah dibatalkan.",
        "expired": "Reservasi pesanan kedaluwarsa — buat pesanan baru bila masih diperlukan.",
    }.get(status, "Periksa kembali tahap pesanan sebelum menjalankan aksi ini.")
