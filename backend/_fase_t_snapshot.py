"""FASE T — ALAT BUKTI REGRESI (dipakai POC T4, bukan sekadar catatan).

Rencana §7 FASE T menuntut: *"3 SPK makloon lama dibuka & dihitung ulang →
`estimate` (`expected_output_qty`, `explain[]`, biaya) **identik byte-per-byte**
dengan sebelum fase."*

Kalau snapshotnya diambil SESUDAH kode berubah, ia tidak membuktikan apa pun —
ia hanya merekam keadaan baru. Jadi berkas ini dijalankan **dua kali**:

    python backend/_fase_t_snapshot.py before   # sebelum satu baris pun diubah
    python backend/_fase_t_snapshot.py after    # sesudah FASE T selesai
    python backend/_fase_t_snapshot.py diff     # bandingkan (0 = identik)

Yang direkam sengaja SEMPIT: hanya field yang menentukan angka & penjelasan
(estimate, expected/actual qty, tarif, biaya, HPP). Field yang MEMANG bertambah
di FASE T (`stage_code`, `changes_stage`, `material_flow`) tidak direkam —
kalau direkam, penambahan yang diminta rencana akan terbaca sebagai kemunduran.
"""
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

OUT = pathlib.Path(__file__).resolve().parent.parent / ".logs" / "fase_t"

# Field per langkah yang WAJIB tidak berubah (angka & jejak audit).
STEP_KEYS = (
    "seq", "process_type", "makloon_id", "makloon_name", "target_use",
    "input_product_id", "input_qty", "input_unit",
    "output_product_id", "output_unit",
    "byproduct_product_id", "byproduct_pct",
    "yield_factor", "yield_override_reason",
    "waste_pct", "shrinkage_pct", "shrinkage_source", "tolerance_pct",
    "estimate", "expected_output_qty", "expected_byproduct_qty",
    "actual_output_qty", "actual_byproduct_qty",
    "tariff_basis", "tariff_rate", "tariff", "tariff_plan", "tariff_original",
    "tariff_base_equivalent", "aux_cost",
    "material_value", "service_value", "output_value", "output_unit_cost",
    "status",
)
ORDER_KEYS = ("mko_number", "mode", "material_qty", "material_unit", "status",
              "planned_service_cost", "forecast", "costing")


async def collect() -> dict:
    from db import db
    rows = await db.makloon_orders.find({}, {"_id": 0}).sort("mko_number", 1).to_list(500)
    out = {}
    for o in rows:
        snap = {k: o.get(k) for k in ORDER_KEYS}
        snap["steps"] = [{k: s.get(k) for k in STEP_KEYS} for s in o.get("steps") or []]
        out[o.get("mko_number") or o.get("id")] = snap
    return out


# ═══════════════════════════════════════════════════════════════════════════
# PEMBANDING — tiga golongan perbedaan, satu di antaranya BOLEH
# ═══════════════════════════════════════════════════════════════════════════
# Rencana §T.D menuntut angka SPK lama **tidak bergeser**. Yang TIDAK dituntutnya:
# field baru yang memang diminta fase ini tidak boleh muncul. Jadi pembanding ini
# menggolongkan setiap perbedaan, bukan hanya menjawab "sama/tidak":
#
#   1. TAMBAHAN  — field yang dulu TIDAK ADA lalu ada, dan namanya terdaftar di
#      `ADDED_FIELDS`. Ini yang diminta rencana (`stage_code`, `material_flow`, …).
#      Kalau nilai lamanya ADA lalu berubah, ia bukan tambahan → pergeseran.
#   2. SENGAJA   — SATU perubahan input yang diputuskan sesi 2026-08-19: pagar PS-03
#      pindah ke service, jadi data demo pun wajib beralasan (`yield_override_reason`
#      kosong → teks). Tiga akibat turunannya diterima HANYA bila bentuknya persis:
#      `estimate.yield_reason` ikut terisi · baris explain OVERRIDE hanya MENDAPAT
#      sufiks " · alasan: …" (kalimat sebelumnya utuh) · peringatan PS-03 hilang.
#      Bentuk lain = pergeseran, walaupun field-nya sama.
#   3. PERGESERAN — sisanya. Satu saja cukup untuk exit 1.
#
# Kenapa tidak sekadar merekam ulang `spk_before.json`: snapshot "sebelum" yang
# diambil sesudah kode berubah tidak membuktikan apa pun. Ia tidak pernah ditimpa.
ADDED_FIELDS = frozenset({
    # FASE T — tahap dari master (rencana §T.D)
    "stage_code", "stage_label", "stage_kind", "stage_seq", "stage_source",
    "stage_from_stage", "stage_to_stage", "changes_stage", "needs_vendor",
    "material_flow", "material_flow_source",
    # FASE T — penyerapan biaya jasa murni ke HPP kain (Dr 5-1200 bila tak terserap)
    "absorbed_service_value", "service_absorption_pending", "service_unabsorbed",
})
PS03_WARNING = "Override yield tanpa alasan — wajib diisi agar bisa diaudit (PS-03)."
MISSING = object()

