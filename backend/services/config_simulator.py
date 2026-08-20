"""FASE G-0 — SIMULATOR KONFIGURASI ("Coba dulu").

Kenapa ada: user bingung menentukan aturan karena tidak bisa melihat akibatnya sebelum
menyimpan. Simulator menjawab pertanyaan **"kalau saya set angka ini, apa yang terjadi?"**
dengan langkah hitung yang terlihat (bukan kotak hitam), memakai *nilai efektif nyata*
dari resolver — termasuk nilai hipotetis yang belum disimpan.

Setiap simulator mendeklarasikan:
  needs  : kunci config yang dipakai
  inputs : contoh angka yang diminta ke user (dengan default masuk akal)
  run    : fungsi murni → {steps[], result, verdict}
"""
from typing import Any, Callable, Dict, List
from core_utils import rupiah


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _rp(v: float) -> str:
    """Alias tipis ke `core_utils.rupiah` — satu sumber format uang untuk seluruh backend."""
    return rupiah(v)


def _num(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}".replace(",", "~").replace(".", ",").replace("~", ".")
    return s.rstrip("0").rstrip(",") if dec and "," in s else s


def I(name: str, label: str, typ: str = "money", default: Any = 0, unit: str = "") -> Dict[str, Any]:
    return {"name": name, "label": label, "type": typ, "default": default, "unit": unit}


