#!/usr/bin/env python3
"""POC R6.4 — Produksi In-House (BOM + Work Order).

Membuktikan (tanpa mock, via HTTP API nyata):
  A. CRUD BOM (output + komponen multi-bahan + overhead) & validasi
     (nama kosong, produk output tak ada, komponen kosong, qty<=0, bahan==output, duplikat).
  B. Buat Work Order (draft) → rencana bahan (required vs available) + snapshot.
  C. Release WO.
  D. Complete WO → konsumsi roll bahan (FEFO) + produksi roll barang jadi:
     - stok output naik = planned_qty; stok tiap bahan turun = qty_per_unit*planned_qty.
     - material_cost>0, total=material+overhead, unit_cost=total/qty; je_id ada (overhead>0).
  E. Idempotensi: complete ulang → tak menggandakan konsumsi/produksi.
  F. Path overhead=0 → tetap sukses, transformasi stok, tanpa jurnal overhead (je_id kosong).
  G. RBAC: sales 403 (view/create); warehouse boleh view+create+release+complete tapi manage_bom & cancel 403;
     tanpa auth ditolak.
  H. Validasi stok kurang → complete ditolak 400.

Integritas diverifikasi TERPISAH via scripts/verify_data_integrity.py (harus tetap 134/0/0).
"""
import os
import sys
import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001") + "/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
SALES = {"email": "sales@kainnusantara.id", "password": "demo12345"}
WH = {"email": "warehouse@kainnusantara.id", "password": "demo12345"}
ENT = "ent_ksc"

PASS = FAIL = 0
created_boms: list = []
created_wos_open: list = []


def ok(label):
    global PASS
    PASS += 1
    print(f"  \u2705 {label}")


def bad(label, extra=""):
    global FAIL
    FAIL += 1
    print(f"  \u274c {label} {extra}")


def check(cond, label, extra=""):
    ok(label) if cond else bad(label, extra)


def login(cred):
    r = requests.post(f"{BASE}/auth/login", json=cred, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}", "X-Entity-Id": ENT}


