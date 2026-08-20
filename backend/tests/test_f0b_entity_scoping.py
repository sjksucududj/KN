"""F0-B Multi-Entity Scoping & Data Isolation Backend Tests.

Memvalidasi:
- Isolasi default (no header) → konteks home.
- Header X-Entity-Id switch konteks.
- Mode "Semua Entitas" (cross-entity) via header 'all' atau ?entity_id=all.
- Prioritas query param di atas header.
- Anti-IDOR 403 untuk single-entity user yang minta entitas lain.
- Kasus khusus kas/bank: kas_besar & akun grup selalu tampil.
- Stamping entity_id pada create.
- Tidak ada regresi 500 di list & summary.
"""
import os
import pytest
import requests

# Load REACT_APP_BACKEND_URL from /app/frontend/.env if missing in env
def _load_backend_url():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

CREDS = {
    "admin": ("admin@kainnusantara.id", "demo12345"),
    "manager": ("manager@kainnusantara.id", "demo12345"),
    "sales3": ("sales3@kainnusantara.id", "demo12345"),  # single ent_kanda
    "sales": ("sales@kainnusantara.id", "demo12345"),    # single ent_ksc
}

ENT_KSC = "ent_ksc"
ENT_KANDA = "ent_kanda"


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def tokens():
    out = {}
    for key, (email, pwd) in CREDS.items():
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
        assert r.status_code == 200, f"Login {key} failed: {r.status_code} {r.text}"
        out[key] = r.json()["token"]
    return out


def H(token, entity=None, qparam=False):
    h = {"Authorization": f"Bearer {token}"}
    if entity and not qparam:
        h["X-Entity-Id"] = entity
    return h


def _get(path, token, entity_header=None, params=None, expect=None):
    headers = H(token, entity_header)
    r = requests.get(f"{API}{path}", headers=headers, params=params, timeout=20)
    if expect is not None:
        assert r.status_code == expect, f"GET {path} (entity={entity_header}, params={params}) -> {r.status_code}, body={r.text[:200]}"
    return r


# ── Endpoints list yang harus discope ───────────────────────────────────────
LIST_ENDPOINTS = [
    "/purchase-orders",
    "/vendor-bills",
    "/suppliers",
    "/rfqs",
    "/purchase-requisitions",
    "/sales-returns",
    "/special-orders",
    "/price-approvals",
    "/tax-invoices",
    "/input-tax-invoices",
    "/ar-receipts",
    "/cash-transactions",
    "/bank-accounts",
]

# Fields utk extract entity_id; ar_receipts/cash_transactions/bank_accounts use entity_id
ENTITY_FIELD = "entity_id"


def _items_of(resp_json):
    """Endpoint return List atau dict {items: [...]}."""
    if isinstance(resp_json, list):
        return resp_json
    if isinstance(resp_json, dict):
        for k in ("items", "data", "results", "rows"):
            if k in resp_json and isinstance(resp_json[k], list):
                return resp_json[k]
    return []


# ── 1. No header → konteks home (admin home=ent_ksc) ────────────────────────
@pytest.mark.parametrize("ep", LIST_ENDPOINTS)
def test_list_no_header_admin_scoped_to_home_ksc(tokens, ep):
    r = _get(ep, tokens["admin"], expect=200)
    items = _items_of(r.json())
    # Bank/Cash punya record 'all' yang selalu tampak; lainnya harus 100% ent_ksc.
    if ep == "/cash-transactions":
        # kas_besar entity_id='all' boleh ada; sisanya harus ent_ksc
        non_all = [it for it in items if it.get(ENTITY_FIELD) not in ("all", None)]
        assert all(it.get(ENTITY_FIELD) == ENT_KSC for it in non_all), \
            f"cash-transactions bocor: {set(it.get(ENTITY_FIELD) for it in items)}"
    elif ep == "/bank-accounts":
        non_all = [it for it in items if it.get(ENTITY_FIELD) not in ("all", None)]
        assert all(it.get(ENTITY_FIELD) == ENT_KSC for it in non_all), \
            f"bank-accounts bocor: {set(it.get(ENTITY_FIELD) for it in items)}"
    else:
        leaked = [it for it in items if it.get(ENTITY_FIELD) and it.get(ENTITY_FIELD) != ENT_KSC]
        assert not leaked, f"{ep}: data entitas selain {ENT_KSC} bocor: {leaked[:3]}"


# ── 2. Header X-Entity-Id: ent_kanda → hanya kanda ─────────────────────────
@pytest.mark.parametrize("ep", LIST_ENDPOINTS)
def test_list_header_switch_to_kanda(tokens, ep):
    r = _get(ep, tokens["admin"], entity_header=ENT_KANDA, expect=200)
    items = _items_of(r.json())
    if ep in ("/cash-transactions", "/bank-accounts"):
        non_all = [it for it in items if it.get(ENTITY_FIELD) not in ("all", None)]
        assert all(it.get(ENTITY_FIELD) == ENT_KANDA for it in non_all), \
            f"{ep}: harus hanya ent_kanda (kecuali 'all'), found {set(it.get(ENTITY_FIELD) for it in items)}"
    else:
        leaked = [it for it in items if it.get(ENTITY_FIELD) and it.get(ENTITY_FIELD) != ENT_KANDA]
        assert not leaked, f"{ep}: harus hanya ent_kanda, bocor: {[it.get(ENTITY_FIELD) for it in leaked[:3]]}"


