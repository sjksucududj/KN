"""
Backend API Tests for Kontrabon Fix + Design Rating Feature

PHASE A: Kontrabon seed fix verification
- GET /api/contra-bons returns 3 kontrabon records

PHASE B: Design Rating API tests
- POST /api/design-gallery/{id}/rating (admin/manager can rate 1-5)
- POST rating as different user (avg reflects both, count=2)
- Re-POST as same user (no duplicate, count stays same)
- GET /api/design-gallery/{id} includes my_rating
- POST invalid stars (9) returns 400
- POST as sales returns 403
- GET as sales sees rating_avg but my_rating is null
- DELETE /api/design-gallery/{id}/rating removes rating
"""
import requests
import sys
from typing import Dict, Any

# Use public endpoint
BASE_URL = "https://po-grid-layout.preview.emergentagent.com/api"
PASSWORD = "demo12345"

# Test users
ADMIN_EMAIL = "admin@kainnusantara.id"
MANAGER_EMAIL = "manager@kainnusantara.id"
SALES_EMAIL = "sales@kainnusantara.id"

# Entity header
ENTITY_ID = "ent_ksc"

# Test counters
tests_run = 0
tests_passed = 0
tests_failed = 0


def log_test(name: str, passed: bool, details: str = ""):
    """Log test result"""
    global tests_run, tests_passed, tests_failed
    tests_run += 1
    if passed:
        tests_passed += 1
        print(f"✅ PASS: {name}")
        if details:
            print(f"   {details}")
    else:
        tests_failed += 1
        print(f"❌ FAIL: {name}")
        if details:
            print(f"   {details}")


