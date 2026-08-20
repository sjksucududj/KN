"""POC (Fase M2 core) — WIP-at-vendor (Makloon) end-to-end tanpa UI.

Membuktikan alur inti terberat:
  issue bahan (available→subcon) → tagihan jasa → konsumsi subcon (retire)
  → terima output + barang sisa (roll baru) → GL SEIMBANG & WIP net 0.

Sekaligus verifikasi anti-drift: perubahan subledger persediaan (rolls PHYS)
== perubahan GL 1-1300 (Persediaan) untuk entitas uji.

Skrip ini MEMBERSIHKAN semua data uji di akhir (DB seeded tetap bersih).
Jalankan: cd /app/backend && python test_makloon_core_poc.py
"""
import asyncio
from db import db
from core_utils import new_id, now_iso
from services.roll_service import create_inbound_roll, rebuild_balance
from services import stock_bucket_service as sb
from services import gl_service as gl

ENT = "ent_ksc"
WH = "wh_jakarta"
POC_TAG = "POC_MAKLOON"
MKO = f"mko_poc_{new_id('x')[-6:]}"

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
results = {"pass": 0, "fail": 0}


def check(name, cond, extra=""):
    tag = PASS if cond else FAIL
    results["pass" if cond else "fail"] += 1
    print(f"  [{tag}] {name}" + (f"  ({extra})" if extra else ""))
    return cond


async def _gl_account_delta(entity_id, code, source_types):
    """Δ akun (debit-credit) dari JE POC (source_id memuat MKO)."""
    jes = await db.journal_entries.find(
        {"entity_id": entity_id, "source_type": {"$in": source_types}}, {"_id": 0}).to_list(1000)
    total = 0.0
    for je in jes:
        if MKO not in str(je.get("source_id", "")) and POC_TAG not in str(je.get("source_label", "")):
            continue
        for l in je.get("lines", []):
            if l.get("account_code") == code:
                total += float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0)
    return round(total, 2)


async def _seg_bucket(product_id, bucket):
    b = await db.inventory_balances.find_one(
        {"product_id": product_id, "warehouse_id": WH, "owner_entity_id": ENT}, {"_id": 0})
    return round(float((b or {}).get(bucket, 0) or 0), 2)


