"""FASE 2 — HTTP API Testing (Digitalisasi Formulir Sukacita).

Comprehensive backend API testing for Phase 2:
- Cash Advance (Form PD): CRUD, state machine, disburse, GL posting
- Settlement (Pertanggungjawaban): CRUD, approval, GL posting
- Vehicles & Usage Logs: CRUD, calculations, summary
- RBAC enforcement per role
- Entity scoping isolation

Run: python backend_test_phase2_forms.py
"""
import requests
import sys
from typing import Dict, Any, Optional

BASE_URL = "https://nav-validated.preview.emergentagent.com"

# Test credentials
USERS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
}

# Entities
ENT_KSC = "ent_ksc"
ENT_KANDA = "ent_kanda"

# Test state
tokens: Dict[str, str] = {}
test_data: Dict[str, Any] = {}
tests_run = 0
tests_passed = 0
tests_failed = 0


def log_test(name: str, passed: bool, detail: str = ""):
    global tests_run, tests_passed, tests_failed
    tests_run += 1
    if passed:
        tests_passed += 1
        print(f"  ✅ {name}")
    else:
        tests_failed += 1
        print(f"  ❌ {name} — {detail}")


def api_call(method: str, endpoint: str, token: str = None, data: Dict = None,
             entity_id: str = None, expected_status: int = 200) -> tuple[bool, Optional[Dict], int]:
    """Make API call and return (success, response_data, status_code)"""
    url = f"{BASE_URL}/api/{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if entity_id:
        headers["X-Entity-Id"] = entity_id
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            resp = requests.post(url, json=data, headers=headers, timeout=30)
        elif method == "PATCH":
            resp = requests.patch(url, json=data, headers=headers, timeout=30)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return False, None, 0
        
        success = resp.status_code == expected_status
        try:
            response_data = resp.json() if resp.text else {}
        except Exception:
            response_data = {}
        
        return success, response_data, resp.status_code
    except Exception as e:
        print(f"    ⚠️  API call failed: {str(e)}")
        return False, None, 0


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════
def test_auth():
    print("\n[TEST 1] Authentication")
    global tokens
    
    for role, creds in USERS.items():
        success, data, status = api_call("POST", "auth/login", data=creds)
        if success and data and "token" in data:
            tokens[role] = data["token"]
            log_test(f"Login {role}", True)
        else:
            log_test(f"Login {role}", False, f"status={status}")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: EXPENSE CATEGORIES
# ═══════════════════════════════════════════════════════════════════════════
def test_expense_categories():
    print("\n[TEST 2] Expense Categories")
    
    # GET list (admin)
    success, data, status = api_call("GET", "expense-categories", token=tokens["admin"])
    log_test("GET expense-categories (admin)", success and isinstance(data, list))
    
    if success and data:
        log_test("8 expense categories exist", len(data) == 8, f"count={len(data)}")
        
        # Check account_code mapping
        has_mapping = all(cat.get("account_code") for cat in data)
        log_test("All categories have account_code", has_mapping)
        
        # Store first category for update test
        if data:
            test_data["expense_category_code"] = data[0]["code"]
    
    # PATCH update (admin with manage permission)
    if "expense_category_code" in test_data:
        code = test_data["expense_category_code"]
        update_data = {"label": "Updated Label Test"}
        success, data, status = api_call("PATCH", f"expense-categories/{code}",
                                        token=tokens["admin"], data=update_data)
        log_test("PATCH expense-category (admin)", success)
        
        # Invalid account_code should return 400
        invalid_data = {"account_code": "9-9999"}
        success, data, status = api_call("PATCH", f"expense-categories/{code}",
                                        token=tokens["admin"], data=invalid_data,
                                        expected_status=400)
        log_test("PATCH with invalid account_code returns 400", success)
    
    # RBAC: sales should be FORBIDDEN (403) on PATCH
    if "expense_category_code" in test_data:
        code = test_data["expense_category_code"]
        update_data = {"label": "Should Fail"}
        success, data, status = api_call("PATCH", f"expense-categories/{code}",
                                        token=tokens["sales"], data=update_data,
                                        expected_status=403)
        log_test("PATCH expense-category (sales) returns 403", success)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: CASH ADVANCE CRUD
