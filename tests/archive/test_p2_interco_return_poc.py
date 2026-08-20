"""POC FASE P2 — Cetak/E-Sign Nota Retur & Nota Kredit Antar-PT.

Membuktikan (bukti-merah) bahwa doc_type baru `interco_return` benar-benar:
  1) terdaftar di DOC_REGISTRY (SSOT dokumen cetak),
  2) me-render HTML untuk KEDUA peran (returner=Nota Retur, receiver=Nota Kredit),
  3) me-render PDF (WeasyPrint) untuk satu dokumen,
  4) menghasilkan judul & watermark yang benar per peran,
  5) mendukung fondasi e-sign (compute_doc_hash → build_document tidak error).

Jalankan: /root/.venv/bin/python test_p2_interco_return_poc.py
"""
import asyncio
import sys

sys.path.insert(0, "/app/backend")

from db import db  # noqa: E402
from services.pdf_resolvers import DOC_REGISTRY  # noqa: E402
from services import pdf_service as pdfsvc  # noqa: E402
from services import esign_service as es  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name} {extra}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {extra}")


async def main():
    print("\n=== POC P2 — Nota Retur/Kredit Antar-PT ===\n")

    # 1) Terdaftar di DOC_REGISTRY
    reg = DOC_REGISTRY.get("interco_return")
    check("interco_return terdaftar di DOC_REGISTRY", reg is not None)
    check("collection = interco_returns", reg and reg.get("collection") == "interco_returns",
          f"(got {reg.get('collection') if reg else None})")
    check("esignable = True", reg and reg.get("esignable") is True)
    check("module = interco", reg and reg.get("module") == "interco")

    # Ambil kedua dokumen kembar
    returner = await db.interco_returns.find_one({"role": "returner"}, {"_id": 0})
    receiver = await db.interco_returns.find_one({"role": "receiver"}, {"_id": 0})
    check("ada dokumen returner (Nota Retur)", returner is not None,
          f"({returner.get('number') if returner else None})")
    check("ada dokumen receiver (Nota Kredit)", receiver is not None,
          f"({receiver.get('number') if receiver else None})")
    if not returner or not receiver:
        print("\n[ABORT] data retur antar-PT tidak ada — seed dulu.")
        return

    # 2) Render HTML kedua peran + cek judul/watermark
    for role_label, docrow, exp_title in [
        ("returner", returner, "Nota Retur Antar-PT"),
        ("receiver", receiver, "Nota Kredit Antar-PT"),
    ]:
        built = await pdfsvc.build_document("interco_return", docrow["id"], docrow.get("entity_id"))
        d = built["doc"]
        check(f"[{role_label}] judul = '{exp_title}'", d.get("title") == exp_title,
              f"(got '{d.get('title')}')")
        check(f"[{role_label}] watermark = ANTAR-PT", d.get("watermark") == "ANTAR-PT")
        check(f"[{role_label}] ada baris item", len(d.get("items") or []) > 0,
              f"({len(d.get('items') or [])} baris)")
        check(f"[{role_label}] total nilai retur > 0", (d.get("_amount") or 0) > 0,
              f"(Rp {d.get('_amount')})")
        html, media, _ = await pdfsvc.render_document(
            "interco_return", docrow["id"], docrow.get("entity_id"), fmt="html")
        check(f"[{role_label}] HTML ter-render", isinstance(html, str) and exp_title in html,
              f"({len(html)} char)")
        check(f"[{role_label}] nomor dok tampil di HTML", docrow["number"] in html)

    # 3) Render PDF (WeasyPrint) untuk returner
    pdf, media, _ = await pdfsvc.render_document(
        "interco_return", returner["id"], returner.get("entity_id"), fmt="pdf")
    check("PDF ter-render (application/pdf)", media == "application/pdf")
    check("PDF byte diawali %PDF", isinstance(pdf, (bytes, bytearray)) and pdf[:4] == b"%PDF",
          f"({len(pdf)} bytes)")

    # 4) Fondasi e-sign: compute_doc_hash memanggil build_document tanpa error
    doc_hash, _b = await es.compute_doc_hash(
        "interco_return", returner["id"], returner.get("entity_id"))
    check("e-sign compute_doc_hash menghasilkan hash", bool(doc_hash) and len(doc_hash) >= 16,
          f"({doc_hash[:16]}…)")

    print(f"\n=== HASIL: {PASS} PASS / {FAIL} FAIL ===\n")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
