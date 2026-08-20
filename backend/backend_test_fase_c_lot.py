#!/usr/bin/env python3
"""
Backend API Test — FASE C: LOT KELAS SATU
==========================================
Comprehensive test for Phase C Lot Management features covering:
1. Lot CRUD operations (list, create, get, patch, status)
2. Lot settings (enforcement mode: warn/block)
3. Lot statistics and filtering
4. Genealogy operations (split, merge, rework)
5. Genealogy tree and recall
6. Label/QR generation
7. Integration with GR (goods receiving)
8. Integration with QC (quality control)
9. RBAC (role-based access control)
10. Roll-lot relationships

Usage: cd /app && python backend/backend_test_fase_c_lot.py
"""
import os
import sys
import requests
from datetime import datetime

# Get backend URL from environment
BASE = os.environ.get("BACKEND_URL", "https://kn-lot-tracking.preview.emergentagent.com").rstrip("/")
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


def head(m):
    print(f"\n\033[96m\033[1m{m}\033[0m")


class LotTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.entity_id = None
        self.product_id = None
        self.warehouse_id = None
        self.lot_id = None
        self.lot_id_2 = None
        
    def login(self, email="admin@kainnusantara.id", password="demo12345"):
        """Login with specified credentials"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed for {email}: {r.status_code} {r.text[:100]}")
                return False
            data = r.json()
            self.token = data.get("token")
            if not self.token:
                bad(f"Login response missing token for {email}")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            ok(f"Login {email}")
            return True
        except Exception as e:
            bad(f"Login exception for {email}: {e}")
            return False
    
    def setup_references(self):
        """Get entity, product, warehouse references"""
        try:
            # Get entity
            r = self.session.get(f"{API}/entities", timeout=30)
            if r.status_code == 200:
                entities = r.json()
                if entities:
                    self.entity_id = entities[0]["id"]
            
            # Get a product
            r = self.session.get(f"{API}/products?limit=1", timeout=30)
            if r.status_code == 200:
                products = r.json()
                if products:
                    self.product_id = products[0]["id"]
            
            # Get a warehouse
            r = self.session.get(f"{API}/warehouses?limit=1", timeout=30)
            if r.status_code == 200:
                warehouses = r.json()
                if warehouses:
                    self.warehouse_id = warehouses[0]["id"]
            
            ok(f"Setup references: entity={self.entity_id[:8] if self.entity_id else 'N/A'}, "
               f"product={self.product_id[:8] if self.product_id else 'N/A'}, "
               f"warehouse={self.warehouse_id[:8] if self.warehouse_id else 'N/A'}")
            return True
        except Exception as e:
            bad(f"Setup references exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 1: LOT LIST & FILTERING
    # ═══════════════════════════════════════════════════════════════════════
    def test_lot_list(self):
        head("TEST 1 — GET /api/lots (list with filters)")
        try:
            # Basic list
            r = self.session.get(f"{API}/lots", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/lots failed: {r.status_code} {r.text[:200]}")
                return False
            
            lots = r.json()
            if isinstance(lots, list):
                ok(f"GET /api/lots returned list with {len(lots)} lots")
            else:
                bad(f"GET /api/lots returned non-list: {type(lots)}")
                return False
            
            # Test pagination
            r = self.session.get(f"{API}/lots?page=1&page_size=5", timeout=30)
            if r.status_code == 200:
                body = r.json()
                if isinstance(body, dict) and "items" in body and "total" in body:
                    ok(f"Pagination works: page_size={body.get('page_size')}, total={body.get('total')}")
                else:
                    bad(f"Pagination envelope incorrect: {list(body.keys())}")
            else:
                bad(f"Pagination failed: {r.status_code}")
            
            # Test filtering
            if lots:
                first_lot = lots[0]
                if first_lot.get("product_id"):
                    r = self.session.get(f"{API}/lots?product_id={first_lot['product_id']}", timeout=30)
                    if r.status_code == 200:
                        filtered = r.json()
                        ok(f"Filter by product_id works: {len(filtered)} lots")
                    else:
                        bad(f"Filter by product_id failed: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"test_lot_list exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 2: LOT STATISTICS
    # ═══════════════════════════════════════════════════════════════════════
    def test_lot_stats(self):
        head("TEST 2 — GET /api/lots/stats")
        try:
            r = self.session.get(f"{API}/lots/stats", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/lots/stats failed: {r.status_code} {r.text[:200]}")
                return False
            
            stats = r.json()
            required_keys = ["total", "by_status", "by_source", "rolls_in_lots", 
                           "incomplete_capture", "rolls_without_lot", "settings"]
            
            missing = [k for k in required_keys if k not in stats]
            if missing:
                bad(f"Stats missing keys: {missing}")
                return False
            
            ok(f"Stats complete: {stats['total']} lots, {stats['rolls_in_lots']} rolls, "
               f"{stats['rolls_without_lot']} rolls without lot")
            
            if stats["rolls_without_lot"] == 0:
                ok("No rolls without lot (clean data)")
            else:
                info(f"Warning: {stats['rolls_without_lot']} rolls without lot")
            
            return True
        except Exception as e:
            bad(f"test_lot_stats exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 3: LOT SETTINGS (GET/PUT)
    # ═══════════════════════════════════════════════════════════════════════
    def test_lot_settings(self):
        head("TEST 3 — GET/PUT /api/lots/settings (enforcement mode)")
        try:
            # Get current settings
            r = self.session.get(f"{API}/lots/settings", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/lots/settings failed: {r.status_code} {r.text[:200]}")
                return False
            
            settings = r.json()
            required_keys = ["enforcement_mode", "require_supplier_lot", "require_dye_lot", 
                           "auto_create_on_receiving", "status_on_receipt"]
            
            missing = [k for k in required_keys if k not in settings]
            if missing:
                bad(f"Settings missing keys: {missing}")
                return False
            
            ok(f"Settings retrieved: enforcement_mode={settings['enforcement_mode']}")
            
            # Save original mode
            original_mode = settings["enforcement_mode"]
            
            # Test changing to block
            r = self.session.put(f"{API}/lots/settings", 
                               json={"enforcement_mode": "block"}, timeout=30)
            if r.status_code != 200:
                bad(f"PUT /api/lots/settings (block) failed: {r.status_code} {r.text[:200]}")
                return False
            
            updated = r.json()
            if updated["enforcement_mode"] == "block":
                ok("Changed enforcement_mode to 'block'")
            else:
                bad(f"Mode not changed to block: {updated['enforcement_mode']}")
            
            # Restore to warn (CRITICAL: must not leave in block mode)
            r = self.session.put(f"{API}/lots/settings", 
                               json={"enforcement_mode": "warn"}, timeout=30)
            if r.status_code == 200 and r.json()["enforcement_mode"] == "warn":
                ok("Restored enforcement_mode to 'warn' (default)")
            else:
                bad(f"Failed to restore to warn: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"test_lot_settings exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 4: CREATE LOT (POST)
    # ═══════════════════════════════════════════════════════════════════════
    def test_create_lot(self):
        head("TEST 4 — POST /api/lots (create manual lot)")
        try:
            if not self.product_id or not self.entity_id:
                bad("Missing product_id or entity_id for lot creation")
                return False
            
            payload = {
                "product_id": self.product_id,
                "owner_entity_id": self.entity_id,
                "warehouse_id": self.warehouse_id or "",
                "supplier_lot": "TEST-SUP-001",
                "dye_lot": "TEST-DYE-001",
                "shade_ref": "SHADE-A",
                "note": "Test lot for Fase C"
            }
            
            r = self.session.post(f"{API}/lots", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"POST /api/lots failed: {r.status_code} {r.text[:200]}")
                return False
            
            lot = r.json()
            self.lot_id = lot.get("id")
            
            # Verify lot number format: KSC/LOT-YYMM-####
            import re
            ym = datetime.now().strftime("%y%m")
            if re.match(rf"^[A-Z0-9]+/LOT-{ym}-\d{{4}}$", lot["lot_number"]):
                ok(f"Lot created with correct format: {lot['lot_number']}")
            else:
                bad(f"Lot number format incorrect: {lot['lot_number']}")
            
            # Verify fields
            if lot.get("supplier_lot") == "TEST-SUP-001":
                ok("supplier_lot saved correctly")
            else:
                bad(f"supplier_lot incorrect: {lot.get('supplier_lot')}")
            
            if lot.get("dye_lot") == "TEST-DYE-001":
                ok("dye_lot saved correctly")
            else:
                bad(f"dye_lot incorrect: {lot.get('dye_lot')}")
            
            return True
        except Exception as e:
            bad(f"test_create_lot exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 5: GET LOT DETAIL
    # ═══════════════════════════════════════════════════════════════════════
    def test_get_lot(self):
        head("TEST 5 — GET /api/lots/{id} (detail with rolls, parents, children)")
        try:
            if not self.lot_id:
                bad("No lot_id available for detail test")
                return False
            
            r = self.session.get(f"{API}/lots/{self.lot_id}", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/lots/{self.lot_id} failed: {r.status_code} {r.text[:200]}")
                return False
            
            lot = r.json()
            
            # Check required fields
            required = ["id", "lot_number", "product_id", "rolls", "parents", "children", "warnings"]
            missing = [k for k in required if k not in lot]
            if missing:
                bad(f"Lot detail missing keys: {missing}")
                return False
            
            ok(f"Lot detail complete: {lot['lot_number']}, {len(lot['rolls'])} rolls")
            
            if isinstance(lot["warnings"], list):
                ok(f"Warnings field present: {len(lot['warnings'])} warnings")
            else:
                bad(f"Warnings field incorrect type: {type(lot['warnings'])}")
            
            return True
        except Exception as e:
            bad(f"test_get_lot exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 6: PATCH LOT
    # ═══════════════════════════════════════════════════════════════════════
    def test_patch_lot(self):
        head("TEST 6 — PATCH /api/lots/{id} (update supplier_lot, dye_lot)")
        try:
            if not self.lot_id:
                bad("No lot_id available for patch test")
                return False
            
            payload = {
                "supplier_lot": "TEST-SUP-002-UPDATED",
                "dye_lot": "TEST-DYE-002-UPDATED",
                "note": "Updated note"
            }
            
            r = self.session.patch(f"{API}/lots/{self.lot_id}", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"PATCH /api/lots/{self.lot_id} failed: {r.status_code} {r.text[:200]}")
                return False
            
            lot = r.json()
            
            if lot.get("supplier_lot") == "TEST-SUP-002-UPDATED":
                ok("supplier_lot updated successfully")
            else:
                bad(f"supplier_lot not updated: {lot.get('supplier_lot')}")
            
            if lot.get("dye_lot") == "TEST-DYE-002-UPDATED":
                ok("dye_lot updated successfully")
            else:
                bad(f"dye_lot not updated: {lot.get('dye_lot')}")
            
            return True
        except Exception as e:
            bad(f"test_patch_lot exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 7: LOT STATUS CHANGE
    # ═══════════════════════════════════════════════════════════════════════
    def test_lot_status(self):
        head("TEST 7 — POST /api/lots/{id}/status (change lot status)")
        try:
            if not self.lot_id:
                bad("No lot_id available for status test")
                return False
            
            # Test valid status change
            payload = {
                "status": "hold_shade",
                "reason": "Testing status change"
            }
            
            r = self.session.post(f"{API}/lots/{self.lot_id}/status", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"POST /api/lots/{self.lot_id}/status failed: {r.status_code} {r.text[:200]}")
                return False
            
            lot = r.json()
            if lot.get("lot_status") == "hold_shade":
                ok("Lot status changed to 'hold_shade'")
            else:
                bad(f"Lot status not changed: {lot.get('lot_status')}")
            
            # Test invalid status (should fail)
            r = self.session.post(f"{API}/lots/{self.lot_id}/status", 
                                json={"status": "invalid_status"}, timeout=30)
            if r.status_code == 400:
                ok("Invalid status rejected with 400")
            else:
                bad(f"Invalid status not rejected: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"test_lot_status exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 8: GENEALOGY - SPLIT
    # ═══════════════════════════════════════════════════════════════════════
    def test_lot_split(self):
        head("TEST 8 — POST /api/lots/{id}/split (split lot)")
        try:
            # First, get a lot with multiple rolls
            r = self.session.get(f"{API}/lots", timeout=30)
            if r.status_code != 200:
                bad("Cannot get lots for split test")
                return False
            
            lots = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            lot_with_rolls = None
            for lot in lots:
                r2 = self.session.get(f"{API}/lots/{lot['id']}", timeout=30)
                if r2.status_code == 200:
                    detail = r2.json()
                    if len(detail.get("rolls", [])) >= 2:
                        lot_with_rolls = detail
                        break
            
            if not lot_with_rolls:
                info("No lot with >=2 rolls found, skipping split test")
                return True
            
            # Test split all rolls (should fail)
            all_roll_ids = [r["id"] for r in lot_with_rolls["rolls"]]
            r = self.session.post(f"{API}/lots/{lot_with_rolls['id']}/split",
                                json={"roll_ids": all_roll_ids, "reason": "Test split all"},
                                timeout=30)
            if r.status_code == 400 and "minimal 1 roll" in r.text.lower():
                ok("Split all rolls rejected with clear message")
            else:
                bad(f"Split all rolls not rejected properly: {r.status_code}")
            
            # Test split partial (should succeed)
            r = self.session.post(f"{API}/lots/{lot_with_rolls['id']}/split",
                                json={"roll_ids": [all_roll_ids[0]], "reason": "Test split partial"},
                                timeout=30)
            if r.status_code == 200:
                result = r.json()
                if "parent" in result and "child" in result:
                    ok(f"Split successful: {result['parent']['lot_number']} → {result['child']['lot_number']}")
                    
                    # Verify genealogy
                    child = result["child"]
                    parent = result["parent"]
                    if child["id"] in parent.get("child_lot_ids", []):
                        ok("Parent-child relationship established")
                    else:
                        bad("Parent-child relationship not established")
                else:
                    bad(f"Split response missing parent/child: {list(result.keys())}")
            else:
                bad(f"Split partial failed: {r.status_code} {r.text[:200]}")
            
            return True
        except Exception as e:
            bad(f"test_lot_split exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 9: GENEALOGY - MERGE
    # ═══════════════════════════════════════════════════════════════════════
    def test_lot_merge(self):
        head("TEST 9 — POST /api/lots/merge (merge lots)")
        try:
            # Get at least 2 lots with same product
            r = self.session.get(f"{API}/lots?limit=50", timeout=30)
            if r.status_code != 200:
                bad("Cannot get lots for merge test")
                return False
            
            lots = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            
            # Group by product_id
            by_product = {}
            for lot in lots:
                pid = lot.get("product_id")
                if pid:
                    if pid not in by_product:
                        by_product[pid] = []
                    by_product[pid].append(lot)
            
            # Find product with >=2 lots
            mergeable = None
            for pid, plots in by_product.items():
                if len(plots) >= 2:
                    mergeable = plots[:2]
                    break
            
            if not mergeable:
                info("No 2 lots with same product found, skipping merge test")
                return True
            
            # Test merge with <2 lots (should fail)
            r = self.session.post(f"{API}/lots/merge",
                                json={"lot_ids": [mergeable[0]["id"]], "reason": "Test merge single"},
                                timeout=30)
            if r.status_code == 400:
                ok("Merge with <2 lots rejected")
            else:
                bad(f"Merge with <2 lots not rejected: {r.status_code}")
            
            # Test merge with 2 lots (should succeed)
            r = self.session.post(f"{API}/lots/merge",
                                json={"lot_ids": [mergeable[0]["id"], mergeable[1]["id"]], 
                                     "reason": "Test merge two lots"},
                                timeout=30)
            if r.status_code == 200:
                result = r.json()
                if "lot" in result and len(result["lot"].get("parent_lot_ids", [])) == 2:
                    ok(f"Merge successful: {result['lot']['lot_number']} with 2 parents")
                else:
                    bad(f"Merge result incorrect: {result.get('lot', {}).get('parent_lot_ids')}")
            else:
                bad(f"Merge failed: {r.status_code} {r.text[:200]}")
            
            return True
        except Exception as e:
            bad(f"test_lot_merge exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 10: GENEALOGY - REWORK
    # ═══════════════════════════════════════════════════════════════════════
    def test_lot_rework(self):
        head("TEST 10 — POST /api/lots/{id}/rework (rework lot)")
        try:
            if not self.lot_id:
                bad("No lot_id available for rework test")
                return False
            
            # Test invalid process_type (should fail)
            r = self.session.post(f"{API}/lots/{self.lot_id}/rework",
                                json={"process_type": "invalid_process", "reason": "Test"},
                                timeout=30)
            if r.status_code == 400:
                ok("Invalid process_type rejected")
            else:
                bad(f"Invalid process_type not rejected: {r.status_code}")
            
            # Test invalid stage transition (should fail)
            r = self.session.post(f"{API}/lots/{self.lot_id}/rework",
                                json={"process_type": "tenun", "to_stage": "grey", 
                                     "reason": "Test invalid transition"},
                                timeout=30)
            if r.status_code == 400:
                ok("Invalid stage transition rejected by state machine")
            else:
                info(f"Stage transition validation: {r.status_code}")
            
            # Test valid rework (should succeed)
            r = self.session.post(f"{API}/lots/{self.lot_id}/rework",
                                json={"process_type": "finishing", "reason": "Test rework"},
                                timeout=30)
            if r.status_code == 200:
                result = r.json()
                if "parent" in result and "child" in result:
                    ok(f"Rework successful: {result['child']['lot_number']}")
                    if result["parent"].get("lot_status") == "rework":
                        ok("Parent lot status changed to 'rework'")
                    else:
                        bad(f"Parent status not 'rework': {result['parent'].get('lot_status')}")
                else:
                    bad(f"Rework response missing parent/child")
            else:
                bad(f"Rework failed: {r.status_code} {r.text[:200]}")
            
            return True
        except Exception as e:
            bad(f"test_lot_rework exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 11: GENEALOGY TREE
    # ═══════════════════════════════════════════════════════════════════════
    def test_genealogy(self):
        head("TEST 11 — GET /api/lots/{id}/genealogy (genealogy tree)")
        try:
            if not self.lot_id:
                bad("No lot_id available for genealogy test")
                return False
            
            r = self.session.get(f"{API}/lots/{self.lot_id}/genealogy", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/lots/{self.lot_id}/genealogy failed: {r.status_code} {r.text[:200]}")
                return False
            
            genealogy = r.json()
            
            required = ["nodes", "edges", "chain", "documents"]
            missing = [k for k in required if k not in genealogy]
            if missing:
                bad(f"Genealogy missing keys: {missing}")
                return False
            
            ok(f"Genealogy complete: {len(genealogy['nodes'])} nodes, {len(genealogy['edges'])} edges")
            
            if genealogy.get("chain"):
                ok(f"Stage chain present: {' → '.join([c['stage'] for c in genealogy['chain']])}")
            
            return True
        except Exception as e:
            bad(f"test_genealogy exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 12: RECALL
    # ═══════════════════════════════════════════════════════════════════════
    def test_recall(self):
        head("TEST 12 — GET /api/lots/{id}/recall (recall tracing)")
        try:
            if not self.lot_id:
                bad("No lot_id available for recall test")
                return False
            
            r = self.session.get(f"{API}/lots/{self.lot_id}/recall", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/lots/{self.lot_id}/recall failed: {r.status_code} {r.text[:200]}")
                return False
            
            recall = r.json()
            
            required = ["rolls", "orders", "shipments", "customers", "totals"]
            missing = [k for k in required if k not in recall]
            if missing:
                bad(f"Recall missing keys: {missing}")
                return False
            
            ok(f"Recall complete: {recall['totals']['rolls']} rolls, "
               f"{recall['totals']['orders']} orders, {recall['totals']['customers']} customers")
            
            # Check if customers have contact info
            if recall["customers"]:
                first_customer = recall["customers"][0]
                if "phone" in first_customer or "contact_person" in first_customer:
                    ok("Customer contact info included for recall action")
                else:
                    info("Customer contact info may be missing")
            
            return True
        except Exception as e:
            bad(f"test_recall exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 13: LABEL/QR GENERATION
    # ═══════════════════════════════════════════════════════════════════════
    def test_label(self):
        head("TEST 13 — POST /api/lots/{id}/label (label/QR generation)")
        try:
            if not self.lot_id:
                bad("No lot_id available for label test")
                return False
            
            # Test invalid format (should fail)
            r = self.session.post(f"{API}/lots/{self.lot_id}/label",
                                json={"format": "invalid_format", "qty": 1},
                                timeout=30)
            if r.status_code == 400:
                ok("Invalid label format rejected")
            else:
                bad(f"Invalid format not rejected: {r.status_code}")
            
            # Test invalid qty (should fail)
            r = self.session.post(f"{API}/lots/{self.lot_id}/label",
                                json={"format": "zpl", "qty": 100},
                                timeout=30)
            if r.status_code in [400, 422]:
                ok("Invalid qty (>50) rejected")
            else:
                bad(f"Invalid qty not rejected: {r.status_code}")
            
            # Test valid label generation
            r = self.session.post(f"{API}/lots/{self.lot_id}/label",
                                json={"format": "zpl", "qty": 2},
                                timeout=30)
            if r.status_code == 200:
                label = r.json()
                if "content" in label and "lot" in label:
                    ok(f"Label generated: format={label.get('format')}, qty={label.get('meta', {}).get('qty')}")
                    
                    # Verify lot number in content
                    r2 = self.session.get(f"{API}/lots/{self.lot_id}", timeout=30)
                    if r2.status_code == 200:
                        lot = r2.json()
                        if lot["lot_number"] in label["content"]:
                            ok("Lot number included in label content")
                        else:
                            bad("Lot number not in label content")
                else:
                    bad(f"Label response missing content/lot: {list(label.keys())}")
            else:
                bad(f"Label generation failed: {r.status_code} {r.text[:200]}")
            
            return True
        except Exception as e:
            bad(f"test_label exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 14: UNASSIGNED ROLLS
    # ═══════════════════════════════════════════════════════════════════════
    def test_unassigned_rolls(self):
        head("TEST 14 — GET /api/lots/unassigned-rolls")
        try:
            r = self.session.get(f"{API}/lots/unassigned-rolls", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/lots/unassigned-rolls failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            if "rolls" in result and "total" in result:
                ok(f"Unassigned rolls endpoint works: {result['total']} rolls without lot")
                if result["total"] == 0:
                    ok("All rolls have lot_id (clean data)")
                else:
                    info(f"Warning: {result['total']} rolls without lot")
            else:
                bad(f"Unassigned rolls response incorrect: {list(result.keys())}")
            
            return True
        except Exception as e:
            bad(f"test_unassigned_rolls exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 15: ROLL-LOT RELATIONSHIP
    # ═══════════════════════════════════════════════════════════════════════
    def test_roll_lot(self):
        head("TEST 15 — GET /api/rolls/{roll_id}/lot")
        try:
            # Get a roll with lot_id
            r = self.session.get(f"{API}/inventory/rolls?limit=1", timeout=30)
            if r.status_code != 200:
                bad("Cannot get rolls for roll-lot test")
                return False
            
            rolls = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            if not rolls:
                info("No rolls found, skipping roll-lot test")
                return True
            
            roll_id = rolls[0]["id"]
            
            r = self.session.get(f"{API}/rolls/{roll_id}/lot", timeout=30)
            if r.status_code == 404:
                info(f"Roll {roll_id} not found (may be expected)")
                return True
            
            if r.status_code != 200:
                bad(f"GET /api/rolls/{roll_id}/lot failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            if "lot" in result or "warning" in result:
                ok(f"Roll-lot relationship endpoint works")
            else:
                bad(f"Roll-lot response incorrect: {list(result.keys())}")
            
            return True
        except Exception as e:
            bad(f"test_roll_lot exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 16: ENUMS
    # ═══════════════════════════════════════════════════════════════════════
    def test_enums(self):
        head("TEST 16 — GET /api/enums (lot_source, lot_status)")
        try:
            r = self.session.get(f"{API}/enums", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/enums failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            enums = data.get("enums", {})
            
            # Check lot_source
            if "lot_source" in enums:
                lot_source = enums["lot_source"]
                if lot_source.get("in_use"):
                    ok(f"lot_source enum active with {len(lot_source.get('values', []))} values")
                else:
                    bad("lot_source enum not marked as in_use")
            else:
                bad("lot_source enum not found")
            
            # Check lot_status
            if "lot_status" in enums:
                lot_status = enums["lot_status"]
                if lot_status.get("in_use"):
                    ok(f"lot_status enum active with {len(lot_status.get('values', []))} values")
                else:
                    bad("lot_status enum not marked as in_use")
            else:
                bad("lot_status enum not found")
            
            # Check decisions
            decisions = data.get("decisions", {})
            if "D-10" in decisions and "D-26" in decisions and "D-27" in decisions:
                ok("Decisions D-10, D-26, D-27 documented in registry")
            else:
                bad(f"Decisions missing: {list(decisions.keys())}")
            
            return True
        except Exception as e:
            bad(f"test_enums exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 17: RBAC - SALES ROLE
    # ═══════════════════════════════════════════════════════════════════════
    def test_rbac_sales(self):
        head("TEST 17 — RBAC: Sales can view but not modify settings")
        try:
            # Login as sales
            sales_session = requests.Session()
            r = sales_session.post(f"{API}/auth/login",
                                  json={"email": "sales@kainnusantara.id", "password": "demo12345"},
                                  timeout=30)
            if r.status_code != 200:
                bad(f"Sales login failed: {r.status_code}")
                return False
            
            token = r.json().get("token")
            sales_session.headers.update({"Authorization": f"Bearer {token}"})
            
            # Test view (should succeed)
            r = sales_session.get(f"{API}/lots", timeout=30)
            if r.status_code == 200:
                ok("Sales can VIEW lots (traceability transparent)")
            else:
                bad(f"Sales cannot view lots: {r.status_code}")
            
            # Test modify settings (should fail with 403)
            r = sales_session.put(f"{API}/lots/settings",
                                json={"enforcement_mode": "block"},
                                timeout=30)
            if r.status_code == 403:
                ok("Sales CANNOT modify lot settings (403 Forbidden)")
            else:
                bad(f"RBAC breach: Sales can modify settings ({r.status_code})")
            
            return True
        except Exception as e:
            bad(f"test_rbac_sales exception: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEST 18: REGRESSION - EXISTING ENDPOINTS
    # ═══════════════════════════════════════════════════════════════════════
    def test_regression(self):
        head("TEST 18 — REGRESSION: Existing endpoints still work")
        try:
            endpoints = [
                f"{API}/inventory/rolls",
                f"{API}/inventory/balances",
                f"{API}/uom-conversions/rules",
            ]
            
            for endpoint in endpoints:
                r = self.session.get(f"{endpoint}?limit=1", timeout=30)
                if r.status_code == 200:
                    ok(f"{endpoint.split('/api/')[-1]} still works")
                else:
                    bad(f"{endpoint.split('/api/')[-1]} broken: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"test_regression exception: {e}")
            return False


def main():
    print("\n" + "=" * 70)
    print("  FASE C — LOT KELAS SATU: Backend API Testing")
    print("=" * 70)
    
    tester = LotTester()
    
    # Login and setup
    if not tester.login():
        return summary()
    
    if not tester.setup_references():
        return summary()
    
    # Run all tests
    tester.test_lot_list()
    tester.test_lot_stats()
    tester.test_lot_settings()
    tester.test_create_lot()
    tester.test_get_lot()
    tester.test_patch_lot()
    tester.test_lot_status()
    tester.test_lot_split()
    tester.test_lot_merge()
    tester.test_lot_rework()
    tester.test_genealogy()
    tester.test_recall()
    tester.test_label()
    tester.test_unassigned_rolls()
    tester.test_roll_lot()
    tester.test_enums()
    tester.test_rbac_sales()
    tester.test_regression()
    
    return summary()


def summary():
    print("\n" + "=" * 70)
    print(f"  \033[92mPASS {len(PASS)}\033[0m  |  \033[91mFAIL {len(FAIL)}\033[0m")
    if FAIL:
        print("\n  Failed tests:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    print("  \033[92m\033[1mALL TESTS PASSED — Backend Fase C Lot APIs working correctly.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
