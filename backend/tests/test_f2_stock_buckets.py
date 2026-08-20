"""F2 — Multi-bucket Stock (Hold/Pending SO & WIP) integration tests.

Tests the additive bucket engine on top of roll-as-SSOT.
- GET /api/stock/buckets, /api/stock/holds, /api/stock/wip
- POST /api/stock/hold + /api/stock/hold/{id}/release
- POST /api/stock/wip/start + /api/stock/wip/{id}/complete
- RBAC: sales (view-only) → 403 on operations
- Owner entity scoping: sales attempting cross-entity → 403
- ATP/on_hand invariants: hold/wip are physical (on_hand stays), but ATP drops
- FEFO + split: partial-roll hold should split parent, not consume entire roll
- Teardown: release all hold + complete all wip created
"""
import os
import time
import pytest
import requests

def _load_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return (url or "").rstrip("/")


BASE_URL = _load_url()
PROD_ID = "prod_ulos_batak"
WH_JKT = "wh_jakarta"
WH_SBY = "wh_surabaya"
OWNER = "ent_ksc"

CREATED_HOLDS = []
CREATED_WIPS = []


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _login(email: str, password: str = "demo12345"):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password},
                      timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@kainnusantara.id")


@pytest.fixture(scope="module")
def warehouse_token():
    return _login("warehouse@kainnusantara.id")


@pytest.fixture(scope="module")
def manager_token():
    return _login("manager@kainnusantara.id")


@pytest.fixture(scope="module")
def sales_token():
    return _login("sales@kainnusantara.id")


def _hdr(token, entity="ent_ksc"):
    return {"Authorization": f"Bearer {token}", "X-Entity-Id": entity,
            "Content-Type": "application/json"}


