"""FASE E-8 (E8.1) — **REGISTRY PERAN**: satu sumber kebenaran untuk peran & peringkat.

KENAPA BERKAS INI ADA
=====================
Sampai FASE E-7 sistem hanya punya **4 peran** (`admin`/`manager`/`sales`/`warehouse`)
dan peringkatnya ditulis sebagai **angka ajaib yang disalin di dua tempat**
(`services/config_service.role_satisfies` dan `services/so_approvals.ROLE_RANK`),
sementara daftar peran yang boleh lintas badan usaha ditulis di tempat KETIGA
(`services/entity_context_service.CROSS_ENTITY_ROLES`), dan label peran untuk manusia
di tempat KEEMPAT (frontend). Menambah satu peran berarti mengubah empat berkas dan
berharap tidak ada yang terlewat — kelas cacat yang paling mahal untuk urusan wewenang.

Berkas ini menjadi SSOT-nya. Semua tempat lama sekarang **membaca dari sini**.

DUA PERAN BARU (keputusan pemilik 2026-08-10, mengikat)
-------------------------------------------------------
Orang yang mengurus keseluruhan pesanan penjualan dulu harus dijadikan `sales`
(tak bisa Konfirmasi SO) atau `manager` (ikut dapat kuasa tutup buku, payroll,
bayar tagihan supplier, hapus master). Keduanya salah. Maka:

* **`sales_admin` (Admin Sales)** — pemilik alur SO end-to-end: validasi → keputusan
  pemenuhan (stok sendiri · ambil dari PT lain · reorder ke supplier) → konfirmasi →
  dokumen → memproses retur. **TANPA** menyentuh uang masuk & faktur pajak.
* **`finance` (Kasir/Finance)** — sisi UANG MASUK & PAJAK KELUARAN: kwitansi AR,
  faktur pajak keluaran, keputusan selisih bayar, penerbitan denda, kas.

PERINGKAT (`rank`) — dipakai matriks persetujuan
-----------------------------------------------
`sales:1 · warehouse:1 · sales_admin:2 · finance:2 · manager:3 · admin:4`
Arti praktisnya: aturan persetujuan yang menuntut `manager` TIDAK bisa dipenuhi oleh
Admin Sales/Finance (peringkat 2 < 3). Itu memang tujuannya — mereka pelaksana, bukan
penyetuju nilai.

LINTAS BADAN USAHA
------------------
Hanya `admin` & `manager`. **`sales_admin` SENGAJA TIDAK lintas-entitas**
(keputusan pemilik E8.10b#1: Admin Sales berbasis PENUGASAN — boleh dikunci 1 badan
usaha atau diberi beberapa lewat `users.allowed_entity_ids`, mekanisme yang sudah ada
untuk peran non-lintas). `finance` mengikuti pola yang sama karena kas & pajak selalu
milik satu badan usaha (keputusan E7e).
"""
from typing import Any, Dict, List, Optional

