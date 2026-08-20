"""FASE E-1 (E1.9) — DAFTAR KESIAPAN BADAN USAHA.

Entitas baru sering “lahir setengah jadi”: sudah ada di daftar tetapi belum punya
pengguna, rekening, harga jual, atau kop surat — lalu orang bingung kenapa layar
kosong. Daftar ini menjawab “apa lagi yang kurang?” dengan **angka terhitung**
(bukan teks statis) dan setiap baris membawa `view` supaya UI bisa mengantar
pengguna ke layar penyelesaiannya (E-3 `EntityReadinessPanel`).

Dipakai:
  GET /api/entities/{id}/readiness           → daftar lengkap
  GET /api/entities?with_readiness=true      → ringkasan (%) per baris daftar
"""
from typing import Any, Dict, List

from db import db
from services.entity_context_service import is_pkp


async def _usable_warehouses(entity_id: str) -> int:
    """Gudang yang boleh dipakai entitas.

    Sebelum FASE E-4 `warehouses` belum punya `sharing_mode`, jadi gudang tanpa
    field itu dianggap BERSAMA (perilaku hari ini) — bukan dianggap tidak ada,
    supaya angka kesiapan tidak berbohong.
    """
    return await db.warehouses.count_documents({
        "$and": [
            {"$or": [{"active": True}, {"active": {"$exists": False}}]},
            {"$or": [{"sharing_mode": {"$exists": False}},
                     {"sharing_mode": "shared"},
                     {"sharing_mode": "dedicated", "entity_ids": entity_id}]},
        ]})


async def readiness(entity_id: str, entity: Dict[str, Any]) -> Dict[str, Any]:
    ent = entity or {}
    pkp = is_pkp(ent)

    users = await db.users.count_documents({"home_entity_id": entity_id, "status": "active"})
    warehouses = await _usable_warehouses(entity_id)
    banks = await db.bank_accounts.count_documents(
        {"entity_id": {"$in": [entity_id, "all"]}})
    prices = await db.entity_prices.count_documents({"entity_id": entity_id})
    global_prices = await db.products.count_documents({"price": {"$gt": 0}})
    opening = await db.journal_entries.count_documents(
        {"entity_id": entity_id, "source": {"$regex": "opening"}})
    branding = await db.document_branding.count_documents({"entity_id": entity_id})

    items: List[Dict[str, Any]] = [
        {
            "key": "users", "label": "Pengguna",
            "ready": users > 0, "count": users,
            "detail": f"{users} akun aktif ber-badan-usaha utama di sini" if users
                      else "Belum ada akun yang bekerja di badan usaha ini",
            "how_to": "Buat akun di tab “Akun & Akses” dan pilih badan usaha ini sebagai utama.",
            "view": "entities-access",
        },
        {
            "key": "warehouses", "label": "Gudang yang boleh dipakai",
            "ready": warehouses > 0, "count": warehouses,
            "detail": f"{warehouses} gudang tersedia" if warehouses
                      else "Tidak ada gudang yang boleh dipakai badan usaha ini",
            "how_to": "Atur gudang bersama/khusus di Master Data → Gudang.",
            "view": "admin",
        },
        {
            "key": "bank_accounts", "label": "Rekening bank",
            "ready": banks > 0, "count": banks,
            "detail": f"{banks} rekening terdaftar" if banks else "Belum ada rekening",
            "how_to": "Tambah rekening di Keuangan → Rekening & Saldo.",
            "view": "bank-accounts",
        },
        {
            "key": "prices", "label": "Harga jual",
            "ready": (prices > 0) or (global_prices > 0), "count": prices,
            "detail": (f"{prices} harga khusus badan usaha ini" if prices
                       else (f"Belum ada harga khusus — memakai {global_prices} harga global"
                             if global_prices else "Belum ada harga jual sama sekali")),
            "how_to": "Buka Produk & Harga → Pricelist per-PT untuk menimpa harga global.",
            "view": "pricelist",
        },
        {
            "key": "opening_balance", "label": "Saldo awal",
            "ready": opening > 0, "count": opening,
            "detail": f"{opening} jurnal saldo awal" if opening
                      else "Belum ada jurnal saldo awal (stok/kas/piutang pembuka)",
            "how_to": "Catat saldo awal lewat Keuangan → Jurnal & Buku Besar.",
            "view": "general-ledger",
        },
        {
            "key": "branding", "label": "Kop surat & logo",
            "ready": bool(branding or ent.get("logo_url")), "count": branding,
            "detail": "Kop surat sudah diatur" if (branding or ent.get("logo_url"))
                      else "Dokumen cetak masih memakai kop bawaan",
            "how_to": "Atur di Pengaturan → Template PDF (branding per badan usaha).",
            "view": "pdf-templates",
        },
        {
            "key": "tax", "label": "Konfigurasi pajak",
            "ready": bool(ent.get("default_tax_mode")) and (bool(ent.get("npwp")) or not pkp),
            "count": 1 if ent.get("default_tax_mode") else 0,
            "detail": ("PKP — NPWP terisi" if pkp and ent.get("npwp")
                       else "PKP tetapi NPWP masih kosong" if pkp
                       else "Non-PKP — tidak memungut PPN"),
            "how_to": "Lengkapi NPWP di detail badan usaha, atau ubah status PKP-nya.",
            "view": "entities-access",
        },
        {
            "key": "fiscal_year", "label": "Tahun fiskal",
            "ready": bool(ent.get("fiscal_year_start")), "count": 0,
            "detail": f"Mulai {ent.get('fiscal_year_start')}" if ent.get("fiscal_year_start")
                      else "Awal tahun fiskal belum ditetapkan",
            "how_to": "Tetapkan awal tahun fiskal di detail badan usaha.",
            "view": "entities-access",
        },
    ]
    ready_count = sum(1 for i in items if i["ready"])
    return {
        "entity_id": entity_id,
        "items": items,
        "ready": ready_count,
        "total": len(items),
        "percent": round(ready_count * 100 / len(items)) if items else 0,
        "is_ready": ready_count == len(items),
    }


async def readiness_summary(entity_id: str, entity: Dict[str, Any]) -> Dict[str, Any]:
    full = await readiness(entity_id, entity)
    counts = {i["key"]: i.get("count", 0) for i in full["items"]}
    return {"percent": full["percent"], "ready": full["ready"], "total": full["total"],
            "missing": [i["label"] for i in full["items"] if not i["ready"]],
            # FASE E-3 — daftar badan usaha menampilkan "#gudang yang boleh dipakai"
            # tanpa harus memanggil endpoint kesiapan satu-satu per baris.
            "warehouse_count": counts.get("warehouses", 0)}
