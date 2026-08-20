#!/usr/bin/env python3
"""
verify_data_integrity.py — Kain Nusantara (KN3) POST-SEED INTEGRITY GATE
========================================================================
"Penjaga yang hilang". Menangkap kelas bug yang TERUS berulang walau RC-1
sudah didokumentasikan:

  L1. Seed↔App collection DRIFT   (seed menulis nama legacy, app baca kanonik)
  L2. Seed GAP                    (koleksi yang dibaca app tidak pernah diisi)
  L3. Cross-endpoint INTENT drift (KPI dashboard != sumbernya; stats != list)
  L4. Invarian akuntansi stok     (konservasi qty; total order == Σ subtotal)

KENAPA gate ini ada (pelajaran CASE_STUDY_INTENT_DRIFT torado60):
  • Validasi di DB dev yang KOTOR menutupi drift → gate ini WAJIB dijalankan di
    DB BERSIH sesudah seed_reset (lihat scripts/seed_reset.sh blok [GATE]).
  • "HTTP 200" / "service running" != benar → gate ini cek NILAI & invarian
    LINTAS-ENDPOINT, bukan status code.
  • Tambah fitur ⇒ tambah Concept(...) di sini (kanonik + legacy-harus-kosong).

Kontrak KN3 yang DIVERIFIKASI (bukan diasumsikan):
  • Auth: POST /api/auth/login {email,password} → {"token": "...", "user": {...}}
    (field token = "token", BUKAN access_token; respons LANGSUNG tanpa envelope).
  • List endpoint mengembalikan ARRAY langsung; dashboard objek langsung.
  • inventory_balances: on_hand == available + reserved + blocked + picked + in_transit.

Usage:
    cd /app && python scripts/verify_data_integrity.py
Exit 0 = semua invarian valid. != 0 = INTEGRITY VIOLATION (pakai sbg gate CI/seed).
"""
import asyncio
import re
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# ── Shared bootstrap (M4): SETIAP entrypoint load env dengan cara yang SAMA,
#    kalau tidak, script diam-diam menatap DB yang salah (bug D1 di Torado). ─────
ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "kain_nusantara")

# API base: utamakan localhost (gate dijalankan di host yang sama dgn backend)
API = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/")
ADMIN_EMAIL = os.environ.get("KN_ADMIN_EMAIL", "admin@kainnusantara.id")
ADMIN_PASS = os.environ.get("KN_ADMIN_PASS", "demo12345")


@dataclass
class Concept:
    """Satu konsep bisnis -> SATU koleksi kanonik yang dibaca app, plus nama
    legacy yang TIDAK BOLEH berisi data (drift aktif) setelah seed diperbaiki."""
    name: str
    canonical: str
    must_have_data: bool = True
    legacy_must_be_empty: list = field(default_factory=list)


# Kontrak executable KN3. Tambah fitur => tambah Concept di sini.
CONCEPTS = [
    Concept("users", "users", True, ["staff", "employees", "operator"]),
    Concept("products", "products", True, ["items", "goods", "materials", "kain"]),
    Concept("customers", "customers", True, ["clients", "buyers"]),
    Concept("warehouses", "warehouses", True, ["gudang", "depot"]),
    Concept("uoms", "uoms", True, ["satuan", "unit_ukur"]),
    Concept("inventory_balances", "inventory_balances", True, ["stock", "stok", "stock_balances"]),
    Concept("inventory_movements", "inventory_movements", True, ["stock_movements", "stock_history"]),
    Concept("inventory_rolls", "inventory_rolls", True, ["stock_units", "rolls", "fabric_rolls"]),
    Concept("system_settings", "system_settings", True, ["settings", "config", "configuration"]),
    Concept("payment_terms", "payment_terms", True, ["terms", "payment_term"]),
    Concept("approval_rules", "approval_rules", True, ["approval_matrix", "approvals"]),
    Concept("sales_orders", "sales_orders", True, ["orders", "penjualan", "customer_orders"]),
    Concept("purchase_orders", "purchase_orders", True, ["po", "pos", "pembelian"]),
    # Fase 3 — Procurement (Supplier Master + Pengelolaan Kas)
    Concept("suppliers", "suppliers", True, ["vendor", "vendors", "pemasok"]),
    Concept("cash_transactions", "cash_transactions", True, ["kas", "petty_cash"]),
    # Depth #1 — Retur Beli (Purchase Return / Nota Debit)
    Concept("purchase_returns", "purchase_returns", True, ["retur_beli", "debit_notes", "po_returns"]),
    # Depth #2 — Purchase Requisition (Hulu Procurement)
    Concept("purchase_requisitions", "purchase_requisitions", True, ["requisitions", "pr_list", "permintaan_pembelian"]),
    Concept("wms_tasks", "wms_tasks", True, ["inbound_tasks", "outbound_tasks", "receiving_tasks"]),
    Concept("document_templates", "document_templates", True, ["templates"]),
    Concept("permission_settings", "permission_settings", True, []),
    # Boleh kosong di seed minimal (transaksional/opsional) — must_have_data=False
    Concept("warehouse_transfers", "warehouse_transfers", False, ["transfers", "stock_transfer"]),
    Concept("cycle_count_sessions", "cycle_count_sessions", False, ["stock_count", "stock_opname"]),
    Concept("invoices", "invoices", False, ["bills", "tagihan"]),
    Concept("audit_logs", "audit_logs", False, ["audit_log", "audits"]),
]

results = {"pass": 0, "fail": 0, "warn": 0}


def line(tag, color, msg, detail=""):
    print(f"  {color}[{tag}]{X} {msg}" + (f"  {color}{detail}{X}" if detail else ""))


async def layer1_collection_reconciliation(db):
    print(f"\n{C}{B}L1/L2 — Rekonsiliasi koleksi Seed↔App (butuh DB clean-seed){X}")
    for c in CONCEPTS:
        canon = await db[c.canonical].count_documents({})
        if c.must_have_data and canon == 0:
            results["fail"] += 1
            line("FAIL", R, f"{c.name}: kanonik '{c.canonical}' KOSONG",
                 "→ seed GAP atau DRIFT (data masuk ke koleksi legacy?)")
        else:
            results["pass"] += 1
            line("PASS", G, f"{c.name}: '{c.canonical}' berisi {canon} dok")
        for legacy in c.legacy_must_be_empty:
            n = await db[legacy].count_documents({})
            if n > 0:
                results["fail"] += 1
                line("FAIL", R, f"{c.name}: legacy '{legacy}' masih berisi {n} dok",
                     "→ DRIFT AKTIF: seed/app menulis koleksi yang salah")
            else:
                results["pass"] += 1


