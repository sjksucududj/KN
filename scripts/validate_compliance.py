#!/usr/bin/env python3
"""
Kain Nusantara — Compliance Validator
======================================
Jalankan sebelum mark task sebagai DONE.
Output: PASS / FAIL per check dengan detail actionable.

Usage:
  python3 /app/scripts/validate_compliance.py
  python3 /app/scripts/validate_compliance.py --quick     # hanya checks kritis
  python3 /app/scripts/validate_compliance.py --fix-hints # tampilkan cara fix
"""
import os
import re
import ast
import sys
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path("/app")
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend" / "src"

# ─── LIMITS ───────────────────────────────────────────────────────────────
# KEBIJAKAN 2026-07-26 (keputusan pemilik):
#   Batas panjang file adalah PANDUAN, bukan tembok. Sebelumnya `> limit` = FAIL
#   keras, sehingga file seperti PurchaseReturns.jsx (498/500) membuat penambahan
#   3 baris memerahkan gate dan MEMAKSA split artifisial — gate mengunci desain,
#   bukan mencegah bug.
#   Sekarang 2 tingkat:
#     > limit            -> WARN  ("pertimbangkan split")
#     > limit * CEILING  -> FAIL  ("file monster sungguhan, wajib refactor")
#   Peringatan "mendekati batas" (0.8/0.85/0.9) DIHAPUS: itu murni kebisingan
#   karena sekarang batasnya sendiri sudah hanya WARN.
MAX_LINES_ROUTER   = 800
MAX_LINES_COMPONENT = 500
MAX_LINES_UTILITY  = 380  # bumped: navigationConfig.js is data-driven IA config (333 lines)
MAX_LINES_CSS      = 400
CEILING_FACTOR     = 2    # FAIL hanya bila > limit * CEILING_FACTOR

results = []   # list of (status, category, message)


def ok(category, message):
    results.append(("PASS", category, message))


def warn(category, message):
    results.append(("WARN", category, message))


def fail(category, message):
    results.append(("FAIL", category, message))


def section(title):
    results.append(("INFO", "", f"{'='*60}"))
    results.append(("INFO", "", f"  {title}"))
    results.append(("INFO", "", f"{'='*60}"))


# ─── CHECK 1: FILE SIZE ──────────────────────────────────────────────────────────
def _judge_size(rel, lines, limit, kind):
    """2 tingkat: > limit = WARN (panduan) · > limit*CEILING = FAIL (monster)."""
    ceiling = int(limit * CEILING_FACTOR)
    if lines > ceiling:
        fail("FILE_SIZE", f"{rel}: {lines} baris (MELEBIHI BATAS KERAS {ceiling} untuk {kind}) — WAJIB REFACTOR")
        return True
    if lines > limit:
        warn("FILE_SIZE", f"{rel}: {lines} baris (di atas panduan {limit} untuk {kind}; batas keras {ceiling}) — pertimbangkan split")
    return False


def check_file_sizes():
    section("CHECK 1: FILE SIZE LIMITS (panduan=WARN · batas keras=FAIL)")
    any_fail = False
    counted = 0

    # Python routers
    router_dir = BACKEND / "routers"
    for f in sorted(router_dir.glob("*.py")):
        lines = len(f.read_text().splitlines())
        counted += 1
        any_fail |= _judge_size(f.relative_to(ROOT), lines, MAX_LINES_ROUTER, "router")

    # Python core files
    for fname in ["server.py", "core_utils.py", "dependencies.py", "schemas.py", "permissions_config.py"]:
        f = BACKEND / fname
        if f.exists():
            lines = len(f.read_text().splitlines())
            counted += 1
            any_fail |= _judge_size(f"backend/{fname}", lines, MAX_LINES_ROUTER, "core")

    # React components
    for f in sorted(FRONTEND.rglob("*.jsx")):
        lines = len(f.read_text().splitlines())
        counted += 1
        any_fail |= _judge_size(f.relative_to(ROOT), lines, MAX_LINES_COMPONENT, "komponen")

    # JS utilities (bukan .jsx)
    for f in sorted(FRONTEND.rglob("*.js")):
        if "node_modules" in str(f):
            continue
        lines = len(f.read_text().splitlines())
        counted += 1
        # Hook files bisa lebih panjang
        limit = MAX_LINES_UTILITY * 2 if "hooks/" in str(f) else MAX_LINES_UTILITY
        any_fail |= _judge_size(f.relative_to(ROOT), lines, limit, "utility")

    # CSS — panduan saja (tak pernah FAIL)
    for f in FRONTEND.glob("*.css"):
        lines = len(f.read_text().splitlines())
        if lines > MAX_LINES_CSS:
            warn("FILE_SIZE", f"{f.relative_to(ROOT)}: {lines} baris (melebihi guideline {MAX_LINES_CSS})")

    if not any_fail:
        ok("FILE_SIZE", f"{counted} berkas diperiksa — tak ada yang melewati batas keras")


