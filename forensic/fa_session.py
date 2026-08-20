#!/usr/bin/env python3
"""FORENSIC 2c — Session / token security (empirical)."""
import os, requests, string, math
from collections import Counter
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta
db=MongoClient(os.environ.get("MONGO_URL","mongodb://localhost:27017"))[os.environ.get("DB_NAME","test_database")]
BASE="http://localhost:8001/api"
F=[]
def rec(sev,msg): F.append((sev,msg)); print(f"  [{sev:4}] {msg}")

def login(email="admin@kainnusantara.id",pw="demo12345",xff=None):
    h={}
    if xff: h["X-Forwarded-For"]=xff
    return requests.post(f"{BASE}/auth/login",json={"email":email,"password":pw},headers=h,timeout=15)

print("########## 2c SESSION / TOKEN SECURITY ##########")

# T1 token entropy
r=login(); tok=r.json()["token"]; setck=r.headers.get("set-cookie","")
alpha=set(tok)
print(f"\n[T1] token len={len(tok)} distinct_chars={len(alpha)} sample={tok[:12]}...")
if len(tok)>=40 and len(alpha)>=16: print("  [OK  ] token entropy tinggi (token_urlsafe32 ~256-bit)")
else: rec("HIGH","token entropy rendah")

# T5 cookie flags
print(f"\n[T5] Set-Cookie: {setck[:120]}")
low=setck.lower()
if "httponly" in low: print("  [OK  ] HttpOnly present")
else: rec("HIGH","cookie tanpa HttpOnly")
if "secure" in low: print("  [OK  ] Secure present")
else: rec("MED","cookie TANPA Secure flag (bisa terkirim via HTTP; app disajikan via HTTPS ingress)")
if "samesite" in low: print(f"  [OK  ] SameSite present")
else: rec("LOW","cookie tanpa SameSite")

# T2 logout invalidation
H={"Authorization":f"Bearer {tok}"}
me1=requests.get(f"{BASE}/auth/me",headers=H)
lo=requests.post(f"{BASE}/auth/logout",headers=H)
me2=requests.get(f"{BASE}/auth/me",headers=H)
print(f"\n[T2] me(before)={me1.status_code} logout={lo.status_code} me(after)={me2.status_code}")
if me2.status_code==401: print("  [OK  ] token invalid setelah logout (session dihapus)")
else: rec("HIGH","token MASIH valid setelah logout (session tak di-invalidate)")

# T6 random/tampered token rejected
r=requests.get(f"{BASE}/auth/me",headers={"Authorization":"Bearer "+("z"*43)})
print(f"\n[T6] random token -> {r.status_code}")
if r.status_code==401: print("  [OK  ] token acak ditolak")
else: rec("HIGH","token acak diterima")

# T7 expired session enforcement
tok2=login().json()["token"]
db.sessions.update_one({"token":tok2},{"$set":{"expires_at":(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()}})
r=requests.get(f"{BASE}/auth/me",headers={"Authorization":f"Bearer {tok2}"})
print(f"\n[T7] expired session -> {r.status_code}")
if r.status_code==401: print("  [OK  ] session kedaluwarsa ditolak")
else: rec("HIGH","session kedaluwarsa MASIH diterima")

# T8 password_hash leak check
tok3=login().json()["token"]; H3={"Authorization":f"Bearer {tok3}"}
for ep in ["/auth/me","/users"]:
    r=requests.get(f"{BASE}{ep}",headers=H3)
    if r.status_code==200 and "password_hash" in r.text:
        rec("HIGH",f"{ep} membocorkan password_hash")
    elif r.status_code==200:
        print(f"\n[T8] {ep} -> 200, tidak ada password_hash [OK]")
    else:
        print(f"\n[T8] {ep} -> {r.status_code}")

# T3 brute-force lockout (fake email, fixed IP)
print("\n[T3] brute-force lockout (email palsu, XFF tetap)")
codes=[]
for i in range(7):
    rr=login("bruteforce_probe@kn.id","wrongpw",xff="203.0.113.9")
    codes.append(rr.status_code)
print(f"  statuses={codes}")
if 429 in codes: print(f"  [OK  ] lockout aktif setelah beberapa gagal (429 muncul di percobaan #{codes.index(429)+1})")
else: rec("MED","tidak ada lockout 429 pada percobaan berulang (fixed IP)")

# T4 lockout bypass via X-Forwarded-For rotation (fake email)
print("\n[T4] lockout bypass via X-Forwarded-For berputar (email sama)")
codes2=[]
for i in range(10):
    rr=login("xffbypass_probe@kn.id","wrongpw",xff=f"198.51.100.{i}")
    codes2.append(rr.status_code)
print(f"  statuses(rotating XFF)={codes2}")
if 429 not in codes2:
    rec("MED","BRUTE-FORCE LOCKOUT DAPAT DI-BYPASS: identifier lockout memakai X-Forwarded-For (dikontrol klien). Rotasi XFF → counter selalu reset, 429 tak pernah muncul walau 10x gagal untuk email sama.")
else:
    print("  [OK  ] lockout tetap kena walau XFF berputar")

# cleanup probe artifacts
db.login_attempts.delete_many({"identifier":{"$regex":"probe@kn.id"}})
db.sessions.delete_many({"token":{"$in":[tok2]}})
print("\n===== 2c SUMMARY =====")
for s,m in F: print(f"  {s}: {m[:100]}")
print(f"  findings: {len(F)}")