# ─── REGISTRY ────────────────────────────────────────────────────────────────
# `home_view`/`home_nav_id` WAJIB sama dengan `frontend/src/config/navMeta.js`
# (ROLE_HOME_REGISTRY). POC E-8 memeriksa kesamaannya supaya tidak diam-diam bercabang.
ROLES: Dict[str, Dict[str, Any]] = {
    "admin": {
        "label": "Admin",
        "long_label": "Admin sistem",
        "rank": 4,
        "cross_entity": True,
        "home_view": "admin-home",
        "home_nav_id": "home",
        "scope_hint": "lintas badan usaha",
        "description": "Kendali penuh sistem, master data, hak akses & audit.",
        "order": 1,
    },
    "manager": {
        "label": "Manajer",
        "long_label": "Manajer",
        "rank": 3,
        "cross_entity": True,
        "home_view": "manager-home",
        "home_nav_id": "home",
        "scope_hint": "lintas badan usaha",
        "description": "Penyetuju nilai/kredit/harga, tutup buku, payroll, pembayaran supplier.",
        "order": 2,
    },
    "sales_admin": {
        "label": "Admin Sales",
        "long_label": "Admin Sales (alur pesanan)",
        "rank": 2,
        "cross_entity": False,
        # GELOMBANG 2: beranda = **Meja Admin Sales** (`sales-admin-desk`). Peran
        # pelaksana yang mendarat di DAFTAR harus menyaring sendiri untuk menemukan
        # apa yang perlu ditindak; meja kerja sudah menyusunnya jadi antrean.
        "home_view": "sales-admin-desk",
        "home_nav_id": "sales-admin-desk",
        "scope_hint": "1 badan usaha (bisa ditugaskan ke beberapa)",
        "description": (
            "Mengelola keseluruhan pesanan: validasi, keputusan pemenuhan "
            "(stok sendiri / ambil dari PT lain / reorder supplier), konfirmasi, "
            "dokumen, dan memproses retur. Tidak menyentuh uang masuk & faktur pajak."
        ),
        "order": 3,
        "new_in": "E-8",
    },
    "finance": {
        "label": "Finance",
        "long_label": "Kasir / Finance (uang masuk & pajak keluaran)",
        "rank": 2,
        "cross_entity": False,
        # GELOMBANG 2: beranda = **Meja Finance** (5 antrean uang masuk & pajak).
        "home_view": "finance-desk",
        "home_nav_id": "finance-desk",
        "scope_hint": "1 badan usaha (bisa ditugaskan ke beberapa)",
        "description": (
            "Mencatat uang masuk (kwitansi AR), menerbitkan faktur pajak keluaran, "
            "memutus selisih bayar, menerbitkan denda, dan mencatat kas."
        ),
        "order": 4,
        "new_in": "E-8",
    },
    "sales": {
        "label": "Sales",
        "long_label": "Sales (lapangan)",
        "rank": 1,
        "cross_entity": False,
        "home_view": "sales-home",
        "home_nav_id": "home",
        "scope_hint": "1 badan usaha",
        "description": (
            "Menjual: basis pelanggan sendiri, membuat pesanan, memantau perjalanan "
            "pesanannya, dan mengajukan retur."
        ),
        "order": 5,
    },
    "warehouse": {
        "label": "Gudang",
        "long_label": "Gudang (WMS)",
        "rank": 1,
        "cross_entity": False,
        "home_view": "operations",
        "home_nav_id": "wms-operations",
        "scope_hint": "1 badan usaha",
        "description": "Penerimaan, penyimpanan, pengambilan, kirim, dan hitung ulang stok.",
        "order": 6,
    },
}

#: Peringkat peran — SATU definisi (dulu disalin di config_service & so_approvals).
ROLE_RANK: Dict[Any, int] = {"": 0, None: 0, **{rid: r["rank"] for rid, r in ROLES.items()}}

#: Peran yang boleh mengoperasikan SEMUA badan usaha (oversight lintas-PT).
CROSS_ENTITY_ROLES = {rid for rid, r in ROLES.items() if r["cross_entity"]}

#: Peringkat yang dipakai bila `required_role` diisi nilai yang tidak dikenal.
#: Sengaja = peringkat manajer (perilaku lama), supaya konfigurasi persetujuan yang
#: sudah tersimpan di basis data tidak mendadak jadi lebih longgar.
_DEFAULT_REQUIRED_RANK = ROLES["manager"]["rank"]


def role_ids() -> List[str]:
    """Semua id peran, urut sesuai wewenang (admin dulu)."""
    return sorted(ROLES, key=lambda r: ROLES[r]["order"])


def is_role(role: str) -> bool:
    return role in ROLES


def role_label(role: str, long: bool = False) -> str:
    """Label untuk MANUSIA. Jangan pernah menampilkan id teknis ke pengguna."""
    entry = ROLES.get(role or "")
    if not entry:
        return role or "—"
    return entry["long_label"] if long else entry["label"]


def rank_of(role: str) -> int:
    return ROLE_RANK.get(role or "", 0)


def required_rank(required_role: Optional[str]) -> int:
    """Peringkat yang dituntut sebuah aturan persetujuan.

    `""`/`None` = tanpa persetujuan (0). Nilai tak dikenal = peringkat manajer.
    """
    if not required_role:
        return 0
    return ROLE_RANK.get(required_role, _DEFAULT_REQUIRED_RANK)


def role_satisfies(actor_role: str, required_role: Optional[str]) -> bool:
    """Apakah peran aktor memenuhi `required_role` dari matriks persetujuan?

    Hirarki: admin(4) > manager(3) > sales_admin/finance(2) > sales/warehouse(1).
    `admin` selalu lolos. Admin Sales & Finance TIDAK memenuhi tuntutan `manager`
    — itu disengaja (mereka pelaksana, bukan penyetuju nilai).
    """
    return rank_of(actor_role) >= required_rank(required_role)


def home_of(role: str) -> Dict[str, str]:
    entry = ROLES.get(role or "") or ROLES["sales"]
    return {"view": entry["home_view"], "nav_id": entry["home_nav_id"]}