async def run():
    print(f"\n=== POC MAKLOON CORE (M2) — mko={MKO} ===")

    # ── SETUP: produk uji (benang input + grey output + sisa) ──
    UC_INPUT = 100.0          # HPP benang per kg
    input_pid = f"prod_poc_yarn_{new_id('p')[-5:]}"
    output_pid = f"prod_poc_grey_{new_id('p')[-5:]}"
    sisa_pid = f"prod_poc_sisa_{new_id('p')[-5:]}"
    now = now_iso()
    for pid, name, unit, cat in [
        (input_pid, "POC Benang Katun", "kg", "benang"),
        (output_pid, "POC Grey Katun", "yard", "grey"),
        (sisa_pid, "POC Barang Sisa", "yard", "sisa"),
    ]:
        await db.products.insert_one({
            "id": pid, "sku": pid.upper(), "name": name, "base_unit": unit,
            "category": cat, "harga_pokok": UC_INPUT if pid == input_pid else 0,
            "status": "active", "created_at": now, "updated_at": now, "_poc": POC_TAG})

    # ── baseline GL 1-1300 & subledger ──
    async def subledger_val(pid):
        PHYS = ["available", "reserved", "committed", "picked", "packed", "quarantine", "hold"]
        rolls = await db.inventory_rolls.find(
            {"owner_entity_id": ENT, "product_id": pid, "status": {"$in": PHYS}}, {"_id": 0}).to_list(10000)
        return round(sum(float(r.get("length_remaining", 0) or 0) *
                         float(r.get("unit_cost") or r.get("base_unit_cost") or 0) for r in rolls), 2)

    # ── STEP 0: buat 100 kg benang available ──
    ISSUE_QTY = 100.0
    r = await create_inbound_roll(input_pid, WH, ENT, ISSUE_QTY, lot="POC-YARN-01",
                                  unit="kg", acquired_via="poc_seed", ref_id=MKO,
                                  unit_cost=UC_INPUT, created_by=POC_TAG)
    avail0 = await _seg_bucket(input_pid, "available_qty")
    sub_in0 = await subledger_val(input_pid)
    check("Setup: 100kg benang available", avail0 == ISSUE_QTY, f"available={avail0}")
    check("Setup: subledger benang = 100*100 = 10000", sub_in0 == 10000.0, f"sub={sub_in0}")

    # ── STEP 1: ISSUE ke makloon (available→subcon) + GL ──
    ref = {"type": "subcon", "id": f"{MKO}:1", "makloon_id": "mak_seed_tenun", "mko_id": MKO, "step": 1}
    issue = await sb.issue_to_subcon(input_pid, WH, ENT, ISSUE_QTY, ref)
    avail1 = await _seg_bucket(input_pid, "available_qty")
    subcon1 = await _seg_bucket(input_pid, "subcon_qty")
    material_value = issue["value"]
    check("Issue: available benang → 0", avail1 == 0.0, f"available={avail1}")
    check("Issue: subcon benang = 100", subcon1 == ISSUE_QTY, f"subcon={subcon1}")
    check("Issue: nilai material = 10000", material_value == 10000.0, f"value={material_value}")
    je_issue = await gl.post_subcon_issue(mko_id=MKO, step_seq=1, entity_id=ENT,
                                          amount=material_value, label=f"{POC_TAG} {MKO}")
    check("Issue: JE terbentuk", je_issue is not None)
    check("Issue: JE seimbang", je_issue and abs(je_issue["total_debit"] - je_issue["total_credit"]) < 0.01,
          f"D={je_issue['total_debit']} C={je_issue['total_credit']}")
    # subledger benang harus turun 10000 SAMA dengan Cr 1-1300
    sub_in1 = await subledger_val(input_pid)
    cr_inv_issue = -(await _gl_account_delta(ENT, "1-1300", ["subcon_issue"]))
    check("Issue: Δsubledger benang (−10000) == Cr 1-1300", (sub_in0 - sub_in1) == cr_inv_issue,
          f"Δsub={sub_in0 - sub_in1} Cr1-1300={cr_inv_issue}")

    # ── STEP 2: TAGIHAN JASA makloon (tarif+aux), ada PPN ──
    TARIFF, AUX, PPN = 2000.0, 500.0, 275.0   # net=2500, ppn=275, grand=2775
    net_service = TARIFF + AUX
    grand = net_service + PPN
    bill_id = f"vb_poc_{new_id('b')[-6:]}"
    await db.vendor_bills.insert_one({
        "id": bill_id, "bill_number": f"VB-{POC_TAG}", "bill_type": "makloon_service",
        "makloon_id": "mak_seed_tenun", "makloon_order_id": MKO, "step_seq": 1, "po_id": "",
        "supplier_name": "PT Tenun (POC)", "grand_total": grand, "ppn_amount": PPN,
        "net_amount": net_service, "status": "posted", "entity_id": ENT,
        "created_at": now, "updated_at": now, "_poc": POC_TAG})
    je_svc = await gl.post_subcon_service(bill_id=bill_id, mko_id=MKO, step_seq=1, entity_id=ENT,
                                          net_amount=net_service, ppn=PPN, grand_total=grand,
                                          makloon_name="PT Tenun (POC)", label=f"{POC_TAG} {MKO}")
    check("Service: JE terbentuk", je_svc is not None)
    check("Service: JE seimbang", je_svc and abs(je_svc["total_debit"] - je_svc["total_credit"]) < 0.01,
          f"D={je_svc['total_debit']} C={je_svc['total_credit']}")

    # ── STEP 3: konsumsi subcon (retire input) ──
    consumed = await sb.consume_subcon_by_ref(f"{MKO}:1")
    subcon3 = await _seg_bucket(input_pid, "subcon_qty")
    check("Consume: subcon benang → 0", subcon3 == 0.0, f"subcon={subcon3}")
    check("Consume: nilai terkonsumsi = 10000", consumed["consumed_value"] == 10000.0,
          f"val={consumed['consumed_value']}")

    # ── STEP 4: terima OUTPUT (grey) + BARANG SISA ──
    # yield 0.95 → 95 yard grey, byproduct 3% → 3 yard sisa
    OUTPUT_QTY, SISA_QTY = 95.0, 3.0
    wip_total = round(material_value + net_service, 2)   # 10000 + 2500 = 12500
    output_uc = round(wip_total / OUTPUT_QTY, 4)         # semua WIP → output
    await create_inbound_roll(output_pid, WH, ENT, OUTPUT_QTY, lot="POC-GREY-01", unit="yard",
                              acquired_via="subcon_receipt", ref_id=MKO,
                              unit_cost=output_uc, created_by=POC_TAG)
    await create_inbound_roll(sisa_pid, WH, ENT, SISA_QTY, lot="POC-SISA-01", unit="yard",
                              acquired_via="subcon_receipt", ref_id=MKO,
                              unit_cost=0.0, is_remnant=True, created_by=POC_TAG)
    out_avail = await _seg_bucket(output_pid, "available_qty")
    sisa_avail = await _seg_bucket(sisa_pid, "available_qty")
    check("Receive: output grey available = 95", out_avail == OUTPUT_QTY, f"avail={out_avail}")
    check("Receive: barang sisa available = 3", sisa_avail == SISA_QTY, f"avail={sisa_avail}")
    je_rcv = await gl.post_subcon_receipt(mko_id=MKO, step_seq=1, entity_id=ENT,
                                          amount=wip_total, label=f"{POC_TAG} {MKO}")
    check("Receive: JE terbentuk", je_rcv is not None)
    check("Receive: JE seimbang", je_rcv and abs(je_rcv["total_debit"] - je_rcv["total_credit"]) < 0.01,
          f"D={je_rcv['total_debit']} C={je_rcv['total_credit']}")

    # ── INVARIAN 1: WIP (1-1350) net = 0 setelah siklus ──
    wip_delta = await _gl_account_delta(ENT, "1-1350", ["subcon_issue", "subcon_service", "subcon_receipt"])
    check("WIP 1-1350 net = 0 (dibuka & di-clear penuh)", abs(wip_delta) < 0.01, f"Δ={wip_delta}")

    # ── INVARIAN 2: rekonsiliasi 1-1300 == Δsubledger (anti-drift) ──
    inv_delta_gl = await _gl_account_delta(ENT, "1-1300", ["subcon_issue", "subcon_receipt"])
    sub_out = await subledger_val(output_pid)
    sub_sisa = await subledger_val(sisa_pid)
    sub_in_final = await subledger_val(input_pid)
    # Δsubledger total (produk POC) = (output + sisa + benang_final) - benang_awal
    sub_delta = round((sub_out + sub_sisa + sub_in_final) - sub_in0, 2)
    check("GL 1-1300 Δ == Δsubledger (rolls) — anti-drift", abs(inv_delta_gl - sub_delta) < 0.01,
          f"ΔGL={inv_delta_gl} Δsub={sub_delta}")

    # ── INVARIAN 3: idempotensi posting ──
    dup = await gl.post_subcon_issue(mko_id=MKO, step_seq=1, entity_id=ENT,
                                     amount=material_value, label="dup")
    check("Idempoten: post_subcon_issue kedua = None", dup is None)

    # ── CLEANUP ──
    await cleanup([input_pid, output_pid, sisa_pid], bill_id)

    print(f"\n=== HASIL POC: {results['pass']} PASS / {results['fail']} FAIL ===\n")
    return results["fail"] == 0


