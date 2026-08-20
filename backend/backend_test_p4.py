#!/usr/bin/env python3
"""
Backend Sanity Test — P4 Modal Conversion
==========================================
Quick sanity checks to verify backend APIs still work after P4 frontend changes.
No backend changes were made in P4, so this just confirms APIs are accessible.
"""
import os
import sys
import requests
from datetime import datetime

BASE = os.environ.get("BACKEND_URL", "https://warehouse-ops-launch.preview.emergentagent.com").rstrip("/")
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


class P4SanityTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        
    def login(self, email="admin@kainnusantara.id", password="demo12345"):
        """Login as admin"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed: {r.status_code} {r.text[:100]}")
                return False
            data = r.json()
            self.token = data.get("token")
            if not self.token:
                bad("Login response missing token")
                return False
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "X-Entity-Id": "ent_ksc"
            })
            ok(f"Login {email}")
            return True
        except Exception as e:
            bad(f"Login exception: {e}")
            return False
    
    def test_get_suppliers(self):
        """GET /api/suppliers"""
        try:
            r = self.session.get(f"{API}/suppliers", timeout=30)
            if r.status_code == 200:
                data = r.json()
                ok(f"GET /api/suppliers → 200 ({len(data)} suppliers)")
                return True
            else:
                bad(f"GET /api/suppliers → {r.status_code}")
                return False
        except Exception as e:
            bad(f"GET /api/suppliers exception: {e}")
            return False
    
    def test_create_supplier(self):
        """POST /api/suppliers"""
        try:
            payload = {
                "name": "PT Uji Backend P4",
                "entity_id": "ent_ksc",
                "status": "active"
            }
            r = self.session.post(f"{API}/suppliers", json=payload, timeout=30)
            if r.status_code in [200, 201]:
                data = r.json()
                ok(f"POST /api/suppliers → {r.status_code} (code={data.get('code')}, name={data.get('name')})")
                return True
            else:
                bad(f"POST /api/suppliers → {r.status_code}: {r.text[:200]}")
                return False
        except Exception as e:
            bad(f"POST /api/suppliers exception: {e}")
            return False
    
    def test_get_purchase_returns(self):
        """GET /api/purchase-returns"""
        try:
            r = self.session.get(f"{API}/purchase-returns", timeout=30)
            if r.status_code == 200:
                data = r.json()
                ok(f"GET /api/purchase-returns → 200 ({len(data)} returns)")
                return True
            else:
                bad(f"GET /api/purchase-returns → {r.status_code}")
                return False
        except Exception as e:
            bad(f"GET /api/purchase-returns exception: {e}")
            return False
    
    def test_get_approval_rules(self):
        """GET /api/approval-rules"""
        try:
            r = self.session.get(f"{API}/approval-rules", timeout=30)
            if r.status_code == 200:
                data = r.json()
                ok(f"GET /api/approval-rules → 200 ({len(data)} rules)")
                return True
            else:
                bad(f"GET /api/approval-rules → {r.status_code}")
                return False
        except Exception as e:
            bad(f"GET /api/approval-rules exception: {e}")
            return False
    
    def test_get_hr_org_units(self):
        """GET /api/hr/org-units"""
        try:
            r = self.session.get(f"{API}/hr/org-units", timeout=30)
            if r.status_code == 200:
                data = r.json()
                ok(f"GET /api/hr/org-units → 200 ({len(data)} units)")
                return True
            else:
                bad(f"GET /api/hr/org-units → {r.status_code}")
                return False
        except Exception as e:
            bad(f"GET /api/hr/org-units exception: {e}")
            return False
    
    def test_get_return_policies(self):
        """GET /api/sales-return-policies"""
        try:
            r = self.session.get(f"{API}/sales-return-policies", timeout=30)
            if r.status_code == 200:
                data = r.json()
                ok(f"GET /api/sales-return-policies → 200 ({len(data)} policies)")
                return True
            else:
                bad(f"GET /api/sales-return-policies → {r.status_code}")
                return False
        except Exception as e:
            bad(f"GET /api/sales-return-policies exception: {e}")
            return False
    
    def test_get_transfers(self):
        """GET /api/transfers"""
        try:
            r = self.session.get(f"{API}/transfers", timeout=30)
            if r.status_code == 200:
                data = r.json()
                ok(f"GET /api/transfers → 200 ({len(data)} transfers)")
                return True
            else:
                bad(f"GET /api/transfers → {r.status_code}")
                return False
        except Exception as e:
            bad(f"GET /api/transfers exception: {e}")
            return False


def main():
    print("\n" + "="*70)
    print("BACKEND SANITY TEST — P4 Modal Conversion")
    print("="*70 + "\n")
    
    tester = P4SanityTester()
    
    # Login
    if not tester.login():
        print("\n❌ Login failed, cannot continue")
        return 1
    
    # Run all sanity checks
    print("\n📋 Running API sanity checks...\n")
    tester.test_get_suppliers()
    tester.test_create_supplier()
    tester.test_get_purchase_returns()
    tester.test_get_approval_rules()
    tester.test_get_hr_org_units()
    tester.test_get_return_policies()
    tester.test_get_transfers()
    
    # Summary
    print("\n" + "="*70)
    print(f"SUMMARY: {len(PASS)} passed, {len(FAIL)} failed")
    print("="*70 + "\n")
    
    if FAIL:
        print("❌ FAILED TESTS:")
        for f in FAIL:
            print(f"  • {f}")
        return 1
    else:
        print("✅ All backend sanity checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
