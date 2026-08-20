"""Customer/CRM service (KN_17 CRM-lite).

Derivasi kredit (AR/overdue/status), Customer 360, dan row-level scoping.
SSOT tunggal `customers`. KPI & kredit = DERIVED dari sales_orders/payments/price_approvals.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from db import db
from core_utils import safe_doc, DEFAULT_ENTITY_ID, rupiah

# Ambang kontrol kredit (KN_17 §5.2)
WARNING_RATIO = 0.8          # ar >= 80% limit -> warning
OVERDUE_BLOCK_DAYS = 14      # overdue terlama > 14 hari -> blocked (overdue ringan <=14 = warning)
NON_AR_METHODS = {"kontan", "tunai", "cash"}
DEAD_STATUSES = {"cancelled", "draft", "expired", "rejected"}


# ─── SALES REVAMP V2 — Sales team (PIC + co-sales + split) di level CUSTOMER ───
def normalize_sales_team(raw: Any, assigned_sales_id: str = "", assigned_sales_name: str = "") -> List[Dict[str, Any]]:
    """Validasi + normalisasi tim sales customer/order (join/group sales).

    - PIC.sales_id = kunci kepemilikan (== assigned_sales_id).
    - Kosong + ada assigned_sales_id → PIC tunggal 100%.
    - Bila diisi: tepat 1 PIC, Σ split_pct == 100 (toleransi 0.01), tak duplikat, tiap split > 0.
    """
    members: List[Dict[str, Any]] = []
    for m in (raw or []):
        d = m.model_dump() if hasattr(m, "model_dump") else dict(m)
        sid = (d.get("sales_id") or "").strip()
        if not sid:
            continue
        members.append({
            "sales_id": sid,
            "name": (d.get("name") or "").strip(),
            "role": "pic" if d.get("role") == "pic" else "co",
            "split_pct": round(float(d.get("split_pct") or 0), 2),
        })
    if not members:
        if assigned_sales_id:
            return [{"sales_id": assigned_sales_id, "name": assigned_sales_name or "", "role": "pic", "split_pct": 100.0}]
        return []
    ids = [m["sales_id"] for m in members]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="Anggota sales tim tidak boleh duplikat.")
    if any(m["split_pct"] <= 0 for m in members):
        raise HTTPException(status_code=400, detail="Setiap anggota sales tim harus punya split insentif > 0%.")
    pic_members = [m for m in members if m["role"] == "pic"]
    if len(pic_members) == 0:
        members[0]["role"] = "pic"
    elif len(pic_members) > 1:
        raise HTTPException(status_code=400, detail="Sales tim harus punya tepat 1 PIC (penanggung jawab).")
    total = round(sum(m["split_pct"] for m in members), 2)
    if abs(total - 100.0) > 0.01:
        raise HTTPException(status_code=400, detail=f"Total split insentif harus 100% (saat ini {total}%).")
    return members


def pic_of(team: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for m in (team or []):
        if m.get("role") == "pic":
            return m
    return (team or [None])[0]


def resolve_customer_sales_team(customer: Dict[str, Any]) -> List[Dict[str, Any]]:
    """SO mewarisi tim sales dari customer; fallback PIC tunggal dari assigned_sales_id."""
    team = customer.get("sales_team") or []
    if team:
        return team
    aid = customer.get("assigned_sales_id") or ""
    if aid:
        return [{"sales_id": aid, "name": customer.get("assigned_sales_name") or "", "role": "pic", "split_pct": 100.0}]
    return []


async def resolve_team_names(team: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Isi `name` tiap anggota dari koleksi users (bila kosong)."""
    out = []
    for m in (team or []):
        nm = m.get("name") or ""
        if not nm and m.get("sales_id"):
            u = await db.users.find_one({"id": m["sales_id"]}, {"_id": 0, "name": 1})
            nm = (u or {}).get("name", "")
        out.append({**m, "name": nm})
    return out


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            dt = datetime.strptime(str(value)[:10], "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None


def _order_grand_total(o: Dict[str, Any]) -> float:
    return float(o.get("grand_total", o.get("total_amount", 0)) or 0)


def _order_paid(o: Dict[str, Any]) -> float:
    return sum(float(p.get("amount", 0) or 0) for p in (o.get("payments") or []))


def order_payment_method(o: Dict[str, Any]) -> str:
    """SSOT tunggal deteksi metode bayar order (P3-7).

    Selalu cek `payment_profile_method` DAN `payment_term_code` agar konsisten di
    credit engine, collection worklist, dan AR receipt (hindari drift NON_AR).
    """
    return str((o.get("payment_profile_method") or o.get("payment_term_code") or "")).lower()


def _term_days(customer: Dict[str, Any], order: Dict[str, Any]) -> int:
    pp = customer.get("payment_profile") or {}
    try:
        td = int(order.get("payment_term_days") or 0)
    except Exception:
        td = 0
    if td > 0:
        return td
    try:
        return int(pp.get("term_days") or 30)
    except Exception:
        return 30


async def compute_customer_credit(customer: Dict[str, Any]) -> Dict[str, Any]:
    """AR outstanding, overdue, dan status kredit (active|warning|blocked)."""
    cid = customer["id"]
    credit_limit = float(customer.get("credit_limit", 0) or 0)
    orders = await db.sales_orders.find(
        {"customer_id": cid}, {"_id": 0}
    ).to_list(2000)
    now = datetime.now(timezone.utc)
    ar = 0.0
    overdue = 0.0
    max_overdue_days = 0
    open_orders = 0
    for o in orders:
        if o.get("status") in DEAD_STATUSES:
            continue
        if o.get("payment_status") == "paid":
            continue
        outstanding = max(_order_grand_total(o) - _order_paid(o), 0.0)
        if outstanding <= 0.01:
            continue
        # Kontan/tunai bukan AR
        method = order_payment_method(o)
        if method in NON_AR_METHODS:
            continue
        ar += outstanding
        open_orders += 1
        created = _parse_dt(o.get("created_at")) or now
        due = created + timedelta(days=_term_days(customer, o))
        if due < now:
            overdue += outstanding
            days_late = (now - due).days
            max_overdue_days = max(max_overdue_days, days_late)
    status = "active"
    near_limit = credit_limit > 0 and ar >= WARNING_RATIO * credit_limit
    over_limit = credit_limit > 0 and ar >= credit_limit
    if near_limit or overdue > 0:
        status = "warning"
    if over_limit or max_overdue_days > OVERDUE_BLOCK_DAYS:
        status = "blocked"
    # status manual 'blocked'/'inactive' di kolom customer.status menang utk blokir
    if customer.get("status") == "blocked":
        status = "blocked"
    return {
        "credit_limit": credit_limit,
        "ar_outstanding": round(ar, 2),
        "overdue_amount": round(overdue, 2),
        "max_overdue_days": max_overdue_days,
        "open_orders": open_orders,
        "available_credit": round(max(credit_limit - ar, 0), 2) if credit_limit > 0 else None,
        "deposit_balance": round(float(customer.get("deposit_balance", 0) or 0), 2),
        "status": status,
    }


async def enrich_customer(customer: Dict[str, Any], with_credit: bool = True) -> Dict[str, Any]:
    """Tambah assigned_sales_name + ringkasan kredit ke dokumen customer."""
    c = safe_doc(customer)
    if c.get("assigned_sales_id") and not c.get("assigned_sales_name"):
        u = await db.users.find_one({"id": c["assigned_sales_id"]}, {"_id": 0, "name": 1})
        c["assigned_sales_name"] = (u or {}).get("name", "")
    if with_credit:
        c["credit"] = await compute_customer_credit(c)
    return c


async def check_credit_for_order(customer: Dict[str, Any], new_amount: float) -> Dict[str, Any]:
    """Gate kredit saat buat SO (KN_17 §5.2). allowed=False bila blocked."""
    credit = await compute_customer_credit(customer)
    limit = credit["credit_limit"]
    projected = credit["ar_outstanding"] + float(new_amount or 0)
    blocked = credit["status"] == "blocked" or (limit > 0 and projected > limit)
    warn = (not blocked) and (
        credit["status"] == "warning" or (limit > 0 and projected >= WARNING_RATIO * limit) or credit["overdue_amount"] > 0
    )
    reasons = []
    if limit > 0 and projected > limit:
        reasons.append(f"Proyeksi AR {rupiah(projected)} melebihi limit {rupiah(limit)}")
    if credit["overdue_amount"] > 0:
        reasons.append(f"Ada tunggakan jatuh tempo {rupiah(credit['overdue_amount'])} ({credit['max_overdue_days']} hari)")
    if customer.get("status") == "blocked":
        reasons.append("Customer berstatus blocked manual")
    return {
        "allowed": not blocked,
        "level": "blocked" if blocked else ("warning" if warn else "ok"),
        "credit": credit,
        "projected_ar": round(projected, 2),
        "reasons": reasons,
    }


async def customer_360(customer_id: str) -> Optional[Dict[str, Any]]:
    """Profil lengkap + riwayat order/dokumen/special price + kredit."""
    customer = safe_doc(await db.customers.find_one({"id": customer_id}, {"_id": 0}))
    if not customer:
        return None
    customer = await enrich_customer(customer, with_credit=True)
    orders = await db.sales_orders.find(
        {"customer_id": customer_id},
        {"_id": 0, "id": 1, "number": 1, "status": 1, "payment_status": 1,
         "grand_total": 1, "total_amount": 1, "created_at": 1, "sales_name": 1, "payments": 1},
    ).sort("created_at", -1).to_list(100)
    order_history = []
    for o in orders:
        order_history.append({
            "id": o.get("id"), "number": o.get("number"), "status": o.get("status"),
            "payment_status": o.get("payment_status"), "grand_total": _order_grand_total(o),
            "paid": _order_paid(o), "created_at": o.get("created_at"), "sales_name": o.get("sales_name", ""),
        })
    docs = await db.generated_documents.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    if not docs:  # fallback: dokumen tertaut via order
        oids = [o.get("id") for o in orders]
        if oids:
            docs = await db.generated_documents.find(
                {"order_id": {"$in": oids}}, {"_id": 0}
            ).sort("created_at", -1).to_list(100)
    special_prices = await db.price_approvals.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    followups = await db.collection_followups.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    overrides = await db.credit_overrides.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {
        **customer,
        "order_history": order_history,
        "document_history": [safe_doc(d) for d in docs],
        "special_price_history": [safe_doc(s) for s in special_prices],
        "collection_followups": [safe_doc(f) for f in followups],
        "credit_overrides": [safe_doc(o) for o in overrides],
        "stats": {
            "total_orders": len(order_history),
            "lifetime_value": round(sum(o["grand_total"] for o in order_history), 2),
        },
    }


def scope_query(user: Dict[str, Any], base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Row-level scoping (KN_17 §4): role=sales hanya customer miliknya."""
    q = dict(base or {})
    if user and user.get("role") == "sales":
        q["assigned_sales_id"] = user.get("id")
    return q


async def can_access_customer(user: Dict[str, Any], customer: Dict[str, Any]) -> bool:
    if not user or not customer:
        return False
    role = user.get("role")
    # admin/manager = CROSS_ENTITY_ROLES → oversight semua entitas.
    if role in ("admin", "manager"):
        return True
    # INV-ENTITY-01 (KN-076-IDOR-READ-SUBRES P0): isolasi lintas-entitas untuk role ter-scope.
    # Dokumen customer di luar entitas yang diizinkan aktor → TOLAK, walau assigned_sales_id cocok
    # (seed bisa meng-assign sales ke customer entitas lain — tetap tak boleh diakses lintas-PT).
    ent = customer.get("entity_id")
    allowed = user.get("allowed_entity_ids") or (
        [user.get("home_entity_id")] if user.get("home_entity_id") else []
    )
    if ent and allowed and ent not in allowed:
        return False
    if role == "sales":
        return customer.get("assigned_sales_id") == user.get("id")
    return True


async def collection_worklist(
    user: Dict[str, Any], sales_id: Optional[str] = None, entity_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Daftar tagihan (order outstanding) untuk follow-up penagihan (KN_17 paragraf 7)."""
    cust_filter: Dict[str, Any] = {}
    if user.get("role") == "sales":
        cust_filter["assigned_sales_id"] = user.get("id")
    elif sales_id:
        cust_filter["assigned_sales_id"] = sales_id
    if entity_id and entity_id != "all":
        cust_filter["entity_id"] = entity_id
    customers = await db.customers.find(
        cust_filter, {"_id": 0, "id": 1, "name": 1, "assigned_sales_id": 1, "payment_profile": 1}
    ).to_list(3000)
    cmap = {c["id"]: c for c in customers}
    cust_ids = list(cmap.keys())
    rows: List[Dict[str, Any]] = []
    if not cust_ids:
        return rows
    orders = await db.sales_orders.find(
        {"customer_id": {"$in": cust_ids}},
        {"_id": 0, "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
         "status": 1, "payment_status": 1, "grand_total": 1, "total_amount": 1,
         "payments": 1, "created_at": 1, "sales_name": 1, "payment_term_code": 1,
         "payment_profile_method": 1},
    ).to_list(8000)
    now = datetime.now(timezone.utc)
    for o in orders:
        if o.get("status") in DEAD_STATUSES or o.get("payment_status") == "paid":
            continue
        outstanding = max(_order_grand_total(o) - _order_paid(o), 0.0)
        if outstanding <= 0.01:
            continue
        method = order_payment_method(o)
        if method in NON_AR_METHODS:
            continue
        c = cmap.get(o["customer_id"], {})
        created = _parse_dt(o.get("created_at")) or now
        due = created + timedelta(days=_term_days(c, o))
        days_late = (now - due).days
        rows.append({
            "order_id": o.get("id"), "order_number": o.get("number"),
            "customer_id": o.get("customer_id"), "customer_name": o.get("customer_name"),
            "assigned_sales_id": c.get("assigned_sales_id", ""),
            "outstanding": round(outstanding, 2),
            "due_date": due.date().isoformat(),
            "days_late": days_late,
            "overdue": days_late > 0,
            "sales_name": o.get("sales_name", ""),
        })
    rows.sort(key=lambda r: r["days_late"], reverse=True)
    return rows


async def evaluate_credit_gate(customer: Dict[str, Any], amount: float) -> Dict[str, Any]:
    """Gate kredit saat buat SO (KN_17 S37 / pilihan owner 1b+2a).

    blocked + tanpa override approved -> tolak. blocked + override approved (cukup nilainya)
    -> boleh lanjut (override akan dikonsumsi). warning -> boleh lanjut (flag).
    """
    gate = await check_credit_for_order(customer, amount)
    override = None
    if not gate["allowed"]:
        ov = await db.credit_overrides.find_one(
            {"customer_id": customer["id"], "status": "approved", "consumed": {"$ne": True}},
            {"_id": 0}, sort=[("decided_at", -1)],
        )
        if ov:
            amt = float(ov.get("amount") or 0)
            if amt <= 0 or float(amount or 0) <= amt + 1e-6:
                override = ov
    return {
        "level": gate["level"],                       # ok | warning | blocked
        "blocked": not gate["allowed"],
        "allowed_after_override": bool(override),
        "reasons": gate["reasons"],
        "credit": gate["credit"],
        "projected_ar": gate["projected_ar"],
        "override": override,
    }


async def collection_reminders(
    user: Dict[str, Any], days_ahead: int = 7, sales_id: Optional[str] = None, entity_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Reminder penagihan (KN_17 §7 / 4b): overdue + akan jatuh tempo <= days_ahead, + flag reminded."""
    rows = await collection_worklist(user, sales_id=sales_id, entity_id=entity_id)
    span = abs(int(days_ahead or 0))
    sel = [r for r in rows if r["days_late"] >= -span]
    if not sel:
        return []
    order_ids = [r["order_id"] for r in sel]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    fus = await db.collection_followups.find(
        {"order_id": {"$in": order_ids}, "outcome": "reminded", "created_at": {"$gte": cutoff}},
        {"_id": 0, "order_id": 1},
    ).to_list(4000)
    reminded = {f["order_id"] for f in fus}
    for r in sel:
        r["reminded"] = r["order_id"] in reminded
        r["due_soon"] = (not r["overdue"]) and r["days_late"] >= -span
    sel.sort(key=lambda r: r["days_late"], reverse=True)
    return sel