# ─── CHECK 2: CONSOLE.LOG ───────────────────────────────────────────────────────────
def check_console_logs():
    section("CHECK 2: DEBUG STATEMENTS")
    found = []

    # Frontend: console.log (kecuali yang di-comment)
    for f in FRONTEND.rglob("*.js"):
        if "node_modules" in str(f):
            continue
        for i, line in enumerate(f.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if "console.log" in line and "// ok" not in line.lower():
                found.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:80]}")

    for f in FRONTEND.rglob("*.jsx"):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if "console.log" in line and "// ok" not in line.lower():
                found.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:80]}")

    # Backend: debug print()
    for f in (BACKEND / "routers").glob("*.py"):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.match(r"\s*print\s*\(", line) and "# ok" not in line.lower():
                found.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:80]}")

    if found:
        for item in found:
            fail("DEBUG", item)
    else:
        ok("DEBUG", "Tidak ada console.log atau debug print() ditemukan")


# ─── CHECK 3: DUPLICATE ENDPOINTS ───────────────────────────────────────────────────
def check_duplicate_endpoints():
    section("CHECK 3: DUPLICATE ENDPOINTS")
    endpoint_map = defaultdict(list)  # (method, path) -> [files]

    pattern = re.compile(r'@router\.(get|post|put|patch|delete)\([\'"](.*?)[\'"]')

    router_dir = BACKEND / "routers"
    for f in router_dir.glob("*.py"):
        content = f.read_text()
        for match in pattern.finditer(content):
            method = match.group(1).upper()
            path = match.group(2)
            key = f"{method} {path}"
            endpoint_map[key].append(f.name)

    duplicates = {k: v for k, v in endpoint_map.items() if len(v) > 1}
    if duplicates:
        for endpoint, files in duplicates.items():
            fail("DUPLICATE_ENDPOINT", f"{endpoint} → ditemukan di: {', '.join(files)}")
    else:
        ok("DUPLICATE_ENDPOINT", f"Tidak ada duplicate endpoint ({len(endpoint_map)} endpoints total)")


# ─── CHECK 4: FORBIDDEN COLLECTION NAMES ────────────────────────────────────────────
def check_forbidden_collections():
    section("CHECK 4: FORBIDDEN COLLECTION NAMES (SSOT)")
    forbidden = [
        "items", "goods", "materials", "accessories", "kain", "fabric",
        "stock", "stok", "stock_levels", "inventory_count",
        "orders", "customer_orders", "penjualan",
        "inbound_tasks", "outbound_tasks", "receiving_tasks",
        r"^transfers$",  # warehouse_transfers is correct
        "stock_transfer", "pemindahan",
        r"^po$", "pembelian", "supplier_orders",
        "bills", "tagihan", "faktur",
        r"^templates$",  # document_templates is correct
        "staff", "operator", "karyawan",
        r"^gudang$", "depot",
        "stock_history", "stock_log", "gerakan_stok",
        "supplier_master", "vendors",  # not yet added, use suppliers if needed
    ]

    found_forbidden = []
    # Scan all Python router files for db.COLLECTION patterns
    pattern = re.compile(r'db\.([a-z_]+)')
    router_dir = BACKEND / "routers"
    for f in router_dir.glob("*.py"):
        content = f.read_text()
        collections_in_file = set(pattern.findall(content))
        for coll in collections_in_file:
            for forb in forbidden:
                if forb.startswith("^"):
                    if re.match(forb, coll):
                        found_forbidden.append((f.name, coll, forb))
                elif coll == forb:
                    found_forbidden.append((f.name, coll, "exact match"))

    if found_forbidden:
        for fname, coll, reason in found_forbidden:
            fail("FORBIDDEN_COLLECTION",
                 f"{fname}: db.{coll} — nama ini dilarang (lihat ENTITY_REGISTRY.md)")
    else:
        ok("FORBIDDEN_COLLECTION", "Tidak ada forbidden collection names ditemukan")


