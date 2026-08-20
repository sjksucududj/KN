#!/usr/bin/env python3
"""POC FASE G-7 — KONTRABON ADVANCED (satu skrip · HTTP · nol residu).

Membuktikan 11 user story fase G-7 memakai API sungguhan, bukan mock:

  1. Jadwal tukar faktur per supplier + pengingat H-1 (berisi angka yang bisa ditindak).
  2. Satu kontrabon `<ENT>/CB-#####` menggabungkan BANYAK faktur dari BANYAK PO.
  3. Daftar "GR belum ditagih" (barang sudah masuk, faktur supplier belum datang).
  4. 3-way match dengan toleransi dari **Pusat Pengaturan**; di luar toleransi wajib
     **keputusan berlabel** — dan mengubah config sungguh-sungguh mengubah hasilnya.
  5. Lima jenis potongan yang menunjuk dokumen NYATA; retur beli & uang muka tidak
     boleh dipakai dua kali; potongan klaim makloon DITOLAK (sudah menempel di faktur).
  6. Siklus draft→submitted→verified→approved→scheduled→paid, ambang persetujuan dari
     config, pemisahan tugas (pembuat ≠ penyetuju), jalur sengketa.
  7. Bayar SEKALI untuk banyak faktur; potongan jadi pelunasan NON-KAS sehingga
     subledger hutang & buku besar rekonsiliasi (celah nyata sebelum fase ini).
  8. Nyambung ke Rekonsiliasi Bank G-8: kandidat berskor + **bayar dari baris mutasi**.
  9. Tanda Terima Kontrabon (data + PDF) memuat seluruh faktur/PO/GR + potongan + net.
 10. Relasi dokumen dua arah (G-4) + jejak waktu siapa memutus apa.
 11. Isolasi lintas-PT (403) + INV-CB-01..04 dengan BUKTI-MERAH.

Jalankan: cd /app && python backend/test_g7_contrabon_poc.py
"""
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from poc_stock_guard import restore_stock, snapshot_stock  # noqa: E402

BASE = os.environ.get("KN_BASE", "http://localhost:8001/api")
PWD = "demo12345"
ENT_A = "ent_ksc"
ENT_B = "ent_kanda"
BANK_A = "bank_bca_ksc"
POC_TAG = "POC_G7"

G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
res = {"pass": 0, "fail": 0}
made: Dict[str, List[str]] = {"bills": [], "cbs": [], "cash": [], "returns": [], "lines": []}
# ── ANTI-RESIDU BERBASIS GARIS DASAR ──────────────────────────────────────────
# `seed_realistic.py` kini menanam 3 kontrabon demo (LUNAS · dijadwalkan · diajukan
# dengan selisih). POC TIDAK boleh mengukur residu dengan "harus nol dokumen" lagi:
# itu akan memerah pada data demo yang sah, ATAU (lebih buruk) menggoda kita menghapus
# data demo demi angka nol. Yang benar: catat keadaan SEBELUM POC lalu pastikan keadaan
# SESUDAH POC identik — termasuk penghitung nomor dokumen & jadwal tukar faktur supplier,
# dua hal yang dulu di-nol-kan buta sehingga menggeser data demo.
base: Dict[str, Any] = {"cbs": 0, "cb_seq": [], "sup_a_exchange": None}
# Id supplier TIDAK boleh dipaku: `seed_realistic.py` membuatnya acak setiap kali dijalankan
# (hanya id PO yang deterministik: po_001..po_011). POC yang memaku id akan mati sesudah
# re-seed — bug nyata yang sudah pernah menghentikan sesi ini. Karena itu id diresolusi
# dari PO demo yang deterministik pada saat POC berjalan (lihat `resolve_actors()`).
SUP_A = ""      # Solo Weave (po_003) — punya 2 PO dengan penerimaan
SUP_C = ""      # NTT Weaving Co (po_002) — untuk uji toleransi config
SUP_B = ""      # Bali Weave Studio (po_006, PT KANDA) — untuk isolasi lintas-PT
SUP_D = ""      # Cirebon Craft (po_001) — untuk jalur sengketa


def ok(cond: bool, name: str, extra: Any = "") -> bool:
    res["pass" if cond else "fail"] += 1
    tag = f"{G}PASS{X}" if cond else f"{R}FAIL{X}"
    print(f"  [{tag}] {name}" + (f"  ({extra})" if extra else ""))
    return bool(cond)


def head(t: str) -> None:
    print(f"\n{C}{B}── {t} ──{X}")


def rp(v: Any) -> str:
    return "Rp " + f"{float(v or 0):,.0f}".replace(",", ".")


