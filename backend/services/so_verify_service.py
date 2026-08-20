"""FASE E-8 (E8.13) — **VERIFIKASI ADMINISTRATIF** pesanan oleh Admin Sales.

KENAPA BERKAS INI ADA (temuan A7 `ANALISIS_DOMAIN_SALES.md`)
==========================================================
Sampai E-7 hanya ada SATU gerbang sebelum pesanan boleh dikonfirmasi: **persetujuan
nilai** yang menuntut peran manajer. Akibatnya pekerjaan administratif rutin —
"alamat kirimnya lengkap? syarat bayarnya sudah dipilih? PPN-nya benar? pelanggan
minta faktur pajak tapi NPWP-nya kosong?" — menumpuk di meja manajer, sementara
tidak ada satu pun tempat yang mencatat siapa yang sudah MEMERIKSA kelengkapan itu.

Berkas ini memisahkan keduanya:

* **Verifikasi (Admin Sales)** — kelengkapan dokumen. Bukan cap stempel: bila ada
  cacat yang menghalangi (alamat/syarat bayar/isi pesanan) verifikasi **DITOLAK**
  dengan daftar yang bisa ditindak, bukan "gagal" telanjang.
* **Persetujuan (Manajer)** — nilai, kredit, harga khusus. Tidak disentuh di sini.

Hasil verifikasi menempel pada dokumen pesanannya (`sales_orders.verification`),
jadi TIDAK ada koleksi baru dan tidak ada yang perlu didaftarkan di
`ENTITY_REGISTRY.md`.
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso, safe_doc

#: Status pesanan yang masih pantas diverifikasi (belum jalan ke gudang).
VERIFIABLE_STATUSES = ("draft", "reserved", "waiting_stock", "waiting_approval", "approved")

#: Status pesanan yang sudah lewat titik verifikasi.
PAST_STATUSES = ("confirmed", "partially_picked", "picked", "partially_shipped",
                 "shipped", "done", "cancelled")

CONFIG_REQUIRE_VERIFY = "sales_admin.require_verification_before_confirm"


class VerifyError(Exception):
    """Kegagalan ber-alasan (dipetakan ke 409 oleh router)."""

    def __init__(self, message: str, checks: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.checks = checks or []


async def _config_bool(key: str, entity_id: str) -> bool:
    from services import config_resolver
    try:
        return bool(await config_resolver.value_of(key, {"entity_id": entity_id}))
    except Exception:  # noqa: BLE001 — config tak boleh menjatuhkan alur pesanan
        return False


def _addr_gaps(order: Dict[str, Any]) -> List[str]:
    addr = order.get("shipping_address") or {}
    perlu = (("address", "alamat jalan"), ("city", "kota"),
             ("recipient_name", "nama penerima"), ("phone", "telepon penerima"))
    return [label for field, label in perlu if not str(addr.get(field) or "").strip()]


async def build_checklist(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Daftar periksa kelengkapan — `blocking=True` berarti menghalangi verifikasi.

    Setiap baris memakai bahasa yang bisa ditindak petugas ("Isi nama penerima &
    telepon"), bukan nama kolom basis data.
    """
    checks: List[Dict[str, Any]] = []

    gaps = _addr_gaps(order)
    checks.append({
        "id": "alamat", "label": "Alamat & penerima lengkap", "blocking": True,
        "ok": not gaps,
        "detail": "Lengkap" if not gaps else "Belum ada: " + ", ".join(gaps),
        "hint": "Surat jalan tanpa nama penerima & telepon membuat kurir menelepon sales.",
    })

    term = str(order.get("payment_term_code") or "").strip()
    checks.append({
        "id": "syarat_bayar", "label": "Syarat pembayaran dipilih", "blocking": True,
        "ok": bool(term),
        "detail": order.get("payment_term_name") or term or "Belum dipilih",
        "hint": "Tanpa syarat bayar, jatuh tempo & penagihan tidak bisa dihitung.",
    })

    items = order.get("items") or []
    # Pesanan yang SELURUHNYA backorder (mis. `SO-0009`) adalah keadaan sah di sistem
    # ini: barang dijanjikan dari PO yang sudah di jalan, barisnya belum dialokasikan.
    # Menghitung `items` saja membuat pesanan seperti itu MUSTAHIL diverifikasi
    # selamanya — dan pesanan itulah yang paling butuh diperiksa, karena dialah yang
    # akan menunggu barang. Karena itu baris backorder ikut dihitung sebagai isi.
    backorders = [b for b in (order.get("backorders") or [])
                  if float(b.get("backorder_qty") or 0) > 0]
    baris = len(items) + len(backorders)
    qty_ok = baris > 0 and all(float(it.get("quantity") or 0) > 0 for it in items)
    if items and backorders:
        detail_isi = f"{len(items)} baris + {len(backorders)} baris kurang stok"
    elif backorders:
        detail_isi = f"{len(backorders)} baris kurang stok (belum dialokasikan)"
    elif items:
        detail_isi = f"{len(items)} baris"
    else:
        detail_isi = "Belum ada item"
    checks.append({
        "id": "isi_pesanan", "label": "Isi pesanan wajar (ada item, jumlah > 0)",
        "blocking": True, "ok": qty_ok,
        "detail": detail_isi,
        "hint": "Pesanan tanpa baris tidak bisa dipenuhi gudang.",
    })

    is_pkp = order.get("is_pkp") is not False
    ppn = float(order.get("ppn_amount") or 0)
    nilai = float(order.get("net_subtotal") or order.get("total_amount") or 0)
    if is_pkp and nilai <= 0:
        # Belum ada nilai yang bisa dikenai pajak (pesanan murni backorder). Menandai
        # ini "PPN NOL — periksa mode PPN" adalah peringatan palsu: peringatan palsu
        # melatih petugas mengabaikan seluruh peringatan.
        checks.append({
            "id": "pajak", "label": "Perlakuan PPN sesuai status badan usaha",
            "blocking": False, "ok": True,
            "detail": "PKP · nilai pesanan belum terbentuk — PPN dihitung saat baris dialokasikan",
            "hint": "Salah perlakuan PPN baru ketahuan saat faktur pajak ditolak Coretax.",
        })
    else:
        pajak_ok = (ppn > 0) if is_pkp else (ppn == 0)
        checks.append({
            "id": "pajak", "label": "Perlakuan PPN sesuai status badan usaha",
            "blocking": False, "ok": pajak_ok,
            "detail": ("PKP · PPN " + ("terisi" if ppn > 0 else "NOL — periksa mode PPN"))
                      if is_pkp else
                      ("Non-PKP · PPN " + ("nol (benar)" if ppn == 0
                                           else "TERISI — seharusnya nol")),
            "hint": "Salah perlakuan PPN baru ketahuan saat faktur pajak ditolak Coretax.",
        })

    npwp = ""
    if order.get("customer_id"):
        cust = safe_doc(await db.customers.find_one(
            {"id": order["customer_id"]}, {"_id": 0, "npwp": 1, "credit_limit": 1})) or {}
        npwp = str(cust.get("npwp") or "").strip()
    minta_faktur = bool(order.get("needs_tax_invoice"))
    checks.append({
        "id": "npwp", "label": "NPWP pelanggan (bila minta Faktur Pajak)",
        "blocking": False, "ok": (not minta_faktur) or bool(npwp),
        "detail": npwp or ("Pelanggan minta faktur tetapi NPWP kosong" if minta_faktur
                           else "Tidak diminta"),
        "hint": "Faktur pajak tanpa NPWP pembeli tidak bisa diunggah.",
    })

    hold = bool(order.get("credit_hold"))
    checks.append({
        "id": "kredit", "label": "Tidak tertahan batas kredit", "blocking": False,
        "ok": not hold,
        "detail": "Tertahan — butuh keputusan manajer" if hold else "Aman",
        "hint": "Penahanan kredit adalah keputusan manajer, bukan verifikasi Anda.",
    })
    return checks


