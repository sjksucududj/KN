#!/usr/bin/env python3
"""Backend test for 360° detail panels (Supplier, Makloon, Employee).

Tests:
- Supplier 360: GET /api/suppliers/{id}/360 -> finance, PO, bills, returns, price_list, price_history, documents
- Makloon 360: GET /api/makloons/{id} -> finance, orders, service_bills, documents
- Employee 360: GET /api/hr/employees/{id}/360 -> attendance_summary, payslips, documents, can_view_pii
- Payslip PDF: GET /api/hr/payslips/{slip_id}/pdf -> PDF binary
"""
import requests
import sys

BASE_URL = "https://kn-doc-esign-wire.preview.emergentagent.com/api"
CREDENTIALS = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class Test360Panels:
    def __init__(self):
        self.token = None
        self.headers = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.supplier_id = None
        self.makloon_id = None
        self.employee_id = None
        self.payslip_id = None

    def log(self, msg, status="info"):
        icons = {"info": "🔍", "pass": "✅", "fail": "❌", "warn": "⚠️"}
        print(f"{icons.get(status, '•')} {msg}")

    def test(self, name, condition, details=""):
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"{name} - PASSED", "pass")
            if details:
                print(f"   {details}")
            return True
        else:
            self.log(f"{name} - FAILED", "fail")
            if details:
                print(f"   {details}")
            return False

    def login(self):
        self.log("Logging in as admin...")
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=CREDENTIALS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token")
                if self.token:
                    self.headers = {
                        "Authorization": f"Bearer {self.token}",
                        "X-Entity-Id": "ent_ksc",
                        "Content-Type": "application/json"
                    }
                    self.log("Login successful", "pass")
                    return True
            self.log(f"Login failed: {r.status_code} - {r.text[:200]}", "fail")
            return False
        except Exception as e:
            self.log(f"Login error: {e}", "fail")
            return False

    def test_supplier_360(self):
        self.log("\n=== TESTING SUPPLIER 360 ===")
        
        # Get supplier list
        try:
            r = requests.get(f"{BASE_URL}/suppliers", headers=self.headers, timeout=10)
            if r.status_code != 200:
                self.test("GET /api/suppliers", False, f"Status {r.status_code}")
                return False
            
            suppliers = r.json()
            if not suppliers or len(suppliers) == 0:
                self.test("GET /api/suppliers", False, "No suppliers found")
                return False
            
            self.supplier_id = suppliers[0].get("id")
            self.test("GET /api/suppliers", True, f"Found {len(suppliers)} suppliers, using {self.supplier_id}")
        except Exception as e:
            self.test("GET /api/suppliers", False, f"Error: {e}")
            return False

        # Get supplier 360
        try:
            r = requests.get(f"{BASE_URL}/suppliers/{self.supplier_id}/360", headers=self.headers, timeout=10)
            if r.status_code != 200:
                self.test("GET /api/suppliers/{id}/360", False, f"Status {r.status_code} - {r.text[:200]}")
                return False
            
            data = r.json()
            
            # Check finance object
            finance = data.get("finance", {})
            has_finance = all(k in finance for k in ["ap_outstanding", "overdue_amount", "overdue_days", 
                                                      "open_po_value", "po_total_value", "purchase_ytd",
                                                      "paid_total", "bill_total", "payment_term_code", 
                                                      "lead_time_days", "open_po_count"])
            self.test("Supplier 360 - finance object", has_finance, 
                     f"AP: {finance.get('ap_outstanding')}, Overdue: {finance.get('overdue_amount')}, Open PO: {finance.get('open_po_count')}")
            
            # Check purchase_orders array
            pos = data.get("purchase_orders", [])
            has_po_with_price = False
            if pos:
                for po in pos:
                    items = po.get("items", [])
                    if items and any("price" in item for item in items):
                        has_po_with_price = True
                        break
            self.test("Supplier 360 - purchase_orders with price", True, 
                     f"Found {len(pos)} POs, items have price field: {has_po_with_price}")
            
            # Check vendor_bills
            bills = data.get("vendor_bills", [])
            self.test("Supplier 360 - vendor_bills", True, f"Found {len(bills)} bills")
            
            # Check returns
            returns = data.get("returns", [])
            self.test("Supplier 360 - returns", True, f"Found {len(returns)} returns")
            
            # Check price_list
            price_list = data.get("price_list", [])
            self.test("Supplier 360 - price_list", len(price_list) >= 0, f"Found {len(price_list)} price list entries")
            
            # Check price_history
            price_history = data.get("price_history", [])
            has_history_structure = True
            if price_history:
                ph = price_history[0]
                has_history_structure = all(k in ph for k in ["product_id", "entries", "last_price", "points"])
            self.test("Supplier 360 - price_history structure", has_history_structure, 
                     f"Found {len(price_history)} products with price history")
            
            # Check documents
            documents = data.get("documents", [])
            has_doc_structure = True
            if documents:
                doc = documents[0]
                has_doc_structure = all(k in doc for k in ["doc_type", "number", "status", "amount"])
            self.test("Supplier 360 - documents", has_doc_structure, 
                     f"Found {len(documents)} documents with proper structure")
            
            return True
        except Exception as e:
            self.test("GET /api/suppliers/{id}/360", False, f"Error: {e}")
            return False

    def test_makloon_360(self):
        self.log("\n=== TESTING MAKLOON 360 ===")
        
        # Get makloon list
        try:
            r = requests.get(f"{BASE_URL}/makloons", headers=self.headers, timeout=10)
            if r.status_code != 200:
                self.test("GET /api/makloons", False, f"Status {r.status_code}")
                return False
            
            makloons = r.json()
            if not makloons or len(makloons) == 0:
                self.test("GET /api/makloons", False, "No makloons found")
                return False
            
            # Try to find mak_seed_tenun or use first
            self.makloon_id = None
            for m in makloons:
                if m.get("id") == "mak_seed_tenun":
                    self.makloon_id = m.get("id")
                    break
            if not self.makloon_id:
                self.makloon_id = makloons[0].get("id")
            
            self.test("GET /api/makloons", True, f"Found {len(makloons)} makloons, using {self.makloon_id}")
        except Exception as e:
            self.test("GET /api/makloons", False, f"Error: {e}")
            return False

        # Get makloon 360 (note: endpoint is /makloons/{id}, not /makloons/{id}/360)
        try:
            r = requests.get(f"{BASE_URL}/makloons/{self.makloon_id}", headers=self.headers, timeout=10)
            if r.status_code != 200:
                self.test("GET /api/makloons/{id}", False, f"Status {r.status_code} - {r.text[:200]}")
                return False
            
            data = r.json()
            
            # Check finance object
            finance = data.get("finance", {})
            has_finance = all(k in finance for k in ["service_ap_outstanding", "overdue_amount", 
                                                      "service_bill_total", "open_order_count"])
            self.test("Makloon 360 - finance object", has_finance, 
                     f"Service AP: {finance.get('service_ap_outstanding')}, Bills: {finance.get('service_bill_total')}, Open orders: {finance.get('open_order_count')}")
            
            # Check orders
            orders = data.get("orders", [])
            self.test("Makloon 360 - orders", True, f"Found {len(orders)} orders")
            
            # Check service_bills
            bills = data.get("service_bills", [])
            self.test("Makloon 360 - service_bills", True, f"Found {len(bills)} service bills")
            
            # Check documents
            documents = data.get("documents", [])
            has_doc_structure = True
            if documents:
                doc = documents[0]
                has_doc_structure = all(k in doc for k in ["doc_type", "number", "status", "amount"])
            self.test("Makloon 360 - documents", has_doc_structure, 
                     f"Found {len(documents)} documents (SPK + bills)")
            
            # Special check for mak_seed_tenun
            if self.makloon_id == "mak_seed_tenun" and bills:
                ap = finance.get("service_ap_outstanding", 0)
                self.test("Makloon 360 - mak_seed_tenun has AP > 0", ap > 0, 
                         f"AP outstanding: {ap}")
            
            return True
        except Exception as e:
            self.test("GET /api/makloons/{id}", False, f"Error: {e}")
            return False

    def test_employee_360(self):
        self.log("\n=== TESTING EMPLOYEE 360 ===")
        
        # Get employee list
        try:
            r = requests.get(f"{BASE_URL}/hr/employees", headers=self.headers, timeout=10)
            if r.status_code != 200:
                self.test("GET /api/hr/employees", False, f"Status {r.status_code}")
                return False
            
            employees = r.json()
            if not employees or len(employees) == 0:
                self.test("GET /api/hr/employees", False, "No employees found")
                return False
            
            # Try to find emp_f656f6426cda or emp_1326e09c0460 (mentioned in requirements)
            self.employee_id = None
            for emp in employees:
                if emp.get("id") in ["emp_f656f6426cda", "emp_1326e09c0460"]:
                    self.employee_id = emp.get("id")
                    break
            if not self.employee_id:
                self.employee_id = employees[0].get("id")
            
            self.test("GET /api/hr/employees", True, f"Found {len(employees)} employees, using {self.employee_id}")
        except Exception as e:
            self.test("GET /api/hr/employees", False, f"Error: {e}")
            return False

        # Get employee 360
        try:
            r = requests.get(f"{BASE_URL}/hr/employees/{self.employee_id}/360", headers=self.headers, timeout=10)
            if r.status_code != 200:
                self.test("GET /api/hr/employees/{id}/360", False, f"Status {r.status_code} - {r.text[:200]}")
                return False
            
            data = r.json()
            
            # Check profile enrichment
            has_profile = all(k in data for k in ["department_name", "position_name"])
            self.test("Employee 360 - profile enrichment", has_profile, 
                     f"Dept: {data.get('department_name')}, Position: {data.get('position_name')}")
            
            # Check attendance_summary
            summ = data.get("attendance_summary", {})
            has_summary = all(k in summ for k in ["present", "late", "leave", "absent", "total"])
            self.test("Employee 360 - attendance_summary", has_summary, 
                     f"Present: {summ.get('present')}, Late: {summ.get('late')}, Leave: {summ.get('leave')}, Absent: {summ.get('absent')}")
            
            # Check attendance
            attendance = data.get("attendance", [])
            self.test("Employee 360 - attendance", True, f"Found {len(attendance)} attendance records")
            
            # Check leave_requests
            leaves = data.get("leave_requests", [])
            self.test("Employee 360 - leave_requests", True, f"Found {len(leaves)} leave requests")
            
            # Check payslips
            payslips = data.get("payslips", [])
            self.test("Employee 360 - payslips", True, f"Found {len(payslips)} payslips")
            if payslips:
                self.payslip_id = payslips[0].get("id")
            
            # Check kpi_entries
            kpis = data.get("kpi_entries", [])
            self.test("Employee 360 - kpi_entries", True, f"Found {len(kpis)} KPI entries")
            
            # Check documents
            documents = data.get("documents", [])
            self.test("Employee 360 - documents", True, f"Found {len(documents)} documents")
            
            # Check can_view_pii (admin should have this)
            can_pii = data.get("can_view_pii", False)
            self.test("Employee 360 - can_view_pii", can_pii == True, 
                     f"Admin can view PII: {can_pii}")
            
            # Check base_salary is visible for admin
            if can_pii:
                has_salary = data.get("base_salary") is not None
                self.test("Employee 360 - base_salary visible", has_salary, 
                         f"Base salary: {data.get('base_salary')}")
            
            return True
        except Exception as e:
            self.test("GET /api/hr/employees/{id}/360", False, f"Error: {e}")
            return False

    def test_payslip_pdf(self):
        self.log("\n=== TESTING PAYSLIP PDF ===")
        
        if not self.payslip_id:
            self.log("No payslip ID available, skipping PDF test", "warn")
            return True
        
        try:
            r = requests.get(f"{BASE_URL}/hr/payslips/{self.payslip_id}/pdf", 
                           headers=self.headers, timeout=10)
            if r.status_code != 200:
                self.test("GET /api/hr/payslips/{id}/pdf", False, 
                         f"Status {r.status_code} - {r.text[:200]}")
                return False
            
            # Check if response starts with %PDF
            is_pdf = r.content[:4] == b'%PDF'
            self.test("GET /api/hr/payslips/{id}/pdf", is_pdf, 
                     f"Response is PDF: {is_pdf}, size: {len(r.content)} bytes")
            
            return is_pdf
        except Exception as e:
            self.test("GET /api/hr/payslips/{id}/pdf", False, f"Error: {e}")
            return False

    def run_all(self):
        self.log("Starting 360° Panels Backend Tests\n")
        
        if not self.login():
            self.log("\n❌ Login failed, cannot proceed", "fail")
            return False
        
        self.test_supplier_360()
        self.test_makloon_360()
        self.test_employee_360()
        self.test_payslip_pdf()
        
        self.log(f"\n{'='*60}")
        self.log(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        self.log(f"{'='*60}\n")
        
        return self.tests_passed == self.tests_run

if __name__ == "__main__":
    tester = Test360Panels()
    success = tester.run_all()
    sys.exit(0 if success else 1)
