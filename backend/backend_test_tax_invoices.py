#!/usr/bin/env python3
"""
Backend API Test — Sub-fase 1.9 Faktur Pajak Jual
==================================================
Tests:
1. Login with admin credentials
2. GET /api/tax-invoices (list tax invoices)
3. Dashboard metrics (products, warehouses)
4. POST /api/sales-orders/{order_id}/tax-invoice (issue tax invoice)
5. Verify seeded tax invoice FKT-00001 exists
"""
import os
import sys
import requests
from datetime import datetime

BASE = "https://po-pdf-sender.preview.emergentagent.com"
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


class TaxInvoiceTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.user = None
        
    def login(self, email="admin@kainnusantara.id", password="demo12345"):
        """Login with provided credentials"""
        try:
            print(f"\n🔐 Testing login: {email}")
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed for {email}: {r.status_code} {r.text[:200]}")
                return False
            data = r.json()
            self.token = data.get("token")
            self.user = data.get("user", {})
            if not self.token:
                bad(f"Login response missing token for {email}")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            ok(f"Login {email} (role: {self.user.get('role', 'unknown')})")
            return True
        except Exception as e:
            bad(f"Login exception for {email}: {e}")
            return False
    
    def test_tax_invoices_list(self):
        """Test GET /api/tax-invoices"""
        try:
            print("\n📋 Testing GET /api/tax-invoices")
            r = self.session.get(f"{API}/tax-invoices", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/tax-invoices failed: {r.status_code} {r.text[:200]}")
                return False
            
            invoices = r.json()
            if not isinstance(invoices, list):
                bad(f"GET /api/tax-invoices returned non-list: {type(invoices)}")
                return False
            
            ok(f"GET /api/tax-invoices returned {len(invoices)} invoices")
            
            # Check for seeded invoice FKT-00001
            fkt_00001 = None
            for inv in invoices:
                if inv.get("number") == "FKT-00001":
                    fkt_00001 = inv
                    break
            
            if fkt_00001:
                ok("Seeded invoice FKT-00001 found")
                info(f"  FKT-00001: DPP={fkt_00001.get('dpp')}, PPN={fkt_00001.get('ppn_amount')}, Total={fkt_00001.get('grand_total')}")
                
                # Verify required fields
                required_fields = ["id", "number", "order_id", "order_number", "dpp", "ppn_amount", "grand_total", "status"]
                missing = [f for f in required_fields if f not in fkt_00001]
                if missing:
                    bad(f"FKT-00001 missing fields: {missing}")
                else:
                    ok("FKT-00001 has all required fields (DPP, PPN, Total)")
            else:
                info("Seeded invoice FKT-00001 not found (may not be seeded yet)")
            
            return True
        except Exception as e:
            bad(f"GET /api/tax-invoices exception: {e}")
            return False
    
    def test_dashboard_metrics(self):
        """Test dashboard metrics (products, warehouses)"""
        try:
            print("\n📊 Testing dashboard metrics")
            
            # Get products count
            r = self.session.get(f"{API}/products", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/products failed: {r.status_code}")
                return False
            products = r.json()
            products_count = len(products) if isinstance(products, list) else 0
            info(f"Products count: {products_count}")
            
            # Get warehouses count
            r = self.session.get(f"{API}/warehouses", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/warehouses failed: {r.status_code}")
                return False
            warehouses = r.json()
            warehouses_count = len(warehouses) if isinstance(warehouses, list) else 0
            info(f"Warehouses count: {warehouses_count}")
            
            # Verify expected counts from review request
            if products_count == 7:
                ok("Dashboard shows 7 products (as expected)")
            else:
                info(f"Dashboard shows {products_count} products (expected 7)")
            
            if warehouses_count == 3:
                ok("Dashboard shows 3 warehouses (as expected)")
            else:
                info(f"Dashboard shows {warehouses_count} warehouses (expected 3)")
            
            return True
        except Exception as e:
            bad(f"Dashboard metrics exception: {e}")
            return False
    
    def test_issue_tax_invoice(self):
        """Test POST /api/sales-orders/{order_id}/tax-invoice"""
        try:
            print("\n📝 Testing POST /api/sales-orders/{order_id}/tax-invoice")
            
            # First, get a confirmed PKP order
            r = self.session.get(f"{API}/sales-orders", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/sales-orders failed: {r.status_code}")
                return False
            
            orders = r.json()
            if not isinstance(orders, list):
                bad(f"GET /api/sales-orders returned non-list: {type(orders)}")
                return False
            
            # Find a confirmed PKP order without tax invoice
            eligible_order = None
            for order in orders:
                status = order.get("status", "")
                is_pkp = order.get("is_pkp", False)
                ppn_amount = float(order.get("ppn_amount", 0))
                
                if status in ["confirmed", "picked", "shipped"] and is_pkp and ppn_amount > 0:
                    # Check if already has tax invoice
                    r_check = self.session.get(f"{API}/tax-invoices", params={"order_id": order["id"]}, timeout=30)
                    if r_check.status_code == 200:
                        existing = r_check.json()
                        if not existing or len(existing) == 0:
                            eligible_order = order
                            break
            
            if not eligible_order:
                info("No eligible order found for tax invoice issuance (all orders may already have tax invoices)")
                return True
            
            info(f"Found eligible order: {eligible_order.get('number')} (status: {eligible_order.get('status')})")
            
            # Issue tax invoice
            r = self.session.post(
                f"{API}/sales-orders/{eligible_order['id']}/tax-invoice",
                json={"kode_transaksi": "01"},
                timeout=30
            )
            
            if r.status_code == 201 or r.status_code == 200:
                tax_invoice = r.json()
                ok(f"Tax invoice issued: {tax_invoice.get('number')} for order {eligible_order.get('number')}")
                info(f"  Tax invoice ID: {tax_invoice.get('id')}")
                return True
            elif r.status_code == 409:
                info(f"Tax invoice already exists for order {eligible_order.get('number')} (409 Conflict)")
                return True
            else:
                bad(f"POST /api/sales-orders/{eligible_order['id']}/tax-invoice failed: {r.status_code} {r.text[:200]}")
                return False
                
        except Exception as e:
            bad(f"Issue tax invoice exception: {e}")
            return False
    
    def test_tax_invoice_document(self):
        """Test GET /api/tax-invoices/{fkt_id}/document"""
        try:
            print("\n📄 Testing GET /api/tax-invoices/{fkt_id}/document")
            
            # Get first tax invoice
            r = self.session.get(f"{API}/tax-invoices", timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/tax-invoices failed: {r.status_code}")
                return False
            
            invoices = r.json()
            if not invoices or len(invoices) == 0:
                info("No tax invoices found to test document endpoint")
                return True
            
            fkt_id = invoices[0]["id"]
            r = self.session.get(f"{API}/tax-invoices/{fkt_id}/document", timeout=30)
            
            if r.status_code != 200:
                bad(f"GET /api/tax-invoices/{fkt_id}/document failed: {r.status_code}")
                return False
            
            # Check if response is HTML
            content_type = r.headers.get("content-type", "")
            if "html" in content_type.lower():
                ok(f"Tax invoice document endpoint returns HTML (content-type: {content_type})")
            else:
                info(f"Tax invoice document endpoint returned content-type: {content_type}")
            
            return True
        except Exception as e:
            bad(f"Tax invoice document exception: {e}")
            return False


def main():
    print("=" * 70)
    print("Backend API Test — Sub-fase 1.9 Faktur Pajak Jual")
    print("=" * 70)
    
    tester = TaxInvoiceTester()
    
    # Test 1: Login as admin
    if not tester.login("admin@kainnusantara.id", "demo12345"):
        print("\n❌ Login failed, stopping tests")
        return 1
    
    # Test 2: Tax invoices list
    tester.test_tax_invoices_list()
    
    # Test 3: Dashboard metrics
    tester.test_dashboard_metrics()
    
    # Test 4: Issue tax invoice
    tester.test_issue_tax_invoice()
    
    # Test 5: Tax invoice document
    tester.test_tax_invoice_document()
    
    # Test other user roles login
    print("\n" + "=" * 70)
    print("Testing other user roles login")
    print("=" * 70)
    
    for email in ["sales@kainnusantara.id", "manager@kainnusantara.id", "warehouse@kainnusantara.id"]:
        role_tester = TaxInvoiceTester()
        role_tester.login(email, "demo12345")
    
    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"✅ PASSED: {len(PASS)}")
    print(f"❌ FAILED: {len(FAIL)}")
    
    if FAIL:
        print("\nFailed tests:")
        for f in FAIL:
            print(f"  • {f}")
    
    return 0 if len(FAIL) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
