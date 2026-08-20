#!/usr/bin/env python3
"""
Kain Nusantara Backend Test - FASE 5 WhatsApp Features
Testing WhatsApp delivery, settings, recipient resolver, auto-send rules, and dispatch
"""
import requests
import sys
from datetime import datetime

# Use public endpoint from frontend/.env
BASE_URL = "https://docflow-verify-1.preview.emergentagent.com/api"

# Test credentials
EMAIL = "admin@kainnusantara.id"
PASSWORD = "demo12345"

class WhatsAppTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.session = requests.Session()
        self.results = []

    def log(self, status, test_name, details=""):
        """Log test result"""
        self.tests_run += 1
        if status == "PASS":
            self.tests_passed += 1
            print(f"✅ PASS: {test_name}")
        else:
            print(f"❌ FAIL: {test_name}")
        if details:
            print(f"   {details}")
        self.results.append({"test": test_name, "status": status, "details": details})

    def get_headers(self):
        """Get auth headers"""
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def test_login(self):
        """Test admin login"""
        try:
            r = self.session.post(f"{BASE_URL}/auth/login", 
                                 json={"email": EMAIL, "password": PASSWORD}, 
                                 timeout=30)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token")
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                self.log("PASS", "Admin Login", f"User: {data.get('user', {}).get('name', 'N/A')}")
                return True
            else:
                self.log("FAIL", "Admin Login", f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Admin Login", f"Error: {str(e)}")
            return False

    def test_wa_settings_get(self):
        """Test GET /deliveries/whatsapp/settings"""
        try:
            r = self.session.get(f"{BASE_URL}/deliveries/whatsapp/settings", timeout=30)
            if r.status_code == 200:
                data = r.json()
                # Check required fields
                has_fields = all(k in data for k in ["provider", "simulate", "enabled", "default_country_code", "sender_label"])
                self.log("PASS" if has_fields else "FAIL", 
                        "GET WhatsApp Settings",
                        f"simulate={data.get('simulate')}, provider={data.get('provider')}, enabled={data.get('enabled')}")
                return has_fields
            else:
                self.log("FAIL", "GET WhatsApp Settings", f"Status: {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "GET WhatsApp Settings", f"Error: {str(e)}")
            return False

    def test_wa_settings_put(self):
        """Test PUT /deliveries/whatsapp/settings"""
        try:
            payload = {
                "simulate": True,
                "enabled": True,
                "default_country_code": "62",
                "sender_label": "Kain Nusantara Test"
            }
            r = self.session.put(f"{BASE_URL}/deliveries/whatsapp/settings", 
                                json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                self.log("PASS", "PUT WhatsApp Settings", 
                        f"simulate={data.get('simulate')}, enabled={data.get('enabled')}")
                return True
            else:
                self.log("FAIL", "PUT WhatsApp Settings", f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "PUT WhatsApp Settings", f"Error: {str(e)}")
            return False

    def test_doc_types(self):
        """Test GET /pdf/doc-types"""
        try:
            r = self.session.get(f"{BASE_URL}/pdf/doc-types", timeout=30)
            if r.status_code == 200:
                data = r.json()
                self.log("PASS", "GET Document Types", f"Count: {len(data)}")
                return data
            else:
                self.log("FAIL", "GET Document Types", f"Status: {r.status_code}")
                return []
        except Exception as e:
            self.log("FAIL", "GET Document Types", f"Error: {str(e)}")
            return []

    def test_documents_list(self, doc_type="sales_order"):
        """Test GET /pdf/documents/{doc_type}"""
        try:
            r = self.session.get(f"{BASE_URL}/pdf/documents/{doc_type}", 
                                params={"entity_id": "all", "limit": 20}, timeout=30)
            if r.status_code == 200:
                data = r.json()
                docs = data.get("documents", [])
                self.log("PASS", f"GET Documents List ({doc_type})", f"Count: {len(docs)}")
                return docs
            else:
                self.log("FAIL", f"GET Documents List ({doc_type})", f"Status: {r.status_code}")
                return []
        except Exception as e:
            self.log("FAIL", f"GET Documents List ({doc_type})", f"Error: {str(e)}")
            return []

    def test_pdf_render(self, doc_type, source_id, entity_id=None):
        """Test GET /pdf/render/{doc_type}/{source_id}"""
        try:
            # Test PDF format
            params = {"format": "pdf", "entity_id": entity_id} if entity_id else {"format": "pdf"}
            r = self.session.get(f"{BASE_URL}/pdf/render/{doc_type}/{source_id}", 
                                params=params, timeout=60)
            is_pdf = r.status_code == 200 and r.content[:4] == b"%PDF"
            
            # Test HTML format
            params["format"] = "html"
            r2 = self.session.get(f"{BASE_URL}/pdf/render/{doc_type}/{source_id}", 
                                 params=params, headers={"Accept": "text/html"}, timeout=60)
            is_html = r2.status_code == 200 and "<" in r2.text
            
            success = is_pdf and is_html
            self.log("PASS" if success else "FAIL", 
                    f"PDF Render ({doc_type})",
                    f"PDF: {is_pdf} (size={len(r.content)}B), HTML: {is_html}")
            return success
        except Exception as e:
            self.log("FAIL", f"PDF Render ({doc_type})", f"Error: {str(e)}")
            return False

    def test_wa_recipient(self, doc_type, source_id, entity_id=None):
        """Test GET /deliveries/whatsapp/recipient/{doc_type}/{source_id}"""
        try:
            params = {"entity_id": entity_id} if entity_id else {}
            r = self.session.get(f"{BASE_URL}/deliveries/whatsapp/recipient/{doc_type}/{source_id}",
                                params=params, timeout=30)
            if r.status_code == 200:
                data = r.json()
                phone = data.get("phone", "")
                mode = data.get("mode")
                name = data.get("name", "")
                # For sales_order, mode should be 'customer' and phone should start with 62
                is_valid = (mode in ["customer", "supplier", None] and 
                           (not phone or phone.startswith("62")))
                self.log("PASS" if is_valid else "FAIL",
                        f"GET Recipient ({doc_type})",
                        f"phone={phone}, mode={mode}, name={name}")
                return data
            else:
                self.log("FAIL", f"GET Recipient ({doc_type})", f"Status: {r.status_code}")
                return {}
        except Exception as e:
            self.log("FAIL", f"GET Recipient ({doc_type})", f"Error: {str(e)}")
            return {}

    def test_wa_send(self, doc_type, source_id, entity_id=None, to="081234567890"):
        """Test POST /deliveries/whatsapp/send"""
        try:
            payload = {
                "doc_type": doc_type,
                "source_id": source_id,
                "entity_id": entity_id,
                "to": to,
                "caption": f"Test {doc_type} {source_id}",
                "message": "Test message from backend test"
            }
            r = self.session.post(f"{BASE_URL}/deliveries/whatsapp/send", 
                                 json=payload, timeout=60)
            if r.status_code == 200:
                data = r.json()
                status = data.get("status")
                message_id = data.get("message_id")
                to_normalized = data.get("to", "")
                is_valid = (status in ["simulated", "sent"] and 
                           message_id and 
                           to_normalized.startswith("62"))
                self.log("PASS" if is_valid else "FAIL",
                        "POST WhatsApp Send",
                        f"status={status}, to={to_normalized}, message_id={message_id}")
                return data
            else:
                self.log("FAIL", "POST WhatsApp Send", f"Status: {r.status_code}, Body: {r.text[:200]}")
                return {}
        except Exception as e:
            self.log("FAIL", "POST WhatsApp Send", f"Error: {str(e)}")
            return {}

    def test_wa_history(self, doc_type, source_id):
        """Test GET /deliveries/{doc_type}/{source_id}"""
        try:
            r = self.session.get(f"{BASE_URL}/deliveries/{doc_type}/{source_id}", timeout=30)
            if r.status_code == 200:
                data = r.json()
                deliveries = data.get("deliveries", [])
                self.log("PASS", f"GET Delivery History ({doc_type})", f"Count: {len(deliveries)}")
                return deliveries
            else:
                self.log("FAIL", f"GET Delivery History ({doc_type})", f"Status: {r.status_code}")
                return []
        except Exception as e:
            self.log("FAIL", f"GET Delivery History ({doc_type})", f"Error: {str(e)}")
            return []

    def test_wa_rules_list(self):
        """Test GET /deliveries/whatsapp/rules"""
        try:
            r = self.session.get(f"{BASE_URL}/deliveries/whatsapp/rules", timeout=30)
            if r.status_code == 200:
                data = r.json()
                rules = data.get("rules", [])
                self.log("PASS", "GET WhatsApp Rules", f"Count: {len(rules)}")
                return rules
            else:
                self.log("FAIL", "GET WhatsApp Rules", f"Status: {r.status_code}")
                return []
        except Exception as e:
            self.log("FAIL", "GET WhatsApp Rules", f"Error: {str(e)}")
            return []

    def test_wa_rules_create(self):
        """Test POST /deliveries/whatsapp/rules"""
        try:
            payload = {
                "doc_type": "sales_order",
                "event": "confirmed",
                "recipient_mode": "customer",
                "caption_template": "Test: {label} {number}",
                "enabled": True
            }
            r = self.session.post(f"{BASE_URL}/deliveries/whatsapp/rules", 
                                 json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                rule_id = data.get("id")
                self.log("PASS", "POST Create WhatsApp Rule", f"rule_id={rule_id}")
                return data
            else:
                self.log("FAIL", "POST Create WhatsApp Rule", f"Status: {r.status_code}, Body: {r.text[:200]}")
                return {}
        except Exception as e:
            self.log("FAIL", "POST Create WhatsApp Rule", f"Error: {str(e)}")
            return {}

    def test_wa_rules_update(self, rule_id):
        """Test PUT /deliveries/whatsapp/rules/{rule_id}"""
        try:
            payload = {"enabled": False}
            r = self.session.put(f"{BASE_URL}/deliveries/whatsapp/rules/{rule_id}", 
                                json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                self.log("PASS", "PUT Update WhatsApp Rule", f"enabled={data.get('enabled')}")
                return data
            else:
                self.log("FAIL", "PUT Update WhatsApp Rule", f"Status: {r.status_code}")
                return {}
        except Exception as e:
            self.log("FAIL", "PUT Update WhatsApp Rule", f"Error: {str(e)}")
            return {}

    def test_wa_rules_delete(self, rule_id):
        """Test DELETE /deliveries/whatsapp/rules/{rule_id}"""
        try:
            r = self.session.delete(f"{BASE_URL}/deliveries/whatsapp/rules/{rule_id}", timeout=30)
            if r.status_code == 200:
                self.log("PASS", "DELETE WhatsApp Rule", f"rule_id={rule_id}")
                return True
            else:
                self.log("FAIL", "DELETE WhatsApp Rule", f"Status: {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "DELETE WhatsApp Rule", f"Error: {str(e)}")
            return False

    def test_wa_autosend_dispatch(self):
        """Test auto-send dispatch on SO confirm"""
        try:
            # Get a sales order that can be confirmed
            docs = self.test_documents_list("sales_order")
            if not docs:
                self.log("FAIL", "Auto-send Dispatch", "No sales orders found")
                return False
            
            # Find SO in reserved/waiting_approval/approved status
            target = next((d for d in docs if d.get("status") in ["reserved", "waiting_approval", "approved"]), None)
            if not target:
                self.log("FAIL", "Auto-send Dispatch", "No SO in suitable status for testing")
                return False
            
            source_id = target["source_id"]
            
            # Create auto-send rule
            rule_payload = {
                "doc_type": "sales_order",
                "event": "confirmed",
                "recipient_mode": "customer",
                "caption_template": "Auto: {label} {number}",
                "enabled": True
            }
            rule_r = self.session.post(f"{BASE_URL}/deliveries/whatsapp/rules", 
                                      json=rule_payload, timeout=30)
            if rule_r.status_code != 200:
                self.log("FAIL", "Auto-send Dispatch", "Failed to create rule")
                return False
            
            rule_id = rule_r.json().get("id")
            
            # Get delivery count before
            before_deliveries = self.test_wa_history("sales_order", source_id)
            before_count = len(before_deliveries)
            
            # Approve if needed
            status = target.get("status")
            if status in ["reserved", "waiting_approval"]:
                approve_r = self.session.post(f"{BASE_URL}/sales-orders/{source_id}/approve", timeout=30)
                if approve_r.status_code != 200:
                    self.log("FAIL", "Auto-send Dispatch", f"Failed to approve SO: {approve_r.status_code}")
                    # Cleanup rule
                    self.session.delete(f"{BASE_URL}/deliveries/whatsapp/rules/{rule_id}")
                    return False
            
            # Confirm SO (should trigger auto-send)
            confirm_r = self.session.post(f"{BASE_URL}/sales-orders/{source_id}/confirm", timeout=30)
            if confirm_r.status_code != 200:
                self.log("FAIL", "Auto-send Dispatch", f"Failed to confirm SO: {confirm_r.status_code}")
                # Cleanup rule
                self.session.delete(f"{BASE_URL}/deliveries/whatsapp/rules/{rule_id}")
                return False
            
            # Check delivery count after
            after_deliveries = self.test_wa_history("sales_order", source_id)
            after_count = len(after_deliveries)
            
            # Check for auto delivery
            auto_deliveries = [d for d in after_deliveries if d.get("auto") and d.get("trigger") == "confirmed"]
            
            success = after_count > before_count and len(auto_deliveries) >= 1
            
            # Check caption template formatting
            if auto_deliveries:
                caption = auto_deliveries[0].get("caption", "")
                template_formatted = "Auto:" in caption and "{number}" not in caption
                success = success and template_formatted
                self.log("PASS" if success else "FAIL",
                        "Auto-send Dispatch",
                        f"before={before_count}, after={after_count}, auto={len(auto_deliveries)}, caption={caption}")
            else:
                self.log("FAIL", "Auto-send Dispatch", f"No auto delivery created")
            
            # Cleanup rule
            self.session.delete(f"{BASE_URL}/deliveries/whatsapp/rules/{rule_id}")
            
            return success
        except Exception as e:
            self.log("FAIL", "Auto-send Dispatch", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all WhatsApp backend tests"""
        print("=" * 70)
        print("KAIN NUSANTARA BACKEND TEST - FASE 5 WHATSAPP FEATURES")
        print("=" * 70)
        print()

        # Login
        if not self.test_login():
            print("\n❌ Login failed. Cannot proceed with tests.")
            return False

        # WhatsApp Settings
        print("\n--- WhatsApp Settings Tests ---")
        self.test_wa_settings_get()
        self.test_wa_settings_put()

        # Document Types & List
        print("\n--- Document Platform Tests ---")
        doc_types = self.test_doc_types()
        docs = self.test_documents_list("sales_order")
        
        if docs:
            # Pick first document for testing
            test_doc = docs[0]
            doc_type = "sales_order"
            source_id = test_doc["source_id"]
            entity_id = test_doc.get("entity_id")
            
            print(f"\n--- Testing with {doc_type} {source_id} ---")
            
            # PDF Render
            self.test_pdf_render(doc_type, source_id, entity_id)
            
            # WhatsApp Recipient
            self.test_wa_recipient(doc_type, source_id, entity_id)
            
            # WhatsApp Send
            self.test_wa_send(doc_type, source_id, entity_id)
            
            # WhatsApp History
            self.test_wa_history(doc_type, source_id)

        # WhatsApp Rules CRUD
        print("\n--- WhatsApp Rules CRUD Tests ---")
        self.test_wa_rules_list()
        rule = self.test_wa_rules_create()
        if rule and rule.get("id"):
            self.test_wa_rules_update(rule["id"])
            self.test_wa_rules_delete(rule["id"])

        # Auto-send Dispatch
        print("\n--- Auto-send Dispatch Test ---")
        self.test_wa_autosend_dispatch()

        # Summary
        print("\n" + "=" * 70)
        print(f"BACKEND TEST SUMMARY")
        print("=" * 70)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("=" * 70)

        return self.tests_passed == self.tests_run


def main():
    tester = WhatsAppTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
