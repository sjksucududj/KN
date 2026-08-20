#!/usr/bin/env python3
"""INV-AUTH-01 — Setiap endpoint router WAJIB menegakkan autentikasi.

Kelas bug yang dicegah (Sesi #076):
  * AUTH-DOC-PREVIEW (P0): GET /documents/preview/{id} → dokumen bisnis penuh TANPA login.
  * AUTH-MASTER-LEAK (P1): GET /products, /uoms, /warehouses, /pos/best-sellers TANPA login.

Aturan (STATIK, tidak butuh backend):
  Tiap `@router.<method>("<path>")` di backend/routers/*.py harus — baik langsung di badannya,
  ATAU via helper lokal (`_xxx(request)`) yang di dalamnya menegakkan auth — memanggil ENFORCER:
    - KERAS : require_permission | require_any_permission | require_role   (login + otorisasi)
    - LUNAK : current_user | entity_ctx              (minimal login) — sah HANYA bila TIDAK
              ditelan try/except (menelan = 401 di-swallow → bocor, spt list_products).
  Delegasi ke helper lokal ditelusuri transitif (mis. /hr/kpi/me → _my_kpi → _emp_for_user →
  current_user). Endpoint benar-benar publik/ber-auth-khusus (device_token) didaftar EKSPLISIT
  di PUBLIC_ALLOWLIST + alasan.

Melanggar → MERAH: sebut file, `METHOD /path`, dan alasan.

CATATAN 2026-08-15 (kenapa `require_any_permission` ada di daftar KERAS)
-----------------------------------------------------------------------
Gate ini pernah MEMERAH untuk `GET /sales-return-policies/{policy_id}` padahal
endpoint itu **menegakkan auth dengan benar** lewat `require_any_permission(...)`
(lihat `backend/dependencies.py` — memanggil `current_user()` lalu menolak 403 bila
tak satu pun izin terpenuhi). Penyebabnya: daftar KERAS di sini hanya mengenal
`require_permission`/`require_role`, dan `"require_permission("` **bukan** substring
dari `"require_any_permission("`.

Akibat kelas cacat ini dua arah dan keduanya buruk:
  1. **Tuduhan palsu** (yang terjadi) — gate merah pada kode yang benar. Gate yang
     salah-tuduh akan dimatikan orang, lalu penjaganya hilang seluruhnya.
  2. **Diam-diam meloloskan** — dulu endpoint yang HANYA memakai
     `require_any_permission` bisa lolos *karena alasan yang salah* (kebetulan juga
     memanggil `entity_ctx`, enforcer LUNAK). Begitu `entity_ctx` dihapus saat
     refactor, endpoint benar-benar tanpa auth pun tetap dinilai LUNAK-lolos.

Supaya perbaikan ini tak pernah "membutakan" penjaga lagi, ditambahkan `--self-test`
(bukti-merah): 8 kasus sintetis membuktikan penjaga masih MENUDUH endpoint tanpa auth
dan tetap menerima ketiga enforcer keras.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import BACKEND, Guard, G, R, B, X  # noqa: E402

# `require_any_permission` = "salah satu dari" (dependencies.py) — tetap memanggil
# current_user() + menolak 403; setara keras dengan require_permission.
HARD = ("require_permission", "require_any_permission", "require_role")
SOFT = ("current_user", "entity_ctx")

PUBLIC_ALLOWLIST = {
    "POST /auth/login",             # gerbang login — wajib publik.
    "POST /auth/logout",            # idempotent: hapus sesi milik token yang dibawa; tak bisa disalahgunakan.
    "POST /hr/attendance/ingest",   # agen jembatan on-prem ZKTeco — auth via device_token (bukan sesi), cek eksplisit.
    "GET /verify/{code}",           # e-sign verifikasi publik (QR/halaman /verify-document) — by design tanpa login; hanya baca status by kode acak.
}

DEC_RE = re.compile(r'@router\.(get|post|patch|put|delete)\(\s*["\']([^"\']+)["\']')
DEF_RE = re.compile(r'^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(')


def _indent(s):
    return len(s) - len(s.lstrip())


def _blocks(lines):
    """Yield (name, start, body_lines) untuk tiap fungsi def di file (endpoint & helper)."""
    idxs = [(i, m.group(1)) for i, ln in enumerate(lines) for m in [DEF_RE.match(ln)] if m]
    for k, (i, name) in enumerate(idxs):
        end = idxs[k + 1][0] if k + 1 < len(idxs) else len(lines)
        yield name, i, lines[i:end]


def swallowed(body, enforcer):
    """True bila panggilan enforcer berada dalam blok try: ... except ...: (401 ditelan)."""
    for j, ln in enumerate(body):
        if enforcer + "(" not in ln:
            continue
        ind = _indent(ln)
        try_ind = None
        for k in range(j - 1, -1, -1):
            s = body[k].strip()
            kind = _indent(body[k])
            if s == "try:" and kind < ind:
                try_ind = kind
                break
            if s.startswith("def ") and kind < ind:
                break
        if try_ind is None:
            continue
        for k in range(j + 1, len(body)):
            s = body[k].lstrip()
            kind = _indent(body[k])
            if kind == try_ind and s.startswith("except"):
                return True
            if s and kind < try_ind:
                break
    return False


def _hard_hit(text):
    """Enforcer KERAS yang benar-benar dipanggil di `text`.

    Dicocokkan dengan batas kata supaya `require_permission` tidak "menelan"
    `require_any_permission` (dan sebaliknya) — pencocokan substring naif itulah
    akar tuduhan palsu 2026-08-15.
    """
    return [h for h in HARD if re.search(r'\b' + h + r'\s*\(', text)]


def _direct_enforced(text, body):
    """True bila body ini langsung menegakkan auth (hard, atau soft tak-ditelan)."""
    if _hard_hit(text):
        return True
    soft_hit = [s for s in SOFT if (s + "(") in text]
    if soft_hit and all(not swallowed(body, s) for s in soft_hit):
        return True
    return False


def _auth_helpers(blocks):
    """Set helper lokal (_xxx) yang menegakkan auth — transitif."""
    helper_body = {name: ("\n".join(b), b) for name, _, b in blocks if name.startswith("_")}
    auth = set()
    # pass langsung
    for name, (text, body) in helper_body.items():
        if _direct_enforced(text, body):
            auth.add(name)
    # pass transitif (helper memanggil helper auth)
    changed = True
    while changed:
        changed = False
        for name, (text, _) in helper_body.items():
            if name in auth:
                continue
            if any((h + "(") in text for h in auth):
                auth.add(name)
                changed = True
    return auth


def scan_source(fname, lines, g):
    """Nilai SATU sumber router. Dipisah dari main() supaya bisa diuji-merah."""
    blocks = list(_blocks(lines))
    helpers = _auth_helpers(blocks)
    decs = [(i, m.group(1).upper(), m.group(2)) for i, ln in enumerate(lines)
            for m in [DEC_RE.search(ln)] if m]
    for idx, (i, method, path) in enumerate(decs):
        end = decs[idx + 1][0] if idx + 1 < len(decs) else len(lines)
        body = lines[i:end]
        text = "\n".join(body)
        key = f"{method} {path}"
        if key in PUBLIC_ALLOWLIST:
            continue
        g.bump()
        if _direct_enforced(text, body):
            continue
        if any((h + "(") in text for h in helpers):  # delegasi ke helper auth
            continue
        soft_hit = [s for s in SOFT if (s + "(") in text]
        if soft_hit:
            g.add(f"{fname}: `{key}` memakai {soft_hit} TAPI ditelan try/except → "
                  f"401 di-swallow (dapat diakses TANPA login). Angkat auth ke luar try / pakai require_permission.")
        else:
            g.add(f"{fname}: `{key}` TIDAK menegakkan auth "
                  f"(require_permission/require_any_permission/require_role/current_user/entity_ctx) → "
                  f"dapat diakses TANPA login. Tambah enforcer atau daftarkan di PUBLIC_ALLOWLIST bila memang publik.")


# ─── BUKTI-MERAH ─────────────────────────────────────────────────────────────
def _case(src):
    g = Guard("INV-AUTH-01", "self-test")
    g.violations, g.checks = [], 0
    scan_source("fake.py", src.strip("\n").splitlines(), g)
    return len(g.violations)


def self_test():
    """Penjaga ini harus MENUDUH endpoint tanpa auth & MENERIMA 3 enforcer keras."""
    kasus = [
        ("endpoint tanpa enforcer apa pun → MERAH", '''
@router.get("/bocor")
async def bocor(request: Request):
    return await db.things.find().to_list(50)
''', 1),
        ("require_permission → hijau", '''
@router.get("/aman")
async def aman(request: Request):
    await require_permission(request, "order", "view")
    return []
''', 0),
        ("require_any_permission → hijau (akar tuduhan palsu 2026-08-15)", '''
@router.get("/sales-return-policies/{policy_id}")
async def detail(policy_id: str, request: Request):
    await require_any_permission(request, [("settings", "view"), ("sales_return", "view")])
    return {}
''', 0),
        ("require_role → hijau", '''
@router.post("/khusus-admin")
async def khusus(request: Request):
    await require_role(request, ["admin"])
    return {}
''', 0),
        ("current_user ditelan try/except → MERAH", '''
@router.get("/senyap")
async def senyap(request: Request):
    try:
        await current_user(request)
    except Exception:
        pass
    return []
''', 1),
        ("current_user di luar try → hijau", '''
@router.get("/lunak")
async def lunak(request: Request):
    await current_user(request)
    return []
''', 0),
        ("delegasi ke helper lokal ber-auth → hijau", '''
async def _ctx(request: Request):
    return await require_permission(request, "order", "view")


@router.get("/via-helper")
async def via_helper(request: Request):
    actor = await _ctx(request)
    return [actor]
''', 0),
        ("PUBLIC_ALLOWLIST dihormati → hijau", '''
@router.post("/auth/login")
async def login(payload: dict):
    return {"token": "x"}
''', 0),
    ]
    gagal = 0
    print(f"{B}== SELF-TEST INV-AUTH-01 (penjaga auth harus bisa MEMERAH) =={X}")
    for nama, src, harap in kasus:
        got = _case(src)
        ok_ = got == harap
        gagal += 0 if ok_ else 1
        print(f"  [{G + 'PASS' + X if ok_ else R + 'FAIL' + X}] {nama}  "
              f"(harap={harap} pelanggaran, dapat={got})")
    if gagal:
        print(f"{R}{B}  SELF-TEST MERAH — penjaga auth tidak bisa dipercaya.{X}")
    else:
        print(f"{G}  HIJAU — penjaga terbukti menuduh endpoint tanpa auth "
              f"dan menerima ketiga enforcer keras.{X}")
    return gagal


def main() -> int:
    g = Guard("INV-AUTH-01", "Tiap endpoint router menegakkan auth (kecuali PUBLIC_ALLOWLIST)")
    for fp in sorted((BACKEND / "routers").glob("*.py")):
        if fp.name == "__init__.py":
            continue
        scan_source(fp.name, fp.read_text().splitlines(), g)
    return g.finish()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(1 if self_test() else 0)
    sys.exit(main())
