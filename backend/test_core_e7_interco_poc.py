#!/usr/bin/env python3
"""POC FASE E-7 — **ANTAR-ENTITAS** (satu berkas, self-cleanup, bukti-merah).

Membuktikan SELURUH gelombang E-7 lewat **endpoint produksi** (bukan menyentuh DB
langsung), memakai identitas nyata (admin · sales) dan badan usaha demo:

  E7a  pagar “lawan transaksi ternyata PT sendiri” — PO · PR · realisasi PR (kebocoran
       nyata yang ditemukan sesi 2026-08-11) · Blanket PO · RFQ · pelanggan/pemasok
       kembar · nonaktifkan cermin pemasok
  E7b  `interco_returns` mengirim `pair_id` + `qty_total`; nomor TRF ber-prefix entitas
  E7c  HPP taksiran WAJIB BERLABEL di rapor margin (bukan “margin 100%” telanjang)
  E7d  Permintaan Internal: sales mengajukan (tanpa memilih PT sumber), admin menindak
       → transaksi antar-PT bertaut, sales 403 di rincian stok PT lain & di konversi
  E7e  kas tingkat grup DIHAPUS: `entity_id="all"` ditolak untuk kas & rekening
  E7f  pinjaman uang antar-PT: dokumen kembar · kas kembar · jurnal DUA buku ·
       saldo non-dagang · eliminasi konsolidasi mengikuti sisa pinjaman
  E7g  pindah aset tetap antar-PT: nilai buku + masa manfaat sisa · utang antar-PT ·
       laba pindah dieliminasi · pembayaran memindahkan uang

BUKTI-MERAH: setiap pagar diuji dari DUA sisi — kasus yang HARUS ditolak dan kasus
kontrol yang HARUS lolos. Kalau pagarnya dicabut, POC ini memerah.

Jalankan: `python backend/test_core_e7_interco_poc.py` (butuh backend hidup + seed).
"""
import os
import sys
import httpx

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
PWD = "demo12345"
ENT_A, ENT_B = "ent_ksc", "ent_kanda"
G_SUPPLIER = "sup_grp_ksc_kanda"          # cermin CV Kanda Suka di layar KSC

GREEN, RED, YEL, RST = "\033[92m", "\033[91m", "\033[93m", "\033[0m"
RESULTS = []
CLEANUP = {"loans": [], "requests": [], "prs": [], "interco_pairs": []}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    tag = f"{GREEN}PASS{RST}" if ok else f"{RED}FAIL{RST}"
    print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(ok)


