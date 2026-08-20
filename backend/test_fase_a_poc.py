#!/usr/bin/env python3
"""test_fase_a_poc.py — POC HTTP TUNGGAL untuk **Fase A: Fondasi Domain Tekstil**.

Rujukan: `docs/KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md` (PS-01, PS-02, PS-03,
PS-09, PS-15 · keputusan §11 + D-19…D-23) & `docs/KN_19_PLAN_FASE_A_FONDASI_DOMAIN.md`.

Membuktikan (lewat HTTP nyata, bukan unit test) seluruh user story Fase A:

  US-1  Registry enum tersedia satu pintu (`GET /api/enums`) — FE tidak hardcode (R7)
  US-2  Stage chain lengkap: `yarn → grey → pfd|pfp → finished` (+remnant/byproduct)
  US-3  Transisi ilegal DITOLAK 400 berbahasa Indonesia; `pre_treatment` butuh target_use
  US-4  `fabric_type` WAJIB sejak stage yarn (D-02) — produk tanpa itu ditolak
  US-5  GSM + lebar WAJIB ≥ grey untuk woven (D-22); knit hanya peringatan (non-blocking)
  US-6  Stage `yarn` wajib `yarn_count`; produk PFD/PFP bisa dibuat (PS-01)
  US-7  Grade hanya nilai enum A|A1|A2|B|BS dengan rank (D-01); nilai bebas ditolak
  US-8  PO WAJIB memilih grade per item (D-19) — tanpa grade → 400
  US-9  Grade roll berubah hanya via inspeksi QC / override manager beralasan (D-23)
        + riwayat `grade_history` (before → after) terbaca lewat API
  US-10 Input desimal `10,5` diterima di produk, PR, PO, makloon, inspeksi, transfer (PS-15)
  US-11 Migrasi idempoten: dijalankan dua kali → `changed=0`, invarian bersih
  US-12 Varian dari template mewarisi `fabric_type` & tetap lulus validasi domain

Jalankan (backend harus hidup):
    cd /app/backend && python test_fase_a_poc.py
Keluar 0 = seluruh POC PASS.
"""
import os
import subprocess
import sys

import requests

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001/api")
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
MANAGER = {"email": "manager@kainnusantara.id", "password": "demo12345"}
WAREHOUSE = {"email": "warehouse@kainnusantara.id", "password": "demo12345"}

PASS, FAIL = [], []
SUFFIX = os.urandom(3).hex().upper()


def check(story: str, cond: bool, detail: str = "") -> bool:
    (PASS if cond else FAIL).append(f"{story} — {detail}")
    print(f"{'✅' if cond else '❌'} {story}" + (f"  ·  {detail}" if detail else ""))
    return cond


def login(cred):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json=cred, timeout=30)
    r.raise_for_status()
    token = r.json().get("token") or r.json().get("session_token") or ""
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def make_product(s, **over):
    body = {"sku": f"POC-{SUFFIX}-{os.urandom(2).hex().upper()}", "name": "POC Produk",
            "category": "Tenun", "base_unit": "meter", "price": 100000}
    body.update(over)
    return s.post(f"{BASE}/products", json=body, timeout=30)


# ─────────────────────────────────────────────────────────────────────────────
def us1_registry(s):
    print("\n── US-1 · Registry enum satu pintu (R7) ──────────────────────────")
    r = s.get(f"{BASE}/enums", timeout=30)
    check("US-1a GET /api/enums 200", r.status_code == 200, f"HTTP {r.status_code}")
    data = r.json() if r.status_code == 200 else {}
    enums = data.get("enums", {})
    wajib = ["grade", "stage", "fabric_type", "process_type", "target_use", "tariff_basis"]
    check("US-1b enum inti tersedia", all(k in enums for k in wajib),
          f"ada: {sorted(enums)[:8]}…")
    grades = [v["value"] for v in enums.get("grade", {}).get("values", [])]
    ranks = [v["rank"] for v in enums.get("grade", {}).get("values", [])]
    check("US-1c urutan grade D-01 (A→A1→A2→B→BS) + rank 1..5",
          grades == ["A", "A1", "A2", "B", "BS"] and ranks == [1, 2, 3, 4, 5], f"{grades} {ranks}")
    r2 = s.get(f"{BASE}/enums/grade", timeout=30)
    check("US-1d GET /api/enums/{name}", r2.status_code == 200 and r2.json()["name"] == "grade")
    r3 = s.get(f"{BASE}/enums/tidak_ada", timeout=30)
    check("US-1e enum tak dikenal → 404", r3.status_code == 404, f"HTTP {r3.status_code}")
    anon = requests.get(f"{BASE}/enums", timeout=30)
    check("US-1f tanpa login → 401 (INV-AUTH-01)", anon.status_code == 401,
          f"HTTP {anon.status_code}")
    return data


