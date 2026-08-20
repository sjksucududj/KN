"""FASE E-8 (E8.4 · US11) — **SATU definisi "Pesanan Saya"**.

KENAPA BERKAS INI ADA
=====================
Temuan SD5/SD8 (`ANALISIS_DOMAIN_SALES.md`): `sales2@` (Bima) membuka daftar pesanan
dan melihat **8 pesanan milik rekannya**, nol miliknya. Penyaringannya hanya
per-badan-usaha, jadi seluruh sales dalam satu PT saling melihat pipeline, harga
negosiasi, dan pelanggan satu sama lain.

Keputusan pemilik E8.10 (MENGIKAT) menutup itu dengan satu kalimat: sales lapangan
mengurus **basis pelanggan sendiri** dan melihat **hanya pesanan miliknya**.

KENAPA JADI SATU MODUL, BUKAN `if role == "sales"` DI TIAP ENDPOINT
-------------------------------------------------------------------
"Pesanan saya" harus berarti SAMA di daftar pesanan, di ringkasan angka di atasnya,
di laporan pelanggan teratas, dan di detail satu pesanan. Kalau definisinya disalin
empat kali, cukup satu salinan tertinggal untuk membuat **angka ringkasan tidak cocok
dengan isi daftar** — kelas bug yang paling melelahkan dilacak karena keduanya
"terlihat benar" sendiri-sendiri.

KEPEMILIKAN DIBACA DARI TIGA JEJAK, BUKAN SATU
----------------------------------------------
Pesanan bisa lahir dari tiga jalan yang sama sahnya:

* dibuat sendiri oleh sales           → `created_by == user.id`
* dibuat Admin Sales/kasir POS **atas nama** sales  → `sales_name == user.name`
* pesanan lama hasil migrasi          → `sales_id == user.id`

Memakai `created_by` saja akan MENGHILANGKAN pesanan yang diinput Admin Sales atas
nama sales itu — padahal itu justru pesanan yang paling sering ia tanyakan. Karena
itu ketiganya diperiksa (`$or`).

BATAS WEWENANG
--------------
Pembatasan ini **keras** untuk peran `sales` (bukan sakelar layar yang bisa
dimatikan): peran lain — `sales_admin`, `finance`, `manager`, `admin`, `warehouse` —
memang harus melihat keseluruhan pesanan, tetapi tetap bisa MEMINTA penyaringan
"punya saya" lewat parameter `mine=true`.
"""
from typing import Any, Dict, List, Optional

#: Peran yang WAJIB dibatasi ke pesanan miliknya sendiri (keputusan pemilik E8.10).
OWNER_LOCKED_ROLES = ("sales",)


def is_owner_locked(actor: Optional[Dict[str, Any]]) -> bool:
    """Benar bila peran aktor hanya boleh melihat pesanan miliknya."""
    return str((actor or {}).get("role") or "") in OWNER_LOCKED_ROLES


def owner_clause(actor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Klausa Mongo `$or` untuk "pesanan milik aktor ini".

    Dikembalikan sebagai klausa terpisah (bukan langsung ditempel ke query) supaya
    pemanggil bisa menggabungnya lewat `$and` tanpa menimpa `$or` lain yang mungkin
    sudah ada di query — mis. penyaringan pencarian.
    """
    uid = str((actor or {}).get("id") or "")
    uname = str((actor or {}).get("name") or "")
    ors: List[Dict[str, Any]] = []
    if uid:
        ors.append({"created_by": uid})
        ors.append({"sales_id": uid})
    if uname:
        ors.append({"sales_name": uname})
    if not ors:
        # Tidak ada jejak identitas sama sekali → jangan buka semuanya diam-diam.
        return {"id": "__tanpa_pemilik__"}
    return {"$or": ors}


def merge(query: Dict[str, Any], clause: Dict[str, Any]) -> Dict[str, Any]:
    """Gabungkan `clause` ke `query` lewat `$and` (aman terhadap `$or` yang sudah ada)."""
    out = dict(query or {})
    if not clause:
        return out
    existing = out.pop("$and", None)
    ands: List[Dict[str, Any]] = list(existing or [])
    ands.append(clause)
    out["$and"] = ands
    return out


def apply_scope(query: Dict[str, Any], actor: Optional[Dict[str, Any]],
                mine: Optional[bool] = None) -> Dict[str, Any]:
    """Terapkan aturan kepemilikan pada query daftar pesanan.

    * peran `sales` → SELALU dibatasi (nilai `mine` diabaikan; ini pagar, bukan tampilan)
    * peran lain    → dibatasi hanya bila `mine=True` diminta layar
    """
    if is_owner_locked(actor) or mine is True:
        return merge(query, owner_clause(actor))
    return dict(query or {})


def owns(order: Dict[str, Any], actor: Optional[Dict[str, Any]]) -> bool:
    """Benar bila `order` memang milik aktor (dibaca dari tiga jejak yang sama)."""
    o = order or {}
    uid = str((actor or {}).get("id") or "")
    uname = str((actor or {}).get("name") or "")
    return bool(
        (uid and (str(o.get("created_by") or "") == uid or str(o.get("sales_id") or "") == uid))
        or (uname and str(o.get("sales_name") or "") == uname)
    )


def assert_may_open(order: Dict[str, Any], actor: Optional[Dict[str, Any]]) -> None:
    """Pagar IDOR untuk detail satu pesanan.

    Tanpa ini pembatasan daftar hanyalah kosmetik: nomor pesanan mudah diterka
    (`SO-0009`) dan `GET /api/sales-orders/{id}` akan tetap membuka isi pesanan rekan
    beserta harga negosiasinya.
    """
    if not is_owner_locked(actor) or owns(order, actor):
        return
    from fastapi import HTTPException
    raise HTTPException(
        status_code=403,
        detail=(f"Pesanan {order.get('number') or ''} bukan pesanan Anda. "
                "Peran sales hanya membuka pesanan miliknya sendiri — minta Admin "
                "Sales bila Anda perlu menindaknya.").strip())
