"""F0-C/D/E/F backend testing — Multi-Entity (Model 1 silo) full validation.

Mengikuti review request iteration_52:
  • F0-C  : isolasi operasional list endpoints (wms_tasks, shipments, inventory/*).
  • F0-D  : penomoran per-entitas (SO/PO) end-to-end via API.
  • F0-E  : buku GL terpisah per entitas + PKP per-entitas.
  • F0-F  : provisioning entitas baru via POST /api/entities (idempotent, 409, slug doc_prefix).
  • Regresi: 10 endpoint komersial fase F0-B tetap 200.
"""
import os
import time
import pytest
import requests

def _load_base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not url:
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
    assert url, "REACT_APP_BACKEND_URL must be configured"
    return url.rstrip("/")


BASE_URL = _load_base_url()
API = f"{BASE_URL}/api"

ADMIN = ("admin@kainnusantara.id", "demo12345")
SALES3 = ("sales3@kainnusantara.id", "demo12345")  # home=ent_kanda

ENT_KSC = "ent_ksc"
ENT_KANDA = "ent_kanda"


# ─── helpers ─────────────────────────────────────────────────────────────────

def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def sales3_token():
    return _login(*SALES3)


def H(token: str, entity_id: str = None):
    h = {"Authorization": f"Bearer {token}"}
    if entity_id:
        h["X-Entity-Id"] = entity_id
    return h


# ─── F0-C — Isolasi Operasional ─────────────────────────────────────────────

OPS_ENDPOINTS = [
    "/wms/tasks",
    "/shipments",
    "/inventory/rolls",
    "/inventory/balances",
    "/inventory/movements",
]


