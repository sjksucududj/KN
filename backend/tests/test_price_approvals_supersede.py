"""Tests for POST /api/price-approvals/{id}/approve supersede-on-approve logic.

Verifies:
  * STANDING approvals: newer approved supersedes prior approved standing rules
    for the same (entity_id, customer_id, product_id).
  * order-scope approvals are NOT superseded and do NOT trigger supersede.
  * Scope is limited by (entity, customer, product) tuple — unrelated approvals
    for other customers/products remain untouched.
  * Audit log for `price_approval_approved` includes `superseded_count`.
  * Regression: basic price-approval lifecycle & critical read endpoints.
"""
from __future__ import annotations

import os
import time
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

def _login(session: requests.Session, creds: Dict[str, str]) -> str:
    r = session.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    token = _login(s, ADMIN)
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def sales_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    token = _login(s, SALES)
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def seed_ids(admin_client: requests.Session) -> Dict[str, Any]:
    """Pull two distinct customers and two products from seeded data."""
    customers = admin_client.get(f"{API}/customers").json()
    products = admin_client.get(f"{API}/products").json()
    assert isinstance(customers, list) and len(customers) >= 2, "need >=2 customers"
    assert isinstance(products, list) and len(products) >= 2, "need >=2 products"
    return {
        "cust_a": customers[0]["id"],
        "cust_b": customers[1]["id"],
        "prod_a": products[0]["id"],
        "prod_b": products[1]["id"],
        "entity_id": customers[0].get("entity_id", ""),
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _create_pra(
    client: requests.Session,
    customer_id: str,
    product_id: str,
    requested_price: float = 12345.67,
    scope: str = "standing",
    submit_now: bool = True,
    reason: str = "TEST_supersede",
) -> Dict[str, Any]:
    r = client.post(
        f"{API}/price-approvals",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "requested_price": requested_price,
            "scope": scope,
            "reason": reason,
            "submit_now": submit_now,
        },
    )
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text[:300]}"
    return r.json()


def _approve(client: requests.Session, approval_id: str) -> Dict[str, Any]:
    r = client.post(
        f"{API}/price-approvals/{approval_id}/approve",
        json={"decision_notes": "TEST_approve"},
    )
    assert r.status_code == 200, f"approve failed: {r.status_code} {r.text[:300]}"
    return r.json()


def _get(client: requests.Session, approval_id: str) -> Dict[str, Any]:
    r = client.get(f"{API}/price-approvals/{approval_id}")
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text[:200]}"
    return r.json()


def _find_audit(
    client: requests.Session, action: str, entity_id: str
) -> Optional[Dict[str, Any]]:
    logs = client.get(f"{API}/audit-logs").json()
    for log in logs:
        if log.get("action") == action and log.get("entity_id") == entity_id:
            return log
    return None


# ─── Tests ───────────────────────────────────────────────────────────────────

# --- Regression: critical endpoints still 200 ------------------------------

CRITICAL_ENDPOINTS = [
    "/dashboard",
    "/products",
    "/customers",
    "/sales-orders",
    "/inventory/balances",
    "/inventory/status-board",
    "/purchase-orders",
    "/wms/tasks",
    "/audit-logs",
]


@pytest.mark.parametrize("path", CRITICAL_ENDPOINTS)
def test_critical_endpoints_ok(admin_client: requests.Session, path: str) -> None:
    r = admin_client.get(f"{API}{path}", timeout=20)
    assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body is not None, f"{path} returned empty body"


# --- Basic lifecycle regression -------------------------------------------