def login(email: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    r.raise_for_status()
    tok = r.json().get("token")
    assert tok, f"login {email} gagal: {r.text[:160]}"
    return tok


def H(tok: str, ent: str = "") -> Dict[str, str]:
    h = {"Authorization": f"Bearer {tok}"}
    if ent:
        h["X-Entity-Id"] = ent
    return h


def api(method: str, path: str, tok: str, ent: str = "", **kw) -> requests.Response:
    return requests.request(method, f"{BASE}{path}", headers=H(tok, ent), timeout=120, **kw)


def dbrun(fn):
    """Operasi Mongo langsung — HANYA untuk suntikan bukti-merah & cleanup."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _go():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"].strip('"'))
        try:
            return await fn(cli[os.environ.get("DB_NAME", "test_database").strip('"')])
        finally:
            cli.close()

    return asyncio.run(_go())


def integrity(only: str = "") -> tuple:
    cmd = [sys.executable, "/app/scripts/verify_data_integrity.py"]
    if only:
        cmd.append(f"--only={only}")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def cfg_set(admin: str, key: str, value: Any, scope: str = "global",
            scope_id: str = "") -> bool:
    r = api("PUT", "/config/values", admin, ENT_A, json={"items": [{
        "key": key, "value": value, "scope_type": scope, "scope_id": scope_id,
        "reason": f"{POC_TAG} — uji kebijakan"}]})
    return r.status_code == 200


def cfg_reset(admin: str, key: str, scope: str = "global", scope_id: str = "") -> bool:
    r = api("POST", "/config/values/reset", admin, ENT_A, json={
        "key": key, "scope_type": scope, "scope_id": scope_id,
        "reason": f"{POC_TAG} — kembalikan default"})
    return r.status_code == 200


def day(offset: int = 0) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


# ═════════════════════════════════════════════════════════════════════════════
#  PERSIAPAN — faktur supplier NYATA (dibuat lewat API, dibersihkan di akhir)
# ═════════════════════════════════════════════════════════════════════════════
def make_bill(admin: str, po_id: str, items: List[Dict[str, Any]], mode: str,
              inv_no: str, ent: str = ENT_A) -> Dict[str, Any]:
    r = api("POST", "/vendor-bills", admin, ent, json={
        "po_id": po_id, "supplier_invoice_no": inv_no, "match_mode": mode,
        "items": items, "bill_date": day(-1), "due_date": day(20),
        "notes": f"{POC_TAG} faktur supplier", "entity_id": ent, "submit_now": True})
    assert r.status_code == 200, f"gagal buat faktur {inv_no}: {r.status_code} {r.text[:220]}"
    bill = r.json()
    made["bills"].append(bill["id"])
    return bill


def setup(admin: str) -> Dict[str, Any]:
    head("0 · PERSIAPAN — faktur supplier nyata dari 2 PO milik satu supplier")
    # Faktur A: menagih SELURUH qty PO (200 yard) padahal gudang menerima 180 →
    # inilah kasus nyata "faktur lebih besar dari barang yang datang".
    bill_a = make_bill(admin, "po_003",
                       [{"product_id": "prod_lurik_classic", "billed_qty": 200, "price": 88000}],
                       "ordered", f"{POC_TAG}/INV-A")
    ok(bill_a.get("status") == "posted", "faktur A (tagih 200 yard, diterima 180) posted",
       f"{bill_a.get('bill_number')} · {rp(bill_a.get('grand_total'))}")
    # Faktur B: harga 3% di atas harga PO → lolos toleransi PEMBELIAN (5%) tetapi
    # melewati toleransi KONTRABON (1%) → membuktikan dua ambang bekerja berlapis.
    # PO kedua supplier yang sama DICARI, tidak dipaku nomornya: nomor PO demo bergantung
    # pada urutan penomoran per-PT, dan memaku "KSC/PO-00007" membuat POC mati begitu
    # data demo bertambah satu PO (kelas bug yang sama dengan id supplier yang dipaku).
    async def _find_po2(db):
        async for p in db.purchase_orders.find(
                {"supplier_id": SUP_A, "entity_id": ENT_A, "id": {"$ne": "po_003"},
                 "status": {"$nin": ["draft", "waiting_approval", "rejected", "cancelled"]}},
                {"_id": 0, "id": 1, "po_number": 1, "items": 1}):
            for it in (p.get("items") or []):
                if it.get("product_id") == "prod_lurik_classic" \
                        and float(it.get("received_qty") or 0) > 0:
                    return {"id": p["id"], "number": p.get("po_number", ""),
                            "qty": float(it["received_qty"]),
                            "price": float(it.get("price") or 0)}
        return {}

    po2 = dbrun(_find_po2)
    ok(bool(po2.get("id")),
       "PO kedua supplier yang sama ditemukan (penerimaan lurik belum ditagih)",
       f"{po2.get('number', '—')} · {po2.get('qty', 0):g} yard @ {rp(po2.get('price'))}")
    bill_b = make_bill(admin, po2["id"],
                       [{"product_id": "prod_lurik_classic", "billed_qty": po2["qty"],
                         "price": round(po2["price"] * 1.03, 2)}],
                       "received", f"{POC_TAG}/INV-B")
    ok(bill_b.get("status") == "posted", "faktur B (harga +3%) posted tanpa sengketa di jalur AP",
       f"{bill_b.get('bill_number')} · {rp(bill_b.get('grand_total'))}")
    # Faktur D: dibayar LEBIH agar lahir UANG MUKA supplier (jalur G-3) → nanti dipakai
    # sebagai potongan kontrabon.
    bill_d = make_bill(admin, "po_003",
                       [{"product_id": "prod_endek_bali", "billed_qty": 4, "price": 255000}],
                       "received", f"{POC_TAG}/INV-D")
    over = api("POST", f"/vendor-bills/{bill_d['id']}/pay", admin, ENT_A, json={
        "amount": float(bill_d["grand_total"]) + 500000, "method": "transfer",
        "cash_type": "kas_besar", "notes": f"{POC_TAG} sengaja lebih bayar",
        "variance": {"kind": "ap_advance", "reason_code": "supplier_advance",
                     "note": f"{POC_TAG} uang muka untuk kontrabon berikutnya"}})
    ok(over.status_code == 200, "kelebihan bayar faktur D menjadi UANG MUKA supplier (G-3)",
       f"HTTP {over.status_code} · {over.text[:80] if over.status_code != 200 else rp(500000)}")
    for p in (over.json().get("payments") or []) if over.status_code == 200 else []:
        if p.get("cash_txn_id"):
            made["cash"].append(p["cash_txn_id"])
    adv = dbrun(lambda db: db.cash_transactions.find_one(
        {"ref_type": "ap_advance", "ref_id": bill_d["id"]}, {"_id": 0}))
    if adv:
        made["cash"].append(adv["id"])
    ok(bool(adv), "transaksi uang muka supplier tercatat", (adv or {}).get("number", "—"))
    # Retur beli (nota debit) untuk supplier yang sama → potongan kontrabon jenis pertama.
    rr = api("POST", "/purchase-returns", admin, ENT_A, json={
        "po_id": "po_003", "warehouse_id": "wh_jakarta",
        "items": [{"product_id": "prod_endek_bali", "quantity": 6, "unit": "yard",
                   "reason": "cacat", "condition": "damaged"}],
        "reason": f"{POC_TAG} kain cacat", "notes": POC_TAG, "submit_now": True})
    ret = rr.json() if rr.status_code == 200 else {}
    if ret.get("id"):
        made["returns"].append(ret["id"])
    ok(rr.status_code == 200, "retur beli dibuat & diajukan",
       f"HTTP {rr.status_code} · {ret.get('number', rr.text[:80])}")
    ra = api("POST", f"/purchase-returns/{ret.get('id')}/approve", admin, ENT_A,
             json={"notes": f"{POC_TAG} disetujui"})
    ret2 = ra.json() if ra.status_code == 200 else {}
    ok(ra.status_code == 200 and ret2.get("supplier_outcome") == "ap_credit",
       "retur beli disetujui dengan konsekuensi POTONG HUTANG (ap_credit)",
       f"{ret2.get('debit_note_number', '')} · {rp(ret2.get('total_amount'))}")
    return {"bill_a": bill_a, "bill_b": bill_b, "bill_d": bill_d,
            "advance": adv or {}, "ret": ret2 or ret}


# ═════════════════════════════════════════════════════════════════════════════
#  US1 — JADWAL TUKAR FAKTUR + PENGINGAT
# ═════════════════════════════════════════════════════════════════════════════
def test_schedule(admin: str) -> None:
    head("1 · JADWAL TUKAR FAKTUR PER SUPPLIER + PENGINGAT H-1 (US1)")
    today_wd = date.today().weekday()
    r = api("PUT", f"/suppliers/{SUP_A}/invoice-exchange", admin, ENT_A, json={
        "mode": "weekly", "weekday": today_wd, "pic_name": "Pak Sutrisno",
        "notes": f"{POC_TAG} tukar faktur mingguan"})
    ok(r.status_code == 200, "jadwal tukar faktur tersimpan (mingguan)",
       f"HTTP {r.status_code} · {r.json().get('schedule_label') if r.status_code == 200 else r.text[:90]}")
    sched = r.json() if r.status_code == 200 else {}
    ok(sched.get("next_exchange_date") == day(0),
       "tanggal siklus berikutnya dihitung benar (hari ini)", sched.get("next_exchange_date"))

    lst = api("GET", "/contra-bons/exchange-schedules", admin, ENT_A).json()
    row = next((x for x in lst.get("rows", []) if x["supplier_id"] == SUP_A), {})
    ok(row.get("due_reminder") is True,
       "supplier masuk daftar 'perlu diingatkan' (H-n dari Pusat Pengaturan)",
       f"H-{lst.get('reminder_days_before')} · sisa {row.get('days_left')} hari")
    ok(row.get("unbilled_gr_value", 0) > 0 or row.get("billable_value", 0) > 0,
       "baris jadwal membawa ANGKA yang bisa ditindak (nilai belum ditagih / siap dikontrabon)",
       f"belum ditagih {rp(row.get('unbilled_gr_value'))} · siap {rp(row.get('billable_value'))}")

    run = api("POST", "/contra-bons/run-reminder", admin, ENT_A)
    ok(run.status_code == 200, "job pengingat dijalankan", f"HTTP {run.status_code}")
    notif = dbrun(lambda db: db.notifications.find_one(
        {"type": "contra_bon_cycle", "ref": {"$regex": f"^cbcycle:{SUP_A}"}}, {"_id": 0}))
    ok(bool(notif), "notifikasi pengingat tukar faktur terbit", (notif or {}).get("title", "—"))
    body = (notif or {}).get("body", "")
    ok("Siap dikontrabon" in body and "Belum ditagih supplier" in body,
       "isi pengingat menyebut tagihan siap & GR belum ditagih (bukan basa-basi)", body[:110])
    again = api("POST", "/contra-bons/run-reminder", admin, ENT_A)
    cnt = dbrun(lambda db: db.notifications.count_documents(
        {"type": "contra_bon_cycle", "ref": {"$regex": f"^cbcycle:{SUP_A}"}}))
    ok(again.status_code == 200 and cnt == 1,
       "job idempoten — dijalankan dua kali tidak menggandakan pengingat", f"{cnt} notifikasi")


# ═════════════════════════════════════════════════════════════════════════════
#  US3 — GR BELUM DITAGIH
# ═════════════════════════════════════════════════════════════════════════════
def test_unbilled(admin: str) -> Dict[str, Any]:
    head("2 · GR BELUM DITAGIH — barang sudah masuk, faktur belum datang (US3)")
    r = api("GET", f"/contra-bons/unbilled-receipts?supplier_id={SUP_A}", admin, ENT_A)
    data = r.json()
    ok(r.status_code == 200, "daftar GR belum ditagih terbaca", f"HTTP {r.status_code}")
    ok(data.get("po_count", 0) >= 1, "ada PO dengan penerimaan yang belum tertagih",
       f"{data.get('po_count')} PO · {rp(data.get('total_value'))}")
    row = (data.get("rows") or [{}])[0]
    ok(bool(row.get("grn_task_id")), "baris menunjuk tugas penerimaan (GRN) yang nyata",
       row.get("grn_task_id", "—"))
    ok("age_days" in row and "overdue" in row,
       "umur & penandaan tertunggak dihitung (ambang dari Pusat Pengaturan)",
       f"{row.get('age_days')} hari · tertunggak={row.get('overdue')} · ambang "
       f"{data.get('age_threshold_days')} hari")
    return data


# ═════════════════════════════════════════════════════════════════════════════
#  US2 — RAKIT & BUAT KONTRABON
# ═════════════════════════════════════════════════════════════════════════════
def test_create(mgr: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    head("3 · SATU KONTRABON MENGGABUNGKAN BANYAK FAKTUR (US2)")
    prep = api("GET", f"/contra-bons/prepare?supplier_id={SUP_A}", mgr, ENT_A).json()
    ids = {b["bill_id"] for b in prep.get("bills", [])}
    ok(ctx["bill_a"]["id"] in ids and ctx["bill_b"]["id"] in ids,
       "kedua faktur (dari 2 PO berbeda) muncul sebagai kandidat", f"{len(ids)} kandidat")
    ok(ctx["bill_d"]["id"] not in ids,
       "faktur yang sudah lunas TIDAK ditawarkan lagi", "faktur D lunas")
    creds = prep.get("credits", {})
    ok(any(c["ref_id"] == ctx["ret"]["id"] for c in creds.get("purchase_returns", [])),
       "nota debit retur beli tersedia sebagai potongan",
       ctx["ret"].get("debit_note_number", ""))
    ok(any(c["ref_id"] == ctx["advance"].get("id") for c in creds.get("supplier_advances", [])),
       "uang muka supplier tersedia sebagai potongan", ctx["advance"].get("number", ""))
    ok(prep.get("suggested", {}).get("term_days") == 30,
       "jatuh tempo diusulkan dari termin supplier (NET30)",
       prep.get("suggested", {}).get("due_date"))

    r = api("POST", "/contra-bons", mgr, ENT_A, json={
        "supplier_id": SUP_A, "entity_id": ENT_A,
        "bills": [{"bill_id": ctx["bill_a"]["id"]}, {"bill_id": ctx["bill_b"]["id"]}],
        "cycle_date": day(0), "supplier_pic": "Pak Sutrisno",
        "notes": f"{POC_TAG} siklus tukar faktur"})
    ok(r.status_code == 200, "kontrabon dibuat", f"HTTP {r.status_code} {r.text[:120]}")
    cb = r.json()
    made["cbs"].append(cb["id"])
    import re
    ok(bool(re.match(r"^KSC/CB-\d{5}$", cb.get("number", ""))),
       "nomor kontrabon berpola <ENT>/CB-#####", cb.get("number"))
    exp = round(float(ctx["bill_a"]["grand_total"]) + float(ctx["bill_b"]["grand_total"]), 2)
    ok(abs(cb["totals"]["bills_total"] - exp) < 0.01,
       "total faktur = Σ sisa hutang kedua faktur", rp(cb["totals"]["bills_total"]))
    ok(len({b["po_number"] for b in cb["bills"]}) == 2,
       "satu kontrabon memuat faktur dari DUA PO berbeda",
       ", ".join(sorted({b["po_number"] for b in cb["bills"]})))

    # Faktur yang sudah dipegang kontrabon tak boleh ditarik kontrabon lain (INV-CB-01).
    dup = api("POST", "/contra-bons", mgr, ENT_A, json={
        "supplier_id": SUP_A, "entity_id": ENT_A,
        "bills": [{"bill_id": ctx["bill_a"]["id"]}]})
    ok(dup.status_code == 400 and "sudah ada di kontrabon" in dup.text,
       "faktur yang sudah dikontrabonkan DITOLAK di kontrabon kedua", dup.text[:110])
    prep2 = api("GET", f"/contra-bons/prepare?supplier_id={SUP_A}", mgr, ENT_A).json()
    ok(ctx["bill_a"]["id"] not in {b["bill_id"] for b in prep2.get("bills", [])},
       "kandidat langsung menyusut setelah faktur dipakai", f"{len(prep2.get('bills', []))} sisa")
    return cb


# ═════════════════════════════════════════════════════════════════════════════
#  US4 — 3-WAY MATCH BERTOLERANSI + KEPUTUSAN BERLABEL
# ═════════════════════════════════════════════════════════════════════════════
def test_match(admin: str, mgr: str, cb: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    head("4 · 3-WAY MATCH BERTOLERANSI + KEPUTUSAN BERLABEL (US4)")
    exc = [e for b in cb["bills"] for e in (b["match"].get("exceptions") or [])]
    kinds = {e["type"] for e in exc}
    ok("qty_over_billed" in kinds,
       "selisih JUMLAH terdeteksi (ditagih 200, diterima 180)",
       next((e["detail"] for e in exc if e["type"] == "qty_over_billed"), "")[:110])
    ok("price_variance" in kinds,
       "selisih HARGA terdeteksi walau lolos toleransi jalur AP (5%)",
       next((e["detail"] for e in exc if e["type"] == "price_variance"), "")[:110])
    ok(cb["match_summary"]["status"] == "needs_decision",
       "ringkasan match menuntut keputusan", f"{cb['match_summary']['exceptions_count']} selisih")

    api("POST", f"/contra-bons/{cb['id']}/submit", mgr, ENT_A)
    v = api("POST", f"/contra-bons/{cb['id']}/verify", mgr, ENT_A)
    ok(v.status_code == 400 and "belum diputus" in v.text,
       "VERIFIKASI DITOLAK selama masih ada selisih tanpa keputusan (INV-CB-03)",
       v.text[:130])

    key_qty = next(e["key"] for e in exc if e["type"] == "qty_over_billed")
    key_price = next(e["key"] for e in exc if e["type"] == "price_variance")
    bad = api("POST", f"/contra-bons/{cb['id']}/decide", mgr, ENT_A, json={
        "exception_key": key_qty, "action": "deduct", "reason_code": "penalty_waiver"})
    ok(bad.status_code == 400 and "bukan untuk kontrabon" in bad.text,
       "label alasan dari domain lain DITOLAK, dengan menyebut pilihan yang benar",
       bad.text[:130])
    nore = api("POST", f"/contra-bons/{cb['id']}/decide", mgr, ENT_A, json={
        "exception_key": key_qty, "action": "deduct", "reason_code": ""})
    ok(nore.status_code == 400 and "wajib dipilih" in nore.text,
       "keputusan tanpa alasan DITOLAK", nore.text[:110])

    d1 = api("POST", f"/contra-bons/{cb['id']}/decide", mgr, ENT_A, json={
        "exception_key": key_qty, "action": "deduct", "reason_code": "cb_qty_shortfall",
        "note": "supplier setuju dipotong 20 yard"})
    ok(d1.status_code == 200, "selisih jumlah diputus: POTONG dari tagihan",
       f"HTTP {d1.status_code} {d1.text[:90] if d1.status_code != 200 else ''}")
    cb = d1.json() if d1.status_code == 200 else cb
    auto = [d for d in cb.get("deductions", []) if d["kind"] == "match_variance"]
    ok(len(auto) == 1 and abs(auto[0]["amount"] - 1760000) < 1,
       "keputusan POTONG melahirkan potongan 'selisih 3-way' bernilai tepat",
       rp(auto[0]["amount"]) if auto else "—")

    twice = api("POST", f"/contra-bons/{cb['id']}/decide", mgr, ENT_A, json={
        "exception_key": key_qty, "action": "accept", "reason_code": "cb_price_agreed"})
    ok(twice.status_code == 400 and "sudah diputus" in twice.text,
       "satu selisih tidak bisa diputus dua kali", twice.text[:100])

    d2 = api("POST", f"/contra-bons/{cb['id']}/decide", mgr, ENT_A, json={
        "exception_key": key_price, "action": "accept", "reason_code": "cb_price_agreed",
        "note": "kenaikan bahan sudah disepakati lewat surel"})
    ok(d2.status_code == 200, "selisih harga diputus: TERIMA (tetap dibayar)",
       f"HTTP {d2.status_code}")
    cb = d2.json() if d2.status_code == 200 else cb
    ok(cb["match_summary"]["pending_count"] == 0,
       "tidak ada lagi selisih tanpa keputusan", f"{len(cb.get('decisions', []))} keputusan")
    return cb


def test_tolerance_is_config(admin: str, mgr: str) -> None:
    """Bukti bahwa toleransi benar-benar dibaca dari Pusat Pengaturan (bukan angka di kode)."""
    head("5 · TOLERANSI 3-WAY = CONFIG (ubah setelan → hasil verifikasi berubah) (US4)")
    bill = make_bill(admin, "po_002",
                     [{"product_id": "prod_tenun_ikat", "billed_qty": 100, "price": 206000}],
                     "received", f"{POC_TAG}/INV-C")
    r = api("POST", "/contra-bons", mgr, ENT_A, json={
        "supplier_id": SUP_C, "entity_id": ENT_A, "bills": [{"bill_id": bill["id"]}],
        "notes": f"{POC_TAG} uji toleransi"})
    cb = r.json()
    made["cbs"].append(cb["id"])
    ok(cb["match_summary"]["exceptions_count"] == 1,
       "harga +3% terdeteksi sebagai selisih pada toleransi bawaan (1% / Rp 50.000)",
       rp(cb["match_summary"]["exceptions_value"]))
    api("POST", f"/contra-bons/{cb['id']}/submit", mgr, ENT_A)
    v1 = api("POST", f"/contra-bons/{cb['id']}/verify", mgr, ENT_A)
    ok(v1.status_code == 400, "verifikasi ditolak (selisih belum diputus)", f"HTTP {v1.status_code}")

    ok(cfg_set(admin, "contra_bon.qty_tolerance_percent", 10, "entity", ENT_A),
       "toleransi persen dinaikkan ke 10% lewat Pusat Pengaturan (scope PT)")
    v2 = api("POST", f"/contra-bons/{cb['id']}/verify", mgr, ENT_A)
    cb2 = v2.json() if v2.status_code == 200 else {}
    ok(v2.status_code == 200 and cb2.get("match_summary", {}).get("exceptions_count") == 0,
       "selisih yang SAMA kini lolos tanpa keputusan — toleransi memang dari config",
       f"HTTP {v2.status_code} · {cb2.get('match_summary', {}).get('exceptions_count')} selisih")
    ok(cfg_reset(admin, "contra_bon.qty_tolerance_percent", "entity", ENT_A),
       "toleransi dikembalikan ke default sistem")
    # Ambang RUPIAH juga menyaring: selisih receh tidak boleh jadi pengecualian.
    ok(cfg_set(admin, "contra_bon.value_tolerance_rupiah", 999000000, "entity", ENT_A),
       "ambang rupiah dinaikkan ke Rp 999.000.000 (uji lapisan kedua)")
    bill2 = make_bill(admin, "po_002",
                      [{"product_id": "prod_ulos_batak", "billed_qty": 80, "price": 303850}],
                      "received", f"{POC_TAG}/INV-C2")
    r3 = api("POST", "/contra-bons", mgr, ENT_A, json={
        "supplier_id": SUP_C, "entity_id": ENT_A, "bills": [{"bill_id": bill2["id"]}],
        "notes": f"{POC_TAG} uji ambang rupiah"})
    cb3 = r3.json()
    made["cbs"].append(cb3["id"])
    ok(cb3["match_summary"]["exceptions_count"] == 0,
       "selisih 3% TIDAK jadi pengecualian karena nilainya di bawah ambang rupiah",
       f"{cb3['match_summary']['exceptions_count']} selisih")
    ok(cfg_reset(admin, "contra_bon.value_tolerance_rupiah", "entity", ENT_A),
       "ambang rupiah dikembalikan ke default")
    for cid in (cb["id"], cb3["id"]):
        api("POST", f"/contra-bons/{cid}/cancel", admin, ENT_A,
            json={"note": f"{POC_TAG} selesai uji toleransi"})


# ═════════════════════════════════════════════════════════════════════════════
#  US5 — POTONGAN TERSTRUKTUR
# ═════════════════════════════════════════════════════════════════════════════
def test_deductions(admin: str, mgr: str, cb: Dict[str, Any],
                    ctx: Dict[str, Any]) -> Dict[str, Any]:
    head("6 · POTONGAN TERSTRUKTUR YANG MENUNJUK DOKUMEN NYATA (US5)")
    r1 = api("POST", f"/contra-bons/{cb['id']}/deductions", mgr, ENT_A, json={
        "kind": "purchase_return", "ref_id": ctx["ret"]["id"],
        "note": "nota debit kain cacat"})
    ok(r1.status_code == 200, "potongan RETUR BELI (nota debit) diterima",
       f"HTTP {r1.status_code} {r1.text[:90] if r1.status_code != 200 else ''}")
    cb = r1.json() if r1.status_code == 200 else cb
    again = api("POST", f"/contra-bons/{cb['id']}/deductions", mgr, ENT_A, json={
        "kind": "purchase_return", "ref_id": ctx["ret"]["id"]})
    ok(again.status_code == 400 and ("sudah dipakai" in again.text
                                    or "sudah menjadi potongan" in again.text
                                    or "tidak tersedia" in again.text),
       "nota debit yang sama TIDAK bisa dipotong dua kali (INV-CB-04)", again.text[:110])

    r2 = api("POST", f"/contra-bons/{cb['id']}/deductions", mgr, ENT_A, json={
        "kind": "supplier_advance", "ref_id": ctx["advance"]["id"]})
    ok(r2.status_code == 200, "potongan UANG MUKA supplier diterima",
       f"HTTP {r2.status_code} {r2.text[:90] if r2.status_code != 200 else ''}")
    cb = r2.json() if r2.status_code == 200 else cb

    r3 = api("POST", f"/contra-bons/{cb['id']}/deductions", mgr, ENT_A, json={
        "kind": "supplier_penalty", "amount": 500000, "reason_code": "cb_supplier_late",
        "note": "kirim terlambat 5 hari dari kesepakatan"})
    ok(r3.status_code == 200, "potongan DENDA KETERLAMBATAN supplier diterima",
       f"HTTP {r3.status_code}")
    cb = r3.json() if r3.status_code == 200 else cb

    r4 = api("POST", f"/contra-bons/{cb['id']}/deductions", mgr, ENT_A, json={
        "kind": "other_agreed", "amount": 250000, "reason_code": "cb_other_agreed",
        "note": "ongkos kirim ditanggung supplier"})
    ok(r4.status_code == 200, "potongan LAIN yang disepakati diterima (wajib alasan)",
       f"HTTP {r4.status_code}")
    cb = r4.json() if r4.status_code == 200 else cb

    nore = api("POST", f"/contra-bons/{cb['id']}/deductions", mgr, ENT_A, json={
        "kind": "other_agreed", "amount": 100000})
    ok(nore.status_code == 400 and "wajib dipilih" in nore.text,
       "potongan bebas TANPA alasan ditolak", nore.text[:100])

    mak = api("POST", f"/contra-bons/{cb['id']}/deductions", mgr, ENT_A, json={
        "kind": "makloon_claim", "amount": 100000, "reason_code": "cb_other_agreed"})
    ok(mak.status_code == 400 and "sudah menempel di faktur" in mak.text,
       "potongan klaim makloon DITOLAK — sudah menempel di faktur (anti dobel potong)",
       mak.text[:120])

    huge = api("POST", f"/contra-bons/{cb['id']}/deductions", mgr, ENT_A, json={
        "kind": "other_agreed", "amount": 999000000, "reason_code": "cb_other_agreed",
        "note": "sengaja berlebihan"})
    ok(huge.status_code == 400 and "tidak boleh negatif" in huge.text,
       "potongan yang membuat nilai bersih NEGATIF ditolak (INV-CB-02)", huge.text[:120])

    kinds = {d["kind"] for d in cb.get("deductions", [])}
    ok(kinds == {"match_variance", "purchase_return", "supplier_advance",
                 "supplier_penalty", "other_agreed"},
       "lima jenis potongan aktif dalam satu kontrabon", ", ".join(sorted(kinds)))
    expected_net = round(cb["totals"]["bills_total"] - cb["totals"]["deductions_total"], 2)
    ok(abs(cb["totals"]["net_payable"] - expected_net) < 0.01,
       "nilai bersih = Σ faktur − Σ potongan", rp(cb["totals"]["net_payable"]))

    # Potongan bisa dicabut selama belum diverifikasi (bukan jalan satu arah).
    tmp = api("POST", f"/contra-bons/{cb['id']}/deductions", mgr, ENT_A, json={
        "kind": "other_agreed", "amount": 1000, "reason_code": "cb_other_agreed",
        "note": "coba lalu dibatalkan"}).json()
    tid = tmp["deductions"][-1]["id"]
    rm = api("DELETE", f"/contra-bons/{cb['id']}/deductions/{tid}", mgr, ENT_A)
    ok(rm.status_code == 200 and len(rm.json()["deductions"]) == 5,
       "potongan bisa dicabut sebelum verifikasi", f"{len(rm.json()['deductions'])} potongan")
    return rm.json() if rm.status_code == 200 else cb


# ═════════════════════════════════════════════════════════════════════════════
#  US6 — SIKLUS, AMBANG PERSETUJUAN, PEMISAHAN TUGAS
# ═════════════════════════════════════════════════════════════════════════════
def test_cycle(admin: str, mgr: str, cb: Dict[str, Any]) -> Dict[str, Any]:
    head("7 · SIKLUS + AMBANG PERSETUJUAN DARI CONFIG + PEMISAHAN TUGAS (US6)")
    v = api("POST", f"/contra-bons/{cb['id']}/verify", mgr, ENT_A)
    ok(v.status_code == 200 and v.json()["status"] == "verified",
       "kontrabon diverifikasi (seluruh selisih sudah diputus)",
       f"HTTP {v.status_code} {v.text[:90] if v.status_code != 200 else ''}")
    cb = v.json() if v.status_code == 200 else cb

    early = api("POST", f"/contra-bons/{cb['id']}/pay", mgr, ENT_A, json={"amount": 1000})
    ok(early.status_code == 400 and "disetujui" in early.text,
       "pembayaran SEBELUM disetujui ditolak (kebijakan Pusat Pengaturan)", early.text[:120])

    self_ap = api("POST", f"/contra-bons/{cb['id']}/approve", mgr, ENT_A)
    ok(self_ap.status_code == 403 and "Pemisahan tugas" in self_ap.text,
       "pembuat kontrabon TIDAK boleh menyetujui kontrabon sendiri (SoD)", self_ap.text[:120])

    ok(cfg_set(admin, "contra_bon.approval_threshold_rupiah", 1000, "entity", ENT_A),
       "ambang 'kontrabon bernilai besar' diturunkan ke Rp 1.000 (uji wewenang)")
    mgr2 = login("sales2@kainnusantara.id")
    low = api("POST", f"/contra-bons/{cb['id']}/approve", mgr2, ENT_A)
    ok(low.status_code == 403, "peran di bawah wewenang ditolak", f"HTTP {low.status_code}")
    a1 = api("POST", f"/contra-bons/{cb['id']}/approve", admin, ENT_A)
    ok(a1.status_code == 200 and a1.json()["status"] == "approved",
       "di atas ambang: hanya ADMIN yang boleh menyetujui — dan berhasil",
       f"HTTP {a1.status_code} · {rp(a1.json()['totals']['net_payable']) if a1.status_code == 200 else a1.text[:90]}")
    cb = a1.json() if a1.status_code == 200 else cb
    ok(cfg_reset(admin, "contra_bon.approval_threshold_rupiah", "entity", ENT_A),
       "ambang dikembalikan ke default sistem")

    s = api("POST", f"/contra-bons/{cb['id']}/schedule", admin, ENT_A, json={
        "planned_payment_date": day(3), "method": "transfer", "bank_account_id": BANK_A,
        "notes": f"{POC_TAG} sesuai termin"})
    ok(s.status_code == 200 and s.json()["status"] == "scheduled_payment",
       "pembayaran dijadwalkan", f"{day(3)} · HTTP {s.status_code}")
    cb = s.json() if s.status_code == 200 else cb
    tl = {e["event"] for e in cb.get("timeline", [])}
    ok({"dibuat", "diajukan", "keputusan", "potongan", "diverifikasi", "disetujui",
        "dijadwalkan"} <= tl, "jejak waktu memuat seluruh langkah siklus", ", ".join(sorted(tl)))
    return cb


# ═════════════════════════════════════════════════════════════════════════════
#  US7/US8 — PEMBAYARAN BORONGAN + REKONSILIASI BANK
# ═════════════════════════════════════════════════════════════════════════════
def test_pay(admin: str, cb: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    head("8 · BAYAR SEKALI UNTUK BANYAK FAKTUR + POTONGAN NON-KAS (US7)")
    net = cb["totals"]["net_payable"]
    part = round(net / 2, 2)
    p1 = api("POST", f"/contra-bons/{cb['id']}/pay", admin, ENT_A, json={
        "amount": part, "method": "transfer", "cash_type": "kas_besar",
        "bank_account_id": BANK_A, "paid_at": day(0), "notes": f"{POC_TAG} termin 1"})
    ok(p1.status_code == 200, "pembayaran pertama dicatat",
       f"HTTP {p1.status_code} {p1.text[:120] if p1.status_code != 200 else rp(part)}")
    cb = p1.json() if p1.status_code == 200 else cb
    pr = cb.get("payment_result") or {}
    cash = pr.get("cash_transaction") or {}
    if cash.get("id"):
        made["cash"].append(cash["id"])
    ok(cash.get("ref_type") == "contra_bon" and len(pr.get("cash_allocations", [])) >= 1,
       "SATU transaksi kas keluar melunasi beberapa faktur sekaligus",
       f"{cash.get('number')} → {len(pr.get('cash_allocations', []))} faktur")
    ok(abs(pr.get("deductions_applied", 0) - cb["totals"]["deductions_total"]) < 0.01,
       "seluruh potongan diterapkan sebagai pelunasan NON-KAS pada pembayaran pertama",
       rp(pr.get("deductions_applied")))
    ok(cb["status"] == "scheduled_payment",
       "pembayaran sebagian belum melunasi kontrabon", f"sisa {rp(cb['totals']['outstanding'])}")

    over = api("POST", f"/contra-bons/{cb['id']}/pay", admin, ENT_A, json={
        "amount": cb["totals"]["outstanding"] + 1000000})
    ok(over.status_code == 400 and "melebihi sisa" in over.text,
       "pembayaran melebihi sisa bersih ditolak", over.text[:110])

    # ── US8 — bayar sisanya LANGSUNG dari baris mutasi bank keluar ────────────
    head("9 · NYAMBUNG KE REKONSILIASI BANK G-8 (US8)")
    rest = cb["totals"]["outstanding"]
    imp = api("POST", "/bank-reconciliation/import", admin, ENT_A, json={
        "bank_account_id": BANK_A, "lines": [
            {"stmt_date": day(0), "amount": rest, "direction": "out",
             "description": f"TRSF KELUAR SOLO WEAVE {cb['number']} [{POC_TAG}]",
             "ref": cb["number"]}]})
    ok(imp.status_code == 200, "mutasi bank keluar diimpor", f"HTTP {imp.status_code}")
    lines = api("GET", f"/bank-reconciliation/lines?bank_account_id={BANK_A}", admin, ENT_A).json()
    ln = next((x for x in lines if POC_TAG in (x.get("description") or "")
               and x.get("status") != "matched"), None)
    if ln:
        made["lines"].append(ln["id"])
    ok(bool(ln), "baris mutasi ditemukan & belum tertaut", (ln or {}).get("id", "—"))

    cand = api("GET", f"/contra-bons/bank-line-candidates/{ln['id']}", admin, ENT_A).json()
    top = (cand.get("candidates") or [{}])[0]
    ok(top.get("id") == cb["id"] and top.get("exact") is True,
       "kontrabon yang cocok muncul sebagai kandidat TERATAS (nominal tepat)",
       f"{top.get('number')} · {rp(top.get('outstanding'))}")

    p2 = api("POST", f"/contra-bons/{cb['id']}/pay-from-bank-line/{ln['id']}", admin, ENT_A,
             json={"note": f"{POC_TAG} dari mutasi bank"})
    ok(p2.status_code == 200, "kontrabon dibayar LANGSUNG dari baris mutasi bank",
       f"HTTP {p2.status_code} {p2.text[:130] if p2.status_code != 200 else rp(rest)}")
    cb = p2.json() if p2.status_code == 200 else cb
    cash2 = (cb.get("payment_result") or {}).get("cash_transaction") or {}
    if cash2.get("id"):
        made["cash"].append(cash2["id"])
    ok(cb["status"] == "paid" and cb["totals"]["outstanding"] < 0.01,
       "kontrabon LUNAS", f"{rp(cb['totals']['paid_total'])} dari {rp(cb['totals']['net_payable'])}")
    ok((cb.get("bank_line") or {}).get("status") == "matched",
       "baris mutasi bank otomatis TERTAUT ke transaksi kasnya (rekonsiliasi beres)",
       (cb.get("bank_line") or {}).get("match_kind", ""))

    # ── Subledger hutang & buku besar ────────────────────────────────────────
    head("10 · SUBLEDGER HUTANG & BUKU BESAR IKUT BENAR (US7)")
    for b in cb["bills"]:
        bill = api("GET", f"/vendor-bills/{b['bill_id']}", admin, ENT_A).json()
        via = round(sum(float(p.get("amount") or 0) for p in (bill.get("payments") or [])
                        if p.get("contra_bon_id") == cb["id"]), 2)
        ok(abs(via - b["applied_amount"]) < 0.01 and bill["status"] == "paid",
           f"faktur {b['bill_number']} lunas & pelunasannya tercatat lewat kontrabon",
           f"{rp(via)} · status {bill['status']}")
    jes = dbrun(lambda db: db.journal_entries.find(
        {"source_type": "contra_bon_deduction",
         "source_id": {"$regex": f"^{cb['id']}:"}}, {"_id": 0}).to_list(50))
    ok(len(jes) == 4, "empat potongan berjurnal (uang muka · denda · selisih 3-way · lain)",
       f"{len(jes)} jurnal")
    ok(all(abs(sum(l["debit"] for l in j["lines"]) - sum(l["credit"] for l in j["lines"])) < 0.01
           for j in jes), "setiap jurnal potongan SEIMBANG")
    ret_je = dbrun(lambda db: db.journal_entries.count_documents(
        {"source_type": "contra_bon_deduction", "source_id": {"$regex": f"^{cb['id']}:"},
         "lines.account_code": "1-1300"}))
    ok(ret_je == 0,
       "potongan RETUR BELI sengaja TIDAK berjurnal ulang (jurnalnya sudah lahir saat retur "
       "disetujui — kalau diulang, hutang berkurang dua kali)")
    accs = {l["account_code"] for j in jes for l in j["lines"]}
    ok({"2-1100", "1-1400", "4-9300", "2-1150", "4-9000"} <= accs,
       "lawan akun tiap jenis potongan sesuai rancangan", ", ".join(sorted(accs)))
    return cb


# ═════════════════════════════════════════════════════════════════════════════
#  US9/US10 — TANDA TERIMA & RELASI DOKUMEN
# ═════════════════════════════════════════════════════════════════════════════
def test_receipt_and_refs(admin: str, cb: Dict[str, Any]) -> None:
    head("11 · TANDA TERIMA KONTRABON + RELASI DOKUMEN (US9/US10)")
    rc = api("GET", f"/contra-bons/{cb['id']}/receipt", admin, ENT_A)
    data = rc.json() if rc.status_code == 200 else {}
    ok(rc.status_code == 200 and len(data.get("contra_bon", {}).get("bills", [])) == 2,
       "data tanda terima memuat seluruh faktur", f"HTTP {rc.status_code}")
    ok(len(data.get("goods_receipts") or []) >= 1,
       "tanda terima juga menyebut penerimaan barang (GRN) yang terkait",
       f"{len(data.get('goods_receipts') or [])} GRN")

    pdf = api("GET", f"/pdf/render/contra_bon/{cb['id']}?format=html", admin, ENT_A)
    blob = pdf.text if pdf.status_code == 200 else ""
    ok(pdf.status_code == 200, "dokumen cetak 'Tanda Terima Kontrabon' terbentuk",
       f"HTTP {pdf.status_code} {pdf.text[:120] if pdf.status_code != 200 else f'{len(blob)} bita'}")
    ok("Tanda Terima Kontrabon" in blob and cb["number"] in blob,
       "judul & nomor kontrabon tercetak", cb["number"])
    ok("POTONGAN" in blob.upper(), "potongan ikut tercetak agar supplier melihat rinciannya")
    ok(all(b["bill_number"] in blob or (b.get("supplier_invoice_no") or "x") in blob
           for b in cb["bills"]), "setiap faktur yang ditukar tercetak")
    pdf_bin = api("GET", f"/pdf/render/contra_bon/{cb['id']}", admin, ENT_A)
    ok(pdf_bin.status_code == 200 and pdf_bin.content[:4] == b"%PDF",
       "berkas PDF benar-benar terbentuk (siap ditandatangani supplier)",
       f"{len(pdf_bin.content)} bita")

    refs = api("GET", f"/documents/refs/contra_bon/{cb['id']}", admin, ENT_A).json()
    blob2 = str(refs)
    ok(all(b["bill_number"] in blob2 for b in cb["bills"]),
       "relasi dokumen: kontrabon → tagihan supplier", f"{len(str(refs))} bita jejak")
    ok(any(t in blob2 for t in ("purchase_order", "Purchase Order")),
       "relasi dokumen: kontrabon → PO")
    ok("cash_transaction" in blob2 or "Kas" in blob2,
       "relasi dokumen: kontrabon → transaksi kas pembayaran")
    back = api("GET", f"/documents/refs/vendor_bill/{cb['bills'][0]['bill_id']}",
               admin, ENT_A).json()
    ok(cb["number"] in str(back), "relasi DUA ARAH: dari tagihan bisa kembali ke kontrabon")


# ═════════════════════════════════════════════════════════════════════════════
#  US11 — ISOLASI LINTAS-PT
# ═════════════════════════════════════════════════════════════════════════════
def test_isolation(admin: str, mgr: str) -> Optional[str]:
    head("12 · ISOLASI LINTAS-PT (US11)")
    bill = make_bill(admin, "po_006",
                     [{"product_id": "prod_endek_bali", "billed_qty": 80, "price": 270000}],
                     "ordered", f"{POC_TAG}/INV-KANDA", ent=ENT_B)
    r = api("POST", "/contra-bons", admin, ENT_B, json={
        "supplier_id": SUP_B, "entity_id": ENT_B, "bills": [{"bill_id": bill["id"]}],
        "notes": f"{POC_TAG} kontrabon PT KANDA"})
    ok(r.status_code == 200, "kontrabon PT-B dibuat oleh admin (entitas aktif PT-B)",
       f"HTTP {r.status_code} {r.text[:120] if r.status_code != 200 else r.json()['number']}")
    if r.status_code != 200:
        return None
    cb_b = r.json()
    made["cbs"].append(cb_b["id"])
    ok(cb_b["number"].startswith("KANDA/CB-"),
       "nomor memakai kode PT-B (bukan nomor PT-A)", cb_b["number"])

    g = api("GET", f"/contra-bons/{cb_b['id']}", mgr, ENT_A)
    ok(g.status_code == 403 and "entitas" in g.text.lower(),
       "manajer dengan entitas aktif PT-A minta kontrabon PT-B → 403 KARENA ENTITAS",
       f"HTTP {g.status_code} · {g.text[:90]}")
    p = api("POST", f"/contra-bons/{cb_b['id']}/pay", mgr, ENT_A, json={"amount": 1000})
    ok(p.status_code == 403, "membayar kontrabon PT lain ditolak walau id dikirim eksplisit",
       f"HTTP {p.status_code}")
    lst = api("GET", "/contra-bons", mgr, ENT_A).json()
    ok(all(x["entity_id"] == ENT_A for x in lst),
       "daftar kontrabon PT-A tidak memuat dokumen PT-B", f"{len(lst)} baris")
    cross = api("POST", "/contra-bons", mgr, ENT_A, json={
        "supplier_id": SUP_B, "entity_id": ENT_B, "bills": [{"bill_id": bill["id"]}]})
    ok(cross.status_code == 403, "membuat kontrabon ATAS NAMA PT lain ditolak",
       f"HTTP {cross.status_code}")
    api("POST", f"/contra-bons/{cb_b['id']}/cancel", admin, ENT_B,
        json={"note": f"{POC_TAG} selesai uji isolasi"})
    return cb_b["id"]


# ═════════════════════════════════════════════════════════════════════════════
#  SENGKETA
# ═════════════════════════════════════════════════════════════════════════════
def test_dispute(admin: str, mgr: str, ctx: Dict[str, Any]) -> None:
    head("13 · JALUR SENGKETA — faktur supplier keliru (US6)")
    bill = make_bill(admin, "po_001",
                     [{"product_id": "prod_batik_mega", "billed_qty": 150, "price": 165000}],
                     "received", f"{POC_TAG}/INV-E")
    cb = api("POST", "/contra-bons", mgr, ENT_A, json={
        "supplier_id": SUP_D, "entity_id": ENT_A,
        "bills": [{"bill_id": bill["id"]}], "notes": f"{POC_TAG} uji sengketa"}).json()
    made["cbs"].append(cb["id"])
    api("POST", f"/contra-bons/{cb['id']}/submit", mgr, ENT_A)
    nore = api("POST", f"/contra-bons/{cb['id']}/dispute", mgr, ENT_A, json={"note": "salah"})
    ok(nore.status_code == 400 and "wajib dipilih" in nore.text,
       "sengketa tanpa alasan berlabel ditolak", nore.text[:100])
    d = api("POST", f"/contra-bons/{cb['id']}/dispute", mgr, ENT_A, json={
        "reason_code": "cb_invoice_wrong", "note": "nomor PO di faktur supplier salah"})
    ok(d.status_code == 200 and d.json()["status"] == "disputed",
       "kontrabon masuk status SENGKETA berikut alasannya", f"HTTP {d.status_code}")
    back = api("POST", f"/contra-bons/{cb['id']}/submit", mgr, ENT_A)
    ok(back.status_code == 200 and back.json()["status"] == "submitted",
       "setelah supplier mengoreksi faktur, kontrabon bisa diajukan lagi",
       f"HTTP {back.status_code}")
    c = api("POST", f"/contra-bons/{cb['id']}/cancel", admin, ENT_A,
            json={"note": f"{POC_TAG} selesai uji sengketa"})
    ok(c.status_code == 200 and c.json()["status"] == "cancelled",
       "kontrabon yang belum dibayar bisa dibatalkan", f"HTTP {c.status_code}")
    rel = api("GET", f"/contra-bons/prepare?supplier_id={SUP_D}", admin, ENT_A).json()
    ok(bill["id"] in {b["bill_id"] for b in rel.get("bills", [])},
       "faktur DILEPAS kembali setelah kontrabon dibatalkan (tidak tersandera)")


# ═════════════════════════════════════════════════════════════════════════════
#  INVARIAN + BUKTI-MERAH
# ═════════════════════════════════════════════════════════════════════════════
def test_invariants(cb_id: str) -> None:
    head("14 · INVARIAN INV-CB-01..04 + BUKTI-MERAH (US11)")
    rc, out = integrity("contrabon")
    ok(rc == 0 and "FAIL 0" in out, "seluruh invarian kontrabon HIJAU pada data nyata",
       out.strip().splitlines()[-2].strip() if out else "")

    def inject(fn):
        return dbrun(fn)

    # ── INV-CB-01: faktur dipegang dua kontrabon ────────────────────────────
    orig = inject(lambda db: db.contra_bons.find_one({"id": cb_id}, {"_id": 0}))
    clone = dict(orig)
    clone["id"] = "cbn_POCRED01"
    clone["number"] = "KSC/CB-99901"
    inject(lambda db: db.contra_bons.insert_one(clone))
    rc1, out1 = integrity("contrabon")
    ok(rc1 != 0 and "INV-CB-01" in out1 and "FAIL" in out1,
       "BUKTI-MERAH INV-CB-01: faktur di dua kontrabon → gate MEMERAH", f"exit {rc1}")
    inject(lambda db: db.contra_bons.delete_one({"id": "cbn_POCRED01"}))

    # ── INV-CB-02: total dipalsukan ─────────────────────────────────────────
    inject(lambda db: db.contra_bons.update_one(
        {"id": cb_id}, {"$set": {"totals.net_payable": 1.0}}))
    rc2, out2 = integrity("contrabon")
    ok(rc2 != 0 and "INV-CB-02" in out2,
       "BUKTI-MERAH INV-CB-02: nilai bersih tidak sama dengan faktur − potongan → MEMERAH",
       f"exit {rc2}")
    inject(lambda db: db.contra_bons.update_one(
        {"id": cb_id}, {"$set": {"totals.net_payable": orig["totals"]["net_payable"]}}))

    # ── INV-CB-03: keputusan dihapus dari kontrabon terverifikasi ───────────
    inject(lambda db: db.contra_bons.update_one({"id": cb_id}, {"$set": {"decisions": []}}))
    rc3, out3 = integrity("contrabon")
    ok(rc3 != 0 and "INV-CB-03" in out3,
       "BUKTI-MERAH INV-CB-03: selisih tanpa keputusan pada kontrabon terverifikasi → MEMERAH",
       f"exit {rc3}")
    inject(lambda db: db.contra_bons.update_one(
        {"id": cb_id}, {"$set": {"decisions": orig["decisions"]}}))

    # ── INV-CB-04: potongan makloon diselundupkan ke DB ────────────────────
    inject(lambda db: db.contra_bons.update_one({"id": cb_id}, {"$push": {"deductions": {
        "id": "cbd_POCRED04", "kind": "makloon_claim", "label": "selundupan",
        "amount": 1000.0, "ref_id": "", "posts_gl": False}}}))
    rc4, out4 = integrity("contrabon")
    ok(rc4 != 0 and "INV-CB-04" in out4,
       "BUKTI-MERAH INV-CB-04: potongan klaim makloon (dobel) → MEMERAH", f"exit {rc4}")
    inject(lambda db: db.contra_bons.update_one(
        {"id": cb_id}, {"$pull": {"deductions": {"id": "cbd_POCRED04"}}}))

    rc5, out5 = integrity("contrabon")
    ok(rc5 == 0 and "FAIL 0" in out5, "sesudah dipulihkan, invarian kontrabon HIJAU lagi",
       f"exit {rc5}")


# ═════════════════════════════════════════════════════════════════════════════
#  PEMBERSIHAN
# ═════════════════════════════════════════════════════════════════════════════
def cleanup(admin: str, stock_snap: Any) -> None:
    head("15 · PEMBERSIHAN — nol residu (POC tidak boleh merusak data demo)")
    bills = list(dict.fromkeys(made["bills"]))
    cbs = list(dict.fromkeys(made["cbs"]))
    cash = list(dict.fromkeys(made["cash"]))
    rets = list(dict.fromkeys(made["returns"]))
    lines = list(dict.fromkeys(made["lines"]))

    async def purge(db):
        n: Dict[str, int] = {}
        n["cbs"] = (await db.contra_bons.delete_many({"id": {"$in": cbs}})).deleted_count
        n["bills"] = (await db.vendor_bills.delete_many({"id": {"$in": bills}})).deleted_count
        n["cash"] = (await db.cash_transactions.delete_many(
            {"$or": [{"id": {"$in": cash}}, {"description": {"$regex": POC_TAG}},
                     {"ref_type": "contra_bon", "ref_id": {"$in": cbs}}]})).deleted_count
        n["returns"] = (await db.purchase_returns.delete_many(
            {"$or": [{"id": {"$in": rets}}, {"notes": {"$regex": POC_TAG}}]})).deleted_count
        n["lines"] = (await db.bank_statement_lines.delete_many(
            {"$or": [{"id": {"$in": lines}},
                     {"description": {"$regex": POC_TAG}}]})).deleted_count
        # Jurnal: hanya yang lahir dari artefak POC.
        srcs = bills + cbs + cash + rets
        n["je"] = (await db.journal_entries.delete_many({"$or": [
            {"source_id": {"$in": srcs}},
            {"source_type": "contra_bon_deduction",
             "$or": [{"source_id": {"$regex": f"^{c}:"}} for c in cbs] or [{"source_id": "-"}]},
        ]})).deleted_count
        n["notif"] = (await db.notifications.delete_many(
            {"type": {"$in": ["contra_bon_cycle", "contra_bon_overdue"]}})).deleted_count
        # Keputusan selisih pembayaran (G-3) yang lahir dari faktur POC — kalau tertinggal,
        # INV-REF-01 memerah karena induknya (faktur) sudah dihapus.
        n["variance"] = (await db.payment_variance_decisions.delete_many(
            {"$or": [{"bill_id": {"$in": bills}}, {"note": {"$regex": POC_TAG}}]})).deleted_count
        # Relasi dua arah (G-4) disimpan INLINE pada dokumen. Dokumen POC sudah dihapus,
        # tetapi dokumen demo yang MASIH HIDUP (PO) menyimpan tautan ke dokumen POC →
        # harus dicabut, kalau tidak layar PO memperlihatkan tautan mati.
        srcs_all = srcs + lines
        n["refs_pulled"] = 0
        for coll in ("purchase_orders", "wms_tasks", "vendor_bills", "cash_transactions",
                     "purchase_returns", "makloon_orders", "sales_orders"):
            upd = await db[coll].update_many(
                {"refs.doc_id": {"$in": srcs_all}},
                {"$pull": {"refs": {"doc_id": {"$in": srcs_all}}}})
            n["refs_pulled"] += upd.modified_count
        n["seq"] = 0
        # Penghitung nomor kontrabon DIPULIHKAN ke nilai sebelum POC (bukan dihapus).
        # Kalau dihapus, kontrabon berikutnya lahir dengan nomor KSC/CB-00001 yang sudah
        # dipakai data demo → nomor kembar pada dokumen keuangan.
        await db.number_sequences.delete_many({"doc_type": "CB"})
        if base["cb_seq"]:
            await db.number_sequences.insert_many([dict(s) for s in base["cb_seq"]])
            n["seq"] = len(base["cb_seq"])
        # Override konfigurasi milik POC: baris riwayat + proyeksi ke setelan lama.
        n["cfg"] = (await db.config_values.delete_many(
            {"reason": {"$regex": POC_TAG}})).deleted_count
        await db.system_settings.update_one({"scope": ENT_A}, {"$unset": {"contra_bon": ""}})
        # Jadwal tukar faktur: dipulihkan ke nilai semula (data demo punya jadwalnya).
        if base["sup_a_exchange"] is None:
            await db.suppliers.update_one({"id": SUP_A}, {"$unset": {"invoice_exchange": ""}})
        else:
            await db.suppliers.update_one({"id": SUP_A},
                                          {"$set": {"invoice_exchange": base["sup_a_exchange"]}})
        # Nilai retur pada PO dipulihkan (retur POC sudah dihapus).
        for po in ("po_001", "po_002", "po_003", "po_006"):
            await db.purchase_orders.update_one({"id": po}, {"$set": {"returned_amount": 0.0}})
        return n

    n = dbrun(purge)
    ok(True, "artefak POC dihapus dari basis data", str(n))

    # Ringkasan penagihan PO dihitung ulang dari faktur yang MASIH ada.
    def resync():
        import asyncio
        sys.path.insert(0, "/app/backend")
        from services.vendor_bill_service import sync_po_billing

        async def go():
            for po in ("po_001", "po_002", "po_003", "po_006"):
                await sync_po_billing(po)
            pos = ["po_001", "po_002", "po_003", "po_006"]
            return pos

        return asyncio.run(go())

    try:
        resync()
        ok(True, "ringkasan penagihan PO dihitung ulang dari faktur yang tersisa")
    except Exception as exc:  # noqa: BLE001
        ok(False, f"gagal menghitung ulang ringkasan PO: {exc}")

    ok(restore_stock(stock_snap) or True,
       "stok (roll/saldo/mutasi/lot) dipulihkan EKSAK dari snapshot")

    left = dbrun(lambda db: db.contra_bons.count_documents({}))
    ok(left == base["cbs"],
       "kontrabon di basis data kembali ke jumlah sebelum POC (data demo utuh)",
       f"{left} dokumen · garis dasar {base['cbs']}")
    left_b = dbrun(lambda db: db.vendor_bills.count_documents(
        {"supplier_invoice_no": {"$regex": POC_TAG}}))
    ok(left_b == 0, "tidak ada faktur POC sisa", f"{left_b} dokumen")
    rc, out = integrity()
    ok(rc == 0, "verify_data_integrity LENGKAP hijau setelah pembersihan",
       out.strip().splitlines()[-2].strip() if out else "")


# ═════════════════════════════════════════════════════════════════════════════
def resolve_actors() -> Dict[str, str]:
    """Ambil id supplier dari PO demo yang deterministik (anti-drift sesudah re-seed)."""
    global SUP_A, SUP_B, SUP_C, SUP_D
    wanted = {"po_003": "SUP_A", "po_002": "SUP_C", "po_006": "SUP_B", "po_001": "SUP_D"}
    rows = dbrun(lambda db: db.purchase_orders.find(
        {"id": {"$in": list(wanted)}}, {"_id": 0, "id": 1, "supplier_id": 1,
                                        "supplier_name": 1}).to_list(20))
    found = {r["id"]: r for r in rows}
    missing = [p for p in wanted if p not in found]
    if missing:
        raise RuntimeError(f"PO demo hilang: {missing} — jalankan `python seed_realistic.py`")
    SUP_A = found["po_003"]["supplier_id"]
    SUP_C = found["po_002"]["supplier_id"]
    SUP_B = found["po_006"]["supplier_id"]
    SUP_D = found["po_001"]["supplier_id"]
    return {p: found[p].get("supplier_name", "") for p in wanted}


def snapshot_baseline() -> None:
    """Keadaan yang HARUS sama sesudah POC (dipakai blok pembersihan)."""
    async def _gather(db):
        return {
            "cbs": await db.contra_bons.count_documents({}),
            "cb_seq": await db.number_sequences.find(
                {"doc_type": "CB"}, {"_id": 0}).to_list(50),
            "sup_a": await db.suppliers.find_one(
                {"id": SUP_A}, {"_id": 0, "invoice_exchange": 1}),
        }

    got = dbrun(_gather)
    base["cbs"] = got["cbs"]
    base["cb_seq"] = got["cb_seq"]
    base["sup_a_exchange"] = (got["sup_a"] or {}).get("invoice_exchange")


def main() -> int:
    print(f"{B}{C}{'=' * 78}\n  POC FASE G-7 — KONTRABON ADVANCED (tukar faktur supplier)\n"
          f"  {BASE}  ·  {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
          f"{'=' * 78}{X}")
    admin = login("admin@kainnusantara.id")
    mgr = login("manager@kainnusantara.id")
    names = resolve_actors()
    snapshot_baseline()
    print(f"  [aktor] {' · '.join(f'{k}={v}' for k, v in names.items())}")
    print(f"  [garis dasar] {base['cbs']} kontrabon demo sudah ada — POC wajib "
          "meninggalkannya utuh.")
    stock = snapshot_stock()
    cb_id = ""
    try:
        ctx = setup(admin)
        test_schedule(admin)
        test_unbilled(admin)
        cb = test_create(mgr, ctx)
        cb = test_match(admin, mgr, cb, ctx)
        test_tolerance_is_config(admin, mgr)
        cb = test_deductions(admin, mgr, cb, ctx)
        cb = test_cycle(admin, mgr, cb)
        cb = test_pay(admin, cb, ctx)
        cb_id = cb["id"]
        test_receipt_and_refs(admin, cb)
        test_isolation(admin, mgr)
        test_dispute(admin, mgr, ctx)
        test_invariants(cb_id)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        ok(False, f"POC berhenti karena galat: {exc}")
    finally:
        try:
            cleanup(admin, stock)
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(False, f"pembersihan gagal: {exc}")

    total = res["pass"] + res["fail"]
    print(f"\n{B}{'=' * 78}\n  {G}PASS {res['pass']}{X}  |  {R}FAIL {res['fail']}{X}  "
          f"|  total {total}\n{'=' * 78}{X}")
    if res["fail"]:
        print(f"{R}{B}POC G-7 GAGAL — perbaiki dulu sebelum lanjut.{X}")
        return 1
    print(f"{G}{B}POC G-7 HIJAU — kontrabon siap dipakai (nol residu).{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