# ─── CHECK 5: HARDCODED IDs / CONFIG ──────────────────────────────────────────────────
def check_hardcoded_values():
    section("CHECK 5: HARDCODED IDs / WAREHOUSE IDs")
    # Pattern: known demo IDs yang tidak boleh hardcoded di bisnis logic
    hardcoded_patterns = [
        (r'["\']wh_jakarta["\']', "warehouse ID hardcoded"),
        (r'["\']wh_bandung["\']', "warehouse ID hardcoded"),
        (r'["\']wh_surabaya["\']', "warehouse ID hardcoded"),
        (r'["\']user_admin_01["\']', "user ID hardcoded"),
        (r'["\']user_sales_01["\']', "user ID hardcoded"),
        (r'["\']prod_batik_mega["\']', "product ID hardcoded"),
        (r'["\']demo12345["\']', "password hardcoded"),
        (r'localhost:8001', "localhost URL hardcoded (use env var)"),
        (r'localhost:3000', "localhost URL hardcoded (use env var)"),
    ]

    found = []
    # Check routers (seed data in server.py is expected to have these)
    router_dir = BACKEND / "routers"
    for f in router_dir.glob("*.py"):
        content = f.read_text()
        for pat, desc in hardcoded_patterns:
            if re.search(pat, content):
                found.append(f"{f.name}: {desc} (pattern: {pat})")

    if found:
        for item in found:
            warn("HARDCODED", item)
    else:
        ok("HARDCODED", "Tidak ada hardcoded IDs di router files")


# ─── CHECK 6: SAFE_DOC USAGE ──────────────────────────────────────────────────────────
def check_safe_doc_usage():
    section("CHECK 6: SAFE_DOC / SERIALIZATION")
    # Look for direct MongoDB return without safe_doc()
    risky_patterns = [
        (r'return await db\.[^\s]+\.find_one', "find_one tanpa safe_doc() wrapper"),
        (r'return await db\.[^\s]+\.insert_one', "insert_one result langsung di-return"),
    ]
    issues = []
    router_dir = BACKEND / "routers"
    for f in router_dir.glob("*.py"):
        content = f.read_text()
        for pat, desc in risky_patterns:
            matches = re.findall(pat, content)
            if matches:
                issues.append(f"{f.name}: {desc} ({len(matches)}x)")

    if issues:
        for item in issues:
            warn("SERIALIZATION", item)
    else:
        ok("SERIALIZATION", "Tidak ada langsung return MongoDB result yang mencurigakan")


# ─── CHECK 7: MISSING DATA-TESTID ───────────────────────────────────────────────────────
def check_data_testids():
    section("CHECK 7: DATA-TESTID COVERAGE")
    # Count testids in feature files (should be substantial)
    total_testids = 0
    files_without_testid = []

    for f in FRONTEND.rglob("*.jsx"):
        content = f.read_text()
        count = content.count("data-testid")
        total_testids += count
        # Feature files should have testids
        if "features/" in str(f) and count == 0:
            files_without_testid.append(str(f.relative_to(ROOT)))

    if files_without_testid:
        for fname in files_without_testid:
            warn("TESTID", f"{fname}: tidak ada data-testid (testing agent tidak bisa test ini)")
    else:
        ok("TESTID", f"Semua feature files punya data-testid (total: {total_testids} testids)")


# ─── CHECK 8: ENTITY REGISTRY SYNC ─────────────────────────────────────────────────────
def _py_code_only(src):
    """
    Buang komentar & string literal dari sumber Python, TAPI pertahankan offset
    (diganti spasi) agar pola seperti `db.nama` tetap utuh.

    Kenapa perlu: check ini me-regex `db\\.([a-z_]+)`. Tanpa pembersihan, sebuah
    KOMENTAR yang menyebut `db.hr_kpi_entries` ikut terhitung sebagai pemakaian
    koleksi — patologi "grep membaca komentar" yang sama seperti bug lama
    `check_imports`. Memakai tokenize agar benar (bukan regex rapuh).

    CATATAN: versi pertama fungsi ini menggabungkan token dengan spasi
    (`" ".join(...)`) sehingga `db.x` menjadi `db . x` dan regex TIDAK PERNAH
    match → seluruh deteksi mati dan check selalu PASS (false negative total).
    Karena itu sekarang blanking berbasis posisi baris/kolom.
    """
    import io
    import tokenize
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return re.sub(r"#[^\n]*", "", src)

    lines = src.split("\n")
    kill = [bytearray(len(ln)) for ln in lines]
    for t in toks:
        if t.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (sr, sc), (er, ec) = t.start, t.end
        for row in range(sr, min(er, len(lines)) + 1):
            ln = lines[row - 1]
            a = sc if row == sr else 0
            b = ec if row == er else len(ln)
            for i in range(a, min(b, len(ln))):
                kill[row - 1][i] = 1

    out = []
    for i, ln in enumerate(lines):
        out.append("".join(" " if kill[i][j] else ch for j, ch in enumerate(ln)))
    return "\n".join(out)


