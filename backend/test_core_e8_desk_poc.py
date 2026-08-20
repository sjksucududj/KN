#!/usr/bin/env python3
"""POC FASE E-8 GELOMBANG 2 & 3 — **MEJA KERJA · VERIFIKASI · KEPUTUSAN PEMENUHAN**.

Satu berkas, idempotent, **self-cleanup** (INV-GATE-01), lewat endpoint produksi.

APA YANG DIBUKTIKAN (nomor = user story di `plan.md` §4)
=======================================================
US11 **Kepemilikan data sales.** Sales lapangan hanya melihat pesanan MILIKNYA — di
     daftar, di ANGKA RINGKASAN, dan di detail. Bukti-merah: membuka pesanan rekan
     lewat id langsung harus 403, bukan 200 (pembatasan daftar tanpa pagar detail
     hanyalah kosmetik karena nomor pesanan mudah diterka).
US12 **Perjalanan pesanan.** Satu endpoint read-only menjawab "pesanan saya di mana?"
     dengan 9 tahapan + sumber pemenuhan — TANPA membuka layar gudang (`/api/wms/tasks`
     tetap 403 untuk sales).
US15 **Meja Admin Sales** = 8 antrean dengan jumlah, nilai, dan umur tertua. Faktur
     pajak & pencatatan uang masuk TIDAK boleh ada di meja ini (itu Finance).
US16 **Tiga pilihan pemenuhan** beserta KELAYAKANNYA masing-masing, lalu keputusan
     "Ambil dari PT lain" dijalankan ujung-ke-ujung: lahir permintaan internal →
     transaksi antar-PT KEMBAR → **jejak dua arah ke pesanannya** (E8.12).
US17 **Verifikasi administratif** dipisah dari persetujuan manajer. Bukti-merah:
     pesanan yang alamatnya bolong DITOLAK dengan daftar yang bisa ditindak.
     Sakelar `sales_admin.require_verification_before_confirm` benar-benar menahan
     Konfirmasi — dan bawaannya MATI (instalasi lama tidak berubah perilaku).
US18 Antrean **retur** ada di meja Admin Sales (diajukan sales, diproses Admin Sales).
US20 **Meja Finance** = 5 antrean uang masuk & pajak keluaran; Finance TIDAK bisa
     membuat/mengonfirmasi pesanan; sales & Admin Sales TIDAK bisa membuka meja ini.
US22 **Tanpa persetujuan manajer** — Admin Sales melepas transaksi antar-PT sendiri;
     bila pemilik menurunkan ambang rupiah di Pusat Pengaturan, transaksi di atas
     ambang otomatis tertahan **tanpa perubahan kode**.
E8.3 Layar mati sales ditutup: `/api/hr/visits/mine` (kunjungan sendiri) 200.
E8.5 `/api/sales-users` ikut badan usaha (dropdown tidak lagi menawarkan sales PT lain).

Jalankan: `python backend/test_core_e8_desk_poc.py`   (butuh backend hidup + seed)
"""
import copy
import os
import sys
from pathlib import Path

import httpx

BE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BE_DIR))
try:                                              # pragma: no cover
    from dotenv import load_dotenv
    load_dotenv(BE_DIR / ".env")
except Exception:                                 # noqa: BLE001
    pass

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
PWD = "demo12345"
ENT_A, ENT_B = "ent_ksc", "ent_kanda"
CFG_VERIFY = "sales_admin.require_verification_before_confirm"
CFG_THRESHOLD = "antar_entitas.approval_threshold_rupiah"

GREEN, RED, YEL, CYAN, RST = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m"
RESULTS = []
TOKENS = []

#: Koleksi yang dibersihkan berbasis "id baru sejak POC mulai".
NEW_DOC_COLLECTIONS = ("interco_transactions", "internal_requests", "journal_entries",
                       "intercompany_eliminations", "notifications", "audit_logs",
                       "purchase_requisitions", "config_values")
#: Koleksi yang dipulihkan UTUH dari cuplikan (karena POC mengubah dokumen yang sudah ada).
SNAPSHOT_COLLECTIONS = ("interco_accounts", "number_sequences", "system_settings")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    tag = f"{GREEN}PASS{RST}" if ok else f"{RED}FAIL{RST}"
    print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(ok)


def client(email, entity=ENT_A):
    cl = httpx.Client(base_url=BASE, timeout=120.0)
    r = cl.post("/api/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    body = r.json()
    cl.headers.update({"Authorization": f"Bearer {body['token']}", "X-Entity-Id": entity})
    cl.me = body.get("user") or {}                # type: ignore[attr-defined]
    TOKENS.append(body["token"])
    return cl


def ent(cl, entity):
    cl.headers["X-Entity-Id"] = entity
    return cl


# ═══════════════════════════════════════════════════════════════════════════
# CUPLIKAN & BERSIH-BERSIH (koneksi sendiri: klien motor global terikat 1 event loop)
# ═══════════════════════════════════════════════════════════════════════════
def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])


