#!/usr/bin/env python3
"""
Backend Testing — Phase 6.1: RFQ / Quotation (Sourcing)
========================================================
Comprehensive testing of RFQ endpoints:
- Create RFQ (manual and from PR)
- Send RFQ (draft → open)
- Submit quotes from suppliers
- Compare quotes (matrix, lowest, recommendations)
- Award RFQ (full and per-line modes)
- PO creation and supplier price list updates
- Permissions (admin/manager/warehouse/sales)
- Response format validation (bare arrays/objects)
"""
import asyncio
import os
import sys
import requests
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

# Use public endpoint for testing
BASE = "https://po-pdf-sender.preview.emergentagent.com"
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ENTITY = "ent_ksc"
WH = "wh_jakarta"

# Test markers
MARK = "RFQTEST"

PASS, FAIL = [], []
def ok(m): PASS.append(m); print(f"  ✅ [PASS] {m}")
def bad(m): FAIL.append(m); print(f"  ❌ [FAIL] {m}")
def info(m): print(f"  ℹ️  {m}")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def login(email, password="demo12345"):
    """Login and return token"""
    try:
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
        r.raise_for_status()
        return r.json()["token"]
    except Exception as e:
        bad(f"Login failed for {email}: {str(e)}")
        return None


async def cleanup(db):
    """Clean up test data"""
    rfqs = await db.rfqs.find({"title": {"$regex": MARK}}, {"_id": 0, "award": 1}).to_list(50)
    po_ids = []
    for r in rfqs:
        po_ids += (r.get("award") or {}).get("po_ids", [])
    if po_ids:
        await db.purchase_orders.delete_many({"id": {"$in": po_ids}})
        await db.wms_tasks.delete_many({"source_id": {"$in": po_ids}})
    await db.rfqs.delete_many({"title": {"$regex": MARK}})
    await db.supplier_price_lists.delete_many({
        "notes": "Auto dari RFQ award",
        "source": "rfq_award",
        "created_by": {"$in": ["Budi Santoso", "Admin"]}
    })
    await db.purchase_requisitions.delete_many({"reason": {"$regex": MARK}})


async def pick_fixtures(db):
    """Pick suppliers and products for testing"""
    sups = await db.suppliers.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(10)
    prods = await db.products.find({}, {"_id": 0, "id": 1, "sku": 1, "name": 1}).to_list(10)
    return sups[:2], prods[:2]


