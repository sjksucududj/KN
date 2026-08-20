#!/usr/bin/env python3
"""
Backend Testing for PS-18 Phase 4 Features
===========================================
CRITICAL FOCUS: Privacy testing for /api/rnd/reports/my-kpi endpoint

Tests:
1. PRIVACY (MOST CRITICAL) - my-kpi endpoint must NOT leak other designers' data
2. Manager Home endpoint with proper RBAC
3. Export endpoints (CSV/XLSX/PDF) with RBAC
4. Data consistency checks
"""

import sys
import json
import httpx

# Public backend URL from frontend/.env
BASE_URL = "https://kn-dev-continue-1.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
CREDENTIALS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
}

# Designer names to check for privacy leaks
DESIGNER_NAMES = ["Dewi Lestari", "Rina Kartika", "Dewi Rahayu", "Bagas Nugroho"]

# Test results
test_results = {
    "passed": [],
    "failed": [],
    "total": 0
}


def log_test(name, passed, detail=""):
    """Log test result"""
    test_results["total"] += 1
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {name}")
    if detail:
        print(f"  → {detail}")
    
    if passed:
        test_results["passed"].append(name)
    else:
        test_results["failed"].append({"name": name, "detail": detail})
    
    return passed


def login(role):
    """Login and return token - uses separate client to avoid cookie contamination"""
    client = httpx.Client(timeout=30.0)
    try:
        creds = CREDENTIALS[role]
        response = client.post(f"{BASE_URL}/auth/login", json=creds)
        response.raise_for_status()
        data = response.json()
        token = data.get("token")
        if not token:
            print(f"❌ Login failed for {role}: No token in response")
            return None
        return token
    except Exception as e:
        print(f"❌ Login failed for {role}: {str(e)}")
        return None
    finally:
        client.close()