def us2_us3_transitions(s, snap):
    print("\n── US-2/US-3 · Stage chain & transisi dikunci server (PS-01) ──────")
    stages = [v["value"] for v in snap.get("enums", {}).get("stage", {}).get("values", [])]
    check("US-2a stage lengkap termasuk pfd/pfp/remnant/byproduct",
          stages == ["yarn", "grey", "pfd", "pfp", "finished", "remnant", "byproduct"], str(stages))
    r = s.get(f"{BASE}/enums/stage-transitions", timeout=30)
    trans = r.json().get("transitions", []) if r.status_code == 200 else []
    pairs = {(t["from_stage"], t["process_type"], t["target_use"], t["to_stage"]) for t in trans}
    check("US-2b yarn --tenun--> grey (woven)", ("yarn", "tenun", None, "grey") in pairs)
    check("US-2c yarn --rajut--> grey (knit)", ("yarn", "rajut", None, "grey") in pairs)
    check("US-2d grey --pre_treatment(dye)--> pfd (D-03)",
          ("grey", "pre_treatment", "dye", "pfd") in pairs)
    check("US-2e grey --pre_treatment(print)--> pfp (D-03)",
          ("grey", "pre_treatment", "print", "pfp") in pairs)
    check("US-2f pfd --celup--> finished", ("pfd", "celup", None, "finished") in pairs)
    check("US-2g pfp --printing--> finished", ("pfp", "printing", None, "finished") in pairs)

    ok = s.post(f"{BASE}/enums/stage-transitions/validate",
                json={"from_stage": "grey", "process_type": "pre_treatment",
                      "target_use": "print"}, timeout=30)
    check("US-3a transisi sah → 200 + to_stage=pfp",
          ok.status_code == 200 and ok.json().get("to_stage") == "pfp",
          f"HTTP {ok.status_code} {ok.json() if ok.status_code == 200 else ok.text[:120]}")

    bad = s.post(f"{BASE}/enums/stage-transitions/validate",
                 json={"from_stage": "yarn", "process_type": "printing"}, timeout=30)
    msg = (bad.json() or {}).get("detail", "") if bad.status_code == 400 else bad.text
    check("US-3b yarn --printing--> ? DITOLAK 400 (pesan Indonesia)",
          bad.status_code == 400 and "tidak sah" in msg.lower(), f"HTTP {bad.status_code}: {msg[:110]}")

    ambig = s.post(f"{BASE}/enums/stage-transitions/validate",
                   json={"from_stage": "grey", "process_type": "pre_treatment"}, timeout=30)
    amsg = (ambig.json() or {}).get("detail", "")
    check("US-3c pre_treatment tanpa target_use → 400 ambigu (minta dye/print)",
          ambig.status_code == 400 and "target_use" in amsg, f"{amsg[:130]}")

    wrong_fabric = s.post(f"{BASE}/enums/stage-transitions/validate",
                          json={"from_stage": "yarn", "process_type": "tenun",
                                "fabric_type": "knit"}, timeout=30)
    check("US-3d tenun untuk knit → 400 (jalur woven saja)",
          wrong_fabric.status_code == 400,
          f"HTTP {wrong_fabric.status_code}: {(wrong_fabric.json() or {}).get('detail', '')[:100]}")