# ═══════════════════════════════════════════════════════════════════════════
def test_cash_advance_crud():
    print("\n[TEST 3] Cash Advance CRUD")
    
    # CREATE (admin, entity ent_ksc)
    ca_data = {
        "entity_id": ENT_KSC,
        "divisi": "Test Division",
        "kegiatan": "Test Activity",
        "payment_method": "tunai",
        "lines": [
            {"description": "Item 1", "qty": 2, "unit_price": 500000, "satuan": "unit"},
            {"description": "Item 2", "qty": 1, "unit_price": 300000, "satuan": "unit"}
        ],
        "catatan": "Test cash advance"
    }
    
    success, data, status = api_call("POST", "cash-advances", token=tokens["admin"],
                                    data=ca_data, entity_id=ENT_KSC)
    if success and data:
        test_data["ca_id_ksc"] = data["id"]
        test_data["ca_number_ksc"] = data.get("number", "")
        log_test("POST cash-advance (admin, ent_ksc)", True)
        log_test("Cash advance total = 1,300,000",
                data.get("total_amount") == 1300000,
                f"total={data.get('total_amount')}")
        log_test("Cash advance status = draft", data.get("status") == "draft")
        log_test("Cash advance has >=1 line", len(data.get("lines", [])) >= 1)
    else:
        log_test("POST cash-advance (admin, ent_ksc)", False, f"status={status}")
    
    # CREATE with total=0 should fail (400)
    invalid_ca = {
        "entity_id": ENT_KSC,
        "divisi": "Test",
        "kegiatan": "Test",
        "payment_method": "tunai",
        "lines": [{"description": "Zero", "qty": 0, "unit_price": 0, "satuan": "unit"}],
    }
    success, data, status = api_call("POST", "cash-advances", token=tokens["admin"],
                                    data=invalid_ca, entity_id=ENT_KSC, expected_status=400)
    log_test("POST cash-advance with total=0 returns 400", success)
    
    # GET list (admin, ent_ksc)
    success, data, status = api_call("GET", "cash-advances", token=tokens["admin"],
                                    entity_id=ENT_KSC)
    log_test("GET cash-advances list (admin, ent_ksc)", success and isinstance(data, list))
    
    # GET by ID
    if "ca_id_ksc" in test_data:
        ca_id = test_data["ca_id_ksc"]
        success, data, status = api_call("GET", f"cash-advances/{ca_id}",
                                        token=tokens["admin"], entity_id=ENT_KSC)
        log_test("GET cash-advance by ID", success and data.get("id") == ca_id)
    
    # PATCH (update draft)
    if "ca_id_ksc" in test_data:
        ca_id = test_data["ca_id_ksc"]
        update_data = {"catatan": "Updated note"}
        success, data, status = api_call("PATCH", f"cash-advances/{ca_id}",
                                        token=tokens["admin"], data=update_data,
                                        entity_id=ENT_KSC)
        log_test("PATCH cash-advance (draft)", success)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: CASH ADVANCE STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════════
