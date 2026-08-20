"""Sub-fase 1.7 — Pegging / Earmark (soft hold) self-test.

Bagian A (API integration): earmark/list/unearmark + guard owner-scope (D3) +
guard status (hanya 'available') + ref_type 'order'.
Bagian B (anti-rebutan): roll_service._available_rolls_for_order MENGECUALIKAN
roll yang di-peg untuk customer LAIN, dan MENYERTAKAN roll yang di-peg untuk
customer/order yang sama (KN_15 E31).

Jalankan: python tests/test_pegging_17.py  (butuh backend RUNNING + seed bersih)
"""
import sys, asyncio
sys.path.insert(0, "/app/backend")
import requests  # noqa: E402

B = "http://localhost:8001/api"
results = []


def _assert(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, ("" if cond else f":: {detail}"))
    results.append(bool(cond))
    return cond


def login(email, pwd="demo12345"):
    r = requests.post(f"{B}/auth/login", json={"email": email, "password": pwd})
    return r.json()["token"]


def api_tests():
    admin = login("admin@kainnusantara.id")
    H = {"Authorization": f"Bearer {admin}"}

    rolls = requests.get(f"{B}/inventory/rolls", headers=H, params={"status": "available"}).json()
    # cari roll available yang BELUM di-earmark
    roll = next((r for r in rolls if not r.get("earmarked_for")), None)
    _assert("ada roll available bebas untuk uji", roll is not None)
    if not roll:
        return None, None, None

    owner = roll["owner_entity_id"]
    custs = requests.get(f"{B}/customers", headers=H, params={"entity_id": owner}).json()
    cust = custs[0]

    # 1) earmark ke customer entitas yang sama
    r = requests.post(f"{B}/inventory/rolls/{roll['id']}/earmark", headers=H,
                      json={"ref_type": "customer", "ref_id": cust["id"], "note": "uji hold"})
    _assert("earmark customer → 200", r.status_code == 200, r.text)
    ear = r.json().get("earmarked_for", {})
    _assert("earmarked_for.type==customer", ear.get("type") == "customer", ear)
    _assert("earmarked_for.name terisi", bool(ear.get("name")), ear)

    # 2) list pegging memuat roll ini
    pegged = requests.get(f"{B}/pegging/rolls", headers=H).json()
    _assert("/pegging/rolls memuat roll", any(p["id"] == roll["id"] for p in pegged), len(pegged))

    # 3) owner-scope: customer entitas LAIN → 409
    other = [c for c in requests.get(f"{B}/customers", headers=H).json() if c.get("entity_id") != owner]
    if other:
        rr = requests.post(f"{B}/inventory/rolls/{roll['id']}/earmark", headers=H,
                           json={"ref_type": "customer", "ref_id": other[0]["id"]})
        _assert("cross-entity earmark → 409", rr.status_code == 409, rr.text)

    # 4) ref_type 'order' → 200 (pakai SO apa pun bila ada)
    sos = requests.get(f"{B}/sales-orders", headers=H).json()
    if sos:
        ro = requests.post(f"{B}/inventory/rolls/{roll['id']}/earmark", headers=H,
                           json={"ref_type": "order", "ref_id": sos[0]["id"]})
        _assert("earmark order → 200", ro.status_code == 200, ro.text)

    # 5) earmark roll NON-available → 409 (cari roll reserved)
    reserved = requests.get(f"{B}/inventory/rolls", headers=H, params={"status": "reserved"}).json()
    if reserved:
        rn = requests.post(f"{B}/inventory/rolls/{reserved[0]['id']}/earmark", headers=H,
                           json={"ref_type": "customer", "ref_id": cust["id"]})
        _assert("earmark non-available → 409", rn.status_code == 409, rn.text)

    # 6) unearmark → 200 + cleared
    ru = requests.delete(f"{B}/inventory/rolls/{roll['id']}/earmark", headers=H)
    _assert("unearmark → 200", ru.status_code == 200, ru.text)
    pegged2 = requests.get(f"{B}/pegging/rolls", headers=H).json()
    _assert("roll tak lagi di list pegging", all(p["id"] != roll["id"] for p in pegged2))

    return roll, owner, cust


async def predicate_tests(roll, owner, cust):
    """Bagian B — anti-rebutan langsung di roll_service (mutasi sementara lalu dibersihkan)."""
    from db import db
    from core_utils import now_iso
    from services.roll_service import _available_rolls_for_order

    product_id = roll["product_id"]
    # peg roll ke customer A (cust)
    ear = {"type": "customer", "id": cust["id"], "name": cust.get("name", ""), "note": "predikat",
           "by": "test", "at": now_iso()}
    await db.inventory_rolls.update_one({"id": roll["id"]}, {"$set": {"earmarked_for": ear}})

    # untuk customer LAIN → roll dikecualikan
    avail_other = await _available_rolls_for_order(product_id, owner, "ord_x", customer_id="cust_other")
    _assert("anti-rebutan: roll dikecualikan utk customer lain",
            all(r["id"] != roll["id"] for r in avail_other))

    # untuk customer A → roll disertakan
    avail_same = await _available_rolls_for_order(product_id, owner, "ord_x", customer_id=cust["id"])
    _assert("roll disertakan utk customer pemegang peg",
            any(r["id"] == roll["id"] for r in avail_same))

    # cleanup
    await db.inventory_rolls.update_one({"id": roll["id"]}, {"$set": {"earmarked_for": None}})


def main():
    roll, owner, cust = api_tests()
    if roll:
        asyncio.run(predicate_tests(roll, owner, cust))
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n=== PEGGING 1.7 — {passed}/{total} PASS ===")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