# Field yang BERUBAH SETIAP SEED ULANG dan bukan angka: cap waktu perhitungan dan
# **id pengganti** (surrogate) dokumen yang lahir baru. Membiarkannya dihitung sebagai
# pergeseran membuat alat ini mustahil hijau, dan alat yang mustahil hijau akan
# diabaikan — lalu berhenti menjaga apa pun (pelajaran `ux_audit` FASE P5).
# Identitas kontrak yang BERARTI tetap dijaga: `contract_number` ada di STEP_KEYS dan
# dibandingkan seperti field lain, jadi kontrak yang tertukar tetap memerah di sini.
VOLATILE_LEAVES = {
    "computed_at": "cap waktu perhitungan tarif",
    "contract_id": "id pengganti kontrak (nomor kontraknya dibandingkan terpisah)",
}


def _flatten(obj: object, prefix: str = "") -> dict:
    """Ubah dokumen bersarang → {jalur: nilai daun} supaya beda bisa DIGOLONGKAN.

    Membandingkan seluruh dict sekaligus hanya bisa menjawab "beda"; menggolongkan
    butuh jalur tiap daun (mis. `steps[0].estimate.explain[2]`).
    """
    out: dict = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def _leaf(path: str) -> str:
    return path.rsplit(".", 1)[-1].split("[", 1)[0]


def _deliberate(path: str, before: object, after: object) -> str:
    """Kembalikan penjelasan bila perbedaan ini SATU perubahan sengaja + turunannya."""
    leaf = _leaf(path)
    empty_before = before in ("", None)
    if leaf in ("yield_override_reason", "yield_reason") and empty_before and isinstance(after, str) and after.strip():
        return f"alasan override yield diisi: “{after}”"
    if leaf == "explain" and isinstance(before, str) and isinstance(after, str):
        if after.startswith(f"{before} · alasan: "):
            return "baris explain OVERRIDE mendapat sufiks alasan (kalimat lama utuh)"
    if leaf == "warnings" and before == PS03_WARNING and after is MISSING:
        return "peringatan PS-03 hilang karena alasannya kini ada"
    return ""


def _volatile(path: str, before: object, after: object) -> str:
    """Perbedaan yang bukan angka: cap waktu & id pengganti yang lahir tiap seed ulang."""
    leaf = _leaf(path)
    why = VOLATILE_LEAVES.get(leaf)
    if not why or not (isinstance(before, str) and isinstance(after, str)):
        return ""
    if leaf == "contract_id" and before.split("_", 1)[0] != after.split("_", 1)[0]:
        return ""            # ganti JENIS dokumen, bukan sekadar id baru → tetap merah
    return why


def compare(before: dict, after: dict) -> int:
    shared = sorted(set(before) & set(after))
    only_after = sorted(set(after) - set(before))
    only_before = sorted(set(before) - set(after))
    same = 0
    added: dict = {}
    volatile: dict = {}
    deliberate: list = []
    drift: list = []
    for key in shared:
        b, a = _flatten(before[key]), _flatten(after[key])
        for path in sorted(set(b) | set(a)):
            bv, av = b.get(path, MISSING), a.get(path, MISSING)
            if bv is not MISSING and av is not MISSING and bv == av:
                same += 1
                continue
            if bv is MISSING and _leaf(path) in ADDED_FIELDS:
                added.setdefault(_leaf(path), 0)
                added[_leaf(path)] += 1
                continue
            vol = _volatile(path, bv, av)
            if vol:
                volatile.setdefault(vol, 0)
                volatile[vol] += 1
                continue
            why = _deliberate(path, bv, av)
            if why:
                deliberate.append((key, path, why))
                continue
            drift.append((key, path, bv, av))

    print(f"{len(shared)} SPK dibandingkan · {same} field angka & jejak IDENTIK.")
    if added:
        print(f"  TAMBAHAN (diminta rencana §T.D) — {sum(added.values())} field baru: "
              + ", ".join(f"{k}×{n}" for k, n in sorted(added.items())))
    for why, n in sorted(volatile.items()):
        print(f"  TIDAK DETERMINISTIK ×{n} — {why}")
    for key, path, why in deliberate:
        print(f"  SENGAJA · {key} · {path} → {why}")
    if only_after:
        print(f"  SPK BARU (bukan regresi, data demo FASE T): {', '.join(only_after)}")
    if only_before:
        print(f"  HILANG — SPK yang dulu ada kini tidak: {', '.join(only_before)}")
        drift += [(k, "(dokumen hilang)", "ada", MISSING) for k in only_before]
    if drift:
        print(f"\nPERGESERAN ANGKA — {len(drift)} field bergerak tanpa izin:")
        for key, path, bv, av in drift[:40]:
            b = "(tidak ada)" if bv is MISSING else repr(bv)
            a = "(tidak ada)" if av is MISSING else repr(av)
            print(f"  · {key} · {path}: {b} → {a}")
        return 1
    print("HASIL: 0 pergeseran angka — estimasi, explain[] & dasar tarif SPK lama utuh.")
    return 0


async def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "before").lower()
    OUT.mkdir(parents=True, exist_ok=True)
    if mode in ("before", "after"):
        data = await collect()
        path = OUT / f"spk_{mode}.json"
        path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        print(f"[{mode}] {len(data)} SPK direkam → {path}")
        return 0
    if mode == "diff":
        a = json.loads((OUT / "spk_before.json").read_text())
        b = json.loads((OUT / "spk_after.json").read_text())
        return compare(a, b)
    print(f"mode tidak dikenal: {mode} (pakai before|after|diff)")
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