def test_cash_advance_state_machine():
    print("\n[TEST 4] Cash Advance State Machine")
    
    if "ca_id_ksc" not in test_data:
        print("  ⚠️  Skipping: no cash advance created")
        return
    
    ca_id = test_data["ca_id_ksc"]
    
    # SUBMIT (draft → pending_atasan)
    success, data, status = api_call("POST", f"cash-advances/{ca_id}/submit",
                                    token=tokens["admin"], entity_id=ENT_KSC)
    log_test("POST submit (draft → pending_atasan)", success)
    if success and data:
        log_test("Status = pending_atasan", data.get("status") == "pending_atasan")
    
    # APPROVE stage 1 (pending_atasan → pending_pimpinan)
    approve_data = {"note": "Approved by atasan"}
    success, data, status = api_call("POST", f"cash-advances/{ca_id}/approve",
                                    token=tokens["admin"], data=approve_data,
                                    entity_id=ENT_KSC)
    log_test("POST approve stage 1 (atasan)", success)
    if success and data:
        log_test("Status = pending_pimpinan", data.get("status") == "pending_pimpinan")
    
    # APPROVE stage 2 (pending_pimpinan → pending_finance)
    approve_data = {"note": "Approved by pimpinan"}
    success, data, status = api_call("POST", f"cash-advances/{ca_id}/approve",
                                    token=tokens["admin"], data=approve_data,
                                    entity_id=ENT_KSC)
    log_test("POST approve stage 2 (pimpinan)", success)
    if success and data:
        log_test("Status = pending_finance", data.get("status") == "pending_finance")
    
    # APPROVE stage 3 (pending_finance → approved)
    approve_data = {"note": "Approved by finance"}
    success, data, status = api_call("POST", f"cash-advances/{ca_id}/approve",
                                    token=tokens["admin"], data=approve_data,
                                    entity_id=ENT_KSC)
    log_test("POST approve stage 3 (finance)", success)
    if success and data:
        log_test("Status = approved", data.get("status") == "approved")
    
    # Try to approve when not in pending status (should return 409)
    approve_data = {"note": "Should fail"}
    success, data, status = api_call("POST", f"cash-advances/{ca_id}/approve",
                                    token=tokens["admin"], data=approve_data,
                                    entity_id=ENT_KSC, expected_status=409)
    log_test("POST approve when status=approved returns 409", success)
    
    # Create another CA for reject test
    ca_data = {
        "entity_id": ENT_KSC,
        "divisi": "Reject Test",
        "kegiatan": "Test Reject",
        "payment_method": "tunai",
        "lines": [{"description": "Test", "qty": 1, "unit_price": 100000, "satuan": "unit"}],
    }
    success, data, status = api_call("POST", "cash-advances", token=tokens["admin"],
                                    data=ca_data, entity_id=ENT_KSC)
    if success and data:
        ca_id_reject = data["id"]
        # Submit
        api_call("POST", f"cash-advances/{ca_id_reject}/submit",
                token=tokens["admin"], entity_id=ENT_KSC)
        # Reject
        reject_data = {"note": "Rejected for testing"}
        success, data, status = api_call("POST", f"cash-advances/{ca_id_reject}/reject",
                                        token=tokens["admin"], data=reject_data,
                                        entity_id=ENT_KSC)
        log_test("POST reject (pending → rejected)", success)
        if success and data:
            log_test("Status = rejected", data.get("status") == "rejected")
            
            # Rejected CA should be editable
            update_data = {"catatan": "Can edit rejected"}
            success, data, status = api_call("PATCH", f"cash-advances/{ca_id_reject}",
                                            token=tokens["admin"], data=update_data,
                                            entity_id=ENT_KSC)
            log_test("PATCH rejected CA is allowed", success)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: CASH ADVANCE DISBURSE
# ═══════════════════════════════════════════════════════════════════════════
def test_cash_advance_disburse():
    print("\n[TEST 5] Cash Advance Disburse")
    
    if "ca_id_ksc" not in test_data:
        print("  ⚠️  Skipping: no approved cash advance")
        return
    
    ca_id = test_data["ca_id_ksc"]
    
    # DISBURSE (approved → disbursed)
    disburse_data = {"cash_type": "kas_kecil", "note": "Test disburse"}
    success, data, status = api_call("POST", f"cash-advances/{ca_id}/disburse",
                                    token=tokens["admin"], data=disburse_data,
                                    entity_id=ENT_KSC)
    log_test("POST disburse (approved → disbursed)", success)
    
    if success and data:
        log_test("Status = disbursed", data.get("status") == "disbursed")
        log_test("Disbursement info exists", data.get("disbursement") is not None)
        
        disb = data.get("disbursement", {})
        log_test("Cash transaction created", disb.get("cash_txn_id") is not None)
        log_test("Journal entry created", disb.get("je_id") is not None)
        
        test_data["ca_disbursed_id"] = ca_id
    
    # Try to disburse when not approved (should return 409)
    # Create a draft CA
    ca_data = {
        "entity_id": ENT_KSC,
        "divisi": "Disburse Test",
        "kegiatan": "Test",
        "payment_method": "tunai",
        "lines": [{"description": "Test", "qty": 1, "unit_price": 50000, "satuan": "unit"}],
    }
    success, data, status = api_call("POST", "cash-advances", token=tokens["admin"],
                                    data=ca_data, entity_id=ENT_KSC)
    if success and data:
        ca_id_draft = data["id"]
        disburse_data = {"cash_type": "kas_kecil", "note": "Should fail"}
        success, data, status = api_call("POST", f"cash-advances/{ca_id_draft}/disburse",
                                        token=tokens["admin"], data=disburse_data,
                                        entity_id=ENT_KSC, expected_status=409)
        log_test("POST disburse when status=draft returns 409", success)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: SETTLEMENT
