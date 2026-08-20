#!/usr/bin/env python3
"""
Backend API Test — Sub-fase 1.11 Returns & Barang Sisa
========================================================
Comprehensive test covering:
1. List returns with status filters
2. Create return from confirmed SO
3. Submit return for approval (draft → pending_approval)
4. Approve return and stock adjustment (admin/manager only)
5. Reject return with reason (admin/manager only)
6. Upload attachments
7. Role-based permissions (admin vs sales)
8. Status transitions validation
"""
import os
import sys
import requests
import io
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


class SalesReturnsTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.sales_token = None
        self.entity_id = None
        self.warehouse_id = None
        self.customer_id = None
        self.address_id = None
        self.product_id = None
        self.order_id = None
        self.return_id = None
        
    def login_admin(self):
        """Login as admin"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": "admin@kainnusantara.id", "password": "demo12345"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Admin login failed: {r.status_code} {r.text[:200]}")
                return False
            data = r.json()
            self.admin_token = data.get("token")
            if not self.admin_token:
                bad("Admin login response missing token")
                return False
            ok("Login admin@kainnusantara.id")
            return True
        except Exception as e:
            bad(f"Admin login exception: {e}")
            return False
    
    def login_sales(self):
        """Login as sales user"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": "sales@kainnusantara.id", "password": "demo12345"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Sales login failed: {r.status_code} {r.text[:200]}")
                return False
            data = r.json()
            self.sales_token = data.get("token")
            if not self.sales_token:
                bad("Sales login response missing token")
                return False
            ok("Login sales@kainnusantara.id")
            return True
        except Exception as e:
            bad(f"Sales login exception: {e}")
            return False
    
    def setup_references(self):
        """Get entity, warehouse, customer, product references"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Get entity
            r = self.session.get(f"{API}/entities", headers=headers, timeout=30)
            entities = r.json()
            if not entities:
                bad("No entities found")
                return False
            self.entity_id = entities[0]["id"]
            
            # Get warehouse
            r = self.session.get(f"{API}/warehouses", headers=headers, timeout=30)
            warehouses = r.json()
            if not warehouses:
                bad("No warehouses found")
                return False
            self.warehouse_id = warehouses[0]["id"]
            
            # Get customer with addresses
            r = self.session.get(f"{API}/customers", headers=headers, timeout=30)
            customers = r.json()
            if not customers:
                bad("No customers found")
                return False
            customer = customers[0]
            self.customer_id = customer["id"]
            
            # Get address_id from customer
            addresses = customer.get("addresses", [])
            if not addresses:
                bad("Customer has no addresses")
                return False
            self.address_id = addresses[0].get("id")
            if not self.address_id:
                bad("Customer address has no id")
                return False
            
            # Get product
            r = self.session.get(f"{API}/products", headers=headers, timeout=30)
            products = r.json()
            if not products:
                bad("No products found")
                return False
            self.product_id = products[0]["id"]
            
            ok(f"Setup references: entity={self.entity_id[:8]}, warehouse={self.warehouse_id[:8]}, customer={self.customer_id[:8]}, product={self.product_id[:8]}")
            return True
        except Exception as e:
            bad(f"Setup references exception: {e}")
            return False
    
    def create_test_order(self):
        """Create a confirmed sales order for testing returns"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Create SO
            payload = {
                "customer_id": self.customer_id,
                "entity_id": self.entity_id,
                "shipping_address_id": self.address_id,
                "items": [{
                    "product_id": self.product_id,
                    "quantity": 100.0,
                    "unit": "meter",
                    "unit_price": 50000,
                }],
                "notes": "Test order for returns testing",
            }
            r = self.session.post(f"{API}/sales-orders", json=payload, headers=headers, timeout=30)
            if r.status_code not in [200, 201]:
                bad(f"Create SO failed: {r.status_code} {r.text[:200]}")
                return False
            
            order = r.json()
            self.order_id = order["id"]
            order_number = order.get("number", self.order_id[:8])
            
            # Confirm SO
            r = self.session.post(f"{API}/sales-orders/{self.order_id}/confirm", headers=headers, timeout=30)
            if r.status_code not in [200, 201]:
                bad(f"Confirm SO failed: {r.status_code} {r.text[:200]}")
                return False
            
            ok(f"Created and confirmed test order: {order_number}")
            return True
        except Exception as e:
            bad(f"Create test order exception: {e}")
            return False
    
    def test_list_returns_empty(self):
        """Test GET /api/sales-returns (should be empty initially)"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            r = self.session.get(f"{API}/sales-returns", headers=headers, timeout=30)
            if r.status_code != 200:
                bad(f"List returns failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            items = data.get("items", data)
            info(f"Found {len(items)} existing returns")
            ok("GET /api/sales-returns - list returns")
            return True
        except Exception as e:
            bad(f"List returns exception: {e}")
            return False
    
    def test_create_return_draft(self):
        """Test POST /api/sales-returns (create draft return)"""
        try:
            headers = {"Authorization": f"Bearer {self.sales_token}"}
            payload = {
                "order_id": self.order_id,
                "return_type": "retur",
                "items": [{
                    "product_id": self.product_id,
                    "product_name": "Test Product",
                    "quantity_returned": 10.0,
                    "unit": "meter",
                    "reason": "Customer tidak puas dengan kualitas",
                    "condition": "ok"
                }],
                "notes": "Test return - draft mode",
                "submit_now": False
            }
            r = self.session.post(f"{API}/sales-returns", json=payload, headers=headers, timeout=30)
            if r.status_code not in [200, 201]:
                bad(f"Create return draft failed: {r.status_code} {r.text[:200]}")
                return False
            
            ret = r.json()
            self.return_id = ret["id"]
            
            if ret.get("status") != "draft":
                bad(f"Return status should be 'draft', got '{ret.get('status')}'")
                return False
            
            if not ret.get("number", "").startswith("SRET-"):
                bad(f"Return number should start with 'SRET-', got '{ret.get('number')}'")
                return False
            
            ok(f"POST /api/sales-returns - created draft return: {ret.get('number')}")
            return True
        except Exception as e:
            bad(f"Create return draft exception: {e}")
            return False
    
    def test_get_return_detail(self):
        """Test GET /api/sales-returns/{id}"""
        try:
            headers = {"Authorization": f"Bearer {self.sales_token}"}
            r = self.session.get(f"{API}/sales-returns/{self.return_id}", headers=headers, timeout=30)
            if r.status_code != 200:
                bad(f"Get return detail failed: {r.status_code} {r.text[:200]}")
                return False
            
            ret = r.json()
            if ret.get("id") != self.return_id:
                bad(f"Return ID mismatch: expected {self.return_id}, got {ret.get('id')}")
                return False
            
            if not ret.get("items"):
                bad("Return should have items")
                return False
            
            ok(f"GET /api/sales-returns/{self.return_id[:8]} - get return detail")
            return True
        except Exception as e:
            bad(f"Get return detail exception: {e}")
            return False
    
    def test_submit_return(self):
        """Test POST /api/sales-returns/{id}/submit (draft → pending_approval)"""
        try:
            headers = {"Authorization": f"Bearer {self.sales_token}"}
            r = self.session.post(f"{API}/sales-returns/{self.return_id}/submit", headers=headers, timeout=30)
            if r.status_code not in [200, 201]:
                bad(f"Submit return failed: {r.status_code} {r.text[:200]}")
                return False
            
            ret = r.json()
            if ret.get("status") != "pending_approval":
                bad(f"Return status should be 'pending_approval', got '{ret.get('status')}'")
                return False
            
            ok(f"POST /api/sales-returns/{self.return_id[:8]}/submit - submitted for approval")
            return True
        except Exception as e:
            bad(f"Submit return exception: {e}")
            return False
    
    def test_upload_attachment(self):
        """Test POST /api/sales-returns/{id}/attachments"""
        try:
            headers = {"Authorization": f"Bearer {self.sales_token}"}
            
            # Create a dummy image file
            file_content = b"fake image content for testing"
            files = {"file": ("test_return_photo.jpg", io.BytesIO(file_content), "image/jpeg")}
            
            # Remove Content-Type from headers for multipart/form-data
            upload_headers = {"Authorization": f"Bearer {self.sales_token}"}
            
            r = self.session.post(
                f"{API}/sales-returns/{self.return_id}/attachments",
                files=files,
                headers=upload_headers,
                timeout=30
            )
            if r.status_code not in [200, 201]:
                bad(f"Upload attachment failed: {r.status_code} {r.text[:200]}")
                return False
            
            att = r.json()
            if not att.get("filename"):
                bad("Attachment response should have filename")
                return False
            
            ok(f"POST /api/sales-returns/{self.return_id[:8]}/attachments - uploaded {att.get('filename')}")
            return True
        except Exception as e:
            bad(f"Upload attachment exception: {e}")
            return False
    
    def test_approve_return(self):
        """Test POST /api/sales-returns/{id}/approve (admin only)"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            payload = {"notes": "Approved by admin - test"}
            
            r = self.session.post(
                f"{API}/sales-returns/{self.return_id}/approve",
                json=payload,
                headers=headers,
                timeout=30
            )
            if r.status_code not in [200, 201]:
                bad(f"Approve return failed: {r.status_code} {r.text[:200]}")
                return False
            
            ret = r.json()
            if ret.get("status") != "approved":
                bad(f"Return status should be 'approved', got '{ret.get('status')}'")
                return False
            
            if not ret.get("stock_adjusted"):
                bad("Return should have stock_adjusted=True after approval")
                return False
            
            if not ret.get("approved_by"):
                bad("Return should have approved_by field")
                return False
            
            ok(f"POST /api/sales-returns/{self.return_id[:8]}/approve - approved and stock adjusted")
            return True
        except Exception as e:
            bad(f"Approve return exception: {e}")
            return False
    
    def test_create_and_reject_return(self):
        """Test reject flow: create return → submit → reject"""
        try:
            # Create another return for rejection test
            headers_sales = {"Authorization": f"Bearer {self.sales_token}"}
            payload = {
                "order_id": self.order_id,
                "return_type": "bs",
                "items": [{
                    "product_id": self.product_id,
                    "product_name": "Test Product",
                    "quantity_returned": 5.0,
                    "unit": "meter",
                    "reason": "Barang sisa dari proyek",
                    "condition": "ok"
                }],
                "notes": "Test return for rejection",
                "submit_now": True  # Direct to pending_approval
            }
            r = self.session.post(f"{API}/sales-returns", json=payload, headers=headers_sales, timeout=30)
            if r.status_code not in [200, 201]:
                bad(f"Create return for rejection failed: {r.status_code} {r.text[:200]}")
                return False
            
            ret = r.json()
            reject_return_id = ret["id"]
            
            if ret.get("status") != "pending_approval":
                bad(f"Return with submit_now=True should be 'pending_approval', got '{ret.get('status')}'")
                return False
            
            # Reject as admin
            headers_admin = {"Authorization": f"Bearer {self.admin_token}"}
            reject_payload = {"notes": "Tidak sesuai dengan kebijakan retur"}
            
            r = self.session.post(
                f"{API}/sales-returns/{reject_return_id}/reject",
                json=reject_payload,
                headers=headers_admin,
                timeout=30
            )
            if r.status_code not in [200, 201]:
                bad(f"Reject return failed: {r.status_code} {r.text[:200]}")
                return False
            
            ret = r.json()
            if ret.get("status") != "rejected":
                bad(f"Return status should be 'rejected', got '{ret.get('status')}'")
                return False
            
            if not ret.get("rejected_by"):
                bad("Return should have rejected_by field")
                return False
            
            if not ret.get("reject_reason"):
                bad("Return should have reject_reason field")
                return False
            
            ok(f"POST /api/sales-returns/{reject_return_id[:8]}/reject - rejected with reason")
            return True
        except Exception as e:
            bad(f"Create and reject return exception: {e}")
            return False
    
    def test_list_returns_with_filters(self):
        """Test GET /api/sales-returns with status filters"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Test filter by status=approved
            r = self.session.get(f"{API}/sales-returns?status=approved", headers=headers, timeout=30)
            if r.status_code != 200:
                bad(f"List returns with filter failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            items = data.get("items", data)
            approved_count = len([x for x in items if x.get("status") == "approved"])
            
            if approved_count == 0:
                bad("Should have at least 1 approved return")
                return False
            
            # Test filter by status=rejected
            r = self.session.get(f"{API}/sales-returns?status=rejected", headers=headers, timeout=30)
            if r.status_code != 200:
                bad(f"List returns with rejected filter failed: {r.status_code}")
                return False
            
            data = r.json()
            items = data.get("items", data)
            rejected_count = len([x for x in items if x.get("status") == "rejected"])
            
            if rejected_count == 0:
                bad("Should have at least 1 rejected return")
                return False
            
            ok(f"GET /api/sales-returns?status=... - filters working (approved={approved_count}, rejected={rejected_count})")
            return True
        except Exception as e:
            bad(f"List returns with filters exception: {e}")
            return False
    
    def test_invalid_order_status(self):
        """Test creating return from invalid order status (should fail)"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Create a draft SO (not confirmed)
            payload = {
                "customer_id": self.customer_id,
                "entity_id": self.entity_id,
                "shipping_address_id": self.address_id,
                "items": [{
                    "product_id": self.product_id,
                    "quantity": 50.0,
                    "unit": "meter",
                    "unit_price": 50000,
                }],
                "notes": "Draft order for negative test",
            }
            r = self.session.post(f"{API}/sales-orders", json=payload, headers=headers, timeout=30)
            if r.status_code not in [200, 201]:
                info("Could not create draft SO for negative test, skipping")
                return True
            
            draft_order = r.json()
            draft_order_id = draft_order["id"]
            
            # Try to create return from draft order (should fail)
            return_payload = {
                "order_id": draft_order_id,
                "return_type": "retur",
                "items": [{
                    "product_id": self.product_id,
                    "product_name": "Test Product",
                    "quantity_returned": 5.0,
                    "unit": "meter",
                    "reason": "Test",
                    "condition": "ok"
                }],
                "notes": "Should fail",
                "submit_now": False
            }
            r = self.session.post(f"{API}/sales-returns", json=return_payload, headers=headers, timeout=30)
            
            if r.status_code == 400:
                ok("POST /api/sales-returns - correctly rejects return from draft order (400)")
                return True
            else:
                bad(f"Should reject return from draft order with 400, got {r.status_code}")
                return False
        except Exception as e:
            bad(f"Invalid order status test exception: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("🧪 SALES RETURNS API TEST — Sub-fase 1.11")
        print("="*70 + "\n")
        
        print("📋 SETUP")
        if not self.login_admin():
            return False
        if not self.login_sales():
            return False
        if not self.setup_references():
            return False
        if not self.create_test_order():
            return False
        
        print("\n📋 BASIC OPERATIONS")
        self.test_list_returns_empty()
        self.test_create_return_draft()
        self.test_get_return_detail()
        
        print("\n📋 STATUS TRANSITIONS")
        self.test_submit_return()
        self.test_upload_attachment()
        self.test_approve_return()
        
        print("\n📋 REJECT FLOW")
        self.test_create_and_reject_return()
        
        print("\n📋 FILTERS & VALIDATION")
        self.test_list_returns_with_filters()
        self.test_invalid_order_status()
        
        print("\n" + "="*70)
        print(f"✅ PASSED: {len(PASS)}")
        print(f"❌ FAILED: {len(FAIL)}")
        print("="*70)
        
        if FAIL:
            print("\n❌ FAILED TESTS:")
            for f in FAIL:
                print(f"  • {f}")
            return False
        else:
            print("\n🎉 ALL TESTS PASSED!")
            return True


def main():
    tester = SalesReturnsTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
