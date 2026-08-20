"""DEMO SEED — rantai retur FASE E-9 (jual → beli internal antar-PT → retur berantai).

MENGAPA ADA BERKAS INI
----------------------
POC `backend/test_core_rantai_retur_poc.py` menjalankan rantai penuh lalu **menghapus
seluruh jejaknya** (POC tidak boleh meninggalkan residu). Akibatnya layar-layar FASE E-9
— **Jejak Retur**, "diambil dari PT lain lewat KANDA/IC-000xx" di layar pesanan, janji
antar-PT di Papan Pending SO — tampil KOSONG di data demo, jadi pemilik tidak bisa
melihat fiturnya dan agen uji tidak punya apa pun untuk dibuka.

Skrip ini menjalankan rantai yang SAMA lewat HTTP nyata (bukan menyuntik dokumen
mentah, supaya semua invarian & jurnal tetap sah) dan **membiarkan hasilnya** sebagai
data demo. Langkah rantainya sengaja dipanggil dari modul POC itu sendiri supaya
hanya ada SATU definisi alurnya — kalau alur berubah, demo ikut berubah.

Sifat: **idempotent**. Kalau rantai demo sudah ada, skrip berhenti tanpa membuat apa pun.

    cd /app && python seed_e9_chain_demo.py           # buat bila belum ada
    cd /app && python seed_e9_chain_demo.py --force   # buat lagi (hapus yang lama dulu)
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"

DEMO_PROD = "prod_e9_demo_rantai"
DEMO_MARK = "DEMOE9"
DEMO_NAME = "Kain Demo Rantai Retur (E-9)"


def _load_poc():
    """Muat modul POC E-9 sebagai pustaka alur (satu sumber kebenaran rantai)."""
    spec = importlib.util.spec_from_file_location(
        "e9_poc", ROOT / "backend" / "test_core_rantai_retur_poc.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Rantai demo memakai produk & penanda SENDIRI supaya tidak pernah bertabrakan
    # dengan produk POC (yang selalu dihapus di akhir setiap jalan-ulang POC).
    mod.PROD = DEMO_PROD
    mod.MARK = DEMO_MARK
    mod.PROD_NAME = DEMO_NAME
    return mod


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="hapus rantai demo lama lalu buat ulang")
    args = ap.parse_args()

    poc = _load_poc()
    from motor.motor_asyncio import AsyncIOMotorClient  # noqa: PLC0415
    db = AsyncIOMotorClient(poc.MONGO_URL)[poc.DB_NAME]

    print(f"{B}DEMO SEED — rantai retur FASE E-9{X}")
    existing = await db.sales_returns.count_documents({"notes": {"$regex": DEMO_MARK}})
    if existing and not args.force:
        pret = await db.purchase_returns.find_one({"notes": {"$regex": DEMO_MARK}},
                                                  {"_id": 0, "number": 1})
        print(f"{G}  Rantai demo sudah ada (retur pelanggan: {existing}"
              + (f" · retur beli {pret.get('number')}" if pret else "") + f"). Tidak ada yang dibuat.{X}")
        return 0
    if args.force:
        removed = await poc.wipe(db)
        print(f"{Y}  --force: rantai demo lama dihapus {removed}{X}")

    await poc.make_product(db)
    await db.products.update_one({"id": DEMO_PROD}, {"$set": {
        "sku": "E9-DEMO-01",
        "notes": f"{DEMO_MARK} data demo rantai retur antar-PT"}})

    adm_all = poc.sess(entity="all")
    adm_a = poc.sess(entity=poc.ENT_A)
    adm_b = poc.sess(entity=poc.ENT_B)
    mgr_a = poc.sess("manager@kainnusantara.id", entity=poc.ENT_A)
    sales_a = poc.sess("sales@kainnusantara.id", entity=poc.ENT_A)
    wh_user = poc.sess("warehouse@kainnusantara.id", entity=poc.ENT_A)
    try:
        if not poc.resolve_demo_data(adm_a, adm_b):
            return 1
        for step in (lambda: poc.step1_supplier_receipt(adm_b, adm_b),
                     lambda: poc.step2_customer_order(adm_a),
                     lambda: poc.step3_internal_purchase(adm_all, adm_a, adm_b),
                     lambda: poc.step4_customer_return(adm_a, mgr_a),
                     lambda: poc.step5_interco_return(adm_a, mgr_a, adm_all, adm_b),
                     lambda: poc.step6_supplier_return(adm_b)):
            if step() is False:
                print(f"{R}  GAGAL di tengah rantai — periksa keluaran di atas.{X}")
                return 1
        poc.step7_chain(adm_all, sales_a, wh_user)
    finally:
        for s in (adm_all, adm_a, adm_b, mgr_a, sales_a, wh_user):
            s.close()

    if poc.FAIL:
        print(f"{R}  Rantai demo terbentuk tetapi {len(poc.FAIL)} pemeriksaan MERAH:{X}")
        for f in poc.FAIL:
            print(f"    · {f}")
        return 1
    st = poc.ST
    print(f"{G}  Rantai demo siap dilihat di layar:{X}")
    print(f"    · Pesanan pelanggan      : {st['so']['number']} (dipenuhi dari PT lain)")
    print(f"    · Pembelian internal     : {st['ict']['seller']['number']} ↔ "
          f"{st['ict']['buyer']['number']}")
    print(f"    · Retur pelanggan        : {st['sret']['number']}")
    print(f"    · Retur antar-PT         : {st['icr']['number']}")
    print(f"    · Retur ke supplier      : {st['pret']['number']}")
    print("    · Buka salah satu dokumen retur → panel “Jejak Retur”.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