def _collections_declared_in_registry():
    """
    Baca nama koleksi LANGSUNG dari ENTITY_REGISTRY.md (sumber kebenaran tunggal).

    Sebelumnya check ini memakai allowlist HARDCODE 79 entri di dalam skrip,
    padahal pesannya berbunyi "tidak ada di ENTITY_REGISTRY.md" — jadi ada DUA
    sumber kebenaran dan drift dijamin terjadi (koleksi yang sudah didokumentasikan
    tetap dilaporkan MERAH sampai seseorang ingat menyunting skrip juga).
    """
    reg = ROOT / "ENTITY_REGISTRY.md"
    if not reg.exists():
        return set()
    text = reg.read_text()
    found = set()
    # 1) heading  "### nama"  /  "#### a + b"
    for m in re.finditer(r"^#{2,4}\s+([a-z0-9_+\s]+)", text, re.M):
        for part in re.split(r"[+\s]+", m.group(1)):
            if len(part) >= 3 and "_" in part or part in ("users", "products", "customers", "invoices", "uoms", "sessions", "warehouses", "suppliers", "budgets", "shipments", "notifications", "makloons", "rfqs"):
                found.add(part)
    # 2) identifier di dalam backtick
    for m in re.finditer(r"`([a-z][a-z0-9_]{2,})`", text):
        found.add(m.group(1))
    # 3) "Collection:" / "Collections:"
    for m in re.finditer(r"Collections?:\s*([a-z][a-z0-9_]+)", text):
        found.add(m.group(1))
    # 4) sel tabel  "| nama |"
    for m in re.finditer(r"^\|\s*`?([a-z][a-z0-9_]{2,})`?\s*\|", text, re.M):
        found.add(m.group(1))
    return found


def check_entity_registry_sync():
    section("CHECK 8: ENTITY REGISTRY SYNC (baca ENTITY_REGISTRY.md langsung)")
    # Allowlist warisan — hanya PELENGKAP. Sumber kebenaran = ENTITY_REGISTRY.md.
    legacy_allowlist = {
        "users", "sessions", "products", "customers", "warehouses",
        "uoms", "sales_orders", "invoices", "inventory_balances",
        "inventory_movements", "wms_tasks", "warehouse_transfers",
        "cycle_count_sessions", "purchase_orders", "document_templates",
        "generated_documents", "permission_settings", "audit_logs",
        "user_onboarding",
        # Fase 0 — Multi-Entity + Notification Center (registered in ENTITY_REGISTRY.md)
        "business_entities", "notifications",
        # Fase 0.5 — Roll-as-SSOT Inventory Ownership (registered in ENTITY_REGISTRY.md)
        "inventory_rolls",
        # Fase 1A — Configuration Foundation (registered in ENTITY_REGISTRY.md)
        "system_settings", "payment_terms", "approval_rules",
        # Sub-fase 1.7 — Special Price (registered in ENTITY_REGISTRY.md)
        "price_approvals",
        # Sub-fase 1.8 — Partial Shipment (registered in ENTITY_REGISTRY.md)
        "shipments",
        "shipments",
        # Sub-fase 1.9 — Faktur Pajak Jual (registered in ENTITY_REGISTRY.md)
        "tax_invoices",
        # Sub-fase 1.11 — Returns & Barang Sisa
        "sales_returns",
        # R0 — Return Policy Engine (kebijakan retur jual; registered in ENTITY_REGISTRY.md)
        "sales_return_policies",
        # Sub-fase 1.12 — Special Orders
        "special_orders",
        # Approval Requests (Sub-fase 1.6+)
        "approval_requests",
        # Fase 3 — Procurement masters & transaksi (registered in ENTITY_REGISTRY.md)
        "suppliers", "cash_transactions", "purchase_returns", "purchase_requisitions",
        # Depth #3 — Supplier Intelligence price-list (registered in ENTITY_REGISTRY.md)
        "supplier_price_lists",
        # EPIC2 — Master Kategori Produk (registered in ENTITY_REGISTRY.md)
        "product_categories",
        # EPIC3B — AR Receipt ledger (registered in ENTITY_REGISTRY.md)
        "ar_receipts",
        # EPIC4 — Incentive rate matrix (registered in ENTITY_REGISTRY.md)
        "incentive_rates",
        # Fase 3 — Procurement transaksi lanjutan (registered in ENTITY_REGISTRY.md)
        "vendor_bills", "landed_cost_vouchers", "rfqs", "tax_invoices_in",
        # AR / Credit (CRM & finance) — registered in ENTITY_REGISTRY.md
        "credit_notes", "credit_overrides", "collection_followups",
        # Sales performance — registered in ENTITY_REGISTRY.md
        "sales_targets", "sales_incentives",
        # Security — registered in ENTITY_REGISTRY.md
        "login_attempts",
        # HRD module (Fase H) — registered in ENTITY_REGISTRY.md
        "hr_employees", "hr_attendance", "hr_devices", "hr_field_tracks",
        "hr_geofences", "hr_kpi", "hr_leave_requests", "hr_org_units",
        "hr_overtime", "hr_shifts", "hr_visits",
        # Makloon / Subkontrak (registered in ENTITY_REGISTRY.md)
        "makloons", "process_recipes", "makloon_orders",
        # Fase D/E — Kontrak mitra & supplier (registered in ENTITY_REGISTRY.md)
        "supplier_contracts", "supplier_items",
        # R6.1 — Bank Reconciliation (registered in ENTITY_REGISTRY.md)
        "bank_statement_lines", "bank_accounts",
        # R6.2 — Fixed Assets & Depresiasi (registered in ENTITY_REGISTRY.md)
        "fin_fixed_assets", "fin_depreciation_entries",
        # R6.3 — Budget Control (registered in ENTITY_REGISTRY.md)
        "budgets", "fin_budget_rules", "expense_categories", "cash_advance_settlements",
        # Fase C — Lot kelas satu (D-10/D-26/D-27; registered in ENTITY_REGISTRY.md)
        "inventory_lots",
    }

    # Scan actual collections used in routers (komentar & docstring DIBUANG)
    pattern = re.compile(r'db\.([a-z_]+)')
    actual_collections = set()
    router_dir = BACKEND / "routers"
    for f in router_dir.glob("*.py"):
        content = _py_code_only(f.read_text())
        for coll in pattern.findall(content):
            actual_collections.add(coll)

    # Also check server.py
    server_content = _py_code_only((BACKEND / "server.py").read_text())
    for coll in pattern.findall(server_content):
        actual_collections.add(coll)

    # Sumber kebenaran = ENTITY_REGISTRY.md; allowlist warisan hanya pelengkap.
    registry = _collections_declared_in_registry()
    known_collections = legacy_allowlist | registry

    # Find collections in code but not in registry
    unregistered = actual_collections - known_collections
    # Remove false positives (not real collection names)
    false_positives = {"items", "client"}  # these are method names
    unregistered -= false_positives

    if unregistered:
        for coll in sorted(unregistered):
            warn("ENTITY_REGISTRY",
                 f"db.{coll} digunakan di code tapi tidak ada di ENTITY_REGISTRY.md — tambahkan jika ini collection baru")
    else:
        ok("ENTITY_REGISTRY",
           f"{len(actual_collections)} koleksi dipakai kode — semuanya terdaftar "
           f"({len(registry)} nama terbaca dari ENTITY_REGISTRY.md)")


