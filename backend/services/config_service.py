"""Config service (Fase 1A) — Configuration Foundation.

Prinsip user: SEMUA CONFIGURABLE, TIDAK ADA HARDCODE.
- `system_settings`  (prefix set_)    : pengaturan global + override per-entitas
- `payment_terms`    (prefix pterm_)  : term pembayaran (tunai/kredit/DP/bertahap)
- `approval_rules`   (prefix aprule_) : matriks approval per dokumen/entitas/threshold

config_service menyediakan resolver "effective settings" (global di-override entitas),
kalkulasi pajak (PPN excluded/included), dan evaluasi approval.
"""
from typing import Any, Dict, List, Optional
from db import db
from core_utils import now_iso, new_id, DEFAULT_ENTITY_ID

GLOBAL_SCOPE = "global"

# Default global settings (seed sekali, lalu editable dari Admin → Pengaturan)
DEFAULT_GLOBAL_SETTINGS: Dict[str, Any] = {
    "tax": {
        "ppn_rate": 12.0,            # % — tarif resmi UU HPP (sejak 2025)
        # F-10 Coretax — DPP Nilai Lain = 11/12 × harga jual (PMK 131/2024) untuk barang
        # non-mewah → PPN efektif 11%. Configurable per entitas via override scope.
        "dpp_nilai_lain": True,
        "ppn_mode": "excluded",     # excluded = ditambah saat invoice | included
        "efaktur_enabled": True,    # PKP terbit Faktur Pajak
        # EPIC 7 — Pajak: butir PPh/withholding CONFIGURABLE per tax-plan perusahaan.
        # basis: "payroll" (otomatis dari payroll pph21) | "omzet" (rate% × peredaran)
        #        | "manual" (rekam DPP → rate% × DPP). enabled → tampil di rekap.
        "pph_items": [
            {"code": "pph21", "name": "PPh 21 — Karyawan", "rate": 0.0, "basis": "payroll", "enabled": True},
            {"code": "pph23", "name": "PPh 23 — Jasa/Sewa", "rate": 2.0, "basis": "manual", "enabled": True},
            {"code": "pph_final_pp23", "name": "PPh Final UMKM (PP23)", "rate": 0.5, "basis": "omzet", "enabled": False},
        ],
    },
    "finance": {
        "base_currency": "IDR",
        "fiscal_year_end_month": 12,
        "default_payment_term_code": "NET30",
    },
    "sales": {
        "quotation_enabled": False,
        "allow_partial_shipment": True,
        # Diskon manual DIHAPUS — potongan harga hanya via Harga Khusus (special-price).
        "allow_order_discount": False,
        "allow_item_discount": False,
    },
    "inventory": {
        "default_uom": "meter",
        "min_cut_qty": 0.5,
        # Stock Analytics (Fase 5) — ambang klasifikasi Fast/Slow/Dead & jendela kecepatan jual.
        # Basis klasifikasi = hari sejak PENJUALAN terakhir (movement outbound_ship).
        "stock_analytics": {
            "fast_max_days": 30,        # ≤ 30 hari sejak terjual → Fast
            "slow_max_days": 90,        # 31–90 → Slow ; > 90 (atau tak pernah terjual & tua) → Dead
            "velocity_window_days": 90,  # jendela hitung qty terjual & rata-rata harian
        },
        # Reorder/ROP (Fase 5) — usulan ROP dinamis berbasis kecepatan jual.
        # ROP disarankan = rata2 jual harian × (lead_time + safety_days).
        "reorder": {
            "velocity_window_days": 90,
            "safety_days": 7,
        },
        "intercompany_transfer_required": True,  # KN_15 D-? — jual stok entitas lain wajib transfer
    },
    # Fase 3 — Purchasing (Procurement)
    "purchasing": {
        "receive_tolerance_percent": 2.0,   # toleransi qty terima vs PO (benang ±2%)
        "require_supplier_master": False,    # True = PO wajib pilih supplier master
        "qc_on_receipt": True,               # Depth #3a — barang masuk → karantina dulu (inspeksi QC)
        "price_deviation_approval_percent": 10.0,  # Depth #3 — harga PO > price-list +X% → wajib approval
        "allow_item_discount": True,         # P0-1 — izinkan diskon per item pada PO
        "allow_order_discount": True,        # P0-1 — izinkan diskon level order pada PO
        "bill_qty_tolerance_percent": 0.0,   # P0-2 — toleransi qty tagih vs diterima/dipesan (3-way)
        "bill_price_tolerance_percent": 5.0, # P0-2 — toleransi harga bill vs harga PO
    },
    # Fase 6.2 (P1) — QC 4-Point Inspection (grade dari poin defect; configurable)
    "qc": {
        "grade_thresholds": {"a_max": 20.0, "b_max": 40.0},  # poin ≤a_max=A, ≤b_max=B, >b_max=C
        "four_point_enabled": True,          # aktifkan inspeksi 4-point per roll saat QC
    },
    # Fase 7.1 (P2) — Multi-Level Sequential Approval (tingkat tambahan di atas L1 dari approval_rules)
    "approval": {
        # extra_levels[doc_type] = level tambahan (L2, L3, …) yang aktif bila amount ≥ min_amount.
        # Default PO: ≥500jt butuh persetujuan Direksi (role admin) SETELAH Manager (L1).
        "extra_levels": {
            "purchase_order": [
                {"min_amount": 500000000, "role": "admin", "label": "Direksi"},
            ],
        },
    },
    # Sub-fase 1.7 — Allocation Policy (KN_15 §6.0) — CONFIGURABLE + CLARITY
    "allocation": {
        "mode": "auto",                                            # auto | assisted | manual
        "priority_order": ["owner", "lot", "location", "roll_efficiency"],  # owner selalu HARD #1
        "lot_mode": "prefer_single",                               # prefer_single | strict_single | allow_mixed
        "lot_selection": "fefo",                                   # fefo | fifo | smallest_fit | largest_fit
        "location_pref": "single_warehouse",                       # single_warehouse | nearest_customer | fewest_splits
        "allow_intercompany": True,
        "allow_partial": True,
        "dye_lot_strict": False,                                   # P0-4 — paksa 1 dye lot (tekstil)
    },
    # EPIC 0 (F4) — UI feature flags (config-driven; dipakai sidebar "Segera Hadir")
    "ui": {
        "show_coming_soon": True,        # tampilkan grup "Segera Hadir" di sidebar
        "coming_soon_collapsed": True,   # grup "Segera Hadir" default ter-collapse
    },
    # EPIC 0 (F5) — Role-home registry (landing view per role; configurable)
    "role_home": {
        "admin": "admin",
        "manager": "reports",
        "sales": "sales",
        "warehouse": "operations",
    },
    # EPIC 7A — AR / Piutang aging + denda (late fee) — ESTIMASI informasional (tidak posting)
    "ar": {
        "denda_rate_pct_per_month": 2.0,   # % per bulan (prorata per 30 hari) atas saldo overdue
        "grace_days": 0,                   # masa tenggang sebelum denda dihitung
        "aging_buckets": [30, 60, 90],     # ambang hari aging (1-30 / 31-60 / 61-90 / 90+)
    },
    # EPIC 4 — Incentive Engine v2 (strategy + mekanik diskon default + margin cap)
    "commission": {
        "strategy": "per_sku",            # per_sku (v2, default) | achievement_tiered (arsip)
        "incentive_unit": "meter",        # UOM dasar per_unit_amount
        "default_margin_cap_pct": 50.0,   # komisi per-line ≤ X% margin line (margin-aware, EPIC3 WAC)
        "discount_threshold_type": "pct", # pct | rp_per_unit — basis ambang diskon
        "discount_threshold": 10.0,       # ambang diskon line (>= → mekanik aktif)
        "discount_mechanic": "tier_factor",  # tier_factor | potong_rp | cutoff
        "discount_factor": 0.5,           # tier_factor: komisi × faktor bila diskon > ambang
        "discount_potong_rp": 0.0,        # potong_rp: kurangi per_unit_amount (Rp/unit) bila > ambang
    },
}