# ── implementasi tiap simulator ─────────────────────────────────────────────
def _tax(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    sub = _f(s.get("subtotal"), 10_000_000)
    rate = _f(c.get("tax.ppn_rate"), 0)
    nl = bool(c.get("tax.dpp_nilai_lain"))
    mode = c.get("tax.ppn_mode") or "excluded"
    pkp = bool(c.get("tax.efaktur_enabled", True))
    steps = [{"label": "Subtotal yang diketik sales", "value": _rp(sub)}]
    if not pkp or rate <= 0:
        steps.append({"label": "Status PKP", "value": "Non-PKP / tarif 0 → tanpa PPN"})
        return {"steps": steps, "result": f"Grand total {_rp(sub)} (tanpa PPN)", "verdict": "ok"}
    factor = 11 / 12 if nl else 1.0
    eff = rate * factor
    steps.append({"label": "Tarif PPN", "value": f"{_num(rate)}%"})
    steps.append({"label": "DPP Nilai Lain (11/12)", "value": "Ya" if nl else "Tidak"})
    steps.append({"label": "Tarif efektif", "value": f"{_num(eff, 4)}%"})
    if mode == "included":
        harga = round(sub / (1 + eff / 100), 2)
        ppn = round(sub - harga, 2)
        grand = sub
        steps.append({"label": "Harga jual (dipisah dari total)", "value": _rp(harga)})
    else:
        harga = sub
        ppn = round(sub * eff / 100, 2)
        grand = round(sub + ppn, 2)
    steps.append({"label": "DPP", "value": _rp(round(harga * factor, 2))})
    steps.append({"label": "PPN", "value": _rp(ppn)})
    return {"steps": steps, "result": f"Grand total {_rp(grand)} (PPN {_rp(ppn)})", "verdict": "ok"}


def _ar_penalty(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    out = _f(s.get("outstanding"), 10_000_000)
    late = int(_f(s.get("days_late"), 45))
    rate = _f(c.get("ar.denda_rate_pct_per_month"), 0)
    grace = int(_f(c.get("ar.grace_days"), 0))
    eff_days = max(0, late - grace)
    denda = round(out * (rate / 100.0) * (eff_days / 30.0), 2)
    steps = [
        {"label": "Sisa tagihan lewat jatuh tempo", "value": _rp(out)},
        {"label": "Hari keterlambatan", "value": f"{late} hari"},
        {"label": "Masa tenggang", "value": f"{grace} hari"},
        {"label": "Hari kena denda", "value": f"{eff_days} hari"},
        {"label": "Bunga denda", "value": f"{_num(rate)}% per bulan (prorata 30 hari)"},
    ]
    verdict = "ok" if denda == 0 else ("warn" if denda < out * 0.05 else "block")
    return {"steps": steps, "result": f"Estimasi denda {_rp(denda)}", "verdict": verdict}


def _ar_bucket(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    late = int(_f(s.get("days_late"), 45))
    buckets = c.get("ar.aging_buckets") or [30, 60, 90]
    b = sorted(int(_f(x)) for x in buckets)
    label, prev = f"{b[-1]}+ hari", 0
    for edge in b:
        if late <= edge:
            label = f"{prev + 1}–{edge} hari"
            break
        prev = edge
    steps = [{"label": "Hari keterlambatan", "value": f"{late} hari"},
             {"label": "Ambang kelompok", "value": ", ".join(str(x) for x in b)}]
    return {"steps": steps, "result": f"Masuk kolom '{label}'", "verdict": "ok"}


def _pricing(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    gross = _f(s.get("subtotal"), 10_000_000)
    item_d = _f(s.get("item_discount_pct"), 5)
    order_d = _f(s.get("order_discount_pct"), 2)
    ai = bool(c.get("sales.allow_item_discount", c.get("purchasing.allow_item_discount")))
    ao = bool(c.get("sales.allow_order_discount", c.get("purchasing.allow_order_discount")))
    d1 = round(gross * item_d / 100, 2) if ai else 0.0
    after = gross - d1
    d2 = round(after * order_d / 100, 2) if ao else 0.0
    net = round(after - d2, 2)
    steps = [
        {"label": "Subtotal bruto", "value": _rp(gross)},
        {"label": f"Diskon baris {(_num(item_d) + '%')}",
         "value": _rp(d1) if ai else "DIABAIKAN (diskon baris dimatikan)"},
        {"label": f"Diskon order {(_num(order_d) + '%')}",
         "value": _rp(d2) if ao else "DIABAIKAN (diskon order dimatikan)"},
    ]
    return {"steps": steps, "result": f"Dasar pajak (netto) {_rp(net)}",
            "verdict": "ok" if (ai or ao) else "warn"}


def _commission_cap(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    margin = _f(s.get("line_margin"), 1_000_000)
    komisi = _f(s.get("commission"), 700_000)
    cap_pct = _f(c.get("commission.default_margin_cap_pct"), 50)
    cap = round(margin * cap_pct / 100, 2)
    paid = min(komisi, cap)
    steps = [{"label": "Margin baris", "value": _rp(margin)},
             {"label": "Komisi hasil hitung", "value": _rp(komisi)},
             {"label": f"Batas {_num(cap_pct)}% dari margin", "value": _rp(cap)}]
    return {"steps": steps,
            "result": (f"Komisi dibayar {_rp(paid)}"
                       + (" (dipotong batas margin)" if paid < komisi else " (tidak terkena batas)")),
            "verdict": "warn" if paid < komisi else "ok"}


def _commission_discount(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    disc = _f(s.get("discount"), 15)
    komisi = _f(s.get("commission"), 1_000_000)
    qty = _f(s.get("quantity"), 100)
    thr = _f(c.get("commission.discount_threshold"), 10)
    mech = c.get("commission.discount_mechanic") or "tier_factor"
    fac = _f(c.get("commission.discount_factor"), 0.5)
    potong = _f(c.get("commission.discount_potong_rp"), 0)
    typ = c.get("commission.discount_threshold_type") or "pct"
    over = disc >= thr
    steps = [{"label": "Diskon baris", "value": (f"{_num(disc)}%" if typ == "pct" else _rp(disc) + "/satuan")},
             {"label": "Ambang", "value": (f"{_num(thr)}%" if typ == "pct" else _rp(thr) + "/satuan")},
             {"label": "Komisi sebelum mekanik", "value": _rp(komisi)}]
    if not over:
        return {"steps": steps, "result": f"Komisi utuh {_rp(komisi)} (di bawah ambang)", "verdict": "ok"}
    if mech == "cutoff":
        final = 0.0
        steps.append({"label": "Mekanik", "value": "Komisi hangus"})
    elif mech == "potong_rp":
        final = max(0.0, komisi - potong * qty)
        steps.append({"label": "Mekanik", "value": f"Kurangi {_rp(potong)} × {_num(qty)} satuan"})
    else:
        final = round(komisi * fac, 2)
        steps.append({"label": "Mekanik", "value": f"Kalikan faktor {_num(fac)}"})
    return {"steps": steps, "result": f"Komisi dibayar {_rp(final)}", "verdict": "warn"}


def _receiving_over(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    expected = _f(s.get("po_qty"), 1000)
    received = _f(s.get("received_total"), 1030)
    tol = _f(c.get("purchasing.receive_tolerance_percent"), 2)
    block = bool(c.get("receiving.block_over_remaining", True))
    max_qty = round(expected * (1 + tol / 100), 4)
    over = received > max_qty + 1e-6
    steps = [{"label": "Qty PO", "value": _num(expected)},
             {"label": f"Toleransi +{_num(tol)}%", "value": f"maks {_num(max_qty)}"},
             {"label": "Total diterima", "value": _num(received)},
             {"label": "Tolak bila lebih?", "value": "Ya" if block else "Tidak (terima + tandai)"}]
    if not over:
        return {"steps": steps, "result": "Diterima normal (masih dalam toleransi)", "verdict": "ok"}
    if block:
        return {"steps": steps, "result": "DITOLAK — melebihi PO + toleransi. Butuh Eskalasi.",
                "verdict": "block"}
    return {"steps": steps,
            "result": f"Diterima dengan tanda 'lebih dari PO' (+{_num(received - max_qty)})",
            "verdict": "warn"}


def _bill_match(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    recv_q = _f(s.get("received_qty"), 1000)
    bill_q = _f(s.get("billed_qty"), 1010)
    po_p = _f(s.get("po_price"), 100_000)
    bill_p = _f(s.get("billed_price"), 108_000)
    tq = _f(c.get("purchasing.bill_qty_tolerance_percent"), 0)
    tp = _f(c.get("purchasing.bill_price_tolerance_percent"), 5)
    dq = ((bill_q - recv_q) / recv_q * 100) if recv_q else 0
    dp = ((bill_p - po_p) / po_p * 100) if po_p else 0
    steps = [{"label": "Selisih qty", "value": f"{_num(dq)}% (toleransi {_num(tq)}%)"},
             {"label": "Selisih harga", "value": f"{_num(dp)}% (toleransi {_num(tp)}%)"}]
    bad = []
    if abs(dq) > tq:
        bad.append("qty")
    if abs(dp) > tp:
        bad.append("harga")
    if not bad:
        return {"steps": steps, "result": "3-way match LOLOS — tagihan bisa langsung diproses",
                "verdict": "ok"}
    return {"steps": steps,
            "result": f"Selisih {' & '.join(bad)} di luar toleransi → butuh keputusan berlabel",
            "verdict": "block"}


def _qc_grade(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    pts = _f(s.get("points"), 25)
    a = _f(c.get("qc.grade_thresholds.a_max"), 20)
    b = _f(c.get("qc.grade_thresholds.b_max"), 40)
    on = bool(c.get("qc.four_point_enabled", True))
    grade = "A" if pts <= a else ("B" if pts <= b else "C")
    steps = [{"label": "Inspeksi 4-Point", "value": "Aktif" if on else "Nonaktif (grade manual)"},
             {"label": "Poin cacat", "value": _num(pts)},
             {"label": "Ambang A / B", "value": f"≤{_num(a)} / ≤{_num(b)}"}]
    return {"steps": steps, "result": f"Grade {grade}",
            "verdict": "ok" if grade == "A" else ("warn" if grade == "B" else "block")}


def _stock_class(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    days = int(_f(s.get("days_since_sale"), 45))
    fast = _f(c.get("inventory.stock_analytics.fast_max_days"), 30)
    slow = _f(c.get("inventory.stock_analytics.slow_max_days"), 90)
    label = "Cepat Laku (Fast)" if days <= fast else ("Lambat (Slow)" if days <= slow else "Mati (Dead)")
    steps = [{"label": "Hari sejak terakhir terjual", "value": f"{days} hari"},
             {"label": "Ambang Fast / Slow", "value": f"≤{_num(fast)} / ≤{_num(slow)} hari"}]
    return {"steps": steps, "result": f"Klasifikasi: {label}",
            "verdict": "ok" if days <= fast else ("warn" if days <= slow else "block")}


def _reorder(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    sold = _f(s.get("sold_qty"), 900)
    lead = _f(s.get("lead_time_days"), 14)
    win = _f(c.get("inventory.reorder.velocity_window_days"), 90)
    safety = _f(c.get("inventory.reorder.safety_days"), 7)
    daily = round(sold / win, 4) if win else 0
    rop = round(daily * (lead + safety), 2)
    steps = [{"label": f"Terjual dalam {_num(win)} hari", "value": _num(sold)},
             {"label": "Rata-rata harian", "value": f"{_num(daily)} / hari"},
             {"label": "Lead time + cadangan", "value": f"{_num(lead)} + {_num(safety)} hari"}]
    return {"steps": steps, "result": f"Titik pesan ulang ≈ {_num(rop)}", "verdict": "ok"}


def _uom_variance(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    exp = _f(s.get("expected"), 47.25)
    act = _f(s.get("actual"), 48.5)
    warn = _f(c.get("uom.warn_pct"), 2)
    block = _f(c.get("uom.block_pct"), 5)
    ovr = bool(c.get("uom.allow_override", True))
    dev = abs((act - exp) / exp * 100) if exp else 0
    steps = [{"label": "Harapan", "value": _num(exp)}, {"label": "Aktual", "value": _num(act)},
             {"label": "Selisih", "value": f"{_num(dev)}%"},
             {"label": "Ambang warn / block", "value": f"{_num(warn)}% / {_num(block)}%"}]
    if dev > block:
        return {"steps": steps,
                "result": "DITOLAK" + (" — kecuali override berizin + alasan" if ovr else " (override dimatikan)"),
                "verdict": "block"}
    if dev > warn:
        return {"steps": steps, "result": "Diterima dengan peringatan kuning", "verdict": "warn"}
    return {"steps": steps, "result": "Diterima tanpa peringatan", "verdict": "ok"}


def _lot_enforce(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    has_lot = bool(s.get("has_supplier_lot"))
    has_dye = bool(s.get("has_dye_lot"))
    mode = c.get("lot.enforcement_mode") or "warn"
    need_lot = bool(c.get("lot.require_supplier_lot", True))
    need_dye = bool(c.get("lot.require_dye_lot", True))
    missing = []
    if need_lot and not has_lot:
        missing.append("Lot Supplier")
    if need_dye and not has_dye:
        missing.append("Dye Lot")
    steps = [{"label": "Ketegasan", "value": mode},
             {"label": "Field wajib", "value": ", ".join(
                 [x for x, y in (("Lot Supplier", need_lot), ("Dye Lot", need_dye)) if y]) or "—"},
             {"label": "Yang kosong", "value": ", ".join(missing) or "tidak ada"}]
    if not missing or mode == "off":
        return {"steps": steps, "result": "Penerimaan lanjut normal", "verdict": "ok"}
    if mode == "block":
        return {"steps": steps, "result": f"DITOLAK — {', '.join(missing)} wajib diisi", "verdict": "block"}
    return {"steps": steps, "result": f"Lanjut dengan peringatan ({', '.join(missing)} kosong)",
            "verdict": "warn"}


def _lot_number(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    fmt = c.get("lot.number_format") or "LOT-YYMM-####"
    seq = int(_f(s.get("sequence"), 7))
    out = fmt.replace("YYMM", "2607").replace("YY", "26").replace("MM", "07")
    hashes = out.count("#")
    if hashes:
        out = out.replace("#" * hashes, str(seq).zfill(hashes))
    return {"steps": [{"label": "Pola", "value": fmt}, {"label": "Urutan", "value": str(seq)}],
            "result": f"Contoh nomor lot: {out}", "verdict": "ok"}


def _makloon_variance(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    sent = _f(s.get("sent_qty"), 1000)
    back = _f(s.get("returned_qty"), 950)
    shr = _f(c.get("makloon.default_shrinkage_pct"), 0)
    tol = _f(c.get("makloon.variance_tolerance_pct"), 3)
    auto = bool(c.get("makloon.auto_claim", True))
    est = round(sent * (1 - shr / 100), 2)
    dev = ((back - est) / est * 100) if est else 0
    steps = [{"label": "Dikirim ke mitra", "value": _num(sent)},
             {"label": f"Susut standar {_num(shr)}%", "value": f"estimasi kembali {_num(est)}"},
             {"label": "Kembali", "value": _num(back)},
             {"label": "Selisih", "value": f"{_num(dev)}% (toleransi {_num(tol)}%)"}]
    if abs(dev) <= tol:
        return {"steps": steps, "result": "Masih wajar — tidak ada klaim", "verdict": "ok"}
    return {"steps": steps,
            "result": ("Klaim OTOMATIS terbuka (menunggu persetujuan)" if auto
                       else "Selisih tercatat, klaim harus dibuat MANUAL"),
            "verdict": "block" if auto else "warn"}


def _payroll_bpjs(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    gaji = _f(s.get("salary"), 8_000_000)
    kes_ceil = _f(c.get("hr.bpjs.kes_ceiling"), 12_000_000)
    jp_ceil = _f(c.get("hr.bpjs.jp_ceiling"), 10_042_300)
    rows = [
        ("BPJS Kesehatan (karyawan)", "hr.bpjs.kes_rate_employee", kes_ceil),
        ("BPJS Kesehatan (perusahaan)", "hr.bpjs.kes_rate_employer", kes_ceil),
        ("JHT (karyawan)", "hr.bpjs.jht_rate_employee", 0),
        ("JHT (perusahaan)", "hr.bpjs.jht_rate_employer", 0),
        ("Jaminan Pensiun (karyawan)", "hr.bpjs.jp_rate_employee", jp_ceil),
        ("Jaminan Pensiun (perusahaan)", "hr.bpjs.jp_rate_employer", jp_ceil),
        ("JKM (perusahaan)", "hr.bpjs.jkm_rate_employer", 0),
    ]
    steps = [{"label": "Gaji bruto", "value": _rp(gaji)}]
    pot = 0.0
    for label, key, ceil in rows:
        rate = _f(c.get(key), 0)
        base = min(gaji, ceil) if ceil else gaji
        amt = round(base * rate / 100, 2)
        steps.append({"label": f"{label} {_num(rate)}%", "value": _rp(amt)})
        if "karyawan" in label:
            pot += amt
    return {"steps": steps, "result": f"Total potongan karyawan {_rp(pot)}", "verdict": "ok"}


def _payroll_overtime(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    gaji = _f(s.get("salary"), 5_000_000)
    hours = _f(s.get("overtime_hours"), 4)
    div = _f(c.get("hr.overtime.hours_divisor"), 173)
    mult = _f(c.get("hr.overtime.multiplier"), 1.5)
    per_hour = round(gaji / div, 2) if div else 0
    total = round(per_hour * mult * hours, 2)
    steps = [{"label": "Gaji bulanan", "value": _rp(gaji)},
             {"label": f"Dibagi {_num(div)} jam", "value": f"{_rp(per_hour)}/jam"},
             {"label": f"Pengali {_num(mult)}× × {_num(hours)} jam", "value": _rp(total)}]
    return {"steps": steps, "result": f"Upah lembur {_rp(total)}", "verdict": "ok"}


def _payroll_pph21(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    on = bool(c.get("hr.ter_enabled", True))
    bruto = _f(s.get("gross"), 8_000_000)
    steps = [{"label": "Bruto bulanan", "value": _rp(bruto)},
             {"label": "Metode", "value": "TER (Tarif Efektif Rata-rata)" if on else "Perhitungan lama (PTKP tahunan)"}]
    return {"steps": steps,
            "result": ("PPh 21 dihitung dari tabel TER per kategori PTKP karyawan" if on
                       else "PPh 21 dihitung dari PTKP tahunan — tabel PTKP menjadi relevan"),
            "verdict": "ok" if on else "warn"}


def _min_cut(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    qty = _f(s.get("qty"), 0.3)
    mn = _f(c.get("inventory.min_cut_qty"), 0.5)
    ok = qty >= mn or qty <= 0
    steps = [{"label": "Qty diminta", "value": _num(qty, 3)},
             {"label": "Minimum potong", "value": _num(mn, 3)}]
    return {"steps": steps,
            "result": "Diterima" if ok else f"DITOLAK — minimum potong {_num(mn, 3)}",
            "verdict": "ok" if ok else "block"}


def _po_supplier(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    has = bool(s.get("has_supplier_master"))
    req = bool(c.get("purchasing.require_supplier_master", False))
    steps = [{"label": "PO memilih supplier terdaftar?", "value": "Ya" if has else "Tidak"},
             {"label": "Wajib supplier master?", "value": "Ya" if req else "Tidak"}]
    if req and not has:
        return {"steps": steps, "result": "DITOLAK — PO wajib memilih supplier master", "verdict": "block"}
    return {"steps": steps, "result": "PO boleh dibuat", "verdict": "ok"}


def _interco(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    other = bool(s.get("uses_other_entity_stock"))
    req = bool(c.get("inventory.intercompany_transfer_required", True))
    steps = [{"label": "Memakai stok entitas lain?", "value": "Ya" if other else "Tidak"},
             {"label": "Wajib transfer dulu?", "value": "Ya" if req else "Tidak"}]
    if other and req:
        return {"steps": steps,
                "result": "DITOLAK — buat Transaksi Antar-Entitas dulu sebelum menjual",
                "verdict": "block"}
    return {"steps": steps, "result": "Pesanan boleh lanjut", "verdict": "ok"}


def _quotation(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    on = bool(c.get("sales.quotation_enabled", False))
    return {"steps": [{"label": "Penawaran aktif?", "value": "Ya" if on else "Tidak"}],
            "result": ("Sales membuat Penawaran dulu, lalu dikonversi menjadi pesanan" if on
                       else "Alur langsung ke pesanan — endpoint penawaran ditolak (400)"),
            "verdict": "ok"}


def _currency(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    from services.config_currency import format_money_with
    cur = c.get("finance.base_currency") or "IDR"
    amt = _f(s.get("amount"), 1_250_000)
    return {"steps": [{"label": "Mata uang", "value": cur}],
            "result": f"Angka {_num(amt)} ditampilkan sebagai {format_money_with(amt, cur)}",
            "verdict": "ok"}


def _fiscal_year(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    from services.config_currency import fiscal_year_bounds
    end_month = int(_f(c.get("finance.fiscal_year_end_month"), 12))
    period = (s.get("period") or "2026-07").strip()
    label, start, end = fiscal_year_bounds(period, end_month)
    return {"steps": [{"label": "Bulan tutup tahun buku", "value": str(end_month)},
                      {"label": "Periode diuji", "value": period}],
            "result": f"Masuk tahun buku {label} ({start} s/d {end})", "verdict": "ok"}


def _price_deviation(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    ref = _f(s.get("reference_price"), 100_000)
    po = _f(s.get("po_price"), 115_000)
    thr = _f(c.get("purchasing.price_deviation_approval_percent"), 10)
    dev = ((po - ref) / ref * 100) if ref else 0
    steps = [{"label": "Harga acuan", "value": _rp(ref)}, {"label": "Harga PO", "value": _rp(po)},
             {"label": "Deviasi", "value": f"{_num(dev)}% (ambang {_num(thr)}%)"}]
    if dev > thr:
        return {"steps": steps, "result": "WAJIB persetujuan — harga naik melebihi ambang",
                "verdict": "block"}
    return {"steps": steps, "result": "Tidak perlu persetujuan harga", "verdict": "ok"}


def _approval(c: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    amount = _f(s.get("amount"), 600_000_000)
    doc = (s.get("doc_type") or "purchase_order").strip()
    extra = (c.get("approval.extra_levels") or {}).get(doc) or []
    steps = [{"label": "Jenis dokumen", "value": doc}, {"label": "Nilai", "value": _rp(amount)}]
    hits = [lv for lv in extra if amount >= _f(lv.get("min_amount"), 0)]
    for lv in extra:
        steps.append({"label": f"Jenjang {lv.get('label') or lv.get('role')}",
                      "value": f"aktif bila ≥ {_rp(_f(lv.get('min_amount')))}"})
    if not hits:
        return {"steps": steps,
                "result": "Hanya level pertama (Approval Rules) yang berlaku", "verdict": "ok"}
    chain = " → ".join(["Level 1 (Approval Rules)"] + [(h.get("label") or h.get("role")) for h in hits])
    return {"steps": steps, "result": f"Rantai persetujuan: {chain}", "verdict": "warn"}


SIMULATORS: Dict[str, Dict[str, Any]] = {
    "tax": {"label": "Hitung PPN faktur",
            "needs": ["tax.ppn_rate", "tax.dpp_nilai_lain", "tax.ppn_mode", "tax.efaktur_enabled"],
            "inputs": [I("subtotal", "Subtotal pesanan", "money", 10_000_000, "Rp")], "run": _tax},
    "ar_penalty": {"label": "Hitung denda keterlambatan",
                   "needs": ["ar.denda_rate_pct_per_month", "ar.grace_days"],
                   "inputs": [I("outstanding", "Sisa tagihan", "money", 10_000_000, "Rp"),
                              I("days_late", "Hari keterlambatan", "int", 45, "hari")],
                   "run": _ar_penalty},
    "ar_bucket": {"label": "Tentukan kolom umur piutang", "needs": ["ar.aging_buckets"],
                  "inputs": [I("days_late", "Hari keterlambatan", "int", 45, "hari")],
                  "run": _ar_bucket},
    "pricing": {"label": "Hitung diskon & dasar pajak",
                "needs": ["sales.allow_item_discount", "sales.allow_order_discount",
                          "purchasing.allow_item_discount", "purchasing.allow_order_discount"],
                "inputs": [I("subtotal", "Subtotal bruto", "money", 10_000_000, "Rp"),
                           I("item_discount_pct", "Diskon baris", "pct", 5, "%"),
                           I("order_discount_pct", "Diskon order", "pct", 2, "%")],
                "run": _pricing},
    "commission_cap": {"label": "Uji batas komisi vs margin",
                       "needs": ["commission.default_margin_cap_pct"],
                       "inputs": [I("line_margin", "Margin baris", "money", 1_000_000, "Rp"),
                                  I("commission", "Komisi hasil hitung", "money", 700_000, "Rp")],
                       "run": _commission_cap},
    "commission_discount": {"label": "Uji pemotongan komisi karena diskon",
                            "needs": ["commission.discount_threshold", "commission.discount_mechanic",
                                      "commission.discount_factor", "commission.discount_potong_rp",
                                      "commission.discount_threshold_type"],
                            "inputs": [I("discount", "Diskon baris", "pct", 15, "%"),
                                       I("commission", "Komisi awal", "money", 1_000_000, "Rp"),
                                       I("quantity", "Qty", "decimal", 100, "satuan")],
                            "run": _commission_discount},
    "receiving_over": {"label": "Uji penerimaan melebihi PO",
                       "needs": ["purchasing.receive_tolerance_percent", "receiving.block_over_remaining"],
                       "inputs": [I("po_qty", "Qty PO", "decimal", 1000, "satuan"),
                                  I("received_total", "Total diterima", "decimal", 1030, "satuan")],
                       "run": _receiving_over},
    "bill_match": {"label": "Uji 3-way match tagihan supplier",
                   "needs": ["purchasing.bill_qty_tolerance_percent",
                             "purchasing.bill_price_tolerance_percent"],
                   "inputs": [I("received_qty", "Qty diterima", "decimal", 1000, "satuan"),
                              I("billed_qty", "Qty ditagih", "decimal", 1010, "satuan"),
                              I("po_price", "Harga PO", "money", 100_000, "Rp"),
                              I("billed_price", "Harga ditagih", "money", 108_000, "Rp")],
                   "run": _bill_match},
    "qc_grade": {"label": "Tentukan grade dari poin cacat",
                 "needs": ["qc.grade_thresholds.a_max", "qc.grade_thresholds.b_max",
                           "qc.four_point_enabled"],
                 "inputs": [I("points", "Poin cacat 4-point", "decimal", 25, "poin")],
                 "run": _qc_grade},
    "stock_class": {"label": "Klasifikasi Fast/Slow/Dead",
                    "needs": ["inventory.stock_analytics.fast_max_days",
                              "inventory.stock_analytics.slow_max_days"],
                    "inputs": [I("days_since_sale", "Hari sejak terjual", "int", 45, "hari")],
                    "run": _stock_class},
    "reorder": {"label": "Hitung titik pesan ulang",
                "needs": ["inventory.reorder.velocity_window_days", "inventory.reorder.safety_days"],
                "inputs": [I("sold_qty", "Terjual di jendela", "decimal", 900, "satuan"),
                           I("lead_time_days", "Lead time supplier", "int", 14, "hari")],
                "run": _reorder},
    "uom_variance": {"label": "Uji selisih konversi satuan",
                     "needs": ["uom.warn_pct", "uom.block_pct", "uom.allow_override"],
                     "inputs": [I("expected", "Qty harapan", "decimal", 47.25, ""),
                                I("actual", "Qty aktual", "decimal", 48.5, "")],
                     "run": _uom_variance},
    "lot_enforce": {"label": "Uji kewajiban nomor lot",
                    "needs": ["lot.enforcement_mode", "lot.require_supplier_lot", "lot.require_dye_lot"],
                    "inputs": [I("has_supplier_lot", "Lot supplier terisi?", "bool", False),
                               I("has_dye_lot", "Dye lot terisi?", "bool", False)],
                    "run": _lot_enforce},
    "lot_number": {"label": "Contoh nomor lot", "needs": ["lot.number_format"],
                   "inputs": [I("sequence", "Urutan ke-", "int", 7, "")], "run": _lot_number},
    "makloon_variance": {"label": "Uji selisih hasil makloon",
                         "needs": ["makloon.variance_tolerance_pct", "makloon.default_shrinkage_pct",
                                   "makloon.auto_claim"],
                         "inputs": [I("sent_qty", "Dikirim", "decimal", 1000, "satuan"),
                                    I("returned_qty", "Kembali", "decimal", 950, "satuan")],
                         "run": _makloon_variance},
    "payroll_bpjs": {"label": "Hitung iuran BPJS",
                     "needs": ["hr.bpjs.kes_rate_employee", "hr.bpjs.kes_rate_employer",
                               "hr.bpjs.jht_rate_employee", "hr.bpjs.jht_rate_employer",
                               "hr.bpjs.jp_rate_employee", "hr.bpjs.jp_rate_employer",
                               "hr.bpjs.jkm_rate_employer", "hr.bpjs.kes_ceiling",
                               "hr.bpjs.jp_ceiling"],
                     "inputs": [I("salary", "Gaji bruto", "money", 8_000_000, "Rp")],
                     "run": _payroll_bpjs},
    "payroll_overtime": {"label": "Hitung upah lembur",
                         "needs": ["hr.overtime.multiplier", "hr.overtime.hours_divisor"],
                         "inputs": [I("salary", "Gaji bulanan", "money", 5_000_000, "Rp"),
                                    I("overtime_hours", "Jam lembur", "decimal", 4, "jam")],
                         "run": _payroll_overtime},
    "payroll_pph21": {"label": "Metode PPh 21", "needs": ["hr.ter_enabled"],
                      "inputs": [I("gross", "Bruto bulanan", "money", 8_000_000, "Rp")],
                      "run": _payroll_pph21},
    "min_cut": {"label": "Uji minimum potong kain", "needs": ["inventory.min_cut_qty"],
                "inputs": [I("qty", "Qty diminta", "decimal", 0.3, "satuan")], "run": _min_cut},
    "po_supplier": {"label": "Uji kewajiban supplier master",
                    "needs": ["purchasing.require_supplier_master"],
                    "inputs": [I("has_supplier_master", "PO pilih supplier terdaftar?", "bool", False)],
                    "run": _po_supplier},
    "interco": {"label": "Uji kewajiban transfer antar entitas",
                "needs": ["inventory.intercompany_transfer_required"],
                "inputs": [I("uses_other_entity_stock", "Pakai stok entitas lain?", "bool", True)],
                "run": _interco},
    "quotation": {"label": "Alur penawaran", "needs": ["sales.quotation_enabled"],
                  "inputs": [], "run": _quotation},
    "currency": {"label": "Format tampilan uang", "needs": ["finance.base_currency"],
                 "inputs": [I("amount", "Nominal", "money", 1_250_000, "")], "run": _currency},
    "fiscal_year": {"label": "Tentukan tahun buku", "needs": ["finance.fiscal_year_end_month"],
                    "inputs": [I("period", "Periode (YYYY-MM)", "text", "2026-07", "")],
                    "run": _fiscal_year},
    "price_deviation": {"label": "Uji deviasi harga beli",
                        "needs": ["purchasing.price_deviation_approval_percent"],
                        "inputs": [I("reference_price", "Harga acuan", "money", 100_000, "Rp"),
                                   I("po_price", "Harga di PO", "money", 115_000, "Rp")],
                        "run": _price_deviation},
    "approval": {"label": "Uji rantai persetujuan", "needs": ["approval.extra_levels"],
                 "inputs": [I("amount", "Nilai dokumen", "money", 600_000_000, "Rp"),
                            I("doc_type", "Jenis dokumen", "text", "purchase_order", "")],
                 "run": _approval},
}


def get(sim_id: str) -> Dict[str, Any]:
    sim = SIMULATORS.get(sim_id)
    if not sim:
        raise KeyError(f"Simulator '{sim_id}' tidak tersedia")
    return sim


def run(sim_id: str, values: Dict[str, Any], sample: Dict[str, Any]) -> Dict[str, Any]:
    sim = get(sim_id)
    fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]] = sim["run"]
    merged = {**{i["name"]: i["default"] for i in sim["inputs"]}, **(sample or {})}
    out = fn(values, merged)
    return {"simulator": sim_id, "label": sim["label"], "inputs": sim["inputs"],
            "sample": merged, "config_used": values, **out}


def catalog() -> List[Dict[str, Any]]:
    return [{"id": k, "label": v["label"], "needs": v["needs"], "inputs": v["inputs"]}
            for k, v in SIMULATORS.items()]
