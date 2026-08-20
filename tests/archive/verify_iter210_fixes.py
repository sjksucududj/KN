#!/usr/bin/env python3
"""Verifikasi ulang 4 temuan iteration_210 dengan payload/kunci yang BENAR.

Temuan yang dilaporkan agen uji:
  M1  /api/settings/effective?entity_id=ent_kanda -> is_pkp=None & ppn=None
      (dugaan: agen uji membaca kunci top-level, padahal ada di bawah `tax`)
  M2  POST /api/sales-orders/preview-allocation sebagai sales3 dgn entity_id=ent_ksc
      -> 422 (agen uji memakai 'qty'; skema minta 'quantity'). Harus 403.
  H1  AR aging: banner entitas (sudah ada di sumber; build sempat basi)
  L7  audit-logs RBAC
"""
import asyncio
import json
import os

import httpx

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
PWD = "demo12345"
results = []


def rec(code, name, ok, detail=""):
    results.append((code, name, ok, detail))
    print(f"{'✅' if ok else '❌'} {code} — {name}")
    if detail:
        print(f"     {detail}")


async def login(email):
    """Login pakai klien SEKALI PAKAI.

    PENTING: `dependencies.extract_token` MENGUTAMAKAN cookie `session_token`
    di atas header Bearer. Kalau satu `AsyncClient` dipakai untuk login banyak
    user, cookie login terakhir menimpa semuanya dan SEMUA permintaan berjalan
    sebagai user terakhir — inilah sumber "403 palsu" pada iteration_210.
    """
    async with httpx.AsyncClient(timeout=60.0) as tmp:
        r = await tmp.post(f"{BASE}/api/auth/login", json={"email": email, "password": PWD})
        r.raise_for_status()
        d = r.json()
        return d["token"], d


