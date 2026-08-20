#!/usr/bin/env python3
"""
Backend API Test — Roll-as-SSOT (KN_15) Integrity Verification
================================================================
Tests the 3 proven SSOT-violation bugs that were fixed:
D1. Intra-warehouse Transfer (roll-based, multi-stage)
D2. Cycle Count (roll-aware adjustment)
D3. Manual inbound WMS task (creates roll, not bare balance)

CRITICAL: After each flow, runs verify_data_integrity.py to confirm
balance == Σ rolls (INV-ROLL-1) and no drift.
"""
import os
import sys
import requests
import subprocess
from datetime import datetime

BASE = os.environ.get("BACKEND_URL", "https://epic-cannon-6.preview.emergentagent.com").rstrip("/")
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


def run_integrity_gate():
    """Run verify_data_integrity.py and return (exit_code, pass_count, fail_count)"""
    try:
        result = subprocess.run(
            ["python", "/app/scripts/verify_data_integrity.py"],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=60
        )
        output = result.stdout + result.stderr
        # Parse PASS/FAIL counts from output
        pass_count = output.count("[PASS]")
        fail_count = output.count("[FAIL]")
        return result.returncode, pass_count, fail_count, output
    except Exception as e:
        return -1, 0, 0, str(e)


class RollSSOTTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.entity_id = None
        self.warehouse_ids = []
        self.product_id = None
        
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
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "X-Entity-Id": "all"
            })
            ok("Login admin@kainnusantara.id")
            return True
        except Exception as e:
            bad(f"Login exception: {e}")
            return False
    
    def setup_references(self):
        """Get entity, warehouses, product references"""
        try:
            # Get entity
            r = self.session.get(f"{API}/entities", timeout=30)
            if r.status_code != 200:
                bad(f"Get entities failed: {r.status_code}")
                return False
            entities = r.json()
            if not entities:
                bad("No entities found")
                return False
            self.entity_id = entities[0]["id"]
            
            # Get warehouses (need at least 2 for transfer)
            r = self.session.get(f"{API}/warehouses", timeout=30)
            if r.status_code != 200:
                bad(f"Get warehouses failed: {r.status_code}")
                return False
            warehouses = r.json()
            if len(warehouses) < 2:
                bad(f"Need at least 2 warehouses, found {len(warehouses)}")
                return False
            self.warehouse_ids = [w["id"] for w in warehouses[:2]]
            
            # Get product with available stock
            r = self.session.get(f"{API}/inventory/balances", timeout=30)
            if r.status_code != 200:
                bad(f"Get balances failed: {r.status_code}")
                return False
            balances = r.json()
            # Find product with available stock at source warehouse
            for bal in balances:
                if bal.get("warehouse_id") == self.warehouse_ids[0] and float(bal.get("available_qty", 0)) > 10:
                    self.product_id = bal["product_id"]
                    break
            
            if not self.product_id:
                bad("No product with available stock found at source warehouse")
                return False
            
            ok(f"Setup: entity={self.entity_id[:8]}, warehouses={len(self.warehouse_ids)}, product={self.product_id[:8]}")
            return True
        except Exception as e:
            bad(f"Setup references exception: {e}")
            return False
    
    def test_d1_intra_warehouse_transfer(self):
        """D1 — Intra-warehouse Transfer (roll-based, multi-stage)"""
        info("\n=== D1: Intra-warehouse Transfer (roll-based) ===")
        
        try:
            source_wh = self.warehouse_ids[0]
            dest_wh = self.warehouse_ids[1]
            transfer_qty = 5.0
            
            # Get initial balance at source
            r = self.session.get(f"{API}/inventory/balances", timeout=30)
            balances = r.json()
            source_bal = next((b for b in balances if b["product_id"] == self.product_id and b["warehouse_id"] == source_wh), None)
            if not source_bal:
                bad("D1: Source balance not found")
                return False
            
            initial_source_avail = float(source_bal.get("available_qty", 0))
            info(f"Initial source available: {initial_source_avail}")
            
            # 1. Create transfer (should RESERVE rolls at source immediately)
            r = self.session.post(
                f"{API}/transfers",
                json={
                    "source_warehouse_id": source_wh,
                    "dest_warehouse_id": dest_wh,
                    "items": [{"product_id": self.product_id, "qty": transfer_qty}],
                    "notes": "Test D1 transfer",
                    "requested_by": "Test Admin"
                },
                timeout=30
            )
            if r.status_code != 200:
                bad(f"D1: Create transfer failed: {r.status_code} {r.text[:200]}")
                return False
            
            transfer = r.json()
            transfer_id = transfer["id"]
            ok(f"D1: Created transfer {transfer['code']}, status={transfer['status']}")
            
            # Verify source available dropped immediately (reserved)
            r = self.session.get(f"{API}/inventory/balances", timeout=30)
            balances = r.json()
            source_bal_after = next((b for b in balances if b["product_id"] == self.product_id and b["warehouse_id"] == source_wh), None)
            new_source_avail = float(source_bal_after.get("available_qty", 0))
            
            if abs(new_source_avail - (initial_source_avail - transfer_qty)) > 0.5:
                bad(f"D1: Source available not reduced correctly: {new_source_avail} (expected ~{initial_source_avail - transfer_qty})")
                return False
            ok(f"D1: Source available reduced to {new_source_avail} (reserved {transfer_qty})")
            
            # 2. Approve transfer
            r = self.session.post(
                f"{API}/transfers/{transfer_id}/approve",
                json={"approved_by": "Test Manager"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"D1: Approve failed: {r.status_code} {r.text[:200]}")
                return False
            ok("D1: Transfer approved")
            
            # 3. Progress through stages: picking → staging → dispatched
            for status in ["picking", "staging", "dispatched"]:
                r = self.session.post(
                    f"{API}/transfers/{transfer_id}/status",
                    json={"status": status, "updated_by": "Test Warehouse"},
                    timeout=30
                )
                if r.status_code != 200:
                    bad(f"D1: Status update to {status} failed: {r.status_code}")
                    return False
                ok(f"D1: Transfer status → {status}")
            
            # 4. Complete transfer (rolls should move to destination)
            r = self.session.post(
                f"{API}/transfers/{transfer_id}/status",
                json={"status": "completed", "updated_by": "Test Warehouse"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"D1: Complete failed: {r.status_code} {r.text[:200]}")
                return False
            ok("D1: Transfer completed")
            
            # 5. Verify rolls at destination
            r = self.session.get(f"{API}/inventory/rolls?warehouse_id={dest_wh}&product_id={self.product_id}", timeout=30)
            if r.status_code != 200:
                bad(f"D1: Get destination rolls failed: {r.status_code}")
                return False
            
            dest_rolls = r.json()
            if isinstance(dest_rolls, dict):
                dest_rolls = dest_rolls.get("items", [])
            
            dest_available_qty = sum(float(roll.get("length_remaining", 0)) for roll in dest_rolls if roll.get("status") == "available")
            
            if dest_available_qty < transfer_qty - 0.5:
                bad(f"D1: Destination available qty {dest_available_qty} < transferred {transfer_qty}")
                return False
            ok(f"D1: Destination has {dest_available_qty} available (transferred {transfer_qty})")
            
            # 6. Run integrity gate
            info("D1: Running integrity gate...")
            exit_code, pass_count, fail_count, output = run_integrity_gate()
            if exit_code != 0 or fail_count > 0:
                bad(f"D1: Integrity gate FAILED: exit={exit_code}, PASS={pass_count}, FAIL={fail_count}")
                info(f"Gate output:\n{output[-500:]}")
                return False
            ok(f"D1: Integrity gate PASSED: {pass_count} checks, 0 FAIL")
            
            return True
            
        except Exception as e:
            bad(f"D1 exception: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_d1_negative_insufficient_stock(self):
        """D1 negative — POST /api/transfers with qty > available must return 409"""
        info("\n=== D1 negative: Insufficient stock ===")
        
        try:
            source_wh = self.warehouse_ids[0]
            dest_wh = self.warehouse_ids[1]
            
            # Get current available
            r = self.session.get(f"{API}/inventory/balances", timeout=30)
            balances = r.json()
            source_bal = next((b for b in balances if b["product_id"] == self.product_id and b["warehouse_id"] == source_wh), None)
            if not source_bal:
                bad("D1-neg: Source balance not found")
                return False
            
            available = float(source_bal.get("available_qty", 0))
            excessive_qty = available + 100.0
            
            # Try to create transfer with excessive qty
            r = self.session.post(
                f"{API}/transfers",
                json={
                    "source_warehouse_id": source_wh,
                    "dest_warehouse_id": dest_wh,
                    "items": [{"product_id": self.product_id, "qty": excessive_qty}],
                    "notes": "Test insufficient stock",
                    "requested_by": "Test Admin"
                },
                timeout=30
            )
            
            if r.status_code == 409:
                ok(f"D1-neg: Correctly returned 409 for qty {excessive_qty} > available {available}")
                return True
            else:
                bad(f"D1-neg: Expected 409, got {r.status_code}")
                return False
                
        except Exception as e:
            bad(f"D1-neg exception: {e}")
            return False
    
    def test_d2_cycle_count(self):
        """D2 — Cycle Count (roll-aware adjustment)"""
        info("\n=== D2: Cycle Count (roll-aware) ===")
        
        try:
            warehouse_id = self.warehouse_ids[0]
            
            # 1. Create cycle count session
            r = self.session.post(
                f"{API}/cycle-count/sessions",
                json={
                    "warehouse_id": warehouse_id,
                    "name": "Test D2 Cycle Count",
                    "notes": "Testing roll-aware adjustment"
                },
                timeout=30
            )
            if r.status_code != 200:
                bad(f"D2: Create session failed: {r.status_code} {r.text[:200]}")
                return False
            
            session = r.json()
            session_id = session["id"]
            ok(f"D2: Created cycle count session {session['name']}")
            
            # 2. Add item to count
            r = self.session.post(
                f"{API}/cycle-count/sessions/{session_id}/items",
                json={"product_id": self.product_id},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"D2: Add item failed: {r.status_code} {r.text[:200]}")
                return False
            
            item = r.json()
            item_id = item["id"]
            expected_qty = float(item.get("expected_qty", 0))
            owner_entity_id = item.get("owner_entity_id")
            ok(f"D2: Added item, expected_qty={expected_qty}, owner={owner_entity_id[:8] if owner_entity_id else 'N/A'}")
            
            # 3. Update with actual qty (surplus of +7)
            actual_qty = expected_qty + 7.0
            r = self.session.patch(
                f"{API}/cycle-count/sessions/{session_id}/items/{item_id}",
                json={"actual_qty": actual_qty, "notes": "Found surplus"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"D2: Update item failed: {r.status_code} {r.text[:200]}")
                return False
            ok(f"D2: Updated actual_qty={actual_qty} (surplus +7)")
            
            # 4. Submit session
            r = self.session.post(
                f"{API}/cycle-count/sessions/{session_id}/submit",
                timeout=30
            )
            if r.status_code != 200:
                bad(f"D2: Submit failed: {r.status_code} {r.text[:200]}")
                return False
            ok("D2: Session submitted")
            
            # 5. Approve session (should create roll adjustment)
            r = self.session.post(
                f"{API}/cycle-count/sessions/{session_id}/approve",
                json={"reason": "Test approval"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"D2: Approve failed: {r.status_code} {r.text[:200]}")
                return False
            ok("D2: Session approved")
            
            # 6. Verify adjustment created roll (check movements)
            r = self.session.get(f"{API}/inventory/movements?limit=50", timeout=30)
            if r.status_code != 200:
                bad(f"D2: Get movements failed: {r.status_code}")
                return False
            
            movements = r.json()
            if isinstance(movements, dict):
                movements = movements.get("items", [])
            
            # Find cycle_count_adjustment movement with roll_id
            adjustment_mov = None
            for mov in movements:
                if mov.get("movement_type") == "cycle_count_adjustment" and mov.get("source_document") == session_id:
                    adjustment_mov = mov
                    break
            
            if not adjustment_mov:
                bad("D2: No cycle_count_adjustment movement found")
                return False
            
            if not adjustment_mov.get("roll_id"):
                bad("D2: Adjustment movement missing roll_id (not roll-linked)")
                return False
            
            ok(f"D2: Adjustment movement has roll_id={adjustment_mov['roll_id'][:8]}")
            
            # 7. Verify rolls reflect the surplus
            r = self.session.get(f"{API}/inventory/rolls?warehouse_id={warehouse_id}&product_id={self.product_id}", timeout=30)
            if r.status_code != 200:
                bad(f"D2: Get rolls failed: {r.status_code}")
                return False
            
            rolls = r.json()
            if isinstance(rolls, dict):
                rolls = rolls.get("items", [])
            
            # Check if there's a roll created by cycle count
            cycle_roll = None
            for roll in rolls:
                if roll.get("acquired", {}).get("via") == "cycle_count_adjustment":
                    cycle_roll = roll
                    break
            
            if not cycle_roll:
                bad("D2: No roll created via cycle_count_adjustment")
                return False
            
            ok(f"D2: Found roll created by cycle count: {cycle_roll['id'][:8]}, length={cycle_roll.get('length_remaining')}")
            
            # 8. Run integrity gate
            info("D2: Running integrity gate...")
            exit_code, pass_count, fail_count, output = run_integrity_gate()
            if exit_code != 0 or fail_count > 0:
                bad(f"D2: Integrity gate FAILED: exit={exit_code}, PASS={pass_count}, FAIL={fail_count}")
                info(f"Gate output:\n{output[-500:]}")
                return False
            ok(f"D2: Integrity gate PASSED: {pass_count} checks, 0 FAIL")
            
            return True
            
        except Exception as e:
            bad(f"D2 exception: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_d3_manual_inbound(self):
        """D3 — Manual inbound WMS task (creates roll, not bare balance)"""
        info("\n=== D3: Manual inbound WMS task ===")
        
        try:
            warehouse_id = self.warehouse_ids[0]
            inbound_qty = 10.0
            
            # Get initial roll count
            r = self.session.get(f"{API}/inventory/rolls?warehouse_id={warehouse_id}&product_id={self.product_id}", timeout=30)
            if r.status_code != 200:
                bad(f"D3: Get initial rolls failed: {r.status_code}")
                return False
            
            initial_rolls = r.json()
            if isinstance(initial_rolls, dict):
                initial_rolls = initial_rolls.get("items", [])
            initial_count = len(initial_rolls)
            
            # Create manual inbound task
            r = self.session.post(
                f"{API}/wms/tasks",
                json={
                    "flow_type": "inbound",
                    "source_type": "supplier",
                    "product_id": self.product_id,
                    "warehouse_id": warehouse_id,
                    "quantity": inbound_qty,
                    "unit": "meter",
                    "bin_id": "",
                    "batch": "TEST-BATCH",
                    "lot": "TEST-LOT-D3",
                    "roll_id": ""
                },
                timeout=30
            )
            if r.status_code != 200:
                bad(f"D3: Create inbound task failed: {r.status_code} {r.text[:200]}")
                return False
            
            task = r.json()
            task_id = task["id"]
            roll_id = task.get("roll_id")
            
            if not roll_id:
                bad("D3: Task response missing roll_id")
                return False
            
            ok(f"D3: Created inbound task {task_id[:8]}, roll_id={roll_id[:8]}")
            
            # Verify roll was created
            r = self.session.get(f"{API}/inventory/rolls?warehouse_id={warehouse_id}&product_id={self.product_id}", timeout=30)
            if r.status_code != 200:
                bad(f"D3: Get rolls after inbound failed: {r.status_code}")
                return False
            
            new_rolls = r.json()
            if isinstance(new_rolls, dict):
                new_rolls = new_rolls.get("items", [])
            new_count = len(new_rolls)
            
            if new_count <= initial_count:
                bad(f"D3: Roll count did not increase: {initial_count} → {new_count}")
                return False
            
            ok(f"D3: Roll count increased: {initial_count} → {new_count}")
            
            # Find the specific roll
            created_roll = next((r for r in new_rolls if r["id"] == roll_id), None)
            if not created_roll:
                bad(f"D3: Roll {roll_id} not found in inventory_rolls")
                return False
            
            if created_roll.get("status") != "available":
                bad(f"D3: Roll status is {created_roll.get('status')}, expected 'available'")
                return False
            
            roll_qty = float(created_roll.get("length_remaining", 0))
            if abs(roll_qty - inbound_qty) > 0.1:
                bad(f"D3: Roll qty {roll_qty} != inbound qty {inbound_qty}")
                return False
            
            ok(f"D3: Roll created correctly: status=available, qty={roll_qty}")
            
            # Run integrity gate
            info("D3: Running integrity gate...")
            exit_code, pass_count, fail_count, output = run_integrity_gate()
            if exit_code != 0 or fail_count > 0:
                bad(f"D3: Integrity gate FAILED: exit={exit_code}, PASS={pass_count}, FAIL={fail_count}")
                info(f"Gate output:\n{output[-500:]}")
                return False
            ok(f"D3: Integrity gate PASSED: {pass_count} checks, 0 FAIL")
            
            return True
            
        except Exception as e:
            bad(f"D3 exception: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_regression_inter_company_transfer(self):
        """Regression — Inter-company transfer still works"""
        info("\n=== Regression: Inter-company transfer ===")
        
        try:
            # Get entities
            r = self.session.get(f"{API}/entities", timeout=30)
            entities = r.json()
            if len(entities) < 2:
                info("Regression: Skipping inter-company test (need 2+ entities)")
                return True
            
            source_entity = entities[0]["id"]
            dest_entity = entities[1]["id"]
            
            # Create inter-company transfer
            r = self.session.post(
                f"{API}/transfers/inter-company",
                json={
                    "source_entity_id": source_entity,
                    "dest_entity_id": dest_entity,
                    "items": [{"product_id": self.product_id, "quantity": 3.0, "unit": "meter"}],
                    "transfer_price": 100.0,
                    "notes": "Test inter-company",
                    "requested_by": "Test Admin"
                },
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Regression: Inter-company create failed: {r.status_code} {r.text[:200]}")
                return False
            
            transfer = r.json()
            transfer_id = transfer["id"]
            ok(f"Regression: Created inter-company transfer {transfer['code']}")
            
            # Approve (should execute ownership transfer)
            r = self.session.post(
                f"{API}/transfers/{transfer_id}/approve",
                json={"approved_by": "Test Manager"},
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Regression: Inter-company approve failed: {r.status_code} {r.text[:200]}")
                return False
            
            approved = r.json()
            if approved.get("status") != "completed":
                bad(f"Regression: Inter-company status is {approved.get('status')}, expected 'completed'")
                return False
            
            ok("Regression: Inter-company transfer approved and completed")
            
            return True
            
        except Exception as e:
            bad(f"Regression exception: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    print("\n" + "="*70)
    print("  Roll-as-SSOT (KN_15) Backend API Test")
    print("  Testing D1, D2, D3 SSOT-violation fixes")
    print("="*70 + "\n")
    
    tester = RollSSOTTester()
    
    # Login and setup
    if not tester.login():
        print("\n❌ Login failed, cannot proceed")
        return 1
    
    if not tester.setup_references():
        print("\n❌ Setup failed, cannot proceed")
        return 1
    
    # Run tests
    tests = [
        ("D1: Intra-warehouse Transfer", tester.test_d1_intra_warehouse_transfer),
        ("D1-neg: Insufficient stock", tester.test_d1_negative_insufficient_stock),
        ("D2: Cycle Count", tester.test_d2_cycle_count),
        ("D3: Manual inbound", tester.test_d3_manual_inbound),
        ("Regression: Inter-company", tester.test_regression_inter_company_transfer),
    ]
    
    for name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            bad(f"{name} crashed: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*70)
    print(f"  ✅ PASSED: {len(PASS)}")
    print(f"  ❌ FAILED: {len(FAIL)}")
    print("="*70)
    
    if FAIL:
        print("\nFailed tests:")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    
    print("\n✅ All tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