class TestF0C_OperationalIsolation:
    """List operasional ter-scope (default=home, X-Entity-Id, view-all)."""

    @pytest.mark.parametrize("endpoint", OPS_ENDPOINTS)
    def test_default_scope_home(self, admin_token, endpoint):
        r = requests.get(f"{API}{endpoint}", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, f"{endpoint} default: {r.status_code} {r.text[:200]}"
        data = r.json()
        rows = data if isinstance(data, list) else data.get("items", data.get("rows", []))
        assert isinstance(rows, list)
        # default (admin home=ent_ksc) — semua row harus ent_ksc atau "all" (kas/bank n/a di ops)
        for row in rows[:20]:
            eid = row.get("entity_id") or row.get("ownerEntity") or ENT_KSC
            assert eid in (ENT_KSC, ""), f"{endpoint}: row entity={eid} bocor pada default home ent_ksc"

    @pytest.mark.parametrize("endpoint", OPS_ENDPOINTS)
    def test_header_ent_kanda(self, admin_token, endpoint):
        r = requests.get(f"{API}{endpoint}", headers=H(admin_token, ENT_KANDA), timeout=20)
        assert r.status_code == 200, f"{endpoint} kanda: {r.status_code} {r.text[:200]}"
        data = r.json()
        rows = data if isinstance(data, list) else data.get("items", data.get("rows", []))
        for row in rows[:20]:
            eid = row.get("entity_id") or row.get("ownerEntity")
            assert eid == ENT_KANDA, f"{endpoint}: row entity={eid} bocor pada X-Entity-Id=ent_kanda"

    @pytest.mark.parametrize("endpoint", OPS_ENDPOINTS)
    def test_view_all_superset(self, admin_token, endpoint):
        r_home = requests.get(f"{API}{endpoint}", headers=H(admin_token), timeout=20)
        r_kan = requests.get(f"{API}{endpoint}", headers=H(admin_token, ENT_KANDA), timeout=20)
        r_all = requests.get(f"{API}{endpoint}", headers=H(admin_token, "all"), timeout=20)
        assert r_home.status_code == r_kan.status_code == r_all.status_code == 200

        def _count(r):
            d = r.json()
            return len(d if isinstance(d, list) else d.get("items", d.get("rows", [])))

        c_home, c_kan, c_all = _count(r_home), _count(r_kan), _count(r_all)
        # all harus >= max(home, kanda) dan biasanya == home+kanda (kecuali grup record)
        assert c_all >= max(c_home, c_kan), f"{endpoint}: count all={c_all} < max(home={c_home},kanda={c_kan})"

    def test_wms_tasks_expected_counts(self, admin_token):
        """Verifikasi count yang diharapkan (per problem statement)."""
        rh = requests.get(f"{API}/wms/tasks", headers=H(admin_token), timeout=20).json()
        rk = requests.get(f"{API}/wms/tasks", headers=H(admin_token, ENT_KANDA), timeout=20).json()
        ra = requests.get(f"{API}/wms/tasks", headers=H(admin_token, "all"), timeout=20).json()
        # Counts: home ent_ksc ≈ 16, kanda ≈ 4, all ≈ 20
        print(f"wms/tasks counts → home={len(rh)} kanda={len(rk)} all={len(ra)}")
        assert len(ra) == len(rh) + len(rk), f"all({len(ra)}) ≠ home({len(rh)})+kanda({len(rk)})"

    def test_shipments_expected_counts(self, admin_token):
        rh = requests.get(f"{API}/shipments", headers=H(admin_token), timeout=20).json()
        rk = requests.get(f"{API}/shipments", headers=H(admin_token, ENT_KANDA), timeout=20).json()
        ra = requests.get(f"{API}/shipments", headers=H(admin_token, "all"), timeout=20).json()
        print(f"shipments counts → home={len(rh)} kanda={len(rk)} all={len(ra)}")
        assert len(ra) == len(rh) + len(rk)


# ─── F0-D — Penomoran per-entitas (SO/PO) ────────────────────────────────────

class TestF0D_NumberingPerEntity:

    @pytest.fixture(scope="class")
    def customers_by_entity(self, admin_token):
        r = requests.get(f"{API}/customers?entity_id=all", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        custs = r.json()
        by = {ENT_KSC: None, ENT_KANDA: None}
        for c in custs:
            eid = c.get("entity_id")
            if eid in by and by[eid] is None and c.get("addresses"):
                by[eid] = c
        assert by[ENT_KSC] and by[ENT_KANDA], f"customer per entitas tidak lengkap: {by}"
        return by

    @pytest.fixture(scope="class")
    def some_product(self, admin_token):
        r = requests.get(f"{API}/products", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        prods = r.json()
        assert prods, "tidak ada produk"
        # pilih produk yang punya harga >0
        for p in prods:
            if float(p.get("price", 0) or 0) > 0:
                return p
        return prods[0]

    def _create_so(self, token, customer, product, entity_id=None):
        payload = {
            "customer_id": customer["id"],
            "shipping_address_id": customer["addresses"][0]["id"],
            "items": [{
                "product_id": product["id"],
                "quantity": 1,
                "unit": product.get("base_unit", "meter"),
            }],
            "sales_name": "F0D Tester",
            "entity_id": entity_id or "",
            "allow_backorder": True,  # F0-D: fokus tes nomor SO; izinkan backorder agar tidak terkunci stok.
        }
        r = requests.post(f"{API}/sales-orders", headers=H(token), json=payload, timeout=30)
        return r

    def test_so_ksc_prefix(self, admin_token, customers_by_entity, some_product):
        cust = customers_by_entity[ENT_KSC]
        r = self._create_so(admin_token, cust, some_product, ENT_KSC)
        assert r.status_code in (200, 201), f"create SO ksc: {r.status_code} {r.text[:300]}"
        so = r.json()
        num = so.get("number", "")
        assert num.startswith("KSC/SO-"), f"SO number ksc tidak benar: {num}"
        # store for sequence test
        pytest.so_ksc_first = num

    def test_so_ksc_sequence(self, admin_token, customers_by_entity, some_product):
        cust = customers_by_entity[ENT_KSC]
        r = self._create_so(admin_token, cust, some_product, ENT_KSC)
        assert r.status_code in (200, 201)
        num2 = r.json().get("number", "")
        assert num2.startswith("KSC/SO-")
        n1 = int(getattr(pytest, "so_ksc_first", "KSC/SO-00000").split("-")[-1])
        n2 = int(num2.split("-")[-1])
        assert n2 == n1 + 1, f"sequence ksc tidak berurutan: {n1} → {n2}"

    def test_so_kanda_prefix(self, admin_token, customers_by_entity, some_product):
        cust = customers_by_entity[ENT_KANDA]
        r = self._create_so(admin_token, cust, some_product, ENT_KANDA)
        assert r.status_code in (200, 201), f"create SO kanda: {r.status_code} {r.text[:300]}"
        so = r.json()
        num = so.get("number", "")
        assert num.startswith("KANDA/SO-"), f"SO number kanda tidak benar: {num}"
        pytest.so_kanda_num = num

    def test_so_sequences_independent(self, admin_token, customers_by_entity, some_product):
        """Buat SO ent_ksc, lalu ent_kanda, lalu ent_ksc lagi — sequence per entitas mandiri."""
        ksc = customers_by_entity[ENT_KSC]
        kan = customers_by_entity[ENT_KANDA]
        r1 = self._create_so(admin_token, ksc, some_product, ENT_KSC)
        r2 = self._create_so(admin_token, kan, some_product, ENT_KANDA)
        r3 = self._create_so(admin_token, ksc, some_product, ENT_KSC)
        for r in (r1, r2, r3):
            assert r.status_code in (200, 201), f"create SO: {r.status_code} {r.text[:200]}"
        n1 = int(r1.json()["number"].split("-")[-1])
        n3 = int(r3.json()["number"].split("-")[-1])
        assert n3 == n1 + 1, f"SO ent_ksc tidak menerus saat diselang ent_kanda: {n1}, {n3}"
        assert r2.json()["number"].startswith("KANDA/SO-")

    def test_po_ksc_prefix(self, admin_token, some_product):
        # Ambil warehouse pertama
        wr = requests.get(f"{API}/warehouses", headers=H(admin_token), timeout=20)
        assert wr.status_code == 200
        wh_list = wr.json()
        assert wh_list, "tidak ada warehouse"
        wh_id = wh_list[0]["id"]
        payload = {
            "supplier_name": "TEST F0D Supplier",
            "warehouse_id": wh_id,
            "items": [{"product_id": some_product["id"], "quantity": 5,
                       "unit": some_product.get("base_unit", "meter"), "price": 10000}],
            "notes": "F0D test PO",
        }
        r = requests.post(f"{API}/purchase-orders", headers=H(admin_token, ENT_KSC), json=payload, timeout=30)
        assert r.status_code in (200, 201), f"create PO ksc: {r.status_code} {r.text[:300]}"
        num = r.json().get("po_number", "")
        assert num.startswith("KSC/PO-"), f"PO number ksc salah: {num}"

    def test_po_kanda_prefix(self, admin_token, some_product):
        wr = requests.get(f"{API}/warehouses", headers=H(admin_token), timeout=20)
        wh_id = wr.json()[0]["id"]
        payload = {
            "supplier_name": "TEST F0D Supplier Kanda",
            "warehouse_id": wh_id,
            "items": [{"product_id": some_product["id"], "quantity": 5,
                       "unit": some_product.get("base_unit", "meter"), "price": 10000}],
            "notes": "F0D test PO kanda",
        }
        r = requests.post(f"{API}/purchase-orders", headers=H(admin_token, ENT_KANDA), json=payload, timeout=30)
        assert r.status_code in (200, 201), f"create PO kanda: {r.status_code} {r.text[:300]}"
        num = r.json().get("po_number", "")
        assert num.startswith("KANDA/PO-"), f"PO number kanda salah: {num}"


# ─── F0-E — Buku GL terpisah + PKP per entitas ──────────────────────────────

class TestF0E_GLSeparation:

    def test_tb_ksc_balanced(self, admin_token):
        r = requests.get(f"{API}/gl/trial-balance?entity_id=ent_ksc", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, f"TB ksc: {r.status_code} {r.text[:200]}"
        tb = r.json()
        assert tb.get("balanced") is True, f"TB ksc tidak balanced: {tb}"
        pytest.tb_ksc = float(tb.get("total_debit", 0))

    def test_tb_kanda_balanced(self, admin_token):
        r = requests.get(f"{API}/gl/trial-balance?entity_id=ent_kanda", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        tb = r.json()
        assert tb.get("balanced") is True, f"TB kanda tidak balanced: {tb}"
        pytest.tb_kanda = float(tb.get("total_debit", 0))

    def test_tb_distinct_totals(self):
        assert pytest.tb_ksc != pytest.tb_kanda, \
            f"total_debit ent_ksc({pytest.tb_ksc}) == ent_kanda({pytest.tb_kanda}) — mestinya berbeda (buku terpisah)"

    def test_tb_all_equals_sum(self, admin_token):
        r = requests.get(f"{API}/gl/trial-balance?entity_id=all", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        tb = r.json()
        assert tb.get("balanced") is True
        total_all = float(tb.get("total_debit", 0))
        expected = pytest.tb_ksc + pytest.tb_kanda
        # Toleransi pembulatan kecil
        assert abs(total_all - expected) < 1.0, \
            f"TB all({total_all}) ≠ ksc({pytest.tb_ksc}) + kanda({pytest.tb_kanda}) = {expected}"

    def test_journal_kanda_scoped(self, admin_token):
        r = requests.get(f"{API}/gl/journal?entity_id=ent_kanda&limit=200", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, f"journal kanda: {r.status_code} {r.text[:200]}"
        data = r.json()
        rows = data if isinstance(data, list) else data.get("items", data.get("entries", []))
        # Semua entry harus ent_kanda
        leaked = [x for x in rows if x.get("entity_id") not in (ENT_KANDA, None, "")]
        # entity_id None bisa berarti legacy; tapi yang non-kanda non-null jelas leak
        leaked_strict = [x for x in rows if x.get("entity_id") and x.get("entity_id") != ENT_KANDA]
        assert not leaked_strict, f"journal_entries leak non-kanda: {len(leaked_strict)} rows, sample={leaked_strict[0] if leaked_strict else {}}"

    def test_gl_summary_scoped(self, admin_token):
        r = requests.get(f"{API}/gl/summary?entity_id=ent_kanda", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, f"gl/summary kanda: {r.status_code} {r.text[:200]}"


class TestF0E_PKPPerEntity:
    """SO ent_ksc kena PPN 11%; SO ent_kanda PPN 0 (non-PKP)."""

    @pytest.fixture(scope="class")
    def customers_by_entity(self, admin_token):
        r = requests.get(f"{API}/customers?entity_id=all", headers=H(admin_token), timeout=20)
        custs = r.json()
        by = {ENT_KSC: None, ENT_KANDA: None}
        for c in custs:
            eid = c.get("entity_id")
            if eid in by and by[eid] is None and c.get("addresses"):
                by[eid] = c
        return by

    @pytest.fixture(scope="class")
    def some_product(self, admin_token):
        r = requests.get(f"{API}/products", headers=H(admin_token), timeout=20)
        for p in r.json():
            if float(p.get("price", 0) or 0) > 0:
                return p
        return r.json()[0]

    def _create(self, token, cust, prod, entity_id):
        payload = {
            "customer_id": cust["id"],
            "shipping_address_id": cust["addresses"][0]["id"],
            "items": [{"product_id": prod["id"], "quantity": 2,
                       "unit": prod.get("base_unit", "meter")}],
            "sales_name": "F0E Tester",
            "entity_id": entity_id,
            "allow_backorder": True,
        }
        return requests.post(f"{API}/sales-orders", headers=H(token), json=payload, timeout=30)

    def test_so_ksc_kena_ppn(self, admin_token, customers_by_entity, some_product):
        r = self._create(admin_token, customers_by_entity[ENT_KSC], some_product, ENT_KSC)
        assert r.status_code in (200, 201), r.text[:300]
        so = r.json()
        assert float(so.get("ppn_amount", 0)) > 0, f"SO ksc ppn_amount=0; should >0. SO: {so.get('number')}"
        assert so.get("is_pkp") is True, f"SO ksc is_pkp={so.get('is_pkp')}"
        assert float(so.get("ppn_rate", 0)) == 11.0, f"ppn_rate ksc != 11: {so.get('ppn_rate')}"

    def test_so_kanda_tanpa_ppn(self, admin_token, customers_by_entity, some_product):
        r = self._create(admin_token, customers_by_entity[ENT_KANDA], some_product, ENT_KANDA)
        assert r.status_code in (200, 201), r.text[:300]
        so = r.json()
        assert float(so.get("ppn_amount", 0)) == 0.0, f"SO kanda ppn_amount harusnya 0: {so.get('ppn_amount')}"
        assert so.get("is_pkp") is False, f"SO kanda is_pkp={so.get('is_pkp')}"
        assert float(so.get("ppn_rate", 0)) == 0.0, f"ppn_rate kanda != 0: {so.get('ppn_rate')}"


# ─── F0-F — Provisioning entitas baru ───────────────────────────────────────

class TestF0F_Provisioning:

    @pytest.fixture(scope="class")
    def unique_short(self):
        # short_name harus menghasilkan slug 6-char yang unik (slug max 6 char dari _slug_prefix)
        return f"F{int(time.time()) % 100000}"

    def test_create_entity_auto_prefix(self, admin_token, unique_short):
        payload = {
            "legal_name": f"PT Uji Provisioning {unique_short}",
            "short_name": unique_short,
            "default_tax_mode": "non_ppn",
        }
        r = requests.post(f"{API}/entities", headers=H(admin_token), json=payload, timeout=20)
        assert r.status_code in (200, 201), f"create entity: {r.status_code} {r.text[:300]}"
        ent = r.json()
        assert ent.get("id"), "id missing"
        assert ent.get("doc_prefix"), "doc_prefix missing"
        # auto-generated harus uppercased alphanumeric dari short_name (slug max 6 char per _slug_prefix)
        slug_full = "".join(ch for ch in unique_short if ch.isalnum()).upper()
        expected_prefix = slug_full[:6]
        assert ent["doc_prefix"] == expected_prefix, f"doc_prefix '{ent['doc_prefix']}' ≠ slug6 '{expected_prefix}'"
        prov = ent.get("provisioning") or {}
        assert prov.get("numbering_scheme") == "per_entity_prefix"
        assert prov.get("is_pkp") is False
        assert prov.get("coa_shared") is True
        pytest.f0f_short = unique_short
        pytest.f0f_id = ent["id"]

    def test_create_entity_409_duplicate(self, admin_token):
        short = getattr(pytest, "f0f_short", None)
        assert short, "prev test failed"
        r = requests.post(f"{API}/entities", headers=H(admin_token), json={
            "legal_name": "Duplicate Attempt",
            "short_name": short,
            "default_tax_mode": "non_ppn",
        }, timeout=20)
        assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text[:200]}"

    def test_new_entity_in_list(self, admin_token):
        new_id = getattr(pytest, "f0f_id", None)
        assert new_id, "prev test failed"
        r = requests.get(f"{API}/entities", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        ents = r.json()
        ids = [e["id"] for e in ents]
        assert new_id in ids, f"entitas baru {new_id} tidak muncul di list"


# ─── Regresi: 10 endpoint komersial tetap 200 ───────────────────────────────

REGRESSION_ENDPOINTS = [
    "/purchase-orders", "/vendor-bills", "/suppliers", "/ar-receipts",
    "/cash-transactions", "/bank-accounts", "/tax-invoices",
    "/sales-returns", "/special-orders", "/price-approvals",
]


class TestRegression:
    @pytest.mark.parametrize("ep", REGRESSION_ENDPOINTS)
    def test_default_home(self, admin_token, ep):
        r = requests.get(f"{API}{ep}", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, f"{ep} default: {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("ep", REGRESSION_ENDPOINTS)
    def test_kanda_scope(self, admin_token, ep):
        r = requests.get(f"{API}{ep}", headers=H(admin_token, ENT_KANDA), timeout=20)
        assert r.status_code == 200, f"{ep} kanda: {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("ep", REGRESSION_ENDPOINTS)
    def test_view_all(self, admin_token, ep):
        r = requests.get(f"{API}{ep}", headers=H(admin_token, "all"), timeout=20)
        assert r.status_code == 200, f"{ep} all: {r.status_code} {r.text[:200]}"
