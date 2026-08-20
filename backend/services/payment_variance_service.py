"""FASE G-3 — **SELISIH PEMBAYARAN: LEBIH & KURANG BAYAR** (`payment_variance_decisions`).

MASALAH NYATA PEMILIK
---------------------
Uang yang masuk hampir **tidak pernah** sama persis dengan tagihan: pelanggan memotong
biaya transfer, membulatkan ke bawah, membayar sebagian karena arus kas, atau justru
mengirim lebih. Sistem lama hanya punya dua sikap ekstrem: menolak (karena "melebihi
outstanding") atau diam-diam menaruh kelebihan ke deposit. Akibatnya:

  * sisa kurang bayar receh menggantung bertahun-tahun di laporan piutang;
  * kelebihan bayar hilang dari pembicaraan (pelanggan merasa sudah bayar, kami merasa belum);
  * keputusan "ya sudah, anggap lunas" terjadi di WhatsApp, tidak di sistem.

TEROBOSAN DESAIN — "KEBIJAKAN SELISIH PEMBAYARAN"
------------------------------------------------
Sistem **tidak menuntut nominal persis**, tetapi setiap selisih **wajib punya label
keputusan** dengan pemutus yang jelas:

    delta = uang masuk − Σ tagihan yang JATUH TEMPO pada pesanan tujuan

| Kondisi                   | Perlakuan                                                        |
|---------------------------|------------------------------------------------------------------|
| `abs(delta) <= toleransi` | **otomatis** (`rounding`) → sisa receh dihapus / kelebihan receh  |
|                           | jadi deposit. Tanpa persetujuan, TAPI tetap jadi keputusan        |
|                           | berlabel yang bisa diaudit.                                       |
| `delta < 0` (kurang)      | (a) sisa tetap **piutang** *(bawaan)* · (b) **ubah jadwal** —     |
|                           | sisa jadi tempo baru · (c) **hapus sisa** + alasan + wewenang     |
| `delta > 0` (lebih)       | (a) **deposit pelanggan** *(bawaan)* · (b) **alokasi ke pesanan   |
|                           | terbuka lain** · (c) **kembalikan** (kas keluar)                  |

KEJUJURAN AKUNTANSI (kenapa keputusan = dokumen sendiri)
--------------------------------------------------------
Kwitansi tetap dibukukan seperti biasa (Dr Kas · Cr Piutang sebesar yang teralokasi ·
Cr 2-1400 Uang Muka Pelanggan sebesar kelebihannya). Keputusan selisih **tidak mengubah
jurnal kwitansi** (ledger append-only, aturan repo #7) melainkan menerbitkan jurnalnya
sendiri:

  * hapus sisa kurang bayar  → Dr 6-9100 Beban Selisih Pembayaran / Cr 1-1200 Piutang
  * kelebihan dipakai untuk pesanan lain → Dr 2-1400 Uang Muka / Cr 1-1200 Piutang
  * kelebihan dikembalikan   → Dr 2-1400 Uang Muka / Cr Kas (lewat `cash_transactions`)

Karena itu keputusan bisa diambil **saat kwitansi dibuat** maupun **belakangan** dari
antrean "Selisih Bayar" tanpa pernah menghasilkan pembukuan ganda.

JALUR AP (bayar ke supplier)
----------------------------
Pola yang sama dipakai saat KITA membayar tagihan supplier: kurang bayar → sisa tetap
hutang / ditutup (potongan supplier, Dr 2-1100 · Cr 4-9000), lebih bayar → **uang muka
supplier** (Dr 1-1400 · Cr Kas) yang bisa dipotongkan pada kontrabon berikutnya (G-7).

INVARIAN
--------
* **INV-VAR-01** Setiap selisih di luar toleransi punya keputusan **berlabel** (kode alasan
  + pemutus). Penghapusan sisa & pengembalian dana wajib peran penyetuju & di bawah batas.
* **INV-VAR-02** Uang tidak hilang: pada setiap kwitansi `dana = teralokasi + belum
  teralokasi`, dan setiap rupiah yang dipindahkan oleh keputusan (alokasi ulang / refund)
  punya jurnal + tidak melebihi kelebihan bayar kwitansinya.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core_utils import DEFAULT_ENTITY_ID, new_id, next_doc_number, now_iso, safe_doc, rupiah
from db import db
from services import gl_service
from services import payment_plan_service as plans
from services.config_resolver import resolve

COLL = "payment_variance_decisions"
EPS = 0.01

# Arah selisih
DIR_NONE, DIR_ROUNDING, DIR_UNDER, DIR_OVER = "none", "rounding", "under", "over"

AR_UNDER_KINDS = ("outstanding", "reschedule", "writeoff")
AR_OVER_KINDS = ("deposit", "allocate", "refund")
AP_KINDS = ("ap_outstanding", "ap_writeoff", "ap_advance")
ROUNDING_KINDS = ("rounding_writeoff", "rounding_deposit",
                  "ap_rounding_writeoff", "ap_rounding_advance")
ALL_KINDS = AR_UNDER_KINDS + AR_OVER_KINDS + AP_KINDS + ROUNDING_KINDS

KIND_LABEL = {
    "outstanding": "Sisa tetap jadi piutang",
    "reschedule": "Ubah jadwal — sisa jadi tempo baru",
    "writeoff": "Hapus sisa kurang bayar",
    "deposit": "Simpan sebagai deposit pelanggan",
    "allocate": "Alokasikan ke pesanan terbuka lain",
    "refund": "Kembalikan ke pelanggan (kas keluar)",
    "rounding_writeoff": "Pembulatan — sisa receh dihapus otomatis",
    "rounding_deposit": "Pembulatan — kelebihan receh jadi deposit",
    "ap_outstanding": "Sisa tetap jadi hutang supplier",
    "ap_writeoff": "Tutup sisa hutang (potongan supplier)",
    "ap_advance": "Kelebihan jadi uang muka supplier",
    "ap_rounding_writeoff": "Pembulatan — sisa hutang receh ditutup",
    "ap_rounding_advance": "Pembulatan — kelebihan receh jadi uang muka",
}
REASON_DOC_TYPE = "payment_variance"     # `amendment_reasons.applies_to` (taksonomi G-1)
SENSITIVE_KINDS = ("writeoff", "refund", "ap_writeoff")


class VarianceError(ValueError):
    """Kesalahan selisih pembayaran dengan pesan siap tampil (Bahasa Indonesia)."""


# ── Kebijakan (registry FASE G-0 — tidak ada angka hardcode) ───────────────
async def variance_policy(entity_id: str = "", customer_id: str = "") -> Dict[str, Any]:
    ctx = {"entity_id": entity_id or "", "customer_id": customer_id or ""}

    async def val(key: str) -> Any:
        return (await resolve(key, ctx))["value"]

    return {
        "tolerance": float(await val("payment.variance_tolerance_rupiah") or 0),
        "underpay_default": str(await val("payment.variance_underpay_default") or "outstanding"),
        "overpay_default": str(await val("payment.variance_overpay_default") or "deposit"),
        "writeoff_requires_approval": bool(await val("payment.variance_writeoff_requires_approval")),
        "writeoff_approver_role": str(await val("payment.variance_writeoff_approver_role") or "manager"),
        "writeoff_max_amount": float(await val("payment.variance_writeoff_max_amount") or 0),
        "reschedule_days": int(await val("payment.variance_reschedule_days") or 14),
        "refund_method": str(await val("payment.variance_refund_method") or "transfer"),
        "ap_tolerance": float(await val("payment.variance_ap_tolerance_rupiah") or 0),
    }


# ── Label alasan (taksonomi FASE G-1, bisa ditambah admin) ─────────────────
async def reasons() -> List[Dict[str, Any]]:
    from services.amendment_service import ensure_reasons
    await ensure_reasons()
    rows = await db.amendment_reasons.find(
        {"applies_to": REASON_DOC_TYPE, "status": {"$ne": "inactive"}}, {"_id": 0}
    ).sort("label", 1).to_list(100)
    return [safe_doc(r) for r in rows]


async def _reason_or_fail(reason_code: str) -> Dict[str, Any]:
    code = (reason_code or "").strip()
    if not code:
        raise VarianceError(
            "Label alasan wajib dipilih — setiap selisih pembayaran harus punya sebab "
            "yang bisa dibaca orang lain.")
    from services.amendment_service import ensure_reasons
    await ensure_reasons()
    row = await db.amendment_reasons.find_one({"code": code}, {"_id": 0})
    if not row or row.get("status") not in (None, "active"):
        raise VarianceError(f"Label alasan '{code}' tidak terdaftar / sudah tidak aktif.")
    applies = row.get("applies_to") or []
    if applies and REASON_DOC_TYPE not in applies:
        raise VarianceError(
            f"Label alasan '{row.get('label')}' tidak berlaku untuk selisih pembayaran.")
    return safe_doc(row)


def _rp(v: Any) -> str:
    """Alias tipis ke `core_utils.rupiah` — satu sumber format uang untuk seluruh backend."""
    return rupiah(v)


def classify(delta: float, tolerance: float) -> str:
    d = round(float(delta or 0), 2)
    tol = round(float(tolerance or 0), 2)
    if abs(d) <= EPS:
        return DIR_NONE
    if abs(d) <= tol + EPS:
        return DIR_ROUNDING
    return DIR_UNDER if d < 0 else DIR_OVER


# ── Sisi AR: apa yang "seharusnya dibayar sekarang" ────────────────────────
async def _order_due_now(order: Dict[str, Any], outstanding: float,
                         as_of: str) -> Dict[str, Any]:
    """Berapa yang jatuh tempo untuk satu pesanan + dari mana angkanya.

    Ada rencana pembayaran (FASE G-2) → Σ baris yang sudah jatuh tempo.
    Tidak ada rencana → pakai jatuh tempo term pesanan; kalau belum jatuh tempo,
    harapannya adalah seluruh sisa tagihan pesanan itu (yang lazim ditagih).
    """
    plan = await plans.get_active("sales_order", order.get("id", ""))
    if plan:
        due_now = plans.due_now_amount(plan, as_of)
        rows = plans.due_lines(plan, as_of)
        return {
            "plan_id": plan["id"], "plan_number": plan.get("number", ""),
            "due_now": min(round(due_now, 2), outstanding),
            "basis": "plan" if due_now > EPS else "plan_not_due",
            "due_lines": [{"seq": l.get("seq"), "label": l.get("label"),
                           "due_date": l.get("due_date"),
                           "amount": round(float(l.get("amount") or 0), 2),
                           "paid_amount": round(float(l.get("paid_amount") or 0), 2),
                           "remaining": round(float(l.get("amount") or 0)
                                              - float(l.get("paid_amount") or 0), 2)}
                          for l in rows],
            "next_due_date": (plans.next_due(plan) or {}).get("due_date", ""),
        }
    from services.customer_service import _parse_dt as parse_dt, _term_days as term_days
    cust = await db.customers.find_one({"id": order.get("customer_id")},
                                       {"_id": 0, "payment_profile": 1}) or {}
    created = parse_dt(order.get("created_at")) or datetime.now(timezone.utc)
    due = created + timedelta(days=term_days(cust, order))
    day = str(as_of or now_iso())[:10]
    is_due = due.date().isoformat() <= day
    return {"plan_id": "", "plan_number": "",
            "due_now": outstanding if is_due else 0.0,
            "basis": "term" if is_due else "term_not_due",
            "due_lines": [], "next_due_date": due.date().isoformat()}


async def _targets(customer_id: str, allocations: Optional[List[Dict[str, Any]]],
                   as_of: str) -> Dict[str, Any]:
    """Pesanan tujuan pembayaran + pesanan terbuka lainnya (untuk pilihan alokasi)."""
    from services import ar_receipt_service as ars
    opens = await ars.list_open_orders(customer_id)
    idx = {o["order_id"]: o for o in opens}
    if allocations:
        wanted = [str(a.get("order_id") or "") for a in allocations if a.get("order_id")]
    else:
        wanted = [o["order_id"] for o in opens]

    rows: List[Dict[str, Any]] = []
    for oid in wanted:
        base = idx.get(oid)
        if not base:
            continue
        order = await db.sales_orders.find_one(
            {"id": oid}, {"_id": 0, "id": 1, "number": 1, "customer_id": 1,
                          "created_at": 1, "payment_term_code": 1, "payment_term_days": 1,
                          "entity_id": 1}) or {}
        info = await _order_due_now(order, base["outstanding"], as_of)
        expected = round(info["due_now"] if info["due_now"] > EPS else base["outstanding"], 2)
        rows.append({
            "order_id": oid, "number": base.get("number", oid),
            "entity_id": order.get("entity_id", ""),
            "outstanding": base["outstanding"], "expected": expected, **info,
        })
    others = [{"order_id": o["order_id"], "number": o.get("number", o["order_id"]),
               "outstanding": o["outstanding"]}
              for o in opens if o["order_id"] not in {r["order_id"] for r in rows}]
    return {"targets": rows, "others": others}


def _options(direction: str, delta: float, policy: Dict[str, Any],
             ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pilihan keputusan dalam bahasa manusia + dampak masing-masing (untuk dialog)."""
    gap = round(abs(delta), 2)
    out: List[Dict[str, Any]] = []
    if direction == DIR_UNDER:
        has_plan = bool(ctx.get("has_plan"))
        new_due = ctx.get("suggested_due_date", "")
        out = [
            {"value": "outstanding", "label": KIND_LABEL["outstanding"],
             "help": f"Sisa {_rp(gap)} tetap ditagih seperti biasa — jadwal tidak berubah.",
             "impact": f"Piutang tetap {_rp(gap)}; pesanan belum lunas.",
             "available": True, "requires_reason": True, "requires_role": ""},
            {"value": "reschedule", "label": KIND_LABEL["reschedule"],
             "help": (f"Sisa {_rp(gap)} dijadwalkan ulang ke {new_due} sehingga tidak "
                      "tercatat sebagai tunggakan telat."),
             "impact": f"Baris jadwal dipecah / digeser; Σ rencana tetap {_rp(ctx.get('plan_total', 0))}.",
             "available": has_plan,
             "unavailable_reason": "" if has_plan else
                 "Pesanan ini belum punya rencana pembayaran — susun jadwal dulu.",
             "requires_reason": True, "requires_role": ""},
            {"value": "writeoff", "label": KIND_LABEL["writeoff"],
             "help": (f"Sisa {_rp(gap)} dihapus dari piutang dan dibebankan ke "
                      "Beban Selisih Pembayaran — pesanan langsung lunas."),
             "impact": f"Piutang −{_rp(gap)} · beban naik {_rp(gap)} (berjurnal, tak bisa dihapus).",
             "available": True, "requires_reason": True,
             "requires_role": policy["writeoff_approver_role"] if policy["writeoff_requires_approval"] else "",
             "max_amount": policy["writeoff_max_amount"]},
        ]
    elif direction == DIR_OVER:
        others_total = round(float(ctx.get("others_total", 0)), 2)
        out = [
            {"value": "deposit", "label": KIND_LABEL["deposit"],
             "help": f"Kelebihan {_rp(gap)} disimpan sebagai saldo pelanggan untuk tagihan berikutnya.",
             "impact": f"Deposit pelanggan +{_rp(gap)} (kewajiban kami ke pelanggan).",
             "available": True, "requires_reason": True, "requires_role": ""},
            {"value": "allocate", "label": KIND_LABEL["allocate"],
             "help": (f"Kelebihan {_rp(gap)} dipakai melunasi pesanan terbuka lain "
                      f"(tersedia {_rp(others_total)})."),
             "impact": "Pesanan lain berkurang piutangnya; deposit tidak menumpuk.",
             "available": others_total > EPS,
             "unavailable_reason": "" if others_total > EPS else
                 "Tidak ada pesanan terbuka lain untuk dialokasikan.",
             "requires_reason": True, "requires_role": ""},
            {"value": "refund", "label": KIND_LABEL["refund"],
             "help": f"Kelebihan {_rp(gap)} dikembalikan ke pelanggan lewat kas keluar.",
             "impact": f"Kas berkurang {_rp(gap)} · deposit tidak bertambah.",
             "available": True, "requires_reason": True,
             "requires_role": policy["writeoff_approver_role"] if policy["writeoff_requires_approval"] else ""},
        ]
    for o in out:
        o["default"] = o["value"] == (policy["underpay_default"] if direction == DIR_UNDER
                                     else policy["overpay_default"]) and o["available"]
    if out and not any(o.get("default") for o in out):
        for o in out:
            if o["available"]:
                o["default"] = True
                break
    return out