def us4_us7_product_rules(s):
    print("\n── US-4…US-7 · Validasi domain produk (PS-02/PS-03/PS-09) ────────")
    r = make_product(s, stage="grey", gramasi=200, lebar=1.5, grade="A")
    check("US-4a produk stage grey TANPA fabric_type ditolak 400",
          r.status_code == 400 and "Jenis kain" in r.text, f"HTTP {r.status_code}: {r.text[:130]}")

    r = make_product(s, stage="yarn", fabric_type="woven")
    check("US-6a produk stage yarn TANPA yarn_count ditolak 400",
          r.status_code == 400 and "benang" in r.text.lower(), f"HTTP {r.status_code}: {r.text[:130]}")

    r = make_product(s, stage="yarn", fabric_type="woven", yarn_count="30s",
                     yarn_count_system="Ne", base_unit="kg")
    check("US-6b produk yarn lengkap tersimpan", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:130]}")

    r = make_product(s, stage="grey", fabric_type="woven", gramasi=0, lebar=1.5)
    check("US-5a woven ≥ grey TANPA GSM ditolak 400 (D-22)",
          r.status_code == 400 and "gsm" in r.text.lower(), f"HTTP {r.status_code}: {r.text[:130]}")

    r = make_product(s, stage="grey", fabric_type="knit", base_unit="kg")
    warn = (r.json() or {}).get("domain_warnings", []) if r.status_code == 200 else []
    check("US-5b knit ≥ grey TANPA GSM DITERIMA + peringatan (D-22)",
          r.status_code == 200 and len(warn) >= 1, f"HTTP {r.status_code} · peringatan={len(warn)}")
    knit_id = (r.json() or {}).get("id", "") if r.status_code == 200 else ""
    check("US-5c produk knit ditandai needs_review",
          bool((r.json() or {}).get("needs_review")) if r.status_code == 200 else False)

    for stage in ("pfd", "pfp"):
        r = make_product(s, stage=stage, fabric_type="woven", gramasi=180, lebar=1.2)
        check(f"US-6c produk stage {stage.upper()} bisa dibuat (PS-01)", r.status_code == 200,
              f"HTTP {r.status_code}: {r.text[:110]}")

    r = make_product(s, stage="finished", fabric_type="woven", gramasi=180, lebar=1.2, grade="Z9")
    check("US-7a grade bebas 'Z9' ditolak 400", r.status_code == 400 and "Grade" in r.text,
          f"HTTP {r.status_code}: {r.text[:120]}")

    r = make_product(s, stage="finished", fabric_type="woven", gramasi=180, lebar=1.2, grade="BS")
    check("US-7b grade 'BS' (barang sortir) diterima", r.status_code == 200,
          f"HTTP {r.status_code}: {r.text[:110]}")

    r = make_product(s, stage="Greige", fabric_type="Tenun", gramasi=180, lebar=1.2, grade="c")
    body = r.json() if r.status_code == 200 else {}
    check("US-7c alias dinormalisasi (Greige→grey, Tenun→woven, c→BS)",
          r.status_code == 200 and body.get("stage") == "grey"
          and body.get("fabric_type") == "woven" and body.get("grade") == "BS",
          f"HTTP {r.status_code} · {body.get('stage')}/{body.get('fabric_type')}/{body.get('grade')}")

    good = make_product(s, stage="finished", fabric_type="woven", gramasi=180, lebar=1.2, grade="A")
    pid = (good.json() or {}).get("id", "")
    bad_patch = s.patch(f"{BASE}/products/{pid}", json={"data": {"stage": "grey", "gramasi": 0}},
                        timeout=30)
    check("US-4b PATCH yang membuat produk cacat ditolak 400",
          bad_patch.status_code == 400, f"HTTP {bad_patch.status_code}: {bad_patch.text[:110]}")
    ok_patch = s.patch(f"{BASE}/products/{pid}", json={"data": {"grade": "A2"}}, timeout=30)
    check("US-7d PATCH grade ke nilai enum berhasil",
          ok_patch.status_code == 200 and ok_patch.json().get("grade") == "A2",
          f"HTTP {ok_patch.status_code}")
    return pid, knit_id