async def test_backend():
    """Main backend test suite"""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # ── Test 1: Login ─────────────────────────────────────────────────────
    info("TEST 1: Authentication")
    admin_token = login("admin@kainnusantara.id")
    if not admin_token:
        bad("Admin login failed - stopping tests")
        client.close()
        return
    ok("Admin login successful")
    
    manager_token = login("manager@kainnusantara.id")
    if manager_token:
        ok("Manager login successful")
    else:
        bad("Manager login failed")
    
    warehouse_token = login("warehouse@kainnusantara.id")
    if warehouse_token:
        ok("Warehouse login successful")
    else:
        bad("Warehouse login failed")
    
    sales_token = login("sales@kainnusantara.id")
    if sales_token:
        ok("Sales login successful")
    else:
        bad("Sales login failed")
    
    # Setup session with admin token
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}"})
    
    # ── Test 2: Cleanup and pick fixtures ─────────────────────────────────
    info("TEST 2: Setup test data")
    await cleanup(db)
    (supA, supB), (p1, p2) = await pick_fixtures(db)
    if not supA or not supB or not p1 or not p2:
        bad("Insufficient fixtures (need 2 suppliers, 2 products)")
        client.close()
        return
    ok(f"Fixtures: supA={supA['name']}, supB={supB['name']}, p1={p1['sku']}, p2={p2['sku']}")
    
    # ── Test 3: Create RFQ manual ─────────────────────────────────────────
    info("TEST 3: POST /api/rfqs (manual source)")
    items = [
        {"product_id": p1["id"], "quantity": 100, "unit": "meter"},
        {"product_id": p2["id"], "quantity": 50, "unit": "meter"}
    ]
    rfq_id = None
    line_ids = []
    try:
        r = s.post(f"{API}/rfqs", json={
            "source": "manual",
            "title": f"{MARK} Manual RFQ 1",
            "entity_id": ENTITY,
            "warehouse_id": WH,
            "items": items,
            "supplier_ids": [supA["id"], supB["id"]],
            "needed_by_date": "2099-02-01T00:00:00+00:00"
        }, timeout=30)
        if r.status_code == 200:
            ok("Create RFQ returns 200")
            rfq = r.json()
            if isinstance(rfq, dict):
                ok("Response is an object (bare object, no envelope)")
                rfq_id = rfq.get("id")
                
                # Check structure
                checks = [
                    (rfq.get("status") == "draft", "status is 'draft'"),
                    (len(rfq.get("items", [])) == 2, "2 items created"),
                    (len(rfq.get("suppliers", [])) == 2, "2 suppliers invited"),
                    (rfq.get("rfq_number", "").startswith("RFQ-"), "rfq_number starts with RFQ-"),
                    (rfq.get("warehouse_id") == WH, "warehouse_id set correctly"),
                    (rfq.get("entity_id") == ENTITY, "entity_id set correctly"),
                ]
                for cond, label in checks:
                    ok(label) if cond else bad(f"{label} FAILED")
                
                # Extract line_ids
                line_ids = [it["line_id"] for it in rfq.get("items", [])]
                if len(line_ids) == 2:
                    ok(f"Line IDs extracted: {line_ids}")
                else:
                    bad(f"Expected 2 line_ids, got {len(line_ids)}")
                
                # Check suppliers have quote_status='pending'
                for sup in rfq.get("suppliers", []):
                    if sup.get("quote_status") == "pending":
                        ok(f"Supplier {sup['supplier_name']} has quote_status='pending'")
                    else:
                        bad(f"Supplier {sup['supplier_name']} quote_status is {sup.get('quote_status')}")
            else:
                bad(f"Response is not an object: {type(rfq)}")
        else:
            bad(f"Create RFQ failed: {r.status_code} {r.text[:250]}")
    except Exception as e:
        bad(f"Create RFQ test error: {str(e)}")
    
    if not rfq_id or not line_ids:
        bad("RFQ creation failed - stopping tests")
        client.close()
        return
    
    # ── Test 4: GET /api/rfqs (list) ──────────────────────────────────────
    info("TEST 4: GET /api/rfqs (list)")
    try:
        r = s.get(f"{API}/rfqs", params={"entity_id": ENTITY}, timeout=30)
        if r.status_code == 200:
            ok("List endpoint returns 200")
            rfqs = r.json()
            if isinstance(rfqs, list):
                ok("Response is a list (bare array, no envelope)")
                test_rfqs = [rfq for rfq in rfqs if MARK in rfq.get("title", "")]
                if len(test_rfqs) >= 1:
                    ok(f"Found {len(test_rfqs)} test RFQ(s)")
                else:
                    bad(f"Expected at least 1 test RFQ, found {len(test_rfqs)}")
            else:
                bad(f"Response is not a list: {type(rfqs)}")
        else:
            bad(f"List endpoint failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
        bad(f"List test error: {str(e)}")
    
    # ── Test 5: GET /api/rfqs/{id} (detail) ───────────────────────────────
    info("TEST 5: GET /api/rfqs/{id} (detail)")
    try:
        r = s.get(f"{API}/rfqs/{rfq_id}", timeout=30)
        if r.status_code == 200:
            ok("Detail endpoint returns 200")
            rfq = r.json()
            if isinstance(rfq, dict):
                ok("Response is an object (bare object)")
                if rfq.get("id") == rfq_id:
                    ok("Correct RFQ returned")
                else:
                    bad(f"Wrong RFQ returned: {rfq.get('id')}")
            else:
                bad(f"Response is not an object: {type(rfq)}")
        else:
            bad(f"Detail endpoint failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
        bad(f"Detail test error: {str(e)}")
    
    # ── Test 6: Send RFQ (draft → open) ───────────────────────────────────
    info("TEST 6: POST /api/rfqs/{id}/send (draft → open)")
    try:
        r = s.post(f"{API}/rfqs/{rfq_id}/send", timeout=30)
        if r.status_code == 200:
            ok("Send endpoint returns 200")
            rfq = r.json()
            if rfq.get("status") == "open":
                ok("Status changed to 'open'")
            else:
                bad(f"Status not 'open': {rfq.get('status')}")
        else:
            bad(f"Send failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
        bad(f"Send test error: {str(e)}")
    
    # ── Test 7: Submit quote from supplier A ──────────────────────────────
    info("TEST 7: POST /api/rfqs/{id}/quote (supplier A)")
    try:
        r = s.post(f"{API}/rfqs/{rfq_id}/quote", json={
            "supplier_id": supA["id"],
            "lines": [
                {"line_id": line_ids[0], "price": 10000, "available": True},
                {"line_id": line_ids[1], "price": 25000, "available": True}
            ],
            "lead_time_days": 7,
            "valid_until": "2099-12-31"
        }, timeout=30)
        if r.status_code == 200:
            ok("Quote submission returns 200")
            rfq = r.json()
            supA_data = next((s for s in rfq.get("suppliers", []) if s["supplier_id"] == supA["id"]), None)
            if supA_data:
                checks = [
                    (supA_data.get("quote_status") == "quoted", "quote_status is 'quoted'"),
                    (abs(float(supA_data.get("total", 0)) - 2250000) < 1, "total is 2,250,000 (10000*100 + 25000*50)"),
                    (supA_data.get("lead_time_days") == 7, "lead_time_days is 7"),
                ]
                for cond, label in checks:
                    ok(label) if cond else bad(f"{label} FAILED")
            else:
                bad("Supplier A data not found in response")
        else:
            bad(f"Quote submission failed: {r.status_code} {r.text[:250]}")
    except Exception as e:
        bad(f"Quote test error: {str(e)}")
    
    # ── Test 8: Submit quote from supplier B ──────────────────────────────
    info("TEST 8: POST /api/rfqs/{id}/quote (supplier B)")
    try:
        r = s.post(f"{API}/rfqs/{rfq_id}/quote", json={
            "supplier_id": supB["id"],
            "lines": [
                {"line_id": line_ids[0], "price": 12000, "available": True},
                {"line_id": line_ids[1], "price": 20000, "available": True}
            ],
            "lead_time_days": 10,
            "valid_until": "2099-12-31"
        }, timeout=30)
        if r.status_code == 200:
            ok("Quote submission returns 200")
            rfq = r.json()
            supB_data = next((s for s in rfq.get("suppliers", []) if s["supplier_id"] == supB["id"]), None)
            if supB_data:
                checks = [
                    (supB_data.get("quote_status") == "quoted", "quote_status is 'quoted'"),
                    (abs(float(supB_data.get("total", 0)) - 2200000) < 1, "total is 2,200,000 (12000*100 + 20000*50)"),
                ]
                for cond, label in checks:
                    ok(label) if cond else bad(f"{label} FAILED")
            else:
                bad("Supplier B data not found in response")
        else:
            bad(f"Quote submission failed: {r.status_code} {r.text[:250]}")
    except Exception as e:
        bad(f"Quote test error: {str(e)}")
    
    # ── Test 9: Compare quotes ────────────────────────────────────────────
    info("TEST 9: GET /api/rfqs/{id}/compare")
    try:
        r = s.get(f"{API}/rfqs/{rfq_id}/compare", timeout=30)
        if r.status_code == 200:
            ok("Compare endpoint returns 200")
            cmp = r.json()
            if isinstance(cmp, dict):
                ok("Response is an object (bare object)")
                
                # Check structure
                required_keys = ["items", "suppliers", "price_map", "lowest_per_line", 
                                "recommended_full_supplier_id", "recommended_line_awards"]
                for key in required_keys:
                    if key in cmp:
                        ok(f"Has '{key}' field")
                    else:
                        bad(f"Missing '{key}' field")
                
                # Check lowest per line
                lowest = cmp.get("lowest_per_line", {})
                if lowest.get(line_ids[0], {}).get("supplier_id") == supA["id"]:
                    ok(f"Lowest for line 1 is supplier A (10,000)")
                else:
                    bad(f"Lowest for line 1 should be A, got {lowest.get(line_ids[0])}")
                
                if lowest.get(line_ids[1], {}).get("supplier_id") == supB["id"]:
                    ok(f"Lowest for line 2 is supplier B (20,000)")
                else:
                    bad(f"Lowest for line 2 should be B, got {lowest.get(line_ids[1])}")
                
                # Check recommended full supplier (B has lowest total)
                if cmp.get("recommended_full_supplier_id") == supB["id"]:
                    ok("Recommended full supplier is B (lowest total 2,200,000)")
                else:
                    bad(f"Recommended full should be B, got {cmp.get('recommended_full_supplier_id')}")
                
                # Check recommended line awards
                line_awards = cmp.get("recommended_line_awards", [])
                if len(line_awards) == 2:
                    ok("Recommended line awards has 2 entries")
                    la_map = {la["line_id"]: la["supplier_id"] for la in line_awards}
                    if la_map.get(line_ids[0]) == supA["id"] and la_map.get(line_ids[1]) == supB["id"]:
                        ok("Recommended line awards: line1→A, line2→B")
                    else:
                        bad(f"Recommended line awards incorrect: {la_map}")
                else:
                    bad(f"Expected 2 line awards, got {len(line_awards)}")
            else:
                bad(f"Response is not an object: {type(cmp)}")
        else:
            bad(f"Compare failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
        bad(f"Compare test error: {str(e)}")
    
    # ── Test 10: Award FULL (supplier B) ──────────────────────────────────
    info("TEST 10: POST /api/rfqs/{id}/award (mode=full)")
    try:
        r = s.post(f"{API}/rfqs/{rfq_id}/award", json={
            "mode": "full",
            "full_supplier_id": supB["id"]
        }, timeout=30)
        if r.status_code == 200:
            ok("Award endpoint returns 200")
            result = r.json()
            if isinstance(result, dict):
                ok("Response is an object")
                
                # Check RFQ status
                rfq = result.get("rfq", {})
                if rfq.get("status") == "awarded":
                    ok("RFQ status is 'awarded'")
                else:
                    bad(f"RFQ status should be 'awarded', got {rfq.get('status')}")
                
                # Check POs created
                pos = result.get("pos", [])
                if len(pos) == 1:
                    ok("1 PO created (full award)")
                    po = pos[0]
                    checks = [
                        (po.get("supplier_id") == supB["id"], "PO supplier is B"),
                        (po.get("source_rfq_id") == rfq_id, "PO has source_rfq_id"),
                        (po.get("po_number", "").startswith("PO-"), "PO number starts with PO-"),
                        (len(po.get("items", [])) == 2, "PO has 2 items"),
                    ]
                    for cond, label in checks:
                        ok(label) if cond else bad(f"{label} FAILED")
                else:
                    bad(f"Expected 1 PO, got {len(pos)}")
                
                # Check award data
                award = rfq.get("award", {})
                if award.get("mode") == "full":
                    ok("Award mode is 'full'")
                else:
                    bad(f"Award mode should be 'full', got {award.get('mode')}")
                
                if len(award.get("po_numbers", [])) == 1:
                    ok(f"Award has 1 PO number: {award.get('po_numbers')}")
                else:
                    bad(f"Expected 1 PO number, got {len(award.get('po_numbers', []))}")
            else:
                bad(f"Response is not an object: {type(result)}")
        else:
            bad(f"Award failed: {r.status_code} {r.text[:250]}")
    except Exception as e:
        bad(f"Award test error: {str(e)}")
    
    # ── Test 11: Check supplier price list upsert ─────────────────────────
    info("TEST 11: Supplier price list upsert")
    try:
        spl = await db.supplier_price_lists.find_one({
            "supplier_id": supB["id"],
            "product_id": p1["id"],
            "source": "rfq_award"
        }, {"_id": 0})
        if spl:
            ok("Price list entry created for supplier B / product 1")
            if abs(float(spl.get("price", 0)) - 12000) < 1:
                ok("Price list price is 12,000")
            else:
                bad(f"Price list price should be 12,000, got {spl.get('price')}")
        else:
            bad("Price list entry not found for supplier B / product 1")
    except Exception as e:
        bad(f"Price list check error: {str(e)}")
    
    # ── Test 12: Guard - award already awarded RFQ (409) ──────────────────
    info("TEST 12: Award already awarded RFQ (409)")
    try:
        r = s.post(f"{API}/rfqs/{rfq_id}/award", json={
            "mode": "full",
            "full_supplier_id": supB["id"]
        }, timeout=30)
        if r.status_code == 409:
            ok("Award already awarded RFQ returns 409")
        else:
            bad(f"Should return 409, got {r.status_code}")
    except Exception as e:
        bad(f"Guard test error: {str(e)}")
    
    # ── Test 13: Create RFQ #2 for per-line award ────────────────────────
    info("TEST 13: Create RFQ #2 for per-line award")
    rfq_id2 = None
    line_ids2 = []
    try:
        r = s.post(f"{API}/rfqs", json={
            "source": "manual",
            "title": f"{MARK} Manual RFQ 2",
            "entity_id": ENTITY,
            "warehouse_id": WH,
            "items": items,
            "supplier_ids": [supA["id"], supB["id"]],
            "needed_by_date": "2099-02-01T00:00:00+00:00"
        }, timeout=30)
        if r.status_code == 200:
            ok("RFQ #2 created")
            rfq = r.json()
            rfq_id2 = rfq.get("id")
            line_ids2 = [it["line_id"] for it in rfq.get("items", [])]
        else:
            bad(f"RFQ #2 creation failed: {r.status_code}")
    except Exception as e:
        bad(f"RFQ #2 creation error: {str(e)}")
    
    if rfq_id2 and line_ids2:
        # Send and quote
        s.post(f"{API}/rfqs/{rfq_id2}/send", timeout=30)
        s.post(f"{API}/rfqs/{rfq_id2}/quote", json={
            "supplier_id": supA["id"],
            "lines": [
                {"line_id": line_ids2[0], "price": 10000, "available": True},
                {"line_id": line_ids2[1], "price": 25000, "available": True}
            ],
            "lead_time_days": 7
        }, timeout=30)
        s.post(f"{API}/rfqs/{rfq_id2}/quote", json={
            "supplier_id": supB["id"],
            "lines": [
                {"line_id": line_ids2[0], "price": 12000, "available": True},
                {"line_id": line_ids2[1], "price": 20000, "available": True}
            ],
            "lead_time_days": 10
        }, timeout=30)
        
        # ── Test 14: Award PER-LINE ───────────────────────────────────────
        info("TEST 14: POST /api/rfqs/{id}/award (mode=line)")
        try:
            r = s.post(f"{API}/rfqs/{rfq_id2}/award", json={
                "mode": "line",
                "line_awards": [
                    {"line_id": line_ids2[0], "supplier_id": supA["id"]},
                    {"line_id": line_ids2[1], "supplier_id": supB["id"]}
                ]
            }, timeout=30)
            if r.status_code == 200:
                ok("Award per-line returns 200")
                result = r.json()
                pos = result.get("pos", [])
                if len(pos) == 2:
                    ok("2 POs created (per-line award)")
                    supplier_ids = {po.get("supplier_id") for po in pos}
                    if supplier_ids == {supA["id"], supB["id"]}:
                        ok("POs split between supplier A and B")
                    else:
                        bad(f"Expected POs for A and B, got {supplier_ids}")
                else:
                    bad(f"Expected 2 POs, got {len(pos)}")
            else:
                bad(f"Award per-line failed: {r.status_code} {r.text[:250]}")
        except Exception as e:
            bad(f"Award per-line test error: {str(e)}")
    
    # ── Test 15: Create RFQ from PR ───────────────────────────────────────
    info("TEST 15: Create RFQ from PR approved")
    pr_id = None
    try:
        # Create PR
        r = s.post(f"{API}/purchase-requisitions", json={
            "items": [{"product_id": p1["id"], "quantity": 80, "unit": "meter", "est_price": 11000}],
            "warehouse_id": WH,
            "entity_id": ENTITY,
            "reason": f"{MARK} PR for RFQ",
            "submit_now": True
        }, timeout=30)
        if r.status_code == 200:
            pr = r.json()
            pr_id = pr.get("id")
            ok(f"PR created: {pr.get('number')}")
            
            # Approve if needed
            if pr.get("status") != "approved":
                r2 = s.post(f"{API}/purchase-requisitions/{pr_id}/approve", json={}, timeout=30)
                if r2.status_code == 200:
                    ok("PR approved")
                else:
                    bad(f"PR approval failed: {r2.status_code}")
            else:
                ok("PR already approved")
            
            # Create RFQ from PR
            r3 = s.post(f"{API}/rfqs", json={
                "source": "pr",
                "pr_id": pr_id,
                "title": f"{MARK} RFQ from PR",
                "entity_id": ENTITY,
                "warehouse_id": WH,
                "supplier_ids": [supA["id"], supB["id"]]
            }, timeout=30)
            if r3.status_code == 200:
                ok("RFQ from PR created")
                rfq_pr = r3.json()
                if len(rfq_pr.get("items", [])) == 1:
                    ok("RFQ pulled 1 item from PR")
                else:
                    bad(f"Expected 1 item from PR, got {len(rfq_pr.get('items', []))}")
                
                # Send, quote, and award
                rfq_pr_id = rfq_pr.get("id")
                line_pr = rfq_pr.get("items", [])[0]["line_id"]
                s.post(f"{API}/rfqs/{rfq_pr_id}/send", timeout=30)
                s.post(f"{API}/rfqs/{rfq_pr_id}/quote", json={
                    "supplier_id": supA["id"],
                    "lines": [{"line_id": line_pr, "price": 10500, "available": True}]
                }, timeout=30)
                r4 = s.post(f"{API}/rfqs/{rfq_pr_id}/award", json={
                    "mode": "full",
                    "full_supplier_id": supA["id"]
                }, timeout=30)
                if r4.status_code == 200:
                    ok("RFQ from PR awarded")
                    
                    # Check PR status
                    pr_check = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0, "status": 1, "po_id": 1})
                    if pr_check and pr_check.get("status") == "converted":
                        ok("PR status changed to 'converted'")
                        if pr_check.get("po_id"):
                            ok("PR has po_id set")
                        else:
                            bad("PR po_id not set")
                    else:
                        bad(f"PR status should be 'converted', got {pr_check.get('status') if pr_check else 'NOT FOUND'}")
                else:
                    bad(f"Award from PR failed: {r4.status_code}")
            else:
                bad(f"RFQ from PR creation failed: {r3.status_code} {r3.text[:250]}")
        else:
            bad(f"PR creation failed: {r.status_code} {r.text[:250]}")
    except Exception as e:
        bad(f"RFQ from PR test error: {str(e)}")
    
    # ── Test 16: Permissions - warehouse cannot award ─────────────────────
    info("TEST 16: Permissions - warehouse cannot award (403)")
    if warehouse_token:
        s_wh = requests.Session()
        s_wh.headers.update({"Authorization": f"Bearer {warehouse_token}"})
        
        # Warehouse can view
        try:
            r = s_wh.get(f"{API}/rfqs", params={"entity_id": ENTITY}, timeout=30)
            if r.status_code == 200:
                ok("Warehouse can view RFQs")
            else:
                bad(f"Warehouse view failed: {r.status_code}")
        except Exception as e:
            bad(f"Warehouse view test error: {str(e)}")
        
        # Warehouse can create
        try:
            r = s_wh.post(f"{API}/rfqs", json={
                "source": "manual",
                "title": f"{MARK} Warehouse RFQ",
                "entity_id": ENTITY,
                "warehouse_id": WH,
                "items": [{"product_id": p1["id"], "quantity": 10, "unit": "meter"}],
                "supplier_ids": [supA["id"]]
            }, timeout=30)
            if r.status_code == 200:
                ok("Warehouse can create RFQ")
                wh_rfq_id = r.json().get("id")
                
                # Try to award (should fail)
                s_wh.post(f"{API}/rfqs/{wh_rfq_id}/send", timeout=30)
                s_wh.post(f"{API}/rfqs/{wh_rfq_id}/quote", json={
                    "supplier_id": supA["id"],
                    "lines": [{"line_id": r.json()["items"][0]["line_id"], "price": 10000}]
                }, timeout=30)
                
                r2 = s_wh.post(f"{API}/rfqs/{wh_rfq_id}/award", json={
                    "mode": "full",
                    "full_supplier_id": supA["id"]
                }, timeout=30)
                if r2.status_code in [403, 401]:
                    ok("Warehouse cannot award RFQ (403/401)")
                else:
                    bad(f"Warehouse award should be forbidden, got {r2.status_code}")
            else:
                bad(f"Warehouse create failed: {r.status_code}")
        except Exception as e:
            bad(f"Warehouse create test error: {str(e)}")
    else:
        bad("No warehouse token to test permissions")
    
    # ── Test 17: Permissions - sales view only ────────────────────────────
    info("TEST 17: Permissions - sales view only")
    if sales_token:
        s_sales = requests.Session()
        s_sales.headers.update({"Authorization": f"Bearer {sales_token}"})
        
        # Sales can view
        try:
            r = s_sales.get(f"{API}/rfqs", params={"entity_id": ENTITY}, timeout=30)
            if r.status_code == 200:
                ok("Sales can view RFQs")
            else:
                bad(f"Sales view failed: {r.status_code}")
        except Exception as e:
            bad(f"Sales view test error: {str(e)}")
        
        # Sales cannot create
        try:
            r = s_sales.post(f"{API}/rfqs", json={
                "source": "manual",
                "title": f"{MARK} Sales RFQ",
                "entity_id": ENTITY,
                "warehouse_id": WH,
                "items": [{"product_id": p1["id"], "quantity": 10, "unit": "meter"}],
                "supplier_ids": [supA["id"]]
            }, timeout=30)
            if r.status_code in [403, 401]:
                ok("Sales cannot create RFQ (403/401)")
            else:
                bad(f"Sales create should be forbidden, got {r.status_code}")
        except Exception as e:
            bad(f"Sales create test error: {str(e)}")
    else:
        bad("No sales token to test permissions")
    
    # ── Cleanup ───────────────────────────────────────────────────────────
    info("Cleaning up test data...")
    await cleanup(db)
    ok("Test data cleaned up")
    
    client.close()


def print_summary():
    """Print test summary"""
    print("\n" + "=" * 70)
    print(f"  BACKEND TEST SUMMARY: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("=" * 70)
    if FAIL:
        print("\n❌ FAILED TESTS:")
        for f in FAIL:
            print(f"  - {f}")
    print()


if __name__ == "__main__":
    asyncio.run(test_backend())
    print_summary()
    sys.exit(0 if not FAIL else 1)
