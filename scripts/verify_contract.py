#!/usr/bin/env python3
"""
verify_contract.py — Kain Nusantara (KN3) Collection Contract Verifier
======================================================================
Verifikasi bahwa kode (seed / router / service baru) menggunakan nama koleksi
MongoDB yang BENAR (kanonik) sesuai ENTITY_REGISTRY.md — mencegah
**RC-1 (Collection Name Drift)** SEBELUM terjadi.

Pelajaran dari case-study Torado (CASE_STUDY_INTENT_DRIFT):
  • Analyzer lama BUTA terhadap akses bracket `db["nama"]` — di sini KEDUA bentuk
    `db.nama` DAN `db["nama"]` dideteksi.
  • Source-of-truth tidak boleh ikut "drift": daftar kanonik di bawah HARUS sama
    dengan ENTITY_REGISTRY.md. Bila menambah koleksi → update keduanya.

Usage:
    cd /app
    python scripts/verify_contract.py --all                 # scan semua router+service
    python scripts/verify_contract.py --router sales_orders  # scan satu router
    python scripts/verify_contract.py --find inventory_balances
    python scripts/verify_contract.py --check-seed seed_realistic
    python scripts/verify_contract.py --list-canonical

Exit code: 0 = bersih. 1 = ditemukan koleksi terlarang (drift) → blokir.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
ROUTERS = BACKEND / "routers"
SERVICES = BACKEND / "services"

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

# ── Koleksi kanonik KN3 — HARUS konsisten dengan ENTITY_REGISTRY.md ────────────
CANONICAL_COLLECTIONS = {
    "users", "sessions", "products", "customers", "warehouses", "uoms",
    "sales_orders", "invoices", "inventory_balances", "inventory_movements",
    "wms_tasks", "warehouse_transfers", "cycle_count_sessions", "purchase_orders",
    "document_templates", "generated_documents", "permission_settings",
    "audit_logs", "user_onboarding",
    # ── Fase 0 (Multi-Entity + Notification Center) ──
    "business_entities", "notifications",
    # ── Fase 0.5 (Roll-as-SSOT Inventory Ownership) ──
    "inventory_rolls",
    # ── Fase 1A (Configuration Foundation) ──
    "system_settings", "payment_terms", "approval_rules",
    # ── Sub-fase 1.7 (Special Price / Approval Harga) ──
    "price_approvals",
    # ── Sub-fase 1.8 (Extended SO Status + Partial/Multi Physical Shipment) ──
    "shipments",
    # ── Sub-fase 1.9 (Faktur Pajak Jual) ──
    "tax_invoices",
    # ── Sub-fase 1.11 (Returns & Barang Sisa) ──
    "sales_returns",
    "special_orders",
    # ── Fase 3 (Procurement: Supplier Master + Pengelolaan Kas) ──
    "suppliers",
    "cash_transactions",
    # ── Depth #1 (Retur Beli / Nota Debit) ──
    "purchase_returns",
    # ── Depth #2 (Purchase Requisition / Hulu Procurement) ──
    "purchase_requisitions",
    # ── Fase 5.2 P0-2 (Vendor Bill + 3-Way Matching) ──
    "vendor_bills",
    # ── Fase 5.4 P0-5 (Landed Cost → alokasi HPP roll) ──
    "landed_cost_vouchers",
    # ── Fase 5.5 P0-3 (Faktur Pajak Masukan / Input VAT) ──
    "tax_invoices_in",
    "tax_pph_records",
    # ── Fase 6.1 P1 (RFQ / Quotation → sourcing) ──
    "rfqs",
    # ── EPIC2 (Master Kategori Produk + Snapshot SO line) ──
    "product_categories",
    # ── M0 (Master Warna Pantone-style — SHARED) ──
    "color_library",
    # ── M1 (Master Mitra Makloon + Resep Proses — SCOPED) ──
    "makloons", "process_recipes",
    # ── M3 (Transaksi Makloon / Subkontrak — SCOPED) ──
    "makloon_orders",
    # ── FASE D/E (Kontrak Mitra Makloon & Supplier — SCOPED) ──
    "supplier_contracts",
    # ── FASE E (Barang Supplier / katalog versi supplier — SCOPED) ──
    "supplier_items",
    # ── EPIC3B (AR Receipt / Payment Application ledger) ──
    "ar_receipts",
    # ── EPIC4 (Incentive Engine v2 — rate matrix entity×category) ──
    "incentive_rates",
    # ── EPIC7-B (Kas & Bank — multi-akun + rekonsiliasi) ──
    "bank_accounts",
    # ── EPIC7-C (Chart of Accounts + General Ledger) ──
    "gl_accounts", "journal_entries",
    # ── FASE H0/H1/H2 (HRD: Employee Master + Org + Absensi + Tracking) ──
    "hr_employees", "hr_org_units",
    "hr_shifts", "hr_geofences", "hr_attendance", "hr_devices",
    "hr_field_tracks", "hr_visits",
    # ── Fase 5 (RFID Simulator — tag↔roll, devices reader/gate, read events) ──
    "rfid_tags", "rfid_devices", "rfid_reads",
    # ── Digitalisasi Formulir Sukacita (Cash Advance/Settlement + Kendaraan) ──
    "cash_advances", "cash_advance_settlements", "expense_categories",
    "vehicles", "vehicle_usage_logs",
    # ── R0 (Return Policy Engine — kebijakan retur jual global/kategori/customer) ──
    "sales_return_policies",
}

# ── Alias TERLARANG → koleksi kanonik (dari bagian FORBIDDEN ENTITY_REGISTRY) ──
DANGEROUS_ALIASES = {
    # products
    "items": "products", "goods": "products", "materials": "products",
    "accessories": "products", "kain": "products", "fabric": "products",
    "product": "products",
    # inventory_balances
    "stock": "inventory_balances", "stok": "inventory_balances",
    "stock_levels": "inventory_balances", "inventory_count": "inventory_balances",
    "stock_balances": "inventory_balances", "stock_balance": "inventory_balances",
    # inventory_movements
    "stock_history": "inventory_movements", "gerakan_stok": "inventory_movements",
    "stock_log": "inventory_movements", "stock_movements": "inventory_movements",
    "movements": "inventory_movements",
    # inventory_rolls (Fase 0.5 — Roll-as-SSOT)
    "stock_units": "inventory_rolls", "rolls": "inventory_rolls",
    "roll": "inventory_rolls", "fabric_rolls": "inventory_rolls",
    # sales_orders
    "orders": "sales_orders", "customer_orders": "sales_orders",
    "so_list": "sales_orders", "penjualan": "sales_orders",
    # wms_tasks
    "inbound_tasks": "wms_tasks", "outbound_tasks": "wms_tasks",
    "receiving_tasks": "wms_tasks", "picking_tasks": "wms_tasks",
    # warehouse_transfers
    "transfers": "warehouse_transfers", "stock_transfer": "warehouse_transfers",
    "stock_transfers": "warehouse_transfers", "pemindahan_barang": "warehouse_transfers",
    # purchase_orders
    "po": "purchase_orders", "pos": "purchase_orders", "pembelian": "purchase_orders",
    "supplier_orders": "purchase_orders", "procurement": "purchase_orders",
    # suppliers (Fase 3)
    "vendor": "suppliers", "vendors": "suppliers", "pemasok": "suppliers",
    # cash_transactions (Fase 3)
    "kas": "cash_transactions", "cash": "cash_transactions", "petty_cash": "cash_transactions",
    # purchase_returns (Depth #1)
    "retur_beli": "purchase_returns", "purchase_return": "purchase_returns",
    "debit_notes": "purchase_returns", "po_returns": "purchase_returns",
    # purchase_requisitions (Depth #2)
    "purchase_requisition": "purchase_requisitions", "requisitions": "purchase_requisitions",
    "pr_list": "purchase_requisitions", "permintaan_pembelian": "purchase_requisitions",
    # invoices
    "bills": "invoices", "tagihan": "invoices", "faktur": "invoices",
    # document_templates
    "templates": "document_templates", "print_templates": "document_templates",
    "doc_config": "document_templates",
    # users
    "staff": "users", "karyawan": "users", "operator": "users", "employee": "users",
    "employees": "users",
    # warehouses
    "gudang": "warehouses", "depot": "warehouses", "storage_location": "warehouses",
    # uoms
    "satuan": "uoms", "unit_ukur": "uoms", "measurement": "uoms", "uom": "uoms",
    # customers
    "clients": "customers", "buyers": "customers", "pembeli": "customers",
    "pelanggan_toko": "customers", "customer": "customers",
    # cycle_count_sessions
    "stock_count": "cycle_count_sessions", "physical_count": "cycle_count_sessions",
    "stock_opname": "cycle_count_sessions",
    # audit (KN3 pakai audit_logs — jamak)
    "audit_log": "audit_logs", "audits": "audit_logs",
}

# Nama method/atribut Motor yang BUKAN koleksi (jangan di-flag)
NON_COLLECTION = {
    "get_db", "command", "ping", "list_collection_names", "client", "name",
    "drop", "create_collection", "with_options",
}


def extract_collections(filepath: Path) -> dict:
    """Ekstrak nama koleksi via db.<name> ATAU db["<name>"]/db['<name>'].
    Mendeteksi KEDUA bentuk (pelajaran RC-1/B3 dari case-study Torado)."""
    pattern = re.compile(r'''db(?:\.([a-z][a-z0-9_]*)|\[\s*['"]([a-z][a-z0-9_]*)['"]\s*\])''')
    cols = {}
    try:
        for i, line in enumerate(filepath.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for m in pattern.finditer(line):
                col = m.group(1) or m.group(2)
                if col and col not in NON_COLLECTION:
                    cols.setdefault(col, []).append(i)
    except Exception as e:
        print(f"  ERROR membaca {filepath}: {e}")
    return cols


def classify(col: str) -> str:
    if col in CANONICAL_COLLECTIONS:
        return "KANONIK"
    if col in DANGEROUS_ALIASES:
        return "TERLARANG"
    return "TIDAK_DIKENAL"


def scan_all() -> int:
    print(f"\n{C}{B}{'='*64}{X}")
    print(f"{B}  KN3 — SCAN CONTRACT: semua router + service{X}")
    print(f"{C}{B}{'='*64}{X}")
    files = sorted(list(ROUTERS.glob("*.py")) + list(SERVICES.rglob("*.py")))
    dangerous, unknown = [], []
    for f in files:
        if "__pycache__" in str(f):
            continue
        rel = f.relative_to(BACKEND)
        for col, lines in extract_collections(f).items():
            k = classify(col)
            if k == "TERLARANG":
                dangerous.append((str(rel), col, DANGEROUS_ALIASES[col], lines[:3]))
            elif k == "TIDAK_DIKENAL" and not col.startswith("_") and len(col) > 3:
                unknown.append((str(rel), col, lines[:3]))

    if dangerous:
        print(f"\n{R}{B}[DRIFT] Koleksi TERLARANG ditemukan (RC-1):{X}")
        for fn, col, correct, lines in dangerous:
            print(f"  {R}{fn}: '{col}' → seharusnya '{correct}' (baris {lines}){X}")
    else:
        print(f"\n{G}[OK] Tidak ada koleksi terlarang.{X}")

    if unknown:
        print(f"\n{Y}[INFO] Koleksi tidak dikenal (mungkin domain baru — daftarkan di ENTITY_REGISTRY):{X}")
        for fn, col, lines in unknown[:40]:
            print(f"  {Y}{fn}: '{col}' (baris {lines}){X}")
    else:
        print(f"{G}[OK] Semua koleksi dikenal (kanonik).{X}")

    print(f"\n{B}{'='*64}{X}")
    if dangerous:
        print(f"  {R}{B}CONTRACT VIOLATION — perbaiki nama koleksi sebelum lanjut.{X}\n")
        return 1
    print(f"  {G}{B}CONTRACT OK.{X}\n")
    return 0


def scan_router(name: str) -> int:
    f = ROUTERS / f"{name}.py"
    if not f.exists():
        matches = list(ROUTERS.glob(f"*{name}*.py"))
        print(f"Router tidak ditemukan. Mirip: {[m.name for m in matches]}")
        return 1
    print(f"\n{B}ROUTER: {f.name}{X}")
    rc = 0
    for col in sorted(extract_collections(f)):
        k = classify(col)
        if k == "KANONIK":
            print(f"  {G}[KANONIK]{X} {col}")
        elif k == "TERLARANG":
            print(f"  {R}[TERLARANG → {DANGEROUS_ALIASES[col]}]{X} {col}")
            rc = 1
        else:
            print(f"  {Y}[TIDAK DIKENAL]{X} {col}")
    return rc


def find_collection(name: str) -> int:
    print(f"\n{B}CARI KOLEKSI: '{name}'{X}")
    pat = re.compile(rf'''db(?:\.{re.escape(name)}\b|\[\s*['"]{re.escape(name)}['"]\s*\])''')
    found = []
    for py in sorted(BACKEND.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        for i, line in enumerate(py.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pat.search(line):
                found.append((str(py.relative_to(ROOT)), i, line.strip()[:100]))
    for fp, ln, txt in found:
        print(f"  {fp}:{ln}  {txt}")
    if not found:
        print("  (tidak ditemukan)")
    if name in DANGEROUS_ALIASES:
        print(f"  {R}PERINGATAN: '{name}' TERLARANG! Gunakan '{DANGEROUS_ALIASES[name]}'.{X}")
    return 0


def check_seed(seed_name: str) -> int:
    candidates = list(ROOT.glob(f"*{seed_name}*.py")) + list(BACKEND.glob(f"seed*/**/*{seed_name}*.py"))
    if not candidates:
        print(f"Seed tidak ditemukan: {seed_name}")
        return 1
    seed_file = candidates[0]
    print(f"\n{B}CHECK SEED: {seed_file}{X}")
    rc = 0
    for col in sorted(extract_collections(seed_file)):
        k = classify(col)
        if k == "KANONIK":
            print(f"  {G}\u2713{X} {col}")
        elif k == "TERLARANG":
            print(f"  {R}\u2717 {col} → seharusnya '{DANGEROUS_ALIASES[col]}' [RC-1!]{X}")
            rc = 1
        else:
            print(f"  {Y}? {col} (tidak dikenal){X}")
    print(f"\n{(R+'ADA DRIFT — perbaiki sebelum seed.' if rc else G+'Semua koleksi seed kanonik.')}{X}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description="KN3 Collection Contract Verifier")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--router")
    ap.add_argument("--find")
    ap.add_argument("--check-seed")
    ap.add_argument("--list-canonical", action="store_true")
    args = ap.parse_args()
    if args.list_canonical:
        print("\nKoleksi Kanonik KN3:")
        for c in sorted(CANONICAL_COLLECTIONS):
            print(f"  - {c}")
        return 0
    if args.all:
        return scan_all()
    if args.router:
        return scan_router(args.router)
    if args.find:
        return find_collection(args.find)
    if args.check_seed:
        return check_seed(args.check_seed)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