def _get_bucket(token, product_id=PROD_ID, warehouse_id=None, entity="ent_ksc"):
    r = requests.get(f"{BASE_URL}/api/stock/buckets", headers=_hdr(token, entity),
                     params={"product_id": product_id}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    if not data:
        return None, None
    prod = data[0]
    wh_row = None
    if warehouse_id:
        for w in prod["warehouses"]:
            if w["warehouse_id"] == warehouse_id:
                wh_row = w
                break
    return prod, wh_row


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestBucketsBoard:
    """GET /api/stock/buckets — board structure & filter."""

    def test_get_buckets_admin_returns_products(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/stock/buckets", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) > 0
        sample = data[0]
        for k in ["product_id", "totals", "warehouses"]:
            assert k in sample
        for f in ["available_qty", "hold_qty", "wip_qty", "on_hand_qty", "atp_qty"]:
            assert f in sample["totals"]

    def test_filter_product_id(self, admin_token):
        prod, _ = _get_bucket(admin_token, PROD_ID)
        assert prod is not None
        assert prod["product_id"] == PROD_ID
        # Verify warehouse breakdown structure
        assert any(w["warehouse_id"] == WH_JKT for w in prod["warehouses"])

    def test_initial_baseline_available(self, admin_token):
        prod, wh = _get_bucket(admin_token, PROD_ID, WH_JKT)
        assert wh is not None
        # Baseline expected: wh_jakarta=95, wh_surabaya=140
        assert wh["available_qty"] >= 90, f"baseline avail jkt = {wh['available_qty']}"
        assert "owner_entity_name" in wh
        assert "warehouse_name" in wh


class TestHoldFlow:
    """POST /api/stock/hold → release_hold."""

    def test_hold_changes_balances_correctly(self, admin_token):
        prod0, wh0 = _get_bucket(admin_token, PROD_ID, WH_JKT)
        avail0 = wh0["available_qty"]
        hold0 = wh0["hold_qty"]
        on_hand0 = wh0["on_hand_qty"]
        atp0 = wh0["atp_qty"]

        qty = 10.0
        r = requests.post(f"{BASE_URL}/api/stock/hold", headers=_hdr(admin_token),
                          json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                "owner_entity_id": OWNER, "quantity": qty,
                                "reason": "TEST_hold_basic", "ref_type": "sales_order",
                                "ref_id": "SO-TEST-F2"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "hold_id" in body and body["hold_id"]
        CREATED_HOLDS.append(body["hold_id"])

        _, wh1 = _get_bucket(admin_token, PROD_ID, WH_JKT)
        assert round(wh1["available_qty"], 2) == round(avail0 - qty, 2), \
            f"available expected {avail0 - qty} got {wh1['available_qty']}"
        assert round(wh1["hold_qty"], 2) == round(hold0 + qty, 2)
        assert round(wh1["on_hand_qty"], 2) == round(on_hand0, 2), \
            "on_hand should be unchanged (hold is physical)"
        assert round(wh1["atp_qty"], 2) == round(atp0 - qty, 2), "atp must drop by hold qty"

    def test_hold_listed_with_enrichment(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/stock/holds", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200
        holds = r.json()
        assert isinstance(holds, list)
        # Match our created hold
        ours = next((h for h in holds if h["ref_id"] in CREATED_HOLDS), None)
        assert ours is not None, "Hold not present in /api/stock/holds"
        for k in ["product_name", "warehouse_name", "owner_entity_name", "quantity", "reason",
                  "ref_type", "ref_doc_id", "unit"]:
            assert k in ours, f"missing field {k}"
        assert ours["ref_doc_id"] == "SO-TEST-F2"
        assert ours["ref_type"] == "sales_order"

    def test_hold_exceeds_available_409(self, admin_token):
        _, wh = _get_bucket(admin_token, PROD_ID, WH_JKT)
        too_much = wh["available_qty"] + 5000
        r = requests.post(f"{BASE_URL}/api/stock/hold", headers=_hdr(admin_token),
                          json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                "owner_entity_id": OWNER, "quantity": too_much,
                                "reason": "TEST_overflow"}, timeout=15)
        assert r.status_code == 409, f"expected 409 got {r.status_code} {r.text}"

    def test_release_hold_restores_balance(self, admin_token):
        if not CREATED_HOLDS:
            pytest.skip("no hold to release")
        hold_id = CREATED_HOLDS[0]
        prod_b, wh_b = _get_bucket(admin_token, PROD_ID, WH_JKT)
        avail_b = wh_b["available_qty"]
        hold_b = wh_b["hold_qty"]

        r = requests.post(f"{BASE_URL}/api/stock/hold/{hold_id}/release",
                          headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("released", 0) >= 9.99

        _, wh_a = _get_bucket(admin_token, PROD_ID, WH_JKT)
        assert round(wh_a["available_qty"], 2) == round(avail_b + 10, 2), \
            f"avail not restored: {wh_a['available_qty']} vs {avail_b + 10}"
        assert round(wh_a["hold_qty"], 2) == round(hold_b - 10, 2)
        CREATED_HOLDS.remove(hold_id)


class TestSplitPartial:
    """Partial-roll hold should split, not consume an entire roll."""

    def test_partial_hold_splits_roll(self, admin_token):
        prod_b, wh_b = _get_bucket(admin_token, PROD_ID, WH_SBY)
        avail_b = wh_b["available_qty"]
        qty = 7.5  # partial value unlikely to match exact roll length
        r = requests.post(f"{BASE_URL}/api/stock/hold", headers=_hdr(admin_token),
                          json={"product_id": PROD_ID, "warehouse_id": WH_SBY,
                                "owner_entity_id": OWNER, "quantity": qty,
                                "reason": "TEST_split_partial"}, timeout=15)
        assert r.status_code == 200, r.text
        hid = r.json()["hold_id"]
        CREATED_HOLDS.append(hid)

        _, wh_a = _get_bucket(admin_token, PROD_ID, WH_SBY)
        delta = round(avail_b - wh_a["available_qty"], 2)
        assert delta == qty, f"split partial expected delta={qty} got {delta}"


class TestWipFlow:
    """WIP start + complete restores available."""

    def test_wip_start_then_complete(self, admin_token):
        prod_b, wh_b = _get_bucket(admin_token, PROD_ID, WH_JKT)
        avail_b = wh_b["available_qty"]
        wip_b = wh_b["wip_qty"]
        on_hand_b = wh_b["on_hand_qty"]
        atp_b = wh_b["atp_qty"]

        qty = 5.0
        r = requests.post(f"{BASE_URL}/api/stock/wip/start", headers=_hdr(admin_token),
                          json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                "owner_entity_id": OWNER, "quantity": qty,
                                "note": "TEST_wip_basic"}, timeout=15)
        assert r.status_code == 200, r.text
        wid = r.json()["wip_id"]
        CREATED_WIPS.append(wid)

        _, wh1 = _get_bucket(admin_token, PROD_ID, WH_JKT)
        assert round(wh1["available_qty"], 2) == round(avail_b - qty, 2)
        assert round(wh1["wip_qty"], 2) == round(wip_b + qty, 2)
        assert round(wh1["on_hand_qty"], 2) == round(on_hand_b, 2)
        assert round(wh1["atp_qty"], 2) == round(atp_b - qty, 2)

        # List wip
        rl = requests.get(f"{BASE_URL}/api/stock/wip", headers=_hdr(admin_token), timeout=15)
        assert rl.status_code == 200
        assert any(w["ref_id"] == wid for w in rl.json())

        # Complete
        rc = requests.post(f"{BASE_URL}/api/stock/wip/{wid}/complete",
                           headers=_hdr(admin_token), timeout=15)
        assert rc.status_code == 200, rc.text
        _, wh2 = _get_bucket(admin_token, PROD_ID, WH_JKT)
        assert round(wh2["available_qty"], 2) == round(avail_b, 2), "wip complete not restored"
        assert round(wh2["wip_qty"], 2) == round(wip_b, 2)
        CREATED_WIPS.remove(wid)


class TestRBAC:
    """Permissions: sales view-only; manager/warehouse can operate."""

    def test_sales_can_view_buckets(self, sales_token):
        r = requests.get(f"{BASE_URL}/api/stock/buckets", headers=_hdr(sales_token), timeout=15)
        assert r.status_code == 200

    def test_sales_cannot_hold(self, sales_token):
        r = requests.post(f"{BASE_URL}/api/stock/hold", headers=_hdr(sales_token),
                          json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                "owner_entity_id": OWNER, "quantity": 1.0,
                                "reason": "TEST_sales_rbac"}, timeout=15)
        assert r.status_code == 403, f"sales should be 403 got {r.status_code}"

    def test_sales_cannot_wip_start(self, sales_token):
        r = requests.post(f"{BASE_URL}/api/stock/wip/start", headers=_hdr(sales_token),
                          json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                "owner_entity_id": OWNER, "quantity": 1.0}, timeout=15)
        assert r.status_code == 403

    def test_warehouse_can_hold(self, warehouse_token):
        r = requests.post(f"{BASE_URL}/api/stock/hold", headers=_hdr(warehouse_token),
                          json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                "owner_entity_id": OWNER, "quantity": 2.0,
                                "reason": "TEST_warehouse_rbac"}, timeout=15)
        assert r.status_code == 200, r.text
        hid = r.json()["hold_id"]
        CREATED_HOLDS.append(hid)

    def test_manager_can_wip(self, manager_token):
        r = requests.post(f"{BASE_URL}/api/stock/wip/start", headers=_hdr(manager_token),
                          json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                "owner_entity_id": OWNER, "quantity": 2.0,
                                "note": "TEST_manager_rbac"}, timeout=15)
        assert r.status_code == 200, r.text
        wid = r.json()["wip_id"]
        CREATED_WIPS.append(wid)