def us8_po_grade(s, product_id):
    print("\n── US-8 · PO wajib memilih grade (D-19) ──────────────────────────")
    wh = s.get(f"{BASE}/warehouses", timeout=30).json()
    wh_id = (wh[0]["id"] if isinstance(wh, list) and wh else "")
    sup = s.get(f"{BASE}/suppliers", timeout=30).json()
    sup_list = sup.get("items", sup) if isinstance(sup, dict) else sup
    sup_id = (sup_list[0]["id"] if sup_list else "")
    base = {"supplier_id": sup_id, "warehouse_id": wh_id, "created_by": "POC",
            "expected_delivery_date": "2026-08-30"}

    r = s.post(f"{BASE}/purchase-orders",
               json={**base, "items": [{"product_id": product_id, "quantity": 100,
                                        "unit": "meter", "price": 50000}]}, timeout=60)
    check("US-8a PO tanpa expected_grade ditolak 400 (tanpa default)",
          r.status_code == 400 and "grade" in r.text.lower(), f"HTTP {r.status_code}: {r.text[:130]}")

    r = s.post(f"{BASE}/purchase-orders",
               json={**base, "items": [{"product_id": product_id, "quantity": "10,5",
                                        "unit": "meter", "price": "50.000,25",
                                        "expected_grade": "A1"}]}, timeout=60)
    po = r.json() if r.status_code == 200 else {}
    item = (po.get("items") or [{}])[0]
    check("US-8b PO dengan grade dipilih tersimpan + tercatat per item",
          r.status_code == 200 and item.get("expected_grade") == "A1",
          f"HTTP {r.status_code} · grade={item.get('expected_grade')} src={item.get('expected_grade_source')}")
    check("US-10a PO menerima desimal koma (10,5 & 50.000,25)",
          abs(float(item.get("quantity", 0)) - 10.5) < 1e-6
          and abs(float(item.get("price", 0)) - 50000.25) < 1e-6,
          f"qty={item.get('quantity')} price={item.get('price')}")

    r = s.post(f"{BASE}/purchase-orders",
               json={**base, "items": [{"product_id": product_id, "quantity": 5,
                                        "unit": "meter", "price": 1000,
                                        "expected_grade": "Z"}]}, timeout=60)
    check("US-8c grade tak dikenal di PO ditolak 400", r.status_code == 400,
          f"HTTP {r.status_code}: {r.text[:110]}")


def us9_grade_governance(admin, manager, warehouse):
    print("\n── US-9 · Tata kelola grade roll (PS-09/D-23) ────────────────────")
    rolls = admin.get(f"{BASE}/inventory/rolls", timeout=30).json()
    rolls = rolls.get("items", rolls) if isinstance(rolls, dict) else rolls
    roll = next((r for r in rolls if r.get("id")), None)
    if not roll:
        return check("US-9 prasyarat roll tersedia", False, "tidak ada roll di DB")
    rid = roll["id"]

    r = manager.post(f"{BASE}/inventory/rolls/{rid}/grade-override",
                     json={"grade": "B", "reason": ""}, timeout=30)
    check("US-9a override TANPA alasan ditolak 400 (D-23)",
          r.status_code == 400 and "alasan" in r.text.lower(), f"HTTP {r.status_code}: {r.text[:110]}")

    r = warehouse.post(f"{BASE}/inventory/rolls/{rid}/grade-override",
                       json={"grade": "B", "reason": "coba-coba"}, timeout=30)
    check("US-9b role warehouse TIDAK boleh override (403)", r.status_code == 403,
          f"HTTP {r.status_code}")

    r = manager.post(f"{BASE}/inventory/rolls/{rid}/grade-override",
                     json={"grade": "Q", "reason": "salah input"}, timeout=30)
    check("US-9c grade di luar enum ditolak 400", r.status_code == 400, f"HTTP {r.status_code}")

    r = manager.post(f"{BASE}/inventory/rolls/{rid}/grade-override",
                     json={"grade": "A2", "reason": "Koreksi salah input inspeksi awal"},
                     timeout=30)
    body = r.json() if r.status_code == 200 else {}
    check("US-9d manager override dengan alasan berhasil",
          r.status_code == 200 and body.get("grade_after") == "A2",
          f"HTTP {r.status_code} · {body.get('grade_before')}→{body.get('grade_after')}")

    h = manager.get(f"{BASE}/inventory/rolls/{rid}/grade-history", timeout=30)
    hist = h.json().get("history", []) if h.status_code == 200 else []
    last = hist[-1] if hist else {}
    check("US-9e riwayat grade terbaca (before→after, sumber, alasan, aktor)",
          h.status_code == 200 and last.get("source") == "manager_override"
          and last.get("grade_after") == "A2" and bool(last.get("reason"))
          and bool(last.get("changed_by")),
          f"entri={len(hist)} · {last.get('grade_before')}→{last.get('grade_after')} "
          f"oleh {last.get('changed_by')}")

    thr = admin.get(f"{BASE}/qc/grade-thresholds", timeout=30).json()
    check("US-9f ambang QC memakai 5 tingkat (A/A1/A2/B/BS)",
          all(k in thr for k in ("a_max", "a1_max", "a2_max", "b_max")), str(thr))


