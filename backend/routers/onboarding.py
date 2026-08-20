"""Onboarding router: per-role checklists for first-time users."""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from db import db
from dependencies import current_user, audit
from core_utils import now_iso, safe_doc

router = APIRouter(prefix="/api")

ROLE_CHECKLISTS: Dict[str, List[Dict[str, Any]]] = {
    "admin": [
        {"id": "create_warehouse", "label": "Buat gudang pertama", "description": "Tambahkan gudang di Gudang \u2192 Gudang (Master)"},
        {"id": "create_uom", "label": "Buat UOM pertama", "description": "Tambahkan satuan di Penjualan \u2192 Produk & Harga \u2192 Satuan (UOM)"},
        {"id": "create_product", "label": "Buat produk pertama", "description": "Tambahkan produk kain di Penjualan \u2192 Produk & Harga \u2192 Produk (Master)"},
        {"id": "configure_template", "label": "Konfigurasi document template", "description": "Atur template Surat Jalan/Invoice di Pengaturan & Master Data \u2192 Templates"},
        {"id": "create_user", "label": "Buat pengguna baru", "description": "Tambahkan user (Sales/Warehouse) di Pengaturan & Master Data \u2192 Users"},
        {"id": "set_permissions", "label": "Tinjau matriks izin", "description": "Cek permission per role di Pengaturan & Master Data \u2192 Permissions"},
    ],
    "sales": [
        {"id": "browse_products", "label": "Jelajahi katalog produk", "description": "Lihat produk tersedia di Sales POS"},
        {"id": "add_customer", "label": "Tambah atau pilih pelanggan", "description": "Buat pelanggan baru atau pilih yang sudah ada"},
        {"id": "create_order", "label": "Buat pesanan penjualan pertama", "description": "Buat pesanan dan reservasi stok otomatis"},
        {"id": "submit_approval", "label": "Kirim pesanan untuk persetujuan", "description": "Kirim pesanan ke manager untuk disetujui"},
        {"id": "print_document", "label": "Cetak dokumen pesanan", "description": "Buat dan cetak Surat Jalan atau Faktur"},
    ],
    "manager": [
        {"id": "check_dashboard", "label": "Cek Dasbor Manajer", "description": "Tinjau KPI stok, pesanan, dan gudang"},
        {"id": "approve_order", "label": "Setujui pesanan penjualan", "description": "Tinjau dan setujui pesanan yang masuk"},
        {"id": "review_stock_aging", "label": "Tinjau umur stok", "description": "Identifikasi stok lama di laporan"},
        {"id": "run_cycle_count", "label": "Jalankan stock opname", "description": "Buat sesi stock opname untuk gudang"},
        {"id": "export_report", "label": "Ekspor laporan", "description": "Ekspor data produk atau pelanggan ke CSV"},
    ],
    "warehouse": [
        {"id": "check_wms_tasks", "label": "Cek antrean tugas WMS", "description": "Lihat daftar tugas barang masuk/keluar"},
        {"id": "scan_inbound", "label": "Proses barang masuk pertama", "description": "Scan dan konfirmasi penerimaan barang"},
        {"id": "advance_task", "label": "Lanjutkan tugas ke tahap berikutnya", "description": "Klik Lanjutkan Tahap untuk memperbarui status"},
        {"id": "scan_outbound", "label": "Proses tugas barang keluar", "description": "Buat barang keluar dari pesanan terkonfirmasi"},
        {"id": "dispatch_shipment", "label": "Kirim barang", "description": "Selesaikan tugas barang keluar sampai status terkirim"},
    ],
}


@router.get("/onboarding")
async def get_onboarding(request: Request) -> Dict[str, Any]:
    user = await current_user(request)
    record = safe_doc(
        await db.user_onboarding.find_one({"user_id": user["id"]}, {"_id": 0})
    )
    checklist = ROLE_CHECKLISTS.get(user["role"], [])
    completed_ids = record.get("completed", []) if record else []
    items = [
        {**item, "completed": item["id"] in completed_ids}
        for item in checklist
    ]
    return {
        "user_id": user["id"],
        "role": user["role"],
        "items": items,
        "total": len(items),
        "completed_count": len(completed_ids),
        "progress_pct": round(len(completed_ids) / len(checklist) * 100) if checklist else 0,
    }


@router.post("/onboarding/{task_id}/complete")
async def complete_task(task_id: str, request: Request) -> Dict[str, Any]:
    user = await current_user(request)
    valid_ids = {item["id"] for item in ROLE_CHECKLISTS.get(user["role"], [])}
    if task_id not in valid_ids:                              # S#074 ONBOARD-NOOP
        raise HTTPException(status_code=404, detail="Task onboarding tidak dikenal untuk role ini")
    await db.user_onboarding.update_one(
        {"user_id": user["id"]},
        {"$addToSet": {"completed": task_id}, "$set": {"updated_at": now_iso()}},
        upsert=True
    )
    await audit(user["name"], "onboarding_completed", "user", user["id"], {"task_id": task_id})
    return {"task_id": task_id, "completed": True}


@router.post("/onboarding/reset")
async def reset_onboarding(request: Request) -> Dict[str, Any]:
    user = await current_user(request)
    await db.user_onboarding.delete_one({"user_id": user["id"]})
    return {"message": "Pengenalan direset"}