class TestEntityScoping:
    """Cross-entity owner outside allowed list → 403."""

    def test_sales_cannot_hold_other_entity(self, sales_token):
        # sales home=ent_ksc; ent_kanda not allowed
        r = requests.post(f"{BASE_URL}/api/stock/hold", headers=_hdr(sales_token),
                          json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                "owner_entity_id": "ent_kanda", "quantity": 1.0,
                                "reason": "TEST_cross_entity"}, timeout=15)
        # Either 403 (permission update) OR 403 (owner not allowed)
        assert r.status_code == 403


class TestRegression:
    """Sister endpoints still respond 200 and rebuild_balance is consistent."""

    def test_inventory_balances_200(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/inventory/balances",
                         headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_status_board_200(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/inventory/status-board",
                         headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_sales_orders_200(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/sales-orders",
                         headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_products_200(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/products",
                         headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_on_hand_includes_hold_wip(self, admin_token):
        """Create hold + wip; verify on_hand stable while available drops."""
        prod_b, wh_b = _get_bucket(admin_token, PROD_ID, WH_JKT)
        on_hand_b = wh_b["on_hand_qty"]
        # hold + wip
        r1 = requests.post(f"{BASE_URL}/api/stock/hold", headers=_hdr(admin_token),
                           json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                 "owner_entity_id": OWNER, "quantity": 3.0,
                                 "reason": "TEST_inv"}, timeout=15)
        assert r1.status_code == 200
        CREATED_HOLDS.append(r1.json()["hold_id"])
        r2 = requests.post(f"{BASE_URL}/api/stock/wip/start", headers=_hdr(admin_token),
                           json={"product_id": PROD_ID, "warehouse_id": WH_JKT,
                                 "owner_entity_id": OWNER, "quantity": 4.0}, timeout=15)
        assert r2.status_code == 200
        CREATED_WIPS.append(r2.json()["wip_id"])

        _, wh_a = _get_bucket(admin_token, PROD_ID, WH_JKT)
        assert round(wh_a["on_hand_qty"], 2) == round(on_hand_b, 2), \
            f"on_hand drift: {on_hand_b} → {wh_a['on_hand_qty']}"


# ─── Final teardown: release/complete all created refs ─────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _teardown_cleanup():
    yield
    token = _login("admin@kainnusantara.id")
    for hid in list(CREATED_HOLDS):
        try:
            requests.post(f"{BASE_URL}/api/stock/hold/{hid}/release",
                          headers=_hdr(token), timeout=15)
        except Exception as e:
            print(f"cleanup hold {hid}: {e}")
    for wid in list(CREATED_WIPS):
        try:
            requests.post(f"{BASE_URL}/api/stock/wip/{wid}/complete",
                          headers=_hdr(token), timeout=15)
        except Exception as e:
            print(f"cleanup wip {wid}: {e}")
    time.sleep(0.5)
    # Sanity verify final balance
    r = requests.get(f"{BASE_URL}/api/stock/buckets", headers=_hdr(token),
                     params={"product_id": PROD_ID}, timeout=15)
    if r.status_code == 200 and r.json():
        prod = r.json()[0]
        print(f"FINAL totals: available={prod['totals']['available_qty']} "
              f"hold={prod['totals']['hold_qty']} wip={prod['totals']['wip_qty']}")