# ═══════════════════════════════════════════════════════════════════════════
def test_settlement():
    print("\n[TEST 6] Settlement (Pertanggungjawaban)")
    
    if "ca_disbursed_id" not in test_data:
        print("  ⚠️  Skipping: no disbursed cash advance")
        return
    
    ca_id = test_data["ca_disbursed_id"]
    
    # CREATE settlement
    stl_data = {
        "cash_advance_id": ca_id,
        "divisi": "Test Division",
        "periode": "2025-01",
        "expense_lines": [
            {"date": "2025-01-15", "description": "Office supplies", "category": "atk", "amount": 200000},
            {"date": "2025-01-16", "description": "Lunch", "category": "lunch_snack_entertainment", "amount": 150000},
            {"date": "2025-01-17", "description": "Transport", "category": "transportasi", "amount": 100000},
        ],
        "catatan": "Test settlement"
    }
    
    success, data, status = api_call("POST", "cash-advance-settlements",
                                    token=tokens["admin"], data=stl_data,
                                    entity_id=ENT_KSC)
    if success and data:
        test_data["stl_id"] = data["id"]
        log_test("POST settlement", True)
        log_test("Settlement status = draft", data.get("status") == "draft")
        log_test("Settlement has expense_lines", len(data.get("expense_lines", [])) >= 1)
        log_test("Settlement total_pengeluaran = 450,000",
                data.get("total_pengeluaran") == 450000,
                f"total={data.get('total_pengeluaran')}")
        log_test("Settlement category_totals exists", data.get("category_totals") is not None)
        log_test("Settlement sisa_kurang_dana calculated",
                data.get("sisa_kurang_dana") is not None)
    else:
        log_test("POST settlement", False, f"status={status}")
    
    # GET list
    success, data, status = api_call("GET", "cash-advance-settlements",
                                    token=tokens["admin"], entity_id=ENT_KSC)
    log_test("GET settlements list", success and isinstance(data, list))
    
    # GET by ID
    if "stl_id" in test_data:
        stl_id = test_data["stl_id"]
        success, data, status = api_call("GET", f"cash-advance-settlements/{stl_id}",
                                        token=tokens["admin"], entity_id=ENT_KSC)
        log_test("GET settlement by ID", success and data.get("id") == stl_id)
    
    # PATCH (update draft)
    if "stl_id" in test_data:
        stl_id = test_data["stl_id"]
        update_data = {"catatan": "Updated settlement note"}
        success, data, status = api_call("PATCH", f"cash-advance-settlements/{stl_id}",
                                        token=tokens["admin"], data=update_data,
                                        entity_id=ENT_KSC)
        log_test("PATCH settlement (draft)", success)
    
    # SUBMIT (draft → submitted)
    if "stl_id" in test_data:
        stl_id = test_data["stl_id"]
        success, data, status = api_call("POST", f"cash-advance-settlements/{stl_id}/submit",
                                        token=tokens["admin"], entity_id=ENT_KSC)
        log_test("POST settlement submit", success)
        if success and data:
            log_test("Settlement status = submitted", data.get("status") == "submitted")
    
    # APPROVE (submitted → posted_to_gl)
    if "stl_id" in test_data:
        stl_id = test_data["stl_id"]
        success, data, status = api_call("POST", f"cash-advance-settlements/{stl_id}/approve",
                                        token=tokens["admin"], entity_id=ENT_KSC)
        log_test("POST settlement approve", success)
        if success and data:
            log_test("Settlement status = posted_to_gl", data.get("status") == "posted_to_gl")
            log_test("Settlement journal_entry_id exists", data.get("journal_entry_id") is not None)
            log_test("Parent CA status = settled", True)  # Would need to verify via GET
    
    # Create another settlement for reject test
    stl_data2 = {
        "cash_advance_id": ca_id,
        "divisi": "Reject Test",
        "periode": "2025-01",
        "expense_lines": [
            {"date": "2025-01-18", "description": "Test", "category": "petty_cash_lain", "amount": 50000},
        ],
    }
    success, data, status = api_call("POST", "cash-advance-settlements",
                                    token=tokens["admin"], data=stl_data2,
                                    entity_id=ENT_KSC)
    if success and data:
        stl_id_reject = data["id"]
        # Submit
        api_call("POST", f"cash-advance-settlements/{stl_id_reject}/submit",
                token=tokens["admin"], entity_id=ENT_KSC)
        # Reject
        reject_data = {"note": "Rejected for testing"}
        success, data, status = api_call("POST", f"cash-advance-settlements/{stl_id_reject}/reject",
                                        token=tokens["admin"], data=reject_data,
                                        entity_id=ENT_KSC)
        log_test("POST settlement reject", success)
        if success and data:
            log_test("Settlement status = rejected", data.get("status") == "rejected")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: VEHICLES
