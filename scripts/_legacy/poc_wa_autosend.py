"""POC auto-send WhatsApp: recipient resolver + rules CRUD + dispatch on SO event."""
import sys
import requests

BASE = "http://localhost:8001/api"
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"[{PASS if cond else FAIL}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def main():
    s = requests.Session()
    s.headers.update({"Authorization": "Bearer " + s.post(
        f"{BASE}/auth/login",
        json={"email": "admin@kainnusantara.id", "password": "demo12345"}).json()["token"]})

    # Recipient resolver on a sales order
    docs = s.get(f"{BASE}/pdf/documents/sales_order", params={"entity_id": "all", "limit": 20}).json()["documents"]
    check("ada sales order utk uji", len(docs) > 0, f"count={len(docs)}")
    # pilih SO yang belum confirmed/done supaya bisa di-approve->confirm
    target = next((d for d in docs if d.get("status") in ("reserved", "waiting_approval", "approved")), docs[0])
    sid = target["source_id"]
    r = s.get(f"{BASE}/deliveries/whatsapp/recipient/sales_order/{sid}", params={"entity_id": target.get("entity_id")})
    check("GET recipient resolver", r.status_code == 200, f"HTTP {r.status_code}")
    rec = r.json() if r.status_code == 200 else {}
    check("recipient phone ternormalisasi (62) & mode=customer",
          str(rec.get("phone", "")).startswith("62") and rec.get("mode") == "customer",
          f"phone={rec.get('phone')} mode={rec.get('mode')} name={rec.get('name')}")

    # Rules CRUD — buat aturan auto-kirim SO 'confirmed' → customer
    # bersihkan aturan sales_order lama
    existing = s.get(f"{BASE}/deliveries/whatsapp/rules").json().get("rules", [])
    for rl in existing:
        if rl["doc_type"] == "sales_order" and rl["event"] == "confirmed":
            s.delete(f"{BASE}/deliveries/whatsapp/rules/{rl['id']}")

    r = s.post(f"{BASE}/deliveries/whatsapp/rules", json={
        "doc_type": "sales_order", "event": "confirmed", "recipient_mode": "customer",
        "caption_template": "Auto: {label} {number}", "enabled": True})
    check("POST create rule", r.status_code == 200, f"HTTP {r.status_code} {('' if r.status_code==200 else r.text[:200])}")
    rule = r.json() if r.status_code == 200 else {}
    rid = rule.get("id")

    r = s.get(f"{BASE}/deliveries/whatsapp/rules")
    rules = r.json().get("rules", [])
    check("GET rules list berisi aturan baru", any(x["id"] == rid for x in rules), f"count={len(rules)}")

    r = s.put(f"{BASE}/deliveries/whatsapp/rules/{rid}", json={"enabled": False})
    check("PUT update rule (disable)", r.status_code == 200 and r.json().get("enabled") is False,
          f"HTTP {r.status_code}")
    # re-enable
    s.put(f"{BASE}/deliveries/whatsapp/rules/{rid}", json={"enabled": True})

    # Count deliveries before
    before = len(s.get(f"{BASE}/deliveries/sales_order/{sid}").json().get("deliveries", []))

    # Trigger: approve (if needed) then confirm the SO -> should auto-send
    st = target.get("status")
    if st in ("reserved", "waiting_approval"):
        s.post(f"{BASE}/sales-orders/{sid}/approve")
    conf = s.post(f"{BASE}/sales-orders/{sid}/confirm")
    check("POST confirm SO (pemicu auto-send)", conf.status_code == 200, f"HTTP {conf.status_code} {('' if conf.status_code==200 else conf.text[:200])}")

    after_rows = s.get(f"{BASE}/deliveries/sales_order/{sid}").json().get("deliveries", [])
    auto_rows = [d for d in after_rows if d.get("auto") and d.get("trigger") == "confirmed"]
    check("auto-send menghasilkan delivery (trigger=confirmed, auto=True)",
          len(after_rows) > before and len(auto_rows) >= 1,
          f"before={before} after={len(after_rows)} auto={len(auto_rows)}")
    if auto_rows:
        d0 = auto_rows[0]
        check("delivery auto ber-caption template terformat",
              "Auto:" in (d0.get("caption") or "") and "{number}" not in (d0.get("caption") or ""),
              f"caption={d0.get('caption')}")

    # cleanup rule
    if rid:
        s.delete(f"{BASE}/deliveries/whatsapp/rules/{rid}")

    passed = sum(1 for c in results if c)
    print(f"\n===== AUTO-SEND POC: {passed}/{len(results)} PASS =====")
    sys.exit(0 if passed == len(results) else 2)


if __name__ == "__main__":
    main()
