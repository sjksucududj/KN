"""HRD services (FASE H0) — helper murni-orchestration untuk modul HR.

Berisi:
- `next_employee_code()` — number series EMP-NNNNN (deletion-safe scan).
- `redact_employee_pii()` — sembunyikan field PII (gaji, NPWP, BPJS no, rekening).
- `get_hr_settings()` / `DEFAULT_HR_SETTINGS` — config statutory (config-driven, dipakai H4).
- `org_unit_map()` / `user_map()` / `enrich_employee()` — resolusi nama dept/posisi/akun (hindari N+1).
- `build_org_tree()` — bentuk hierarki Company(entitas) > department > position.

Tanpa JSX/HTTP — mudah diuji. Semua I/O async ke Mongo (motor).
"""
from typing import Any, Dict, List

from db import db

# Field PII yang diredaksi untuk pemirsa tanpa permission hr.view_pii.
PII_FIELDS = [
    "npwp", "ptkp_status", "bpjs_kes_no", "bpjs_tk_no", "jkk_risk_class",
    "bank_name", "bank_acc_no", "bank_acc_name", "base_salary", "allowances",
]

# Default config statutory Indonesia (acuan 2026 — config-driven, owner bisa koreksi).
DEFAULT_HR_SETTINGS: Dict[str, Any] = {
    "bpjs": {
        "kes_rate_employee": 1.0, "kes_rate_employer": 4.0, "kes_ceiling": 12000000,
        "jht_rate_employee": 2.0, "jht_rate_employer": 3.7,
        "jp_rate_employee": 1.0, "jp_rate_employer": 2.0, "jp_ceiling": 10042300,
        "jkm_rate_employer": 0.3,
    },
    "jkk_classes": [
        {"class": "I", "rate": 0.24}, {"class": "II", "rate": 0.54},
        {"class": "III", "rate": 0.89}, {"class": "IV", "rate": 1.27},
        {"class": "V", "rate": 1.74},
    ],
    "ptkp_table": {
        "TK0": 54000000, "TK1": 58500000, "TK2": 63000000, "TK3": 67500000,
        "K0": 58500000, "K1": 63000000, "K2": 67500000, "K3": 72000000,
    },
    "ter_enabled": True,
    "overtime": {"multiplier": 1.5, "hours_divisor": 173},
    "feature_toggles": {
        "bpjs_kesehatan": True, "bpjs_ketenagakerjaan": True,
        "pph21": True, "npwp_required": False,
    },
    "employment_types": ["tetap", "kontrak", "harian", "borongan"],
    "payroll_commission_mode": "accrue_then_settle",
}


async def next_employee_code() -> str:
    """Number series EMP-NNNNN (cegah duplikat via max existing)."""
    last = await db.hr_employees.find_one({}, {"_id": 0, "code": 1}, sort=[("code", -1)])
    n = 0
    if last and isinstance(last.get("code"), str) and last["code"].startswith("EMP-"):
        try:
            n = int(last["code"].split("-")[1])
        except (ValueError, IndexError):
            n = await db.hr_employees.count_documents({})
    else:
        n = await db.hr_employees.count_documents({})
    return f"EMP-{n + 1:05d}"


def redact_employee_pii(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Set field PII ke None + flag pii_redacted (untuk pemirsa tanpa hr.view_pii)."""
    if not doc:
        return doc
    out = dict(doc)
    for f in PII_FIELDS:
        if f in out:
            out[f] = None
    out["pii_redacted"] = True
    return out


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Gabung rekursif dua dict. Nilai dict di-merge per-leaf; non-dict ditimpa.

    Dipakai agar update parsial pada config bersarang (mis. `bpjs`) tidak
    menghapus key saudara yang tak dikirim klien.
    """
    out: Dict[str, Any] = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out



async def get_hr_settings(entity_id: str = "") -> Dict[str, Any]:
    """Ambil config HR (deep-merge default + tersimpan; tersimpan menang per-leaf).

    Deep-merge mencegah HILANGNYA sub-key statutory: bila dokumen tersimpan hanya
    memuat sebagian `bpjs` (mis. tersisa kes_*), key lain (jht/jp/jkm/ceiling) tetap
    diisi dari DEFAULT_HR_SETTINGS, bukan ikut lenyap (anti data-loss).

    FASE E-4 (E4.5) — `entity_id` menambahkan lapisan **badan usaha** di atas nilai
    global. Ini kebutuhan nyata: satu badan usaha bisa PKP dengan karyawan tetap
    (BPJS penuh, PPh21 TER) sementara badan usaha lain non-PKP dengan tenaga
    borongan. Tanpa `entity_id`, hasilnya identik dengan perilaku lama.
    """
    rec = await db.system_settings.find_one({"scope": "hr"}, {"_id": 0})
    stored = {k: v for k, v in (rec or {}).items()
              if k not in ("scope", "id", "created_at", "updated_at")}
    merged = deep_merge(DEFAULT_HR_SETTINGS, stored)
    if entity_id and entity_id != "all":
        from services.config_resolver import entity_overlay
        ovr = await entity_overlay("hr", entity_id) or {}
        if ovr:
            merged = deep_merge(merged, ovr)
        merged["entity_id"] = entity_id
        merged["entity_overrides"] = sorted(ovr.keys())
    return merged


async def org_unit_map(entity_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Map id -> unit (name/unit_type/parent) untuk resolusi nama dept/posisi."""
    ids = [e for e in (entity_ids or []) if e]
    if not ids:
        return {}
    units = await db.hr_org_units.find(
        {"entity_id": {"$in": ids}},
        {"_id": 0, "id": 1, "name": 1, "unit_type": 1, "parent_id": 1}).to_list(5000)
    return {u["id"]: u for u in units}


async def user_map(user_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Map id -> user (name/role/email) untuk karyawan yang punya akun login."""
    ids = [u for u in (user_ids or []) if u]
    if not ids:
        return {}
    users = await db.users.find(
        {"id": {"$in": ids}},
        {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1}).to_list(5000)
    return {u["id"]: u for u in users}


def enrich_employee(emp: Dict[str, Any], omap: Dict[str, Any],
                    umap: Dict[str, Any]) -> Dict[str, Any]:
    """Tambahkan field turunan: department_name, position_name, user_name/role, has_account."""
    out = dict(emp)
    dep = omap.get(out.get("department_id"))
    pos = omap.get(out.get("position_id"))
    out["department_name"] = dep["name"] if dep else ""
    out["position_name"] = pos["name"] if pos else ""
    usr = umap.get(out.get("user_id"))
    out["user_name"] = usr["name"] if usr else ""
    out["user_role"] = usr["role"] if usr else ""
    out["user_email"] = usr.get("email", "") if usr else ""
    out["has_account"] = bool(usr)
    return out


def build_org_tree(units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bentuk hierarki dari daftar unit (parent_id). Root = unit tanpa parent valid.

    Hasil tiap node: {...unit, children: [...]}. Stabil untuk Company > dept > position.
    """
    by_id: Dict[str, Dict[str, Any]] = {u["id"]: {**u, "children": []} for u in units}
    roots: List[Dict[str, Any]] = []
    for node in by_id.values():
        pid = node.get("parent_id")
        if pid and pid in by_id:
            by_id[pid]["children"].append(node)
        else:
            roots.append(node)
    # urutkan: department dulu lalu position, alfabetis nama
    def _sort(items: List[Dict[str, Any]]):
        items.sort(key=lambda x: (0 if x.get("unit_type") == "department" else 1,
                                  (x.get("name") or "").lower()))
        for it in items:
            _sort(it["children"])
    _sort(roots)
    return roots
