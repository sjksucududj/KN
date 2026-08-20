"""F1a + Consolidation backend regression tests.

Covers:
- GET /api/gl/consolidation (admin) + 403 for sales/warehouse
- F1a Pricelist GRID (entity isolation, fallback global)
- CREATE entity price → effective_price=entity for that entity only
- HISTORI scheduled vs current; resolver picks current
- SO integration uses entity price (or global fallback)
- PATCH/DELETE pricelist + RBAC (sales view-only)
- Regression: products has global_price+price_source; GL endpoints still 200
"""
import os
import time
import pytest
import requests

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL missing"
    return v.rstrip("/")

BASE = _load_base()
KSC = "ent_ksc"
KANDA = "ent_kanda"
SKU = "BTK-MEGA-001"

CREATED_PRICES: list = []
CREATED_ORDERS: list = []


def _login(email, password="demo12345"):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _h(token, eid=None):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if eid:
        h["X-Entity-Id"] = eid
    return h


@pytest.fixture(scope="module")
def tokens():
    return {
        "admin": _login("admin@kainnusantara.id"),
        "manager": _login("manager@kainnusantara.id"),
        "sales": _login("sales@kainnusantara.id"),
        "warehouse": _login("warehouse@kainnusantara.id"),
    }


@pytest.fixture(scope="module")
def product_id(tokens):
    r = requests.get(f"{BASE}/api/products", headers=_h(tokens["admin"], KSC), timeout=20)
    assert r.status_code == 200, r.text
    products = r.json()
    target = next((p for p in products if p.get("sku") == SKU), None)
    assert target, f"product {SKU} not found"
    return target["id"]


@pytest.fixture(scope="module", autouse=True)
def cleanup(tokens):
    yield
    # deactivate created prices
    for pid in CREATED_PRICES:
        try:
            requests.delete(f"{BASE}/api/pricelist/{pid}", headers=_h(tokens["admin"], KSC), timeout=15)
        except Exception:
            pass
    # cancel created SO
    for soid in CREATED_ORDERS:
        try:
            requests.post(f"{BASE}/api/sales-orders/{soid}/cancel", headers=_h(tokens["admin"], KSC), timeout=15)
        except Exception:
            pass