def client(email, entity=ENT_A):
    cl = httpx.Client(base_url=BASE, timeout=90.0)
    r = cl.post("/api/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    cl.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                       "X-Entity-Id": entity})
    return cl


def rows(x):
    return x.get("items") if isinstance(x, dict) else x


# ═══════════════════════════════════════════════════════════════════════════
def e7a_group_partner_guard(adm, mgr):
    print(f"\n{YEL}E7a — pagar “lawan transaksi ternyata PT sendiri”{RST}")
    prod = rows(adm.get("/api/products?limit=1").json())[0]
    wh = rows(adm.get("/api/warehouses").json())[0]
    ext = [s for s in rows(adm.get("/api/suppliers").json())
           if not s.get("group_entity_id") and s.get("status") != "inactive"]
    check("BUKTI-MERAH: pemasok bertipe 'Entitas grup' memang ada di daftar",
          any(s.get("partner_kind") == "entity"
              for s in rows(adm.get("/api/suppliers").json())))

    body = {"supplier_id": G_SUPPLIER, "warehouse_id": wh["id"],
            "expected_date": "2026-12-01",
            "items": [{"product_id": prod["id"], "product_name": prod["name"],
                       "quantity": 5, "unit_price": 50000, "warehouse_id": wh["id"]}]}
    r = adm.post("/api/purchase-orders", json=body)
    check("PO ke badan usaha grup DITOLAK 409 + kalimat menuntun", r.status_code == 409
          and "Antar Entitas" in str(r.json().get("detail", "")), f"HTTP {r.status_code}")

    r = adm.post("/api/purchase-requisitions", json={
        "items": [{"product_id": prod["id"], "quantity": 3}],
        "preferred_supplier_id": G_SUPPLIER, "notes": "POC E7", "needed_by_date": "2026-12-01"})
    check("PR ber-pemasok badan usaha grup DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")

    # KEBOCORAN yang ditemukan sesi 2026-08-11: PR → realisasi PO menembus pagar.
    pr = adm.post("/api/purchase-requisitions", json={
        "items": [{"product_id": prod["id"], "quantity": 3}],
        "notes": "POC E7 realisasi", "needed_by_date": "2026-12-01",
        "submit_now": True}).json()
    CLEANUP["prs"].append(pr.get("id"))
    r = adm.post(f"/api/purchase-requisitions/{pr['id']}/convert-to-po",
                 json={"supplier_id": G_SUPPLIER, "warehouse_id": wh["id"]})
    check("PR → convert-to-po ke badan usaha grup DITOLAK 409 (kebocoran KSC/PO-00013)",
          r.status_code == 409, f"HTTP {r.status_code}")
    r = adm.post(f"/api/purchase-requisitions/{pr['id']}/realize-po",
                 json={"supplier_id": G_SUPPLIER, "warehouse_id": wh["id"], "line_nos": [1]})
    check("PR → realize-po ke badan usaha grup DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")

    r = adm.post("/api/purchase-orders/blanket", json={
        "supplier_id": G_SUPPLIER, "warehouse_id": wh["id"], "valid_from": "2026-08-01",
        "items": [{"product_id": prod["id"], "contract_qty": 10, "contract_price": 50000}]})
    check("Blanket PO ke badan usaha grup DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")
    r = adm.post("/api/rfqs", json={"supplier_ids": [G_SUPPLIER], "warehouse_id": wh["id"],
                                    "items": [{"product_id": prod["id"], "quantity": 5}]})
    check("RFQ mengundang badan usaha grup DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")
    r = adm.post("/api/customers", json={"name": "CV Kanda Suka", "pic_name": "x",
                                         "phone": "0812", "email": "a@b.c", "city": "Bandung",
                                         "address": "jl"})
    check("Buat PELANGGAN bernama badan usaha grup DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")
    r = adm.post("/api/suppliers", json={"name": "CV Kanda Suka", "pic_name": "x",
                                         "phone": "0812"})
    check("Buat pemasok KEMBAR badan usaha grup DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")
    r = adm.delete(f"/api/suppliers/{G_SUPPLIER}")
    check("Nonaktifkan cermin pemasok badan usaha grup DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")

    # KONTROL: pemasok LUAR tetap jalan (pagar tidak boleh menutup pekerjaan sah).
    r = adm.post("/api/purchase-requisitions", json={
        "items": [{"product_id": prod["id"], "quantity": 2}],
        "preferred_supplier_id": ext[0]["id"], "notes": "POC E7 kontrol",
        "needed_by_date": "2026-12-01"})
    if r.status_code == 200:
        CLEANUP["prs"].append(r.json().get("id"))
    check("KONTROL: PR ke pemasok LUAR tetap boleh (200)", r.status_code == 200,
          f"HTTP {r.status_code}")


def e7bc_labels(adm):
    print(f"\n{YEL}E7b/E7c — konsistensi kecil & HPP taksiran berlabel{RST}")
    rets = rows(adm.get("/api/interco/returns").json()) or []
    check("BUKTI-MERAH: ada dokumen retur antar-PT untuk diuji", len(rets) > 0,
          f"{len(rets)} dokumen")
    if rets:
        r0 = rets[0]
        check("E7b: retur antar-PT mengirim `pair_id` + `qty_total`",
              bool(r0.get("pair_id")) and r0.get("qty_total") is not None,
              f"pair_id={r0.get('pair_id')} qty_total={r0.get('qty_total')}")
    trf = [t.get("code", "") for t in (rows(adm.get("/api/transfers").json()) or [])]
    check("E7b: nomor transfer gudang ber-prefix badan usaha",
          all("/" in c for c in trf) if trf else True,
          ", ".join(trf[:4]) or "tidak ada transfer")

    rep = adm.get("/api/interco/margin-report", params={"entity_id": "all"}).json()
    t = rep.get("totals", {})
    check("E7c: identitas margin tetap utuh (margin = jual − HPP)",
          abs(float(t.get("margin", 0)) - (float(t.get("subtotal", 0))
                                          - float(t.get("cost", 0)))) < 0.05)
    # FASE E-9 — eliminasi konsolidasi menghapus LABA belum terealisasi. Bila margin
    # antar-PT NEGATIF (mis. barang yang diretur sudah dihapus-bukukan menjadi Rp 0),
    # itu RUGI nyata bagi grup dan sengaja TIDAK dieliminasi (konservatisme) — tetapi
    # wajib tampil terpisah dengan alasannya, bukan lenyap tanpa jejak.
    check("E7c: eliminasi = LABA belum terealisasi (INV-IC-03)",
          abs(float(t.get("eliminated_unrealized", 0))
              - float(t.get("unrealized_profit", 0))) < 0.05,
          f"eliminasi={t.get('eliminated_unrealized')} laba_belum_terealisasi={t.get('unrealized_profit')}")
    check("E7c: rugi belum terealisasi dilaporkan terpisah (tidak dieliminasi diam-diam)",
          (float(t.get("unrealized_loss", 0)) <= 0.05)
          or bool(t.get("loss_not_eliminated") and t.get("loss_reason")),
          f"rugi={t.get('unrealized_loss')} alasan={(t.get('loss_reason') or '')[:60]}")
    est_rows = [r for r in rep.get("rows", []) if r.get("cost_estimated")]
    check("BUKTI-MERAH: ada transaksi yang HPP-nya belum diposting", len(est_rows) > 0,
          f"{len(est_rows)} dari {len(rep.get('rows', []))}")
    if est_rows:
        r0 = est_rows[0]
        check("E7c: HPP taksiran BERLABEL + ada angka taksiran & alasannya",
              r0.get("cost_basis") in ("wac_estimate", "unknown")
              and float(r0.get("cost_estimate", 0)) >= 0
              and len(str(r0.get("cost_estimate_reason", ""))) > 20,
              f"basis={r0.get('cost_basis')} est={r0.get('cost_estimate')}")
        check("E7c: total ikut jujur (`estimated_doc_count` > 0 & margin taksiran ada)",
              int(t.get("estimated_doc_count", 0)) > 0 and "margin_estimate" in t)


def e7d_internal_request(adm, sales):
    print(f"\n{YEL}E7d — Permintaan Internal (jalur sales yang dulu buntu){RST}")
    board = rows(sales.get("/api/inventory/status-board").json()) or []
    cand = [b for b in board if float(b.get("other_entities_available") or 0) > 0]
    check("BUKTI-MERAH: papan stok memberi isyarat 'tersedia di badan usaha lain'",
          len(cand) > 0, f"{len(cand)} barang")
    if not cand:
        return
    pid = cand[0]["product_id"]
    r = sales.post("/api/internal-requests", json={
        "items": [{"product_id": pid, "quantity": 1}],
        "reason": "POC E7d — stok sendiri habis"})
    ok = check("Sales BOLEH mengajukan permintaan internal (nomor <ENT>/PIN-#####)",
               r.status_code == 200 and "/PIN-" in str(r.json().get("number", "")),
               f"HTTP {r.status_code} {r.json().get('number', '')}")
    if not ok:
        return
    req = r.json()
    CLEANUP["requests"].append(req["id"])
    check("Cuplikan bukti ketersediaan tersimpan TANPA rincian per badan usaha (E5.1)",
          bool(req.get("availability_snapshot"))
          and "by_entity" not in req["availability_snapshot"][0])
    r = sales.post("/api/internal-requests", json={
        "items": [{"product_id": pid, "quantity": 1}], "reason": "POC pilih sumber",
        "source_entity_id": ENT_B})
    check("Sales DITOLAK memilih badan usaha sumber (keputusan E5.1)",
          r.status_code == 400, f"HTTP {r.status_code}")
    r = sales.get(f"/api/internal-requests/{req['id']}/sources")
    check("Sales 403 di rincian stok badan usaha lain", r.status_code == 403,
          f"HTTP {r.status_code}")
    r = sales.post(f"/api/internal-requests/{req['id']}/convert",
                   json={"source_entity_id": ENT_B})
    check("Sales 403 mengubah permintaan menjadi transaksi antar-PT", r.status_code == 403,
          f"HTTP {r.status_code}")

    s = adm.get(f"/api/internal-requests/{req['id']}/sources")
    check("Admin melihat kandidat sumber + kesiapan harga internalnya",
          s.status_code == 200 and isinstance(s.json().get("candidates"), list),
          f"{len(s.json().get('candidates', []))} kandidat")
    cnd = [c for c in s.json().get("candidates", []) if c.get("can_fulfill")]
    if not cnd:
        check("Kandidat siap dipenuhi ADA (butuh kontrak internal arah ini)", False,
              "tidak ada kandidat siap — periksa kontrak internal demo")
        return
    r = adm.post(f"/api/internal-requests/{req['id']}/convert",
                 json={"source_entity_id": cnd[0]["entity_id"], "submit_now": False})
    ok = check("Admin mengubahnya menjadi transaksi antar-PT (dokumen kembar)",
               r.status_code == 200, f"HTTP {r.status_code}")
    if ok:
        d = r.json()
        # Dokumen kembar ini adalah DRAF (submit_now=False) → belum berjurnal dan
        # belum menggeser stok, jadi ia WAJIB dibersihkan. Sebelum ini ia
        # tertinggal setiap kali gate berjalan (KANDA/IC-##### menumpuk) dan
        # recompute saldo arah baliknya MENGHAPUS utang nyata pasangan PT itu —
        # akar KN-G6-ICA-CLOBBER.
        CLEANUP["interco_pairs"].append(d["interco"]["seller"]["pair_id"])
        check("Transaksi antar-PT membawa asal permintaannya (`source_request_number`)",
              d["interco"]["buyer"].get("source_request_number") == req["number"])
        check("Permintaan tertaut dua arah ke transaksinya (mesin G-4)",
              any(x.get("rel") == "fulfilled_by"
                  for x in (d["request"].get("refs") or [])))


def e7e_group_cash(adm):
    print(f"\n{YEL}E7e — kas tingkat grup DIHAPUS{RST}")
    r = adm.post("/api/cash-transactions", json={
        "cash_type": "kas_besar", "direction": "in", "amount": 1000, "category": "modal",
        "description": "POC E7e", "entity_id": "all"})
    check("Transaksi kas ber-`entity_id=all` DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")
    r = adm.post("/api/bank-accounts", json={"name": "POC Rekening Grup",
                                             "account_type": "cash", "entity_id": "all"})
    check("Rekening ber-`entity_id=all` DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")
    s = adm.get("/api/cash-transactions/summary").json()
    pend = s.get("group_cash_pending", {})
    check("Ringkasan kas melaporkan sisa kas tingkat grup (jujur, bukan disembunyikan)",
          isinstance(pend, dict) and "transactions" in pend, str(pend))
    check("Data demo bersih dari kas tingkat grup", int(pend.get("transactions", 1)) == 0
          and int(pend.get("accounts", 1)) == 0, str(pend))
    # KONTROL: kas milik badan usaha tetap boleh
    r = adm.post("/api/cash-transactions", json={
        "cash_type": "kas_besar", "direction": "in", "amount": 1000, "category": "modal",
        "description": "POC E7e kontrol"})
    ok = check("KONTROL: kas milik satu badan usaha tetap boleh (200)",
               r.status_code == 200, f"HTTP {r.status_code}")
    if ok:
        adm.post(f"/api/cash-transactions/{r.json()['id']}/void")


def e7f_loans(adm):
    print(f"\n{YEL}E7f — pinjaman uang antar-PT{RST}")
    # Data lama boleh ada (pinjaman berjalan): yang diuji adalah SELISIHNYA, bukan
    # angka mutlak — kalau tidak, POC memerah hanya karena demo punya pinjaman lain.
    base = float(adm.get(f"/api/interco/non-trade/{ENT_A}/{ENT_B}").json()
                 .get("loan_outstanding", 0))
    r = adm.post("/api/interco/loans", json={
        "lender_entity_id": ENT_A, "borrower_entity_id": ENT_A, "principal": 1000,
        "purpose": "POC pagar pasangan sama"})
    check("Pinjaman ke DIRI SENDIRI ditolak", r.status_code == 400, f"HTTP {r.status_code}")
    r = adm.post("/api/interco/loans", json={
        "lender_entity_id": ENT_A, "borrower_entity_id": ENT_B, "principal": 5000000,
        "purpose": "abc"})
    check("Tujuan pinjaman kosong/pendek ditolak", r.status_code == 400,
          f"HTTP {r.status_code}")

    r = adm.post("/api/interco/loans", json={
        "lender_entity_id": ENT_A, "borrower_entity_id": ENT_B, "principal": 7500000,
        "purpose": "POC E7f — menalangi kebutuhan modal kerja"})
    ok = check("Pinjaman dibuat sebagai DOKUMEN KEMBAR (dua nomor per badan usaha)",
               r.status_code == 200 and r.json()["lender"]["number"] != r.json()["borrower"]["number"],
               f"HTTP {r.status_code}")
    if not ok:
        return
    pair = r.json()
    CLEANUP["loans"].append(pair["pair_id"])
    lid = pair["lender"]["id"]
    r = adm.post(f"/api/interco/loans/{lid}/disburse")
    ok = check("Pencairan: status `disbursed` & sisa = pokok", r.status_code == 200
               and r.json()["lender"]["status"] == "disbursed", f"HTTP {r.status_code}")
    if not ok:
        return
    nt = adm.get(f"/api/interco/non-trade/{ENT_A}/{ENT_B}").json()
    check("Saldo NON-DAGANG pasangan PT naik sebesar pinjaman",
          abs(float(nt.get("loan_outstanding", 0)) - (base + 7500000)) < 0.05,
          f"{nt.get('loan_outstanding')} (awal {base})")
    r = adm.post(f"/api/interco/loans/{lid}/repay", json={"amount": 7500000})
    check("Angsuran penuh → status `repaid` & sisa 0", r.status_code == 200
          and r.json()["lender"]["status"] == "repaid"
          and float(r.json()["lender"]["outstanding"]) == 0.0, f"HTTP {r.status_code}")
    r = adm.post(f"/api/interco/loans/{lid}/repay", json={"amount": 1000})
    check("Angsuran melebihi sisa ditolak", r.status_code == 400, f"HTTP {r.status_code}")
    nt2 = adm.get(f"/api/interco/non-trade/{ENT_A}/{ENT_B}").json()
    check("Setelah lunas, saldo non-dagang pinjaman kembali ke angka awal",
          abs(float(nt2.get("loan_outstanding", -1)) - base) < 0.05,
          f"{nt2.get('loan_outstanding')} (awal {base})")


def e7g_asset_transfer(adm):
    print(f"\n{YEL}E7g — pindah aset tetap antar-PT{RST}")
    assets = rows(adm.get("/api/fixed-assets").json()) or []
    mine = [a for a in assets if a.get("entity_id") == ENT_A and a.get("status") == "active"]
    if not mine:
        # POC menyiapkan bahan ujinya sendiri (aset demo mungkin sudah dipindah semua).
        r = adm.post("/api/fixed-assets", json={
            "name": "POC E7g Mesin Uji", "category": "Peralatan & Mesin",
            "acquisition_cost": 60000000, "useful_life_months": 60,
            "salvage_value": 5000000, "entity_id": ENT_A,
            "acquisition_date": "2026-01-15", "notes": "dibuat POC E-7"})
        if r.status_code == 200:
            mine = [r.json()]
    check("BUKTI-MERAH: ada aset tetap aktif untuk dipindah", len(mine) > 0,
          f"{len(mine)} aset")
    if not mine:
        return
    a = mine[0]
    r = adm.post(f"/api/fixed-assets/{a['id']}/transfer",
                 json={"to_entity_id": ENT_B, "reason": "abc"})
    check("Alasan pindah kosong/pendek ditolak", r.status_code == 400, f"HTTP {r.status_code}")
    r = adm.post(f"/api/fixed-assets/{a['id']}/transfer",
                 json={"to_entity_id": ENT_A, "reason": "POC pagar entitas sama"})
    check("Pindah ke badan usaha SENDIRI ditolak", r.status_code == 400,
          f"HTTP {r.status_code}")

    price = round(float(a["book_value"]) + 1000000, 2)
    r = adm.post(f"/api/fixed-assets/{a['id']}/transfer", json={
        "to_entity_id": ENT_B, "transfer_price": price,
        "reason": "POC E7g — aset dipakai badan usaha lain"})
    ok = check("Pindah aset berhasil & lahir aset baru di badan usaha penerima",
               r.status_code == 200 and r.json()["new_asset"]["entity_id"] == ENT_B,
               f"HTTP {r.status_code}")
    if not ok:
        return
    d = r.json()
    check("Masa manfaat yang pindah adalah SISA (bukan mulai dari awal)",
          int(d["new_asset"]["useful_life_months"]) <= int(a["useful_life_months"])
          and int(d["new_asset"]["useful_life_months"]) > 0,
          f"{d['new_asset']['useful_life_months']} dari {a['useful_life_months']} bulan")
    check("Harga pindah di atas nilai buku → laba pindah tercatat",
          float(d["gain"]) > 0, f"laba {d['gain']}")
    nt = adm.get(f"/api/interco/non-trade/{ENT_A}/{ENT_B}").json()
    check("Utang antar-PT atas aset masuk saldo non-dagang",
          float(nt.get("asset_transfer_outstanding", 0)) >= price,
          str(nt.get("asset_transfer_outstanding")))
    base_asset = float(nt.get("asset_transfer_outstanding", 0)) - price
    r = adm.post(f"/api/fixed-assets/{a['id']}/transfer/settle", json={"note": "POC"})
    check("Pembayaran pindah aset memindahkan uang di kedua buku", r.status_code == 200
          and len(r.json().get("cash", [])) == 2, f"HTTP {r.status_code}")
    nt2 = adm.get(f"/api/interco/non-trade/{ENT_A}/{ENT_B}").json()
    check("Setelah dibayar, saldo non-dagang aset kembali ke angka awal",
          abs(float(nt2.get("asset_transfer_outstanding", -1)) - base_asset) < 0.05,
          f"{nt2.get('asset_transfer_outstanding')} (awal {base_asset})")
    r = adm.post(f"/api/fixed-assets/{a['id']}/transfer",
                 json={"to_entity_id": ENT_B, "reason": "POC pindah dua kali"})
    check("Aset yang sudah dipindah tidak bisa dipindah lagi", r.status_code == 400,
          f"HTTP {r.status_code}")

    # ── E7g-2 (cacat NYATA yang ditemukan lewat layar, ditutup sesi penutup E-7) ──
    # Ringkasan aset dulu memakai aturan "semua yang bukan `disposed` = aktif", sehingga
    # buku PENJUAL tetap mengaku memegang aset yang hak & fisiknya sudah pindah
    # (Rp 420 jt "Nilai Perolehan" padahal nilai buku barisnya sudah 0).
    sm = adm.get(f"/api/fixed-assets/summary?entity_id={ENT_A}").json()
    ls = rows(adm.get(f"/api/fixed-assets?entity_id={ENT_A}").json()) or []
    still_owned = [x for x in ls if x.get("status") not in ("disposed", "transferred")]
    gross_owned = round(sum(float(x.get("acquisition_cost", 0) or 0) for x in still_owned), 2)
    check("Ringkasan aset TIDAK mengaku memiliki aset yang sudah pindah PT",
          abs(float(sm.get("gross_cost", -1)) - gross_owned) < 0.05,
          f"gross {sm.get('gross_cost')} == milik sendiri {gross_owned}")
    check("Ringkasan aset melaporkan jumlah & nilai aset yang pindah (jujur, terlihat)",
          int(sm.get("transferred", 0)) >= 1 and float(sm.get("transferred_book_value", 0)) > 0,
          f"{sm.get('transferred')} aset · {sm.get('transferred_book_value')}")
    check("Aset yang pindah TIDAK ikut dihitung sebagai aset dimiliki",
          int(sm.get("active", -1)) == len(still_owned),
          f"active {sm.get('active')} == {len(still_owned)}")


def _residue_baseline():
    """INV-GATE-01 — sidik jari jejak SEBELUM POC (audit & notifikasi).

    POC ini melakukan aksi bisnis NYATA lewat endpoint produksi, jadi ia otomatis
    menulis jejak audit & notifikasi. Jejak itu tidak boleh tertinggal (gate
    anti-residu memeriksanya), karena kalau tertinggal, layar audit demo terisi
    baris uji yang tidak pernah dilakukan siapa pun.
    """
    from pymongo import MongoClient
    db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "test_database")]
    return db, ({d["id"] for d in db.audit_logs.find({}, {"_id": 0, "id": 1})},
                {d["id"] for d in db.notifications.find({}, {"_id": 0, "id": 1})},
                {d["id"] for d in db.interco_transactions.find({}, {"_id": 0, "id": 1})})