# ─── CHECK 9: REQUIRED DOCS EXIST ───────────────────────────────────────────────────────
def check_required_docs():
    section("CHECK 9: REQUIRED DOCUMENTATION")
    required_docs = [
        ROOT / "ENTITY_REGISTRY.md",
        ROOT / "CODEBASE_MAP.md",
        ROOT / "memory" / "PRD.md",
        ROOT / "memory" / "SESSION_HANDOFF.md",
        ROOT / "memory" / "SESSION_LOG.md",
        ROOT / "memory" / "TECH_DECISIONS.md",
        ROOT / "plan.md",
        ROOT / "docs" / "KN_00_AGENT_QUICK_START.md",
        ROOT / "docs" / "KN_13_NAVIGATION_MAP.md",
    ]
    for doc in required_docs:
        if doc.exists():
            ok("DOCS", f"{doc.relative_to(ROOT)} ✓")
        else:
            fail("DOCS", f"{doc.relative_to(ROOT)} — FILE TIDAK ADA (wajib ada!)")


# ─── CHECK 10: API PREFIX ───────────────────────────────────────────────────────────────
def check_api_prefix():
    section("CHECK 10: API PREFIX (/api/)")
    # All router prefixes should start with /api/
    pattern = re.compile(r'APIRouter\(prefix=["\']([^\'"]+)["\']')
    issues = []
    router_dir = BACKEND / "routers"
    for f in router_dir.glob("*.py"):
        content = f.read_text()
        for match in pattern.finditer(content):
            prefix = match.group(1)
            if not prefix.startswith("/api"):
                issues.append(f"{f.name}: prefix '{prefix}' tidak diawali /api")

    # Also check @router decorators without /api prefix (no router-level prefix)
    endpoint_pattern = re.compile(r'@router\.(get|post|put|patch|delete)\(["\']([^\'"]+)["\']')
    for f in router_dir.glob("*.py"):
        content = f.read_text()
        # If no APIRouter prefix, all endpoints should start with /api
        if 'APIRouter(prefix=' not in content:
            for match in endpoint_pattern.finditer(content):
                path = match.group(2)
                if not path.startswith("/api"):
                    issues.append(f"{f.name}: endpoint '{path}' tanpa /api prefix dan tidak ada router prefix")

    if issues:
        for item in issues:
            warn("API_PREFIX", item)
    else:
        ok("API_PREFIX", "Semua endpoints menggunakan prefix /api/")