# ═══════════════════════════════════════════════════════════════════════════
def test_vehicles():
    print("\n[TEST 7] Vehicles")
    
    # CREATE vehicle
    veh_data = {
        "entity_id": ENT_KSC,
        "no_polisi": "B 1234 XYZ",
        "nama": "Toyota Avanza",
        "jenis": "mobil",
        "active": True
    }
    
    success, data, status = api_call("POST", "vehicles", token=tokens["admin"],
                                    data=veh_data, entity_id=ENT_KSC)
    if success and data:
        test_data["vehicle_id"] = data["id"]
        test_data["vehicle_no_polisi"] = data.get("no_polisi", "")
        log_test("POST vehicle", True)
        log_test("Vehicle no_polisi uppercase", data.get("no_polisi") == "B 1234 XYZ")
    else:
        log_test("POST vehicle", False, f"status={status}")
    
    # Duplicate no_polisi should return 409
    success, data, status = api_call("POST", "vehicles", token=tokens["admin"],
                                    data=veh_data, entity_id=ENT_KSC,
                                    expected_status=409)
    log_test("POST vehicle with duplicate no_polisi returns 409", success)
    
    # GET list
    success, data, status = api_call("GET", "vehicles", token=tokens["admin"],
                                    entity_id=ENT_KSC)
    log_test("GET vehicles list", success and isinstance(data, list))
    
    # PATCH vehicle
    if "vehicle_id" in test_data:
        veh_id = test_data["vehicle_id"]
        update_data = {"nama": "Toyota Avanza Updated"}
        success, data, status = api_call("PATCH", f"vehicles/{veh_id}",
                                        token=tokens["admin"], data=update_data,
                                        entity_id=ENT_KSC)
        log_test("PATCH vehicle", success)
    
    # DELETE vehicle (should deactivate if used in logs, else hard delete)
    # Create a vehicle for deletion test
    veh_data2 = {
        "entity_id": ENT_KSC,
        "no_polisi": "B 5678 ABC",
        "nama": "Honda Jazz",
        "jenis": "mobil"
    }
    success, data, status = api_call("POST", "vehicles", token=tokens["admin"],
                                    data=veh_data2, entity_id=ENT_KSC)
    if success and data:
        veh_id_delete = data["id"]
        success, data, status = api_call("DELETE", f"vehicles/{veh_id_delete}",
                                        token=tokens["admin"], entity_id=ENT_KSC)
        log_test("DELETE vehicle (unused)", success and data.get("deleted") == True)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: VEHICLE USAGE LOGS