DEFAULT_PAYMENT_TERMS: List[Dict[str, Any]] = [
    {"code": "CASH",  "name": "Tunai / POS",          "type": "cash",        "net_days": 0,  "dp_percent": 0,  "installment_count": 0, "sort": 1},
    {"code": "NET7",  "name": "Kredit NET 7 Hari",    "type": "credit",      "net_days": 7,  "dp_percent": 0,  "installment_count": 0, "sort": 2},
    {"code": "NET14", "name": "Kredit NET 14 Hari",   "type": "credit",      "net_days": 14, "dp_percent": 0,  "installment_count": 0, "sort": 3},
    {"code": "NET30", "name": "Kredit NET 30 Hari",   "type": "credit",      "net_days": 30, "dp_percent": 0,  "installment_count": 0, "sort": 4},
    {"code": "DP50",  "name": "DP 50% + Pelunasan",   "type": "dp",          "net_days": 14, "dp_percent": 50, "installment_count": 0, "sort": 5},
    {"code": "INST3", "name": "Bertahap 3x",          "type": "installment", "net_days": 30, "dp_percent": 0,  "installment_count": 3, "sort": 6},
]

DEFAULT_APPROVAL_RULES: List[Dict[str, Any]] = [
    {"doc_type": "sales_order",    "entity_id": "all", "min_amount": 0,         "max_amount": 50000000,  "required_role": "",        "sort": 1},
    {"doc_type": "sales_order",    "entity_id": "all", "min_amount": 50000000,  "max_amount": 200000000, "required_role": "manager", "sort": 2},
    {"doc_type": "sales_order",    "entity_id": "all", "min_amount": 200000000, "max_amount": None,       "required_role": "admin",   "sort": 3},
    {"doc_type": "discount",       "entity_id": "all", "min_amount": 0,         "max_amount": 10,         "required_role": "",        "sort": 1, "is_percent": True},
    {"doc_type": "discount",       "entity_id": "all", "min_amount": 10,        "max_amount": None,       "required_role": "manager", "sort": 2, "is_percent": True},
    {"doc_type": "purchase_order", "entity_id": "all", "min_amount": 0,         "max_amount": 100000000, "required_role": "",        "sort": 1},
    {"doc_type": "purchase_order", "entity_id": "all", "min_amount": 100000000, "max_amount": None,       "required_role": "manager", "sort": 2},
    {"doc_type": "purchase_requisition", "entity_id": "all", "min_amount": 0,         "max_amount": 50000000,  "required_role": "",        "sort": 1},
    {"doc_type": "purchase_requisition", "entity_id": "all", "min_amount": 50000000,  "max_amount": None,       "required_role": "manager", "sort": 2},
]