def us10_decimal(s, product_id):
    print("\n── US-10 · Input desimal seragam (PS-15/R5) ──────────────────────")
    r = make_product(s, stage="finished", fabric_type="woven", gramasi="180,75",
                     lebar="1,25", price="1.250.000,50", grade="A")
    body = r.json() if r.status_code == 200 else {}
    check("US-10b produk: gramasi '180,75' & lebar '1,25' & harga '1.250.000,50'",
          r.status_code == 200 and body.get("gramasi") == 180.75
          and body.get("lebar") == 1.25 and body.get("price") == 1250000.5,
          f"HTTP {r.status_code} · {body.get('gramasi')}/{body.get('lebar')}/{body.get('price')}")

    wh = s.get(f"{BASE}/warehouses", timeout=30).json()
    wh_id = wh[0]["id"] if wh else ""
    pr = s.post(f"{BASE}/purchase-requisitions",
                json={"warehouse_id": wh_id, "reason": "POC desimal",
                      "items": [{"product_id": product_id, "quantity": "10,5",
                                 "unit": "meter", "est_price": "12.500,75"}],
                      "created_by": "POC"}, timeout=60)
    pitem = ((pr.json() or {}).get("items") or [{}])[0] if pr.status_code == 200 else {}
    check("US-10c PR menerima '10,5' & '12.500,75'",
          pr.status_code == 200 and float(pitem.get("quantity", 0)) == 10.5
          and float(pitem.get("est_price", 0)) == 12500.75,
          f"HTTP {pr.status_code} · {pitem.get('quantity')}/{pitem.get('est_price')}")

    # Transfer: pakai produk yang BENAR-BENAR punya stok agar alur penuh teruji.
    rolls_all = s.get(f"{BASE}/inventory/rolls", timeout=30).json()
    rolls_all = rolls_all.get("items", rolls_all) if isinstance(rolls_all, dict) else rolls_all
    stocked = next((r for r in rolls_all if r.get("status") == "available"
                    and float(r.get("length_remaining") or 0) >= 3), None)
    if stocked and len(wh) > 1:
        src = stocked.get("warehouse_id")
        dest = next((w["id"] for w in wh if w["id"] != src), "")
        tr = s.post(f"{BASE}/transfers",
                    json={"source_warehouse_id": src, "dest_warehouse_id": dest,
                          "items": [{"product_id": stocked["product_id"], "qty": "2,5",
                                     "unit": "meter"}],
                          "requested_by": "POC"}, timeout=60)
        titem = ((tr.json() or {}).get("items") or [{}])[0] if tr.status_code in (200, 201) else {}
        check("US-10d Transfer menerima '2,5'",
              tr.status_code in (200, 201) and float(titem.get("qty", 0)) == 2.5,
              f"HTTP {tr.status_code} · {titem.get('qty')} {tr.text[:90] if tr.status_code >= 400 else ''}")

    # Makloon: validasi payload desimal lewat forecast preview (tanpa membuat order)
    fc = s.post(f"{BASE}/process-recipes/forecast",
                json={"input_qty": "10,5", "gramasi": "200,5", "lebar": "1,5",
                      "yield_factor": 1, "waste_pct": "2,5"}, timeout=30)
    check("US-10e Makloon forecast menerima desimal koma",
          fc.status_code == 200, f"HTTP {fc.status_code}: {fc.text[:110]}")

    # Inspeksi QC: gsm/lebar aktual desimal (payload divalidasi walau roll tak ada task)
    rolls = s.get(f"{BASE}/inventory/rolls", timeout=30).json()
    rolls = rolls.get("items", rolls) if isinstance(rolls, dict) else rolls
    if rolls:
        rid = rolls[0]["id"]
        insp = s.post(f"{BASE}/inbound/rolls/{rid}/inspect",
                      json={"defects": [{"point_value": 2, "count": 1}],
                            "gsm_actual": "182,5", "width_actual": "1,48",
                            "note": "POC desimal"}, timeout=30)
        gsm = ((insp.json() or {}).get("roll") or {}).get("inspection", {}).get("gsm_actual")
        check("US-10f Inspeksi QC menerima '182,5' & '1,48'",
              insp.status_code == 200 and float(gsm or 0) == 182.5,
              f"HTTP {insp.status_code} · gsm={gsm}")
        hist = s.get(f"{BASE}/inventory/rolls/{rid}/grade-history", timeout=30).json()
        sources = [h.get("source") for h in hist.get("history", [])]
        check("US-9g inspeksi QC menulis riwayat grade (source=qc_inspection)",
              "qc_inspection" in sources, f"sumber={sources[-3:]}")