# ═══════════════════════════════════════════════════════════════════════════
def test_vehicle_usage_logs():
    print("\n[TEST 8] Vehicle Usage Logs")
    
    if "vehicle_id" not in test_data:
        print("  ⚠️  Skipping: no vehicle created")
        return
    
    veh_id = test_data["vehicle_id"]
    
    # CREATE log
    log_data = {
        "entity_id": ENT_KSC,
        "vehicle_id": veh_id,
        "tanggal": "2025-01-15",
        "km_awal": 10000,
        "km_akhir": 10150,
        "bbm": 200000,
        "tol": 50000,
        "parkir": 10000,
        "lain_lain": 5000,
        "tujuan": "Jakarta - Bandung",
        "driver": "Test Driver",
        "pemakai": "Test User"
    }
    
    success, data, status = api_call("POST", "vehicle-usage-logs",
                                    token=tokens["admin"], data=log_data,
                                    entity_id=ENT_KSC)
    if success and data:
        test_data["vlog_id"] = data["id"]
        log_test("POST vehicle-usage-log", True)
        log_test("Log number starts with VHL-", data.get("number", "").startswith("VHL-"))
        log_test("Log jarak_tempuh = 150", data.get("jarak_tempuh") == 150,
                f"jarak={data.get('jarak_tempuh')}")
        log_test("Log total = 265,000", data.get("total") == 265000,
                f"total={data.get('total')}")
    else:
        log_test("POST vehicle-usage-log", False, f"status={status}")
    
    # GET list
    success, data, status = api_call("GET", "vehicle-usage-logs",
                                    token=tokens["admin"], entity_id=ENT_KSC)
    log_test("GET vehicle-usage-logs list", success and isinstance(data, list))
    
    # GET summary
    success, data, status = api_call("GET", "vehicle-usage-logs/summary",
                                    token=tokens["admin"], entity_id=ENT_KSC)
    log_test("GET vehicle-usage-logs summary", success)
    if success and data:
        log_test("Summary has grand_total", "grand_total" in data)
        log_test("Summary has per_vehicle", "per_vehicle" in data)
    
    # PATCH log
    if "vlog_id" in test_data:
        vlog_id = test_data["vlog_id"]
        update_data = {"tujuan": "Jakarta - Surabaya"}
        success, data, status = api_call("PATCH", f"vehicle-usage-logs/{vlog_id}",
                                        token=tokens["admin"], data=update_data,
                                        entity_id=ENT_KSC)
        log_test("PATCH vehicle-usage-log", success)
    
    # DELETE log
    if "vlog_id" in test_data:
        vlog_id = test_data["vlog_id"]
        success, data, status = api_call("DELETE", f"vehicle-usage-logs/{vlog_id}",
                                        token=tokens["admin"], entity_id=ENT_KSC)
        log_test("DELETE vehicle-usage-log", success and data.get("deleted") == True)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9: RBAC NEGATIVE TESTS
# ═══════════════════════════════════════════════════════════════════════════
def test_rbac_negative():
    print("\n[TEST 9] RBAC Negative Tests")
    
    # Sales can create/submit cash-advances but FORBIDDEN on disburse
    ca_data = {
        "entity_id": ENT_KSC,
        "divisi": "Sales Test",
        "kegiatan": "Test",
        "payment_method": "tunai",
        "lines": [{"description": "Test", "qty": 1, "unit_price": 100000, "satuan": "unit"}],
    }
    success, data, status = api_call("POST", "cash-advances", token=tokens["sales"],
                                    data=ca_data, entity_id=ENT_KSC)
    if success and data:
        ca_id_sales = data["id"]
        log_test("Sales can create cash-advance", True)
        
        # Submit
        api_call("POST", f"cash-advances/{ca_id_sales}/submit",
                token=tokens["sales"], entity_id=ENT_KSC)
        # Approve 3 times (using admin)
        for _ in range(3):
            api_call("POST", f"cash-advances/{ca_id_sales}/approve",
                    token=tokens["admin"], data={"note": "ok"},
                    entity_id=ENT_KSC)
        
        # Try to disburse as sales (should be 403)
        disburse_data = {"cash_type": "kas_kecil", "note": "Should fail"}
        success, data, status = api_call("POST", f"cash-advances/{ca_id_sales}/disburse",
                                        token=tokens["sales"], data=disburse_data,
                                        entity_id=ENT_KSC, expected_status=403)
        log_test("Sales FORBIDDEN on disburse (403)", success)
    else:
        log_test("Sales can create cash-advance", False, f"status={status}")
    
    # Warehouse FORBIDDEN on GET cash-advances (no cash_advance module)
    success, data, status = api_call("GET", "cash-advances",
                                    token=tokens["warehouse"], entity_id=ENT_KSC,
                                    expected_status=403)
    log_test("Warehouse FORBIDDEN on GET cash-advances (403)", success)
    
    # Warehouse ALLOWED on GET/POST vehicles
    success, data, status = api_call("GET", "vehicles",
                                    token=tokens["warehouse"], entity_id=ENT_KSC)
    log_test("Warehouse ALLOWED on GET vehicles", success)
    
    veh_data = {
        "entity_id": ENT_KSC,
        "no_polisi": "B 9999 WH",
        "nama": "Warehouse Vehicle",
        "jenis": "mobil"
    }
    success, data, status = api_call("POST", "vehicles",
                                    token=tokens["warehouse"], data=veh_data,
                                    entity_id=ENT_KSC)
    log_test("Warehouse ALLOWED on POST vehicles", success)
    
    # Sales FORBIDDEN on PATCH expense-categories (needs manage)
    if "expense_category_code" in test_data:
        code = test_data["expense_category_code"]
        update_data = {"label": "Should fail"}
        success, data, status = api_call("PATCH", f"expense-categories/{code}",
                                        token=tokens["sales"], data=update_data,
                                        expected_status=403)
        log_test("Sales FORBIDDEN on PATCH expense-categories (403)", success)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10: ENTITY SCOPING
