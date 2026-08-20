"""POC P0-A — Number-series deletion-safe (max-based, RC-5).

Membuktikan: setelah dokumen di-tengah-deret DIHAPUS, generator nomor TIDAK
menghasilkan duplikat (count+1 lama BUG; next_doc_number baru AMAN).

Skenario reproduksi sesuai handoff #041:
  - Ada PO-00001..PO-00012 (12 dok), lalu PO-00010 dihapus → tersisa 11 dok,
    nomor maks = PO-00012.
  - count+1 LAMA → PO-{11+1:05d} = PO-00012  (DUPLIKAT dengan yang sudah ada!)
  - next_doc_number BARU → PO-00013          (AMAN, mengambil max+1)

Pakai koleksi sandbox sementara agar TIDAK menyentuh data produksi.
"""
import asyncio
import sys
sys.path.insert(0, "/app/backend")

from db import db                       # noqa: E402
from core_utils import next_doc_number  # noqa: E402

SANDBOX = "_poc_number_series"
PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} — {detail}")


async def main():
    coll = db[SANDBOX]
    await coll.delete_many({})

    # 1) Deret bersih 1..12
    for i in range(1, 13):
        await coll.insert_one({"id": f"x{i}", "doc_no": f"PO-{i:05d}"})

    # baseline: count+1 (BUG-able) vs next (AMAN) saat belum ada hapus
    cnt = await coll.count_documents({})
    legacy = f"PO-{cnt + 1:05d}"
    nxt = await next_doc_number(SANDBOX, "doc_no", "PO-")
    check("Deret penuh: next_doc_number == PO-00013", nxt == "PO-00013", nxt)
    check("Deret penuh: legacy count+1 juga PO-00013 (belum ada hapus)", legacy == "PO-00013", legacy)

    # 2) HAPUS dokumen di tengah (PO-00010) → reproduksi kondisi handoff
    await coll.delete_one({"doc_no": "PO-00010"})
    cnt2 = await coll.count_documents({})
    legacy2 = f"PO-{cnt2 + 1:05d}"          # = PO-00012 (DUPLIKAT!)
    nxt2 = await next_doc_number(SANDBOX, "doc_no", "PO-")

    check("Setelah hapus: count_documents == 11", cnt2 == 11, cnt2)
    check("BUKTI BUG LAMA: count+1 menghasilkan PO-00012 (duplikat)", legacy2 == "PO-00012", legacy2)
    dup_exists = await coll.find_one({"doc_no": legacy2}) is not None
    check("BUKTI BUG LAMA: PO-00012 SUDAH ADA → count+1 = COLLISION", dup_exists, "tidak ada dup")
    check("FIX: next_doc_number menghasilkan PO-00013 (AMAN, max+1)", nxt2 == "PO-00013", nxt2)
    fix_collision = await coll.find_one({"doc_no": nxt2}) is not None
    check("FIX: PO-00013 belum ada → TIDAK collision", not fix_collision, "ternyata ada")

    # 3) Insert pakai nomor baru, lalu generate lagi → tetap unik & menaik
    await coll.insert_one({"id": "x13", "doc_no": nxt2})
    nxt3 = await next_doc_number(SANDBOX, "doc_no", "PO-")
    check("Berurutan: setelah insert PO-00013, next == PO-00014", nxt3 == "PO-00014", nxt3)

    # 4) Koleksi kosong → mulai dari 1
    await coll.delete_many({})
    nxt4 = await next_doc_number(SANDBOX, "doc_no", "PO-")
    check("Koleksi kosong → PO-00001", nxt4 == "PO-00001", nxt4)

    # 5) Lebar digit tak seragam (data lama) → tetap ambil max numerik
    await coll.insert_one({"id": "y1", "doc_no": "PO-9"})        # 9 (non-padded)
    await coll.insert_one({"id": "y2", "doc_no": "PO-00010"})    # 10 (padded)
    nxt5 = await next_doc_number(SANDBOX, "doc_no", "PO-")
    check("Lebar campur: max(9,10)+1 → PO-00011 (bukan PO-00010)", nxt5 == "PO-00011", nxt5)

    # 6) Prefix berbeda tidak saling mengganggu (TRF vs PO)
    await coll.delete_many({})
    await coll.insert_one({"id": "z1", "doc_no": "TRF-00005"})
    await coll.insert_one({"id": "z2", "doc_no": "PO-00002"})
    nxt_po = await next_doc_number(SANDBOX, "doc_no", "PO-")
    nxt_trf = await next_doc_number(SANDBOX, "doc_no", "TRF-")
    check("Prefix terisolasi: PO- → PO-00003", nxt_po == "PO-00003", nxt_po)
    check("Prefix terisolasi: TRF- → TRF-00006", nxt_trf == "TRF-00006", nxt_trf)

    await coll.drop()
    print(f"\n  RESULT: {PASS} PASS / {FAIL} FAIL")
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