# ─── CHECK 11: ENV VARS (NO HARDCODED) ─────────────────────────────────────────────────
def check_env_vars():
    section("CHECK 11: ENVIRONMENT VARIABLES")
    # Check .env files exist
    backend_env = BACKEND / ".env"
    frontend_env = ROOT / "frontend" / ".env"

    if backend_env.exists():
        content = backend_env.read_text()
        if "MONGO_URL" in content:
            ok("ENV", "backend/.env: MONGO_URL ✓")
        else:
            fail("ENV", "backend/.env: MONGO_URL tidak ada!")
        if "DB_NAME" in content:
            ok("ENV", "backend/.env: DB_NAME ✓")
        else:
            warn("ENV", "backend/.env: DB_NAME tidak ada (akan default)")
        # Check no secrets hardcoded in code
        if "kain-nusantara::" in content:
            warn("ENV", "backend/.env: berisi string internal (bukan secret tapi perhatikan)")
    else:
        fail("ENV", "backend/.env tidak ditemukan!")

    if frontend_env.exists():
        content = frontend_env.read_text()
        if "REACT_APP_BACKEND_URL" in content:
            ok("ENV", "frontend/.env: REACT_APP_BACKEND_URL ✓")
        else:
            fail("ENV", "frontend/.env: REACT_APP_BACKEND_URL tidak ada!")
    else:
        fail("ENV", "frontend/.env tidak ditemukan!")


# ─── CHECK 12: DIHAPUS 2026-07-26 ──────────────────────────────────────────────────────
# `check_monster_files()` DIHAPUS karena DUPLIKAT MURNI dari `check_file_sizes()`:
# limit sama (MAX_LINES_ROUTER/COMPONENT/UTILITY), glob sama, ambang sama (0.9 vs 0.85).
# Akibatnya setiap temuan dilaporkan DUA KALI dengan label berbeda
# ([FILE_SIZE] + [MONSTER_FILE]) → 10 dari 19 warning repo ini adalah fakta yang sama.
# Deteksi "file monster" kini jadi tingkat FAIL di `_judge_size()` (> limit × CEILING).


# ─── CHECK 13: NAMING CONSISTENCY ──────────────────────────────────────────────────────
def check_naming_consistency():
    section("CHECK 13: NAMING CONVENTIONS")
    issues = []
    
    # Check Python files for camelCase (should be snake_case)
    pattern_camelcase = re.compile(r'\bdef ([a-z]+[A-Z][a-zA-Z]*)\(')
    router_dir = BACKEND / "routers"
    for f in router_dir.glob("*.py"):
        content = f.read_text()
        matches = pattern_camelcase.findall(content)
        if matches:
            for match in matches[:3]:  # Show max 3 examples
                issues.append(f"{f.name}: function '{match}' menggunakan camelCase (seharusnya snake_case)")
    
    # Check for inconsistent collection naming in MongoDB queries
    pattern_collection = re.compile(r'db\.([a-zA-Z_]+)')
    all_collections = set()
    for f in router_dir.glob("*.py"):
        content = f.read_text()
        collections = pattern_collection.findall(content)
        all_collections.update(collections)
    
    # Check if collections follow domain prefix convention
    # `document_` ditambahkan 2026-07-26: document_templates/deliveries/signatures adalah
    # satu domain (Platform Dokumen) — sebelumnya hanya document_templates di allowlist
    # individual, sehingga 2 koleksi sedomain dilaporkan "tidak mengikuti convention".
    valid_prefixes = ["inventory_", "warehouse_", "sales_", "finance_", "hr_", "audit_", "wms_", "cycle_",
                      "document_"]
    for coll in all_collections:
        if coll in ["users", "sessions", "products", "customers", "warehouses", "uoms", 
                    "invoices", "purchase_orders", "document_templates", "generated_documents",
                    "permission_settings", "user_onboarding",
                    "business_entities", "notifications",
                    "system_settings", "payment_terms", "approval_rules",
                    "price_approvals", "shipments", "tax_invoices", "sales_returns",
                    # Fase 3 + Depth #2/#3 — procurement masters & transaksi (domain entity)
                    "suppliers", "supplier_price_lists", "cash_transactions",
                    "purchase_returns", "purchase_requisitions", "special_orders",
                    "approval_requests", "product_categories", "ar_receipts", "incentive_rates",
                    # Fase 3 lanjutan + AR/credit + security (domain entity tanpa prefix)
                    "vendor_bills", "landed_cost_vouchers", "rfqs", "tax_invoices_in",
                    "credit_notes", "credit_overrides", "collection_followups",
                    "login_attempts",
                    # Makloon / Subkontrak (domain entity, registered in ENTITY_REGISTRY.md)
                    "makloons", "process_recipes", "makloon_orders",
                    # Fase D/E — kontrak mitra & supplier (registered in ENTITY_REGISTRY.md)
                    "supplier_contracts", "supplier_items"]:
            continue  # Known valid without prefix (config/master/domain entity)
        
        has_valid_prefix = any(coll.startswith(prefix) for prefix in valid_prefixes)
        if not has_valid_prefix and len(coll) > 3:  # Ignore false positives like "db"
            issues.append(f"Collection 'db.{coll}' tidak mengikuti domain prefix convention")
    
    if issues:
        for issue in issues[:10]:  # Show max 10 issues
            warn("NAMING", issue)
    else:
        ok("NAMING", "Naming conventions konsisten")