def summarize(checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    blokir = [c for c in checks if c["blocking"] and not c["ok"]]
    peringatan = [c for c in checks if not c["blocking"] and not c["ok"]]
    return {
        "blocking_gaps": [c["label"] for c in blokir],
        "warnings": [c["label"] for c in peringatan],
        "ready": not blokir,
        "checked": len(checks),
    }


async def preview(order: Dict[str, Any]) -> Dict[str, Any]:
    """Pratinjau daftar periksa (read-only) — dipakai dialog sebelum menekan Verifikasi."""
    checks = await build_checklist(order)
    return {
        "order_id": order.get("id"), "order_number": order.get("number"),
        "status": order.get("status"),
        "verifiable": order.get("status") in VERIFIABLE_STATUSES,
        "verification": order.get("verification") or None,
        "checks": checks, **summarize(checks),
    }


async def verify(order: Dict[str, Any], actor: Dict[str, Any], note: str = "") -> Dict[str, Any]:
    """Tandai pesanan TERVERIFIKASI secara administratif.

    Menolak (VerifyError) bila masih ada cacat yang menghalangi — verifikasi yang
    selalu berhasil sama saja dengan tidak ada verifikasi.
    """
    if order.get("status") in PAST_STATUSES:
        raise VerifyError(
            f"Pesanan {order.get('number')} sudah melewati tahap verifikasi "
            f"(status sekarang: {order.get('status')}).")
    checks = await build_checklist(order)
    ringkas = summarize(checks)
    if not ringkas["ready"]:
        raise VerifyError(
            "Belum bisa diverifikasi — lengkapi dulu: " + " · ".join(ringkas["blocking_gaps"]),
            checks)

    rec = {
        "status": "verified",
        "by": actor.get("name", ""),
        "by_id": actor.get("id", ""),
        "by_role": actor.get("role", ""),
        "at": now_iso(),
        "note": (note or "").strip()[:400],
        "warnings": ringkas["warnings"],
        "checks": [{"id": c["id"], "label": c["label"], "ok": c["ok"], "detail": c["detail"]}
                   for c in checks],
    }
    await db.sales_orders.update_one(
        {"id": order["id"]},
        {"$set": {"verification": rec, "updated_at": now_iso()},
         "$push": {"status_history": {"status": order.get("status"),
                                      "stage": "verified_by_sales_admin",
                                      "timestamp": rec["at"], "user": rec["by"],
                                      "note": "Kelengkapan administratif diverifikasi"}}})
    return {"order_id": order["id"], "order_number": order.get("number"),
            "verification": rec, **ringkas}


async def assert_ready_to_confirm(order: Dict[str, Any]) -> None:
    """Gerbang opsional sebelum Konfirmasi SO (config, bawaan MATI).

    Sengaja tidak dinyalakan otomatis: instalasi yang sudah berjalan tidak boleh
    mendadak menolak konfirmasi yang tadinya sah. Pemilik bisa menyalakannya di
    Pusat Pengaturan → Persetujuan & Ambang kapan pun tanpa deploy.
    """
    if (order.get("verification") or {}).get("status") == "verified":
        return
    if not await _config_bool(CONFIG_REQUIRE_VERIFY, order.get("entity_id") or ""):
        return
    from fastapi import HTTPException
    raise HTTPException(
        status_code=409,
        detail=("Verifikasi kelengkapan dulu (alamat · syarat bayar · isi pesanan) "
                "sebelum pesanan ini dikonfirmasi — buka Meja Admin Sales → "
                "antrean “Perlu diverifikasi”."))