async def pre_assess(customer_id: str, funds: float,
                     allocations: Optional[List[Dict[str, Any]]] = None,
                     as_of: str = "", entity_id: str = "") -> Dict[str, Any]:
    """Hitung selisih pembayaran SEBELUM uang dialokasikan (dipakai dialog & kwitansi).

    Dua batas yang dipakai — dan inilah yang membuat angkanya jujur:
      * `expected`  = Σ tagihan yang **sudah jatuh tempo** pada pesanan tujuan;
      * `capacity`  = Σ **seluruh sisa tagihan** pesanan tujuan.

    Uang di antara kedua batas itu (mis. pelanggan membayar cicilan berikutnya lebih awal)
    BUKAN selisih: uangnya masih bisa dialokasikan ke pesanan yang sama, jadi tidak ada
    yang perlu diputuskan. Selisih hanya lahir bila uang **kurang dari yang jatuh tempo**
    atau **lebih dari yang bisa dialokasikan**.

    Dipanggil dari `ar_receipt_service.create_receipt` sebelum alokasi mengubah
    outstanding, sehingga `expected` tidak bisa dikarang dari sisi klien.
    """
    day = str(as_of or now_iso())[:10]
    policy = await variance_policy(entity_id, customer_id)
    tg = await _targets(customer_id, allocations, day)
    targets, others = tg["targets"], tg["others"]
    expected = round(sum(t["expected"] for t in targets), 2)
    open_capacity = round(sum(t["outstanding"] for t in targets), 2)
    # Bila petugas MENYEBUT alokasinya, yang benar-benar mendarat di tagihan adalah
    # nominal itu (dibatasi sisa tagihan) — sisanya pasti menjadi kelebihan bayar.
    if allocations:
        planned = round(sum(min(round(float(a.get("amount") or 0), 2),
                                next((t["outstanding"] for t in targets
                                      if t["order_id"] == a.get("order_id")), 0.0))
                            for a in allocations), 2)
        capacity = min(planned, open_capacity)
    else:
        capacity = open_capacity
    others_total = round(sum(o["outstanding"] for o in others), 2)
    money = round(float(funds or 0), 2)

    if money > capacity + EPS:
        delta = round(money - capacity, 2)          # LEBIH bayar (tak bisa dialokasikan)
        boundary, boundary_label = capacity, "sisa tagihan pesanan tujuan"
    elif money < expected - EPS:
        delta = round(money - expected, 2)          # KURANG bayar (jatuh tempo tak tertutup)
        boundary, boundary_label = expected, "tagihan yang jatuh tempo"
    else:
        delta, boundary, boundary_label = 0.0, expected, "tagihan yang jatuh tempo"
    direction = classify(delta, policy["tolerance"])
    suggested_due = (datetime.now(timezone.utc)
                     + timedelta(days=int(policy["reschedule_days"]))).date().isoformat()
    ctx = {"has_plan": any(t.get("plan_id") for t in targets),
           "others_total": others_total, "plan_total": capacity,
           "suggested_due_date": suggested_due}
    cust = await db.customers.find_one({"id": customer_id},
                                       {"_id": 0, "name": 1, "deposit_balance": 1}) or {}
    explain = [
        f"Uang masuk {_rp(money)}",
        (f"{boundary_label.capitalize()} ({len(targets)} pesanan tujuan) = {_rp(boundary)}"
         if targets else "Tidak ada pesanan terbuka untuk dialokasikan"),
        (f"Selisih {_rp(abs(delta))} "
         + ("KURANG bayar" if delta < 0 else "LEBIH bayar" if delta > 0 else "nihil")),
        f"Toleransi berlaku {_rp(policy['tolerance'])} (Pusat Pengaturan → Uang Masuk & Piutang)",
    ]
    return {
        "customer_id": customer_id, "customer_name": cust.get("name", ""),
        "deposit_balance": round(float(cust.get("deposit_balance") or 0), 2),
        "as_of": day, "funds": money, "expected": expected, "delta": delta,
        "capacity": capacity, "open_capacity": open_capacity,
        "boundary": round(float(boundary), 2),
        "boundary_label": boundary_label, "direction": direction,
        "needs_decision": direction in (DIR_UNDER, DIR_OVER),
        "auto": direction == DIR_ROUNDING,
        "tolerance": policy["tolerance"], "policy": policy,
        "targets": targets, "others": others, "others_total": others_total,
        "suggested_due_date": suggested_due,
        "options": _options(direction, delta, policy, ctx),
        "explain": explain,
    }


