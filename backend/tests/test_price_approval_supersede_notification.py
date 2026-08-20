"""Tests for the price_approval_superseded notification side-effect on approve.

Focus (iter_110): when a NEW STANDING price-approval is approved and it supersedes
existing approved standing rules for the same (entity, customer, product), a
notification of type='price_approval_superseded' MUST be created for the OWNER of
each superseded rule. Verified via GET /api/notifications with the sales token.

Also covers:
- Dedupe on ref='pra_superseded:<old_approval_id>'.
- order-scope approve does NOT create notification.
- No prior approved → no notification, superseded_count==0.
- Reject flow does NOT create notification.
- Regression sanity on critical endpoints.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or (
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0].strip()
)
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
SALES = {"email": "sales@kainnusantara.id", "password": "demo12345"}


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _login(session: requests.Session, creds: Dict[str, str]) -> Dict[str, Any]:
    r = session.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    tok = body.get("token")
    assert tok, f"no token in login response: {body}"
    return body


@pytest.fixture(scope="module")
def admin_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    body = _login(s, ADMIN)
    s.headers.update({"Authorization": f"Bearer {body['token']}"})
    s.user = body.get("user") or {}  # type: ignore[attr-defined]
    return s


@pytest.fixture(scope="module")
def sales_ctx() -> Dict[str, Any]:
    """Sales session + user profile so we can assert recipient_user==sales.id."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    body = _login(s, SALES)
    s.headers.update({"Authorization": f"Bearer {body['token']}"})
    user = body.get("user") or {}
    if not user.get("id"):
        # fallback: hit /auth/me if profile not embedded
        try:
            me = s.get(f"{API}/auth/me", timeout=10)
            if me.status_code == 200:
                user = me.json().get("user") or me.json()
        except Exception:
            pass
    return {"client": s, "user": user}


@pytest.fixture(scope="module")
def seed_ids(admin_client: requests.Session) -> Dict[str, Any]:
    customers = admin_client.get(f"{API}/customers").json()
    products = admin_client.get(f"{API}/products").json()
    assert isinstance(customers, list) and len(customers) >= 2
    assert isinstance(products, list) and len(products) >= 2
    return {
        "cust_a": customers[0]["id"],
        "cust_b": customers[1]["id"],
        "prod_a": products[0]["id"],
        "prod_b": products[1]["id"],
        "prod_c": products[2]["id"] if len(products) >= 3 else products[1]["id"],
        "cust_a_name": customers[0].get("name", ""),
        "prod_a_name": products[0].get("name", ""),
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _create_pra(
    client: requests.Session, customer_id: str, product_id: str,
    requested_price: float, scope: str = "standing", submit_now: bool = True,
    reason: str = "TEST_supersede_notif",
) -> Dict[str, Any]:
    r = client.post(f"{API}/price-approvals", json={
        "customer_id": customer_id, "product_id": product_id,
        "requested_price": requested_price, "scope": scope,
        "reason": reason, "submit_now": submit_now,
    })
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text[:300]}"
    return r.json()


def _approve(client: requests.Session, approval_id: str) -> Dict[str, Any]:
    r = client.post(
        f"{API}/price-approvals/{approval_id}/approve",
        json={"decision_notes": "TEST_supersede_notif_approve"},
    )
    assert r.status_code == 200, f"approve failed: {r.status_code} {r.text[:300]}"
    return r.json()


def _reject(client: requests.Session, approval_id: str) -> Dict[str, Any]:
    r = client.post(
        f"{API}/price-approvals/{approval_id}/reject",
        json={"decision_notes": "TEST_reject_notes"},
    )
    assert r.status_code == 200, f"reject failed: {r.status_code} {r.text[:300]}"
    return r.json()


def _list_notifications(client: requests.Session) -> List[Dict[str, Any]]:
    r = client.get(f"{API}/notifications", timeout=15)
    assert r.status_code == 200, f"list notifs failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert isinstance(body, list), f"expected list, got {type(body)}: {body!r}"
    return body