# ─── CHECK 14: TECH DEBT MARKERS ───────────────────────────────────────────────────────
def check_tech_debt():
    section("CHECK 14: TECH DEBT MARKERS")
    # Look for TODO, FIXME, HACK, XXX comments
    markers = []
    
    # Backend
    for f in (BACKEND / "routers").glob("*.py"):
        content = f.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r'#\s*(TODO|FIXME|HACK|XXX|BUG)\b', line, re.IGNORECASE):
                marker_type = re.search(r'(TODO|FIXME|HACK|XXX|BUG)', line, re.IGNORECASE).group(1).upper()
                markers.append((f.relative_to(ROOT), i, marker_type, line.strip()[:60]))
    
    # Frontend
    for f in FRONTEND.rglob("*.jsx"):
        content = f.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r'//\s*(TODO|FIXME|HACK|XXX|BUG)\b', line, re.IGNORECASE):
                marker_type = re.search(r'(TODO|FIXME|HACK|XXX|BUG)', line, re.IGNORECASE).group(1).upper()
                markers.append((f.relative_to(ROOT), i, marker_type, line.strip()[:60]))
    
    if markers:
        for filepath, line_num, marker, text in markers[:15]:  # Show max 15
            warn("TECH_DEBT", f"{filepath}:{line_num} [{marker}] {text}")
        if len(markers) > 15:
            warn("TECH_DEBT", f"... dan {len(markers) - 15} tech debt markers lainnya")
    else:
        ok("TECH_DEBT", "Tidak ada tech debt markers (TODO/FIXME/HACK)")


