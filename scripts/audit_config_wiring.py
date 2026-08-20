#!/usr/bin/env python3
"""audit_config_wiring.py — FASE G-0 · Audit "apakah konfigurasi benar-benar berfungsi".

Pertanyaan yang dijawab (permintaan owner 2026-07-26):
  "sepertinya banyak konfigurasi yang sudah ada di system, coba masukan dalam plan ini
   adalah audit konfigurasi ini wiringnya sudah benar atau belum dan benar benar berfungsi"

Untuk SETIAP kunci konfigurasi kita periksa 3 sisi:
  1. DECLARED  — kunci ada di default/registry backend (config_service.DEFAULT_GLOBAL_SETTINGS
                 atau default scope lain di services/*.py & bootstrap.py).
  2. CONSUMED  — ada kode aplikasi (services/ atau routers/) yang MEMBACA kunci itu.
  3. EDITABLE  — user benar-benar bisa mengubahnya lewat UI.

Klasifikasi hasil:
  OK          declared + consumed + editable          → wiring lengkap
  HIDDEN      declared + consumed, TIDAK ada UI        → hanya bisa diubah lewat DB/API mentah
  ORPHAN_UI   declared + editable, TIDAK ada consumer  → "tombol palsu": diubah user, TIDAK berefek
  DEAD        declared saja                            → tak dipakai, tak bisa diubah
  NOT_USED    registry menyatakan tidak dipakai + alasan → SAH, bukan pelanggaran
  DOUBLE_UI   kunci registry TAPI masih ada form lama yang menulisnya → DUA sumber kebenaran

──────────────────────────────────────────────────────────────────────────────
PERBAIKAN BLIND-SPOT (FASE G-0, penutupan):
  Versi lama menilai "EDITABLE" dengan mencari NAMA KUNCI secara harfiah di berkas
  frontend. Cara itu jadi BOHONG sejak "Pusat Pengaturan" (`SettingsHub`) merender
  SELURUH registry secara generik: tidak ada satu pun nama kunci tertulis di kode
  frontend, sehingga 77 kunci yang sebenarnya bisa diubah user dilaporkan HIDDEN.
  Persis patologi "guardrail-nya sendiri bug → temuan hantu".

  Sekarang audit MEMBACA SUMBER KEBENARANNYA (aturan repo #5: baca dokumennya,
  jangan menyalin daftarnya ke skrip):
    • `backend/config_registry.py` → kunci apa saja yang terdaftar + statusnya;
    • lalu MEMBUKTIKAN bahwa layar generiknya benar-benar tersambung
      (`hub_wired()`: nav item → route → komponen yang merender registry).
  Kalau layar itu diputus, seluruh kunci registry otomatis kembali HIDDEN.
  Bukti-merah wajib (aturan repo #6) dijalankan lewat `--self-test`.

Pemakaian:
    python3 /app/scripts/audit_config_wiring.py            # ringkasan + tabel
    python3 /app/scripts/audit_config_wiring.py --json     # JSON untuk gate
    python3 /app/scripts/audit_config_wiring.py --md FILE  # tulis laporan markdown
    python3 /app/scripts/audit_config_wiring.py --strict   # exit 1 bila ada pelanggaran
    python3 /app/scripts/audit_config_wiring.py --self-test # bukti-merah guardrail
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple

BACKEND = "/app/backend"
FRONTEND = "/app/frontend/src"
sys.path.insert(0, BACKEND)

# Direktori/berkas yang TIDAK dihitung sebagai "consumer" aplikasi.
BE_SKIP_FILE_RE = re.compile(r"(^|/)(test_|.*_test\.py$|backend_test|conftest\.py|bootstrap\.py)")
BE_SKIP_DIRS = {"tests", "__pycache__", "scripts"}
FE_SKIP_DIRS = {"node_modules", "__pycache__"}


# ── 1. Kumpulkan kunci yang DIDEKLARASIKAN ──────────────────────────────────
def flatten(prefix: str, obj: Any, out: List[str]) -> None:
    """Ubah dict bersarang → daftar path 'a.b.c'. List dianggap leaf."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(f"{prefix}.{k}" if prefix else k, v, out)
    else:
        out.append(prefix)