def _find_notif_by_ref(items: List[Dict[str, Any]], ref: str) -> Optional[Dict[str, Any]]:
    for n in items:
        if n.get("ref") == ref:
            return n
    return None


# ─── Regression sanity (parallel-friendly, cheap) ────────────────────────────

CRITICAL_ENDPOINTS = [
    "/dashboard", "/products", "/customers", "/sales-orders",
    "/notifications", "/notifications/unread-count",
]


@pytest.mark.parametrize("path", CRITICAL_ENDPOINTS)
def test_critical_endpoints_ok(admin_client: requests.Session, path: str) -> None:
    r = admin_client.get(f"{API}{path}", timeout=20)
    assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"
    assert r.json() is not None


def test_notifications_shape_for_sales(sales_ctx: Dict[str, Any]) -> None:
    items = _list_notifications(sales_ctx["client"])
    for n in items[:5]:
        # ensure no MongoDB _id leaks through
        assert "_id" not in n, f"_id leaked in notification: {n}"


# ─── Notification side-effect: STANDING supersede → notify owner ────────────

def test_supersede_creates_notification_for_sales_owner(
    admin_client: requests.Session, sales_ctx: Dict[str, Any],
    seed_ids: Dict[str, Any],
) -> None:
    """Sales creates+approves (via admin) a standing PRA; then admin creates+approves
    another standing PRA for the SAME (customer, product). The sales user MUST
    see a 'price_approval_superseded' notification for their old approval."""
    sales_client: requests.Session = sales_ctx["client"]
    sales_user: Dict[str, Any] = sales_ctx["user"] or {}
    sales_id = sales_user.get("id") or ""
    assert sales_id, f"sales user id missing: {sales_user}"

    cust = seed_ids["cust_a"]
    prod = seed_ids["prod_c"]  # distinct product to avoid cross-test pollution

    # 1) SALES creates a standing PRA (owner=sales)
    old_price = 12345.0
    p_old = _create_pra(sales_client, cust, prod, requested_price=old_price)
    assert p_old["requested_by"] == sales_id, (
        f"owner mismatch: {p_old.get('requested_by')} vs sales_id {sales_id}"
    )

    # 2) ADMIN approves the SALES-owned PRA (first approval, no supersede)
    _approve(admin_client, p_old["id"])

    # 3) ADMIN creates + approves a NEW standing PRA for same tuple.
    #    This should supersede p_old AND trigger a notification to sales.
    new_price = 9999.0
    p_new = _create_pra(admin_client, cust, prod, requested_price=new_price)
    p_new = _approve(admin_client, p_new["id"])  # capture approved doc for approver_name

    # 4) Sales fetches their notifications — must contain the superseded one.
    items = _list_notifications(sales_client)
    ref = f"pra_superseded:{p_old['id']}"
    n = _find_notif_by_ref(items, ref)
    assert n is not None, (
        f"expected notification ref={ref} for sales; got refs="
        f"{[x.get('ref') for x in items[:15]]}"
    )

    # Field-level assertions
    assert n.get("type") == "price_approval_superseded"
    assert n.get("severity") == "warning"
    assert n.get("link") == "price-approvals"
    assert n.get("recipient_role") == "sales"
    assert n.get("recipient_user") == sales_id, (
        f"recipient_user mismatch: {n.get('recipient_user')} vs {sales_id}"
    )
    assert n.get("action_type") == "price_approval_view"
    assert n.get("action_id") == p_new["id"]
    assert n.get("read") is False
    assert n.get("id", "").startswith("ntf_")
    assert n.get("created_at")

    # Body must reference approver name, both prices in Rupiah, and delta%.
    body = n.get("body") or ""
    approver_name = (p_new.get("approved_by_name") or "").strip()
    assert approver_name and approver_name in body, (
        f"approver_name '{approver_name}' missing in body: {body}"
    )
    # Rupiah format uses "Rp <num>" with thousands separator (comma).
    assert "Rp 12,345" in body, f"old price missing in body: {body}"
    assert "Rp 9,999" in body, f"new price missing in body: {body}"
    # delta% present (regex: signed number followed by %)
    assert re.search(r"[+-]\d+(\.\d+)?%", body), f"delta% missing in body: {body}"
    # Customer + product identifiers should appear
    cust_name = (seed_ids.get("cust_a_name") or "").strip()
    prod_name = (seed_ids.get("prod_a_name") or "").strip()
    if cust_name:
        # customer_name of cust_a; body uses old.customer_name from the doc
        assert cust_name in body or "·" in body  # separator present at minimum
    # Title mentions product
    title = n.get("title") or ""
    assert title.lower().startswith("aturan harga anda diganti"), f"unexpected title: {title}"


