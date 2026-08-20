"""FASE G-6 — Backend tests for Transaksi Antar Entitas (interco).

Covers: meta, summary, create (dokumen kembar), fixed_price reject,
lifecycle (ship/receive/invoice), accounts, settlements (full & partial),
GL posting invariants (INV-IC-01..05).
"""
import os
import pytest
import requests

BASE = "http://localhost:8001"
LOGIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json=LOGIN)
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def cleanup_before():
    # Clean interco collections before running tests
    import asyncio
    import sys
    sys.path.insert(0, "/app/backend")
    from db import db

    async def clean():
        for c in ["interco_transactions", "interco_accounts", "interco_settlements"]:
            await db[c].delete_many({})
        await db.journal_entries.delete_many(
            {"source_type": {"$in": ["interco_transaction", "interco_settlement"]}}
        )
    asyncio.get_event_loop().run_until_complete(clean())
    return True


# Shared state across ordered tests
STATE = {}


def test_00_cleanup(cleanup_before):
    assert cleanup_before


def test_01_login_returns_token_and_cookie(client):
    r = client.post(f"{BASE}/api/auth/login", json=LOGIN)
    assert r.status_code == 200
    d = r.json()
    assert "token" in d and d["token"]
    assert d["user"]["email"] == LOGIN["email"]
    # cookie
    assert any(c.name == "session_token" for c in r.cookies) or "session_token" in client.cookies


def test_02_meta(client):
    r = client.get(f"{BASE}/api/interco/meta")
    assert r.status_code == 200, r.text
    d = r.json()
    for key in ("statuses", "pricing_modes", "ppn_modes", "settlement_methods"):
        assert key in d and isinstance(d[key], list) and len(d[key]) > 0


def test_03_summary_initial_zero(client):
    r = client.get(f"{BASE}/api/interco/summary")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_receivable"] == 0
    assert d["total_payable"] == 0
    assert d["open_documents"] == 0