def declared_global() -> List[Tuple[str, str, Any]]:
    """(scope, path, default) dari config_service.DEFAULT_GLOBAL_SETTINGS."""
    from services import config_service  # noqa: WPS433

    paths: List[str] = []
    flatten("", config_service.DEFAULT_GLOBAL_SETTINGS, paths)
    rows = []
    for p in paths:
        cur: Any = config_service.DEFAULT_GLOBAL_SETTINGS
        for part in p.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                cur = None
        rows.append(("global", p, cur))
    return rows


# Scope non-global di koleksi system_settings. Ditemukan lewat grep
# {"scope": "<nama>"} pada services/ + bootstrap.py.
SCOPE_DEFAULT_SOURCES = [
    ("uom", "services/uom_rules_service.py"),
    ("lot", "services/lot_service.py"),
    ("makloon", "services/makloon_service.py"),
    ("receiving", "services/receiving_uom_service.py"),
    ("hr", "services/hr_payroll_service.py"),
    ("integrations", "services/integrations_service.py"),
    ("scheduler", "services/scheduler_service.py"),
    ("contract", "services/contract_service.py"),
]


def declared_other_scopes() -> List[Tuple[str, str, Any]]:
    """Ambil kunci scope non-global dari DB kalau ada (sumber kebenaran runtime),
    jatuh ke grep DEFAULT_* di service terkait bila DB kosong."""
    rows: List[Tuple[str, str, Any]] = []
    try:
        from pymongo import MongoClient

        url = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip('"')
        dbn = os.environ.get("DB_NAME", "test_database").strip('"')
        coll = MongoClient(url, serverSelectionTimeoutMS=3000)[dbn].system_settings
        for doc in coll.find({"scope": {"$ne": "global"}}, {"_id": 0}):
            scope = doc.get("scope")
            if not scope or scope in {"alerts"}:  # 'alerts' = lock runtime, bukan config
                continue
            body = {
                k: v
                for k, v in doc.items()
                if k not in {"id", "scope", "created_at", "updated_at", "updated_by", "lock"}
            }
            paths: List[str] = []
            flatten("", body, paths)
            for p in paths:
                cur: Any = body
                for part in p.split("."):
                    cur = cur.get(part) if isinstance(cur, dict) else None
                rows.append((scope, p, cur))
    except Exception as exc:  # pragma: no cover
        print(f"[warn] tidak bisa baca system_settings dari DB: {exc}", file=sys.stderr)
    return rows


# ── 2. Cari consumer di backend & UI di frontend ────────────────────────────
def walk(root: str, skip_dirs: set, exts: Tuple[str, ...]) -> List[str]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            if fn.endswith(exts):
                files.append(os.path.join(dirpath, fn))
    return files


# Berkas frontend yang perannya EDITOR konfigurasi (form pengaturan), bukan consumer.
# DIDETEKSI OTOMATIS: file yang melakukan PUT/PATCH/POST ke endpoint bernuansa
# config (settings|config|polic|rule|term|rates). Sisanya = CONSUMER, yaitu FE yang
# mengubah PERILAKU/tampilan berdasarkan nilai config.
FE_EDITOR_WRITE_RE = re.compile(
    r"""\.(put|patch|post)\(\s*[`"'][^`"']*(setting|config|polic|rule|term|rates)""",
    re.IGNORECASE,
)
# Sebagian editor menulis lewat helper api (mis. `lotApi.saveSettings(...)`).
# Dulu ini berupa DAFTAR BERKAS HARDCODE — persis patologi "dua sumber kebenaran"
# yang ditemukan audit 2026-07-26. Kini dideteksi dari BENTUK KODEnya.
FE_EDITOR_HELPER_RE = re.compile(
    r"""\.(saveSettings|savePolicy|updateSettings|saveConfig|putSettings)\s*\(""",
)
# Pusat Pengaturan sendiri BUKAN "editor lama" — ia justru satu-satunya editor sah.
# Berkasnya dikecualikan agar tidak dihitung sebagai duplikat terhadap dirinya sendiri.
HUB_DIR = "features/settings/config/"