async def snapshot():
    """Cuplikan keadaan awal.

    WAJIB dipanggil **SEBELUM login pertama**. Setiap `POST /auth/login` menulis
    satu baris `audit_logs`; kalau cuplikan diambil sesudah login, baris-baris itu
    ikut terhitung sebagai "data lama" sehingga tidak pernah dihapus dan tertinggal
    sebagai residu. Cacat itu nyata: begitu POC ini didaftarkan sebagai pagar,
    gate `INV-GATE-01` langsung memerah `audit_logs: 93 -> 98 (+5)` = tepat jumlah
    login POC ini (admin · sales · sales2 · admin sales · finance).
    """
    cl = _mongo()
    try:
        db = cl[os.environ["DB_NAME"]]
        snap = {"ids": {}, "docs": {}, "orders": {}, "counts": {}}
        for coll in NEW_DOC_COLLECTIONS:
            snap["ids"][coll] = {d["id"] async for d in db[coll].find({}, {"_id": 0, "id": 1})
                                 if d.get("id")}
            # Jumlah MENTAH juga dicatat: dokumen tanpa field `id` tak terlihat oleh
            # perbandingan himpunan, tetapi gate `INV-GATE-01` menghitungnya.
            snap["counts"][coll] = await db[coll].count_documents({})
        for coll in SNAPSHOT_COLLECTIONS:
            snap["docs"][coll] = [copy.deepcopy(d)
                                  async for d in db[coll].find({}, {"_id": 0})]
        return snap
    finally:
        cl.close()


async def capture_orders(snap, order_ids):
    """Simpan bentuk asli pesanan yang akan disentuh POC (butuh sesi, jadi setelah login)."""
    cl = _mongo()
    try:
        db = cl[os.environ["DB_NAME"]]
        for oid in order_ids:
            doc = await db.sales_orders.find_one({"id": oid}, {"_id": 0})
            if doc:
                snap["orders"][oid] = copy.deepcopy(doc)
        return snap
    finally:
        cl.close()


async def cleanup(snap):
    """Pulihkan keadaan awal. Dilaporkan sebagai temuan, bukan disembunyikan."""
    cl = _mongo()
    laporan = {}
    try:
        db = cl[os.environ["DB_NAME"]]
        for coll in NEW_DOC_COLLECTIONS:
            now = {d["id"] async for d in db[coll].find({}, {"_id": 0, "id": 1})
                   if d.get("id")}
            baru = list(now - snap["ids"][coll])
            if baru:
                await db[coll].delete_many({"id": {"$in": baru}})
            laporan[coll] = len(baru)
        for coll in SNAPSHOT_COLLECTIONS:
            await db[coll].delete_many({})
            if snap["docs"][coll]:
                await db[coll].insert_many([copy.deepcopy(d) for d in snap["docs"][coll]])
        for oid, doc in snap["orders"].items():
            await db.sales_orders.replace_one({"id": oid}, copy.deepcopy(doc))
        await db.sessions.delete_many({"token": {"$in": TOKENS}})
        # Sisa: id baru yang masih tertinggal + selisih JUMLAH MENTAH per koleksi
        # (dua-duanya, karena dokumen tanpa field `id` hanya terlihat oleh jumlah).
        sisa = 0
        for coll in NEW_DOC_COLLECTIONS:
            now = {d["id"] async for d in db[coll].find({}, {"_id": 0, "id": 1})
                   if d.get("id")}
            sisa += len(now - snap["ids"][coll])
            selisih = await db[coll].count_documents({}) - snap["counts"][coll]
            if selisih > 0:
                sisa += selisih
                laporan[f"{coll}:SISA_JUMLAH"] = selisih
        return laporan, sisa
    finally:
        cl.close()


# ═══════════════════════════════════════════════════════════════════════════
def cfg_set(adm, key, value, scope="global", entity_id=""):
    """Ubah setting lewat Pusat Pengaturan (jalur produksi, bukan tulis langsung ke DB)."""
    return adm.put("/api/config/values", json={"items": [{
        "key": key, "value": value, "scope_type": scope, "scope_id": entity_id or "",
        "reason": "POC E-8 gelombang 2"}]})


