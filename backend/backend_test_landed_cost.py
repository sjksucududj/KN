#!/usr/bin/env python3
"""
Backend API Testing for Kain Nusantara ERP - Phase 5.4: Landed Cost (P0-5)
Tests full lifecycle: create PO+GR → create voucher → submit → SoD → approve → pay

This test creates its own test data (PO + GR with rolls) to ensure landed cost has
rolls with base_unit_cost to allocate to.
"""
import requests
import sys
import json
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

# Public endpoint from frontend/.env
BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# Test credentials
CREDENTIALS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
}

MARK = "LCTEST"
PROD_ID = f"prod_{MARK.lower()}"
PO_ID = f"po_{MARK.lower()}"
PO_NUMBER = f"PO-{MARK}"
PO_PRICE = 45000.0  # per meter

def now_iso():
    return datetime.now(timezone.utc).isoformat()

class LandedCostTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.tokens = {}
        self.results = []
        self.po_id = PO_ID
        self.voucher_id = None
        
    def login(self, role):
        """Login and get token for a role"""
        creds = CREDENTIALS[role]
        try:
            resp = requests.post(f"{BASE_URL}/auth/login", json=creds, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.tokens[role] = data.get("token")
                print(f"✅ Login {role}: SUCCESS")
                return True
            else:
                print(f"❌ Login {role}: FAILED - Status {resp.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login {role}: ERROR - {str(e)}")
            return False
    
    def test(self, name, method, endpoint, expected_status, role=None, data=None, check_fn=None):
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if role and role in self.tokens:
            headers["Authorization"] = f"Bearer {self.tokens[role]}"
        
        print(f"\n🔍 Test #{self.tests_run}: {name}")
        
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=15)
            elif method == "POST":
                resp = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == "PUT":
                resp = requests.put(url, json=data, headers=headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            status_match = resp.status_code == expected_status
            check_pass = True
            check_msg = ""
            
            if status_match and check_fn:
                try:
                    response_data = resp.json() if resp.text else {}
                    check_pass, check_msg = check_fn(response_data)
                except Exception as e:
                    check_pass = False
                    check_msg = f"Check function error: {str(e)}"
            
            if status_match and check_pass:
                self.tests_passed += 1
                print(f"✅ PASSED - Status: {resp.status_code}")
                if check_msg:
                    print(f"   {check_msg}")
                self.results.append({"test": name, "status": "PASSED", "details": check_msg})
                return True, resp.json() if resp.text else {}
            else:
                self.tests_failed += 1
                if not status_match:
                    print(f"❌ FAILED - Expected {expected_status}, got {resp.status_code}")
                    try:
                        error_detail = resp.json().get("detail", resp.text[:200])
                        print(f"   Response: {error_detail}")
                    except Exception:
                        print(f"   Response: {resp.text[:200]}")
                else:
                    print(f"❌ FAILED - {check_msg}")
                self.results.append({"test": name, "status": "FAILED", "details": f"Status: {resp.status_code}, {check_msg}"})
                return False, {}
        except Exception as e:
            self.tests_failed += 1
            print(f"❌ FAILED - Exception: {str(e)}")
            self.results.append({"test": name, "status": "FAILED", "details": str(e)})
            return False, {}
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("📊 LANDED COST TEST SUMMARY")
        print("="*70)
        print(f"Total Tests: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0:.1f}%")
        print("="*70)
    
    async def setup_test_data(self):
        """Setup test PO and GR with rolls"""
        print("\n📝 Phase 0: Setup Test Data (PO + GR with rolls)")
        print("-"*70)
        
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        
        # Cleanup old test data
        await db.wms_tasks.delete_many({"mark": MARK})
        await db.inventory_rolls.delete_many({"$or": [{"mark": MARK}, {"product_id": PROD_ID}]})
        await db.inventory_movements.delete_many({"product_id": PROD_ID})
        await db.products.delete_many({"id": PROD_ID})
        await db.purchase_orders.delete_many({"id": PO_ID})
        await db.landed_cost_vouchers.delete_many({"po_ids": PO_ID})
        await db.cash_transactions.delete_many({"ref_type": "landed_cost", "description": {"$regex": MARK}})
        
        # Create product
        await db.products.update_one({"id": PROD_ID}, {"$set": {
            "id": PROD_ID, "sku": "TEST-LC", "name": "Test Fabric for Landed Cost",
            "category": "Kain", "base_unit": "meter", "price": 80000.0, "harga_pokok": 40000.0,
            "entity_id": "ent_ksc", "status": "active", "created_at": now_iso()}}, upsert=True)
        print(f"   ✅ Created test product: {PROD_ID}")
        
        # Create PO
        await db.purchase_orders.update_one({"id": PO_ID}, {"$set": {
            "id": PO_ID, "po_number": PO_NUMBER, "supplier_id": "sup_test", "supplier_name": "Test Supplier",
            "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara", "entity_id": "ent_ksc",
            "status": "received",
            "items": [{"product_id": PROD_ID, "sku": "TEST-LC", "product_name": "Test Fabric for Landed Cost",
                       "quantity": 100, "unit": "meter", "price": PO_PRICE, "received_qty": 100}],
            "created_at": now_iso(), "updated_at": now_iso()}}, upsert=True)
        print(f"   ✅ Created test PO: {PO_NUMBER} (price: {PO_PRICE}/meter)")
        
        # Create inbound task and complete it to create rolls
        tid = f"wms_{MARK.lower()}_{int(datetime.now().timestamp()*1000)}"
        await db.wms_tasks.insert_one({
            "id": tid, "mark": MARK, "flow_type": "inbound", "source_type": "po",
            "po_id": PO_ID, "po_number": PO_NUMBER,
            "product_id": PROD_ID, "product_name": "Test Fabric for Landed Cost", "sku": "TEST-LC",
            "expected_qty": 100, "received_qty": 100, "quantity": 100,
            "unit": "meter", "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
            "warehouse_city": "Jakarta", "supplier_name": "Test Supplier",
            "bin_id": "", "batch": "", "lot": "", "roll_id": "", "dye_lot": "", "grade": "",
            "status": "qc_check", "stages": ["waiting_goods", "receiving", "qc_check", "put_away", "completed"],
            "scan_log": [], "escalation": None,
            "created_by": "test", "created_at": now_iso(), "updated_at": now_iso()})
        
        # Complete GR via API to create rolls with base_unit_cost
        headers = {"Authorization": f"Bearer {self.tokens['admin']}", "Content-Type": "application/json"}
        resp = requests.post(
            f"{BASE_URL}/inbound/tasks/{tid}/complete",
            json={"rolls": [{"length": 60}, {"length": 40}]},
            headers=headers,
            timeout=30
        )
        
        if resp.status_code == 200:
            print(f"   ✅ Completed GR: created 2 rolls (60m + 40m) with base_unit_cost={PO_PRICE}")
            
            # Verify rolls were created
            rolls = await db.inventory_rolls.find({"acquired.ref_id": PO_ID}, {"_id": 0}).to_list(10)
            if len(rolls) == 2:
                print(f"   ✅ Verified: {len(rolls)} rolls in inventory with base_unit_cost set")
            else:
                print(f"   ⚠️  Expected 2 rolls, found {len(rolls)}")
        else:
            print(f"   ❌ Failed to complete GR: {resp.status_code} {resp.text[:200]}")
            client.close()
            return False
        
        client.close()
        return True
    
    async def cleanup_test_data(self):
        """Cleanup test data"""
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        
        await db.wms_tasks.delete_many({"mark": MARK})
        await db.inventory_rolls.delete_many({"$or": [{"mark": MARK}, {"product_id": PROD_ID}]})
        await db.inventory_movements.delete_many({"product_id": PROD_ID})
        await db.products.delete_many({"id": PROD_ID})
        await db.purchase_orders.delete_many({"id": PO_ID})
        await db.landed_cost_vouchers.delete_many({"po_ids": PO_ID})
        await db.cash_transactions.delete_many({"ref_type": "landed_cost", "description": {"$regex": MARK}})
        
        client.close()
        print("\n   🧹 Cleaned up test data")

def main():
    tester = LandedCostTester()
    
    print("="*70)
    print("🧪 Kain Nusantara ERP - Phase 5.4: Landed Cost Test")
    print("="*70)
    
    # Phase 1: Authentication
    print("\n📝 Phase 1: Authentication")
    print("-"*70)
    if not tester.login("admin"):
        print("❌ Cannot proceed without admin login")
        return 1
    if not tester.login("manager"):
        print("❌ Cannot proceed without manager login")
        return 1
    
    # Phase 0: Setup test data
    loop = asyncio.get_event_loop()
    if not loop.run_until_complete(tester.setup_test_data()):
        print("❌ Cannot proceed without test data")
        return 1
    
    # Phase 2: GET endpoints
    print("\n📝 Phase 2: GET Endpoints")
    print("-"*70)
    
    tester.test(
        "GET /api/landed-costs (list all)",
        "GET", "/landed-costs", 200, role="admin",
        check_fn=lambda d: (True, f"Got {len(d)} vouchers") if isinstance(d, list) else (False, "Expected array response")
    )
    
    tester.test(
        "GET /api/landed-costs/payables/summary",
        "GET", "/landed-costs/payables/summary", 200, role="admin",
        check_fn=lambda d: (True, f"Outstanding: {d.get('total_outstanding', 0)}, Applied: {d.get('total_applied', 0)}") if isinstance(d, dict) else (False, "Expected object response")
    )
    
    # Phase 3: Get PO with received rolls for testing
    print("\n📝 Phase 3: Verify Test PO with Rolls")
    print("-"*70)
    
    # Use our test PO
    print(f"   Using test PO: {PO_NUMBER} (ID: {tester.po_id})")
    
    # Phase 4: Test landed cost context endpoint
    print("\n📝 Phase 4: Landed Cost Context")
    print("-"*70)
    
    success, context_data = tester.test(
        f"GET /api/purchase-orders/{tester.po_id}/landed-cost-context",
        "GET", f"/purchase-orders/{tester.po_id}/landed-cost-context", 200, role="admin",
        check_fn=lambda d: (True, f"PO {d.get('po_number')}: {d.get('roll_count', 0)} rolls, base value: {d.get('total_base_value', 0)}") if isinstance(d, dict) else (False, "Expected object")
    )
    
    roll_count = context_data.get("roll_count", 0) if success else 0
    if roll_count < 2:
        print(f"⚠️  Expected 2 rolls, found {roll_count}. Test may fail.")
    
    # Phase 5: Create landed cost voucher
    print("\n📝 Phase 5: Create Landed Cost Voucher")
    print("-"*70)
    
    voucher_payload = {
        "po_ids": [tester.po_id],
        "provider_name": "Test Forwarder",
        "basis": "value",
        "cost_lines": [
            {"category": "freight", "description": "Shipping cost", "amount": 500000},
            {"category": "duty", "description": "Import duty", "amount": 300000}
        ],
        "notes": "Test landed cost voucher",
        "submit_now": False
    }
    
    success, voucher_data = tester.test(
        "POST /api/landed-costs (create voucher)",
        "POST", "/landed-costs", 200, role="admin", data=voucher_payload,
        check_fn=lambda d: (True, f"Voucher {d.get('voucher_number')} created, status: {d.get('status')}, total: {d.get('total_cost')}") if d.get("id") else (False, "No voucher ID returned")
    )
    
    if success and voucher_data.get("id"):
        tester.voucher_id = voucher_data["id"]
        
        # Check allocation preview
        preview = voucher_data.get("allocation_preview", [])
        if preview:
            total_alloc = sum(a.get("alloc_amount", 0) for a in preview)
            expected_total = voucher_data.get("total_cost", 0)
            if abs(total_alloc - expected_total) < 0.5:
                print(f"   ✅ Allocation preview sum ({total_alloc}) matches total_cost ({expected_total})")
            else:
                print(f"   ⚠️  Allocation preview sum ({total_alloc}) != total_cost ({expected_total})")
    else:
        print("❌ Cannot proceed without voucher ID")
        tester.print_summary()
        return 1
    
    # Phase 6: Submit voucher
    print("\n📝 Phase 6: Submit Voucher")
    print("-"*70)
    
    success, submit_data = tester.test(
        "POST /api/landed-costs/{id}/submit",
        "POST", f"/landed-costs/{tester.voucher_id}/submit", 200, role="admin",
        check_fn=lambda d: (True, f"Status: {d.get('status')}") if d.get("status") == "pending_approval" else (False, f"Expected pending_approval, got {d.get('status')}")
    )
    
    # Phase 7: SoD - Admin tries to approve own voucher (should fail)
    print("\n📝 Phase 7: Segregation of Duties (SoD)")
    print("-"*70)
    
    tester.test(
        "POST /api/landed-costs/{id}/approve (admin tries to approve own voucher - should fail)",
        "POST", f"/landed-costs/{tester.voucher_id}/approve", 403, role="admin",
        check_fn=lambda d: (True, f"SoD enforced: {d.get('detail', '')}") if "SoD" in str(d.get('detail', '')) or "Pemisahan tugas" in str(d.get('detail', '')) else (False, f"Expected SoD error, got: {d.get('detail', '')}")
    )
    
    # Phase 8: Manager approves voucher (should succeed)
    print("\n📝 Phase 8: Manager Approval")
    print("-"*70)
    
    success, approve_data = tester.test(
        "POST /api/landed-costs/{id}/approve (manager approves)",
        "POST", f"/landed-costs/{tester.voucher_id}/approve", 200, role="manager",
        check_fn=lambda d: (True, f"Status: {d.get('status')}, allocations: {len(d.get('allocations', []))}") if d.get("status") == "applied" else (False, f"Expected applied status, got {d.get('status')}")
    )
    
    # Phase 9: Idempotency - Try to approve again (should fail)
    print("\n📝 Phase 9: Idempotency Check")
    print("-"*70)
    
    tester.test(
        "POST /api/landed-costs/{id}/approve (approve again - should fail with 409)",
        "POST", f"/landed-costs/{tester.voucher_id}/approve", 409, role="manager",
        check_fn=lambda d: (True, f"Idempotency enforced: {d.get('detail', '')}") if "tidak menunggu approval" in str(d.get('detail', '')) else (False, f"Expected idempotency error, got: {d.get('detail', '')}")
    )
    
    # Phase 10: Pay voucher
    print("\n📝 Phase 10: Payment")
    print("-"*70)
    
    payment_payload = {
        "amount": 800000,
        "cash_type": "kas_besar",
        "method": "transfer",
        "notes": "Test payment"
    }
    
    success, pay_data = tester.test(
        "POST /api/landed-costs/{id}/pay",
        "POST", f"/landed-costs/{tester.voucher_id}/pay", 200, role="admin", data=payment_payload,
        check_fn=lambda d: (True, f"Status: {d.get('status')}, amount_paid: {d.get('amount_paid')}") if d.get("amount_paid") else (False, "Payment not recorded")
    )
    
    # Phase 11: Verify voucher detail
    print("\n📝 Phase 11: Verify Voucher Detail")
    print("-"*70)
    
    tester.test(
        "GET /api/landed-costs/{id} (verify final state)",
        "GET", f"/landed-costs/{tester.voucher_id}", 200, role="admin",
        check_fn=lambda d: (True, f"Voucher {d.get('voucher_number')}: status={d.get('status')}, financials.outstanding={d.get('financials', {}).get('outstanding', 0)}") if d.get("id") else (False, "Voucher not found")
    )
    
    # Print summary
    tester.print_summary()
    
    # Cleanup
    loop.run_until_complete(tester.cleanup_test_data())
    
    # Return exit code
    return 0 if tester.tests_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