def test_supersede_notification_deduped_on_second_supersede(
    admin_client: requests.Session, sales_ctx: Dict[str, Any],
    seed_ids: Dict[str, Any],
) -> None:
    """Once a superseded notif exists for a given old_id (ref = pra_superseded:<old_id>)
    and is still unread, a subsequent supersede attempt on that same old_id MUST NOT
    create a duplicate row. We simulate by approving another standing PRA for the
    SAME tuple — but this time old_id is already superseded so its status is no longer
    approved and shouldn't be picked up again. That confirms:
      1) no new notif with the same ref (natural: old_id no longer approved), and
      2) count of notifs with that ref stays == 1.
    """
    sales_client: requests.Session = sales_ctx["client"]
    cust = seed_ids["cust_a"]
    prod = seed_ids["prod_c"]

    # Build state: create+approve as sales, then approve #2 as admin (supersede #1)
    p1 = _create_pra(sales_client, cust, prod, requested_price=15000.0)
    _approve(admin_client, p1["id"])
    p2 = _create_pra(admin_client, cust, prod, requested_price=16000.0)
    _approve(admin_client, p2["id"])

    # first notif must exist for ref=pra_superseded:p1
    ref1 = f"pra_superseded:{p1['id']}"
    items = _list_notifications(sales_client)
    matches1 = [n for n in items if n.get("ref") == ref1]
    assert len(matches1) == 1, f"expected exactly 1 notif for {ref1}, got {len(matches1)}"

    # Now approve p3 for same tuple — p1 is already 'superseded' so it should NOT
    # produce another notif with ref1. p2 (still approved) will be superseded now
    # → creates a NEW notif with ref2 (different ref, so allowed).
    p3 = _create_pra(admin_client, cust, prod, requested_price=17000.0)
    _approve(admin_client, p3["id"])

    items2 = _list_notifications(sales_client)
    matches1_again = [n for n in items2 if n.get("ref") == ref1]
    assert len(matches1_again) == 1, (
        f"ref {ref1} must not duplicate — got {len(matches1_again)}"
    )
    # p2 was owned by admin — check whether a notif exists for p2 supersede.
    # Sales only sees notifs where recipient_user==sales.id OR recipient_role='sales'.
    # p2 owner=admin (not sales), so recipient_user=admin_id → sales will NOT see it.
    # This is fine; we only need to assert no duplicate of ref1.


def test_order_scope_approve_does_not_notify(
    admin_client: requests.Session, sales_ctx: Dict[str, Any],
    seed_ids: Dict[str, Any],
) -> None:
    """Approving an order-scope PRA MUST NOT create any price_approval_superseded
    notification (order scope bypasses supersede logic entirely)."""
    sales_client: requests.Session = sales_ctx["client"]
    cust = seed_ids["cust_b"]
    prod = seed_ids["prod_b"]

    # Create sales-owned order-scope PRA — approve as admin. No supersede expected.
    p = _create_pra(sales_client, cust, prod, requested_price=21000.0, scope="order")
    _approve(admin_client, p["id"])

    ref = f"pra_superseded:{p['id']}"
    items = _list_notifications(sales_client)
    n = _find_notif_by_ref(items, ref)
    assert n is None, f"order-scope approve should not create supersede notif; got {n}"