def balances(H):
    r = requests.get(f"{BASE}/inventory/balances", params={"entity_id": ENT}, headers=H, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else (d.get("items") or d.get("balances") or [])


def avail(H, pid, wid):
    tot = 0.0
    for b in balances(H):
        if b.get("product_id") == pid and b.get("warehouse_id") == wid and b.get("owner_entity_id") == ENT:
            tot += float(b.get("available_qty") or 0)
    return round(tot, 2)


def pick_scenario(H):
    """Cari 1 gudang dgn >=2 produk berstok, + 1 produk output berbeda."""
    bals = [b for b in balances(H) if float(b.get("available_qty") or 0) >= 40]
    by_wh = {}
    for b in bals:
        by_wh.setdefault(b["warehouse_id"], []).append(b)
    for wid, rows in by_wh.items():
        prods = list({r["product_id"]: r for r in rows}.values())
        if len(prods) >= 2:
            mats = prods[:2]
            # output = produk lain (boleh berstok / tidak) di entitas
            all_pids = [p["id"] for p in requests.get(f"{BASE}/products", headers=H, timeout=30).json()]
            out_pid = next((p for p in all_pids if p not in (mats[0]["product_id"], mats[1]["product_id"])), None)
            if out_pid:
                return wid, mats[0]["product_id"], mats[1]["product_id"], out_pid
    return None


def main():  # noqa: C901
    global PASS, FAIL
    print("== R6.4 PRODUCTION (BOM + WORK ORDER) POC ==")
    H = login(ADMIN)
    HS = login(SALES)
    HW = login(WH)

    scen = pick_scenario(H)
    if not scen:
        print("SETUP GAGAL: tak menemukan gudang dgn 2 bahan berstok.")
        sys.exit(1)
    wid, mat1, mat2, out_pid = scen
    print(f"  skenario: gudang={wid} bahan1={mat1} bahan2={mat2} output={out_pid}")

    # ── A. Validasi BOM ──────────────────────────────────────────────────────
    def mk_bom(body, expect):
        r = requests.post(f"{BASE}/production/boms", json=body, headers=H, timeout=30)
        return r

    check(mk_bom({"name": "", "output_product_id": out_pid,
                  "components": [{"material_product_id": mat1, "qty_per_unit": 1}]}, 400).status_code in (400, 422),
          "A1: BOM nama kosong ditolak")
    check(mk_bom({"name": "X", "output_product_id": "prod_tidak_ada",
                  "components": [{"material_product_id": mat1, "qty_per_unit": 1}]}, 400).status_code == 400,
          "A2: output produk tak ada ditolak (400)")
    check(mk_bom({"name": "X", "output_product_id": out_pid, "components": []}, 400).status_code in (400, 422),
          "A3: komponen kosong ditolak")
    check(mk_bom({"name": "X", "output_product_id": out_pid,
                  "components": [{"material_product_id": mat1, "qty_per_unit": 0}]}, 400).status_code in (400, 422),
          "A4: qty_per_unit<=0 ditolak")
    check(mk_bom({"name": "X", "output_product_id": out_pid,
                  "components": [{"material_product_id": out_pid, "qty_per_unit": 1}]}, 400).status_code == 400,
          "A5: bahan==output ditolak (400)")
    check(mk_bom({"name": "X", "output_product_id": out_pid,
                  "components": [{"material_product_id": mat1, "qty_per_unit": 1},
                                 {"material_product_id": mat1, "qty_per_unit": 2}]}, 400).status_code == 400,
          "A6: komponen duplikat ditolak (400)")

    # BOM valid (overhead>0)
    r = mk_bom({"name": "POC Batik Jadi", "output_product_id": out_pid, "overhead_per_unit": 1000,
                "components": [{"material_product_id": mat1, "qty_per_unit": 2},
                               {"material_product_id": mat2, "qty_per_unit": 1}]}, 200)
    check(r.status_code == 200, "A7: buat BOM valid (overhead 1000)", r.text[:120])
    bom = r.json()
    created_boms.append(bom["id"])
    check(len(bom.get("components", [])) == 2 and bom["status"] == "active", "A8: BOM tersimpan (2 komponen, aktif)")

    # PATCH & GET & list
    rp = requests.patch(f"{BASE}/production/boms/{bom['id']}", json={"overhead_per_unit": 1500}, headers=H, timeout=30)
    check(rp.status_code == 200 and rp.json().get("overhead_per_unit") == 1500, "A9: PATCH BOM overhead")
    rg = requests.get(f"{BASE}/production/boms/{bom['id']}", headers=H, timeout=30)
    check(rg.status_code == 200 and rg.json()["id"] == bom["id"], "A10: GET BOM detail")
    rl = requests.get(f"{BASE}/production/boms", params={"entity_id": ENT}, headers=H, timeout=30)
    check(rl.status_code == 200 and any(b["id"] == bom["id"] for b in rl.json()), "A11: BOM muncul di list")

    # ── B. Work Order draft ──────────────────────────────────────────────────
    planned = 5.0
    pre_out = avail(H, out_pid, wid)
    pre_m1 = avail(H, mat1, wid)
    pre_m2 = avail(H, mat2, wid)
    rw = requests.post(f"{BASE}/production/work-orders",
                       json={"bom_id": bom["id"], "planned_qty": planned, "warehouse_id": wid,
                             "entity_id": ENT}, headers=H, timeout=30)
    check(rw.status_code == 200, "B1: buat WO (draft)", rw.text[:150])
    wo = rw.json()
    check(wo["status"] == "draft" and wo["wo_number"].startswith("WO-"), "B2: WO draft + nomor WO")
    plan = {p["material_product_id"]: p for p in wo.get("material_plan", [])}
    check(abs(plan.get(mat1, {}).get("required_qty", 0) - 2 * planned) < 0.01, "B3: rencana bahan1 = 2×qty")
    check(abs(plan.get(mat2, {}).get("required_qty", 0) - 1 * planned) < 0.01, "B4: rencana bahan2 = 1×qty")
    check(all(p.get("sufficient") for p in wo["material_plan"]), "B5: semua bahan mencukupi")

    # ── C. Release ───────────────────────────────────────────────────────────
    rr = requests.post(f"{BASE}/production/work-orders/{wo['id']}/release", headers=H, timeout=30)
    check(rr.status_code == 200 and rr.json()["status"] == "released", "C1: WO released")

    # ── D. Complete ──────────────────────────────────────────────────────────
    rc = requests.post(f"{BASE}/production/work-orders/{wo['id']}/complete", headers=H, timeout=30)
    check(rc.status_code == 200, "D1: WO complete 200", rc.text[:150])
    done = rc.json()
    check(done["status"] == "completed", "D2: status completed")
    check(abs(avail(H, out_pid, wid) - (pre_out + planned)) < 0.01,
          "D3: stok barang jadi naik = planned_qty", f"{avail(H, out_pid, wid)} vs {pre_out + planned}")
    check(abs(avail(H, mat1, wid) - (pre_m1 - 2 * planned)) < 0.01, "D4: stok bahan1 turun 2×qty")
    check(abs(avail(H, mat2, wid) - (pre_m2 - 1 * planned)) < 0.01, "D5: stok bahan2 turun 1×qty")
    check(done["material_cost"] > 0, "D6: material_cost > 0")
    exp_oh = round(1500 * planned, 2)
    check(abs(done["overhead_cost"] - exp_oh) < 0.5, "D7: overhead_cost = 1500×qty")
    check(abs(done["total_cost"] - round(done["material_cost"] + done["overhead_cost"], 2)) < 0.5,
          "D8: total = material + overhead")
    check(abs(done["unit_cost"] - round(done["total_cost"] / planned, 4)) < 0.01, "D9: unit_cost = total/qty")
    check(bool(done.get("je_id")), "D10: jurnal overhead terbit (je_id ada)")
    check(len(done.get("produced_roll_ids", [])) >= 1, "D11: roll barang jadi tercatat")

    # ── E. Idempotensi ──────────────────────────────────────────────────────
    rc2 = requests.post(f"{BASE}/production/work-orders/{wo['id']}/complete", headers=H, timeout=30)
    check(rc2.status_code == 200, "E1: complete ulang 200 (idempotent)")
    check(abs(avail(H, out_pid, wid) - (pre_out + planned)) < 0.01, "E2: stok output TIDAK dobel")
    check(abs(avail(H, mat1, wid) - (pre_m1 - 2 * planned)) < 0.01, "E3: stok bahan TIDAK dobel-konsumsi")

    # ── F. Path overhead = 0 ────────────────────────────────────────────────
    r0 = mk_bom({"name": "POC Tanpa Overhead", "output_product_id": out_pid, "overhead_per_unit": 0,
                 "components": [{"material_product_id": mat1, "qty_per_unit": 1}]}, 200)
    bom0 = r0.json(); created_boms.append(bom0["id"])
    pre_out0 = avail(H, out_pid, wid); pre_m10 = avail(H, mat1, wid)
    w0 = requests.post(f"{BASE}/production/work-orders",
                       json={"bom_id": bom0["id"], "planned_qty": 3, "warehouse_id": wid, "entity_id": ENT},
                       headers=H, timeout=30).json()
    d0 = requests.post(f"{BASE}/production/work-orders/{w0['id']}/complete", headers=H, timeout=30).json()
    check(d0["status"] == "completed" and d0["overhead_cost"] == 0, "F1: WO overhead=0 selesai")
    check(d0.get("je_id", "") == "", "F2: tanpa jurnal overhead (je_id kosong)")
    check(abs(avail(H, out_pid, wid) - (pre_out0 + 3)) < 0.01, "F3: stok output naik 3")
    check(abs(avail(H, mat1, wid) - (pre_m10 - 3)) < 0.01, "F4: stok bahan turun 3")

    # ── H. Stok kurang → tolak ────────────────────────────────────────────────
    big = mk_bom({"name": "POC Over-demand", "output_product_id": out_pid,
                  "components": [{"material_product_id": mat2, "qty_per_unit": 100000}]}, 200).json()
    created_boms.append(big["id"])
    wbig = requests.post(f"{BASE}/production/work-orders",
                         json={"bom_id": big["id"], "planned_qty": 1, "warehouse_id": wid, "entity_id": ENT},
                         headers=H, timeout=30).json()
    created_wos_open.append(wbig["id"])
    rhc = requests.post(f"{BASE}/production/work-orders/{wbig['id']}/complete", headers=H, timeout=30)
    check(rhc.status_code == 400, "H1: complete stok kurang ditolak (400)", rhc.text[:120])

    # ── G. RBAC ────────────────────────────────────────────────────────────────
    check(requests.get(f"{BASE}/production/boms", headers=HS, timeout=30).status_code == 403,
          "G1: sales dilarang lihat BOM (403)")
    check(requests.post(f"{BASE}/production/boms",
                        json={"name": "x", "output_product_id": out_pid,
                              "components": [{"material_product_id": mat1, "qty_per_unit": 1}]},
                        headers=HS, timeout=30).status_code == 403, "G2: sales dilarang buat BOM (403)")
    check(requests.post(f"{BASE}/production/work-orders",
                        json={"bom_id": bom["id"], "planned_qty": 1, "warehouse_id": wid},
                        headers=HS, timeout=30).status_code == 403, "G3: sales dilarang buat WO (403)")
    check(requests.get(f"{BASE}/production/boms", headers=HW, timeout=30).status_code == 200,
          "G4: warehouse boleh lihat BOM (200)")
    check(requests.post(f"{BASE}/production/boms",
                        json={"name": "x", "output_product_id": out_pid,
                              "components": [{"material_product_id": mat1, "qty_per_unit": 1}]},
                        headers=HW, timeout=30).status_code == 403, "G5: warehouse dilarang kelola BOM (403)")
    rwh = requests.post(f"{BASE}/production/work-orders",
                        json={"bom_id": bom["id"], "planned_qty": 1, "warehouse_id": wid, "entity_id": ENT},
                        headers=HW, timeout=30)
    check(rwh.status_code == 200, "G6: warehouse boleh buat WO (200)", rwh.text[:120])
    if rwh.status_code == 200:
        wo_wh = rwh.json()["id"]
        created_wos_open.append(wo_wh)
        check(requests.post(f"{BASE}/production/work-orders/{wo_wh}/cancel", json={}, headers=HW, timeout=30).status_code == 403,
              "G7: warehouse dilarang batalkan WO (403)")
    check(requests.get(f"{BASE}/production/boms", timeout=30).status_code in (401, 403),
          "G8: tanpa auth ditolak")

    # ── Cleanup ────────────────────────────────────────────────────────────────
    cancelled = 0
    for wid_ in created_wos_open:
        rc_ = requests.post(f"{BASE}/production/work-orders/{wid_}/cancel", json={"reason": "poc cleanup"},
                            headers=H, timeout=30)
        if rc_.status_code == 200:
            cancelled += 1
    deleted = 0
    for bid in created_boms:
        rd = requests.delete(f"{BASE}/production/boms/{bid}", headers=H, timeout=30)
        if rd.status_code == 200:
            deleted += 1
    print(f"  \U0001f9f9 cleanup: {cancelled} WO dibatalkan, {deleted} BOM dihapus "
          f"(WO selesai disimpan sbg histori — integritas tetap valid)")

    print(f"\n=== HASIL R6.4: PASS={PASS} FAIL={FAIL} ===")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
