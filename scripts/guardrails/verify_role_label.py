#!/usr/bin/env python3
"""
verify_role_label.py — GUARDRAIL **INV-ROLE-01**: peran hanya boleh dikenali dari
REGISTRY, dan wewenang di layar keuangan/pesanan hanya boleh diputuskan oleh IZIN.
=============================================================================

KELAS BUG NYATA (FASE E-8, terlihat di layar 2026-08-14)
--------------------------------------------------------
Menambah dua peran (`sales_admin`, `finance`) membongkar tiga kebiasaan lama:

1. **Peta label peran lokal.** `EntitySwitcher.jsx` & `OnboardingPanel.jsx` punya
   peta sendiri berisi 4 peran. Peran ke-5/6 jatuh ke cadangan "besarkan huruf
   pertama" sehingga pengguna melihat id teknis setengah jadi: **"Sales_admin"**.
2. **Wewenang dari nama peran.** `TaxInvoices.jsx` memakai
   `["manager","admin"].includes(role)` → Kasir/**Finance** melihat layar Faktur
   Pajak **tanpa satu pun tombol**, padahal server sudah mengizinkannya.
   `OrderDetailPanel.jsx` sebaliknya: tombol "Terbitkan Faktur Pajak" & "Catat
   pembayaran" tetap muncul untuk **sales** lalu ditolak 403 di belakang — kelas UX
   terburuk, karena pengguna menyalahkan dirinya sendiri.
3. **Registry bercabang.** Label/peringkat/beranda peran ada di `role_registry.py`
   (server), `config/roles.js` (layar) dan `config/navMeta.js` (beranda). Bila
   ketiganya tak sinkron, peran baru mendarat di layar kosong.

Tak satu pun gate lama bisa menangkap ini: semuanya memeriksa kontrak API, isolasi
data, dan invarian angka — bukan "apakah layar tahu peran ini ada".

YANG DIPERIKSA
    CHECK 1  registry peran IDENTIK: server ↔ layar ↔ beranda (id·label·peringkat·
             lintas-entitas·urutan·beranda)
    CHECK 2  tidak ada peta label peran lokal di luar `config/roles.js`
    CHECK 3  tidak ada "besarkan huruf pertama" atas id peran untuk ditampilkan
    CHECK 4  di layar UANG/PAJAK/ALUR PESANAN, tombol tidak boleh dinyalakan oleh
             literal peran — wajib `can(perms, modul, aksi)`

CARA PAKAI
    python scripts/guardrails/verify_role_label.py             # gate (exit 1 bila melanggar)
    python scripts/guardrails/verify_role_label.py --self-test # bukti-merah: harus MENANGKAP
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "frontend" / "src"
BE_REGISTRY = ROOT / "backend" / "role_registry.py"
FE_REGISTRY = SRC / "config" / "roles.js"
FE_NAVMETA = SRC / "config" / "navMeta.js"

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

ROLE_IDS = ("admin", "manager", "sales_admin", "finance", "sales", "warehouse")

# Berkas yang MEMANG boleh bicara peran sebagai data (registry & cermin-nya).
EXEMPT = {
    "config/roles.js",          # registry sisi layar
    "config/navMeta.js",        # beranda peran (dicek CHECK 1)
    "config/navStructure.js",   # `roles:` = niat desain menu, dioverlay ROLE_NAV
    "config/hubTabs.js",        # idem untuk tab hub
    "config/navigationConfig.js",
    "components/LoginScreen.jsx",   # tombol demo: butuh email per peran, bukan label
    "data/tourDefinitions.js",      # panduan per peran (materi, bukan wewenang)
}

# CHECK 4 — layar yang menyentuh UANG / PAJAK / ALUR PESANAN. Dideteksi dari jejak
# endpoint yang dipanggilnya, jadi layar BARU otomatis ikut terjaga tanpa daftar manual.
AUTHORITY_ENDPOINTS = (
    "/tax-invoices", "tax-invoice", "/ar-receipts", "payment-variances",
    "mark-delivered", "/earmark", "/interco/settlements", "/penalties",
)
# Pola "wewenang dari nama peran" (yang harus diganti `can(perms, …)`).
AUTHORITY_PATTERNS = [
    re.compile(r"\[[^\]]*\"(?:" + "|".join(ROLE_IDS) + r")\"[^\]]*\]\s*\.includes\("),
    re.compile(r"\brole\s*(?:===|==)\s*[\"'](?:" + "|".join(ROLE_IDS) + r")[\"']"),
    re.compile(r"\.role\s*(?:===|==)\s*[\"'](?:" + "|".join(ROLE_IDS) + r")[\"']"),
]
# Baris yang jelas BUKAN keputusan wewenang (penyaringan tampilan / rute layar).
AUTHORITY_OK_HINTS = ("data-testid", "placeholder", "label:", "title=", "// nav",
                      "recipient_role", "required_role")
# Baris KOMENTAR — penjelasan sejarah ("dulu `[\"admin\",\"manager\"].includes(role)`")
# justru harus boleh ditulis; tanpa pengecualian ini gate menghukum dokumentasinya
# sendiri dan mendorong orang menghapus penjelasan yang berharga.
COMMENT_LINE = re.compile(r"^\s*(?://|\*|/\*)")


def rel(p: Path) -> str:
    return str(p.relative_to(SRC))


def be_registry():
    """Baca `backend/role_registry.py` tanpa mengimpor FastAPI (gate harus ringan)."""
    txt = BE_REGISTRY.read_text()
    blok = re.search(r"ROLES:\s*Dict\[str, Dict\[str, Any\]\]\s*=\s*\{(.*?)\n\}\n", txt, re.S)
    body = blok.group(1) if blok else ""
    out = {}
    for m in re.finditer(r'^    "(\w+)":\s*\{(.*?)^    \},', body, re.S | re.M):
        rid, b = m.group(1), m.group(2)
        def g(pat, cast=str, default=None):
            mm = re.search(pat, b)
            return cast(mm.group(1)) if mm else default
        out[rid] = {
            "label": g(r'"label":\s*"([^"]+)"'),
            "rank": g(r'"rank":\s*(\d+)', int, -1),
            "cross": g(r'"cross_entity":\s*(True|False)', lambda v: v == "True", None),
            "order": g(r'"order":\s*(\d+)', int, -1),
            "home": g(r'"home_view":\s*"([^"]+)"'),
        }
    return out


def fe_registry():
    txt = FE_REGISTRY.read_text()
    blok = re.search(r"ROLE_REGISTRY\s*=\s*\{(.*?)\n\};", txt, re.S)
    body = blok.group(1) if blok else ""
    out = {}
    for m in re.finditer(r"^  (\w+):\s*\{(.*?)^  \},", body, re.S | re.M):
        rid, b = m.group(1), m.group(2)
        def g(pat, cast=str, default=None):
            mm = re.search(pat, b)
            return cast(mm.group(1)) if mm else default
        out[rid] = {
            "label": g(r'label:\s*"([^"]+)"'),
            "rank": g(r"rank:\s*(\d+)", int, -1),
            "cross": g(r"crossEntity:\s*(true|false)", lambda v: v == "true", None),
            "order": g(r"order:\s*(\d+)", int, -1),
        }
    return out


def fe_homes():
    txt = FE_NAVMETA.read_text()
    blok = re.search(r"ROLE_HOME_REGISTRY\s*=\s*\{(.*?)\n\};", txt, re.S)
    return dict(re.findall(r'(\w+):\s*\{\s*view:\s*"([^"]+)"', blok.group(1) if blok else ""))


def check_1_parity(viol):
    be, fe, homes = be_registry(), fe_registry(), fe_homes()
    if not be or not fe:
        viol.append(("config/roles.js", 0, "registry peran tidak bisa dibaca (server/layar)"))
        return be, fe
    hilang = sorted(set(be) - set(fe))
    lebih = sorted(set(fe) - set(be))
    for rid in hilang:
        viol.append((rel(FE_REGISTRY), 0, f"peran `{rid}` ada di server tapi TIDAK di layar"))
    for rid in lebih:
        viol.append((rel(FE_REGISTRY), 0, f"peran `{rid}` ada di layar tapi TIDAK di server"))
    for rid in sorted(set(be) & set(fe)):
        for key, nama in (("label", "label"), ("rank", "peringkat"),
                          ("cross", "lintas-entitas"), ("order", "urutan")):
            if be[rid][key] != fe[rid][key]:
                viol.append((rel(FE_REGISTRY), 0,
                             f"`{rid}`.{nama} bercabang: server={be[rid][key]!r} layar={fe[rid][key]!r}"))
        if homes.get(rid) != be[rid]["home"]:
            viol.append((rel(FE_NAVMETA), 0,
                         f"beranda `{rid}` bercabang: server={be[rid]['home']!r} layar={homes.get(rid)!r}"))
    return be, fe


def scan_files():
    for p in sorted(SRC.rglob("*.js")) + sorted(SRC.rglob("*.jsx")):
        if "node_modules" in p.parts or rel(p) in EXEMPT:
            continue
        yield p, p.read_text()


def check_2_3_4(viol):
    # peta label peran lokal: objek literal dengan >=2 kunci peran → nilai string
    map_pat = re.compile(r"\{[^{}\n]*\b(?:" + "|".join(ROLE_IDS) + r")\b\s*:\s*\"[^\"]+\"[^{}]*\}")
    cap_pat = re.compile(r"(?:role|userRole|Role)\s*(?:\?\.)?\s*\.charAt\(0\)\.toUpperCase\(\)")
    # id peran MENTAH dicetak sebagai TEKS JSX: `>{user?.role}<`. Meneruskannya sebagai
    # PROP (`role={user?.role}`) tetap sah — yang dilarang hanya menampilkannya.
    raw_pat = re.compile(r"(?:>\s*\{\s*(?:user|currentUser|u)\??\.role\s*\}"
                         r"|\{\s*(?:user|currentUser|u)\??\.role\s*\}\s*<)")
    for p, txt in scan_files():
        lines = txt.splitlines()
        for i, line in enumerate(lines, 1):
            m = map_pat.search(line)
            if m and sum(1 for r in ROLE_IDS if f"{r}:" in m.group(0)) >= 2:
                viol.append((rel(p), i, "peta LABEL PERAN lokal — pakai `roleLabel()` dari config/roles.js"))
            if cap_pat.search(line):
                viol.append((rel(p), i, "id peran dibesarkan hurufnya untuk ditampilkan "
                                       "(peran ber-underscore jadi \"Sales_admin\") — pakai `roleLabel()`"))
            if raw_pat.search(line) and "roleLabel" not in line and "role_label" not in line:
                viol.append((rel(p), i, "id peran MENTAH dicetak ke layar (`sales_admin` → CSS jadi "
                                       "\"Sales_admin\") — pakai `roleLabel()` / `user.role_label`"))
        # CHECK 4 — hanya untuk layar yang benar-benar menyentuh uang/pajak/alur pesanan
        if not any(e in txt for e in AUTHORITY_ENDPOINTS):
            continue
        for i, line in enumerate(lines, 1):
            if COMMENT_LINE.match(line) or any(h in line for h in AUTHORITY_OK_HINTS):
                continue
            if any(pat.search(line) for pat in AUTHORITY_PATTERNS):
                viol.append((rel(p), i, "wewenang layar UANG/PAJAK/PESANAN diputuskan LITERAL PERAN — "
                                       "pakai `can(perms, modul, aksi)`"))


def run(quiet=False):
    viol = []
    check_1_parity(viol)
    check_2_3_4(viol)
    if not quiet:
        print(f"{B}== INV-ROLE-01 — peran dari registry, wewenang dari izin =={X}")
        if viol:
            for f, ln, msg in viol:
                print(f"  {R}[FAIL]{X} {f}:{ln}  {msg}")
        print(f"  {'%s[PASS]%s' % (G, X) if not viol else '%s[FAIL]%s' % (R, X)} "
              f"{len(list(scan_files()))} berkas layar diperiksa · {len(viol)} pelanggaran")
    return viol


def self_test():
    """BUKTI-MERAH: gate harus MENANGKAP pelanggaran & tidak salah-tuduh yang benar."""
    print(f"{B}== SELF-TEST verify_role_label (gate harus bisa MEMERAH) =={X}")
    fails = 0

    def chk(nama, ok, detail=""):
        nonlocal fails
        print(f"  {'%s[PASS]%s' % (G, X) if ok else '%s[FAIL]%s' % (R, X)} {nama}"
              + (f"  · {detail}" if detail else ""))
        if not ok:
            fails += 1

    tmp = SRC / "features" / "__poc_role_label_probe.jsx"
    try:
        tmp.write_text(
            'const M = { admin: "Admin", finance: "Finance" };\n'
            'const t = role.charAt(0).toUpperCase() + role.slice(1);\n'
            'const canX = ["manager", "admin"].includes(role);\n'
            'const el = <span className="role">{user?.role}</span>;\n'
            'axios.get(`${API}/tax-invoices`);\n')
        v = run(quiet=True)
        mine = [x for x in v if "__poc_role_label_probe" in x[0]]
        chk("peta label peran lokal TERTANGKAP", any("peta LABEL PERAN" in m for _, _, m in mine))
        chk("pembesaran huruf id peran TERTANGKAP", any("dibesarkan hurufnya" in m for _, _, m in mine))
        chk("id peran MENTAH dicetak ke layar TERTANGKAP", any("MENTAH" in m for _, _, m in mine))
        chk("wewenang dari literal peran di layar pajak TERTANGKAP",
            any("LITERAL PERAN" in m for _, _, m in mine), f"{len(mine)} temuan")

        # kasus kontrol: pemakaian yang BENAR tidak boleh dituduh
        tmp.write_text(
            'import { roleLabel, can } from "../config/roles";\n'
            'const t = roleLabel(role);\n'
            'const el = <span className="role">{user?.role_label || roleLabel(user?.role)}</span>;\n'
            'const pass = <Child role={user?.role} />;\n'
            'const canX = can(perms, "tax_invoice", "create");\n'
            'axios.get(`${API}/tax-invoices`);\n')
        v = run(quiet=True)
        chk("pemakaian BENAR (roleLabel + can) tidak salah-tuduh",
            not [x for x in v if "__poc_role_label_probe" in x[0]])
    finally:
        tmp.unlink(missing_ok=True)

    v = run(quiet=True)
    chk("kode nyata saat ini HIJAU", not v,
        "; ".join(f"{f}:{ln} {m}" for f, ln, m in v[:4]))
    print(f"\n  {G if not fails else R}{'HIJAU' if not fails else 'MERAH'}{X} — "
          f"{fails} pemeriksaan gagal.")
    return fails


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(1 if self_test() else 0)
    sys.exit(1 if run() else 0)