# ── Seed defaults (idempotent) ───────────────────────────────────────────────

async def seed_config_defaults() -> Dict[str, int]:
    created = {"settings": 0, "payment_terms": 0, "approval_rules": 0}
    if await db.system_settings.count_documents({"scope": GLOBAL_SCOPE}) == 0:
        await db.system_settings.insert_one({
            "id": new_id("set"), "scope": GLOBAL_SCOPE,
            **DEFAULT_GLOBAL_SETTINGS,
            "created_at": now_iso(), "updated_at": now_iso(),
        })
        created["settings"] = 1
    if await db.payment_terms.count_documents({}) == 0:
        await db.payment_terms.insert_many([
            # FASE E-4 (E4.3) — lahir sebagai baris GLOBAL (`entity_id="all"`): berlaku
            # untuk semua badan usaha sampai ada yang menimpanya dengan "Buat khusus".
            {"id": new_id("pterm"), "entity_id": "all", **t, "active": True,
             "created_at": now_iso(), "updated_at": now_iso()} for t in DEFAULT_PAYMENT_TERMS
        ])
        created["payment_terms"] = len(DEFAULT_PAYMENT_TERMS)
    if await db.approval_rules.count_documents({}) == 0:
        await db.approval_rules.insert_many([
            {"id": new_id("aprule"), "is_percent": r.get("is_percent", False), "active": True,
             "created_at": now_iso(), "updated_at": now_iso(),
             **{k: v for k, v in r.items() if k != "is_percent"}} for r in DEFAULT_APPROVAL_RULES
        ])
        created["approval_rules"] = len(DEFAULT_APPROVAL_RULES)
    return created


# ── Effective settings (global di-override per-entitas) ──────────────────────

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