# ─── Consolidation ───────────────────────────────────────────────────────────
class TestConsolidation:
    def test_admin_consolidation_shape(self, tokens):
        r = requests.get(f"{BASE}/api/gl/consolidation", headers=_h(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "entities" in data and "consolidated" in data
        entities = data["entities"]
        assert isinstance(entities, list) and len(entities) >= 2
        for e in entities:
            for k in ["revenue", "cogs", "opex", "net_income", "net_margin",
                      "assets", "liabilities", "equity_total", "cash", "ar",
                      "ap", "journal_count", "balanced"]:
                assert k in e, f"missing field {k} in entity {e.get('entity_id')}"
        cons = data["consolidated"]
        # sum check
        for f in ["revenue", "cogs", "opex", "net_income", "assets", "liabilities",
                  "equity_total", "cash", "ar", "ap", "journal_count"]:
            s = round(sum(float(x.get(f, 0) or 0) for x in entities), 2)
            c = round(float(cons.get(f, 0) or 0), 2)
            assert abs(s - c) < 0.5, f"consolidated.{f} mismatch sum={s} cons={c}"

    def test_sales_forbidden(self, tokens):
        r = requests.get(f"{BASE}/api/gl/consolidation", headers=_h(tokens["sales"]), timeout=20)
        assert r.status_code == 403, r.text

    def test_warehouse_forbidden(self, tokens):
        r = requests.get(f"{BASE}/api/gl/consolidation", headers=_h(tokens["warehouse"]), timeout=20)
        assert r.status_code == 403, r.text


# ─── F1a Pricelist GRID ──────────────────────────────────────────────────────
class TestPricelistGrid:
    def test_grid_ksc_default_global(self, tokens, product_id):
        r = requests.get(f"{BASE}/api/pricelist?entity_id={KSC}", headers=_h(tokens["admin"]), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rows" in data and "count" in data
        row = next((x for x in data["rows"] if x["product_id"] == product_id), None)
        assert row
        for k in ["global_price", "effective_price", "price_source", "has_entity_price"]:
            assert k in row
        # initially: should be global (we haven't created any KSC override yet in this run)
        # NOTE: previous test runs may leave residue; not asserting exact source here.

    def test_grid_kanda_isolated(self, tokens, product_id):
        r = requests.get(f"{BASE}/api/pricelist?entity_id={KANDA}", headers=_h(tokens["admin"]), timeout=20)
        assert r.status_code == 200
        assert any(x["product_id"] == product_id for x in r.json()["rows"])


# ─── CREATE harga + isolation ────────────────────────────────────────────────
class TestCreatePrice:
    def test_create_then_grid_shows_entity_only_for_ksc(self, tokens, product_id):
        payload = {"product_id": product_id, "sell_price": 199000,
                   "valid_from": "", "valid_until": "", "note": "TEST_F1a"}
        r = requests.post(f"{BASE}/api/pricelist", json=payload,
                          headers=_h(tokens["admin"], KSC), timeout=20)
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec["entity_id"] == KSC
        assert rec["sell_price"] == 199000
        CREATED_PRICES.append(rec["id"])

        # KSC grid → entity
        g = requests.get(f"{BASE}/api/pricelist?entity_id={KSC}",
                         headers=_h(tokens["admin"]), timeout=20).json()
        row = next(x for x in g["rows"] if x["product_id"] == product_id)
        assert row["price_source"] == "entity"
        assert row["effective_price"] == 199000
        assert row["has_entity_price"] is True

        # KANDA grid → global (isolated)
        g2 = requests.get(f"{BASE}/api/pricelist?entity_id={KANDA}",
                          headers=_h(tokens["admin"]), timeout=20).json()
        row2 = next(x for x in g2["rows"] if x["product_id"] == product_id)
        assert row2["price_source"] == "global"
        assert row2["effective_price"] == row2["global_price"]


# ─── HISTORI / scheduled ──────────────────────────────────────────────────────
class TestHistory:
    def test_scheduled_not_used_yet(self, tokens, product_id):
        # Create scheduled price 1 year in future
        future = "2099-01-01"
        payload = {"product_id": product_id, "sell_price": 250000,
                   "valid_from": future, "valid_until": "", "note": "TEST_scheduled"}
        r = requests.post(f"{BASE}/api/pricelist", json=payload,
                          headers=_h(tokens["admin"], KSC), timeout=20)
        assert r.status_code == 200, r.text
        rec = r.json()
        CREATED_PRICES.append(rec["id"])
        assert rec["effective_status"] == "scheduled"

        # records list
        rec_url = f"{BASE}/api/pricelist/records?product_id={product_id}&entity_id={KSC}"
        rr = requests.get(rec_url, headers=_h(tokens["admin"]), timeout=20)
        assert rr.status_code == 200, rr.text
        recs = rr.json()
        statuses = {r["id"]: r["effective_status"] for r in recs}
        assert statuses.get(rec["id"]) == "scheduled"

        # grid still uses current (199000 from previous test), not 250000
        g = requests.get(f"{BASE}/api/pricelist?entity_id={KSC}",
                         headers=_h(tokens["admin"]), timeout=20).json()
        row = next(x for x in g["rows"] if x["product_id"] == product_id)
        assert row["effective_price"] != 250000, "scheduled price must not be active yet"


# ─── SO integration ──────────────────────────────────────────────────────────
class TestSOIntegration:
    @staticmethod
    def _pick_customer(token, eid):
        r = requests.get(f"{BASE}/api/customers", headers=_h(token, eid), timeout=20)
        assert r.status_code == 200
        rows = r.json()
        rows = rows if isinstance(rows, list) else rows.get("customers", [])
        for c in rows:
            if (c.get("addresses") or []) and (c.get("entity_id") in (eid, None, "")):
                return c
        return rows[0] if rows else None

    def test_so_uses_entity_price_for_ksc(self, tokens, product_id):
        cust = self._pick_customer(tokens["admin"], KSC)
        assert cust, "no customer in ksc"
        addr_id = (cust.get("addresses") or [{}])[0].get("id", "")
        payload = {
            "customer_id": cust["id"],
            "shipping_address_id": addr_id,
            "entity_id": KSC,
            "sales_name": "TEST_F1a",
            "shipment_policy": "all_or_nothing",
            "allow_backorder": True,
            "confirm_mixed_lot": True,
            "items": [{"product_id": product_id, "quantity": 1, "unit": "meter"}],
        }
        r = requests.post(f"{BASE}/api/sales-orders", json=payload,
                          headers=_h(tokens["admin"], KSC), timeout=30)
        assert r.status_code == 200, r.text
        so = r.json()
        CREATED_ORDERS.append(so["id"])
        item = so["items"][0]
        # KSC price = 199000 (set in TestCreatePrice). global = 185000.
        assert abs(item["price"] - 199000) < 0.01, f"expected entity price 199000, got {item['price']}"

    def test_so_uses_global_for_kanda(self, tokens, product_id):
        cust = self._pick_customer(tokens["admin"], KANDA)
        assert cust, "no customer in kanda"
        addr_id = (cust.get("addresses") or [{}])[0].get("id", "")
        payload = {
            "customer_id": cust["id"],
            "shipping_address_id": addr_id,
            "entity_id": KANDA,
            "sales_name": "TEST_F1a",
            "shipment_policy": "all_or_nothing",
            "allow_backorder": True,
            "confirm_mixed_lot": True,
            "items": [{"product_id": product_id, "quantity": 1, "unit": "meter"}],
        }
        r = requests.post(f"{BASE}/api/sales-orders", json=payload,
                          headers=_h(tokens["admin"], KANDA), timeout=30)
        assert r.status_code == 200, r.text
        so = r.json()
        CREATED_ORDERS.append(so["id"])
        item = so["items"][0]
        # global = 185000
        assert abs(item["price"] - 185000) < 0.01, f"expected global 185000, got {item['price']}"


# ─── PATCH / DELETE / RBAC ───────────────────────────────────────────────────
class TestPatchDeleteRBAC:
    def test_patch_price(self, tokens, product_id):
        # find KSC current price record
        rr = requests.get(f"{BASE}/api/pricelist/records?product_id={product_id}&entity_id={KSC}",
                          headers=_h(tokens["admin"]), timeout=20).json()
        cur = next((x for x in rr if x.get("effective_status") == "current"), None)
        assert cur, "no current price to patch"
        r = requests.patch(f"{BASE}/api/pricelist/{cur['id']}",
                           json={"sell_price": 210000}, headers=_h(tokens["admin"], KSC), timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["sell_price"] == 210000

    def test_delete_falls_back_to_global(self, tokens, product_id):
        # Create a fresh price for KANDA, then delete, expect fallback
        payload = {"product_id": product_id, "sell_price": 222000,
                   "valid_from": "", "valid_until": "", "note": "TEST_delete"}
        rc = requests.post(f"{BASE}/api/pricelist", json=payload,
                           headers=_h(tokens["admin"], KANDA), timeout=20)
        assert rc.status_code == 200, rc.text
        pid = rc.json()["id"]
        CREATED_PRICES.append(pid)

        # verify entity
        g = requests.get(f"{BASE}/api/pricelist?entity_id={KANDA}",
                         headers=_h(tokens["admin"]), timeout=20).json()
        row = next(x for x in g["rows"] if x["product_id"] == product_id)
        assert row["price_source"] == "entity"

        # delete
        rd = requests.delete(f"{BASE}/api/pricelist/{pid}",
                             headers=_h(tokens["admin"], KANDA), timeout=20)
        assert rd.status_code == 200, rd.text

        # back to global
        g2 = requests.get(f"{BASE}/api/pricelist?entity_id={KANDA}",
                          headers=_h(tokens["admin"]), timeout=20).json()
        row2 = next(x for x in g2["rows"] if x["product_id"] == product_id)
        assert row2["price_source"] == "global"

    def test_sales_rbac_view_only(self, tokens, product_id):
        # sales can GET
        r = requests.get(f"{BASE}/api/pricelist?entity_id={KSC}",
                         headers=_h(tokens["sales"]), timeout=20)
        assert r.status_code == 200, r.text
        # sales cannot POST
        rp = requests.post(f"{BASE}/api/pricelist",
                           json={"product_id": product_id, "sell_price": 100000,
                                 "valid_from": "", "valid_until": "", "note": "x"},
                           headers=_h(tokens["sales"], KSC), timeout=20)
        assert rp.status_code == 403, rp.text
        # sales cannot DELETE arbitrary id
        rd = requests.delete(f"{BASE}/api/pricelist/epr_nonexistent",
                             headers=_h(tokens["sales"], KSC), timeout=20)
        assert rd.status_code == 403, rd.text


# ─── Regression ──────────────────────────────────────────────────────────────
class TestRegression:
    def test_products_has_global_price(self, tokens):
        r = requests.get(f"{BASE}/api/products", headers=_h(tokens["admin"], KSC), timeout=20)
        assert r.status_code == 200
        p = r.json()[0]
        assert "global_price" in p
        assert "price_source" in p

    def test_so_list_ok(self, tokens):
        r = requests.get(f"{BASE}/api/sales-orders", headers=_h(tokens["admin"], KSC), timeout=20)
        assert r.status_code == 200

    def test_gl_trial_balance_ok(self, tokens):
        r = requests.get(f"{BASE}/api/gl/trial-balance", headers=_h(tokens["admin"], KSC), timeout=20)
        assert r.status_code == 200

    def test_gl_summary_ok(self, tokens):
        r = requests.get(f"{BASE}/api/gl/summary", headers=_h(tokens["admin"], KSC), timeout=20)
        assert r.status_code == 200