# ─── CHECK 15: IMPORT STATEMENTS QUALITY ───────────────────────────────────────────────
def _unused_imports_ast(path):
    """
    Deteksi import tak terpakai memakai AST (pengganti string-split yang buggy).

    Menangani:
      import x                -> bind "x"
      import x.y              -> bind "x"  (pemakaian `x.y.z` = Name 'x')
      import x as z           -> bind "z"
      from a import b         -> bind "b"
      from a import b as c    -> bind "c"
      from a import *         -> dilewati (tak bisa dinilai)

    Anti-false-positive:
      - `_dr.foo()` tertangkap karena `_dr` adalah ast.Name di dalam ast.Attribute.
      - anotasi string ("Model"), __all__, dan penyebutan di docstring/teks
        dianggap "terpakai" (cek fallback substring pada sumber).
      - re-export murni (`__all__`) tidak dilaporkan.
    """
    try:
        src = path.read_text()
        tree = ast.parse(src)
    except (SyntaxError, UnicodeDecodeError):
        return []

    bound = {}          # nama -> lineno
    import_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            import_nodes.add(id(node))
            for a in node.names:
                bound[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            import_nodes.add(id(node))
            # `from __future__ import annotations` adalah direktif compiler —
            # namanya memang tidak pernah dirujuk. Jangan laporkan.
            if node.module == "__future__":
                continue
            for a in node.names:
                if a.name == "*":
                    continue
                bound[a.asname or a.name] = node.lineno

    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            # `a.b.c` -> ujungnya ast.Name, sudah tercakup di atas
            pass
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # anotasi/forward-ref berbentuk string
            for tok in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", node.value):
                used.add(tok)

    out = []
    for name, lineno in sorted(bound.items(), key=lambda kv: kv[1]):
        if name in used:
            continue
        # fallback: disebut di tempat lain (decorator string, __all__, dsb.)
        if re.search(rf"(?<![A-Za-z_0-9]){re.escape(name)}(?![A-Za-z_0-9])",
                     "\n".join(l for i, l in enumerate(src.splitlines(), 1)
                               if i != lineno)):
            continue
        out.append((name, lineno))
    return out


def check_imports():
    section("CHECK 15: IMPORT QUALITY (AST — bukan string-split)")
    issues = []

    # Check for wildcard imports in Python (bad practice)
    router_dir = BACKEND / "routers"
    for f in router_dir.glob("*.py"):
        content = f.read_text()
        if re.search(r'from .* import \*', content):
            issues.append(f"{f.name}: menggunakan wildcard import (from X import *)")

    # Unused imports — DIPERBAIKI 2026-07-26.
    # BUG LAMA: `alias = imp_line.split(' as ')[-1].strip()` tidak membuang komentar
    # inline, sehingga untuk
    #     import domain_registry as _dr        # Fase A · R7 — SSOT domain
    # alias menjadi "_dr        # Fase A · R7 — SSOT domain (stamp defaults)".
    # `content.count(alias) == 1` lalu selalu True → 3 warning HANTU di
    # admin.py / inbound_receiving.py / inventory.py, padahal `_dr` betul-betul
    # dipakai (`_dr.stamp_domain_defaults`, `_dr.DomainValidationError`).
    # Sekarang memakai AST: nama yang di-bind oleh import dibandingkan dengan
    # ast.Name yang benar-benar terpakai (mencakup `_dr.x` karena `_dr` = Name).
    for f in sorted(router_dir.glob("*.py")):
        for name, lineno in _unused_imports_ast(f):
            issues.append(f"{f.name}:{lineno}: import '{name}' tidak terpakai")

    if issues:
        for issue in issues[:10]:
            warn("IMPORTS", issue)
        if len(issues) > 10:
            warn("IMPORTS", f"... dan {len(issues) - 10} temuan lain")
    else:
        ok("IMPORTS", f"{len(list(router_dir.glob('*.py')))} router bersih "
                      f"(nol wildcard, nol import tak terpakai)")


# ─── MAIN RUNNER ─────────────────────────────────────────────────────────────────────
def run_all_checks(quick=False):
    # Critical checks (always run)
    check_file_sizes()
    check_console_logs()
    check_duplicate_endpoints()
    check_forbidden_collections()
    check_entity_registry_sync()
    check_required_docs()
    check_env_vars()


    if not quick:
        # Additional quality checks
        check_hardcoded_values()
        check_safe_doc_usage()
        check_data_testids()
        check_api_prefix()
        check_naming_consistency()
        check_tech_debt()
        check_imports()


def print_report():
    print("\n" + "="*70)
    print("  KAIN NUSANTARA — COMPLIANCE REPORT")
    print("="*70)

    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "INFO": 0}
    fails = []
    warns = []

    for status, category, message in results:
        counts[status] = counts.get(status, 0) + 1
        if status == "FAIL":
            fails.append((category, message))
        elif status == "WARN":
            warns.append((category, message))

    # Print all results
    for status, category, message in results:
        if status == "INFO":
            print(f"\n{message}")
        elif status == "PASS":
            print(f"  \u2705 [{category}] {message}")
        elif status == "FAIL":
            print(f"  \u274c [{category}] {message}")
        elif status == "WARN":
            print(f"  \u26a0\ufe0f  [{category}] {message}")

    # Summary
    print("\n" + "="*70)
    print(f"  SUMMARY: {counts['PASS']} PASS | {counts['FAIL']} FAIL | {counts['WARN']} WARN")
    print("="*70)

    if fails:
        print("\n\u274c FAILURES (HARUS DIFIX SEBELUM MARK DONE):")
        for cat, msg in fails:
            print(f"   [{cat}] {msg}")

    if warns:
        print("\n\u26a0\ufe0f  WARNINGS (Perlu diperhatikan):")
        for cat, msg in warns:
            print(f"   [{cat}] {msg}")

    if counts["FAIL"] == 0 and counts["WARN"] == 0:
        print("\n\U0001f389 SEMUA CHECKS PASSED! Sistem dalam kondisi baik.")
    elif counts["FAIL"] == 0:
        print(f"\n\u26a0\ufe0f  {counts['WARN']} warning — fix sebelum ke production")
    else:
        print(f"\n\u274c {counts['FAIL']} failure harus difix sebelum task dianggap DONE")

    return counts["FAIL"]


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    print(f"\nMenjalankan compliance check{'(quick mode)' if quick else ''}...")
    run_all_checks(quick=quick)
    fail_count = print_report()
    sys.exit(1 if fail_count > 0 else 0)
