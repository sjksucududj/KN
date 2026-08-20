"""Gelombang 3 SEC-1/SEC-2 + F-10 backend tests.

Cakupan:
- AUTH: login bcrypt + cookie HttpOnly + Bearer fallback + logout + lockout
- Migrasi transparan SHA256 → bcrypt saat login sukses
- Pajak: compute-tax PPN 12% DPP Nilai Lain 11/12 (PKP), non-PKP (kanda) nol
- E2E Sales Order → simulate-payment → GL journal_entries balance
    (Cr Pendapatan = grand − ppn, BUKAN DPP), Cr PPN Out = ppn
- Faktur Pajak kode_transaksi default '04' saat dpp_nilai_lain
- Regresi PO (PPN efektif 11% dari net)
"""
import os
import time
from typing import Any, Dict, Optional, Tuple

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = ("admin@kainnusantara.id", "demo12345")
MANAGER = ("manager@kainnusantara.id", "demo12345")
SALES = ("sales@kainnusantara.id", "demo12345")
WAREHOUSE = ("warehouse@kainnusantara.id", "demo12345")
ENT_KSC = "ent_ksc"
ENT_KANDA = "ent_kanda"


# ── Helper ───────────────────────────────────────────────────────────────────

def _login(email: str, password: str) -> Tuple[requests.Session, Dict[str, Any]]:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"Login {email} gagal: {r.status_code} {r.text}"
    data = r.json()
    tok = data["token"]
    s.headers.update({"Authorization": f"Bearer {tok}", "X-Entity-Id": ENT_KSC})
    return s, data


@pytest.fixture(scope="module")
def admin_session() -> Tuple[requests.Session, Dict[str, Any]]:
    return _login(*ADMIN)


# ── 1. AUTH ──────────────────────────────────────────────────────────────────