def test_04_create_transaction_at_cost_pair(client):
    payload = {
        "seller_entity_id": "ent_ksc",
        "buyer_entity_id": "ent_kanda",
        "pricing_mode": "at_cost",
        "items": [{"product_id": "prod_batik_mega", "quantity": 10,
                   "unit_price": 50000}],
        "submit_now": True,
    }
    r = client.post(f"{BASE}/api/interco/transactions", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("pair_id")
    assert d["seller"]["role"] == "seller"
    assert d["buyer"]["role"] == "buyer"
    assert d["seller"]["grand_total"] == d["buyer"]["grand_total"]
    # subtotal 500000 + PPN 11% = 555000 (ent_ksc is PKP default_tax_mode=ppn)
    assert abs(d["seller"]["subtotal"] - 500000) < 0.01
    assert abs(d["seller"]["tax_amount"] - 55000) < 0.01
    assert abs(d["seller"]["grand_total"] - 555000) < 0.01
    assert d["seller"]["status"] == "confirmed"
    STATE["pair_id"] = d["pair_id"]
    STATE["seller_id"] = d["seller"]["id"]
    STATE["buyer_id"] = d["buyer"]["id"]
    STATE["seller_number"] = d["seller"]["number"]


def test_05_fixed_price_without_contract_rejected(client):
    payload = {
        "seller_entity_id": "ent_ksc",
        "buyer_entity_id": "ent_kanda",
        # No pricing_mode → default fixed_price from config
        "items": [{"product_id": "prod_tenun_ikat", "quantity": 5}],
        "submit_now": False,
    }
    r = client.post(f"{BASE}/api/interco/transactions", json=payload)
    assert r.status_code == 400, r.text
    msg = r.json().get("detail", "")
    assert "belum punya harga internal" in msg or "kontrak" in msg.lower()


def test_06_summary_after_create(client):
    r = client.get(f"{BASE}/api/interco/summary")
    d = r.json()
    assert d["open_documents"] >= 1
    assert d["total_receivable"] > 0


def test_07_accounts_pair_balances(client):
    r = client.get(f"{BASE}/api/interco/accounts")
    assert r.status_code == 200
    rows = r.json()
    ar = [x for x in rows if x["from_entity_id"] == "ent_ksc" and x["to_entity_id"] == "ent_kanda"]
    ap = [x for x in rows if x["from_entity_id"] == "ent_kanda" and x["to_entity_id"] == "ent_ksc"]
    assert len(ar) == 1 and len(ap) == 1
    assert ar[0]["role"] == "receivable"
    assert ap[0]["role"] == "payable"
    # INV-IC-02
    assert abs(ar[0]["outstanding"] - ap[0]["outstanding"]) < 0.01
    assert abs(ar[0]["outstanding"] - 555000) < 0.01


def test_08_gl_entries_balanced_and_correct_accounts(client):
    r = client.get(f"{BASE}/api/gl/journal?source=interco_transaction&entity_id=all&limit=50")
    assert r.status_code == 200, r.text
    entries = r.json()
    # Expected: seller entry, buyer entry, cogs entry (all with source_type=interco_transaction)
    pair = STATE["pair_id"]
    ours = [e for e in entries if e.get("source_id", "").startswith(pair)]
    assert len(ours) >= 2, f"Expected >=2 GL entries for pair, got {len(ours)}"
    # Validate balance on each entry
    for e in ours:
        dr = sum(float(l.get("debit", 0)) for l in e.get("lines", []))
        cr = sum(float(l.get("credit", 0)) for l in e.get("lines", []))
        assert abs(dr - cr) < 0.01, f"Unbalanced entry {e.get('source_id')}: dr={dr} cr={cr}"

    seller_e = next((e for e in ours if e.get("source_id", "").endswith(":seller")), None)
    buyer_e = next((e for e in ours if e.get("source_id", "").endswith(":buyer")), None)
    assert seller_e and buyer_e

    def line_of(e, code):
        return next((l for l in e["lines"] if l["account_code"] == code), None)

    # Seller book: Dr 1-1250 = 555000, Cr 4-1000 = 500000, Cr 2-1200 = 55000
    ar_line = line_of(seller_e, "1-1250")
    assert ar_line and abs(float(ar_line["debit"]) - 555000) < 0.01
    rev_line = line_of(seller_e, "4-1000")
    assert rev_line and abs(float(rev_line["credit"]) - 500000) < 0.01
    ppn_out = line_of(seller_e, "2-1200")
    assert ppn_out and abs(float(ppn_out["credit"]) - 55000) < 0.01

    # Buyer book: Dr 1-1300 = 500000, Dr 1-1500 = 55000, Cr 2-1250 = 555000
    inv_line = line_of(buyer_e, "1-1300")
    assert inv_line and abs(float(inv_line["debit"]) - 500000) < 0.01
    ppn_in = line_of(buyer_e, "1-1500")
    assert ppn_in and abs(float(ppn_in["debit"]) - 55000) < 0.01
    ap_line = line_of(buyer_e, "2-1250")
    assert ap_line and abs(float(ap_line["credit"]) - 555000) < 0.01

    # INV-IC-05: PPN keluaran penjual == PPN masukan pembeli
    assert abs(float(ppn_out["credit"]) - float(ppn_in["debit"])) < 0.01


def test_09_ship_receive_invoice_cycle(client):
    sid = STATE["seller_id"]
    r = client.post(f"{BASE}/api/interco/transactions/{sid}/ship", json={"note": "kirim"})
    assert r.status_code == 200, r.text
    assert r.json()["seller"]["status"] == "shipped"

    r = client.post(f"{BASE}/api/interco/transactions/{sid}/receive", json={"note": "terima"})
    assert r.status_code == 200, r.text
    assert r.json()["seller"]["status"] == "received"

    r = client.post(f"{BASE}/api/interco/transactions/{sid}/invoice", json={"note": "faktur"})
    assert r.status_code == 200, r.text
    assert r.json()["seller"]["status"] == "invoiced"


def test_10_partial_settlement(client):
    sid = STATE["seller_id"]
    payload = {
        "payer_entity_id": "ent_kanda",
        "payee_entity_id": "ent_ksc",
        "method": "netting",
        "transactions": [{"interco_id": sid, "applied_amount": 200000}],
    }
    r = client.post(f"{BASE}/api/interco/settlements", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert abs(d["total_applied"] - 200000) < 0.01
    STATE["partial_settle_id"] = d["id"]

    # Transaction NOT yet settled
    r = client.get(f"{BASE}/api/interco/transactions/{sid}")
    doc = r.json()
    assert doc["seller"]["status"] == "invoiced"
    assert abs(doc["seller"]["settled_amount"] - 200000) < 0.01

    # Accounts outstanding reduced
    r = client.get(f"{BASE}/api/interco/accounts")
    rows = r.json()
    ar = [x for x in rows if x["from_entity_id"] == "ent_ksc" and x["to_entity_id"] == "ent_kanda"][0]
    assert abs(ar["outstanding"] - 355000) < 0.01


def test_11_full_settlement_marks_settled(client):
    sid = STATE["seller_id"]
    payload = {
        "payer_entity_id": "ent_kanda",
        "payee_entity_id": "ent_ksc",
        "method": "netting",
        "transactions": [{"interco_id": sid}],  # full remainder
    }
    r = client.post(f"{BASE}/api/interco/settlements", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert abs(d["total_applied"] - 355000) < 0.01

    # Transaction settled
    r = client.get(f"{BASE}/api/interco/transactions/{sid}")
    doc = r.json()
    assert doc["seller"]["status"] == "settled"
    assert doc["buyer"]["status"] == "settled"

    # Accounts outstanding = 0
    r = client.get(f"{BASE}/api/interco/accounts")
    rows = r.json()
    ar = [x for x in rows if x["from_entity_id"] == "ent_ksc" and x["to_entity_id"] == "ent_kanda"]
    if ar:
        assert abs(ar[0]["outstanding"]) < 0.01


def test_12_list_settlements(client):
    r = client.get(f"{BASE}/api/interco/settlements")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 2
    assert all("total_applied" in x for x in rows)
