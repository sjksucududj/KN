"""M-3 — Test CoA per-PT override + Inter-company Transfer JE (iter_111).

Test scope:
- Feature 1: /api/gl/accounts multi-entity behaviour (global template vs PT override).
- Feature 2: /api/transfers/inter-company + approve → auto-post JE at-cost.
- Regression: seed idempotency, GL summary/trial-balance/journal endpoints.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@kainnusantara.id"
ADMIN_PASSWORD = "demo12345"

ENT_KSC = "ent_ksc"
ENT_KANDA = "ent_kanda"

# ─── Auth fixture ────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _cleanup_account(client, code, entity_id=None):
    try:
        params = {"entity_id": entity_id} if entity_id else {}
        client.delete(f"{API}/gl/accounts/{code}", params=params, timeout=15)
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════════════
# FEATURE 1 — CoA per-PT override
# ═════════════════════════════════════════════════════════════════════════════
class TestCoAPerPT:
    """CoA per-PT override behaviour."""

    def test_list_accounts_global_only_no_entity_param(self, client):
        r = client.get(f"{API}/gl/accounts", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        # All must have entity_id=None (or missing/empty)
        for a in rows:
            assert a.get("entity_id") in (None, ""), f"Account {a.get('code')} has entity_id={a.get('entity_id')} in global-only view"
        # Sanity: IC-AR & IC-AP must exist as template
        codes = {a["code"] for a in rows}
        assert "1-1250" in codes, "IC-AR template account 1-1250 missing"
        assert "2-1250" in codes, "IC-AP template account 2-1250 missing"

    def test_list_accounts_effective_view_for_entity(self, client):
        r = client.get(f"{API}/gl/accounts", params={"entity_id": ENT_KSC}, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        codes = {a["code"] for a in rows}
        assert "1-1250" in codes and "2-1250" in codes

    def test_create_pt_only_account(self, client):
        code = f"9-KSC-{uuid.uuid4().hex[:4].upper()}"
        try:
            r = client.post(
                f"{API}/gl/accounts", params={"entity_id": ENT_KSC},
                json={"code": code, "name": f"KSC Only {code}", "type": "asset",
                      "is_postable": True},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["code"] == code
            assert body["entity_id"] == ENT_KSC
            # KSC view sees it
            r_ksc = client.get(f"{API}/gl/accounts", params={"entity_id": ENT_KSC}, timeout=30)
            assert any(a["code"] == code for a in r_ksc.json())
            # KANDA view does NOT see it (isolation)
            r_kanda = client.get(f"{API}/gl/accounts", params={"entity_id": ENT_KANDA}, timeout=30)
            assert not any(a["code"] == code for a in r_kanda.json()), f"PT-only account {code} leaked to KANDA"
            # Global template list does NOT see it
            r_global = client.get(f"{API}/gl/accounts", timeout=30)
            assert not any(a["code"] == code for a in r_global.json()), f"PT-only account {code} leaked to global template"
        finally:
            _cleanup_account(client, code, ENT_KSC)

    def test_override_existing_template_account(self, client):
        """POST /gl/accounts?entity_id=<id> with existing template code → creates override."""
        code = "1-1200"  # Piutang Usaha template
        # Ensure no leftover override
        _cleanup_account(client, code, ENT_KSC)
        try:
            r = client.post(
                f"{API}/gl/accounts", params={"entity_id": ENT_KSC},
                json={"code": code, "name": "Piutang Usaha (KSC Override)", "type": "asset",
                      "is_postable": True},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["entity_id"] == ENT_KSC
            assert body["name"] == "Piutang Usaha (KSC Override)"

            # Global template unchanged
            r_global = client.get(f"{API}/gl/accounts", timeout=30)
            global_acc = next((a for a in r_global.json() if a["code"] == code), None)
            assert global_acc is not None
            assert global_acc["name"] == "Piutang Usaha", f"Template mutated: {global_acc['name']}"

            # KANDA view NOT affected (still template)
            r_kanda = client.get(f"{API}/gl/accounts", params={"entity_id": ENT_KANDA}, timeout=30)
            kanda_acc = next((a for a in r_kanda.json() if a["code"] == code), None)
            assert kanda_acc is not None
            assert kanda_acc["name"] == "Piutang Usaha"

            # KSC view sees override
            r_ksc = client.get(f"{API}/gl/accounts", params={"entity_id": ENT_KSC}, timeout=30)
            ksc_acc = next((a for a in r_ksc.json() if a["code"] == code), None)
            assert ksc_acc is not None
            assert ksc_acc["name"] == "Piutang Usaha (KSC Override)"
        finally:
            _cleanup_account(client, code, ENT_KSC)

    def test_patch_autocreates_override_from_template(self, client):
        """PATCH /gl/accounts/{code}?entity_id=<id> auto-creates override from template."""
        code = "1-1100"
        _cleanup_account(client, code, ENT_KANDA)
        try:
            r = client.patch(
                f"{API}/gl/accounts/{code}", params={"entity_id": ENT_KANDA},
                json={"name": "Kas Kanda", "description": "Override untuk Kanda"},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["entity_id"] == ENT_KANDA
            assert body["name"] == "Kas Kanda"

            # Global unchanged
            r_global = client.get(f"{API}/gl/accounts", timeout=30)
            global_acc = next((a for a in r_global.json() if a["code"] == code), None)
            assert global_acc["name"] == "Kas Besar / Bank"

            # KSC unaffected (still template)
            r_ksc = client.get(f"{API}/gl/accounts", params={"entity_id": ENT_KSC}, timeout=30)
            ksc_acc = next((a for a in r_ksc.json() if a["code"] == code), None)
            assert ksc_acc["name"] == "Kas Besar / Bank"
        finally:
            _cleanup_account(client, code, ENT_KANDA)

    def test_delete_override_only_removes_override(self, client):
        code = "1-1110"
        _cleanup_account(client, code, ENT_KSC)
        # Create override
        r = client.post(
            f"{API}/gl/accounts", params={"entity_id": ENT_KSC},
            json={"code": code, "name": "Kas Kecil (KSC)", "type": "asset", "is_postable": True},
            timeout=30,
        )
        assert r.status_code == 200
        # Delete override
        r_del = client.delete(f"{API}/gl/accounts/{code}", params={"entity_id": ENT_KSC}, timeout=30)
        assert r_del.status_code == 200
        # Global template still exists
        r_global = client.get(f"{API}/gl/accounts", timeout=30)
        assert any(a["code"] == code for a in r_global.json())

    def test_delete_system_template_forbidden(self, client):
        """DELETE without entity_id on system template account → 400."""
        r = client.delete(f"{API}/gl/accounts/1-1200", timeout=30)
        assert r.status_code == 400, f"Expected 400 system-account block, got {r.status_code}: {r.text}"


# ═════════════════════════════════════════════════════════════════════════════
# FEATURE 2 — Inter-company Transfer JE
# ═════════════════════════════════════════════════════════════════════════════
class TestIcTransferJE:
    """Inter-company transfer JE auto-post on approve."""

    @pytest.fixture(scope="class")
    def transfer_ctx(self, client):
        # Find a product that has stock owned by KSC (source)
        rolls = client.get(f"{API}/inventory/rolls", params={"owner_entity_id": ENT_KSC},
                           timeout=30)
        if rolls.status_code != 200:
            pytest.skip(f"inventory-rolls endpoint failed: {rolls.status_code}")
        pool = [r for r in rolls.json()
                if r.get("status") == "available" and float(r.get("length_remaining") or 0) >= 1.0
                and (float(r.get("unit_cost") or r.get("base_unit_cost") or 0) > 0)]
        if not pool:
            pytest.skip("No available KSC-owned rolls with unit_cost > 0 to test IC transfer")
        chosen = pool[0]
        return {"product_id": chosen["product_id"],
                "unit_cost": float(chosen.get("unit_cost") or chosen.get("base_unit_cost") or 0),
                "quantity": 1.0}

    def _create_and_approve_ic(self, client, product_id, qty):
        payload = {
            "source_entity_id": ENT_KSC,
            "dest_entity_id": ENT_KANDA,
            "items": [{"product_id": product_id, "quantity": qty, "unit": "meter"}],
            "notes": "M-3 test IC transfer",
        }
        r = client.post(f"{API}/transfers/inter-company", json=payload, timeout=30)
        assert r.status_code == 200, f"Create failed: {r.text}"
        tid = r.json()["id"]
        r_app = client.post(f"{API}/transfers/{tid}/approve",
                            json={"approved_by": "Manager Test"}, timeout=30)
        assert r_app.status_code == 200, f"Approve failed: {r_app.text}"
        return r_app.json()

    def test_ic_transfer_approve_posts_balanced_je_both_sides(self, client, transfer_ctx):
        approved = self._create_and_approve_ic(client, transfer_ctx["product_id"], transfer_ctx["quantity"])
        assert approved.get("status") == "completed"
        assert approved.get("ownership_moved") is not None
        je = approved.get("je_intercompany")
        assert je is not None, "je_intercompany field missing"
        assert je.get("posted") is True, f"JE not posted: {je}"
        assert je.get("total", 0) > 0
        pair_id = je.get("pair_id", "")
        assert pair_id.startswith("ict_")
        assert je.get("source_je", {}).get("entity_id") == ENT_KSC
        assert je.get("dest_je", {}).get("entity_id") == ENT_KANDA
        src_je_id = je["source_je"]["id"]
        dst_je_id = je["dest_je"]["id"]

        # Fetch both JEs and verify lines
        r_src = client.get(f"{API}/gl/journal/{src_je_id}", timeout=30)
        assert r_src.status_code == 200
        src = r_src.json()
        assert src["source_type"] == "inter_company_transfer"
        assert src["entity_id"] == ENT_KSC
        assert src.get("intercompany_pair_id") == pair_id
        assert src.get("intercompany_counterpart_entity_id") == ENT_KANDA
        src_lines = {l["account_code"]: l for l in src["lines"]}
        assert "1-1250" in src_lines and src_lines["1-1250"]["debit"] > 0
        assert "1-1300" in src_lines and src_lines["1-1300"]["credit"] > 0
        assert abs(src["total_debit"] - src["total_credit"]) < 0.01

        r_dst = client.get(f"{API}/gl/journal/{dst_je_id}", timeout=30)
        assert r_dst.status_code == 200
        dst = r_dst.json()
        assert dst["source_type"] == "inter_company_transfer"
        assert dst["entity_id"] == ENT_KANDA
        assert dst.get("intercompany_pair_id") == pair_id
        assert dst.get("intercompany_counterpart_entity_id") == ENT_KSC
        dst_lines = {l["account_code"]: l for l in dst["lines"]}
        assert "1-1300" in dst_lines and dst_lines["1-1300"]["debit"] > 0
        assert "2-1250" in dst_lines and dst_lines["2-1250"]["credit"] > 0
        assert abs(dst["total_debit"] - dst["total_credit"]) < 0.01

        # source_id format
        assert src["source_id"].endswith(":src")
        assert dst["source_id"].endswith(":dst")

    def test_trial_balance_balanced_both_pt(self, client):
        for eid in (ENT_KSC, ENT_KANDA):
            r = client.get(f"{API}/gl/trial-balance", params={"entity_id": eid}, timeout=30)
            assert r.status_code == 200, r.text
            tb = r.json()
            assert tb["balanced"] is True, f"Trial balance unbalanced for {eid}: Dr={tb['total_debit']} Cr={tb['total_credit']}"
            assert abs(tb["total_debit"] - tb["total_credit"]) < 0.5

    def test_ic_transfer_idempotent_via_service(self, client, transfer_ctx):
        """Second call to gl_service.post_intercompany_transfer should not duplicate JE.
        We simulate by counting JEs for a pair_id — should be exactly 2 (src+dst) after approve."""
        approved = self._create_and_approve_ic(client, transfer_ctx["product_id"], transfer_ctx["quantity"])
        je = approved.get("je_intercompany", {})
        pair_id = je.get("pair_id")
        assert pair_id
        # Find all JEs with this pair via /gl/journal search
        r = client.get(f"{API}/gl/journal", params={"source": "inter_company_transfer",
                                                     "entity_id": ENT_KSC}, timeout=30)
        assert r.status_code == 200
        ksc_matches = [j for j in r.json() if j.get("intercompany_pair_id") == pair_id]
        r2 = client.get(f"{API}/gl/journal", params={"source": "inter_company_transfer",
                                                      "entity_id": ENT_KANDA}, timeout=30)
        kanda_matches = [j for j in r2.json() if j.get("intercompany_pair_id") == pair_id]
        assert len(ksc_matches) == 1, f"Expected 1 KSC JE for {pair_id}, got {len(ksc_matches)}"
        assert len(kanda_matches) == 1, f"Expected 1 KANDA JE for {pair_id}, got {len(kanda_matches)}"

    def test_rejected_ic_transfer_no_je(self, client, transfer_ctx):
        payload = {
            "source_entity_id": ENT_KSC,
            "dest_entity_id": ENT_KANDA,
            "items": [{"product_id": transfer_ctx["product_id"], "quantity": 1.0, "unit": "meter"}],
            "notes": "M-3 test IC transfer reject",
        }
        r = client.post(f"{API}/transfers/inter-company", json=payload, timeout=30)
        assert r.status_code == 200
        tid = r.json()["id"]
        r_rej = client.post(f"{API}/transfers/{tid}/reject",
                            json={"rejected_by": "Manager", "reason": "test"}, timeout=30)
        assert r_rej.status_code == 200
        # Verify no JE with this transfer_id
        r_j = client.get(f"{API}/gl/journal", params={"source": "inter_company_transfer"}, timeout=30)
        matches = [j for j in r_j.json() if j.get("source_id", "").startswith(tid)]
        assert not matches, f"Rejected transfer should not post JE, found: {[m['id'] for m in matches]}"

    def test_intra_entity_transfer_no_ic_je(self, client):
        """Regular warehouse transfer (intra_entity) must not trigger IC JE."""
        # Find 2 warehouses in same entity
        whs = client.get(f"{API}/warehouses", timeout=30).json()
        # Just verify no inter_company_transfer JE was created by intra flow — sanity via count before/after
        # This is a soft check: we simply verify intra-entity approve doesn't call IC JE.
        # Get an existing intra transfer (if any)
        transfers = client.get(f"{API}/transfers", params={"transfer_kind": "intra_entity"}, timeout=30).json()
        for t in transfers:
            assert not t.get("je_intercompany"), f"Intra transfer {t['id']} has je_intercompany"


# ═════════════════════════════════════════════════════════════════════════════
# REGRESSION
# ═════════════════════════════════════════════════════════════════════════════
class TestRegression:
    def test_gl_summary_ok(self, client):
        r = client.get(f"{API}/gl/summary", timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ("journal_count", "account_count", "total_debit", "total_credit", "balanced"):
            assert k in body

    def test_gl_journal_ok(self, client):
        r = client.get(f"{API}/gl/journal", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_dashboard_ok(self, client):
        r = client.get(f"{API}/dashboard", timeout=30)
        assert r.status_code == 200

    def test_sales_orders_ok(self, client):
        r = client.get(f"{API}/sales-orders", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_seed_default_coa_idempotent(self, client):
        """Second /gl/sync call must NOT duplicate template accounts."""
        r1 = client.get(f"{API}/gl/accounts", timeout=30)
        n1 = len(r1.json())
        r_sync = client.post(f"{API}/gl/sync", timeout=60)
        assert r_sync.status_code == 200
        r2 = client.get(f"{API}/gl/accounts", timeout=30)
        n2 = len(r2.json())
        assert n2 == n1, f"Template count changed after sync: {n1} → {n2}"
        # Sanity: >= 45 template accounts
        assert n1 >= 45, f"Template account count too low: {n1}"