def public_list() -> List[Dict[str, Any]]:
    """Bentuk untuk API/FE (dipakai layar “Badan Usaha & Akses” + POC)."""
    return [
        {
            "id": rid,
            "label": ROLES[rid]["label"],
            "long_label": ROLES[rid]["long_label"],
            "rank": ROLES[rid]["rank"],
            "cross_entity": ROLES[rid]["cross_entity"],
            "scope_hint": ROLES[rid]["scope_hint"],
            "description": ROLES[rid]["description"],
            "home_view": ROLES[rid]["home_view"],
            "new_in": ROLES[rid].get("new_in", ""),
        }
        for rid in role_ids()
    ]


def assert_valid_role(role: str) -> str:
    """Validasi peran saat membuat/mengubah akun.

    Dulu `role` adalah teks bebas: salah ketik (`"sales-admin"`, `"Finance"`) membuat
    akun yang **tidak punya izin apa pun** dan pemiliknya bingung kenapa semua layar
    kosong. Sekarang ditolak dengan menyebut pilihan yang sah.
    """
    from fastapi import HTTPException

    clean = (role or "").strip()
    if clean in ROLES:
        return clean
    pilihan = " · ".join(f"{rid} ({ROLES[rid]['label']})" for rid in role_ids())
    raise HTTPException(
        status_code=400,
        detail=f"Peran “{clean or '(kosong)'}” tidak dikenal. Pilihan yang sah: {pilihan}.",
    )


# ─── SELF-TEST (dipakai gate: `python -m role_registry --self-test`) ─────────
def _self_test() -> int:
    fails = 0

    def chk(name: str, cond: bool, note: str = "") -> None:
        nonlocal fails
        mark = "\033[92m[PASS]\033[0m" if cond else "\033[91m[FAIL]\033[0m"
        print(f"  {mark} {name}" + (f"  · {note}" if note else ""))
        if not cond:
            fails += 1

    print("== SELF-TEST role_registry (FASE E-8) ==")
    chk("6 peran terdaftar", len(ROLES) == 6, " · ".join(role_ids()))
    chk("admin peringkat tertinggi", max(r["rank"] for r in ROLES.values()) == ROLES["admin"]["rank"])
    chk("sales_admin & finance di atas sales/gudang",
        rank_of("sales_admin") > rank_of("sales") and rank_of("finance") > rank_of("warehouse"))
    chk("sales_admin & finance DI BAWAH manajer (bukan penyetuju nilai)",
        rank_of("sales_admin") < rank_of("manager") and rank_of("finance") < rank_of("manager"))
    chk("lintas badan usaha HANYA admin & manager",
        CROSS_ENTITY_ROLES == {"admin", "manager"}, str(sorted(CROSS_ENTITY_ROLES)))
    chk("aturan 'manager' tidak bisa dipenuhi Admin Sales",
        not role_satisfies("sales_admin", "manager"))
    chk("aturan 'manager' dipenuhi manajer & admin",
        role_satisfies("manager", "manager") and role_satisfies("admin", "manager"))
    chk("aturan kosong = tanpa persetujuan (siapa pun yang boleh ubah)",
        role_satisfies("sales", "") and role_satisfies("warehouse", None))
    chk("required_role tak dikenal jatuh ke peringkat manajer (tidak jadi longgar)",
        not role_satisfies("sales_admin", "direksi") and role_satisfies("manager", "direksi"))
    chk("setiap peran punya label manusia & beranda",
        all(ROLES[r]["label"] and ROLES[r]["home_view"] for r in ROLES))
    chk("tidak ada label peran yang dobel",
        len({ROLES[r]["label"] for r in ROLES}) == len(ROLES))

    # BUKTI-MERAH: kalau peringkat Admin Sales disamakan dengan manajer, gate HARUS memerah.
    saved = ROLE_RANK["sales_admin"]
    ROLE_RANK["sales_admin"] = ROLE_RANK["manager"]
    broke = role_satisfies("sales_admin", "manager")
    ROLE_RANK["sales_admin"] = saved
    chk("BUKTI-MERAH: menaikkan peringkat Admin Sales memang mengubah keputusan",
        broke and not role_satisfies("sales_admin", "manager"))

    print(f"\n  {'HIJAU' if fails == 0 else 'MERAH'} — {len(ROLES)} peran, {fails} gagal.")
    return fails


if __name__ == "__main__":
    import sys

    sys.exit(1 if _self_test() else 0)