async def get_global_settings() -> Dict[str, Any]:
    doc = await db.system_settings.find_one({"scope": GLOBAL_SCOPE}, {"_id": 0})
    if not doc:
        await seed_config_defaults()
        doc = await db.system_settings.find_one({"scope": GLOBAL_SCOPE}, {"_id": 0})
    return doc or {"scope": GLOBAL_SCOPE, **DEFAULT_GLOBAL_SETTINGS}


async def get_effective_settings(entity_id: Optional[str] = None) -> Dict[str, Any]:
    stored = await get_global_settings()
    # Deep-merge default kode (sumber kebenaran key terbaru) ← stored global (nilai user menang).
    # Ini memastikan key default baru (mis. purchasing.price_deviation_approval_percent)
    # otomatis tersedia & configurable walau doc lama belum memuatnya.
    default_sections = {k: v for k, v in DEFAULT_GLOBAL_SETTINGS.items() if isinstance(v, dict)}
    stored_sections = {k: v for k, v in stored.items() if isinstance(v, dict)}
    sections = _deep_merge(default_sections, stored_sections)
    if entity_id and entity_id != "all":
        override = await db.system_settings.find_one({"scope": entity_id}, {"_id": 0})
        if override:
            ov_sections = {k: v for k, v in override.items() if isinstance(v, dict)}
            sections = _deep_merge(sections, ov_sections)
        # entitas PKP/non-PKP mempengaruhi pajak efektif
        entity = await db.business_entities.find_one({"id": entity_id}, {"_id": 0})
        if entity:
            is_pkp = (entity.get("default_tax_mode") == "ppn")
            sections.setdefault("tax", {})
            sections["tax"] = dict(sections.get("tax", {}))
            sections["tax"]["is_pkp"] = is_pkp
            if not is_pkp:
                sections["tax"]["ppn_rate"] = 0.0
                sections["tax"]["efaktur_enabled"] = False
    else:
        sections.setdefault("tax", {})
        sections["tax"] = dict(sections.get("tax", {}))
        sections["tax"]["is_pkp"] = True
    return {"scope": entity_id or "all", **sections}


# ── Kalkulasi pajak (PPN) ────────────────────────────────────────────────────

