"""M3 + FASE D — Makloon Order service: orkestrasi transaksi subkontrak (Procure→Process→Pay).

Alur (per step, reuse engine roll-SSOT + GL Fase M2):
  1) issue  : bahan `available` → `subcon` (WIP-at-vendor) + JE Dr WIP / Cr Persediaan.
  2) service: tagihan JASA makloon (vendor_bill ber-makloon_id) + JE Dr WIP+PPN / Cr Hutang.
  3) receive: konsumsi roll subcon (retire) → roll output baru (+barang sisa) `available`,
              LOT manual per roll + JE Dr Persediaan / Cr WIP (clear WIP → HPP output).
Rantai berlapis: output step-k jadi input step-(k+1) (unit_cost roll membawa HPP akumulatif).

FASE D (PS-03/PS-04/PS-08/PS-11 · keputusan D-04/D-05/D-07/D-09) menambahkan:
  * **Rantai dipaksa sistem** — output langkah N WAJIB = input langkah N+1; produk output
    wajib ditentukan per langkah (KN_18 §5.2).
  * **Kontrak mitra** (`supplier_contracts`) sebagai SSOT tarif (basis bebas + formula
    custom), **susut standar** (D-05) dan **toleransi selisih** (D-09) per mitra/kontrak.
  * **Estimasi berbasis GSM + lebar + susut** dengan angka antara yang bisa diaudit
    (`services/makloon_calc_service.py`); `yield_factor` hanya override sadar + alasan.
  * **Jejak konversi satuan** pada issue & receive (D-07) — mitra boleh memakai satuan
    sendiri (kg/bale/roll) dan sistem menyimpan doc↔base.
  * **Selisih & klaim** (`steps[].claim`) dengan approval manajer/admin dan konsekuensi
    potong bon / tagih ganti rugi / terima dengan catatan.
  * **HPP berjenjang** per langkah (`costing.steps[]`).
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from core_utils import new_id, now_iso, parse_decimal, safe_doc, rupiah
from services import stock_bucket_service as sb
from services import gl_service as gl
from services import contract_service as cs
from services import makloon_calc_service as mcalc
from services import makloon_claim_service as mclaim
from services import uom_rules_service as uomr
from services.roll_service import create_inbound_roll
from services.process_recipe_service import compute_forecast
from services import line_scope as _lines      # FASE L — satu pintu normalisasi lini
from services import master_registry as mreg   # FASE T — satu pembaca master tahapan

DRAFT, IN_PROCESS, PARTIAL, COMPLETED, CANCELLED = (
    "draft", "in_process", "partially_received", "completed", "cancelled")

# FASE T — aliran kain per langkah (lihat domain_registry.MATERIAL_FLOWS).
FLOW_MOVES, FLOW_SERVICE = "moves", "service_only"


async def _resolve_stage(step_in: Dict[str, Any], process_type: str, entity_id: str,
                         seq: int) -> Dict[str, Any]:
    """FASE T — tentukan TAHAP satu langkah dari master (dengan jalur kompatibilitas).

    Tiga jalur, dari yang paling eksplisit:
      1. `stage_code` diisi klien  → baris master itu yang dipakai.
      2. tidak diisi              → dicari lewat `process_type` (+`target_use`), yaitu
         cara 3 SPK sebelum FASE T menyimpan langkahnya. Ini yang menjaga angkanya
         tidak bergeser saat SPK lama dibuka/dihitung ulang.
      3. tidak ketemu juga        → langkah berperilaku seperti sebelum FASE T
         (`changes_stage=True`, kain bergerak). Diam-diam menolak akan mematikan
         instalasi yang masternya belum ter-seed.

    Mengembalikan bentuk yang SUDAH dinormalkan + `resolved_from` untuk jejak.
    """
    code = str(step_in.get("stage_code") or "").strip().lower()
    stage: Dict[str, Any] = {}
    src = ""
    if code:
        stage = await mreg.stage_meta(code, entity_id)
        src = f"stage_code='{code}'"
        if not stage:
            opts = [r["value"] for r in await mreg.active_stages(entity_id)]
            raise HTTPException(
                status_code=400,
                detail=f"Langkah {seq}: tahapan '{code}' tidak ada di master Tahapan Proses. "
                       f"Pilihan yang aktif: {', '.join(opts) or '(master belum ter-seed)'}. "
                       "Tambahkan tahapnya di Pengaturan → Master → Tahapan Proses.")
    if not stage:
        stage = await mreg.stage_by_process_type(process_type, entity_id,
                                                 step_in.get("target_use") or "")
        src = f"process_type='{process_type}'" if stage else "bawaan (tanpa master)"
    return {
        "code": stage.get("value", "") or "",
        "label": stage.get("label", "") or "",
        "kind": stage.get("kind", "") or ("makloon" if stage else ""),
        "seq": stage.get("seq", 0) or 0,
        "process_type": stage.get("process_type", "") or "",
        "target_use": stage.get("target_use", "") or "",
        "changes_stage": stage.get("changes_stage", True) is not False,
        "from_stage": stage.get("from_stage", "") or "",
        "to_stage": stage.get("to_stage", "") or "",
        "needs_vendor": bool(stage.get("needs_vendor")),
        "material_flow": stage.get("material_flow", "") or "",
        "material_flow_default": stage.get("material_flow_default", "") or "",
        "tariff_basis_default": stage.get("tariff_basis_default", "") or "",
        "found": bool(stage),
        "resolved_from": src,
    }


def _resolve_material_flow(stage: Dict[str, Any], step_in: Dict[str, Any],
                           warnings: List[str], seq: int) -> Dict[str, str]:
    """FASE T (keputusan pemilik 1c) — apakah KAIN bergerak pada langkah ini.

    Master menentukan apa yang BOLEH; langkah menentukan pilihannya bila master
    membuka dua-duanya (`either`). Bila langkah diam, dipakai `material_flow_default`
    master — dan itu **dicatat** di `estimate.explain[]`, bukan diputuskan diam-diam.
    """
    allowed = str(stage.get("material_flow") or "").strip().lower()
    picked = str(step_in.get("material_flow") or "").strip().lower()
    if allowed == "either":
        if picked in (FLOW_MOVES, FLOW_SERVICE):
            return {"flow": picked, "source": "pilihan pada langkah SPK"}
        fallback = str(stage.get("material_flow_default") or "").strip().lower()
        flow = fallback if fallback in (FLOW_MOVES, FLOW_SERVICE) else FLOW_MOVES
        return {"flow": flow,
                "source": f"bawaan master tahap '{stage.get('code') or '-'}'"}
    if allowed in (FLOW_MOVES, FLOW_SERVICE):
        if picked and picked != allowed:
            warnings.append(
                f"Langkah {seq}: aliran kain '{picked}' diabaikan — master tahap "
                f"'{stage.get('code') or '-'}' mengunci langkah ini pada "
                f"'{allowed}'. Ubah di Pengaturan → Master → Tahapan Proses bila "
                "tahap ini memang boleh dua-duanya.")
        return {"flow": allowed, "source": f"master tahap '{stage.get('code') or '-'}'"}
    # Tahap tanpa aliran kain (material/inspection) atau master belum ter-seed →
    # perilaku sebelum FASE T: kainnya bergerak.
    return {"flow": FLOW_MOVES, "source": "bawaan (tahap tanpa aliran kain di master)"}


# ─── FASE D (PS-03) — SATU definisi "override yield wajib beralasan" ─────────
# Kalimatnya berdiri di satu tempat saja supaya pesan penolakan tidak bercabang
# antara pintu HTTP, seed, dan migrasi.
YIELD_REASON_MSG = ("Langkah {seq}: mengisi yield secara manual adalah OVERRIDE atas "
                    "rumus GSM — alasan wajib diisi (kolom 'Alasan override yield').")


def assert_yield_reason(steps_in: List[Dict[str, Any]], settings: Dict[str, Any]) -> None:
    """PS-03 — override yield WAJIB beralasan; dijaga DI SERVICE, bukan di router.

    Kenapa dipindah ke sini (temuan POC FASE T uji T4): pagar ini dulu hanya berdiri
    di `routers/makloon_orders.py`. Akibatnya setiap penulis yang TIDAK lewat HTTP —
    `seed_realistic.py`, skrip migrasi, realisasi PR, panggilan service internal —
    bisa melahirkan langkah ber-`yield_factor` tanpa satu kata alasan. Buktinya ada
    di data demo sendiri: MKO-00001/00002 lahir dengan yield 3.8 tanpa alasan,
    sehingga data demo itu **tidak bisa dibuat ulang lewat API aplikasinya sendiri**
    (uji regresi T4 yang meniru SPK lama ditolak 400). Aturan uang/audit yang hanya
    berdiri di satu pintu bukan aturan — ia cuma kebiasaan pemakai pintu itu.

    Yang diperiksa tetap nilai yang **dikirim pemanggil**, bukan yield hasil resolusi
    kontrak: yield yang datang dari kontrak mitra justru sumber paling bisa dilacak,
    dan menuntut alasan untuknya berarti menuduh orang yang sudah benar.
    """
    if not settings.get("require_yield_reason", True):
        return
    for i, s in enumerate(steps_in or [], start=1):
        if parse_decimal(s.get("yield_factor")) <= 0:
            continue
        if not str(s.get("yield_override_reason") or "").strip():
            raise HTTPException(status_code=400, detail=YIELD_REASON_MSG.format(seq=i))


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _next_mko_number() -> str:
    last = await db.makloon_orders.find_one({}, {"_id": 0, "mko_number": 1}, sort=[("mko_number", -1)])
    n = 0
    if last and isinstance(last.get("mko_number"), str) and last["mko_number"].startswith("MKO-"):
        try:
            n = int(last["mko_number"].split("-")[1])
        except (ValueError, IndexError):
            n = await db.makloon_orders.count_documents({})
    else:
        n = await db.makloon_orders.count_documents({})
    return f"MKO-{n + 1:05d}"


async def _prod_snap(pid: str) -> Dict[str, str]:
    if not pid:
        return {"sku": "", "name": "", "base_unit": "", "line_code": ""}
    p = await db.products.find_one({"id": pid},
                                   {"_id": 0, "sku": 1, "name": 1, "base_unit": 1,
                                    "line_code": 1})
    return {"sku": (p or {}).get("sku", ""), "name": (p or {}).get("name", ""),
            "base_unit": (p or {}).get("base_unit", ""),
            # FASE L — lini kerja MD SPK makloon diambil dari produk bahan/output;
            # dipakai penyaring layar Makloon & papan lini.
            "line_code": _lines.norm((p or {}).get("line_code"))}


async def _makloon_name(mid: str) -> str:
    if not mid:
        return ""
    mk = await db.makloons.find_one({"id": mid}, {"_id": 0, "name": 1})
    return (mk or {}).get("name", "")


def _tl(order: Dict[str, Any], event: str, note: str = "") -> None:
    order.setdefault("timeline", []).append({"at": now_iso(), "event": event, "note": note})


async def _get_order(mko_id: str) -> Dict[str, Any]:
    o = await db.makloon_orders.find_one({"id": mko_id}, {"_id": 0})
    if not o:
        raise HTTPException(status_code=404, detail="Order makloon tidak ditemukan")
    return o


def _find_step(order: Dict[str, Any], seq: int) -> Dict[str, Any]:
    for s in order.get("steps", []):
        if int(s.get("seq")) == int(seq):
            return s
    raise HTTPException(status_code=404, detail=f"Step {seq} tidak ada pada order")


# ─── Create ──────────────────────────────────────────────────────────────────

async def create_makloon_order(payload: Dict[str, Any], *, entity_id: str,
                               actor_name: str) -> Dict[str, Any]:
    mode = payload.get("mode") or "process_only"
    if mode not in ("process_only", "buy_process"):
        raise HTTPException(status_code=400, detail="Mode harus process_only atau buy_process")
    steps_in = payload.get("steps") or []
    if not steps_in:
        raise HTTPException(status_code=400, detail="Minimal 1 step proses diperlukan")

    material_pid = payload.get("material_product_id")
    if not material_pid:
        raise HTTPException(status_code=400, detail="Produk bahan (material) wajib diisi")
    mat_snap = await _prod_snap(material_pid)
    material_qty = round(float(payload.get("material_qty") or 0), 2)
    if material_qty <= 0:
        raise HTTPException(status_code=400, detail="Qty bahan harus > 0")

    mko_id = new_id("mko")
    from_wh = payload.get("from_warehouse_id") or ""
    target_wh = payload.get("target_warehouse_id") or from_wh

    # FASE D — kebijakan makloon (toleransi/susut default, mode kontrak) & mesin konversi.
    # E-4 (E4.5): kebijakan dibaca PER BADAN USAHA. Sebelumnya service memanggil
    # `get_settings()` tanpa entitas sementara routernya memakai versi ber-entitas,
    # jadi setelan khusus satu PT tidak pernah sampai ke mesin yang mengeksekusinya.
    settings = await cs.get_settings(entity_id)
    engine = await uomr.load_engine()
    order_warnings: List[str] = []

    # PS-03 — diperiksa SEBELUM satu langkah pun dibangun: menolak di tengah
    # pembangunan rantai membuat pesannya menyebut nomor langkah yang salah.
    assert_yield_reason(steps_in, settings)

    # Bangun steps (rantai). Step 1 input_qty = material_qty; step>1 diisi dari estimasi step sebelumnya.
    steps: List[Dict[str, Any]] = []
    prev_output_qty = material_qty
    prev_output_pid = material_pid
    for i, s in enumerate(steps_in, start=1):
        # Ambil default dari resep bila step tak melengkapi field (robust untuk semua klien).
        recipe = None
        if s.get("recipe_id"):
            recipe = await db.process_recipes.find_one({"id": s["recipe_id"]}, {"_id": 0})
        rcp = recipe or {}
        input_pid = s.get("input_product_id") or rcp.get("input_product_id") or (material_pid if i == 1 else prev_output_pid)
        in_snap = await _prod_snap(input_pid)
        mk_id = s.get("makloon_id") or rcp.get("default_makloon_id") or ""
        process_type = s.get("process_type") or rcp.get("process_type") or "tenun"

        # ── FASE T — TAHAP dari master (di samping `process_type`, bukan pengganti) ──
        # Diselesaikan SEBELUM pemeriksaan "produk output wajib", karena tahap yang
        # tidak mengubah kain (mis. Screen) memang tidak punya produk hasil baru —
        # outputnya kain yang sama. Kalau urutannya dibalik, tahap sah itu ditolak.
        stage = await _resolve_stage(s, process_type, entity_id, i)
        if stage["found"] and stage["process_type"]:
            # Tahap master adalah sumbernya: `process_type` mengikuti tahap supaya
            # mesin tarif/estimasi & matriks transisi tidak pernah bertengkar dengan
            # papan. (Untuk SPK lama tahapnya justru DICARI dari process_type, jadi
            # nilainya sama dan angkanya tidak bergeser.)
            process_type = stage["process_type"]
        changes_stage = stage["changes_stage"]
        flow_res = _resolve_material_flow(stage, s, order_warnings, i)
        material_flow = flow_res["flow"]
        if stage["found"] and stage["target_use"] and not s.get("target_use"):
            s = {**s, "target_use": stage["target_use"]}
        if stage["needs_vendor"] and not mk_id:
            # Keputusan pemilik 3b — PERINGATAN, bukan penolakan. Menolak di sini
            # membuat SPK darurat (mitra belum diputuskan) tidak bisa dicatat sama
            # sekali; gate INV-DOMAIN-06 tetap memerah bila TIDAK ADA mitra terdaftar
            # untuk prosesnya, jadi kelalaian tetap terlihat.
            order_warnings.append(
                f"Langkah {i} ({stage['label'] or process_type}): tahap ini dikerjakan "
                "mitra, tetapi mitra makloon belum dipilih. Pilih mitra sebelum "
                "Issue/Catat Jasa — kalau belum ada, daftarkan di Mitra Makloon.")

        out_pid = s.get("output_product_id") or rcp.get("output_product_id") or ""
        if not out_pid and not changes_stage:
            # FASE T — tahap tanpa transformasi: kain keluar = kain masuk.
            out_pid = input_pid
        # KN_18 §5.2 — produk output WAJIB eksplisit per langkah (bisa dimatikan via kebijakan).
        if not out_pid and settings.get("require_output_product", True):
            raise HTTPException(
                status_code=400,
                detail=f"Langkah {i}: produk OUTPUT wajib ditentukan (pilih resep atau produk "
                       "hasil proses) agar rantai & HPP berjenjang dapat dihitung.")
        # PS-04 — rantai dipaksa sistem: output langkah sebelumnya = input langkah ini.
        if i > 1 and prev_output_pid and input_pid != prev_output_pid:
            prev_name = (await _prod_snap(prev_output_pid))["name"] or prev_output_pid
            raise HTTPException(
                status_code=400,
                detail=f"Rantai proses terputus pada langkah {i}: bahan masuk "
                       f"'{in_snap['name'] or input_pid}' tidak sama dengan hasil langkah "
                       f"{i - 1} '{prev_name}'. Output langkah N harus menjadi input langkah N+1.")
        out_snap = await _prod_snap(out_pid)
        by_pid = s.get("byproduct_product_id") or rcp.get("byproduct_product_id") or ""
        input_qty = round(parse_decimal(s.get("input_qty")) or 0, 3) if i == 1 and parse_decimal(s.get("input_qty")) > 0 \
            else (material_qty if i == 1 else prev_output_qty)

        # ── Kontrak mitra (SSOT tarif · susut · toleransi) ──────────────────
        contract: Optional[Dict[str, Any]] = None
        if s.get("contract_id"):
            contract = await cs.get_contract(s["contract_id"])
            if not contract:
                raise HTTPException(status_code=400,
                                    detail=f"Langkah {i}: kontrak {s['contract_id']} tidak ditemukan.")
        elif mk_id:
            contract = await cs.resolve_active(partner_id=mk_id, process_type=process_type,
                                               product_id=out_pid, input_product_id=input_pid,
                                               entity_id=entity_id)
        mode_contract = settings.get("contract_mode", "warn")
        if not contract and mode_contract != "off":
            msg = (f"Langkah {i} ({process_type}): belum ada kontrak aktif untuk mitra "
                   f"{await _makloon_name(mk_id) or '-'} — tarif, susut & toleransi memakai "
                   "input manual/kebijakan global.")
            if mode_contract == "block":
                raise HTTPException(status_code=400, detail=msg + " Kebijakan saat ini "
                                    "mewajibkan kontrak aktif (Pengaturan → Kebijakan Makloon).")
            order_warnings.append(msg)

        # ── Susut (D-05) & toleransi (D-09): langkah > kontrak > kebijakan ──
        if s.get("waste_pct") not in (None, ""):
            shrink, shrink_src = parse_decimal(s.get("waste_pct")), "input langkah"
        elif contract and parse_decimal(contract.get("shrinkage_pct")) > 0:
            shrink = parse_decimal(contract.get("shrinkage_pct"))
            shrink_src = f"kontrak {contract.get('contract_number')}"
        elif rcp.get("waste_pct") not in (None, ""):
            shrink, shrink_src = parse_decimal(rcp.get("waste_pct")), "resep proses"
        else:
            shrink = parse_decimal(settings.get("default_shrinkage_pct"))
            shrink_src = "kebijakan global"
        if s.get("tolerance_pct") not in (None, ""):
            tolerance = parse_decimal(s.get("tolerance_pct"))
        elif contract and contract.get("tolerance_pct") is not None:
            tolerance = parse_decimal(contract.get("tolerance_pct"))
        else:
            tolerance = parse_decimal(settings.get("variance_tolerance_pct"))

        # ── Estimasi berbasis GSM (PS-03) + override yield sadar ────────────
        yf = parse_decimal(s.get("yield_factor"))
        if yf <= 0 and contract:
            yf = parse_decimal(contract.get("yield_factor"))
        byp_pct = parse_decimal(s.get("byproduct_pct")) or parse_decimal(rcp.get("byproduct_pct")) \
            or (parse_decimal(contract.get("byproduct_pct")) if contract else 0)
        in_prod = await db.products.find_one({"id": input_pid}, {"_id": 0}) or {}
        out_prod = await db.products.find_one({"id": out_pid}, {"_id": 0}) or in_prod
        est = await mcalc.estimate_output(
            input_product=in_prod, output_product=out_prod, input_qty=input_qty,
            shrinkage_pct=shrink, shrinkage_source=shrink_src,
            yield_factor=yf, yield_reason=s.get("yield_override_reason") or "",
            byproduct_pct=byp_pct, process_type=process_type, engine=engine,
            # FASE T — tahap tanpa transformasi memotong rumus GSM (lihat calc service).
            changes_stage=changes_stage, stage_code=stage["code"],
            stage_label=stage["label"], material_flow=material_flow,
            material_flow_source=flow_res["source"])
        exp_out = est["expected_output_qty"]
        exp_by = est["expected_byproduct_qty"]
        if not changes_stage:
            # Paksa juga nilai tersimpan, bukan hanya estimasinya: kalau `waste_pct`
            # 3% tetap tersimpan di langkah, penerimaan nanti akan menghitung selisih
            # terhadap angka yang tidak pernah berlaku dan membuka klaim palsu.
            shrink, shrink_src = 0.0, "tahap tidak mengubah kain"
            yf, byp_pct = 0.0, 0.0
            exp_by = 0.0
        if est["method"] == "unknown" and s.get("formula"):
            fc = await compute_forecast({"input_qty": input_qty, "yield_factor": yf or 1.0,
                                         "waste_pct": shrink, "byproduct_pct": byp_pct,
                                         "formula": s.get("formula") or "",
                                         "recipe_id": s.get("recipe_id") or ""})
            exp_out, exp_by = fc["expected_output"], fc["expected_byproduct"]
            est["method"], est["expected_output_qty"] = "formula", exp_out
            est["explain"].append(f"Formula resep dipakai: {fc.get('formula_used')} → {exp_out:g}")

        # ── Rencana tarif (D-07 — basis bebas/formula custom, jejak konversi) ─
        override: Dict[str, Any] = {}
        for key_in, key_out in (("tariff_basis", "tariff_basis"), ("tariff_rate", "tariff_rate"),
                                ("tariff_formula", "tariff_formula"), ("min_charge", "min_charge"),
                                ("ppi", "ppi")):
            if s.get(key_in) not in (None, "", 0):
                override[key_out] = s[key_in]
        if s.get("aux_fees"):
            override["aux_fees"] = s["aux_fees"]
        legacy_amount = parse_decimal(s.get("tariff"), 2)
        if not override and not contract and legacy_amount > 0:
            override = {"tariff_basis": "lumpsum", "tariff_rate": legacy_amount}
        qty_source = (override.get("tariff_qty_source")
                      or (contract or {}).get("tariff_qty_source") or "output")
        tariff_product = out_prod if qty_source == "output" else in_prod
        tariff_qty = exp_out if qty_source == "output" else input_qty
        try:
            plan = await cs.compute_tariff(product=tariff_product, qty_base=tariff_qty,
                                           contract=contract, override=override,
                                           roll_count=int(s.get("roll_count") or 0),
                                           colors=int(s.get("colors") or 0),
                                           repeats=int(s.get("repeats") or 0),
                                           engine=engine, label=f"step{i}")
        except (cs.ContractError, uomr.UomRuleError) as exc:
            raise HTTPException(status_code=400,
                                detail=f"Langkah {i}: {exc}") from exc

        steps.append({
            "seq": i,
            "process_type": process_type,
            # ── FASE T — TAHAP (dari master). `process_type` tetap ada di sampingnya
            # supaya mesin tarif/estimasi lama identik; `stage_code` yang dipakai papan.
            "stage_code": stage["code"],
            "stage_label": stage["label"],
            "stage_kind": stage["kind"],
            "stage_seq": stage["seq"],
            "stage_from_stage": stage["from_stage"],
            "stage_to_stage": stage["to_stage"],
            "stage_source": stage["resolved_from"],
            "changes_stage": changes_stage,
            "needs_vendor": stage["needs_vendor"],
            "material_flow": material_flow,
            "material_flow_source": flow_res["source"],
            "makloon_id": mk_id,
            "makloon_name": await _makloon_name(mk_id),
            "recipe_id": s.get("recipe_id") or "",
            "target_use": s.get("target_use") or "",
            "input_product_id": input_pid,
            "input_sku": in_snap["sku"], "input_name": in_snap["name"],
            "input_unit": in_snap["base_unit"], "input_qty": round(input_qty, 3),
            # FASE U — DUA SATUAN per langkah SPK. `qty_rolls` = jumlah roll yang
            # DIRENCANAKAN masuk (diketik; `roll_count` sudah dipakai basis tarif
            # "per roll" sejak FASE D, jadi angkanya tidak diketik dua kali).
            # `qty_rolls_out` diisi saat hasil DITERIMA (roll nyata yang lahir).
            "qty_rolls": (int(s.get("roll_count")) if s.get("roll_count") else None),
            "qty_rolls_out": None,
            "output_product_id": out_pid,
            "output_sku": out_snap["sku"], "output_name": out_snap["name"],
            "output_unit": out_snap["base_unit"],
            "byproduct_product_id": by_pid,
            "yield_factor": yf,
            "yield_override_reason": s.get("yield_override_reason") or "",
            "waste_pct": shrink, "shrinkage_pct": shrink, "shrinkage_source": shrink_src,
            "tolerance_pct": tolerance,
            "byproduct_pct": byp_pct,
            "estimate": est,
            "expected_output_qty": exp_out, "expected_byproduct_qty": exp_by,
            "actual_output_qty": 0.0, "actual_byproduct_qty": 0.0,
            # Kontrak & tarif (Fase D)
            "contract_id": (contract or {}).get("id", ""),
            "contract_number": (contract or {}).get("contract_number", ""),
            "tariff_basis": plan["basis"], "tariff_rate": plan["rate"],
            "tariff_plan": plan,
            "tariff_original": {"basis": plan["basis"], "rate": plan["rate"],
                                "qty": plan["basis_qty"], "uom": plan["basis_uom"]},
            "tariff_base_equivalent": {"qty": plan["qty_base"], "uom": plan["base_uom"],
                                       "amount": plan["amount"]},
            "tariff": plan["amount"], "aux_cost": parse_decimal(s.get("aux_cost"), 2),
            "material_value": 0.0, "service_value": 0.0, "output_value": 0.0,
            "service_bill_id": "", "issue_ref": f"{mko_id}:{i}",
            "input_lot_ids": [], "output_lot_ids": [], "output_lot_id": "",
            "claim": mclaim.blank_claim(),
            # FASE T — jasa "jasa murni" (mis. screen) yang diserap langkah ini.
            "absorbed_service_value": 0.0, "absorbed_service_steps": [],
            "status": "pending", "issued_at": "", "received_at": "", "lots": [],
        })
        if contract:
            await cs.mark_used(contract["id"])
        prev_output_qty = exp_out
        prev_output_pid = out_pid

    final_output_pid = steps[-1]["output_product_id"]
    final_snap = await _prod_snap(final_output_pid)

    # buy_process → buat PO bahan standar tertaut (best-effort; tak menggagalkan create).
    po_id, po_number = "", ""
    if mode == "buy_process":
        po_id, po_number = await _spawn_material_po(payload, mat_snap, material_qty,
                                                    entity_id, actor_name, mko_id, from_wh)

    order = {
        "id": mko_id, "mko_number": await _next_mko_number(), "entity_id": entity_id,
        "mode": mode,
        "material_product_id": material_pid, "material_sku": mat_snap["sku"],
        "material_name": mat_snap["name"], "material_qty": material_qty,
        "material_unit": payload.get("material_unit") or mat_snap["base_unit"],
        "material_source": "purchase" if mode == "buy_process" else "stock",
        "from_warehouse_id": from_wh, "target_warehouse_id": target_wh,
        "po_id": po_id, "po_number": po_number,
        "final_output_product_id": final_output_pid,
        "final_output_sku": final_snap["sku"], "final_output_name": final_snap["name"],
        "final_output_unit": final_snap["base_unit"],
        # FASE L — lini SPK: dari produk OUTPUT akhir (itu yang menentukan papan
        # pekerjaannya); bila output belum punya lini, pakai lini bahan.
        "line_code": (final_snap.get("line_code") or mat_snap.get("line_code") or ""),
        "steps": steps,
        "forecast": {"input_qty": material_qty,
                     "expected_finished_qty": steps[-1]["expected_output_qty"],
                     "expected_byproduct_qty": round(sum(st["expected_byproduct_qty"] for st in steps), 2),
                     "method": steps[0]["estimate"]["method"] if steps else "",
                     "explain": [ln for st in steps for ln in st["estimate"].get("explain", [])]},
        "costing": {"material_cost": 0.0, "service_cost": 0.0, "aux_cost": 0.0,
                    "byproduct_credit": 0.0, "hpp_output": 0.0, "hpp_per_unit": 0.0,
                    "steps": []},
        "planned_service_cost": round(sum(parse_decimal(st.get("tariff"), 2) for st in steps), 2),
        "pr_id": payload.get("pr_id") or "", "pr_number": payload.get("pr_number") or "",
        "pr_line_no": payload.get("pr_line_no") or None,
        "claim_summary": {"open": 0, "pending_approval": 0, "approved": 0, "rejected": 0,
                          "approved_amount": 0.0, "needs_action": 0},
        # FASE T — biaya jasa langkah "jasa murni" yang BELUM menempel ke kain.
        # Disimpan di kepala dokumen (bukan dihitung ulang) supaya penyerapannya bisa
        # ditelusuri: langkah kain berikutnya menyerapnya, atau — bila SPK habis —
        # `gl_service.post_subcon_service_unabsorbed` mengeluarkannya dari WIP.
        "service_absorption_pending": 0.0,
        "warnings": order_warnings,
        "status": DRAFT, "notes": payload.get("notes") or "",
        "timeline": [], "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
    }
    _tl(order, "created",
        f"Order dibuat ({mode}) · {len(steps)} langkah · "
        f"{len({st['makloon_id'] for st in steps if st.get('makloon_id')})} mitra"
        + (f" · PO {po_number}" if po_number else ""))
    # Rincian HPP berjenjang sudah tersedia sejak draft (rencana) — dipakai wizard.
    _recompute_status_and_costing(order)
    order["status"] = DRAFT
    await db.makloon_orders.insert_one(dict(order))
    # FASE G-4 — order makloon menaut ke kontrak & PO bahan (bila ada), dua arah.
    from services import doc_refs_service as _refs
    for st in order.get("steps") or []:
        if st.get("contract_id"):
            await _refs.safe_link(("makloon_order", order["id"]),
                                  ("supplier_contract", st["contract_id"]), "fulfills",
                                  note=f"kontrak langkah {st.get('seq', '')}".strip())
    if order.get("po_id"):
        await _refs.safe_link(("makloon_order", order["id"]),
                              ("purchase_order", order["po_id"]), "parent",
                              note="PO bahan makloon")
    return safe_doc(order)


async def _spawn_material_po(payload, mat_snap, qty, entity_id, actor_name, mko_id, from_wh):
    """Buat PO standar untuk bahan (buy_process). Reuse _create_po_core; best-effort."""
    try:
        from routers.purchase_orders import _create_po_core
        from schemas import PurchaseOrderCreate, POItemCreate
        po_payload = PurchaseOrderCreate(
            supplier_id=payload.get("supplier_id") or "",
            supplier_name=payload.get("supplier_name") or "",
            warehouse_id=from_wh,
            items=[POItemCreate(product_id=payload["material_product_id"], quantity=qty,
                                unit=payload.get("material_unit") or mat_snap["base_unit"] or "meter",
                                price=float(payload.get("material_price") or 0))],
            expected_delivery_date=payload.get("expected_delivery_date") or "",
            notes=f"Bahan untuk Order Makloon {mko_id}", entity_id=entity_id,
            created_by=actor_name)
        po = await _create_po_core(po_payload, {"name": actor_name}, active_entity_id=entity_id)
        await db.purchase_orders.update_one({"id": po["id"]},
                                            {"$set": {"makloon_order_id": mko_id}})
        return po.get("id", ""), po.get("po_number", "")
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("makloon_order").warning("[buy_process] gagal buat PO bahan: %s", exc)
        return "", ""


# ─── Issue ───────────────────────────────────────────────────────────────────

async def issue_step(mko_id: str, seq: int, *, from_warehouse_id: str = "",
                     doc_uom: str = "", doc_qty: Any = 0,
                     actor_name: str = "system") -> Dict[str, Any]:
    order = await _get_order(mko_id)
    if order.get("status") == CANCELLED:
        raise HTTPException(status_code=409, detail="Order sudah dibatalkan")
    step = _find_step(order, seq)
    if step.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"Step {seq} sudah di-issue/diterima")
    # FASE T — langkah "jasa murni" TIDAK memindahkan kain. Tanpa penjaga ini, kain
    # akan keluar ke bucket `subcon` pada langkah yang seharusnya tak menyentuhnya,
    # lalu tak pernah kembali (tidak ada penerimaan roll) — stok "hilang" tanpa jejak.
    if str(step.get("material_flow") or FLOW_MOVES) == FLOW_SERVICE:
        raise HTTPException(
            status_code=409,
            detail=f"Langkah {seq} ({step.get('stage_label') or step.get('process_type')}) "
                   "adalah JASA MURNI — tidak ada kain yang dikirim ke mitra. Pakai aksi "
                   "\"Catat Jasa\" untuk mencatat tagihan jasanya. Bila kain memang harus "
                   "dikirim, ubah aliran kain langkah ini menjadi \"kain dikirim & kembali\".")
    # Rantai: step>1 harus setelah step sebelumnya diterima
    if seq > 1:
        prev = _find_step(order, seq - 1)
        if prev.get("status") != "received":
            raise HTTPException(status_code=409, detail=f"Step {seq-1} harus diterima dulu")
    wh = from_warehouse_id or order.get("from_warehouse_id") or ""
    if not wh:
        raise HTTPException(status_code=400, detail="Gudang sumber bahan wajib diisi")
    input_pid = step["input_product_id"]
    input_qty = round(float(step["input_qty"] or 0), 2)

    # FASE D (PS-08/D-07) — mitra boleh memakai satuan sendiri (kg/bale/roll):
    # konversi ke satuan dasar + SIMPAN JEJAK. Bila diisi, qty dokumen menang.
    uom_trail = None
    if doc_uom and parse_decimal(doc_qty) > 0:
        prod = await db.products.find_one({"id": input_pid}, {"_id": 0}) or {}
        try:
            uom_trail = await uomr.convert_with_trail(prod, doc_qty, doc_uom,
                                                      prod.get("base_unit") or "",
                                                      context=f"makloon_issue:{mko_id}:{seq}")
        except uomr.UomRuleError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        input_qty = round(float(uom_trail["base_qty"]), 3)
        if input_qty <= 0:
            raise HTTPException(status_code=400, detail="Qty bahan hasil konversi harus > 0")
        step["input_qty"] = input_qty

    ref = {"type": "subcon", "id": step["issue_ref"], "makloon_id": step.get("makloon_id"),
           "makloon_name": step.get("makloon_name"), "mko_id": mko_id, "mko_number": order.get("mko_number"),
           "step": seq, "created_by": actor_name, "created_at": now_iso()}
    res = await sb.issue_to_subcon(input_pid, wh, order["entity_id"], input_qty, ref)
    material_value = res["value"]
    label = f"{order.get('mko_number')} step{seq}"
    await gl.post_subcon_issue(mko_id=mko_id, step_seq=seq, entity_id=order["entity_id"],
                               amount=material_value, label=label)
    step.update({"status": "issued", "material_value": material_value,
                 "issued_at": now_iso(), "from_warehouse_id": wh,
                 "issue_uom_trail": uom_trail})
    _tl(order, "issued", f"Step {seq}: issue {input_qty} {step.get('input_unit')} "
        f"{step.get('input_name')} → {step.get('makloon_name') or 'makloon'} ({rupiah(material_value)})"
        + (f" · dokumen {uom_trail['doc_qty']:g} {uom_trail['doc_uom']}" if uom_trail else ""))
    order["status"] = IN_PROCESS
    order["updated_at"] = now_iso()
    await db.makloon_orders.replace_one({"id": mko_id}, order)
    return safe_doc(order)


# ─── FASE T — Catat Jasa (langkah "jasa murni": kain TIDAK bergerak) ─────────

async def _reestimate_next(order: Dict[str, Any], seq: int, actual_out: float) -> None:
    """Set input langkah berikutnya = hasil aktual langkah `seq`, lalu estimasi ulang.

    Dipakai DUA jalur penyelesaian langkah (terima kain & catat jasa) supaya keduanya
    memakai rumus yang sama. Sebelum FASE T logika ini hanya ada di `receive_step`;
    menyalinnya akan melahirkan dua versi estimasi yang perlahan berbeda.
    """
    nxt = next((s for s in order["steps"] if int(s["seq"]) == seq + 1), None)
    if not nxt:
        return
    nxt["input_qty"] = actual_out
    nxt_in = await db.products.find_one({"id": nxt.get("input_product_id")}, {"_id": 0}) or {}
    nxt_out = await db.products.find_one({"id": nxt.get("output_product_id")}, {"_id": 0}) or nxt_in
    est_next = await mcalc.estimate_output(
        input_product=nxt_in, output_product=nxt_out, input_qty=actual_out,
        shrinkage_pct=nxt.get("shrinkage_pct", nxt.get("waste_pct") or 0),
        shrinkage_source=nxt.get("shrinkage_source") or "kontrak/kebijakan",
        yield_factor=nxt.get("yield_factor") or 0,
        yield_reason=nxt.get("yield_override_reason") or "",
        byproduct_pct=nxt.get("byproduct_pct") or 0,
        process_type=nxt.get("process_type") or "",
        changes_stage=nxt.get("changes_stage", True) is not False,
        stage_code=nxt.get("stage_code") or "", stage_label=nxt.get("stage_label") or "",
        material_flow=nxt.get("material_flow") or FLOW_MOVES,
        material_flow_source=nxt.get("material_flow_source") or "")
    if est_next["method"] == "unknown":
        fc = await compute_forecast({"input_qty": actual_out, "yield_factor": nxt.get("yield_factor") or 1.0,
                                     "waste_pct": nxt.get("waste_pct"), "byproduct_pct": nxt.get("byproduct_pct"),
                                     "formula": nxt.get("formula") or "", "recipe_id": nxt.get("recipe_id") or ""})
        est_next["expected_output_qty"] = fc["expected_output"]
        est_next["expected_byproduct_qty"] = fc["expected_byproduct"]
    nxt["estimate"] = est_next
    nxt["expected_output_qty"] = est_next["expected_output_qty"]
    nxt["expected_byproduct_qty"] = est_next["expected_byproduct_qty"]


async def _flush_unabsorbed_service(order: Dict[str, Any], label: str) -> None:
    """SPK habis tetapi jasa "jasa murni" belum menempel ke kain → keluarkan dari WIP.

    Biaya screen SEHARUSNYA diserap langkah kain berikutnya (masuk HPP kain cetak).
    Kalau SPK-nya hanya berisi Screen — kasus yang sah, mis. membuat kasa untuk order
    bulan depan — tidak ada kain yang bisa menyerapnya. Membiarkannya di WIP 1-1350
    berarti saldo persediaan-dalam-proses membesar tanpa barang, dan
    `verify_data_integrity` akan melaporkan drift yang tak punya pemilik.
    """
    pending = round(float(order.get("service_absorption_pending") or 0), 2)
    if pending <= 0 or order.get("status") != COMPLETED:
        return
    await gl.post_subcon_service_unabsorbed(
        mko_id=order["id"], entity_id=order["entity_id"], amount=pending, label=label)
    order["service_absorption_pending"] = 0.0
    order.setdefault("costing", {})["service_unabsorbed"] = pending
    _tl(order, "service_unabsorbed",
        f"Jasa {rupiah(pending)} tidak menempel ke kain mana pun di SPK ini "
        "(tidak ada langkah kain sesudahnya) → diakui sebagai Beban Jasa Makloon "
        "Tak Terserap (5-1200), keluar dari WIP.")


async def record_service_step(mko_id: str, seq: int, data: Dict[str, Any], *,
                              actor_name: str = "system") -> Dict[str, Any]:
    """FASE T — selesaikan langkah **jasa murni** (mis. pembuatan kasa/screen).

    Tidak ada bahan yang keluar gudang dan tidak ada roll yang lahir; yang terjadi
    hanyalah **tagihan jasa** + jurnalnya. Karena itu langkah ini tidak lewat
    `issue_step`/`receive_step`: memakainya akan memaksa kain bergerak dan menuntut
    LOT roll output yang tidak pernah ada.

    Qty langkah tetap dicatat (`actual_output_qty = input_qty`) supaya rantai
    "output langkah N = input langkah N+1" tidak terputus — kainnya memang tidak
    berubah sedikit pun.
    """
    order = await _get_order(mko_id)
    if order.get("status") == CANCELLED:
        raise HTTPException(status_code=409, detail="Order sudah dibatalkan")
    step = _find_step(order, seq)
    flow = str(step.get("material_flow") or FLOW_MOVES)
    if flow != FLOW_SERVICE:
        raise HTTPException(
            status_code=409,
            detail=f"Langkah {seq} ({step.get('stage_label') or step.get('process_type')}) "
                   "memindahkan kain ke mitra — selesaikan dengan Issue lalu Terima "
                   "Hasil, bukan Catat Jasa.")
    if step.get("status") != "pending":
        raise HTTPException(status_code=409,
                            detail=f"Langkah {seq} sudah dicatat/diterima sebelumnya")
    if seq > 1:
        prev = _find_step(order, seq - 1)
        if prev.get("status") != "received":
            raise HTTPException(status_code=409,
                                detail=f"Langkah {seq - 1} harus diselesaikan dulu")

    entity_id = order["entity_id"]
    label = f"{order.get('mko_number')} step{seq}"
    input_qty = round(float(step.get("input_qty") or 0), 3)

    # ── Tarif: manual menang; kalau tidak, dihitung dari kontrak/basis langkah ──
    tariff_trace: Dict[str, Any] = {}
    manual_tariff = data.get("tariff") is not None and parse_decimal(data.get("tariff"), 2) > 0
    if manual_tariff:
        tariff = round(parse_decimal(data.get("tariff"), 2), 2)
        tariff_trace = {"source": "manual_input", "amount": tariff,
                        "basis": step.get("tariff_basis", "lumpsum"),
                        "explain": [f"Biaya jasa diisi manual: {rupiah(tariff)}"]}
    else:
        contract = await cs.get_contract(step.get("contract_id")) if step.get("contract_id") else None
        override: Dict[str, Any] = {}
        if not contract:
            override = {"tariff_basis": step.get("tariff_basis") or "lumpsum",
                        "tariff_rate": step.get("tariff_rate") or 0}
        t_prod = await db.products.find_one({"id": step.get("input_product_id")}, {"_id": 0}) or {}
        try:
            tariff_trace = await cs.compute_tariff(
                product=t_prod, qty_base=input_qty, contract=contract, override=override,
                roll_count=int(data.get("roll_count") or step.get("roll_count") or 0),
                colors=int(data.get("colors") or 0), repeats=int(data.get("repeats") or 0),
                label=f"step{seq}-jasa")
        except (cs.ContractError, uomr.UomRuleError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        tariff = round(parse_decimal(tariff_trace.get("amount"), 2), 2)
    aux = round(float(data.get("aux_cost") if data.get("aux_cost") is not None
                      else step.get("aux_cost", 0)) or 0, 2)
    ppn = round(float(data.get("ppn") or 0), 2)
    net_service = round(tariff + aux, 2)
    if net_service <= 0:
        raise HTTPException(
            status_code=400,
            detail="Biaya jasa harus lebih dari 0. Langkah jasa murni tidak mengubah "
                   "kain — kalau biayanya nol, langkah ini tidak punya alasan dicatat "
                   "(hapus langkahnya atau isi tarifnya).")

    service_bill_id = new_id("vb")
    bill_no = await _next_service_bill_no()
    await db.vendor_bills.insert_one({
        "id": service_bill_id, "bill_number": bill_no, "bill_type": "makloon_service",
        "makloon_id": step.get("makloon_id"), "makloon_order_id": mko_id, "step_seq": seq,
        "po_id": "", "supplier_id": step.get("makloon_id"),
        "supplier_name": step.get("makloon_name") or "Makloon",
        "supplier_invoice_no": data.get("supplier_invoice_no") or "",
        "net_amount": net_service, "ppn_amount": ppn,
        "grand_total": round(net_service + ppn, 2),
        "tariff": tariff, "aux_cost": aux,
        # FASE T — penanda supaya laporan bisa memisahkan jasa TANPA kain.
        "service_only": True, "stage_code": step.get("stage_code") or "",
        "status": "posted", "entity_id": entity_id,
        "bill_date": now_iso(), "posted_at": now_iso(),
        "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
    })
    await gl.post_subcon_service(bill_id=service_bill_id, mko_id=mko_id, step_seq=seq,
                                 entity_id=entity_id, net_amount=net_service, ppn=ppn,
                                 grand_total=round(net_service + ppn, 2),
                                 makloon_name=step.get("makloon_name") or "", label=label)
    from services import doc_refs_service as _refs
    await _refs.safe_link(("vendor_bill", service_bill_id), ("makloon_order", mko_id),
                          "settles", note=f"jasa langkah {seq} (tanpa kain)")

    variance = mcalc.evaluate_variance(
        expected_qty=step.get("expected_output_qty"), actual_qty=input_qty,
        tolerance_pct=step.get("tolerance_pct") or 0,
        unit=step.get("output_unit") or step.get("input_unit") or "", unit_value=0)
    step.update({
        "status": "received",
        "actual_output_qty": input_qty, "actual_byproduct_qty": 0.0,
        "tariff": tariff, "aux_cost": aux, "service_value": net_service,
        "service_bill_id": service_bill_id, "tariff_actual": tariff_trace,
        # Tidak ada kain yang bergerak → tidak ada nilai bahan & tidak ada HPP output.
        "material_value": 0.0, "output_value": 0.0, "output_unit_cost": 0.0,
        "byproduct_value": 0.0, "lots": [],
        "received_at": now_iso(), "service_recorded_at": now_iso(),
        "supplier_invoice_no": data.get("supplier_invoice_no") or "",
        "service_note": (data.get("note") or "").strip(),
        "variance": variance, "claim": mclaim.blank_claim(),
    })
    order["service_absorption_pending"] = round(
        float(order.get("service_absorption_pending") or 0) + net_service, 2)
    _tl(order, "service_recorded",
        f"Langkah {seq} ({step.get('stage_label') or step.get('process_type')}): jasa "
        f"{rupiah(net_service)} dicatat ke {step.get('makloon_name') or 'mitra'} "
        f"({bill_no}) — kain TIDAK bergerak, qty tetap {input_qty:g} "
        f"{step.get('input_unit') or ''}.")

    await _reestimate_next(order, seq, input_qty)
    _recompute_status_and_costing(order)
    order["claim_summary"] = mclaim.summarize(order)
    await _flush_unabsorbed_service(order, label)
    order["updated_at"] = now_iso()
    await db.makloon_orders.replace_one({"id": mko_id}, order)
    return safe_doc(order)


# ─── Receive ─────────────────────────────────────────────────────────────────

async def receive_step(mko_id: str, seq: int, data: Dict[str, Any], *,
                       actor_name: str = "system") -> Dict[str, Any]:
    order = await _get_order(mko_id)
    step = _find_step(order, seq)
    if step.get("status") != "issued":
        raise HTTPException(status_code=409, detail=f"Step {seq} belum di-issue / sudah diterima")
    # FASE T — langkah jasa murni tidak pernah berstatus `issued`, tetapi pesan di atas
    # ("belum di-issue") akan menyesatkan. Beri kalimat yang menuntun ke aksi benar.
    if str(step.get("material_flow") or FLOW_MOVES) == FLOW_SERVICE:
        raise HTTPException(
            status_code=409,
            detail=f"Langkah {seq} ({step.get('stage_label') or step.get('process_type')}) "
                   "adalah JASA MURNI — tidak ada kain yang diterima. Selesaikan dengan "
                   "aksi \"Catat Jasa\".")
    out_pid = step.get("output_product_id")
    if not out_pid:
        raise HTTPException(status_code=400, detail="Produk output step belum ditentukan")

    actual_out = round(float(data.get("actual_output_qty") or 0), 2)
    actual_by = round(float(data.get("actual_byproduct_qty") or 0), 2)
    out_prod = await db.products.find_one({"id": out_pid}, {"_id": 0}) or {}

    # FASE D (PS-08/D-04/D-07) — mitra melaporkan dalam satuannya sendiri (mis. kg untuk
    # kain rajut, bale/roll untuk gulungan): konversi ke satuan dasar + simpan jejak.
    receive_trail = None
    if data.get("output_uom") and parse_decimal(data.get("output_doc_qty")) > 0:
        try:
            receive_trail = await uomr.convert_with_trail(
                out_prod, data["output_doc_qty"], data["output_uom"],
                out_prod.get("base_unit") or "", context=f"makloon_receive:{mko_id}:{seq}")
        except uomr.UomRuleError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        actual_out = round(float(receive_trail["base_qty"]), 2)

    if actual_out <= 0:
        raise HTTPException(status_code=400, detail="Qty output aktual harus > 0")
    rolls_in = data.get("rolls") or []
    # LOT manual WAJIB (keputusan user §13.3). Bila rolls kosong → tolak.
    if not rolls_in:
        raise HTTPException(status_code=400, detail="Minimal 1 roll output dengan LOT manual wajib diisi")
    sum_rolls = round(sum(float(r.get("length") or 0) for r in rolls_in), 2)
    if abs(sum_rolls - actual_out) > 0.5:
        raise HTTPException(status_code=400,
                            detail=f"Total panjang roll ({sum_rolls}) ≠ qty output ({actual_out})")
    for r in rolls_in:
        if not (r.get("lot") or "").strip():
            raise HTTPException(status_code=400, detail="Setiap roll output wajib punya nomor LOT (manual)")

    entity_id = order["entity_id"]
    out_wh = data.get("output_warehouse_id") or step.get("from_warehouse_id") or order.get("target_warehouse_id") or order.get("from_warehouse_id")
    label = f"{order.get('mko_number')} step{seq}"

    # 1) Konsumsi roll subcon (retire input) → nilai material terkonsumsi
    consumed = await sb.consume_subcon_by_ref(step["issue_ref"])
    material_value = consumed["consumed_value"] or step.get("material_value", 0.0)

    # 2) Tagihan jasa makloon — FASE D (D-07): tarif DIHITUNG dari kontrak/basis memakai
    #    qty AKTUAL bila user tidak menimpa manual; jejak perhitungan disimpan.
    tariff_trace: Dict[str, Any] = {}
    manual_tariff = data.get("tariff") is not None and parse_decimal(data.get("tariff"), 2) > 0
    if manual_tariff:
        tariff = round(parse_decimal(data.get("tariff"), 2), 2)
        tariff_trace = {"source": "manual_input", "amount": tariff,
                        "basis": step.get("tariff_basis", "lumpsum"),
                        "explain": [f"Ongkos jasa diisi manual saat penerimaan: {rupiah(tariff)}"]}
    else:
        contract = await cs.get_contract(step.get("contract_id")) if step.get("contract_id") else None
        override: Dict[str, Any] = {}
        if not contract:
            override = {"tariff_basis": step.get("tariff_basis") or "lumpsum",
                        "tariff_rate": step.get("tariff_rate") or 0}
        qty_source = (contract or {}).get("tariff_qty_source", "output")
        if qty_source == "input":
            t_prod = await db.products.find_one({"id": step.get("input_product_id")}, {"_id": 0}) or {}
            t_qty = consumed.get("consumed_qty") or step.get("input_qty") or 0
        else:
            t_prod, t_qty = out_prod, actual_out
        try:
            tariff_trace = await cs.compute_tariff(
                product=t_prod, qty_base=t_qty, contract=contract, override=override,
                roll_count=len(rolls_in), colors=int(data.get("colors") or 0),
                repeats=int(data.get("repeats") or 0), label=f"step{seq}-aktual")
        except (cs.ContractError, uomr.UomRuleError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        tariff = round(parse_decimal(tariff_trace.get("amount"), 2), 2)
    aux = round(float(data.get("aux_cost") if data.get("aux_cost") is not None else step.get("aux_cost", 0)) or 0, 2)
    ppn = round(float(data.get("ppn") or 0), 2)
    net_service = round(tariff + aux, 2)
    service_bill_id = ""
    if net_service > 0:
        service_bill_id = new_id("vb")
        bill_no = await _next_service_bill_no()
        await db.vendor_bills.insert_one({
            "id": service_bill_id, "bill_number": bill_no, "bill_type": "makloon_service",
            "makloon_id": step.get("makloon_id"), "makloon_order_id": mko_id, "step_seq": seq,
            "po_id": "", "supplier_id": step.get("makloon_id"),
            "supplier_name": step.get("makloon_name") or "Makloon",
            "supplier_invoice_no": data.get("supplier_invoice_no") or "",
            "net_amount": net_service, "ppn_amount": ppn, "grand_total": round(net_service + ppn, 2),
            "tariff": tariff, "aux_cost": aux,
            "status": "posted", "entity_id": entity_id,
            "bill_date": now_iso(), "posted_at": now_iso(),
            "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
        })
        await gl.post_subcon_service(bill_id=service_bill_id, mko_id=mko_id, step_seq=seq,
                                     entity_id=entity_id, net_amount=net_service, ppn=ppn,
                                     grand_total=round(net_service + ppn, 2),
                                     makloon_name=step.get("makloon_name") or "", label=label)
        # FASE G-4 — tagihan jasa makloon menaut ke order makloonnya (dua arah).
        from services import doc_refs_service as _refs
        await _refs.safe_link(("vendor_bill", service_bill_id), ("makloon_order", mko_id),
                              "settles", note=f"jasa langkah {seq}")

    # 3) WIP total di-clear ke Persediaan (output + barang sisa). Rekonsiliasi tetap utuh:
    #    output_value + sisa_value == wip_total (semua ke 1-1300).
    # FASE T — WIP yang di-clear TERMASUK jasa langkah "jasa murni" sebelumnya
    # (mis. pembuatan kasa) yang belum menempel ke kain. Itulah tempat biaya screen
    # seharusnya mendarat: pada HPP kain cetak yang memakai kasa itu. Kalau tidak
    # diserap di sini, WIP 1-1350 tak pernah nol dan HPP kain cetak terlalu murah.
    absorbed = round(float(order.get("service_absorption_pending") or 0), 2)
    absorbed_from = [int(s.get("seq")) for s in order.get("steps", [])
                     if str(s.get("material_flow") or "") == FLOW_SERVICE
                     and s.get("status") == "received"
                     and not s.get("absorbed_by_seq")] if absorbed > 0 else []
    wip_total = round(material_value + net_service + absorbed, 2)
    consumed_qty = consumed.get("consumed_qty") or step.get("input_qty") or 0
    input_unit_cost = round(material_value / consumed_qty, 4) if consumed_qty else 0.0

    # Barang sisa = SISA BAHAN INPUT (benang/grey) → produk master tersendiri, satuan input,
    #    dinilai pada HPP bahan (WAC). Bila resep tak punya byproduct_product_id → fallback ke
    #    produk output & dinilai 0 (perilaku lama, tetap rekonsiliasi).
    by_pid = step.get("byproduct_product_id") or ""
    sisa_value = 0.0
    if actual_by > 0 and by_pid:
        sisa_value = round(min(actual_by * input_unit_cost, wip_total * 0.95), 2)
    by_unit_cost = round(sisa_value / actual_by, 4) if (actual_by > 0 and sisa_value > 0) else 0.0

    output_value = round(wip_total - sisa_value, 2)
    out_uc = round(output_value / actual_out, 4) if actual_out > 0 else 0.0

    created_lots: List[Dict[str, Any]] = []
    # FASE C (D-10) — genealogi makloon: lot bahan (input) menjadi INDUK lot output,
    # sehingga silsilah benang → grey → PFD/PFP → finished terbaca di layar Silsilah.
    _input_lot_ids = consumed.get("lot_ids") or []
    _mko_ref = {"type": "makloon_order", "id": mko_id,
                "number": f"{order.get('mko_number')} step{seq}"}
    for r in rolls_in:
        roll = await create_inbound_roll(
            out_pid, out_wh, entity_id, round(float(r["length"]), 2),
            lot=str(r["lot"]).strip(), unit=step.get("output_unit") or "meter",
            grade=r.get("grade") or "A", acquired_via="subcon_receipt", ref_id=mko_id,
            unit_cost=out_uc, created_by=actor_name,
            lot_source="makloon", lot_source_ref=_mko_ref,
            parent_lot_ids=_input_lot_ids,
            dye_lot=(r.get("dye_lot") or "").strip())
        created_lots.append({"roll_id": roll["id"], "lot": roll["lot"],
                             "lot_id": roll.get("lot_id", ""),
                             "length": roll["length_remaining"], "unit": roll["unit"]})

    # Barang sisa → roll available (is_remnant). Satuan roll = base_unit produk sisa (kg/yard).
    byproduct_lot = ""
    if actual_by > 0:
        target_by_pid = by_pid or out_pid
        byproduct_lot = (data.get("byproduct_lot") or f"SISA-{order.get('mko_number')}-{seq}").strip()
        await create_inbound_roll(
            target_by_pid, out_wh, entity_id, actual_by,
            lot=byproduct_lot, unit=step.get("input_unit") or step.get("output_unit") or "meter",
            acquired_via="subcon_receipt_byproduct", ref_id=mko_id,
            unit_cost=by_unit_cost, is_remnant=True, created_by=actor_name,
            lot_source="makloon", lot_source_ref=_mko_ref,
            parent_lot_ids=_input_lot_ids)

    # 4) GL terima: Dr Persediaan (output+sisa = wip_total) / Cr WIP (clear penuh)
    await gl.post_subcon_receipt(mko_id=mko_id, step_seq=seq, entity_id=entity_id,
                                 amount=wip_total, label=label)

    step.update({
        "status": "received", "actual_output_qty": actual_out, "actual_byproduct_qty": actual_by,
        # FASE U — DUA SATUAN pada hasil langkah: jumlah roll yang BENAR-BENAR lahir
        # (dihitung dari roll yang dibuat, bukan diketik) di samping ukurannya.
        "qty_rolls_out": (len(created_lots) if created_lots else None),
        "tariff": tariff, "aux_cost": aux, "service_value": net_service, "service_bill_id": service_bill_id,
        "tariff_actual": tariff_trace,
        "receive_uom_trail": receive_trail,
        "output_value": output_value, "output_unit_cost": out_uc,
        "byproduct_value": sisa_value, "byproduct_lot": byproduct_lot,
        "byproduct_product_id": by_pid, "received_at": now_iso(),
        "lots": created_lots, "output_warehouse_id": out_wh,
        "input_lot_ids": _input_lot_ids,
        "output_lot_ids": sorted({l["lot_id"] for l in created_lots if l.get("lot_id")}),
        "output_lot_id": (created_lots[0].get("lot_id") if created_lots else ""),
        "supplier_invoice_no": data.get("supplier_invoice_no") or "",
        # FASE T — jejak penyerapan jasa "jasa murni" ke HPP kain ini.
        "absorbed_service_value": absorbed,
        "absorbed_service_steps": absorbed_from,
    })
    if absorbed > 0:
        for s2 in order.get("steps", []):
            if int(s2.get("seq") or 0) in absorbed_from:
                s2["absorbed_by_seq"] = seq
        order["service_absorption_pending"] = 0.0
        _tl(order, "service_absorbed",
            f"Jasa {rupiah(absorbed)} dari langkah {', '.join(str(x) for x in absorbed_from)} "
            f"(jasa murni — tanpa kain) diserap ke HPP hasil langkah {seq}.")

    # FASE D (PS-11 · D-05/D-09) — selisih estimasi vs aktual + klaim otomatis.
    settings = await cs.get_settings()
    variance = mcalc.evaluate_variance(
        expected_qty=step.get("expected_output_qty"), actual_qty=actual_out,
        tolerance_pct=step.get("tolerance_pct", settings.get("variance_tolerance_pct")),
        unit=step.get("output_unit") or "", unit_value=out_uc)
    step["variance"] = variance
    step["claim"] = mclaim.build_claim_from_variance(
        variance, auto_open=bool(settings.get("auto_claim", True)))

    _tl(order, "received", f"Step {seq}: terima {actual_out} {step.get('output_unit')} "
        f"{step.get('output_name')} (HPP {rupiah(output_value)})" +
        (f" + sisa {actual_by} {step.get('input_unit') or ''} ({rupiah(sisa_value)})" if actual_by > 0 else ""))
    if variance.get("message"):
        _tl(order, "variance", f"Step {seq}: {variance['message']}")

    # Rantai: set input step berikutnya = output aktual step ini (estimasi ulang berbasis GSM)
    await _reestimate_next(order, seq, actual_out)

    _recompute_status_and_costing(order)
    order["claim_summary"] = mclaim.summarize(order)
    # FASE T — jaring pengaman: bila SPK selesai tetapi masih ada jasa "jasa murni"
    # yang belum terserap (mis. langkah screen ADA di belakang langkah kain terakhir),
    # keluarkan dari WIP supaya 1-1350 kembali nol.
    await _flush_unabsorbed_service(order, label)
    order["updated_at"] = now_iso()
    await db.makloon_orders.replace_one({"id": mko_id}, order)
    if (step.get("claim") or {}).get("status") == "open":
        await mclaim.notify_claim_opened(order, step)
    return safe_doc(order)


async def _next_service_bill_no() -> str:
    last = await db.vendor_bills.find_one(
        {"bill_type": "makloon_service"}, {"_id": 0, "bill_number": 1}, sort=[("bill_number", -1)])
    n = await db.vendor_bills.count_documents({"bill_type": "makloon_service"})
    if last and isinstance(last.get("bill_number"), str) and last["bill_number"].startswith("VBM-"):
        try:
            n = int(last["bill_number"].split("-")[1])
        except (ValueError, IndexError):
            pass
    return f"VBM-{n + 1:05d}"


def _recompute_status_and_costing(order: Dict[str, Any]) -> None:
    steps = order.get("steps", [])
    received = [s for s in steps if s.get("status") == "received"]
    if len(received) == len(steps) and steps:
        order["status"] = COMPLETED
    elif received:
        order["status"] = PARTIAL
    elif any(s.get("status") == "issued" for s in steps):
        order["status"] = IN_PROCESS
    # FASE T — bahan pokok tidak selalu masuk di langkah PERTAMA. SPK printing bisa
    # dimulai dengan langkah "jasa murni" (pembuatan kasa) yang `material_value`-nya
    # nol; memakai `steps[0]` di situ melaporkan biaya bahan Rp 0 padahal kainnya
    # dikirim di langkah kedua. Diambil nilai bahan pertama yang BUKAN nol — untuk
    # SPK lama hasilnya persis sama dengan `steps[0]` (jadi angkanya tidak bergeser).
    material_cost = 0.0
    for s in sorted(steps, key=lambda x: int(x.get("seq") or 0)):
        val = float(s.get("material_value", 0) or 0)
        if val:
            material_cost = val
            break
    service_cost = round(sum(float(s.get("tariff", 0) or 0) for s in steps), 2)
    aux_cost = round(sum(float(s.get("aux_cost", 0) or 0) for s in steps), 2)
    byproduct_credit = round(sum(float(s.get("byproduct_value", 0) or 0) for s in steps), 2)
    hpp_output = 0.0
    final_qty = 0.0
    if received:
        # FASE T — langkah "jasa murni" tidak melahirkan kain, jadi ia tidak boleh
        # menjadi "hasil akhir" SPK (HPP-nya 0 dan qty-nya bukan barang baru).
        fabric_received = [s for s in received
                           if str(s.get("material_flow") or FLOW_MOVES) != FLOW_SERVICE]
        last = (fabric_received or received)[-1]
        hpp_output = round(float(last.get("output_value", 0) or 0), 2)
        final_qty = round(float(last.get("actual_output_qty", 0) or 0), 2)
    prev_costing = order.get("costing") or {}
    order["costing"] = {
        "material_cost": round(material_cost, 2), "service_cost": service_cost, "aux_cost": aux_cost,
        "byproduct_credit": byproduct_credit, "hpp_output": hpp_output,
        "hpp_per_unit": round(hpp_output / final_qty, 2) if final_qty else 0.0,
        # FASE T — jasa tanpa kain: yang masih menggantung & yang akhirnya dibebankan.
        "service_absorption_pending": round(float(order.get("service_absorption_pending") or 0), 2),
        "service_unabsorbed": round(float(prev_costing.get("service_unabsorbed") or 0), 2),
        # FASE D (PS-04) — HPP BERJENJANG: rincian biaya & HPP/unit tiap langkah.
        "steps": [{
            "seq": s.get("seq"),
            "process_type": s.get("process_type"),
            # FASE T — papan biaya menyebut TAHAP-nya, bukan cuma jenis prosesnya.
            "stage_code": s.get("stage_code", ""),
            "stage_label": s.get("stage_label", ""),
            "changes_stage": s.get("changes_stage", True) is not False,
            "material_flow": s.get("material_flow", "") or FLOW_MOVES,
            "absorbed_service_value": round(float(s.get("absorbed_service_value") or 0), 2),
            "makloon_name": s.get("makloon_name", ""),
            "status": s.get("status"),
            "input_qty": s.get("input_qty"), "input_unit": s.get("input_unit"),
            "expected_output_qty": s.get("expected_output_qty"),
            "actual_output_qty": s.get("actual_output_qty"),
            "output_unit": s.get("output_unit"),
            "material_value": round(float(s.get("material_value") or 0), 2),
            "service_value": round(float(s.get("service_value") or s.get("tariff") or 0), 2),
            "aux_cost": round(float(s.get("aux_cost") or 0), 2),
            "byproduct_value": round(float(s.get("byproduct_value") or 0), 2),
            "output_value": round(float(s.get("output_value") or 0), 2),
            "hpp_per_unit": round(float(s.get("output_unit_cost") or 0), 2),
            "tariff_basis": s.get("tariff_basis", ""),
            "contract_number": s.get("contract_number", ""),
            "variance_pct": (s.get("variance") or {}).get("variance_pct"),
            "claim_status": (s.get("claim") or {}).get("status", "none"),
        } for s in steps],
    }


# ─── Cancel ──────────────────────────────────────────────────────────────────

async def cancel_order(mko_id: str, *, reason: str = "", actor_name: str = "system") -> Dict[str, Any]:
    order = await _get_order(mko_id)
    if order.get("status") in (COMPLETED, CANCELLED):
        raise HTTPException(status_code=409, detail="Order sudah selesai/dibatalkan")
    if any(s.get("status") == "received" for s in order.get("steps", [])):
        raise HTTPException(status_code=409,
                            detail="Ada step yang sudah diterima — order tidak bisa dibatalkan")
    # Balikkan step yang sudah di-issue (belum diterima): subcon → available + reversal GL
    for s in order.get("steps", []):
        if s.get("status") == "issued":
            await sb.move_rolls_by_ref(s["issue_ref"], "available", movement_type="subcon_issue_cancel")
            await gl.reverse_subcon_issue(mko_id=mko_id, step_seq=int(s["seq"]),
                                          entity_id=order["entity_id"],
                                          amount=float(s.get("material_value", 0) or 0),
                                          label=f"{order.get('mko_number')} step{s['seq']}")
            s["status"] = "cancelled"
    order["status"] = CANCELLED
    _tl(order, "cancelled", reason or "Dibatalkan")
    order["updated_at"] = now_iso()
    await db.makloon_orders.replace_one({"id": mko_id}, order)
    return safe_doc(order)


# ─── Read ────────────────────────────────────────────────────────────────────

async def list_makloon_orders(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = await db.makloon_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    for r in rows:
        r["step_count"] = len(r.get("steps", []))
        active = 0.0
        for s in r.get("steps", []):
            if s.get("status") == "issued":
                active += await sb.subcon_qty_by_ref(s["issue_ref"])
        r["subcon_active_qty"] = round(active, 2)
        # FASE T — papan daftar menyebut TAHAP-nya (bukan hanya jenis proses), dan
        # menandai SPK yang memuat langkah tanpa transformasi kain (mis. Screen).
        r["stage_codes"] = [s.get("stage_code") or s.get("process_type") or ""
                            for s in r.get("steps", [])]
        r["stage_labels"] = [s.get("stage_label") or s.get("process_type") or ""
                             for s in r.get("steps", [])]
        r["has_service_only_step"] = any(
            str(s.get("material_flow") or "") == FLOW_SERVICE for s in r.get("steps", []))
        r["has_no_transform_step"] = any(
            s.get("changes_stage") is False for s in r.get("steps", []))
    return [safe_doc(r) for r in rows]


async def makloon_order_detail(mko_id: str) -> Optional[Dict[str, Any]]:
    o = await db.makloon_orders.find_one({"id": mko_id}, {"_id": 0})
    if not o:
        return None
    # Enrich: subcon qty aktif per step (untuk UI)
    for s in o.get("steps", []):
        s["subcon_qty"] = await sb.subcon_qty_by_ref(s["issue_ref"]) if s.get("status") == "issued" else 0.0
        # FASE T — aksi yang SAH untuk langkah ini. Dihitung server supaya layar tidak
        # menebak: langkah jasa murni tidak punya tombol Issue/Terima sama sekali.
        flow = str(s.get("material_flow") or FLOW_MOVES)
        s["material_flow"] = flow
        if s.get("status") == "pending":
            s["next_action"] = "record_service" if flow == FLOW_SERVICE else "issue"
        elif s.get("status") == "issued":
            s["next_action"] = "receive"
        else:
            s["next_action"] = ""
    o["service_absorption_pending"] = round(float(o.get("service_absorption_pending") or 0), 2)
    # Tagihan jasa terkait
    o["service_bills"] = await db.vendor_bills.find(
        {"makloon_order_id": mko_id}, {"_id": 0}).sort("created_at", 1).to_list(100)
    o["claim_summary"] = mclaim.summarize(o)
    return safe_doc(o)


# ─── FASE D — Estimasi & simulasi untuk wizard (tidak menyimpan apa pun) ──────

async def estimate_step_preview(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Pratinjau 1 langkah wizard: kontrak aktif → susut → estimasi GSM → tarif.

    Dipakai layar **Wizard Order Makloon** agar user melihat rumus & angka antara
    SEBELUM menyimpan (PS-03 \"bisa diaudit\").
    """
    in_pid = payload.get("input_product_id") or ""
    out_pid = payload.get("output_product_id") or ""
    in_prod = await db.products.find_one({"id": in_pid}, {"_id": 0}) or {}
    if not in_prod:
        raise HTTPException(status_code=400, detail="Produk bahan (input) tidak ditemukan.")
    out_prod = await db.products.find_one({"id": out_pid}, {"_id": 0}) or in_prod
    # Kebijakan dibaca PER BADAN USAHA, sama seperti `create_makloon_order`. Pratinjau
    # yang memakai kebijakan GLOBAL sementara penyimpanan memakai kebijakan PT akan
    # menampilkan angka yang berbeda dari yang tersimpan — persis kelas galat yang
    # paling sulit dipercaya pengguna ("di layar 109, tersimpan 112").
    settings = await cs.get_settings(payload.get("entity_id") or "")
    engine = await uomr.load_engine()
    process_type = payload.get("process_type") or ""
    mk_id = payload.get("makloon_id") or ""
    # ── FASE T — tahap dari master menentukan APAKAH kain berubah & bergerak ──
    ent = payload.get("entity_id") or ""
    warn: List[str] = []
    stage = await _resolve_stage(payload, process_type, ent, 1)
    if stage["found"] and stage["process_type"]:
        process_type = stage["process_type"]
    changes_stage = stage["changes_stage"]
    flow_res = _resolve_material_flow(stage, payload, warn, 1)
    contract = None
    if payload.get("contract_id"):
        contract = await cs.get_contract(payload["contract_id"])
    elif mk_id:
        contract = await cs.resolve_active(partner_id=mk_id, process_type=process_type,
                                           product_id=out_pid, input_product_id=in_pid,
                                           entity_id=payload.get("entity_id") or "")
    if payload.get("waste_pct") not in (None, ""):
        shrink, shrink_src = parse_decimal(payload.get("waste_pct")), "input langkah"
    elif contract and parse_decimal(contract.get("shrinkage_pct")) > 0:
        shrink = parse_decimal(contract.get("shrinkage_pct"))
        shrink_src = f"kontrak {contract.get('contract_number')}"
    else:
        shrink, shrink_src = parse_decimal(settings.get("default_shrinkage_pct")), "kebijakan global"
    tolerance = (parse_decimal(payload.get("tolerance_pct"))
                 if payload.get("tolerance_pct") not in (None, "")
                 else (parse_decimal(contract.get("tolerance_pct"))
                       if contract and contract.get("tolerance_pct") is not None
                       else parse_decimal(settings.get("variance_tolerance_pct"))))

    input_qty = parse_decimal(payload.get("input_qty"))
    input_trail = None
    doc_uom = payload.get("input_uom") or ""
    if doc_uom and uomr.normalize_unit(doc_uom) != uomr.normalize_unit(in_prod.get("base_unit") or ""):
        try:
            input_trail = await uomr.convert_with_trail(in_prod, input_qty, doc_uom,
                                                        in_prod.get("base_unit") or "",
                                                        engine=engine, context="wizard")
            input_qty = float(input_trail["base_qty"])
        except uomr.UomRuleError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    est = await mcalc.estimate_output(
        input_product=in_prod, output_product=out_prod, input_qty=input_qty,
        shrinkage_pct=shrink, shrinkage_source=shrink_src,
        yield_factor=payload.get("yield_factor") or 0,
        yield_reason=payload.get("yield_override_reason") or "",
        byproduct_pct=payload.get("byproduct_pct") or 0,
        process_type=process_type, engine=engine,
        changes_stage=changes_stage, stage_code=stage["code"], stage_label=stage["label"],
        material_flow=flow_res["flow"], material_flow_source=flow_res["source"])
    if not changes_stage:
        shrink, shrink_src = 0.0, "tahap tidak mengubah kain"

    override = {k: payload.get(k) for k in ("tariff_basis", "tariff_rate", "tariff_formula",
                                            "min_charge", "ppi") if payload.get(k) not in (None, "", 0)}
    if payload.get("aux_fees"):
        override["aux_fees"] = payload["aux_fees"]
    qty_source = (contract or {}).get("tariff_qty_source", "output")
    t_prod = out_prod if qty_source == "output" else in_prod
    t_qty = est["expected_output_qty"] if qty_source == "output" else input_qty
    tariff = None
    tariff_error = ""
    try:
        tariff = await cs.compute_tariff(product=t_prod, qty_base=t_qty, contract=contract,
                                         override=override,
                                         roll_count=int(payload.get("roll_count") or 0),
                                         colors=int(payload.get("colors") or 0),
                                         repeats=int(payload.get("repeats") or 0),
                                         engine=engine, label="wizard")
    except (cs.ContractError, uomr.UomRuleError) as exc:
        tariff_error = str(exc)

    return {
        "contract": contract, "contract_found": bool(contract),
        "shrinkage_pct": shrink, "shrinkage_source": shrink_src,
        "tolerance_pct": tolerance,
        "input_qty_base": input_qty, "input_unit": in_prod.get("base_unit", ""),
        "input_trail": input_trail,
        "estimate": est, "tariff": tariff, "tariff_error": tariff_error,
        # ── FASE T — apa yang tahap ini lakukan (dipakai layar untuk menjelaskan
        # kenapa kolom susut/yield dimatikan & aksi mana yang akan tersedia).
        "stage": {
            "code": stage["code"], "label": stage["label"], "kind": stage["kind"],
            "found": stage["found"], "resolved_from": stage["resolved_from"],
            "process_type": process_type,
            "changes_stage": changes_stage,
            "from_stage": stage["from_stage"], "to_stage": stage["to_stage"],
            "needs_vendor": stage["needs_vendor"],
            "material_flow": flow_res["flow"], "material_flow_source": flow_res["source"],
            "material_flow_allowed": stage["material_flow"],
            "next_action": ("record_service" if flow_res["flow"] == FLOW_SERVICE else "issue"),
            "warnings": warn + ([
                f"Tahap {stage['label'] or stage['code']} dikerjakan mitra, tetapi mitra "
                "belum dipilih — pilih dulu sebelum Issue/Catat Jasa."]
                if stage["needs_vendor"] and not mk_id else []),
        },
        "policy": {"contract_mode": settings.get("contract_mode"),
                   "auto_claim": settings.get("auto_claim")},
    }