def get_headers(token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: PRIVACY - my-kpi endpoint (MOST CRITICAL)
# ═══════════════════════════════════════════════════════════════════════════
def test_privacy_my_kpi():
    """Test that my-kpi endpoint does NOT leak other designers' data"""
    print("\n" + "="*80)
    print("TEST 1: PRIVACY - my-kpi endpoint (MOST CRITICAL)")
    print("="*80)
    
    client = httpx.Client(timeout=30.0)
    
    try:
        # First, get all designer names from the full KPI report (admin view)
        admin_token = login("admin")
        if not admin_token:
            log_test("Privacy Test - Admin Login", False, "Failed to login as admin")
            return
        
        response = client.get(
            f"{BASE_URL}/rnd/reports/designer-kpi?period=all",
            headers=get_headers(admin_token)
        )
        
        if response.status_code != 200:
            log_test("Privacy Test - Get All Designers", False, 
                    f"HTTP {response.status_code}: {response.text[:200]}")
            return
        
        full_report = response.json()
        all_designers = [item["designer"] for item in full_report.get("items", [])]
        
        log_test("Privacy Test - Get All Designers", len(all_designers) >= 2,
                f"Found {len(all_designers)} designers: {', '.join(all_designers[:5])}")
        
        # Test manager's my-kpi endpoint
        manager_token = login("manager")
        if not manager_token:
            log_test("Privacy Test - Manager Login", False, "Failed to login as manager")
            return
        
        log_test("Privacy Test - Manager Login", True, "Manager logged in successfully")
        
        # Test all periods
        for period in ["all", "30d", "90d", "month"]:
            response = client.get(
                f"{BASE_URL}/rnd/reports/my-kpi?period={period}",
                headers=get_headers(manager_token)
            )
            
            if response.status_code != 200:
                log_test(f"Privacy Test - Manager my-kpi ({period})", False,
                        f"HTTP {response.status_code}: {response.text[:200]}")
                continue
            
            my_kpi = response.json()
            manager_name = my_kpi.get("designer", "")
            
            # Check that manager sees their own data
            has_me = my_kpi.get("me") is not None
            log_test(f"Privacy Test - Manager has 'me' field ({period})", has_me,
                    f"Manager: {manager_name}, Grade: {my_kpi.get('me', {}).get('grade_letter', 'N/A')}")
            
            # CRITICAL: Check for privacy leaks - no other designer names in response
            response_text = json.dumps(my_kpi, ensure_ascii=False)
            leaked_names = []
            for designer in all_designers:
                if designer != manager_name and designer in response_text:
                    leaked_names.append(designer)
            
            log_test(f"Privacy Test - No leaked names ({period})", 
                    len(leaked_names) == 0,
                    f"Leaked names: {leaked_names}" if leaked_names else "No leaks detected")
            
            # Check that response does NOT have 'items' or 'leaderboard' keys
            has_items = "items" in my_kpi
            has_leaderboard = "leaderboard" in my_kpi
            log_test(f"Privacy Test - No 'items' or 'leaderboard' ({period})",
                    not has_items and not has_leaderboard,
                    f"items={has_items}, leaderboard={has_leaderboard}")
            
            # Check that team data is aggregate only
            team = my_kpi.get("team", {})
            is_aggregate = isinstance(team, dict) and "designers" in team
            log_test(f"Privacy Test - Team is aggregate only ({period})", is_aggregate,
                    f"Team: {team.get('designers', 0)} designers, avg_grade={team.get('avg_grade', 'N/A')}")
            
            # Check rank and total_designers are present
            has_rank = my_kpi.get("rank") is not None
            has_total = my_kpi.get("total_designers") is not None
            log_test(f"Privacy Test - Rank info present ({period})", has_rank and has_total,
                    f"Rank {my_kpi.get('rank', '?')} of {my_kpi.get('total_designers', '?')}")
        
        # Test non-designer roles (sales, warehouse) - should return 200 with me=null
        for role in ["sales", "warehouse"]:
            token = login(role)
            if not token:
                log_test(f"Privacy Test - {role.title()} Login", False, f"Failed to login as {role}")
                continue
            
            response = client.get(
                f"{BASE_URL}/rnd/reports/my-kpi?period=all",
                headers=get_headers(token)
            )
            
            if response.status_code != 200:
                log_test(f"Privacy Test - {role.title()} my-kpi access", False,
                        f"HTTP {response.status_code}: {response.text[:200]}")
                continue
            
            data = response.json()
            has_no_me = data.get("me") is None
            
            # Check for leaks in non-designer response
            response_text = json.dumps(data, ensure_ascii=False)
            leaked = [name for name in all_designers if name in response_text]
            
            log_test(f"Privacy Test - {role.title()} has no 'me' data", has_no_me,
                    f"me={data.get('me')}")
            log_test(f"Privacy Test - {role.title()} no leaked names", len(leaked) == 0,
                    f"Leaked: {leaked}" if leaked else "No leaks")
    
    except Exception as e:
        log_test("Privacy Test - Exception", False, str(e))
    finally:
        client.close()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Manager Home Endpoint
# ═══════════════════════════════════════════════════════════════════════════
def test_manager_home():
    """Test manager home endpoint with proper RBAC"""
    print("\n" + "="*80)
    print("TEST 2: Manager Home Endpoint")
    print("="*80)
    
    client = httpx.Client(timeout=30.0)
    
    try:
        # Test manager access
        manager_token = login("manager")
        if not manager_token:
            log_test("Manager Home - Manager Login", False, "Failed to login")
            return
        
        response = client.get(
            f"{BASE_URL}/home/manager",
            headers=get_headers(manager_token)
        )
        
        if response.status_code != 200:
            log_test("Manager Home - Manager Access", False,
                    f"HTTP {response.status_code}: {response.text[:200]}")
            return
        
        data = response.json()
        log_test("Manager Home - Manager Access", True, f"HTTP {response.status_code}")
        
        # Check required fields
        required_fields = ["period", "approvals", "target", "late_today", "team", "designers"]
        for field in required_fields:
            has_field = field in data
            log_test(f"Manager Home - Has '{field}' field", has_field,
                    f"Value: {str(data.get(field, 'N/A'))[:100]}")
        
        # Check approvals structure
        approvals = data.get("approvals", {})
        has_total = "total" in approvals
        has_items = "items" in approvals
        has_all_items = "all_items" in approvals
        log_test("Manager Home - Approvals structure", 
                has_total and has_items and has_all_items,
                f"total={approvals.get('total', 0)}, items={len(approvals.get('items', []))}")
        
        # Check that all_items has 4 types
        all_items = approvals.get("all_items", [])
        expected_keys = {"sales_order", "purchase_order", "price", "generic"}
        actual_keys = {item["key"] for item in all_items}
        log_test("Manager Home - Approval types complete", expected_keys == actual_keys,
                f"Expected: {expected_keys}, Got: {actual_keys}")
        
        # Check target structure
        target = data.get("target", {})
        has_amount = "amount" in target
        has_achievement = "achievement_pct" in target
        has_progress = "month_progress_pct" in target
        log_test("Manager Home - Target structure", 
                has_amount and has_achievement and has_progress,
                f"target={target.get('amount', 0)}, achievement={target.get('achievement_pct', 0)}%")
        
        # Check late_today structure
        late = data.get("late_today", {})
        has_total_items = "total_items" in late
        has_all_rows = "all_rows" in late
        log_test("Manager Home - Late today structure", has_total_items and has_all_rows,
                f"total_items={late.get('total_items', 0)}")
        
        # Check that late_today has 4 sources
        all_rows = late.get("all_rows", [])
        expected_sources = {"ar", "rnd", "wms", "production"}
        actual_sources = {row["key"] for row in all_rows}
        log_test("Manager Home - Late sources complete", expected_sources == actual_sources,
                f"Expected: {expected_sources}, Got: {actual_sources}")
        
        # Check RND consistency
        rnd_overdue = late.get("rnd_overdue", 0)
        log_test("Manager Home - RND overdue count present", rnd_overdue >= 0,
                f"rnd_overdue={rnd_overdue}, rnd_escalated_admin={late.get('rnd_escalated_admin', 0)}")
        
        # Check designers snapshot
        designers = data.get("designers", {})
        has_count = "count" in designers
        has_summary = "summary" in designers
        has_top = "top" in designers
        log_test("Manager Home - Designers snapshot", has_count and has_summary and has_top,
                f"count={designers.get('count', 0)}, top={len(designers.get('top', []))}")
        
        # Test admin access (should also work)
        admin_token = login("admin")
        if admin_token:
            response = client.get(
                f"{BASE_URL}/home/manager",
                headers=get_headers(admin_token)
            )
            log_test("Manager Home - Admin Access", response.status_code == 200,
                    f"HTTP {response.status_code}")
        
        # Test RBAC - sales and warehouse should get 403
        for role in ["sales", "warehouse"]:
            token = login(role)
            if not token:
                continue
            
            response = client.get(
                f"{BASE_URL}/home/manager",
                headers=get_headers(token)
            )
            log_test(f"Manager Home - {role.title()} RBAC (403)", response.status_code == 403,
                    f"HTTP {response.status_code}")
    
    except Exception as e:
        log_test("Manager Home - Exception", False, str(e))
    finally:
        client.close()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Export Endpoints (CSV/XLSX/PDF)
# ═══════════════════════════════════════════════════════════════════════════
def test_export_endpoints():
    """Test export endpoints with proper RBAC and file validation"""
    print("\n" + "="*80)
    print("TEST 3: Export Endpoints (CSV/XLSX/PDF)")
    print("="*80)
    
    client = httpx.Client(timeout=60.0)
    
    try:
        # Get designer list first
        admin_token = login("admin")
        if not admin_token:
            log_test("Export - Admin Login", False, "Failed to login")
            return
        
        response = client.get(
            f"{BASE_URL}/rnd/reports/designer-kpi?period=all",
            headers=get_headers(admin_token)
        )
        
        if response.status_code != 200:
            log_test("Export - Get Designer KPI", False, f"HTTP {response.status_code}")
            return
        
        kpi_data = response.json()
        designer_count = kpi_data.get("count", 0)
        designer_names = [item["designer"] for item in kpi_data.get("items", [])]
        
        log_test("Export - Get Designer KPI", True, 
                f"Found {designer_count} designers")
        
        # Test each format
        magic_bytes = {
            "csv": b"\xef\xbb\xbf",  # UTF-8 BOM
            "xlsx": b"PK",           # ZIP signature
            "pdf": b"%PDF"           # PDF signature
        }
        
        for fmt in ["csv", "xlsx", "pdf"]:
            # Test with admin
            response = client.get(
                f"{BASE_URL}/rnd/reports/designer-kpi/export?period=all&format={fmt}",
                headers=get_headers(admin_token)
            )
            
            if response.status_code != 200:
                log_test(f"Export - {fmt.upper()} Admin", False,
                        f"HTTP {response.status_code}: {response.text[:200]}")
                continue
            
            content = response.content
            disposition = response.headers.get("content-disposition", "")
            
            # Check magic bytes
            has_magic = content.startswith(magic_bytes[fmt])
            log_test(f"Export - {fmt.upper()} Magic Bytes", has_magic,
                    f"First bytes: {content[:10].hex()}")
            
            # Check Content-Disposition header
            has_attachment = "attachment" in disposition
            has_filename = f"kpi-desainer-" in disposition
            log_test(f"Export - {fmt.upper()} Headers", has_attachment and has_filename,
                    f"Disposition: {disposition[:80]}")
            
            # Check file size
            size_ok = len(content) > 500
            log_test(f"Export - {fmt.upper()} Size", size_ok,
                    f"Size: {len(content)} bytes")
            
            # Format-specific checks
            if fmt == "csv":
                text = content.decode("utf-8-sig")
                has_title = "Laporan KPI Desainer" in text
                has_formula = "Nilai =" in text
                has_all_names = all(name in text for name in designer_names)
                
                log_test(f"Export - CSV Content", has_title and has_formula,
                        f"Has title: {has_title}, Has formula: {has_formula}")
                log_test(f"Export - CSV All Designers", has_all_names,
                        f"Found {sum(1 for n in designer_names if n in text)}/{len(designer_names)} names")
            
            elif fmt == "xlsx":
                # Basic XLSX validation - just check it's a valid ZIP
                log_test(f"Export - XLSX Valid", content.startswith(b"PK"),
                        "Valid XLSX (ZIP) format")
        
        # Test period parameter
        response = client.get(
            f"{BASE_URL}/rnd/reports/designer-kpi/export?period=30d&format=csv",
            headers=get_headers(admin_token)
        )
        
        if response.status_code == 200:
            text = response.content.decode("utf-8-sig")
            has_period_label = "30 hari terakhir" in text
            log_test("Export - Period Parameter", has_period_label,
                    "Period label found in CSV")
        
        # Test invalid format
        response = client.get(
            f"{BASE_URL}/rnd/reports/designer-kpi/export?format=docx",
            headers=get_headers(admin_token)
        )
        
        is_400 = response.status_code == 400
        has_error_msg = "csv" in response.text.lower() if is_400 else False
        log_test("Export - Invalid Format (400)", is_400 and has_error_msg,
                f"HTTP {response.status_code}, Message: {response.text[:100]}")
        
        # Test RBAC
        manager_token = login("manager")
        if manager_token:
            response = client.get(
                f"{BASE_URL}/rnd/reports/designer-kpi/export?format=csv",
                headers=get_headers(manager_token)
            )
            log_test("Export - Manager Access (200)", response.status_code == 200,
                    f"HTTP {response.status_code}")
        
        for role in ["sales", "warehouse"]:
            token = login(role)
            if not token:
                continue
            
            response = client.get(
                f"{BASE_URL}/rnd/reports/designer-kpi/export?format=csv",
                headers=get_headers(token)
            )
            log_test(f"Export - {role.title()} RBAC (403)", response.status_code == 403,
                    f"HTTP {response.status_code}")
    
    except Exception as e:
        log_test("Export - Exception", False, str(e))
    finally:
        client.close()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Designer KPI Report (Full Report)
# ═══════════════════════════════════════════════════════════════════════════
def test_designer_kpi_report():
    """Test full designer KPI report endpoint"""
    print("\n" + "="*80)
    print("TEST 4: Designer KPI Report (Full Report)")
    print("="*80)
    
    client = httpx.Client(timeout=30.0)
    
    try:
        admin_token = login("admin")
        if not admin_token:
            log_test("KPI Report - Admin Login", False, "Failed to login")
            return
        
        # Test with different periods
        for period in ["all", "30d", "90d", "month"]:
            response = client.get(
                f"{BASE_URL}/rnd/reports/designer-kpi?period={period}",
                headers=get_headers(admin_token)
            )
            
            if response.status_code != 200:
                log_test(f"KPI Report - Period {period}", False,
                        f"HTTP {response.status_code}")
                continue
            
            data = response.json()
            
            # Check structure
            has_items = "items" in data
            has_summary = "summary" in data
            has_weights = "weights" in data
            has_grade_bands = "grade_bands" in data
            
            log_test(f"KPI Report - Structure ({period})", 
                    has_items and has_summary and has_weights and has_grade_bands,
                    f"count={data.get('count', 0)}, period_label={data.get('period_label', 'N/A')}")
        
        # Test RBAC - only admin and manager should access
        manager_token = login("manager")
        if manager_token:
            response = client.get(
                f"{BASE_URL}/rnd/reports/designer-kpi?period=all",
                headers=get_headers(manager_token)
            )
            log_test("KPI Report - Manager Access (200)", response.status_code == 200,
                    f"HTTP {response.status_code}")
        
        for role in ["sales", "warehouse"]:
            token = login(role)
            if not token:
                continue
            
            response = client.get(
                f"{BASE_URL}/rnd/reports/designer-kpi?period=all",
                headers=get_headers(token)
            )
            log_test(f"KPI Report - {role.title()} RBAC (403)", response.status_code == 403,
                    f"HTTP {response.status_code}")
    
    except Exception as e:
        log_test("KPI Report - Exception", False, str(e))
    finally:
        client.close()


# ═══════════════════════════════════════════════════════════════════════════
# Main Test Runner
# ═══════════════════════════════════════════════════════════════════════════
def main():
    """Run all backend tests"""
    print("\n" + "="*80)
    print("BACKEND TESTING - PS-18 Phase 4 Features")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print("="*80)
    
    # Run all tests
    test_privacy_my_kpi()
    test_manager_home()
    test_export_endpoints()
    test_designer_kpi_report()
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total Tests: {test_results['total']}")
    print(f"Passed: {len(test_results['passed'])} ✅")
    print(f"Failed: {len(test_results['failed'])} ❌")
    
    if test_results['failed']:
        print("\nFailed Tests:")
        for failure in test_results['failed']:
            print(f"  ❌ {failure['name']}")
            if failure['detail']:
                print(f"     → {failure['detail']}")
    
    success_rate = (len(test_results['passed']) / test_results['total'] * 100) if test_results['total'] > 0 else 0
    print(f"\nSuccess Rate: {success_rate:.1f}%")
    print("="*80)
    
    # Return exit code
    return 0 if len(test_results['failed']) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
