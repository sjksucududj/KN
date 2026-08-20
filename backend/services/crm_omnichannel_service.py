"""CRM Omnichannel (MVP manual) — Lead pipeline + timeline interaksi.

Pencatatan manual (tanpa integrasi API eksternal). Dua koleksi:
- `crm_leads`      : prospek dengan pipeline stage (new→qualified→proposal→won→lost)
- `crm_interactions`: catatan interaksi multi-channel (phone/email/whatsapp/meeting/chat/sms/other)

Scoping per-entitas; row-level: sales hanya data miliknya (owner/creator).
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID

STAGES = ["new", "qualified", "proposal", "won", "lost"]
STAGE_LABELS = {
    "new": "Baru", "qualified": "Kualifikasi", "proposal": "Penawaran",
    "won": "Menang", "lost": "Kalah",
}
CHANNELS = ["phone", "email", "whatsapp", "meeting", "chat", "sms", "other"]


# ═══════════════════════════════════════════════════════════════════════════
#  LEADS
# ═══════════════════════════════════════════════════════════════════════════

async def list_leads(scope: Dict[str, Any], stage: Optional[str] = None,
                     owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
    q = dict(scope)
    if stage:
        q["stage"] = stage
    if owner_id:
        q["owner_id"] = owner_id
    return await db.crm_leads.find(q, {"_id": 0}).sort("updated_at", -1).to_list(1000)


async def board(scope: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db.crm_leads.find(scope, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    columns = []
    for s in STAGES:
        items = [r for r in rows if r.get("stage") == s]
        columns.append({
            "stage": s,
            "label": STAGE_LABELS[s],
            "count": len(items),
            "total_value": round(sum(float(r.get("est_value", 0) or 0) for r in items), 2),
            "leads": items,
        })
    return {"columns": columns, "total": len(rows)}


async def pipeline_stats(scope: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db.crm_leads.find(scope, {"_id": 0}).to_list(5000)
    by_stage: Dict[str, Any] = {}
    for s in STAGES:
        items = [r for r in rows if r.get("stage") == s]
        by_stage[s] = {
            "count": len(items),
            "value": round(sum(float(r.get("est_value", 0) or 0) for r in items), 2),
        }
    won = by_stage["won"]["count"]
    lost = by_stage["lost"]["count"]
    decided = won + lost
    open_stages = ["new", "qualified", "proposal"]
    return {
        "by_stage": by_stage,
        "win_rate": round(won / decided * 100, 1) if decided > 0 else 0.0,
        "open_count": sum(by_stage[s]["count"] for s in open_stages),
        "open_value": round(sum(by_stage[s]["value"] for s in open_stages), 2),
        "won_value": by_stage["won"]["value"],
        "total": len(rows),
    }


async def create_lead(data: Dict[str, Any], actor: Dict[str, Any], entity_id: str) -> Dict[str, Any]:
    owner_id = data.get("owner_id") or actor["id"]
    owner_name = (data.get("owner_name") or "").strip()
    if owner_id and not owner_name:
        u = await db.users.find_one({"id": owner_id}, {"_id": 0, "name": 1})
        owner_name = (u or {}).get("name", actor.get("name", ""))
    stage = data.get("stage") if data.get("stage") in STAGES else "new"
    doc = {
        "id": new_id("lead"),
        "entity_id": entity_id,
        "name": (data.get("name") or "").strip(),
        "company": (data.get("company") or "").strip(),
        "phone": (data.get("phone") or "").strip(),
        "email": (data.get("email") or "").strip(),
        "source": data.get("source") or "other",
        "stage": stage,
        "est_value": float(data.get("est_value") or 0),
        "owner_id": owner_id,
        "owner_name": owner_name,
        "notes": (data.get("notes") or "").strip(),
        "customer_id": None,
        "lost_reason": None,
        "created_by": actor.get("name", "system"),
        "created_by_id": actor["id"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "stage_changed_at": now_iso(),
    }
    await db.crm_leads.insert_one(dict(doc))
    return safe_doc(doc)


async def get_lead(lead_id: str) -> Optional[Dict[str, Any]]:
    return await db.crm_leads.find_one({"id": lead_id}, {"_id": 0})


async def update_lead(lead_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = await db.crm_leads.find_one({"id": lead_id}, {"_id": 0})
    if not existing:
        return None
    allowed = ["name", "company", "phone", "email", "source", "est_value",
               "owner_id", "owner_name", "notes", "stage", "lost_reason"]
    upd: Dict[str, Any] = {}
    for k in allowed:
        if k in data and data[k] is not None:
            upd[k] = data[k]
    if "est_value" in upd:
        upd["est_value"] = float(upd["est_value"] or 0)
    if "stage" in upd:
        if upd["stage"] not in STAGES:
            raise ValueError("stage tidak valid")
        if upd["stage"] != existing.get("stage"):
            upd["stage_changed_at"] = now_iso()
    if upd.get("owner_id") and not upd.get("owner_name"):
        u = await db.users.find_one({"id": upd["owner_id"]}, {"_id": 0, "name": 1})
        upd["owner_name"] = (u or {}).get("name", "")
    upd["updated_at"] = now_iso()
    await db.crm_leads.update_one({"id": lead_id}, {"$set": upd})
    return safe_doc(await db.crm_leads.find_one({"id": lead_id}, {"_id": 0}))


async def delete_lead(lead_id: str) -> bool:
    r = await db.crm_leads.delete_one({"id": lead_id})
    return r.deleted_count > 0


async def convert_lead(lead_id: str, actor: Dict[str, Any],
                       existing_customer_id: Optional[str] = None):
    lead = await db.crm_leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        return None, "Lead tidak ditemukan"
    if lead.get("customer_id"):
        return None, "Lead sudah dikonversi ke pelanggan."
    if existing_customer_id:
        cust = await db.customers.find_one({"id": existing_customer_id}, {"_id": 0})
        if not cust:
            return None, "Pelanggan tujuan tidak ditemukan."
        customer_id = existing_customer_id
    else:
        count = await db.customers.count_documents({}) + 1
        customer = {
            "id": new_id("cust"),
            "code": f"CUST-{count:04d}",
            "name": lead.get("company") or lead.get("name") or "Pelanggan Baru",
            "pic_name": lead.get("name", ""),
            "phone": lead.get("phone", ""),
            "email": lead.get("email", ""),
            "type": "umum",
            "city": "",
            "entity_id": lead.get("entity_id", DEFAULT_ENTITY_ID),
            "status": "active",
            "credit_limit": 0,
            "assigned_sales_id": lead.get("owner_id", ""),
            "assigned_sales_name": lead.get("owner_name", ""),
            "sales_pic": lead.get("owner_name", ""),
            "addresses": [],
            "contacts": [],
            "source_lead_id": lead_id,
            "created_by": actor.get("name", "system"),
            "created_at": now_iso(),
        }
        await db.customers.insert_one(dict(customer))
        customer_id = customer["id"]
    await db.crm_leads.update_one(
        {"id": lead_id},
        {"$set": {"customer_id": customer_id, "stage": "won",
                  "updated_at": now_iso(), "stage_changed_at": now_iso()}},
    )
    # tautkan interaksi lead ini ke customer
    await db.crm_interactions.update_many({"lead_id": lead_id}, {"$set": {"customer_id": customer_id}})
    updated = safe_doc(await db.crm_leads.find_one({"id": lead_id}, {"_id": 0}))
    return {"lead": updated, "customer_id": customer_id}, None


# ═══════════════════════════════════════════════════════════════════════════
#  INTERACTIONS
# ═══════════════════════════════════════════════════════════════════════════

async def list_interactions(scope: Dict[str, Any], customer_id: Optional[str] = None,
                            lead_id: Optional[str] = None, channel: Optional[str] = None,
                            limit: int = 300) -> List[Dict[str, Any]]:
    q = dict(scope)
    if customer_id:
        q["customer_id"] = customer_id
    if lead_id:
        q["lead_id"] = lead_id
    if channel:
        q["channel"] = channel
    return await db.crm_interactions.find(q, {"_id": 0}).sort("occurred_at", -1).to_list(limit)


async def create_interaction(data: Dict[str, Any], actor: Dict[str, Any], entity_id: str) -> Dict[str, Any]:
    channel = data.get("channel") if data.get("channel") in CHANNELS else "other"
    direction = data.get("direction") if data.get("direction") in ("inbound", "outbound") else "outbound"
    customer_id = data.get("customer_id") or None
    customer_name = ""
    if customer_id:
        c = await db.customers.find_one({"id": customer_id}, {"_id": 0, "name": 1})
        customer_name = (c or {}).get("name", "")
    doc = {
        "id": new_id("intx"),
        "entity_id": entity_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "lead_id": data.get("lead_id") or None,
        "channel": channel,
        "direction": direction,
        "subject": (data.get("subject") or "").strip(),
        "notes": (data.get("notes") or "").strip(),
        "occurred_at": data.get("occurred_at") or now_iso(),
        "follow_up_date": data.get("follow_up_date") or None,
        "created_by": actor.get("name", "system"),
        "created_by_id": actor["id"],
        "created_at": now_iso(),
    }
    await db.crm_interactions.insert_one(dict(doc))
    return safe_doc(doc)


async def get_interaction(intx_id: str) -> Optional[Dict[str, Any]]:
    return await db.crm_interactions.find_one({"id": intx_id}, {"_id": 0})


async def delete_interaction(intx_id: str) -> bool:
    r = await db.crm_interactions.delete_one({"id": intx_id})
    return r.deleted_count > 0
