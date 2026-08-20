#!/usr/bin/env python3
"""INV-DOMAIN-06 — MASTER TAHAPAN PROSES vs REGISTRY DOMAIN (FASE T).

KELAS BUG YANG DICEGAH
======================
FASE T memindahkan daftar tahapan kerja (benang · tenun · rajut · pfp · pfd ·
celup · **screen** · printing · proofing · inspect) dari kode ke **master**
`process_stages`, supaya pemilik bisa menambah "Sanforize" besok tanpa programmer.
Kebebasan itu membuka lima cara gagal yang semuanya SENYAP — tidak ada galat,
tidak ada layar merah, hanya papan yang perlahan berbohong:

  A. **Tahap yang masih dipakai dokumen DINONAKTIFKAN/DIHAPUS.** SPK lama menunjuk
     `stage_code` yang tak ada lagi di master → papan menampilkan langkah tanpa
     nama, dan `_resolve_stage` jatuh ke jalur kompatibilitas tanpa ada yang tahu.
     Karena itu penjaga ini tidak cukup membandingkan daftar: ia **MENGHITUNG
     dokumen pemakainya** sebelum menuduh.
  B. **`process_type` asing.** Baris master menunjuk jenis proses yang tidak ada
     di `domain_registry.PROCESS_TYPES` → mesin tarif/estimasi tidak punya aturan
     untuk langkah itu, dan pemilih mitra menyaring dengan nilai yang tak pernah
     cocok (form SPK jadi jalan buntu).
  C. **`from_stage`/`to_stage` asing.** Papan mengatakan kain berpindah ke tahap
     yang tidak ada di enum `stage` → validator transisi menolak langkah yang
     "sah menurut master".
  D. **Tahap mengubah kain tetapi transisinya tidak ada di `STAGE_TRANSITIONS`.**
     Ini kelas bug paling mahal di fase ini: papan MENAWARKAN langkah yang mesin
     makloon PASTI menolak. Petugas mengisi form lengkap, menekan Simpan, lalu
     ditolak tanpa jalan keluar.
  E. **`needs_vendor=true` tetapi tidak ada satu pun mitra terdaftar** dengan
     `process_types` memuat proses itu. Keputusan pemilik 3b membuat form hanya
     MEMPERINGATKAN (supaya SPK darurat tetap bisa dicatat), jadi kelalaian ini
     HARUS ditangkap di sini — kalau tidak, ia tak pernah terlihat sama sekali.

Ditambah satu pemeriksaan milik keputusan 1c (aliran kain):
  F. `material_flow` hanya boleh `moves|service_only|either` (kosong untuk tahap
     non-makloon), dan bila `either` maka `material_flow_default` WAJIB salah satu
     dari `moves|service_only` — kalau tidak, mesin harus MENEBAK apakah kain
     bergerak, dan tebakan itu memindahkan (atau tidak memindahkan) stok sungguhan.

YANG DIPERIKSA
--------------
STATIK  (tanpa basis data)
  S1. benih `PROCESS_STAGES` konsisten dengan enum lain di registry (aturan B–D–F
      diberlakukan ke benihnya sendiri; benih yang salah akan disebar migrasi).
RUNTIME (Mongo langsung — opini kedua, tidak lewat API yang sedang diuji)
  R1. (A) tahap yang dipakai `makloon_orders.steps[].stage_code` masih ada & aktif
  R2. (B) `process_stages.process_type` ∈ PROCESS_TYPES
  R3. (C) `from_stage`/`to_stage` ∈ STAGES
  R4. (D) `changes_stage=true` punya pasangan di STAGE_TRANSITIONS
  R5. (E) `needs_vendor=true` punya ≥1 mitra `makloons` untuk prosesnya
  R6. (F) `material_flow`/`material_flow_default` sah

Resilient: tanpa MONGO_URL / basis data mati → bagian runtime SKIP (exit 0),
bagian statik tetap jalan. Exit 1 hanya bila invarian terbukti dilanggar.

Usage:
    python scripts/guardrails/verify_master_stages.py
    python scripts/guardrails/verify_master_stages.py --self-test   # bukti-merah, tanpa DB
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import B, G, R, X, Y, Guard  # noqa: E402

import domain_registry as dr  # noqa: E402

VALID_FLOWS = {"moves", "service_only", "either"}
CONCRETE_FLOWS = {"moves", "service_only"}


# ═══════════════════════════════════════════════════════════════════════════
# FUNGSI MURNI — bisa diuji tanpa Mongo (dipakai --self-test)
# ═══════════════════════════════════════════════════════════════════════════

def _code(row: Dict[str, Any]) -> str:
    return str(row.get("code") or row.get("value") or "").strip().lower()


def _is_active(row: Dict[str, Any]) -> bool:
    if row.get("active") is False:
        return False
    return str(row.get("status") or "active") != "inactive"


def check_still_used(master_rows: List[Dict[str, Any]],
                     usage: Dict[str, int]) -> List[str]:
    """A — tahap yang MASIH dipakai dokumen tidak boleh hilang/nonaktif.

    `usage` = {stage_code: jumlah langkah SPK yang memakainya}. Menuduh berdasarkan
    daftar saja akan memerah setiap kali pemilik merapikan tahap yang memang tak
    terpakai — penjaga yang menuduh palsu akan diabaikan, lalu berhenti menjaga.
    """
    out: List[str] = []
    active = {_code(r) for r in master_rows if _is_active(r)}
    known = {_code(r) for r in master_rows}
    for code, n in sorted(usage.items()):
        if not code or n <= 0:
            continue
        if code not in known:
            out.append(f"(A) tahap '{code}' dipakai {n} langkah SPK tetapi TIDAK ADA "
                       "di master `process_stages` — papan menampilkan langkah tanpa nama. "
                       "Kembalikan barisnya (Pengaturan → Master → Tahapan Proses) atau "
                       "pindahkan SPK-nya ke tahap lain lebih dulu.")
        elif code not in active:
            out.append(f"(A) tahap '{code}' DINONAKTIFKAN padahal masih dipakai {n} "
                       "langkah SPK. Nonaktifkan hanya setelah tidak ada dokumen pemakai.")
    return out


def check_process_type(master_rows: List[Dict[str, Any]],
                       live_process_types: Set[str]) -> List[str]:
    """B — `process_type` baris master harus dikenal mesin tarif/estimasi."""
    out: List[str] = []
    for r in master_rows:
        if not _is_active(r):
            continue
        pt = str(r.get("process_type") or "").strip().lower()
        if not pt:
            continue                      # tahap non-makloon (benang/inspect) — sah
        if pt not in live_process_types:
            out.append(f"(B) tahap '{_code(r)}' menunjuk process_type '{pt}' yang tidak "
                       f"ada di registry. Pilihan: {', '.join(sorted(live_process_types))}. "
                       "Tambahkan nilainya di `domain_registry.PROCESS_TYPES` atau perbaiki "
                       "masternya — tanpa itu mesin tarif tidak punya aturan untuk langkah ini.")
    return out


def check_stages_known(master_rows: List[Dict[str, Any]],
                       stages: Set[str]) -> List[str]:
    """C — `from_stage`/`to_stage` harus ada di enum `stage`."""
    out: List[str] = []
    for r in master_rows:
        if not _is_active(r):
            continue
        for field in ("from_stage", "to_stage"):
            v = str(r.get(field) or "").strip().lower()
            if v and v not in stages:
                out.append(f"(C) tahap '{_code(r)}' punya {field}='{v}' yang bukan tahap "
                           f"kain. Pilihan: {', '.join(sorted(stages))}.")
    return out


def check_transition_exists(master_rows: List[Dict[str, Any]],
                            transitions: List[Dict[str, Any]]) -> List[str]:
    """D — tahap yang MENGUBAH kain wajib punya pasangan di STAGE_TRANSITIONS."""
    out: List[str] = []
    for r in master_rows:
        if not _is_active(r):
            continue
        if r.get("changes_stage") is False:
            continue                      # tidak mengubah kain → tak butuh transisi
        pt = str(r.get("process_type") or "").strip().lower()
        fs = str(r.get("from_stage") or "").strip().lower()
        ts = str(r.get("to_stage") or "").strip().lower()
        if not (pt and fs and ts):
            continue                      # tahap non-makloon / belum lengkap
        tu = str(r.get("target_use") or "").strip().lower() or None
        hit = [t for t in transitions
               if t.get("from_stage") == fs and t.get("process_type") == pt
               and t.get("to_stage") == ts
               and (tu is None or (t.get("target_use") or None) == tu)]
        if not hit:
            out.append(f"(D) tahap '{_code(r)}' menjanjikan {fs} --{pt}--> {ts}"
                       + (f" (target_use={tu})" if tu else "")
                       + " tetapi transisi itu TIDAK ADA di `STAGE_TRANSITIONS`. Papan akan "
                       "menawarkan langkah yang mesin makloon pasti menolak. Tambahkan "
                       "transisinya di `domain_registry.STAGE_TRANSITIONS`.")
    return out


def check_vendor_available(master_rows: List[Dict[str, Any]],
                           vendor_process_types: Set[str]) -> List[str]:
    """E — `needs_vendor=true` wajib punya minimal 1 mitra terdaftar untuk prosesnya."""
    out: List[str] = []
    for r in master_rows:
        if not _is_active(r) or not r.get("needs_vendor"):
            continue
        pt = str(r.get("process_type") or "").strip().lower()
        if not pt:
            continue
        if pt not in vendor_process_types:
            out.append(f"(E) tahap '{_code(r)}' dikerjakan mitra ('{pt}') tetapi TIDAK ADA "
                       "satu pun mitra di `makloons` yang mencantumkan proses itu. Form SPK "
                       "akan jadi jalan buntu: petugas dituntut memilih mitra dari daftar "
                       "kosong. Daftarkan mitranya di Mitra Makloon (centang kemampuan "
                       f"'{pt}').")
    return out


def check_material_flow(master_rows: List[Dict[str, Any]]) -> List[str]:
    """F — aliran kain harus tegas; `either` wajib punya bawaan yang konkret."""
    out: List[str] = []
    for r in master_rows:
        if not _is_active(r):
            continue
        kind = str(r.get("kind") or "makloon").strip().lower()
        flow = str(r.get("material_flow") or "").strip().lower()
        default = str(r.get("material_flow_default") or "").strip().lower()
        if not flow:
            if kind in ("makloon", "sampling"):
                out.append(f"(F) tahap '{_code(r)}' berjenis '{kind}' (bisa jadi langkah SPK) "
                           "tetapi `material_flow` kosong — mesin harus MENEBAK apakah kain "
                           "bergerak, dan tebakan itu memindahkan stok sungguhan. Isi "
                           "`moves`, `service_only`, atau `either`.")
            continue
        if flow not in VALID_FLOWS:
            out.append(f"(F) tahap '{_code(r)}' punya material_flow='{flow}' yang tidak "
                       f"dikenal. Pilihan: {', '.join(sorted(VALID_FLOWS))}.")
            continue
        if flow == "either" and default not in CONCRETE_FLOWS:
            out.append(f"(F) tahap '{_code(r)}' membuka dua-duanya (`either`) tetapi "
                       f"`material_flow_default` = '{default or '(kosong)'}'. Isi `moves` "
                       "atau `service_only` — itulah yang dipakai bila langkah SPK tidak "
                       "memilih, dan nilainya dicatat di jejak estimasi.")
    return out


# ═══════════════════════════════════════════════════════════════════════════
# STATIK — benihnya sendiri harus lolos aturan B, C, D, F
# ═══════════════════════════════════════════════════════════════════════════

def run_static(guard: Guard) -> None:
    seed = [dict(v) for v in dr.enum_items("process_stage")]
    live_pt = set(dr.values_of("process_type"))
    stages = set(dr.values_of("stage"))
    guard.bump(4)
    for v in check_process_type(seed, live_pt):
        guard.add(f"[benih] {v}")
    for v in check_stages_known(seed, stages):
        guard.add(f"[benih] {v}")
    for v in check_transition_exists(seed, dr.STAGE_TRANSITIONS):
        guard.add(f"[benih] {v}")
    for v in check_material_flow(seed):
        guard.add(f"[benih] {v}")
    # Aturan E TIDAK diberlakukan ke benih: mitra hidup di basis data, bukan di kode.
    print(f"  · benih PROCESS_STAGES: {len(seed)} tahap diperiksa "
          f"({', '.join(_code(r) for r in seed)})")


# ═══════════════════════════════════════════════════════════════════════════
# RUNTIME — master hidup + dokumen pemakainya
# ═══════════════════════════════════════════════════════════════════════════

async def run_runtime(guard: Guard) -> None:
    from db import db
    from services import master_registry as mreg

    rows = await db.process_stages.find({}, {"_id": 0}).to_list(1000)
    if not rows:
        # Fallback benih adalah perilaku yang DISENGAJA (instalasi baru tidak mati).
        # Tetapi ia harus disebut, bukan dianggap "hijau" diam-diam.
        print(f"{Y}  · koleksi `process_stages` masih KOSONG — sistem memakai nilai benih "
              f"`domain_registry.PROCESS_STAGES`. Jalankan "
              f"`python scripts/migrate_process_stages.py` agar tahapnya bisa diubah pemilik.{X}")
        rows = [dict(v) for v in dr.enum_items("process_stage")]

    usage: Dict[str, int] = {}
    async for o in db.makloon_orders.find({}, {"_id": 0, "steps": 1}):
        for s in o.get("steps") or []:
            code = str(s.get("stage_code") or "").strip().lower()
            if code:
                usage[code] = usage.get(code, 0) + 1

    vendor_pt: Set[str] = set()
    async for m in db.makloons.find({}, {"_id": 0, "process_types": 1, "status": 1}):
        if str(m.get("status") or "active") == "inactive":
            continue
        for p in m.get("process_types") or []:
            vendor_pt.add(str(p).strip().lower())

    live_pt = {v["value"] for v in await mreg.process_types("")}
    stages = set(dr.values_of("stage"))

    guard.bump(6)
    for v in check_still_used(rows, usage):
        guard.add(v)
    for v in check_process_type(rows, live_pt):
        guard.add(v)
    for v in check_stages_known(rows, stages):
        guard.add(v)
    for v in check_transition_exists(rows, dr.STAGE_TRANSITIONS):
        guard.add(v)
    for v in check_vendor_available(rows, vendor_pt):
        guard.add(v)
    for v in check_material_flow(rows):
        guard.add(v)
    print(f"  · master hidup: {len(rows)} tahap · SPK memakai {len(usage)} tahap "
          f"({sum(usage.values())} langkah) · mitra menutup {len(vendor_pt)} jenis proses")


# ═══════════════════════════════════════════════════════════════════════════
# SELF-TEST — bukti-merah DUA ARAH (bersih & pelanggaran)
# ═══════════════════════════════════════════════════════════════════════════

def self_test() -> int:
    cases: List[Tuple[str, bool]] = []

    def case(label: str, cond: bool) -> None:
        cases.append((label, bool(cond)))

    screen = {"code": "screen", "kind": "makloon", "process_type": "screen",
              "from_stage": "pfp", "to_stage": "pfp", "changes_stage": False,
              "needs_vendor": True, "material_flow": "either",
              "material_flow_default": "service_only", "active": True}
    tenun = {"code": "tenun", "kind": "makloon", "process_type": "tenun",
             "from_stage": "yarn", "to_stage": "grey", "changes_stage": True,
             "needs_vendor": True, "material_flow": "moves",
             "material_flow_default": "moves", "active": True}
    inspect = {"code": "inspect", "kind": "inspection", "process_type": "",
               "from_stage": "", "to_stage": "", "changes_stage": False,
               "needs_vendor": False, "material_flow": "", "active": True}
    good = [screen, tenun, inspect]

    # ── A — tahap yang masih dipakai dokumen ────────────────────────────────
    case("A bersih (semua tahap yang dipakai ada & aktif)",
         check_still_used(good, {"screen": 2, "tenun": 5}) == [])
    case("A memerah bila tahap yang dipakai DIHAPUS dari master",
         len(check_still_used([tenun], {"screen": 2})) == 1)
    case("A memerah bila tahap yang dipakai DINONAKTIFKAN",
         len(check_still_used([{**screen, "active": False}, tenun], {"screen": 3})) == 1)
    case("A TIDAK menuduh tahap tak terpakai yang dinonaktifkan (anti tuduhan palsu)",
         check_still_used([{**screen, "active": False}, tenun], {"tenun": 1}) == [])

    # ── B — process_type asing ──────────────────────────────────────────────
    live = {"tenun", "screen", "printing"}
    case("B bersih", check_process_type(good, live) == [])
    case("B memerah untuk process_type yang tak ada di registry",
         len(check_process_type([{**screen, "process_type": "sablon"}], live)) == 1)
    case("B TIDAK menuduh tahap non-makloon (process_type kosong)",
         check_process_type([inspect], live) == [])

    # ── C — from/to stage asing ─────────────────────────────────────────────
    st = {"yarn", "grey", "pfd", "pfp", "finished"}
    case("C bersih", check_stages_known(good, st) == [])
    case("C memerah untuk to_stage asing",
         len(check_stages_known([{**tenun, "to_stage": "kain_setengah"}], st)) == 1)

    # ── D — transisi wajib ada ──────────────────────────────────────────────
    trans = [{"from_stage": "yarn", "process_type": "tenun", "to_stage": "grey",
              "target_use": None},
             {"from_stage": "grey", "process_type": "pre_treatment", "to_stage": "pfp",
              "target_use": "print"}]
    case("D bersih (tenun punya transisi · screen tidak mengubah kain)",
         check_transition_exists(good, trans) == [])
    case("D memerah bila tahap pengubah kain tak punya transisi",
         len(check_transition_exists(
             [{**tenun, "process_type": "printing", "from_stage": "pfp",
               "to_stage": "finished"}], trans)) == 1)
    case("D memperhatikan target_use (dye vs print)",
         len(check_transition_exists(
             [{"code": "pfd", "kind": "makloon", "process_type": "pre_treatment",
               "from_stage": "grey", "to_stage": "pfd", "target_use": "dye",
               "changes_stage": True, "active": True}], trans)) == 1)

    # ── E — mitra tersedia ──────────────────────────────────────────────────
    case("E bersih bila mitra menutup semua proses ber-mitra",
         check_vendor_available(good, {"tenun", "screen"}) == [])
    case("E memerah bila needs_vendor tanpa mitra terdaftar (bukti-merah T6)",
         len(check_vendor_available(good, {"tenun"})) == 1)
    case("E TIDAK menuduh tahap yang tidak butuh mitra",
         check_vendor_available([inspect], set()) == [])

    # ── F — aliran kain ─────────────────────────────────────────────────────
    case("F bersih", check_material_flow(good) == [])
    case("F memerah untuk nilai aliran kain yang tak dikenal",
         len(check_material_flow([{**screen, "material_flow": "kirim_saja"}])) == 1)
    case("F memerah bila `either` tanpa bawaan konkret",
         len(check_material_flow([{**screen, "material_flow_default": ""}])) == 1)
    case("F memerah bila tahap SPK tidak punya aliran kain sama sekali",
         len(check_material_flow([{**tenun, "material_flow": ""}])) == 1)
    case("F TIDAK menuduh tahap inspeksi tanpa aliran kain",
         check_material_flow([inspect]) == [])

    print(f"{B}== SELF-TEST INV-DOMAIN-06 (bukti-merah dua arah) =={X}")
    fails = 0
    for label, cond in cases:
        print(f"  {G}[OK]{X} {label}" if cond else f"  {R}[GAGAL]{X} {label}")
        fails += 0 if cond else 1
    if fails:
        print(f"{R}SELF-TEST GAGAL: {fails}/{len(cases)} — penjaga tidak bisa dipercaya.{X}")
        return 1
    print(f"{G}SELF-TEST LULUS: {len(cases)}/{len(cases)} kasus (bersih & pelanggaran).{X}")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    guard = Guard("INV-DOMAIN-06", "Master tahapan proses vs registry domain "
                                   "(tahap terpakai · process_type · stage · transisi · "
                                   "mitra · aliran kain)")
    run_static(guard)
    if os.environ.get("MONGO_URL"):
        try:
            asyncio.run(run_runtime(guard))
        except Exception as exc:  # noqa: BLE001 — DB mati ≠ pelanggaran invarian
            print(f"{Y}[SKIP]{X} bagian runtime dilewati: {type(exc).__name__}: {exc}")
    else:
        print(f"{Y}[SKIP]{X} MONGO_URL tidak tersedia — hanya pemeriksaan statik.")
    return guard.finish()


if __name__ == "__main__":
    raise SystemExit(main())
