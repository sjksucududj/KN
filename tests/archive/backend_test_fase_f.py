#!/usr/bin/env python3
"""
FASE F R&D & Design - Backend API Testing
Tests key R&D endpoints for specifications, samples, designs, and reports
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://kn-supplier-verify.preview.emergentagent.com"
API = f"{BASE_URL}/api"

# Test credentials (all password: demo12345)
USERS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
}

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add(self, name, passed, details=""):
        self.tests.append({"name": name, "passed": passed, "details": details})
        if passed:
            self.passed += 1
            print(f"✓ {name}")
            if details:
                print(f"  → {details}")
        else:
            self.failed += 1
            print(f"✗ {name}")
            if details:
                print(f"  → {details}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"BACKEND API TEST RESULTS - FASE F R&D")
        print(f"{'='*60}")
        print(f"Passed: {self.passed}/{total}")
        print(f"Failed: {self.failed}/{total}")
        print(f"Success Rate: {(self.passed/total*100) if total > 0 else 0:.1f}%")
        return self.failed == 0

results = TestResults()

def login(role):
    """Login and get token"""
    try:
        r = requests.post(f"{API}/auth/login", json=USERS[role], timeout=10)
        if r.status_code == 200:
            return r.json().get("token")
        return None
    except Exception as e:
        print(f"Login failed for {role}: {e}")
        return None

def headers(token):
    """Get auth headers"""
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def test_rnd_meta(tokens):
    """Test R&D metadata endpoint"""
    print("\n--- Testing R&D Metadata ---")
    
    try:
        r = requests.get(f"{API}/rnd/meta", headers=headers(tokens["admin"]), timeout=10)
        results.add(
            "GET /api/rnd/meta",
            r.status_code == 200,
            f"Status: {r.status_code}"
        )
        
        if r.status_code == 200:
            meta = r.json()
            results.add(
                "Meta contains policy",
                "policy" in meta,
                f"Policy keys: {list(meta.get('policy', {}).keys())}"
            )
            results.add(
                "Meta contains sample_types",
                "sample_types" in meta and len(meta.get("sample_types", [])) > 0,
                f"Sample types: {len(meta.get('sample_types', []))}"
            )
            results.add(
                "Meta contains lifecycles",
                "lifecycles" in meta and len(meta.get("lifecycles", [])) > 0,
                f"Lifecycles: {len(meta.get('lifecycles', []))}"
            )
    except Exception as e:
        results.add("GET /api/rnd/meta", False, str(e))

def test_rnd_specs(tokens):
    """Test R&D specifications endpoints"""
    print("\n--- Testing R&D Specifications ---")
    
    # Test GET /api/rnd/specs
    try:
        r = requests.get(f"{API}/rnd/specs", headers=headers(tokens["admin"]), timeout=10)
        results.add(
            "GET /api/rnd/specs",
            r.status_code == 200,
            f"Status: {r.status_code}, Count: {len(r.json()) if r.status_code == 200 else 0}"
        )
        
        if r.status_code == 200:
            specs = r.json()
            if specs:
                # Test GET /api/rnd/specs/{id}
                spec_id = specs[0]["id"]
                try:
                    r2 = requests.get(f"{API}/rnd/specs/{spec_id}", headers=headers(tokens["admin"]), timeout=10)
                    results.add(
                        "GET /api/rnd/specs/{id}",
                        r2.status_code == 200,
                        f"Status: {r2.status_code}, Number: {r2.json().get('number') if r2.status_code == 200 else 'N/A'}"
                    )
                except Exception as e:
                    results.add("GET /api/rnd/specs/{id}", False, str(e))
    except Exception as e:
        results.add("GET /api/rnd/specs", False, str(e))
    
    # Test RBAC: warehouse cannot create specs
    try:
        r = requests.post(
            f"{API}/rnd/specs",
            headers=headers(tokens["warehouse"]),
            json={"title": "Test Spec", "target": {"fabric_type": "woven"}},
            timeout=10
        )
        results.add(
            "Warehouse cannot create specs (RBAC)",
            r.status_code == 403,
            f"Status: {r.status_code}"
        )
    except Exception as e:
        results.add("Warehouse cannot create specs (RBAC)", False, str(e))

def test_rnd_samples(tokens):
    """Test R&D samples endpoints"""
    print("\n--- Testing R&D Samples ---")
    
    # Test GET /api/rnd/samples
    try:
        r = requests.get(f"{API}/rnd/samples", headers=headers(tokens["admin"]), timeout=10)
        results.add(
            "GET /api/rnd/samples",
            r.status_code == 200,
            f"Status: {r.status_code}, Count: {len(r.json()) if r.status_code == 200 else 0}"
        )
        
        if r.status_code == 200:
            samples = r.json()
            if samples:
                # Test GET /api/rnd/samples/{id}
                sample_id = samples[0]["id"]
                try:
                    r2 = requests.get(f"{API}/rnd/samples/{sample_id}", headers=headers(tokens["admin"]), timeout=10)
                    results.add(
                        "GET /api/rnd/samples/{id}",
                        r2.status_code == 200,
                        f"Status: {r2.status_code}, Number: {r2.json().get('number') if r2.status_code == 200 else 'N/A'}"
                    )
                    
                    if r2.status_code == 200:
                        sample = r2.json()
                        results.add(
                            "Sample has required fields",
                            all(k in sample for k in ["number", "status", "sample_type"]),
                            f"Type: {sample.get('sample_type')}, Status: {sample.get('status')}"
                        )
                        
                        # Check if sample has rounds
                        if sample.get("rounds"):
                            results.add(
                                "Sample has rounds",
                                len(sample["rounds"]) > 0,
                                f"Rounds: {len(sample['rounds'])}"
                            )
                except Exception as e:
                    results.add("GET /api/rnd/samples/{id}", False, str(e))
    except Exception as e:
        results.add("GET /api/rnd/samples", False, str(e))

def test_design_gallery(tokens):
    """Test design gallery endpoints"""
    print("\n--- Testing Design Gallery ---")
    
    # Test GET /api/design-gallery
    try:
        r = requests.get(f"{API}/design-gallery", headers=headers(tokens["admin"]), timeout=10)
        results.add(
            "GET /api/design-gallery",
            r.status_code == 200,
            f"Status: {r.status_code}, Count: {len(r.json()) if r.status_code == 200 else 0}"
        )
        
        if r.status_code == 200:
            designs = r.json()
            if designs:
                design = designs[0]
                results.add(
                    "Design has required fields",
                    all(k in design for k in ["id", "title", "status"]),
                    f"Title: {design.get('title')}, Status: {design.get('status')}"
                )
                
                # Check if design has code (FASE F addition)
                if "code" in design:
                    results.add(
                        "Design has code field (FASE F)",
                        True,
                        f"Code: {design.get('code')}"
                    )
    except Exception as e:
        results.add("GET /api/design-gallery", False, str(e))

def test_rnd_reports(tokens):
    """Test R&D reports endpoints"""
    print("\n--- Testing R&D Reports ---")
    
    # Test GET /api/rnd/reports/performer
    try:
        r = requests.get(f"{API}/rnd/reports/performer", headers=headers(tokens["manager"]), timeout=10)
        results.add(
            "GET /api/rnd/reports/performer",
            r.status_code == 200,
            f"Status: {r.status_code}"
        )
        
        if r.status_code == 200:
            report = r.json()
            results.add(
                "Performer report has data",
                "count" in report or "stats" in report,
                f"Keys: {list(report.keys())}"
            )
    except Exception as e:
        results.add("GET /api/rnd/reports/performer", False, str(e))
    
    # Test GET /api/rnd/lifecycle-board
    try:
        r = requests.get(f"{API}/rnd/lifecycle-board", headers=headers(tokens["manager"]), timeout=10)
        results.add(
            "GET /api/rnd/lifecycle-board",
            r.status_code == 200,
            f"Status: {r.status_code}"
        )
        
        if r.status_code == 200:
            board = r.json()
            results.add(
                "Lifecycle board has data",
                "not_orderable" in board or "enforcement" in board,
                f"Keys: {list(board.keys())}"
            )
    except Exception as e:
        results.add("GET /api/rnd/lifecycle-board", False, str(e))

def test_products_orderable(tokens):
    """Test products orderable_only filter"""
    print("\n--- Testing Products Orderable Filter ---")
    
    # Test GET /api/products?orderable_only=true
    try:
        r = requests.get(
            f"{API}/products",
            headers=headers(tokens["sales"]),
            params={"orderable_only": "true"},
            timeout=10
        )
        results.add(
            "GET /api/products?orderable_only=true",
            r.status_code == 200,
            f"Status: {r.status_code}, Count: {len(r.json()) if r.status_code == 200 else 0}"
        )
        
        if r.status_code == 200:
            products = r.json()
            # Check if products have lifecycle field
            if products:
                has_lifecycle = any("lifecycle" in p for p in products)
                results.add(
                    "Products have lifecycle field (FASE F)",
                    has_lifecycle,
                    f"Sample product lifecycle: {products[0].get('lifecycle', 'N/A')}"
                )
    except Exception as e:
        results.add("GET /api/products?orderable_only=true", False, str(e))

def test_color_library(tokens):
    """Test color library (used by R&D specs)"""
    print("\n--- Testing Color Library Integration ---")
    
    # Test GET /api/color-library
    try:
        r = requests.get(f"{API}/color-library", headers=headers(tokens["admin"]), timeout=10)
        results.add(
            "GET /api/color-library",
            r.status_code == 200,
            f"Status: {r.status_code}, Count: {len(r.json()) if r.status_code == 200 else 0}"
        )
        
        if r.status_code == 200:
            colors = r.json()
            if colors:
                color = colors[0]
                results.add(
                    "Color has required fields",
                    all(k in color for k in ["id", "code", "name"]),
                    f"Code: {color.get('code')}, Name: {color.get('name')}"
                )
    except Exception as e:
        results.add("GET /api/color-library", False, str(e))

def main():
    print("="*60)
    print("FASE F R&D & Design - Backend API Testing")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Login all users
    print("\n--- Logging in users ---")
    tokens = {}
    for role in USERS.keys():
        token = login(role)
        if token:
            tokens[role] = token
            print(f"✓ Logged in as {role}")
        else:
            print(f"✗ Failed to login as {role}")
            return 1
    
    # Run tests
    test_rnd_meta(tokens)
    test_rnd_specs(tokens)
    test_rnd_samples(tokens)
    test_design_gallery(tokens)
    test_rnd_reports(tokens)
    test_products_orderable(tokens)
    test_color_library(tokens)
    
    # Print summary
    success = results.summary()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