# ── 3. Mode "Semua Entitas" via header X-Entity-Id: all ────────────────────
@pytest.mark.parametrize("ep", LIST_ENDPOINTS)
def test_list_view_all_via_header_admin(tokens, ep):
    r_home = _get(ep, tokens["admin"], expect=200)
    r_all = _get(ep, tokens["admin"], entity_header="all", expect=200)
    home_count = len(_items_of(r_home.json()))
    all_count = len(_items_of(r_all.json()))
    # Untuk endpoint dengan data 'all' (cash/bank), bisa sama; lainnya all >= home
    assert all_count >= home_count, f"{ep}: 'all' count ({all_count}) < home count ({home_count})"


# ── 4. Mode "Semua Entitas" via query ?entity_id=all (admin) ───────────────
@pytest.mark.parametrize("ep", LIST_ENDPOINTS)
def test_list_view_all_via_query_admin(tokens, ep):
    r = _get(ep, tokens["admin"], params={"entity_id": "all"}, expect=200)
    items = _items_of(r.json())
    ents = {it.get(ENTITY_FIELD) for it in items if it.get(ENTITY_FIELD)}
    # Boleh hanya satu entitas jika seed memang punya satu; cukup pastikan tidak 403/500.
    assert ents.issubset({ENT_KSC, ENT_KANDA, "all"}), f"{ep}: ents={ents}"


# ── 5. Query param diprioritaskan & spesifik ───────────────────────────────
@pytest.mark.parametrize("ep", LIST_ENDPOINTS)
def test_query_param_priority_over_header(tokens, ep):
    # Header minta ksc, query minta kanda → harus kanda
    r = _get(ep, tokens["admin"], entity_header=ENT_KSC, params={"entity_id": ENT_KANDA}, expect=200)
    items = _items_of(r.json())
    if ep in ("/cash-transactions", "/bank-accounts"):
        non_all = [it for it in items if it.get(ENTITY_FIELD) not in ("all", None)]
        assert all(it.get(ENTITY_FIELD) == ENT_KANDA for it in non_all), \
            f"{ep}: param ent_kanda harus override header, found {set(it.get(ENTITY_FIELD) for it in items)}"
    else:
        leaked = [it for it in items if it.get(ENTITY_FIELD) and it.get(ENTITY_FIELD) != ENT_KANDA]
        assert not leaked, f"{ep}: query param tidak prioritas: bocor {[it.get(ENTITY_FIELD) for it in leaked[:3]]}"


# ── 6. Anti-IDOR: sales3 (home=ent_kanda) minta ent_ksc → 403 ───────────────
def test_sales3_request_ksc_customers_403(tokens):
    r = _get("/customers", tokens["sales3"], params={"entity_id": ENT_KSC})
    assert r.status_code == 403, f"sales3 customers?entity_id=ent_ksc harus 403, got {r.status_code} {r.text[:200]}"


def test_sales3_request_ksc_sales_orders_403(tokens):
    r = _get("/sales-orders", tokens["sales3"], params={"entity_id": ENT_KSC})
    assert r.status_code == 403, f"sales3 sales-orders?entity_id=ent_ksc harus 403, got {r.status_code} {r.text[:200]}"


def test_sales3_no_param_scoped_to_kanda(tokens):
    """sales3 default home=ent_kanda → list customers hanya kanda."""
    r = _get("/customers", tokens["sales3"], expect=200)
    items = _items_of(r.json())
    leaked = [it for it in items if it.get(ENTITY_FIELD) and it.get(ENTITY_FIELD) != ENT_KANDA]
    assert not leaked, f"sales3 customers bocor: {[it.get(ENTITY_FIELD) for it in leaked[:3]]}"


# ── 7. Admin cross-entity bisa ?entity_id=ent_ksc dan ent_kanda ─────────────
@pytest.mark.parametrize("target", [ENT_KSC, ENT_KANDA])
def test_admin_can_filter_each_entity(tokens, target):
    r = _get("/purchase-orders", tokens["admin"], params={"entity_id": target}, expect=200)
    items = _items_of(r.json())
    leaked = [it for it in items if it.get(ENTITY_FIELD) and it.get(ENTITY_FIELD) != target]
    assert not leaked, f"admin filter {target} bocor: {[it.get(ENTITY_FIELD) for it in leaked[:3]]}"