def us11_migration():
    print("\n── US-11 · Migrasi idempoten (R8) ────────────────────────────────")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "scripts", "migrate_fase_a_domain.py")
    first = subprocess.run([sys.executable, script], capture_output=True, text=True)
    second = subprocess.run([sys.executable, script], capture_output=True, text=True)
    check("US-11a migrasi jalan tanpa error", first.returncode == 0 and second.returncode == 0,
          f"rc={first.returncode}/{second.returncode}")
    check("US-11b jalan kedua → changed=0 (idempoten)", "changed=0" in second.stdout,
          [ln for ln in second.stdout.splitlines() if "Ringkasan" in ln][:1])
    check("US-11c invarian pasca-migrasi bersih", "masalah_invarian=0" in second.stdout)


def us12_template_variant(s):
    print("\n── US-12 · Template & varian mewarisi domain (PS-02) ─────────────")
    bad = s.post(f"{BASE}/product-templates",
                 json={"name": f"POC Tpl {SUFFIX}", "category": "Tenun", "stage": "grey",
                       "gramasi": 200, "lebar": 1.4}, timeout=30)
    check("US-12a template stage grey tanpa fabric_type ditolak 400",
          bad.status_code == 400, f"HTTP {bad.status_code}: {bad.text[:110]}")

    tpl = s.post(f"{BASE}/product-templates",
                 json={"name": f"POC Tpl {SUFFIX}", "category": "Tenun", "stage": "grey",
                       "fabric_type": "knit", "gramasi": "210,5", "lebar": "1,45",
                       "base_unit": "kg", "sku_prefix": f"PT{SUFFIX}",
                       "axes": [{"key": "color", "label": "Warna",
                                 "options": [{"code": "MRH", "label": "Merah"},
                                             {"code": "BIRU", "label": "Biru"}]}]},
                 timeout=30)
    tid = (tpl.json() or {}).get("id", "")
    check("US-12b template knit tersimpan (desimal koma diterima)",
          tpl.status_code == 200 and (tpl.json() or {}).get("gramasi") == 210.5,
          f"HTTP {tpl.status_code} · gsm={(tpl.json() or {}).get('gramasi')}")
    if not tid:
        return
    gen = s.post(f"{BASE}/product-templates/{tid}/generate-variants", json={}, timeout=60)
    variants = (gen.json() or {}).get("variants", []) if gen.status_code == 200 else []
    check("US-12c generate varian berhasil", gen.status_code == 200 and len(variants) == 2,
          f"HTTP {gen.status_code} · {len(variants)} varian")
    check("US-12d varian mewarisi fabric_type & stage induk",
          all(v.get("fabric_type") == "knit" and v.get("stage") == "grey" for v in variants),
          str([(v.get("fabric_type"), v.get("stage")) for v in variants]))


def main() -> int:
    print("=" * 78)
    print("  POC FASE A — FONDASI DOMAIN TEKSTIL (PS-01/02/03/09/15)")
    print("=" * 78)
    admin = login(ADMIN)
    manager = login(MANAGER)
    warehouse = login(WAREHOUSE)

    snap = us1_registry(admin)
    us2_us3_transitions(admin, snap)
    pid, _knit = us4_us7_product_rules(admin)
    us8_po_grade(admin, pid)
    us9_grade_governance(admin, manager, warehouse)
    us10_decimal(admin, pid)
    us11_migration()
    us12_template_variant(admin)

    print("\n" + "=" * 78)
    print(f"  HASIL: {len(PASS)} PASS · {len(FAIL)} FAIL")
    print("=" * 78)
    for f in FAIL:
        print(f"  ❌ {f}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