def detect_fe_editors(fe: Dict[str, str]) -> set:
    found = set()
    for rel, text in fe.items():
        if rel.startswith(HUB_DIR):
            continue
        code = _strip_config_links(_js_code_only(text))
        if FE_EDITOR_WRITE_RE.search(code) or FE_EDITOR_HELPER_RE.search(code):
            found.add(rel)
    return found


# Endpoint konfigurasi LAMA — satu-satunya jalur tulis yang boleh dipakai UI
# sekarang adalah PUT /api/config/values (Pusat Pengaturan). Daftar ini ditulis
# eksplisit karena memang inilah permukaan API-nya; setiap entri punya pasangan
# di registry lewat `legacy_scope` (lihat backend/config_registry.py).
LEGACY_CONFIG_ENDPOINTS = (
    "/settings",
    "/hr/payroll/settings",
    "/lots/settings",
    "/uom-conversions/settings",
    "/receiving/uom-settings",
    "/supplier-contracts/policy",
)
# Cocokkan URL SECARA UTUH (`${API}/settings`), bukan sebagai potongan. Tanpa ini
# `/scheduler/settings` dan `/deliveries/whatsapp/settings` — yang BUKAN kunci
# registry — ikut tertangkap dan melahirkan temuan hantu.
_LEGACY_WRITE_RE = re.compile(
    r"""\.(put|patch)\(\s*[`"'](?:\$\{[A-Za-z_$][\w$]*\})?(%s)[`"']"""
    % "|".join(re.escape(e) for e in LEGACY_CONFIG_ENDPOINTS)
)
_LEGACY_HELPER_RE = re.compile(r"""\.(saveSettings|savePolicy|putSettings)\s*\(""")


def _strip_config_links(text: str) -> str:
    """Buang MENAUTKAN-ke-pengaturan sebelum menilai "apakah ini editor kedua".

    `<ConfigRedirectCard settings={[{ key: "tax.ppn_rate" … }]} />` dan
    `openConfig({ key: "…" })` menyebut nama kunci, tetapi keduanya justru
    MENGANTAR ke satu-satunya editor — bukan editor tandingan. Tanpa pengecualian
    ini, kartu pengalih yang kita pasang sendiri akan dilaporkan sebagai
    "sumber kebenaran ganda" (temuan hantu).
    """
    text = re.sub(r"<ConfigRedirectCard\b.*?/>", " ", text, flags=re.S)
    text = re.sub(r"openConfig\s*\(.*?\)", " ", text, flags=re.S)
    return text


def legacy_config_writers(fe: Dict[str, str]) -> Dict[str, List[str]]:
    """Berkas frontend yang MASIH menulis ke endpoint konfigurasi lama.

    Ini invarian inti FASE G-0 (INV-CFG-04): setelah editor lama dihapus, tidak
    boleh ada satu pun layar selain Pusat Pengaturan yang menyimpan konfigurasi.
    """
    out: Dict[str, List[str]] = {}
    for rel, text in fe.items():
        if rel.startswith(HUB_DIR):
            continue
        code = _strip_config_links(_js_code_only(text))
        found = sorted({m.group(2) for m in _LEGACY_WRITE_RE.finditer(code)})
        if _LEGACY_HELPER_RE.search(code):
            found.append("helper saveSettings/savePolicy")
        if found:
            out[rel] = found
    return out


def _js_code_only(text: str) -> str:
    """Buang komentar JS/JSX sebelum menilai kode.

    Alasan: bug guardrail nyata di repo ini lahir dari mencocokkan pola pada teks
    mentah — komentar ikut terbaca dan melahirkan temuan hantu. Nama kunci sengaja
    TIDAK dibuang karena justru itu yang ingin dideteksi.
    """
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", " ", text)
    return text


