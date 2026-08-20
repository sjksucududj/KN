"""FASE G-2 — **DENDA KETERLAMBATAN SEBAGAI DOKUMEN** (`penalties`).

MASALAH NYATA PEMILIK
---------------------
Denda hari ini hanya **angka estimasi** di laporan Umur Piutang: tidak bisa ditagih, tidak
bisa dinegosiasikan, tidak bisa dibebaskan dengan alasan, dan tidak pernah masuk pembukuan.
Akibatnya pembicaraan denda dengan pelanggan selalu di luar sistem.

DESAIN (kunci fleksibilitas)
----------------------------
Denda lahir sebagai **`draft`** — **TANPA jurnal**. Jadi bisa dinegosiasikan atau dibatalkan
tanpa pernah mengotori buku besar. Siklusnya:

    draft  ──terbitkan──>  issued   (Dr 1-1270 Piutang Denda / Cr 4-9300 Pendapatan Denda)
      │                        │
      │                        ├──bayar──>  paid    (Dr Kas / Cr Piutang Denda)
      │                        ├──bebaskan──> waived  (JE pembalik — ledger append-only)
      │                        └──ubah nominal──> adjusted (JE selisih)
      └──bebaskan / ubah nominal saat masih draft → cukup ubah dokumen (tak ada jurnal)

Pembebasan & perubahan nominal WAJIB: **label alasan** (taksonomi `amendment_reasons`
yang bisa ditambah admin, warisan FASE G-1) + **persetujuan** bila kebijakan mensyaratkan.

INVARIAN
--------
* **INV-PEN-01** denda `draft` tidak boleh punya jurnal.
* **INV-PEN-02** `waived` / `adjusted` wajib punya alasan; wajib penyetuju bila kebijakan
  `payment.penalty_waive_requires_approval` aktif.
* **INV-PEN-03** Σ denda terbit yang belum dibayar == saldo akun Piutang Denda di GL.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core_utils import new_id, next_doc_number, now_iso, safe_doc, rupiah
from db import db
from services import gl_service
from services import payment_plan_service as plans
from services.config_resolver import resolve

COLL = "penalties"
EPS = 0.01
STATUSES = ("draft", "issued", "waived", "adjusted", "paid")
STATUS_LABEL = {
    "draft": "Usulan (belum berjurnal)",
    "issued": "Terbit (sudah berjurnal)",
    "waived": "Dibebaskan",
    "adjusted": "Nominal diubah",
    "paid": "Sudah dibayar",
}
REASON_DOC_TYPE = "penalty"        # `amendment_reasons.applies_to` — dikelola admin


class PenaltyError(ValueError):
    """Kesalahan denda dengan pesan siap tampil (Bahasa Indonesia)."""


# ── Kebijakan (registry) ───────────────────────────────────────────────
async def penalty_policy(entity_id: str = "", customer_id: str = "",
                         plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Kebijakan denda yang BERLAKU: global → entitas → pelanggan → override rencana.

    Bunga & masa tenggang sengaja memakai kunci yang sudah dipakai laporan Umur Piutang
    (`ar.denda_rate_pct_per_month`, `ar.grace_days`) supaya laporan dan nota denda tidak
    pernah bercerita beda.
    """
    ctx = {"entity_id": entity_id or "", "customer_id": customer_id or ""}

    async def val(key: str) -> Any:
        return (await resolve(key, ctx))["value"]

    pol = {
        "mode": str(await val("payment.penalty_mode") or "draft"),
        "base": str(await val("payment.penalty_base") or "installment"),
        "cap_pct": float(await val("payment.penalty_cap_pct") or 0),
        "min_amount": float(await val("payment.penalty_min_amount") or 0),
        "waive_requires_approval": bool(await val("payment.penalty_waive_requires_approval")),
        "approver_role": str(await val("payment.penalty_waive_approver_role") or "manager"),
        "rate_pct_per_month": float(await val("ar.denda_rate_pct_per_month") or 0),
        "grace_days": int(await val("ar.grace_days") or 0),
    }
    # Override per rencana pembayaran (kesepakatan khusus pelanggan tertentu).
    over = (plan or {}).get("penalty") or {}
    for src, dst in (("mode", "mode"), ("base", "base")):
        if over.get(src):
            pol[dst] = str(over[src])
    for src, dst in (("grace_days", "grace_days"), ("cap_pct", "cap_pct"),
                     ("rate_pct_per_month", "rate_pct_per_month")):
        if over.get(src) not in (None, ""):
            pol[dst] = float(over[src]) if dst != "grace_days" else int(over[src])
    return pol