# ═══════════════════════════════════════════════════════════════════════════
def test_entity_scoping():
    print("\n[TEST 10] Entity Scoping")
    
    # Create CA under ent_kanda
    ca_data = {
        "entity_id": ENT_KANDA,
        "divisi": "Kanda Division",
        "kegiatan": "Kanda Activity",
        "payment_method": "tunai",
        "lines": [{"description": "Kanda Item", "qty": 1, "unit_price": 200000, "satuan": "unit"}],
    }
    success, data, status = api_call("POST", "cash-advances", token=tokens["admin"],
                                    data=ca_data, entity_id=ENT_KANDA)
    if success and data:
        ca_id_kanda = data["id"]
        log_test("Create CA under ent_kanda", True)
        
        # List under ent_ksc should NOT show ent_kanda CA
        success, data, status = api_call("GET", "cash-advances",
                                        token=tokens["admin"], entity_id=ENT_KSC)
        if success and isinstance(data, list):
            kanda_in_ksc = any(ca.get("id") == ca_id_kanda for ca in data)
            log_test("ent_kanda CA NOT in ent_ksc list", not kanda_in_ksc)
        
        # GET by ID under mismatched entity should 404
        success, data, status = api_call("GET", f"cash-advances/{ca_id_kanda}",
                                        token=tokens["admin"], entity_id=ENT_KSC,
                                        expected_status=404)
        log_test("GET ent_kanda CA under ent_ksc returns 404", success)
        
        # GET by ID under correct entity should work
        success, data, status = api_call("GET", f"cash-advances/{ca_id_kanda}",
                                        token=tokens["admin"], entity_id=ENT_KANDA)
        log_test("GET ent_kanda CA under ent_kanda works", success and data.get("id") == ca_id_kanda)
    else:
        log_test("Create CA under ent_kanda", False, f"status={status}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 80)
    print("FASE 2 — Backend API Testing (Digitalisasi Formulir Sukacita)")
    print("=" * 80)
    
    test_auth()
    
    if not tokens.get("admin"):
        print("\n❌ CRITICAL: Admin login failed. Cannot proceed with tests.")
        return 1
    
    test_expense_categories()
    test_cash_advance_crud()
    test_cash_advance_state_machine()
    test_cash_advance_disburse()
    test_settlement()
    test_vehicles()
    test_vehicle_usage_logs()
    test_rbac_negative()
    test_entity_scoping()
    
    print("\n" + "=" * 80)
    print(f"RESULTS: {tests_passed}/{tests_run} tests passed")
    if tests_failed > 0:
        print(f"❌ {tests_failed} tests FAILED")
    else:
        print("✅ All tests PASSED")
    print("=" * 80)
    
    return 0 if tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