# ── Pusat Pengaturan: benarkah layar generiknya tersambung? ──────────────────
def hub_wired() -> Tuple[bool, List[str]]:
    """Buktikan rantai UI generik utuh: nav → route → komponen perender registry.

    Mengembalikan (wired, alasan_gagal[]). Dipakai supaya klaim "semua setting
    bisa diubah user" TIDAK boleh berdasar asumsi: kalau salah satu mata rantai
    hilang, seluruh kunci registry kembali dihitung HIDDEN.
    """
    problems: List[str] = []

    def read(rel: str) -> str:
        try:
            return _js_code_only(open(os.path.join(FRONTEND, rel), encoding="utf-8").read())
        except OSError:
            problems.append(f"berkas hilang: {rel}")
            return ""

    nav = read("config/navStructure.js") + read("config/hubTabs.js")
    if not re.search(r"""view:\s*["']settings-config["']""", nav):
        problems.append("navStructure.js: tidak ada menu ke view 'settings-config'")

    router = read("AppViewRouter.jsx")
    if not re.search(r"""activeView\s*===\s*["']settings-config["']""", router):
        problems.append("AppViewRouter.jsx: view 'settings-config' tidak dirutekan")
    if not re.search(r"<SettingsHub\b", router):
        problems.append("AppViewRouter.jsx: <SettingsHub> tidak dirender")

    hub = read("features/settings/config/SettingsHub.jsx")
    if not re.search(r"configApi\.registry\s*\(", hub):
        problems.append("SettingsHub.jsx: tidak membaca katalog registry")
    if not re.search(r"configApi\.effective\s*\(", hub):
        problems.append("SettingsHub.jsx: tidak membaca nilai efektif registry")
    if not re.search(r"items\.map\s*\(", hub):
        problems.append("SettingsHub.jsx: tidak merender daftar setting secara generik")

    editor = read("features/settings/config/SettingEditor.jsx")
    if not re.search(r"switch\s*\(\s*entry\.type\s*\)", editor):
        problems.append("SettingEditor.jsx: tidak menyediakan input per tipe setting")

    return (not problems), problems


# ── Registry backend = sumber kebenaran kunci yang bisa diubah lewat Hub ─────
def registry_index() -> Dict[str, Dict[str, Any]]:
    """Baca `backend/config_registry.py` (via import) — BUKAN salinan daftar."""
    try:
        import config_registry as reg  # noqa: WPS433
        import config_catalog_core  # noqa: F401,WPS433
        import config_catalog_ops  # noqa: F401,WPS433
    except Exception as exc:  # pragma: no cover
        print(f"[warn] config_registry tidak bisa dimuat: {exc}", file=sys.stderr)
        return {}
    return {e["key"]: e for e in reg.all_entries()}


def registry_key_for(scope: str, path: str, index: Dict[str, Dict[str, Any]]) -> str:
    """Cocokkan kunci tersimpan (bisa lebih dalam) ke entri registry terpanjang.

    Contoh: DB menyimpan daun `hr.ptkp_table.K1`, registry mengelolanya sebagai
    SATU entri `hr.ptkp_table` (tipe tabel). Tanpa pencocokan ini, tiap daun
    dilaporkan DEAD padahal induknya terkelola — temuan hantu lagi.

    TAMBAHAN (temuan FASE G-7, 2026-07-30): untuk override **per-entitas**, nama
    scope dokumen legacy adalah **id PT** (`ent_ksc`), bukan awalan kunci registry.
    Jadi `f"{scope}.{path}"` menghasilkan `ent_ksc.contra_bon.qty_tolerance_percent`
    yang tidak pernah ada di registry → entri dianggap tak terkelola → seluruh
    setting yang di-override per-PT dilaporkan **HIDDEN** padahal UI-nya ada.
    Terukur: 3 override PT baru = 3 pelanggaran INV-CFG-01 palsu. Karena itu bila
    gabungan scope+path gagal, `path` dicoba SENDIRI (scope PT bukan bagian kunci).
    """
    candidates = [path if scope == "global" else f"{scope}.{path}"]
    if scope != "global" and path not in candidates:
        candidates.append(path)
    for full in candidates:
        parts = full.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in index:
                return cand
    return ""


def strip_declaration_block(text: str) -> str:
    """Buang literal DEFAULT_* dari config_service.py supaya file itu tetap bisa
    dihitung sebagai CONSUMER (compute_order_pricing / get_allocation_policy /
    compute_tax memang membaca kunci-kunci ini) tanpa deklarasi ikut ter-grep."""
    out, skipping = [], False
    for line in text.splitlines():
        if re.match(r"^(DEFAULT_GLOBAL_SETTINGS|DEFAULT_PAYMENT_TERMS|DEFAULT_APPROVAL_RULES)\b", line):
            skipping = True
            continue
        if skipping:
            # blok literal berakhir saat kolom-0 bukan lanjutan dict/list
            if line and not line[0].isspace() and not line.startswith((")", "]", "}")):
                skipping = False
            else:
                continue
        out.append(line)
    return "\n".join(out)