def find_order(cl, number):
    for o in cl.get("/api/sales-orders").json():
        if o.get("number") == number:
            return o
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# A · US11 — kepemilikan data sales
# ═══════════════════════════════════════════════════════════════════════════
def a_ownership(s1, s2, sa):
    print(f"\n{YEL}A · US11 — sales hanya melihat pesanan MILIKNYA{RST}")
    l1 = s1.get("/api/sales-orders").json()
    l2 = s2.get("/api/sales-orders").json()
    la = sa.get("/api/sales-orders").json()
    n1, n2, na = len(l1), len(l2), len(la)
    check("Admin Sales melihat SELURUH pesanan badan usahanya", na >= 8, f"{na} pesanan")
    check("dua sales TIDAK melihat jumlah yang sama (dulu keduanya melihat 8 milik Ayu)",
          n1 != na or n2 != na, f"ayu={n1} bima={n2} adminsales={na}")
    check("setiap sales punya pesanan sendiri (daftar tidak kosong)", n1 > 0 and n2 > 0,
          f"ayu={n1} bima={n2}")
    check("jumlah keduanya = jumlah Admin Sales (tidak ada pesanan hilang)",
          n1 + n2 == na, f"{n1}+{n2} vs {na}")
    milik1 = {o["number"] for o in l1}
    milik2 = {o["number"] for o in l2}
    check("tidak ada pesanan yang muncul di KEDUA sales", not (milik1 & milik2),
          str(sorted(milik1 & milik2))[:60])

    r1 = s1.get("/api/sales-orders/stats/summary").json()
    r2 = s2.get("/api/sales-orders/stats/summary").json()
    check("US11 — ANGKA RINGKASAN sales cocok dengan isi daftarnya (Ayu)",
          r1.get("total_orders") == n1, f"ringkasan={r1.get('total_orders')} daftar={n1}")
    check("US11 — ANGKA RINGKASAN sales cocok dengan isi daftarnya (Bima)",
          r2.get("total_orders") == n2, f"ringkasan={r2.get('total_orders')} daftar={n2}")

    # ── PINTU BELAKANG YANG DULU TERLEWAT (ditemukan uji LAYAR, sesi 2026-08-15) ──
    # Layar "Pesanan" TIDAK memanggil `GET /sales-orders`. Ia memakai `orders[]` dari
    # `GET /dashboard` — satu panggilan yang menyuplai seluruh aplikasi
    # (`frontend/src/hooks/useAppActions.js`). Dasbor dulu hanya menyaring per BADAN
    # USAHA, jadi `sales@` tetap melihat `SO-0008` milik `sales2@` DI LAYAR (kartu
    # TOTAL 9) padahal `GET /sales-orders` sudah benar mengembalikan 8. Pagar API
    # yang benar tetapi sumber data layar yang bocor = kebocoran nyata bagi pengguna,
    # jadi invarian ini diuji pada SUMBER YANG DIPAKAI LAYAR.
    d1 = s1.get("/api/dashboard").json()
    d2 = s2.get("/api/dashboard").json()
    da = sa.get("/api/dashboard").json()
    dn1 = {o.get("number") for o in (d1.get("orders") or [])}
    dn2 = {o.get("number") for o in (d2.get("orders") or [])}
    dna = {o.get("number") for o in (da.get("orders") or [])}
    check("US11 — dasbor (SUMBER DATA LAYAR PESANAN) ikut aturan kepemilikan (Ayu)",
          bool(dn1) and dn1 <= milik1, f"dasbor={len(dn1)} daftar={len(milik1)} "
          f"asing={sorted(dn1 - milik1)[:3]}")
    check("US11 — dasbor ikut aturan kepemilikan (Bima)",
          bool(dn2) and dn2 <= milik2, f"dasbor={len(dn2)} daftar={len(milik2)} "
          f"asing={sorted(dn2 - milik2)[:3]}")
    check("BUKTI-MERAH: pesanan REKAN tidak pernah ikut ke dasbor sales",
          not (dn1 & milik2) and not (dn2 & milik1),
          str(sorted((dn1 & milik2) | (dn2 & milik1)))[:60])
    check("Admin Sales tetap melihat pesanan SELURUH sales di dasbornya (tak ikut terkunci)",
          milik1 <= dna and milik2 <= dna, f"adminsales={len(dna)} ayu={len(milik1)} "
          f"bima={len(milik2)}")
    check("US11 — kartu 'Pesanan Aktif' di dasbor tak pernah melebihi daftarnya",
          int((d1.get("metrics") or {}).get("active_orders") or 0) <= len(dn1),
          f"aktif={(d1.get('metrics') or {}).get('active_orders')} daftar={len(dn1)}")

    punya_bima = l2[0]["id"] if l2 else ""
    punya_ayu = l1[0]["id"] if l1 else ""
    rr = s2.get(f"/api/sales-orders/{punya_ayu}")
    check("BUKTI-MERAH: sales membuka pesanan REKAN lewat id → 403",
          rr.status_code == 403, f"HTTP {rr.status_code}")
    check("pesan penolakan menyebut sebabnya (bukan 403 telanjang)",
          "bukan pesanan Anda" in str(rr.json().get("detail", "")),
          str(rr.json().get("detail", ""))[:70])
    check("sales tetap bisa membuka pesanan SENDIRI",
          s2.get(f"/api/sales-orders/{punya_bima}").status_code == 200)
    check("Admin Sales bisa membuka pesanan sales mana pun (dia pemilik alurnya)",
          sa.get(f"/api/sales-orders/{punya_ayu}").status_code == 200)

    rp = s2.patch(f"/api/sales-orders/{punya_ayu}", json={"data": {"notes": "coba"}})
    check("BUKTI-MERAH: sales MENYUNTING pesanan rekan → 403", rp.status_code == 403,
          f"HTTP {rp.status_code}")

    # Laporan adalah pintu belakang yang paling mudah terlupakan. Invarian yang benar
    # BUKAN "tidak ada pelanggan yang sama" (dua sales memang boleh melayani pelanggan
    # yang sama), melainkan: setiap pelanggan di laporan HARUS berasal dari pesanan
    # milik sales itu sendiri, dan nilainya tidak boleh melebihi nilai pesanannya.
    tc1 = s1.get("/api/reports/top-customers").json()
    tc2 = s2.get("/api/reports/top-customers").json()
    milik = {"ayu": {o["customer_id"] for o in l1}, "bima": {o["customer_id"] for o in l2}}
    bocor1 = [c["customer_name"] for c in tc1 if c["customer_id"] not in milik["ayu"]]
    bocor2 = [c["customer_name"] for c in tc2 if c["customer_id"] not in milik["bima"]]
    check("US11 — laporan pelanggan teratas hanya dari pesanan SENDIRI (Ayu)",
          not bocor1, str(bocor1)[:70])
    check("US11 — laporan pelanggan teratas hanya dari pesanan SENDIRI (Bima)",
          not bocor2, str(bocor2)[:70])
    tca = {c["customer_id"]: c["order_count"] for c in
           sa.get("/api/reports/top-customers").json()}
    lebih = [c["customer_name"] for c in tc2
             if c["order_count"] > tca.get(c["customer_id"], 0)]
    check("US11 — angka laporan sales tidak pernah melebihi angka Admin Sales",
          not lebih, str(lebih)[:70])
    mine = sa.get("/api/sales-orders", params={"mine": "true"}).json()
    check("peran non-sales boleh MEMINTA saringan 'punya saya' (mine=true)",
          isinstance(mine, list) and len(mine) <= na, f"{len(mine)} dari {na}")
    return punya_ayu


