#!/usr/bin/env python3
"""Tambal `services/pdf_resolvers.py` untuk FASE U — kolom ROLL terpisah.

Skrip sekali-pakai (disimpan supaya perubahannya bisa dibaca ulang & diulang bila
berkasnya di-generate ulang). Setiap penggantian memakai jangkar PERSIS agar tidak
ada resolver yang tertambal dua kali atau salah alamat.
"""
import pathlib
import sys

P = pathlib.Path("/app/backend/services/pdf_resolvers.py")
s = P.read_text()
n_ok = 0
n_skip = []


def rep(old: str, new: str, tag: str):
    global s, n_ok
    if new in s:
        n_skip.append(f"{tag} (sudah tertambal)")
        return
    if s.count(old) != 1:
        n_skip.append(f"{tag} (jangkar {s.count(old)}×  — TIDAK ditambal)")
        return
    s = s.replace(old, new, 1)
    n_ok += 1
    print(f"  + {tag}")


# ── 1. Sales Order ───────────────────────────────────────────────────────────
rep('''            "no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
            "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
            "price": fmt_rp(it.get("price")), "disc": f"{it.get('discount_percent', 0):g}%",
            "total": fmt_rp(it.get("line_total", it.get("subtotal"))),
        })''',
    '''            "no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
            "rolls": _rolls_cell(it.get("qty_rolls")),
            "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
            "price": fmt_rp(it.get("price")), "disc": f"{it.get('discount_percent', 0):g}%",
            "total": fmt_rp(it.get("line_total", it.get("subtotal"))),
        })''', "SO items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"),
                    _col("qty", "Qty", "num"), _col("price", "Harga", "num"),
                    _col("disc", "Disc", "num"), _col("total", "Subtotal", "num")],
        "items": items, "totals": totals,
        "terbilang": terbilang(doc.get("grand_total", doc.get("total_amount"))),''',
    '''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"),
                    _col_rolls(), _col("qty", "Jumlah", "num"), _col("price", "Harga", "num"),
                    _col("disc", "Disc", "num"), _col("total", "Subtotal", "num")],
        "items": items, "totals": totals,
        "terbilang": terbilang(doc.get("grand_total", doc.get("total_amount"))),''',
    "SO columns")

# ── 2. Purchase Order ────────────────────────────────────────────────────────
rep('''            "no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
            "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
            "price": fmt_rp(it.get("price")), "total": fmt_rp(it.get("line_total", it.get("subtotal"))),
        })''',
    '''            "no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
            "rolls": _rolls_cell(it.get("qty_rolls")),
            "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
            "price": fmt_rp(it.get("price")), "total": fmt_rp(it.get("line_total", it.get("subtotal"))),
        })''', "PO items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"),
                    _col("qty", "Qty", "num"), _col("price", "Harga", "num"), _col("total", "Subtotal", "num")],
        "items": items, "totals": totals,
        "terbilang": terbilang(doc.get("grand_total", doc.get("total_amount"))),
        "notes": doc.get("notes"),
        "signatures": [{"label": "Dibuat", "role": "Purchasing", "name": doc.get("created_by")},''',
    '''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"),
                    _col_rolls("Roll Dipesan"), _col("qty", "Jumlah", "num"),
                    _col("price", "Harga", "num"), _col("total", "Subtotal", "num")],
        "items": items, "totals": totals,
        "terbilang": terbilang(doc.get("grand_total", doc.get("total_amount"))),
        "notes": doc.get("notes"),
        "signatures": [{"label": "Dibuat", "role": "Purchasing", "name": doc.get("created_by")},''',
    "PO columns")