def _residue_cleanup(db, before):
    audit_ids, notif_ids, ict_ids = before
    # Dokumen kembar antar-PT dari E7d adalah DRAF: belum berjurnal & belum
    # menggeser stok, jadi menghapusnya tidak menghilangkan jejak uang apa pun.
    # Sebelumnya ia tertinggal permanen setiap kali gate berjalan — dan residu
    # itulah yang memicu KN-G6-ICA-CLOBBER (saldo dua arah saling menimpa).
    ict = db.interco_transactions.delete_many(
        {"id": {"$nin": list(ict_ids)}, "status": "draft"}).deleted_count if ict_ids else 0
    left_i = db.interco_transactions.count_documents({"id": {"$nin": list(ict_ids)}})
    check("CLEANUP (INV-GATE-01): nol residu transaksi antar-PT (draf E7d dihapus)",
          left_i == 0, f"dihapus {ict} draf · sisa {left_i}")
    a = db.audit_logs.delete_many(
        {"id": {"$nin": list(audit_ids)}}).deleted_count if audit_ids else 0
    n = db.notifications.delete_many(
        {"id": {"$nin": list(notif_ids)}}).deleted_count if notif_ids else 0
    left_a = db.audit_logs.count_documents({"id": {"$nin": list(audit_ids)}})
    left_n = db.notifications.count_documents({"id": {"$nin": list(notif_ids)}})
    check("CLEANUP (INV-GATE-01): nol residu jejak audit & notifikasi",
          left_a == 0 and left_n == 0,
          f"dihapus audit={a} notifikasi={n} · sisa {left_a}/{left_n}")