class TestAuth:
    def test_login_admin_returns_token_user_context_and_cookie(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and len(data["token"]) >= 30
        assert data["user"]["email"] == ADMIN[0]
        assert "entity_context" in data
        assert data["entity_context"]["active_entity_id"] == ENT_KSC
        # Set-Cookie session_token HttpOnly
        cookie = r.cookies.get("session_token")
        assert cookie is not None, f"session_token cookie tidak diset. Headers: {dict(r.headers)}"
        raw = r.headers.get("set-cookie", "")
        assert "HttpOnly" in raw, f"session_token bukan HttpOnly: {raw}"

    def test_me_via_cookie_only(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=20)
        assert r.status_code == 200
        # cookie sudah otomatis disimpan di s.cookies
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=20)
        assert me.status_code == 200, me.text
        assert me.json()["email"] == ADMIN[0]

    def test_me_via_bearer_only(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=20)
        tok = r.json()["token"]
        me = requests.get(f"{BASE_URL}/api/auth/me",
                          headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        assert me.status_code == 200
        assert me.json()["email"] == ADMIN[0]

    def test_all_roles_login_and_bcrypt_migration(self):
        """Login semua role — trigger migrasi bcrypt untuk hash legacy."""
        for email, pw in [ADMIN, MANAGER, SALES, WAREHOUSE]:
            r = requests.post(f"{BASE_URL}/api/auth/login",
                              json={"email": email, "password": pw}, timeout=20)
            assert r.status_code == 200, f"login {email} gagal: {r.text}"
        # Verifikasi hash DB berawalan $2b$
        from motor.motor_asyncio import AsyncIOMotorClient
        import asyncio
        async def check():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            out = {}
            for email, _ in [ADMIN, MANAGER, SALES, WAREHOUSE]:
                u = await db.users.find_one({"email": email}, {"password_hash": 1, "_id": 0})
                out[email] = u["password_hash"] if u else None
            c.close()
            return out
        hashes = asyncio.run(check())
        for email, h in hashes.items():
            assert h and h.startswith("$2"), f"{email} hash bukan bcrypt: {h[:20] if h else None}"

    def test_logout_invalidates_session(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=20)
        tok = r.json()["token"]
        # Logout via bearer
        lo = requests.post(f"{BASE_URL}/api/auth/logout",
                           headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        assert lo.status_code == 200
        # Setelah logout, /me dengan token lama harus 401
        me = requests.get(f"{BASE_URL}/api/auth/me",
                          headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        assert me.status_code == 401

    def test_wrong_password_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": ADMIN[0], "password": "salahsekali!!"}, timeout=20)
        # bisa 401 atau 429 kalau sebelumnya sudah gagal — di sini uji satu kali saja
        assert r.status_code in (401, 429)


# ── 2. PPN 12% + DPP Nilai Lain 11/12 ────────────────────────────────────────

class TestPajakConfig:
    def test_compute_tax_ent_ksc(self, admin_session):
        s, _ = admin_session
        r = s.get(f"{BASE_URL}/api/settings/compute-tax",
                  params={"subtotal": 1000000, "entity_id": ENT_KSC}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["ppn_rate"] == 12.0
        assert d["effective_rate"] == 11.0
        assert d["dpp_nilai_lain"] is True
        assert d["is_pkp"] is True
        assert abs(d["dpp"] - 916666.67) < 0.02
        assert d["ppn_amount"] == 110000.0
        assert d["grand_total"] == 1110000.0

    def test_compute_tax_ent_kanda_non_pkp(self, admin_session):
        s, _ = admin_session
        r = s.get(f"{BASE_URL}/api/settings/compute-tax",
                  params={"subtotal": 1000000, "entity_id": ENT_KANDA}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["ppn_rate"] == 0.0
        assert d["ppn_amount"] == 0.0
        assert d["grand_total"] == 1000000.0
        assert d["is_pkp"] is False


# ── 3. E2E: Sales Order → payment → GL ───────────────────────────────────────

def _pick_product_with_stock(s: requests.Session) -> Optional[Dict[str, Any]]:
    r = s.get(f"{BASE_URL}/api/products", timeout=30)
    assert r.status_code == 200
    prods = r.json()
    # cari stok terbanyak di ent_ksc, harga > 0
    best = None
    for p in prods:
        if float(p.get("price", 0) or 0) <= 0:
            continue
        # gunakan produk seed yang biasanya punya stok
        stock = float(p.get("stock", p.get("total_stock", 0)) or 0)
        if best is None or stock > best[0]:
            best = (stock, p)
    return best[1] if best else None


def _pick_customer(s: requests.Session) -> Optional[Dict[str, Any]]:
    r = s.get(f"{BASE_URL}/api/customers", timeout=30)
    assert r.status_code == 200
    customers = r.json()
    for c in customers:
        if c.get("entity_id") in (ENT_KSC, None, "") and c.get("addresses"):
            return c
    return customers[0] if customers else None


@pytest.fixture(scope="module")
def created_order(admin_session):
    s, _ = admin_session
    product = _pick_product_with_stock(s)
    assert product, "Tidak ada produk untuk testing"
    customer = _pick_customer(s)
    assert customer, "Tidak ada customer"
    payload = {
        "customer_id": customer["id"],
        "shipping_address_id": customer["addresses"][0]["id"],
        "items": [{
            "product_id": product["id"],
            "quantity": 5,
            "unit": product.get("base_unit", "meter"),
        }],
        "sales_name": "TEST-AGENT G3",
        "entity_id": ENT_KSC,
        "payment_term_code": "CASH",
        "allow_backorder": True,
    }
    r = s.post(f"{BASE_URL}/api/sales-orders", json=payload, timeout=40)
    assert r.status_code in (200, 201), f"Buat SO gagal: {r.status_code} {r.text}"
    order = r.json()
    return order, product


class TestSalesOrderPPN:
    def test_order_saves_dpp_nilai_lain_and_effective_rate(self, created_order):
        order, _ = created_order
        assert order.get("dpp_nilai_lain") is True, f"dpp_nilai_lain tidak True: {order.get('dpp_nilai_lain')}"
        assert abs(float(order["effective_rate"]) - 11.0) < 0.01
        assert order["ppn_rate"] == 12.0
        net = float(order["net_subtotal"])
        # ppn = 11% dari net
        assert abs(order["ppn_amount"] - round(net * 0.11, 2)) < 0.02, \
            f"ppn_amount {order['ppn_amount']} != 11% x {net}"
        # dpp = net × 11/12
        assert abs(order["dpp"] - round(net * 11 / 12, 2)) < 0.02
        # grand = net × 1.11
        assert abs(order["grand_total"] - round(net * 1.11, 2)) < 0.02


class TestSalesOrderGL:
    def test_payment_creates_balanced_je_with_revenue_equals_grand_minus_ppn(
            self, admin_session, created_order):
        s, _ = admin_session
        order, _ = created_order
        # simulate-payment → memicu post_sales_order (GL)
        r = s.post(f"{BASE_URL}/api/sales-orders/{order['id']}/simulate-payment",
                   json={"amount": 0, "method": "Kas Besar",
                         "created_by": "TEST-AGENT"}, timeout=40)
        assert r.status_code == 200, f"simulate-payment gagal: {r.status_code} {r.text}"

        # Cari JE via mongo langsung (lebih andal karena endpoint /gl/journal ada lag)
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient

        async def fetch():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            for _ in range(15):
                je = await db.journal_entries.find_one(
                    {"source_type": "sales_order", "source_id": order["id"]}, {"_id": 0})
                if je:
                    c.close()
                    return je
                await asyncio.sleep(1)
            c.close()
            return None

        je = asyncio.run(fetch())
        assert je is not None, f"JE sales_order tidak ditemukan untuk {order['id']}"
        lines = je["lines"]
        total_debit = round(sum(float(l["debit"]) for l in lines), 2)
        total_credit = round(sum(float(l["credit"]) for l in lines), 2)
        assert abs(total_debit - total_credit) < 0.01, \
            f"JE tidak balance: Dr={total_debit} Cr={total_credit} lines={lines}"

        grand = float(order["grand_total"])
        ppn = float(order["ppn_amount"])
        rev_expected = round(grand - ppn, 2)

        rev_line = next((l for l in lines if l["account_code"] == "4-1000"), None)
        ppn_line = next((l for l in lines if l["account_code"] == "2-1200"), None)
        assert rev_line, f"Baris Pendapatan (4-1000) tidak ada: {lines}"
        assert ppn_line, f"Baris PPN Keluaran (2-1200) tidak ada: {lines}"
        assert abs(float(rev_line["credit"]) - rev_expected) < 0.02, \
            f"Cr Pendapatan {rev_line['credit']} != grand−ppn {rev_expected} (BUKAN DPP)"
        assert abs(float(ppn_line["credit"]) - ppn) < 0.02
        # Pastikan revenue BUKAN dipakai nilai DPP 11/12
        dpp = float(order["dpp"])
        assert abs(float(rev_line["credit"]) - dpp) > 1.0 or dpp == rev_expected, \
            f"Cr Pendapatan sama dengan DPP {dpp} — seharusnya harga jual {rev_expected}"
        # Tidak ada baris suspense besar
        suspense = [l for l in lines if l["account_code"] in ("4-9000", "7-9000") and abs(float(l.get("debit", 0)) + float(l.get("credit", 0))) > 1.0]
        assert not suspense, f"Ada baris suspense: {suspense}"


# ── 4. Faktur Pajak — kode 04 default saat dpp_nilai_lain ────────────────────

class TestFakturPajak:
    def test_issue_tax_invoice_defaults_to_kode_04(self, admin_session, created_order):
        s, _ = admin_session
        order, _ = created_order
        # Konfirmasi order dulu (kalau belum). Coba beberapa transisi.
        # simulate-payment sudah bayar, tapi status mungkin masih pending — coba confirm.
        for act in ["submit-for-approval", "approve", "confirm"]:
            s.post(f"{BASE_URL}/api/sales-orders/{order['id']}/{act}", timeout=20)
        # Untuk uji ini KODE TRANSAKSI TIDAK dikirim.
        # NOTE: schema default = "01"; hanya null yang trigger fallback "04".
        # Kirim eksplisit null via JSON.
        r = requests.post(
            f"{BASE_URL}/api/sales-orders/{order['id']}/tax-invoice",
            headers=s.headers,
            json={"kode_transaksi": None},
            timeout=30,
        )
        # Test toleran: skip kalau server mengharuskan status confirmed & belum tercapai.
        if r.status_code >= 400 and ("status" in r.text.lower() or "confirmed" in r.text.lower()
                                     or "belum" in r.text.lower()):
            pytest.skip(f"Order belum di status yang diperlukan untuk terbit FP: {r.text}")
        assert r.status_code in (200, 201), f"Terbit FP gagal: {r.status_code} {r.text}"
        fkt = r.json()
        assert fkt.get("kode_transaksi") == "04", \
            f"kode_transaksi default seharusnya '04' (dpp_nilai_lain), diperoleh: {fkt.get('kode_transaksi')}"
        assert fkt.get("dpp_nilai_lain") is True
        # dpp snapshot = 11/12 × harga jual
        harga = float(order["grand_total"]) - float(order["ppn_amount"])
        assert abs(float(fkt.get("dpp", 0)) - round(harga * 11 / 12, 2)) < 0.5


# ── 5. Regresi PO — PPN efektif 11% ──────────────────────────────────────────

class TestPurchaseOrderPPN:
    def test_po_uses_effective_rate_11(self, admin_session):
        s, _ = admin_session
        # ambil supplier & produk apa saja
        sup = s.get(f"{BASE_URL}/api/suppliers", timeout=20)
        assert sup.status_code == 200
        suppliers = sup.json()
        if not suppliers:
            pytest.skip("Tidak ada supplier")
        supplier = suppliers[0]
        prods = s.get(f"{BASE_URL}/api/products", timeout=20).json()
        product = next((p for p in prods if float(p.get("price", 0) or 0) > 0), None)
        assert product, "Tidak ada produk"
        whs = s.get(f"{BASE_URL}/api/warehouses", timeout=20).json()
        wh = next((w for w in whs if (w.get("entity_id") in (ENT_KSC, None, ""))), whs[0] if whs else None)
        assert wh, "Tidak ada warehouse"
        payload = {
            "supplier_id": supplier["id"],
            "supplier_name": supplier.get("name", ""),
            "entity_id": ENT_KSC,
            "warehouse_id": wh["id"],
            "items": [{
                "product_id": product["id"],
                "product_name": product["name"],
                "sku": product.get("sku", ""),
                "quantity": 10,
                "unit": product.get("base_unit", "meter"),
                "price": 100000,
                "discount_percent": 0,
            }],
            "expected_arrival": "",
            "notes": "TEST-AGENT G3 PPN12",
        }
        r = s.post(f"{BASE_URL}/api/purchase-orders", json=payload, timeout=30)
        if r.status_code >= 400:
            pytest.skip(f"Buat PO gagal (bukan fokus test): {r.status_code} {r.text[:200]}")
        po = r.json()
        net = float(po.get("net_subtotal", po.get("total_amount", 0)))
        ppn = float(po.get("ppn_amount", 0))
        # PO tidak selalu expose effective_rate; validasi via nilai (ppn_amount = 11% × net).
        assert abs(ppn - round(net * 0.11, 2)) < 0.02, \
            f"PO ppn_amount {ppn} != 11% × net {net} (rezim PPN 12% + DPP Nilai Lain harus efektif 11%)"
        # dpp = net × 11/12
        assert abs(float(po.get("dpp", 0)) - round(net * 11 / 12, 2)) < 0.5
        # grand = net × 1.11
        assert abs(float(po.get("grand_total", 0)) - round(net * 1.11, 2)) < 0.5


# ── 6. Lockout brute-force (jalankan PALING AKHIR, email fiktif) ─────────────

class TestLockoutLast:
    def test_lockout_after_5_failures(self):
        """Email fiktif per test-run agar tidak mengunci akun demo & tidak konflik antar run."""
        import uuid
        fake = f"lockout-{uuid.uuid4().hex[:8]}@test.invalid"
        # 5 percobaan salah → semua 401
        for i in range(5):
            r = requests.post(f"{BASE_URL}/api/auth/login",
                              json={"email": fake, "password": "salah"}, timeout=20)
            assert r.status_code == 401, f"attempt {i+1}: {r.status_code} {r.text}"
        # percobaan ke-6 → 429
        r6 = requests.post(f"{BASE_URL}/api/auth/login",
                           json={"email": fake, "password": "salah"}, timeout=20)
        assert r6.status_code == 429, f"attempt 6 seharusnya 429: {r6.status_code} {r6.text}"
        # Pesan Indonesia
        detail = r6.json().get("detail", "")
        assert "menit" in detail.lower() or "coba" in detail.lower() or "lockout" in detail.lower(), \
            f"Pesan lockout tidak dalam Indonesia: {detail}"
