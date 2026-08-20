"""PS-20 (D-14) — **Penegakan matriks persetujuan divisi** + antrean "Persetujuan Saya".

Sebelum fase ini matriks approver PS-17 hanya RUJUKAN tampilan. Modul ini menjadikannya
MENGIKAT dengan satu jalur keputusan untuk empat tahap (design_acc, sample_acc,
po_custom, purchase_request) sehingga tidak ada dua sumber kebenaran:

  • `evaluate()`  — murni: boleh/tidak + alasan (dipakai UI untuk menonaktifkan tombol).
  • `guard()`     — sama dengan evaluate, tetapi MELEMPAR 403 bila mode `enforce`.
  • `record()`    — tulis jejak ke koleksi `approval_matrix_log` + `audit_logs`.
  • `my_queue()`  — antrean lintas-tahap: apa yang menunggu keputusan SAYA.

Kebijakan (Pusat Pengaturan → Persetujuan & Ambang; lihat `config_catalog_approval_matrix.py`):
  approval.matrix_enforcement   off | warn | enforce      (bawaan enforce)
  approval.matrix_scope         all_pending | new_only     (bawaan all_pending)
  approval.matrix_effective_from  TTTT-BB-HH               (dipakai bila new_only)
  approval.matrix_sod           bool                       (bawaan aktif)
  approval.po_custom_direksi_min money                      (ambang tingkat 2 Direksi)

Catatan: "Direksi" = peran **admin** (keputusan pemilik) — tidak ada peran baru.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from config_divisions import (APPROVER_MATRIX, DIREKSI_MIN_KEY, STAGE_BY_ID,
                              role_label, roles_label, stage_label)
from core_utils import new_id, now_iso, safe_doc
from db import db
from services.config_resolver import value_of

LOG_COLL = "approval_matrix_log"

K_MODE = "approval.matrix_enforcement"
K_SCOPE = "approval.matrix_scope"
K_FROM = "approval.matrix_effective_from"
K_SOD = "approval.matrix_sod"

MODES = ("off", "warn", "enforce")
SCOPES = ("all_pending", "new_only")


# ─── Kebijakan ──────────────────────────────────────────────────────
def _as_bool(v: Any, default: bool = True) -> bool:
    if isinstance(v, bool):
        return v
    if v is None or v == "":
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on", "aktif")


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


async def settings(entity_id: str = "") -> Dict[str, Any]:
    """Kebijakan penegakan yang BERLAKU (berlapis global → entitas)."""
    ctx = {"entity_id": entity_id or ""}
    mode = str(await value_of(K_MODE, ctx) or "enforce").strip().lower()
    scope = str(await value_of(K_SCOPE, ctx) or "all_pending").strip().lower()
    eff = str(await value_of(K_FROM, ctx) or "").strip()[:10]
    sod = _as_bool(await value_of(K_SOD, ctx), True)
    direksi_min = _as_float(await value_of(DIREKSI_MIN_KEY, ctx), 0.0)
    if mode not in MODES:
        mode = "enforce"
    if scope not in SCOPES:
        scope = "all_pending"
    return {
        "mode": mode, "scope": scope, "effective_from": eff, "sod": sod,
        "po_custom_direksi_min": direksi_min,
        "mode_label": {"off": "Nonaktif (rujukan saja)", "warn": "Peringatkan saja",
                       "enforce": "Ditegakkan"}[mode],
        "scope_label": ("Semua dokumen (termasuk yang menunggu)"
                        if scope == "all_pending" else "Hanya dokumen baru"),
    }


# ─── Tingkat persetujuan per tahap ─────────────────────────────────────
def levels_for(stage: str, amount: float = 0.0, direksi_min: float = 0.0) -> List[Dict[str, Any]]:
    """Tingkat yang BERLAKU untuk satu dokumen (tingkat ber-ambang ikut nilai dokumen)."""
    st = STAGE_BY_ID.get(stage) or {}
    out: List[Dict[str, Any]] = []
    for lv in st.get("levels") or []:
        if lv.get("min_amount_key") == DIREKSI_MIN_KEY:
            if _as_float(amount) < _as_float(direksi_min):
                continue
        out.append({"level": len(out) + 1, "label": lv.get("label") or "Persetujuan",
                    "roles": list(lv.get("roles") or []),
                    "roles_label": roles_label(list(lv.get("roles") or [])),
                    "min_amount": (_as_float(direksi_min)
                                   if lv.get("min_amount_key") == DIREKSI_MIN_KEY else 0.0)})
    if not out:  # jaring aman: selalu ada minimal satu tingkat
        out = [{"level": 1, "label": "Persetujuan", "roles": ["manager", "admin"],
                "roles_label": roles_label(["manager", "admin"]), "min_amount": 0.0}]
    return out


def build_chain(levels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"level": lv["level"], "label": lv["label"], "roles": lv["roles"],
             "status": "pending", "approved_by": "", "approved_by_id": "",
             "approved_at": ""} for lv in levels]


def pending_level(chain: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for lv in chain or []:
        if lv.get("status") != "approved":
            return lv
    return None


def chain_summary(chain: List[Dict[str, Any]]) -> Dict[str, Any]:
    done = sum(1 for lv in (chain or []) if lv.get("status") == "approved")
    cur = pending_level(chain or [])
    return {"levels_total": len(chain or []), "levels_done": done,
            "current_level": (cur or {}).get("level", 0),
            "current_label": (cur or {}).get("label", ""),
            "current_roles": list((cur or {}).get("roles") or []),
            "complete": cur is None}


# ─── Pemisahan tugas (SoD) ───────────────────────────────────────────
_REQUESTER_FIELDS = ("created_by", "created_by_id", "created_by_email", "submitted_by",
                     "submitted_by_id", "requested_by", "requested_by_id", "requester")


def is_requester(doc: Dict[str, Any], actor: Dict[str, Any]) -> bool:
    """True bila `actor` adalah pengaju/pembuat dokumen (cocok id, nama, atau email)."""
    mine = {str((actor or {}).get(k) or "").strip().lower()
            for k in ("id", "name", "email")} - {""}
    if not mine:
        return False
    theirs = set()
    for f in _REQUESTER_FIELDS:
        v = (doc or {}).get(f)
        if isinstance(v, str) and v.strip():
            theirs.add(v.strip().lower())
    # Pesanan khusus menyimpan pembuat di status_history[0].user (email)
    hist = (doc or {}).get("status_history") or []
    if hist and isinstance(hist[0], dict) and hist[0].get("user"):
        theirs.add(str(hist[0]["user"]).strip().lower())
    return bool(mine & theirs)


# ─── Retroaktif (dokumen lama vs baru) ──────────────────────────────────
def _doc_date(doc: Dict[str, Any]) -> str:
    for f in ("created_at", "submitted_at", "updated_at"):
        v = (doc or {}).get(f)
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
        if isinstance(v, datetime):
            return v.astimezone(timezone.utc).date().isoformat()
    return ""


def is_legacy_doc(doc: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """Dokumen dianggap LAMA (dikecualikan) hanya bila kebijakan `new_only`."""
    if cfg.get("scope") != "new_only":
        return False
    eff = (cfg.get("effective_from") or "")[:10] or date.today().isoformat()
    dd = _doc_date(doc)
    if not dd:
        return True  # tanpa tanggal = data lama
    return dd < eff


# Alias lama (kompatibilitas internal)
_is_legacy_doc = is_legacy_doc


async def sod_blocked(doc: Dict[str, Any], actor: Dict[str, Any],
                      entity_id: str = "") -> bool:
    """Pemisahan tugas SATU SUMBER: dipakai juga oleh layanan lama (mis. PR) supaya
    aturan SoD mereka ikut kebijakan Pusat Pengaturan, bukan hardcode."""
    cfg = await settings(entity_id or (doc or {}).get("entity_id", ""))
    if cfg.get("mode") == "off" or not cfg.get("sod"):
        return False
    if is_legacy_doc(doc or {}, cfg):
        return False
    return is_requester(doc or {}, actor or {})


# ─── Inti keputusan ───────────────────────────────────────────────
def evaluate(stage: str, actor: Dict[str, Any], doc: Dict[str, Any],
             cfg: Dict[str, Any], amount: Optional[float] = None,
             level: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """MURNI (tanpa I/O): boleh atau tidak seseorang memutuskan tahap ini sekarang."""
    st = STAGE_BY_ID.get(stage) or {}
    amt = _as_float(amount if amount is not None else (doc or {}).get("total_amount"), 0.0)
    lv_all = levels_for(stage, amt, cfg.get("po_custom_direksi_min", 0.0))
    chain = (doc or {}).get("approval_chain") or []
    cur = level or pending_level(chain) or lv_all[0]
    roles = list(cur.get("roles") or [])
    role = str((actor or {}).get("role") or "").strip().lower()

    res: Dict[str, Any] = {
        "stage": stage, "stage_label": st.get("label") or stage_label(stage),
        "mode": cfg.get("mode"), "scope": cfg.get("scope"),
        "level": cur.get("level", 1), "level_label": cur.get("label", ""),
        "roles": roles, "roles_label": roles_label(roles),
        "levels": lv_all, "levels_total": len(lv_all),
        "amount": amt, "enforced": True, "allowed": True,
        "reasons": [], "skip_reason": "",
    }

    if cfg.get("mode") == "off":
        res["enforced"] = False
        res["skip_reason"] = "Penegakan matriks dinonaktifkan di Pusat Pengaturan."
        return res
    if _is_legacy_doc(doc or {}, cfg):
        res["enforced"] = False
        res["skip_reason"] = ("Dokumen lama — kebijakan 'Hanya dokumen baru' "
                              f"(berlaku sejak {cfg.get('effective_from') or date.today().isoformat()}).")
        return res

    if roles and role not in roles:
        res["allowed"] = False
        res["reasons"].append({
            "code": "role",
            "message": (f"Tahap “{res['stage_label']}” tingkat {res['level']} "
                        f"({cur.get('label', '')}) hanya boleh diputuskan oleh "
                        f"{roles_label(roles)} sesuai matriks persetujuan divisi. "
                        f"Peran Anda: {role_label(role)}.")})
    if cfg.get("sod") and is_requester(doc or {}, actor or {}):
        res["allowed"] = False
        res["reasons"].append({
            "code": "sod",
            "message": ("Pemisahan tugas: Anda yang mengajukan dokumen "
                        f"{(doc or {}).get('number', '')} sehingga tidak boleh "
                        "menyetujuinya sendiri. Minta approver lain — aturan ini bisa "
                        "diubah di Pusat Pengaturan → Persetujuan & Ambang.")})
    res["blocked"] = bool(not res["allowed"] and cfg.get("mode") == "enforce")
    return res


async def guard(stage: str, actor: Dict[str, Any], doc: Dict[str, Any],
                entity_id: str = "", amount: Optional[float] = None,
                level: Optional[Dict[str, Any]] = None,
                action: str = "approve") -> Dict[str, Any]:
    """Penjaga endpoint: 403 bila tidak berhak (mode `enforce`). Pelanggaran dicatat."""
    cfg = await settings(entity_id)
    res = evaluate(stage, actor, doc, cfg, amount=amount, level=level)
    res["config"] = cfg
    if not res.get("allowed"):
        detail = " ".join(r["message"] for r in res.get("reasons") or [])
        await record(stage=stage, action=action, actor=actor, doc=doc, entity_id=entity_id,
                     level=res.get("level", 1), level_label=res.get("level_label", ""),
                     outcome=("ditolak sistem" if cfg.get("mode") == "enforce"
                              else "pelanggaran dicatat (mode peringatan)"),
                     note=detail, enforced=res.get("enforced", True),
                     violation=True, reasons=res.get("reasons") or [])
        if cfg.get("mode") == "enforce":
            raise HTTPException(status_code=403, detail=detail)
    return res


# ─── Jejak persetujuan ────────────────────────────────────────────
async def record(*, stage: str, action: str, actor: Dict[str, Any], doc: Dict[str, Any],
                 entity_id: str = "", level: int = 1, level_label: str = "",
                 outcome: str = "", note: str = "", enforced: bool = True,
                 violation: bool = False,
                 reasons: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    st = STAGE_BY_ID.get(stage) or {}
    # FASE E-7 — stempel entitas WAJIB ada: jejak tanpa entitas akan terbaca semua PT
    # (dan membuat gate kepatuhan memerah karena dokumen ter-scope tanpa field entitas).
    # Urutan: yang dikirim pemanggil → dokumennya → badan usaha aktif pelaku.
    _ent = entity_id or (doc or {}).get("entity_id") or ""
    if not _ent:
        try:
            from request_context import get_active_entity
            _ent = get_active_entity() or ""
        except Exception:  # noqa: BLE001 — jangan pernah menggagalkan pencatatan jejak
            _ent = ""
    entry = {
        "id": new_id("amlog"),
        "entity_id": _ent,
        "stage": stage, "stage_label": st.get("label") or stage_label(stage),
        "doc_type": st.get("doc_type") or "", "doc_label": st.get("doc_label") or "",
        "doc_id": (doc or {}).get("id") or "", "doc_number": (doc or {}).get("number") or "",
        "amount": _as_float((doc or {}).get("total_amount")
                            or (doc or {}).get("total_est_amount")
                            or (doc or {}).get("target_price"), 0.0),
        "action": action, "level": int(level or 1), "level_label": level_label,
        "actor_id": (actor or {}).get("id", ""), "actor_name": (actor or {}).get("name", ""),
        "actor_role": (actor or {}).get("role", ""),
        "requester": (doc or {}).get("created_by") or (doc or {}).get("submitted_by") or "",
        "outcome": outcome, "note": note[:600], "enforced": bool(enforced),
        "violation": bool(violation),
        "reasons": [r.get("code", "") for r in (reasons or [])],
        "created_at": now_iso(),
    }
    await db[LOG_COLL].insert_one(dict(entry))
    try:  # jejak ganda di audit_logs supaya muncul di Master Data & Audit
        from dependencies import audit
        await audit(entry["actor_name"], f"approval_matrix_{action}",
                    st.get("collection") or "approval_matrix", entry["doc_id"],
                    {"stage": stage, "level": entry["level"], "outcome": outcome,
                     "violation": entry["violation"]}, reason=note[:400])
    except Exception:  # noqa: BLE001 — jejak utama sudah tersimpan
        pass
    return safe_doc(entry)


async def log(entity_id: str = "", stage: str = "", limit: int = 50,
              only_violations: bool = False) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    if stage:
        q["stage"] = stage
    if only_violations:
        q["violation"] = True
    rows = await db[LOG_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(
        max(1, min(int(limit or 50), 300)))
    return [safe_doc(r) for r in rows]


# ─── Antrean "Persetujuan Saya" ──────────────────────────────────────
def _days_waiting(iso: str) -> int:
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds() // 86400))
    except Exception:  # noqa: BLE001
        return 0


def _scope(entity_id: str) -> Dict[str, Any]:
    return {} if (not entity_id or entity_id == "all") else {"entity_id": entity_id}


async def my_queue(actor: Dict[str, Any], entity_id: str = "",
                   stage: str = "") -> Dict[str, Any]:
    """Semua dokumen yang MENUNGGU keputusan, lintas 4 tahap matriks.

    Setiap baris membawa `can_decide` + `block_reasons` supaya UI bisa menonaktifkan
    tombol dengan alasan yang jujur (bukan menyembunyikan pekerjaan).
    """
    cfg = await settings(entity_id)
    base = _scope(entity_id)
    items: List[Dict[str, Any]] = []

    async def _add(stage_id: str, doc: Dict[str, Any], *, title: str, amount: float,
                   requester: str, since: str, ready: bool = True,
                   ready_note: str = "", extra: Optional[Dict[str, Any]] = None) -> None:
        st = STAGE_BY_ID[stage_id]
        ev = evaluate(stage_id, actor, doc, cfg, amount=amount)
        reasons = list(ev.get("reasons") or [])
        can = bool(ev.get("allowed")) or not ev.get("enforced", True)
        if cfg.get("mode") == "warn" and not ev.get("allowed"):
            can = True  # mode peringatan: tetap boleh, pelanggaran dicatat
        if not ready:
            can = False
            reasons = reasons + [{"code": "not_ready", "message": ready_note}]
        items.append({
            "stage": stage_id, "stage_label": st["label"], "doc_type": st["doc_type"],
            "doc_label": st["doc_label"], "view": st["view"],
            "id": doc.get("id", ""), "number": doc.get("number", ""), "title": title,
            "amount": _as_float(amount), "requester": requester,
            "created_at": since, "days_waiting": _days_waiting(since),
            "entity_id": doc.get("entity_id", ""),
            "level": ev.get("level", 1), "level_label": ev.get("level_label", ""),
            "levels_total": ev.get("levels_total", 1),
            "required_roles": ev.get("roles", []),
            "required_roles_label": ev.get("roles_label", ""),
            "approval_chain": doc.get("approval_chain") or [],
            "ready": bool(ready),
            "can_decide": can, "block_reasons": [r["message"] for r in reasons],
            "enforced": ev.get("enforced", True), "skip_reason": ev.get("skip_reason", ""),
            **(extra or {}),
        })

    want = (stage or "").strip()

    if not want or want == "design_acc":
        for d in await db.md_specs.find({**base, "status": "review"}, {"_id": 0}
                                        ).sort("created_at", -1).to_list(200):
            await _add("design_acc", d, title=d.get("title") or "(tanpa judul)",
                       amount=_as_float(d.get("target_price")),
                       requester=d.get("submitted_by") or d.get("created_by") or "",
                       since=d.get("submitted_at") or d.get("created_at") or "")

    if not want or want == "sample_acc":
        cur = db.md_samples.find({**base, "status": {"$in": ["in_progress", "assessed"]}},
                                 {"_id": 0}).sort("created_at", -1)
        for d in await cur.to_list(200):
            if (d.get("decision") or {}).get("supplier_id"):
                continue
            rounds = d.get("rounds") or []
            ready = any(r.get("result") == "acc" for r in rounds)
            await _add("sample_acc", d, title=d.get("title") or d.get("spec_number") or "",
                       amount=_as_float(d.get("cost_total")),
                       requester=d.get("created_by") or "",
                       since=d.get("created_at") or "", ready=ready,
                       ready_note=("Belum ada round yang ACC — nilai dulu hasil sample "
                                   "sebelum memilih pemenang."),
                       extra={"rounds": len(rounds),
                              "sample_type": d.get("sample_type", "")})

    if not want or want == "purchase_request":
        for d in await db.purchase_requisitions.find(
                {**base, "status": "pending_approval"}, {"_id": 0}
        ).sort("created_at", -1).to_list(200):
            await _add("purchase_request", d,
                       title=(d.get("reason") or f"{len(d.get('items') or [])} item kebutuhan"),
                       amount=_as_float(d.get("total_est_amount")),
                       requester=d.get("created_by") or "",
                       since=d.get("created_at") or "",
                       extra={"warehouse_name": d.get("warehouse_name", ""),
                              "lines": len(d.get("items") or [])})

    if not want or want == "po_custom":
        for d in await db.special_orders.find({**base, "status": "pending_approval"},
                                              {"_id": 0}
                                              ).sort("created_at", -1).to_list(200):
            ci = d.get("custom_item") or {}
            await _add("po_custom", d,
                       title=ci.get("description") or "Pesanan khusus",
                       amount=_as_float(d.get("total_amount")),
                       requester=d.get("created_by") or "",
                       since=d.get("created_at") or "",
                       extra={"customer_name": d.get("customer_name", ""),
                              "quantity": _as_float(ci.get("quantity")),
                              "unit": ci.get("unit", "")})

    items.sort(key=lambda x: (not x["can_decide"], -x["days_waiting"], x["stage"]))
    counts = {s["stage"]: 0 for s in APPROVER_MATRIX}
    actionable = 0
    for it in items:
        counts[it["stage"]] = counts.get(it["stage"], 0) + 1
        if it["can_decide"]:
            actionable += 1
    return {
        "items": items, "total": len(items), "actionable": actionable,
        "counts": counts, "config": cfg,
        "stages": [{"stage": s["stage"], "label": s["label"], "doc_label": s["doc_label"],
                    "view": s["view"], "count": counts.get(s["stage"], 0)}
                   for s in APPROVER_MATRIX],
        "actor": {"name": (actor or {}).get("name", ""), "role": (actor or {}).get("role", ""),
                  "role_label": role_label((actor or {}).get("role", ""))},
    }


async def matrix(entity_id: str = "") -> Dict[str, Any]:
    """Matriks + kebijakan penegakan (untuk layar Divisi & Persetujuan / Pusat Persetujuan)."""
    cfg = await settings(entity_id)
    stages: List[Dict[str, Any]] = []
    for s in APPROVER_MATRIX:
        lv = levels_for(s["stage"], amount=cfg["po_custom_direksi_min"],
                        direksi_min=cfg["po_custom_direksi_min"])
        stages.append({**{k: s[k] for k in ("stage", "label", "approvers", "note",
                                            "doc_type", "doc_label", "view")},
                       "levels": lv,
                       "binding": cfg["mode"] != "off",
                       "endpoints": _ENDPOINTS.get(s["stage"], [])})
    return {"stages": stages, "config": cfg,
            "approver_matrix": APPROVER_MATRIX}


_ENDPOINTS = {
    "design_acc": ["POST /api/rnd/specs/{id}/approve", "POST /api/rnd/specs/{id}/reject"],
    "sample_acc": ["POST /api/rnd/samples/{id}/decide"],
    "po_custom": ["POST /api/special-orders/{id}/approve",
                  "POST /api/special-orders/{id}/reject"],
    "purchase_request": ["POST /api/purchase-requisitions/{id}/approve",
                         "POST /api/purchase-requisitions/{id}/reject"],
}


# ─── Bantuan khusus PO Custom (2 tingkat) ─────────────────────────────────
async def special_order_chain(doc: Dict[str, Any], entity_id: str = "") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Rantai persetujuan pesanan khusus (dibuat sekali, lalu dipakai apa adanya)."""
    cfg = await settings(entity_id or (doc or {}).get("entity_id", ""))
    lv = levels_for("po_custom", _as_float((doc or {}).get("total_amount")),
                    cfg["po_custom_direksi_min"])
    chain = (doc or {}).get("approval_chain") or build_chain(lv)
    return chain, cfg