# ── 3. Nota Retur Penjualan ──────────────────────────────────────────────────
rep('''    items = [{"no": i, "desc": it.get("product_name", ""),
              "qty": f"{it.get('quantity_returned', 0):g} {it.get('unit', '')}",
              "reason": it.get("reason", "-"), "cond": it.get("condition", "-")}
             for i, it in enumerate(doc.get("items", []), 1)]''',
    '''    items = [{"no": i, "desc": it.get("product_name", ""),
              "rolls": _rolls_cell(it.get("qty_rolls")),
              "qty": f"{it.get('quantity_returned', 0):g} {it.get('unit', '')}",
              "reason": it.get("reason", "-"), "cond": it.get("condition", "-")}
             for i, it in enumerate(doc.get("items", []), 1)]''',
    "Retur jual items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("desc", "Produk"), _col("qty", "Qty Retur", "num"),
                    _col("reason", "Alasan"), _col("cond", "Kondisi", "ctr")],''',
    '''        "columns": [_col("no", "No", "num"), _col("desc", "Produk"),
                    _col_rolls("Roll Retur"), _col("qty", "Jumlah Retur", "num"),
                    _col("reason", "Alasan"), _col("cond", "Kondisi", "ctr")],''',
    "Retur jual columns")

# ── 4. Nota Retur Pembelian ──────────────────────────────────────────────────
rep('''    items = [{"no": i, "desc": it.get("product_name", it.get("sku", "")),
              "qty": f"{it.get('quantity', it.get('quantity_returned', 0)):g} {it.get('unit', '')}",
              "reason": it.get("reason", "-")}
             for i, it in enumerate(doc.get("items", []), 1)]''',
    '''    items = [{"no": i, "desc": it.get("product_name", it.get("sku", "")),
              "rolls": _rolls_cell(it.get("qty_rolls")),
              "qty": f"{it.get('quantity', it.get('quantity_returned', 0)):g} {it.get('unit', '')}",
              "reason": it.get("reason", "-")}
             for i, it in enumerate(doc.get("items", []), 1)]''',
    "Retur beli items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("desc", "Produk"), _col("qty", "Qty Retur", "num"), _col("reason", "Alasan")],''',
    '''        "columns": [_col("no", "No", "num"), _col("desc", "Produk"),
                    _col_rolls("Roll Retur"), _col("qty", "Jumlah Retur", "num"),
                    _col("reason", "Alasan")],''',
    "Retur beli columns")

# ── 5. SPK Makloon (steps[]) ─────────────────────────────────────────────────
rep('''    items = [{"no": i, "proc": s.get("process_name", s.get("name", s.get("process", "-"))),
              "wh": s.get("makloon_name", s.get("subcon_name", s.get("vendor_name", "-"))),
              "qty": f"{s.get('input_qty', s.get('qty', 0)):g}", "tariff": fmt_rp(s.get("tariff", s.get("cost", 0)))}
             for i, s in enumerate(steps, 1)]''',
    '''    items = [{"no": i, "proc": s.get("process_name", s.get("name", s.get("process", "-"))),
              "wh": s.get("makloon_name", s.get("subcon_name", s.get("vendor_name", "-"))),
              "rolls": _rolls_cell(s.get("qty_rolls")),
              "rolls_out": _rolls_cell(s.get("qty_rolls_out")),
              "qty": f"{s.get('input_qty', s.get('qty', 0)):g}", "tariff": fmt_rp(s.get("tariff", s.get("cost", 0)))}
             for i, s in enumerate(steps, 1)]''',
    "SPK steps[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("proc", "Proses"), _col("wh", "Pelaksana"),
                    _col("qty", "Qty Input", "num"), _col("tariff", "Tarif", "num")],''',
    '''        "columns": [_col("no", "No", "num"), _col("proc", "Proses"), _col("wh", "Pelaksana"),
                    _col_rolls("Roll Masuk"), _col("qty", "Jumlah Masuk", "num"),
                    _col("rolls_out", "Roll Keluar", "num"), _col("tariff", "Tarif", "num")],''',
    "SPK columns")

# ── 6. Surat Jalan Transfer ──────────────────────────────────────────────────
rep('''    items = [{"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
              "qty": f"{it.get('quantity', it.get('qty', 0)):g} {it.get('unit', '')}"}
             for i, it in enumerate(doc.get("items", []), 1)]''',
    '''    items = [{"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
              "rolls": _rolls_cell(it.get("qty_rolls")),
              "qty": f"{it.get('quantity', it.get('qty', 0)):g} {it.get('unit', '')}"}
             for i, it in enumerate(doc.get("items", []), 1)]''',
    "Transfer items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"), _col("qty", "Qty", "num")],
        "items": items, "notes": doc.get("notes"),
        "signatures": [{"label": "Pengirim", "role": "Gudang Asal", "name": ""},''',
    '''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"),
                    _col_rolls(), _col("qty", "Jumlah", "num")],
        "items": items,
        "totals": [{"label": "Total Roll",
                    "value": _sum_rolls([it.get("qty_rolls") for it in doc.get("items", [])])},
                   {"label": "Total Kuantitas",
                    "value": _sum_by_unit([(it.get("quantity", it.get("qty", 0)), it.get("unit", ""))
                                           for it in doc.get("items", [])]), "strong": True}],
        "notes": doc.get("notes"),
        "signatures": [{"label": "Pengirim", "role": "Gudang Asal", "name": ""},''',
    "Transfer columns + totals")

