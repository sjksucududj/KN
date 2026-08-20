"""Customers router: CRUD + addresses + CRM-lite (KN_17)."""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID
from schemas import CustomerAddress, CustomerCreate, GenericPatch, PaymentProfile
from services.customer_service import (
    enrich_customer, scope_query, can_access_customer,
    normalize_sales_team, pic_of, resolve_team_names,
)
from entity_scope import entity_ctx, resolve_list_scope
from pagination import is_paged, get_page_params, build_search, merge_query, fetch_page, envelope, paginate_list
from request_context import active_entity_or

router = APIRouter(prefix="/api")


@router.get("/customers")
async def list_customers(request: Request, entity_id: str = None,
                         segment: str = None, credit_status: str = None,
                         assigned_sales_id: str = None, with_credit: bool = True) -> Any:
    actor = await require_permission(request, "customer", "view")
    ctx = await entity_ctx(request)
    base: Dict[str, Any] = {}
    if segment:
        base["segment"] = segment
    if assigned_sales_id:
        base["assigned_sales_id"] = assigned_sales_id
    base = resolve_list_scope("customers", base, ctx, entity_id)  # entity isolation
    query = scope_query(actor, base)  # row-level: sales -> own customers

    if is_paged(request):
        page, page_size, q, _sort = get_page_params(request)
        if q:
            query = merge_query(query, build_search(q, ["name", "code", "pic_name", "city", "phone", "email"]))
        # credit_status memfilter SETELAH enrichment → tak bisa paginasi murni di DB;
        # ambil superset (bounded) lalu paginasi in-memory agar total akurat.
        if with_credit and credit_status:
            rows = await db.customers.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
            enriched = []
            for c in rows:
                ec = await enrich_customer(c, with_credit=True)
                if ec.get("credit", {}).get("status") == credit_status:
                    enriched.append(ec)
            return paginate_list(enriched, page, page_size)
        items, total = await fetch_page(db.customers, query, page, page_size, sort_field="created_at", sort_dir=-1)
        if with_credit:
            items = [await enrich_customer(c, with_credit=True) for c in items]
        else:
            items = [safe_doc(c) for c in items]
        return envelope(items, total, page, page_size)

    rows = await db.customers.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    if with_credit:
        out = []
        for c in rows:
            ec = await enrich_customer(c, with_credit=True)
            if credit_status and ec.get("credit", {}).get("status") != credit_status:
                continue
            out.append(ec)
        return out
    return [safe_doc(c) for c in rows]


@router.post("/customers")
async def create_customer(payload: CustomerCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "create")
    # FASE E-7 (E7.7) — keputusan pemilik: "JANGAN membuat pelanggan untuk PT sendiri".
    # Badan usaha grup muncul sebagai PEMASOK bertipe "Entitas grup" di sisi pembeli.
    from services import group_partner_service as _grp
    await _grp.assert_new_customer_allowed(payload.name, getattr(payload, "npwp", "") or "")
    count = await db.customers.count_documents({}) + 1
    # assigned_sales: eksplisit > (sales pembuat jadi pemilik, S40) > kosong
    assigned_id = payload.assigned_sales_id
    if not assigned_id and actor.get("role") == "sales":
        assigned_id = actor["id"]
    assigned_name = ""
    if assigned_id:
        su = await db.users.find_one({"id": assigned_id, "role": "sales"}, {"_id": 0, "name": 1})
        assigned_name = (su or {}).get("name", "")
    # SALES REVAMP V2 — sales team (PIC + co-sales + split). PIC menentukan kepemilikan.
    sales_team = normalize_sales_team(payload.sales_team, assigned_id, assigned_name)
    if sales_team:
        pic = pic_of(sales_team)
        if pic and pic.get("sales_id"):
            assigned_id = pic["sales_id"]
            su2 = await db.users.find_one({"id": assigned_id}, {"_id": 0, "name": 1})
            assigned_name = (su2 or {}).get("name", "") or pic.get("name", "")
    sales_team = await resolve_team_names(sales_team)
    profile = (payload.payment_profile or PaymentProfile()).model_dump()
    contacts = [c.model_dump() for c in payload.contacts]
    if not contacts and payload.pic_name:
        contacts = [{"name": payload.pic_name, "role": "PIC", "phone": payload.phone,
                     "email": payload.email, "is_primary": True}]
    customer = {
        "id": new_id("cust"),
        "code": f"CUST-{count:04d}",
        "name": payload.name,
        "pic_name": payload.pic_name,
        "phone": payload.phone,
        "email": payload.email,
        "type": payload.type,
        "city": payload.city,
        "npwp": payload.npwp,
        "credit_limit": payload.credit_limit,
        "sales_pic": assigned_name or payload.sales_pic,
        # FASE E-1 (E1.10) — pelanggan milik badan usaha PEMBUATNYA. Dulu jatuh ke
        # DEFAULT_ENTITY_ID sehingga sales CV Kanda Suka membuat pelanggan yang
        # mendarat di PT Kain Suka Cita lalu hilang dari layarnya sendiri.
        "entity_id": payload.entity_id or active_entity_or(DEFAULT_ENTITY_ID),
        "enforce_single_dye_lot": bool(payload.enforce_single_dye_lot),  # P0-4
        "lot_policy": payload.lot_policy or "",                          # P0-4 / KN_15
        "allocation_policy": {},
        # --- CRM-lite (KN_17) ---
        "assigned_sales_id": assigned_id or "",
        "assigned_sales_name": assigned_name,
        "sales_team": sales_team,  # SALES REVAMP V2 — PIC + co-sales + split insentif
        "segment": payload.segment or payload.type or "Retail",
        "tags": payload.tags or [],
        "contacts": contacts,
        "payment_profile": profile,
        "customer_group_id": "",
        "status": "active",
        "created_by": actor["name"],
        "created_at": now_iso(),
        "addresses": [
            CustomerAddress(
                recipient_name=payload.pic_name, phone=payload.phone,
                city=payload.city, address=payload.address, is_primary=True
            ).model_dump()
        ],
    }
    await db.customers.insert_one(customer)
    await audit(actor["name"], "customer_created", "customer", customer["id"], customer)
    return await enrich_customer(customer, with_credit=True)


