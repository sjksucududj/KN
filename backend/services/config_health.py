"""FASE G-0 — KESEHATAN KONFIGURASI: apakah setiap setting benar-benar tersambung?

Setiap entri registry WAJIB mencantumkan `consumers` (berkas kode yang membacanya).
Modul ini memverifikasi klaim tersebut secara nyata:

  OK       berkas consumer ADA dan benar-benar menyebut kunci itu
  STALE    berkas ADA tetapi TIDAK menyebut kunci  → klaim registry basi
  MISSING  berkas TIDAK ADA                        → referensi salah
  NOT_USED sengaja dinyatakan tidak dipakai (dengan alasan)

Dipakai oleh layar "Kesehatan Konfigurasi" (admin) dan invarian `INV-CFG-01`.
Gate menyeluruh (memindai SELURUH repo) tetap di `scripts/audit_config_wiring.py`.
"""
import os
import re
from typing import Any, Dict, List

import config_registry as registry

BACKEND = "/app/backend"
FRONTEND = "/app/frontend/src"
_CACHE: Dict[str, str] = {}


def _read(path: str) -> str:
    if path in _CACHE:
        return _CACHE[path]
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        text = ""
    _CACHE[path] = text
    return text


def _resolve_path(ref: str) -> str:
    """'services/x.py:fn' → /app/backend/services/x.py · 'App.js' → /app/frontend/src/App.js"""
    file_part = ref.split(":", 1)[0].strip()
    root = BACKEND if file_part.endswith(".py") else FRONTEND
    return os.path.join(root, file_part)


def _mentions(text: str, key: str) -> bool:
    """Apakah teks menyebut kunci ini (leaf, dot-path, atau nama variabel)?"""
    if not text:
        return False
    leaf = key.split(".")[-1]
    pats = [re.escape(key), r"[\"']%s[\"']" % re.escape(leaf), r"\.%s\b" % re.escape(leaf)]
    return any(re.search(p, text) for p in pats)


def check_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    key = entry["key"]
    ok, stale, missing = [], [], []
    for ref in entry["consumers"]:
        path = _resolve_path(ref)
        if not os.path.exists(path):
            missing.append(ref)
            continue
        (ok if _mentions(_read(path), key) else stale).append(ref)
    if entry["status"] == "not_used":
        status = "NOT_USED"
    elif missing:
        status = "MISSING"
    elif not ok:
        status = "STALE"
    else:
        status = "OK"
    return {
        "key": key, "label": entry["label"], "group": entry["group"],
        "registry_status": entry["status"], "not_used_reason": entry["not_used_reason"],
        "wiring_status": status, "risk": entry["risk"],
        "consumers_ok": ok, "consumers_stale": stale, "consumers_missing": missing,
        "consumer_count": len(entry["consumers"]),
    }


def report() -> Dict[str, Any]:
    _CACHE.clear()
    rows = [check_entry(e) for e in registry.all_entries()]
    summary: Dict[str, int] = {}
    for r in rows:
        summary[r["wiring_status"]] = summary.get(r["wiring_status"], 0) + 1
    per_group: Dict[str, Dict[str, int]] = {}
    for r in rows:
        g = per_group.setdefault(r["group"], {})
        g[r["wiring_status"]] = g.get(r["wiring_status"], 0) + 1
    broken = [r for r in rows if r["wiring_status"] in {"MISSING", "STALE"}]
    return {
        "total": len(rows),
        "summary": summary,
        "per_group": per_group,
        "healthy": not broken,
        "broken": broken,
        "rows": rows,
        "legend": {
            "OK": "Tersambung — kode pembacanya ada dan benar-benar memakai setting ini.",
            "STALE": "Referensi kode basi — berkas ada tetapi tidak lagi menyebut setting ini.",
            "MISSING": "Referensi kode salah — berkas tidak ditemukan.",
            "NOT_USED": "Sengaja tidak dipakai — lihat alasannya.",
        },
    }


def coverage() -> Dict[str, Any]:
    """Cakupan registry terhadap kunci yang benar-benar hidup di `system_settings`
    (dipakai POC/gate: memastikan tidak ada setting liar di luar registry)."""
    from config_registry import covers
    return {"registered": len(registry.all_entries()),
            "resolver": bool(covers("tax.ppn_rate"))}


def uncovered_leaves(leaves: List[str]) -> List[str]:
    """Kunci daun (dari audit) yang belum tercakup registry."""
    return [lk for lk in leaves if registry.covers(lk) is None]
