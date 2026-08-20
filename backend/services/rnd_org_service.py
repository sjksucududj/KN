"""PS-17 — Layanan Organisasi R&D (divisi + anggota).

Realita data: 'aktor' R&D (desainer) sering BUKAN akun user — mereka muncul sebagai
NAMA pada round sample. Maka penempatan divisi disimpan **per-nama** di koleksi
`rnd_person_divisions` (kunci: entity_id + name). Bila nama itu kebetulan seorang user,
nilainya juga dicerminkan ke `users.division` supaya konsisten. Ini menjaga cakupan
tetap R&D-only tanpa memaksa setiap desainer jadi user.
"""
from typing import Any, Dict, List, Optional

from core_utils import now_iso
from db import db
from config_divisions import (APPROVER_MATRIX, DIVISION_IDS, RND_DIVISIONS,
                              division_name)
from services import rnd_kpi_service as kpi

COLL = "rnd_person_divisions"


async def division_map(entity_id: str) -> Dict[str, str]:
    """name -> division_id untuk satu entity (fallback ke users.division)."""
    m: Dict[str, str] = {}
    async for r in db[COLL].find({"entity_id": entity_id},
                                 {"_id": 0, "name": 1, "division": 1}):
        if r.get("division"):
            m[r["name"]] = r["division"]
    async for u in db.users.find({}, {"_id": 0, "name": 1, "division": 1}):
        if u.get("division") and u["name"] not in m:
            m[u["name"]] = u["division"]
    return m


async def list_divisions(entity_id: str) -> Dict[str, Any]:
    amap = await division_map(entity_id)
    counts: Dict[str, int] = {}
    for div in amap.values():
        if div:
            counts[div] = counts.get(div, 0) + 1
    divisions = [{**d, "member_count": counts.get(d["id"], 0)} for d in RND_DIVISIONS]
    return {
        "divisions": divisions,
        "approver_matrix": APPROVER_MATRIX,
        "assigned": sum(counts.values()),
    }


async def list_members(scope: Dict[str, Any], entity_id: str) -> List[Dict[str, Any]]:
    """Gabungan orang R&D: nama desainer (dari KPI) + user sistem, dengan divisinya."""
    rep = await kpi.designer_kpi(dict(scope or {}), period="all", entity_id=entity_id)
    designer_names = [it["designer"] for it in rep.get("items", [])]
    users = await db.users.find(
        {}, {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1}).to_list(200)
    amap = await division_map(entity_id)

    people: Dict[str, Dict[str, Any]] = {}
    for nm in designer_names:
        people[nm] = {"name": nm, "role": "designer", "source": "designer", "user_id": ""}
    for u in users:
        nm = u.get("name") or ""
        if not nm:
            continue
        if nm in people:
            people[nm]["source"] = "both"
            people[nm]["role"] = u.get("role") or people[nm]["role"]
            people[nm]["user_id"] = u.get("id") or ""
            people[nm]["email"] = u.get("email") or ""
        else:
            people[nm] = {"name": nm, "role": u.get("role") or "",
                          "source": "user", "user_id": u.get("id") or "",
                          "email": u.get("email") or ""}
    out: List[Dict[str, Any]] = []
    for nm, info in people.items():
        div = amap.get(nm, "")
        out.append({**info, "division": div, "division_name": division_name(div)})
    out.sort(key=lambda x: (x["division"] == "", x["division"], x["name"]))
    return out


async def set_member_division(entity_id: str, name: str, division: str,
                              actor_name: str = "") -> Dict[str, Any]:
    name = (name or "").strip()
    division = (division or "").strip()
    if not name:
        raise ValueError("Nama orang wajib diisi.")
    if division and division not in DIVISION_IDS:
        raise ValueError("Divisi tidak dikenal.")
    await db[COLL].update_one(
        {"entity_id": entity_id, "name": name},
        {"$set": {"entity_id": entity_id, "name": name, "division": division,
                  "updated_at": now_iso(), "updated_by": actor_name}}, upsert=True)
    # Cermin ke akun user bila namanya seorang user (1 user = 1 divisi).
    u = await db.users.find_one({"name": name}, {"_id": 0, "id": 1})
    if u:
        await db.users.update_one({"id": u["id"]}, {"$set": {"division": division}})
    return {"name": name, "division": division, "division_name": division_name(division)}
