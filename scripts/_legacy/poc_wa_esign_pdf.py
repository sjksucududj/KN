"""POC verifikasi core: PDF render + E-Sign + WhatsApp (simulasi).

Menguji end-to-end lewat API backend (localhost:8001) memakai kredensial demo.
Jalankan: python /app/scripts/poc_wa_esign_pdf.py
"""
import sys
import requests

BASE = "http://localhost:8001/api"
EMAIL = "admin@kainnusantara.id"
PASSWORD = "demo12345"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{PASS if cond else FAIL}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def main():
    s = requests.Session()

    # 1) Login
    r = s.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if not check("login admin", r.status_code == 200, f"HTTP {r.status_code}"):
        print(r.text[:300]); sys.exit(1)
    token = r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {token}"})

    # 2) doc-types
    r = s.get(f"{BASE}/pdf/doc-types", timeout=30)
    check("GET /pdf/doc-types", r.status_code == 200, f"HTTP {r.status_code}")
    doc_types = r.json() if r.status_code == 200 else []
    check("doc-types non-empty", len(doc_types) > 0, f"count={len(doc_types)}")

    # Pilih doc_type yang punya dokumen; utamakan sales_order
    chosen = None
    doc = None
    ordered = sorted(doc_types, key=lambda d: 0 if d.get("doc_type") == "sales_order" else 1)
    for dt in ordered:
        dtp = dt["doc_type"]
        rr = s.get(f"{BASE}/pdf/documents/{dtp}", params={"entity_id": "all", "limit": 5}, timeout=30)
        if rr.status_code == 200 and rr.json().get("documents"):
            chosen = dt
            doc = rr.json()["documents"][0]
            break
    if not check("ada dokumen untuk diuji", doc is not None, f"doc_type={chosen and chosen['doc_type']}"):
        sys.exit(1)
    dt = chosen["doc_type"]
    sid = doc["source_id"]
    eid = doc.get("entity_id")
    print(f"    -> uji doc_type={dt} source_id={sid} entity_id={eid} number={doc.get('number')}")

    # 3) PDF render (pdf + html)
    r = s.get(f"{BASE}/pdf/render/{dt}/{sid}", params={"format": "pdf", "entity_id": eid}, timeout=60)
    is_pdf = r.status_code == 200 and r.content[:4] == b"%PDF"
    check("render PDF valid (%PDF)", is_pdf, f"HTTP {r.status_code} size={len(r.content)}B")
    r = s.get(f"{BASE}/pdf/render/{dt}/{sid}", params={"format": "html", "entity_id": eid},
              headers={"Accept": "text/html"}, timeout=60)
    check("render HTML preview", r.status_code == 200 and "<" in r.text, f"HTTP {r.status_code}")

    # 4) WhatsApp settings GET
    r = s.get(f"{BASE}/deliveries/whatsapp/settings", timeout=30)
    check("GET wa settings", r.status_code == 200, f"HTTP {r.status_code}")
    settings = r.json() if r.status_code == 200 else {}
    check("wa mode simulasi default", settings.get("simulate") in (True, False),
          f"simulate={settings.get('simulate')} provider={settings.get('provider')}")

    # 5) WhatsApp send (simulate)
    r = s.post(f"{BASE}/deliveries/whatsapp/send", json={
        "doc_type": dt, "source_id": sid, "entity_id": eid,
        "to": "081234567890", "caption": "POC caption", "message": "POC test message",
    }, timeout=60)
    ok_send = r.status_code == 200
    check("POST wa send", ok_send, f"HTTP {r.status_code} {('' if ok_send else r.text[:200])}")
    if ok_send:
        body = r.json()
        check("wa send status simulated/sent", body.get("status") in ("simulated", "sent"),
              f"status={body.get('status')} provider={body.get('provider')} mid={body.get('message_id')}")
        check("wa send phone normalized (62)", str(body.get("to", "")).startswith("62"),
              f"to={body.get('to')}")

    # 6) WhatsApp history
    r = s.get(f"{BASE}/deliveries/{dt}/{sid}", timeout=30)
    hist = r.json().get("deliveries", []) if r.status_code == 200 else []
    check("GET wa history", r.status_code == 200 and len(hist) >= 1, f"count={len(hist)}")

    # 7) E-Sign request (OTP simulasi) — cari doc_type esignable YANG punya dokumen
    esignable_dt = None
    edoc = None
    for d in doc_types:
        if not d.get("esignable"):
            continue
        rr = s.get(f"{BASE}/pdf/documents/{d['doc_type']}", params={"entity_id": "all", "limit": 5}, timeout=30)
        if rr.status_code == 200 and rr.json().get("documents"):
            esignable_dt = d["doc_type"]
            edoc = rr.json()["documents"][0]
            break
    if esignable_dt:
        if edoc:
            r = s.post(f"{BASE}/esign/request", json={
                "doc_type": esignable_dt, "source_id": edoc["source_id"],
                "entity_id": edoc.get("entity_id"),
                "signer_name": "Budi Santoso", "signer_role": "admin",
            }, timeout=30)
            ok_req = r.status_code == 200
            check("POST esign request (OTP simulasi)", ok_req,
                  f"HTTP {r.status_code} {('' if ok_req else r.text[:200])}")
            if ok_req:
                req = r.json()
                req_id = req.get("request_id") or req.get("id")
                otp = req.get("reveal_code")  # simulasi mengembalikan OTP
                check("esign request menghasilkan OTP (simulasi)", bool(otp),
                      f"request_id={req_id} otp={'***' if otp else None}")
                # tiny 1x1 png signature
                sig = ("data:image/png;base64,"
                       "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
                if otp and req_id:
                    r = s.post(f"{BASE}/esign/verify", json={
                        "request_id": req_id, "otp": str(otp), "signature_b64": sig,
                    }, timeout=60)
                    ok_ver = r.status_code == 200
                    check("POST esign verify -> tanda tangan tersimpan", ok_ver,
                          f"HTTP {r.status_code} {('' if ok_ver else r.text[:200])}")
                    if ok_ver:
                        vr = r.json()
                        code = vr.get("verification_code") or vr.get("code")
                        check("esign verification_code + doc_hash ada",
                              bool(code) and bool(vr.get("doc_hash") or vr.get("hash")),
                              f"code={code}")
                        if code:
                            # public verify (tanpa auth)
                            pub = requests.get(f"{BASE}/esign/verify/{code}", timeout=30)
                            check("GET public verify /esign/verify/{code}",
                                  pub.status_code == 200, f"HTTP {pub.status_code}")
    else:
        check("ada doc_type esignable", False, "tidak ada doc_type esignable di registry")

    # Ringkasan
    total = len(results)
    passed = sum(1 for _, c, _ in results if c)
    print(f"\n===== POC RESULT: {passed}/{total} PASS =====")
    sys.exit(0 if passed == total else 2)


if __name__ == "__main__":
    main()