# ── Perhitungan (auditable) ───────────────────────────────────────────
def _days_late(due_date: str, today: str) -> int:
    try:
        d1 = datetime.strptime(str(due_date)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        d2 = datetime.strptime(str(today)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0
    return max(0, (d2 - d1).days)


def compute_amount(base_amount: float, days_late: int, policy: Dict[str, Any]) -> Dict[str, Any]:
    """Hitung denda + `explain[]` supaya angkanya bisa dipertanggungjawabkan ke pelanggan."""
    grace = int(policy["grace_days"])
    billable = max(0, days_late - grace)
    rate = float(policy["rate_pct_per_month"])
    raw = round(float(base_amount) * (rate / 100.0) * (billable / 30.0), 2)
    cap_pct = float(policy["cap_pct"] or 0)
    capped = raw
    if cap_pct > 0:
        limit = round(float(base_amount) * cap_pct / 100.0, 2)
        capped = min(raw, limit)
    explain = [
        f"Dasar denda {rupiah(float(base_amount))} ({'nilai cicilan' if policy['base'] == 'installment' else 'sisa piutang order'})",
        f"Telat {days_late} hari − tenggang {grace} hari = {billable} hari kena denda",
        f"Bunga {rate:g}% / bulan × {billable}/30 hari → {rupiah(raw)}",
    ]
    if cap_pct > 0:
        explain.append(
            f"Batas maksimum {cap_pct:g}% dari dasar = {rupiah(round(float(base_amount) * cap_pct / 100.0))} → dipakai {rupiah(capped)}")
    return {"amount": capped, "raw_amount": raw, "days_late": days_late,
            "billable_days": billable, "rate_pct_per_month": rate,
            "grace_days": grace, "cap_pct": cap_pct, "explain": explain}


def _period_key(due_date: str, today: str) -> str:
    """Kunci periode akrual: satu nota per baris per BULAN kalender berjalan.

    Ini yang membuat job harian idempotent: dijalankan 30× sebulan tetap satu nota,
    hanya nominalnya yang diperbarui selama masih `draft`.
    """
    return f"{str(due_date)[:10]}|{str(today)[:7]}"


# ── Akrual (dipakai job harian & tombol "hitung sekarang") ─────────────────
async def accrue_plan(plan: Dict[str, Any], today: Optional[str] = None,
                      actor_name: str = "system") -> List[Dict[str, Any]]:
    """Bentuk / perbarui nota denda untuk semua baris yang telat pada satu rencana."""
    day = (today or now_iso())[:10]
    policy = await penalty_policy(plan.get("entity_id") or "",
                                  plan.get("customer_id") or "", plan)
    if policy["mode"] == "off":
        return []
    order = await db.sales_orders.find_one({"id": plan.get("doc_id")}, {"_id": 0}) or {}
    outstanding = round(plans.source_total(safe_doc(order)) - plans.source_paid(safe_doc(order)), 2)
    out: List[Dict[str, Any]] = []

    for line in plans.overdue_lines(plan, day):
        days = _days_late(line.get("due_date", ""), day)
        if days <= int(policy["grace_days"]):
            continue
        line_out = round(float(line.get("amount") or 0) - float(line.get("paid_amount") or 0), 2)
        base_amount = line_out if policy["base"] == "installment" else max(outstanding, 0.0)
        if base_amount <= EPS:
            continue
        calc = compute_amount(base_amount, days, policy)
        if calc["amount"] < float(policy["min_amount"]) - EPS:
            continue

        pkey = _period_key(line.get("due_date", ""), day)
        existing = await db[COLL].find_one(
            {"plan_id": plan["id"], "line_seq": line["seq"], "period_key": pkey}, {"_id": 0})
        if existing:
            # Nota yang sudah diputus manusia TIDAK boleh ditimpa mesin.
            if existing.get("status") != "draft":
                out.append(safe_doc(existing))
                continue
            await db[COLL].update_one({"id": existing["id"]}, {"$set": {
                "amount": calc["amount"], "base_amount": base_amount,
                "days_late": calc["days_late"], "billable_days": calc["billable_days"],
                "explain": calc["explain"], "updated_at": now_iso()}})
            out.append(await get(existing["id"]))
            continue

        doc = await _create(plan, line, calc, base_amount, pkey, policy, actor_name)
        if policy["mode"] == "auto":
            doc = await issue(doc["id"], {"name": actor_name, "role": "system"}, auto=True)
        out.append(doc)
    return out


async def _create(plan: Dict[str, Any], line: Dict[str, Any], calc: Dict[str, Any],
                  base_amount: float, period_key: str, policy: Dict[str, Any],
                  actor_name: str) -> Dict[str, Any]:
    entity_id = plan.get("entity_id") or ""
    number = await next_doc_number(COLL, "number", "DN-DENDA-", entity_id=entity_id or None)
    now = now_iso()
    doc = {
        "id": new_id("pnl"), "number": number, "entity_id": entity_id,
        "doc_type": plan.get("doc_type", "sales_order"), "doc_id": plan.get("doc_id", ""),
        "doc_number": plan.get("doc_number", ""),
        "plan_id": plan.get("id", ""), "plan_number": plan.get("number", ""),
        "line_seq": line.get("seq"), "line_label": line.get("label", ""),
        "due_date": line.get("due_date", ""), "period_key": period_key,
        "customer_id": plan.get("customer_id", ""), "customer_name": plan.get("customer_name", ""),
        "base_amount": round(float(base_amount), 2), "base": policy["base"],
        "amount": calc["amount"], "original_amount": calc["amount"],
        "days_late": calc["days_late"], "billable_days": calc["billable_days"],
        "rate_pct_per_month": calc["rate_pct_per_month"], "grace_days": calc["grace_days"],
        "cap_pct": calc["cap_pct"],
        "status": "draft", "status_label": STATUS_LABEL["draft"],
        "paid_amount": 0.0, "je_id": "", "je_number": "",
        "reason_code": "", "reason_label": "", "decision_note": "",
        "decided_by": "", "decided_at": "", "approval_request_id": "",
        "policy_snapshot": policy, "explain": calc["explain"],
        "created_by": actor_name, "created_at": now, "updated_at": now, "refs": [],
    }
    await db[COLL].insert_one(dict(doc))
    # FASE G-4 — nota denda WAJIB menyebut dokumen sumbernya (bisa ditelusuri dua arah).
    from services import doc_refs_service as _refs
    await _refs.safe_link(("penalty", doc["id"]), (doc["doc_type"], doc["doc_id"]),
                          "parent", note=f"denda keterlambatan {line.get('label', '')}")
    await _notify(doc)
    return safe_doc(doc)


async def accrue_order(order: Dict[str, Any], today: Optional[str] = None,
                       actor_name: str = "system") -> List[Dict[str, Any]]:
    """FASE G-3 (pelengkap G-2) — nota denda untuk pesanan yang **tidak punya rencana**.

    Laporan Umur Piutang menghitung denda untuk SETIAP pesanan yang telat, sementara
    FASE G-2 hanya bisa menerbitkan nota dari baris rencana pembayaran. Akibatnya kolom
    denda di laporan tidak bisa ditautkan ke dokumen nyata untuk pesanan tanpa rencana —
    tepat masalah yang diminta pemilik untuk ditutup.

    Di sini pesanannya diperlakukan sebagai **satu baris jatuh tempo** (tempo = tanggal
    pesanan + term pelanggan), memakai kebijakan, perhitungan, jurnal, dan siklus
    keputusan yang SAMA — jadi tidak ada mesin denda kedua yang bisa bercerita beda.
    """
    day = (today or now_iso())[:10]
    if await plans.get_active("sales_order", order.get("id", "")):
        return []   # ada rencana → nota denda lahir dari barisnya (jangan dobel)
    policy = await penalty_policy(order.get("entity_id") or "",
                                  order.get("customer_id") or "")
    if policy["mode"] == "off":
        return []
    from services.customer_service import (_order_grand_total as gt_of,
                                           _order_paid as paid_of,
                                           order_payment_method, _parse_dt as parse_dt,
                                           _term_days as term_days, DEAD_STATUSES,
                                           NON_AR_METHODS)
    if order.get("status") in DEAD_STATUSES or order_payment_method(order) in NON_AR_METHODS:
        return []
    outstanding = round(gt_of(order) - paid_of(order), 2)
    if outstanding <= EPS:
        return []
    cust = await db.customers.find_one({"id": order.get("customer_id")},
                                       {"_id": 0, "payment_profile": 1, "name": 1}) or {}
    from datetime import timedelta as _td
    created = parse_dt(order.get("created_at")) or datetime.now(timezone.utc)
    due = (created + _td(days=term_days(cust, order))).date().isoformat()
    days = _days_late(due, day)
    if days <= int(policy["grace_days"]):
        return []
    calc = compute_amount(outstanding, days, policy)
    if calc["amount"] < float(policy["min_amount"]) - EPS:
        return []
    pseudo_plan = {
        "id": "", "number": "", "entity_id": order.get("entity_id") or "",
        "doc_type": "sales_order", "doc_id": order.get("id", ""),
        "doc_number": order.get("number", ""),
        "customer_id": order.get("customer_id", ""),
        "customer_name": order.get("customer_name") or cust.get("name", ""),
    }
    line = {"seq": 0, "label": f"Sisa tagihan pesanan {order.get('number', '')}",
            "due_date": due, "amount": outstanding, "paid_amount": 0.0}
    pkey = _period_key(due, day)
    existing = await db[COLL].find_one(
        {"doc_id": order.get("id"), "plan_id": "", "line_seq": 0, "period_key": pkey},
        {"_id": 0})
    if existing:
        if existing.get("status") != "draft":
            return [safe_doc(existing)]
        await db[COLL].update_one({"id": existing["id"]}, {"$set": {
            "amount": calc["amount"], "base_amount": outstanding,
            "days_late": calc["days_late"], "billable_days": calc["billable_days"],
            "explain": calc["explain"], "updated_at": now_iso()}})
        return [await get(existing["id"])]
    doc = await _create(pseudo_plan, line, calc, outstanding, pkey, policy, actor_name)
    if policy["mode"] == "auto":
        doc = await issue(doc["id"], {"name": actor_name, "role": "system"}, auto=True)
    return [doc]


async def accrue_customer(customer_id: str, today: Optional[str] = None,
                          actor_name: str = "system") -> List[Dict[str, Any]]:
    """Hitung denda untuk SEMUA pesanan telat satu pelanggan (dengan / tanpa rencana).

    Inilah tombol "Buat Nota Denda" pada laporan Umur Piutang: kolom denda estimasi
    berubah menjadi dokumen nyata yang bisa ditagih, dinegosiasikan, atau dibebaskan.
    """
    out: List[Dict[str, Any]] = []
    async for row in db[plans.COLL].find({"customer_id": customer_id, "status": "active"},
                                         {"_id": 0}):
        out.extend(await accrue_plan(safe_doc(row), today=today, actor_name=actor_name))
    async for row in db.sales_orders.find({"customer_id": customer_id}, {"_id": 0}):
        out.extend(await accrue_order(safe_doc(row), today=today, actor_name=actor_name))
    return out


async def for_docs(doc_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Nota denda per dokumen sumber (dipakai laporan Umur Piutang menautkan kolomnya)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not doc_ids:
        return out
    async for r in db[COLL].find({"doc_id": {"$in": list(doc_ids)}}, {"_id": 0}):
        out.setdefault(r.get("doc_id", ""), []).append(safe_doc(r))
    for rows in out.values():
        rows.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return out


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ringkasan nota denda: berapa yang masih usulan, terbit, dibebaskan, dibayar."""
    draft = issued = waived = paid = 0.0
    counts = {s: 0 for s in STATUSES}
    for r in rows or []:
        st = r.get("status", "draft")
        counts[st] = counts.get(st, 0) + 1
        amt = float(r.get("amount") or 0)
        if st == "draft":
            draft += amt
        elif st in ("issued", "adjusted"):
            issued += amt - float(r.get("paid_amount") or 0)
        elif st == "waived":
            waived += float(r.get("waived_amount") or 0)
        elif st == "paid":
            paid += float(r.get("paid_amount") or amt)
    return {"count": len(rows or []), "counts": counts,
            "draft_amount": round(draft, 2), "issued_outstanding": round(issued, 2),
            "waived_amount": round(waived, 2), "paid_amount": round(paid, 2),
            "actual_amount": round(draft + issued, 2)}


async def _notify(doc: Dict[str, Any]) -> None:
    try:
        from services import notification_service as ns
        await ns.create_notification(
            notif_type="penalty_draft", severity="warning",
            title=f"Usulan denda {doc['number']} · {doc.get('customer_name', '')}",
            body=(f"{doc.get('line_label', '')} pada {doc.get('doc_number', '')} telat "
                  f"{doc.get('days_late', 0)} hari — usulan denda {rupiah(doc['amount'])}. "
                  "Masih bisa dinegosiasikan / dibebaskan.").replace(",", "."),
            link="payment-plans", entity_id=doc.get("entity_id"),
            recipient_role="manager", ref=doc["id"], dedupe_scope="day")
    except Exception:  # noqa: BLE001 — notifikasi best-effort
        return


# ── Siklus keputusan ──────────────────────────────────────────────────
async def get(penalty_id: str) -> Optional[Dict[str, Any]]:
    row = await db[COLL].find_one({"id": penalty_id}, {"_id": 0})
    return safe_doc(row) if row else None


async def _reason_or_fail(reason_code: str) -> Dict[str, Any]:
    code = (reason_code or "").strip()
    if not code:
        raise PenaltyError("Label alasan wajib dipilih — denda tidak boleh hilang tanpa sebab.")
    from services.amendment_service import ensure_reasons
    await ensure_reasons()
    row = await db.amendment_reasons.find_one({"code": code}, {"_id": 0})
    if not row or row.get("active") is False or row.get("status") not in (None, "active"):
        raise PenaltyError(f"Label alasan '{code}' tidak terdaftar / sudah tidak aktif.")
    applies = row.get("applies_to") or []
    if applies and REASON_DOC_TYPE not in applies:
        raise PenaltyError(f"Label alasan '{row['label']}' tidak berlaku untuk denda.")
    return safe_doc(row)


async def issue(penalty_id: str, actor: Dict[str, Any], auto: bool = False) -> Dict[str, Any]:
    """Terbitkan denda → jurnal Dr Piutang Denda / Cr Pendapatan Denda (sekali saja)."""
    p = await get(penalty_id)
    if not p:
        raise PenaltyError("Nota denda tidak ditemukan.")
    if p["status"] != "draft":
        raise PenaltyError(f"Nota denda sudah berstatus '{STATUS_LABEL.get(p['status'], p['status'])}'.")
    if float(p["amount"]) <= EPS:
        raise PenaltyError("Nominal denda nol — tidak ada yang bisa diterbitkan.")
    je = await gl_service.post_penalty_issue(
        penalty_id=p["id"], entity_id=p.get("entity_id", ""), amount=float(p["amount"]),
        label=f"{p['number']} · {p.get('customer_name', '')}",
        date=now_iso(), created_by=actor.get("name", "system"))
    await db[COLL].update_one({"id": p["id"]}, {"$set": {
        "status": "issued", "status_label": STATUS_LABEL["issued"],
        "je_id": (je or {}).get("id", ""), "je_number": (je or {}).get("number", ""),
        "issued_by": actor.get("name", "system"), "issued_at": now_iso(),
        "issued_auto": bool(auto), "updated_at": now_iso()}})
    return await get(p["id"])


async def _needs_approval(p: Dict[str, Any]) -> Dict[str, Any]:
    policy = await penalty_policy(p.get("entity_id", ""), p.get("customer_id", ""))
    return {"required": bool(policy["waive_requires_approval"]),
            "role": policy["approver_role"]}


async def waive(penalty_id: str, reason_code: str, note: str,
                actor: Dict[str, Any]) -> Dict[str, Any]:
    """Bebaskan denda. Bila sudah berjurnal → JE PEMBALIK (ledger append-only)."""
    p = await get(penalty_id)
    if not p:
        raise PenaltyError("Nota denda tidak ditemukan.")
    if p["status"] in ("waived", "paid"):
        raise PenaltyError(f"Nota denda sudah '{STATUS_LABEL.get(p['status'], p['status'])}'.")
    reason = await _reason_or_fail(reason_code)
    appr = await _needs_approval(p)
    if appr["required"] and (actor.get("role") or "") not in (appr["role"], "admin"):
        raise PenaltyError(
            f"Pembebasan denda wajib disetujui {appr['role']} — ajukan lewat penyetuju.")
    je = None
    if p["status"] in ("issued", "adjusted") and float(p.get("amount") or 0) > EPS:
        je = await gl_service.post_penalty_reversal(
            penalty_id=p["id"], entity_id=p.get("entity_id", ""), amount=float(p["amount"]),
            label=f"Pembebasan denda {p['number']} · {reason['label']}",
            date=now_iso(), created_by=actor.get("name", "system"), suffix="waive")
    await db[COLL].update_one({"id": p["id"]}, {"$set": {
        "status": "waived", "status_label": STATUS_LABEL["waived"],
        "waived_amount": float(p["amount"]), "amount": 0.0,
        "reason_code": reason["code"], "reason_label": reason["label"],
        "decision_note": (note or "").strip(),
        "decided_by": actor.get("name", ""), "decided_at": now_iso(),
        "approver_role_required": appr["role"] if appr["required"] else "",
        "reversal_je_id": (je or {}).get("id", ""),
        "updated_at": now_iso()}})
    return await get(p["id"])


async def adjust(penalty_id: str, new_amount: float, reason_code: str, note: str,
                 actor: Dict[str, Any]) -> Dict[str, Any]:
    """Ubah nominal denda (negosiasi). Bila sudah berjurnal → JE SELISIH."""
    p = await get(penalty_id)
    if not p:
        raise PenaltyError("Nota denda tidak ditemukan.")
    if p["status"] in ("waived", "paid"):
        raise PenaltyError(f"Nota denda sudah '{STATUS_LABEL.get(p['status'], p['status'])}'.")
    amt = round(float(new_amount or 0), 2)
    if amt < 0:
        raise PenaltyError("Nominal denda tidak boleh negatif.")
    if amt > round(float(p["amount"]), 2) + EPS:
        raise PenaltyError("Nominal baru tidak boleh lebih besar dari denda semula — "
                           "terbitkan nota denda baru bila memang bertambah.")
    reason = await _reason_or_fail(reason_code)
    appr = await _needs_approval(p)
    if appr["required"] and (actor.get("role") or "") not in (appr["role"], "admin"):
        raise PenaltyError(
            f"Perubahan nominal denda wajib disetujui {appr['role']}.")
    delta = round(float(p["amount"]) - amt, 2)
    je = None
    if p["status"] in ("issued", "adjusted") and delta > EPS:
        je = await gl_service.post_penalty_reversal(
            penalty_id=p["id"], entity_id=p.get("entity_id", ""), amount=delta,
            label=f"Penyesuaian denda {p['number']} · {reason['label']}",
            date=now_iso(), created_by=actor.get("name", "system"), suffix="adjust")
    await db[COLL].update_one({"id": p["id"]}, {"$set": {
        "status": "adjusted" if p["status"] != "draft" else "draft",
        "status_label": STATUS_LABEL["adjusted"] if p["status"] != "draft" else STATUS_LABEL["draft"],
        "amount": amt, "adjusted_from": float(p["amount"]),
        "reason_code": reason["code"], "reason_label": reason["label"],
        "decision_note": (note or "").strip(),
        "decided_by": actor.get("name", ""), "decided_at": now_iso(),
        "approver_role_required": appr["role"] if appr["required"] else "",
        "adjust_je_id": (je or {}).get("id", ""),
        "updated_at": now_iso()}})
    return await get(p["id"])


async def pay(penalty_id: str, amount: float, method: str,
              actor: Dict[str, Any]) -> Dict[str, Any]:
    """Terima pembayaran denda → Dr Kas / Cr Piutang Denda."""
    p = await get(penalty_id)
    if not p:
        raise PenaltyError("Nota denda tidak ditemukan.")
    if p["status"] not in ("issued", "adjusted"):
        raise PenaltyError("Denda harus DITERBITKAN dulu sebelum bisa menerima pembayaran.")
    amt = round(float(amount or 0), 2)
    outstanding = round(float(p["amount"]) - float(p.get("paid_amount") or 0), 2)
    if amt <= EPS:
        raise PenaltyError("Nominal pembayaran harus lebih dari nol.")
    if amt > outstanding + EPS:
        raise PenaltyError(f"Pembayaran melebihi sisa denda ({rupiah(outstanding)})."
                           .replace(",", "."))
    je = await gl_service.post_penalty_payment(
        penalty_id=p["id"], entity_id=p.get("entity_id", ""), amount=amt, method=method or "transfer",
        label=f"Pembayaran denda {p['number']}", date=now_iso(),
        created_by=actor.get("name", "system"))
    paid = round(float(p.get("paid_amount") or 0) + amt, 2)
    full = paid >= round(float(p["amount"]), 2) - EPS
    await db[COLL].update_one({"id": p["id"]}, {"$set": {
        "paid_amount": paid,
        "status": "paid" if full else p["status"],
        "status_label": STATUS_LABEL["paid"] if full else p.get("status_label", ""),
        "payment_je_id": (je or {}).get("id", ""),
        "paid_at": now_iso() if full else "",
        "updated_at": now_iso()}})
    return await get(p["id"])


# ── Pembacaan & invarian ──────────────────────────────────────────────
async def list_penalties(entity_id: str = "", status: str = "", doc_id: str = "",
                        q: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    flt: Dict[str, Any] = {}
    # FASE E-0 (L4) — dukung filter entitas siap-pakai dari `entity_scope.scope_value()`.
    if isinstance(entity_id, dict):
        flt["entity_id"] = entity_id
    elif entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    if status:
        flt["status"] = status
    if doc_id:
        flt["doc_id"] = doc_id
    if q:
        import re as _re
        rx = _re.compile(_re.escape(q), _re.I)
        flt["$or"] = [{"number": rx}, {"doc_number": rx}, {"customer_name": rx}]
    rows = await db[COLL].find(flt, {"_id": 0}).sort("created_at", -1).to_list(int(limit))
    return [safe_doc(r) for r in rows]


async def stats(entity_id: Any = "") -> Dict[str, Any]:
    flt: Dict[str, Any] = {}
    if isinstance(entity_id, dict):
        flt["entity_id"] = entity_id
    elif entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    out = {s: 0 for s in STATUSES}
    draft_amount = issued_outstanding = waived_amount = 0.0
    async for r in db[COLL].find(flt, {"_id": 0, "status": 1, "amount": 1, "paid_amount": 1,
                                       "waived_amount": 1}):
        st = r.get("status", "draft")
        out[st] = out.get(st, 0) + 1
        if st == "draft":
            draft_amount += float(r.get("amount") or 0)
        elif st in ("issued", "adjusted"):
            issued_outstanding += float(r.get("amount") or 0) - float(r.get("paid_amount") or 0)
        elif st == "waived":
            waived_amount += float(r.get("waived_amount") or 0)
    return {**out, "draft_amount": round(draft_amount, 2),
            "issued_outstanding": round(issued_outstanding, 2),
            "waived_amount": round(waived_amount, 2)}


async def outstanding_total(entity_id: str = "") -> float:
    """Σ denda terbit yang belum dibayar — bahan INV-PEN-03 (dibanding saldo GL)."""
    flt: Dict[str, Any] = {"status": {"$in": ["issued", "adjusted"]}}
    if entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    total = 0.0
    async for r in db[COLL].find(flt, {"_id": 0, "amount": 1, "paid_amount": 1}):
        total += float(r.get("amount") or 0) - float(r.get("paid_amount") or 0)
    return round(total, 2)


async def drafts_with_journal(limit: int = 20) -> List[Dict[str, Any]]:
    """Bahan INV-PEN-01: denda draft yang (salah) punya jurnal."""
    bad: List[Dict[str, Any]] = []
    async for r in db[COLL].find({"status": "draft"}, {"_id": 0, "id": 1, "number": 1}):
        if await db.journal_entries.find_one(
                {"source_type": "penalty", "source_id": r["id"], "status": {"$ne": "void"}},
                {"_id": 1}):
            bad.append({"id": r["id"], "number": r.get("number", r["id"])})
            if len(bad) >= limit:
                break
    return bad


async def decided_without_reason(limit: int = 20) -> List[Dict[str, Any]]:
    """Bahan INV-PEN-02: keputusan bebas/ubah tanpa alasan atau tanpa pemutus."""
    bad: List[Dict[str, Any]] = []
    async for r in db[COLL].find({"status": {"$in": ["waived", "adjusted"]}},
                                 {"_id": 0, "id": 1, "number": 1, "status": 1,
                                  "reason_code": 1, "decided_by": 1}):
        if not (r.get("reason_code") or "").strip() or not (r.get("decided_by") or "").strip():
            bad.append({"id": r["id"], "number": r.get("number", r["id"]),
                        "status": r.get("status")})
            if len(bad) >= limit:
                break
    return bad


# ── Job penjadwal ─────────────────────────────────────────────────────
async def job_penalty_accrual() -> Dict[str, Any]:
    """Pindai seluruh rencana aktif → bentuk/perbarui usulan denda. Idempotent per periode."""
    created = updated = 0
    scanned = 0
    async for row in db[plans.COLL].find({"status": "active"}, {"_id": 0}):
        plan = safe_doc(row)
        scanned += 1
        before = await db[COLL].count_documents({"plan_id": plan["id"]})
        rows = await accrue_plan(plan, actor_name="scheduler")
        after = await db[COLL].count_documents({"plan_id": plan["id"]})
        created += max(0, after - before)
        updated += max(0, len(rows) - max(0, after - before))
    return {"scanned_plans": scanned, "created": created, "updated": updated}