def cleanup(adm):
    """Self-cleanup: dokumen uji yang masih bisa dibatalkan dibersihkan."""
    n = 0
    for rid in CLEANUP["requests"]:
        try:
            if adm.post(f"/api/internal-requests/{rid}/cancel",
                        json={"reason": "pembersihan POC"}).status_code == 200:
                n += 1
        except Exception:  # noqa: BLE001
            pass
    for pid in CLEANUP["prs"]:
        try:
            if pid and adm.post(f"/api/purchase-requisitions/{pid}/cancel").status_code == 200:
                n += 1
        except Exception:  # noqa: BLE001
            pass
    print(f"\n  (self-cleanup: {n} dokumen uji dibatalkan · pinjaman & pindah aset uji "
          f"SENGAJA ditinggalkan karena uangnya sudah berpindah — append-only)")


def main() -> int:
    print("=" * 78)
    print("  POC FASE E-7 — ANTAR-ENTITAS (pagar · label · permintaan internal · "
          "kas · pinjaman · aset)")
    print("=" * 78)
    db, residue_before = _residue_baseline()
    adm = client("admin@kainnusantara.id")
    mgr = client("manager@kainnusantara.id")
    sales = client("sales@kainnusantara.id")
    try:
        e7a_group_partner_guard(adm, mgr)
        e7bc_labels(adm)
        e7d_internal_request(adm, sales)
        e7e_group_cash(adm)
        e7f_loans(adm)
        e7g_asset_transfer(adm)
    finally:
        cleanup(adm)
        for c in (adm, mgr, sales):
            c.close()
        _residue_cleanup(db, residue_before)

    ok = sum(1 for _, p, _ in RESULTS if p)
    bad = [n for n, p, _ in RESULTS if not p]
    print("\n" + "=" * 78)
    print(f"  HASIL: {GREEN}{ok} PASS{RST} · {RED}{len(bad)} FAIL{RST} "
          f"dari {len(RESULTS)} pemeriksaan")
    for n in bad:
        print(f"    {RED}✗{RST} {n}")
    print("=" * 78)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
