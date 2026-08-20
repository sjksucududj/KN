"""
Backend API Testing for CRM Omnichannel Module
Tests: Lead Pipeline, Interactions, Conversions, Entity Scoping, RBAC, Regression
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"
LOGIN_EMAIL = "admin@kainnusantara.id"
LOGIN_PASSWORD = "demo12345"
ENTITY_ID = "ent_ksc"

class CRMOmnichannelAPITester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.created_lead_id = None
        self.created_interaction_id = None

    def log(self, message, level="INFO"):
        """Log test messages"""
        prefix = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️"
        }.get(level, "•")
        print(f"{prefix} {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None, headers=None):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        req_headers = {'Content-Type': 'application/json'}
        if self.token:
            req_headers['Authorization'] = f'Bearer {self.token}'
        if headers:
            req_headers.update(headers)

        self.tests_run += 1
        self.log(f"Testing: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=req_headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=req_headers, params=params, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=req_headers, params=params, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=req_headers, params=params, timeout=30)

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - {name} (Status: {response.status_code})", "SUCCESS")
                return True, response
            else:
                self.tests_failed += 1
                self.failed_tests.append(name)
                self.log(f"FAILED - {name} (Expected {expected_status}, got {response.status_code})", "FAIL")
                try:
                    error_detail = response.json()
                    self.log(f"  Error: {error_detail}", "FAIL")
                except:
                    self.log(f"  Response: {response.text[:200]}", "FAIL")
                return False, response

        except Exception as e:
            self.tests_failed += 1
            self.failed_tests.append(name)
            self.log(f"FAILED - {name} (Exception: {str(e)})", "FAIL")
            return False, None

    def test_login(self):
        """Test login and get token"""
        self.log("\n=== AUTHENTICATION ===", "INFO")
        success, response = self.run_test(
            "Login",
            "POST",
            "/auth/login",
            200,
            data={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}
        )
        if success and response:
            try:
                data = response.json()
                self.token = data.get('token')
                if self.token:
                    self.log(f"  Token obtained: {self.token[:20]}...", "SUCCESS")
                    return True
                else:
                    self.log("  No token in response", "FAIL")
                    return False
            except:
                self.log("  Failed to parse login response", "FAIL")
                return False
        return False

    # ========== LEAD TESTS ==========
    
    def test_create_lead_success(self):
        """Test creating a lead with valid data"""
        self.log("\n=== LEAD CREATION - SUCCESS ===", "INFO")
        success, response = self.run_test(
            "Create Lead (valid data)",
            "POST",
            "/crm/leads",
            200,
            data={
                "name": "Test Lead Auto",
                "company": "PT Test Automation",
                "phone": "081234567890",
                "email": "test@automation.com",
                "source": "whatsapp",
                "stage": "new",
                "est_value": 5000000,
                "notes": "Lead created by automated test",
                "entity_id": ENTITY_ID
            }
        )
        if success and response:
            try:
                data = response.json()
                self.created_lead_id = data.get('id')
                if self.created_lead_id:
                    self.log(f"  Lead created with ID: {self.created_lead_id}", "SUCCESS")
                    self.log(f"  Stage: {data.get('stage')}, Value: {data.get('est_value')}", "SUCCESS")
                    return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_create_lead_missing_name(self):
        """Test creating a lead without name (should fail with 400)"""
        self.log("\n=== LEAD VALIDATION - MISSING NAME ===", "INFO")
        success, response = self.run_test(
            "Create Lead (missing name)",
            "POST",
            "/crm/leads",
            400,
            data={
                "company": "PT Test",
                "entity_id": ENTITY_ID
            }
        )
        return success

    def test_get_leads_list(self):
        """Test getting list of leads"""
        self.log("\n=== LEAD LIST ===", "INFO")
        success, response = self.run_test(
            "Get Leads List",
            "GET",
            "/crm/leads",
            200,
            params={"entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"  Retrieved {len(data)} leads", "SUCCESS")
                    return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_get_leads_board(self):
        """Test getting leads board (Kanban)"""
        self.log("\n=== LEAD BOARD (KANBAN) ===", "INFO")
        success, response = self.run_test(
            "Get Leads Board",
            "GET",
            "/crm/leads/board",
            200,
            params={"entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                columns = data.get('columns', [])
                total = data.get('total', 0)
                self.log(f"  Total leads: {total}", "SUCCESS")
                
                # Check all stages present
                stages = [col.get('stage') for col in columns]
                expected_stages = ['new', 'qualified', 'proposal', 'won', 'lost']
                if all(s in stages for s in expected_stages):
                    self.log(f"  All stages present: {stages}", "SUCCESS")
                else:
                    self.log(f"  Missing stages. Found: {stages}", "WARN")
                
                # Check column structure
                for col in columns:
                    stage = col.get('stage')
                    count = col.get('count', 0)
                    total_value = col.get('total_value', 0)
                    self.log(f"  Stage '{stage}': {count} leads, value: {total_value}", "SUCCESS")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_get_pipeline_stats(self):
        """Test getting pipeline statistics"""
        self.log("\n=== PIPELINE STATS ===", "INFO")
        success, response = self.run_test(
            "Get Pipeline Stats",
            "GET",
            "/crm/pipeline-stats",
            200,
            params={"entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                required_fields = ['by_stage', 'win_rate', 'open_count', 'open_value', 'won_value', 'total']
                missing = [f for f in required_fields if f not in data]
                if missing:
                    self.log(f"  Missing fields: {missing}", "WARN")
                else:
                    self.log(f"  All fields present", "SUCCESS")
                    self.log(f"  Win Rate: {data.get('win_rate')}%, Open Count: {data.get('open_count')}", "SUCCESS")
                    self.log(f"  Open Value: {data.get('open_value')}, Won Value: {data.get('won_value')}", "SUCCESS")
                
                # Check by_stage structure
                by_stage = data.get('by_stage', {})
                for stage in ['new', 'qualified', 'proposal', 'won', 'lost']:
                    if stage in by_stage:
                        stage_data = by_stage[stage]
                        self.log(f"  Stage '{stage}': count={stage_data.get('count')}, value={stage_data.get('value')}", "SUCCESS")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_update_lead_stage(self):
        """Test updating lead stage"""
        if not self.created_lead_id:
            self.log("\n=== LEAD UPDATE - STAGE (SKIPPED - no lead ID) ===", "WARN")
            return False
        
        self.log("\n=== LEAD UPDATE - STAGE ===", "INFO")
        success, response = self.run_test(
            "Update Lead Stage (new -> qualified)",
            "PATCH",
            f"/crm/leads/{self.created_lead_id}",
            200,
            data={"stage": "qualified"}
        )
        if success and response:
            try:
                data = response.json()
                new_stage = data.get('stage')
                if new_stage == "qualified":
                    self.log(f"  Stage updated to: {new_stage}", "SUCCESS")
                    self.log(f"  Stage changed at: {data.get('stage_changed_at')}", "SUCCESS")
                    return True
                else:
                    self.log(f"  Stage not updated correctly: {new_stage}", "FAIL")
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_update_lead_invalid_stage(self):
        """Test updating lead with invalid stage (should fail with 400)"""
        if not self.created_lead_id:
            self.log("\n=== LEAD VALIDATION - INVALID STAGE (SKIPPED) ===", "WARN")
            return False
        
        self.log("\n=== LEAD VALIDATION - INVALID STAGE ===", "INFO")
        success, response = self.run_test(
            "Update Lead (invalid stage)",
            "PATCH",
            f"/crm/leads/{self.created_lead_id}",
            400,
            data={"stage": "invalid_stage"}
        )
        return success

    def test_convert_lead_to_customer(self):
        """Test converting lead to customer"""
        if not self.created_lead_id:
            self.log("\n=== LEAD CONVERSION (SKIPPED - no lead ID) ===", "WARN")
            return False
        
        self.log("\n=== LEAD CONVERSION TO CUSTOMER ===", "INFO")
        success, response = self.run_test(
            "Convert Lead to Customer",
            "POST",
            f"/crm/leads/{self.created_lead_id}/convert",
            200,
            data={}
        )
        if success and response:
            try:
                data = response.json()
                customer_id = data.get('customer_id')
                lead = data.get('lead', {})
                if customer_id:
                    self.log(f"  Customer created with ID: {customer_id}", "SUCCESS")
                    self.log(f"  Lead stage updated to: {lead.get('stage')}", "SUCCESS")
                    self.log(f"  Lead customer_id: {lead.get('customer_id')}", "SUCCESS")
                    return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_convert_lead_already_converted(self):
        """Test converting already converted lead (should fail with 400)"""
        if not self.created_lead_id:
            self.log("\n=== LEAD CONVERSION - ALREADY CONVERTED (SKIPPED) ===", "WARN")
            return False
        
        self.log("\n=== LEAD CONVERSION - ALREADY CONVERTED ===", "INFO")
        success, response = self.run_test(
            "Convert Lead (already converted)",
            "POST",
            f"/crm/leads/{self.created_lead_id}/convert",
            400,
            data={}
        )
        return success

    def test_delete_lead(self):
        """Test deleting a lead"""
        # Create a new lead for deletion
        self.log("\n=== LEAD DELETION ===", "INFO")
        success, response = self.run_test(
            "Create Lead for Deletion",
            "POST",
            "/crm/leads",
            200,
            data={
                "name": "Lead to Delete",
                "entity_id": ENTITY_ID
            }
        )
        if success and response:
            try:
                data = response.json()
                lead_id = data.get('id')
                if lead_id:
                    # Now delete it
                    success_del, response_del = self.run_test(
                        "Delete Lead",
                        "DELETE",
                        f"/crm/leads/{lead_id}",
                        200
                    )
                    if success_del and response_del:
                        try:
                            del_data = response_del.json()
                            if del_data.get('deleted'):
                                self.log(f"  Lead deleted successfully", "SUCCESS")
                                return True
                        except:
                            pass
            except Exception as e:
                self.log(f"  Failed: {e}", "FAIL")
        return False

    # ========== INTERACTION TESTS ==========

    def test_create_interaction_success(self):
        """Test creating an interaction with valid data"""
        self.log("\n=== INTERACTION CREATION - SUCCESS ===", "INFO")
        success, response = self.run_test(
            "Create Interaction (valid data)",
            "POST",
            "/crm/interactions",
            200,
            data={
                "channel": "whatsapp",
                "direction": "outbound",
                "subject": "Follow-up Test",
                "notes": "Interaction created by automated test",
                "entity_id": ENTITY_ID
            }
        )
        if success and response:
            try:
                data = response.json()
                self.created_interaction_id = data.get('id')
                if self.created_interaction_id:
                    self.log(f"  Interaction created with ID: {self.created_interaction_id}", "SUCCESS")
                    self.log(f"  Channel: {data.get('channel')}, Direction: {data.get('direction')}", "SUCCESS")
                    return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_create_interaction_missing_subject_and_notes(self):
        """Test creating interaction without subject and notes (should fail with 400)"""
        self.log("\n=== INTERACTION VALIDATION - MISSING SUBJECT & NOTES ===", "INFO")
        success, response = self.run_test(
            "Create Interaction (missing subject & notes)",
            "POST",
            "/crm/interactions",
            400,
            data={
                "channel": "phone",
                "entity_id": ENTITY_ID
            }
        )
        return success

    def test_get_interactions_list(self):
        """Test getting list of interactions"""
        self.log("\n=== INTERACTION LIST ===", "INFO")
        success, response = self.run_test(
            "Get Interactions List",
            "GET",
            "/crm/interactions",
            200,
            params={"entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"  Retrieved {len(data)} interactions", "SUCCESS")
                    return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_get_interactions_filter_channel(self):
        """Test filtering interactions by channel"""
        self.log("\n=== INTERACTION FILTER - CHANNEL ===", "INFO")
        success, response = self.run_test(
            "Get Interactions (filter by channel)",
            "GET",
            "/crm/interactions",
            200,
            params={"entity_id": ENTITY_ID, "channel": "whatsapp"}
        )
        if success and response:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"  Retrieved {len(data)} WhatsApp interactions", "SUCCESS")
                    # Verify all are whatsapp
                    all_whatsapp = all(item.get('channel') == 'whatsapp' for item in data)
                    if all_whatsapp:
                        self.log(f"  All interactions are WhatsApp", "SUCCESS")
                    else:
                        self.log(f"  Some interactions are not WhatsApp", "WARN")
                    return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_delete_interaction(self):
        """Test deleting an interaction"""
        if not self.created_interaction_id:
            self.log("\n=== INTERACTION DELETION (SKIPPED - no interaction ID) ===", "WARN")
            return False
        
        self.log("\n=== INTERACTION DELETION ===", "INFO")
        success, response = self.run_test(
            "Delete Interaction",
            "DELETE",
            f"/crm/interactions/{self.created_interaction_id}",
            200
        )
        if success and response:
            try:
                data = response.json()
                if data.get('deleted'):
                    self.log(f"  Interaction deleted successfully", "SUCCESS")
                    return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    # ========== REGRESSION TESTS ==========

    def test_regression_customers(self):
        """Test existing customers endpoint still works"""
        self.log("\n=== REGRESSION - CUSTOMERS ===", "INFO")
        success, response = self.run_test(
            "Get Customers (regression)",
            "GET",
            "/customers",
            200,
            params={"entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"  Retrieved {len(data)} customers", "SUCCESS")
                    return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_regression_sales_users(self):
        """Test sales users endpoint still works"""
        self.log("\n=== REGRESSION - SALES USERS ===", "INFO")
        success, response = self.run_test(
            "Get Sales Users (regression)",
            "GET",
            "/sales-users",
            200
        )
        if success and response:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"  Retrieved {len(data)} sales users", "SUCCESS")
                    return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*60, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("="*60, "INFO")
        self.log(f"Total Tests: {self.tests_run}", "INFO")
        self.log(f"Passed: {self.tests_passed}", "SUCCESS")
        self.log(f"Failed: {self.tests_failed}", "FAIL" if self.tests_failed > 0 else "INFO")
        
        if self.tests_failed > 0:
            self.log("\nFailed Tests:", "FAIL")
            for test in self.failed_tests:
                self.log(f"  - {test}", "FAIL")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\nSuccess Rate: {success_rate:.1f}%", "SUCCESS" if success_rate >= 80 else "WARN")
        self.log("="*60, "INFO")
        
        return 0 if self.tests_failed == 0 else 1

def main():
    """Main test runner"""
    tester = CRMOmnichannelAPITester()
    
    print("\n" + "="*60)
    print("CRM OMNICHANNEL MODULE - BACKEND API TESTS")
    print("="*60)
    
    # Authentication
    if not tester.test_login():
        print("\n❌ Login failed, stopping tests")
        return 1
    
    # Lead Tests
    tester.test_create_lead_success()
    tester.test_create_lead_missing_name()
    tester.test_get_leads_list()
    tester.test_get_leads_board()
    tester.test_get_pipeline_stats()
    tester.test_update_lead_stage()
    tester.test_update_lead_invalid_stage()
    tester.test_convert_lead_to_customer()
    tester.test_convert_lead_already_converted()
    tester.test_delete_lead()
    
    # Interaction Tests
    tester.test_create_interaction_success()
    tester.test_create_interaction_missing_subject_and_notes()
    tester.test_get_interactions_list()
    tester.test_get_interactions_filter_channel()
    tester.test_delete_interaction()
    
    # Regression Tests
    tester.test_regression_customers()
    tester.test_regression_sales_users()
    
    # Print summary
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