# ── 7. Purchase Requisition ──────────────────────────────────────────────────
rep('''        items.append({"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", it.get("description", "")),
                      "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
                      "price": fmt_rp(it.get("est_price")), "total": fmt_rp(it.get("subtotal"))})''',
    '''        items.append({"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", it.get("description", "")),
                      "rolls": _rolls_cell(it.get("qty_rolls")),
                      "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
                      "price": fmt_rp(it.get("est_price")), "total": fmt_rp(it.get("subtotal"))})''',
    "PR items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Nama Barang"),
                    _col("qty", "Qty", "num"), _col("price", "Est. Harga", "num"), _col("total", "Estimasi", "num")],''',
    '''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Nama Barang"),
                    _col_rolls(), _col("qty", "Jumlah", "num"),
                    _col("price", "Est. Harga", "num"), _col("total", "Estimasi", "num")],''',
    "PR columns")

# ── 8. Faktur Komersial ──────────────────────────────────────────────────────
rep('''        items.append({"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
                      "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
                      "price": fmt_rp(it.get("price")), "disc": f"{it.get('discount_percent', 0):g}%",
                      "total": fmt_rp(it.get("line_total", it.get("subtotal")))})''',
    '''        items.append({"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
                      "rolls": _rolls_cell(it.get("qty_rolls")),
                      "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
                      "price": fmt_rp(it.get("price")), "disc": f"{it.get('discount_percent', 0):g}%",
                      "total": fmt_rp(it.get("line_total", it.get("subtotal")))})''',
    "Faktur items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"),
                    _col("qty", "Qty", "num"), _col("price", "Harga", "num"),
                    _col("disc", "Disc", "num"), _col("total", "Subtotal", "num")],
        "items": items, "totals": totals, "terbilang": terbilang(grand), "notes": doc.get("notes"),''',
    '''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"),
                    _col_rolls(), _col("qty", "Jumlah", "num"), _col("price", "Harga", "num"),
                    _col("disc", "Disc", "num"), _col("total", "Subtotal", "num")],
        "items": items, "totals": totals, "terbilang": terbilang(grand), "notes": doc.get("notes"),''',
    "Faktur columns")

# ── 9. Faktur Pajak ──────────────────────────────────────────────────────────
rep('''        items.append({"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
                      "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
                      "price": fmt_rp(it.get("price")), "total": fmt_rp(it.get("line_total", it.get("subtotal")))})''',
    '''        items.append({"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
                      "rolls": _rolls_cell(it.get("qty_rolls")),
                      "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
                      "price": fmt_rp(it.get("price")), "total": fmt_rp(it.get("line_total", it.get("subtotal")))})''',
    "Faktur pajak items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Nama BKP/JKP"),
                    _col("qty", "Qty", "num"), _col("price", "Harga", "num"), _col("total", "Total", "num")],''',
    '''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Nama BKP/JKP"),
                    _col_rolls(), _col("qty", "Jumlah", "num"),
                    _col("price", "Harga", "num"), _col("total", "Total", "num")],''',
    "Faktur pajak columns")

# ── 10. RFQ ──────────────────────────────────────────────────────────────────
rep('''    items = [{"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", it.get("description", "")),
              "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}"}
             for i, it in enumerate(doc.get("items", []), 1)]''',
    '''    items = [{"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", it.get("description", "")),
              "rolls": _rolls_cell(it.get("qty_rolls")),
              "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}"}
             for i, it in enumerate(doc.get("items", []), 1)]''',
    "RFQ items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Nama Barang"), _col("qty", "Qty", "num")],''',
    '''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Nama Barang"),
                    _col_rolls(), _col("qty", "Jumlah", "num")],''',
    "RFQ columns")

