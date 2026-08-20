"""FASE E-8 (E8.7/E8.15/E8.20) — **MEJA KERJA BERBASIS ANTREAN** (Admin Sales & Finance).

KENAPA BERKAS INI ADA
=====================
Temuan A9 (`ANALISIS_DOMAIN_SALES.md`): keputusan yang harus diambil Admin Sales
tersebar di **lima layar milik domain lain** (Pembelian, Gudang, Keuangan, CRM,
Antar Entitas). Orang yang seharusnya menjaga alur pesanan justru harus berkeliling
menu untuk tahu "apa yang menunggu saya hari ini" — dan karena tidak ada satu tempat
yang menghitungnya, pekerjaan basi tanpa ada yang sadar.

Yang dibangun di sini **bukan mesin baru**: seluruh angka diambil dari mesin yang
sudah terbukti (papan pending SO, backorder, retur, permintaan internal, pengingat
penagihan, selisih bayar, denda). Modul ini hanya **menyusunnya jadi antrean kerja**
dengan satu tindakan jelas per baris.

DUA MEJA, SESUAI KEPUTUSAN PEMILIK (E8.10b#2)
---------------------------------------------
* **Meja Admin Sales** (8 antrean) — alur pesanan: verifikasi → konfirmasi → dokumen
  → pemenuhan → retur → permintaan internal. **Faktur pajak & uang masuk TIDAK di
  sini** (itu Finance) supaya pemisahan tugas terlihat di layar, bukan cuma di izin.
* **Meja Finance** (5 antrean) — uang masuk & pajak keluaran: faktur pajak siap
  terbit, uang masuk perlu dicatat, selisih bayar, denda perlu diterbitkan, jatuh tempo.

Tiap baris membawa: konteks pelanggan · nilai · **umur (hari)** · tindakan tunggal.
Umur dipakai sebagai isyarat SLA: makin tua, makin merah di layar.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso, safe_doc

ROW_LIMIT = 60

# ── Status pesanan per tahap alur ────────────────────────────────────────────
STATUS_BARU = ("reserved", "waiting_stock")
STATUS_SIAP_KONFIRMASI = ("approved",)
STATUS_MENUNGGU_MANAJER = ("waiting_approval",)
STATUS_DOKUMEN = ("confirmed", "partially_picked", "picked", "partially_shipped", "shipped")
STATUS_PAJAK_LAYAK = ("confirmed", "partially_picked", "picked", "partially_shipped",
                      "shipped", "done")
RETUR_ANTREAN = ("pending_approval", "approved", "pending_process", "quarantine")
PIN_ANTREAN = ("draft", "submitted", "open", "pending")


def _age_days(iso: Optional[str]) -> int:
    if not iso:
        return 0
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if not t.tzinfo:
            t = t.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - t).days)
    except Exception:  # noqa: BLE001
        return 0


def _q(scope: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(scope or {})
    out.update(extra)
    return out


def _row(*, ref_type: str, ref_id: str, number: str, title: str, subtitle: str = "",
         value: float = 0.0, age_days: int = 0, badge: str = "",
         action: str = "", action_kind: str = "open", extra: Optional[Dict[str, Any]] = None
         ) -> Dict[str, Any]:
    return {"ref_type": ref_type, "ref_id": ref_id, "number": number, "title": title,
            "subtitle": subtitle, "value": round(float(value or 0), 2),
            "age_days": int(age_days), "badge": badge,
            "action": action, "action_kind": action_kind, **(extra or {})}


def _queue(qid: str, label: str, hint: str, rows: List[Dict[str, Any]], *,
           action_label: str = "", owner: str = "sales_admin",
           value_kind: str = "money", value_label: str = "Nilai") -> Dict[str, Any]:
    """Bungkus satu antrean + ringkasannya.

    `value_kind` ada karena tidak semua antrean menghitung RUPIAH: antrean
    "Perlu dipenuhi" menghitung **jumlah barang yang kurang** (yard/meter). Tanpa
    penanda ini layar akan menuliskan `Rp 200` untuk 200 yard — angka yang salah
    arti, dan jenis kekeliruan yang membuat pengguna berhenti percaya pada ringkasan.
    """
    rows = rows[:ROW_LIMIT]
    return {
        "id": qid, "label": label, "hint": hint, "owner": owner,
        "count": len(rows),
        "total_value": round(sum(r["value"] for r in rows), 2),
        "value_kind": value_kind, "value_label": value_label,
        "oldest_age_days": max([r["age_days"] for r in rows], default=0),
        "action_label": action_label,
        "rows": rows,
    }


async def _orders(scope: Dict[str, Any], statuses, *, verified: Optional[bool] = None
                  ) -> List[Dict[str, Any]]:
    flt = _q(scope, {"status": {"$in": list(statuses)}})
    rows = await db.sales_orders.find(flt, {
        "_id": 0, "id": 1, "number": 1, "customer_name": 1, "customer_city": 1,
        "grand_total": 1, "total_amount": 1, "created_at": 1, "status": 1, "stage": 1,
        "sales_name": 1, "verification": 1, "entity_id": 1, "is_pkp": 1, "ppn_amount": 1,
        "payment_status": 1, "pending_approvals": 1, "required_approval_role": 1,
    }).sort("created_at", 1).to_list(500)
    out = []
    for o in rows:
        ver = ((o.get("verification") or {}).get("status") == "verified")
        if verified is True and not ver:
            continue
        if verified is False and ver:
            continue
        out.append(safe_doc(o))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# MEJA ADMIN SALES
# ═══════════════════════════════════════════════════════════════════════════
async def sales_admin_desk(actor: Dict[str, Any], scope: Dict[str, Any],
                           entity_ids: List[str]) -> Dict[str, Any]:
    queues: List[Dict[str, Any]] = []

    # 1 — perlu diverifikasi (E8.13): pesanan baru dari sales, belum diperiksa
    belum = await _orders(scope, STATUS_BARU, verified=False)
    queues.append(_queue(
        "perlu_verifikasi", "Perlu diverifikasi",
        "Periksa kelengkapan: alamat & penerima · syarat bayar · PPN · NPWP bila minta faktur.",
        [_row(ref_type="sales_order", ref_id=o["id"], number=o["number"],
              title=o.get("customer_name", "—"),
              subtitle=f"{o.get('customer_city') or '—'} · dibuat {o.get('sales_name') or '—'}",
              value=o.get("grand_total") or o.get("total_amount") or 0,
              age_days=_age_days(o.get("created_at")), badge=o.get("stage") or o.get("status"),
              action="Verifikasi", action_kind="verify") for o in belum],
        action_label="Verifikasi"))

    # 2 — siap dikonfirmasi: sudah disetujui → tekan konfirmasi, tugas gudang lahir
    approved = await _orders(scope, STATUS_SIAP_KONFIRMASI)
    queues.append(_queue(
        "siap_dikonfirmasi", "Siap dikonfirmasi",
        "Konfirmasi memicu tugas gudang. Wewenang Anda — tidak perlu menunggu manajer.",
        [_row(ref_type="sales_order", ref_id=o["id"], number=o["number"],
              title=o.get("customer_name", "—"),
              subtitle=("Terverifikasi" if (o.get("verification") or {}).get("status") == "verified"
                        else "Belum diverifikasi"),
              value=o.get("grand_total") or o.get("total_amount") or 0,
              age_days=_age_days(o.get("created_at")), badge=o.get("stage") or o.get("status"),
              action="Konfirmasi", action_kind="confirm") for o in approved],
        action_label="Konfirmasi"))

    # 3 — menunggu keputusan manajer (harga khusus/kredit/nilai) → hanya memantau
    tunggu = await _orders(scope, STATUS_MENUNGGU_MANAJER)
    queues.append(_queue(
        "menunggu_manajer", "Menunggu keputusan manajer",
        "Nilai · kredit · harga khusus adalah keputusan manajer. Anda memantau, bukan menyetujui.",
        [_row(ref_type="sales_order", ref_id=o["id"], number=o["number"],
              title=o.get("customer_name", "—"),
              subtitle="Butuh peran " + str(o.get("required_approval_role") or "manager"),
              value=o.get("grand_total") or o.get("total_amount") or 0,
              age_days=_age_days(o.get("created_at")), badge="menunggu",
              action="Lihat", action_kind="open") for o in tunggu],
        action_label="Lihat"))

    # 4 — siap cetak Surat Jalan / Invoice
    dok = await _orders(scope, STATUS_DOKUMEN)
    queues.append(_queue(
        "siap_cetak_dokumen", "Siap cetak Surat Jalan / Invoice",
        "Dokumen pengiriman & tagihan untuk pesanan yang sudah dikonfirmasi.",
        [_row(ref_type="sales_order", ref_id=o["id"], number=o["number"],
              title=o.get("customer_name", "—"), subtitle=o.get("stage") or o.get("status"),
              value=o.get("grand_total") or o.get("total_amount") or 0,
              age_days=_age_days(o.get("created_at")), badge=o.get("status"),
              action="Cetak", action_kind="open") for o in dok],
        action_label="Cetak"))

    # 5 — perlu dipenuhi (kurang stok) → TIGA tombol keputusan pemenuhan (US16)
    from services import stock_bucket_service as sbs
    pend = await sbs.pending_so_board(dict(scope or {}))
    per_order: Dict[str, Dict[str, Any]] = {}
    for b in pend:
        cur = per_order.setdefault(b["order_id"], {
            "order_number": b["order_number"], "customer_name": b.get("customer_name", "—"),
            "lines": [], "created_at": b.get("created_at"), "coverage": "covered"})
        cur["lines"].append(b)
        if b.get("coverage") != "covered":
            cur["coverage"] = b.get("coverage") or "partial"
    queues.append(_queue(
        "perlu_dipenuhi", "Perlu dipenuhi (kurang stok)",
        "Pilih SATU: ambil dari PT lain · reorder ke supplier · tahan untuk barang masuk.",
        [_row(ref_type="sales_order", ref_id=oid, number=v["order_number"],
              title=v["customer_name"],
              subtitle=" · ".join(f"{ln['product_name']} kurang "
                                  f"{ln['backorder_qty']:g} {ln['unit']}"
                                  for ln in v["lines"][:2]),
              value=sum(float(ln.get("backorder_qty") or 0) for ln in v["lines"]),
              age_days=_age_days(v.get("created_at")),
              badge=v["coverage"], action="Putuskan pemenuhan", action_kind="fulfill",
              extra={"lines": v["lines"],
                     "unit": (v["lines"][0].get("unit") if v["lines"] else "")})
         for oid, v in per_order.items()],
        action_label="Putuskan pemenuhan",
        # Yang dijumlahkan di sini JUMLAH BARANG yang kurang, bukan rupiah.
        value_kind="qty", value_label="Kurang"))

    # 6 — jatuh tempo & pengingat (Admin Sales memantau SELURUH pelanggan)
    from services.customer_service import collection_reminders
    tagih = await collection_reminders(actor, days_ahead=30,
                                       entity_id=entity_ids[0] if len(entity_ids) == 1 else None)
    queues.append(_queue(
        "jatuh_tempo", "Jatuh tempo & pengingat",
        "Tagihan lewat/nyaris jatuh tempo. Pencatatan uangnya di Meja Finance.",
        [_row(ref_type="sales_order", ref_id=r["order_id"], number=r["order_number"],
              title=r.get("customer_name", "—"),
              subtitle=(f"lewat {r['days_late']} hari" if r.get("overdue")
                        else f"jatuh tempo {abs(r['days_late'])} hari lagi"),
              value=r.get("outstanding") or 0,
              age_days=max(0, int(r.get("days_late") or 0)),
              badge="lewat" if r.get("overdue") else "segera",
              action="Follow-up", action_kind="open") for r in tagih],
        action_label="Follow-up"))

    # 7 — retur menunggu proses dokumen (diajukan sales, diproses Admin Sales)
    ret = await db.sales_returns.find(
        _q(scope, {"status": {"$in": list(RETUR_ANTREAN)}}),
        {"_id": 0, "id": 1, "number": 1, "customer_name": 1, "order_number": 1,
         "status": 1, "created_at": 1, "total_refund": 1, "items": 1, "return_type": 1}
    ).sort("created_at", 1).to_list(200)
    queues.append(_queue(
        "retur", "Retur menunggu proses dokumen",
        "Sales mengajukan, Anda memproses dokumennya. Persetujuan akhir tetap manajer.",
        [_row(ref_type="sales_return", ref_id=r["id"], number=r.get("number", "—"),
              title=r.get("customer_name", "—"),
              subtitle=f"atas {r.get('order_number') or '—'} · {len(r.get('items') or [])} baris",
              value=r.get("total_refund") or 0, age_days=_age_days(r.get("created_at")),
              badge=r.get("status", ""), action="Proses", action_kind="open")
         for r in map(safe_doc, ret)],
        action_label="Proses"))

    # 8 — permintaan internal dari sales (E8.8) → jadikan transaksi antar-PT
    pin = await db.internal_requests.find(
        _q(scope, {"status": {"$in": list(PIN_ANTREAN)}}),
        {"_id": 0, "id": 1, "number": 1, "reason": 1, "status": 1, "created_at": 1,
         "est_value": 1, "items": 1, "requested_by_name": 1, "source_order_number": 1}
    ).sort("created_at", 1).to_list(200)
    queues.append(_queue(
        "permintaan_internal", "Permintaan internal dari sales",
        "Sales meminta barang dari PT lain — Anda yang memilih sumbernya & mengesahkan.",
        [_row(ref_type="internal_request", ref_id=r["id"], number=r.get("number", "—"),
              title=r.get("reason", "—")[:70] or "—",
              subtitle=(f"untuk {r.get('source_order_number')}" if r.get("source_order_number")
                        else f"{len(r.get('items') or [])} barang"),
              value=r.get("est_value") or 0, age_days=_age_days(r.get("created_at")),
              badge=r.get("status", ""), action="Tindak", action_kind="open")
         for r in map(safe_doc, pin)],
        action_label="Tindak"))

    return {"desk": "sales_admin", "desk_label": "Meja Admin Sales",
            "generated_at": now_iso(), "entity_ids": entity_ids,
            "queues": queues,
            "totals": {"open_items": sum(q["count"] for q in queues)},
            "not_my_desk": ["Faktur Pajak keluaran", "Pencatatan uang masuk (kwitansi AR)",
                            "Keputusan selisih bayar"]}


# ═══════════════════════════════════════════════════════════════════════════
# MEJA FINANCE
# ═══════════════════════════════════════════════════════════════════════════
async def finance_desk(actor: Dict[str, Any], scope: Dict[str, Any],
                       entity_ids: List[str]) -> Dict[str, Any]:
    queues: List[Dict[str, Any]] = []

    # 1 — siap terbitkan Faktur Pajak: pesanan layak pajak yang belum ber-faktur aktif
    layak = await _orders(scope, STATUS_PAJAK_LAYAK)
    ids = [o["id"] for o in layak]
    ber_faktur = set()
    if ids:
        async for f in db.tax_invoices.find(
                {"order_id": {"$in": ids}, "status": {"$ne": "batal"}},
                {"_id": 0, "order_id": 1}):
            ber_faktur.add(f["order_id"])
    kandidat = [o for o in layak
                if o.get("is_pkp") is not False and float(o.get("ppn_amount") or 0) > 0
                and o["id"] not in ber_faktur]
    queues.append(_queue(
        "siap_faktur_pajak", "Siap terbitkan Faktur Pajak",
        "Pesanan ber-PPN yang belum punya faktur pajak keluaran aktif.",
        [_row(ref_type="sales_order", ref_id=o["id"], number=o["number"],
              title=o.get("customer_name", "—"),
              subtitle=f"PPN {float(o.get('ppn_amount') or 0):,.0f}".replace(",", "."),
              value=o.get("grand_total") or o.get("total_amount") or 0,
              age_days=_age_days(o.get("created_at")), badge=o.get("status", ""),
              action="Terbitkan", action_kind="issue_tax") for o in kandidat],
        action_label="Terbitkan", owner="finance"))

    # 2 & 5 — uang masuk perlu dicatat + jatuh tempo (dari pengingat penagihan)
    from services.customer_service import collection_reminders
    tagih = await collection_reminders(actor, days_ahead=30,
                                       entity_id=entity_ids[0] if len(entity_ids) == 1 else None)
    queues.append(_queue(
        "uang_masuk", "Uang masuk perlu dicatat & dialokasikan",
        "Catat kwitansi AR lalu alokasikan ke invoice — inilah wewenang inti Anda.",
        [_row(ref_type="customer", ref_id=r["customer_id"], number=r["order_number"],
              title=r.get("customer_name", "—"),
              subtitle=("lewat " + str(r["days_late"]) + " hari" if r.get("overdue")
                        else "belum jatuh tempo"),
              value=r.get("outstanding") or 0,
              age_days=max(0, int(r.get("days_late") or 0)),
              badge="lewat" if r.get("overdue") else "segera",
              action="Catat kwitansi", action_kind="receipt",
              extra={"order_id": r["order_id"]}) for r in tagih],
        action_label="Catat kwitansi", owner="finance"))

    # 3 — selisih bayar (lebih/kurang bayar) dalam batas kewenangan Finance
    from services import payment_variance_service as pvs
    ent_scope: Any = scope.get("entity_id") if isinstance(scope, dict) else ""
    selisih = await pvs.pending(ent_scope or "")
    queues.append(_queue(
        "selisih_bayar", "Selisih bayar perlu diputuskan",
        "Lebih/kurang bayar yang belum diputus. Di luar batas kewenangan → manajer.",
        [_row(ref_type="ar_receipt", ref_id=r.get("id", ""), number=r.get("number", "—"),
              title=r.get("customer_name", "—"),
              subtitle=str((r.get("variance") or {}).get("kind_label")
                           or (r.get("variance") or {}).get("kind") or "selisih"),
              value=abs(float((r.get("variance") or {}).get("amount") or 0)),
              age_days=_age_days(r.get("created_at")), badge="perlu keputusan",
              action="Putuskan", action_kind="decide_variance")
         for r in map(safe_doc, selisih)],
        action_label="Putuskan", owner="finance"))

    # 4 — denda perlu diterbitkan (draf hasil hitungan sistem)
    denda = await db.penalties.find(
        _q(scope, {"status": "draft"}),
        {"_id": 0, "id": 1, "number": 1, "customer_name": 1, "amount": 1, "created_at": 1,
         "doc_number": 1, "days_late": 1}
    ).sort("created_at", 1).to_list(200)
    queues.append(_queue(
        "denda_draft", "Denda perlu diterbitkan",
        "Nota denda hasil hitungan sistem — Anda yang menerbitkan; pembebasan → manajer.",
        [_row(ref_type="penalty", ref_id=d["id"], number=d.get("number", "—"),
              title=d.get("customer_name", "—"),
              subtitle=f"atas {d.get('doc_number') or '—'}",
              value=d.get("amount") or 0, age_days=_age_days(d.get("created_at")),
              badge="draf", action="Terbitkan", action_kind="issue_penalty")
         for d in map(safe_doc, denda)],
        action_label="Terbitkan", owner="finance"))

    lewat = [r for r in tagih if r.get("overdue")]
    queues.append(_queue(
        "jatuh_tempo", "Jatuh tempo (sudah lewat)",
        "Tagihan yang sudah melewati tanggal jatuh tempo.",
        [_row(ref_type="sales_order", ref_id=r["order_id"], number=r["order_number"],
              title=r.get("customer_name", "—"),
              subtitle=f"lewat {r['days_late']} hari · sales {r.get('sales_name') or '—'}",
              value=r.get("outstanding") or 0, age_days=int(r.get("days_late") or 0),
              badge="lewat", action="Tagih", action_kind="open") for r in lewat],
        action_label="Tagih", owner="finance"))

    return {"desk": "finance", "desk_label": "Meja Finance",
            "generated_at": now_iso(), "entity_ids": entity_ids,
            "queues": queues,
            "totals": {"open_items": sum(q["count"] for q in queues)},
            "not_my_desk": ["Membuat / mengonfirmasi pesanan",
                            "Keputusan pemenuhan (ambil dari PT lain · reorder)",
                            "Sisi hutang: tagihan supplier · kontrabon · landed cost"]}