def load_corpus() -> Tuple[Dict[str, str], Dict[str, str]]:
    be: Dict[str, str] = {}
    for f in walk(BACKEND, BE_SKIP_DIRS, (".py",)):
        rel = os.path.relpath(f, BACKEND)
        if BE_SKIP_FILE_RE.search(rel):
            continue
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if rel == "services/config_service.py":
            text = strip_declaration_block(text)
        be[rel] = text
    fe: Dict[str, str] = {}
    for f in walk(FRONTEND, FE_SKIP_DIRS, (".js", ".jsx")):
        rel = os.path.relpath(f, FRONTEND)
        try:
            fe[rel] = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            pass
    return be, fe


def hits(corpus: Dict[str, str], leaf: str, parent: str, index=None) -> List[str]:
    """File yang menyebut leaf-key. Cocokkan beberapa gaya penulisan:
      get("leaf") / ["leaf"] / .leaf / "parent.leaf" (dot-path Mongo/JS).

    KINERJA (terukur 2026-07-29): fungsi ini dipanggil 3× per setting (105
    setting) dan setiap panggilan me-regex-scan SELURUH korpus (719 berkas) →
    `build_rows` 6.2 detik. Karena `verify_data_integrity.py` memanggil lapisan
    config di SETIAP eksekusi, dan POC fase memanggil skrip itu 8–10×, satu
    `gate.sh --full` membakar ±200 detik hanya di sini.
    Solusi: `index` = hasil SATU kali pembacaan korpus (`build_hit_index`),
    berisi himpunan literal-berkutip & token setelah titik per berkas. Semantik
    dijaga identik dengan jalur regex (lihat `--self-test` bagian [6] yang
    membandingkan kedua jalur berkas-per-berkas).
    """
    if len(leaf) < 3:
        return []
    # Jalur cepat: leaf berupa identifier biasa & index tersedia.
    if index is not None and _IDENT_FULL.fullmatch(leaf):
        dotpath = f"{parent}.{leaf}" if parent else None
        return sorted(rel for rel, (quoted, dotted) in index.items()
                      if leaf in quoted or leaf in dotted
                      or (dotpath is not None and dotpath in quoted))
    pats = [
        re.compile(r"""["']%s["']""" % re.escape(leaf)),
        re.compile(r"""\.%s\b""" % re.escape(leaf)),
    ]
    if parent:
        pats.append(re.compile(r"""["']%s\.%s["']""" % (re.escape(parent), re.escape(leaf))))
    found = []
    for rel, text in corpus.items():
        if any(p.search(text) for p in pats):
            found.append(rel)
    return sorted(found)


# Index token per berkas — dibuat SEKALI per korpus lalu dipakai semua setting.
# `_QUOTED_ADJ` menangkap token yang DIAPIT tanda kutip (kutip boleh campur,
# persis seperti pola regex lama `["']leaf["']`). Ia SENGAJA tidak memasangkan
# kutip buka/tutup: di dalam f-string Python (`f"... '{x or 'manager'}' ..."`)
# pemasangan kutip akan menelan literal di dalamnya, sehingga hasilnya berbeda
# dari regex lama. Token berdot juga ditangkap agar pola `"parent.leaf"` sah.
_IDENT_FULL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_QUOTED_ADJ = re.compile(r"""['"]([A-Za-z_][A-Za-z0-9_.]*)['"]""")
_AFTER_DOT = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)")


def build_hit_index(corpus: Dict[str, str]) -> Dict[str, tuple]:
    """{berkas: (token yang diapit kutip, token sesudah titik)}."""
    out = {}
    for rel, text in corpus.items():
        out[rel] = (set(_QUOTED_ADJ.findall(text)), set(_AFTER_DOT.findall(text)))
    return out