async def cleanup(pids, bill_id):
    # FASE C — lot yang lahir bersama roll POC ikut dibersihkan supaya invarian
    # INV-LOT-01 (lot harus menunjuk produk yang ada) tetap hijau setelah POC.
    lots = await db.inventory_lots.find({"product_id": {"$in": pids}},
                                        {"_id": 0, "id": 1}).to_list(500)
    lot_ids = [x["id"] for x in lots]
    await db.inventory_lots.delete_many({"product_id": {"$in": pids}})
    if lot_ids:
        await db.inventory_lots.update_many({}, {"$pull": {"parent_lot_ids": {"$in": lot_ids}}})
        await db.inventory_lots.update_many({}, {"$pull": {"child_lot_ids": {"$in": lot_ids}}})
    await db.inventory_rolls.delete_many({"owner_entity_id": ENT, "product_id": {"$in": pids}})
    await db.inventory_movements.delete_many({"owner_entity_id": ENT, "product_id": {"$in": pids}})
    await db.inventory_balances.delete_many({"owner_entity_id": ENT, "product_id": {"$in": pids}})
    await db.products.delete_many({"id": {"$in": pids}})
    await db.vendor_bills.delete_many({"id": bill_id})
    await db.journal_entries.delete_many({"source_id": {"$regex": MKO}})
    await db.journal_entries.delete_many({"source_id": bill_id})
    print("  [cleanup] data uji POC dihapus.")


if __name__ == "__main__":
    ok = asyncio.get_event_loop().run_until_complete(run())
    raise SystemExit(0 if ok else 1)
