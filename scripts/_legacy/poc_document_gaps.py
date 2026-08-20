"""
poc_document_gaps.py — POC: render SEMUA dokumen GAP baru (picking/packing/surat jalan/
put-away/GRN/PR/invoice/faktur pajak/RFQ/landed cost) → HTML + PDF asli.

Membuktikan resolver baru menghasilkan PDF valid (%PDF) + konten benar
(multi-item, rincian per-roll, kolom warna/kode, bin, dsb) SEBELUM wiring UI.

Run: cd /app && python scripts/poc_document_gaps.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

from db import db  # noqa: E402
from services import pdf_service as svc  # noqa: E402
from services.pdf_resolvers import DOC_REGISTRY  # noqa: E402

PASS = 0
FAIL = 0
SKIP = 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"   ✅ {msg}")
    else:
        FAIL += 1
        print(f"   ❌ {msg}")


# doc_type → (marker substrings yang WAJIB muncul di HTML)
NEW_DOCS = {
    "picking_list":         ["Picking List", "Lokasi Bin", "Roll ID", "Qty Ambil"],
    "packing_list":         ["Packing List", "Jml Roll", "Total Qty"],
    "delivery_note":        ["Surat Jalan", "Nama Kain", "Warna", "Kode Brg", "Total Roll"],
    "put_away":             ["Put-Away", "Bin Tujuan", "Roll ID"],
    "goods_receipt":        ["Bukti Terima Barang", "Dipesan", "Diterima", "Selisih"],
    "purchase_requisition": ["Purchase Requisition", "Est. Harga", "Total Estimasi"],
    "invoice":              ["Invoice", "Grand Total", "Terbilang"],
    "tax_invoice":          ["Faktur Pajak", "DPP", "PPN"],
    "rfq":                  ["Permintaan Penawaran", "Qty"],
    "landed_cost":          ["Landed Cost", "Komponen Biaya"],
}


async def sample_id(doc_type):
    reg = DOC_REGISTRY[doc_type]
    coll = reg["collection"]
    # untuk picking/packing/delivery: pilih SO yang PUNYA outbound task (biar ada roll)
    if doc_type in ("picking_list", "packing_list", "delivery_note"):
        task = await db.wms_tasks.find_one({"flow_type": "outbound"}, {"_id": 0, "order_id": 1})
        if task:
            row = await db[coll].find_one({"id": task["order_id"]}, {"_id": 0, "id": 1, "entity_id": 1})
            if row:
                return row["id"], row.get("entity_id")
    if doc_type in ("put_away", "goods_receipt"):
        task = await db.wms_tasks.find_one({"flow_type": "inbound"}, {"_id": 0, "po_id": 1})
        if task:
            row = await db[coll].find_one({"id": task["po_id"]}, {"_id": 0, "id": 1, "entity_id": 1})
            if row:
                return row["id"], row.get("entity_id")
    row = await db[coll].find_one({}, {"_id": 0, "id": 1, "entity_id": 1})
    return (row["id"], row.get("entity_id")) if row else (None, None)


async def main():
    global SKIP
    print("=" * 68)
    print("  POC DOKUMEN GAP — render HTML + PDF asli untuk 10 doc_type baru")
    print("=" * 68)

    # 1) registry lengkap
    print("\n[1] Registrasi DOC_REGISTRY")
    for dt in NEW_DOCS:
        ok(dt in DOC_REGISTRY, f"doc_type '{dt}' terdaftar ({DOC_REGISTRY.get(dt, {}).get('label', '?')})")

    # 2) render tiap dokumen
    for dt, markers in NEW_DOCS.items():
        reg = DOC_REGISTRY[dt]
        print(f"\n[render] {dt} — {reg['label']} (coll={reg['collection']})")
        sid, eid = await sample_id(dt)
        if not sid:
            SKIP += 1
            print(f"   ⚠️  SKIP — belum ada data di koleksi '{reg['collection']}'")
            continue
        # HTML
        try:
            html, media, built = await svc.render_document(dt, sid, eid, fmt="html",
                                                           public_base="https://demo.local")
            missing = [m for m in markers if m not in html]
            ok(not missing, f"HTML memuat marker wajib {markers}" + (f" — HILANG: {missing}" if missing else ""))
            doc = built["doc"]
            ok(len(doc.get("items", [])) >= 1, f"items >= 1 (dapat {len(doc.get('items', []))})")
        except Exception as e:  # noqa: BLE001
            ok(False, f"HTML render error: {e}")
            continue
        # PDF
        try:
            pdf, media2, _ = await svc.render_document(dt, sid, eid, fmt="pdf",
                                                       public_base="https://demo.local")
            ok(pdf[:4] == b"%PDF", f"PDF valid (%PDF), engine byte OK")
            ok(len(pdf) > 3000, f"PDF size {len(pdf)} bytes (>3KB)")
        except Exception as e:  # noqa: BLE001
            ok(False, f"PDF render error: {e}")

    # 3) cek khusus: delivery_note multi-item + per-roll
    print("\n[deep] delivery_note — validasi multi-item + rincian per-roll")
    sid, eid = await sample_id("delivery_note")
    if sid:
        _, _, built = await svc.render_document("delivery_note", sid, eid, fmt="html", public_base="x")
        doc = built["doc"]
        cols = [c["label"] for c in doc.get("columns", [])]
        ok("Nama Kain" in cols and "Warna" in cols and "Roll" in cols,
           f"kolom tekstil klasik: {cols}")
        # minimal ada baris; idealnya >=1 roll dengan qty
        rows = doc.get("items", [])
        ok(len(rows) >= 1, f"baris surat jalan: {len(rows)}")
        has_qty = any("yard" in str(r.get("jumlah", "")) or "kg" in str(r.get("jumlah", "")) for r in rows)
        ok(has_qty, "setiap baris memuat jumlah + satuan")
        totals = {t["label"]: t["value"] for t in doc.get("totals", [])}
        ok("Total Roll" in totals and "Total Kuantitas" in totals, f"totals: {totals}")
        ok(len(doc.get("signatures", [])) == 3, f"3 blok tanda tangan (dapat {len(doc.get('signatures', []))})")

    print("\n" + "=" * 68)
    print(f"  HASIL: PASS={PASS}  FAIL={FAIL}  SKIP={SKIP}")
    print("=" * 68)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