async def main():
    # cookies=None → klien tidak menyimpan cookie apa pun; identitas murni dari Bearer.
    async with httpx.AsyncClient(timeout=60.0, cookies=None) as cl:
        adm_tok, adm = await login("admin@kainnusantara.id")
        s3_tok, s3 = await login("sales3@kainnusantara.id")
        s1_tok, _ = await login("sales@kainnusantara.id")
        wh_tok, _ = await login("warehouse@kainnusantara.id")
        A = {"Authorization": f"Bearer {adm_tok}"}
        S3 = {"Authorization": f"Bearer {s3_tok}"}
        S1 = {"Authorization": f"Bearer {s1_tok}"}
        WH = {"Authorization": f"Bearer {wh_tok}"}

        # ── M1: settings/effective untuk entitas non-PKP ────────────────────
        r = await cl.get(f"{BASE}/api/settings/effective",
                         headers={**A, "X-Entity-Id": "ent_kanda"})
        tax = (r.json() or {}).get("tax", {})
        rec("M1a", "settings/effective (header X-Entity-Id: ent_kanda) → tax.is_pkp=false & tax.ppn_rate=0",
            r.status_code == 200 and tax.get("is_pkp") is False and float(tax.get("ppn_rate", -1)) == 0.0,
            f"HTTP {r.status_code} · is_pkp={tax.get('is_pkp')} · ppn_rate={tax.get('ppn_rate')}")

        r = await cl.get(f"{BASE}/api/settings/effective?entity_id=ent_kanda", headers=A)
        tax = (r.json() or {}).get("tax", {})
        rec("M1b", "settings/effective (?entity_id=ent_kanda) → tax.is_pkp=false & tax.ppn_rate=0",
            r.status_code == 200 and tax.get("is_pkp") is False and float(tax.get("ppn_rate", -1)) == 0.0,
            f"HTTP {r.status_code} · is_pkp={tax.get('is_pkp')} · ppn_rate={tax.get('ppn_rate')}")

        r = await cl.get(f"{BASE}/api/settings/effective",
                         headers={**A, "X-Entity-Id": "ent_ksc"})
        tax_ksc = (r.json() or {}).get("tax", {})
        rec("M1c", "KSC (PKP) BERBEDA dari Kanda → tax.is_pkp=true & ppn_rate>0",
            tax_ksc.get("is_pkp") is True and float(tax_ksc.get("ppn_rate", 0)) > 0,
            f"KSC is_pkp={tax_ksc.get('is_pkp')} ppn_rate={tax_ksc.get('ppn_rate')}")

        # ── M2: preview-allocation lintas entitas harus 403 ─────────────────
        prods = (await cl.get(f"{BASE}/api/products?limit=5", headers=S3)).json()
        plist = prods.get("items", prods) if isinstance(prods, dict) else prods
        pid = plist[0]["id"] if plist else ""
        body_ksc = {"entity_id": "ent_ksc", "items": [
            {"product_id": pid, "quantity": 100, "unit": "yard"}]}
        r = await cl.post(f"{BASE}/api/sales-orders/preview-allocation",
                          headers=S3, json=body_ksc)
        rec("M2a", "sales3 preview-allocation entity_id=ent_ksc → 403 (bukan 422)",
            r.status_code == 403,
            f"HTTP {r.status_code} · {str(r.text)[:200]}")

        body_own = {"entity_id": "ent_kanda", "items": [
            {"product_id": pid, "quantity": 100, "unit": "yard"}]}
        r = await cl.post(f"{BASE}/api/sales-orders/preview-allocation",
                          headers=S3, json=body_own)
        ok = r.status_code == 200
        detail = ""
        if ok:
            d = r.json()
            lines = d.get("lines") or d.get("items") or []
            detail = json.dumps(lines)[:300]
        rec("M2b", "sales3 preview-allocation entitas SENDIRI (ent_kanda) → 200",
            ok, f"HTTP {r.status_code} · {detail}")

        # entity_id kosong → harus jatuh ke entitas aktif sales3 (Kanda), bukan default KSC
        r = await cl.post(f"{BASE}/api/sales-orders/preview-allocation",
                          headers=S3, json={"items": [{"product_id": pid, "quantity": 100, "unit": "yard"}]})
        rec("M2c", "sales3 preview-allocation TANPA entity_id → 200 (pakai konteks Kanda)",
            r.status_code == 200, f"HTTP {r.status_code}")

        # ── L7: audit logs RBAC ─────────────────────────────────────────────
        for name, hdr, want in [("sales", S1, 403), ("warehouse", WH, 403),
                                ("sales3", S3, 403), ("admin", A, 200)]:
            r = await cl.get(f"{BASE}/api/audit-logs?limit=5", headers=hdr)
            rec(f"L7-{name}", f"GET /api/audit-logs sebagai {name} → {want}",
                r.status_code == want, f"HTTP {r.status_code}")

        # ── H1: AR aging per entitas ────────────────────────────────────────
        tot = {}
        for ent in ("ent_ksc", "ent_kanda"):
            r = await cl.get(f"{BASE}/api/ar/aging", headers={**A, "X-Entity-Id": ent},
                             params={"entity_id": ent})
            d = r.json()
            tot[ent] = (d.get("entity_id"), d.get("entity_name"),
                        (d.get("totals") or {}).get("total"), d.get("is_consolidated"))
            rec(f"H1-{ent}", f"AR aging {ent} → entity_id/entity_name terisi",
                r.status_code == 200 and d.get("entity_id") == ent and bool(d.get("entity_name")),
                f"HTTP {r.status_code} · {tot[ent]}")
        rec("H1-diff", "Total piutang KSC ≠ Kanda (tidak lagi tercampur)",
            tot["ent_ksc"][2] != tot["ent_kanda"][2],
            f"KSC={tot['ent_ksc'][2]} · Kanda={tot['ent_kanda'][2]}")

        r = await cl.get(f"{BASE}/api/ar/aging", headers=A)
        d = r.json()
        rec("H1-all", "AR aging mode gabungan → is_consolidated=true + label entitas",
            r.status_code == 200 and bool(d.get("entity_name")),
            f"is_consolidated={d.get('is_consolidated')} entity_name={d.get('entity_name')} total={(d.get('totals') or {}).get('total')}")

    print("\n" + "=" * 72)
    bad = [r for r in results if not r[2]]
    print(f"HASIL: {len(results) - len(bad)}/{len(results)} LULUS")
    for c, n, _, d in bad:
        print(f"  ❌ {c} — {n} :: {d}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