# ═══════════════════════════════════════════════════════════════════════════
# B · US12 — perjalanan pesanan
# ═══════════════════════════════════════════════════════════════════════════
def b_journey(s1, order_id):
    print(f"\n{YEL}B · US12 — perjalanan pesanan untuk sales (read-only){RST}")
    r = s1.get(f"/api/sales-orders/{order_id}/journey")
    check("endpoint perjalanan pesanan tersedia untuk sales", r.status_code == 200,
          f"HTTP {r.status_code}")
    if r.status_code != 200:
        return
    j = r.json()
    kunci = [s["key"] for s in j["steps"]]
    harus = ["dipesan", "diverifikasi", "disetujui", "dikonfirmasi", "disiapkan",
             "dikirim", "diterima", "ditagih", "dibayar"]
    check("9 tahapan dalam bahasa pelanggan, berurutan", kunci == harus, str(kunci))
    check("setiap tahap membawa keterangan yang bisa dibacakan ke pelanggan",
          all(("detail" in s and "label" in s) for s in j["steps"]))
    check("ada tahap yang SUDAH & ada yang BELUM (bukan semua hijau)",
          0 < j["progress"]["done"] < j["progress"]["total"], str(j["progress"]))
    check("menyebut tahap yang sedang berjalan", bool(j.get("current_label")),
          j.get("current_label", ""))
    check("membawa ringkasan uang (tagihan & sisa)",
          "grand_total" in j and "outstanding" in j,
          f"total={j.get('grand_total')} sisa={j.get('outstanding')}")
    check("membawa blok sumber pemenuhan (US12: 'diambil dari PT lain / lewat PO')",
          "fulfillment" in j and "shortages" in j["fulfillment"])
    check("membawa progres gudang TANPA memberi akses layar gudang",
          isinstance(j.get("warehouse_tasks"), list))
    check("BUKTI-MERAH: layar gudang tetap tertutup untuk sales (`/api/wms/tasks` 403)",
          s1.get("/api/wms/tasks").status_code == 403,
          f"HTTP {s1.get('/api/wms/tasks').status_code}")


# ═══════════════════════════════════════════════════════════════════════════
# C · US15/US18 — Meja Admin Sales
# ═══════════════════════════════════════════════════════════════════════════
def c_sales_admin_desk(sa, fin, s1):
    print(f"\n{YEL}C · US15/US18 — Meja Admin Sales berbasis antrean{RST}")
    r = sa.get("/api/sales-admin/desk")
    check("Meja Admin Sales terbuka untuk peran sales_admin", r.status_code == 200,
          f"HTTP {r.status_code}")
    if r.status_code != 200:
        return {}
    d = r.json()
    ids = [q["id"] for q in d["queues"]]
    harus = ["perlu_verifikasi", "siap_dikonfirmasi", "menunggu_manajer",
             "siap_cetak_dokumen", "perlu_dipenuhi", "jatuh_tempo", "retur",
             "permintaan_internal"]
    check("8 antrean sesuai keputusan pemilik", ids == harus, str(ids))
    check("US15 — setiap antrean membawa JUMLAH, NILAI, dan UMUR TERTUA",
          all({"count", "total_value", "oldest_age_days"} <= set(q) for q in d["queues"]))
    check("setiap antrean punya SATU tindakan jelas per baris",
          all(q["action_label"] for q in d["queues"]),
          str([q["id"] for q in d["queues"] if not q["action_label"]]))
    kurang = next(q for q in d["queues"] if q["id"] == "perlu_dipenuhi")
    check("antrean 'perlu dipenuhi' menandai satuannya BUKAN rupiah "
          "(200 yard bukan Rp 200)", kurang.get("value_kind") == "qty",
          str(kurang.get("value_kind")))
    check("US18 — antrean retur ada di meja Admin Sales",
          any(q["id"] == "retur" for q in d["queues"]))
    check("US15 — faktur pajak & uang masuk TIDAK di meja ini (itu Finance)",
          not any(k in ids for k in ("siap_faktur_pajak", "uang_masuk"))
          and len(d.get("not_my_desk") or []) >= 3, str(d.get("not_my_desk"))[:90])
    check("BUKTI-MERAH: Finance TIDAK bisa membuka Meja Admin Sales",
          fin.get("/api/sales-admin/desk").status_code == 403)
    check("BUKTI-MERAH: sales lapangan TIDAK bisa membuka Meja Admin Sales",
          s1.get("/api/sales-admin/desk").status_code == 403)
    baris = [row for q in d["queues"] for row in q["rows"]]
    check("setiap baris membawa konteks pelanggan + umur (isyarat SLA)",
          all(("title" in b and "age_days" in b) for b in baris), f"{len(baris)} baris")
    return d