@router.patch("/customers/{customer_id}")
async def update_customer(customer_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "update")
    existing = safe_doc(await db.customers.find_one({"id": customer_id}, {"_id": 0}))
    if not existing:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    if not await can_access_customer(actor, existing):
        raise HTTPException(status_code=403, detail="Customer ini bukan milik Anda")
    allowed = ["name", "pic_name", "phone", "email", "type", "city", "status", "addresses",
               "npwp", "credit_limit", "sales_pic", "entity_id",
               "enforce_single_dye_lot", "lot_policy", "allocation_policy",
               # CRM-lite
               "segment", "tags", "contacts", "payment_profile", "customer_group_id",
               # SALES REVAMP V2 — tim sales (split insentif)
               "sales_team"]
    data = {k: v for k, v in payload.data.items() if k in allowed}
    # SALES REVAMP V2 — validasi tim sales; PIC tetap = pemilik (ubah owner via Reassign).
    if "sales_team" in data:
        aid = existing.get("assigned_sales_id", "")
        aname = existing.get("assigned_sales_name", "")
        team = normalize_sales_team(data.get("sales_team") or [], aid, aname)
        if aid and team:
            if not any(m["sales_id"] == aid for m in team):
                raise HTTPException(status_code=400, detail="Tim sales harus menyertakan pemilik (PIC) saat ini. Ubah pemilik via Reassign.")
            for m in team:
                m["role"] = "pic" if m["sales_id"] == aid else "co"
            total = round(sum(m["split_pct"] for m in team), 2)
            if abs(total - 100.0) > 0.01:
                raise HTTPException(status_code=400, detail=f"Total split insentif harus 100% (saat ini {total}%).")
        data["sales_team"] = await resolve_team_names(team)
    data["updated_at"] = now_iso()
    # FASE E-7 (E7.7) — pintu belakang yang ditutup: mengganti NAMA/NPWP pelanggan biasa
    # menjadi identitas badan usaha grup akan membuat penjualan antar-PT lolos dari
    # eliminasi margin tanpa pernah melewati layar Antar Entitas.
    if "name" in data or "npwp" in data:
        from services import group_partner_service as _grp
        await _grp.assert_new_customer_allowed(
            data.get("name", existing.get("name", "")),
            data.get("npwp", existing.get("npwp", "")))
    customer = await db.customers.find_one_and_update(
        {"id": customer_id}, {"$set": data},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    await audit(actor["name"], "customer_updated", "customer", customer_id, customer)
    return await enrich_customer(customer, with_credit=True)


@router.post("/customers/{customer_id}/addresses")
async def add_customer_address(customer_id: str, payload: CustomerAddress, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "update")
    address = payload.model_dump()
    customer = await db.customers.find_one_and_update(
        {"id": customer_id},
        {"$push": {"addresses": address}, "$set": {"updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    await audit(actor["name"], "customer_address_added", "customer", customer_id, address)
    return safe_doc(customer)
