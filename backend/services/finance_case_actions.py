"""FASE G-9 — EKSEKUTOR AKSI PLAYBOOK KASUS KEUANGAN.

Di sini uang benar-benar berpindah. Setiap fungsi `act_*`:
* memakai **service yang sudah ada** (rekonsiliasi bank G-8, kwitansi AR, store credit,
  denda G-2, buku besar) — tidak menulis ulang mekanika uang;
* mengembalikan daftar **dokumen turunan** (`documents[]`) yang benar-benar lahir,
  supaya `INV-CASE-01` bisa membuktikan kasus `resolved` tidak kosong;
* tidak pernah mengubah dokumen finansial lama (ledger tambah-saja) — koreksi selalu
  lewat jurnal/baris baru.

Bentuk dokumen turunan: `{"kind","id","number","label"}`.
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from core_utils import new_id, now_iso, safe_doc, rupiah
from db import db
from services import gl_service as gl

EPS = 0.01


class CaseActionError(ValueError):
    """Kesalahan aksi kasus dengan pesan siap tampil (Bahasa Indonesia)."""


def _rp(v: Any) -> str:
    """Alias tipis ke `core_utils.rupiah` — satu sumber format uang untuk seluruh backend."""
    return rupiah(v)


def _doc(kind: str, doc_id: str, number: str, label: str) -> Dict[str, Any]:
    return {"kind": kind, "id": doc_id or "", "number": number or "", "label": label}


def _je_doc(je: Optional[Dict[str, Any]], label: str) -> List[Dict[str, Any]]:
    if not je:
        return []
    return [_doc("journal_entry", je.get("id", ""), je.get("number", je.get("id", "")), label)]


async def _next_cash_number(entity_id: str = "") -> str:
    """FASE E-1 (E1.7) — nomor kas PER BADAN USAHA.

    Kas “all” (tingkat grup) sengaja tetap memakai deret bersama; itu satu-satunya
    kas yang memang bukan milik satu badan usaha (lihat FASE E-7).
    """
    from core_utils import next_doc_number
    return await next_doc_number("cash_transactions", "number", "CASH-",
                                 entity_id=(entity_id or None))


async def _cash_txn(*, direction: str, amount: float, category: str, description: str,
                    entity_id: str, account_id: str = "", cash_type: str = "kas_besar",
                    ref_type: str = "", ref_id: str = "", contra: str = "",
                    owner_entity_id: str = "", actor: str = "system") -> Dict[str, Any]:
    """Catat mutasi kas NYATA + jurnalnya (idempotent di sisi jurnal).

    Memakai koleksi & bentuk dokumen yang sama dengan layar Transaksi Kas supaya saldo
    rekening di layar Kas & Bank ikut bergerak — bukan angka bayangan milik modul kasus.
    """
    amount = round(float(amount or 0), 2)
    if amount <= EPS:
        raise CaseActionError("Nominal harus lebih dari 0")
    # FASE E-7 (E7.4) — kas grup dihapus: uang kasus keuangan tetap milik badan usaha
    # kasusnya. `kas_besar` di sini hanya berarti "lewat bank", bukan "milik grup".
    from services.cash_entity_service import resolve_owner
    cash_owner = resolve_owner(entity_id, owner_entity_id, what="Kas kasus keuangan")
    doc = {
        "id": new_id("cash"), "number": await _next_cash_number(entity_id),
        "cash_type": cash_type if cash_type in ("kas_besar", "kas_kecil") else "kas_besar",
        "direction": direction, "amount": amount, "category": category,
        "description": description,
        "entity_id": cash_owner,
        "ref_type": ref_type, "ref_id": ref_id, "txn_date": now_iso(),
        "account_id": account_id or "", "reconciled": False, "status": "posted",
        "created_by": actor, "created_at": now_iso(), "updated_at": now_iso(),
    }
    if contra:
        doc["contra_account_code"] = contra
    if owner_entity_id:
        doc["owner_entity_id"] = owner_entity_id
    await db.cash_transactions.insert_one(dict(doc))
    je = await gl.post_cash_transaction(doc)
    out = [_doc("cash_transaction", doc["id"], doc["number"],
                f"Kas {'masuk' if direction == 'in' else 'keluar'} {_rp(amount)}")]
    out += _je_doc(je, f"Jurnal kas {doc['number']}")
    return {"txn": safe_doc(doc), "documents": out}


async def _order_or_fail(order_id: str) -> Dict[str, Any]:
    o = await db.sales_orders.find_one({"id": order_id}, {"_id": 0})
    if not o:
        raise CaseActionError(f"Pesanan {order_id} tidak ditemukan")
    return o


async def _apply_payment(order_id: str, amount: float, case: Dict[str, Any],
                         method: str) -> List[Dict[str, Any]]:
    """Tempelkan pelunasan ke pesanan (piutang berkurang) TANPA kas baru."""
    from services import ar_receipt_service as ar
    res = await ar.apply_from_case(order_id, amount, case["id"], case["number"], method)
    try:
        from services import payment_plan_service as plans
        await plans.recompute_for_doc("sales_order", order_id)
    except Exception:  # noqa: BLE001 — jadwal bayar bersifat pelengkap
        pass
    return [_doc("order_payment", order_id, res.get("order_number", order_id),
                 f"Pelunasan {_rp(amount)} menempel di pesanan "
                 f"{res.get('order_number', order_id)}")]


# ═════════════════════════════════════════════════════════════════════════════
#  AKSI PER PLAYBOOK
# ═════════════════════════════════════════════════════════════════════════════
async def act_alokasi_titipan(case: Dict[str, Any], p: Dict[str, Any],
                              actor: Dict[str, Any]) -> Dict[str, Any]:
    """Titipan dana G-8 → melunasi pesanan pelanggan (Dr 2-1950 / Cr 1-1200)."""
    from services import bank_recon_service as bank
    line_id = (case.get("source") or {}).get("id") or ""
    if not line_id:
        raise CaseActionError(
            "Kasus ini belum menunjuk baris titipan dana. Buka kasus dari layar "
            "Rekonsiliasi Bank → Dana Titipan supaya sumber dananya jelas.")
    allocs = [{"order_id": a["order_id"], "amount": float(a["amount"])}
              for a in (p.get("allocations") or [])]
    if not allocs:
        raise CaseActionError("Pilih pesanan yang dilunasi beserta nominalnya")
    res = await bank.allocate_holding(
        line_id, allocs, p.get("customer_id") or case.get("customer_id") or "",
        p.get("reason_code") or "", p.get("note") or f"Kasus {case['number']}",
        actor.get("name", ""), None)
    # `allocate_holding` mengembalikan BARIS titipan setelah dialokasikan; alokasi yang
    # baru saja terjadi adalah N entri terakhir `holding_allocated[]` (append-only).
    done = (res.get("holding_allocated") or [])[-len(allocs):]
    docs: List[Dict[str, Any]] = []
    for a in done:
        if a.get("je_id"):
            docs.append(_doc("journal_entry", a["je_id"], a.get("je_number", ""),
                             "Jurnal Dr 2-1950 Titipan Dana / Cr 1-1200 Piutang"))
        docs.append(_doc("order_payment", a.get("order_id", ""), a.get("order_number", ""),
                         f"Pelunasan {_rp(a.get('amount'))} di pesanan "
                         f"{a.get('order_number', '')}"))
    if not any(d["kind"] == "journal_entry" for d in docs):
        raise CaseActionError(
            "Alokasi titipan tidak menghasilkan jurnal — kasus tidak ditutup supaya "
            "uangnya tidak hilang dari laporan. Periksa buku besar lalu coba lagi.")
    return {"documents": docs, "amount": round(sum(a["amount"] for a in allocs), 2)}


async def act_refund_titipan(case: Dict[str, Any], p: Dict[str, Any],
                             actor: Dict[str, Any]) -> Dict[str, Any]:
    """Dana tak dikenal dikembalikan ke pengirim (Dr 2-1950 / Cr Kas-Bank)."""
    from services import bank_recon_service as bank
    line_id = (case.get("source") or {}).get("id") or ""
    amount = round(float(p.get("amount") or 0), 2)
    ln = await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0}) if line_id else None
    if not ln or ln.get("status") != "holding":
        raise CaseActionError("Sumber kasus bukan titipan dana yang masih aktif")
    remaining = round(float(ln.get("holding_remaining", ln.get("amount")) or 0), 2)
    if amount > remaining + EPS:
        raise CaseActionError(
            f"Pengembalian {_rp(amount)} melebihi sisa titipan {_rp(remaining)}")
    res = await _cash_txn(
        direction="out", amount=amount, category="titipan",
        description=f"Pengembalian dana tak dikenal · {case['number']}",
        entity_id=case.get("entity_id", ""), account_id=ln.get("bank_account_id", ""),
        cash_type="kas_besar", ref_type="finance_case", ref_id=case["id"],
        contra=gl.ACC_TITIPAN_DANA, owner_entity_id=case.get("entity_id", ""),
        actor=actor.get("name", "system"))
    # Titipan berkurang: baris ditutup lewat service G-8 supaya INV-BNK-03 tetap sah.
    await bank.holding_refunded(line_id, amount, case["number"], actor.get("name", ""))
    return {"documents": res["documents"], "amount": amount}


async def act_alokasi_uang_muka(case: Dict[str, Any], p: Dict[str, Any],
                                actor: Dict[str, Any]) -> Dict[str, Any]:
    """Kelebihan bayar (uang muka pelanggan) dipakai melunasi pesanan lain."""
    from services import ar_receipt_service as ar
    cust = p.get("customer_id") or case.get("customer_id") or ""
    allocs = p.get("allocations") or []
    total = round(sum(float(a["amount"]) for a in allocs), 2)
    if total <= EPS:
        raise CaseActionError("Pilih pesanan yang dilunasi beserta nominalnya")
    dep = await ar.get_deposit_balance(cust)
    if total > dep + EPS:
        raise CaseActionError(
            f"Alokasi {_rp(total)} melebihi saldo uang muka pelanggan {_rp(dep)}")
    docs: List[Dict[str, Any]] = []
    for a in allocs:
        docs += await _apply_payment(a["order_id"], float(a["amount"]), case, "deposit")
    await ar.adjust_deposit(cust, -total)
    je = await gl.post_finance_case(
        case_id=case["id"], entity_id=case.get("entity_id", ""), amount=total,
        debit_acc=gl.ACC_UANG_MUKA_PELANGGAN, credit_acc=gl.ACC_PIUTANG,
        label=f"{case['number']} · uang muka dipakai melunasi pesanan", suffix="alloc",
        created_by=actor.get("name", "system"))
    docs += _je_doc(je, "Jurnal Dr 2-1400 Uang Muka Pelanggan / Cr 1-1200 Piutang")
    return {"documents": docs, "amount": total}


async def act_refund_pelanggan(case: Dict[str, Any], p: Dict[str, Any],
                               actor: Dict[str, Any]) -> Dict[str, Any]:
    """Uang muka pelanggan dikembalikan (Dr 2-1400 / Cr Kas-Bank)."""
    from services import ar_receipt_service as ar
    cust = p.get("customer_id") or case.get("customer_id") or ""
    amount = round(float(p.get("amount") or 0), 2)
    dep = await ar.get_deposit_balance(cust)
    if amount > dep + EPS:
        raise CaseActionError(
            f"Pengembalian {_rp(amount)} melebihi saldo uang muka pelanggan {_rp(dep)}")
    res = await _cash_txn(
        direction="out", amount=amount, category="refund pelanggan",
        description=f"Pengembalian dana pelanggan · {case['number']}",
        entity_id=case.get("entity_id", ""), account_id=p.get("account_id", ""),
        cash_type=p.get("cash_type") or "kas_besar", ref_type="ar_refund",
        ref_id=case["id"], owner_entity_id=case.get("entity_id", ""),
        actor=actor.get("name", "system"))
    await ar.adjust_deposit(cust, -amount)
    return {"documents": res["documents"], "amount": amount}


async def act_refund_store_credit(case: Dict[str, Any], p: Dict[str, Any],
                                  actor: Dict[str, Any]) -> Dict[str, Any]:
    """Saldo kredit toko dicairkan menjadi uang (Dr 2-1450 / Cr Kas-Bank)."""
    from services import store_credit_service as sc
    cust = p.get("customer_id") or case.get("customer_id") or ""
    amount = round(float(p.get("amount") or 0), 2)
    ent = case.get("entity_id") or ""
    bal = await sc.balance(cust, ent)
    if amount > bal + EPS:
        raise CaseActionError(
            f"Pengembalian {_rp(amount)} melebihi saldo kredit toko {_rp(bal)}")
    entry = await sc.adjust(customer_id=cust, entity_id=ent, amount_signed=-amount,
                            note=f"Dicairkan lewat kasus {case['number']}", actor=actor)
    res = await _cash_txn(
        direction="out", amount=amount, category="refund store credit",
        description=f"Pencairan saldo kredit toko · {case['number']}",
        entity_id=ent, account_id=p.get("account_id", ""),
        cash_type=p.get("cash_type") or "kas_besar", ref_type="finance_case",
        ref_id=case["id"], contra=gl.ACC_STORE_CREDIT, owner_entity_id=ent,
        actor=actor.get("name", "system"))
    docs = res["documents"] + [
        _doc("store_credit_entry", (entry or {}).get("id", ""), "",
             f"Baris buku saldo kredit −{_rp(amount)}")]
    return {"documents": docs, "amount": amount}


async def act_pindah_buku(case: Dict[str, Any], p: Dict[str, Any],
                          actor: Dict[str, Any]) -> Dict[str, Any]:
    """Pindah-buku antar rekening sendiri lewat akun transit (akun transit kembali nol)."""
    amount = round(float(p.get("amount") or 0), 2)
    to_acc = p.get("to_account_id") or ""
    src = (case.get("source") or {})
    from_acc = p.get("account_id") or ""
    if not from_acc and src.get("kind") in ("bank_holding", "bank_line") and src.get("id"):
        ln = await db.bank_statement_lines.find_one({"id": src["id"]}, {"_id": 0})
        from_acc = (ln or {}).get("bank_account_id", "")
    if not (from_acc and to_acc):
        raise CaseActionError("Rekening asal dan rekening tujuan wajib dipilih")
    if from_acc == to_acc:
        raise CaseActionError("Rekening asal dan tujuan tidak boleh sama")
    names = {}
    for aid in (from_acc, to_acc):
        acc = await db.bank_accounts.find_one({"id": aid}, {"_id": 0})
        if not acc:
            raise CaseActionError(f"Rekening {aid} tidak ditemukan")
        names[aid] = acc.get("name") or acc.get("bank_name") or aid
    ent = case.get("entity_id", "")
    out = await _cash_txn(
        direction="out", amount=amount, category="pindah buku",
        description=f"Pindah-buku ke {names[to_acc]} · {case['number']}",
        entity_id=ent, account_id=from_acc, ref_type="finance_case", ref_id=case["id"],
        contra=gl.ACC_KAS_TRANSIT, owner_entity_id=ent, actor=actor.get("name", "system"))
    inn = await _cash_txn(
        direction="in", amount=amount, category="pindah buku",
        description=f"Pindah-buku dari {names[from_acc]} · {case['number']}",
        entity_id=ent, account_id=to_acc, ref_type="finance_case", ref_id=case["id"],
        contra=gl.ACC_KAS_TRANSIT, owner_entity_id=ent, actor=actor.get("name", "system"))
    return {"documents": out["documents"] + inn["documents"], "amount": amount,
            "extra": {"from_account_id": from_acc, "to_account_id": to_acc,
                      "from_account": names[from_acc], "to_account": names[to_acc]}}


async def act_akui_dipegang_karyawan(case: Dict[str, Any], p: Dict[str, Any],
                                     actor: Dict[str, Any]) -> Dict[str, Any]:
    """Langkah 1: piutang pelanggan lunas → berpindah jadi piutang karyawan."""
    amount = round(float(p.get("amount") or 0), 2)
    order_id = p.get("order_id") or (case.get("order_ids") or [""])[0]
    emp = (p.get("employee_name") or "").strip()
    if not emp:
        raise CaseActionError("Nama karyawan yang memegang uang wajib diisi")
    o = await _order_or_fail(order_id)
    docs = await _apply_payment(order_id, amount, case, "titipan_karyawan")
    je = await gl.post_finance_case(
        case_id=case["id"], entity_id=o.get("entity_id") or case.get("entity_id", ""),
        amount=amount, debit_acc=gl.ACC_PIUTANG_KARYAWAN, credit_acc=gl.ACC_PIUTANG,
        label=f"{case['number']} · uang dipegang {emp}", suffix="emp1",
        created_by=actor.get("name", "system"))
    docs += _je_doc(je, "Jurnal Dr 1-1280 Piutang Titipan Karyawan / Cr 1-1200 Piutang")
    return {"documents": docs, "amount": amount, "hold": True,
            "extra": {"employee_name": emp, "step": 1},
            "next_action": "setor_dari_karyawan"}


async def act_setor_dari_karyawan(case: Dict[str, Any], p: Dict[str, Any],
                                  actor: Dict[str, Any]) -> Dict[str, Any]:
    """Langkah 2: karyawan menyetor → piutang karyawan kembali nol."""
    amount = round(float(p.get("amount") or 0), 2)
    emp = (p.get("employee_name") or (case.get("resolution") or {})
           .get("extra", {}).get("employee_name") or "karyawan")
    res = await _cash_txn(
        direction="in", amount=amount, category="setoran karyawan",
        description=f"Setoran {emp} · {case['number']}",
        entity_id=case.get("entity_id", ""), account_id=p.get("account_id", ""),
        cash_type=p.get("cash_type") or "kas_besar", ref_type="finance_case",
        ref_id=case["id"], contra=gl.ACC_PIUTANG_KARYAWAN,
        owner_entity_id=case.get("entity_id", ""), actor=actor.get("name", "system"))
    return {"documents": res["documents"], "amount": amount,
            "extra": {"employee_name": emp, "step": 2}}


async def act_realokasi_pesanan(case: Dict[str, Any], p: Dict[str, Any],
                                actor: Dict[str, Any]) -> Dict[str, Any]:
    """Alokasi pembayaran berpindah antar pesanan (ledger tambah-saja, tanpa void)."""
    from services import ar_receipt_service as ar
    amount = round(float(p.get("amount") or 0), 2)
    src_id, dst_id = p.get("from_order_id") or "", p.get("to_order_id") or ""
    if not (src_id and dst_id) or src_id == dst_id:
        raise CaseActionError("Pesanan asal dan pesanan tujuan wajib berbeda dan terisi")
    src, dst = await _order_or_fail(src_id), await _order_or_fail(dst_id)
    if src.get("customer_id") != dst.get("customer_id"):
        raise CaseActionError(
            "Realokasi hanya boleh antar pesanan pelanggan yang SAMA. Untuk pelanggan "
            "berbeda, kembalikan dananya lalu terima pembayaran baru.")
    if (src.get("entity_id") or "") != (dst.get("entity_id") or ""):
        raise CaseActionError(
            "Realokasi hanya boleh antar pesanan pada PT yang sama — perpindahan uang "
            "antar PT memakai playbook 'Pelanggan bayar ke PT yang salah'.")
    pulled = await ar.unapply_for_case(src_id, amount, case["id"], case["number"])
    docs = [_doc("order_payment", src_id, pulled.get("order_number", src_id),
                 f"Pengurang alokasi −{_rp(amount)} di pesanan "
                 f"{pulled.get('order_number', '')}")]
    docs += await _apply_payment(dst_id, amount, case, "realokasi")
    return {"documents": docs, "amount": amount,
            "extra": {"from_order": src.get("number"), "to_order": dst.get("number")}}


async def act_bank_charge(case: Dict[str, Any], p: Dict[str, Any],
                          actor: Dict[str, Any]) -> Dict[str, Any]:
    """Selisih kecil karena biaya bank → Dr 6-8000 / Cr 1-1200 + pesanan ditutup."""
    amount = round(float(p.get("amount") or 0), 2)
    order_id = p.get("order_id") or (case.get("order_ids") or [""])[0]
    o = await _order_or_fail(order_id)
    docs = await _apply_payment(order_id, amount, case, "bank_charge")
    je = await gl.post_finance_case(
        case_id=case["id"], entity_id=o.get("entity_id") or case.get("entity_id", ""),
        amount=amount, debit_acc=gl.ACC_BEBAN_BANK, credit_acc=gl.ACC_PIUTANG,
        label=f"{case['number']} · selisih biaya bank {o.get('number', '')}",
        suffix="chg", created_by=actor.get("name", "system"))
    docs += _je_doc(je, "Jurnal Dr 6-8000 Beban Administrasi Bank / Cr 1-1200 Piutang")
    return {"documents": docs, "amount": amount}


async def act_batalkan_kwitansi(case: Dict[str, Any], p: Dict[str, Any],
                                actor: Dict[str, Any]) -> Dict[str, Any]:
    """Giro ditolak → kwitansi dibatalkan (jurnal pembalik) + nota denda opsional."""
    from services import ar_receipt_service as ar
    rid = p.get("receipt_id") or (case.get("source") or {}).get("id") or ""
    if not rid:
        raise CaseActionError("Kwitansi yang dibatalkan wajib ditunjuk")
    rec = await db.ar_receipts.find_one({"id": rid}, {"_id": 0})
    if not rec:
        raise CaseActionError("Kwitansi tidak ditemukan")
    if rec.get("status") == "void":
        raise CaseActionError("Kwitansi ini sudah dibatalkan sebelumnya")
    voided = await ar.void_receipt(rid, actor)
    docs = [_doc("ar_receipt", rid, rec.get("number", rid),
                 f"Kwitansi {rec.get('number', rid)} dibatalkan (jurnal pembalik)")]
    # Jurnal PEMBALIK-nya diposting `void_receipt` lewat `gl.post_cash_void` (append-only:
    # jurnal asli tidak diubah). Kita ambil jurnal itu agar ikut tercatat sebagai dokumen
    # turunan kasus — tanpa ini INV-CASE-03 benar menolak menutup kasus karena tampak
    # "memindahkan uang tanpa jurnal".
    for cid in [c.get("id") for c in (rec.get("cash_transactions") or [])] + \
               [rec.get("cash_txn_id", "")]:
        if not cid:
            continue
        rev = await db.journal_entries.find_one(
            {"source_type": "cash_transaction_void", "source_id": cid}, {"_id": 0})
        if rev:
            docs += _je_doc(rev, f"Jurnal pembalik kas {rev.get('number', '')}")
    if not any(d["kind"] == "journal_entry" for d in docs):
        rev = await db.journal_entries.find_one(
            {"source_type": "cash_transaction_void",
             "source_id": {"$in": [t.get("id") for t in await db.cash_transactions.find(
                 {"ref_type": "ar_receipt", "ref_id": rid}, {"_id": 0, "id": 1}
             ).to_list(20)]}}, {"_id": 0})
        if rev:
            docs += _je_doc(rev, f"Jurnal pembalik kas {rev.get('number', '')}")
    if p.get("with_penalty"):
        from services import penalty_service as pen
        order_ids = [a.get("order_id") for a in (rec.get("allocations") or [])
                     if a.get("order_id")]
        for oid in order_ids:
            o = await db.sales_orders.find_one({"id": oid}, {"_id": 0})
            if not o:
                continue
            for pn in (await pen.accrue_order(o, actor_name=actor.get("name", "system")) or []):
                docs.append(_doc("penalty", pn.get("id", ""), pn.get("number", ""),
                                 f"Nota denda {pn.get('number', '')} "
                                 f"({_rp(pn.get('amount'))} · {pn.get('status', '')})"))
    return {"documents": docs, "amount": round(float(rec.get("amount") or 0), 2),
            "extra": {"voided_status": (voided or {}).get("status", "void")}}


async def act_settlement_antar_entitas(case: Dict[str, Any], p: Dict[str, Any],
                                       actor: Dict[str, Any]) -> Dict[str, Any]:
    """Uang masuk di PT lain → jurnal berpasangan di DUA buku (dasar; netting = G-6)."""
    amount = round(float(p.get("amount") or 0), 2)
    owner = (p.get("owner_entity_id") or "").strip()
    order_id = p.get("order_id") or (case.get("order_ids") or [""])[0]
    receiver = case.get("entity_id") or ""
    if not owner:
        raise CaseActionError("PT pemilik tagihan wajib dipilih")
    if owner == receiver:
        raise CaseActionError(
            "PT penerima uang dan PT pemilik tagihan sama — ini bukan kasus salah entitas")
    o = await _order_or_fail(order_id)
    if (o.get("entity_id") or "") != owner:
        raise CaseActionError(
            f"Pesanan {o.get('number')} bukan milik PT pemilik tagihan yang dipilih")
    # Buku PT PENERIMA uang: titipan berubah menjadi utang ke PT pemilik tagihan.
    je_a = await gl.post_finance_case(
        case_id=case["id"], entity_id=receiver, amount=amount,
        debit_acc=gl.ACC_TITIPAN_DANA, credit_acc=gl.ACC_IC_AP,
        label=f"{case['number']} · utang ke PT pemilik tagihan", suffix="ic_ap",
        created_by=actor.get("name", "system"))
    # Buku PT PEMILIK tagihan: piutang pelanggan lunas, ganti piutang antar-perusahaan.
    je_b = await gl.post_finance_case(
        case_id=case["id"], entity_id=owner, amount=amount,
        debit_acc=gl.ACC_IC_AR, credit_acc=gl.ACC_PIUTANG,
        label=f"{case['number']} · piutang antar-perusahaan", suffix="ic_ar",
        created_by=actor.get("name", "system"))
    docs = await _apply_payment(order_id, amount, case, "antar_entitas")
    docs += _je_doc(je_a, "Jurnal PT penerima: Dr 2-1950 Titipan / Cr 2-1250 Utang Antar-PT")
    docs += _je_doc(je_b, "Jurnal PT pemilik: Dr 1-1250 Piutang Antar-PT / Cr 1-1200 Piutang")
    line_id = (case.get("source") or {}).get("id") or ""
    if line_id:
        from services import bank_recon_service as bank
        await bank.holding_refunded(line_id, amount, case["number"], actor.get("name", ""),
                                    label="settlement antar entitas")
    return {"documents": docs, "amount": amount,
            "extra": {"owner_entity_id": owner, "receiver_entity_id": receiver,
                      "pending_phase": "G-6 netting antar entitas"}}


async def act_uang_muka_supplier(case: Dict[str, Any], p: Dict[str, Any],
                                 actor: Dict[str, Any]) -> Dict[str, Any]:
    """Kelebihan bayar supplier → uang muka (Dr 1-1400 / Cr 2-1100)."""
    amount = round(float(p.get("amount") or 0), 2)
    sup_id = p.get("supplier_id") or case.get("supplier_id") or ""
    sup = await db.suppliers.find_one({"id": sup_id}, {"_id": 0})
    if not sup:
        raise CaseActionError("Supplier tidak ditemukan")
    je = await gl.post_finance_case(
        case_id=case["id"], entity_id=case.get("entity_id", ""), amount=amount,
        debit_acc=gl.ACC_UANG_MUKA, credit_acc=gl.ACC_HUTANG,
        label=f"{case['number']} · uang muka supplier {sup.get('name', '')}",
        suffix="ap_adv", created_by=actor.get("name", "system"))
    await db.suppliers.update_one({"id": sup_id}, {
        "$inc": {"advance_balance": amount}, "$set": {"updated_at": now_iso()}})
    docs = _je_doc(je, "Jurnal Dr 1-1400 Uang Muka / Cr 2-1100 Utang Usaha")
    docs.append(_doc("supplier_advance", sup_id, sup.get("code", ""),
                     f"Saldo uang muka {sup.get('name', '')} +{_rp(amount)}"))
    return {"documents": docs, "amount": amount}


async def act_terima_refund_supplier(case: Dict[str, Any], p: Dict[str, Any],
                                     actor: Dict[str, Any]) -> Dict[str, Any]:
    """Supplier mengembalikan uang → Dr Kas-Bank / Cr 1-1400 Uang Muka."""
    amount = round(float(p.get("amount") or 0), 2)
    sup_id = p.get("supplier_id") or case.get("supplier_id") or ""
    sup = await db.suppliers.find_one({"id": sup_id}, {"_id": 0})
    if not sup:
        raise CaseActionError("Supplier tidak ditemukan")
    adv = round(float(sup.get("advance_balance") or 0), 2)
    if amount > adv + EPS:
        raise CaseActionError(
            f"Pengembalian {_rp(amount)} melebihi saldo uang muka supplier {_rp(adv)}")
    res = await _cash_txn(
        direction="in", amount=amount, category="refund supplier",
        description=f"Pengembalian dana dari {sup.get('name', '')} · {case['number']}",
        entity_id=case.get("entity_id", ""), account_id=p.get("account_id", ""),
        cash_type=p.get("cash_type") or "kas_besar", ref_type="finance_case",
        ref_id=case["id"], contra=gl.ACC_UANG_MUKA,
        owner_entity_id=case.get("entity_id", ""), actor=actor.get("name", "system"))
    await db.suppliers.update_one({"id": sup_id}, {
        "$inc": {"advance_balance": -amount}, "$set": {"updated_at": now_iso()}})
    return {"documents": res["documents"], "amount": amount}


EXECUTORS = {
    "alokasi_titipan": act_alokasi_titipan,
    "refund_titipan": act_refund_titipan,
    "alokasi_uang_muka": act_alokasi_uang_muka,
    "refund_pelanggan": act_refund_pelanggan,
    "refund_store_credit": act_refund_store_credit,
    "pindah_buku": act_pindah_buku,
    "akui_dipegang_karyawan": act_akui_dipegang_karyawan,
    "setor_dari_karyawan": act_setor_dari_karyawan,
    "realokasi_pesanan": act_realokasi_pesanan,
    "bebankan_biaya_bank": act_bank_charge,
    "batalkan_kwitansi": act_batalkan_kwitansi,
    "settlement_antar_entitas": act_settlement_antar_entitas,
    "uang_muka_supplier": act_uang_muka_supplier,
    "terima_refund_supplier": act_terima_refund_supplier,
}


async def execute(action: str, case: Dict[str, Any], payload: Dict[str, Any],
                  actor: Dict[str, Any]) -> Dict[str, Any]:
    fn = EXECUTORS.get(action)
    if not fn:
        raise CaseActionError(f"Aksi '{action}' belum punya pelaksana")
    try:
        return await fn(case, payload, actor)
    except HTTPException as e:                      # pesan service lain tetap tampil apa adanya
        raise CaseActionError(str(e.detail)) from e