# ── 11. Nota Retur / Kredit Antar-PT ─────────────────────────────────────────
rep('''            "no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
            "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
            "price": fmt_rp(it.get("unit_price", it.get("price"))),
            "total": fmt_rp(it.get("line_subtotal", it.get("subtotal"))),
        })''',
    '''            "no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
            "rolls": _rolls_cell(it.get("qty_rolls")),
            "qty": f"{it.get('quantity', 0):g} {it.get('unit', '')}",
            "price": fmt_rp(it.get("unit_price", it.get("price"))),
            "total": fmt_rp(it.get("line_subtotal", it.get("subtotal"))),
        })''', "Retur antar-PT items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"),
                    _col("qty", "Qty Retur", "num"), _col("price", "Harga", "num"),
                    _col("total", "Subtotal", "num")],''',
    '''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Produk"),
                    _col_rolls("Roll Retur"), _col("qty", "Jumlah Retur", "num"),
                    _col("price", "Harga", "num"), _col("total", "Subtotal", "num")],''',
    "Retur antar-PT columns")

# ── 12. GRN — dua pasang kolom: dipesan vs diterima ──────────────────────────
rep('''        items.append({"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
                      "ordered": f"{ordered:g}", "received": f"{received:g}",
                      "diff": f"{(received - ordered):g}", "unit": it.get("unit", "")})''',
    '''        items.append({"no": i, "sku": it.get("sku", ""), "desc": it.get("product_name", ""),
                      "rolls_ord": _rolls_cell(it.get("qty_rolls")),
                      "ordered": f"{ordered:g}",
                      "rolls_rcv": _rolls_cell(it.get("received_rolls")),
                      "received": f"{received:g}",
                      "diff": f"{(received - ordered):g}", "unit": it.get("unit", "")})''',
    "GRN items[].rolls")

rep('''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Nama Barang"),
                    _col("ordered", "Dipesan", "num"), _col("received", "Diterima", "num"),
                    _col("diff", "Selisih", "num"), _col("unit", "Satuan", "ctr")],
        "items": items,
        "totals": [{"label": "Total Dipesan", "value": total_ord},
                   {"label": "Total Diterima", "value": total_rcv, "strong": True}],''',
    '''        "columns": [_col("no", "No", "num"), _col("sku", "SKU"), _col("desc", "Nama Barang"),
                    _col("rolls_ord", "Roll Dipesan", "num"), _col("ordered", "Dipesan", "num"),
                    _col("rolls_rcv", "Roll Diterima", "num"), _col("received", "Diterima", "num"),
                    _col("diff", "Selisih", "num"), _col("unit", "Satuan", "ctr")],
        "items": items,
        "totals": [{"label": "Roll Dipesan",
                    "value": _sum_rolls([it.get("qty_rolls") for it in doc.get("items", [])])},
                   {"label": "Total Dipesan", "value": total_ord},
                   {"label": "Roll Diterima",
                    "value": _sum_rolls([it.get("received_rolls") for it in doc.get("items", [])])},
                   {"label": "Total Diterima", "value": total_rcv, "strong": True}],''',
    "GRN columns + totals")

P.write_text(s)
print(f"\n  {n_ok} penggantian berhasil")
if n_skip:
    print("  DILEWATI:")
    for x in n_skip:
        print(f"    ! {x}")
    sys.exit(1 if any("TIDAK ditambal" in x for x in n_skip) else 0)