def classify(consumers: List[str], ui: List[str]) -> str:
    if consumers and ui:
        return "OK"
    if consumers:
        return "HIDDEN"
    if ui:
        return "ORPHAN_UI"
    return "DEAD"


def build_rows(declared, be, fe_consumers, fe_editors, reg_index, wired: bool):
    """Susun satu baris hasil per kunci tersimpan.

    `wired` sengaja jadi PARAMETER (bukan dibaca di dalam) supaya bukti-merah
    bisa menjalankan skenario "Pusat Pengaturan diputus" tanpa menyentuh berkas.
    """
    rows: List[Dict[str, Any]] = []
    ix_be = build_hit_index(be)
    ix_fe = build_hit_index(fe_consumers)
    ix_ed = build_hit_index(fe_editors)
    for scope, path, default in declared:
        parts = path.split(".")
        leaf, parent = parts[-1], (parts[-2] if len(parts) > 1 else scope)
        be_c = hits(be, leaf, parent, ix_be)
        fe_c = hits(fe_consumers, leaf, parent, ix_fe)
        legacy_ui = hits(fe_editors, leaf, parent, ix_ed)
        consumers = [f"be:{x}" for x in be_c] + [f"fe:{x}" for x in fe_c]

        rkey = registry_key_for(scope, path, reg_index)
        entry = reg_index.get(rkey) if rkey else None
        hub_ui = bool(entry) and wired and entry.get("status") == "active"

        ui = list(legacy_ui)
        if hub_ui:
            ui.append("features/settings/config/SettingsHub.jsx (registry generik)")

        if entry is not None and entry.get("status") == "not_used":
            status = "NOT_USED"
        else:
            status = classify(consumers, ui)

        rows.append(
            {
                "scope": scope,
                "path": path,
                "registry_key": rkey,
                "default": default if not isinstance(default, (dict, list)) else "<complex>",
                "status": status,
                "consumers": consumers[:6],
                "consumer_count": len(consumers),
                "ui": ui[:6],
                "ui_count": len(ui),
                "legacy_ui": legacy_ui[:6],
                "not_used_reason": (entry or {}).get("not_used_reason", ""),
            }
        )
    return rows


# Status yang dianggap PELANGGARAN oleh gate (INV-CFG).
VIOLATIONS = ("HIDDEN", "ORPHAN_UI", "DEAD")


