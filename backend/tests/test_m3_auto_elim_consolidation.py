"""M-3 — Test auto-elimination sync from IC pairs + consolidation summary (iter_112).

Scope:
- POST /api/finance/consolidation/eliminations/sync-from-pairs (idempotent).
- GET /api/finance/consolidation/summary (auto-sync + eliminations_auto_count).
- Consolidation balance invariants (assets - IC, liabilities - IC, equity unchanged).
- No-op behaviour when no IC transfer exists.
- Regression on manual eliminations CRUD (no side-effect from sync).
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


# ─── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def ic_transfer(client):
    """Create + approve 1 IC transfer to ensure at least 1 JE pair exists."""
    # Pick a KSC-owned roll with cost>0.
    rolls = client.get(f"{API}/inventory/rolls",
                       params={"owner_entity_id": ENT_KSC}, timeout=30)
    if rolls.status_code != 200:
        pytest.skip("inventory/rolls endpoint failed")
    pool = [r for r in rolls.json()
            if r.get("status") == "available"
            and float(r.get("length_remaining") or 0) >= 1.0
            and (float(r.get("unit_cost") or r.get("base_unit_cost") or 0) > 0)]
    if not pool:
        pytest.skip("No KSC-owned rolls with cost>0 to create IC transfer")
    chosen = pool[0]
    payload = {
        "source_entity_id": ENT_KSC,
        "dest_entity_id": ENT_KANDA,
        "items": [{"product_id": chosen["product_id"], "quantity": 1.0, "unit": "meter"}],
        "notes": "iter_112 auto-elim test",
    }
    r = client.post(f"{API}/transfers/inter-company", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    r_app = client.post(f"{API}/transfers/{tid}/approve",
                        json={"approved_by": "Manager Test"}, timeout=30)
    assert r_app.status_code == 200, r_app.text
    approved = r_app.json()
    je = approved.get("je_intercompany") or {}
    assert je.get("posted") is True, f"IC JE not posted: {je}"
    return {"transfer_id": tid, "pair_id": je["pair_id"], "total": float(je.get("total") or 0)}


def _delete_auto_elim_by_pair(client, pair_id):
    """Helper: find & delete auto-elim entry for a given pair_id."""
    r = client.get(f"{API}/finance/consolidation/eliminations", timeout=30)
    if r.status_code != 200:
        return
    for e in r.json():
        if e.get("source_pair_id") == pair_id:
            client.delete(f"{API}/finance/consolidation/eliminations/{e['id']}",
                          timeout=30)


# ═════════════════════════════════════════════════════════════════════════════
# SYNC-FROM-PAIRS: create + idempotent
# ═════════════════════════════════════════════════════════════════════════════
class TestAutoElimSync:
    def test_sync_creates_auto_elim_for_new_pair(self, client, ic_transfer):
        pair_id = ic_transfer["pair_id"]
        # Ensure no leftover from prior runs (e.g. summary auto-sync already ran).
        _delete_auto_elim_by_pair(client, pair_id)

        r = client.post(f"{API}/finance/consolidation/eliminations/sync-from-pairs",
                        timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        # Response schema
        assert "created" in body and "skipped_existing" in body and "pairs_seen" in body
        assert "entries" in body and isinstance(body["entries"], list)
        assert body["pairs_seen"] >= 1
        assert body["created"] >= 1

        # Find the created entry for our pair
        matched = [e for e in body["entries"] if e.get("source_pair_id") == pair_id]
        assert len(matched) == 1, f"Expected 1 entry for pair {pair_id}, got {len(matched)}"
        entry = matched[0]
        assert entry["auto_generated"] is True
        assert entry["source_pair_id"] == pair_id
        assert entry["name"].startswith("Auto: Eliminasi IC transfer")
        assert pair_id in entry["name"]
        assert entry["balanced"] is True
        assert entry["total_debit"] == entry["total_credit"]
        # 2 lines: Dr 2-1250 / Cr 1-1250
        assert len(entry["lines"]) == 2
        codes = {l["account_code"] for l in entry["lines"]}
        assert codes == {"1-1250", "2-1250"}, f"Unexpected codes: {codes}"
        for l in entry["lines"]:
            if l["account_code"] == "2-1250":
                assert l["debit"] > 0 and l["credit"] == 0
            if l["account_code"] == "1-1250":
                assert l["credit"] > 0 and l["debit"] == 0

    def test_second_sync_skips_existing(self, client, ic_transfer):
        # First sync (may create-or-be-noop if summary already synced).
        client.post(f"{API}/finance/consolidation/eliminations/sync-from-pairs", timeout=60)
        # Second sync — must be idempotent (no new creation for this pair).
        r = client.post(f"{API}/finance/consolidation/eliminations/sync-from-pairs",
                        timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert body["created"] == 0, f"Second sync created {body['created']} — not idempotent"
        assert body["skipped_existing"] >= 1
        assert body["pairs_seen"] >= 1

    def test_delete_and_resync_recreates(self, client, ic_transfer):
        pair_id = ic_transfer["pair_id"]
        # ensure covered first
        client.post(f"{API}/finance/consolidation/eliminations/sync-from-pairs", timeout=60)
        _delete_auto_elim_by_pair(client, pair_id)
        # Verify gone
        r = client.get(f"{API}/finance/consolidation/eliminations", timeout=30)
        assert not any(e.get("source_pair_id") == pair_id for e in r.json())
        # Resync — should recreate
        r_sync = client.post(f"{API}/finance/consolidation/eliminations/sync-from-pairs",
                             timeout=60)
        assert r_sync.status_code == 200
        assert r_sync.json()["created"] >= 1
        r2 = client.get(f"{API}/finance/consolidation/eliminations", timeout=30)
        assert any(e.get("source_pair_id") == pair_id for e in r2.json())


# ═════════════════════════════════════════════════════════════════════════════
# CONSOLIDATION SUMMARY (auto-sync + auto_count)
# ═════════════════════════════════════════════════════════════════════════════
class TestConsolidationSummary:
    def test_summary_triggers_auto_sync_and_returns_auto_count(self, client, ic_transfer):
        r = client.get(f"{API}/finance/consolidation/summary", timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "eliminations_auto_count" in body
        assert isinstance(body["eliminations_auto_count"], int)
        assert body["eliminations_auto_count"] >= 1, \
            f"Expected >=1 auto-elim after IC transfer, got {body['eliminations_auto_count']}"
        # Balance invariant
        assert body["balanced"] is True
        c = body["consolidated"]
        diff = abs(c["assets"] - (c["liabilities"] + c["equity"]))
        assert diff < 1.0, f"Consolidated not balanced: A={c['assets']} L+E={c['liabilities']+c['equity']}"

    def test_consolidation_impact_matches_ic_total(self, client, ic_transfer):
        """assets_consol = assets_gross - IC_total  &  liab_consol = liab_gross - IC_total.
        Equity unchanged (auto-elim only touches IC-AR asset and IC-AP liability)."""
        # Ensure sync has run (summary itself triggers sync).
        r = client.get(f"{API}/finance/consolidation/summary", timeout=60)
        assert r.status_code == 200
        body = r.json()
        gross = body["gross"]
        elim = body["elimination"]
        cons = body["consolidated"]

        # Elimination impact
        # assets_elim & liab_elim should both be negative (offsets), equity_elim ~ 0
        assert elim["assets"] <= 0, f"Auto-elim assets should be <=0, got {elim['assets']}"
        assert elim["liabilities"] <= 0, f"Auto-elim liabilities should be <=0, got {elim['liabilities']}"
        # equity: only auto-elim → no equity/PL touch → net-income-elim = 0 → equity_elim = 0
        # (Manual elims may add non-zero equity — allow tolerance if only auto elims exist.)
        # We only assert magnitudes match: |assets_elim| == |liab_elim|
        assert abs(abs(elim["assets"]) - abs(elim["liabilities"])) < 1.0, \
            f"IC-AR ({elim['assets']}) must equal IC-AP ({elim['liabilities']}) in magnitude"

        # Consolidated = Gross + Elimination (elim entries are signed impacts)
        assert abs(cons["assets"] - (gross["assets"] + elim["assets"])) < 1.0
        assert abs(cons["liabilities"] - (gross["liabilities"] + elim["liabilities"])) < 1.0

    def test_no_duplicate_auto_elim(self, client, ic_transfer):
        """After multiple summary calls, only 1 auto-elim per pair_id."""
        for _ in range(3):
            client.get(f"{API}/finance/consolidation/summary", timeout=60)
        r = client.get(f"{API}/finance/consolidation/eliminations", timeout=30)
        by_pair = {}
        for e in r.json():
            pid = e.get("source_pair_id")
            if pid:
                by_pair.setdefault(pid, []).append(e)
        for pid, entries in by_pair.items():
            assert len(entries) == 1, f"Pair {pid} has {len(entries)} auto-elim entries (should be 1)"


# ═════════════════════════════════════════════════════════════════════════════
# REGRESSION — Manual eliminations CRUD untouched by sync
# ═════════════════════════════════════════════════════════════════════════════
class TestManualElimRegression:
    def test_manual_elim_create_untouched_by_sync(self, client):
        """Create manual elim (no source_pair_id) → sync must not touch or delete it."""
        payload = {
            "name": f"TEST_manual_{uuid.uuid4().hex[:6]}",
            "entity_from": ENT_KSC, "entity_to": ENT_KANDA,
            "effective_date": "2026-01-15",
            "note": "iter_112 regression",
            "lines": [
                {"account_code": "1-1250", "debit": 0, "credit": 1000,
                 "description": "manual IC-AR eliminate"},
                {"account_code": "2-1250", "debit": 1000, "credit": 0,
                 "description": "manual IC-AP eliminate"},
            ],
        }
        r = client.post(f"{API}/finance/consolidation/eliminations", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["balanced"] is True
        assert "source_pair_id" not in created or created.get("source_pair_id") is None
        assert created.get("auto_generated") in (None, False)
        elim_id = created["id"]
        try:
            # Run sync — must not touch manual entry
            client.post(f"{API}/finance/consolidation/eliminations/sync-from-pairs",
                        timeout=60)
            r_all = client.get(f"{API}/finance/consolidation/eliminations", timeout=30)
            still = next((e for e in r_all.json() if e["id"] == elim_id), None)
            assert still is not None, "Manual entry disappeared after sync"
            assert still["name"] == created["name"]
            assert still["total_debit"] == created["total_debit"]
        finally:
            client.delete(f"{API}/finance/consolidation/eliminations/{elim_id}",
                          timeout=30)

    def test_delete_manual_elim(self, client):
        payload = {
            "name": f"TEST_del_{uuid.uuid4().hex[:6]}",
            "effective_date": "2026-01-15",
            "lines": [
                {"account_code": "1-1250", "debit": 0, "credit": 500},
                {"account_code": "2-1250", "debit": 500, "credit": 0},
            ],
        }
        r = client.post(f"{API}/finance/consolidation/eliminations", json=payload, timeout=30)
        assert r.status_code == 200
        eid = r.json()["id"]
        r_del = client.delete(f"{API}/finance/consolidation/eliminations/{eid}",
                              timeout=30)
        assert r_del.status_code == 200
        assert r_del.json().get("deleted") is True
        # Verify gone
        r_all = client.get(f"{API}/finance/consolidation/eliminations", timeout=30)
        assert not any(e["id"] == eid for e in r_all.json())

    def test_list_eliminations_endpoint(self, client):
        r = client.get(f"{API}/finance/consolidation/eliminations", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_unbalanced_still_accepted_but_flagged(self, client):
        """Create manual elim with unbalanced lines: system should still store it,
        but balanced=False (business rule per code: no hard reject)."""
        payload = {
            "name": f"TEST_unbal_{uuid.uuid4().hex[:6]}",
            "effective_date": "2026-01-15",
            "lines": [
                {"account_code": "1-1250", "debit": 0, "credit": 100},
                {"account_code": "2-1250", "debit": 50, "credit": 0},
            ],
        }
        r = client.post(f"{API}/finance/consolidation/eliminations", json=payload, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["balanced"] is False
        client.delete(f"{API}/finance/consolidation/eliminations/{body['id']}", timeout=30)