async def compute_tax(subtotal: float, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """PPN per entitas. F-10 Coretax: dpp_nilai_lain=True → DPP = 11/12 × harga jual,
    PPN = tarif × DPP (efektif tarif × 11/12 dari harga jual). Nilai rupiah identik
    rezim 11% lama; representasi Faktur Pajak (kolom DPP, tarif 12%, kode 04) berbeda."""
    s = await get_effective_settings(entity_id)
    tax = s.get("tax", {})
    rate = float(tax.get("ppn_rate", 0) or 0)
    mode = tax.get("ppn_mode", "excluded")
    is_pkp = tax.get("is_pkp", True)
    use_nl = bool(tax.get("dpp_nilai_lain", False))
    subtotal = round(float(subtotal or 0), 2)
    if not is_pkp or rate <= 0:
        return {"ppn_rate": 0.0, "effective_rate": 0.0, "dpp_nilai_lain": False,
                "ppn_mode": mode, "is_pkp": is_pkp, "dpp": subtotal, "harga_jual": subtotal,
                "ppn_amount": 0.0, "grand_total": subtotal}
    dpp_factor = 11.0 / 12.0 if use_nl else 1.0
    eff_rate = rate * dpp_factor
    if mode == "included":
        harga_jual = round(subtotal / (1 + eff_rate / 100), 2)
        ppn = round(subtotal - harga_jual, 2)
        grand = subtotal
    else:  # excluded (default)
        harga_jual = subtotal
        ppn = round(subtotal * eff_rate / 100, 2)
        grand = round(subtotal + ppn, 2)
    dpp = round(harga_jual * dpp_factor, 2)
    return {"ppn_rate": rate, "effective_rate": round(eff_rate, 4), "dpp_nilai_lain": use_nl,
            "ppn_mode": mode, "is_pkp": is_pkp, "dpp": dpp, "harga_jual": harga_jual,
            "ppn_amount": ppn, "grand_total": grand}


async def migrate_tax_regime() -> None:
    """F-10 — migrasi rezim PPN 11% flat → 12% + DPP Nilai Lain 11/12 (idempotent).
    Rupiah tak berubah (efektif tetap 11%). Scope dgn tarif custom → flag False eksplisit
    agar default baru tidak mengubah perilakunya."""
    await db.system_settings.update_many(
        {"tax.ppn_rate": 11.0, "tax.dpp_nilai_lain": {"$exists": False}},
        {"$set": {"tax.ppn_rate": 12.0, "tax.dpp_nilai_lain": True, "updated_at": now_iso()}})
    await db.system_settings.update_many(
        {"tax": {"$exists": True}, "tax.dpp_nilai_lain": {"$exists": False}},
        {"$set": {"tax.dpp_nilai_lain": False, "updated_at": now_iso()}})


# ── Evaluasi approval (matriks configurable) ─────────────────────────────────

async def evaluate_approval(doc_type: str, amount: float, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Tentukan apakah dokumen butuh approval & role minimum, dari approval_rules.
    Rule entitas-spesifik diutamakan; fallback ke entity_id='all'. amount untuk
    doc_type='discount' adalah persen (is_percent)."""
    rules = await db.approval_rules.find(
        {"doc_type": doc_type, "active": True}, {"_id": 0}
    ).sort("sort", 1).to_list(200)
    scoped = [r for r in rules if r.get("entity_id") == entity_id] if entity_id else []
    pool = scoped if scoped else [r for r in rules if r.get("entity_id") in (None, "all")]
    amount = float(amount or 0)
    for r in pool:
        lo = float(r.get("min_amount", 0) or 0)
        hi = r.get("max_amount")
        hi = float(hi) if hi is not None else float("inf")
        if lo <= amount < hi or (amount == hi == float("inf")):
            role = r.get("required_role") or ""
            return {"requires_approval": bool(role), "required_role": role or None,
                    "rule_id": r.get("id"), "doc_type": doc_type}
    return {"requires_approval": False, "required_role": None, "rule_id": None, "doc_type": doc_type}


async def build_approval_chain(doc_type: str, amount: float, entity_id: Optional[str] = None,
                               force_level1_role: Optional[str] = None) -> Dict[str, Any]:
    """Fase 7.1 — Bangun RANTAI approval berjenjang (multi-level sequential).

    Level 1 = hasil `evaluate_approval` (matriks approval_rules, biasanya manager).
    Level 2+ = dari settings `approval.extra_levels[doc_type]` (mis. ≥500jt → Direksi/admin),
    AKTIF hanya bila approval level-1 sudah diperlukan (atau dipaksa via force_level1_role,
    mis. deviasi harga). Backward-compatible: doc tanpa extra_levels → rantai 1 elemen.

    Return:
      requires_approval: bool
      required_role:     role level pertama yang masih pending (untuk kompat lama)
      approval_chain:    [{level, required_role, label, status:'pending', approved_by:'', approved_at:''}]
    """
    base = await evaluate_approval(doc_type, amount, entity_id)
    chain: List[Dict[str, Any]] = []

    l1_role = base.get("required_role")
    if force_level1_role and not l1_role:
        l1_role = force_level1_role
    if l1_role:
        chain.append({"level": 1, "required_role": l1_role, "label": "Persetujuan",
                      "status": "pending", "approved_by": "", "approved_by_id": "", "approved_at": ""})

    if chain:  # extra levels hanya bila approval L1 sudah diperlukan
        settings = await get_effective_settings(entity_id)
        extra = (((settings.get("approval") or {}).get("extra_levels") or {}).get(doc_type) or [])
        amt = float(amount or 0)
        for lv in extra:
            try:
                min_amt = float(lv.get("min_amount", 0) or 0)
            except (TypeError, ValueError):
                min_amt = 0.0
            role = (lv.get("role") or "").strip()
            if role and amt >= min_amt:
                chain.append({"level": len(chain) + 1, "required_role": role,
                              "label": lv.get("label") or role.title(),
                              "status": "pending", "approved_by": "", "approved_by_id": "", "approved_at": ""})

    return {
        "requires_approval": bool(chain),
        "required_role": chain[0]["required_role"] if chain else None,
        "approval_chain": chain,
        "rule_id": base.get("rule_id"),
        "doc_type": doc_type,
    }


def current_pending_level(chain: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Level pending pertama dalam rantai (None bila semua approved)."""
    for lv in chain or []:
        if lv.get("status") != "approved":
            return lv
    return None


# ── Pricing engine (Fase 1B) — diskon + PPN, INVARIAN-SAFE ───────────────────
# PENTING (verify_data_integrity L4): item.subtotal = price×quantity (GROSS) dan
# order.total_amount = Σ subtotal (GROSS) HARUS dipertahankan. Diskon & pajak
# disimpan di FIELD TERPISAH (discount_amount/line_total/net_subtotal/dpp/ppn/
# grand_total) sehingga invarian akuntansi lama tetap valid.

def _clamp_pct(v: float) -> float:
    try:
        return max(0.0, min(100.0, float(v or 0)))
    except (TypeError, ValueError):
        return 0.0


async def compute_order_pricing(
    raw_items: List[Dict[str, Any]],
    entity_id: Optional[str] = None,
    order_discount_percent: float = 0.0,
    settings: Optional[Dict[str, Any]] = None,
    cfg_section: str = "sales",
    tax_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Hitung breakdown harga order: gross subtotal, diskon item, diskon order,
    DPP, PPN, grand total. Menghormati toggle settings.{cfg_section}.allow_*_discount &
    PKP/non-PKP entitas. `raw_items` = list {price, quantity, discount_percent?, ...}.

    Parameter:
      - cfg_section: bagian settings sumber toggle diskon ("sales" | "purchasing").
      - tax_override: paksa mode pajak ("non_ppn" → tanpa PPN; "ppn" → ikut rate config;
        None/"" → ikut compute_tax dari config entitas).

    Mengembalikan dict siap-simpan (items diperkaya + agregat). INVARIAN-SAFE:
      - item.subtotal = price × quantity   (GROSS, tak terpengaruh diskon)
      - total_amount  = Σ item.subtotal    (GROSS)
      - net_subtotal  = DPP base = total_amount − items_discount − order_discount
    """
    s = settings or await get_effective_settings(entity_id)
    disc_cfg = s.get(cfg_section, {}) or {}
    allow_item = bool(disc_cfg.get("allow_item_discount", True))
    allow_order = bool(disc_cfg.get("allow_order_discount", True))

    priced_items: List[Dict[str, Any]] = []
    gross_total = 0.0
    items_discount_total = 0.0
    for it in raw_items:
        price = round(float(it.get("price", 0) or 0), 2)
        qty = float(it.get("quantity", 0) or 0)
        subtotal = round(price * qty, 2)                      # GROSS — invarian
        disc_pct = _clamp_pct(it.get("discount_percent", 0)) if allow_item else 0.0
        disc_amt = round(subtotal * disc_pct / 100.0, 2)
        line_total = round(subtotal - disc_amt, 2)
        enriched = dict(it)
        enriched.update({
            "price": price, "subtotal": subtotal,
            "discount_percent": disc_pct, "discount_amount": disc_amt,
            "line_total": line_total,
        })
        priced_items.append(enriched)
        gross_total += subtotal
        items_discount_total += disc_amt

    gross_total = round(gross_total, 2)
    items_discount_total = round(items_discount_total, 2)
    after_item = round(gross_total - items_discount_total, 2)
    order_disc_pct = _clamp_pct(order_discount_percent) if allow_order else 0.0
    order_disc_amt = round(after_item * order_disc_pct / 100.0, 2)
    net_subtotal = round(after_item - order_disc_amt, 2)      # = DPP base

    if (tax_override or "").strip().lower() == "non_ppn":
        # Supplier non-PKP / transaksi tanpa PPN → tanpa Faktur Pajak Masukan.
        tax = {"ppn_rate": 0.0, "effective_rate": 0.0, "dpp_nilai_lain": False,
               "ppn_mode": "excluded", "is_pkp": False, "dpp": net_subtotal,
               "harga_jual": net_subtotal, "ppn_amount": 0.0, "grand_total": net_subtotal}
    else:
        tax = await compute_tax(net_subtotal, entity_id)
    return {
        "items": priced_items,
        "total_amount": gross_total,                          # GROSS (invarian)
        "items_discount_total": items_discount_total,
        "order_discount_percent": order_disc_pct,
        "order_discount_amount": order_disc_amt,
        "discount_total": round(items_discount_total + order_disc_amt, 2),
        "net_subtotal": net_subtotal,
        "dpp": tax["dpp"],
        "dpp_nilai_lain": tax.get("dpp_nilai_lain", False),
        "effective_rate": tax.get("effective_rate", tax["ppn_rate"]),
        "ppn_rate": tax["ppn_rate"],
        "ppn_mode": tax["ppn_mode"],
        "is_pkp": tax["is_pkp"],
        "ppn_amount": tax["ppn_amount"],
        "grand_total": tax["grand_total"],
    }


def role_satisfies(actor_role: str, required_role: Optional[str]) -> bool:
    """Cek apakah role aktor memenuhi required_role dari matriks approval.

    FASE E-8 (E8.1) — peringkat peran TIDAK lagi ditulis di sini. Dulu angkanya
    disalin di dua tempat (`so_approvals.ROLE_RANK`) sehingga menambah peran berarti
    dua tempat harus diingat. Sumber tunggal sekarang `backend/role_registry.py`.
    """
    from role_registry import role_satisfies as _rs
    return _rs(actor_role, required_role)


# ── Allocation Policy resolver (Sub-fase 1.7, KN_15 §6.0) ────────────────────
# Hierarki override: order > customer > system-settings(default). OWNER selalu HARD #1.

VALID_ALLOC = {
    "mode": {"auto", "assisted", "manual"},
    "lot_mode": {"prefer_single", "strict_single", "allow_mixed"},
    "lot_selection": {"fefo", "fifo", "smallest_fit", "largest_fit"},
    "location_pref": {"single_warehouse", "nearest_customer", "fewest_splits"},
}


def _sanitize_alloc(policy: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    """Pastikan nilai enum valid; jika tidak, pakai base/default."""
    out = dict(base)
    for k, v in (policy or {}).items():
        if k in VALID_ALLOC:
            out[k] = v if v in VALID_ALLOC[k] else base.get(k)
        elif k in ("allow_intercompany", "allow_partial", "dye_lot_strict"):
            out[k] = bool(v)
        elif k == "priority_order" and isinstance(v, list) and v:
            # owner selalu #1 (HARD)
            rest = [x for x in v if x in ("lot", "location", "roll_efficiency")]
            out[k] = ["owner"] + [x for x in rest if x != "owner"]
        elif k in out:
            out[k] = v
    return out


async def get_allocation_policy(
    entity_id: Optional[str] = None,
    customer: Optional[Dict[str, Any]] = None,
    order_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Effective allocation policy: system(global+entity) → customer.allocation_policy → order_overrides."""
    s = await get_effective_settings(entity_id)
    base = dict(DEFAULT_GLOBAL_SETTINGS["allocation"])
    base = _sanitize_alloc(s.get("allocation", {}) or {}, base)
    # FASE G-0 — `inventory.intercompany_transfer_required` DULU tombol palsu (0 consumer).
    # Sekarang benar-benar mengikat: bila wajib transfer, alokasi TIDAK BOLEH memakai stok
    # milik entitas lain secara diam-diam — pengguna harus membuat Transaksi Antar-Entitas
    # lebih dulu sehingga laba/HPP setiap PT tetap benar.
    if bool((s.get("inventory", {}) or {}).get("intercompany_transfer_required", False)):
        base["allow_intercompany"] = False
        base["intercompany_blocked_reason"] = (
            "Pengaturan 'Wajib transfer sebelum jual stok entitas lain' aktif — buat "
            "Transaksi Antar-Entitas dulu sebelum memakai stok milik PT lain.")
    if customer and isinstance(customer.get("allocation_policy"), dict):
        base = _sanitize_alloc(customer["allocation_policy"], base)
    # Customer lot_policy (KN_15 R4) → peta ke lot_mode bila ada
    cust_lot_policy = (customer or {}).get("lot_policy")
    lot_policy_map = {"strict_single": "strict_single", "prefer_single": "prefer_single", "allow_mixed": "allow_mixed"}
    if cust_lot_policy in lot_policy_map:
        base["lot_mode"] = lot_policy_map[cust_lot_policy]
    # P0-4 — customer flag "enforce_single_dye_lot" → paksa alokasi 1 dye lot.
    if (customer or {}).get("enforce_single_dye_lot"):
        base["dye_lot_strict"] = True
    if order_overrides:
        base = _sanitize_alloc(order_overrides, base)
    return base