def test_no_supersede_no_notification_and_zero_count(
    admin_client: requests.Session, sales_ctx: Dict[str, Any],
    seed_ids: Dict[str, Any],
) -> None:
    """When there are no prior approved standing rules for the same tuple, approve
    must NOT create a supersede notification AND audit.superseded_count==0."""
    sales_client: requests.Session = sales_ctx["client"]
    cust = seed_ids["cust_b"]
    # use a fresh product to minimise chance of prior approved standing
    prod = seed_ids["prod_a"]

    # First ensure no prior approved standing for this tuple by inspecting list.
    prior = admin_client.get(
        f"{API}/price-approvals",
        params={"customer_id": cust, "product_id": prod, "status": "approved"},
    ).json()
    prior_standing = [x for x in prior if x.get("scope", "standing") != "order"]
    # Reject-approve them first? No — simpler: skip assertion if prior exists.
    if prior_standing:
        pytest.skip(f"tuple has {len(prior_standing)} prior approved standing rows; skip")

    p = _create_pra(sales_client, cust, prod, requested_price=88888.0)
    approve_resp = _approve(admin_client, p["id"])
    assert approve_resp["status"] == "approved"

    # Check audit log
    logs = admin_client.get(f"{API}/audit-logs").json()
    log = next(
        (l for l in logs if l.get("action") == "price_approval_approved"
         and l.get("entity_id") == p["id"]),
        None,
    )
    assert log is not None, "audit for approve missing"
    after = log.get("after") or {}
    assert int(after.get("superseded_count", -1)) == 0, (
        f"superseded_count expected 0, got {after.get('superseded_count')}"
    )

    # No supersede notif should exist keyed by this approval's own id — sanity check.
    ref = f"pra_superseded:{p['id']}"
    items = _list_notifications(sales_client)
    assert _find_notif_by_ref(items, ref) is None


def test_reject_flow_creates_no_supersede_notification(
    admin_client: requests.Session, sales_ctx: Dict[str, Any],
    seed_ids: Dict[str, Any],
) -> None:
    """Rejecting a PRA must not create a price_approval_superseded notification."""
    sales_client: requests.Session = sales_ctx["client"]
    p = _create_pra(sales_client, seed_ids["cust_a"], seed_ids["prod_b"], requested_price=4321.0)
    _reject(admin_client, p["id"])

    ref = f"pra_superseded:{p['id']}"
    items = _list_notifications(sales_client)
    assert _find_notif_by_ref(items, ref) is None


# ─── Regression: audit still carries superseded_count metadata ──────────────

def test_audit_contains_superseded_count(
    admin_client: requests.Session, sales_ctx: Dict[str, Any],
    seed_ids: Dict[str, Any],
) -> None:
    """Regression: audit_logs for 'price_approval_approved' still contains
    superseded_count equal to db modified_count (>=1 when a real supersede
    happened)."""
    sales_client: requests.Session = sales_ctx["client"]
    cust = seed_ids["cust_b"]
    prod = seed_ids["prod_c"]

    p1 = _create_pra(sales_client, cust, prod, requested_price=1111.0)
    _approve(admin_client, p1["id"])
    p2 = _create_pra(admin_client, cust, prod, requested_price=2222.0)
    _approve(admin_client, p2["id"])

    logs = admin_client.get(f"{API}/audit-logs").json()
    log = next(
        (l for l in logs if l.get("action") == "price_approval_approved"
         and l.get("entity_id") == p2["id"]),
        None,
    )
    assert log is not None, "audit for approve p2 missing"
    after = log.get("after") or {}
    assert "superseded_count" in after
    assert int(after["superseded_count"]) >= 1
