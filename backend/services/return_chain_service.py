"""FASE E-9 (E9.6) — **JEJAK RANTAI RETUR**.

Satu pertanyaan pemilik yang dulu tidak bisa dijawab layar mana pun:

    "Kain yang diretur Customer A itu akhirnya ke mana?"

Rantainya bisa tiga tingkat:

    Retur PELANGGAN  (Customer A → Entitas A)
        └─ Retur ANTAR-PT  (Entitas A → Entitas B)   ← dokumen kembar, harga internal
              ├─ Retur BELI  (Entitas B → supplier)  ← bila supplier menerima retur
              └─ atau **disimpan** Entitas B         ← barang jadi stok B (regrade/jual lokal)

Mesin relasi dokumen (FASE G-4 `doc_refs_service`) sudah ada dan dipakai 79 tautan di
data demo, tetapi rantai retur **belum pernah dipasang** ke sana. Modul ini menyusun
rantainya dari tautan + field asal (`source_sales_return_id`, `origin_interco_return_id`)
dan menutupnya dengan keadaan FISIK barangnya sekarang (roll retur milik siapa,
statusnya apa) — supaya jawabannya bukan "ada dokumennya" melainkan "kainnya di mana".

Read-only: modul ini tidak pernah menulis apa pun.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from core_utils import safe_doc
from db import db
from services import movement_label_service as _mlabel

STAGE_LABEL = {
    "sales_return": "Retur Pelanggan",
    "interco_return": "Retur Antar-PT",
    "purchase_return": "Retur ke Supplier",
    "kept": "Disimpan Sendiri",
}


class ChainForbidden(Exception):
    """Rantai ini tidak menyentuh badan usaha mana pun dalam cakupan pembaca."""


async def _entity_names(ids: List[str], viewer: Optional[Set[str]] = None,
                        cross_entity: bool = False) -> Dict[str, str]:
    """Nama badan usaha untuk ditampilkan.

    Aturan E5.3 dipakai apa adanya: badan usaha **milik sendiri** (atau pembaca
    lintas-entitas) boleh disebut dengan nama badan hukumnya; badan usaha **lawan**
    hanya boleh muncul sebagai NAMA SINGKAT ("Kanda"), bukan nama badan hukum dan
    tentu bukan id teknis `ent_*`.
    """
    ids = [i for i in {x for x in ids if x}]
    if not ids:
        return {}
    rows = await _mlabel._entity_short_names(set(ids))  # noqa: SLF001 — satu sumber nama
    out: Dict[str, str] = {}
    for eid in ids:
        row = rows.get(eid, {})
        short = row.get("short") or _mlabel.UNKNOWN_ENTITY_LABEL
        legal = row.get("legal") or short
        own = cross_entity or (viewer is not None and eid in viewer)
        out[eid] = legal if own else short
    return out


async def _resolve_root(doc_id: str) -> Dict[str, Any]:
    """Terima id retur mana pun (pelanggan / antar-PT / beli) → retur PELANGGAN akarnya."""
    sr = await db.sales_returns.find_one({"id": doc_id}, {"_id": 0})
    if sr:
        return sr
    icr = await db.interco_returns.find_one({"id": doc_id}, {"_id": 0})
    if icr:
        sid = (icr.get("source_sales_return_id") or "").strip()
        if sid:
            sr = await db.sales_returns.find_one({"id": sid}, {"_id": 0})
            if sr:
                return sr
        return {"__interco_only__": icr}
    pret = await db.purchase_returns.find_one({"id": doc_id}, {"_id": 0})
    if pret:
        sid = (pret.get("origin_sales_return_id") or "").strip()
        if sid:
            sr = await db.sales_returns.find_one({"id": sid}, {"_id": 0})
            if sr:
                return sr
        icr_id = (pret.get("origin_interco_return_id") or "").strip()
        if icr_id:
            return await _resolve_root(icr_id)
        return {"__purchase_only__": pret}
    return {}


async def chain(doc_id: str, viewer_entity_ids: Optional[List[str]] = None,
                cross_entity: bool = False) -> Dict[str, Any]:
    """Rantai retur lengkap + keadaan fisik barangnya sekarang.

    `viewer_entity_ids` = badan usaha dalam cakupan pembaca (None → tanpa redaksi,
    hanya untuk pemanggil internal). Langkah & roll milik badan usaha DI LUAR
    cakupan itu diringkas: yang tampil hanya tahap, nomor dokumen, status, dan
    NAMA SINGKAT pemiliknya — bukan lawan dagangnya, nilainya, lot, atau PO-nya.
    Rantai yang sama sekali tidak menyentuh cakupan pembaca → `ChainForbidden`.
    """
    viewer: Optional[Set[str]] = ({v for v in viewer_entity_ids if v}
                                  if viewer_entity_ids is not None else None)
    root = await _resolve_root(doc_id)
    if not root:
        return {"found": False, "requested_id": doc_id, "steps": [],
                "note": "Dokumen retur tidak ditemukan."}

    # Kasus tepi: retur antar-PT / retur beli yang TIDAK lahir dari retur pelanggan
    # (mis. barang yang salah kirim). Rantainya tetap ditampilkan apa adanya.
    if root.get("__interco_only__") or root.get("__purchase_only__"):
        doc = root.get("__interco_only__") or root.get("__purchase_only__")
        kind = "interco_return" if root.get("__interco_only__") else "purchase_return"
        own_ids = [doc.get("entity_id", ""), doc.get("buyer_entity_id", ""),
                   doc.get("seller_entity_id", "")]
        own_ids = [i for i in own_ids if i]
        if viewer is not None and not cross_entity and own_ids and not (set(own_ids) & viewer):
            raise ChainForbidden(
                "Retur ini tidak menyentuh badan usaha yang sedang Anda akses.")
        return {"found": True, "requested_id": doc_id, "root_type": kind,
                "sales_return": None,
                "steps": [{
                    "stage": kind, "stage_label": STAGE_LABEL[kind],
                    "doc_type": kind, "doc_id": doc.get("id", ""),
                    "number": doc.get("number", ""), "status": doc.get("status", ""),
                    "date": doc.get("doc_date") or doc.get("created_at", ""),
                    "amount": float(doc.get("grand_total") or doc.get("total_amount") or 0),
                    "note": "Tidak berasal dari retur pelanggan.",
                }],
                "complete": False,
                "summary": "Retur ini tidak berasal dari retur pelanggan, jadi rantainya berdiri sendiri."}

    sr_id = root["id"]
    steps: List[Dict[str, Any]] = []

    # ── 1. Retur PELANGGAN ────────────────────────────────────────────────────
    ent_ids = [root.get("entity_id", "")]
    icrs = await db.interco_returns.find(
        {"source_sales_return_id": sr_id, "role": "returner"}, {"_id": 0}
    ).sort("created_at", 1).to_list(50)
    icr_pairs = [r.get("return_pair_id") for r in icrs if r.get("return_pair_id")]
    receivers = await db.interco_returns.find(
        {"return_pair_id": {"$in": icr_pairs}, "role": "receiver"}, {"_id": 0}
    ).to_list(50) if icr_pairs else []
    recv_by_pair = {r["return_pair_id"]: r for r in receivers}
    for r in icrs:
        ent_ids += [r.get("buyer_entity_id", ""), r.get("seller_entity_id", "")]

    prets = await db.purchase_returns.find(
        {"$or": [{"origin_sales_return_id": sr_id},
                 {"origin_interco_return_id": {"$in": [r["id"] for r in receivers]}}]},
        {"_id": 0}).sort("created_at", 1).to_list(50) if (receivers or sr_id) else []
    ent_ids += [p.get("entity_id", "") for p in prets]

    # ── Keadaan FISIK barangnya sekarang ──────────────────────────────────────
    rolls = await db.inventory_rolls.find(
        {"return_id": sr_id},
        {"_id": 0, "id": 1, "roll_no": 1, "lot": 1, "grade": 1,
         "status": 1, "owner_entity_id": 1, "length_remaining": 1, "unit": 1,
         "warehouse_id": 1, "supplier_id": 1, "supplier_name": 1, "po_number": 1,
         "origin_interco_number": 1}).to_list(2000)
    ent_ids += [r.get("owner_entity_id", "") for r in rolls]
    names = await _entity_names(ent_ids, viewer, cross_entity)

    steps.append({
        "stage": "sales_return", "stage_label": STAGE_LABEL["sales_return"],
        "doc_type": "sales_return", "doc_id": sr_id,
        "number": root.get("number", ""), "status": root.get("status", ""),
        "date": root.get("return_date") or root.get("created_at", ""),
        "amount": float(root.get("total_amount") or 0),
        "entity_id": root.get("entity_id", ""),
        "entity_name": names.get(root.get("entity_id", ""), ""),
        "party": root.get("customer_name", ""),
        "order_number": root.get("order_number", ""),
        "note": (f"{len(rolls)} roll masuk karantina" if rolls
                 else "Belum ada roll retur (barang belum masuk / belum diinspeksi)"),
    })

    # ── 2. Retur ANTAR-PT ─────────────────────────────────────────────────────
    for r in icrs:
        rc = recv_by_pair.get(r.get("return_pair_id"), {})
        steps.append({
            "stage": "interco_return", "stage_label": STAGE_LABEL["interco_return"],
            "doc_type": "interco_return", "doc_id": r["id"],
            "number": r.get("number", ""), "status": r.get("status", ""),
            "date": r.get("doc_date") or r.get("created_at", ""),
            "amount": float(r.get("grand_total") or 0),
            "entity_id": r.get("buyer_entity_id", ""),
            "entity_name": names.get(r.get("buyer_entity_id", ""), ""),
            "party": names.get(r.get("seller_entity_id", ""), ""),
            "counterpart_number": rc.get("number", r.get("counterpart_number", "")),
            "counterpart_doc_id": rc.get("id", ""),
            "warehouse_transfer_code": r.get("warehouse_transfer_code", ""),
            "warehouse_transfer_status": r.get("warehouse_transfer_status", ""),
            "origin_number": r.get("origin_number", ""),
            "note": (f"Barang dikembalikan ke {names.get(r.get('seller_entity_id',''), 'PT penjual')}"
                     f" atas {r.get('origin_number','')}"),
        })

    # ── 3. Retur BELI (atau disimpan) ─────────────────────────────────────────
    for p in prets:
        steps.append({
            "stage": "purchase_return", "stage_label": STAGE_LABEL["purchase_return"],
            "doc_type": "purchase_return", "doc_id": p["id"],
            "number": p.get("number", ""), "status": p.get("status", ""),
            "supplier_status": p.get("supplier_status", ""),
            "date": p.get("created_at", ""),
            "amount": float(p.get("total_amount") or 0),
            "entity_id": p.get("entity_id", ""),
            "entity_name": names.get(p.get("entity_id", ""), ""),
            "party": p.get("supplier_name", ""),
            "po_number": p.get("po_number", ""),
            "origin_type": p.get("origin_type", ""),
            "note": (f"Diteruskan ke supplier {p.get('supplier_name','')}"
                     + (f" (PO {p.get('po_number')})" if p.get("po_number") else "")),
        })

    held: Dict[str, Dict[str, Any]] = {}
    for r in rolls:
        if r.get("status") in ("consumed", "damaged"):
            continue
        own = r.get("owner_entity_id", "")
        row = held.setdefault(own, {"qty": 0.0, "rolls": 0, "unit": r.get("unit", "")})
        row["qty"] = round(row["qty"] + float(r.get("length_remaining") or 0), 2)
        row["rolls"] += 1
    for own, row in held.items():
        if row["qty"] <= 0.01:
            continue
        steps.append({
            "stage": "kept", "stage_label": STAGE_LABEL["kept"],
            "doc_type": "", "doc_id": "", "number": "",
            "status": "held", "entity_id": own, "entity_name": names.get(own, own),
            "amount": 0.0,
            "note": (f"{row['qty']:g} {row['unit']} ({row['rolls']} roll) masih dipegang "
                     f"{names.get(own, own)} — bisa di-regrade & dijual lokal."),
        })

    complete = bool(icrs) and (bool(prets) or any(s["stage"] == "kept" for s in steps))
    out_rolls = [{
        "roll_id": r.get("id"), "roll_no": r.get("roll_no", ""),
        "lot": r.get("lot", ""), "grade": r.get("grade", ""),
        "status": r.get("status", ""),
        "qty": round(float(r.get("length_remaining") or 0), 2), "unit": r.get("unit", ""),
        "owner_entity_id": r.get("owner_entity_id", ""),
        "owner_entity_name": names.get(r.get("owner_entity_id", ""), ""),
        "supplier_name": r.get("supplier_name", ""),
        "po_number": r.get("po_number", ""),
        "origin_interco_number": r.get("origin_interco_number", ""),
    } for r in rolls]

    _guard_and_redact(steps, out_rolls, viewer, cross_entity)

    sr_block = safe_doc({k: root.get(k) for k in
                         ("id", "number", "status", "customer_name",
                          "order_number", "entity_id", "total_amount")})
    if _foreign(root.get("entity_id", ""), viewer, cross_entity):
        # Pembaca bukan bagian badan usaha penerbit retur pelanggan → nama pelanggan
        # dan nilainya bukan urusannya; nomor & statusnya cukup untuk memahami rantai.
        sr_block = {"id": sr_block.get("id"), "number": sr_block.get("number"),
                    "status": sr_block.get("status"), "redacted": True}
    return {
        "found": True, "requested_id": doc_id, "root_type": "sales_return",
        "sales_return": sr_block,
        "steps": steps,
        "rolls": out_rolls,
        "complete": complete,
        "summary": _summary(steps),
    }


def _foreign(entity_id: str, viewer: Optional[Set[str]], cross_entity: bool) -> bool:
    """Milik badan usaha DI LUAR cakupan pembaca?"""
    if cross_entity or viewer is None or not entity_id:
        return False
    return entity_id not in viewer


def _guard_and_redact(steps: List[Dict[str, Any]], out_rolls: List[Dict[str, Any]],
                      viewer: Optional[Set[str]], cross_entity: bool) -> None:
    """Pagar + redaksi rantai (E5.3) — dijalankan di tempat.

    Rantai retur memang melintasi badan usaha; itu justru gunanya. Yang tidak boleh
    adalah rincian badan usaha lain ikut terbaca: nama lawan dagangnya (supplier /
    pelanggan), nilai rupiahnya, nomor lot, nomor PO, dan **id teknis** `ent_*`.
    Yang tetap tampil: tahap, nomor dokumen, status, jumlah barang, dan NAMA
    SINGKAT badan usaha pemiliknya — cukup untuk menjawab "kainnya ke mana".
    """
    if viewer is None or cross_entity:
        return
    touched = {s.get("entity_id") for s in steps if s.get("entity_id")}
    touched |= {r.get("owner_entity_id") for r in out_rolls if r.get("owner_entity_id")}
    if touched and not (touched & viewer):
        raise ChainForbidden(
            "Rantai retur ini tidak menyentuh badan usaha yang sedang Anda akses.")
    for s in steps:
        if not _foreign(s.get("entity_id", ""), viewer, cross_entity):
            continue
        name = s.get("entity_name") or "badan usaha lain"
        s.pop("entity_id", None)
        for fld in ("party", "po_number", "supplier_status", "order_number",
                    "origin_number", "counterpart_doc_id"):
            s.pop(fld, None)
        s["amount"] = None
        s["redacted"] = True
        s["note"] = f"Dokumen milik {name} — rinciannya tidak ditampilkan di sini."
    for r in out_rolls:
        if not _foreign(r.get("owner_entity_id", ""), viewer, cross_entity):
            continue
        r.pop("owner_entity_id", None)
        for fld in ("lot", "supplier_name", "po_number", "origin_interco_number",
                    "roll_no"):
            r[fld] = ""
        r["redacted"] = True


def _summary(steps: List[Dict[str, Any]]) -> str:
    parts = []
    for s in steps:
        if s["stage"] == "kept":
            parts.append(f"disimpan {s.get('entity_name','')}")
        else:
            parts.append(f"{s['stage_label']} {s.get('number','')}".strip())
    return " → ".join(parts) if parts else "Belum ada jejak."
