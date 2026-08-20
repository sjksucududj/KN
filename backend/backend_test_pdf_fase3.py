"""
Backend Test — PDF Template Designer (Fase 3)
Tests all PDF endpoints: doc-types, sample, templates, branding, preview, render + RBAC.
"""
import requests
import sys
from typing import Dict, Any

BASE_URL = "https://static-bundle-2.preview.emergentagent.com"

class PdfTemplateTest:
    def __init__(self):
        self.admin_token = None
        self.sales_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failures = []

    def log(self, msg: str, status: str = "info"):
        prefix = {"info": "ℹ️", "pass": "✅", "fail": "❌", "warn": "⚠️"}
        print(f"{prefix.get(status, 'ℹ️')} {msg}")

    def test(self, name: str, method: str, endpoint: str, expected_status: int,
             token: str = None, data: Dict = None, params: Dict = None) -> tuple[bool, Any]:
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self.tests_run += 1
        self.log(f"Testing {name}...", "info")

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, params=params, timeout=10)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"PASS — {name} (status: {response.status_code})", "pass")
            else:
                self.log(f"FAIL — {name} (expected {expected_status}, got {response.status_code})", "fail")
                self.log(f"Response: {response.text[:200]}", "warn")
                self.failures.append(f"{name}: expected {expected_status}, got {response.status_code}")

            try:
                return success, response.json() if response.text else {}
            except Exception:
                return success, response.text

        except Exception as e:
            self.log(f"FAIL — {name} (error: {str(e)})", "fail")
            self.failures.append(f"{name}: {str(e)}")
            return False, {}

    def login(self, email: str, password: str) -> str:
        """Login and return token"""
        self.log(f"Logging in as {email}...", "info")
        success, response = self.test(
            f"Login {email}",
            "POST",
            "/api/auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and "token" in response:
            self.log(f"Login successful, token: {response['token'][:20]}...", "pass")
            return response["token"]
        self.log(f"Login failed for {email}", "fail")
        return None

    def run_all_tests(self):
        """Run all PDF template tests"""
        self.log("=" * 60, "info")
        self.log("PDF TEMPLATE DESIGNER — BACKEND TEST (Fase 3)", "info")
        self.log("=" * 60, "info")

        # ── 1. Login ─────────────────────────────────────────────────────────
        self.log("\n[1] LOGIN", "info")
        self.admin_token = self.login("admin@kainnusantara.id", "demo12345")
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")

        if not self.admin_token:
            self.log("Admin login failed, cannot continue", "fail")
            return 1

        # ── 2. GET /api/pdf/doc-types (admin) ───────────────────────────────
        self.log("\n[2] GET /api/pdf/doc-types (admin)", "info")
        success, doc_types = self.test(
            "GET doc-types (admin)",
            "GET",
            "/api/pdf/doc-types",
            200,
            token=self.admin_token
        )
        if success and isinstance(doc_types, list) and len(doc_types) > 0:
            self.log(f"Found {len(doc_types)} doc types", "pass")
            # Check if sales_order exists
            so_found = any(d.get("doc_type") == "sales_order" for d in doc_types)
            if so_found:
                self.log("sales_order doc type found", "pass")
            else:
                self.log("sales_order doc type NOT found", "fail")
                self.failures.append("sales_order not in doc-types")
        else:
            self.log("doc-types response invalid", "fail")

        # ── 3. GET /api/pdf/sample/sales_order?entity_id=ent_ksc ────────────
        self.log("\n[3] GET /api/pdf/sample/sales_order?entity_id=ent_ksc", "info")
        success, sample = self.test(
            "GET sample sales_order",
            "GET",
            "/api/pdf/sample/sales_order",
            200,
            token=self.admin_token,
            params={"entity_id": "ent_ksc"}
        )
        source_id = None
        if success and isinstance(sample, dict):
            source_id = sample.get("source_id")
            entity_id = sample.get("entity_id")
            number = sample.get("number")
            self.log(f"Sample: source_id={source_id}, entity_id={entity_id}, number={number}", "pass")
            if not source_id:
                self.log("No sample sales_order found (source_id is None)", "warn")
        else:
            self.log("sample response invalid", "fail")

        # ── 4. GET /api/pdf/templates/sales_order ───────────────────────────
        self.log("\n[4] GET /api/pdf/templates/sales_order", "info")
        success, template = self.test(
            "GET template sales_order",
            "GET",
            "/api/pdf/templates/sales_order",
            200,
            token=self.admin_token
        )
        if success and isinstance(template, dict):
            config = template.get("config")
            defaults = template.get("defaults")
            if config and defaults:
                self.log(f"Template config keys: {list(config.keys())[:5]}...", "pass")
            else:
                self.log("Template missing config or defaults", "fail")
                self.failures.append("Template missing config/defaults")
        else:
            self.log("template response invalid", "fail")

        # ── 5. PUT /api/pdf/templates/sales_order (save config) ─────────────
        self.log("\n[5] PUT /api/pdf/templates/sales_order (save config)", "info")
        test_config = {
            "paper_size": "A4",
            "orientation": "portrait",
            "margin_top": 16,
            "margin_right": 14,
            "margin_bottom": 16,
            "margin_left": 14,
            "font_family": "'DejaVu Sans'",
            "font_size": 10,
            "color_primary": "#0058CC",
            "color_accent": "#1a1a1a",
            "show_logo": True,
            "show_terbilang": True,
            "watermark_text": "SALINAN",
            "footer_text": "",
            "title_override": "UJI JUDUL",
            "custom_fields": [],
            "signature_slots": [],
            "hidden_fields": [],
        }
        success, saved = self.test(
            "PUT template sales_order",
            "PUT",
            "/api/pdf/templates/sales_order",
            200,
            token=self.admin_token,
            data={"config": test_config}
        )
        if success and isinstance(saved, dict):
            saved_config = saved.get("config", {})
            if saved_config.get("title_override") == "UJI JUDUL" and saved_config.get("watermark_text") == "SALINAN":
                self.log("Config saved correctly (title_override + watermark)", "pass")
            else:
                self.log(f"Config mismatch: title={saved_config.get('title_override')}, watermark={saved_config.get('watermark_text')}", "fail")
                self.failures.append("PUT template config mismatch")
        else:
            self.log("PUT template response invalid", "fail")

        # ── 6. GET /api/pdf/templates/sales_order again (verify persistence) ─
        self.log("\n[6] GET /api/pdf/templates/sales_order (verify persistence)", "info")
        success, template2 = self.test(
            "GET template sales_order (verify)",
            "GET",
            "/api/pdf/templates/sales_order",
            200,
            token=self.admin_token
        )
        if success and isinstance(template2, dict):
            config2 = template2.get("config", {})
            if config2.get("title_override") == "UJI JUDUL" and config2.get("watermark_text") == "SALINAN":
                self.log("Config persisted correctly", "pass")
            else:
                self.log(f"Config NOT persisted: title={config2.get('title_override')}, watermark={config2.get('watermark_text')}", "fail")
                self.failures.append("Template config not persisted")
        else:
            self.log("GET template (verify) response invalid", "fail")

        # ── 7. GET /api/pdf/branding/ent_ksc ────────────────────────────────
        self.log("\n[7] GET /api/pdf/branding/ent_ksc", "info")
        success, branding = self.test(
            "GET branding ent_ksc",
            "GET",
            "/api/pdf/branding/ent_ksc",
            200,
            token=self.admin_token
        )
        if success and isinstance(branding, dict):
            self.log(f"Branding: company_name={branding.get('company_name')}, address={branding.get('address')[:30] if branding.get('address') else 'N/A'}...", "pass")
        else:
            self.log("branding response invalid", "fail")

        # ── 8. PUT /api/pdf/branding/ent_ksc (save branding) ────────────────
        self.log("\n[8] PUT /api/pdf/branding/ent_ksc (save branding)", "info")
        test_branding = {
            "company_name": "PT Uji Coba",
            "address": "Jl. Test",
            "phone": "021",
            "npwp": "00.000",
            "logo_b64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCA",
        }
        success, saved_brand = self.test(
            "PUT branding ent_ksc",
            "PUT",
            "/api/pdf/branding/ent_ksc",
            200,
            token=self.admin_token,
            data=test_branding
        )
        if success and isinstance(saved_brand, dict):
            if saved_brand.get("company_name") == "PT Uji Coba" and saved_brand.get("phone") == "021":
                self.log("Branding saved correctly", "pass")
            else:
                self.log(f"Branding mismatch: company={saved_brand.get('company_name')}, phone={saved_brand.get('phone')}", "fail")
                self.failures.append("PUT branding mismatch")
        else:
            self.log("PUT branding response invalid", "fail")

        # ── 9. GET /api/pdf/branding/ent_ksc again (verify persistence) ─────
        self.log("\n[9] GET /api/pdf/branding/ent_ksc (verify persistence)", "info")
        success, branding2 = self.test(
            "GET branding ent_ksc (verify)",
            "GET",
            "/api/pdf/branding/ent_ksc",
            200,
            token=self.admin_token
        )
        if success and isinstance(branding2, dict):
            if branding2.get("company_name") == "PT Uji Coba" and branding2.get("phone") == "021":
                self.log("Branding persisted correctly", "pass")
            else:
                self.log(f"Branding NOT persisted: company={branding2.get('company_name')}, phone={branding2.get('phone')}", "fail")
                self.failures.append("Branding not persisted")
        else:
            self.log("GET branding (verify) response invalid", "fail")

        # ── 10. POST /api/pdf/preview (with config override) ────────────────
        self.log("\n[10] POST /api/pdf/preview (with config override)", "info")
        if source_id:
            preview_config = {
                "title_override": "PRATINJAU UJI",
                "watermark_text": "DRAFT",
            }
            success, preview_html = self.test(
                "POST preview",
                "POST",
                "/api/pdf/preview",
                200,
                token=self.admin_token,
                data={
                    "doc_type": "sales_order",
                    "source_id": source_id,
                    "entity_id": "ent_ksc",
                    "config": preview_config,
                }
            )
            if success and isinstance(preview_html, str):
                if "PRATINJAU UJI" in preview_html and "DRAFT" in preview_html:
                    self.log("Preview HTML contains title_override and watermark", "pass")
                else:
                    self.log(f"Preview HTML missing expected text (len={len(preview_html)})", "fail")
                    self.failures.append("Preview HTML missing title_override or watermark")
            else:
                self.log("Preview response invalid", "fail")
        else:
            self.log("Skipping preview test (no source_id)", "warn")

        # ── 11. GET /api/pdf/render/sales_order/{id}?format=pdf ─────────────
        self.log("\n[11] GET /api/pdf/render/sales_order/{id}?format=pdf", "info")
        if source_id:
            success, pdf_data = self.test(
                "GET render PDF",
                "GET",
                f"/api/pdf/render/sales_order/{source_id}",
                200,
                token=self.admin_token,
                params={"format": "pdf"}
            )
            if success:
                # Check if response starts with %PDF
                if isinstance(pdf_data, str) and pdf_data.startswith("%PDF"):
                    self.log("PDF render successful (starts with %PDF)", "pass")
                elif isinstance(pdf_data, bytes) and pdf_data.startswith(b"%PDF"):
                    self.log("PDF render successful (binary starts with %PDF)", "pass")
                else:
                    self.log(f"PDF render response doesn't start with %PDF (type={type(pdf_data)})", "fail")
                    self.failures.append("PDF render doesn't start with %PDF")
            else:
                self.log("PDF render failed", "fail")
        else:
            self.log("Skipping PDF render test (no source_id)", "warn")

        # ── 12. GET /api/pdf/render/sales_order/{id}?format=html ────────────
        self.log("\n[12] GET /api/pdf/render/sales_order/{id}?format=html", "info")
        if source_id:
            success, html_data = self.test(
                "GET render HTML",
                "GET",
                f"/api/pdf/render/sales_order/{source_id}",
                200,
                token=self.admin_token,
                params={"format": "html"}
            )
            if success and isinstance(html_data, str):
                self.log(f"HTML render successful (len={len(html_data)})", "pass")
            else:
                self.log("HTML render response invalid", "fail")
        else:
            self.log("Skipping HTML render test (no source_id)", "warn")

        # ── 13. Resolver fix — check for 'recipient_name' leak ──────────────
        self.log("\n[13] Resolver fix — check HTML doesn't contain 'recipient_name' string", "info")
        if source_id:
            success, html_data = self.test(
                "GET render HTML (resolver check)",
                "GET",
                f"/api/pdf/render/sales_order/{source_id}",
                200,
                token=self.admin_token,
                params={"format": "html"}
            )
            if success and isinstance(html_data, str):
                if "recipient_name" in html_data:
                    self.log("FAIL — HTML contains 'recipient_name' (resolver leak)", "fail")
                    self.failures.append("HTML contains 'recipient_name' string (resolver leak)")
                else:
                    self.log("PASS — HTML does NOT contain 'recipient_name'", "pass")
                
                # Check for formatted address
                if "Jl." in html_data or "Jakarta" in html_data:
                    self.log("PASS — HTML contains formatted address (Jl./Jakarta)", "pass")
                else:
                    self.log("WARN — HTML may not contain formatted address", "warn")
            else:
                self.log("HTML render response invalid", "fail")
        else:
            self.log("Skipping resolver check (no source_id)", "warn")

        # ── 14. RBAC: sales user should get 403 on template/branding/preview ─
        self.log("\n[14] RBAC: sales user permissions", "info")
        if self.sales_token:
            # sales should get 403 on GET /api/pdf/templates/sales_order
            success, _ = self.test(
                "GET template (sales) — expect 403",
                "GET",
                "/api/pdf/templates/sales_order",
                403,
                token=self.sales_token
            )
            
            # sales should get 403 on GET /api/pdf/branding/ent_ksc
            success, _ = self.test(
                "GET branding (sales) — expect 403",
                "GET",
                "/api/pdf/branding/ent_ksc",
                403,
                token=self.sales_token
            )
            
            # sales should get 403 on POST /api/pdf/preview
            if source_id:
                success, _ = self.test(
                    "POST preview (sales) — expect 403",
                    "POST",
                    "/api/pdf/preview",
                    403,
                    token=self.sales_token,
                    data={
                        "doc_type": "sales_order",
                        "source_id": source_id,
                        "entity_id": "ent_ksc",
                        "config": {},
                    }
                )
            
            # sales SHOULD be able to render PDF (has document:print)
            if source_id:
                success, _ = self.test(
                    "GET render PDF (sales) — expect 200",
                    "GET",
                    f"/api/pdf/render/sales_order/{source_id}",
                    200,
                    token=self.sales_token,
                    params={"format": "pdf"}
                )
        else:
            self.log("Skipping RBAC tests (no sales token)", "warn")

        # ── SUMMARY ──────────────────────────────────────────────────────────
        self.log("\n" + "=" * 60, "info")
        self.log(f"TESTS PASSED: {self.tests_passed}/{self.tests_run}", "info")
        self.log("=" * 60, "info")

        if self.failures:
            self.log("\nFAILURES:", "fail")
            for f in self.failures:
                self.log(f"  • {f}", "fail")

        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = PdfTemplateTest()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