def variance_block(assessment: Dict[str, Any]) -> Dict[str, Any]:
    """Ringkasan selisih yang DISIMPAN pada kwitansi (bahan antrean & invarian)."""
    return {
        "expected": assessment["expected"], "funds": assessment["funds"],
        "capacity": assessment.get("capacity", 0.0),
        "boundary": assessment.get("boundary", assessment["expected"]),
        "boundary_label": assessment.get("boundary_label", ""),
        "delta": assessment["delta"], "direction": assessment["direction"],
        "tolerance": assessment["tolerance"],
        "needs_decision": assessment["needs_decision"],
        "target_order_ids": [t["order_id"] for t in assessment.get("targets") or []],
        "decision_id": "", "decision_kind": "", "decision_number": "",
        "resolved": assessment["direction"] in (DIR_NONE,),
        "explain": assessment.get("explain") or [],
    }


# ── Efek keputusan (masing-masing punya jejak jurnal sendiri) ──────────────
async def _write_off_orders(order_ids: List[str], amount: float, *, decision_id: str,
                            decision_number: str, receipt_number: str,
                            reason_label: str, actor: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Tutup sisa piutang pesanan (berurutan) lewat entri pembayaran ber-jenis `writeoff`.

    Memakai guard $expr yang sama dengan alokasi kwitansi supaya tidak mungkin
    menutup lebih dari sisa tagihan (anti balapan / dobel-tutup).
    """
    from pymongo import ReturnDocument
    from services.customer_service import (_order_grand_total as gt_of,
                                           _order_paid as paid_of)
    left = round(float(amount or 0), 2)
    done: List[Dict[str, Any]] = []
    for oid in order_ids:
        if left <= EPS:
            break
        order = await db.sales_orders.find_one({"id": oid}, {"_id": 0})
        if not order:
            continue
        gt = round(gt_of(order), 2)
        outstanding = round(gt - paid_of(order), 2)
        take = min(left, outstanding)
        if take <= EPS:
            continue
        entry = {
            "id": new_id("pay"), "amount": round(take, 2), "method": "writeoff",
            "kind": "writeoff", "receipt_number": receipt_number,
            "variance_decision_id": decision_id,
            "variance_decision_number": decision_number,
            "note": f"Selisih kurang bayar dihapus · {reason_label}",
            "date": now_iso(), "created_at": now_iso(),
            "created_by": actor.get("name", "system"),
        }
        updated = await db.sales_orders.find_one_and_update(
            {"id": oid, "$expr": {"$lte": [{"$add": [{"$sum": "$payments.amount"},
                                                     round(take, 2)]}, gt + EPS]}},
            {"$push": {"payments": entry}, "$inc": {"paid_total": round(take, 2)},
             "$set": {"updated_at": now_iso()}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if not updated:
            raise VarianceError(
                f"Gagal menutup sisa pesanan {order.get('number')} — sisa tagihan berubah "
                "(kemungkinan pembayaran paralel). Muat ulang lalu coba lagi.")
        new_paid = round(paid_of(updated), 2)
        status = "paid" if new_paid >= gt - EPS else ("partial" if new_paid > EPS else "unpaid")
        await db.sales_orders.update_one({"id": oid}, {"$set": {"payment_status": status}})
        try:
            await plans.recompute_for_doc("sales_order", oid)
        except Exception:  # noqa: BLE001 — turunan, tak boleh menggagalkan keputusan
            pass
        done.append({"order_id": oid, "order_number": order.get("number", oid),
                     "amount": round(take, 2), "payment_status": status})
        left = round(left - take, 2)
    if left > EPS:
        raise VarianceError(
            f"Sisa {_rp(left)} tidak bisa dihapus — tidak ada tagihan terbuka sebesar itu "
            "pada pesanan tujuan.")
    return done


async def _reschedule(target: Dict[str, Any], amount: float, due_date: str,
                      reason_label: str, note: str,
                      actor: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Sisa kurang bayar dijadikan tempo baru pada rencana pembayaran pesanan."""
    plan_id = target.get("plan_id") or ""
    if not plan_id:
        raise VarianceError(
            f"Pesanan {target.get('number')} belum punya rencana pembayaran — "
            "susun jadwal dulu sebelum memilih 'Ubah jadwal'.")
    plan = await plans.get(plan_id)
    if not plan:
        raise VarianceError("Rencana pembayaran tujuan tidak ditemukan.")
    left = round(float(amount or 0), 2)
    moved: List[Dict[str, Any]] = []
    guard = 0
    while left > EPS and guard < 24:
        guard += 1
        plan = await plans.get(plan_id)
        rows = plans.due_lines(plan) or [l for l in (plan.get("lines") or [])
                                         if l.get("status") != "paid"]
        if not rows:
            raise VarianceError("Tidak ada baris jadwal terbuka untuk dijadwalkan ulang.")
        line = rows[0]
        remaining = round(float(line.get("amount") or 0) - float(line.get("paid_amount") or 0), 2)
        take = min(left, remaining)
        if take <= EPS:
            break
        plan = await plans.reschedule_line(
            plan_id, int(line.get("seq") or 0), take, due_date,
            reason_label=reason_label, note=note, actor=actor)
        moved.append({"plan_id": plan_id, "plan_number": plan.get("number", ""),
                      "line_seq": int(line.get("seq") or 0),
                      "line_label": line.get("label", ""), "amount": take,
                      "new_due_date": due_date})
        left = round(left - take, 2)
    if left > EPS:
        raise VarianceError(
            f"Sisa {_rp(left)} melebihi baris jadwal yang bisa digeser pada rencana ini.")
    return moved


async def _allocate_from_deposit(customer_id: str, allocations: List[Dict[str, Any]], *,
                                 decision_id: str, decision_number: str, entity_id: str,
                                 receipt_number: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    """Kelebihan bayar dipakai melunasi pesanan terbuka lain (Dr 2-1400 / Cr 1-1200)."""
    from services import ar_receipt_service as ars
    wanted = round(sum(round(float(a.get("amount") or 0), 2) for a in allocations or []), 2)
    if wanted <= EPS:
        raise VarianceError("Pilih minimal satu pesanan dan nominal alokasinya.")
    avail = await ars.get_deposit_balance(customer_id)
    if wanted > avail + EPS:
        raise VarianceError(f"Deposit pelanggan tidak cukup (tersedia {_rp(avail)}).")
    rows: List[Dict[str, Any]] = []
    total = 0.0
    for al in allocations or []:
        amt = round(float(al.get("amount") or 0), 2)
        oid = str(al.get("order_id") or "")
        if not oid or amt <= EPS:
            continue
        applied = await ars.apply_from_deposit(
            oid, amt, decision_id, decision_number, receipt_number, actor)
        rows.append(applied)
        total = round(total + amt, 2)
    await ars.adjust_deposit(customer_id, -total)
    je = await gl_service.post_variance_reallocation(
        decision_id=decision_id, entity_id=entity_id, amount=total,
        label=f"{decision_number} · kelebihan bayar dialihkan", created_by=actor.get("name", ""))
    return {"rows": rows, "total": total, "je_id": (je or {}).get("id", ""),
            "je_number": (je or {}).get("number", "")}


async def _refund(customer: Dict[str, Any], amount: float, method: str, *,
                  decision_id: str, decision_number: str, entity_id: str,
                  receipt_number: str, reason_label: str,
                  actor: Dict[str, Any]) -> Dict[str, Any]:
    """Kelebihan bayar dikembalikan: kas keluar + Dr 2-1400 Uang Muka Pelanggan."""
    from services import ar_receipt_service as ars
    amt = round(float(amount or 0), 2)
    if amt <= EPS:
        raise VarianceError("Nominal pengembalian harus lebih dari nol.")
    avail = await ars.get_deposit_balance(customer["id"])
    if amt > avail + EPS:
        raise VarianceError(
            f"Saldo kelebihan bayar pelanggan tidak cukup untuk dikembalikan "
            f"(tersedia {_rp(avail)}).")
    tunai = (method or "").lower() in ("cash", "tunai", "kontan")
    cash_type = "kas_kecil" if tunai else "kas_besar"
    # FASE E-7 (E7.4) — pengembalian dana pelanggan adalah uang badan usaha penjualnya.
    from services.cash_entity_service import resolve_owner as _cash_owner
    cash_entity = _cash_owner(entity_id, DEFAULT_ENTITY_ID,
                              what="Kas pengembalian dana pelanggan")
    cdoc = {
        "id": new_id("cash"),
        "number": await next_doc_number("cash_transactions", "number", "CASH-",
                                        entity_id=cash_entity),
        "cash_type": cash_type, "direction": "out", "amount": amt,
        "category": "pengembalian dana pelanggan",
        "description": (f"Pengembalian kelebihan bayar {decision_number} · "
                        f"{customer.get('name', '')} ({reason_label})"),
        "entity_id": cash_entity, "owner_entity_id": entity_id or DEFAULT_ENTITY_ID,
        "ref_type": "ar_refund", "ref_id": decision_id,
        "txn_date": now_iso(), "status": "posted",
        "created_by": actor.get("name", "system"),
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.cash_transactions.insert_one(cdoc)
    je = await gl_service.post_cash_transaction(cdoc)
    await ars.adjust_deposit(customer["id"], -amt)
    return {"amount": amt, "cash_txn_id": cdoc["id"], "cash_txn_number": cdoc["number"],
            "method": method or "transfer", "je_id": (je or {}).get("id", ""),
            "je_number": (je or {}).get("number", "")}


# ── Wewenang ──────────────────────────────────────────────────────────────
def _assert_authority(kind: str, amount: float, policy: Dict[str, Any],
                      actor: Dict[str, Any]) -> str:
    """Peran & batas nominal untuk keputusan sensitif (hapus sisa / refund)."""
    if kind not in SENSITIVE_KINDS or not policy["writeoff_requires_approval"]:
        return ""
    role = (actor.get("role") or "").lower()
    need = (policy["writeoff_approver_role"] or "manager").lower()
    if role not in (need, "admin"):
        raise VarianceError(
            f"Keputusan '{KIND_LABEL.get(kind, kind)}' wajib diputus {need} atau admin — "
            "ajukan ke penyetuju.")
    cap = float(policy["writeoff_max_amount"] or 0)
    if cap > 0 and round(float(amount), 2) > cap + EPS and role != "admin":
        raise VarianceError(
            f"Nominal {_rp(amount)} melebihi batas keputusan {need} ({_rp(cap)}) — "
            "harus admin/direksi.")
    return need


# ── Dokumen keputusan ─────────────────────────────────────────────────────
async def _insert_decision(doc: Dict[str, Any]) -> Dict[str, Any]:
    await db[COLL].insert_one(dict(doc))
    # FASE G-4 — keputusan selisih adalah DOKUMEN: menaut sumbernya dua arah.
    try:
        from services import doc_refs_service as _refs
        if doc.get("receipt_id"):
            await _refs.safe_link(("payment_variance", doc["id"]),
                                  ("ar_receipt", doc["receipt_id"]), "parent",
                                  note="keputusan selisih pembayaran kwitansi ini")
        for t in doc.get("orders") or []:
            if t.get("order_id"):
                await _refs.safe_link(("payment_variance", doc["id"]),
                                      ("sales_order", t["order_id"]), "settles",
                                      note="selisih pembayaran pesanan ini")
    except Exception:  # noqa: BLE001 — jejak relasi best-effort
        pass
    return safe_doc(doc)


async def _notify(doc: Dict[str, Any]) -> None:
    if doc.get("kind") not in SENSITIVE_KINDS:
        return
    try:
        from services import notification_service as ns
        await ns.create_notification(
            notif_type="payment_variance", severity="warning",
            title=f"{KIND_LABEL.get(doc['kind'], doc['kind'])} {doc['number']}",
            body=(f"{doc.get('customer_name', '')} · {_rp(doc.get('amount'))} "
                  f"— alasan: {doc.get('reason_label', '')} (pemutus {doc.get('decided_by', '')})"),
            link="payment-plans", entity_id=doc.get("entity_id"),
            recipient_role="manager", ref=doc["id"], dedupe_scope="day")
    except Exception:  # noqa: BLE001
        return


async def get(decision_id: str) -> Optional[Dict[str, Any]]:
    row = await db[COLL].find_one({"id": decision_id}, {"_id": 0})
    return safe_doc(row) if row else None


# ── Keputusan sisi AR ─────────────────────────────────────────────────────
async def decide_receipt(receipt_id: str, payload: Dict[str, Any],
                         actor: Dict[str, Any]) -> Dict[str, Any]:
    """Terapkan keputusan selisih pada satu kwitansi (saat dibuat ATAU belakangan)."""
    receipt = await db.ar_receipts.find_one({"id": receipt_id}, {"_id": 0})
    if not receipt:
        raise VarianceError("Kwitansi tidak ditemukan.")
    receipt = safe_doc(receipt)
    if receipt.get("status") == "void":
        raise VarianceError("Kwitansi sudah dibatalkan — tidak ada selisih untuk diputus.")
    v = receipt.get("variance") or {}
    if not v:
        raise VarianceError(
            "Kwitansi ini tidak punya catatan selisih pembayaran (dibuat sebelum FASE G-3).")
    if v.get("decision_id"):
        raise VarianceError(
            f"Selisih kwitansi {receipt.get('number')} sudah diputus "
            f"({KIND_LABEL.get(v.get('decision_kind'), v.get('decision_kind'))}).")
    direction = v.get("direction") or DIR_NONE
    if direction in (DIR_NONE,):
        raise VarianceError("Kwitansi ini tidak punya selisih yang perlu diputus.")

    kind = str(payload.get("kind") or "").strip()
    allowed = (AR_UNDER_KINDS if direction in (DIR_UNDER,) else AR_OVER_KINDS)
    if direction == DIR_ROUNDING:
        allowed = ("rounding_writeoff", "rounding_deposit")
    if kind not in allowed:
        raise VarianceError(
            f"Pilihan '{kind}' tidak tersedia untuk selisih {direction}. "
            f"Pilihan yang sah: {', '.join(allowed)}.")

    customer = await db.customers.find_one({"id": receipt.get("customer_id")}, {"_id": 0}) or {}
    entity_id = receipt.get("entity_id") or customer.get("entity_id") or DEFAULT_ENTITY_ID
    policy = await variance_policy(entity_id, receipt.get("customer_id", ""))
    gap = round(abs(float(v.get("delta") or 0)), 2)
    amount = round(float(payload.get("amount") or 0), 2) or gap
    if amount > gap + EPS:
        raise VarianceError(f"Nominal keputusan {_rp(amount)} melebihi selisih {_rp(gap)}.")
    reason = await _reason_or_fail(payload.get("reason_code", ""))
    approver_role = _assert_authority(kind, amount, policy, actor)

    number = await next_doc_number(COLL, "number", "SLB-", entity_id=entity_id or None)
    decision_id = new_id("pvd")
    orders_touched: List[Dict[str, Any]] = []
    effect: Dict[str, Any] = {}
    je_id = je_number = ""
    target_ids = list(v.get("target_order_ids") or [])
    tg = await _targets(receipt.get("customer_id", ""),
                        [{"order_id": oid} for oid in target_ids] or None,
                        str(receipt.get("receipt_date") or now_iso())[:10])
    targets = tg["targets"]

    if kind in ("outstanding",):
        effect = {"note": "Sisa tetap ditagih — tidak ada perubahan pembukuan."}
    elif kind == "reschedule":
        due = str(payload.get("due_date") or "")[:10] or (
            datetime.now(timezone.utc)
            + timedelta(days=int(policy["reschedule_days"]))).date().isoformat()
        chosen = next((t for t in targets if t.get("plan_id")), None)
        if payload.get("order_id"):
            chosen = next((t for t in targets if t["order_id"] == payload["order_id"]), chosen)
        if not chosen:
            raise VarianceError(
                "Tidak ada pesanan tujuan yang punya rencana pembayaran — "
                "susun jadwal dulu atau pilih 'sisa tetap piutang'.")
        moved = await _reschedule(chosen, amount, due, reason["label"],
                                  payload.get("note", ""), actor)
        effect = {"rescheduled": moved, "due_date": due}
        orders_touched = [{"order_id": chosen["order_id"], "order_number": chosen["number"],
                           "amount": amount}]
    elif kind in ("writeoff", "rounding_writeoff"):
        ids = [t["order_id"] for t in targets] or target_ids
        orders_touched = await _write_off_orders(
            ids, amount, decision_id=decision_id, decision_number=number,
            receipt_number=receipt.get("number", ""), reason_label=reason["label"],
            actor=actor)
        je = await gl_service.post_variance_writeoff(
            decision_id=decision_id,
            entity_id=(orders_touched[0].get("entity_id") if orders_touched else "") or entity_id,
            amount=amount, label=f"{number} · {receipt.get('number', '')}",
            created_by=actor.get("name", "system"))
        je_id, je_number = (je or {}).get("id", ""), (je or {}).get("number", "")
        effect = {"written_off": orders_touched, "account": gl_service.ACC_SELISIH_BAYAR}
    elif kind in ("deposit", "rounding_deposit"):
        effect = {"deposit_added": amount,
                  "note": "Kelebihan bayar tetap sebagai saldo/deposit pelanggan."}
    elif kind == "allocate":
        res = await _allocate_from_deposit(
            receipt.get("customer_id", ""), payload.get("allocations") or [],
            decision_id=decision_id, decision_number=number, entity_id=entity_id,
            receipt_number=receipt.get("number", ""), actor=actor)
        if round(res["total"], 2) > gap + EPS:
            raise VarianceError(
                f"Total alokasi {_rp(res['total'])} melebihi kelebihan bayar {_rp(gap)}.")
        amount = round(res["total"], 2)
        orders_touched = res["rows"]
        je_id, je_number = res["je_id"], res["je_number"]
        effect = {"allocated": res["rows"]}
    elif kind == "refund":
        res = await _refund(
            customer or {"id": receipt.get("customer_id"), "name": receipt.get("customer_name")},
            amount, payload.get("method") or policy["refund_method"],
            decision_id=decision_id, decision_number=number, entity_id=entity_id,
            receipt_number=receipt.get("number", ""), reason_label=reason["label"], actor=actor)
        je_id, je_number = res["je_id"], res["je_number"]
        effect = {"refund": res}

    doc = {
        "id": decision_id, "number": number, "side": "ar", "entity_id": entity_id,
        "receipt_id": receipt["id"], "receipt_number": receipt.get("number", ""),
        "customer_id": receipt.get("customer_id", ""),
        "customer_name": receipt.get("customer_name", ""),
        "direction": direction, "kind": kind, "kind_label": KIND_LABEL.get(kind, kind),
        "expected": round(float(v.get("expected") or 0), 2),
        "funds": round(float(v.get("funds") or 0), 2),
        "delta": round(float(v.get("delta") or 0), 2),
        "amount": amount, "tolerance": round(float(v.get("tolerance") or 0), 2),
        "auto": bool(payload.get("auto")),
        "reason_code": reason["code"], "reason_label": reason["label"],
        "note": str(payload.get("note") or ""),
        "decided_by": actor.get("name", "system"), "decided_by_role": actor.get("role", ""),
        "decided_at": now_iso(), "approver_role_required": approver_role,
        "orders": orders_touched, "effect": effect,
        "je_id": je_id, "je_number": je_number,
        "policy_snapshot": policy, "refs": [],
        "explain": (v.get("explain") or []) + [
            f"Keputusan: {KIND_LABEL.get(kind, kind)} sebesar {_rp(amount)}",
            f"Alasan: {reason['label']}" + (f" — {payload.get('note')}" if payload.get("note") else ""),
            f"Pemutus: {actor.get('name', 'system')}"
            + (f" (wajib {approver_role})" if approver_role else ""),
        ],
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    saved = await _insert_decision(doc)
    await db.ar_receipts.update_one({"id": receipt["id"]}, {"$set": {
        "variance.decision_id": decision_id, "variance.decision_kind": kind,
        "variance.decision_number": number, "variance.resolved": True,
        "variance.needs_decision": False,
        "variance.decided_by": actor.get("name", ""), "variance.decided_at": now_iso(),
        "variance.reason_label": reason["label"], "variance.decision_amount": amount,
        "updated_at": now_iso()}})
    await _notify(saved)
    return saved


async def auto_resolve_receipt(receipt: Dict[str, Any], actor: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Selisih di dalam toleransi → diputus otomatis, TAPI tetap tercatat berlabel."""
    v = receipt.get("variance") or {}
    if v.get("direction") != DIR_ROUNDING or v.get("decision_id"):
        return None
    delta = round(float(v.get("delta") or 0), 2)
    kind = "rounding_writeoff" if delta < 0 else "rounding_deposit"
    return await decide_receipt(receipt["id"], {
        "kind": kind, "reason_code": "rounding_diff", "auto": True,
        "note": "Diselesaikan otomatis karena masih di dalam toleransi selisih pembayaran.",
    }, {**actor, "role": "admin"})


# ── Pembatalan keputusan (dipakai saat kwitansi di-void) ──────────────────
async def reverse_decision(decision_id: str, reason: str,
                           actor: Dict[str, Any]) -> Dict[str, Any]:
    """Anulir keputusan selisih: efeknya dibalik, jejaknya TETAP ada (append-only).

    Dipanggil otomatis saat kwitansinya dibatalkan (`void_receipt`) sehingga tidak
    mungkin ada piutang yang sudah "dihapus" atau dana yang sudah "dikembalikan"
    padahal uangnya ternyata tidak pernah ada.
    """
    d = await get(decision_id)
    if not d:
        raise VarianceError("Keputusan selisih pembayaran tidak ditemukan.")
    if d.get("status") == "reversed":
        return d
    if not (reason or "").strip():
        raise VarianceError("Alasan pembatalan keputusan wajib diisi.")
    from services import ar_receipt_service as ars
    kind = d.get("kind", "")
    amount = round(float(d.get("amount") or 0), 2)
    entity_id = d.get("entity_id") or DEFAULT_ENTITY_ID
    rev_je = None
    undone: Dict[str, Any] = {}

    if kind in ("writeoff", "rounding_writeoff"):
        for row in d.get("orders") or []:
            oid = row.get("order_id")
            if not oid:
                continue
            order = await db.sales_orders.find_one({"id": oid}, {"_id": 0})
            if not order:
                continue
            keep = [p for p in (order.get("payments") or [])
                    if p.get("variance_decision_id") != decision_id]
            paid = round(sum(float(p.get("amount") or 0) for p in keep), 2)
            from services.customer_service import _order_grand_total as gt_of
            gt = round(gt_of(order), 2)
            await db.sales_orders.update_one({"id": oid}, {"$set": {
                "payments": keep, "paid_total": paid,
                "payment_status": ("paid" if paid >= gt - EPS
                                   else "partial" if paid > EPS else "unpaid"),
                "updated_at": now_iso()}})
            try:
                await plans.recompute_for_doc("sales_order", oid)
            except Exception:  # noqa: BLE001
                pass
        rev_je = await gl_service.post_variance_reversal(
            decision_id=decision_id, entity_id=entity_id, amount=amount,
            debit_acc=gl_service.ACC_PIUTANG, credit_acc=gl_service.ACC_SELISIH_BAYAR,
            label=f"{d.get('number')} · {reason}", created_by=actor.get("name", "system"))
        undone = {"orders_restored": [r.get("order_number") for r in d.get("orders") or []]}
    elif kind == "allocate":
        for row in d.get("orders") or []:
            oid = row.get("order_id")
            if not oid:
                continue
            order = await db.sales_orders.find_one({"id": oid}, {"_id": 0})
            if not order:
                continue
            keep = [p for p in (order.get("payments") or [])
                    if p.get("receipt_id") != decision_id]
            paid = round(sum(float(p.get("amount") or 0) for p in keep), 2)
            from services.customer_service import _order_grand_total as gt_of
            gt = round(gt_of(order), 2)
            await db.sales_orders.update_one({"id": oid}, {"$set": {
                "payments": keep, "paid_total": paid,
                "payment_status": ("paid" if paid >= gt - EPS
                                   else "partial" if paid > EPS else "unpaid"),
                "updated_at": now_iso()}})
            try:
                await plans.recompute_for_doc("sales_order", oid)
            except Exception:  # noqa: BLE001
                pass
        await ars.adjust_deposit(d.get("customer_id", ""), amount)
        rev_je = await gl_service.post_variance_reversal(
            decision_id=decision_id, entity_id=entity_id, amount=amount,
            debit_acc=gl_service.ACC_PIUTANG,
            credit_acc=gl_service.ACC_UANG_MUKA_PELANGGAN,
            label=f"{d.get('number')} · {reason}", created_by=actor.get("name", "system"))
        undone = {"deposit_restored": amount}
    elif kind == "refund":
        ref = (d.get("effect") or {}).get("refund") or {}
        cash_id = ref.get("cash_txn_id", "")
        cash_acc = gl_service.ACC_KAS_KECIL if (ref.get("method") or "").lower() in (
            "cash", "tunai", "kontan") else gl_service.ACC_KAS_BESAR
        if cash_id:
            await db.cash_transactions.update_one(
                {"id": cash_id}, {"$set": {"status": "void", "updated_at": now_iso()}})
        await ars.adjust_deposit(d.get("customer_id", ""), amount)
        rev_je = await gl_service.post_variance_reversal(
            decision_id=decision_id, entity_id=entity_id, amount=amount,
            debit_acc=cash_acc, credit_acc=gl_service.ACC_UANG_MUKA_PELANGGAN,
            label=f"{d.get('number')} · {reason}", created_by=actor.get("name", "system"))
        undone = {"cash_voided": cash_id, "deposit_restored": amount}
    else:
        # `outstanding` / `deposit` / `reschedule` tidak memindahkan uang. Jadwal yang
        # sudah digeser TIDAK dipaksa kembali (itu kesepakatan dengan pelanggan) —
        # cukup dicatat supaya terlihat di jejak.
        undone = {"note": "Keputusan tidak memindahkan uang; tidak ada jurnal untuk dibalik."}

    await db[COLL].update_one({"id": decision_id}, {"$set": {
        "status": "reversed", "reversed_reason": reason.strip(),
        "reversed_by": actor.get("name", "system"), "reversed_at": now_iso(),
        "reversal_je_id": (rev_je or {}).get("id", ""),
        "reversal_je_number": (rev_je or {}).get("number", ""),
        "reversal_effect": undone, "updated_at": now_iso()}})
    if d.get("receipt_id"):
        await db.ar_receipts.update_one({"id": d["receipt_id"]}, {"$set": {
            "variance.decision_id": "", "variance.decision_kind": "",
            "variance.decision_number": "", "variance.resolved": False,
            "variance.reversed_decision_id": decision_id,
            "variance.needs_decision": (d.get("direction") in (DIR_UNDER, DIR_OVER)),
            "updated_at": now_iso()}})
    return await get(decision_id)


# ── Keputusan sisi AP (bayar supplier) ────────────────────────────────────
async def assess_bill(bill: Dict[str, Any], amount: float) -> Dict[str, Any]:
    """Selisih saat membayar tagihan supplier (kurang / lebih dari sisa hutang)."""
    entity_id = bill.get("entity_id") or DEFAULT_ENTITY_ID
    policy = await variance_policy(entity_id)
    grand = round(float(bill.get("grand_total") or 0), 2)
    paid = round(float(bill.get("amount_paid") or 0), 2)
    outstanding = round(grand - paid, 2)
    money = round(float(amount or 0), 2)
    delta = round(money - outstanding, 2)
    direction = classify(delta, policy["ap_tolerance"])
    options: List[Dict[str, Any]] = []
    if direction == DIR_UNDER:
        options = [
            {"value": "ap_outstanding", "label": KIND_LABEL["ap_outstanding"],
             "help": f"Sisa {_rp(abs(delta))} tetap tercatat sebagai hutang supplier.",
             "impact": "Tagihan tetap berstatus sebagian dibayar.",
             "available": True, "default": True, "requires_reason": True, "requires_role": ""},
            {"value": "ap_writeoff", "label": KIND_LABEL["ap_writeoff"],
             "help": (f"Sisa {_rp(abs(delta))} dianggap selesai (potongan/pembulatan dari "
                      "supplier) dan tagihan ditutup lunas."),
             "impact": "Hutang −" + _rp(abs(delta)) + " · Pendapatan lain-lain naik (berjurnal).",
             "available": True, "default": False, "requires_reason": True,
             "requires_role": policy["writeoff_approver_role"] if policy["writeoff_requires_approval"] else ""},
        ]
    elif direction == DIR_OVER:
        options = [
            {"value": "ap_advance", "label": KIND_LABEL["ap_advance"],
             "help": (f"Kelebihan {_rp(delta)} dicatat sebagai uang muka ke supplier dan bisa "
                      "dipotongkan pada tagihan / kontrabon berikutnya."),
             "impact": "Uang Muka (1-1400) +" + _rp(delta) + " · kas keluar lebih besar.",
             "available": True, "default": True, "requires_reason": True, "requires_role": ""},
        ]
    return {
        "side": "ap", "bill_id": bill.get("id"), "bill_number": bill.get("bill_number", ""),
        "supplier_name": bill.get("supplier_name", ""), "entity_id": entity_id,
        "grand_total": grand, "paid": paid, "outstanding": outstanding,
        "funds": money, "expected": outstanding, "delta": delta, "direction": direction,
        "needs_decision": direction in (DIR_UNDER, DIR_OVER),
        "auto": direction == DIR_ROUNDING, "tolerance": policy["ap_tolerance"],
        "policy": policy, "options": options,
        "explain": [
            f"Sisa hutang {bill.get('bill_number', '')} = {_rp(outstanding)}",
            f"Dibayar {_rp(money)}",
            f"Selisih {_rp(abs(delta))} " + ("KURANG" if delta < 0 else "LEBIH" if delta > 0 else "nihil"),
            f"Toleransi supplier {_rp(policy['ap_tolerance'])}",
        ],
    }


async def decide_bill(bill: Dict[str, Any], assessment: Dict[str, Any],
                      payload: Dict[str, Any], actor: Dict[str, Any],
                      *, advance_cash: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Catat + terapkan keputusan selisih pembayaran supplier."""
    direction = assessment["direction"]
    if direction in (DIR_NONE,):
        raise VarianceError("Tidak ada selisih yang perlu diputus pada pembayaran ini.")
    kind = str(payload.get("kind") or "").strip()
    if direction == DIR_ROUNDING:
        kind = kind or ("ap_rounding_writeoff" if assessment["delta"] < 0
                        else "ap_rounding_advance")
    if kind not in AP_KINDS + ("ap_rounding_writeoff", "ap_rounding_advance"):
        raise VarianceError(f"Pilihan '{kind}' tidak dikenal untuk selisih pembayaran supplier.")
    entity_id = assessment["entity_id"]
    policy = assessment["policy"]
    gap = round(abs(float(assessment["delta"])), 2)
    reason_code = payload.get("reason_code") or (
        "rounding_diff" if direction == DIR_ROUNDING else "")
    reason = await _reason_or_fail(reason_code)
    approver_role = _assert_authority(
        "ap_writeoff" if kind in ("ap_writeoff",) else kind, gap, policy, actor)

    number = await next_doc_number(COLL, "number", "SLB-", entity_id=entity_id or None)
    decision_id = new_id("pvd")
    je_id = je_number = ""
    effect: Dict[str, Any] = {}

    if kind in ("ap_writeoff", "ap_rounding_writeoff"):
        je = await gl_service.post_ap_variance_writeoff(
            decision_id=decision_id, entity_id=entity_id, amount=gap,
            label=f"{number} · {bill.get('bill_number', '')}",
            created_by=actor.get("name", "system"))
        je_id, je_number = (je or {}).get("id", ""), (je or {}).get("number", "")
        await db.vendor_bills.update_one({"id": bill["id"]}, {"$set": {
            "status": "paid", "ap_variance_closed": gap,
            "ap_variance_decision_id": decision_id, "updated_at": now_iso()}})
        effect = {"closed_amount": gap, "bill_status": "paid"}
    elif kind in ("ap_advance", "ap_rounding_advance"):
        effect = {"advance_amount": gap,
                  "cash_txn_number": (advance_cash or {}).get("number", ""),
                  "account": gl_service.ACC_UANG_MUKA}
        if bill.get("supplier_id"):
            await db.suppliers.update_one({"id": bill["supplier_id"]},
                                          {"$inc": {"advance_balance": gap},
                                           "$set": {"updated_at": now_iso()}})
    else:  # ap_outstanding
        effect = {"note": "Sisa tetap hutang supplier — tidak ada perubahan pembukuan."}

    doc = {
        "id": decision_id, "number": number, "side": "ap", "entity_id": entity_id,
        "bill_id": bill.get("id"), "bill_number": bill.get("bill_number", ""),
        "supplier_id": bill.get("supplier_id", ""), "supplier_name": bill.get("supplier_name", ""),
        "direction": direction, "kind": kind, "kind_label": KIND_LABEL.get(kind, kind),
        "expected": assessment["expected"], "funds": assessment["funds"],
        "delta": assessment["delta"], "amount": gap, "tolerance": assessment["tolerance"],
        "auto": direction == DIR_ROUNDING,
        "reason_code": reason["code"], "reason_label": reason["label"],
        "note": str(payload.get("note") or ""),
        "decided_by": actor.get("name", "system"), "decided_by_role": actor.get("role", ""),
        "decided_at": now_iso(), "approver_role_required": approver_role,
        "orders": [], "effect": effect, "je_id": je_id, "je_number": je_number,
        "policy_snapshot": policy, "refs": [],
        "explain": (assessment.get("explain") or []) + [
            f"Keputusan: {KIND_LABEL.get(kind, kind)} sebesar {_rp(gap)}",
            f"Alasan: {reason['label']}",
            f"Pemutus: {actor.get('name', 'system')}",
        ],
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    saved = await _insert_decision(doc)
    try:
        from services import doc_refs_service as _refs
        if bill.get("id"):
            await _refs.safe_link(("payment_variance", decision_id),
                                  ("vendor_bill", bill["id"]), "parent",
                                  note="selisih pembayaran tagihan supplier")
    except Exception:  # noqa: BLE001
        pass
    return saved


# ── Pembacaan untuk UI, antrean & invarian ────────────────────────────────
async def list_decisions(entity_id: Any = "", side: str = "", kind: str = "",
                         direction: str = "", q: str = "",
                         limit: int = 200) -> List[Dict[str, Any]]:
    flt: Dict[str, Any] = {}
    # FASE E-0 (L3) — dukung filter entitas siap-pakai `{"$in": [...]}`.
    if isinstance(entity_id, dict):
        flt["entity_id"] = entity_id
    elif entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    if side:
        flt["side"] = side
    if kind:
        flt["kind"] = kind
    if direction:
        flt["direction"] = direction
    if q:
        import re as _re
        rx = _re.compile(_re.escape(q), _re.I)
        flt["$or"] = [{"number": rx}, {"receipt_number": rx}, {"customer_name": rx},
                      {"bill_number": rx}, {"supplier_name": rx}]
    rows = await db[COLL].find(flt, {"_id": 0}).sort("created_at", -1).to_list(int(limit))
    return [safe_doc(r) for r in rows]


async def pending(entity_id: Any = "", limit: int = 200) -> List[Dict[str, Any]]:
    """Kwitansi yang selisihnya BELUM diputus — antrean kerja finance."""
    flt: Dict[str, Any] = {"status": {"$ne": "void"},
                           "variance.needs_decision": True,
                           "variance.decision_id": ""}
    if isinstance(entity_id, dict):
        flt["entity_id"] = entity_id
    elif entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    rows = await db.ar_receipts.find(flt, {"_id": 0}).sort("created_at", -1).to_list(int(limit))
    out = []
    for r in rows:
        r = safe_doc(r)
        v = r.get("variance") or {}
        out.append({
            "receipt_id": r["id"], "number": r.get("number", ""),
            "entity_id": r.get("entity_id", ""),
            "customer_id": r.get("customer_id", ""), "customer_name": r.get("customer_name", ""),
            "receipt_date": r.get("receipt_date", ""), "method": r.get("method", ""),
            "funds": round(float(r.get("total_funds") or 0), 2),
            "applied_total": round(float(r.get("applied_total") or 0), 2),
            "unapplied_amount": round(float(r.get("unapplied_amount") or 0), 2),
            "expected": round(float(v.get("expected") or 0), 2),
            "delta": round(float(v.get("delta") or 0), 2),
            "direction": v.get("direction", ""),
            "target_order_ids": v.get("target_order_ids") or [],
            "explain": v.get("explain") or [],
            "age_days": _age_days(r.get("created_at", "")),
        })
    return out


def _age_days(created_at: str) -> int:
    try:
        d = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - d).days)
    except Exception:  # noqa: BLE001
        return 0


async def stats(entity_id: Any = "") -> Dict[str, Any]:
    flt: Dict[str, Any] = {}
    if isinstance(entity_id, dict):
        flt["entity_id"] = entity_id
    elif entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    out = {"decisions": 0, "under": 0, "over": 0, "rounding": 0,
           "writeoff_amount": 0.0, "refund_amount": 0.0, "allocated_amount": 0.0,
           "deposit_amount": 0.0, "rescheduled_amount": 0.0, "auto": 0}
    async for r in db[COLL].find(flt, {"_id": 0, "direction": 1, "kind": 1,
                                       "amount": 1, "auto": 1}):
        out["decisions"] += 1
        out[r.get("direction", "rounding")] = out.get(r.get("direction", "rounding"), 0) + 1
        amt = float(r.get("amount") or 0)
        kind = r.get("kind", "")
        if r.get("auto"):
            out["auto"] += 1
        if kind in ("writeoff", "rounding_writeoff", "ap_writeoff", "ap_rounding_writeoff"):
            out["writeoff_amount"] += amt
        elif kind == "refund":
            out["refund_amount"] += amt
        elif kind == "allocate":
            out["allocated_amount"] += amt
        elif kind in ("deposit", "rounding_deposit", "ap_advance", "ap_rounding_advance"):
            out["deposit_amount"] += amt
        elif kind == "reschedule":
            out["rescheduled_amount"] += amt
    for k in ("writeoff_amount", "refund_amount", "allocated_amount", "deposit_amount",
              "rescheduled_amount"):
        out[k] = round(out[k], 2)
    out["pending"] = len(await pending(entity_id))
    return out


# ── Bahan invarian (INV-VAR-01 / INV-VAR-02) ──────────────────────────────
async def undecided_variances(limit: int = 20) -> List[Dict[str, Any]]:
    """INV-VAR-01 — selisih di luar toleransi yang tidak punya keputusan berlabel."""
    bad: List[Dict[str, Any]] = []
    async for r in db.ar_receipts.find(
            {"status": {"$ne": "void"}, "variance.needs_decision": True},
            {"_id": 0, "id": 1, "number": 1, "variance": 1, "created_at": 1}):
        v = r.get("variance") or {}
        if v.get("decision_id"):
            continue
        bad.append({"id": r["id"], "number": r.get("number", r["id"]),
                    "delta": round(float(v.get("delta") or 0), 2),
                    "age_days": _age_days(r.get("created_at", ""))})
        if len(bad) >= limit:
            break
    return bad


async def decisions_without_label(limit: int = 20) -> List[Dict[str, Any]]:
    """INV-VAR-01 — keputusan tanpa label alasan / tanpa pemutus (tidak boleh ada)."""
    bad: List[Dict[str, Any]] = []
    async for r in db[COLL].find({}, {"_id": 0, "id": 1, "number": 1, "kind": 1,
                                      "reason_code": 1, "decided_by": 1}):
        if not (r.get("reason_code") or "").strip() or not (r.get("decided_by") or "").strip():
            bad.append({"id": r["id"], "number": r.get("number", r["id"]),
                        "kind": r.get("kind", "")})
            if len(bad) >= limit:
                break
    return bad


async def sensitive_without_journal(limit: int = 20) -> List[Dict[str, Any]]:
    """INV-VAR-02 — keputusan yang MEMINDAHKAN uang wajib punya jurnal."""
    need_je = ("writeoff", "rounding_writeoff", "allocate", "refund",
               "ap_writeoff", "ap_rounding_writeoff")
    bad: List[Dict[str, Any]] = []
    async for r in db[COLL].find({"kind": {"$in": list(need_je)}},
                                 {"_id": 0, "id": 1, "number": 1, "kind": 1,
                                  "je_id": 1, "amount": 1}):
        if float(r.get("amount") or 0) <= EPS:
            continue
        if not (r.get("je_id") or "").strip():
            bad.append({"id": r["id"], "number": r.get("number", r["id"]),
                        "kind": r.get("kind", "")})
            if len(bad) >= limit:
                break
    return bad


async def receipt_money_leaks(limit: int = 20) -> List[Dict[str, Any]]:
    """INV-VAR-02 — pada tiap kwitansi: dana == teralokasi + belum teralokasi."""
    bad: List[Dict[str, Any]] = []
    async for r in db.ar_receipts.find(
            {"status": {"$ne": "void"}},
            {"_id": 0, "id": 1, "number": 1, "total_funds": 1, "amount": 1,
             "used_deposit": 1, "applied_total": 1, "unapplied_amount": 1}):
        funds = round(float(r.get("total_funds")
                            if r.get("total_funds") is not None
                            else float(r.get("amount") or 0) + float(r.get("used_deposit") or 0)), 2)
        parts = round(float(r.get("applied_total") or 0) + float(r.get("unapplied_amount") or 0), 2)
        if abs(funds - parts) > 0.01:
            bad.append({"id": r["id"], "number": r.get("number", r["id"]),
                        "funds": funds, "parts": parts})
            if len(bad) >= limit:
                break
    return bad


async def overspent_decisions(limit: int = 20) -> List[Dict[str, Any]]:
    """INV-VAR-02 — keputusan tidak boleh memindahkan lebih dari kelebihan kwitansinya."""
    bad: List[Dict[str, Any]] = []
    async for r in db[COLL].find({"side": "ar", "kind": {"$in": ["allocate", "refund"]}},
                                 {"_id": 0, "id": 1, "number": 1, "amount": 1,
                                  "receipt_id": 1, "delta": 1}):
        rec = await db.ar_receipts.find_one({"id": r.get("receipt_id")},
                                            {"_id": 0, "unapplied_amount": 1, "number": 1})
        cap = round(float((rec or {}).get("unapplied_amount") or 0), 2)
        if round(float(r.get("amount") or 0), 2) > cap + 0.01:
            bad.append({"id": r["id"], "number": r.get("number", r["id"]),
                        "amount": round(float(r.get("amount") or 0), 2), "cap": cap})
            if len(bad) >= limit:
                break
    return bad
