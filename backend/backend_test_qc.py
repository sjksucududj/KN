#!/usr/bin/env python3
"""
Backend API Test — Depth #3a QC Hold / Quarantine at Goods Receipt
====================================================================
Tests QC inspection flow:
1. GR routes to quarantine (scan-receive → complete → qc_pending)
2. QC queue endpoint returns enriched tasks
3. QC accept (full) - quarantine → available
4. QC reject damaged - quarantine → damaged
5. QC reject return - quarantine → returned_supplier + Purchase Return
6. Validations (over-allocation, both zero, non-qc_pending task)
7. Data integrity verification
"""
import os
import sys
import requests
from datetime import datetime

BASE = os.environ.get("BACKEND_URL", "https://po-pdf-sender.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
PASS, FAIL = [], []


def ok(m):
    PASS.append(m)
    print(f"  ✅ [PASS] {m}")


def bad(m):
    FAIL.append(m)
    print(f"  ❌ [FAIL] {m}")


def info(m):
    print(f"  ℹ️  {m}")


class QCTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.entity_id = None
        self.warehouse_id = None
        
    def login(self):
        """Login as admin"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": "admin@kainnusantara.id", "password": "demo12345"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed: {r.status_code} {r.text[:200]}")
                return False
            data = r.json()
            self.token = data.get("token")
            if not self.token:
                bad("Login response missing token")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            ok("Login admin@kainnusantara.id")
            return True
        except Exception as e:
            bad(f"Login exception: {e}")
            return False
    
    def get_references(self):
        """Get entity and warehouse references"""
        try:
            r = self.session.get(f"{API}/entities", timeout=30)
            entities = r.json()
            if entities:
                self.entity_id = entities[0]["id"]
            
            r = self.session.get(f"{API}/warehouses", timeout=30)
            warehouses = r.json()
            if warehouses:
                self.warehouse_id = warehouses[0]["id"]
            
            ok(f"References: entity={self.entity_id[:8] if self.entity_id else 'N/A'}, warehouse={self.warehouse_id[:8] if self.warehouse_id else 'N/A'}")
            return True
        except Exception as e:
            bad(f"Get references exception: {e}")
            return False
    
    def test_qc_queue_initial(self):
        """Test 1: QC queue endpoint returns seeded qc_pending task"""
        info("TEST 1: QC queue endpoint")
        try:
            r = self.session.get(f"{API}/inbound/qc/queue", timeout=30)
            if r.status_code != 200:
                bad(f"QC queue failed: {r.status_code} {r.text[:200]}")
                return None
            
            queue = r.json()
            if not isinstance(queue, list):
                bad(f"QC queue not a list: {type(queue)}")
                return None
            
            ok(f"QC queue returned {len(queue)} tasks")
            
            # Check for seeded task (Batik Mega Mendung Premium)
            if len(queue) > 0:
                task = queue[0]
                required_fields = ["id", "product_name", "sku", "supplier_name", "po_number", 
                                   "warehouse_name", "quarantine_qty", "status", "qc_status"]
                missing = [f for f in required_fields if f not in task]
                if missing:
                    bad(f"QC queue task missing fields: {missing}")
                else:
                    ok(f"QC queue task enriched: {task['product_name']}, PO {task['po_number']}, {task['quarantine_qty']}m karantina")
                    info(f"   Task ID: {task['id']}, Status: {task['status']}, QC: {task['qc_status']}")
                    return task
            else:
                info("QC queue empty (expected if all tasks already inspected)")
                return None
                
        except Exception as e:
            bad(f"QC queue exception: {e}")
            return None
    
    def test_gr_to_quarantine(self):
        """Test 2: GR flow creates quarantine roll and qc_pending task"""
        info("TEST 2: GR routes to quarantine")
        try:
            # Get waiting_goods tasks
            r = self.session.get(f"{API}/inbound/tasks?status=waiting_goods", timeout=30)
            if r.status_code != 200:
                bad(f"Get waiting_goods tasks failed: {r.status_code}")
                return None
            
            tasks = r.json()
            if not tasks:
                info("No waiting_goods tasks available for GR test")
                return None
            
            task = tasks[0]
            task_id = task["id"]
            product_id = task["product_id"]
            expected_qty = task.get("expected_qty", 0)
            
            info(f"   Testing with task {task_id}, product {product_id}, qty {expected_qty}")
            
            # Step 1: scan-receive
            r = self.session.post(
                f"{API}/inbound/tasks/{task_id}/scan-receive",
                json={
                    "product_id": product_id,
                    "actual_qty": expected_qty,
                    "batch": "TEST-BATCH",
                    "lot": "TEST-LOT",
                    "roll_id": "",
                    "bin_id": ""
                },
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Scan-receive failed: {r.status_code} {r.text[:200]}")
                return None
            
            scan_result = r.json()
            if scan_result.get("status") != "qc_check":
                bad(f"After scan-receive, status should be qc_check, got: {scan_result.get('status')}")
                return None
            
            ok(f"Scan-receive: status={scan_result['status']}, received_qty={scan_result.get('received_qty')}")
            
            # Step 2: complete (should create quarantine roll)
            r = self.session.post(f"{API}/inbound/tasks/{task_id}/complete", timeout=30)
            if r.status_code != 200:
                bad(f"Complete failed: {r.status_code} {r.text[:200]}")
                return None
            
            complete_result = r.json()
            if complete_result.get("status") != "qc_pending":
                bad(f"After complete, status should be qc_pending, got: {complete_result.get('status')}")
                return None
            
            if complete_result.get("qc_status") != "pending":
                bad(f"After complete, qc_status should be pending, got: {complete_result.get('qc_status')}")
                return None
            
            if not complete_result.get("quarantine_qty"):
                bad(f"After complete, quarantine_qty should be set, got: {complete_result.get('quarantine_qty')}")
                return None
            
            ok(f"Complete: status={complete_result['status']}, qc_status={complete_result['qc_status']}, quarantine_qty={complete_result['quarantine_qty']}")
            
            # Verify inventory_rolls created with status=quarantine
            r = self.session.get(f"{API}/inventory/rolls?product_id={product_id}", timeout=30)
            if r.status_code == 200:
                rolls = r.json()
                quarantine_rolls = [roll for roll in rolls if roll.get("status") == "quarantine" and roll.get("qc_task_id") == task_id]
                if quarantine_rolls:
                    ok(f"Quarantine roll created: {len(quarantine_rolls)} roll(s) with status=quarantine")
                else:
                    bad("No quarantine roll found after complete")
            
            return complete_result
            
        except Exception as e:
            bad(f"GR to quarantine exception: {e}")
            return None
    
    def test_qc_accept_full(self, task):
        """Test 3: QC accept (full) - quarantine → available"""
        info("TEST 3: QC accept (full)")
        try:
            task_id = task["id"]
            quarantine_qty = task.get("quarantine_qty", 0)
            
            r = self.session.post(
                f"{API}/inbound/tasks/{task_id}/qc-decision",
                json={
                    "accept_qty": quarantine_qty,
                    "reject_qty": 0,
                    "reject_disposition": "damaged",
                    "reason": "Test QC accept full"
                },
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"QC accept failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            
            # Verify result
            if result.get("accepted_qty") != quarantine_qty:
                bad(f"Accepted qty mismatch: expected {quarantine_qty}, got {result.get('accepted_qty')}")
                return False
            
            if result.get("rejected_qty") != 0:
                bad(f"Rejected qty should be 0, got {result.get('rejected_qty')}")
                return False
            
            if result.get("task_status") != "completed":
                bad(f"Task status should be completed, got {result.get('task_status')}")
                return False
            
            if result.get("qc_status") != "passed":
                bad(f"QC status should be passed, got {result.get('qc_status')}")
                return False
            
            ok(f"QC accept: accepted_qty={result['accepted_qty']}, task_status={result['task_status']}, qc_status={result['qc_status']}")
            
            # Verify balance updated (quarantine → available)
            # This would require checking inventory balance endpoint
            
            return True
            
        except Exception as e:
            bad(f"QC accept exception: {e}")
            return False
    
    def test_qc_reject_damaged(self, task):
        """Test 4: QC reject damaged - quarantine → damaged"""
        info("TEST 4: QC reject damaged")
        try:
            task_id = task["id"]
            quarantine_qty = task.get("quarantine_qty", 0)
            
            r = self.session.post(
                f"{API}/inbound/tasks/{task_id}/qc-decision",
                json={
                    "accept_qty": 0,
                    "reject_qty": quarantine_qty,
                    "reject_disposition": "damaged",
                    "reason": "Test QC reject damaged"
                },
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"QC reject damaged failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            
            # Verify result
            if result.get("accepted_qty") != 0:
                bad(f"Accepted qty should be 0, got {result.get('accepted_qty')}")
                return False
            
            if result.get("rejected_qty") != quarantine_qty:
                bad(f"Rejected qty mismatch: expected {quarantine_qty}, got {result.get('rejected_qty')}")
                return False
            
            if result.get("task_status") != "qc_rejected":
                bad(f"Task status should be qc_rejected, got {result.get('task_status')}")
                return False
            
            if result.get("qc_status") != "rejected":
                bad(f"QC status should be rejected, got {result.get('qc_status')}")
                return False
            
            if result.get("reject_disposition") != "damaged":
                bad(f"Reject disposition should be damaged, got {result.get('reject_disposition')}")
                return False
            
            ok(f"QC reject damaged: rejected_qty={result['rejected_qty']}, task_status={result['task_status']}, disposition={result['reject_disposition']}")
            
            return True
            
        except Exception as e:
            bad(f"QC reject damaged exception: {e}")
            return False
    
    def test_qc_reject_return(self, task):
        """Test 5: QC reject return - creates Purchase Return (Nota Debit)"""
        info("TEST 5: QC reject return (Nota Debit)")
        try:
            task_id = task["id"]
            quarantine_qty = task.get("quarantine_qty", 0)
            
            # Partial: accept some, reject some with return
            accept_qty = round(quarantine_qty * 0.6, 2)
            reject_qty = round(quarantine_qty * 0.4, 2)
            
            r = self.session.post(
                f"{API}/inbound/tasks/{task_id}/qc-decision",
                json={
                    "accept_qty": accept_qty,
                    "reject_qty": reject_qty,
                    "reject_disposition": "return",
                    "reason": "Test QC reject return - cacat"
                },
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"QC reject return failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            
            # Verify result
            if abs(result.get("accepted_qty", 0) - accept_qty) > 0.1:
                bad(f"Accepted qty mismatch: expected ~{accept_qty}, got {result.get('accepted_qty')}")
                return False
            
            if abs(result.get("rejected_qty", 0) - reject_qty) > 0.1:
                bad(f"Rejected qty mismatch: expected ~{reject_qty}, got {result.get('rejected_qty')}")
                return False
            
            if result.get("reject_disposition") != "return":
                bad(f"Reject disposition should be return, got {result.get('reject_disposition')}")
                return False
            
            # Verify Purchase Return created
            if not result.get("purchase_return"):
                bad("Purchase return not created")
                return False
            
            pret = result["purchase_return"]
            if not pret.get("number"):
                bad("Purchase return missing number")
                return False
            
            ok(f"QC reject return: accepted={result['accepted_qty']}, rejected={result['rejected_qty']}, PR={pret['number']}")
            
            # Verify purchase_returns document exists
            r = self.session.get(f"{API}/purchase-returns", timeout=30)
            if r.status_code == 200:
                prets = r.json()
                found = any(p.get("id") == pret["id"] for p in prets)
                if found:
                    ok(f"Purchase Return document verified: {pret['number']}")
                else:
                    bad(f"Purchase Return document not found: {pret['id']}")
            
            return True
            
        except Exception as e:
            bad(f"QC reject return exception: {e}")
            return False
    
    def test_qc_validations(self):
        """Test 6: QC decision validations"""
        info("TEST 6: QC decision validations")
        
        # Get a qc_pending task
        r = self.session.get(f"{API}/inbound/qc/queue", timeout=30)
        if r.status_code != 200 or not r.json():
            info("No qc_pending tasks for validation tests")
            return True
        
        task = r.json()[0]
        task_id = task["id"]
        quarantine_qty = task.get("quarantine_qty", 0)
        
        # Test 6a: Over-allocation (accept + reject > quarantine)
        try:
            r = self.session.post(
                f"{API}/inbound/tasks/{task_id}/qc-decision",
                json={
                    "accept_qty": quarantine_qty,
                    "reject_qty": quarantine_qty,
                    "reject_disposition": "damaged",
                    "reason": "Test over-allocation"
                },
                timeout=30
            )
            
            if r.status_code == 400:
                ok("Validation: Over-allocation rejected (400)")
            else:
                bad(f"Validation: Over-allocation should return 400, got {r.status_code}")
        except Exception as e:
            bad(f"Validation over-allocation exception: {e}")
        
        # Test 6b: Both zero
        try:
            r = self.session.post(
                f"{API}/inbound/tasks/{task_id}/qc-decision",
                json={
                    "accept_qty": 0,
                    "reject_qty": 0,
                    "reject_disposition": "damaged",
                    "reason": "Test both zero"
                },
                timeout=30
            )
            
            if r.status_code == 400:
                ok("Validation: Both zero rejected (400)")
            else:
                bad(f"Validation: Both zero should return 400, got {r.status_code}")
        except Exception as e:
            bad(f"Validation both zero exception: {e}")
        
        # Test 6c: Non-qc_pending task
        try:
            # Get a completed task
            r = self.session.get(f"{API}/inbound/tasks?status=completed", timeout=30)
            if r.status_code == 200 and r.json():
                completed_task = r.json()[0]
                r = self.session.post(
                    f"{API}/inbound/tasks/{completed_task['id']}/qc-decision",
                    json={
                        "accept_qty": 10,
                        "reject_qty": 0,
                        "reject_disposition": "damaged",
                        "reason": "Test non-qc_pending"
                    },
                    timeout=30
                )
                
                if r.status_code == 400:
                    ok("Validation: Non-qc_pending task rejected (400)")
                else:
                    bad(f"Validation: Non-qc_pending should return 400, got {r.status_code}")
            else:
                info("No completed tasks for non-qc_pending validation")
        except Exception as e:
            bad(f"Validation non-qc_pending exception: {e}")
        
        return True
    
    def test_data_integrity(self):
        """Test 7: Verify data integrity after QC operations"""
        info("TEST 7: Data integrity verification")
        try:
            # Run integrity script
            import subprocess
            result = subprocess.run(
                ["python", "/app/scripts/verify_data_integrity.py"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd="/app"
            )
            
            output = result.stdout + result.stderr
            
            if "0 FAIL" in output or "INV_OK=true" in output:
                ok("Data integrity verified: 0 FAIL")
            else:
                bad(f"Data integrity issues found:\n{output[:500]}")
            
            return True
            
        except Exception as e:
            bad(f"Data integrity check exception: {e}")
            return False
    
    def run_all_tests(self):
        """Run all QC tests"""
        print("\n" + "="*70)
        print("QC HOLD / QUARANTINE BACKEND TESTS (Depth #3a)")
        print("="*70 + "\n")
        
        if not self.login():
            return False
        
        if not self.get_references():
            return False
        
        # Test 1: QC queue
        seeded_task = self.test_qc_queue_initial()
        
        # Test 2: GR to quarantine (create new qc_pending task)
        new_task = self.test_gr_to_quarantine()
        
        # Test 3: QC accept (use new task if available, else seeded)
        if new_task:
            self.test_qc_accept_full(new_task)
        elif seeded_task:
            # Don't consume seeded task yet, save for other tests
            pass
        
        # Test 4: QC reject damaged (need another task)
        new_task2 = self.test_gr_to_quarantine()
        if new_task2:
            self.test_qc_reject_damaged(new_task2)
        
        # Test 5: QC reject return (need another task)
        new_task3 = self.test_gr_to_quarantine()
        if new_task3:
            self.test_qc_reject_return(new_task3)
        
        # Test 6: Validations
        self.test_qc_validations()
        
        # Test 7: Data integrity
        self.test_data_integrity()
        
        # Summary
        print("\n" + "="*70)
        print(f"SUMMARY: {len(PASS)} PASS, {len(FAIL)} FAIL")
        print("="*70)
        
        if FAIL:
            print("\n❌ FAILED TESTS:")
            for f in FAIL:
                print(f"  - {f}")
        
        return len(FAIL) == 0


if __name__ == "__main__":
    tester = QCTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