def test_lifecycle_create_submit_approve(
    admin_client: requests.Session, seed_ids: Dict[str, Any]
) -> None:
    # Create as draft
    pra = _create_pra(
        admin_client,
        seed_ids["cust_a"],
        seed_ids["prod_a"],
        requested_price=10000.0,
        submit_now=False,
        reason="TEST_lifecycle",
    )
    assert pra["status"] == "draft"
    assert pra["scope"] == "standing"
    aid = pra["id"]

    # Submit
    r = admin_client.post(f"{API}/price-approvals/{aid}/submit")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"

    # Approve
    ap = _approve(admin_client, aid)
    assert ap["status"] == "approved"
    assert ap["approved_by_name"]

    # Detail
    detail = _get(admin_client, aid)
    assert detail["id"] == aid
    assert detail["status"] == "approved"

    # List
    lst = admin_client.get(f"{API}/price-approvals").json()
    assert isinstance(lst, list)
    assert any(x["id"] == aid for x in lst)


def test_reject_flow(admin_client: requests.Session, seed_ids: Dict[str, Any]) -> None:
    pra = _create_pra(
        admin_client,
        seed_ids["cust_a"],
        seed_ids["prod_b"],
        requested_price=9999.0,
        submit_now=True,
        reason="TEST_reject",
    )
    r = admin_client.post(
        f"{API}/price-approvals/{pra['id']}/reject",
        json={"decision_notes": "TEST_reject_notes"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


# --- Supersede-on-approve core -------------------------------------------

def test_supersede_standing_same_tuple(
    admin_client: requests.Session, seed_ids: Dict[str, Any]
) -> None:
    """Two STANDING approvals for same (entity, customer, product).
    Approve #1, then approve #2 → #1 should become 'superseded' with
    superseded_by=id2 and superseded_at populated. #2 remains 'approved'.
    Audit for #2 must include superseded_count>=1."""
    cust = seed_ids["cust_a"]
    prod = seed_ids["prod_a"]

    p1 = _create_pra(admin_client, cust, prod, requested_price=11111.0, scope="standing")
    p2 = _create_pra(admin_client, cust, prod, requested_price=22222.0, scope="standing")

    a1 = _approve(admin_client, p1["id"])
    assert a1["status"] == "approved"

    # #1 still approved (no other approved to supersede)
    d1_before = _get(admin_client, p1["id"])
    assert d1_before["status"] == "approved"

    a2 = _approve(admin_client, p2["id"])
    assert a2["status"] == "approved"

    # Post-approve of #2, #1 must be superseded
    d1_after = _get(admin_client, p1["id"])
    assert d1_after["status"] == "superseded", (
        f"expected superseded, got {d1_after['status']} — full: {d1_after}"
    )
    assert d1_after.get("superseded_by") == p2["id"], (
        f"superseded_by mismatch: got {d1_after.get('superseded_by')}, want {p2['id']}"
    )
    assert d1_after.get("superseded_at"), "superseded_at must be populated"

    # #2 still approved
    d2 = _get(admin_client, p2["id"])
    assert d2["status"] == "approved"

    # Audit for #2 approval → superseded_count>=1
    log = _find_audit(admin_client, "price_approval_approved", p2["id"])
    assert log is not None, "audit log for price_approval_approved missing"
    after = log.get("after") or {}
    assert "superseded_count" in after, f"superseded_count missing in audit: {after}"
    assert int(after["superseded_count"]) >= 1, (
        f"superseded_count expected >=1, got {after['superseded_count']}"
    )


def test_supersede_zero_when_no_prior(
    admin_client: requests.Session, seed_ids: Dict[str, Any]
) -> None:
    """Approving a standing rule with no prior approved rule for the same
    tuple → audit superseded_count == 0."""
    # Use a fresh (customer, product) pair unlikely to have prior approvals.
    # cust_b + prod_b — reject any prior approvals to be safe.
    cust = seed_ids["cust_b"]
    prod = seed_ids["prod_b"]

    # Clear the field: reject any pre-existing 'approved' rows in this tuple by
    # creating a helper approve then… simpler — just create fresh & check count.
    p = _create_pra(admin_client, cust, prod, requested_price=33333.0, scope="standing")
    # Ensure no other approved standing for same tuple currently (best-effort).
    approved_others = admin_client.get(
        f"{API}/price-approvals",
        params={"customer_id": cust, "product_id": prod, "status": "approved"},
    ).json()

    _approve(admin_client, p["id"])

    log = _find_audit(admin_client, "price_approval_approved", p["id"])
    assert log is not None
    after = log.get("after") or {}
    assert "superseded_count" in after, f"superseded_count missing: {after}"
    # Only pre-existing approved standing rows for same tuple should be counted.
    # Cast defensively.
    expected = len([r for r in approved_others if r.get("scope", "standing") != "order"])
    assert int(after["superseded_count"]) == expected, (
        f"superseded_count expected {expected}, got {after['superseded_count']}"
    )


def test_supersede_ignores_different_customer(
    admin_client: requests.Session, seed_ids: Dict[str, Any]
) -> None:
    """Approving a standing rule for cust_b must NOT supersede an approved
    standing rule for cust_a (same product)."""
    prod = seed_ids["prod_a"]

    # First approved standing for cust_a
    p_a = _create_pra(admin_client, seed_ids["cust_a"], prod, requested_price=44440.0)
    _approve(admin_client, p_a["id"])

    # New standing for cust_b (different customer)
    p_b = _create_pra(admin_client, seed_ids["cust_b"], prod, requested_price=44441.0)
    _approve(admin_client, p_b["id"])

    d_a = _get(admin_client, p_a["id"])
    assert d_a["status"] == "approved", (
        f"cust_a approval must remain approved when cust_b's is approved: got {d_a['status']}"
    )
    assert "superseded_by" not in d_a or not d_a.get("superseded_by")


def test_supersede_ignores_different_product(
    admin_client: requests.Session, seed_ids: Dict[str, Any]
) -> None:
    """Approving standing rule for prod_b must NOT supersede approved rule for
    prod_a (same customer)."""
    cust = seed_ids["cust_a"]

    p_a = _create_pra(admin_client, cust, seed_ids["prod_a"], requested_price=55550.0)
    _approve(admin_client, p_a["id"])

    p_b = _create_pra(admin_client, cust, seed_ids["prod_b"], requested_price=55551.0)
    _approve(admin_client, p_b["id"])

    d_a = _get(admin_client, p_a["id"])
    assert d_a["status"] == "approved", (
        f"prod_a approval must remain approved when prod_b's is approved: got {d_a['status']}"
    )


def test_order_scope_not_superseded_and_does_not_supersede(
    admin_client: requests.Session, seed_ids: Dict[str, Any]
) -> None:
    """order-scope approvals must not be affected by supersede logic:
      (a) an approved order-scope must NOT be superseded when a later standing
          rule (same tuple) is approved;
      (b) approving an order-scope must NOT set superseded_count on standing
          rules (superseded_count==0 in audit for order-scope approve)."""
    cust = seed_ids["cust_a"]
    prod = seed_ids["prod_a"]

    # (a) Create an approved order-scope first (so_id required-ish? optional)
    p_order = _create_pra(
        admin_client, cust, prod, requested_price=66660.0, scope="order",
    )
    _approve(admin_client, p_order["id"])

    # Then approve a standing rule for same tuple
    p_std = _create_pra(admin_client, cust, prod, requested_price=66661.0, scope="standing")
    _approve(admin_client, p_std["id"])

    d_order = _get(admin_client, p_order["id"])
    assert d_order["status"] == "approved", (
        f"order-scope approval must remain approved (not superseded), got {d_order['status']}"
    )

    # (b) audit of order-scope approve → superseded_count == 0
    log = _find_audit(admin_client, "price_approval_approved", p_order["id"])
    assert log is not None
    after = log.get("after") or {}
    assert "superseded_count" in after
    assert int(after["superseded_count"]) == 0, (
        f"order-scope approve must not supersede others, got {after['superseded_count']}"
    )