# ── 8. Cash kas_besar selalu tampil ─────────────────────────────────────────
def test_cash_kas_besar_visible_in_all_contexts(tokens):
    found_kas_besar = []
    for ctx_header in (None, ENT_KSC, ENT_KANDA, "all"):
        r = _get("/cash-transactions", tokens["admin"], entity_header=ctx_header, expect=200)
        items = _items_of(r.json())
        kb = [it for it in items if it.get("cash_type") == "kas_besar"]
        found_kas_besar.append((ctx_header, len(kb)))
    # Semua konteks harus konsisten (jumlah kas_besar sama)
    counts = {n for _, n in found_kas_besar}
    assert len(counts) == 1, f"kas_besar tidak konsisten lintas konteks: {found_kas_besar}"


def test_bank_accounts_group_visible(tokens):
    """Akun bank entity_id='all' selalu tampil."""
    r_ksc = _get("/bank-accounts", tokens["admin"], entity_header=ENT_KSC, expect=200)
    r_kanda = _get("/bank-accounts", tokens["admin"], entity_header=ENT_KANDA, expect=200)
    ksc_all = [it for it in _items_of(r_ksc.json()) if it.get(ENTITY_FIELD) == "all"]
    kanda_all = [it for it in _items_of(r_kanda.json()) if it.get(ENTITY_FIELD) == "all"]
    assert len(ksc_all) == len(kanda_all), \
        f"bank 'all' tidak konsisten: ksc={len(ksc_all)} kanda={len(kanda_all)}"


# ── 9. Anti-IDOR GET /{id} untuk admin (kedua entitas accessible) ──────────
def test_admin_get_by_id_both_entities(tokens):
    """admin bisa GET PO detail di ent_ksc maupun ent_kanda."""
    for ent in (ENT_KSC, ENT_KANDA):
        lst = _get("/purchase-orders", tokens["admin"], params={"entity_id": ent}, expect=200)
        items = _items_of(lst.json())
        if not items:
            continue
        po_id = items[0].get("id")
        if not po_id:
            continue
        r = _get(f"/purchase-orders/{po_id}", tokens["admin"])
        assert r.status_code == 200, f"admin GET /purchase-orders/{po_id} ({ent}) -> {r.status_code}"


# ── 10. Summary & blanket endpoints tidak 500 ───────────────────────────────
SUMMARY_ENDPOINTS = [
    "/vendor-bills/payables/summary",
    "/purchase-orders/payables/summary",
    "/cash-transactions/summary",
    "/purchase-orders/blanket",
]


@pytest.mark.parametrize("ep", SUMMARY_ENDPOINTS)
def test_summary_endpoints_no_500(tokens, ep):
    for ctx_header in (None, ENT_KSC, ENT_KANDA, "all"):
        r = _get(ep, tokens["admin"], entity_header=ctx_header)
        assert r.status_code != 500, f"{ep} (entity={ctx_header}) -> 500: {r.text[:300]}"
        assert r.status_code in (200, 204), f"{ep} -> {r.status_code}: {r.text[:200]}"


# ── 11. Create stamping: POST /suppliers stamp entity_id ────────────────────
def test_create_supplier_stamping(tokens):
    payload = {
        "name": "TEST_F0B Supplier Stamping",
        "contact_person": "Tester",
        "phone": "0800",
        "email": "f0b@test.local",
        "goods_type": "kain",
    }
    # Create dengan header X-Entity-Id=ent_kanda, body tanpa entity_id
    headers = H(tokens["admin"], ENT_KANDA)
    headers["Content-Type"] = "application/json"
    r = requests.post(f"{API}/suppliers", json=payload, headers=headers, timeout=15)
    assert r.status_code in (200, 201), f"create supplier -> {r.status_code} {r.text[:300]}"
    created = r.json()
    sid = created.get("id")
    assert sid, f"supplier id missing: {created}"
    assert created.get(ENTITY_FIELD) == ENT_KANDA, \
        f"supplier seharusnya distempel ent_kanda, got {created.get(ENTITY_FIELD)}"

    # List konteks ent_ksc → TIDAK boleh muncul
    r_ksc = _get("/suppliers", tokens["admin"], entity_header=ENT_KSC, expect=200)
    ids_ksc = {it.get("id") for it in _items_of(r_ksc.json())}
    assert sid not in ids_ksc, f"supplier kanda bocor di konteks ksc"

    # List konteks ent_kanda → muncul
    r_kanda = _get("/suppliers", tokens["admin"], entity_header=ENT_KANDA, expect=200)
    ids_kanda = {it.get("id") for it in _items_of(r_kanda.json())}
    assert sid in ids_kanda, f"supplier kanda tidak muncul di konteks kanda"


# ── 12. Sanity: tidak ada regresi 500 di semua list endpoints ──────────────
@pytest.mark.parametrize("ep", LIST_ENDPOINTS)
def test_no_regression_500(tokens, ep):
    for ctx_header in (None, ENT_KSC, ENT_KANDA, "all"):
        r = _get(ep, tokens["admin"], entity_header=ctx_header)
        assert r.status_code != 500, f"{ep} (entity={ctx_header}) -> 500: {r.text[:300]}"
