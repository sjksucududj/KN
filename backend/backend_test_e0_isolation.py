"""
Backend API Test - FASE E-0 Entity Isolation
Tests critical entity isolation fixes (L1-L21) via API calls.
"""
import requests
import sys
from typing import Dict, Any

BASE_URL = "https://code-forward-6.preview.emergentagent.com"

class EntityIsolationTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def login(self, email: str, password: str) -> str:
        """Login and get token"""
        print(f"\n🔐 Login: {email}")
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"email": email, "password": password},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                token = data.get("token")
                if token:
                    self.tokens[email] = token
                    print(f"✅ Login berhasil: {email}")
                    return token
                else:
                    print(f"❌ Login gagal: token tidak ditemukan")
                    return None
            else:
                print(f"❌ Login gagal: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return None

    def test_api(self, name: str, email: str, method: str, endpoint: str, 
                 expected_status: int, headers: Dict[str, str] = None,
                 data: Any = None, check_fn=None) -> bool:
        """Run a single API test"""
        self.tests_run += 1
        print(f"\n🔍 Test #{self.tests_run}: {name}")
        print(f"   User: {email}, Method: {method}, Endpoint: {endpoint}")
        
        try:
            token = self.tokens.get(email)
            if not token:
                print(f"❌ GAGAL - Token tidak ditemukan untuk {email}")
                self.tests_failed += 1
                self.failures.append(f"{name}: Token tidak ditemukan")
                return False

            req_headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            if headers:
                req_headers.update(headers)

            url = f"{self.base_url}{endpoint}"
            
            if method == 'GET':
                response = requests.get(url, headers=req_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=req_headers, timeout=10)
            else:
                print(f"❌ GAGAL - Method tidak didukung: {method}")
                self.tests_failed += 1
                return False

            status_match = response.status_code == expected_status
            
            if status_match:
                # Additional check function
                if check_fn:
                    try:
                        resp_data = response.json() if response.text else {}
                        check_result = check_fn(resp_data)
                        if check_result:
                            print(f"✅ LULUS - Status: {response.status_code}, Check: OK")
                            self.tests_passed += 1
                            return True
                        else:
                            print(f"❌ GAGAL - Status OK tapi check gagal")
                            self.tests_failed += 1
                            self.failures.append(f"{name}: Check function failed")
                            return False
                    except Exception as e:
                        print(f"❌ GAGAL - Check error: {str(e)}")
                        self.tests_failed += 1
                        self.failures.append(f"{name}: {str(e)}")
                        return False
                else:
                    print(f"✅ LULUS - Status: {response.status_code}")
                    self.tests_passed += 1
                    return True
            else:
                print(f"❌ GAGAL - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:300]}")
                self.tests_failed += 1
                self.failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ GAGAL - Error: {str(e)}")
            self.tests_failed += 1
            self.failures.append(f"{name}: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all entity isolation tests"""
        print("=" * 80)
        print("BACKEND API TEST - FASE E-0 ENTITY ISOLATION")
        print("=" * 80)

        # Login all users
        print("\n" + "=" * 80)
        print("FASE 1: LOGIN SEMUA AKUN")
        print("=" * 80)
        
        users = [
            ("admin@kainnusantara.id", "demo12345"),
            ("sales@kainnusantara.id", "demo12345"),
            ("sales3@kainnusantara.id", "demo12345"),
            ("warehouse@kainnusantara.id", "demo12345"),
        ]
        
        for email, password in users:
            self.login(email, password)

        # L7 - Audit logs (only admin can access)
        print("\n" + "=" * 80)
        print("FASE 2: L7 - JEJAK AUDIT (hanya admin)")
        print("=" * 80)
        
        self.test_api(
            "L7.1 - Sales tidak boleh akses audit logs",
            "sales@kainnusantara.id",
            "GET",
            "/api/audit-logs",
            403
        )
        
        self.test_api(
            "L7.2 - Warehouse tidak boleh akses audit logs",
            "warehouse@kainnusantara.id",
            "GET",
            "/api/audit-logs",
            403
        )
        
        self.test_api(
            "L7.3 - Admin boleh akses audit logs",
            "admin@kainnusantara.id",
            "GET",
            "/api/audit-logs",
            200
        )

        # L9 - AR Aging per entity
        print("\n" + "=" * 80)
        print("FASE 3: L9 - LAPORAN PIUTANG PER ENTITAS")
        print("=" * 80)
        
        def check_ar_aging_ksc(data):
            entity_id = data.get("entity_id")
            entity_name = data.get("entity_name")
            print(f"   AR Aging KSC - entity_id: {entity_id}, entity_name: {entity_name}")
            return entity_id == "ent_ksc" and entity_name is not None
        
        def check_ar_aging_kanda(data):
            entity_id = data.get("entity_id")
            entity_name = data.get("entity_name")
            print(f"   AR Aging Kanda - entity_id: {entity_id}, entity_name: {entity_name}")
            return entity_id == "ent_kanda" and entity_name is not None
        
        self.test_api(
            "L9.1 - AR Aging untuk KSC",
            "admin@kainnusantara.id",
            "GET",
            "/api/ar/aging",
            200,
            headers={"X-Entity-Id": "ent_ksc"},
            check_fn=check_ar_aging_ksc
        )
        
        self.test_api(
            "L9.2 - AR Aging untuk Kanda",
            "admin@kainnusantara.id",
            "GET",
            "/api/ar/aging",
            200,
            headers={"X-Entity-Id": "ent_kanda"},
            check_fn=check_ar_aging_kanda
        )

        # L10 - Settings effective per entity
        print("\n" + "=" * 80)
        print("FASE 4: L10 - PENGATURAN EFEKTIF PER ENTITAS")
        print("=" * 80)
        
        def check_settings_kanda(data):
            is_pkp = data.get("is_pkp")
            ppn = data.get("ppn")
            print(f"   Settings Kanda - is_pkp: {is_pkp}, ppn: {ppn}")
            # Kanda is non-PKP, so is_pkp should be false and ppn should be 0
            return is_pkp == False and ppn == 0
        
        self.test_api(
            "L10.1 - Settings untuk Kanda (non-PKP)",
            "admin@kainnusantara.id",
            "GET",
            "/api/settings/effective?entity_id=ent_kanda",
            200,
            check_fn=check_settings_kanda
        )

        # L21 - Preview allocation (CRITICAL - sales should only see own entity stock)
        print("\n" + "=" * 80)
        print("FASE 5: L21 - PRATINJAU ALOKASI (KRITIS)")
        print("=" * 80)
        
        # Sales3 (Kanda) should NOT be able to force entity_id=ent_ksc
        self.test_api(
            "L21.1 - Sales3 tidak boleh pratinjau stok KSC",
            "sales3@kainnusantara.id",
            "POST",
            "/api/sales-orders/preview-allocation",
            403,
            data={"entity_id": "ent_ksc", "items": [{"product_id": "BTK-MEGA-001", "qty": 10}]}
        )

        # General isolation - sales3 should not see KSC data
        print("\n" + "=" * 80)
        print("FASE 6: ISOLASI UMUM - SALES3 TIDAK LIHAT DATA KSC")
        print("=" * 80)
        
        def check_sales_orders_kanda(data):
            items = data if isinstance(data, list) else data.get("items", [])
            print(f"   Sales3 melihat {len(items)} pesanan")
            # Sales3 should only see 1 SO (SO-0002 from Kanda)
            # Should NOT see KSC orders like SO-0007, SO-0005
            for item in items:
                order_num = item.get("order_number", "")
                entity_id = item.get("entity_id", "")
                if order_num in ["SO-0007", "SO-0005"] or entity_id == "ent_ksc":
                    print(f"   ❌ BOCOR: Sales3 melihat pesanan KSC: {order_num}")
                    return False
            return True
        
        self.test_api(
            "ISOLASI.1 - Sales3 hanya lihat pesanan Kanda",
            "sales3@kainnusantara.id",
            "GET",
            "/api/sales-orders",
            200,
            headers={"X-Entity-Id": "ent_kanda"},
            check_fn=check_sales_orders_kanda
        )
        
        def check_notifications_kanda(data):
            items = data if isinstance(data, list) else data.get("items", [])
            print(f"   Sales3 melihat {len(items)} notifikasi")
            # Sales3 should NOT see KSC notifications
            for item in items:
                entity_id = item.get("entity_id", "")
                message = item.get("message", "")
                if entity_id == "ent_ksc" or "SO-0007" in message or "SO-0005" in message:
                    print(f"   ❌ BOCOR: Sales3 melihat notifikasi KSC")
                    return False
            return True
        
        self.test_api(
            "ISOLASI.2 - Sales3 tidak lihat notifikasi KSC",
            "sales3@kainnusantara.id",
            "GET",
            "/api/notifications",
            200,
            headers={"X-Entity-Id": "ent_kanda"},
            check_fn=check_notifications_kanda
        )

        # Print summary
        print("\n" + "=" * 80)
        print("RINGKASAN HASIL TES")
        print("=" * 80)
        print(f"Total tes: {self.tests_run}")
        print(f"✅ Lulus: {self.tests_passed}")
        print(f"❌ Gagal: {self.tests_failed}")
        
        if self.failures:
            print("\n❌ DAFTAR KEGAGALAN:")
            for i, failure in enumerate(self.failures, 1):
                print(f"   {i}. {failure}")
        
        print("=" * 80)
        
        return 0 if self.tests_failed == 0 else 1

def main():
    tester = EntityIsolationTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
