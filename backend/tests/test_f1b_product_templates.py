"""F1b — Product Templates & Variants (ADDITIVE/non-destruktif) tests.

Cakupan: create template, generate varian (cartesian + idempoten + subset),
detail/list, assign/detach, delete non-destruktif, integrasi /api/products,
RBAC, regresi (products/sales-orders/pricelist/konsolidasi)."""
import os
import pytest
import requests
from pathlib import Path
from pymongo import MongoClient


def _load_env(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env("/app/frontend/.env")
_load_env("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
assert BASE_URL.startswith("http"), f"REACT_APP_BACKEND_URL invalid: {BASE_URL!r}"

TEST_PREFIX = "TPLTST"  # Prefix SKU yang dipakai test → mudah dibersihkan
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
MGR = {"email": "manager@kainnusantara.id", "password": "demo12345"}
SALES = {"email": "sales@kainnusantara.id", "password": "demo12345"}


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login fail {creds['email']}: {r.text}"
    return r.json()["token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def mgr_token():
    return _login(MGR)


@pytest.fixture(scope="module")
def sales_token():
    return _login(SALES)


@pytest.fixture(scope="module")
def created_template_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_token, created_template_ids):
    yield
    # Hapus template yang dibuat test (otomatis lepas tautan varian)
    for tid in created_template_ids:
        try:
            requests.delete(f"{BASE_URL}/api/product-templates/{tid}",
                            headers=_hdr(admin_token), timeout=15)
        except Exception:
            pass
    # Hapus produk varian ber-SKU prefix test langsung di DB
    try:
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        db.products.delete_many({"sku": {"$regex": f"^{TEST_PREFIX}-"}})
        # Hapus template sisa berdasarkan sku_prefix test
        db.product_templates.delete_many({"sku_prefix": TEST_PREFIX})
        client.close()
    except Exception as e:
        print(f"DB cleanup warn: {e}")


# ─── 1. Create template ─────────────────────────────────────────────────────
def test_create_template_invalid_no_name(admin_token):
    # Empty name → service ValueError → 400. Pydantic enforces field presence (422)
    # so we test empty string which trips business validation.
    r = requests.post(f"{BASE_URL}/api/product-templates", headers=_hdr(admin_token),
                      json={"name": "", "category": "Kain", "base_price": 100000}, timeout=15)
    assert r.status_code == 400, r.text
    # Also verify missing field → 422 (FastAPI/Pydantic default)
    r2 = requests.post(f"{BASE_URL}/api/product-templates", headers=_hdr(admin_token),
                       json={"category": "Kain"}, timeout=15)
    assert r2.status_code in (400, 422), r2.text


def test_create_template_ok(admin_token, created_template_ids):
    payload = {
        "name": "TPL Test Katun",
        "category": "Kain",
        "base_price": 150000,
        "sku_prefix": TEST_PREFIX,
        "axes": [
            {"key": "color", "label": "Warna", "options": [
                {"label": "Merah"}, {"label": "Biru"}, {"label": "Hijau"}]},
            {"key": "grade", "label": "Grade", "options": [
                {"label": "A"}, {"label": "B"}]},
        ],
    }
    r = requests.post(f"{BASE_URL}/api/product-templates", headers=_hdr(admin_token),
                      json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert "id" in body and body["name"] == "TPL Test Katun"
    assert body["sku_prefix"] == TEST_PREFIX
    assert len(body["axes"]) == 2
    # axes ter-normalisasi: tiap option punya code & label
    for ax in body["axes"]:
        for opt in ax["options"]:
            assert opt.get("code") and opt.get("label")
    created_template_ids.append(body["id"])


# ─── 2. Generate varian massal (cartesian + idempoten) ──────────────────────
def test_generate_variants_cartesian(admin_token, created_template_ids):
    assert created_template_ids, "template harus sudah dibuat"
    tid = created_template_ids[0]
    r = requests.post(f"{BASE_URL}/api/product-templates/{tid}/generate-variants",
                      headers=_hdr(admin_token), json={}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    # 3 warna × 2 grade = 6
    assert body["total_combinations"] == 6
    assert body["created"] == 6
    assert body["skipped"] == 0
    assert len(body["variants"]) == 6
    # SKU pattern uppercase
    for v in body["variants"]:
        assert v["sku"].startswith(f"{TEST_PREFIX}-")
        assert v["sku"] == v["sku"].upper()
        assert v["template_id"] == tid
        assert isinstance(v.get("variant_attrs"), dict)
        assert "color" in v["variant_attrs"] and "grade" in v["variant_attrs"]
        assert v["price"] == 150000


def test_generate_variants_idempotent(admin_token, created_template_ids):
    tid = created_template_ids[0]
    r = requests.post(f"{BASE_URL}/api/product-templates/{tid}/generate-variants",
                      headers=_hdr(admin_token), json={}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 0
    assert body["skipped"] == 6
    assert body["total_combinations"] == 6


def test_generate_variants_subset_axes(admin_token, created_template_ids):
    tid = created_template_ids[0]
    # Override axes subset: 1 warna baru × 1 grade existing → 1 kombinasi baru
    payload = {"axes": [
        {"key": "color", "label": "Warna", "options": [{"label": "Kuning"}]},
        {"key": "grade", "label": "Grade", "options": [{"label": "A"}]},
    ]}
    r = requests.post(f"{BASE_URL}/api/product-templates/{tid}/generate-variants",
                      headers=_hdr(admin_token), json=payload, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_combinations"] == 1
    assert body["created"] == 1
    assert body["skipped"] == 0


# ─── 3. Detail & List ───────────────────────────────────────────────────────
def test_get_template_detail(admin_token, created_template_ids):
    tid = created_template_ids[0]
    r = requests.get(f"{BASE_URL}/api/product-templates/{tid}",
                     headers=_hdr(admin_token), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == tid
    assert isinstance(body["variants"], list)
    assert body["variant_count"] == 7  # 6 + 1 (Kuning/A)
    assert body["variant_count"] == len(body["variants"])


def test_list_templates(admin_token, created_template_ids):
    r = requests.get(f"{BASE_URL}/api/product-templates",
                     headers=_hdr(admin_token), timeout=15)
    assert r.status_code == 200
    arr = r.json()
    assert isinstance(arr, list)
    ours = [t for t in arr if t["id"] == created_template_ids[0]]
    assert len(ours) == 1
    assert ours[0]["variant_count"] == 7
    assert "axes" in ours[0]


def test_list_templates_search(admin_token):
    r = requests.get(f"{BASE_URL}/api/product-templates?search=TPL Test Katun",
                     headers=_hdr(admin_token), timeout=15)
    assert r.status_code == 200
    arr = r.json()
    assert any("TPL Test Katun" in t["name"] for t in arr)


# ─── 4. Assign / Detach ─────────────────────────────────────────────────────
def test_assign_and_detach(admin_token, created_template_ids):
    tid = created_template_ids[0]
    # Ambil 1 produk seed existing (bukan varian template kita)
    r = requests.get(f"{BASE_URL}/api/products", headers=_hdr(admin_token), timeout=15)
    assert r.status_code == 200
    all_prods = r.json()
    seed = [p for p in all_prods if not p.get("template_id") and not p["sku"].startswith(TEST_PREFIX)]
    assert seed, "perlu produk seed tanpa template_id"
    pid = seed[0]["id"]
    r2 = requests.post(f"{BASE_URL}/api/product-templates/{tid}/assign",
                       headers=_hdr(admin_token), json={"product_ids": [pid]}, timeout=15)
    assert r2.status_code == 200
    assert r2.json()["assigned"] == 1
    # Verify via products
    r3 = requests.get(f"{BASE_URL}/api/products", headers=_hdr(admin_token), timeout=15)
    p = next(x for x in r3.json() if x["id"] == pid)
    assert p.get("template_id") == tid
    # Detach
    r4 = requests.post(f"{BASE_URL}/api/product-templates/detach",
                       headers=_hdr(admin_token), json={"product_ids": [pid]}, timeout=15)
    assert r4.status_code == 200
    assert r4.json()["detached"] == 1
    r5 = requests.get(f"{BASE_URL}/api/products", headers=_hdr(admin_token), timeout=15)
    p2 = next(x for x in r5.json() if x["id"] == pid)
    assert p2.get("template_id", "") == ""


# ─── 5. Integrasi /api/products ─────────────────────────────────────────────
def test_products_include_template_fields(admin_token, created_template_ids):
    r = requests.get(f"{BASE_URL}/api/products", headers=_hdr(admin_token), timeout=15)
    assert r.status_code == 200
    arr = r.json()
    variants = [p for p in arr if p["sku"].startswith(f"{TEST_PREFIX}-")]
    assert len(variants) >= 6
    for v in variants:
        assert v["template_id"] == created_template_ids[0]
        assert isinstance(v.get("variant_attrs"), dict)


def test_patch_product_template_id(admin_token, created_template_ids):
    # Cari produk seed bebas
    r = requests.get(f"{BASE_URL}/api/products", headers=_hdr(admin_token), timeout=15)
    seed = [p for p in r.json() if not p.get("template_id") and not p["sku"].startswith(TEST_PREFIX)]
    pid = seed[0]["id"]
    tid = created_template_ids[0]
    r2 = requests.patch(f"{BASE_URL}/api/products/{pid}",
                        headers=_hdr(admin_token),
                        json={"data": {"template_id": tid}}, timeout=15)
    assert r2.status_code == 200, r2.text
    # Verify persisted
    r3 = requests.get(f"{BASE_URL}/api/products", headers=_hdr(admin_token), timeout=15)
    p = next(x for x in r3.json() if x["id"] == pid)
    assert p.get("template_id") == tid
    # Cleanup: detach
    requests.post(f"{BASE_URL}/api/product-templates/detach",
                  headers=_hdr(admin_token), json={"product_ids": [pid]}, timeout=15)


# ─── 6. RBAC ────────────────────────────────────────────────────────────────
def test_rbac_sales_cannot_create(sales_token):
    r = requests.post(f"{BASE_URL}/api/product-templates", headers=_hdr(sales_token),
                      json={"name": "Should Fail", "axes": []}, timeout=15)
    assert r.status_code == 403


def test_rbac_manager_cannot_create(mgr_token):
    r = requests.post(f"{BASE_URL}/api/product-templates", headers=_hdr(mgr_token),
                      json={"name": "Should Fail Manager", "axes": []}, timeout=15)
    assert r.status_code == 403


def test_rbac_sales_can_view(sales_token):
    r = requests.get(f"{BASE_URL}/api/product-templates", headers=_hdr(sales_token), timeout=15)
    assert r.status_code == 200


def test_rbac_manager_can_view(mgr_token):
    r = requests.get(f"{BASE_URL}/api/product-templates", headers=_hdr(mgr_token), timeout=15)
    assert r.status_code == 200


def test_rbac_sales_cannot_generate(sales_token, created_template_ids):
    tid = created_template_ids[0]
    r = requests.post(f"{BASE_URL}/api/product-templates/{tid}/generate-variants",
                      headers=_hdr(sales_token), json={}, timeout=15)
    assert r.status_code == 403


def test_rbac_sales_cannot_delete(sales_token, created_template_ids):
    tid = created_template_ids[0]
    r = requests.delete(f"{BASE_URL}/api/product-templates/{tid}",
                        headers=_hdr(sales_token), timeout=15)
    assert r.status_code == 403


# ─── 7. Delete non-destruktif ───────────────────────────────────────────────
def test_delete_template_non_destructive(admin_token, created_template_ids):
    tid = created_template_ids[0]
    # Hitung varian sebelum delete
    r0 = requests.get(f"{BASE_URL}/api/products", headers=_hdr(admin_token), timeout=15)
    vbefore = [p for p in r0.json() if p["sku"].startswith(f"{TEST_PREFIX}-")]
    n_variants = len(vbefore)
    assert n_variants >= 7
    # Delete template
    r = requests.delete(f"{BASE_URL}/api/product-templates/{tid}",
                        headers=_hdr(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["detached_variants"] == n_variants
    # Verify template gone
    r2 = requests.get(f"{BASE_URL}/api/product-templates/{tid}",
                      headers=_hdr(admin_token), timeout=15)
    assert r2.status_code == 404
    # Verify produk varian masih ada
    r3 = requests.get(f"{BASE_URL}/api/products", headers=_hdr(admin_token), timeout=15)
    after = [p for p in r3.json() if p["sku"].startswith(f"{TEST_PREFIX}-")]
    assert len(after) == n_variants
    # template_id kosong di semua varian
    for p in after:
        assert p.get("template_id", "") == ""
    # Hapus dari tracking (sudah dihapus)
    created_template_ids.remove(tid)


# ─── 8. Regresi endpoints lain tetap 200 ────────────────────────────────────
def test_regression_endpoints(admin_token):
    hdr = _hdr(admin_token)
    for path in ["/api/products", "/api/sales-orders", "/api/pricelist",
                 "/api/gl/consolidation"]:
        r = requests.get(f"{BASE_URL}{path}", headers=hdr, timeout=20)
        assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"


def test_products_seed_count_preserved(admin_token):
    """Setelah delete template (varian terlepas), produk varian test masih ada
    tapi seed produk asli (7) harus tetap. Hitung non-varian-test."""
    r = requests.get(f"{BASE_URL}/api/products", headers=_hdr(admin_token), timeout=15)
    assert r.status_code == 200
    non_test = [p for p in r.json() if not p["sku"].startswith(f"{TEST_PREFIX}-")]
    # Seed awal = 7 (per problem statement)
    assert len(non_test) >= 7, f"non-test products={len(non_test)} (expected ≥7)"
