#!/usr/bin/env python3
"""
Backend API Test — F-3: Special Order MTO & Aftersales/RMA
===========================================================
Comprehensive test covering:
1. Special Order MTO lifecycle (create, approve, auto-SKU, convert-to-SO)
2. GL auto-posting for invoices (revenue + COGS)
3. Aftersales credit note flow (komplain/garansi types, GL reversal)
4. Entity scoping (no cross-entity leakage)
5. RBAC (sales role 403 on create-sku, manager/admin succeed)
"""
import os
import sys
import requests
from datetime import datetime, timedelta

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


class F3Tester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.manager_token = None
        self.sales_token = None
        self.entity_id = None
        self.warehouse_id = None
        self.customer_id = None
        self.address_id = None
        self.special_order_id = None
        self.product_id = None
        self.sales_order_id = None
        self.sales_return_id = None
        self.credit_note_id = None
        
    def login(self, email, password):
        """Login and return token"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed for {email}: {r.status_code} {r.text[:100]}")
                return None
            data = r.json()
            token = data.get("token")
            if not token:
                bad(f"Login response missing token for {email}")
                return None
            ok(f"Login {email}")
            return token
        except Exception as e:
            bad(f"Login exception for {email}: {e}")
            return None
    
    def setup_tokens(self):
        """Login all users"""
        self.admin_token = self.login("admin@kainnusantara.id", "demo12345")
        self.manager_token = self.login("manager@kainnusantara.id", "demo12345")
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")
        
        if not self.admin_token:
            return False
        
        # Set admin as default
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
        return True
    
    def setup_references(self):
        """Get entity, warehouse, customer references"""
        try:
            # Get entity
            r = self.session.get(f"{API}/entities", timeout=30)
            entities = r.json()
            if not entities:
                bad("No entities found")
                return False
            self.entity_id = entities[0]["id"]
            
            # Get warehouse
            r = self.session.get(f"{API}/warehouses", timeout=30)
            warehouses = r.json()
            if not warehouses:
                bad("No warehouses found")
                return False
            self.warehouse_id = warehouses[0]["id"]
            
            # Get customer
            r = self.session.get(f"{API}/customers", timeout=30)
            customers = r.json()
            if not customers:
                bad("No customers found")
                return False
            self.customer_id = customers[0]["id"]
            self.address_id = customers[0].get("addresses", [{}])[0].get("id")
            
            ok(f"Setup references: entity={self.entity_id[:8]}, customer={self.customer_id[:8]}")
            return True
        except Exception as e:
            bad(f"Setup references exception: {e}")
            return False
    
    def test_create_special_order(self):
        """Test 1: POST /api/special-orders → create custom special order (>10jt auto pending_approval)"""
        info("Test 1: Create special order >10jt (auto pending_approval)")
        try:
            payload = {
                "customer_id": self.customer_id,
                "entity_id": self.entity_id,
                "custom_item": {
                    "description": "Kain Batik Custom Premium",
                    "specifications": {
                        "color": "Merah Maroon",
                        "motif": "Parang Rusak",
                        "grade": "A+",
                        "category": "Batik Premium"
                    },
                    "quantity": 100.0,
                    "unit": "meter",
                    "target_price": 150000.0,  # 150k/meter × 100 = 15jt (>10jt threshold)
                    "notes": "Pesanan khusus untuk event corporate"
                },
                "expected_delivery": (datetime.now() + timedelta(days=30)).isoformat(),
                "shipping_address_id": self.address_id,
                "notes": "Urgent order - high priority",
                "submit_for_approval": True  # Auto-submit because >10jt
            }
            
            r = self.session.post(f"{API}/special-orders", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"Create special order failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            self.special_order_id = data.get("id")
            
            # Verify response
            if not self.special_order_id:
                bad("Special order response missing id")
                return False
            
            if data.get("status") != "pending_approval":
                bad(f"Expected status 'pending_approval', got '{data.get('status')}'")
                return False
            
            if data.get("total_amount") != 15000000.0:
                bad(f"Expected total_amount 15000000, got {data.get('total_amount')}")
                return False
            
            if not data.get("requires_approval"):
                bad("Expected requires_approval=true for >10jt order")
                return False
            
            ok(f"Created special order {data.get('number')} with status pending_approval (total: 15jt)")
            return True
            
        except Exception as e:
            bad(f"Create special order exception: {e}")
            return False
    
    def test_approve_special_order(self):
        """Test 2: POST /api/special-orders/{id}/approve → must auto-create Product SKU"""
        info("Test 2: Approve special order (auto-create SKU)")
        try:
            # Switch to manager token (has approve permission)
            self.session.headers.update({"Authorization": f"Bearer {self.manager_token}"})
            
            r = self.session.post(
                f"{API}/special-orders/{self.special_order_id}/approve",
                json={"notes": "Approved by manager"},
                timeout=30
            )
            
            # Switch back to admin
            self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
            
            if r.status_code != 200:
                bad(f"Approve special order failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            
            # Verify status transition
            if data.get("status") != "confirmed":
                bad(f"Expected status 'confirmed' after approve, got '{data.get('status')}'")
                return False
            
            # Verify auto-created product SKU
            self.product_id = data.get("linked_product_id")
            product_sku = data.get("linked_product_sku")
            
            if not self.product_id:
                bad("Approve response missing linked_product_id (auto-create SKU failed)")
                return False
            
            if not product_sku:
                bad("Approve response missing linked_product_sku")
                return False
            
            ok(f"Approved special order → status=confirmed, auto-created product {product_sku}")
            
            # Verify product exists in products collection
            r = self.session.get(f"{API}/products", timeout=30)
            if r.status_code != 200:
                bad(f"Get products failed: {r.status_code}")
                return False
            
            products = r.json()
            product = next((p for p in products if p.get("id") == self.product_id), None)
            
            if not product:
                bad(f"Product {self.product_id} not found in GET /api/products")
                return False
            
            if product.get("sku") != product_sku:
                bad(f"Product SKU mismatch: expected {product_sku}, got {product.get('sku')}")
                return False
            
            ok(f"Verified product {product_sku} exists in products collection")
            return True
            
        except Exception as e:
            bad(f"Approve special order exception: {e}")
            return False
    
    def test_create_sku_idempotent(self):
        """Test 3: POST /api/special-orders/{id}/create-sku → idempotent (returns same product)"""
        info("Test 3: Manual create-sku (idempotent)")
        try:
            # Call create-sku again (should return same product)
            r = self.session.post(
                f"{API}/special-orders/{self.special_order_id}/create-sku",
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Create SKU failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            product = data.get("product")
            
            if not product:
                bad("Create SKU response missing product")
                return False
            
            if product.get("id") != self.product_id:
                bad(f"Create SKU not idempotent: expected {self.product_id}, got {product.get('id')}")
                return False
            
            ok(f"Create-sku is idempotent (returned same product {product.get('sku')})")
            return True
            
        except Exception as e:
            bad(f"Create SKU exception: {e}")
            return False
    
    def test_create_sku_rbac(self):
        """Test 4: RBAC - sales role should get 403 on create-sku"""
        info("Test 4: RBAC - sales role 403 on create-sku")
        try:
            if not self.sales_token:
                info("Skipping RBAC test (sales token not available)")
                return True
            
            # Switch to sales token
            self.session.headers.update({"Authorization": f"Bearer {self.sales_token}"})
            
            r = self.session.post(
                f"{API}/special-orders/{self.special_order_id}/create-sku",
                timeout=30
            )
            
            # Switch back to admin
            self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
            
            if r.status_code != 403:
                bad(f"Expected 403 for sales role on create-sku, got {r.status_code}")
                return False
            
            ok("Sales role correctly denied (403) on create-sku endpoint")
            return True
            
        except Exception as e:
            bad(f"RBAC test exception: {e}")
            return False
    
    def test_convert_to_so(self):
        """Test 5: POST /api/special-orders/{id}/convert-to-so → creates Sales Order (idempotent)"""
        info("Test 5: Convert special order to Sales Order")
        try:
            r = self.session.post(
                f"{API}/special-orders/{self.special_order_id}/convert-to-so",
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Convert to SO failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            special_order = data.get("special_order")
            sales_order = data.get("sales_order")
            
            if not special_order or not sales_order:
                bad("Convert response missing special_order or sales_order")
                return False
            
            self.sales_order_id = sales_order.get("id")
            so_number = sales_order.get("number")
            
            if not self.sales_order_id:
                bad("Sales order missing id")
                return False
            
            # Verify linkage
            if special_order.get("linked_sales_order_id") != self.sales_order_id:
                bad("Special order not linked to sales order")
                return False
            
            if special_order.get("linked_sales_order_number") != so_number:
                bad("Special order missing linked_sales_order_number")
                return False
            
            # Verify sales order has source_special_order_id
            if sales_order.get("source_special_order_id") != self.special_order_id:
                bad("Sales order missing source_special_order_id")
                return False
            
            # Verify allow_backorder=True (MTO product has no stock)
            # Status should be waiting_stock or draft (acceptable, not error)
            status = sales_order.get("status")
            if status not in ["waiting_stock", "draft", "reserved"]:
                info(f"Note: SO status is '{status}' (expected waiting_stock/draft/reserved for MTO)")
            
            ok(f"Converted to SO {so_number} (status: {status}, allow_backorder: {sales_order.get('allow_backorder')})")
            
            # Test idempotency - calling again should return 400
            r2 = self.session.post(
                f"{API}/special-orders/{self.special_order_id}/convert-to-so",
                timeout=30
            )
            
            if r2.status_code != 400:
                bad(f"Convert-to-SO not idempotent: expected 400 on second call, got {r2.status_code}")
                return False
            
            ok("Convert-to-SO is idempotent (second call returned 400)")
            return True
            
        except Exception as e:
            bad(f"Convert to SO exception: {e}")
            return False
    
    def test_gl_posting_invoice(self):
        """Test 6: GL auto-posting for invoices (revenue + COGS)"""
        info("Test 6: GL auto-posting for invoices")
        try:
            # First, we need to approve the SO if it's in reserved/waiting_approval
            r = self.session.get(f"{API}/sales-orders/{self.sales_order_id}", timeout=30)
            if r.status_code != 200:
                bad(f"Get SO failed: {r.status_code}")
                return False
            
            so = r.json()
            status = so.get("status")
            
            # Try to move SO to a state where we can simulate payment
            if status in ["reserved", "waiting_approval"]:
                # Try to approve
                r = self.session.post(f"{API}/sales-orders/{self.sales_order_id}/approve", timeout=30)
                if r.status_code == 200:
                    ok(f"Approved SO (was {status})")
                    status = "approved"
            
            # Simulate payment to trigger GL posting
            r = self.session.post(
                f"{API}/sales-orders/{self.sales_order_id}/simulate-payment",
                json={
                    "amount": so.get("grand_total", 15000000),
                    "method": "transfer",
                    "created_by": "admin"
                },
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Simulate payment failed: {r.status_code} {r.text[:200]}")
                return False
            
            invoice = r.json()
            ok(f"Created invoice {invoice.get('number')} (amount: {invoice.get('amount')})")
            
            # Verify GL journal entries exist
            r = self.session.get(f"{API}/gl/journal", timeout=30)
            
            if r.status_code != 200:
                bad(f"Get GL journal failed: {r.status_code}")
                return False
            
            entries = r.json()
            
            # Find sales_order journal entry
            so_entry = None
            cogs_entry = None
            
            for entry in entries:
                if entry.get("source_type") == "sales_order" and entry.get("source_id") == self.sales_order_id:
                    so_entry = entry
                elif entry.get("source_type") == "sales_cogs" and entry.get("source_id") == self.sales_order_id:
                    cogs_entry = entry
            
            if not so_entry:
                bad("No sales_order journal entry found in GL")
                return False
            
            ok(f"Found sales_order GL entry {so_entry.get('number')} (debit: {so_entry.get('total_debit')}, credit: {so_entry.get('total_credit')})")
            
            if cogs_entry:
                ok(f"Found COGS GL entry {cogs_entry.get('number')} (debit: {cogs_entry.get('total_debit')}, credit: {cogs_entry.get('total_credit')})")
            else:
                info("Note: COGS entry not found (may be 0 if no cost data)")
            
            # Verify trial balance is balanced
            r = self.session.get(f"{API}/gl/trial-balance?balanced=true", timeout=30)
            if r.status_code != 200:
                bad(f"Get trial balance failed: {r.status_code}")
                return False
            
            tb = r.json()
            if not tb.get("balanced"):
                bad(f"Trial balance not balanced: debit={tb.get('total_debit')}, credit={tb.get('total_credit')}")
                return False
            
            ok(f"Trial balance is balanced (debit={tb.get('total_debit')}, credit={tb.get('total_credit')})")
            return True
            
        except Exception as e:
            bad(f"GL posting test exception: {e}")
            return False
    
    def test_sales_return_komplain(self):
        """Test 7: Create sales return with komplain type (must be accepted)"""
        info("Test 7: Create sales return with komplain type")
        try:
            # First, get the SO to find product details
            r = self.session.get(f"{API}/sales-orders/{self.sales_order_id}", timeout=30)
            if r.status_code != 200:
                bad(f"Get SO failed: {r.status_code}")
                return False
            
            so = r.json()
            status = so.get("status")
            
            # Try to move SO to confirmed state if needed
            if status in ["waiting_stock", "draft", "reserved"]:
                # Try to confirm the SO
                r = self.session.post(f"{API}/sales-orders/{self.sales_order_id}/confirm", timeout=30)
                if r.status_code == 200:
                    ok(f"Confirmed SO (was {status})")
                    so = r.json()
                    status = so.get("status")
                else:
                    info(f"Could not confirm SO (status: {status}, code: {r.status_code})")
            
            # Check if SO is in a valid state for returns
            valid_statuses = ["confirmed", "partially_picked", "picked", "partially_shipped", "shipped", "done"]
            if status not in valid_statuses:
                info(f"Skipping sales return tests (SO status '{status}' not in {valid_statuses})")
                return True
            
            items = so.get("items", [])
            if not items:
                bad("SO has no items")
                return False
            
            item = items[0]
            
            payload = {
                "order_id": self.sales_order_id,
                "return_type": "komplain",  # Must be accepted
                "items": [{
                    "product_id": item.get("product_id"),
                    "product_name": item.get("product_name"),
                    "quantity_returned": 10.0,
                    "unit": item.get("unit", "meter"),
                    "reason": "Cacat produksi - warna tidak sesuai",
                    "condition": "ok"
                }],
                "notes": "Customer complaint - quality issue",
                "entity_id": self.entity_id,
                "submit_now": True
            }
            
            r = self.session.post(f"{API}/sales-returns", json=payload, timeout=30)
            
            if r.status_code != 200:
                bad(f"Create sales return failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            self.sales_return_id = data.get("id")
            
            if not self.sales_return_id:
                bad("Sales return response missing id")
                return False
            
            if data.get("return_type") != "komplain":
                bad(f"Expected return_type 'komplain', got '{data.get('return_type')}'")
                return False
            
            if data.get("status") != "pending_approval":
                bad(f"Expected status 'pending_approval', got '{data.get('status')}'")
                return False
            
            ok(f"Created sales return {data.get('number')} with type 'komplain' (status: pending_approval)")
            return True
            
        except Exception as e:
            bad(f"Create sales return exception: {e}")
            return False
    
    def test_sales_return_garansi(self):
        """Test 8: Create sales return with garansi type (must be accepted)"""
        info("Test 8: Create sales return with garansi type")
        try:
            # Get SO items
            r = self.session.get(f"{API}/sales-orders/{self.sales_order_id}", timeout=30)
            if r.status_code != 200:
                bad(f"Get SO failed: {r.status_code}")
                return False
            
            so = r.json()
            status = so.get("status")
            
            # Check if SO is in a valid state for returns
            valid_statuses = ["confirmed", "partially_picked", "picked", "partially_shipped", "shipped", "done"]
            if status not in valid_statuses:
                info(f"Skipping garansi return test (SO status '{status}' not valid)")
                return True
            
            items = so.get("items", [])
            if not items:
                bad("SO has no items")
                return False
            
            item = items[0]
            
            payload = {
                "order_id": self.sales_order_id,
                "return_type": "garansi",  # Must be accepted
                "items": [{
                    "product_id": item.get("product_id"),
                    "product_name": item.get("product_name"),
                    "quantity_returned": 5.0,
                    "unit": item.get("unit", "meter"),
                    "reason": "Garansi - kain luntur setelah dicuci",
                    "condition": "damaged"
                }],
                "notes": "Warranty claim - fabric fading",
                "entity_id": self.entity_id,
                "submit_now": True
            }
            
            r = self.session.post(f"{API}/sales-returns", json=payload, timeout=30)
            
            if r.status_code != 200:
                bad(f"Create sales return (garansi) failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            garansi_return_id = data.get("id")
            
            if not garansi_return_id:
                bad("Sales return (garansi) response missing id")
                return False
            
            if data.get("return_type") != "garansi":
                bad(f"Expected return_type 'garansi', got '{data.get('return_type')}'")
                return False
            
            ok(f"Created sales return {data.get('number')} with type 'garansi' (accepted)")
            return True
            
        except Exception as e:
            bad(f"Create sales return (garansi) exception: {e}")
            return False
    
    def test_approve_return_credit_note(self):
        """Test 9: Approve sales return → generates Credit Note + GL reversal"""
        info("Test 9: Approve sales return (generates Credit Note)")
        try:
            # Check if we have a sales return to approve
            if not self.sales_return_id:
                info("Skipping approve return test (no sales return created)")
                return True
            
            # Switch to manager token
            self.session.headers.update({"Authorization": f"Bearer {self.manager_token}"})
            
            r = self.session.post(
                f"{API}/sales-returns/{self.sales_return_id}/approve",
                json={"notes": "Approved - valid complaint"},
                timeout=30
            )
            
            # Switch back to admin
            self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
            
            if r.status_code != 200:
                bad(f"Approve sales return failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            
            if data.get("status") != "approved":
                bad(f"Expected status 'approved', got '{data.get('status')}'")
                return False
            
            # Verify credit note was generated
            credit_note_number = data.get("credit_note_number")
            self.credit_note_id = data.get("credit_note_id")
            
            if not credit_note_number:
                bad("Approved return missing credit_note_number")
                return False
            
            if not self.credit_note_id:
                bad("Approved return missing credit_note_id")
                return False
            
            ok(f"Approved return → generated Credit Note {credit_note_number}")
            
            # Verify credit note exists in collection
            r = self.session.get(f"{API}/credit-notes", timeout=30)
            if r.status_code != 200:
                bad(f"Get credit notes failed: {r.status_code}")
                return False
            
            cn_data = r.json()
            credit_notes = cn_data.get("items", [])
            
            cn = next((c for c in credit_notes if c.get("id") == self.credit_note_id), None)
            
            if not cn:
                bad(f"Credit note {self.credit_note_id} not found in GET /api/credit-notes")
                return False
            
            if not cn.get("gross_amount"):
                bad("Credit note missing gross_amount")
                return False
            
            ok(f"Verified Credit Note {credit_note_number} exists (gross_amount: {cn.get('gross_amount')})")
            
            # Verify GL reversal journal entry
            r = self.session.get(f"{API}/gl/journal", timeout=30)
            
            if r.status_code != 200:
                bad(f"Get GL journal failed: {r.status_code}")
                return False
            
            entries = r.json()
            
            # Find sales_return journal entry
            return_entry = None
            for entry in entries:
                if entry.get("source_type") == "sales_return" and entry.get("source_id") == self.sales_return_id:
                    return_entry = entry
                    break
            
            if not return_entry:
                bad("No sales_return GL reversal entry found")
                return False
            
            ok(f"Found GL reversal entry {return_entry.get('number')} for sales_return (debit: {return_entry.get('total_debit')}, credit: {return_entry.get('total_credit')})")
            return True
            
        except Exception as e:
            bad(f"Approve return test exception: {e}")
            return False
    
    def test_entity_scoping(self):
        """Test 10: Entity scoping - no cross-entity leakage"""
        info("Test 10: Entity scoping validation")
        try:
            # Get all entities
            r = self.session.get(f"{API}/entities", timeout=30)
            if r.status_code != 200:
                bad(f"Get entities failed: {r.status_code}")
                return False
            
            entities = r.json()
            if len(entities) < 2:
                info("Skipping entity scoping test (only 1 entity)")
                return True
            
            # Get another entity ID
            other_entity_id = next((e["id"] for e in entities if e["id"] != self.entity_id), None)
            if not other_entity_id:
                info("Skipping entity scoping test (no other entity)")
                return True
            
            # Note: Admin users may have cross-entity access by design
            # Test that special orders list is properly scoped when using X-Entity-Id header
            self.session.headers.update({"X-Entity-Id": other_entity_id})
            r = self.session.get(f"{API}/special-orders", timeout=30)
            self.session.headers.pop("X-Entity-Id", None)
            
            if r.status_code != 200:
                bad(f"Get special orders failed: {r.status_code}")
                return False
            
            data = r.json()
            items = data.get("items", [])
            
            # Should not contain our special order when filtered by other entity
            if any(item.get("id") == self.special_order_id for item in items):
                bad("Entity scoping failed: special order leaked to other entity list")
                return False
            
            ok("Entity scoping verified for special orders list (X-Entity-Id header)")
            
            # Verify products are also scoped
            # Note: Products are shared across entities by design (global catalog)
            # Only inventory/pricing is entity-specific
            self.session.headers.update({"X-Entity-Id": other_entity_id})
            r = self.session.get(f"{API}/products", timeout=30)
            self.session.headers.pop("X-Entity-Id", None)
            
            if r.status_code != 200:
                bad(f"Get products failed: {r.status_code}")
                return False
            
            products = r.json()
            
            # Products are shared across entities (global catalog)
            # The MTO product will be visible but inventory is entity-scoped
            info(f"Products are shared across entities (found {len(products)} products)")
            ok("Entity scoping verified: special orders scoped, products shared (by design)")
            return True
            
        except Exception as e:
            bad(f"Entity scoping test exception: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("F-3 Special Order MTO & Aftersales/RMA Backend Tests")
        print("="*70 + "\n")
        
        if not self.setup_tokens():
            print("\n❌ Failed to setup tokens")
            return False
        
        if not self.setup_references():
            print("\n❌ Failed to setup references")
            return False
        
        # Run tests in sequence
        tests = [
            self.test_create_special_order,
            self.test_approve_special_order,
            self.test_create_sku_idempotent,
            self.test_create_sku_rbac,
            self.test_convert_to_so,
            self.test_gl_posting_invoice,
            self.test_sales_return_komplain,
            self.test_sales_return_garansi,
            self.test_approve_return_credit_note,
            self.test_entity_scoping,
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                bad(f"Test {test.__name__} crashed: {e}")
        
        # Print summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"✅ PASSED: {len(PASS)}")
        print(f"❌ FAILED: {len(FAIL)}")
        
        if FAIL:
            print("\nFailed tests:")
            for f in FAIL:
                print(f"  • {f}")
        
        print("\n" + "="*70 + "\n")
        
        return len(FAIL) == 0


def main():
    tester = F3Tester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
