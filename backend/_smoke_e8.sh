#!/usr/bin/env bash
# Smoke cepat E-8 (bukan POC) — dipakai saat membangun. POC resmi: test_core_e8_desk_poc.py
API=http://localhost:8001/api
tok () { curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
         -d "{\"email\":\"$1\",\"password\":\"demo12345\"}" | python -c 'import sys,json;print(json.load(sys.stdin).get("token",""))'; }

SA=$(tok salesadmin@kainnusantara.id)
FI=$(tok finance@kainnusantara.id)
S2=$(tok sales2@kainnusantara.id)
S1=$(tok sales@kainnusantara.id)
echo "token sales_admin=${SA:0:10} finance=${FI:0:10} sales2=${S2:0:10}"

show_desk () {
python - "$1" <<'PY'
import sys, json
d = json.load(sys.stdin)
print("  queues:", len(d.get("queues", [])), "| open_items:", d.get("totals", {}).get("open_items"))
for q in d.get("queues", []):
    print("   {:22s} n={:3d} nilai={:>16,.0f} tertua={}h".format(
        q["id"], q["count"], q["total_value"], q["oldest_age_days"]))
PY
}

echo "--- Meja Admin Sales ---"
curl -s "$API/sales-admin/desk" -H "Authorization: Bearer $SA" -H "X-Entity-Id: ent_ksc" | show_desk

echo "--- Meja Finance ---"
curl -s "$API/finance/desk" -H "Authorization: Bearer $FI" -H "X-Entity-Id: ent_ksc" | show_desk

echo "--- pemisahan meja ---"
curl -s -o /dev/null -w "  finance -> /sales-admin/desk : %{http_code} (harus 403)\n" \
  "$API/sales-admin/desk" -H "Authorization: Bearer $FI" -H "X-Entity-Id: ent_ksc"
curl -s -o /dev/null -w "  sales   -> /finance/desk     : %{http_code} (harus 403)\n" \
  "$API/finance/desk" -H "Authorization: Bearer $S2" -H "X-Entity-Id: ent_ksc"
curl -s -o /dev/null -w "  s.admin -> /finance/desk     : %{http_code} (harus 403)\n" \
  "$API/finance/desk" -H "Authorization: Bearer $SA" -H "X-Entity-Id: ent_ksc"

echo "--- US11 kepemilikan SO ---"
for who in "sales@:$S1" "sales2@:$S2" "salesadmin@:$SA"; do
  n="${who%%:*}"; t="${who#*:}"
  cnt=$(curl -s "$API/sales-orders" -H "Authorization: Bearer $t" -H "X-Entity-Id: ent_ksc" | python -c 'import sys,json;print(len(json.load(sys.stdin)))')
  sm=$(curl -s "$API/sales-orders/stats/summary" -H "Authorization: Bearer $t" -H "X-Entity-Id: ent_ksc" | python -c 'import sys,json;print(json.load(sys.stdin).get("total_orders"))')
  echo "  $n daftar=$cnt ringkasan=$sm"
done
echo -n "  sales2 buka SO Ayu (so_001) : "
curl -s -o /dev/null -w "%{http_code} (harus 403)\n" "$API/sales-orders/so_001" -H "Authorization: Bearer $S2" -H "X-Entity-Id: ent_ksc"
echo -n "  sales2 buka SO sendiri (so_008) : "
curl -s -o /dev/null -w "%{http_code} (harus 200)\n" "$API/sales-orders/so_008" -H "Authorization: Bearer $S2" -H "X-Entity-Id: ent_ksc"

echo "--- US12 perjalanan pesanan ---"
curl -s "$API/sales-orders/so_001/journey" -H "Authorization: Bearer $S1" -H "X-Entity-Id: ent_ksc" | python - <<'PY'
import sys, json
d = json.load(sys.stdin)
print("  ", d.get("order_number"), "|", d.get("current_label"), "|", d.get("progress"))
for s in d.get("steps", []):
    print("    ", "v" if s["done"] else ".", s["label"], "|", s["detail"][:52])
print("   pemenuhan:", d.get("fulfillment", {}).get("sentence", "")[:90])
PY

echo "--- US16 pilihan pemenuhan SO-0009 ---"
SO9=$(python - <<'PY'
import asyncio, sys
sys.path.insert(0, "/app/backend")
from db import db
async def m():
    o = await db.sales_orders.find_one({"number": "SO-0009"}, {"_id": 0, "id": 1})
    print((o or {}).get("id", ""))
asyncio.run(m())
PY
)
echo "  SO-0009 id=$SO9"
curl -s "$API/sales-admin/orders/$SO9/fulfillment" -H "Authorization: Bearer $SA" -H "X-Entity-Id: ent_ksc" | python - <<'PY'
import sys, json
d = json.load(sys.stdin)
if "options" not in d:
    print("  GAGAL:", str(d)[:300]); raise SystemExit
print("  kekurangan:", [(s["product_name"], s["backorder_qty"], s["unit"]) for s in d["shortages"]])
for k, v in d["options"].items():
    print(f"   {k:9s} tersedia={v['available']} alasan={v.get('reason','')[:60]}")
for c in d["options"]["interco"]["candidates"]:
    print("     kandidat:", c["entity_name"], "cukup=", c["enough"],
          [(l["product_name"][:18], l["available"]) for l in c["lines"]])
PY

echo "--- verifikasi pratinjau SO-0009 ---"
curl -s "$API/sales-orders/$SO9/verification" -H "Authorization: Bearer $SA" -H "X-Entity-Id: ent_ksc" | python - <<'PY'
import sys, json
d = json.load(sys.stdin)
print("  ready=", d.get("ready"), "| blocking=", d.get("blocking_gaps"), "| warn=", d.get("warnings"))
for c in d.get("checks", []):
    print("    ", "v" if c["ok"] else "x", c["label"], "|", c["detail"][:50])
PY

echo "--- E8.3 layar sales ---"
curl -s -o /dev/null -w "  sales -> /hr/visits/mine : %{http_code} (harus 200)\n" "$API/hr/visits/mine" -H "Authorization: Bearer $S1"
curl -s -o /dev/null -w "  sales -> /wms/tasks      : %{http_code} (harus 403)\n" "$API/wms/tasks" -H "Authorization: Bearer $S1"
echo "--- E8.5 sales-users ikut entitas ---"
for e in ent_ksc ent_kanda; do
  echo -n "  $e : "
  curl -s "$API/sales-users" -H "Authorization: Bearer $SA" -H "X-Entity-Id: $e" | python -c 'import sys,json;print([u["name"] for u in json.load(sys.stdin)])'
done
