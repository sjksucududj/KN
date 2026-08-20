#!/usr/bin/env python3
"""VERIFIKASI CAKUPAN ANTAR-ENTITAS (FASE G-6/G-6b) — hanya baca."""
import json
import requests

BASE = "http://localhost:8001/api"
A, B = "ent_ksc", "ent_kanda"


def login(e, p="demo12345"):
    return requests.post(f"{BASE}/auth/login", json={"email": e, "password": p}, timeout=20).json()["token"]


TADM = login("admin@kainnusantara.id")
TSA = login("sales@kainnusantara.id")       # sales KSC
TSB = login("sales3@kainnusantara.id")      # sales Kanda
TWH = login("warehouse@kainnusantara.id")


def get(path, tok=TADM, ent=None):
    h = {"Authorization": f"Bearer {tok}"}
    if ent:
        h["X-Entity-Id"] = ent
    r = requests.get("http://localhost:8001" + path, headers=h, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


def rows(b):
    if isinstance(b, list):
        return b
    if isinstance(b, dict):
        for k in ("items", "rows", "transactions", "data", "accounts", "settlements", "returns", "eliminations"):
            if isinstance(b.get(k), list):
                return b[k]
    return []


print("=" * 80)
print(" 1. META & KONFIGURASI ANTAR-ENTITAS")
print("=" * 80)
st, meta = get("/api/interco/meta")
print(f"  [{st}] meta keys: {list(meta.keys()) if isinstance(meta, dict) else meta}")
if isinstance(meta, dict):
    print("  ", json.dumps(meta, ensure_ascii=False)[:1200])

st, reg = get("/api/config/registry?group=antar_entitas")
ents = [e for e in (reg or {}).get("entries", []) if e.get("group") == "antar_entitas"]
print(f"\n  kunci konfigurasi grup 'antar_entitas': {len(ents)}")
for e in ents:
    print(f"    - {e['key']:44s} scopes={e.get('scopes')} default={e.get('default')!r}")

print("\n" + "=" * 80)
print(" 2. TRANSAKSI ANTAR-ENTITAS (dokumen kembar)")
print("=" * 80)
for label, ent in [("KSC", A), ("KANDA", B), ("ALL", "all")]:
    st, b = get("/api/interco/transactions", TADM, ent)
    rs = rows(b)
    print(f"  {label:6s} [{st}] {len(rs)} dokumen")
    for r in rs:
        print(f"     {str(r.get('number')):16s} role={str(r.get('role')):7s} status={str(r.get('status')):10s} "
              f"entity={str(r.get('entity_id')):11s} pair={str(r.get('pair_id'))[:12]:14s} "
              f"total={r.get('grand_total')} settled={r.get('settled_amount')} "
              f"pricing={r.get('pricing_mode')} ppn={r.get('tax_amount')} trf={r.get('warehouse_transfer_code')}")

print("\n  --- ISOLASI: apakah sales melihat sisi PT lain? ---")
for label, tok, own in [("sales KSC", TSA, A), ("sales KANDA", TSB, B)]:
    st, b = get("/api/interco/transactions", tok)
    rs = rows(b)
    foreign = [r for r in rs if r.get("entity_id") != own]
    print(f"  {label:12s} [{st}] {len(rs)} dokumen · milik PT lain = {len(foreign)}")
    if rs:
        print("      nomor:", [r.get("number") for r in rs])

print("\n" + "=" * 80)
print(" 3. SALDO PASANGAN PT (IC-AR / IC-AP) & PELUNASAN")
print("=" * 80)
for label, ent in [("KSC", A), ("KANDA", B)]:
    st, b = get("/api/interco/accounts", TADM, ent)
    for r in rows(b):
        print(f"  {label:6s} {r.get('from_entity_name')} → {r.get('to_entity_name')} "
              f"role={r.get('role')} terbuka={r.get('open_count')} bruto={r.get('gross_amount')} "
              f"lunas={r.get('settled_amount')} sisa={r.get('outstanding')} umur={r.get('aging_days')}h "
              f"ingatkan={r.get('reminder_active')}")
st, b = get("/api/interco/settlements", TADM, "all")
print(f"\n  settlement: {len(rows(b))}")
for r in rows(b):
    print(f"    {r.get('number')} metode={r.get('method')} bayar={r.get('payer_entity_name')} → "
          f"{r.get('payee_entity_name')} total={r.get('total_applied')} status={r.get('status')} "
          f"applied={len(r.get('applied') or [])} dokumen")
st, b = get("/api/interco/reminders", TADM, "all")
print(f"  pengingat pelunasan: [{st}] {json.dumps(b, ensure_ascii=False)[:300]}")

print("\n" + "=" * 80
      )
print(" 4. HARGA INTERNAL (kontrak) & MARGIN")
print("=" * 80)
st, b = get("/api/interco/contracts", TADM, A)
rs = rows(b)
print(f"  kontrak harga internal (KSC): [{st}] {len(rs)}")
for r in rs[:6]:
    print("    ", json.dumps({k: r.get(k) for k in ("id", "number", "partner_kind", "partner_id",
          "partner_name", "product_name", "price", "unit_price", "valid_from", "valid_until", "status")},
          ensure_ascii=False)[:260])
st, b = get("/api/interco/margin-report", TADM, "all")
print(f"\n  margin-report: [{st}] {json.dumps(b, ensure_ascii=False)[:500]}")
st, b = get("/api/interco/margin-by-product", TADM, "all")
print(f"  margin-by-product: [{st}] {json.dumps(b, ensure_ascii=False)[:400]}")

print("\n" + "=" * 80)
print(" 5. PAJAK INTERNAL (faktur pajak antar-PT)")
print("=" * 80)
st, b = get("/api/interco/transactions", TADM, "all")
for r in rows(b):
    tid = r.get("id")
    st2, t = get(f"/api/interco/transactions/{tid}/tax-invoice", TADM, r.get("entity_id"))
    if st2 == 200 and t:
        print(f"  {r.get('number'):16s} → {json.dumps(t, ensure_ascii=False)[:260]}")
    else:
        print(f"  {r.get('number'):16s} → [{st2}] {json.dumps(t, ensure_ascii=False)[:120] if t else ''}")

print("\n" + "=" * 80)
print(" 6. RETUR ANTAR-PT")
print("=" * 80)
st, b = get("/api/interco/returns", TADM, "all")
print(f"  [{st}] {len(rows(b))} retur")
for r in rows(b):
    print("    ", json.dumps({k: r.get(k) for k in ("number", "entity_id", "role", "status",
          "pair_id", "qty_total", "grand_total", "warehouse_transfer_code", "tax_status")}, ensure_ascii=False)[:300])
st, b = get("/api/interco/returns/meta")
print("  meta retur:", json.dumps(b, ensure_ascii=False)[:400])

print("\n" + "=" * 80)
print(" 7. JEMBATAN GUDANG (barang fisik berpindah)")
print("=" * 80)
st, b = get("/api/transfers?entity_id=all", TADM, "all")
for r in rows(b):
    print("    ", json.dumps({k: r.get(k) for k in ("code", "entity_id", "status", "interco_pair_id",
          "from_warehouse_name", "to_warehouse_name", "transfer_kind", "owner_change")}, ensure_ascii=False)[:300])

print("\n" + "=" * 80)
print(" 8. KONSOLIDASI GRUP & ELIMINASI MARGIN")
print("=" * 80)
st, b = get("/api/finance/consolidation/summary", TADM, "all")
print(f"  summary: [{st}] {json.dumps(b, ensure_ascii=False)[:900]}")
st, b = get("/api/finance/consolidation/eliminations", TADM, "all")
rs = rows(b)
print(f"\n  eliminasi: [{st}] {len(rs)}")
for r in rs:
    print("    ", json.dumps({k: r.get(k) for k in ("id", "kind", "label", "amount", "auto_generated",
          "source_g6_pair_id", "period")}, ensure_ascii=False)[:300])
st, b = get("/api/finance/consolidation/ic-candidates", TADM, "all")
print(f"\n  kandidat eliminasi manual: [{st}] {json.dumps(b, ensure_ascii=False)[:400]}")

print("\n" + "=" * 80)
print(" 9. RBAC ANTAR-ENTITAS")
print("=" * 80)
for label, tok in [("sales KSC", TSA), ("gudang KSC", TWH)]:
    for path in ["/api/interco/transactions", "/api/interco/accounts", "/api/interco/settlements",
                 "/api/interco/margin-report", "/api/finance/consolidation/summary"]:
        st, _ = get(path, tok)
        print(f"  {label:11s} GET {path:44s} → {st}")

print("\n" + "=" * 80)
print(" 10. KAS/BANK TINGKAT GRUP (entity_id='all') — apakah memang disengaja?")
print("=" * 80)
st, b = get("/api/bank-accounts?entity_id=all", TADM, "all")
for r in rows(b):
    print("    bank:", json.dumps({k: r.get(k) for k in ("id", "name", "bank_name", "entity_id",
          "account_number", "current_balance")}, ensure_ascii=False)[:220])
st, b = get("/api/cash-transactions?entity_id=all", TADM, "all")
rs = rows(b)
grp = [r for r in rs if r.get("entity_id") == "all"]
print(f"    kas: {len(rs)} transaksi · ber-entity_id 'all' (kas besar grup) = {len(grp)}")
for r in grp[:4]:
    print("      ", json.dumps({k: r.get(k) for k in ("number", "entity_id", "kind", "amount",
          "description")}, ensure_ascii=False)[:200])