async def layer2_db_invariants(db):
    """Invarian level-DB (tidak butuh API) — konservasi stok & total order."""
    print(f"\n{C}{B}L4 — Invarian akuntansi (level DB){X}")
    # INV-DB1: konservasi stok per balance (KN_15 §3.4 — on_hand = Σ bucket fisik)
    bals = await db.inventory_balances.find({}, {"_id": 0}).to_list(5000)
    cons_viol, neg_viol = [], []
    PHYS = ["available_qty", "reserved_qty", "committed_qty", "picked_qty",
            "packed_qty", "quarantine_qty", "blocked_qty", "damaged_qty"]
    for b in bals:
        oh = float(b.get("on_hand_qty", 0))
        phys_sum = sum(float(b.get(k, 0) or 0) for k in PHYS)
        # fallback legacy (in_transit_qty pernah masuk on_hand di model lama)
        if abs(oh - phys_sum) > 0.01:
            cons_viol.append(b.get("id"))
        bucket_vals = [float(b.get(k, 0) or 0) for k in PHYS] + [oh]
        if min(bucket_vals) < -0.01:
            neg_viol.append(b.get("id"))
    if cons_viol:
        results["fail"] += 1
        line("FAIL", R, f"stok: {len(cons_viol)} balance melanggar konservasi",
             "on_hand != Σ(available+reserved+committed+picked+packed+quarantine+blocked+damaged)")
    else:
        results["pass"] += 1
        line("PASS", G, f"stok: {len(bals)} balance — konservasi qty (bucket fisik) terpenuhi")
    if neg_viol:
        results["fail"] += 1
        line("FAIL", R, f"stok: {len(neg_viol)} balance punya bucket NEGATIF")
    else:
        results["pass"] += 1
        line("PASS", G, "stok: tidak ada qty negatif")

    # INV-DB2: sales_order.total_amount == Σ items.subtotal & subtotal == price*qty
    orders = await db.sales_orders.find({}, {"_id": 0}).to_list(2000)
    tot_viol, sub_viol = [], []
    for o in orders:
        items = o.get("items", [])
        ssum = sum(float(i.get("subtotal", 0)) for i in items)
        if abs(ssum - float(o.get("total_amount", 0))) > 0.01:
            tot_viol.append(o.get("number", o.get("id")))
        for i in items:
            if abs(float(i.get("subtotal", 0)) - float(i.get("price", 0)) * float(i.get("quantity", 0))) > 0.01:
                sub_viol.append(o.get("number", o.get("id")))
                break
    if tot_viol:
        results["fail"] += 1
        line("FAIL", R, f"order: {len(tot_viol)} total_amount != Σ subtotal", str(tot_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"order: {len(orders)} order — total_amount == Σ subtotal")
    if sub_viol:
        results["fail"] += 1
        line("FAIL", R, f"order: {len(sub_viol)} item subtotal != price×qty", str(sub_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "order: subtotal == price × quantity")

    # INV-DB3 (Fase 1B): konsistensi pricing diskon+PPN untuk order ber-breakdown.
    #   - net_subtotal == total_amount − discount_total (≥0, ≤ total)
    #   - excluded: ppn == round(dpp×rate/100); grand == net_subtotal + ppn
    #   - included: grand == net_subtotal; dpp + ppn == net_subtotal
    #   - line_total item == subtotal − discount_amount; 0 ≤ discount_percent ≤ 100
    tax_viol, disc_viol, line_viol = [], [], []
    n_breakdown = 0
    for o in orders:
        if o.get("grand_total") is None:
            continue
        n_breakdown += 1
        num = o.get("number", o.get("id"))
        total = float(o.get("total_amount", 0) or 0)
        disc_total = float(o.get("discount_total", 0) or 0)
        net = float(o.get("net_subtotal", 0) or 0)
        dpp = float(o.get("dpp", 0) or 0)
        ppn = float(o.get("ppn_amount", 0) or 0)
        grand = float(o.get("grand_total", 0) or 0)
        rate = float(o.get("ppn_rate", 0) or 0)
        mode = o.get("ppn_mode", "excluded")
        if disc_total < -0.01 or disc_total > total + 0.01:
            disc_viol.append(num)
        if abs(net - round(total - disc_total, 2)) > 0.5:
            disc_viol.append(num)
        if mode == "included":
            if abs(grand - net) > 0.5 or abs((dpp + ppn) - net) > 0.5:
                tax_viol.append(num)
        else:  # excluded
            exp_ppn = round(dpp * rate / 100.0, 2)
            if abs(ppn - exp_ppn) > 0.5 or abs(grand - round(net + ppn, 2)) > 0.5:
                tax_viol.append(num)
        for it in o.get("items", []):
            st = float(it.get("subtotal", 0) or 0)
            da = float(it.get("discount_amount", 0) or 0)
            lt = float(it.get("line_total", st) or 0)
            dp = float(it.get("discount_percent", 0) or 0)
            if abs(lt - round(st - da, 2)) > 0.5 or dp < -0.01 or dp > 100.01:
                line_viol.append(num)
                break
    if disc_viol:
        results["fail"] += 1
        line("FAIL", R, f"order: {len(set(disc_viol))} order diskon tak konsisten (net != total−diskon)", str(list(set(disc_viol))[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"order: {n_breakdown} order — net_subtotal == total_amount − discount_total")
    if tax_viol:
        results["fail"] += 1
        line("FAIL", R, f"order: {len(set(tax_viol))} order PPN/grand_total tak konsisten", str(list(set(tax_viol))[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"order: {n_breakdown} order — PPN & grand_total konsisten (mode excluded/included)")
    if line_viol:
        results["fail"] += 1
        line("FAIL", R, f"order: {len(set(line_viol))} order line_total/diskon item tak konsisten", str(list(set(line_viol))[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "order: line_total == subtotal − discount_amount (0 ≤ disc% ≤ 100)")

    # INV-DB-PO (P0-1): konsistensi pricing untuk PURCHASE ORDER.
    #   PERBAIKAN false-PASS (blindspot): dulu SEMUA PO tanpa `net_subtotal` di-`continue`
    #   → 0 PO tervalidasi tapi tetap PASS (hijau palsu, RC-10). Kini invarian DASAR
    #   (total_amount == Σ price×qty · item subtotal == price×qty) divalidasi untuk
    #   SEMUA PO (subtotal legacy yang hilang di-fallback ke price×qty). Invarian
    #   BREAKDOWN (diskon+PPN Masukan) tetap hanya untuk PO ber-`net_subtotal`, TETAPI
    #   jumlah tervalidasi (`n_po_breakdown`) dilaporkan agar 0-validasi tak menyamar hijau.
    pos = await db.purchase_orders.find({}, {"_id": 0}).to_list(2000)
    po_tot_viol, po_sub_viol, po_tax_viol, po_disc_viol, po_line_viol = [], [], [], [], []
    n_po = len(pos)
    n_po_breakdown = 0
    for o in pos:
        num = o.get("po_number", o.get("id"))
        items = o.get("items", [])
        # DASAR (SEMUA PO): total_amount == Σ subtotal & subtotal item == price×qty.
        #   Fallback basis = price×qty bila subtotal item belum tersimpan (PO legacy).
        ssum = 0.0
        for i in items:
            expected = round(float(i.get("price", 0) or 0) * float(i.get("quantity", 0) or 0), 2)
            ssum += expected
            stored_sub = i.get("subtotal")
            if stored_sub is not None and abs(float(stored_sub or 0) - expected) > 0.01:
                po_sub_viol.append(num)
        ssum = round(ssum, 2)
        stored_total = o.get("total_amount")
        total = float(stored_total or 0) if stored_total is not None else ssum
        if abs(ssum - total) > 0.01:
            po_tot_viol.append(num)
        # BREAKDOWN (hanya PO ber-net_subtotal): diskon + PPN Masukan + line_total.
        if o.get("net_subtotal") is None:
            continue
        n_po_breakdown += 1
        disc_total = float(o.get("discount_total", 0) or 0)
        net = float(o.get("net_subtotal", 0) or 0)
        dpp = float(o.get("dpp", 0) or 0)
        ppn = float(o.get("ppn_amount", 0) or 0)
        grand = float(o.get("grand_total", 0) or 0)
        rate = float(o.get("ppn_rate", 0) or 0)
        mode = o.get("ppn_mode", "excluded")
        if disc_total < -0.01 or disc_total > total + 0.01:
            po_disc_viol.append(num)
        if abs(net - round(total - disc_total, 2)) > 0.5:
            po_disc_viol.append(num)
        if mode == "included":
            if abs(grand - net) > 0.5 or abs((dpp + ppn) - net) > 0.5:
                po_tax_viol.append(num)
        else:  # excluded
            exp_ppn = round(dpp * rate / 100.0, 2)
            if abs(ppn - exp_ppn) > 0.5 or abs(grand - round(net + ppn, 2)) > 0.5:
                po_tax_viol.append(num)
        for it in items:
            st = float(it.get("subtotal", 0) or 0)
            da = float(it.get("discount_amount", 0) or 0)
            lt = float(it.get("line_total", st) or 0)
            dp = float(it.get("discount_percent", 0) or 0)
            if abs(lt - round(st - da, 2)) > 0.5 or dp < -0.01 or dp > 100.01:
                po_line_viol.append(num)
                break
    # INV-DB-PO-S1 (audit #071): setiap PO WAJIB persist field total kanonik
    #   (grand_total ATAU total_amount). Mencegah regresi schema-drift (S1) di mana
    #   nilai finansial hanya hidup di sub-objek computed dan null di top-level.
    po_missing_total = [o.get("po_number", o.get("id")) for o in pos
                        if o.get("grand_total") is None and o.get("total_amount") is None]
    if po_missing_total:
        results["fail"] += 1
        line("FAIL", R, f"PO: {len(po_missing_total)} PO tanpa field total kanonik (grand_total & total_amount null — S1)", str(po_missing_total[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"PO: {n_po} PO — field total kanonik tersimpan (grand_total/total_amount, anti schema-drift S1)")
    if po_tot_viol:
        results["fail"] += 1
        line("FAIL", R, f"PO: {len(set(po_tot_viol))} total_amount != Σ subtotal", str(list(set(po_tot_viol))[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"PO: {n_po} PO (semua) — total_amount == Σ subtotal · {n_po_breakdown} ber-breakdown")
    if po_sub_viol:
        results["fail"] += 1
        line("FAIL", R, f"PO: {len(set(po_sub_viol))} item subtotal != price×qty", str(list(set(po_sub_viol))[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "PO: subtotal == price × quantity")
    if po_disc_viol:
        results["fail"] += 1
        line("FAIL", R, f"PO: {len(set(po_disc_viol))} PO diskon tak konsisten (net != total−diskon)", str(list(set(po_disc_viol))[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"PO: {n_po_breakdown} PO — net_subtotal == total_amount − discount_total")
    if po_tax_viol:
        results["fail"] += 1
        line("FAIL", R, f"PO: {len(set(po_tax_viol))} PO PPN/grand_total tak konsisten", str(list(set(po_tax_viol))[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"PO: {n_po_breakdown} PO — PPN Masukan & grand_total konsisten")
    if po_line_viol:
        results["fail"] += 1
        line("FAIL", R, f"PO: {len(set(po_line_viol))} PO line_total/diskon item tak konsisten", str(list(set(po_line_viol))[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "PO: line_total == subtotal − discount_amount (0 ≤ disc% ≤ 100)")



async def _login(client):
    r = await client.post(f"{API}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    d = r.json()
    # KN3: token field = "token" (respons langsung, tanpa envelope)
    return d.get("token") or (d.get("data") or {}).get("token")


async def layer3_intent_invariants():
    print(f"\n{C}{B}L3 — Invarian INTENT lintas-endpoint (KPI dashboard == sumber data){X}")
    try:
        import httpx
    except ImportError:
        os.system("pip install httpx -q"); import httpx
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tok = await _login(client)
        if not tok:
            results["fail"] += 1
            line("FAIL", R, "login gagal — invarian API dilewati"); return
        h = {"Authorization": f"Bearer {tok}"}

        async def get(path):
            r = await client.get(f"{API}{path}", headers=h, timeout=25)
            return r.json()

        # INV-1: dashboard.metrics.products == jumlah GET /products
        try:
            dash = await get("/api/dashboard")
            metrics = dash.get("metrics", {})
            prods = await get("/api/products")
            n_prod = len(prods) if isinstance(prods, list) else len(prods.get("items", []))
            if metrics.get("products") == n_prod:
                results["pass"] += 1
                line("PASS", G, f"dashboard: products KPI {metrics.get('products')} == /products {n_prod}")
            else:
                results["fail"] += 1
                line("FAIL", R, f"dashboard: products {metrics.get('products')} != /products {n_prod}",
                     "→ KPI dan list baca sumber berbeda")
        except Exception as e:
            results["fail"] += 1; line("FAIL", R, f"invarian products GAGAL/error (bukan di-skip): {e}")

        # INV-2: dashboard available_qty == Σ /inventory/balances available_qty
        try:
            dash = await get("/api/dashboard")
            kpi_avail = round(float(dash.get("metrics", {}).get("available_qty", 0)), 2)
            bals = await get("/api/inventory/balances")
            bal_list = bals if isinstance(bals, list) else bals.get("items", [])
            sum_avail = round(sum(float(b.get("available_qty", 0)) for b in bal_list), 2)
            if abs(kpi_avail - sum_avail) <= 0.5:
                results["pass"] += 1
                line("PASS", G, f"dashboard: available KPI {kpi_avail} == Σbalances {sum_avail}")
            else:
                results["fail"] += 1
                line("FAIL", R, f"dashboard: available {kpi_avail} != Σbalances {sum_avail}",
                     "→ KPI stok dan ledger stok tidak sinkron")
        except Exception as e:
            results["fail"] += 1; line("FAIL", R, f"invarian available_qty GAGAL/error: {e}")

        # INV-3: dashboard reserved_qty == Σ balances reserved_qty
        try:
            dash = await get("/api/dashboard")
            kpi_res = round(float(dash.get("metrics", {}).get("reserved_qty", 0)), 2)
            bals = await get("/api/inventory/balances")
            bal_list = bals if isinstance(bals, list) else bals.get("items", [])
            sum_res = round(sum(float(b.get("reserved_qty", 0)) for b in bal_list), 2)
            if abs(kpi_res - sum_res) <= 0.5:
                results["pass"] += 1
                line("PASS", G, f"dashboard: reserved KPI {kpi_res} == Σbalances {sum_res}")
            else:
                results["fail"] += 1
                line("FAIL", R, f"dashboard: reserved {kpi_res} != Σbalances {sum_res}")
        except Exception as e:
            results["fail"] += 1; line("FAIL", R, f"invarian reserved_qty GAGAL/error: {e}")

        # INV-4: sales-orders/stats/summary total_orders == jumlah GET /sales-orders
        try:
            stats = await get("/api/sales-orders/stats/summary")
            orders = await get("/api/sales-orders")
            n_orders = len(orders) if isinstance(orders, list) else len(orders.get("items", []))
            if stats.get("total_orders") == n_orders:
                results["pass"] += 1
                line("PASS", G, f"orders: stats total {stats.get('total_orders')} == /sales-orders {n_orders}")
            else:
                results["fail"] += 1
                line("FAIL", R, f"orders: stats {stats.get('total_orders')} != list {n_orders}",
                     "→ breakdown/summary menyembunyikan order")
        except Exception as e:
            results["fail"] += 1; line("FAIL", R, f"invarian orders stats GAGAL/error: {e}")

        # INV-5 (G9/RC-7): dashboard active_orders == count SELURUH order aktif,
        # bukan hasil window 20 order terakhir.
        try:
            dash = await get("/api/dashboard")
            kpi_active = dash.get("metrics", {}).get("active_orders")
            orders = await get("/api/sales-orders")
            olist = orders if isinstance(orders, list) else orders.get("items", [])
            actual_active = sum(1 for o in olist
                                if o.get("status") not in ["done", "cancelled", "expired"])
            if kpi_active == actual_active:
                results["pass"] += 1
                line("PASS", G, f"dashboard: active_orders KPI {kpi_active} == hitung penuh {actual_active}")
            else:
                results["fail"] += 1
                line("FAIL", R, f"dashboard: active_orders {kpi_active} != hitung penuh {actual_active}",
                     "→ KPI dihitung dari window terbatas (RC-7), salah saat order banyak")
        except Exception as e:
            results["fail"] += 1; line("FAIL", R, f"invarian active_orders GAGAL/error: {e}")


def _entity_registry_collections():
    """Ekstrak nama koleksi kanonik dari ENTITY_REGISTRY.md (SSOT) untuk
    cross-check (cegah gate & dokumen drift sendiri — pelajaran B2)."""
    import re
    reg = ROOT / "ENTITY_REGISTRY.md"
    if not reg.exists():
        return None
    text = reg.read_text(encoding="utf-8", errors="ignore")
    found = set()
    for m in re.finditer(r"Collection:\s*([a-z][a-z0-9_]+)", text):
        found.add(m.group(1))
    for m in re.finditer(r"`([a-z][a-z0-9_]+)`", text):
        found.add(m.group(1))
    return found


async def layer0_self_check():
    """G4: daftar kanonik di verify_contract.py HARUS konsisten dgn ENTITY_REGISTRY.md."""
    print(f"\n{C}{B}L0 — Self-check: gate vs ENTITY_REGISTRY (anti self-drift){X}")
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_contract import CANONICAL_COLLECTIONS
    except Exception as e:
        results["warn"] += 1; line("WARN", Y, f"tidak bisa impor CANONICAL_COLLECTIONS: {e}"); return
    reg = _entity_registry_collections()
    if reg is None:
        results["warn"] += 1; line("WARN", Y, "ENTITY_REGISTRY.md tidak ditemukan"); return
    # setiap koleksi kanonik gate harus disebut di ENTITY_REGISTRY
    missing_in_reg = sorted(c for c in CANONICAL_COLLECTIONS if c not in reg)
    if missing_in_reg:
        results["fail"] += 1
        line("FAIL", R, f"{len(missing_in_reg)} koleksi gate tidak ada di ENTITY_REGISTRY: {missing_in_reg}",
             "→ gate & SSOT drift; samakan keduanya")
    else:
        results["pass"] += 1
        line("PASS", G, f"{len(CANONICAL_COLLECTIONS)} koleksi kanonik konsisten dengan ENTITY_REGISTRY")


async def layer5_number_series(db):
    """G8/RC-5: deteksi duplikat nomor dokumen (sumber duplicate-key/kebingungan)."""
    print(f"\n{C}{B}L5 — Number-series integrity (cegah RC-5 duplicate number){X}")
    for coll, fld in [("sales_orders", "number"), ("purchase_orders", "po_number"),
                      ("invoices", "number")]:
        docs = await db[coll].find({}, {"_id": 0, fld: 1}).to_list(5000)
        nums = [d.get(fld) for d in docs if d.get(fld)]
        dupes = {n for n in nums if nums.count(n) > 1}
        if dupes:
            results["fail"] += 1
            line("FAIL", R, f"{coll}.{fld}: nomor DUPLIKAT {sorted(dupes)[:5]}",
                 "→ RC-5: penomoran berbasis count rentan tabrakan")
        elif nums:
            results["pass"] += 1
            line("PASS", G, f"{coll}.{fld}: {len(nums)} nomor unik (tidak ada duplikat)")


async def layer_roll_invariants(db):
    """Fase 0.5 — Invarian Roll-as-SSOT (KN_15 §10): balance == proyeksi rolls,
    panjang valid, referensi owner/lot, owner-scoped allocation."""
    print(f"\n{C}{B}L4-ROLL — Invarian Roll-as-SSOT (KN_15){X}")
    rolls = await db.inventory_rolls.find({}, {"_id": 0}).to_list(50000)
    if not rolls:
        results["fail"] += 1
        line("FAIL", R, "inventory_rolls KOSONG", "→ Roll-as-SSOT belum ter-generate")
        return

    # INV-ROLL-2: 0 <= length_remaining <= length_initial
    len_viol = [r.get("id") for r in rolls
                if not (0 - 0.01 <= float(r.get("length_remaining", 0) or 0)
                        <= float(r.get("length_initial", 0) or 0) + 0.01)]
    if len_viol:
        results["fail"] += 1
        line("FAIL", R, f"roll: {len(len_viol)} roll length_remaining di luar [0, length_initial]", str(len_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"roll: {len(rolls)} roll — 0 ≤ length_remaining ≤ length_initial")

    # INV-ROLL-3: referensi valid + lot wajib
    ent_ids = {e["id"] for e in await db.business_entities.find({}, {"_id": 0, "id": 1}).to_list(100)}
    wh_ids = {w["id"] for w in await db.warehouses.find({}, {"_id": 0, "id": 1}).to_list(100)}
    prod_ids = {p["id"] for p in await db.products.find({}, {"_id": 0, "id": 1}).to_list(2000)}
    ref_viol = [r.get("id") for r in rolls
                if r.get("owner_entity_id") not in ent_ids
                or r.get("warehouse_id") not in wh_ids
                or r.get("product_id") not in prod_ids
                or not r.get("lot")]
    if ref_viol:
        results["fail"] += 1
        line("FAIL", R, f"roll: {len(ref_viol)} roll referensi owner/wh/product/lot tidak valid", str(ref_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"roll: referensi owner/warehouse/product valid + lot wajib terisi")

    # INV-ROLL-1: balance == proyeksi rolls per segmen (available & reserved)
    from collections import defaultdict
    seg_avail = defaultdict(float)
    seg_res = defaultdict(float)
    for r in rolls:
        key = (r.get("product_id"), r.get("warehouse_id"), r.get("owner_entity_id"))
        length = float(r.get("length_remaining", 0) or 0)
        if r.get("status") == "available":
            seg_avail[key] += length
        elif r.get("status") == "reserved":
            seg_res[key] += length
    bals = await db.inventory_balances.find({}, {"_id": 0}).to_list(5000)
    proj_viol = []
    for b in bals:
        key = (b.get("product_id"), b.get("warehouse_id"), b.get("owner_entity_id"))
        if abs(float(b.get("available_qty", 0) or 0) - round(seg_avail.get(key, 0.0), 2)) > 0.5:
            proj_viol.append((b.get("id"), "available"))
        if abs(float(b.get("reserved_qty", 0) or 0) - round(seg_res.get(key, 0.0), 2)) > 0.5:
            proj_viol.append((b.get("id"), "reserved"))
    if proj_viol:
        results["fail"] += 1
        line("FAIL", R, f"roll: {len(proj_viol)} segmen balance != proyeksi rolls", str(proj_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"roll: {len(bals)} segmen — balance == Σ rolls (available/reserved)")

    # INV-OWN-1: alokasi SO owner-scoped (owner_entity_id == SO.entity_id) bila tersedia
    orders = await db.sales_orders.find(
        {"status": {"$in": ["reserved", "waiting_approval", "approved", "confirmed"]}}, {"_id": 0}
    ).to_list(2000)
    own_viol = []
    for o in orders:
        for a in o.get("allocations", []):
            if a.get("owner_entity_id") and a.get("owner_entity_id") != o.get("entity_id"):
                own_viol.append(o.get("number", o.get("id")))
                break
    if own_viol:
        results["fail"] += 1
        line("FAIL", R, f"order: {len(own_viol)} SO menjual roll milik entitas lain (langgar D3)", str(own_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "order: alokasi owner-scoped (owner == SO.entity_id) — D3 terpenuhi")

    # INV-LOT-1 (Sub-fase 1.7): konsistensi lot_mode per-alokasi & has_mixed_lot per-order.
    # Defensif: hanya cek alokasi yang punya field lot_mode (order pra-1.7 dilewati).
    lot_viol = []
    mixed_viol = []
    for o in orders:
        order_lots = set()
        has_lotmode_field = False
        for a in o.get("allocations", []):
            lm = a.get("lot_mode")
            lots = [l for l in (a.get("lots") or []) if l]
            order_lots.update(lots)
            if lm is None:
                continue
            has_lotmode_field = True
            if lm == "single" and len(lots) > 1:
                lot_viol.append(o.get("number", o.get("id")))
            if lm == "mixed" and len(lots) < 2:
                lot_viol.append(o.get("number", o.get("id")))
        # has_mixed_lot harus true bila >1 lot dipakai lintas alokasi (per order)
        if has_lotmode_field and "has_mixed_lot" in o:
            expect_mixed = len(order_lots) > 1
            if bool(o.get("has_mixed_lot")) != expect_mixed:
                mixed_viol.append(o.get("number", o.get("id")))
    if lot_viol:
        results["fail"] += 1
        line("FAIL", R, f"order: {len(lot_viol)} alokasi lot_mode tak konsisten (single>1 lot / mixed<2 lot)", str(lot_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "order: alokasi lot_mode konsisten (single≤1 lot, mixed≥2 lot) — Sub-fase 1.7")
    if mixed_viol:
        results["fail"] += 1
        line("FAIL", R, f"order: {len(mixed_viol)} SO has_mixed_lot tak cocok lot dipakai", str(mixed_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "order: has_mixed_lot ⟺ >1 lot dipakai (lintas alokasi) — Sub-fase 1.7")

    # INV-PEG (Pegging/Earmark): roll yang di-pegging WAJIB berstatus 'available'.
    peg_viol = [r.get("roll_no", r.get("id")) for r in rolls
                if r.get("earmarked_for") and r.get("status") != "available"]
    if peg_viol:
        results["fail"] += 1
        line("FAIL", R, f"roll: {len(peg_viol)} roll di-pegging tapi status != available", str(peg_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "roll: earmarked_for terisi ⟹ status 'available' (Pegging) — konsisten")


async def layer_backorder_invariants(db):
    """Sub-fase 1.6 — Invarian Backorder Lifecycle.
    Hanya untuk SO ber-anotasi fulfillment (reserved_qty/backorder_qty per item)."""
    print(f"\n{C}{B}L4-BO — Invarian Backorder (Sub-fase 1.6){X}")
    EPS = 0.5
    ACTIVE = {"reserved", "waiting_approval", "approved", "confirmed", "waiting_stock", "dispatched"}
    orders = await db.sales_orders.find({}, {"_id": 0}).to_list(5000)
    annotated = [o for o in orders
                 if any("backorder_qty" in (it or {}) for it in o.get("items", []))]
    if not annotated:
        results["pass"] += 1
        line("PASS", G, "backorder: tidak ada SO ber-anotasi fulfillment (skip — valid)")
        return

    # INV-BO-1: per item, quantity == reserved_qty + backorder_qty (+ intercompany_pending_qty)
    bo1_viol = []
    for o in annotated:
        for it in o.get("items", []):
            if "backorder_qty" not in it:
                continue
            # Sub-fase 1.13 — reservasi & backorder dalam BASE unit ⇒ bandingkan base_quantity.
            q = float(it.get("base_quantity", it.get("quantity", 0)) or 0)
            rq = float(it.get("reserved_qty", 0) or 0)
            bq = float(it.get("backorder_qty", 0) or 0)
            # SALES REVAMP V2 — Beli per Roll lintas-entitas: qty menunggu transfer antar-entitas.
            ic = float(it.get("intercompany_pending_qty", 0) or 0)
            if abs(q - (rq + bq + ic)) > EPS:
                bo1_viol.append((o.get("number", o.get("id")), it.get("sku")))
    if bo1_viol:
        results["fail"] += 1
        line("FAIL", R, f"backorder: {len(bo1_viol)} item base_quantity != reserved+backorder+intercompany", str(bo1_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"backorder: {len(annotated)} SO — base_quantity == reserved + backorder + intercompany per item")

    # INV-BO-2: konsistensi flag has_backorder + makna waiting_stock (decoupled, Sub-fase 1.6.1)
    bo2_viol = []
    for o in annotated:
        if o.get("status") not in ACTIVE:
            continue
        total_bo = sum(float(it.get("backorder_qty", 0) or 0) for it in o.get("items", []))
        total_res = sum(float(it.get("reserved_qty", 0) or 0) for it in o.get("items", []))
        has_bo_flag = bool(o.get("has_backorder"))
        if has_bo_flag != (total_bo > EPS):
            bo2_viol.append((o.get("number"), "flag has_backorder tidak konsisten"))
        if o.get("status") == "waiting_stock":
            if total_bo <= EPS:
                bo2_viol.append((o.get("number"), "waiting_stock tanpa backorder"))
            if total_res > EPS:
                bo2_viol.append((o.get("number"), "waiting_stock tapi ada porsi reserved (harusnya reserved)"))
    if bo2_viol:
        results["fail"] += 1
        line("FAIL", R, f"backorder: {len(bo2_viol)} SO status/flag tak konsisten", str(bo2_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "backorder: flag has_backorder ⟺ Σbackorder>0; waiting_stock ⟹ Σreserved≈0")

    # INV-BO-3: backorders[].entity_id == order.entity_id (owner-scoped, jaga D3)
    bo3_viol = []
    for o in annotated:
        for bo in o.get("backorders", []):
            if bo.get("entity_id") and bo.get("entity_id") != o.get("entity_id"):
                bo3_viol.append(o.get("number"))
                break
    if bo3_viol:
        results["fail"] += 1
        line("FAIL", R, f"backorder: {len(bo3_viol)} SO backorder owner != SO.entity_id", str(bo3_viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "backorder: backorder owner-scoped (entity == SO.entity_id) — D3")


async def layer_shipment_invariants(db):
    """Sub-fase 1.8 — Status SO diperluas + Partial Shipment (SSOT-safe)."""
    from collections import defaultdict
    print(f"\n{C}{B}L4-SHIP — Invarian Shipment & Status SO (Sub-fase 1.8){X}")
    EPS = 0.5
    tasks = await db.wms_tasks.find({"flow_type": "outbound"}, {"_id": 0}).to_list(20000)
    shipments = await db.shipments.find({}, {"_id": 0}).to_list(20000)
    orders = {o["id"]: o for o in await db.sales_orders.find({}, {"_id": 0}).to_list(20000)}

    # SHIP-1: 0 <= shipped_qty <= quantity per task
    s1 = [t.get("id") for t in tasks
          if not (-EPS <= float(t.get("shipped_qty", 0) or 0) <= float(t.get("quantity", 0) or 0) + EPS)]
    if s1:
        results["fail"] += 1
        line("FAIL", R, f"shipment: {len(s1)} task shipped_qty di luar [0, quantity]", str(s1[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"shipment: {len(tasks)} task outbound — 0 ≤ shipped_qty ≤ quantity")

    # SHIP-2: Σ shipments.qty per order == Σ task.shipped_qty per order
    ship_by_order = defaultdict(float)
    for s in shipments:
        ship_by_order[s.get("order_id")] += float(s.get("qty", 0) or 0)
    task_ship_by_order = defaultdict(float)
    for t in tasks:
        task_ship_by_order[t.get("order_id")] += float(t.get("shipped_qty", 0) or 0)
    s2 = [oid for oid in set(list(ship_by_order) + list(task_ship_by_order))
          if abs(ship_by_order.get(oid, 0) - task_ship_by_order.get(oid, 0)) > EPS]
    if s2:
        results["fail"] += 1
        line("FAIL", R, f"shipment: {len(s2)} order Σshipments.qty != Σtask.shipped_qty",
             str([orders.get(o, {}).get("number", o) for o in s2[:5]]))
    else:
        results["pass"] += 1
        line("PASS", G, f"shipment: {len(shipments)} shipment — Σ qty == Σ task.shipped_qty per order")

    # SHIP-3: status SO konsisten dgn progres task outbound
    s3 = []
    by_order_tasks = defaultdict(list)
    for t in tasks:
        by_order_tasks[t.get("order_id")].append(t)
    for oid, ts in by_order_tasks.items():
        o = orders.get(oid)
        if not o or o.get("status") in {"cancelled", "expired"}:
            continue
        total = sum(float(t.get("quantity", 0) or 0) for t in ts)
        shipped = sum(float(t.get("shipped_qty", 0) or 0) for t in ts)
        st = o.get("status")
        if st in {"shipped", "done"} and not (total > 0 and shipped + EPS >= total):
            s3.append((o.get("number"), f"{st} tapi shipped {round(shipped,1)}/{round(total,1)}"))
        if st == "partially_shipped" and not (EPS < shipped < total + EPS):
            s3.append((o.get("number"), f"partially_shipped tapi shipped {round(shipped,1)}/{round(total,1)}"))
        if st in {"confirmed", "partially_picked", "picked"} and shipped > EPS:
            s3.append((o.get("number"), f"{st} tapi sudah ada shipped {round(shipped,1)}"))
    if s3:
        results["fail"] += 1
        line("FAIL", R, f"shipment: {len(s3)} SO status tak konsisten dgn progres task", str(s3[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "shipment: status SO ⟺ progres task (picked/partially_shipped/shipped/done)")


async def layer_tax_invoice_invariants(db):
    """Sub-fase 1.9 — Faktur Pajak Jual (tax_invoices)."""
    print(f"\n{C}{B}L4-FKT — Invarian Faktur Pajak (Sub-fase 1.9){X}")
    EPS = 1.0
    fakturs = await db.tax_invoices.find({}, {"_id": 0}).to_list(20000)
    order_ids = {o["id"] for o in await db.sales_orders.find({}, {"id": 1, "_id": 0}).to_list(20000)}
    if not fakturs:
        results["pass"] += 1
        line("PASS", G, "faktur: belum ada Faktur Pajak (skip — valid, pajak opsional)")
        return

    # FKT-1: PPN ≈ DPP × rate ; grand ≈ Harga Jual + PPN.
    #   Gelombang 3 F-10 (Coretax PMK 131/2024): DPP Nilai Lain → dpp = 11/12 × harga_jual,
    #   ppn = rate × dpp (efektif 11%), grand = harga_jual + ppn. Basis harga jual = net_subtotal.
    bad_calc = []
    for f in fakturs:
        if f.get("status") == "batal":
            continue
        dpp = float(f.get("dpp", 0) or 0)
        rate = float(f.get("ppn_rate", 0) or 0)
        ppn = float(f.get("ppn_amount", 0) or 0)
        grand = float(f.get("grand_total", 0) or 0)
        base = float(f.get("net_subtotal", 0) or 0) or dpp  # harga jual (fallback: dpp bila tak ada nilai lain)
        if abs(ppn - round(dpp * rate / 100, 2)) > EPS or abs(grand - round(base + ppn, 2)) > EPS:
            bad_calc.append(f.get("number"))
    if bad_calc:
        results["fail"] += 1
        line("FAIL", R, f"faktur: {len(bad_calc)} faktur PPN/Grand tidak konsisten", str(bad_calc[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"faktur: {len(fakturs)} faktur — PPN==DPP×rate & Grand==HargaJual+PPN (F-10 DPP Nilai Lain)")

    # FKT-2: referensi order valid + hanya PKP & ppn>0 (utk normal/pengganti)
    # FASE G-6b — faktur pajak INTERNAL (antar-PT) tidak lahir dari pesanan penjualan;
    # referensinya `interco_pair_id` (dijaga INV-IC-07), jadi ia tidak wajib ber-`order_id`.
    bad_ref = [f.get("number") for f in fakturs
               if f.get("source_type") != "interco" and f.get("order_id") not in order_ids]
    bad_ref += [f.get("number") for f in fakturs
                if f.get("source_type") == "interco" and not f.get("interco_pair_id")]
    bad_pkp = [f.get("number") for f in fakturs
               if f.get("status") != "batal" and not (f.get("is_pkp") and float(f.get("ppn_amount", 0) or 0) > 0)]
    if bad_ref or bad_pkp:
        results["fail"] += 1
        line("FAIL", R, f"faktur: {len(bad_ref)} ref order invalid / {len(bad_pkp)} non-PKP-atau-tanpa-PPN",
             str((bad_ref + bad_pkp)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "faktur: referensi order valid + hanya PKP & ber-PPN (normal/pengganti)")

    # FKT-3: maksimal 1 faktur AKTIF (bukan batal & belum diganti) per order + nomor unik
    from collections import defaultdict
    active_by_order = defaultdict(int)
    for f in fakturs:
        if f.get("status") != "batal" and not f.get("replaced_by_id"):
            active_by_order[f.get("order_id")] += 1
    dup_active = [oid for oid, n in active_by_order.items() if n > 1]
    numbers = [f.get("number") for f in fakturs]
    dup_no = len(numbers) != len(set(numbers))
    if dup_active or dup_no:
        results["fail"] += 1
        line("FAIL", R, f"faktur: {len(dup_active)} order >1 faktur aktif / nomor duplikat={dup_no}",
             str(dup_active[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"faktur: ≤1 faktur aktif/order + {len(set(numbers))} nomor unik")

    # FKT-4: rantai pengganti konsisten (replaces_id menunjuk faktur yang ada)
    ids = {f.get("id") for f in fakturs}
    bad_chain = [f.get("number") for f in fakturs
                 if f.get("status") == "pengganti" and f.get("replaces_id") not in ids]
    if bad_chain:
        results["fail"] += 1
        line("FAIL", R, f"faktur: {len(bad_chain)} pengganti dgn replaces_id menggantung", str(bad_chain[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "faktur: rantai pengganti konsisten (replaces_id valid)")


async def layer_pr_invariants(db):
    """Depth #2 — Invarian Purchase Requisition (purchase_requisitions)."""
    print(f"\n{C}{B}L4-PR — Invarian Purchase Requisition (Depth #2){X}")
    EPS = 1.0
    prs = await db.purchase_requisitions.find({}, {"_id": 0}).to_list(20000)
    if not prs:
        results["pass"] += 1
        line("PASS", G, "PR: belum ada Purchase Requisition (skip — valid, opsional)")
        return

    po_ids = {p["id"] for p in await db.purchase_orders.find({}, {"id": 1, "_id": 0}).to_list(20000)}

    # PR-1: subtotal == est_price × qty  &&  total_est == Σ subtotal
    bad_calc = []
    for pr in prs:
        tot = 0.0
        ok = True
        for it in pr.get("items", []):
            sub = float(it.get("subtotal", 0) or 0)
            calc = round(float(it.get("est_price", 0) or 0) * float(it.get("quantity", 0) or 0), 2)
            if abs(sub - calc) > EPS:
                ok = False
            tot += sub
        if not ok or abs(round(tot, 2) - float(pr.get("total_est_amount", 0) or 0)) > EPS:
            bad_calc.append(pr.get("number"))
    if bad_calc:
        results["fail"] += 1
        line("FAIL", R, f"PR: {len(bad_calc)} PR subtotal/total tidak konsisten", str(bad_calc[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"PR: {len(prs)} PR — subtotal==est×qty & total==Σ subtotal")

    # PR-2: status 'converted' ⟹ po_id valid (menunjuk PO yang ada)
    bad_conv = [pr.get("number") for pr in prs
                if pr.get("status") == "converted" and pr.get("po_id") not in po_ids]
    if bad_conv:
        results["fail"] += 1
        line("FAIL", R, f"PR: {len(bad_conv)} PR converted dgn po_id menggantung", str(bad_conv[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "PR: status converted ⟹ po_id valid")

    # PR-3: nomor PR unik
    numbers = [pr.get("number") for pr in prs]
    if len(numbers) != len(set(numbers)):
        results["fail"] += 1
        line("FAIL", R, "PR: ada nomor PR duplikat")
    else:
        results["pass"] += 1
        line("PASS", G, f"PR: {len(set(numbers))} nomor PR unik")


async def layer_return_invariants(db):
    """R1-06 — Invarian Retur Penjualan: Σ quantity_returned per (order, produk) dari
    retur AKTIF (status ≠ rejected) TIDAK boleh melebihi kuantitas TERKIRIM (Σ outbound
    wms_tasks.shipped_qty) bila ada tracking, else TERJUAL (Σ order line quantity).
    Menutup bug over/double-return yang membengkakkan stok (REVIEW_LOG R1-06)."""
    from collections import defaultdict
    print(f"\n{C}{B}L4-RET — Invarian Retur ≤ Terkirim/Terjual (R1-06){X}")
    EPS = 0.01
    ACTIVE = {"draft", "pending_approval", "approved"}
    rets = await db.sales_returns.find({"status": {"$in": list(ACTIVE)}}, {"_id": 0}).to_list(20000)
    if not rets:
        results["pass"] += 1
        line("PASS", G, "retur: belum ada retur aktif (skip — valid)")
        return

    # returned per (order_id, product_id)
    returned = defaultdict(float)
    order_ids = set()
    for r in rets:
        oid = r.get("order_id")
        order_ids.add(oid)
        for it in r.get("items", []):
            pid = it.get("product_id")
            if pid:
                returned[(oid, pid)] += float(it.get("quantity_returned", 0) or 0)

    # sold per (order, product)
    orders = {o["id"]: o for o in await db.sales_orders.find(
        {"id": {"$in": list(order_ids)}}, {"_id": 0, "id": 1, "items": 1, "number": 1}).to_list(20000)}
    sold = defaultdict(float)
    for oid, o in orders.items():
        for it in o.get("items", []):
            pid = it.get("product_id")
            if pid:
                sold[(oid, pid)] += float(it.get("quantity", 0) or 0)

    # shipped per (order, product) dari outbound tasks
    shipped = defaultdict(float)
    async for t in db.wms_tasks.find(
            {"order_id": {"$in": list(order_ids)}, "flow_type": "outbound"},
            {"_id": 0, "order_id": 1, "product_id": 1, "shipped_qty": 1}):
        pid = t.get("product_id")
        if pid:
            shipped[(t.get("order_id"), pid)] += float(t.get("shipped_qty", 0) or 0)

    viol = []
    for key, ret_qty in returned.items():
        sh = round(shipped.get(key, 0.0), 2)
        cap = sh if sh > 0 else round(sold.get(key, 0.0), 2)
        if round(ret_qty, 2) > cap + EPS:
            oid, pid = key
            viol.append(f"{orders.get(oid, {}).get('number', oid)}/{pid}(ret {ret_qty:g}>{cap:g})")
    if viol:
        results["fail"] += 1
        line("FAIL", R, f"retur: {len(viol)} (order,produk) retur > terkirim/terjual", str(viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"retur: {len(returned)} (order,produk) — Σ retur ≤ terkirim/terjual (R1-06)")



async def layer_gl_invariants(db):
    """Session #074 — Invarian General Ledger. Menutup META-GATE-GL: gate lama
    BUTA terhadap keseimbangan jurnal & rekonsiliasi persediaan.
      GL-1 (FAIL): setiap JE non-void seimbang (Σline.debit == Σline.credit == header).
      GL-2 (FAIL): trial balance seimbang per entitas.
      GL-3 (WARN): rekonsiliasi persediaan subledger(rolls) vs GL 1-1300 (INV-GL-DRIFT).
      GL-4 (WARN): order berpendapatan tanpa jurnal HPP (COGS-ZERO detector).
    """
    from collections import defaultdict
    print(f"\n{C}{B}L4-GL — Invarian General Ledger (keseimbangan & rekonsiliasi){X}")
    EPS = 0.5
    jes = await db.journal_entries.find({"status": {"$ne": "void"}}, {"_id": 0}).to_list(200000)

    # GL-1: setiap JE seimbang (baris & header konsisten)
    unbal = []
    for je in jes:
        d = round(sum(float(l.get("debit", 0) or 0) for l in je.get("lines", [])), 2)
        c = round(sum(float(l.get("credit", 0) or 0) for l in je.get("lines", [])), 2)
        td = round(float(je.get("total_debit", 0) or 0), 2)
        tc = round(float(je.get("total_credit", 0) or 0), 2)
        if abs(d - c) > EPS or abs(td - tc) > EPS or abs(d - td) > EPS:
            unbal.append(je.get("number", je.get("id")))
    if unbal:
        results["fail"] += 1
        line("FAIL", R, f"GL: {len(unbal)} jurnal TIDAK seimbang (Σdebit != Σkredit)", str(unbal[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"GL: {len(jes)} jurnal — setiap entri seimbang (Σdebit == Σkredit)")

    # GL-2: trial balance seimbang per entitas
    tb = defaultdict(lambda: [0.0, 0.0])
    for je in jes:
        eid = je.get("entity_id", "")
        for l in je.get("lines", []):
            tb[eid][0] += float(l.get("debit", 0) or 0)
            tb[eid][1] += float(l.get("credit", 0) or 0)
    tb_viol = [f"{eid}(Δ{round(v[0]-v[1],2)})" for eid, v in tb.items() if abs(v[0] - v[1]) > EPS]
    if tb_viol:
        results["fail"] += 1
        line("FAIL", R, f"GL: trial balance tak seimbang per entitas: {tb_viol[:5]}")
    else:
        results["pass"] += 1
        line("PASS", G, f"GL: trial balance seimbang untuk {len(tb)} buku entitas")

    # GL-3 (WARN): rekonsiliasi persediaan subledger(rolls) vs GL 1-1300
    PHYS = ["available", "reserved", "committed", "picked", "packed", "quarantine", "hold"]
    ents = await db.business_entities.find({}, {"_id": 0, "id": 1}).to_list(100)
    gl_inv = defaultdict(float)
    for je in jes:
        eid = je.get("entity_id", "")
        for l in je.get("lines", []):
            if l.get("account_code") == "1-1300":
                gl_inv[eid] += float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0)
    drift = []
    for e in ents:
        eid = e["id"]
        rolls = await db.inventory_rolls.find(
            {"owner_entity_id": eid, "status": {"$in": PHYS}},
            {"_id": 0, "length_remaining": 1, "unit_cost": 1, "base_unit_cost": 1}).to_list(100000)
        sub = round(sum(float(r.get("length_remaining", 0) or 0) *
                        float(r.get("unit_cost") or r.get("base_unit_cost") or 0) for r in rolls), 2)
        diff = round(sub - round(gl_inv.get(eid, 0.0), 2), 2)
        if abs(diff) > 1.0:
            drift.append(f"{eid}(Δ{diff:,.0f})")
    if drift:
        results["warn"] += 1
        line("WARN", Y, f"GL: {len(drift)} entitas drift persediaan subledger vs GL 1-1300: {drift[:5]}",
             "→ jalankan post_inventory_opening_balance / cek posting GR·COGS·retur·LC (INV-GL-DRIFT)")
    else:
        results["pass"] += 1
        line("PASS", G, "GL: rekonsiliasi persediaan (subledger rolls == GL 1-1300) per entitas")

    # GL-4 (WARN): order berpendapatan tapi tanpa jurnal HPP (COGS-ZERO)
    posted_rev = {je.get("source_id") for je in jes if je.get("source_type") == "sales_order"}
    posted_cogs = {je.get("source_id") for je in jes if je.get("source_type") == "sales_cogs"}
    missing_cogs = [sid for sid in posted_rev if sid and sid not in posted_cogs]
    if missing_cogs:
        results["warn"] += 1
        line("WARN", Y, f"GL: {len(missing_cogs)} order punya jurnal pendapatan tanpa jurnal HPP (COGS-ZERO)",
             "→ laba kotor bisa overstated; cek cost roll / _order_item_unit_cost")
    else:
        results["pass"] += 1
        line("PASS", G, "GL: setiap order berpendapatan juga punya jurnal HPP (tidak ada COGS-ZERO)")

    # GL-5 (INV-AR-01): rekonsiliasi Piutang 1-1200 lintas-PT (KN-076-AR-GL-DRIFT).
    #   (a) FAIL: AR ter-buku di buku NON-entitas ("all"/kosong) → bocor ke konsolidasi
    #             (penerimaan AR kas_besar salah entitas).
    #   (b) WARN: saldo AR NEGATIF per entitas → over-credit (kelebihan bayar/deposit tak
    #             dipisah ke Uang Muka Pelanggan 2-1400).
    real_ids = {e["id"] for e in ents}
    ar_bal = defaultdict(float)
    for je in jes:
        eid = je.get("entity_id", "")
        for l in je.get("lines", []):
            if l.get("account_code") == "1-1200":
                ar_bal[eid] += float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0)
    ar_leak = [f"{eid or '(kosong)'}(Δ{round(v,0):,.0f})" for eid, v in ar_bal.items()
               if eid not in real_ids and abs(v) > EPS]
    ar_neg = [f"{eid}({round(v,0):,.0f})" for eid, v in ar_bal.items()
              if eid in real_ids and v < -EPS]
    if ar_leak:
        results["fail"] += 1
        line("FAIL", R, f"GL: AR 1-1200 ter-buku di buku non-entitas: {ar_leak[:5]}",
             "→ posting penerimaan AR harus di entitas pemilik piutang (KN-076-AR-GL-DRIFT)")
    elif ar_neg:
        results["warn"] += 1
        line("WARN", Y, f"GL: {len(ar_neg)} entitas saldo AR negatif (over-credit): {ar_neg[:5]}",
             "→ pisahkan kelebihan bayar ke Uang Muka Pelanggan 2-1400 (KN-076-AR-GL-DRIFT)")
    else:
        results["pass"] += 1
        line("PASS", G, "GL: Piutang 1-1200 ter-rekonsiliasi per entitas (tak bocor ke 'all', tak negatif)")


async def layer_fixed_asset_invariants(db):
    """R6.2 — Fixed Assets: konsistensi subledger↔GL (straight-line + disposal gain/loss)."""
    print(f"\n{C}{B}FA — Aset Tetap & Penyusutan (R6.2){X}")
    assets = await db.fin_fixed_assets.find({}, {"_id": 0}).to_list(20000)
    entries = await db.fin_depreciation_entries.find({}, {"_id": 0}).to_list(50000)
    ASSET_ACCS = {"1-2100", "1-2200", "1-2300", "1-2400"}
    ACC_DEP, ASSET_DEFAULT = "1-2900", "1-2100"
    # FASE E-7 (E7g) memperkenalkan status `transferred`: aset yang HAKNYA sudah
    # berpindah ke badan usaha lain. Di buku penjual aset itu DI-DEREKOGNISI —
    # perolehan & akumulasinya dikeluarkan dari GL dan nilai bukunya menjadi 0.
    #
    # Invarian di bawah dulu memakai satu aturan: "semua yang bukan `disposed` =
    # aktif". Akibatnya aset yang sudah pindah PT tetap DIHITUNG sebagai milik
    # penjual, sehingga FA-2/FA-3/FA-4 memerah padahal GL-nya benar — persis kelas
    # bug yang sama sudah ditemukan & ditutup di layar Aset Tetap (`summary()`)
    # pada sesi E-7, tetapi invarian ini belum ikut diperbarui. Invarian yang
    # memerah untuk keadaan yang SAH adalah invarian yang mengajari orang
    # mengabaikan gate, jadi definisi "aktif" disatukan di sini.
    INACTIVE = ("disposed", "transferred")
    aktif = [a for a in assets if a.get("status") not in INACTIVE]

    # FA-1 — accumulated aset == Σ entri penyusutan
    sum_by_asset = {}
    for e in entries:
        sum_by_asset[e.get("asset_id")] = round(sum_by_asset.get(e.get("asset_id"), 0) + float(e.get("amount", 0) or 0), 2)
    v1 = [a.get("number") for a in assets
          if abs(round(float(a.get("accumulated_depreciation", 0) or 0), 2) - sum_by_asset.get(a.get("id"), 0.0)) > 0.01]
    if v1:
        results["fail"] += 1
        line("FAIL", R, f"FA-1: {len(v1)} aset accumulated≠Σentri: {v1[:5]}",
             "→ subledger penyusutan drift dari master aset")
    else:
        results["pass"] += 1
        line("PASS", G, f"FA-1: accumulated == Σ entri penyusutan ({len(assets)} aset)")

    # FA-2 — book_value == cost − accumulated (aset yang masih dimiliki)
    v2 = [a.get("number") for a in aktif
          if abs(round(float(a.get("acquisition_cost", 0) or 0) - float(a.get("accumulated_depreciation", 0) or 0), 2)
                  - round(float(a.get("book_value", 0) or 0), 2)) > 0.01]
    if v2:
        results["fail"] += 1
        line("FAIL", R, f"FA-2: {len(v2)} aset book_value≠cost−akum: {v2[:5]}", "")
    else:
        results["pass"] += 1
        line("PASS", G, "FA-2: book_value == harga_perolehan − akumulasi (aset aktif)")

    # FA-2b — aset yang sudah PINDAH PT tidak boleh menyisakan nilai buku di buku
    # penjual. Ini pengganti cakupan yang hilang saat `transferred` dikecualikan:
    # tanpa pemeriksaan ini, aset pindah yang lupa di-derekognisi lolos tanpa suara.
    v2b = [a.get("number") for a in assets if a.get("status") == "transferred"
           and abs(round(float(a.get("book_value", 0) or 0), 2)) > 0.01]
    if v2b:
        results["fail"] += 1
        line("FAIL", R, f"FA-2b: {len(v2b)} aset pindah PT masih bernilai buku: {v2b[:5]}",
             "→ hak sudah berpindah tetapi buku penjual belum derekognisi")
    else:
        results["pass"] += 1
        line("PASS", G, "FA-2b: aset yang pindah PT bernilai buku 0 di buku penjual")

    # GL sums (non-void)
    jes = await db.journal_entries.find({"status": {"$ne": "void"}}, {"_id": 0, "lines": 1}).to_list(200000)
    gl_net = {}  # code -> Σdebit − Σcredit
    for je in jes:
        for l in je.get("lines", []):
            code = l.get("account_code")
            gl_net[code] = round(gl_net.get(code, 0) + float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0), 2)

    # FA-3 — Akumulasi Penyusutan (1-2900) saldo kredit == Σ accumulated aset non-disposed
    exp_accdep = round(sum(float(a.get("accumulated_depreciation", 0) or 0)
                           for a in aktif), 2)
    actual_accdep = round(-gl_net.get(ACC_DEP, 0.0), 2)  # saldo kredit = −net
    if abs(actual_accdep - exp_accdep) > 0.5:
        results["fail"] += 1
        line("FAIL", R, f"FA-3: GL 1-2900={actual_accdep} ≠ Σakumulasi aktif={exp_accdep}",
             "→ akumulasi penyusutan GL drift dari subledger")
    else:
        results["pass"] += 1
        line("PASS", G, f"FA-3: GL Akumulasi Penyusutan (1-2900) == Σ akumulasi aset aktif ({exp_accdep:.0f})")

    # FA-4 — akun aset (1-21xx..24xx) saldo debit == Σ harga perolehan aset non-disposed
    exp_asset = round(sum(float(a.get("acquisition_cost", 0) or 0)
                          for a in aktif), 2)
    actual_asset = round(sum(gl_net.get(c, 0.0) for c in ASSET_ACCS), 2)
    if abs(actual_asset - exp_asset) > 0.5:
        results["fail"] += 1
        line("FAIL", R, f"FA-4: GL akun aset={actual_asset} ≠ Σperolehan aktif={exp_asset}",
             "→ perolehan/disposal aset tidak seimbang di GL")
    else:
        results["pass"] += 1
        line("PASS", G, f"FA-4: GL akun aset tetap == Σ harga perolehan aset aktif ({exp_asset:.0f})")


async def layer_budget_invariants(db):
    """R6.3 — Budget Control: konsistensi master anggaran & kebijakan per entitas."""
    print(f"\n{C}{B}BG — Anggaran & Budget Control (R6.3){X}")
    budgets = await db.budgets.find({}, {"_id": 0}).to_list(20000)
    accounts = {a.get("code") for a in await db.gl_accounts.find({}, {"_id": 0, "code": 1}).to_list(5000)}
    cats = {c.get("code") for c in await db.expense_categories.find({}, {"_id": 0, "code": 1}).to_list(500)}
    VALID_MODES = {"off", "warn", "block"}
    VALID_UNBUDGETED = {"allow", "warn", "block"}

    # BG-1 — tidak ada anggaran duplikat per (entity, year, month, dimension, key)
    seen, dup = set(), []
    for b in budgets:
        k = (b.get("entity_id"), b.get("year"), int(b.get("month", 0) or 0),
             b.get("dimension") or "account", b.get("key") or b.get("account_code"))
        if k in seen:
            dup.append(k)
        seen.add(k)
    if dup:
        results["fail"] += 1
        line("FAIL", R, f"BG-1: {len(dup)} anggaran duplikat: {dup[:5]}",
             "→ satu kunci anggaran hanya boleh 1 baris per entitas/tahun/bulan")
    else:
        results["pass"] += 1
        line("PASS", G, f"BG-1: tidak ada anggaran duplikat ({len(budgets)} baris)")

    # BG-2 — amount > 0 dan month 0..12
    bad = [b.get("id") for b in budgets
           if float(b.get("amount", 0) or 0) <= 0 or not (0 <= int(b.get("month", 0) or 0) <= 12)]
    if bad:
        results["fail"] += 1
        line("FAIL", R, f"BG-2: {len(bad)} anggaran nominal≤0 / bulan invalid: {bad[:5]}", "")
    else:
        results["pass"] += 1
        line("PASS", G, "BG-2: nominal anggaran > 0 & bulan 0–12 (valid)")

    # BG-3 — key anggaran terdaftar (akun COA / kategori beban)
    orphan = []
    for b in budgets:
        dim = b.get("dimension") or "account"
        key = b.get("key") or b.get("account_code")
        if dim == "account" and accounts and key not in accounts:
            orphan.append(f"{key}(acc)")
        elif dim == "category" and cats and key not in cats:
            orphan.append(f"{key}(cat)")
    if orphan:
        results["fail"] += 1
        line("FAIL", R, f"BG-3: {len(orphan)} anggaran menunjuk kunci tak dikenal: {orphan[:5]}",
             "→ akun COA / kategori beban sudah dihapus atau salah tulis")
    else:
        results["pass"] += 1
        line("PASS", G, "BG-3: semua kunci anggaran terdaftar (akun COA / kategori beban)")

    # BG-4 — kebijakan budget rules valid
    rules = await db.fin_budget_rules.find({}, {"_id": 0}).to_list(500)
    badr = [r.get("entity_id") for r in rules
            if (r.get("mode") and r["mode"] not in VALID_MODES)
            or (r.get("unbudgeted_action") and r["unbudgeted_action"] not in VALID_UNBUDGETED)
            or (r.get("warn_threshold_pct") is not None
                and not (0 <= float(r["warn_threshold_pct"]) <= 100))]
    if badr:
        results["fail"] += 1
        line("FAIL", R, f"BG-4: {len(badr)} kebijakan anggaran invalid: {badr[:5]}", "")
    else:
        results["pass"] += 1
        line("PASS", G, f"BG-4: kebijakan over-budget valid ({len(rules)} entitas terkonfigurasi)")


async def layer_production_invariants(db):
    """R6.4 — Produksi In-House (BOM + Work Order): resep valid, HPP konsisten,
    konsumsi bahan == movement, roll barang jadi ada, overhead terkapitalisasi di GL."""
    print(f"\n{C}{B}MFG — Produksi In-House · BOM & Work Order (R6.4){X}")
    boms = await db.mfg_boms.find({}, {"_id": 0}).to_list(20000)
    wos = await db.mfg_work_orders.find({}, {"_id": 0}).to_list(50000)
    pids = {p.get("id") for p in await db.products.find({}, {"_id": 0, "id": 1}).to_list(20000)}
    VALID_BOM_STATUS = {"active", "inactive"}
    VALID_WO_STATUS = {"draft", "released", "completed", "cancelled"}
    done = [w for w in wos if w.get("status") == "completed"]

    # MFG-1 — resep BOM valid (komponen ada, qty>0, tak duplikat, bahan≠output, produk terdaftar)
    bad1 = []
    for b in boms:
        comps = b.get("components") or []
        label = b.get("name") or b.get("id")
        out_pid = b.get("output_product_id")
        if not comps:
            bad1.append(f"{label}(komponen kosong)")
            continue
        if b.get("status") not in VALID_BOM_STATUS:
            bad1.append(f"{label}(status {b.get('status')})")
        if pids and out_pid not in pids:
            bad1.append(f"{label}(output orphan)")
        seen = set()
        for c in comps:
            mpid = c.get("material_product_id")
            if float(c.get("qty_per_unit", 0) or 0) <= 0:
                bad1.append(f"{label}(qty_per_unit≤0)")
            if mpid == out_pid:
                bad1.append(f"{label}(bahan==output)")
            if mpid in seen:
                bad1.append(f"{label}(komponen duplikat)")
            if pids and mpid not in pids:
                bad1.append(f"{label}(bahan orphan)")
            seen.add(mpid)
    if bad1:
        results["fail"] += 1
        line("FAIL", R, f"MFG-1: {len(bad1)} pelanggaran resep BOM: {bad1[:5]}",
             "→ BOM harus punya ≥1 komponen valid, qty>0, tanpa duplikat, bahan≠output")
    else:
        results["pass"] += 1
        line("PASS", G, f"MFG-1: semua resep BOM valid ({len(boms)} BOM)")

    # MFG-2 — HPP WO selesai konsisten (total = bahan + overhead; unit = total/qty; qty = rencana)
    bad2 = []
    for w in done:
        num = w.get("wo_number") or w.get("id")
        mat = round(float(w.get("material_cost", 0) or 0), 2)
        ovh = round(float(w.get("overhead_cost", 0) or 0), 2)
        tot = round(float(w.get("total_cost", 0) or 0), 2)
        qty = round(float(w.get("produced_qty", 0) or 0), 2)
        plan = round(float(w.get("planned_qty", 0) or 0), 2)
        if abs(mat + ovh - tot) > 0.05:
            bad2.append(f"{num}(total≠bahan+overhead)")
        if qty <= 0 or abs(qty - plan) > 0.01:
            bad2.append(f"{num}(produced_qty≠planned_qty)")
        elif abs(round(tot / qty, 2) - round(float(w.get("unit_cost", 0) or 0), 2)) > 0.05:
            bad2.append(f"{num}(unit_cost≠total/qty)")
        if abs(round(float(w.get("overhead_per_unit", 0) or 0) * plan, 2) - ovh) > 0.05:
            bad2.append(f"{num}(overhead≠per_unit×qty)")
        if not (w.get("produced_roll_ids") or []):
            bad2.append(f"{num}(tanpa roll barang jadi)")
        if mat <= 0:
            bad2.append(f"{num}(material_cost≤0)")
    badstat = [w.get("wo_number") for w in wos if w.get("status") not in VALID_WO_STATUS]
    if bad2 or badstat:
        results["fail"] += 1
        line("FAIL", R, f"MFG-2: {len(bad2)} HPP WO tak konsisten: {bad2[:5]} status_invalid={badstat[:3]}",
             "→ HPP produksi = Σnilai bahan + overhead; roll output wajib ada")
    else:
        results["pass"] += 1
        line("PASS", G, f"MFG-2: HPP & status WO konsisten ({len(done)} WO selesai / {len(wos)} total)")

    # MFG-3 — konsumsi bahan == movement `production_consume`, roll output ada & senilai unit_cost
    movs = await db.inventory_movements.find(
        {"movement_type": "production_consume"}, {"_id": 0}).to_list(200000)
    mov_qty = {}
    for m in movs:
        k = (m.get("source_document"), m.get("product_id"))
        mov_qty[k] = round(mov_qty.get(k, 0.0) + abs(float(m.get("quantity", 0) or 0)), 2)
    roll_ids = {w.get("id"): (w.get("produced_roll_ids") or []) for w in done}
    all_out_rolls = await db.inventory_rolls.find(
        {"id": {"$in": [rid for v in roll_ids.values() for rid in v]}}, {"_id": 0}).to_list(50000)
    roll_by_id = {r["id"]: r for r in all_out_rolls}
    bad3 = []
    for w in done:
        num = w.get("wo_number") or w.get("id")
        for c in (w.get("consumed") or []):
            want = round(float(c.get("qty", 0) or 0), 2)
            got = mov_qty.get((w.get("id"), c.get("material_product_id")), 0.0)
            if abs(want - got) > 0.05:
                bad3.append(f"{num}/{c.get('sku') or c.get('material_product_id')}({want}≠{got})")
        for rid in (w.get("produced_roll_ids") or []):
            r = roll_by_id.get(rid)
            if not r:
                bad3.append(f"{num}(roll {rid} hilang)")
                continue
            if (r.get("acquired") or {}).get("via") != "production_output":
                bad3.append(f"{num}(roll bukan production_output)")
            if abs(round(float(r.get("unit_cost", 0) or 0), 2)
                   - round(float(w.get("unit_cost", 0) or 0), 2)) > 0.05:
                bad3.append(f"{num}(unit_cost roll≠HPP WO)")
    if bad3:
        results["fail"] += 1
        line("FAIL", R, f"MFG-3: {len(bad3)} drift konsumsi/roll produksi: {bad3[:5]}",
             "→ Roll-as-SSOT: konsumsi WO wajib punya movement & roll output senilai HPP")
    else:
        results["pass"] += 1
        line("PASS", G, f"MFG-3: konsumsi bahan == movement & roll output senilai HPP "
                        f"({len(movs)} movement konsumsi)")

    # MFG-4 — overhead terkapitalisasi di GL (Cr 5-1100) == Σ overhead WO selesai; je_id iff overhead>0
    jes = await db.journal_entries.find(
        {"status": {"$ne": "void"}, "source_type": "production_output"},
        {"_id": 0, "id": 1, "lines": 1, "source_id": 1}).to_list(50000)
    gl_ovh = 0.0
    for je in jes:
        for l in (je.get("lines") or []):
            if l.get("account_code") == "5-1100":
                gl_ovh += float(l.get("credit", 0) or 0)
    gl_ovh = round(gl_ovh, 2)
    exp_ovh = round(sum(float(w.get("overhead_cost", 0) or 0) for w in done), 2)
    je_ids = {je.get("source_id") for je in jes}
    bad4 = []
    for w in done:
        num = w.get("wo_number") or w.get("id")
        ovh = round(float(w.get("overhead_cost", 0) or 0), 2)
        has_je = bool(w.get("je_id"))
        if ovh > 0.005 and not (has_je and w.get("id") in je_ids):
            bad4.append(f"{num}(overhead {ovh} tanpa JE)")
        if ovh <= 0.005 and has_je:
            bad4.append(f"{num}(JE padahal overhead 0)")
    if bad4 or abs(gl_ovh - exp_ovh) > 0.5:
        results["fail"] += 1
        line("FAIL", R, f"MFG-4: GL overhead 5-1100={gl_ovh} ≠ Σoverhead WO={exp_ovh}; anomali={bad4[:5]}",
             "→ overhead produksi wajib Dr 1-1300 / Cr 5-1100 tepat sekali per WO (idempotent)")
    else:
        results["pass"] += 1
        line("PASS", G, f"MFG-4: overhead produksi terkapitalisasi tepat di GL "
                        f"(5-1100 kredit {exp_ovh:.0f} == Σ WO, {len(jes)} JE)")


async def layer_scheduler_invariants(db):
    """R6.5 — Penjadwal & Notifikasi + kanal WhatsApp: histori run valid, notifikasi
    ter-dedupe harian & severity valid, outbox WA ternormalisasi + tanpa kebocoran
    kredensial, pengaturan alert konsisten dengan provider terpilih."""
    print(f"\n{C}{B}SCH — Penjadwal, Notifikasi & Outbox WhatsApp (R6.5){X}")
    runs = await db.sys_scheduler_runs.find({}, {"_id": 0}).to_list(50000)
    notifs = await db.notifications.find({}, {"_id": 0}).to_list(50000)
    outbox = await db.sys_wa_outbox.find({}, {"_id": 0}).to_list(50000)
    st = await db.system_settings.find_one({"scope": "alerts"}, {"_id": 0}) or {}

    VALID_RUN_STATUS = {"success", "failed", "running"}
    VALID_SEVERITY = {"info", "warning", "critical"}
    VALID_WA_STATUS = {"simulated", "sent", "failed"}
    VALID_PROVIDER = {"simulated", "meta_cloud", "fonnte"}
    # Job R6.5 memakai dedupe_scope="day" → 1 notifikasi per (type, ref) per HARI.
    SCHED_ALERT_TYPES = {"ar_overdue", "ap_due", "depreciation_due", "budget_alert",
                         "production_stalled", "ops_stalled"}

    # SCH-1 — histori eksekusi job valid (status, durasi, urutan waktu, counter ≥ 0)
    bad1 = []
    for r in runs:
        rid = r.get("id", "?")
        if r.get("status") not in VALID_RUN_STATUS:
            bad1.append(f"{rid}(status {r.get('status')})")
        if not r.get("job_id") or not r.get("job_label"):
            bad1.append(f"{rid}(job_id/label kosong)")
        if float(r.get("duration_ms", 0) or 0) < 0:
            bad1.append(f"{rid}(durasi negatif)")
        for k in ("created", "scanned", "wa_queued"):
            if float(r.get(k, 0) or 0) < 0:
                bad1.append(f"{rid}({k} negatif)")
        fin, sta = r.get("finished_at") or "", r.get("started_at") or ""
        if fin and sta and fin < sta:
            bad1.append(f"{rid}(finished < started)")
        if r.get("status") == "success" and (r.get("error") or ""):
            bad1.append(f"{rid}(sukses tapi ada error)")
        if r.get("status") == "failed" and not (r.get("error") or ""):
            bad1.append(f"{rid}(gagal tanpa pesan error)")
    if bad1:
        results["fail"] += 1
        line("FAIL", R, f"SCH-1: {len(bad1)} baris histori job invalid: {bad1[:5]}",
             "→ setiap run wajib status valid, durasi ≥ 0, finished ≥ started, error iff gagal")
    else:
        results["pass"] += 1
        line("PASS", G, f"SCH-1: histori eksekusi job valid ({len(runs)} run)")

    # SCH-2 — notifikasi: severity valid, dedupe_key konsisten (type:ref:hari)
    bad2 = []
    for n in notifs:
        nid = n.get("id", "?")
        if n.get("severity") not in VALID_SEVERITY:
            bad2.append(f"{nid}(severity {n.get('severity')})")
        if not n.get("type") or not n.get("title"):
            bad2.append(f"{nid}(type/title kosong)")
        if not isinstance(n.get("read"), bool):
            bad2.append(f"{nid}(read bukan bool)")
        ref, day = n.get("ref") or "", (n.get("created_at") or "")[:10]
        if ref and n.get("dedupe_key") != f"{n.get('type')}:{ref}:{day}":
            bad2.append(f"{nid}(dedupe_key drift)")
    if bad2:
        results["fail"] += 1
        line("FAIL", R, f"SCH-2: {len(bad2)} notifikasi invalid: {bad2[:5]}",
             "→ dedupe_key wajib '<type>:<ref>:<YYYY-MM-DD>' & severity info/warning/critical")
    else:
        results["pass"] += 1
        line("PASS", G, f"SCH-2: notifikasi valid & dedupe_key konsisten ({len(notifs)} notifikasi)")

    # SCH-3 — idempotensi harian job alert: TIDAK ada dedupe_key ganda untuk tipe job R6.5
    dupes = {}
    for n in notifs:
        if n.get("type") in SCHED_ALERT_TYPES and n.get("dedupe_key"):
            dupes[n["dedupe_key"]] = dupes.get(n["dedupe_key"], 0) + 1
    dup_keys = [k for k, v in dupes.items() if v > 1]
    if dup_keys:
        results["fail"] += 1
        line("FAIL", R, f"SCH-3: {len(dup_keys)} alert terduplikasi dalam hari sama: {dup_keys[:5]}",
             "→ job scheduler wajib dedupe_scope='day' (jalankan 2× sehari tidak menduplikasi)")
    else:
        results["pass"] += 1
        line("PASS", G, f"SCH-3: alert scheduler idempotent harian ({len(dupes)} kunci unik)")

    # SCH-4 — Outbox WA: nomor E.164 Indonesia, status valid, 1 pesan/tujuan/kunci,
    #         tanpa kredensial tersimpan; + pengaturan provider konsisten
    bad4 = []
    seen_keys = set()
    for o in outbox:
        oid = o.get("id", "?")
        to = str(o.get("to") or "")
        if not (to.startswith("62") and 10 <= len(to) <= 15 and to.isdigit()):
            bad4.append(f"{oid}(nomor '{to}' tak ternormalisasi 62xx)")
        if o.get("status") not in VALID_WA_STATUS:
            bad4.append(f"{oid}(status {o.get('status')})")
        if o.get("severity") not in VALID_SEVERITY:
            bad4.append(f"{oid}(severity {o.get('severity')})")
        if not (o.get("text") or ""):
            bad4.append(f"{oid}(isi pesan kosong)")
        if set(o.keys()) & {"access_token", "fonnte_token"}:
            bad4.append(f"{oid}(KREDENSIAL BOCOR di outbox)")
        key = o.get("dedupe_key") or ""
        if key.startswith("wa_test:"):
            continue  # tes manual memang boleh berulang (kunci ber-timestamp)
        if key and key in seen_keys:
            bad4.append(f"{oid}(dedupe_key ganda)")
        seen_keys.add(key)
    wa = st.get("wa") or {}
    if wa:
        if wa.get("provider") and wa["provider"] not in VALID_PROVIDER:
            bad4.append(f"settings(provider {wa.get('provider')})")
        if wa.get("min_severity") and wa["min_severity"] not in VALID_SEVERITY:
            bad4.append(f"settings(min_severity {wa.get('min_severity')})")
        if wa.get("enabled") and wa.get("provider") == "meta_cloud" \
                and not (wa.get("access_token") and wa.get("phone_number_id")):
            bad4.append("settings(meta_cloud aktif tanpa kredensial)")
        if wa.get("enabled") and wa.get("provider") == "fonnte" and not wa.get("fonnte_token"):
            bad4.append("settings(fonnte aktif tanpa token)")
        pic = str(wa.get("pic_number") or "")
        if pic and not pic.startswith("62"):
            bad4.append(f"settings(pic_number '{pic}' tak ternormalisasi)")
    for jid, cfg in (st.get("jobs") or {}).items():
        for k, v in (cfg or {}).items():
            if k == "hour" and not (0 <= int(v) <= 23):
                bad4.append(f"jobs.{jid}(hour {v})")
            if k == "minute" and not (0 <= int(v) <= 59):
                bad4.append(f"jobs.{jid}(minute {v})")
            if k == "interval_hours" and not (1 <= int(v) <= 24):
                bad4.append(f"jobs.{jid}(interval {v})")
            if k not in ("enabled", "hour", "minute", "interval_hours"):
                bad4.append(f"jobs.{jid}(field asing '{k}')")
    if bad4:
        results["fail"] += 1
        line("FAIL", R, f"SCH-4: {len(bad4)} pelanggaran outbox/pengaturan WA: {bad4[:5]}",
             "→ nomor wajib 62xx, status valid, 1 pesan per kunci dedupe, kredensial "
             "hanya di system_settings (tidak pernah di outbox)")
    else:
        results["pass"] += 1
        line("PASS", G, f"SCH-4: outbox WA & pengaturan alert konsisten "
                        f"({len(outbox)} pesan · provider {wa.get('provider', 'simulated')})")

    # ── R6.6 ─────────────────────────────────────────────────────────────────
    esc_cfg = {"enabled": True, "after_hours": 8, "min_severity": "warning", "max_level": 2}
    esc_cfg.update(st.get("escalation") or {})

    # SCH-5 — rantai ESKALASI valid (R6.6): induk ditandai, tak ganda, level terbatas
    bad5 = []
    escals = [n for n in notifs if n.get("type") == "escalation"]
    by_id = {n.get("id"): n for n in notifs}
    parents_seen = {}
    max_level = int(esc_cfg.get("max_level", 2) or 2)
    for e in escals:
        eid = e.get("id", "?")
        parent_id = e.get("escalated_from") or ""
        if not parent_id:
            bad5.append(f"{eid}(tanpa escalated_from)")
            continue
        parents_seen[parent_id] = parents_seen.get(parent_id, 0) + 1
        parent = by_id.get(parent_id)
        if not parent:
            bad5.append(f"{eid}(induk {parent_id} tidak ada / yatim)")
            continue
        if e.get("severity") != "critical":
            bad5.append(f"{eid}(severity {e.get('severity')} != critical)")
        depth = int(e.get("escalation_depth", 0) or 0)
        if not 1 <= depth <= max_level:
            bad5.append(f"{eid}(depth {depth} di luar 1..{max_level})")
        if parent.get("escalation_level") != 1:
            bad5.append(f"{eid}(induk tidak ditandai escalation_level=1)")
        if parent.get("escalated_to") != e.get("recipient_role"):
            bad5.append(f"{eid}(penerima {e.get('recipient_role')} != escalated_to "
                        f"{parent.get('escalated_to')})")
        if parent.get("recipient_role") == "admin":
            bad5.append(f"{eid}(induk sudah level tertinggi, tak boleh dieskalasi)")
    ganda = [p for p, c in parents_seen.items() if c > 1]
    if ganda:
        bad5.append(f"eskalasi ganda untuk induk: {ganda[:3]}")
    # Induk bertanda escalation_level=1 wajib punya notifikasi eskalasi.
    for n in notifs:
        if int(n.get("escalation_level", 0) or 0) == 1 and n.get("id") not in parents_seen:
            bad5.append(f"{n.get('id')}(ditandai tereskalasi tapi notifikasi eskalasi hilang)")
    if bad5:
        results["fail"] += 1
        line("FAIL", R, f"SCH-5: {len(bad5)} pelanggaran rantai eskalasi: {bad5[:5]}",
             "→ 1 eskalasi per induk, severity critical, depth 1..max_level, "
             "induk ditandai escalation_level=1 + escalated_to == penerima eskalasi")
    else:
        results["pass"] += 1
        line("PASS", G, f"SCH-5: rantai eskalasi valid ({len(escals)} eskalasi · "
                        f"{len(parents_seen)} induk · batas {max_level} tingkat)")

    # SCH-6 — RINGKASAN HARIAN (digest) & konfigurasi kanal valid (R6.6)
    bad6 = []
    digests = [o for o in outbox if o.get("notif_type") == "daily_digest"]
    seen_digest = set()
    for d in digests:
        did = d.get("id", "?")
        day_d = (d.get("created_at") or "")[:10]
        if d.get("dedupe_key") != f"digest:{day_d}|{d.get('to')}":
            bad6.append(f"{did}(dedupe_key digest tidak standar)")
        if "RINGKASAN HARIAN" not in (d.get("text") or ""):
            bad6.append(f"{did}(isi bukan ringkasan)")
        if int(d.get("digest_alerts", 0) or 0) < 1 or int(d.get("digest_groups", 0) or 0) < 1:
            bad6.append(f"{did}(ringkasan tanpa alert/kelompok)")
        pair = (d.get("to"), day_d)
        if pair in seen_digest:
            bad6.append(f"{did}(ringkasan ganda untuk {d.get('to')} pada {day_d})")
        seen_digest.add(pair)
    mode = wa.get("delivery_mode", "instant")
    if mode not in ("instant", "digest"):
        bad6.append(f"settings(delivery_mode '{mode}' tidak dikenal)")
    if not isinstance(wa.get("critical_bypass", True), bool):
        bad6.append("settings(critical_bypass bukan bool)")
    if not isinstance(esc_cfg.get("enabled", True), bool):
        bad6.append("settings(escalation.enabled bukan bool)")
    if not 1 <= int(esc_cfg.get("after_hours", 8) or 8) <= 72:
        bad6.append(f"settings(escalation.after_hours {esc_cfg.get('after_hours')} di luar 1..72)")
    if not 1 <= max_level <= 3:
        bad6.append(f"settings(escalation.max_level {max_level} di luar 1..3)")
    if esc_cfg.get("min_severity") not in VALID_SEVERITY:
        bad6.append(f"settings(escalation.min_severity {esc_cfg.get('min_severity')})")
    for k in (esc_cfg or {}):
        if k not in ("enabled", "after_hours", "min_severity", "max_level"):
            bad6.append(f"settings(escalation field asing '{k}')")
    if bad6:
        results["fail"] += 1
        line("FAIL", R, f"SCH-6: {len(bad6)} pelanggaran ringkasan/konfigurasi kanal: {bad6[:5]}",
             "→ maks 1 ringkasan per nomor per hari, isi wajib ringkasan bergrup, "
             "delivery_mode instant|digest, kebijakan eskalasi dalam rentang valid")
    else:
        results["pass"] += 1
        line("PASS", G, f"SCH-6: ringkasan harian & konfigurasi kanal konsisten "
                        f"({len(digests)} ringkasan · mode {mode} · "
                        f"eskalasi {'aktif' if esc_cfg.get('enabled', True) else 'nonaktif'} "
                        f">{esc_cfg.get('after_hours')} jam)")


async def layer_domain_invariants(db):
    """Fase A — Invarian FONDASI DOMAIN TEKSTIL (KN_18 PS-01/02/03/09 · §11).

    INV-DOMAIN-01  products.stage ∈ enum stage (yarn|grey|pfd|pfp|finished|remnant|byproduct)
    INV-DOMAIN-02  products.fabric_type ∈ {woven, knit} — WAJIB sejak stage yarn (D-02/D-20)
    INV-DOMAIN-03  products/rolls.grade ∈ enum grade (A|A1|A2|B|BS) — D-01 (tak ada A+/C lagi)
    INV-DOMAIN-04  woven stage ≥ grey tanpa GSM/lebar WAJIB ditandai needs_review (D-22)
    INV-DOMAIN-05  inventory_rolls punya snapshot stage & fabric_type (PS-02)
    INV-DOMAIN-06  grade_history konsisten: entri terakhir.grade_after == roll.grade (PS-09)
    """
    print(f"\n{C}{B}L4-DOMAIN — Invarian Fondasi Domain Tekstil (KN_18 Fase A){X}")
    sys.path.insert(0, str(ROOT / "backend"))
    import domain_registry as dr

    stages, fabrics, grades = dr.values_of("stage"), dr.values_of("fabric_type"), dr.values_of("grade")
    products = await db.products.find({}, {"_id": 0}).to_list(20000)
    templates = await db.product_templates.find({}, {"_id": 0}).to_list(20000)
    rolls = await db.inventory_rolls.find({}, {"_id": 0}).to_list(50000)

    if not products:
        results["warn"] += 1
        line("WARN", Y, "products KOSONG — invarian domain dilewati")
        return

    # INV-DOMAIN-01
    bad_stage = [p.get("sku") for p in products + templates if (p.get("stage") or "") not in stages]
    if bad_stage:
        results["fail"] += 1
        line("FAIL", R, f"INV-DOMAIN-01: {len(bad_stage)} produk/template stage di luar enum", str(bad_stage[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-DOMAIN-01: {len(products) + len(templates)} produk/template stage valid")

    # INV-DOMAIN-02
    bad_fabric = [p.get("sku") for p in products + templates if (p.get("fabric_type") or "") not in fabrics]
    if bad_fabric:
        results["fail"] += 1
        line("FAIL", R, f"INV-DOMAIN-02: {len(bad_fabric)} produk/template tanpa fabric_type sah (D-02)",
             str(bad_fabric[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-DOMAIN-02: fabric_type (woven|knit) terisi di semua produk & template")

    # INV-DOMAIN-03
    bad_grade = [p.get("sku") for p in products + templates
                 if (p.get("grade") or "") and (p.get("grade") or "") not in grades]
    bad_roll_grade = [r.get("roll_no") for r in rolls if (r.get("grade") or "") not in grades]
    if bad_grade or bad_roll_grade:
        results["fail"] += 1
        line("FAIL", R, f"INV-DOMAIN-03: grade di luar enum — produk {len(bad_grade)}, roll {len(bad_roll_grade)}",
             str((bad_grade[:3], bad_roll_grade[:3])))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-DOMAIN-03: grade produk & {len(rolls)} roll memakai enum A|A1|A2|B|BS (D-01)")

    # INV-DOMAIN-04
    gap_unflagged = []
    for p in products:
        chk = dr.validate_product(p)
        if chk["errors"] and not p.get("needs_review"):
            gap_unflagged.append(p.get("sku"))
    if gap_unflagged:
        results["fail"] += 1
        line("FAIL", R, f"INV-DOMAIN-04: {len(gap_unflagged)} produk kurang lengkap tanpa needs_review",
             str(gap_unflagged[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-DOMAIN-04: produk dengan kelengkapan kurang selalu ditandai needs_review (D-22)")

    # INV-DOMAIN-05
    if rolls:
        no_snapshot = [r.get("roll_no") for r in rolls
                       if not (r.get("stage") or "") or not (r.get("fabric_type") or "")]
        if no_snapshot:
            results["fail"] += 1
            line("FAIL", R, f"INV-DOMAIN-05: {len(no_snapshot)} roll tanpa snapshot stage/fabric_type",
                 str(no_snapshot[:5]))
        else:
            results["pass"] += 1
            line("PASS", G, f"INV-DOMAIN-05: {len(rolls)} roll punya snapshot stage & fabric_type")

        # INV-DOMAIN-06
        hist_viol = []
        for r in rolls:
            hist = r.get("grade_history") or []
            if hist and (hist[-1].get("grade_after") or "") != (r.get("grade") or ""):
                hist_viol.append(r.get("roll_no"))
        if hist_viol:
            results["fail"] += 1
            line("FAIL", R, f"INV-DOMAIN-06: {len(hist_viol)} roll grade ≠ entri terakhir grade_history",
                 str(hist_viol[:5]))
        else:
            n_hist = sum(1 for r in rolls if r.get("grade_history"))
            results["pass"] += 1
            line("PASS", G, f"INV-DOMAIN-06: riwayat grade konsisten ({n_hist} roll punya grade_history)")


async def layer_ps21_invariants(db):
    """PS-21 — Invarian NOTIFIKASI OPERASIONAL & REPEAT/RESTOCK (KN_18 §A.3).

    INV-PS21-01  notifikasi job baru (po_arrival/backorder_ready/ar_due_soon) ter-dedupe
                 harian: `dedupe_key` = "<type>:<ref>:<hari>" & unik
    INV-PS21-02  ref `ar_due_soon` memuat offset sah (H-3|H-1|H+0|H+1) → tidak ada
                 pengingat di offset liar
    INV-PS21-03  jejak dua arah restock: SO.restock_requests[].pr_id ⟺ PR(source=so_repeat)
                 dengan source_ref_id = SO.id
    INV-PS21-04  PR hasil restock memakai satuan & produk yang ADA di master (tanpa item hantu)
    """
    print(f"\n{C}{B}L4-PS21 — Invarian Notifikasi Operasional & Repeat/Restock{X}")
    PS21_TYPES = ["po_arrival", "backorder_ready", "ar_due_soon"]
    notifs = await db.notifications.find(
        {"type": {"$in": PS21_TYPES}}, {"_id": 0}).to_list(20000)

    # INV-PS21-01
    bad_key, keys = [], []
    for n in notifs:
        key, ref = n.get("dedupe_key") or "", n.get("ref") or ""
        day = (n.get("created_at") or "")[:10]
        keys.append(key)
        if not key or not ref or not key.endswith(day) or not key.startswith(n.get("type", "")):
            bad_key.append(n.get("id"))
    dupes = len(keys) - len(set(keys))
    if bad_key or dupes:
        results["fail"] += 1
        line("FAIL", R, f"INV-PS21-01: dedupe harian rusak — {len(bad_key)} kunci cacat, "
                        f"{dupes} duplikat", str(bad_key[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-PS21-01: {len(notifs)} notifikasi operasional ter-dedupe "
                        "harian (kunci unik & konsisten)")

    # INV-PS21-02
    ALLOWED = ("H-3", "H-1", "H+0", "H+1")
    bad_offset = [n.get("id") for n in notifs
                  if n.get("type") == "ar_due_soon"
                  and not any(o in (n.get("ref") or "") for o in ALLOWED)]
    if bad_offset:
        results["fail"] += 1
        line("FAIL", R, f"INV-PS21-02: {len(bad_offset)} notifikasi ar_due_soon di offset "
                        "tidak sah", str(bad_offset[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-PS21-02: pengingat piutang hanya pada offset H-3/H-1/H/H+1")

    # INV-PS21-03 + INV-PS21-04
    orders = await db.sales_orders.find(
        {"restock_requests": {"$exists": True, "$ne": []}}, {"_id": 0}).to_list(5000)
    pr_ids = [r.get("pr_id") for o in orders for r in (o.get("restock_requests") or [])]
    prs = await db.purchase_requisitions.find(
        {"id": {"$in": pr_ids}}, {"_id": 0}).to_list(5000)
    prmap = {p["id"]: p for p in prs}
    broken = []
    for o in orders:
        for r in (o.get("restock_requests") or []):
            pr = prmap.get(r.get("pr_id"))
            if (not pr or pr.get("source") != "so_repeat"
                    or pr.get("source_ref_id") != o.get("id")
                    or pr.get("number") != r.get("pr_number")):
                broken.append(f"{o.get('number')}→{r.get('pr_number')}")
    if broken:
        results["fail"] += 1
        line("FAIL", R, f"INV-PS21-03: {len(broken)} jejak restock SO↔PR tidak konsisten",
             str(broken[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-PS21-03: jejak dua arah restock konsisten "
                        f"({len(pr_ids)} PR dari {len(orders)} order)")

    prod_ids = {p["id"] for p in await db.products.find({}, {"_id": 0, "id": 1}).to_list(20000)}
    ghost = [f"{p.get('number')}:{it.get('product_id')}" for p in prs
             for it in (p.get("items") or [])
             if it.get("product_id") and it["product_id"] not in prod_ids]
    if ghost:
        results["fail"] += 1
        line("FAIL", R, f"INV-PS21-04: {len(ghost)} item PR restock menunjuk produk tak ada",
             str(ghost[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-PS21-04: seluruh item PR restock menunjuk produk master yang sah")


async def layer_uom_invariants(db):
    """FASE B — Invarian KONVERSI SATUAN (KN_18 §11 D-06/D-07).

    INV-UOM-01  aturan global sah: satuan terisi, faktor > 0 (kecuali formula), tanpa
                self-pair, dan HANYA SATU aturan aktif per pasangan (from,to)
    INV-UOM-02  jejak konversi konsisten: `uom_trail.base_qty ≈ doc_qty × factor` dan
                sama dengan `quantity_base` baris dokumen (tidak ada dua angka berbeda)
    INV-UOM-03  pengaturan toleransi sah: 0 < warn_pct ≤ block_pct ≤ 100, precision 0–6
    INV-UOM-04  selisih konversi di luar toleransi WAJIB ditandai (needs_review) dan
                yang di atas batas blokir wajib punya alasan override
    """
    print(f"\n{C}{B}L4-UOM — Invarian Konversi Satuan (Fase B · D-06/D-07){X}")
    sys.path.insert(0, str(ROOT / "backend"))
    rules = await db.uom_conversion_rules.find({}, {"_id": 0}).to_list(5000)

    # INV-UOM-01
    bad, seen = [], {}
    for r in rules:
        fu, tu = (r.get("from_unit") or "").strip(), (r.get("to_unit") or "").strip()
        kind = r.get("kind") or "fixed"
        if not fu or not tu or fu == tu:
            bad.append(f"{r.get('id')}:pasangan")
            continue
        if kind != "formula" and float(r.get("factor") or 0) <= 0:
            bad.append(f"{fu}->{tu}:faktor")
        if r.get("status") == "active":
            key = (fu, tu)
            if key in seen:
                bad.append(f"{fu}->{tu}:ganda")
            seen[key] = r.get("id")
    if bad:
        results["fail"] += 1
        line("FAIL", R, f"INV-UOM-01: {len(bad)} aturan konversi tidak sah", str(bad[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-UOM-01: {len(rules)} aturan konversi sah "
                        f"({len(seen)} pasangan aktif unik)")

    # INV-UOM-02
    mismatch, trailed = [], 0
    for coll, num in (("purchase_orders", "po_number"), ("purchase_requisitions", "number")):
        docs = await db[coll].find({"items.uom_trail": {"$exists": True}},
                                   {"_id": 0, num: 1, "items": 1}).to_list(20000)
        for d in docs:
            for it in d.get("items") or []:
                t = it.get("uom_trail") or {}
                if not t:
                    continue
                trailed += 1
                factor = t.get("factor")
                if factor in (None, ""):
                    mismatch.append(f"{d.get(num)}:{it.get('sku')}:tanpa-faktor")
                    continue
                calc = round(float(t.get("doc_qty") or 0) * float(factor), 2)
                if abs(calc - float(t.get("base_qty") or 0)) > 0.05:
                    mismatch.append(f"{d.get(num)}:{it.get('sku')}:jejak")
                if it.get("quantity_base") is not None and abs(
                        float(it["quantity_base"]) - float(t.get("base_qty") or 0)) > 0.05:
                    mismatch.append(f"{d.get(num)}:{it.get('sku')}:base_qty")
    if mismatch:
        results["fail"] += 1
        line("FAIL", R, f"INV-UOM-02: {len(mismatch)} jejak konversi tidak konsisten",
             str(mismatch[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-UOM-02: {trailed} baris dokumen berjejak konversi konsisten "
                        "(doc_qty × faktor == base_qty == quantity_base)")

    # INV-UOM-03
    st = await db.system_settings.find_one({"scope": "uom"}, {"_id": 0}) or {}
    warn, block = float(st.get("warn_pct", 0) or 0), float(st.get("block_pct", 0) or 0)
    prec = int(st.get("precision", 2) or 0)
    if not st:
        results["warn"] += 1
        line("WARN", Y, "INV-UOM-03: pengaturan toleransi konversi belum ada (jalankan migrasi)")
    elif not (0 < warn <= block <= 100) or not (0 <= prec <= 6):
        results["fail"] += 1
        line("FAIL", R, f"INV-UOM-03: pengaturan toleransi tidak sah (warn {warn}, "
                        f"block {block}, precision {prec})")
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-UOM-03: toleransi sah (peringatan {warn:g}% ≤ blokir {block:g}%, "
                        f"pembulatan {prec})")

    # INV-UOM-04
    tasks = await db.wms_tasks.find({"conversion_variance": {"$exists": True}},
                                    {"_id": 0, "id": 1, "po_number": 1,
                                     "conversion_variance": 1, "needs_review": 1}).to_list(20000)
    viol = []
    for t in tasks:
        v = t.get("conversion_variance") or {}
        lvl = v.get("level")
        if lvl in ("warn", "block") and not t.get("needs_review"):
            viol.append(f"{t.get('po_number') or t.get('id')}:tanpa-review")
        if lvl == "block" and not (v.get("override_reason") or "").strip():
            viol.append(f"{t.get('po_number') or t.get('id')}:tanpa-alasan")
    if viol:
        results["fail"] += 1
        line("FAIL", R, f"INV-UOM-04: {len(viol)} penerimaan dengan selisih konversi tak tertangani",
             str(viol[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-UOM-04: {len(tasks)} penerimaan dengan cek selisih konversi "
                        "ditandai & beralasan sesuai kebijakan")


async def layer_lot_invariants(db):
    """FASE C — Invarian LOT KELAS SATU (KN_18 PS-10 · D-10/D-26/D-27).

    INV-LOT-01  nomor lot sah & unik: format `(KODE/)LOT-YYMM-####`, tidak duplikat,
                dan setiap lot menunjuk produk + pemilik (entitas) yang ada
    INV-LOT-02  keterhubungan roll: `roll.lot_id` menunjuk lot yang ADA; roll stage
                ≥ grey tanpa lot = **WARN** (keputusan pemilik: mode peringatan)
    INV-LOT-03  genealogi konsisten: relasi parent/child dua arah & TANPA siklus
    INV-LOT-04  agregat lot = Σ roll (roll_count / qty_initial / qty_remaining) —
                proyeksi selalu turunan roll, tidak pernah $inc
    INV-LOT-05  lot tidak lintas produk / lintas pemilik (integritas batch)
    """
    print(f"\n{C}{B}L4-LOT — Invarian Lot Kelas Satu (Fase C · D-10/D-26/D-27){X}")
    lots = await db.inventory_lots.find({}, {"_id": 0}).to_list(50000)
    rolls = await db.inventory_rolls.find(
        {}, {"_id": 0, "id": 1, "lot_id": 1, "product_id": 1, "owner_entity_id": 1,
             "stage": 1, "length_initial": 1, "length_remaining": 1, "status": 1,
             "lot": 1}).to_list(200000)
    by_lot = {}
    for r in rolls:
        if r.get("lot_id"):
            by_lot.setdefault(r["lot_id"], []).append(r)
    lot_ids = {l["id"] for l in lots}

    # ── INV-LOT-01 ──────────────────────────────────────────────────────────
    num_re = re.compile(r"^(?:[A-Z0-9]+/)?LOT-\d{4}-\d{4,}$")
    product_ids = {p["id"] for p in await db.products.find({}, {"_id": 0, "id": 1}).to_list(50000)}
    entity_ids = {e["id"] for e in await db.business_entities.find(
        {}, {"_id": 0, "id": 1}).to_list(1000)}
    bad, seen = [], {}
    for l in lots:
        num = (l.get("lot_number") or "").strip()
        if not num_re.match(num):
            bad.append(f"{l.get('id')}:format({num})")
        if num in seen:
            bad.append(f"{num}:ganda")
        seen[num] = l["id"]
        if l.get("product_id") not in product_ids:
            bad.append(f"{num}:produk")
        if entity_ids and l.get("owner_entity_id") not in entity_ids:
            bad.append(f"{num}:owner")
    if bad:
        results["fail"] += 1
        line("FAIL", R, f"INV-LOT-01: {len(bad)} lot dengan nomor/referensi tidak sah", str(bad[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-LOT-01: {len(lots)} lot bernomor sah & unik "
                        f"(format LOT-YYMM-#### per entitas)")

    # ── INV-LOT-02 ──────────────────────────────────────────────────────────
    dangling = [r["id"] for r in rolls if r.get("lot_id") and r["lot_id"] not in lot_ids]
    if dangling:
        results["fail"] += 1
        line("FAIL", R, f"INV-LOT-02: {len(dangling)} roll menunjuk lot yang tidak ada",
             str(dangling[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-LOT-02: {sum(len(v) for v in by_lot.values())} roll tertaut lot yang sah")
    stage_order = {"yarn": 1, "grey": 2, "pfd": 3, "pfp": 3, "finished": 4}
    missing = [r["id"] for r in rolls
               if not r.get("lot_id") and stage_order.get(r.get("stage") or "", 0) >= 2]
    if missing:
        results["warn"] += 1
        line("WARN", Y, f"INV-LOT-02: {len(missing)} roll stage ≥ grey belum bertaut lot "
                        f"(mode peringatan — jalankan migrate_fase_c_lots.py)", str(missing[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-LOT-02: tidak ada roll stage ≥ grey tanpa lot")

    # ── INV-LOT-03 ──────────────────────────────────────────────────────────
    viol = []
    parents = {l["id"]: set(l.get("parent_lot_ids") or []) for l in lots}
    children = {l["id"]: set(l.get("child_lot_ids") or []) for l in lots}
    for lid, pset in parents.items():
        for pid in pset:
            if pid not in lot_ids:
                viol.append(f"{lid}:induk-hilang")
            elif lid not in children.get(pid, set()):
                viol.append(f"{lid}:tak-dua-arah")
    for lid, cset in children.items():
        for cid in cset:
            if cid not in lot_ids:
                viol.append(f"{lid}:anak-hilang")
            elif lid not in parents.get(cid, set()):
                viol.append(f"{lid}:tak-dua-arah")

    def _has_cycle(start):
        stack, seen_ids = [start], set()
        while stack:
            cur = stack.pop()
            if cur in seen_ids:
                continue
            seen_ids.add(cur)
            for nxt in children.get(cur, set()):
                if nxt == start:
                    return True
                stack.append(nxt)
        return False

    cycles = [lid for lid in lot_ids if _has_cycle(lid)]
    if viol or cycles:
        results["fail"] += 1
        line("FAIL", R, f"INV-LOT-03: genealogi tidak konsisten ({len(viol)} relasi, "
                        f"{len(cycles)} siklus)", str((viol[:3] + cycles[:3])))
    else:
        edges = sum(len(v) for v in parents.values())
        results["pass"] += 1
        line("PASS", G, f"INV-LOT-03: genealogi dua arah & bebas siklus ({edges} relasi induk-anak)")

    # ── INV-LOT-04 ──────────────────────────────────────────────────────────
    drift = []
    for l in lots:
        members = by_lot.get(l["id"], [])
        exp_count = len(members)
        exp_init = round(sum(float(m.get("length_initial") or 0) for m in members), 3)
        exp_rem = round(sum(float(m.get("length_remaining") or 0) for m in members), 3)
        if int(l.get("roll_count") or 0) != exp_count:
            drift.append(f"{l.get('lot_number')}:roll_count({l.get('roll_count')}≠{exp_count})")
        if abs(float(l.get("qty_initial") or 0) - exp_init) > 0.05:
            drift.append(f"{l.get('lot_number')}:qty_initial")
        if abs(float(l.get("qty_remaining") or 0) - exp_rem) > 0.05:
            drift.append(f"{l.get('lot_number')}:qty_remaining")
    if drift:
        results["fail"] += 1
        line("FAIL", R, f"INV-LOT-04: {len(drift)} agregat lot menyimpang dari Σ roll",
             str(drift[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-LOT-04: agregat {len(lots)} lot == Σ roll (proyeksi murni turunan)")

    # ── INV-LOT-05 ──────────────────────────────────────────────────────────
    mixed = []
    for l in lots:
        members = by_lot.get(l["id"], [])
        if any(m.get("product_id") != l.get("product_id") for m in members):
            mixed.append(f"{l.get('lot_number')}:produk")
        if any((m.get("owner_entity_id") or "") != l.get("owner_entity_id") for m in members):
            mixed.append(f"{l.get('lot_number')}:owner")
    if mixed:
        results["fail"] += 1
        line("FAIL", R, f"INV-LOT-05: {len(mixed)} lot bercampur produk/pemilik", str(mixed[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-LOT-05: tidak ada lot lintas produk/pemilik (integritas batch)")

    # ── Pengaturan penegakan (D-27) ────────────────────────────────────────
    st = await db.system_settings.find_one({"scope": "lot"}, {"_id": 0}) or {}
    if not st:
        results["warn"] += 1
        line("WARN", Y, "INV-LOT-06: pengaturan penegakan lot belum ada "
                        "(jalankan migrate_fase_c_lots.py)")
    elif st.get("enforcement_mode") not in ("warn", "block"):
        results["fail"] += 1
        line("FAIL", R, f"INV-LOT-06: mode penegakan lot tidak sah ({st.get('enforcement_mode')})")
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-LOT-06: penegakan lot = {st.get('enforcement_mode')} "
                        f"(supplier_lot wajib: {bool(st.get('require_supplier_lot'))}, "
                        f"dye_lot wajib: {bool(st.get('require_dye_lot'))})")


async def layer_makloon_invariants(db):
    """FASE D — Invarian MAKLOON RANTAI PROSES (KN_18 PS-03/PS-04/PS-08/PS-11).

    INV-MKO-01  rantai langkah nyambung: output langkah N == input langkah N+1
                dan setiap langkah punya produk output (KN_18 §5.2)
    INV-MKO-02  langkah `received` punya lot output ber-`lot_id` + genealogi induk
                (integrasi Fase C tidak boleh putus)
    INV-MKO-03  jejak tarif: langkah dengan tarif > 0 menyimpan basis + jejak
                perhitungan/konversi (D-07 “wajib jejak”)
    INV-MKO-04  rekonsiliasi nilai langkah: output_value == material + jasa + aux − sisa
                (FASE T: + jasa yang DISERAP dari langkah jasa-murni, − jasa yang
                DITERUSKAN oleh langkah jasa-murni itu sendiri)
    INV-MKO-05  klaim sah: status ∈ registry, klaim `approved` punya penyetuju + nilai,
                `potong_bon` menunjuk vendor bill yang ada
    INV-MKO-06  kontrak: `steps[].contract_id` menunjuk `supplier_contracts` yang ada;
                nomor kontrak unik & sesuai format `(KODE/)SCT-#####`
    INV-MKO-07  FASE T — biaya jasa langkah "jasa murni" (mis. pembuatan kasa/screen)
                tidak boleh HILANG: Σ jasa-murni == Σ yang diserap langkah kain +
                yang masih menggantung + yang dibebankan sbg tak terserap
    """
    import re as _re
    print(f"\n{C}{B}L4-MKO — Invarian Makloon Rantai Proses (Fase D · D-05/D-07/D-09 · FASE T){X}")
    orders = await db.makloon_orders.find({}, {"_id": 0}).to_list(20000)
    contracts = await db.supplier_contracts.find({}, {"_id": 0}).to_list(20000)
    lots = {l["id"] for l in await db.inventory_lots.find({}, {"_id": 0, "id": 1}).to_list(100000)}
    bills = {b["id"] for b in await db.vendor_bills.find({}, {"_id": 0, "id": 1}).to_list(50000)}
    EPS = 1.0

    def _service_only(s) -> bool:
        """FASE T — langkah yang TIDAK memindahkan kain (jasa murni).

        Dibaca dari `material_flow` langkah, bukan dari `process_type`: "screen" boleh
        dijalankan dua cara (kain dikirim / jasa saja) dan invariannya berbeda untuk
        masing-masing. Langkah sebelum FASE T tidak punya field ini → dianggap
        memindahkan kain, persis seperti perilakunya dulu.
        """
        return str(s.get("material_flow") or "moves") == "service_only"

    # ── INV-MKO-01 rantai & produk output ───────────────────────────────────
    broken, no_output = [], []
    for o in orders:
        steps = sorted(o.get("steps", []), key=lambda s: int(s.get("seq") or 0))
        for i, s in enumerate(steps):
            if not s.get("output_product_id"):
                no_output.append(f"{o.get('mko_number')}#{s.get('seq')}")
            if i > 0:
                prev_out = steps[i - 1].get("output_product_id")
                if prev_out and s.get("input_product_id") and s["input_product_id"] != prev_out:
                    broken.append(f"{o.get('mko_number')}#{s.get('seq')}")
    if broken:
        results["fail"] += 1
        line("FAIL", R, f"INV-MKO-01: {len(broken)} langkah rantai terputus (input≠output sebelumnya)",
             str(broken[:5]))
    elif no_output:
        results["warn"] += 1
        line("WARN", Y, f"INV-MKO-01: {len(no_output)} langkah lama tanpa produk output "
                        "(data sebelum Fase D)", str(no_output[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-MKO-01: rantai {len(orders)} order makloon nyambung & "
                        "setiap langkah punya produk output")

    # ── INV-MKO-02 lot output & genealogi ───────────────────────────────────
    lot_missing, genealogy_missing = [], []
    for o in orders:
        for s in o.get("steps", []):
            if s.get("status") != "received":
                continue
            # FASE T — langkah jasa murni tidak menyentuh kain: tidak ada roll yang
            # lahir, jadi tidak ada lot yang bisa dituntut. Menuntutnya di sini akan
            # membuat gate memerah untuk pekerjaan yang memang tidak menghasilkan kain.
            if _service_only(s):
                continue
            step_lots = [l.get("lot_id") for l in (s.get("lots") or [])]
            if not step_lots or not all(step_lots):
                lot_missing.append(f"{o.get('mko_number')}#{s.get('seq')}")
                continue
            if any(lid not in lots for lid in step_lots):
                genealogy_missing.append(f"{o.get('mko_number')}#{s.get('seq')}")
    if lot_missing or genealogy_missing:
        results["fail"] += 1
        line("FAIL", R, f"INV-MKO-02: {len(lot_missing)} langkah tanpa lot output · "
                        f"{len(genealogy_missing)} menunjuk lot yang hilang",
             str((lot_missing + genealogy_missing)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-MKO-02: semua penerimaan makloon melahirkan lot output valid "
                        "(genealogi Fase C utuh)")

    # ── INV-MKO-03 jejak tarif ──────────────────────────────────────────────
    no_trace = []
    for o in orders:
        for s in o.get("steps", []):
            if s.get("status") != "received":
                continue
            if float(s.get("tariff") or 0) <= 0:
                continue
            trace = s.get("tariff_actual") or s.get("tariff_plan") or {}
            if not trace.get("basis") and not trace.get("source"):
                no_trace.append(f"{o.get('mko_number')}#{s.get('seq')}")
    if no_trace:
        results["warn"] += 1
        line("WARN", Y, f"INV-MKO-03: {len(no_trace)} langkah lama tanpa jejak basis tarif "
                        "(order sebelum Fase D)", str(no_trace[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-MKO-03: setiap ongkos jasa menyimpan basis & jejak perhitungan (D-07)")

    # ── INV-MKO-04 rekonsiliasi nilai langkah ───────────────────────────────
    # FASE T menambah dua aliran yang harus masuk persamaan, kalau tidak gate ini
    # memerah untuk perilaku yang MEMANG dirancang:
    #   · langkah jasa murni MENERUSKAN biayanya (output_value-nya 0 — tidak ada kain);
    #   · langkah kain berikutnya MENYERAPnya (`absorbed_service_value`) sehingga
    #     biaya kasa mendarat di HPP kain cetak, bukan menggantung di WIP.
    drift = []
    for o in orders:
        for s in o.get("steps", []):
            if s.get("status") != "received":
                continue
            svc = float(s.get("service_value") or 0)
            absorbed = float(s.get("absorbed_service_value") or 0)
            carried = svc if _service_only(s) else 0.0
            calc = (float(s.get("material_value") or 0) + svc + absorbed
                    - float(s.get("byproduct_value") or 0) - carried)
            if abs(calc - float(s.get("output_value") or 0)) > EPS:
                drift.append(f"{o.get('mko_number')}#{s.get('seq')}"
                             f"(Δ{round(calc - float(s.get('output_value') or 0), 2)})")
    if drift:
        results["fail"] += 1
        line("FAIL", R, f"INV-MKO-04: {len(drift)} langkah nilai output tidak rekonsiliasi "
                        "(bahan+jasa+jasa_diserap−sisa−jasa_diteruskan ≠ output)", str(drift[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-MKO-04: nilai output tiap langkah = bahan + jasa + jasa diserap "
                        "− barang sisa − jasa diteruskan (WIP di-clear penuh)")

    # ── INV-MKO-07 (FASE T) jasa murni tidak boleh HILANG ───────────────────
    # Biaya pembuatan kasa masuk WIP saat dicatat. Ia hanya boleh keluar lewat TIGA
    # pintu: diserap HPP kain, masih menggantung (SPK belum selesai), atau dibebankan
    # sebagai "tak terserap". Kalau jumlahnya tidak sama, ada uang yang menguap dari
    # WIP tanpa jejak — kelas bug yang paling mahal karena tak ada yang melihatnya.
    svc_drift = []
    n_service_steps = 0
    for o in orders:
        produced = 0.0
        absorbed = 0.0
        for s in o.get("steps", []):
            if s.get("status") == "received" and _service_only(s):
                produced += float(s.get("service_value") or 0)
                n_service_steps += 1
            absorbed += float(s.get("absorbed_service_value") or 0)
        pending = float(o.get("service_absorption_pending") or 0)
        unabsorbed = float((o.get("costing") or {}).get("service_unabsorbed") or 0)
        if abs(produced - (absorbed + pending + unabsorbed)) > EPS:
            svc_drift.append(
                f"{o.get('mko_number')}(jasa {produced:.0f} ≠ diserap {absorbed:.0f} + "
                f"menggantung {pending:.0f} + beban {unabsorbed:.0f})")
    if svc_drift:
        results["fail"] += 1
        line("FAIL", R, f"INV-MKO-07: {len(svc_drift)} SPK — biaya jasa murni tidak "
                        "terlacak penuh", str(svc_drift[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-MKO-07: {n_service_steps} langkah jasa murni (FASE T) — "
                        "biayanya terlacak penuh (diserap HPP / menggantung / dibebankan)")

    # ── INV-MKO-05 klaim sah ────────────────────────────────────────────────
    valid_status = {"none", "open", "pending_approval", "approved", "rejected"}
    valid_action = {"", "potong_bon", "tagih_ganti", "terima_catatan"}
    bad_claims = []
    approved_n = 0
    for o in orders:
        for s in o.get("steps", []):
            c = s.get("claim") or {}
            if not c:
                continue
            ref = f"{o.get('mko_number')}#{s.get('seq')}"
            if c.get("status") not in valid_status or c.get("action", "") not in valid_action:
                bad_claims.append(f"{ref}:status")
                continue
            if c.get("status") == "approved":
                approved_n += 1
                if not c.get("approved_by"):
                    bad_claims.append(f"{ref}:tanpa-penyetuju")
                if c.get("action") in ("potong_bon", "tagih_ganti") and float(c.get("amount") or 0) <= 0:
                    bad_claims.append(f"{ref}:nilai-0")
                if c.get("action") == "potong_bon":
                    bid = (c.get("effect") or {}).get("bill_id")
                    if bid and bid not in bills:
                        bad_claims.append(f"{ref}:bill-hilang")
    if bad_claims:
        results["fail"] += 1
        line("FAIL", R, f"INV-MKO-05: {len(bad_claims)} klaim tidak sah", str(bad_claims[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-MKO-05: klaim selisih valid ({approved_n} disetujui dengan "
                        "penyetuju, nilai & dokumen turunan)")

    # ── INV-MKO-06 kontrak ──────────────────────────────────────────────────
    cid_set = {c["id"] for c in contracts}
    dangling = []
    for o in orders:
        for s in o.get("steps", []):
            if s.get("contract_id") and s["contract_id"] not in cid_set:
                dangling.append(f"{o.get('mko_number')}#{s.get('seq')}")
    num_re = _re.compile(r"^(?:[A-Z0-9]+/)?SCT-\d{4,}$")
    bad_num = [c.get("contract_number") for c in contracts
               if not num_re.match(str(c.get("contract_number") or ""))]
    nums = [c.get("contract_number") for c in contracts]
    dup = len(nums) - len(set(nums))
    if dangling or bad_num or dup:
        results["fail"] += 1
        line("FAIL", R, f"INV-MKO-06: {len(dangling)} langkah menunjuk kontrak hilang · "
                        f"{len(bad_num)} nomor tidak sah · {dup} duplikat",
             str((dangling + bad_num)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-MKO-06: {len(contracts)} kontrak mitra bernomor sah & semua "
                        "referensi langkah valid")


async def layer_sourcing_invariants(db):
    """FASE E — Invarian SOURCING BERBASIS KONTRAK (KN_18 PS-06 · E-01/E-02/E-03).

    INV-SRC-01  `purchase_requisitions.items[].fulfillment_mode` ∈ (purchase|makloon);
                `line_no` unik per PR; baris makloon WAJIB punya product_id
    INV-SRC-02  realisasi tidak melebihi kebutuhan: Σ realizations[].qty == realized_qty
                dan realized_qty ≤ quantity (toleransi 0,01)
    INV-SRC-03  status realisasi turunan konsisten: `realization_status` == hasil hitung
                dari baris; PR `converted` ⟹ semua baris terealisasi penuh
    INV-SRC-04  referensi realisasi hidup: setiap `realizations[].ref_id` menunjuk
                purchase_orders / makloon_orders yang ADA
    INV-SRC-05  `supplier_items` sehat: (supplier_id, supplier_sku) unik, product_id &
                supplier_id valid, conv_factor > 0; referensi `supplier_item_id` pada
                baris PO menunjuk barang supplier yang ada
    """
    print(f"\n{C}{B}L4-SRC — Invarian Sourcing Berbasis Kontrak (Fase E · E-01/E-02/E-03){X}")
    prs = await db.purchase_requisitions.find({}, {"_id": 0}).to_list(20000)
    sitems = await db.supplier_items.find({}, {"_id": 0}).to_list(50000)
    pos = await db.purchase_orders.find({}, {"_id": 0}).to_list(50000)
    po_ids = {p["id"] for p in pos}
    mko_ids = {m["id"] for m in await db.makloon_orders.find({}, {"_id": 0, "id": 1}).to_list(20000)}
    prod_ids = {p["id"] for p in await db.products.find({}, {"_id": 0, "id": 1}).to_list(20000)}
    sup_ids = {s["id"] for s in await db.suppliers.find({}, {"_id": 0, "id": 1}).to_list(20000)}
    EPS = 0.011
    VALID_MODES = ("purchase", "makloon")

    # ── INV-SRC-01 mode & line_no ───────────────────────────────────────────
    bad_mode, dup_line, makloon_no_prod = [], [], []
    for pr in prs:
        seen = set()
        for it in pr.get("items") or []:
            mode = it.get("fulfillment_mode")
            if mode is not None and mode not in VALID_MODES:
                bad_mode.append(f"{pr.get('number')}#{it.get('line_no')}={mode}")
            ln = it.get("line_no")
            if ln is not None:
                if ln in seen:
                    dup_line.append(f"{pr.get('number')}#{ln}")
                seen.add(ln)
            if mode == "makloon" and not it.get("product_id"):
                makloon_no_prod.append(f"{pr.get('number')}#{ln}")
    if bad_mode or dup_line or makloon_no_prod:
        results["fail"] += 1
        line("FAIL", R, f"INV-SRC-01: {len(bad_mode)} mode tak dikenal · {len(dup_line)} line_no "
                        f"duplikat · {len(makloon_no_prod)} baris makloon tanpa produk",
             str((bad_mode + dup_line + makloon_no_prod)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-SRC-01: routing pemenuhan {len(prs)} PR valid "
                        "(mode ∈ purchase|makloon · line_no unik · baris makloon berkatalog)")

    # ── INV-SRC-02 realisasi tidak melebihi kebutuhan ───────────────────────
    over, drift = [], []
    for pr in prs:
        for it in pr.get("items") or []:
            qty = float(it.get("quantity") or 0)
            done = float(it.get("realized_qty") or 0)
            rsum = round(sum(float(r.get("qty") or 0) for r in (it.get("realizations") or [])), 3)
            if done > qty + EPS:
                over.append(f"{pr.get('number')}#{it.get('line_no')}:{done}>{qty}")
            if it.get("realizations") is not None and abs(rsum - done) > EPS:
                drift.append(f"{pr.get('number')}#{it.get('line_no')}:{rsum}≠{done}")
    if over or drift:
        results["fail"] += 1
        line("FAIL", R, f"INV-SRC-02: {len(over)} realisasi melebihi kebutuhan · "
                        f"{len(drift)} jumlah realisasi tidak cocok", str((over + drift)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-SRC-02: realisasi PR ≤ kebutuhan & Σ jejak == realized_qty")

    # ── INV-SRC-03 status realisasi turunan ─────────────────────────────────
    bad_status, bad_converted = [], []
    for pr in prs:
        items = pr.get("items") or []
        if not any(it.get("realizations") is not None for it in items):
            continue                      # PR lama tanpa jejak Fase E — dilewati
        total_lines = len([i for i in items if float(i.get("quantity") or 0) > 0])
        done_lines = sum(1 for i in items
                         if float(i.get("realized_qty") or 0) >= float(i.get("quantity") or 0) - EPS
                         and float(i.get("quantity") or 0) > 0)
        done_qty = sum(float(i.get("realized_qty") or 0) for i in items)
        want = "open" if done_qty <= EPS else ("realized" if done_lines >= total_lines
                                              else "partially_realized")
        got = pr.get("realization_status")
        if got and got != want:
            bad_status.append(f"{pr.get('number')}:{got}≠{want}")
        if pr.get("status") == "converted" and want != "realized" and got:
            bad_converted.append(f"{pr.get('number')}:{want}")
    if bad_status or bad_converted:
        results["fail"] += 1
        line("FAIL", R, f"INV-SRC-03: {len(bad_status)} status realisasi menyimpang · "
                        f"{len(bad_converted)} PR 'converted' belum penuh",
             str((bad_status + bad_converted)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-SRC-03: status realisasi PR konsisten dengan baris (turunan murni)")

    # ── INV-SRC-04 referensi realisasi hidup ────────────────────────────────
    dangling = []
    for pr in prs:
        for it in pr.get("items") or []:
            for r in (it.get("realizations") or []):
                rid, kind = r.get("ref_id"), r.get("type")
                if kind == "purchase_order" and rid not in po_ids:
                    dangling.append(f"{pr.get('number')}#{it.get('line_no')}→PO {rid}")
                elif kind == "makloon_order" and rid not in mko_ids:
                    dangling.append(f"{pr.get('number')}#{it.get('line_no')}→MKO {rid}")
    if dangling:
        results["fail"] += 1
        line("FAIL", R, f"INV-SRC-04: {len(dangling)} jejak realisasi menunjuk dokumen hilang",
             str(dangling[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-SRC-04: semua jejak realisasi PR menunjuk PO/Order Makloon yang ada")

    # ── INV-SRC-05 kesehatan supplier_items + referensi PO ──────────────────
    seen_key, dup_key, bad_ref, bad_conv = set(), [], [], []
    for si in sitems:
        key = (si.get("supplier_id"), si.get("supplier_sku"))
        if key in seen_key:
            dup_key.append(f"{si.get('supplier_id')}/{si.get('supplier_sku')}")
        seen_key.add(key)
        if si.get("supplier_id") not in sup_ids:
            bad_ref.append(f"{si.get('id')}:supplier")
        if si.get("product_id") not in prod_ids:
            bad_ref.append(f"{si.get('id')}:produk")
        if float(si.get("conv_factor") or 0) <= 0:
            bad_conv.append(si.get("id"))
    sit_ids = {s["id"] for s in sitems}
    po_dangling = [f"{p.get('po_number')}:{it.get('supplier_item_id')}"
                   for p in pos for it in (p.get("items") or [])
                   if it.get("supplier_item_id") and it["supplier_item_id"] not in sit_ids]
    if dup_key or bad_ref or bad_conv or po_dangling:
        results["fail"] += 1
        line("FAIL", R, f"INV-SRC-05: {len(dup_key)} kunci duplikat · {len(bad_ref)} referensi "
                        f"tak valid · {len(bad_conv)} faktor ≤ 0 · {len(po_dangling)} baris PO "
                        "menunjuk barang supplier hilang",
             str((dup_key + bad_ref + bad_conv + po_dangling)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-SRC-05: {len(sitems)} barang supplier sehat "
                        "(kunci supplier+kode unik · referensi & faktor konversi valid)")


async def layer_receiving_uom_invariants(db):
    """FASE F-1 — Invarian PENERIMAAN BERBASIS SATUAN SUPPLIER (F1-01…F1-03).

    INV-RCV-01  jejak konversi penerimaan LENGKAP: setiap `wms_tasks.scan_log[].uom_trail`
                punya `doc_uom`, `doc_qty` > 0, `task_uom`, `task_qty` > 0 dan `factor` > 0
                (jejak D-07 tidak boleh setengah — kalau ada, harus bisa diaudit)
    INV-RCV-02  matematika konsisten: `doc_qty × factor == task_qty` (toleransi pembulatan),
                dan `task_qty` yang tercatat == `scan_log[].actual_qty` baris yang sama
                (angka di stok = angka hasil konversi, bukan angka lain)
    INV-RCV-03  sumber faktor SAH: `source ∈ same_unit|supplier_item|fixed_uom|
                product_override|global_rule|formula_gsm_width|hop_base`; bila
                `source == supplier_item` maka `supplier_item_id` WAJIB menunjuk
                `supplier_items` yang ADA (faktor tidak boleh "karangan").
                Selain itu `receive_uom_trails[]` WAJIB sinkron dengan jejak di `scan_log`.
    """
    print(f"\n{C}{B}L4-RCV — Invarian Penerimaan Satuan Supplier (Fase F-1 · F1-01/F1-02/F1-03){X}")
    tasks = await db.wms_tasks.find({"flow_type": "inbound"}, {"_id": 0}).to_list(50000)
    sit_ids = {s["id"] for s in await db.supplier_items.find({}, {"_id": 0, "id": 1}).to_list(50000)}
    VALID_SOURCES = {"same_unit", "supplier_item", "fixed_uom", "product_override",
                     "global_rule", "formula_gsm_width", "hop_base"}
    EPS = 0.05

    incomplete, math_off, qty_off, bad_source, dangling_sit, trail_drift = [], [], [], [], [], []
    trail_count = 0
    for t in tasks:
        scan_trails = {}
        for sc in t.get("scan_log") or []:
            tr = sc.get("uom_trail") or {}
            if not tr:
                continue
            trail_count += 1
            tag = f"{t.get('po_number') or t.get('id')}/{sc.get('id')}"
            scan_trails[sc.get("id")] = tr
            # ── INV-RCV-01 kelengkapan
            if not (tr.get("doc_uom") and tr.get("task_uom")
                    and float(tr.get("doc_qty") or 0) > 0
                    and float(tr.get("task_qty") or 0) > 0
                    and float(tr.get("factor") or 0) > 0):
                incomplete.append(tag)
                continue
            # ── INV-RCV-02 matematika & keselarasan dengan qty yang dipakai stok
            if abs(float(tr["doc_qty"]) * float(tr["factor"]) - float(tr["task_qty"])) > EPS:
                math_off.append(f"{tag}: {tr['doc_qty']}×{tr['factor']}≠{tr['task_qty']}")
            if abs(float(sc.get("actual_qty") or 0) - float(tr["task_qty"])) > EPS:
                qty_off.append(f"{tag}: actual={sc.get('actual_qty')} trail={tr['task_qty']}")
            # ── INV-RCV-03 sumber faktor sah + referensi barang supplier hidup
            if tr.get("source") not in VALID_SOURCES:
                bad_source.append(f"{tag}={tr.get('source')}")
            if tr.get("source") == "supplier_item":
                if not tr.get("supplier_item_id") or (sit_ids and tr["supplier_item_id"] not in sit_ids):
                    dangling_sit.append(f"{tag}→{tr.get('supplier_item_id') or '-'}")
        # akumulasi `receive_uom_trails[]` wajib sinkron dengan jejak di scan_log
        acc = t.get("receive_uom_trails") or []
        if len(acc) != len(scan_trails):
            trail_drift.append(f"{t.get('po_number') or t.get('id')}: acc={len(acc)} scans={len(scan_trails)}")
        else:
            for a in acc:
                sid = a.get("scan_id")
                if sid and sid not in scan_trails:
                    trail_drift.append(f"{t.get('po_number') or t.get('id')}: scan_id {sid} yatim")

    if incomplete:
        results["fail"] += 1
        line("FAIL", R, f"INV-RCV-01: {len(incomplete)} jejak konversi penerimaan tidak lengkap",
             str(incomplete[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-RCV-01: {trail_count} jejak konversi penerimaan lengkap "
                        f"(dari {len(tasks)} task inbound)")

    if math_off or qty_off:
        results["fail"] += 1
        line("FAIL", R, f"INV-RCV-02: {len(math_off)} matematika konversi menyimpang · "
                        f"{len(qty_off)} qty stok ≠ hasil konversi",
             str((math_off + qty_off)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-RCV-02: doc_qty × faktor == task_qty == qty yang masuk stok "
                        "(angka di layar = angka tersimpan)")

    if bad_source or dangling_sit or trail_drift:
        results["fail"] += 1
        line("FAIL", R, f"INV-RCV-03: {len(bad_source)} sumber faktor tak dikenal · "
                        f"{len(dangling_sit)} referensi barang supplier hilang · "
                        f"{len(trail_drift)} akumulasi jejak tidak sinkron",
             str((bad_source + dangling_sit + trail_drift)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-RCV-03: sumber faktor sah & referensi barang supplier hidup "
                        "(receive_uom_trails sinkron dengan scan_log)")


async def layer_config_invariants(db):
    """FASE G-0 (penutupan) — Invarian PUSAT PENGATURAN: satu sumber kebenaran.

    LATAR BELAKANG:
      Audit 2026-07-26 menemukan konfigurasi tersebar di 13 permukaan editor dengan
      13 bentuk API. Akibat nyatanya: "tombol palsu" (UI tanpa pembaca kode) dan
      aturan tersembunyi (dipakai mesin, tak bisa disentuh user). Pemilik memutuskan
      editor lama DIHAPUS. Lapisan ini menjaga keputusan itu supaya tidak pelan-pelan
      kembali lagi.

    INV-CFG-01  setiap setting terdeklarasi punya PEMBACA KODE nyata dan JALUR UBAH
                nyata (tidak ada HIDDEN / ORPHAN_UI / DEAD). Kunci yang memang tidak
                dipakai HARUS bersetatus `not_used` + alasan tertulis di registry.
    INV-CFG-02  rantai UI generik utuh: menu → route → SettingsHub → SettingEditor.
                Kalau putus, semua setting jadi tak bisa diubah user tanpa ada yang tahu.
    INV-CFG-03  registry konsisten: kunci `active` wajib punya consumers; `not_used`
                wajib punya alasan; setting bertipe tabel wajib punya bentuk baris.
    INV-CFG-04  TIDAK ADA layar lain yang menulis endpoint konfigurasi lama —
                satu-satunya jalur tulis dari UI adalah PUT /api/config/values.
    INV-CFG-05  nilai tersimpan valid terhadap batas registry (min/max/enum),
                sehingga mesin tidak pernah menerima angka di luar rentang.
    """
    print(f"\n{C}{B}L4-CFG — Invarian Pusat Pengaturan (FASE G-0 · satu sumber kebenaran){X}")

    sys.path.insert(0, "/app/scripts")
    try:
        import audit_config_wiring as acw
    except Exception as exc:  # pragma: no cover
        results["fail"] += 1
        line("FAIL", R, f"INV-CFG-01: audit wiring tidak bisa dimuat: {exc}")
        return

    reg_index = acw.registry_index()
    wired, wired_problems = acw.hub_wired()
    be, fe = acw.load_corpus()
    editor_set = acw.detect_fe_editors(fe)
    rows = acw.build_rows(
        acw.declared_global() + acw.declared_other_scopes(),
        be,
        {k: v for k, v in fe.items() if k not in editor_set},
        {k: v for k, v in fe.items() if k in editor_set},
        reg_index,
        wired,
    )
    bad = [r for r in rows if r["status"] in acw.VIOLATIONS]
    if bad:
        results["fail"] += 1
        line("FAIL", R, f"INV-CFG-01: {len(bad)} setting tanpa pembaca kode / tanpa jalur ubah",
             str([f"{r['status']} {r['scope']}:{r['path']}" for r in bad[:5]]))
    else:
        n_used = sum(1 for r in rows if r["status"] == "OK")
        n_off = sum(1 for r in rows if r["status"] == "NOT_USED")
        results["pass"] += 1
        line("PASS", G, f"INV-CFG-01: {len(rows)} setting — {n_used} aktif & bisa diubah user, "
                        f"{n_off} ditandai tidak dipakai + alasan; nol tersembunyi/palsu/mati")

    if not wired:
        results["fail"] += 1
        line("FAIL", R, "INV-CFG-02: rantai UI Pusat Pengaturan PUTUS", str(wired_problems[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-CFG-02: menu → route → SettingsHub → SettingEditor tersambung")

    reg_bad = []
    for key, e in reg_index.items():
        if e.get("status") == "active" and not e.get("consumers"):
            reg_bad.append(f"{key}: aktif tanpa consumers")
        if e.get("status") == "not_used" and not e.get("not_used_reason"):
            reg_bad.append(f"{key}: not_used tanpa alasan")
        if e.get("type") == "table" and not e.get("row_shape"):
            reg_bad.append(f"{key}: tabel tanpa row_shape")
        if e.get("row_shape") == "list" and not e.get("columns"):
            reg_bad.append(f"{key}: baris tabel tanpa definisi kolom")
    if reg_bad:
        results["fail"] += 1
        line("FAIL", R, f"INV-CFG-03: {len(reg_bad)} entri registry tidak lengkap",
             str(reg_bad[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-CFG-03: {len(reg_index)} entri registry lengkap "
                        "(consumers · alasan · bentuk tabel)")

    writers = acw.legacy_config_writers(fe)
    if writers:
        results["fail"] += 1
        line("FAIL", R, f"INV-CFG-04: {len(writers)} layar masih menulis konfigurasi "
                        "di luar Pusat Pengaturan",
             str([f"{k} → {', '.join(v)}" for k, v in list(writers.items())[:5]]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-CFG-04: satu-satunya jalur tulis konfigurasi dari UI adalah "
                        "PUT /api/config/values")

    # INV-CFG-05 — nilai TERSIMPAN harus patuh batas registry.
    out_of_range = []
    stored = await db.config_values.find({}, {"_id": 0}).to_list(50000)
    for row in stored:
        e = reg_index.get(row.get("key") or "")
        if not e:
            continue
        v = row.get("value")
        if isinstance(v, bool) or v is None:
            continue
        if e.get("type") == "enum":
            allowed = {o.get("value") for o in (e.get("options") or [])}
            if allowed and v not in allowed:
                out_of_range.append(f"{row['key']}={v!r} bukan pilihan sah")
            continue
        if isinstance(v, (int, float)):
            if e.get("min") is not None and v < e["min"]:
                out_of_range.append(f"{row['key']}={v} < min {e['min']}")
            if e.get("max") is not None and v > e["max"]:
                out_of_range.append(f"{row['key']}={v} > max {e['max']}")
    if out_of_range:
        results["fail"] += 1
        line("FAIL", R, f"INV-CFG-05: {len(out_of_range)} nilai tersimpan di luar batas registry",
             str(out_of_range[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-CFG-05: {len(stored)} nilai konfigurasi tersimpan patuh batas "
                        "(min/max/enum) — mesin tidak pernah menerima angka liar")


async def layer_amendment_invariants(db):
    """FASE G-1 — Invarian FONDASI AMANDEMEN: tidak ada perubahan angka yang senyap.

    INV-AMD-01  setiap amandemen yang SUDAH DITERAPKAN wajib punya nomor, label alasan
                yang dikenal, dampak terhitung, pengusul, dan jejak `refs` ke dokumen asal.
    INV-AMD-02  amandemen yang butuh persetujuan wajib punya penyetuju, dan bila kontrol
                ganda aktif saat itu, penyetuju HARUS orang yang berbeda dari pengusul.
    INV-AMD-03  DOKUMEN TERBIT TIDAK PERNAH BERUBAH: untuk amandemen bermetode nota,
                nilai dokumen asal harus tetap sama dengan `amount_before`, dan nilai
                nota yang terbit == besarnya dampak.
    INV-AMD-04  setiap nota hasil amandemen punya induk amandemen yang hidup, bernomor
                unik, dan matematika `net + PPN == bruto`.
    INV-AMD-05  keputusan bisa diaudit ulang: ambang yang dipakai ikut tersimpan
                (`policy_snapshot`) pada setiap amandemen.
    """
    print(f"\n{C}{B}L4-AMD — Invarian Fondasi Amandemen (FASE G-1 · tanpa edit senyap){X}")
    amds = await db.doc_amendments.find({}, {"_id": 0}).to_list(50000)
    reasons = {r["code"] for r in await db.amendment_reasons.find(
        {}, {"_id": 0, "code": 1}).to_list(500)}
    applied = [a for a in amds if a.get("status") in {"applied", "auto_applied"}]

    incomplete = []
    for a in applied:
        if not a.get("number"):
            incomplete.append(f"{a.get('id')}: tanpa nomor")
        if a.get("reason_code") not in reasons:
            incomplete.append(f"{a.get('number')}: alasan '{a.get('reason_code')}' tak dikenal")
        if not (a.get("impact") or {}).get("amount_before") and \
                not (a.get("impact") or {}).get("delta"):
            incomplete.append(f"{a.get('number')}: dampak tidak terhitung")
        if not a.get("proposed_by_id"):
            incomplete.append(f"{a.get('number')}: tanpa pengusul")
        if not any(r.get("rel") == "amends" for r in (a.get("refs") or [])):
            incomplete.append(f"{a.get('number')}: tanpa jejak ke dokumen asal")
    if incomplete:
        results["fail"] += 1
        line("FAIL", R, f"INV-AMD-01: {len(incomplete)} amandemen tidak lengkap",
             str(incomplete[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-AMD-01: {len(applied)} amandemen diterapkan — semuanya bernomor, "
                        "ber-alasan dikenal, ber-dampak, ber-pengusul, ber-jejak")

    bad_appr = []
    for a in amds:
        if not a.get("requires_approval"):
            continue
        if a.get("status") in {"applied", "approved", "rejected"}:
            if not a.get("decided_by_id"):
                bad_appr.append(f"{a.get('number')}: tanpa penyetuju")
            elif (a.get("policy_snapshot") or {}).get("dual_control") and \
                    a["decided_by_id"] == a.get("proposed_by_id"):
                bad_appr.append(f"{a.get('number')}: pengusul = penyetuju (kontrol ganda dilanggar)")
        elif a.get("status") == "auto_applied":
            bad_appr.append(f"{a.get('number')}: butuh approval tapi diterapkan otomatis")
    if bad_appr:
        results["fail"] += 1
        line("FAIL", R, f"INV-AMD-02: {len(bad_appr)} pelanggaran alur persetujuan",
             str(bad_appr[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-AMD-02: setiap amandemen ber-approval punya penyetuju yang sah "
                        "& berbeda dari pengusul (kontrol ganda)")

    mutated, note_mismatch = [], []
    notes_by_amd = {}
    for n in await db.credit_notes.find({"source": "amendment"}, {"_id": 0}).to_list(50000):
        notes_by_amd.setdefault(n.get("amendment_id"), []).append(n)
    for a in applied:
        if a.get("method") == "re_derive":
            continue
        order = await db.sales_orders.find_one({"id": a.get("doc_id")},
                                               {"_id": 0, "grand_total": 1, "number": 1})
        if not order:
            continue
        before = float((a.get("impact") or {}).get("amount_before", 0) or 0)
        if abs(float(order.get("grand_total", 0) or 0) - before) > 1:
            mutated.append(f"{a.get('number')}: {order.get('number')} berubah "
                           f"{before} → {order.get('grand_total')}")
        expect = abs(float((a.get("impact") or {}).get("delta", 0) or 0))
        got = sum(abs(float(n.get("gross_amount", 0) or 0)) for n in notes_by_amd.get(a["id"], []))
        if abs(got - expect) > 1:
            note_mismatch.append(f"{a.get('number')}: nota {got} ≠ dampak {expect}")
    if mutated or note_mismatch:
        results["fail"] += 1
        line("FAIL", R, f"INV-AMD-03: {len(mutated)} dokumen terbit BERUBAH · "
                        f"{len(note_mismatch)} nilai nota tidak cocok dampak",
             str((mutated + note_mismatch)[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-AMD-03: dokumen terbit tidak pernah berubah nominalnya — "
                        "koreksinya persis sebesar nota yang diterbitkan")

    amd_ids = {a["id"] for a in amds}
    bad_notes, seen_numbers = [], set()
    all_notes = [n for ns in notes_by_amd.values() for n in ns]
    for n in all_notes:
        if n.get("amendment_id") not in amd_ids:
            bad_notes.append(f"{n.get('number')}: induk amandemen hilang")
        if n.get("number") in seen_numbers:
            bad_notes.append(f"{n.get('number')}: nomor ganda")
        seen_numbers.add(n.get("number"))
        net = float(n.get("net_amount", 0) or 0)
        ppn = float(n.get("ppn_amount", 0) or 0)
        gross = float(n.get("gross_amount", 0) or 0)
        if abs(round(net + ppn, 2) - round(gross, 2)) > 0.05:
            bad_notes.append(f"{n.get('number')}: net+PPN ≠ bruto")
    if bad_notes:
        results["fail"] += 1
        line("FAIL", R, f"INV-AMD-04: {len(bad_notes)} nota bermasalah", str(bad_notes[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-AMD-04: {len(all_notes)} nota koreksi sehat "
                        "(induk hidup · nomor unik · net+PPN == bruto)")

    no_policy = [a.get("number") for a in amds if not (a.get("policy_snapshot") or {})]
    if no_policy:
        results["fail"] += 1
        line("FAIL", R, f"INV-AMD-05: {len(no_policy)} amandemen tanpa rekaman ambang",
             str(no_policy[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-AMD-05: {len(amds)} amandemen menyimpan ambang yang berlaku "
                        "saat itu — keputusan bisa diaudit ulang")


async def layer_docref_invariants(db):
    """FASE G-4 — Invarian **RELASI DOKUMEN**: tidak ada surat yang buntu.

    INV-REF-01  dokumen turunan (surat jalan, faktur, kwitansi, retur, tagihan supplier,
                nota koreksi, penerimaan barang) WAJIB menunjuk minimal satu dokumen
                induk yang masih HIDUP. Dokumen yatim = penelusuran retur/klaim buntu.
                Bisa dimatikan admin lewat `docref.require_parent` (configurable G-0).
    INV-REF-02  relasi selalu DUA ARAH: kalau A menunjuk B, B harus menunjuk A. Tanpa ini
                jejak hanya bisa dibaca dari satu sisi (persis masalah yang dikeluhkan
                pemilik: "banyak surat lahir tapi saling tidak mereferensikan").
    INV-REF-03  dokumen yang DICETAK benar-benar menyebut nomor referensinya: satu
                dokumen nyata dirender lewat mesin PDF dan blok "Referensi Dokumen"
                (plus QR Jejak Dokumen) harus ada di hasilnya.
    """
    print(f"\n{C}{B}L4-REF — Invarian Relasi Dokumen (FASE G-4 · tidak ada surat buntu){X}")
    sys.path.insert(0, "/app/backend")
    try:
        from services import doc_refs_service as refs
    except Exception as exc:  # noqa: BLE001
        results["fail"] += 1
        line("FAIL", R, "INV-REF: services/doc_refs_service.py tidak bisa diimpor", str(exc))
        return

    # ── INV-REF-01 ──────────────────────────────────────────────────────────
    try:
        required = await refs.parent_required()
    except Exception:  # noqa: BLE001 — config belum ter-seed
        required = True
    orphans = await refs.orphan_children(limit=50)
    if required and orphans:
        results["fail"] += 1
        line("FAIL", R, f"INV-REF-01: {len(orphans)} dokumen turunan tanpa induk hidup",
             str([f"{o['doc_type']} {o['number']}" for o in orphans[:6]]))
    elif not required:
        results["warn"] += 1
        line("WARN", Y, "INV-REF-01: pemeriksaan induk DIMATIKAN admin "
                        "(`docref.require_parent` = false)")
    else:
        total_children = 0
        for meta in refs.DOC_TYPES.values():
            if meta["needs_parent"]:
                total_children += await db[meta["collection"]].count_documents(meta["filter"])
        standalone = await refs.standalone_children(limit=500)
        results["pass"] += 1
        extra = (f" · {len(standalone)} dokumen SAH berdiri sendiri (tanpa kolom sumber: "
                 f"{', '.join(sorted({s['doc_type'] for s in standalone}))})"
                 if standalone else "")
        line("PASS", G, f"INV-REF-01: {total_children} dokumen turunan semuanya menunjuk "
                        f"dokumen induk yang hidup{extra}")

    # ── INV-REF-02 ──────────────────────────────────────────────────────────
    one_way = await refs.one_way_refs(limit=50)
    if one_way:
        results["fail"] += 1
        line("FAIL", R, f"INV-REF-02: {len(one_way)} relasi hanya satu arah",
             str(one_way[:5]))
    else:
        total_refs = 0
        for meta in refs.DOC_TYPES.values():
            flt = dict(meta["filter"])
            flt["refs.0"] = {"$exists": True}
            total_refs += await db[meta["collection"]].count_documents(flt)
        results["pass"] += 1
        line("PASS", G, f"INV-REF-02: relasi dua arah konsisten pada {total_refs} dokumen "
                        "ber-referensi (bisa ditelusuri dari sisi mana pun)")

    # ── INV-REF-03 ──────────────────────────────────────────────────────────
    sample = await db.sales_orders.find_one({"refs.0": {"$exists": True}}, {"_id": 0, "id": 1,
                                                                           "number": 1})
    if not sample:
        results["warn"] += 1
        line("WARN", Y, "INV-REF-03: tidak ada dokumen ber-referensi untuk diuji cetak "
                        "(jalankan backfill / seed ulang)")
        return
    try:
        from services import pdf_service
        built = await pdf_service.build_document(
            "invoice", sample["id"], None,
            public_base="https://kn.example.test")
        block = (built.get("doc") or {}).get("refs_block") or {}
        html = __import__("services.pdf_engine", fromlist=["render_html"]).render_html(
            built["cfg"], built["branding"], built["doc"])
        ok_text = "Referensi Dokumen" in html and (block.get("text") or "") in html
        ok_qr = bool(block.get("qr_src")) and "jejak-dokumen" in (block.get("trace_url") or "")
        # INV-REF-03b — render TANPA header Origin (job/penjadwal/WhatsApp/skrip) tetap
        # wajib menghasilkan QR ber-HOST. Bug nyata 2026-07-27: QR kosong pada jalur ini
        # sehingga pemegang kertas tidak bisa membuka apa pun.
        built_job = await pdf_service.build_document("invoice", sample["id"], None)
        block_job = (built_job.get("doc") or {}).get("refs_block") or {}
        url_job = block_job.get("trace_url") or ""
        ok_abs = url_job.startswith("http") and bool(block_job.get("qr_src"))
        if ok_text and ok_qr and ok_abs:
            results["pass"] += 1
            line("PASS", G, f"INV-REF-03: dokumen cetak {sample.get('number')} menampilkan "
                            f"blok referensi ({block.get('text')}) + QR Jejak Dokumen "
                            f"(juga saat dirender tanpa browser: {url_job[:48]}…)")
        else:
            results["fail"] += 1
            line("FAIL", R, "INV-REF-03: dokumen cetak TIDAK menampilkan referensi/QR",
                 f"text={ok_text} qr={ok_qr} qr_absolut_tanpa_browser={ok_abs} url={url_job!r}")
    except Exception as exc:  # noqa: BLE001
        results["fail"] += 1
        line("FAIL", R, "INV-REF-03: gagal merender dokumen uji", str(exc)[:200])


async def layer_payment_penalty_invariants(db):
    """FASE G-2 — Invarian **RENCANA PEMBAYARAN & DENDA**.

    INV-PAY-01  Σ baris rencana pembayaran == nilai dokumen sumber (toleransi dibaca dari
                `payment.plan_tolerance_rupiah`). Rencana yang tidak pas = jadwal tagih yang
                menyesatkan; penagihan jadi salah sejak awal.
    INV-PAY-02  Alokasi terbayar tidak boleh melebihi nominal baris, dan Σ terbayar pada
                rencana tidak boleh melebihi pembayaran NYATA di dokumen sumber (tak ada uang
                hantu di jadwal).
    INV-PEN-01  Denda `draft` TIDAK boleh punya jurnal — inilah yang membuat denda bisa
                dinegosiasikan tanpa mengotori buku besar.
    INV-PEN-02  Denda `waived` / `adjusted` wajib punya label alasan DAN pemutus.
    INV-PEN-03  Σ denda terbit yang belum dibayar == saldo akun 1-1270 Piutang Denda di GL.
    """
    print(f"\n{C}{B}L4-PAY — Invarian Rencana Pembayaran & Denda (FASE G-2){X}")
    sys.path.insert(0, "/app/backend")
    try:
        from services import payment_plan_service as plans
        from services import penalty_service as pen
        from services import gl_service
    except Exception as exc:  # noqa: BLE001
        results["fail"] += 1
        line("FAIL", R, "INV-PAY/PEN: layanan FASE G-2 tidak bisa diimpor", str(exc))
        return

    # ── INV-PAY-01 & INV-PAY-02 ─────────────────────────────────────────────
    bad_total, bad_paid = [], []
    total_plans = 0
    async for row in db[plans.COLL].find({"status": {"$ne": "void"}}, {"_id": 0}):
        total_plans += 1
        policy = await plans.plan_policy(row.get("entity_id") or "", row.get("customer_id") or "")
        order = await db.sales_orders.find_one({"id": row.get("doc_id")}, {"_id": 0})
        if not order:
            continue
        total = plans.source_total(order)
        okay, diff = plans.check_total(row.get("lines") or [], total, policy["tolerance"])
        if not okay:
            bad_total.append(f"{row.get('number')} selisih Rp {diff:,.0f}".replace(",", "."))
        paid_sum = round(sum(float(l.get("paid_amount") or 0) for l in (row.get("lines") or [])), 2)
        real_paid = plans.source_paid(order)
        over_line = [l.get("label") for l in (row.get("lines") or [])
                     if float(l.get("paid_amount") or 0) > float(l.get("amount") or 0) + 0.01]
        if paid_sum > real_paid + 0.01 or over_line:
            bad_paid.append(f"{row.get('number')} (jadwal Rp {paid_sum:,.0f} vs kas Rp {real_paid:,.0f})"
                            .replace(",", "."))

    if bad_total:
        results["fail"] += 1
        line("FAIL", R, f"INV-PAY-01: {len(bad_total)} rencana pembayaran tidak sama dengan "
                        "nilai dokumennya", str(bad_total[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-PAY-01: {total_plans} rencana pembayaran jumlahnya PAS dengan "
                        "nilai dokumen sumber")
    if bad_paid:
        results["fail"] += 1
        line("FAIL", R, f"INV-PAY-02: {len(bad_paid)} rencana mencatat pembayaran melebihi "
                        "kas nyata / nominal baris", str(bad_paid[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-PAY-02: alokasi pembayaran pada jadwal tidak pernah melebihi "
                        "kas yang benar-benar masuk")

    # ── INV-PEN-01 ──────────────────────────────────────────────────────────
    drafts_je = await pen.drafts_with_journal()
    total_pen = await db[pen.COLL].count_documents({})
    if drafts_je:
        results["fail"] += 1
        line("FAIL", R, f"INV-PEN-01: {len(drafts_je)} denda DRAFT punya jurnal "
                        "(seharusnya belum menyentuh buku besar)",
             str([d["number"] for d in drafts_je[:5]]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-PEN-01: dari {total_pen} nota denda, tidak ada draft yang "
                        "menyentuh buku besar")

    # ── INV-PEN-02 ──────────────────────────────────────────────────────────
    no_reason = await pen.decided_without_reason()
    if no_reason:
        results["fail"] += 1
        line("FAIL", R, f"INV-PEN-02: {len(no_reason)} denda dibebaskan/diubah tanpa alasan "
                        "atau tanpa pemutus", str([d["number"] for d in no_reason[:5]]))
    else:
        decided = await db[pen.COLL].count_documents({"status": {"$in": ["waived", "adjusted"]}})
        results["pass"] += 1
        line("PASS", G, f"INV-PEN-02: {decided} keputusan denda semuanya ber-alasan & "
                        "ber-pemutus (tidak ada denda hilang diam-diam)")

    # ── INV-PEN-03 ──────────────────────────────────────────────────────────
    doc_out = await pen.outstanding_total()
    gl_bal = await gl_service.penalty_receivable_balance()
    if abs(doc_out - gl_bal) > 1.0:
        results["fail"] += 1
        line("FAIL", R, "INV-PEN-03: saldo Piutang Denda di GL tidak sama dengan nota denda",
             f"dokumen Rp {doc_out:,.0f} vs GL Rp {gl_bal:,.0f}".replace(",", "."))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-PEN-03: Σ denda terbit belum dibayar == saldo GL 1-1270 "
                        f"(Rp {doc_out:,.0f})".replace(",", "."))


async def layer_rnd_invariants(db):
    """FASE F — Invarian **R&D & DESAIN** (labdip · proofing · lifecycle produk).

    INV-RND-01  Setiap permintaan sample `decided` wajib punya round ber-hasil **acc**,
                pemutus, dan alasan berlabel; bila keputusan menyebut kontrak, kontraknya
                WAJIB benar-benar ada dan `sample_ref`-nya menunjuk balik ke nomor sample.
                Ini yang membuat "harga PO ini dari mana" selalu bisa dijawab.
    INV-RND-02  Round yang sudah ditutup (ada `result`) WAJIB punya lampiran bukti +
                catatan bila saat penutupan kebijakan bukti sedang aktif (`proof_required`),
                dan `round_no` per supplier berurut tanpa lompatan.
    INV-RND-03  Spesifikasi `approved` wajib punya produk NYATA, dan produk itu menunjuk
                balik `spec_id` (relasi dua arah, tidak ada produk "yatim spesifikasi").
    INV-RND-04  **Tidak ada uang keluar/masuk untuk barang yang belum sah**: produk dengan
                lifecycle konsep/labdip/proofing tidak boleh muncul di SO, PR, atau PO.
    INV-RND-05  Setiap pengambilan bahan sample punya mutasi stok NYATA bertipe
                `sample_issue` dengan qty negatif yang sama (PS-19: stok sample = stok
                gudang, satu angka).
    INV-RND-06  Permintaan `proofing` wajib merujuk desain yang ada di master desain.
    INV-RND-07  **Bahan sample yang keluar gudang wajib berjurnal**: tiap `material_issues`
                dengan biaya > 0 punya jurnal `rnd_sample_issue` (Dr 6-7000 Beban Sample &
                Pengembangan / Cr 1-1300 Persediaan) dengan nilai yang SAMA. Tanpa ini nilai
                persediaan turun di subledger tetapi GL tidak — uang "hilang" tanpa beban.

    CATATAN KEJUJURAN: produk yang lahir SEBELUM FASE F tidak punya `lifecycle`; oleh
    `services/rnd_gate.py` maupun invarian ini diperlakukan sebagai `produksi` sehingga
    tidak ada transaksi lama yang dituduh melanggar.
    """
    print(f"\n{C}{B}L4-RND — Invarian R&D & Desain (FASE F){X}")

    specs = await db.md_specs.find({}, {"_id": 0}).to_list(5000)
    samples = await db.md_samples.find({}, {"_id": 0}).to_list(5000)
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(20000)}

    # ── INV-RND-01
    bad = []
    contracts = {c["id"]: c for c in
                 await db.supplier_contracts.find({}, {"_id": 0}).to_list(5000)}
    decided = [s for s in samples if s.get("status") == "decided"]
    for s in decided:
        d = s.get("decision") or {}
        acc = [r for r in (s.get("rounds") or [])
               if r.get("supplier_id") == d.get("supplier_id") and r.get("result") == "acc"]
        if not acc:
            bad.append(f"{s.get('number')}: diputus tanpa round ACC")
        if not d.get("decided_by") or not d.get("reason_code"):
            bad.append(f"{s.get('number')}: keputusan tanpa pemutus/alasan")
        cid = d.get("contract_id") or ""
        if cid:
            c = contracts.get(cid)
            if not c:
                bad.append(f"{s.get('number')}: kontrak {cid} tidak ada")
            elif (c.get("sample_ref") or "") != (s.get("number") or ""):
                bad.append(f"{s.get('number')}: kontrak {c.get('contract_number')} "
                           "tidak menunjuk balik nomor sample")
    if bad:
        results["fail"] += 1
        line("FAIL", R, f"INV-RND-01: {len(bad)} keputusan sample tidak sah", str(bad[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-RND-01: {len(decided)} keputusan sample ber-ACC, ber-alasan & "
                        "ber-pemutus; kontrak yang lahir menunjuk balik ke nomor sample")

    # ── INV-RND-02
    bad2 = []
    n_rounds = n_closed = 0
    for s in samples:
        per_sup = {}
        for r in (s.get("rounds") or []):
            n_rounds += 1
            per_sup.setdefault(r.get("supplier_id"), []).append(int(r.get("round_no") or 0))
            if not r.get("result"):
                continue
            n_closed += 1
            if r.get("proof_required") and not (r.get("attachments") or []):
                bad2.append(f"{s.get('number')} rnd{r.get('round_no')}: ditutup tanpa lampiran")
            if r.get("proof_required") and not (r.get("note") or "").strip():
                bad2.append(f"{s.get('number')} rnd{r.get('round_no')}: ditutup tanpa catatan")
        for sup, nos in per_sup.items():
            if sorted(nos) != list(range(1, len(nos) + 1)):
                bad2.append(f"{s.get('number')}/{sup}: nomor round tidak berurut {sorted(nos)}")
    if bad2:
        results["fail"] += 1
        line("FAIL", R, f"INV-RND-02: {len(bad2)} round tanpa bukti / nomor melompat",
             str(bad2[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-RND-02: {n_closed} dari {n_rounds} round tertutup — semuanya "
                        "ber-lampiran & ber-catatan; nomor round berurut per supplier")

    # ── INV-RND-03
    bad3 = []
    approved = [s for s in specs if s.get("status") == "approved"]
    for s in approved:
        pid = s.get("product_id") or ""
        prod = products.get(pid)
        if not prod:
            bad3.append(f"{s.get('number')}: produk hasil ACC tidak ada")
        elif (prod.get("spec_id") or "") != s.get("id"):
            bad3.append(f"{s.get('number')}: produk {prod.get('sku')} tidak menunjuk balik spec")
    if bad3:
        results["fail"] += 1
        line("FAIL", R, f"INV-RND-03: {len(bad3)} spesifikasi disetujui tanpa produk sah",
             str(bad3[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-RND-03: {len(approved)} spesifikasi disetujui \u2192 produk nyata "
                        "dengan tautan dua arah")

    # ── INV-RND-04
    NOT_ORDERABLE = {"konsep", "labdip", "proofing"}
    blocked_ids = {pid for pid, p in products.items()
                   if str(p.get("lifecycle") or "produksi").strip().lower() in NOT_ORDERABLE}
    leaks = []
    if blocked_ids:
        for so in await db.sales_orders.find({}, {"_id": 0, "number": 1, "items": 1}).to_list(20000):
            for it in (so.get("items") or []):
                if it.get("product_id") in blocked_ids:
                    leaks.append(f"SO {so.get('number')} \u2192 {it.get('sku') or it.get('product_id')}")
        for pr in await db.purchase_requisitions.find({}, {"_id": 0, "number": 1, "items": 1}).to_list(20000):
            for it in (pr.get("items") or []):
                if it.get("product_id") in blocked_ids:
                    leaks.append(f"PR {pr.get('number')} \u2192 {it.get('sku') or it.get('product_id')}")
        for po in await db.purchase_orders.find({}, {"_id": 0, "po_number": 1, "items": 1}).to_list(20000):
            for it in (po.get("items") or []):
                if it.get("product_id") in blocked_ids:
                    leaks.append(f"PO {po.get('po_number')} \u2192 {it.get('sku') or it.get('product_id')}")
    if leaks:
        results["fail"] += 1
        line("FAIL", R, f"INV-RND-04: {len(leaks)} baris dokumen memakai produk yang BELUM sah "
                        f"(dari {len(blocked_ids)} produk belum rilis)", str(leaks[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-RND-04: {len(blocked_ids)} produk belum rilis \u2014 nol kebocoran "
                        "ke SO/PR/PO (uang tidak keluar untuk barang belum sah)")

    # ── INV-RND-05
    bad5 = []
    n_issue = 0
    movs = {m["id"]: m for m in await db.inventory_movements.find(
        {"movement_type": "sample_issue"}, {"_id": 0}).to_list(20000)}
    for s in samples:
        for mi in (s.get("material_issues") or []):
            n_issue += 1
            m = movs.get(mi.get("movement_id") or "")
            if not m:
                bad5.append(f"{s.get('number')}: pengambilan {mi.get('qty')} tanpa mutasi stok")
                continue
            if abs(float(m.get("quantity") or 0) + float(mi.get("qty") or 0)) > 0.01:
                bad5.append(f"{s.get('number')}: mutasi {m.get('quantity')} \u2260 "
                            f"-{mi.get('qty')} (stok sample \u2260 stok gudang)")
    if bad5:
        results["fail"] += 1
        line("FAIL", R, f"INV-RND-05: {len(bad5)} pengambilan bahan sample tanpa mutasi "
                        "stok yang cocok", str(bad5[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-RND-05: {n_issue} pengambilan bahan sample \u2014 semuanya punya "
                        "mutasi `sample_issue` dengan qty yang sama (satu angka stok)")

    # ── INV-RND-06
    designs = {d["id"] for d in await db.design_gallery.find({}, {"_id": 0, "id": 1}).to_list(5000)}
    proofs = [s for s in samples if s.get("sample_type") == "proofing"]
    bad6 = [s.get("number") for s in proofs
            if not s.get("design_id") or s.get("design_id") not in designs]
    if bad6:
        results["fail"] += 1
        line("FAIL", R, f"INV-RND-06: {len(bad6)} permintaan proofing tanpa desain sah",
             str(bad6[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-RND-06: {len(proofs)} permintaan proofing \u2014 semuanya merujuk "
                        "desain nyata di master desain")

    # ── INV-RND-07 — bahan sample keluar gudang WAJIB berjurnal (anti INV-GL-DRIFT)
    jes = {j.get("source_id"): j for j in await db.journal_entries.find(
        {"source_type": "rnd_sample_issue", "status": {"$ne": "void"}}, {"_id": 0}).to_list(20000)}
    bad7, n_cost = [], 0
    for s in samples:
        for mi in (s.get("material_issues") or []):
            cost = round(float(mi.get("cost") or 0), 2)
            if cost <= 0.01:
                continue
            n_cost += 1
            je = jes.get(mi.get("movement_id") or "")
            if not je:
                bad7.append(f"{s.get('number')}: bahan Rp {cost:,.0f} keluar gudang TANPA "
                            "jurnal beban sample")
                continue
            if abs(float(je.get("total_debit") or 0) - cost) > 0.01:
                bad7.append(f"{s.get('number')}: jurnal {je.get('number')} "
                            f"Rp {float(je.get('total_debit') or 0):,.0f} \u2260 biaya bahan "
                            f"Rp {cost:,.0f}")
    if bad7:
        results["fail"] += 1
        line("FAIL", R, f"INV-RND-07: {len(bad7)} pengambilan bahan sample tanpa jurnal "
                        "beban yang cocok (persediaan turun tanpa beban di GL)", str(bad7[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-RND-07: {n_cost} pengambilan bahan sample berbiaya \u2014 semuanya "
                        "berjurnal Dr 6-7000 / Cr 1-1300 dengan nilai sama (GL sejalan subledger)")


async def layer_bank_invariants(db):
    """FASE G-8 — Invarian **REKONSILIASI BANK** (mutasi, tautan, titipan dana).

    INV-BNK-01  Setiap baris mutasi berstatus jelas (`unmatched|matched|ignored|holding`).
                Baris `matched` WAJIB punya tautan dgn Σ alokasi == nominal mutasinya
                (tidak ada "tercocok" yang sebenarnya kosong); baris `unmatched`/`ignored`
                TIDAK boleh menyimpan tautan sisa; baris `holding` WAJIB punya bukti kas
                (transaksi kas titipan).
    INV-BNK-02  Σ yang direkonsiliasi pada transaksi buku == Σ alokasi yang menunjuk
                transaksi itu, dan tidak pernah melebihi nominalnya. Ini yang mencegah
                satu kwitansi "dilunasi" dua kali oleh dua transfer.
    INV-BNK-03  Saldo akun titipan di BUKU BESAR == Σ titipan yang belum dialokasikan.
                Uang tak dikenal tidak boleh hilang dari laporan: kalau jurnalnya hilang
                atau alokasinya tidak menjurnal, invarian ini memerah.
                Titipan yang menganggur melebihi ambang umur dilaporkan sebagai WARN
                (antrean tindak lanjut FASE G-9), bukan FAIL — dana itu sah, hanya perlu
                diurus.
    INV-BNK-04  Baris **biaya administrasi bank / bunga · jasa giro** yang dibukukan dari
                layar rekonsiliasi WAJIB punya transaksi kas hidup + jurnal aktif pada akun
                yang dicatat pada barisnya. Kalau kasnya di-void atau jurnalnya hilang
                sementara barisnya tetap "tercocok", bebannya lenyap dari laba rugi padahal
                rekonsiliasi tampak beres.
    INV-BNK-05  **Titipan tidak pernah melintasi PT.** Setiap alokasi titipan menunjuk
                pesanan yang ADA dan berada di entitas yang sama dengan baris mutasinya —
                uang yang masuk ke rekening PT-A tidak boleh melunasi piutang PT-B.
    """
    print(f"\n{C}{B}L4-BNK — Invarian Rekonsiliasi Bank (FASE G-8){X}")
    EPSB = 0.01
    ALLOWED = {"unmatched", "matched", "ignored", "holding"}
    lines = await db.bank_statement_lines.find({}, {"_id": 0}).to_list(50000)

    # ── INV-BNK-01 ──
    bad1 = []
    for ln in lines:
        st = ln.get("status") or ""
        allocs = ln.get("allocations") or []
        total = round(sum(float(a.get("amount", 0) or 0) for a in allocs), 2)
        amt = round(float(ln.get("amount", 0) or 0), 2)
        if st not in ALLOWED:
            bad1.append(f"{ln.get('id')}: status '{st}' tidak dikenal")
            continue
        if st == "matched":
            if not allocs:
                bad1.append(f"{ln.get('id')}: matched tanpa tautan transaksi")
            elif abs(total - amt) > EPSB:
                bad1.append(f"{ln.get('id')}: Σ alokasi {total} != nominal {amt}")
        elif st in ("unmatched", "ignored") and allocs:
            bad1.append(f"{ln.get('id')}: status {st} tapi masih menyimpan {len(allocs)} tautan")
        elif st == "holding":
            hold = ln.get("holding") or {}
            if not hold.get("cash_txn_id"):
                bad1.append(f"{ln.get('id')}: titipan tanpa transaksi kas")
            alloc_h = round(sum(float(a.get("amount", 0) or 0)
                                for a in (ln.get("holding_allocated") or [])), 2)
            rem = round(float(ln.get("holding_remaining", amt) or 0), 2)
            if abs(alloc_h + rem - amt) > EPSB:
                bad1.append(f"{ln.get('id')}: titipan {amt} != teralokasi {alloc_h} + sisa {rem}")
    if bad1:
        results["fail"] += 1
        line("FAIL", R, f"INV-BNK-01: {len(bad1)} baris mutasi bank tidak konsisten", str(bad1[:4]))
    else:
        results["pass"] += 1
        st_count = {s: sum(1 for l in lines if l.get("status") == s) for s in sorted(ALLOWED)}
        line("PASS", G, f"INV-BNK-01: {len(lines)} baris mutasi berstatus sah & tautannya utuh",
             str(st_count))

    # ── INV-BNK-02 ──
    per_txn: Dict[str, float] = {}
    for ln in lines:
        if ln.get("status") != "matched":
            continue
        for a in (ln.get("allocations") or []):
            per_txn[a.get("txn_id", "")] = round(
                per_txn.get(a.get("txn_id", ""), 0.0) + float(a.get("amount", 0) or 0), 2)
    bad2 = []
    checked = 0
    for tid, alloc in per_txn.items():
        t = await db.cash_transactions.find_one({"id": tid}, {"_id": 0})
        if not t:
            bad2.append(f"{tid}: transaksi buku yang ditaut tidak ada")
            continue
        checked += 1
        rec = round(float(t.get("reconciled_amount", 0) or 0), 2)
        amt = round(float(t.get("amount", 0) or 0), 2)
        if abs(rec - alloc) > EPSB:
            bad2.append(f"{t.get('number', tid)}: tercatat {rec} vs Σ alokasi {alloc}")
        if alloc > amt + EPSB:
            bad2.append(f"{t.get('number', tid)}: dialokasikan {alloc} > nominal {amt}")
    if bad2:
        results["fail"] += 1
        line("FAIL", R, f"INV-BNK-02: {len(bad2)} transaksi buku tidak seimbang dgn tautannya",
             str(bad2[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-BNK-02: {checked} transaksi buku tertaut — Σ rekonsiliasi == Σ alokasi "
                        "& tidak melebihi nominal")

    # ── INV-BNK-03 ──
    holding = [l for l in lines if l.get("status") == "holding"]
    remaining = round(sum(float(l.get("holding_remaining", l.get("amount", 0)) or 0)
                          for l in holding), 2)
    acc_code = "2-1950"
    try:
        sys.path.insert(0, "/app/backend")
        from services import bank_recon_service as brs
        cfg = await brs.load_cfg("")
        acc_code = cfg.get("holding_acc") or acc_code
        max_age = int(cfg.get("holding_max_age_days") or 7)
    except Exception:  # noqa: BLE001
        max_age = 7
    debit = credit = 0.0
    async for je in db.journal_entries.find({"status": {"$ne": "void"},
                                             "lines.account_code": acc_code}, {"_id": 0}):
        for l in (je.get("lines") or []):
            if l.get("account_code") == acc_code:
                debit += float(l.get("debit", 0) or 0)
                credit += float(l.get("credit", 0) or 0)
    gl_balance = round(credit - debit, 2)   # akun kewajiban: saldo normal KREDIT
    if abs(gl_balance - remaining) > 0.5:
        results["fail"] += 1
        line("FAIL", R, f"INV-BNK-03: saldo titipan GL {acc_code} = {gl_balance} "
                        f"tapi Σ titipan belum teralokasi = {remaining}",
             "→ jurnal titipan/alokasi hilang atau ganda")
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-BNK-03: saldo titipan {acc_code} = Rp {gl_balance:,.0f} "
                        f"sama dgn {len(holding)} baris titipan belum teralokasi")
    stale = []
    today = datetime.now(timezone.utc).date()
    for l in holding:
        try:
            d = datetime.fromisoformat(str(l.get("stmt_date"))[:10]).date()
        except Exception:  # noqa: BLE001
            continue
        if (today - d).days > max_age and float(l.get("holding_remaining", 0) or 0) > EPSB:
            stale.append(l.get("id"))
    if stale:
        results["warn"] += 1
        line("WARN", Y, f"INV-BNK-03: {len(stale)} titipan menganggur > {max_age} hari "
                        "— perlu tindak lanjut (antrean FASE G-9)", str(stale[:4]))

    # ── INV-BNK-04 ── biaya/bunga bank yang dibukukan dari layar rekonsiliasi
    # Baris "biaya bank" melahirkan transaksi kas + jurnal sendiri. Kalau kas-nya di-void
    # atau jurnalnya hilang sementara barisnya tetap 'tercocok', beban itu lenyap dari laba
    # rugi tetapi rekonsiliasi tetap tampak beres — persis jenis kebocoran yang harus memerah.
    charged = [l for l in lines if (l.get("charge") or {}).get("cash_txn_id")]
    bad4 = []
    for ln in charged:
        ch = ln.get("charge") or {}
        cash = await db.cash_transactions.find_one({"id": ch["cash_txn_id"]}, {"_id": 0})
        matched = ln.get("status") == "matched" and ln.get("match_type") == "charge"
        if not cash:
            bad4.append(f"{ln.get('id')}: transaksi kas biaya/bunga bank hilang")
            continue
        if matched and cash.get("status") == "void":
            bad4.append(f"{ln.get('id')}: baris tercocok tapi kas {cash.get('number')} void")
            continue
        if not matched:
            bad4.append(f"{ln.get('id')}: jejak biaya bank tertinggal padahal status "
                        f"'{ln.get('status')}' (seharusnya dibersihkan saat dilepas)")
            continue
        je = await db.journal_entries.find_one(
            {"source_type": "cash_transaction", "source_id": ch["cash_txn_id"],
             "status": {"$ne": "void"}}, {"_id": 0})
        if not je:
            bad4.append(f"{ln.get('id')}: kas {cash.get('number')} tanpa jurnal aktif")
            continue
        codes = {l.get("account_code") for l in (je.get("lines") or [])}
        if ch.get("account_code") and ch["account_code"] not in codes:
            bad4.append(f"{ln.get('id')}: jurnal {je.get('number')} tidak memakai akun "
                        f"{ch['account_code']}")
    if bad4:
        results["fail"] += 1
        line("FAIL", R, f"INV-BNK-04: {len(bad4)} baris biaya/bunga bank tidak berbukti",
             str(bad4[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-BNK-04: {len(charged)} baris biaya/bunga bank punya kas + jurnal "
                        "aktif pada akun yang benar")

    # ── INV-BNK-05 ── titipan tidak pernah melintasi PT
    # Uang yang masuk ke rekening PT-A hanya boleh melunasi piutang PT-A. Kalau alokasinya
    # menunjuk pesanan PT lain, piutang PT-B berkurang memakai uang PT-A dan jurnalnya pecah
    # di dua buku (Cr Piutang di buku PT-B, Cr Titipan di buku PT-A) → laporan kedua PT salah.
    bad5 = []
    checked5 = 0
    for ln in lines:
        lent = ln.get("entity_id") or ""
        for al in (ln.get("holding_allocated") or []):
            oid = al.get("order_id") or ""
            if not oid:
                bad5.append(f"{ln.get('id')}: alokasi titipan tanpa pesanan")
                continue
            order = await db.sales_orders.find_one({"id": oid}, {"_id": 0, "entity_id": 1,
                                                                "number": 1})
            checked5 += 1
            if not order:
                bad5.append(f"{ln.get('id')}: alokasi menunjuk pesanan {oid} yang tidak ada")
                continue
            oent = order.get("entity_id") or ""
            if lent and oent and oent != lent and "all" not in (lent, oent):
                bad5.append(f"{ln.get('id')}: titipan {lent} melunasi pesanan "
                            f"{order.get('number', oid)} milik {oent}")
    if bad5:
        results["fail"] += 1
        line("FAIL", R, f"INV-BNK-05: {len(bad5)} alokasi titipan melintasi PT / menggantung",
             str(bad5[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-BNK-05: {checked5} alokasi titipan menunjuk pesanan yang ADA "
                        "dan berada di entitas rekeningnya sendiri")


async def layer_finance_case_invariants(db):
    """FASE G-9 — Invarian **PUSAT KASUS KEUANGAN** (uang nyangkut punya penyelesaian sah).

    INV-CASE-01  Kasus `resolved` WAJIB punya **dokumen turunan** + **alasan berlabel** +
                 **penyelesai**. Inilah yang membuat "sudah beres kok" tidak bisa terjadi
                 tanpa jejak: kalau kasus ditutup, harus ada surat/jurnal yang lahir.
    INV-CASE-02  Tidak ada **dana titipan** (2-1950, FASE G-8) yang menganggur lebih lama
                 dari `case.holding_case_after_days` TANPA kasus terbuka. Uang tak dikenal
                 tidak boleh terlupakan tanpa penanggung jawab.
    INV-CASE-03  Kasus yang **memindahkan uang** wajib punya jurnal, dan jurnalnya
                 seimbang. Playbook `moves_cash=False` (realokasi antar pesanan)
                 dikecualikan DENGAN SENGAJA: di buku besar akunnya sama (1-1200 Piutang),
                 jadi jurnal baru justru menyesatkan — pengecualiannya dideklarasikan di
                 `services/finance_case_playbooks.py`, bukan disembunyikan di sini.
    """
    print(f"\n{C}{B}L4-CASE — Invarian Pusat Kasus Keuangan (FASE G-9){X}")
    sys.path.insert(0, "/app/backend")
    try:
        from services import finance_case_scan as fcs
    except Exception as exc:  # noqa: BLE001
        results["fail"] += 1
        line("FAIL", R, "INV-CASE: layanan FASE G-9 tidak bisa diimpor", str(exc))
        return

    total = await db["finance_cases"].count_documents({})
    resolved = await db["finance_cases"].count_documents({"status": "resolved"})

    # ── INV-CASE-01 ─────────────────────────────────────────────────────────
    bad1 = await fcs.resolved_without_documents()
    if bad1:
        results["fail"] += 1
        line("FAIL", R, f"INV-CASE-01: {len(bad1)} kasus 'selesai' tanpa dokumen/alasan/penyelesai",
             str([f"{b['number']}: {b['missing']}" for b in bad1[:4]]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-CASE-01: {resolved} kasus selesai punya dokumen turunan, "
                        f"alasan berlabel & penyelesai (dari {total} kasus)")

    # ── INV-CASE-02 ─────────────────────────────────────────────────────────
    bad2 = await fcs.aged_holding_without_case()
    if bad2:
        results["fail"] += 1
        line("FAIL", R, f"INV-CASE-02: {len(bad2)} titipan dana menganggur lama TANPA kasus terbuka",
             str([f"{b['stmt_date']} Rp {b['amount']:,.0f}" for b in bad2[:4]]))
    else:
        results["pass"] += 1
        pol = await fcs.svc.policy("")
        aged = await fcs.aged_holding_lines(pol["holding_days"])
        line("PASS", G, f"INV-CASE-02: {len(aged)} titipan dana berumur > "
                        f"{pol['holding_days']} hari semuanya punya kasus terbuka "
                        "(tidak ada uang terlupakan)")

    # ── INV-CASE-03 ─────────────────────────────────────────────────────────
    bad3 = await fcs.resolved_without_journal()
    if bad3:
        results["fail"] += 1
        line("FAIL", R, f"INV-CASE-03: {len(bad3)} kasus memindahkan uang tanpa jurnal seimbang",
             str([f"{b['number']}: {b['reason']}" for b in bad3[:4]]))
    else:
        results["pass"] += 1
        je_cnt = await db.journal_entries.count_documents({"source_type": "finance_case"})
        line("PASS", G, f"INV-CASE-03: setiap kasus uang berjurnal seimbang "
                        f"({je_cnt} jurnal kasus terbit)")


async def layer_contra_bon_invariants(db):
    """FASE G-7 — Invarian **KONTRABON** (siklus tukar faktur supplier).

    INV-CB-01  Satu faktur supplier hanya boleh berada di **satu** kontrabon yang belum
               dibatalkan, dan Σ nilai yang dikontrabonkan atas satu faktur ≤ nilai
               fakturnya. Kalau bocor: satu tagihan bisa dibayar dua kali lewat dua
               siklus — kerugian uang yang tak terlihat di layar mana pun.
    INV-CB-02  `net_payable == Σ faktur − Σ potongan` (≥ 0); kontrabon `paid` → Σ
               pembayaran == nilai bersih; dan uang yang keluar + potongan benar-benar
               **menempel di subledger faktur** (menutup drift GL↔daftar hutang yang
               ada sebelum fase ini).
    INV-CB-03  Selisih 3-way di luar toleransi WAJIB punya **keputusan berlabel** sebelum
               kontrabon melewati verifikasi; labelnya wajib terdaftar untuk kontrabon
               (bukan sembarang kode) — pelajaran `KN-G9-REASON-MISMATCH`.
    INV-CB-04  Satu nota debit / uang muka hanya boleh dipotong di satu kontrabon, tidak
               melebihi nilai dokumen sumbernya, potongan klaim makloon yang sudah
               menempel di faktur tidak boleh dipotong lagi, dan potongan yang butuh
               jurnal wajib berjurnal — sedangkan retur beli TIDAK boleh berjurnal ulang.
    """
    print(f"\n{C}{B}L4-CB — Invarian Kontrabon / Tukar Faktur (FASE G-7){X}")
    sys.path.insert(0, "/app/backend")
    try:
        from services import contra_bon_scan as cbn
    except Exception as exc:  # noqa: BLE001
        results["fail"] += 1
        line("FAIL", R, "INV-CB: layanan FASE G-7 tidak bisa diimpor", str(exc))
        return

    st = await cbn.stats()

    # ── INV-CB-01 ───────────────────────────────────────────────────────────
    dup = await cbn.bills_in_multiple_contra_bons()
    over = await cbn.bill_over_applied()
    if dup or over:
        results["fail"] += 1
        line("FAIL", R, f"INV-CB-01: {len(dup)} faktur di >1 kontrabon aktif · "
                        f"{len(over)} faktur nilainya kelebihan",
             str([d.get("reason") for d in (dup + over)[:3]]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-CB-01: {st['live']} kontrabon aktif — tidak ada faktur yang "
                        f"dipegang dua kontrabon & nilainya tak melebihi faktur")

    # ── INV-CB-02 ───────────────────────────────────────────────────────────
    tot = await cbn.totals_mismatch()
    settle = await cbn.settlement_mismatch()
    if tot or settle:
        results["fail"] += 1
        line("FAIL", R, f"INV-CB-02: {len(tot)} total tidak konsisten · "
                        f"{len(settle)} pelunasan tak menempel di faktur",
             str([f"{b.get('number')}: {b.get('reason')}" for b in (tot + settle)[:3]]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-CB-02: {st['total']} kontrabon konsisten "
                        f"(net = faktur − potongan) · {st['paid']} lunas & pelunasannya "
                        "menempel di subledger hutang")

    # ── INV-CB-03 ───────────────────────────────────────────────────────────
    und = await cbn.undecided_exceptions()
    nore = await cbn.decisions_without_reason()
    if und or nore:
        results["fail"] += 1
        line("FAIL", R, f"INV-CB-03: {len(und)} selisih tanpa keputusan · "
                        f"{len(nore)} keputusan tanpa label alasan sah",
             str([f"{b.get('number')}: {b.get('reason')}" for b in (und + nore)[:3]]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-CB-03: setiap selisih 3-way di luar toleransi diputus berlabel "
                        "sebelum verifikasi (tidak ada selisih diterima diam-diam)")

    # ── INV-CB-04 ───────────────────────────────────────────────────────────
    reuse = await cbn.deduction_refs_reused()
    cap = await cbn.deduction_over_source()
    mak = await cbn.makloon_double_deduction()
    je = await cbn.deduction_journal_missing()
    if reuse or cap or mak or je:
        results["fail"] += 1
        line("FAIL", R, f"INV-CB-04: {len(reuse)} dokumen potongan dipakai ulang · "
                        f"{len(cap)} melebihi sumber · {len(mak)} dobel potong makloon · "
                        f"{len(je)} jurnal potongan salah",
             str([b.get("reason") for b in (reuse + cap + mak + je)[:3]]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-CB-04: {st['deductions']} potongan menunjuk dokumen nyata, "
                        "sekali pakai, tak melebihi sumbernya, dan jurnalnya tepat "
                        "(retur beli sengaja tanpa jurnal ulang)")


async def layer_payment_variance_invariants(db):
    """FASE G-3 — Invarian **SELISIH PEMBAYARAN** (lebih & kurang bayar).

    INV-VAR-01  Setiap selisih di luar toleransi punya **keputusan berlabel**: kwitansi
                tidak boleh menggantung tanpa keputusan, dan setiap keputusan wajib punya
                kode alasan + pemutus. Inilah yang membuat "ya sudah anggap lunas" tidak
                bisa terjadi di luar sistem.
    INV-VAR-02  Uang tidak hilang: pada tiap kwitansi `dana == teralokasi + belum
                teralokasi`; setiap keputusan yang MEMINDAHKAN uang (hapus sisa / alokasi
                ulang / pengembalian) punya jurnal; dan tidak ada keputusan yang
                memindahkan lebih besar dari kelebihan bayar kwitansinya.

    CATATAN KEJUJURAN: kwitansi yang lahir SEBELUM FASE G-3 (mis. dari seed atau
    rekonsiliasi bank lama) tidak punya blok `variance` — invarian ini TIDAK menuduhnya
    melanggar, karena selisihnya memang belum pernah ditakar. Yang dijaga adalah semua
    kwitansi baru yang lewat mesin G-3.
    """
    print(f"\n{C}{B}L4-VAR — Invarian Selisih Pembayaran (FASE G-3){X}")
    sys.path.insert(0, "/app/backend")
    try:
        from services import payment_variance_service as pvs
    except Exception as exc:  # noqa: BLE001
        results["fail"] += 1
        line("FAIL", R, "INV-VAR: layanan FASE G-3 tidak bisa diimpor", str(exc))
        return

    total_dec = await db[pvs.COLL].count_documents({})
    scored = await db.ar_receipts.count_documents({"variance": {"$exists": True}})

    # ── INV-VAR-01 ──────────────────────────────────────────────────────────
    undecided = await pvs.undecided_variances()
    unlabeled = await pvs.decisions_without_label()
    if unlabeled:
        results["fail"] += 1
        line("FAIL", R, f"INV-VAR-01: {len(unlabeled)} keputusan selisih tanpa label alasan "
                        "atau tanpa pemutus", str([d["number"] for d in unlabeled[:5]]))
    elif undecided:
        # Selisih yang masih di antrean BUKAN pelanggaran selama masih segar — yang
        # berbahaya adalah selisih yang dibiarkan menggantung berhari-hari.
        stale = [d for d in undecided if d.get("age_days", 0) > 7]
        if stale:
            results["fail"] += 1
            line("FAIL", R, f"INV-VAR-01: {len(stale)} kwitansi ber-selisih menggantung "
                            ">7 hari tanpa keputusan",
                 str([f"{d['number']}({d['age_days']}h)" for d in stale[:5]]))
        else:
            results["warn"] += 1
            line("WARN", Y, f"INV-VAR-01: {len(undecided)} kwitansi ber-selisih menunggu "
                            "keputusan di antrean Selisih Bayar",
                 "→ wajar bila baru; jadi FAIL bila dibiarkan >7 hari")
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-VAR-01: {total_dec} keputusan selisih semuanya ber-alasan & "
                        f"ber-pemutus · tak ada selisih menggantung "
                        f"(dari {scored} kwitansi ter-takar)")

    # ── INV-VAR-02 ──────────────────────────────────────────────────────────
    leaks = await pvs.receipt_money_leaks()
    no_je = await pvs.sensitive_without_journal()
    overspent = await pvs.overspent_decisions()
    if leaks:
        results["fail"] += 1
        line("FAIL", R, f"INV-VAR-02a: {len(leaks)} kwitansi dananya tidak sama dengan "
                        "teralokasi + belum teralokasi",
             str([f"{d['number']}: {d['funds']} vs {d['parts']}" for d in leaks[:4]]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-VAR-02a: setiap kwitansi — dana == teralokasi + belum "
                        "teralokasi (tidak ada uang hilang)")
    if no_je:
        results["fail"] += 1
        line("FAIL", R, f"INV-VAR-02b: {len(no_je)} keputusan memindahkan uang TANPA jurnal",
             str([f"{d['number']}({d['kind']})" for d in no_je[:5]]))
    elif overspent:
        results["fail"] += 1
        line("FAIL", R, f"INV-VAR-02b: {len(overspent)} keputusan memindahkan lebih besar "
                        "dari kelebihan bayar kwitansinya",
             str([f"{d['number']}: {d['amount']} > {d['cap']}" for d in overspent[:4]]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-VAR-02b: setiap rupiah yang dipindah keputusan selisih punya "
                        "jurnal & tidak melebihi kelebihan bayarnya")


async def layer_movement_ledger_invariants(db):
    """
    INV-MOV-01..04 — integritas LEDGER MUTASI STOK  [BARU 2026-07-26]

    LATAR BELAKANG (kenapa lapisan ini lahir):
      Audit guardrail 2026-07-26 menemukan `scripts/guardrails/verify_state_machine.py`
      membocorkan 2 baris `inventory_movements` setiap kali gate dijalankan — sebuah
      `initial_stock` tambahan 250 yard pada produk seed NYATA `prod_batik_mega`,
      sehingga ledger mutasinya membengkak 300 -> 550 yard. TIDAK ADA satu pun dari
      179 invarian yang menangkapnya, karena semua invarian stok memeriksa
      `inventory_balances` sementara kebocoran terjadi di `inventory_movements`.
      Lapisan ini menutup celah itu.

    CATATAN PENTING (kejujuran model data):
      Invarian "Σ inventory_movements == on_hand_qty" DIUJI dan **TIDAK VALID** di
      repo ini: 14 dari 22 pasangan (produk,gudang) tidak rekonsiliasi pada seed
      bersih, bahkan ada balance dengan NOL mutasi (mis. prod_ulos_batak/wh_jakarta
      on_hand 95 tanpa mutasi). Artinya ledger mutasi bersifat ILUSTRATIF, bukan
      sumber otoritatif saldo. Menambahkan invarian itu = menambah gate palsu yang
      selalu merah. Karena itu di sini hanya dipasang invarian yang BENAR-BENAR
      berlaku dan tetap menangkap kebocoran nyata.
    """
    print(f"\n{C}{B}L-MOV — Integritas ledger mutasi stok (INV-MOV-01..04){X}")

    movements = await db.inventory_movements.find({}, {"_id": 0}).to_list(20000)
    prods = {p["id"] for p in await db.products.find({}, {"id": 1}).to_list(5000)}
    whs = {w["id"] for w in await db.warehouses.find({}, {"id": 1}).to_list(500)}

    # INV-MOV-01 — stok awal hanya boleh tercatat SEKALI per (produk, gudang).
    from collections import defaultdict as _dd
    init_seen = _dd(list)
    for m in movements:
        if (m.get("movement_type") or "") == "initial_stock":
            init_seen[(m.get("product_id"), m.get("warehouse_id"))].append(
                float(m.get("quantity") or 0))
    dup_init = {k: v for k, v in init_seen.items() if len(v) > 1}
    if dup_init:
        results["fail"] += 1
        sample = list(dup_init.items())[:3]
        line("FAIL", R, f"INV-MOV-01: {len(dup_init)} pasangan (produk,gudang) punya "
                        f"initial_stock GANDA",
             f"→ ledger stok awal terhitung dobel: {sample} "
             f"(penyebab tipikal: alat uji/guardrail menulis fixture tanpa cleanup)")
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-MOV-01: {len(init_seen)} pasangan punya initial_stock "
                        f"— tidak ada yang ganda")

    # INV-MOV-02 — tidak ada mutasi yatim (produk / gudang harus hidup).
    orphan = [m.get("id") for m in movements
              if m.get("product_id") not in prods or m.get("warehouse_id") not in whs]
    if orphan:
        results["fail"] += 1
        line("FAIL", R, f"INV-MOV-02: {len(orphan)} mutasi menunjuk produk/gudang "
                        f"yang tidak ada", str(orphan[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-MOV-02: {len(movements)} mutasi — semua produk & gudang hidup")

    # INV-MOV-03 — mutasi qty nol tidak bermakna (indikasi tulis gagal/parsial).
    zero = [m.get("id") for m in movements if float(m.get("quantity") or 0) == 0]
    if zero:
        results["fail"] += 1
        line("FAIL", R, f"INV-MOV-03: {len(zero)} mutasi ber-quantity NOL", str(zero[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-MOV-03: tidak ada mutasi ber-quantity nol")

    # INV-MOV-04 — timestamp wajib ada, terparse, dan TIMEZONE-AWARE.
    #   Datetime naive membuat batas hari laporan/absen bergeser tanpa jejak.
    import datetime as _dt
    miss, naive, unparsed = [], [], []
    for m in movements:
        ts = m.get("timestamp")
        if not ts:
            miss.append(m.get("id")); continue
        try:
            d = _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            unparsed.append(m.get("id")); continue
        if d.tzinfo is None:
            naive.append(m.get("id"))
    bad_ts = miss + naive + unparsed
    if bad_ts:
        results["fail"] += 1
        line("FAIL", R, f"INV-MOV-04: {len(bad_ts)} mutasi bermasalah waktu "
                        f"(kosong={len(miss)} naive={len(naive)} tak-terparse={len(unparsed)})",
             str(bad_ts[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-MOV-04: {len(movements)} mutasi — timestamp ada & timezone-aware")


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRI LAPISAN — satu daftar, dipakai `main()` DAN opsi `--only`.
# ─────────────────────────────────────────────────────────────────────────────
# KENAPA ADA `--only` (terukur 2026-07-29):
#   Satu eksekusi LENGKAP = 211 invarian ≈ 8 detik (CPU-bound, bukan IO).
#   POC fase memanggil skrip ini 8–10× (pola BUKTI-MERAH: suntik pelanggaran →
#   pastikan invarian TERKAIT memerah → pulihkan). Jadi 4 POC fase membakar
#   ±220 detik hanya untuk menunggu invarian yang TIDAK diuji.
#   `--only rnd` menjalankan HANYA lapisan yang relevan (±0.5 detik) sehingga
#   `gate.sh --full` turun drastis TANPA mengurangi cakupan: klaim GLOBAL
#   ("seluruh invarian hijau / nol residu") tetap memakai eksekusi LENGKAP.
#
# Setiap entri: (kunci, fungsi, butuh_db). `alias` = awalan invarian yang
# dilaporkan lapisan itu, supaya `--only INV-RND` juga sah.
async def layer_interco_invariants(db):
    """FASE G-6 — Invarian **TRANSAKSI ANTAR ENTITAS** (jual-beli antar-PT).

    INV-IC-01  Setiap transaksi antar-PT punya **pasangan jurnal seimbang di DUA buku**
               (penjual: IC-AR/Pendapatan + HPP; pembeli: Persediaan/IC-AP). Tidak ada
               dokumen yang hanya membebani satu PT — dan transaksi yang DIBATALKAN
               setelah dikonfirmasi wajib sudah **dibalik** (dampak bersih nol), bukan
               sekadar berganti status.
    INV-IC-02  `IC-AR` di PT penjual **sama besar** dengan `IC-AP` di PT pembeli untuk
               setiap ARAH DAGANG (setelah settlement diperhitungkan), baik dilihat
               dari `interco_accounts` maupun dari jurnal — dan **tidak boleh ada dua
               baris beperan sama yang berbagi satu arah dagang** (saling menimpa).
    INV-IC-03  Margin antar-PT **ter-eliminasi** di konsolidasi selama barangnya belum
               terjual ke pihak luar: tiap pair aktif punya TEPAT SATU entri auto yang
               seimbang, menghapus pendapatan sebesar subtotal, mengoreksi persediaan
               sebesar margin, dan menghapus IC-AR/IC-AP sebesar **sisa** (bukan nilai
               lama sebelum settlement).
    INV-IC-04  Saldo `interco_accounts` == Σ transaksi terbuka − Σ settlement (tidak
               boleh drift), `settled_amount` tak boleh melebihi nilai dokumen, dan
               **setiap arah dagang yang punya transaksi terbuka WAJIB punya baris
               piutang & utang** (baris yang hilang dulu lolos hijau — KN-G6-ICA-CLOBBER).
    INV-IC-05  PPN keluaran penjual == PPN masukan pembeli untuk transaksi yang sama;
               bila `tanpa_ppn`, kedua sisi WAJIB nol (tidak boleh miring sebelah).
    INV-IC-06  Perpindahan fisik yang tertaut transaksi G-6 **tidak boleh** memposting
               jurnal at-cost M-3 lagi (dobel IC-AR/IC-AP & persediaan), dan roll yang
               berpindah wajib dinilai ulang ke **harga beli internal** supaya GL 1-1300
               pembeli sejalan dengan subledger.
    INV-IC-07  *(FASE G-6b)* **Faktur pajak internal** selalu BERPASANGAN: keluaran di
               buku penjual == masukan di buku pembeli (DPP & PPN sama besar), hanya ada
               untuk transaksi ber-PPN, dan angkanya == nilai bersih transaksi kecuali
               fakturnya ditandai **perlu pengganti** (dokumen terbit tidak diedit).
    INV-IC-08  *(FASE G-6b)* **Retur antar-PT** punya jurnal berpasangan seimbang di dua
               buku, jumlah retur tidak pernah melebihi jumlah transaksi asalnya,
               `returned_amount` == Σ retur yang berlaku, dan retur `completed` wajib
               punya tugas gudang selesai + jurnal barang (bukan hanya berganti status).
    """
    print(f"\n{C}{B}L4-IC — Invarian Transaksi Antar Entitas (FASE G-6){X}")
    # SATU sumber kebenaran untuk rasio "belum terjual keluar": helper yang sama
    # dipakai mesin eliminasi konsolidasi & layar Rapor Margin Grup.
    sys.path.insert(0, "/app/backend")
    from services import interco_margin as _g6_margin
    OPEN = ["confirmed", "shipped", "received", "invoiced"]
    sellers = await db.interco_transactions.find({"role": "seller"}, {"_id": 0}).to_list(20000)
    buyers = {b["pair_id"]: b for b in await db.interco_transactions.find(
        {"role": "buyer"}, {"_id": 0}).to_list(20000)}
    if not sellers:
        results["warn"] += 1
        line("WARN", Y, "INV-IC: belum ada transaksi antar-PT (FASE G-6) untuk diperiksa",
             "jalankan seed_realistic.py atau buat transaksi di layar Antar Entitas")
        return

    jes = await db.journal_entries.find(
        {"source_type": {"$in": ["interco_transaction", "interco_settlement"]}},
        {"_id": 0}).to_list(50000)
    by_src = {}
    for je in jes:
        by_src.setdefault(je.get("source_id", ""), []).append(je)

    def _net(je_list):
        agg = {}
        for je in je_list:
            if je.get("status") == "void":
                continue
            for l in je.get("lines", []):
                agg[l["account_code"]] = round(
                    agg.get(l["account_code"], 0.0)
                    + float(l.get("debit") or 0) - float(l.get("credit") or 0), 2)
        return agg

    # ── INV-IC-01 ───────────────────────────────────────────────────────────
    v1 = []
    for s in sellers:
        pair = s["pair_id"]
        b = buyers.get(pair)
        if not b:
            v1.append(f"{s.get('number')}: dokumen kembar pembeli hilang")
            continue
        if s.get("status") in ("draft",):
            if by_src.get(f"{pair}:seller"):
                v1.append(f"{s.get('number')}: masih draf tapi sudah berjurnal")
            continue
        if s.get("status") == "cancelled":
            if not by_src.get(f"{pair}:seller"):
                continue        # dibatalkan saat masih draf — tidak pernah berjurnal
            net = _net([je for k, v in by_src.items() if k.startswith(f"{pair}:") for je in v])
            drift = {k: v for k, v in net.items() if abs(v) > 0.01}
            if drift:
                v1.append(f"{s.get('number')}: dibatalkan tetapi jurnal belum dibalik {drift}")
            continue
        if float(s.get("grand_total") or 0) <= 0.01:
            continue
        for side in ("seller", "buyer"):
            rows = [je for je in by_src.get(f"{pair}:{side}", []) if je.get("status") != "void"]
            if not rows:
                v1.append(f"{s.get('number')}: jurnal buku {side} tidak ada")
                continue
            for je in rows:
                if abs(float(je.get("total_debit") or 0) - float(je.get("total_credit") or 0)) > 0.01:
                    v1.append(f"{je.get('number')}: jurnal {side} tidak seimbang")
        # Jurnal barang mengikuti BARANGNYA: HPP penjual & penerimaan pembeli hanya
        # ada setelah barang benar-benar berpindah (status received/invoiced/settled).
        delivered = bool([je for je in by_src.get(f"{pair}:receipt", [])
                          if je.get("status") != "void"])
        cogs_rows = [je for je in by_src.get(f"{pair}:cogs", [])
                     if je.get("status") != "void"]
        sudah_terima = bool(s.get("received_at")) or s.get("status") in ("received", "invoiced")
        if sudah_terima:
            if not delivered:
                v1.append(f"{s.get('number')}: sudah diterima tapi jurnal penerimaan "
                          f"(transit→persediaan) tidak ada")
            if not cogs_rows:
                v1.append(f"{s.get('number')}: sudah diterima tapi jurnal HPP penjual tidak ada")
        if not sudah_terima and (delivered or cogs_rows):
            v1.append(f"{s.get('number')}: jurnal barang diposting padahal barangnya "
                      f"belum diterima")
        if delivered and not cogs_rows:
            v1.append(f"{s.get('number')}: penerimaan pembeli berjurnal tetapi HPP penjual tidak")
    if v1:
        results["fail"] += 1
        line("FAIL", R, f"INV-IC-01: {len(v1)} transaksi antar-PT tanpa pasangan jurnal seimbang",
             str(v1[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-IC-01: {len(sellers)} transaksi antar-PT — jurnal berpasangan "
                        f"seimbang di dua buku (pembatalan pun dibalik penuh)")

    # ── INV-IC-02 ───────────────────────────────────────────────────────────
    accounts = await db.interco_accounts.find({}, {"_id": 0}).to_list(5000)

    def _pair_key(a):
        """ARAH DAGANG (penjual>pembeli) sebuah baris saldo.

        Baris baru menyimpannya eksplisit; baris warisan (sebelum
        KN-G6-ICA-CLOBBER ditutup) disimpulkan dari perannya.
        """
        if a.get("pair_key"):
            return str(a["pair_key"])
        if a.get("role") == "receivable":
            return f"{a.get('from_entity_id')}>{a.get('to_entity_id')}"
        return f"{a.get('to_entity_id')}>{a.get('from_entity_id')}"

    v2 = []
    ar_rows = [a for a in accounts if a.get("role") == "receivable"]
    ap_rows = [a for a in accounts if a.get("role") == "payable"]
    ar_by = {}
    ap_by = {}
    # DUA arah dagang tidak boleh berbagi satu baris. Kalau dua baris beperan sama
    # memiliki arah yang sama, salah satu pasti menimpa yang lain (akar
    # KN-G6-ICA-CLOBBER: utang Rp 1.766.010 hilang dari layar tanpa pesan).
    for src, dest, label in ((ar_rows, ar_by, "piutang"), (ap_rows, ap_by, "utang")):
        for a in src:
            k = _pair_key(a)
            if k in dest:
                v2.append(f"{a.get('id')}: dua baris {label} berbagi arah dagang {k} "
                          f"(saling menimpa) — juga {dest[k].get('id')}")
            dest[k] = a
    for k, acc in ar_by.items():
        mirror = ap_by.get(k)
        if not mirror:
            v2.append(f"{acc.get('id')}: cermin utang di PT pembeli tidak ada (arah {k})")
            continue
        if abs(float(acc.get("outstanding") or 0) - float(mirror.get("outstanding") or 0)) > 0.01:
            v2.append(f"{acc.get('id')}: piutang {acc.get('outstanding')} != utang "
                      f"{mirror.get('outstanding')}")
    for k, acc in ap_by.items():
        if k not in ar_by:
            v2.append(f"{acc.get('id')}: cermin piutang di PT penjual tidak ada (arah {k})")
    ar = ap = 0.0
    for je in jes:
        if je.get("status") == "void":
            continue
        for l in je.get("lines", []):
            if l["account_code"] == "1-1250":
                ar += float(l.get("debit") or 0) - float(l.get("credit") or 0)
            if l["account_code"] == "2-1250":
                ap += float(l.get("credit") or 0) - float(l.get("debit") or 0)
    if abs(ar - ap) > 0.01:
        v2.append(f"jurnal: IC-AR bersih {ar:,.2f} != IC-AP bersih {ap:,.2f}")
    if v2:
        results["fail"] += 1
        line("FAIL", R, f"INV-IC-02: {len(v2)} ketidakcocokan piutang↔utang antar-PT", str(v2[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-IC-02: {len(accounts)} baris saldo antar-PT berpasangan sama besar "
                        f"({len(ar_by)} arah dagang · IC-AR bersih {ar:,.0f} == IC-AP bersih {ap:,.0f})")

    # ── INV-IC-03 ───────────────────────────────────────────────────────────
    elims = await db.intercompany_eliminations.find(
        {"source_g6_pair_id": {"$exists": True, "$ne": None}}, {"_id": 0}).to_list(5000)
    elim_by_pair = {}
    for e in elims:
        elim_by_pair.setdefault(e["source_g6_pair_id"], []).append(e)
    v3 = []
    active = [s for s in sellers if s.get("status") not in ("draft", "cancelled")]
    for s in active:
        pair = s["pair_id"]
        rows = elim_by_pair.get(pair, [])
        if len(rows) != 1:
            v3.append(f"{s.get('number')}: {len(rows)} entri eliminasi (harus tepat 1)")
            continue
        e = rows[0]
        if not e.get("balanced"):
            v3.append(f"{e.get('name')}: entri eliminasi tidak seimbang")
            continue
        # FASE G-6b — nilai EFEKTIF: bagian yang sudah diretur bukan transaksi
        # intra-grup lagi, dan hanya margin yang masih menempel di persediaan
        # pembeli (u) yang boleh dieliminasi.
        sub_eff = round(float(s.get("subtotal") or 0)
                        - float(s.get("returned_subtotal") or 0), 2)
        rev = sum(float(l.get("debit") or 0) for l in e.get("lines", [])
                  if l["account_code"] == "4-1000")
        if abs(rev - sub_eff) > 0.01:
            v3.append(f"{s.get('number')}: pendapatan intra-grup dieliminasi {rev:,.2f} "
                      f"!= subtotal efektif {sub_eff:,.2f}")
        cogs_je = await db.journal_entries.find_one(
            {"source_type": "interco_transaction", "source_id": f"{pair}:cogs",
             "status": "posted"}, {"_id": 0, "total_debit": 1})
        cost_eff = round(float((cogs_je or {}).get("total_debit") or 0)
                         - float(s.get("returned_cost") or 0), 2)
        margin_eff = round(sub_eff - cost_eff, 2)
        # SATU sumber kebenaran rasio: helper yang dipakai mesin eliminasi juga.
        u_info = await _g6_margin.unsold_ratio(pair, seller=s)
        u = max(0.0, min(1.0, float(u_info["ratio"])))
        want_unreal = round(margin_eff * u, 2)
        stored_u = e.get("g6_unsold_ratio")
        if stored_u is not None and abs(float(stored_u) - u) > 0.001:
            v3.append(f"{s.get('number')}: rasio belum-terjual tersimpan {stored_u} != "
                      f"hitung ulang {u}")
        inv_c = sum(float(l.get("credit") or 0) for l in e.get("lines", [])
                    if l["account_code"] in ("1-1300", "1-1310"))
        inv_d = sum(float(l.get("debit") or 0) for l in e.get("lines", [])
                    if l["account_code"] in ("1-1300", "1-1310"))
        if want_unreal > 0.005 and abs(inv_c - want_unreal) > 0.01:
            v3.append(f"{s.get('number')}: unrealized profit {inv_c:,.2f} != margin belum "
                      f"terealisasi {want_unreal:,.2f} (margin {margin_eff:,.2f} × u={u})")
        if want_unreal < -0.005 and abs(inv_d - abs(want_unreal)) > 0.01:
            v3.append(f"{s.get('number')}: koreksi persediaan jual-rugi tidak sesuai")
        outstanding = round(float(s.get("grand_total") or 0)
                            - float(s.get("settled_amount") or 0)
                            - float(s.get("returned_amount") or 0), 2)
        ic_ap = sum(float(l.get("debit") or 0) for l in e.get("lines", [])
                    if l["account_code"] == "2-1250")
        if abs(ic_ap - max(outstanding, 0)) > 0.01:
            v3.append(f"{s.get('number')}: eliminasi IC-AP {ic_ap:,.2f} != sisa {outstanding:,.2f}")
    stale = [p for p in elim_by_pair
             if p not in {s["pair_id"] for s in active}]
    for p in stale:
        v3.append(f"pair {p}: entri eliminasi tertinggal padahal transaksinya tidak aktif")
    if v3:
        results["fail"] += 1
        line("FAIL", R, f"INV-IC-03: {len(v3)} masalah eliminasi unrealized profit", str(v3[:4]))
    else:
        results["pass"] += 1
        margin_total = 0.0
        for s in active:
            e = elim_by_pair.get(s["pair_id"], [{}])[0]
            margin_total += sum(float(l.get("credit") or 0) for l in e.get("lines", [])
                                if l["account_code"] in ("1-1300", "1-1310"))
        line("PASS", G, f"INV-IC-03: {len(active)} pair aktif ter-eliminasi otomatis di "
                        f"konsolidasi (unrealized profit Rp {margin_total:,.0f} tidak "
                        f"menggelembungkan laba grup)")

    # ── INV-IC-04 ───────────────────────────────────────────────────────────
    v4 = []
    for acc in accounts:
        sel, buy = _pair_key(acc).split(">", 1)
        docs = [s for s in sellers if s.get("seller_entity_id") == sel
                and s.get("buyer_entity_id") == buy and s.get("status") in OPEN]
        expected = round(sum(float(d.get("grand_total") or 0) -
                             float(d.get("settled_amount") or 0) -
                             float(d.get("returned_amount") or 0) for d in docs), 2)
        if abs(expected - float(acc.get("outstanding") or 0)) > 0.01:
            v4.append(f"{acc.get('id')}: outstanding {acc.get('outstanding')} != hitung {expected}")
    # KELENGKAPAN (celah yang ditutup bersama KN-G6-ICA-CLOBBER): dulu invarian ini
    # hanya memeriksa baris yang ADA, jadi baris yang HILANG — tertimpa arah dagang
    # lain — lolos HIJAU sementara utangnya benar-benar menghilang dari layar.
    # Sekarang arah dagang-lah yang memimpin: setiap arah yang punya transaksi
    # terbuka WAJIB punya baris piutang DAN baris utang.
    dirs: dict = {}
    for s in sellers:
        if s.get("status") in OPEN:
            dirs.setdefault(f"{s.get('seller_entity_id')}>{s.get('buyer_entity_id')}",
                            []).append(s)
    for k, docs in dirs.items():
        sel, buy = k.split(">", 1)
        expected = round(sum(float(d.get("grand_total") or 0) -
                             float(d.get("settled_amount") or 0) -
                             float(d.get("returned_amount") or 0) for d in docs), 2)
        for role, bucket, label in (("receivable", ar_by, "piutang"),
                                    ("payable", ap_by, "utang")):
            row = bucket.get(k)
            if not row:
                v4.append(f"arah {sel}→{buy}: baris {label} HILANG padahal ada "
                          f"{len(docs)} dokumen terbuka bersisa {expected:,.2f}")
            elif abs(expected - float(row.get("outstanding") or 0)) > 0.01:
                v4.append(f"{row.get('id')}: {label} {row.get('outstanding')} != "
                          f"hitung {expected}")
    for s in sellers:
        if (float(s.get("settled_amount") or 0) + float(s.get("returned_amount") or 0)
                - float(s.get("grand_total") or 0)) > 0.01:
            v4.append(f"{s.get('number')}: terlunasi+diretur melebihi nilai dokumen")
    settlements = await db.interco_settlements.find({}, {"_id": 0}).to_list(5000)
    for st in settlements:
        tot = round(sum(float(a.get("applied_amount") or 0) for a in st.get("applied", [])), 2)
        if abs(tot - float(st.get("total_applied") or 0)) > 0.01:
            v4.append(f"{st.get('number')}: total {st.get('total_applied')} != Σ baris {tot}")
    if v4:
        results["fail"] += 1
        line("FAIL", R, f"INV-IC-04: {len(v4)} drift saldo antar-PT / settlement", str(v4[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-IC-04: {len(accounts)} saldo pasangan PT == Σ transaksi − Σ "
                        f"settlement ({len(dirs)} arah dagang lengkap piutang+utang · "
                        f"{len(settlements)} settlement konsisten)")

    # ── INV-IC-05 ───────────────────────────────────────────────────────────
    v5 = []
    for s in sellers:
        pair = s["pair_id"]
        if s.get("status") in ("draft", "cancelled"):
            continue
        out_ppn = sum(float(l.get("credit") or 0)
                      for je in by_src.get(f"{pair}:seller", [])
                      for l in je.get("lines", []) if l["account_code"] == "2-1200")
        in_ppn = sum(float(l.get("debit") or 0)
                     for je in by_src.get(f"{pair}:buyer", [])
                     for l in je.get("lines", []) if l["account_code"] == "1-1500")
        if abs(out_ppn - in_ppn) > 0.01:
            v5.append(f"{s.get('number')}: PPN keluaran {out_ppn:,.2f} != masukan {in_ppn:,.2f}")
        if not s.get("tax_apply") and (out_ppn > 0.01 or in_ppn > 0.01):
            v5.append(f"{s.get('number')}: mode tanpa PPN tapi ada PPN di jurnal")
        if s.get("tax_apply") and abs(out_ppn - float(s.get("tax_amount") or 0)) > 0.01:
            v5.append(f"{s.get('number')}: PPN jurnal {out_ppn:,.2f} != dokumen "
                      f"{float(s.get('tax_amount') or 0):,.2f}")
    if v5:
        results["fail"] += 1
        line("FAIL", R, f"INV-IC-05: {len(v5)} ketidakcocokan PPN antar-PT", str(v5[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, "INV-IC-05: PPN keluaran penjual == PPN masukan pembeli untuk setiap "
                        "transaksi antar-PT (mode tanpa-PPN nol di kedua sisi)")

    # ── INV-IC-06 (jembatan gudang) ─────────────────────────────────────────
    linked = await db.warehouse_transfers.find(
        {"interco_pair_id": {"$exists": True, "$ne": None}}, {"_id": 0}).to_list(5000)
    v6 = []
    for t in linked:
        pair = t.get("interco_pair_id")
        s = next((x for x in sellers if x["pair_id"] == pair), None)
        if not s:
            v6.append(f"{t.get('code')}: menaut pair {pair} yang tidak ada")
            continue
        atcost = await db.journal_entries.count_documents(
            {"source_type": "inter_company_transfer",
             "source_id": {"$regex": t["id"]}})
        if atcost:
            v6.append(f"{t.get('code')}: {atcost} jurnal at-cost M-3 DOBEL "
                      f"(G-6 sudah memposting harga jual)")
        if t.get("status") != "completed":
            continue
        price = {it["product_id"]: float(it.get("unit_price") or 0)
                 for it in s.get("items", [])}
        moved = await db.inventory_rolls.find(
            {"acquired.ref_id": t["id"], "owner_entity_id": t.get("dest_entity_id")},
            {"_id": 0, "product_id": 1, "unit_cost": 1, "roll_no": 1}).to_list(10000)
        if not moved:
            v6.append(f"{t.get('code')}: selesai tetapi tidak ada roll di PT pembeli")
        for m in moved:
            want = price.get(m.get("product_id"))
            if want and abs(float(m.get("unit_cost") or 0) - want) > 0.01:
                v6.append(f"{t.get('code')}/{m.get('roll_no')}: nilai roll "
                          f"{m.get('unit_cost')} != harga beli internal {want}")
    # Transit WAJIB kosong untuk pair yang sudah diterima (Dr 1-1310 saat konfirmasi
    # harus dihapus Cr 1-1310 saat penerimaan) — kalau tidak, neraca pembeli memuat
    # "barang dalam perjalanan" untuk barang yang sudah ada di gudangnya.
    for s in sellers:
        if not (s.get("received_at") or s.get("status") in ("received", "invoiced")):
            continue
        transit = 0.0
        for key in (f"{s['pair_id']}:buyer", f"{s['pair_id']}:receipt"):
            for je in by_src.get(key, []):
                if je.get("status") == "void":
                    continue
                for l in je.get("lines", []):
                    if l["account_code"] == "1-1310":
                        transit += float(l.get("debit") or 0) - float(l.get("credit") or 0)
        if abs(transit) > 0.01:
            v6.append(f"{s.get('number')}: saldo transit 1-1310 tersisa {transit:,.2f} "
                      f"padahal barang sudah diterima")
    if v6:
        results["fail"] += 1
        line("FAIL", R, f"INV-IC-06: {len(v6)} masalah jembatan gudang antar-PT", str(v6[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-IC-06: {len(linked)} tugas gudang antar-PT tanpa jurnal dobel; "
                        f"roll pembeli dinilai ulang ke harga beli internal")

    # ── INV-IC-07 (FASE G-6b — faktur pajak internal) ───────────────────────
    fkt_out = await db.tax_invoices.find({"source_type": "interco"}, {"_id": 0}).to_list(5000)
    fkt_in = await db.tax_invoices_in.find({"source_type": "interco"}, {"_id": 0}).to_list(5000)
    by_pair_out = {}
    for f in fkt_out:
        by_pair_out.setdefault(f.get("interco_pair_id"), []).append(f)
    by_pair_in = {}
    for f in fkt_in:
        by_pair_in.setdefault(f.get("interco_pair_id"), []).append(f)
    seller_by_pair = {s["pair_id"]: s for s in sellers}
    v7 = []
    for pair, outs in by_pair_out.items():
        s = seller_by_pair.get(pair)
        if not s:
            v7.append(f"faktur pajak internal menaut pair {pair} yang tidak ada")
            continue
        act_out = [f for f in outs if f.get("status") in ("normal", "pengganti")
                   and not f.get("replaced_by_id")]
        act_in = [f for f in by_pair_in.get(pair, []) if f.get("status") == "recorded"]
        if len(act_out) > 1:
            v7.append(f"{s.get('number')}: {len(act_out)} faktur pajak keluaran aktif (harus ≤1)")
        if act_out and len(act_in) != 1:
            v7.append(f"{s.get('number')}: faktur keluaran ada tetapi pasangan masukan "
                      f"aktif {len(act_in)} (harus tepat 1 — PPN masukan pembeli hilang)")
        for f in act_out:
            if not s.get("tax_apply") or float(s.get("tax_amount") or 0) <= 0.01:
                v7.append(f"{f.get('number')}: faktur pajak terbit untuk transaksi TANPA PPN")
            if f.get("entity_id") != s.get("seller_entity_id"):
                v7.append(f"{f.get('number')}: buku faktur keluaran bukan PT penjual")
            for g in act_in:
                if abs(float(f.get("ppn_amount") or 0) - float(g.get("ppn_amount") or 0)) > 0.01:
                    v7.append(f"{f.get('number')}: PPN keluaran {f.get('ppn_amount')} != "
                              f"PPN masukan {g.get('ppn_amount')} pada {g.get('number')}")
                if abs(float(f.get("dpp") or 0) - float(g.get("dpp") or 0)) > 0.01:
                    v7.append(f"{f.get('number')}: DPP keluaran != DPP masukan {g.get('number')}")
                if g.get("entity_id") != s.get("buyer_entity_id"):
                    v7.append(f"{g.get('number')}: buku faktur masukan bukan PT pembeli")
            net_ppn = round(float(s.get("tax_amount") or 0)
                            - float(s.get("returned_tax") or 0), 2)
            # Angka boleh tertinggal HANYA bila fakturnya ditandai perlu pengganti
            # (praktik e-Faktur: dokumen terbit tidak diedit diam-diam).
            if abs(float(f.get("ppn_amount") or 0) - net_ppn) > 0.01 \
                    and not f.get("needs_replacement"):
                v7.append(f"{f.get('number')}: PPN faktur {f.get('ppn_amount')} != PPN bersih "
                          f"transaksi {net_ppn} tanpa ditandai perlu pengganti")
    for pair, inns in by_pair_in.items():
        if pair not in by_pair_out and [g for g in inns if g.get("status") == "recorded"]:
            v7.append(f"pair {pair}: faktur masukan internal tanpa pasangan keluaran")
    if v7:
        results["fail"] += 1
        line("FAIL", R, f"INV-IC-07: {len(v7)} masalah faktur pajak internal antar-PT",
             str(v7[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-IC-07: {len(fkt_out)} faktur pajak internal berpasangan "
                        f"(keluaran penjual == masukan pembeli, hanya untuk transaksi ber-PPN)")

    # ── INV-IC-08 (FASE G-6b — retur antar-PT) ──────────────────────────────
    rets = await db.interco_returns.find({}, {"_id": 0}).to_list(20000)
    ret_jes = await db.journal_entries.find(
        {"source_type": "interco_return"}, {"_id": 0}).to_list(20000)
    ret_by_src = {}
    for je in ret_jes:
        ret_by_src.setdefault(je.get("source_id", ""), []).append(je)
    returners = [r for r in rets if r.get("role") == "returner"]
    receivers = {r["return_pair_id"]: r for r in rets if r.get("role") == "receiver"}
    v8 = []
    per_origin = {}
    for r in returners:
        rp = r["return_pair_id"]
        if rp not in receivers:
            v8.append(f"{r.get('number')}: dokumen kembar penjual (nota kredit) hilang")
        if r.get("status") == "draft":
            if ret_by_src.get(f"{rp}:seller") or ret_by_src.get(f"{rp}:buyer"):
                v8.append(f"{r.get('number')}: masih draf tapi sudah berjurnal")
            continue
        if r.get("status") == "cancelled":
            continue
        for side in ("seller", "buyer"):
            rows = [je for je in ret_by_src.get(f"{rp}:{side}", [])
                    if je.get("status") != "void"]
            if not rows:
                v8.append(f"{r.get('number')}: jurnal retur buku {side} tidak ada")
                continue
            for je in rows:
                if abs(float(je.get("total_debit") or 0)
                       - float(je.get("total_credit") or 0)) > 0.01:
                    v8.append(f"{je.get('number')}: jurnal retur {side} tidak seimbang")
        if r.get("status") == "completed":
            # FASE E-9 — jurnal sisi barang HANYA ada bila memang ada nilai yang
            # berpindah. Sejak E9.4 yang dikembalikan bisa roll hasil retur pelanggan
            # yang sudah dihapus-bukukan (nilai Rp 0): tidak ada nilai yang keluar dari
            # persediaan pembeli, jadi jurnal palsu justru merusak GL. Karena itu
            # dokumen retur MENCATAT nilainya (`goods_out_value`/`goods_in_value`) dan
            # invarian ini menuntut kesesuaian dua arah:
            #   nilai > 0  → jurnal WAJIB ada & nominalnya sama
            #   nilai == 0 → jurnal WAJIB tidak ada (bukan "boleh lupa")
            for blk, val in (("goods_out", r.get("goods_out_value")),
                             ("goods_in", r.get("goods_in_value"))):
                rows = [je for je in ret_by_src.get(f"{rp}:{blk}", [])
                        if je.get("status") != "void"]
                if val is None:
                    # Dokumen warisan (sebelum nilai dicatat): aturan lama tetap dipakai.
                    if not rows:
                        v8.append(f"{r.get('number')}: barang sudah kembali tetapi jurnal "
                                  f"{blk} tidak ada")
                    continue
                val = round(float(val or 0), 2)
                if val > 0.01:
                    if not rows:
                        v8.append(f"{r.get('number')}: nilai barang {blk} {val} tetapi "
                                  f"jurnalnya tidak ada")
                        continue
                    posted = round(sum(float(je.get("total_debit") or 0) for je in rows), 2)
                    if abs(posted - val) > 0.01:
                        v8.append(f"{r.get('number')}: jurnal {blk} {posted} != nilai "
                                  f"barang tercatat {val}")
                elif rows:
                    v8.append(f"{r.get('number')}: tidak ada nilai barang {blk} "
                              f"(Rp 0) tetapi jurnalnya ada")
            tr = await db.warehouse_transfers.find_one(
                {"interco_return_pair_id": rp, "status": "completed"}, {"_id": 0, "code": 1})
            if not tr:
                v8.append(f"{r.get('number')}: berstatus selesai tanpa tugas gudang selesai")
        if r.get("status") in ("approved", "completed"):
            o = per_origin.setdefault(r["origin_pair_id"], {"total": 0.0, "qty": {}})
            o["total"] = round(o["total"] + float(r.get("grand_total") or 0), 2)
            for it in r.get("items", []):
                pid = it.get("product_id", "")
                o["qty"][pid] = round(o["qty"].get(pid, 0.0) + float(it.get("quantity") or 0), 4)
    for origin_pair, agg in per_origin.items():
        s = seller_by_pair.get(origin_pair)
        if not s:
            v8.append(f"retur menaut transaksi {origin_pair} yang tidak ada")
            continue
        if abs(float(s.get("returned_amount") or 0) - agg["total"]) > 0.01:
            v8.append(f"{s.get('number')}: returned_amount {s.get('returned_amount')} != "
                      f"Σ retur {agg['total']}")
        origin_qty = {it.get("product_id"): float(it.get("quantity") or 0)
                      for it in s.get("items", [])}
        for pid, q in agg["qty"].items():
            if q > origin_qty.get(pid, 0.0) + 0.0001:
                v8.append(f"{s.get('number')}/{pid}: retur {q} melebihi jumlah transaksi "
                          f"{origin_qty.get(pid, 0.0)}")
    if v8:
        results["fail"] += 1
        line("FAIL", R, f"INV-IC-08: {len(v8)} masalah retur antar-PT", str(v8[:4]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-IC-08: {len(returners)} retur antar-PT berpasangan seimbang di "
                        f"dua buku; jumlah retur tidak melebihi transaksi asalnya")


async def layer_closing_invariants(db):
    """FASE G-5 — Invarian **UNLOCK PERIODE TERTUTUP** (hard-lock + dual-control).

    INV-CLS-01  Tidak ada jurnal yang MENYUSUP ke periode `closed`: setiap JE non-void
                yang tanggalnya berada dalam periode tertutup DAN dibuat SETELAH periode
                itu ditutup wajib berupa jurnal penutup (`source_type='closing'`) ATAU
                membawa tanda `backdated_in_unlock` (lahir di dalam jendela unlock resmi).
                Jurnal operasional yang lahir SEBELUM tutup buku tidak dituduh (memang
                sah — closing-lah yang merangkumnya).
    INV-CLS-02  Setiap usul buka periode yang pernah DISETUJUI (approved/reclosed/expired)
                punya `reason` DAN pengusul ≠ penyetuju (kontrol ganda dua orang).
    """
    print(f"\n{C}{B}L4-CLS — Invarian Unlock Periode Tertutup (FASE G-5){X}")

    closings = await db.period_closings.find(
        {"status": "closed"}, {"_id": 0, "entity_id": 1, "start_date": 1, "end_date": 1,
                               "closed_at": 1, "reclosed_at": 1, "period_label": 1}).to_list(2000)

    # ── INV-CLS-01 ────────────────────────────────────────────────────────────
    v1 = []
    checked = 0
    for c in closings:
        eid = c.get("entity_id")
        s, e = c.get("start_date", ""), c.get("end_date", "")
        if not (eid and s and e):
            continue
        # Ambang "dibuat setelah tutup" = waktu tutup terakhir (reclose lebih baru bila ada).
        cutoff = max(str(c.get("closed_at") or ""), str(c.get("reclosed_at") or ""))
        q = {"entity_id": eid, "status": {"$ne": "void"},
             "date": {"$gte": s, "$lte": e + "T23:59:59.999999"}}
        async for je in db.journal_entries.find(
                q, {"_id": 0, "number": 1, "source_type": 1, "backdated_in_unlock": 1,
                    "created_at": 1, "date": 1}):
            if je.get("source_type") == "closing":
                continue
            created = str(je.get("created_at") or "")
            # Hanya jurnal yang lahir SETELAH periode ditutup yang wajib ber-unlock.
            if cutoff and created and created <= cutoff:
                continue
            checked += 1
            if not je.get("backdated_in_unlock"):
                v1.append(f"{je.get('number')} ({c.get('period_label', '')})")
    if v1:
        results["fail"] += 1
        line("FAIL", R, f"INV-CLS-01: {len(v1)} jurnal mundur menyusup ke periode tertutup "
                        f"tanpa jendela unlock (backdated_in_unlock kosong)", str(v1[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-CLS-01: {len(closings)} periode tertutup — tak ada jurnal mundur "
                        f"tanpa unlock resmi ({checked} jurnal pasca-tutup diperiksa)")

    # ── INV-CLS-02 ────────────────────────────────────────────────────────────
    v2 = []
    approved = await db.period_unlock_requests.find(
        {"status": {"$in": ["approved", "reclosed", "expired"]}}, {"_id": 0}).to_list(2000)
    for r in approved:
        if not (r.get("reason") or "").strip():
            v2.append(f"{r.get('id')}: tanpa alasan")
        rq, ap = r.get("requested_by_id"), r.get("approved_by_id")
        if rq and ap and rq == ap:
            v2.append(f"{r.get('id')}: pengusul == penyetuju (kontrol ganda gagal)")
        if not ap:
            v2.append(f"{r.get('id')}: berstatus {r.get('status')} tanpa penyetuju")
    if v2:
        results["fail"] += 1
        line("FAIL", R, f"INV-CLS-02: {len(v2)} usul unlock melanggar alasan/kontrol-ganda",
             str(v2[:5]))
    else:
        results["pass"] += 1
        line("PASS", G, f"INV-CLS-02: {len(approved)} unlock disetujui — semua ber-alasan & "
                        f"pengusul ≠ penyetuju (dual-control)")


def _layer_registry():
    return [
        ("self",        layer0_self_check,                False, ()),
        ("collections", layer1_collection_reconciliation, True,  ()),
        ("db",          layer2_db_invariants,             True,  ("INV-DB",)),
        ("movement",    layer_movement_ledger_invariants, True,  ("INV-MOV",)),
        ("gl",          layer_gl_invariants,              True,  ("INV-GL",)),
        ("domain",      layer_domain_invariants,          True,  ("INV-DOM",)),
        ("roll",        layer_roll_invariants,            True,  ("INV-ROLL",)),
        ("backorder",   layer_backorder_invariants,       True,  ("INV-BO",)),
        ("shipment",    layer_shipment_invariants,        True,  ("INV-SHIP",)),
        ("tax",         layer_tax_invoice_invariants,     True,  ("INV-TAX",)),
        ("pr",          layer_pr_invariants,              True,  ("INV-PR",)),
        ("return",      layer_return_invariants,          True,  ("INV-RET",)),
        ("asset",       layer_fixed_asset_invariants,     True,  ("INV-FA",)),
        ("budget",      layer_budget_invariants,          True,  ("INV-BUD",)),
        ("production",  layer_production_invariants,      True,  ("INV-PROD",)),
        ("scheduler",   layer_scheduler_invariants,       True,  ("SCH-",)),
        ("ps21",        layer_ps21_invariants,            True,  ("PS21-",)),
        ("uom",         layer_uom_invariants,             True,  ("INV-UOM",)),
        ("lot",         layer_lot_invariants,             True,  ("INV-LOT",)),
        ("makloon",     layer_makloon_invariants,         True,  ("INV-MKO",)),
        ("sourcing",    layer_sourcing_invariants,        True,  ("INV-SRC",)),
        ("receiving",   layer_receiving_uom_invariants,   True,  ("INV-RCV",)),
        ("config",      layer_config_invariants,          True,  ("INV-CFG",)),
        ("amendment",   layer_amendment_invariants,       True,  ("INV-AMD",)),
        ("docref",      layer_docref_invariants,          True,  ("INV-REF",)),
        ("payment",     layer_payment_penalty_invariants, True,  ("INV-PAY", "INV-PEN")),
        ("variance",    layer_payment_variance_invariants, True, ("INV-VAR",)),
        ("bank",        layer_bank_invariants,            True,  ("INV-BNK",)),
        ("case",        layer_finance_case_invariants,    True,  ("INV-CASE",)),
        ("contrabon",   layer_contra_bon_invariants,      True,  ("INV-CB",)),
        ("interco",     layer_interco_invariants,         True,  ("INV-IC",)),
        ("closing",     layer_closing_invariants,         True,  ("INV-CLS",)),
        ("rnd",         layer_rnd_invariants,             True,  ("INV-RND",)),
        ("series",      layer5_number_series,             True,  ("INV-SEQ",)),
        ("intent",      layer3_intent_invariants,         False, ("INV-INTENT",)),
    ]


def _resolve_only(tokens):
    """Ubah daftar token CLI (`rnd`, `INV-RND`, `INV-PAY-01`) menjadi kunci lapisan."""
    reg = _layer_registry()
    keys = {k for k, *_ in reg}
    picked, unknown = [], []
    for raw in tokens:
        t = raw.strip()
        if not t:
            continue
        if t in keys:
            picked.append(t)
            continue
        up = t.upper()
        hit = [k for k, _f, _d, aliases in reg
               if any(up.startswith(a.upper()) or a.upper().startswith(up) for a in aliases)]
        if hit:
            picked += hit
        else:
            unknown.append(t)
    # urutan registri dipertahankan; duplikat dibuang
    order = {k: i for i, (k, *_) in enumerate(reg)}
    return sorted(set(picked), key=lambda k: order[k]), unknown


async def main():
    argv = sys.argv[1:]
    timing = "--timing" in argv
    only_tokens = []
    for i, a in enumerate(argv):
        if a.startswith("--only="):
            only_tokens += a.split("=", 1)[1].split(",")
        elif a == "--only" and i + 1 < len(argv):
            only_tokens += argv[i + 1].split(",")
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        print("  --only KEY[,KEY]   jalankan HANYA lapisan tsb (kunci atau awalan invarian)")
        print("  --timing           tampilkan durasi tiap lapisan")
        print("  kunci tersedia   : " + ", ".join(k for k, *_ in _layer_registry()))
        return 0

    layers = _layer_registry()
    subset = None
    if only_tokens:
        subset, unknown = _resolve_only(only_tokens)
        if unknown:
            print(f"{R}[FAIL]{X} --only tidak dikenal: {unknown}. "
                  f"Kunci sah: {', '.join(k for k, *_ in layers)}")
            return 2
        layers = [row for row in layers if row[0] in subset]

    print(f"{B}{C}{'='*64}{X}")
    print(f"{B}  KN3 — DATA INTEGRITY GATE  (DB={DB_NAME}  API={API}){X}")
    if subset:
        print(f"{B}{Y}  SUBSET --only: {', '.join(subset)}  "
              f"(klaim GLOBAL wajib pakai eksekusi LENGKAP){X}")
    print(f"{B}{C}{'='*64}{X}")

    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    import time as _time
    durations = []
    for key, fn, needs_db, _aliases in layers:
        t0 = _time.perf_counter()
        await (fn(db) if needs_db else fn())
        durations.append((key, _time.perf_counter() - t0))

    if timing:
        print(f"\n{C}{B}DURASI PER LAPISAN (detik){X}")
        for key, dt in sorted(durations, key=lambda r: -r[1]):
            print(f"  {dt:6.2f}  {key}")
        print(f"  {sum(d for _, d in durations):6.2f}  TOTAL")

    print(f"\n{B}{'='*64}{X}")
    print(f"  {G}PASS {results['pass']}{X}  |  {R}FAIL {results['fail']}{X}  |  {Y}WARN {results['warn']}{X}")
    if results["fail"]:
        print(f"  {R}{B}INTEGRITY VIOLATION — blokir seed/deploy sampai diperbaiki.{X}\n")
        return 1
    print(f"  {G}{B}SEMUA INVARIAN VALID.{X}\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