# ═══════════════════════════════════════════════════════════════════════════
# D · US20 — Meja Finance
# ═══════════════════════════════════════════════════════════════════════════
def d_finance_desk(fin, sa, s1):
    print(f"\n{YEL}D · US20 — Meja Finance (uang masuk & pajak keluaran){RST}")
    r = fin.get("/api/finance/desk")
    check("Meja Finance terbuka untuk peran finance", r.status_code == 200,
          f"HTTP {r.status_code}")
    if r.status_code != 200:
        return
    d = r.json()
    ids = [q["id"] for q in d["queues"]]
    harus = ["siap_faktur_pajak", "uang_masuk", "selisih_bayar", "denda_draft",
             "jatuh_tempo"]
    check("5 antrean sesuai keputusan pemilik", ids == harus, str(ids))
    check("semua antrean bertanda milik Finance",
          all(q["owner"] == "finance" for q in d["queues"]))
    check("US20 — meja ini menyebut yang BUKAN wewenangnya (buat/konfirmasi pesanan)",
          any("pesanan" in s.lower() for s in (d.get("not_my_desk") or [])),
          str(d.get("not_my_desk"))[:90])
    check("BUKTI-MERAH: sales TIDAK bisa membuka Meja Finance "
          "(izin `ar_receipt.view` saja tidak cukup)",
          s1.get("/api/finance/desk").status_code == 403,
          f"HTTP {s1.get('/api/finance/desk').status_code}")
    check("BUKTI-MERAH: Admin Sales TIDAK bisa membuka Meja Finance",
          sa.get("/api/finance/desk").status_code == 403)
    o = fin.get("/api/sales-orders").json()
    check("Finance boleh MELIHAT pesanan (dia menagihnya)", isinstance(o, list) and o)
    oid = o[0]["id"] if o else "x"
    check("BUKTI-MERAH: Finance TIDAK bisa mengonfirmasi pesanan",
          fin.post(f"/api/sales-orders/{oid}/confirm").status_code == 403)
    check("BUKTI-MERAH: Finance TIDAK bisa memverifikasi pesanan",
          fin.post(f"/api/sales-orders/{oid}/verify", json={"note": ""}).status_code == 403)


# ═══════════════════════════════════════════════════════════════════════════
# E · US17 — verifikasi administratif ≠ persetujuan manajer
# ═══════════════════════════════════════════════════════════════════════════
def e_verify(sa, adm, s1):
    print(f"\n{YEL}E · US17 — verifikasi administratif (E8.13){RST}")
    desk = sa.get("/api/sales-admin/desk").json()
    antrean = next(q for q in desk["queues"] if q["id"] == "perlu_verifikasi")
    check("ada pesanan di antrean 'perlu diverifikasi'", antrean["count"] > 0,
          f"{antrean['count']} pesanan")
    if not antrean["count"]:
        return
    target = antrean["rows"][0]["ref_id"]
    nomor = antrean["rows"][0]["number"]

    pv = sa.get(f"/api/sales-orders/{target}/verification")
    check("pratinjau daftar periksa tersedia sebelum menekan Verifikasi",
          pv.status_code == 200, f"HTTP {pv.status_code}")
    pre = pv.json()
    wajib = {"alamat", "syarat_bayar", "isi_pesanan", "pajak", "npwp", "kredit"}
    check("daftar periksa mencakup alamat · syarat bayar · isi · pajak · NPWP · kredit",
          {c["id"] for c in pre["checks"]} == wajib,
          str({c["id"] for c in pre["checks"]}))
    check("setiap baris memakai bahasa yang bisa ditindak (bukan nama kolom)",
          all(" " in c["label"] and c.get("hint") for c in pre["checks"]))
    check("kredit ditandai TIDAK menghalangi (itu keputusan manajer)",
          not next(c for c in pre["checks"] if c["id"] == "kredit")["blocking"])
    check("BUKTI-MERAH: sales lapangan tidak punya wewenang verifikasi",
          s1.post(f"/api/sales-orders/{target}/verify",
                  json={"note": ""}).status_code == 403)

    # BUKTI-MERAH: alamat dilubangi → verifikasi WAJIB ditolak dengan daftar.
    asli = sa.get(f"/api/sales-orders/{target}").json().get("shipping_address") or {}
    adm.patch(f"/api/sales-orders/{target}",
              json={"data": {"notes": "poc-e8"}})       # pemanasan: pastikan patch hidup
    import asyncio as _a
    _a.run(_poke_address(target, {}))
    bad = sa.post(f"/api/sales-orders/{target}/verify", json={"note": "poc"})
    det = bad.json().get("detail", {})
    check("BUKTI-MERAH: pesanan tanpa alamat/penerima DITOLAK verifikasi (409)",
          bad.status_code == 409, f"HTTP {bad.status_code}")
    check("penolakan menyebut APA yang harus dilengkapi (bukan 'gagal' telanjang)",
          isinstance(det, dict) and det.get("checks")
          and "Alamat" in str(det.get("message", "")), str(det)[:90])
    _a.run(_poke_address(target, asli))

    ok = sa.post(f"/api/sales-orders/{target}/verify", json={"note": "POC E-8"})
    check(f"verifikasi {nomor} BERHASIL setelah lengkap", ok.status_code == 200,
          f"HTTP {ok.status_code}")
    if ok.status_code == 200:
        rec = ok.json()["verification"]
        check("verifikasi mencatat SIAPA & KAPAN (jejak, bukan cap stempel)",
              rec.get("by") and rec.get("at") and rec.get("by_role") == "sales_admin",
              f"{rec.get('by')} · {rec.get('by_role')}")
        check("hasil pemeriksaan ikut tersimpan di dokumen pesanan",
              len(rec.get("checks") or []) == 6, str(len(rec.get("checks") or [])))
    after = sa.get("/api/sales-admin/desk").json()
    a2 = next(q for q in after["queues"] if q["id"] == "perlu_verifikasi")
    check("pesanan itu KELUAR dari antrean 'perlu diverifikasi' (antrean bergerak)",
          a2["count"] == antrean["count"] - 1,
          f"{antrean['count']} → {a2['count']}")

    # Sakelar Pusat Pengaturan: bawaan MATI, dan benar-benar menahan bila dinyalakan.
    siap = next((q for q in after["queues"] if q["id"] == "siap_dikonfirmasi"), {"rows": []})
    kandidat = next((r for r in siap["rows"]
                     if "Belum diverifikasi" in (r.get("subtitle") or "")), None)
    check(f"bawaan sakelar `{CFG_VERIFY}` = MATI (perilaku instalasi lama tak berubah)",
          _cfg_value(adm, CFG_VERIFY) in (False, None, "", 0), str(_cfg_value(adm, CFG_VERIFY)))
    if kandidat:
        r_on = cfg_set(adm, CFG_VERIFY, True)
        check("sakelar bisa dinyalakan dari Pusat Pengaturan", r_on.status_code == 200,
              f"HTTP {r_on.status_code}")
        blocked = sa.post(f"/api/sales-orders/{kandidat['ref_id']}/confirm")
        check("saat sakelar HIDUP: konfirmasi pesanan belum terverifikasi DITOLAK 409",
              blocked.status_code == 409, f"HTTP {blocked.status_code}")
        check("penolakannya MENUNTUN ke antrean yang benar",
              "Meja Admin Sales" in str(blocked.json().get("detail", "")),
              str(blocked.json().get("detail", ""))[:80])
        cfg_set(adm, CFG_VERIFY, False)
        check("setelah sakelar dimatikan lagi, konfirmasi tidak lagi tertahan",
              sa.post(f"/api/sales-orders/{kandidat['ref_id']}/confirm").status_code != 409)
    else:
        check("kandidat 'siap dikonfirmasi & belum diverifikasi' tersedia untuk uji sakelar",
              False, "tidak ada kandidat")


