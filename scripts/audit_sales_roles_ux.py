#!/usr/bin/env python3
"""AUDIT **PERAN** — menu yang TERLIHAT vs data yang BOLEH DIBACA (semua peran).

Menutup item yang diparkir di `plan.md` §8: *"analisis akses & UI/UX sales vs
admin-sales"* — dan diperluas 2026-08-15 ke SELURUH peran karena kelas cacatnya
ternyata tidak eksklusif milik dua peran itu (bukti: `finance` tidak boleh membaca
`/ar/aging` padahal Aging Piutang adalah menunya sendiri; `warehouse` tidak boleh
membaca `/suppliers` padahal ia yang membuat RFQ & Permintaan Pembelian).

DUA KELAS CACAT YANG DIJAGA
===========================
1. **LAYAR/PANEL MATI** — menunya muncul, diklik, lalu datanya `403`.
   · *layar mati*  : SEMUA endpoint layar itu 403 → layar tak ada gunanya.
   · *panel mati*  : SEBAGIAN endpoint 403 → layar terbuka, satu panel/dropdown
     kosong tanpa penjelasan. Sampai 2026-08-15 kelas ini hanya "peringatan kuning"
     dan itulah sebabnya 11 kasus nyata bisa hidup berbulan-bulan, termasuk yang
     paling mahal: `finance` membuka **Kasus Keuangan** dan SELURUH referensinya
     (playbook, alasan, kebijakan, pelanggan, rekening) kosong hanya karena satu
     `GET /suppliers` 403 ikut di dalam `Promise.all` yang sama. Sekarang MEMERAH.
2. **IZIN YATIM** — izin tulis diberikan di matriks tetapi tak ada satu pun layar
   yang bisa dijangkau peran itu yang memanggil endpoint bersangkutan. Wewenangnya
   ada di kertas, tidak ada di layar. Dilaporkan sebagai INDIKASI (tidak memerah):
   sebagian jalur sah lahir dari aksi berparameter/modal yang tak bisa dipetakan
   statis, jadi keputusan cabut-izin/buka-pintu tetap milik pemilik.

Gate `check_nav_map.py` memeriksa navigasi terhadap dirinya sendiri; gate isolasi
memeriksa kebocoran antar badan usaha. **Tidak ada** yang memeriksa "menu ini
benar-benar bisa dipakai oleh peran yang melihatnya" — itulah lubang yang diisi
berkas ini.

CARA KERJA (semuanya dari kode & HTTP nyata, tanpa daftar tebakan)
------------------------------------------------------------------
1. Menu yang terlihat per peran → `navStructure.js` + overlay `ROLE_NAV` lewat
   `check_nav_map.reachable_ids()` (SSOT yang sama dengan sidebar & deep-link),
   ditambah tab hub dari `config/hubTabs.js`.
2. Layar → berkas komponen → `AppViewRouter.jsx`.
3. Endpoint yang dipakai layar itu → `axios.get(...)` di berkas layar **dan**
   komponen lokal yang ia impor (transitif, 2 tingkat).
4. Endpoint diketuk sungguhan dengan token tiap peran (`X-Entity-Id: ent_ksc`).
   `403` = ditolak izin. `404/400/409` = izin LOLOS (dokumennya saja tak ada).
5. Izin yatim → peta `(modul, aksi) → endpoint` dibaca STATIK dari
   `backend/routers/*.py` (`require_permission` / `require_any_permission`), lalu
   dicocokkan dengan seluruh panggilan axios (semua metode) di layar peran itu.

Usage:
    python scripts/audit_sales_roles_ux.py             # ringkas (semua peran)
    python scripts/audit_sales_roles_ux.py -v          # + daftar endpoint & izin yatim
    python scripts/audit_sales_roles_ux.py --roles sales,sales_admin
    python scripts/audit_sales_roles_ux.py --json      # untuk pipa/CI
    python scripts/audit_sales_roles_ux.py --self-test  # bukti-merah (tanpa backend)
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend/src"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend/.env")
except Exception:  # noqa: BLE001
    pass

import httpx  # noqa: E402
import check_nav_map as nav  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
from _common import run_with_restore  # noqa: E402

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
PWD = "demo12345"
ENT = "ent_ksc"
G, R, Y, B, DIM, X = ("\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[2m",
                      "\033[0m")

#: Peran yang diaudit + akun demonya (`memory/test_credentials.md`).
#: `admin` ikut sebagai KONTROL: ia berizin `*`, jadi temuan pada admin berarti
#: audit ini sendiri yang salah, bukan izinnya.
AKUN = {
    "sales": "sales@kainnusantara.id",
    "sales_admin": "salesadmin@kainnusantara.id",
    "finance": "finance@kainnusantara.id",
    "warehouse": "warehouse@kainnusantara.id",
    "manager": "manager@kainnusantara.id",
    "admin": "admin@kainnusantara.id",
}

#: Layar yang MEMANG hanya pengumuman/placeholder (tidak punya data sendiri) —
#: tidak dihitung sebagai layar mati. Ditulis eksplisit supaya pengecualiannya
#: terbaca, bukan disembunyikan di logika.
TANPA_DATA_SENDIRI = {
    "home", "hr-my-profile", "profile", "coming-soon",
}

#: Endpoint yang **memang** 403 untuk peran tertentu TETAPI tidak pernah dipanggil
#: olehnya karena pemanggilnya sudah dipagari di kode.
#:
#: KUNCINYA `(layar, path)` — bukan `path` saja. Kunci global dulu terlalu longgar:
#: "/suppliers" yang dimaafkan karena wizard Kontrabon dipagari `canWrite` akan
#: sekaligus memaafkan dropdown Supplier yang BENAR-BENAR mati di layar RFQ. Pakai
#: `("*", path)` hanya bila pagarnya ada di modul API bersama (berlaku di mana saja).
#: Nilainya = ALAMAT PAGARNYA. Kalau pagar itu hilang, baris di sini menjadi salah dan
#: audit kembali berbunyi.
TERGATED_DI_KODE = {
    ("customers-crm", "/incentive-rates"):
        "features/crm/CrmView.jsx — tab 'rates' hanya dirender bila isManager",
    ("customers-crm", "/sales/leaderboard"):
        "features/crm/SalesForceDashboard.jsx — fetch di dalam `if (isManager)`",
    ("operations", "/cycle-count/sessions"):
        "features/wms/OperationsView.jsx — tab 'cycle' disaring izin inventory.cycle_count",
    ("hr-visits", "/hr/visits"):
        "features/hr/VisitsView.jsx — peran sales dialihkan ke /hr/visits/mine",
    ("hr-visits", "/hr/visits/summary"):
        "features/hr/VisitsView.jsx — hanya cabang Log Kunjungan (manajer/admin)",
    ("hr-visits", "/hr/employees"):
        "features/hr/VisitsView.jsx — hanya cabang Log Kunjungan (manajer/admin)",
    ("orders", "/shipments"):
        "features/orders/OrderDetailPanel.jsx — dipagari can(perms,'wms','view')",
    ("orders", "/tax-invoices"):
        "features/orders/OrderDetailPanel.jsx — dipagari can(perms,'tax_invoice','view')",
    # Modul API bersama dua meja kerja: satu berkas dipakai dua layar, masing-masing
    # hanya dibuka perannya sendiri → berlaku di layar mana pun yang mengimpornya.
    ("*", "/finance/desk"):
        "features/sales_admin/workDeskApi.js — satu modul API dua meja kerja; "
        "Meja Finance hanya dibuka peran finance",
    ("*", "/sales-admin/desk"):
        "features/sales_admin/workDeskApi.js — dipanggil hanya dari Meja Admin Sales",
    # ── Ditambahkan 2026-08-15 setelah audit diperluas ke SEMUA peran ────────────
    ("md-products", "/admin/integrations"):
        "features/admin/AdminView.jsx — <IntegrationsPanel> hanya dirender saat "
        "tab 'integrations' (Pusat Pengaturan, admin); layar Master Produk memakai only=['products']",
    ("md-categories", "/admin/integrations"):
        "features/admin/AdminView.jsx — idem (only=['categories'])",
    ("md-uoms", "/admin/integrations"):
        "features/admin/AdminView.jsx — idem (only=['uoms'])",
    ("md-products", "/products/sales-owners"):
        "features/admin/AdminView.jsx — loadSalesOwners() dipagari can(perms,'product','update')",
    ("md-categories", "/products/sales-owners"):
        "features/admin/AdminView.jsx — idem",
    ("md-uoms", "/products/sales-owners"):
        "features/admin/AdminView.jsx — idem",
    ("inventory-board", "/internal-requests"):
        "features/inventory/InventoryStatusBoard.jsx — modal 'Minta dari PT lain' "
        "hanya dirender bila can(perms,'internal_request','create')",
    ("inventory-board", "/internal-requests/meta"):
        "features/inventory/InventoryStatusBoard.jsx — idem (modal yang sama)",
    ("contra-bons", "/suppliers"):
        "features/purchasing/contrabon/ContraBonsView.jsx — `if (!canWrite) return;` "
        "sebelum mengambil daftar supplier (wizard Kontrabon baru)",
    ("contra-bons", "/bank-accounts"):
        "features/purchasing/contrabon/PayModal.jsx & PaymentScheduleModal.jsx — "
        "modal pembayaran hanya dirender untuk peran yang boleh membayar",
    ("purchase-returns", "/gl/cash-accounts"):
        "features/purchasing/ReturnDetailPanel.jsx — fetch akun refund dipagari canApprove",
}


def gated_reason(view, path, gated=None):
    """Alasan pagar-di-kode untuk (layar, path) — mendukung kunci `("*", path)`."""
    g = TERGATED_DI_KODE if gated is None else gated
    return g.get((view, path)) or g.get(("*", path))


# ─── 1. Menu terlihat per peran (SIDEBAR + TAB HUB) ──────────────────────────
HUB_TABS_RE = re.compile(r'"([\w-]+)"\s*:\s*\[(.*?)\]\s*,?\s*\n\s*(?="|\})',
                         re.S)
TAB_RE = re.compile(r'\{\s*view:\s*"([\w-]+)"[^}]*?roles:\s*\[([^\]]*)\]', re.S)


def parse_hub_tabs():
    """`{hubId: [(view, roles[])]}` dari `config/hubTabs.js` (SSOT tab hub)."""
    txt = (SRC / "config/hubTabs.js").read_text(encoding="utf-8")
    out = {}
    for hub, body in HUB_TABS_RE.findall(txt):
        tabs = [(v, [r.strip().strip('"') for r in roles.split(",") if r.strip()])
                for v, roles in TAB_RE.findall(body)]
        if tabs:
            out[hub] = tabs
    return out


def visible_views(role, entries, role_nav, hub_tabs):
    """Layar yang BENAR-BENAR bisa dibuka peran ini.

    Bukan sekadar id menu: satu menu hub mendarat di **tab pertama yang boleh**
    (`withHubView` di `navigationConfig.js`), dan tab-tab lainnya juga layar
    tersendiri. Versi pertama audit ini hanya memakai id menu, sehingga
    (a) menuduh `approval-inbox` mati padahal sales mendarat di tab
    "Persetujuan Harga", dan (b) melewatkan tab `hr-visits` yang benar-benar 403.
    """
    reach = nav.reachable_ids(entries, role, role_nav)
    rule = role_nav.get(role) or {"inherit": None, "add": [], "remove": []}

    def tab_allowed(view, roles):
        if view in rule["remove"]:
            return False
        if role in roles:
            return True
        if view in rule["add"]:
            return True
        return bool(rule["inherit"] and rule["inherit"] in roles)

    views = set()
    for vid in reach:
        tabs = hub_tabs.get(vid)
        if tabs:
            allowed = [v for v, roles in tabs if tab_allowed(v, roles)]
            views.update(allowed)          # semua tab yang boleh = layar terbuka
            if not allowed:
                views.add(vid)             # hub tanpa tab → layar itu sendiri
        else:
            views.add(vid)
    # Tab hub yang ditambahkan EKSPLISIT lewat ROLE_NAV.add walau hubnya tak ter-reach
    for hub, tabs in hub_tabs.items():
        for v, roles in tabs:
            if v in rule["add"] and tab_allowed(v, roles):
                views.add(v)
    return views


def menu_per_role(roles=None):
    entries = nav.parse_nav_config()
    role_nav = nav.parse_role_nav()
    hub_tabs = parse_hub_tabs()
    return ({role: visible_views(role, entries, role_nav, hub_tabs)
             for role in (roles or AKUN)}, entries)


# ─── 2. Layar → berkas komponen ──────────────────────────────────────────────
def view_to_file():
    router = (SRC / "AppViewRouter.jsx").read_text(encoding="utf-8")
    lazy_map = {}
    for m in re.finditer(r'const\s+(\w+)\s*=\s*lazy\(\(\)\s*=>\s*import\("([^"]+)"',
                         router):
        lazy_map[m.group(1)] = m.group(2)
    direct = {}
    for m in re.finditer(r'import\s+(\w+)\s+from\s+"(\.[^"]+)"', router):
        direct[m.group(1)] = m.group(2)

    out = defaultdict(set)
    for m in re.finditer(r'activeView\s*===\s*"([\w-]+)"[^\n]{0,400}?<(\w+)', router):
        view, comp = m.group(1), m.group(2)
        rel = lazy_map.get(comp) or direct.get(comp)
        if not rel:
            continue
        p = (SRC / rel.lstrip("./")).with_suffix("")
        for suffix in (".jsx", ".js"):
            f = Path(str(p) + suffix)
            if f.exists():
                out[view].add(f)
                break
    return out


# ─── 3. Endpoint yang dipakai satu layar ─────────────────────────────────────
GET_RE = re.compile(r"axios\.get\(\s*`\$\{API\}(/[^`]*)`")
#: semua metode (untuk analisis IZIN YATIM — bukan untuk pengetukan)
ANY_CALL_RE = re.compile(r"axios\.(get|post|patch|put|delete)\(\s*`\$\{API\}(/[^`]*)`")
#: URL API apa pun (window.open / href / helper) — dipakai deteksi "ada pintunya"
API_URL_RE = re.compile(r"\$\{API\}(/[^`\"'\s)]*)")
IMPORT_RE = re.compile(r'^\s*(?:import\s[^"\']*from\s*|import\s*)["\'](\.[^"\']+)["\']',
                       re.M)


def _resolve(base: Path, rel: str):
    p = (base.parent / rel).resolve()
    for cand in (p, Path(str(p) + ".jsx"), Path(str(p) + ".js"),
                 p / "index.jsx", p / "index.js"):
        if cand.is_file():
            return cand
    return None


def closure(files, depth=2):
    """Berkas layar + komponen lokal yang IA IMPOR (bukan seluruh folder).

    Memakai seluruh folder membuat audit menuduh layar mati karena berkas
    SEBELAHNYA (mis. "Kategori Beban" yang hanya untuk admin) — tuduhan palsu
    persis yang harus dihindari kalau laporan ini mau dipercaya.
    """
    seen, frontier = set(files), list(files)
    for _ in range(depth):
        nxt = []
        for f in frontier:
            try:
                txt = f.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            for rel in IMPORT_RE.findall(txt):
                t = _resolve(f, rel)
                if t and t not in seen and SRC in t.parents:
                    seen.add(t)
                    nxt.append(t)
        frontier = nxt
    return seen


def paths_for_files(files, all_methods=False):
    """Endpoint yang dipanggil berkas-berkas ini.

    `all_methods=False` → hanya GET berpath literal (bisa diketuk buta).
    `all_methods=True`  → semua metode, path berparameter dinormalkan ke `*`
                          (dipakai analisis IZIN YATIM, bukan pengetukan).
    """
    found = set()
    for f in sorted(closure(files)):
        # `components/ui/*` = infrastruktur, bukan data layar.
        if "/components/ui/" in str(f):
            continue
        try:
            txt = f.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        if all_methods:
            for m in ANY_CALL_RE.finditer(txt):
                found.add((m.group(1).upper(), norm_path(m.group(2))))
        else:
            for m in GET_RE.finditer(txt):
                raw = m.group(1)
                if "${" in raw:              # butuh id nyata → tak bisa diketuk buta
                    continue
                found.add(raw.split("?")[0].rstrip("/") or "/")
    return found


def norm_path(raw):
    """`/orders/${id}/lines?x=1` → `/orders/*/lines` ; `{order_id}` → `*`.

    Placeholder BERDAMPINGAN (`` `${API}/purchase-requisitions/${pr.id}${path}` ``,
    pola "aksi dinamis" yang dipakai tombol Ajukan/Batalkan) menghasilkan `**` =
    penanda "sisa path apa pun". Tanpa penanda ini pintu yang JELAS ADA di layar
    (`act("/submit")`) dilaporkan sebagai izin tanpa pintu.
    """
    p = raw.split("?")[0]
    p = re.sub(r"(?:\$\{[^}]*\}){2,}", "**", p)     # dua placeholder berdampingan
    p = re.sub(r"\$\{[^}]*\}", "*", p)
    p = re.sub(r"\{[^}]*\}", "*", p)
    p = re.sub(r"/+", "/", p)
    return p.rstrip("/") or "/"


# ─── 4. Ketuk endpoint sebagai tiap peran ────────────────────────────────────
def login(email):
    cl = httpx.Client(base_url=BASE, timeout=60.0)
    r = cl.post("/api/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    body = r.json()
    cl.headers.update({"Authorization": f"Bearer {body['token']}", "X-Entity-Id": ENT})
    return cl, body


def probe(cl, cache, path):
    if path in cache:
        return cache[path]
    try:
        code = cl.get(f"/api{path}").status_code
    except Exception:  # noqa: BLE001
        code = -1
    cache[path] = code
    return code


def classify(codes, view="?", gated=None):
    """(ditolak_tanpa_penjelasan, tergated, verdict) untuk SATU layar.

    `verdict`: `"mati"` bila SEMUA endpointnya 403 dan ada yang tak berpenjelasan ·
    `"panel"` bila hanya SEBAGIAN (layar terbuka, satu panel/dropdown kosong tanpa
    penjelasan — SEJAK 2026-08-15 ini pun temuan) · `"ok"` bila tak ada 403 tanpa
    penjelasan. Fungsi murni supaya bisa diuji-merah tanpa backend (`--self-test`).
    """
    ditolak = [p for p, c in codes.items() if c == 403 and not gated_reason(view, p, gated)]
    tergated = [p for p, c in codes.items() if c == 403 and gated_reason(view, p, gated)]
    if ditolak and len(ditolak) + len(tergated) == len(codes):
        return ditolak, tergated, "mati"
    if ditolak:
        return ditolak, tergated, "panel"
    return ditolak, tergated, "ok"


# ─── 5. IZIN YATIM: (modul, aksi) → endpoint (statik dari router) ─────────────
DEC_RE = re.compile(r'@router\.(get|post|patch|put|delete)\(\s*["\']([^"\']+)["\']')
PREFIX_RE = re.compile(r'APIRouter\(\s*prefix\s*=\s*["\']([^"\']*)["\']')
PERM_RE = re.compile(r'require_permission\(\s*request\s*,\s*["\'](\w+)["\']\s*,\s*["\'](\w+)["\']')
ANYPERM_RE = re.compile(r'require_any_permission\(\s*request\s*,\s*\[(.*?)\]', re.S)
PAIR_RE = re.compile(r'\(\s*["\'](\w+)["\']\s*,\s*["\'](\w+)["\']\s*\)')


def perm_to_endpoints():
    """`{(modul, aksi): {(METHOD, path_norm), …}}` dibaca dari backend/routers/*.py.

    PREFIX ROUTER IKUT DIBACA. Tanpa ini `routers/pdf.py` yang ber-`prefix="/api/pdf"`
    menghasilkan path `/render/*/*` sementara layar memanggil `/pdf/render/...` →
    izin `document.print` selalu terlihat "yatim". Tuduhan palsu seperti itu yang
    membuat laporan audit berhenti dipercaya.
    """
    out = defaultdict(set)
    for fp in sorted((ROOT / "backend" / "routers").glob("*.py")):
        raw = fp.read_text(encoding="utf-8")
        lines = raw.splitlines()
        pm = PREFIX_RE.search(raw)
        prefix = (pm.group(1) if pm else "/api")
        if prefix.startswith("/api"):
            prefix = prefix[4:]              # path relatif seperti dipakai layar
        decs = [(i, m.group(1).upper(), m.group(2)) for i, ln in enumerate(lines)
                for m in [DEC_RE.search(ln)] if m]
        for idx, (i, method, path) in enumerate(decs):
            end = decs[idx + 1][0] if idx + 1 < len(decs) else len(lines)
            text = "\n".join(lines[i:end])
            key = (method, norm_path(prefix + path))
            for mod, act in PERM_RE.findall(text):
                out[(mod, act)].add(key)
            for blob in ANYPERM_RE.findall(text):
                for mod, act in PAIR_RE.findall(blob):
                    out[(mod, act)].add(key)
    return out


def path_match(ep_path, call_path):
    """Cocokkan path endpoint & path panggilan layar.

    `*`  = satu segmen apa pun. `**` = sisa path apa pun (aksi dinamis di layar).
    Perlu dua arah: layar sering menyusun aksi secara dinamis
    (`` `${API}/approval-requests/${id}/${action}` `` → `/approval-requests/*/*`;
    `` `${API}/purchase-requisitions/${pr.id}${path}` `` → `/purchase-requisitions/**`),
    sedangkan endpoint-nya `/purchase-requisitions/*/submit`. Perbandingan string
    biasa menyatakan keduanya berbeda dan tombol "Ajukan" yang jelas ada di layar
    akan dilaporkan sebagai izin tanpa pintu.
    """
    a, b = ep_path.strip("/").split("/"), call_path.strip("/").split("/")
    for i, (x, y) in enumerate(zip(a, b)):
        if x == "**" or y == "**":
            return True                        # sisa path bebas → cocok
        if not (x == y or x == "*" or y == "*"):
            return False
    return len(a) == len(b)


def has_door(eps, calls):
    """True bila ADA panggilan di layar yang menuju salah satu endpoint izin ini."""
    for method, ep in eps:
        for cm, cp in calls:
            if (cm in ("ANY", method) or method == "ANY") and path_match(ep, cp):
                return True
    return False


def orphan_permissions(role_perms, all_calls, p2e):
    """Izin TULIS yang tak punya SATU PUN pintu di seluruh layar aplikasi.

    KENAPA CAKUPANNYA SELURUH FRONTEND, BUKAN LAYAR PERAN ITU SAJA
    --------------------------------------------------------------
    Versi pertama memakai closure impor layar peran tersebut. Hasilnya 58 "izin
    yatim" untuk `admin` — termasuk `user.create` padahal tombol "Akun baru" jelas
    ada di layar Badan Usaha & Akses. Sebabnya: aksi tulis di aplikasi ini banyak
    yang dialirkan sebagai **prop** dari kulit aplikasi (`App.js` + `hooks/*`),
    sehingga `axios.post()`-nya berada di berkas yang bukan bagian dari closure impor
    komponen layarnya. Laporan yang salah-tuduh 58 kali akan diabaikan orang, dan
    penjaga yang diabaikan sama saja dengan tidak ada.
    Karena itu pertanyaannya dipersempit menjadi yang bisa dijawab BUKTI:
    *"apakah ada pintu untuk izin ini DI MANA PUN di layar?"* Bila tidak ada satu pun
    panggilan axios di seluruh `frontend/src` yang menuju endpoint pemegang izin itu,
    maka wewenangnya memang hanya ada di kertas. Tetap INDIKASI (bukan merah): bisa
    jadi jalurnya memang disengaja lewat alat internal/otomatis.
    """
    yatim = []
    for module, actions in sorted((role_perms or {}).items()):
        for action in sorted(a for a in actions if a not in ("view", "*")):
            eps = p2e.get((module, action))
            if not eps:
                continue                      # tak ada endpoint pakai izin ini → bukan urusan layar
            if not has_door(eps, all_calls):
                yatim.append((f"{module}.{action}", sorted(f"{m} {p}" for m, p in eps)[:3]))
    return yatim


def all_frontend_calls():
    """Semua pintu di layar: panggilan axios **dan** URL `${API}/…` lain.

    Sebagian pintu bukan `axios.<verb>()` — dokumen dicetak lewat `window.open()`
    atau `href={`${API}/…`}`. Untuk pertanyaan "apakah ada pintunya", URL apa pun
    yang menunjuk API dihitung sebagai pintu (metode `ANY`).
    """
    found = set()
    for f in sorted(SRC.rglob("*.js")) + sorted(SRC.rglob("*.jsx")):
        if "/components/ui/" in str(f):
            continue
        try:
            txt = f.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        for m in ANY_CALL_RE.finditer(txt):
            found.add((m.group(1).upper(), norm_path(m.group(2))))
        for m in API_URL_RE.finditer(txt):
            found.add(("ANY", norm_path(m.group(1))))
    return found


# ─── BUKTI-MERAH ─────────────────────────────────────────────────────────────
def self_test():
    """Audit ini harus BISA menuduh — dan tidak salah-tuduh. Tanpa backend."""
    kasus = [
        ("layar mati (semua 403 tanpa penjelasan)",
         "vendor-bills", {"/vendor-bills": 403, "/vendor-bills/summary": 403}, {}, "mati"),
        ("panel mati: SATU panel 403 → TEMUAN (dulu hanya kuning)",
         "orders", {"/sales-orders": 200, "/tax-invoices": 403}, {}, "panel"),
        ("403 yang sudah dipagari di kode BUKAN temuan",
         "orders", {"/sales-orders": 200, "/shipments": 403},
         {("orders", "/shipments"): "dipagari can()"}, "ok"),
        ("pagar khusus layar TIDAK memaafkan layar lain",
         "rfq", {"/rfq": 200, "/suppliers": 403},
         {("contra-bons", "/suppliers"): "wizard dipagari canWrite"}, "panel"),
        ("pagar `('*', path)` berlaku di layar mana pun (modul API bersama)",
         "orders", {"/sales-orders": 200, "/finance/desk": 403},
         {("*", "/finance/desk"): "modul API dua meja kerja"}, "ok"),
        ("semua 403 tetapi SEMUANYA berpenjelasan → bukan layar mati",
         "orders", {"/shipments": 403},
         {("orders", "/shipments"): "dipagari can()"}, "ok"),
        ("layar sehat",
         "orders", {"/sales-orders": 200, "/customers": 200}, {}, "ok"),
    ]
    gagal = 0
    print(f"{B}== SELF-TEST audit peran (gate harus bisa MEMERAH) =={X}")
    for nama, view, codes, gated, harap in kasus:
        _, _, got = classify(codes, view, gated)
        ok_ = got == harap
        gagal += 0 if ok_ else 1
        tag = f"{G}PASS{X}" if ok_ else f"{R}FAIL{X}"
        print(f"  [{tag}] {nama}  (harap={harap} dapat={got})")

    # Izin yatim: harus menuduh izin tanpa pintu & MEMBIARKAN izin yang punya pintu.
    p2e = {("interco", "create"): {("POST", "/interco-transactions")},
           ("order", "confirm"): {("POST", "/sales-orders/*/confirm")}}
    y1 = orphan_permissions({"interco": ["view", "create"]}, set(), p2e)
    y2 = orphan_permissions({"interco": ["view", "create"]},
                            {("POST", "/interco-transactions")}, p2e)
    for nama, got, harap in (("izin tulis tanpa pintu → terdeteksi yatim", len(y1), 1),
                             ("izin tulis dengan pintu → BUKAN yatim", len(y2), 0)):
        ok_ = got == harap
        gagal += 0 if ok_ else 1
        print(f"  [{G + 'PASS' + X if ok_ else R + 'FAIL' + X}] {nama}  "
              f"(harap={harap} dapat={got})")

    if gagal:
        print(f"{R}{B}  SELF-TEST MERAH — logika penilaian audit tidak bisa dipercaya.{X}")
    else:
        print(f"{G}  HIJAU — audit terbukti menuduh layar/panel mati DAN tidak salah-tuduh.{X}")
    return gagal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--roles", default="", help="daftar peran dipisah koma (baku: semua)")
    ap.add_argument("--self-test", action="store_true",
                    help="bukti-merah logika penilaian (tanpa backend)")
    args = ap.parse_args()

    if args.self_test:
        return 1 if self_test() else 0

    roles = [r.strip() for r in args.roles.split(",") if r.strip()] or list(AKUN)
    bad = [r for r in roles if r not in AKUN]
    if bad:
        print(f"{R}Peran tak dikenal: {bad}. Pilihan: {list(AKUN)}{X}")
        return 2

    print(f"{B}{'=' * 78}\n  AUDIT PERAN — menu terlihat vs data yang boleh dibaca"
          f"\n  {BASE}  ·  peran: {', '.join(roles)}\n{'=' * 78}{X}")

    reach, _entries = menu_per_role(roles)
    v2f = view_to_file()
    p2e = perm_to_endpoints()
    fe_calls = all_frontend_calls()

    clients, perms = {}, {}
    for role in roles:
        email = AKUN[role]
        try:
            cl, body = login(email)
        except Exception as exc:  # noqa: BLE001
            print(f"{R}Tidak bisa login {email}: {exc}{X}")
            return 2
        clients[role] = cl
        perms[role] = (body.get("user") or {}).get("permissions") or body.get(
            "permissions") or {}

    hasil = {}
    for role in roles:
        cache = {}
        mati, panel, tanpa_endpoint, dijelaskan = [], [], [], []
        for view in sorted(reach[role]):
            files = v2f.get(view)
            if not files:
                continue
            if view in TANPA_DATA_SENDIRI:
                continue
            paths = paths_for_files(files)
            if not paths:
                tanpa_endpoint.append(view)
                continue
            codes = {p: probe(clients[role], cache, p) for p in sorted(paths)}
            ditolak, tergated, verdict = classify(codes, view)
            if verdict == "mati":
                mati.append((view, ditolak))
            elif verdict == "panel":
                panel.append((view, ditolak))
            if tergated:
                dijelaskan.append((view, tergated))
        hasil[role] = {"menu": sorted(reach[role]), "layar_mati": mati,
                       "panel_mati": panel,
                       "tergated_di_kode": dijelaskan,
                       "tanpa_endpoint_terdeteksi": tanpa_endpoint,
                       "izin_yatim": orphan_permissions(perms[role], fe_calls, p2e)}

    # ── Laporan ──────────────────────────────────────────────────────────────
    temuan = 0
    for role in roles:
        h = hasil[role]
        print(f"\n{B}▶ {role}{X}  ({AKUN[role]})")
        print(f"  menu terlihat: {len(h['menu'])} · layar dengan endpoint terdeteksi: "
              f"{len(h['menu']) - len(h['tanpa_endpoint_terdeteksi'])}")
        for judul, kunci in (("LAYAR MATI (menu terlihat tetapi SEMUA datanya 403)", "layar_mati"),
                             ("PANEL MATI (layar terbuka, panel/dropdown 403 tanpa penjelasan)",
                              "panel_mati")):
            if h[kunci]:
                temuan += len(h[kunci])
                print(f"  {R}{judul}: {len(h[kunci])}{X}")
                for view, paths in h[kunci]:
                    print(f"    {R}✗{X} {view:28s} → " + ", ".join(paths[:4]))
        if not h["layar_mati"] and not h["panel_mati"]:
            print(f"  {G}✓ tidak ada layar/panel mati{X}")
        if h["tergated_di_kode"] and args.verbose:
            print(f"  {DIM}403 yang SUDAH dipagari di kode (bukan temuan): "
                  f"{len(h['tergated_di_kode'])} layar{X}")
            for view, paths in h["tergated_di_kode"]:
                for p in paths:
                    print(f"    {DIM}· {view:22s} {p:26s} {gated_reason(view, p)}{X}")
        if h["izin_yatim"]:
            print(f"  {Y}izin tulis tanpa pintu di layar (indikasi): "
                  f"{len(h['izin_yatim'])}{X}"
                  + ("" if args.verbose else f" {DIM}(pakai -v untuk rincian){X}"))
            if args.verbose:
                for izin, eps in h["izin_yatim"]:
                    print(f"    {Y}○{X} {izin:28s} endpoint: " + ", ".join(eps))

    # ── Beda menu antar peran (dibaca sekali pandang) ────────────────────────
    if "sales" in hasil and "sales_admin" in hasil:
        only_sales = sorted(set(hasil["sales"]["menu"]) - set(hasil["sales_admin"]["menu"]))
        only_sa = sorted(set(hasil["sales_admin"]["menu"]) - set(hasil["sales"]["menu"]))
        print(f"\n{B}▶ BEDA MENU sales vs Admin Sales{X}")
        print(f"  hanya sales      ({len(only_sales)}): " + (", ".join(only_sales) or "—"))
        print(f"  hanya Admin Sales({len(only_sa)}): " + (", ".join(only_sa) or "—"))

    print(f"\n{B}{'=' * 78}{X}")
    if temuan:
        print(f"  {R}{B}{temuan} LAYAR/PANEL MATI ditemukan — beri izin bacanya, "
              f"pagari pemanggilnya di kode (lalu daftarkan alamat pagarnya), "
              f"ATAU cabut menunya.{X}")
    else:
        print(f"  {G}{B}HIJAU — setiap menu yang terlihat bisa dipakai perannya.{X}")
    print(f"{B}{'=' * 78}{X}")

    if args.json:
        print(json.dumps(hasil, indent=1, default=str))
    return 1 if temuan else 0


if __name__ == "__main__":
    # Audit ini MENGETUK HTTP nyata (login tiap peran + ratusan GET), jadi ia MENGUBAH
    # data: tiap `POST /auth/login` menulis satu baris `audit_logs` — persis residu yang
    # membuat gate `INV-GATE-01` memerah saat audit ini pertama kali didaftarkan.
    # Aturan repo untuk gate runtime: snapshot DB sebelum uji & pulihkan di `finally`
    # (scripts/guardrails/_common.py). `--self-test` murni statik → tak menyentuh DB.
    if "--self-test" in sys.argv:
        sys.exit(main())
    sys.exit(run_with_restore(main))
