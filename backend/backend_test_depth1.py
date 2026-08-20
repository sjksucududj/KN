#!/usr/bin/env python3
"""
Backend API Test — Depth #1 Purchasing Module
==============================================
Tests PO state machine, Purchase Returns (Retur Beli), and Payables/AP.

Test Coverage:
1A. PO State Machine: complete receiving, close short, terminal status validation
1B. Purchase Returns: approve/reject, debit note, stock adjustment
1C. PO Payment & Payables: payment processing, cash transactions, AP aging, permissions
"""
import os
import sys
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://po-pdf-sender.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PASS, FAIL = [], []


def ok(m):
    PASS.append(m)
    print(f"  ✅ [PASS] {m}")


def bad(m):
    FAIL.append(m)
    print(f"  ❌ [FAIL] {m}")


def info(m):
    print(f"  ℹ️  {m}")


class DepthOneTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.admin_token = None
        self.sales_token = None
        self.warehouse_token = None
        
    def login(self, email, password):
        """Login and return token"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login {email} failed: {r.status_code}")
                return None
            data = r.json()
            token = data.get("token")
            if not token:
                bad(f"Login {email} missing token")
                return None
            ok(f"Login {email}")
            return token
        except Exception as e:
            bad(f"Login {email} exception: {e}")
            return None
    
    def setup_tokens(self):
        """Login all test users"""
        info("\n=== Setup: Login Test Users ===")
        self.admin_token = self.login("admin@kainnusantara.id", "demo12345")
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")
        self.warehouse_token = self.login("warehouse@kainnusantara.id", "demo12345")
        
        if not self.admin_token:
            return False
        
        # Set admin as default
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
        return True
    
    # ========== 1A: PO State Machine Tests ==========
    
    def test_1a_po_list_and_find_po009(self):
        """1A: GET /api/purchase-orders and find PO-00009"""
        info("\n=== TEST 1A.1: List POs and Find PO-00009 ===")
        
        try:
            r = self.session.get(f"{API}/purchase-orders", timeout=30)
            if r.status_code != 200:
                bad(f"GET purchase-orders failed: {r.status_code}")
                return None
            
            pos = r.json()
            ok(f"GET purchase-orders returned {len(pos)} POs")
            
            # Find PO-00009 (id: po_009)
            po_009 = next((p for p in pos if p.get("id") == "po_009" or p.get("po_number") == "PO-00009"), None)
            
            if not po_009:
                bad("PO-00009 (po_009) not found in seeded data")
                return None
            
            ok(f"Found PO-00009: status={po_009.get('status')}")
            
            # Verify it's pending
            if po_009.get("status") == "pending":
                ok("PO-00009 status is 'pending'")
            else:
                info(f"PO-00009 status is '{po_009.get('status')}' (expected 'pending')")
            
            return po_009
        except Exception as e:
            bad(f"Test 1A.1 exception: {e}")
            return None
    
    def test_1a_complete_receiving_po009(self, po_009):
        """1A: Complete receiving for PO-00009 via inbound tasks"""
        info("\n=== TEST 1A.2: Complete Receiving for PO-00009 ===")
        
        try:
            po_id = po_009.get("id")
            
            # Get inbound tasks for po_009
            r = self.session.get(f"{API}/inbound/tasks", timeout=30)
            if r.status_code != 200:
                bad(f"GET inbound/tasks failed: {r.status_code}")
                return False
            
            tasks = r.json()
            po_009_tasks = [t for t in tasks if t.get("po_id") == po_id]
            
            if not po_009_tasks:
                bad(f"No inbound tasks found for PO-00009 (po_id={po_id})")
                return False
            
            ok(f"Found {len(po_009_tasks)} inbound task(s) for PO-00009")
            
            # Complete each task
            for task in po_009_tasks:
                task_id = task.get("id")
                product_id = task.get("product_id")
                expected_qty = float(task.get("expected_qty", 0))
                
                info(f"Processing task {task_id}: product={product_id}, expected_qty={expected_qty}")
                
                # Skip if already completed
                if task.get("status") == "completed":
                    info(f"Task {task_id} already completed")
                    continue
                
                # Scan receive
                r = self.session.post(
                    f"{API}/inbound/tasks/{task_id}/scan-receive",
                    json={
                        "product_id": product_id,
                        "actual_qty": expected_qty,
                        "batch": "B1",
                        "bin_id": "A1"
                    },
                    timeout=30
                )
                
                if r.status_code != 200:
                    bad(f"Scan-receive task {task_id} failed: {r.status_code} {r.text[:200]}")
                    continue
                
                ok(f"Scan-receive task {task_id}: {expected_qty} units")
                
                # Complete task
                r = self.session.post(
                    f"{API}/inbound/tasks/{task_id}/complete",
                    json={"bin_id": "A1"},
                    timeout=30
                )
                
                if r.status_code != 200:
                    bad(f"Complete task {task_id} failed: {r.status_code} {r.text[:200]}")
                    continue
                
                ok(f"Complete task {task_id}")
            
            # Verify PO status changed to 'completed'
            r = self.session.get(f"{API}/purchase-orders/{po_id}", timeout=30)
            if r.status_code != 200:
                bad(f"GET PO-00009 after receiving failed: {r.status_code}")
                return False
            
            po_updated = r.json()
            status = po_updated.get("status")
            
            if status == "completed":
                ok(f"PO-00009 status changed to 'completed' after receiving")
            else:
                bad(f"PO-00009 status is '{status}' (expected 'completed')")
            
            # Verify received_qty
            items = po_updated.get("items", [])
            if items:
                item = items[0]
                received_qty = float(item.get("received_qty", 0))
                quantity = float(item.get("quantity", 0))
                
                if received_qty >= quantity * 0.98:  # Allow 2% tolerance
                    ok(f"PO-00009 item received_qty={received_qty} (ordered={quantity})")
                else:
                    bad(f"PO-00009 item received_qty={received_qty} < ordered={quantity}")
            
            return True
        except Exception as e:
            bad(f"Test 1A.2 exception: {e}")
            return False
    
    def test_1a_close_short(self):
        """1A: Create PO and close it short"""
        info("\n=== TEST 1A.3: Close PO Short ===")
        
        try:
            # Get supplier and warehouse
            r = self.session.get(f"{API}/suppliers", timeout=30)
            suppliers = r.json()
            if not suppliers:
                bad("No suppliers found")
                return False
            supplier_id = suppliers[0].get("id")
            
            r = self.session.get(f"{API}/warehouses", timeout=30)
            warehouses = r.json()
            if not warehouses:
                bad("No warehouses found")
                return False
            warehouse_id = warehouses[0].get("id")
            
            # Get a product
            r = self.session.get(f"{API}/products", timeout=30)
            products = r.json()
            if not products:
                bad("No products found")
                return False
            product_id = products[0].get("id")
            
            # Create small PO
            r = self.session.post(
                f"{API}/purchase-orders",
                json={
                    "supplier_id": supplier_id,
                    "warehouse_id": warehouse_id,
                    "items": [{"product_id": product_id, "quantity": 20, "unit": "meter", "price": 150000}],
                    "notes": "Test close short",
                    "created_by": "Admin Test"
                },
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Create PO failed: {r.status_code} {r.text[:200]}")
                return False
            
            po = r.json()
            po_id = po.get("id")
            po_number = po.get("po_number")
            
            ok(f"Created PO {po_number} for close short test")
            
            # Approve if needed
            if po.get("status") == "waiting_approval":
                r = self.session.post(f"{API}/purchase-orders/{po_id}/approve", timeout=30)
                if r.status_code != 200:
                    bad(f"Approve PO failed: {r.status_code}")
                    return False
                ok(f"Approved PO {po_number}")
            
            # Close short
            r = self.session.post(
                f"{API}/purchase-orders/{po_id}/close",
                json={"reason": "stop produksi"},
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Close short failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            if result.get("status") == "closed_short":
                ok(f"PO {po_number} closed short successfully")
            else:
                bad(f"PO {po_number} status is '{result.get('status')}' (expected 'closed_short')")
            
            # Test closing a completed PO (should fail with 400)
            # Find a completed PO from earlier test
            r = self.session.get(f"{API}/purchase-orders", timeout=30)
            pos = r.json()
            completed_po = next((p for p in pos if p.get("status") == "completed"), None)
            
            if completed_po:
                r = self.session.post(
                    f"{API}/purchase-orders/{completed_po['id']}/close",
                    json={"reason": "test"},
                    timeout=30
                )
                
                if r.status_code == 400:
                    ok("Closing completed PO correctly returns 400")
                else:
                    bad(f"Closing completed PO returned {r.status_code} (expected 400)")
            
            return True
        except Exception as e:
            bad(f"Test 1A.3 exception: {e}")
            return False
    
    # ========== 1B: Purchase Returns Tests ==========
    
    def test_1b_list_purchase_returns(self):
        """1B: GET /api/purchase-returns and verify seeded data"""
        info("\n=== TEST 1B.1: List Purchase Returns ===")
        
        try:
            r = self.session.get(f"{API}/purchase-returns", timeout=30)
            if r.status_code != 200:
                bad(f"GET purchase-returns failed: {r.status_code}")
                return None
            
            data = r.json()
            items = data.get("items", [])
            
            ok(f"GET purchase-returns returned {len(items)} returns")
            
            # Find PRET-00001 and PRET-00002
            pret_001 = next((p for p in items if p.get("number") == "PRET-00001"), None)
            pret_002 = next((p for p in items if p.get("number") == "PRET-00002"), None)
            
            if pret_001:
                ok(f"Found PRET-00001: status={pret_001.get('status')}")
            else:
                bad("PRET-00001 not found in seeded data")
            
            if pret_002:
                ok(f"Found PRET-00002: status={pret_002.get('status')}")
            else:
                bad("PRET-00002 not found in seeded data")
            
            return {"pret_001": pret_001, "pret_002": pret_002}
        except Exception as e:
            bad(f"Test 1B.1 exception: {e}")
            return None
    
    def test_1b_approve_pret_001(self, pret_001):
        """1B: Approve PRET-00001 and verify debit note + stock adjustment"""
        info("\n=== TEST 1B.2: Approve PRET-00001 ===")
        
        if not pret_001:
            bad("PRET-00001 not available for approval test")
            return False
        
        try:
            return_id = pret_001.get("id")
            
            # Get inventory before approval (for stock verification)
            product_id = pret_001.get("items", [{}])[0].get("product_id")
            warehouse_id = pret_001.get("warehouse_id")
            
            # Approve the return
            r = self.session.post(
                f"{API}/purchase-returns/{return_id}/approve",
                json={"notes": "ok"},
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Approve PRET-00001 failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            
            # Verify status is 'approved'
            if result.get("status") == "approved":
                ok("PRET-00001 status changed to 'approved'")
            else:
                bad(f"PRET-00001 status is '{result.get('status')}' (expected 'approved')")
            
            # Verify debit note number
            debit_note = result.get("debit_note_number", "")
            if debit_note.startswith("DN-"):
                ok(f"Debit note generated: {debit_note}")
            else:
                bad(f"Debit note number invalid: '{debit_note}'")
            
            # Verify stock_adjusted flag
            if result.get("stock_adjusted"):
                ok("stock_adjusted flag is true")
            else:
                bad("stock_adjusted flag should be true")
            
            return True
        except Exception as e:
            bad(f"Test 1B.2 exception: {e}")
            return False
    
    def test_1b_create_and_submit_return(self):
        """1B: Create new purchase return and submit"""
        info("\n=== TEST 1B.3: Create and Submit New Return ===")
        
        try:
            # Get supplier, warehouse, product
            r = self.session.get(f"{API}/suppliers", timeout=30)
            suppliers = r.json()
            if not suppliers:
                bad("No suppliers found")
                return False
            supplier_id = suppliers[0].get("id")
            
            r = self.session.get(f"{API}/warehouses", timeout=30)
            warehouses = r.json()
            if not warehouses:
                bad("No warehouses found")
                return False
            warehouse_id = warehouses[0].get("id")
            
            r = self.session.get(f"{API}/products", timeout=30)
            products = r.json()
            if not products:
                bad("No products found")
                return False
            product_id = products[0].get("id")
            
            # Create return
            r = self.session.post(
                f"{API}/purchase-returns",
                json={
                    "supplier_id": supplier_id,
                    "warehouse_id": warehouse_id,
                    "items": [{
                        "product_id": product_id,
                        "quantity": 5,
                        "unit": "meter",
                        "price": 100000,
                        "reason": "cacat",
                        "condition": "damaged"
                    }],
                    "reason": "Barang cacat",
                    "notes": "Test return",
                    "submit_now": True
                },
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Create return failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            return_number = result.get("number", "")
            
            if return_number.startswith("PRET-"):
                ok(f"Created return: {return_number}")
            else:
                bad(f"Return number invalid: '{return_number}'")
            
            # Verify status is pending_approval (submit_now=True)
            if result.get("status") == "pending_approval":
                ok(f"Return {return_number} status is 'pending_approval'")
            else:
                bad(f"Return {return_number} status is '{result.get('status')}' (expected 'pending_approval')")
            
            return result
        except Exception as e:
            bad(f"Test 1B.3 exception: {e}")
            return False
    
    def test_1b_submit_draft_pret_002(self, pret_002):
        """1B: Submit draft PRET-00002"""
        info("\n=== TEST 1B.4: Submit Draft PRET-00002 ===")
        
        if not pret_002:
            bad("PRET-00002 not available for submit test")
            return False
        
        try:
            return_id = pret_002.get("id")
            
            # Submit the draft
            r = self.session.post(
                f"{API}/purchase-returns/{return_id}/submit",
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Submit PRET-00002 failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            
            if result.get("status") == "pending_approval":
                ok("PRET-00002 submitted, status changed to 'pending_approval'")
            else:
                bad(f"PRET-00002 status is '{result.get('status')}' (expected 'pending_approval')")
            
            return True
        except Exception as e:
            bad(f"Test 1B.4 exception: {e}")
            return False
    
    def test_1b_reject_return(self):
        """1B: Create return and reject it"""
        info("\n=== TEST 1B.5: Create and Reject Return ===")
        
        try:
            # Get supplier, warehouse, product
            r = self.session.get(f"{API}/suppliers", timeout=30)
            suppliers = r.json()
            supplier_id = suppliers[0].get("id")
            
            r = self.session.get(f"{API}/warehouses", timeout=30)
            warehouses = r.json()
            warehouse_id = warehouses[0].get("id")
            
            r = self.session.get(f"{API}/products", timeout=30)
            products = r.json()
            product_id = products[0].get("id")
            
            # Create return
            r = self.session.post(
                f"{API}/purchase-returns",
                json={
                    "supplier_id": supplier_id,
                    "warehouse_id": warehouse_id,
                    "items": [{
                        "product_id": product_id,
                        "quantity": 3,
                        "unit": "meter",
                        "price": 100000,
                        "reason": "test reject",
                        "condition": "ok"
                    }],
                    "submit_now": True
                },
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Create return for reject test failed: {r.status_code}")
                return False
            
            result = r.json()
            return_id = result.get("id")
            return_number = result.get("number")
            
            ok(f"Created return {return_number} for reject test")
            
            # Reject it
            r = self.session.post(
                f"{API}/purchase-returns/{return_id}/reject",
                json={"notes": "tolak"},
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Reject return failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            
            if result.get("status") == "rejected":
                ok(f"Return {return_number} rejected successfully")
            else:
                bad(f"Return {return_number} status is '{result.get('status')}' (expected 'rejected')")
            
            return True
        except Exception as e:
            bad(f"Test 1B.5 exception: {e}")
            return False
    
    # ========== 1C: PO Payment & Payables Tests ==========
    
    def test_1c_pay_po(self):
        """1C: Pay PO and verify cash transaction"""
        info("\n=== TEST 1C.1: Pay PO ===")
        
        try:
            # Find a PO with outstanding > 0
            r = self.session.get(f"{API}/purchase-orders", timeout=30)
            pos = r.json()
            
            # Find any PO with outstanding > 0
            po_to_pay = next((p for p in pos if float(p.get("outstanding", 0)) > 0), None)
            
            if not po_to_pay:
                bad("No PO with outstanding found for payment test")
                return False
            
            po_id = po_to_pay.get("id")
            po_number = po_to_pay.get("po_number")
            outstanding = float(po_to_pay.get("outstanding", 0))
            
            info(f"Testing payment for {po_number}, outstanding={outstanding}")
            
            # Pay partial amount
            payment_amount = min(10000000, outstanding)
            
            r = self.session.post(
                f"{API}/purchase-orders/{po_id}/pay",
                json={
                    "amount": payment_amount,
                    "cash_type": "kas_besar",
                    "method": "transfer"
                },
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Pay PO failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            financials = result.get("financials", {})
            
            ok(f"Paid {payment_amount} to {po_number}")
            
            # Verify amount_paid increased
            amount_paid = float(financials.get("amount_paid", 0))
            if amount_paid >= payment_amount:
                ok(f"amount_paid={amount_paid} (includes payment)")
            else:
                bad(f"amount_paid={amount_paid} < payment_amount={payment_amount}")
            
            # Verify outstanding decreased
            new_outstanding = float(financials.get("outstanding", 0))
            if new_outstanding < outstanding:
                ok(f"outstanding decreased to {new_outstanding}")
            else:
                bad(f"outstanding={new_outstanding} did not decrease")
            
            # Verify payment_status
            payment_status = financials.get("payment_status")
            if payment_status in ["partial", "paid"]:
                ok(f"payment_status={payment_status}")
            else:
                bad(f"payment_status={payment_status} (expected 'partial' or 'paid')")
            
            # Verify cash transaction created
            r = self.session.get(
                f"{API}/cash-transactions",
                params={"cash_type": "kas_besar"},
                timeout=30
            )
            
            if r.status_code == 200:
                cash_txns = r.json()
                # Find transaction for this PO
                po_txn = next((t for t in cash_txns if t.get("ref_type") == "purchase_order" and t.get("ref_id") == po_id), None)
                
                if po_txn:
                    ok(f"Cash transaction created: {po_txn.get('number')}")
                else:
                    bad("Cash transaction not found for PO payment")
            
            # Test overpayment (should return 400)
            r = self.session.post(
                f"{API}/purchase-orders/{po_id}/pay",
                json={
                    "amount": new_outstanding + 1000000,  # Pay more than outstanding
                    "cash_type": "kas_besar",
                    "method": "transfer"
                },
                timeout=30
            )
            
            if r.status_code == 400:
                ok("Overpayment correctly returns 400")
            else:
                bad(f"Overpayment returned {r.status_code} (expected 400)")
            
            return True
        except Exception as e:
            bad(f"Test 1C.1 exception: {e}")
            return False
    
    def test_1c_payables_summary(self):
        """1C: GET payables summary and verify aging"""
        info("\n=== TEST 1C.2: Payables Summary ===")
        
        try:
            r = self.session.get(f"{API}/purchase-orders/payables/summary", timeout=30)
            
            if r.status_code != 200:
                bad(f"GET payables/summary failed: {r.status_code}")
                return False
            
            summary = r.json()
            
            ok("GET payables/summary successful")
            
            # Verify structure
            total_outstanding = summary.get("total_outstanding")
            if total_outstanding is not None:
                ok(f"total_outstanding={total_outstanding}")
            else:
                bad("total_outstanding missing")
            
            # Verify aging buckets
            aging = summary.get("aging", {})
            expected_buckets = ["0-30", "31-60", "61-90", ">90"]
            
            for bucket in expected_buckets:
                if bucket in aging:
                    ok(f"Aging bucket '{bucket}' present: {aging[bucket]}")
                else:
                    bad(f"Aging bucket '{bucket}' missing")
            
            # Verify by_supplier array
            by_supplier = summary.get("by_supplier", [])
            if by_supplier:
                ok(f"by_supplier has {len(by_supplier)} entries")
            else:
                info("by_supplier is empty (no outstanding payables)")
            
            # Verify purchase_orders array
            purchase_orders = summary.get("purchase_orders", [])
            if purchase_orders:
                ok(f"purchase_orders has {len(purchase_orders)} entries")
                
                # Verify PO-00002 (fully paid) should NOT appear
                po_002_in_list = any(p.get("po_number") == "PO-00002" for p in purchase_orders)
                if not po_002_in_list:
                    ok("PO-00002 (fully paid) not in payables list")
                else:
                    bad("PO-00002 (fully paid) should not be in payables list")
            else:
                info("purchase_orders is empty")
            
            return True
        except Exception as e:
            bad(f"Test 1C.2 exception: {e}")
            return False
    
    def test_1c_permissions(self):
        """1C: Test permissions for sales and warehouse roles"""
        info("\n=== TEST 1C.3: Permissions ===")
        
        if not self.sales_token or not self.warehouse_token:
            bad("Sales or warehouse token not available")
            return False
        
        try:
            # Test sales can view payables
            self.session.headers.update({"Authorization": f"Bearer {self.sales_token}"})
            
            r = self.session.get(f"{API}/purchase-orders/payables/summary", timeout=30)
            if r.status_code == 200:
                ok("Sales can view payables (GET)")
            else:
                bad(f"Sales GET payables failed: {r.status_code}")
            
            # Test sales cannot pay PO
            r = self.session.get(f"{API}/purchase-orders", timeout=30)
            if r.status_code == 200:
                pos = r.json()
                if pos:
                    po_id = pos[0].get("id")
                    
                    r = self.session.post(
                        f"{API}/purchase-orders/{po_id}/pay",
                        json={"amount": 1000, "cash_type": "kas_besar", "method": "transfer"},
                        timeout=30
                    )
                    
                    if r.status_code == 403:
                        ok("Sales cannot pay PO (403)")
                    else:
                        bad(f"Sales pay PO returned {r.status_code} (expected 403)")
            
            # Test warehouse can view and create returns
            self.session.headers.update({"Authorization": f"Bearer {self.warehouse_token}"})
            
            r = self.session.get(f"{API}/purchase-returns", timeout=30)
            if r.status_code == 200:
                ok("Warehouse can view purchase returns")
            else:
                bad(f"Warehouse GET purchase-returns failed: {r.status_code}")
            
            # Test warehouse cannot approve returns
            r = self.session.get(f"{API}/purchase-returns", timeout=30)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                pending_return = next((p for p in items if p.get("status") == "pending_approval"), None)
                
                if pending_return:
                    r = self.session.post(
                        f"{API}/purchase-returns/{pending_return['id']}/approve",
                        json={"notes": "test"},
                        timeout=30
                    )
                    
                    if r.status_code == 403:
                        ok("Warehouse cannot approve return (403)")
                    else:
                        bad(f"Warehouse approve return returned {r.status_code} (expected 403)")
            
            # Restore admin token
            self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
            
            return True
        except Exception as e:
            bad(f"Test 1C.3 exception: {e}")
            # Restore admin token
            self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
            return False
    
    def run_all_tests(self):
        """Run all Depth #1 tests"""
        print("\n" + "="*70)
        print("  BACKEND API TEST — Depth #1 Purchasing Module")
        print("="*70)
        
        if not self.setup_tokens():
            return False
        
        # 1A: PO State Machine
        po_009 = self.test_1a_po_list_and_find_po009()
        if po_009:
            self.test_1a_complete_receiving_po009(po_009)
        
        self.test_1a_close_short()
        
        # 1B: Purchase Returns
        prets = self.test_1b_list_purchase_returns()
        if prets:
            if prets.get("pret_001") and prets["pret_001"].get("status") == "pending_approval":
                self.test_1b_approve_pret_001(prets["pret_001"])
            
            if prets.get("pret_002") and prets["pret_002"].get("status") == "draft":
                self.test_1b_submit_draft_pret_002(prets["pret_002"])
        
        self.test_1b_create_and_submit_return()
        self.test_1b_reject_return()
        
        # 1C: PO Payment & Payables
        self.test_1c_pay_po()
        self.test_1c_payables_summary()
        self.test_1c_permissions()
        
        return True


def main():
    tester = DepthOneTester()
    tester.run_all_tests()
    
    print("\n" + "="*70)
    print(f"  HASIL: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("="*70)
    
    if FAIL:
        print("\n❌ FAILED TESTS:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    
    print("\n✅ SEMUA TEST BACKEND LULUS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