def self_test() -> int:
    """BUKTI-MERAH (aturan repo #6): guardrail harus MEMERAH saat dilanggar.

    Tanpa ini, "semua hijau" tidak berarti apa-apa — bisa saja skrip memang tak
    mampu mendeteksi pelanggaran apa pun.
    """
    be, fe = load_corpus()
    reg_index = registry_index()
    fe_editor_set = detect_fe_editors(fe)
    fe_editors = {k: v for k, v in fe.items() if k in fe_editor_set}
    fe_consumers = {k: v for k, v in fe.items() if k not in fe_editor_set}
    declared = declared_global() + declared_other_scopes()

    ok = True

    # 1. Keadaan nyata harus HIJAU.
    wired, why = hub_wired()
    rows = build_rows(declared, be, fe_consumers, fe_editors, reg_index, wired)
    bad = [r for r in rows if r["status"] in VIOLATIONS]
    print(f"[1] keadaan nyata          : wired={wired} pelanggaran={len(bad)}")
    if not wired:
        print("    alasan:", "; ".join(why))
    if bad or not wired:
        ok = False
        for r in bad[:10]:
            print(f"    - {r['status']} {r['scope']}:{r['path']}")

    # 2. Putuskan Pusat Pengaturan → kunci registry WAJIB kembali HIDDEN.
    rows_off = build_rows(declared, be, fe_consumers, fe_editors, reg_index, False)
    hidden_off = sum(1 for r in rows_off if r["status"] == "HIDDEN")
    print(f"[2] Hub diputus (simulasi) : HIDDEN={hidden_off} (harus > 0)")
    if hidden_off <= 0:
        ok = False
        print("    GAGAL: audit tetap hijau walau Pusat Pengaturan diputus — deteksi palsu.")

    # 3. Nyata: tidak boleh ada layar lain yang menulis endpoint konfigurasi lama.
    writers = legacy_config_writers(fe)
    print(f"[3] penulis config lama    : {len(writers)} berkas (harus 0)")
    for rel, eps in writers.items():
        ok = False
        print(f"    - {rel} → {', '.join(eps)}")

    # 4. Suntik layar yang menulis endpoint lama → WAJIB terdeteksi.
    probe = dict(fe)
    probe["__suntikan__/LegacyEditor.jsx"] = (
        "axios.put(`${API}/lots/settings`, draft);"
    )
    n_probe = len(legacy_config_writers(probe))
    print(f"[4] penulis lama disuntik  : terdeteksi={n_probe} (harus > {len(writers)})")
    if n_probe <= len(writers):
        ok = False
        print("    GAGAL: penulisan konfigurasi di luar Pusat Pengaturan tidak terdeteksi.")

    # 5. Kartu pengalih TIDAK boleh dianggap editor kedua (anti temuan hantu).
    probe2 = dict(fe)
    probe2["__suntikan__/OnlyLink.jsx"] = (
        '<ConfigRedirectCard settings={[{ key: "tax.ppn_rate" }]} />\n'
        'openConfig({ key: "lot.enforcement_mode" });'
    )
    if len(legacy_config_writers(probe2)) != len(writers):
        ok = False
        print("[5] GAGAL: kartu pengalih salah dihitung sebagai editor kedua.")
    else:
        print("[5] kartu pengalih murni   : tidak dihitung editor (benar)")

    # 6. KINERJA TANPA MENGUBAH ARTI — jalur index (cepat) WAJIB memberi hasil
    #    identik dengan jalur regex (lambat) untuk SETIAP setting × SETIAP korpus.
    #    Tanpa pemeriksaan ini, optimasi kecepatan bisa diam-diam menghilangkan
    #    temuan (gate jadi "hijau palsu").
    ix_be = build_hit_index(be)
    ix_fc = build_hit_index(fe_consumers)
    ix_fe = build_hit_index(fe_editors)
    diff = 0
    for scope, path, _default in declared:
        parts = path.split(".")
        leaf, parent = parts[-1], (parts[-2] if len(parts) > 1 else scope)
        for corpus, index in ((be, ix_be), (fe_consumers, ix_fc), (fe_editors, ix_fe)):
            if hits(corpus, leaf, parent) != hits(corpus, leaf, parent, index):
                diff += 1
                if diff <= 5:
                    print(f"    - beda pada {scope}:{path}")
    n_pair = len(declared) * 3
    print(f"[6] index == regex         : {n_pair - diff}/{n_pair} sama (harus 100%)")
    if diff:
        ok = False
        print("    GAGAL: jalur cepat mengubah hasil audit — optimasi tidak sah.")

    print()
    print("SELF-TEST:", "PASS — guardrail terbukti bisa memerah" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md", default="")
    ap.add_argument("--only", default="", help="filter status: OK|HIDDEN|ORPHAN_UI|DEAD")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 bila ada HIDDEN/ORPHAN_UI/DEAD/DOUBLE_UI (dipakai gate)")
    ap.add_argument("--self-test", action="store_true",
                    help="bukti-merah: pastikan guardrail memerah saat dilanggar")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    declared = declared_global() + declared_other_scopes()
    be, fe = load_corpus()
    reg_index = registry_index()
    wired, wired_problems = hub_wired()
    fe_editor_set = detect_fe_editors(fe)
    fe_editors = {k: v for k, v in fe.items() if k in fe_editor_set}
    fe_consumers = {k: v for k, v in fe.items() if k not in fe_editor_set}

    rows = build_rows(declared, be, fe_consumers, fe_editors, reg_index, wired)

    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    violations = [r for r in rows if r["status"] in VIOLATIONS]
    writers = legacy_config_writers(fe)

    if args.json:
        print(json.dumps({"summary": counts, "total": len(rows), "rows": rows,
                          "hub_wired": wired, "hub_problems": wired_problems,
                          "legacy_writers": writers,
                          "violations": len(violations) + len(writers)}, indent=2))
        return 1 if (args.strict and (violations or writers)) else 0

    print("=" * 96)
    print("AUDIT WIRING KONFIGURASI — apakah setiap setting benar-benar berfungsi?")
    print("=" * 96)
    print(f"Total kunci terdeklarasi : {len(rows)}")
    for st in ("OK", "NOT_USED", "HIDDEN", "ORPHAN_UI", "DEAD"):
        label = {
            "OK": "wiring lengkap (dibaca kode + bisa diubah user)",
            "NOT_USED": "registry menyatakan tidak dipakai + alasan (SAH)",
            "HIDDEN": "dibaca kode TAPI TANPA UI (hanya via DB/API)",
            "ORPHAN_UI": "ADA UI TAPI TIDAK DIBACA KODE  <-- tombol palsu",
            "DEAD": "tidak dibaca & tidak ada UI",
        }[st]
        print(f"  {st:<10} {counts.get(st, 0):>4}   {label}")
    print()
    print("Pusat Pengaturan (UI generik):",
          "TERSAMBUNG" if wired else "TIDAK TERSAMBUNG")
    for w in wired_problems:
        print(f"  ! {w}")
    if writers:
        print(f"Editor konfigurasi di luar Pusat Pengaturan: {len(writers)} berkas "
              f"<-- sumber kebenaran ganda")
        for rel, eps in writers.items():
            print(f"  ! {rel} → {', '.join(eps)}")
    else:
        print("Editor konfigurasi di luar Pusat Pengaturan: TIDAK ADA (satu sumber kebenaran)")
    print()

    per_scope: Dict[str, Dict[str, int]] = {}
    for r in rows:
        per_scope.setdefault(r["scope"], {}).setdefault(r["status"], 0)
        per_scope[r["scope"]][r["status"]] += 1
    print("Per scope:")
    for sc in sorted(per_scope):
        c = per_scope[sc]
        print(
            f"  {sc:<14} total={sum(c.values()):>3}  OK={c.get('OK',0):>3} "
            f"HIDDEN={c.get('HIDDEN',0):>3} ORPHAN_UI={c.get('ORPHAN_UI',0):>3} "
            f"DEAD={c.get('DEAD',0):>3} NOT_USED={c.get('NOT_USED',0):>3}"
        )
    print()

    for st in ("ORPHAN_UI", "DEAD", "HIDDEN", "NOT_USED"):
        if args.only and args.only != st:
            continue
        sel = [r for r in rows if r["status"] == st]
        if not sel:
            continue
        print(f"── {st} ({len(sel)}) " + "─" * (76 - len(st)))
        for r in sel:
            extra = ""
            if st == "ORPHAN_UI":
                extra = f"  UI: {', '.join(r['ui'][:2])}"
            elif st == "HIDDEN":
                extra = f"  kode: {', '.join(r['consumers'][:2])}"
            elif st == "NOT_USED":
                extra = f"  alasan: {r['not_used_reason'][:70]}"
            print(f"  [{r['scope']}] {r['path']:<52} default={r['default']!r}{extra}")
        print()

    if args.md:
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write("# Audit Wiring Konfigurasi\n\n")
            fh.write(f"Total kunci: **{len(rows)}**\n\n")
            fh.write("| Status | Jumlah | Arti |\n|---|---|---|\n")
            for st in ("OK", "NOT_USED", "HIDDEN", "ORPHAN_UI", "DEAD"):
                fh.write(f"| {st} | {counts.get(st,0)} | |\n")
            fh.write("\n| Scope | Path | Status | Default | #consumer | #UI |\n")
            fh.write("|---|---|---|---|---|---|\n")
            for r in sorted(rows, key=lambda x: (x["status"], x["scope"], x["path"])):
                fh.write(
                    f"| {r['scope']} | `{r['path']}` | {r['status']} | `{r['default']}` "
                    f"| {r['consumer_count']} | {r['ui_count']} |\n"
                )
        print(f"[md] laporan ditulis ke {args.md}")

    if violations or writers:
        print(f"\u26a0\ufe0f  {len(violations)} kunci bermasalah + {len(writers)} editor ganda "
              f"(INV-CFG).")
        return 1 if args.strict else 0
    print("\u2705 INV-CFG: setiap setting terdeklarasi punya pembaca kode DAN jalur ubah "
          "yang nyata; tidak ada editor ganda.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