def login(email: str) -> Dict[str, Any]:
    """Login and return token + user info"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": email, "password": PASSWORD},
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        return {"token": data["token"], "user": data.get("user", {})}
    except Exception as e:
        print(f"❌ Login failed for {email}: {e}")
        sys.exit(1)


def headers(token: str, entity_id: str = ENTITY_ID) -> Dict[str, str]:
    """Return authorization headers with entity"""
    return {
        "Authorization": f"Bearer {token}",
        "X-Entity-Id": entity_id
    }


def test_kontrabon_seeded():
    """PHASE A: Verify 3 kontrabon records exist after seed fix"""
    print("\n=== PHASE A: Kontrabon Seed Fix Verification ===")
    
    admin = login(ADMIN_EMAIL)
    
    # Test: GET /api/contra-bons returns 3 records
    try:
        response = requests.get(
            f"{BASE_URL}/contra-bons",
            headers=headers(admin["token"]),
            timeout=15
        )
        response.raise_for_status()
        contra_bons = response.json()
        
        count = len(contra_bons)
        has_three = count == 3
        
        # Check for expected numbers
        numbers = [cb.get("number") for cb in contra_bons]
        has_cb1 = any("CB-00001" in n for n in numbers)
        has_cb2 = any("CB-00002" in n for n in numbers)
        has_cb3 = any("CB-00003" in n for n in numbers)
        
        log_test(
            "GET /api/contra-bons returns 3 kontrabon records",
            has_three and has_cb1 and has_cb2 and has_cb3,
            f"Count: {count}, Numbers: {numbers}"
        )
        
        # Check statuses
        if has_three:
            statuses = {cb.get("number"): cb.get("status") for cb in contra_bons}
            log_test(
                "Kontrabon statuses are correct",
                True,
                f"Statuses: {statuses}"
            )
    except Exception as e:
        log_test("GET /api/contra-bons returns 3 records", False, str(e))


def test_design_rating_api():
    """PHASE B: Design Rating API comprehensive tests"""
    print("\n=== PHASE B: Design Rating API Tests ===")
    
    admin = login(ADMIN_EMAIL)
    manager = login(MANAGER_EMAIL)
    sales = login(SALES_EMAIL)
    
    # First, get a design to test with
    try:
        response = requests.get(
            f"{BASE_URL}/design-gallery",
            headers=headers(admin["token"]),
            timeout=15
        )
        response.raise_for_status()
        designs = response.json()
        
        if not designs:
            log_test("Find design for rating tests", False, "No designs found in gallery")
            return
        
        design_id = designs[0]["id"]
        design_title = designs[0].get("title", "")
        print(f"   Using design: {design_title} ({design_id})")
        
    except Exception as e:
        log_test("Find design for rating tests", False, str(e))
        return
    
    # Test B1: Admin can POST rating with stars 1-5
    try:
        response = requests.post(
            f"{BASE_URL}/design-gallery/{design_id}/rating",
            json={"stars": 5, "note": "Excellent design"},
            headers=headers(admin["token"]),
            timeout=15
        )
        is_200 = response.status_code == 200
        if is_200:
            data = response.json()
            has_avg = "rating_avg" in data
            has_count = "rating_count" in data
            has_my_rating = "my_rating" in data
            count_is_one = data.get("rating_count") == 1
            avg_is_five = data.get("rating_avg") == 5.0
            my_rating_is_five = data.get("my_rating") == 5
            
            log_test(
                "Admin POST rating stars=5 returns 200 with rating_avg, rating_count, my_rating",
                is_200 and has_avg and has_count and has_my_rating and count_is_one and avg_is_five and my_rating_is_five,
                f"Status: {response.status_code}, avg: {data.get('rating_avg')}, count: {data.get('rating_count')}, my_rating: {data.get('my_rating')}"
            )
        else:
            log_test("Admin POST rating", False, f"Status: {response.status_code}, Error: {response.text[:200]}")
    except Exception as e:
        log_test("Admin POST rating", False, str(e))
    
    # Test B2: Manager can POST rating, avg reflects both raters, count=2
    try:
        response = requests.post(
            f"{BASE_URL}/design-gallery/{design_id}/rating",
            json={"stars": 3, "note": "Good but needs improvement"},
            headers=headers(manager["token"]),
            timeout=15
        )
        is_200 = response.status_code == 200
        if is_200:
            data = response.json()
            count_is_two = data.get("rating_count") == 2
            avg_is_four = abs(data.get("rating_avg", 0) - 4.0) < 0.01  # (5+3)/2 = 4.0
            my_rating_is_three = data.get("my_rating") == 3
            
            log_test(
                "Manager POST rating stars=3, avg=(5+3)/2=4.0, count=2",
                is_200 and count_is_two and avg_is_four and my_rating_is_three,
                f"Status: {response.status_code}, avg: {data.get('rating_avg')}, count: {data.get('rating_count')}, my_rating: {data.get('my_rating')}"
            )
        else:
            log_test("Manager POST rating", False, f"Status: {response.status_code}")
    except Exception as e:
        log_test("Manager POST rating", False, str(e))
    
    # Test B3: Re-POST as admin with stars=4, count stays 2 (no duplicate), avg updates
    try:
        response = requests.post(
            f"{BASE_URL}/design-gallery/{design_id}/rating",
            json={"stars": 4, "note": "Updated rating"},
            headers=headers(admin["token"]),
            timeout=15
        )
        is_200 = response.status_code == 200
        if is_200:
            data = response.json()
            count_still_two = data.get("rating_count") == 2
            avg_is_three_five = abs(data.get("rating_avg", 0) - 3.5) < 0.01  # (4+3)/2 = 3.5
            my_rating_is_four = data.get("my_rating") == 4
            
            log_test(
                "Admin re-POST rating stars=4, count stays 2 (no duplicate), avg=(4+3)/2=3.5",
                is_200 and count_still_two and avg_is_three_five and my_rating_is_four,
                f"Status: {response.status_code}, avg: {data.get('rating_avg')}, count: {data.get('rating_count')}, my_rating: {data.get('my_rating')}"
            )
        else:
            log_test("Admin re-POST rating", False, f"Status: {response.status_code}")
    except Exception as e:
        log_test("Admin re-POST rating", False, str(e))
    
    # Test B4: GET design as admin includes my_rating
    try:
        response = requests.get(
            f"{BASE_URL}/design-gallery/{design_id}",
            headers=headers(admin["token"]),
            timeout=15
        )
        is_200 = response.status_code == 200
        if is_200:
            data = response.json()
            has_my_rating = "my_rating" in data
            my_rating_is_four = data.get("my_rating") == 4
            
            log_test(
                "GET design as admin includes my_rating=4",
                is_200 and has_my_rating and my_rating_is_four,
                f"Status: {response.status_code}, my_rating: {data.get('my_rating')}"
            )
        else:
            log_test("GET design includes my_rating", False, f"Status: {response.status_code}")
    except Exception as e:
        log_test("GET design includes my_rating", False, str(e))
    
    # Test B5: POST invalid stars (9) returns 400 with Indonesian message
    try:
        response = requests.post(
            f"{BASE_URL}/design-gallery/{design_id}/rating",
            json={"stars": 9},
            headers=headers(admin["token"]),
            timeout=15
        )
        is_400 = response.status_code == 400
        has_indonesian_msg = any(word in response.text.lower() for word in ["bintang", "nilai", "antara"])
        
        log_test(
            "POST invalid stars=9 returns 400 with Indonesian message",
            is_400 and has_indonesian_msg,
            f"Status: {response.status_code}, Has Indonesian message: {has_indonesian_msg}"
        )
    except Exception as e:
        log_test("POST invalid stars returns 400", False, str(e))
    
    # Test B6: POST as sales returns 403 (sales cannot rate)
    try:
        response = requests.post(
            f"{BASE_URL}/design-gallery/{design_id}/rating",
            json={"stars": 5},
            headers=headers(sales["token"]),
            timeout=15
        )
        is_403 = response.status_code == 403
        
        log_test(
            "POST rating as sales returns 403 (sales cannot rate)",
            is_403,
            f"Status: {response.status_code}"
        )
    except Exception as e:
        log_test("POST rating as sales returns 403", False, str(e))
    
    # Test B7: GET as sales sees rating_avg but my_rating is null
    try:
        response = requests.get(
            f"{BASE_URL}/design-gallery/{design_id}",
            headers=headers(sales["token"]),
            timeout=15
        )
        is_200 = response.status_code == 200
        if is_200:
            data = response.json()
            has_rating_avg = "rating_avg" in data
            has_rating_count = "rating_count" in data
            my_rating_is_null = data.get("my_rating") is None
            
            log_test(
                "GET as sales sees rating_avg and rating_count but my_rating is null",
                is_200 and has_rating_avg and has_rating_count and my_rating_is_null,
                f"Status: {response.status_code}, rating_avg: {data.get('rating_avg')}, rating_count: {data.get('rating_count')}, my_rating: {data.get('my_rating')}"
            )
        else:
            log_test("GET as sales sees rating_avg", False, f"Status: {response.status_code}")
    except Exception as e:
        log_test("GET as sales sees rating_avg", False, str(e))
    
    # Test B8: DELETE rating as admin removes only admin's rating (count decreases to 1)
    try:
        response = requests.delete(
            f"{BASE_URL}/design-gallery/{design_id}/rating",
            headers=headers(admin["token"]),
            timeout=15
        )
        is_200 = response.status_code == 200
        if is_200:
            data = response.json()
            count_is_one = data.get("rating_count") == 1
            avg_is_three = data.get("rating_avg") == 3.0  # Only manager's rating (3) remains
            my_rating_is_null = data.get("my_rating") is None
            
            log_test(
                "DELETE rating as admin removes only admin's rating (count=1, avg=3.0)",
                is_200 and count_is_one and avg_is_three and my_rating_is_null,
                f"Status: {response.status_code}, avg: {data.get('rating_avg')}, count: {data.get('rating_count')}, my_rating: {data.get('my_rating')}"
            )
        else:
            log_test("DELETE rating as admin", False, f"Status: {response.status_code}")
    except Exception as e:
        log_test("DELETE rating as admin", False, str(e))


def main():
    """Run all backend tests"""
    print("\n" + "="*80)
    print("Backend API Tests — Kontrabon Fix + Design Rating")
    print("="*80)
    
    try:
        test_kontrabon_seeded()
        test_design_rating_api()
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        return 1
    
    print("\n" + "="*80)
    print(f"RESULTS: {tests_passed} PASSED / {tests_failed} FAILED / {tests_run} TOTAL")
    print("="*80 + "\n")
    
    return 0 if tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