async def _poke_address(order_id, value):
    """Ubah `shipping_address` LANGSUNG di basis data.

    Endpoint `PATCH /sales-orders/{id}` sengaja hanya mengizinkan 3 field, jadi
    lubang alamat tidak bisa dibuat lewat API — dan memang tidak boleh bisa.
    Untuk bukti-merah kita butuh keadaan itu, jadi dibuat di lapisan data lalu
    DIPULIHKAN persis seperti semula beberapa baris kemudian.
    """
    cl = _mongo()
    try:
        db = cl[os.environ["DB_NAME"]]
        await db.sales_orders.update_one({"id": order_id},
                                        {"$set": {"shipping_address": value}})
    finally:
        cl.close()


def _cfg_value(adm, key):
    r = adm.get("/api/config/effective", params={"q": key})
    if r.status_code != 200:
        return None
    for row in (r.json().get("items") or []):
        if row.get("key") == key:
            return row.get("value")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# F · US16/US22 — tiga pilihan pemenuhan + ambil dari PT lain ujung-ke-ujung
# ═══════════════════════════════════════════════════════════════════════════
def f_fulfillment(sa, adm, s1):
    print(f"\n{YEL}F · US16/US22 — keputusan pemenuhan (3 jalan){RST}")
    ent(sa, ENT_B)
    kanda = find_order(sa, "KANDA/SO-00001")
    check("pesanan Kanda yang kurang barang tersedia di data demo", bool(kanda),
          kanda.get("number", "-"))
    if not kanda:
        ent(sa, ENT_A)
        return
    oid = kanda["id"]

    opt = sa.get(f"/api/sales-admin/orders/{oid}/fulfillment")
    check("panel pemenuhan terbuka untuk Admin Sales", opt.status_code == 200,
          f"HTTP {opt.status_code}")
    if opt.status_code != 200:
        ent(sa, ENT_A)
        return
    o = opt.json()
    check("US16 — kekurangan pesanan terbaca (bukan 'tidak ada data')",
          len(o["shortages"]) > 0,
          str([(s["product_name"], s["backorder_qty"]) for s in o["shortages"]])[:70])
    check("US16 — TIGA pilihan disajikan sekaligus",
          set(o["options"]) == {"interco", "reorder", "wait"}, str(list(o["options"])))
    check("setiap pilihan membawa KELAYAKAN + alasan bila mati "
          "(tombol mati tanpa alasan = teka-teki)",
          all(("available" in v and "reason" in v) for v in o["options"].values()))
    ic = o["options"]["interco"]
    check("US16 — kandidat badan usaha sumber beserta stok per baris",
          ic["candidates"] and all("lines" in c for c in ic["candidates"]),
          str([(c["entity_name"], c["enough"]) for c in ic["candidates"]]))
    cukup = [c for c in ic["candidates"] if c["enough"]]
    check("ada badan usaha sumber yang stoknya CUKUP (jalur antar-PT bisa dibuktikan)",
          bool(cukup) and ic["available"], str([c["entity_name"] for c in cukup]))
    check("BUKTI-MERAH: sales lapangan TIDAK melihat rincian stok badan usaha lain",
          s1.get(f"/api/sales-admin/orders/{oid}/fulfillment").status_code == 403)
    if not cukup:
        ent(sa, ENT_A)
        return
    sumber = cukup[0]["entity_id"]

    # ── US22: ambang rupiah benar-benar mengunci (config, tanpa deploy) ──
    r_low = cfg_set(adm, CFG_THRESHOLD, 1, "entity", sumber)
    check("ambang rupiah antar-PT bisa diturunkan pemilik di Pusat Pengaturan",
          r_low.status_code == 200, f"HTTP {r_low.status_code}")
    ditahan = sa.post(f"/api/sales-admin/orders/{oid}/fulfillment-decision",
                      json={"mode": "interco", "source_entity_id": sumber,
                            "note": "POC ambang"})
    check("US22 — di ATAS ambang: keputusan Admin Sales TERTAHAN (400/409)",
          ditahan.status_code in (400, 409), f"HTTP {ditahan.status_code}")
    check("penolakan menyebut peran penyetuju yang dibutuhkan",
          "peran" in str(ditahan.json().get("detail", "")).lower(),
          str(ditahan.json().get("detail", ""))[:90])
    cfg_set(adm, CFG_THRESHOLD, 100000000, "entity", sumber)

    # ── US16/US22: keputusan "Ambil dari PT lain" ujung-ke-ujung, tanpa manajer ──
    res = sa.post(f"/api/sales-admin/orders/{oid}/fulfillment-decision",
                  json={"mode": "interco", "source_entity_id": sumber,
                        "note": "POC E-8 ambil dari PT lain"})
    check("US22 — di BAWAH ambang: Admin Sales memutuskan SENDIRI (tanpa manajer)",
          res.status_code == 200,
          f"HTTP {res.status_code} {str(res.json())[:110]}")
    if res.status_code != 200:
        ent(sa, ENT_A)
        return
    body = res.json()
    dec = body["decision"]
    check("keputusan tercatat pada dokumen pesanan (bukan di ingatan orang)",
          dec["mode"] == "interco" and dec["by_role"] == "sales_admin",
          f"{dec['mode']} oleh {dec['by']}")
    check("lahir PERMINTAAN INTERNAL sebagai jejak permintaannya",
          bool((body.get("internal_request") or {}).get("number")),
          str((body.get("internal_request") or {}).get("number")))
    check("lahir TRANSAKSI ANTAR-PT kembar (nomor penjual & pembeli)",
          bool(body["interco"].get("buyer_number"))
          and bool(body["interco"].get("seller_number")),
          f"{body['interco'].get('buyer_number')} ⇄ {body['interco'].get('seller_number')}")
    check("harga transaksinya BUKAN nol (memakai kontrak harga internal)",
          float(body["interco"].get("grand_total") or 0) > 0,
          str(body["interco"].get("grand_total")))
    check("kalimat keputusan bisa dibacakan ke pelanggan",
          "PT lain" in dec["summary"] or "antar-PT" in dec["summary"],
          dec["summary"][:80])

    # E8.12 — jejak DUA ARAH pesanan ⇄ transaksi antar-PT
    refs = sa.get(f"/api/documents/refs/sales_order/{oid}")
    if refs.status_code == 200:
        tujuan = str(refs.json())
        check("E8.12 — pesanan menunjuk transaksi antar-PT (jejak dua arah)",
              "interco_transaction" in tujuan, tujuan[:80])
    else:
        check("E8.12 — endpoint relasi dokumen terjangkau", False,
              f"HTTP {refs.status_code}")
    ict = sa.get(f"/api/documents/refs/interco_transaction/{dec['ref_id']}")
    if ict.status_code == 200:
        check("E8.12 — transaksi antar-PT menunjuk balik ke pesanannya",
              "sales_order" in str(ict.json()), str(ict.json())[:80])

    # US12 — sumber pemenuhan muncul di perjalanan pesanan milik sales.
    # Dibuka oleh CITRA (sales ber-home Kanda): Ayu ditugaskan hanya di KSC, jadi
    # baginya pesanan ini memang HARUS 403 — pagar entitas, bukan pagar pemilik.
    s3 = client("sales3@kainnusantara.id", ENT_B)
    check("BUKTI-MERAH: sales KSC tetap tertutup atas pesanan Kanda (pagar entitas)",
          s1.get(f"/api/sales-orders/{oid}/journey",
                 headers={"X-Entity-Id": ENT_B}).status_code == 403)
    jr = s3.get(f"/api/sales-orders/{oid}/journey")
    if jr.status_code == 200:
        kal = (jr.json().get("fulfillment") or {}).get("sentence", "")
        check("US12 — sales membaca sumber pemenuhannya di perjalanan pesanan",
              bool(kal) and dec["ref_number"] in kal, kal[:90])
    else:
        check("US12 — sales Kanda bisa membuka perjalanan pesanannya", False,
              f"HTTP {jr.status_code}")

    # Jalur yang tidak layak harus MENOLAK dengan alasan, bukan diam-diam sukses.
    ent(sa, ENT_A)
    ksc = find_order(sa, "SO-0009")
    if ksc:
        rr = sa.get(f"/api/sales-admin/orders/{ksc['id']}/fulfillment").json()
        check("US16 — pilihan 'ambil dari PT lain' MATI bila stok grup tak cukup, "
              "dengan alasan tertulis",
              not rr["options"]["interco"]["available"]
              and "cukup" in rr["options"]["interco"]["reason"],
              rr["options"]["interco"]["reason"][:70])
        bad = sa.post(f"/api/sales-admin/orders/{ksc['id']}/fulfillment-decision",
                      json={"mode": "kirim-doa", "source_entity_id": ""})
        check("BUKTI-MERAH: mode pemenuhan asal-asalan ditolak 400",
              bad.status_code == 400, f"HTTP {bad.status_code}")
        tanpa = sa.post(f"/api/sales-admin/orders/{ksc['id']}/fulfillment-decision",
                        json={"mode": "interco", "source_entity_id": ""})
        check("BUKTI-MERAH: 'ambil dari PT lain' tanpa memilih sumber ditolak "
              "dengan kalimat menuntun",
              tanpa.status_code == 400
              and "badan usaha sumber" in str(tanpa.json().get("detail", "")).lower(),
              str(tanpa.json().get("detail", ""))[:80])


