#!/usr/bin/env python3
"""POC FASE E-8 GELOMBANG 1 — **DUA PERAN BARU** (`sales_admin` · `finance`).

Satu berkas, tanpa residu (semua percobaan tulis memakai id yang TIDAK ADA sehingga
berhenti di pagar izin / 404 — tak ada dokumen yang lahir), lewat endpoint produksi.

APA YANG DIBUKTIKAN
===================
E8.1  **Registry peran = SATU sumber kebenaran.** 6 peran, peringkat, beranda, dan
      label manusia harus IDENTIK di `backend/role_registry.py`,
      `frontend/src/config/roles.js`, dan `frontend/src/config/navMeta.js`.
      Kalau ketiganya bercabang, peran baru akan mendarat di layar kosong atau
      tombolnya mati tanpa alasan — kelas cacat yang paling mahal untuk wewenang.
E8.2  **Pemisahan tugas (SD2).** Sales kehilangan uang masuk (kwitansi AR), faktur
      pajak keluaran, keputusan selisih bayar, pegging, dan "tandai diterima".
      Tetap boleh MELIHAT (dia yang ditanya pelanggan), tidak lagi menerbitkan.
E8.6  **`mark-delivered`** boleh gudang MAUPUN Admin Sales, DICABUT dari sales.
E8.10b#1 **Admin Sales berbasis PENUGASAN**: bisa diberi beberapa badan usaha lewat
      `users.allowed_entity_ids` tanpa menjadi peran lintas-PT — termasuk **mode
      gabungan "Semua Entitas" yang benar-benar menggabungkan** (cacat nyata yang
      ditemukan sesi 2026-08-14: dulu hanya badan usaha aktif yang tampil, 1 pesanan
      Kanda hilang tanpa pesan, dan pagar tulis mode gabungan tidak menyala).
E8.10b#2 **Finance** yang mencatat uang masuk & menerbitkan faktur pajak — bukan
      Admin Sales, bukan sales. Finance TIDAK bisa membuat/mengonfirmasi pesanan.
E8.1b **Peringkat**: `sales_admin`/`finance` (2) TIDAK memenuhi tuntutan `manager` (3).

BUKTI-MERAH: setiap pagar diuji dari DUA sisi — peran yang HARUS ditolak (403) dan
peran yang HARUS lolos (bukan 403; 404/400/409 = izin lolos, dokumen tak ada).
Ditambah 2 sabotase in-process (peringkat & parser id menu) yang WAJIB mengubah hasil.

Jalankan: `python backend/test_core_e8_roles_poc.py`  (butuh backend hidup + seed)
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

BE_DIR = Path(__file__).resolve().parent          # /app/backend
ROOT = BE_DIR.parent                              # /app
sys.path.insert(0, str(BE_DIR))

# `MONGO_URL`/`DB_NAME` dipakai blok bersih-bersih (INV-GATE-01). POC bisa dijalankan
# dari mana saja, jadi env dibaca langsung dari `backend/.env`.
try:                                              # pragma: no cover
    from dotenv import load_dotenv
    load_dotenv(BE_DIR / ".env")
except Exception:                                 # noqa: BLE001
    pass

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
PWD = "demo12345"
ENT_A, ENT_B = "ent_ksc", "ent_kanda"
FAKE = "id_tidak_ada_poc_e8"

GREEN, RED, YEL, CYAN, RST = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m"
RESULTS = []
TOKENS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    tag = f"{GREEN}PASS{RST}" if ok else f"{RED}FAIL{RST}"
    print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(ok)


def client(email, entity=ENT_A):
    cl = httpx.Client(base_url=BASE, timeout=90.0)
    r = cl.post("/api/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    body = r.json()
    cl.headers.update({"Authorization": f"Bearer {body['token']}", "X-Entity-Id": entity})
    cl.login_body = body            # type: ignore[attr-defined]
    TOKENS.append(body["token"])
    return cl


async def _audit_ids():
    """Kumpulan id `audit_logs` saat ini.

    Sengaja MEMBUAT KONEKSI SENDIRI (bukan `from db import db`): klien motor global
    terikat pada event loop pertama, sedangkan POC ini memanggil `asyncio.run` dua
    kali (sebelum & sesudah). Memakai klien global membuat panggilan kedua mati
    dengan "Event loop is closed" tepat di blok bersih-bersih.
    """
    from motor.motor_asyncio import AsyncIOMotorClient
    cl = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = cl[os.environ["DB_NAME"]]
        return {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    finally:
        cl.close()


async def _cleanup(before_ids):
    """INV-GATE-01 — POC tidak boleh meninggalkan residu.

    POC ini sengaja tidak membuat dokumen bisnis (semua percobaan tulis memakai id
    yang tidak ada), tetapi **login tetap menulis** baris `sessions` + jejak audit
    `login`. Tanpa blok ini gate anti-residu memerah (+4 `audit_logs` per putaran)
    dan data demo perlahan menggelembung setiap kali gate dijalankan.
    """
    from motor.motor_asyncio import AsyncIOMotorClient
    cl = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = cl[os.environ["DB_NAME"]]
        await db.sessions.delete_many({"token": {"$in": TOKENS}})
        now_ids = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
        baru = now_ids - before_ids
        if baru:
            await db.audit_logs.delete_many({"id": {"$in": list(baru)}})
        sisa = await db.audit_logs.count_documents({"id": {"$in": list(baru)}})
        return len(baru), sisa
    finally:
        cl.close()


def rows(x):
    return x.get("items") if isinstance(x, dict) else x


def ent_count(cl, path, entity_header):
    """Hitung sebaran entity_id sebuah daftar pada satu konteks entitas."""
    r = cl.get(path, headers={"X-Entity-Id": entity_header})
    if r.status_code != 200:
        return {"__http__": r.status_code}
    out = {}
    for row in rows(r.json()) or []:
        out[row.get("entity_id")] = out.get(row.get("entity_id"), 0) + 1
    return out


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # type: ignore[union-attr]
    return mod


# ═══════════════════════════════════════════════════════════════════════════
# BAGIAN A — REGISTRY PERAN: satu kebenaran di tiga berkas (statik, tanpa HTTP)
# ═══════════════════════════════════════════════════════════════════════════
def a_registry_parity():
    print(f"\n{YEL}A · E8.1 — registry peran: server ↔ layar tidak boleh bercabang{RST}")
    import role_registry as rr

    # A1 — self-test registry (peringkat, lintas-entitas, bukti-merah internal)
    p = subprocess.run([sys.executable, "-m", "role_registry", "--self-test"],
                       cwd=str(BE_DIR), capture_output=True, text=True)
    check("self-test role_registry HIJAU", p.returncode == 0,
          (p.stdout.strip().splitlines() or ["-"])[-1].strip())

    check("6 peran terdaftar (admin·manager·sales_admin·finance·sales·warehouse)",
          set(rr.ROLES) == {"admin", "manager", "sales_admin", "finance", "sales", "warehouse"},
          " · ".join(rr.role_ids()))

    # A2 — cermin sisi layar: frontend/src/config/roles.js
    # CATATAN: hanya blok `ROLE_REGISTRY` yang dibaca. `ROLE_NAV` di berkas yang sama
    # memakai kunci peran yang SAMA pada indentasi yang sama, jadi menyapu seluruh
    # berkas membuat entri registry tertimpa entri overlay menu (label kosong).
    js_full = (ROOT / "frontend/src/config/roles.js").read_text()
    reg = re.search(r"ROLE_REGISTRY\s*=\s*\{(.*?)\n\};", js_full, re.S)
    js = reg.group(1) if reg else ""
    fe = {}
    for m in re.finditer(r"^  (\w+):\s*\{(.*?)^  \},", js, re.S | re.M):
        rid, body = m.group(1), m.group(2)
        if rid in ("sales_admin", "finance", "admin", "manager", "sales", "warehouse"):
            lab = re.search(r'label:\s*"([^"]+)"', body)
            rank = re.search(r"rank:\s*(\d+)", body)
            cross = re.search(r"crossEntity:\s*(true|false)", body)
            order = re.search(r"order:\s*(\d+)", body)
            fe[rid] = {"label": lab.group(1) if lab else "",
                       "rank": int(rank.group(1)) if rank else -1,
                       "cross": (cross.group(1) == "true") if cross else None,
                       "order": int(order.group(1)) if order else -1}
    check("layar mengenal 6 peran yang sama", set(fe) == set(rr.ROLES), " · ".join(sorted(fe)))
    beda = [rid for rid in rr.ROLES
            if fe.get(rid, {}).get("label") != rr.ROLES[rid]["label"]
            or fe.get(rid, {}).get("rank") != rr.ROLES[rid]["rank"]
            or fe.get(rid, {}).get("cross") != rr.ROLES[rid]["cross_entity"]
            or fe.get(rid, {}).get("order") != rr.ROLES[rid]["order"]]
    check("label · peringkat · lintas-entitas · urutan IDENTIK server↔layar",
          not beda, "bercabang: " + ", ".join(beda) if beda else "6/6 sama")

    # A3 — beranda peran: navMeta.ROLE_HOME_REGISTRY == role_registry.home_of
    nav = (ROOT / "frontend/src/config/navMeta.js").read_text()
    blok = re.search(r"ROLE_HOME_REGISTRY\s*=\s*\{(.*?)\n\};", nav, re.S)
    homes = dict(re.findall(r'(\w+):\s*\{\s*view:\s*"([^"]+)"', blok.group(1) if blok else ""))
    salah = [rid for rid in rr.ROLES if homes.get(rid) != rr.ROLES[rid]["home_view"]]
    check("beranda tiap peran sama di server & layar (tak ada yang mendarat di layar kosong)",
          not salah, "beda: " + ", ".join(salah) if salah else
          " · ".join(f"{r}→{homes.get(r)}" for r in ("sales_admin", "finance")))

    # A4 — gate navigasi: beranda peran baru WAJIB ter-reach dari menu
    g = subprocess.run([sys.executable, "scripts/check_nav_map.py"],
                       cwd=str(ROOT), capture_output=True, text=True)
    check("gate check_nav_map PASS (beranda `finance` & `sales_admin` ter-reach)",
          g.returncode == 0, "exit 0" if g.returncode == 0 else g.stdout[-160:])

    # A5 — BUKTI-MERAH parser id menu: id sesudah baris komentar TIDAK boleh tertelan.
    # Ini cacat nyata di gate sendiri: `split(",")` menelan id yang berada tepat
    # setelah `// …` (komentar penjelas di `roles.js` bahkan memuat koma), sehingga
    # gate melapor "landing finance tidak ter-reach" padahal menunya ada.
    nm = load_module(ROOT / "scripts/check_nav_map.py", "poc_check_nav_map")
    contoh = '\n"customers-crm",\n// Keuangan: uang masuk, piutang, denda, kas\n"keuangan", "finance-tower",\n'
    parsed = nm._id_set(contoh)
    check("BUKTI-MERAH parser: id sesudah komentar (& komentar berkoma) tetap terbaca",
          parsed == {"customers-crm", "keuangan", "finance-tower"}, str(sorted(parsed)))

    # A6 — BUKTI-MERAH peringkat: menaikkan Admin Sales ke peringkat manajer HARUS
    # mengubah keputusan persetujuan (kalau tidak, hirarki itu hiasan).
    simpan = rr.ROLE_RANK["sales_admin"]
    rr.ROLE_RANK["sales_admin"] = rr.ROLE_RANK["manager"]
    naik = rr.role_satisfies("sales_admin", "manager")
    rr.ROLE_RANK["sales_admin"] = simpan
    check("BUKTI-MERAH peringkat: Admin Sales bukan penyetuju nilai (dan pagar ini nyata)",
          naik and not rr.role_satisfies("sales_admin", "manager"))


# ═══════════════════════════════════════════════════════════════════════════
# BAGIAN B — IDENTITAS & DAFTAR PERAN LEWAT API
# ═══════════════════════════════════════════════════════════════════════════
def b_identity(adm, sa, fin):
    print(f"\n{YEL}B · E8.1 — identitas & daftar peran dari server{RST}")
    import role_registry as rr

    r = adm.get("/api/roles")
    daftar = {x["id"]: x for x in (r.json().get("roles") or [])} if r.status_code == 200 else {}
    check("GET /api/roles mengirim 6 peran + penjelasannya", len(daftar) == 6,
          f"HTTP {r.status_code} · {' · '.join(sorted(daftar))}")
    check("peran baru ditandai `new_in: E-8` (formulir akun bisa memberi lencana “baru”)",
          daftar.get("sales_admin", {}).get("new_in") == "E-8"
          and daftar.get("finance", {}).get("new_in") == "E-8")
    check("peringkat yang dikirim server = registry",
          all(daftar.get(rid, {}).get("rank") == rr.ROLES[rid]["rank"] for rid in rr.ROLES))

    sab, fb = sa.login_body, fin.login_body
    check("Admin Sales masuk & dilabeli MANUSIA (bukan id teknis `sales_admin`)",
          sab["user"]["role"] == "sales_admin" and sab["user"]["role_label"] == "Admin Sales",
          sab["user"]["role_label"])
    check("Finance masuk & dilabeli “Finance”",
          fb["user"]["role"] == "finance" and fb["user"]["role_label"] == "Finance",
          fb["user"]["role_label"])
    check("login mengirim IZIN EFEKTIF milik pengguna (layar tak perlu menebak dari peran)",
          isinstance(sab.get("permissions"), dict) and bool(sab["permissions"].get("order")),
          f"order={sab['permissions'].get('order')}")

    sac, fc = sab["entity_context"], fb["entity_context"]
    check("E8.10b#1 Admin Sales ditugaskan 2 badan usaha & boleh berpindah",
          sorted(sac["allowed_entity_ids"]) == sorted([ENT_A, ENT_B])
          and sac["can_switch_entity"] is True, str(sac["allowed_entity_ids"]))
    check("Finance terkunci 1 badan usaha (kas & pajak selalu milik satu badan usaha)",
          fc["allowed_entity_ids"] == [ENT_A] and fc["can_switch_entity"] is False,
          str(fc["allowed_entity_ids"]))
    check("peran baru BUKAN peran lintas-entitas (tak ikut oversight grup)",
          rr.CROSS_ENTITY_ROLES == {"admin", "manager"}, str(sorted(rr.CROSS_ENTITY_ROLES)))


# ═══════════════════════════════════════════════════════════════════════════
# BAGIAN C — E8.2: SALES KEHILANGAN UANG & PAJAK (US14)
# ═══════════════════════════════════════════════════════════════════════════
def c_sales_separation(sales):
    print(f"\n{YEL}C · E8.2 — sales tak lagi menyentuh uang masuk, pajak & pegging{RST}")
    r = sales.post(f"/api/sales-orders/{FAKE}/tax-invoice", json={})
    check("sales TERBITKAN Faktur Pajak → 403", r.status_code == 403, f"HTTP {r.status_code}")
    r = sales.post("/api/ar-receipts", json={"customer_id": FAKE, "amount": 1})
    check("sales CATAT uang masuk (kwitansi AR) → 403", r.status_code == 403, f"HTTP {r.status_code}")
    r = sales.post(f"/api/payment-variances/receipt/{FAKE}/decide",
                   json={"kind": "outstanding", "reason_code": "poc"})
    check("sales PUTUSKAN selisih bayar → 403", r.status_code == 403, f"HTTP {r.status_code}")
    r = sales.post(f"/api/inventory/rolls/{FAKE}/earmark",
                   json={"ref_type": "customer", "ref_id": FAKE})
    check("sales PEGGING roll (kunci stok atas namanya) → 403", r.status_code == 403,
          f"HTTP {r.status_code}")
    r = sales.post(f"/api/sales-orders/{FAKE}/mark-delivered")
    check("E8.6 sales TANDAI DITERIMA sendiri → 403", r.status_code == 403, f"HTTP {r.status_code}")
    r = sales.post(f"/api/sales-orders/{FAKE}/confirm")
    check("sales KONFIRMASI pesanan → 403 (sebab lahirnya peran Admin Sales)",
          r.status_code == 403, f"HTTP {r.status_code}")

    # Sisi kontrol: yang MASIH boleh — melihat. Sales-lah yang ditanya pelanggan
    # “faktur saya sudah keluar belum?”, jadi mencabut sampai buta itu salah.
    check("sales tetap MELIHAT faktur pajak", sales.get("/api/tax-invoices").status_code == 200)
    check("sales tetap MELIHAT kwitansi AR", sales.get("/api/ar-receipts").status_code == 200)
    perms = sales.login_body["permissions"]
    check("izin efektif sales: tax_invoice hanya `view`", perms.get("tax_invoice") == ["view"],
          str(perms.get("tax_invoice")))
    check("izin efektif sales: ar_receipt hanya `view`", perms.get("ar_receipt") == ["view"],
          str(perms.get("ar_receipt")))
    check("izin efektif sales: TANPA `order.deliver` & TANPA `inventory.pegging`",
          "deliver" not in (perms.get("order") or [])
          and "pegging" not in (perms.get("inventory") or []),
          f"order={perms.get('order')} inventory={perms.get('inventory')}")
    check("sales tetap boleh MEMBUAT pesanan (pekerjaan intinya utuh)",
          "create" in (perms.get("order") or []))
    check("E7d/E8.8 sales tetap boleh MENGAJUKAN permintaan internal ke PT lain",
          "create" in (perms.get("internal_request") or []),
          str(perms.get("internal_request")))


# ═══════════════════════════════════════════════════════════════════════════
# BAGIAN D — ADMIN SALES: pemilik alur pesanan, TANPA uang & pajak
# ═══════════════════════════════════════════════════════════════════════════
def d_sales_admin(sa):
    print(f"\n{YEL}D · E8.1b/E8.10b — Admin Sales: alur pesanan penuh, uang & pajak TIDAK{RST}")
    r = sa.post(f"/api/sales-orders/{FAKE}/confirm")
    check("Admin Sales KONFIRMASI pesanan → izin lolos (404, pesanan tak ada)",
          r.status_code == 404, f"HTTP {r.status_code}")
    r = sa.post(f"/api/sales-orders/{FAKE}/mark-delivered")
    check("E8.6 Admin Sales TANDAI DITERIMA → izin lolos (404)", r.status_code == 404,
          f"HTTP {r.status_code}")
    r = sa.post(f"/api/inventory/rolls/{FAKE}/earmark",
                json={"ref_type": "customer", "ref_id": FAKE})
    check("Admin Sales PEGGING roll → izin lolos (404)", r.status_code == 404,
          f"HTTP {r.status_code}")
    r = sa.post("/api/purchase-requisitions", json={"items": [], "notes": "poc"})
    check("Admin Sales REORDER ke supplier (buat PR) → izin lolos (400 item kosong)",
          r.status_code == 400, f"HTTP {r.status_code}")
    r = sa.post("/api/interco/transactions", json={"buyer_entity_id": ENT_A,
                                                   "seller_entity_id": ENT_B, "items": []})
    check("E8.10b#4 Admin Sales AMBIL DARI PT LAIN → izin lolos (bukan 403)",
          r.status_code != 403, f"HTTP {r.status_code}")

    # Yang HARUS tertutup — uang, pajak, dan keputusan manajerial.
    r = sa.post(f"/api/sales-orders/{FAKE}/tax-invoice", json={})
    check("Admin Sales TERBITKAN Faktur Pajak → 403 (itu wilayah Finance)",
          r.status_code == 403, f"HTTP {r.status_code}")
    r = sa.post("/api/ar-receipts", json={"customer_id": FAKE, "amount": 1})
    check("Admin Sales CATAT uang masuk → 403", r.status_code == 403, f"HTTP {r.status_code}")
    r = sa.post(f"/api/payment-variances/receipt/{FAKE}/decide",
                json={"kind": "outstanding", "reason_code": "poc"})
    check("Admin Sales PUTUSKAN selisih bayar → 403", r.status_code == 403, f"HTTP {r.status_code}")
    r = sa.post("/api/interco/settlements", json={"payer_entity_id": ENT_A,
                                                  "payee_entity_id": ENT_B, "transactions": []})
    check("Admin Sales LUNASI saldo antar-PT (settlement) → 403 (tetap manajer)",
          r.status_code == 403, f"HTTP {r.status_code}")
    r = sa.post(f"/api/price-approvals/{FAKE}/approve", json={"decision_notes": "poc"})
    check("E8.1b Admin Sales SETUJUI harga khusus → 403 (peringkat 2 < manajer 3)",
          r.status_code == 403, f"HTTP {r.status_code}")
    r = sa.post(f"/api/sales-orders/{FAKE}/approve")
    check("Admin Sales SETUJUI nilai pesanan → 403 (verifikasi ≠ persetujuan)",
          r.status_code == 403, f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════
# BAGIAN E — FINANCE: uang masuk & pajak keluaran, TANPA meja pesanan
# ═══════════════════════════════════════════════════════════════════════════
def e_finance(fin):
    print(f"\n{YEL}E · E8.10b#2 — Finance: uang masuk & pajak keluaran{RST}")
    r = fin.post("/api/ar-receipts", json={"customer_id": FAKE, "amount": 1})
    check("Finance CATAT uang masuk → izin lolos (404, pelanggan tak ada)",
          r.status_code == 404, f"HTTP {r.status_code}")
    r = fin.post(f"/api/sales-orders/{FAKE}/tax-invoice", json={})
    check("Finance TERBITKAN Faktur Pajak → izin lolos (404)", r.status_code == 404,
          f"HTTP {r.status_code}")
    r = fin.post(f"/api/payment-variances/receipt/{FAKE}/decide",
                 json={"kind": "outstanding", "reason_code": "poc"})
    check("Finance PUTUSKAN selisih bayar → izin lolos (kwitansi tak ada)",
          r.status_code in (400, 404), f"HTTP {r.status_code}")
    r = fin.patch(f"/api/tax-invoices/{FAKE}/nsfp", json={"nsfp": "0000000000000000"})
    check("Finance ISI NSFP resmi → izin lolos (404)", r.status_code == 404, f"HTTP {r.status_code}")
    check("Finance melihat kas", fin.get("/api/cash-transactions").status_code == 200)
    check("Finance melihat piutang (AR aging)", fin.get("/api/ar-aging").status_code in (200, 404))

    # Yang HARUS tertutup — meja pesanan bukan wilayahnya.
    r = fin.post(f"/api/sales-orders/{FAKE}/confirm")
    check("Finance KONFIRMASI pesanan → 403", r.status_code == 403, f"HTTP {r.status_code}")
    r = fin.post("/api/customers", json={"name": "POC", "pic_name": "x", "phone": "08",
                                         "email": "a@b.c", "city": "Bandung", "address": "jl"})
    check("Finance BUAT pelanggan → 403 (hanya melihat)", r.status_code == 403,
          f"HTTP {r.status_code}")
    perms = fin.login_body["permissions"]
    check("izin efektif Finance: pesanan hanya `view`+`print`",
          sorted(perms.get("order") or []) == ["print", "view"], str(perms.get("order")))
    check("izin efektif Finance: TANPA sisi hutang (vendor_bill/contra_bon/landed_cost)",
          not any(perms.get(m) for m in ("vendor_bill", "contra_bon", "landed_cost")))
    check("izin efektif Finance: batal faktur pajak TETAP manajer",
          "cancel" not in (perms.get("tax_invoice") or []), str(perms.get("tax_invoice")))


# ═══════════════════════════════════════════════════════════════════════════
# BAGIAN F — PENUGASAN BADAN USAHA & MODE GABUNGAN (cacat nyata 2026-08-14)
# ═══════════════════════════════════════════════════════════════════════════
def f_entity_assignment(sa, fin, sales):
    print(f"\n{YEL}F · E8.10b#1 — penugasan badan usaha & mode gabungan yang benar{RST}")
    check("Admin Sales boleh bekerja di badan usaha penugasan KEDUA (Kanda)",
          sa.get("/api/sales-orders", headers={"X-Entity-Id": ENT_B}).status_code == 200)
    r = sa.get("/api/sales-orders", headers={"X-Entity-Id": "ent_tidak_ditugaskan"})
    check("Admin Sales menyebut badan usaha yang BUKAN penugasannya → 403 (bukan jatuh diam-diam)",
          r.status_code == 403, f"HTTP {r.status_code}")

    sebar = ent_count(sa, "/api/sales-orders", "all")
    check("CACAT DITUTUP: mode “Semua Entitas” Admin Sales menggabungkan KEDUA penugasan",
          set(sebar) >= {ENT_A, ENT_B}, str(sebar))
    r = sa.post("/api/customers", headers={"X-Entity-Id": "all"},
                json={"name": "POC gabungan", "pic_name": "x", "phone": "08",
                      "email": "a@b.c", "city": "Bandung", "address": "jl"})
    check("mode gabungan Admin Sales = HANYA LIHAT (tulis ditolak 409 + kalimat menuntun)",
          r.status_code == 409 and "Semua Entitas" in str(r.json().get("detail", "")),
          f"HTTP {r.status_code}")

    sebar_f = ent_count(fin, "/api/ar-receipts", "all")
    check("ISOLASI TETAP: Finance (1 penugasan) di mode gabungan hanya melihat badan usahanya",
          set(sebar_f) <= {ENT_A}, str(sebar_f))
    sebar_s = ent_count(sales, "/api/sales-orders", "all")
    check("ISOLASI TETAP: sales (1 penugasan) tidak kebocoran PT lain di mode gabungan",
          set(sebar_s) <= {ENT_A}, str(sebar_s))
    r = fin.get("/api/sales-orders", headers={"X-Entity-Id": ENT_B})
    check("Finance menyebut badan usaha lain → 403", r.status_code == 403, f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════
# BAGIAN G — VALIDASI PERAN SAAT MEMBUAT/MENGUBAH AKUN
# ═══════════════════════════════════════════════════════════════════════════
def g_role_validation(adm):
    print(f"\n{YEL}G · E8.1 — peran bukan teks bebas lagi{RST}")
    u = [x for x in (rows(adm.get("/api/users").json()) or [])
         if x.get("role") == "warehouse"]
    target = u[0]["id"] if u else FAKE
    r = adm.patch(f"/api/users/{target}", json={"data": {"role": "sales-admin"}})
    detail = str(r.json().get("detail", "")) if r.status_code != 200 else ""
    check("salah ketik peran (`sales-admin`) DITOLAK 400", r.status_code == 400,
          f"HTTP {r.status_code}")
    check("pesan penolakan MENYEBUT pilihan yang sah (bukan “400 Bad Request” telanjang)",
          "sales_admin" in detail and "finance" in detail, detail[:110])
    r2 = adm.patch(f"/api/users/{target}", json={"data": {"role": "Finance"}})
    check("huruf besar/kecil tidak ditebak-tebak (`Finance` ditolak)", r2.status_code == 400,
          f"HTTP {r2.status_code}")
    after = adm.get(f"/api/users/{target}").json() if target != FAKE else {}
    check("akun TIDAK berubah setelah percobaan gagal (nol residu)",
          not after or after.get("role") == "warehouse", after.get("role", "-"))


# ═══════════════════════════════════════════════════════════════════════════
def main():
    print(f"{CYAN}{'=' * 78}\n  POC FASE E-8 GELOMBANG 1 — DUA PERAN BARU (sales_admin · finance)"
          f"\n  {BASE}\n{'=' * 78}{RST}")
    import asyncio
    audit_before = asyncio.run(_audit_ids())
    try:
        adm = client("admin@kainnusantara.id")
        sales = client("sales@kainnusantara.id")
        sa = client("salesadmin@kainnusantara.id")
        fin = client("finance@kainnusantara.id")
    except Exception as exc:  # noqa: BLE001
        print(f"{RED}Tidak bisa login: {exc}{RST}")
        return 1

    try:
        a_registry_parity()
        b_identity(adm, sa, fin)
        c_sales_separation(sales)
        d_sales_admin(sa)
        e_finance(fin)
        f_entity_assignment(sa, fin, sales)
        g_role_validation(adm)
    finally:
        print(f"\n{YEL}── CLEANUP (INV-GATE-01: nol residu){RST}")
        dihapus, sisa = asyncio.run(_cleanup(audit_before))
        check("CLEANUP: nol residu sessions & audit_logs (POC tak membuat dokumen bisnis)",
              sisa == 0, f"dihapus={dihapus} sisa={sisa}")

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