# ═══════════════════════════════════════════════════════════════════════════
# G · E8.3/E8.5 — layar mati & dropdown lintas badan usaha
# ═══════════════════════════════════════════════════════════════════════════
def g_dead_screens(s1, sa):
    print(f"\n{YEL}G · E8.3/E8.5 — layar mati sales & dropdown ikut badan usaha{RST}")
    r = s1.get("/api/hr/visits/mine")
    check("E8.3 — sales melihat KUNJUNGANNYA SENDIRI (dulu menu 403)",
          r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        b = r.json()
        check("kunjungan sendiri membawa KPI ringkas (total · selesai · berbuah order)",
              {"total", "done", "with_order"} <= set(b.get("totals") or {}),
              str(b.get("totals")))
        check("hanya kunjungan milik akun yang login (pagar dari sesi, bukan parameter)",
              all(v.get("employee_id") == b["employee"]["id"] for v in b.get("rows") or []))
    check("BUKTI-MERAH: daftar kunjungan SELURUH karyawan tetap tertutup untuk sales",
          s1.get("/api/hr/visits").status_code == 403,
          f"HTTP {s1.get('/api/hr/visits').status_code}")

    a = ent(sa, ENT_A).get("/api/sales-users").json()
    b = ent(sa, ENT_B).get("/api/sales-users").json()
    ent(sa, ENT_A)
    na, nb = {x["name"] for x in a}, {x["name"] for x in b}
    check("E8.5 — dropdown sales BERBEDA per badan usaha", na != nb,
          f"KSC={sorted(na)} Kanda={sorted(nb)}")
    check("E8.5 — tidak ada sales PT lain yang bocor ke dropdown", not (na & nb),
          str(sorted(na & nb)))


# ═══════════════════════════════════════════════════════════════════════════
def main():
    print(f"{CYAN}{'=' * 78}\n  POC FASE E-8 GELOMBANG 2&3 — MEJA KERJA · VERIFIKASI · PEMENUHAN"
          f"\n  {BASE}\n{'=' * 78}{RST}")
    import asyncio
    # INV-GATE-01 — cuplikan diambil SEBELUM login pertama (lihat penjelasan di
    # `snapshot()`): login menulis baris `audit_logs`, dan baris yang lahir sesudah
    # cuplikan-lah yang boleh dihapus saat bersih-bersih.
    snap = asyncio.run(snapshot())
    try:
        try:
            adm = client("admin@kainnusantara.id")
            s1 = client("sales@kainnusantara.id")
            s2 = client("sales2@kainnusantara.id")
            sa = client("salesadmin@kainnusantara.id")
            fin = client("finance@kainnusantara.id")
        except Exception as exc:  # noqa: BLE001
            print(f"{RED}Tidak bisa login: {exc}{RST}")
            return 1

        order_ids = [o["id"] for o in adm.get("/api/sales-orders",
                                              headers={"X-Entity-Id": "all"}).json()]
        asyncio.run(capture_orders(snap, order_ids))

        milik_ayu = a_ownership(s1, s2, sa)
        b_journey(s1, milik_ayu)
        c_sales_admin_desk(sa, fin, s1)
        d_finance_desk(fin, sa, s1)
        e_verify(sa, adm, s1)
        f_fulfillment(sa, adm, s1)
        g_dead_screens(s1, sa)
    finally:
        print(f"\n{YEL}── CLEANUP (INV-GATE-01: nol residu){RST}")
        laporan, sisa = asyncio.run(cleanup(snap))
        check("CLEANUP: seluruh dokumen yang dibuat POC dihapus & dokumen lama dipulihkan",
              sisa == 0,
              " ".join(f"{k}={v}" for k, v in laporan.items() if v) + f" sisa={sisa}")

    ok = sum(1 for _, o, _ in RESULTS if o)
    bad = [n for n, o, _ in RESULTS if not o]
    print(f"\n{CYAN}{'=' * 78}{RST}")
    print(f"  {GREEN if not bad else RED}{ok}/{len(RESULTS)} PASS{RST}")
    if bad:
        print(f"{RED}  GAGAL:{RST}")
        for n in bad:
            print(f"   - {n}")
    print(f"{CYAN}{'=' * 78}{RST}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
