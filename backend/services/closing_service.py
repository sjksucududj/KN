"""FINANCE — Tutup Buku (Period Closing) bulanan & tahunan.

Alur: hitung Laba-Rugi OPERASIONAL periode (mengecualikan jurnal penutup) →
buat jurnal penutup otomatis yang me-nol-kan akun pendapatan & beban dan
memindahkan Laba/Rugi Bersih ke **Laba Ditahan (3-2000)** → simpan record
`period_closings` dan tandai periode tertutup.

Prinsip:
- Neraca (balance_sheet) MENYERTAKAN jurnal penutup → Laba Ditahan bertambah,
  "Laba Tahun Berjalan" berkurang (benar secara akuntansi, tetap seimbang).
- Laba-Rugi (income_statement) MENGECUALIKAN jurnal penutup → angka operasional
  periode tetap stabil walau sudah ditutup.
- Gelombang 3 F-9(a): **closing TAHUNAN diperbolehkan di atas closing bulanan**.
  Jurnal tahunan hanya menutup **SISA** yang belum ditutup bulanan (residual per
  akun = operasional − yang sudah ditutup). Blokir hanya bila TAHUN vs TAHUN
  (atau menutup bulan yang tahunnya sudah ditutup).
- Gelombang 3 F-9(b): posting/void jurnal backdate ke periode tertutup menandai
  closing **STALE** (via `gl_service._mark_stale_closings`) → owner dapat
  **Tutup Ulang** (reclose) untuk menghitung ulang snapshot.
- Locking bersifat SOFT (peringatan di UI), tidak memblokir posting jurnal.

Scope: per-entitas (buku terpisah per PT, F0-E). Caller (router) menyuntik
`entity_id` konkret.
"""
import calendar
from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso, new_id, safe_doc
from services import financial_statement_service as fs
from services import gl_service

RETAINED_EARNINGS = "3-2000"  # Laba Ditahan
EPS = 0.005


# ─── Util periode ─────────────────────────────────────────────────────────────

def _period_bounds(period_type: str, period_key: str, fy_end_month: int = 12):
    """Kembalikan (start_date, end_date) 'YYYY-MM-DD' untuk periode.

    FASE G-0 — `fy_end_month` berasal dari setting `finance.fiscal_year_end_month`
    (dulu tombol palsu tanpa consumer). Untuk `period_type="year"`, batas tahun buku
    mengikuti bulan tutup: mis. bulan tutup 3 ⇒ tahun buku 2026 = 2025-04-01 s/d 2026-03-31.
    """
    if period_type == "year":
        y = int(period_key)
        fy_end_month = max(1, min(12, int(fy_end_month or 12)))
        if fy_end_month == 12:
            return f"{y}-01-01", f"{y}-12-31"
        start_month = fy_end_month + 1
        last = calendar.monthrange(y, fy_end_month)[1]
        return f"{y - 1}-{start_month:02d}-01", f"{y}-{fy_end_month:02d}-{last:02d}"
    # month: "YYYY-MM"
    parts = period_key.split("-")
    y, m = int(parts[0]), int(parts[1])
    last = calendar.monthrange(y, m)[1]
    return f"{y}-{m:02d}-01", f"{y}-{m:02d}-{last:02d}"


async def period_bounds(period_type: str, period_key: str,
                        entity_id: Optional[str] = None):
    """Batas periode dengan bulan tutup tahun buku dari konfigurasi entitas."""
    from services.config_resolver import value_of
    try:
        fy_end = int(await value_of("finance.fiscal_year_end_month",
                                    {"entity_id": entity_id}) or 12)
    except (TypeError, ValueError):
        fy_end = 12
    return _period_bounds(period_type, period_key, fy_end)


def _period_label(period_type: str, period_key: str) -> str:
    if period_type == "year":
        return f"Tahun {period_key}"
    months = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
              "Agustus", "September", "Oktober", "November", "Desember"]
    try:
        y, m = period_key.split("-")
        return f"{months[int(m)]} {y}"
    except Exception:
        return period_key


def _overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return not (a_end < b_start or a_start > b_end)


# ─── Jurnal penutup (residual-aware — F-9a) ──────────────────────────────────

def _close_line(code: str, name: str, is_revenue: bool, amt: float,
                ac: Dict[str, Any]):
    """Bangun 1 baris jurnal penutup RESIDUAL untuk 1 akun.

    `amt` = saldo OPERASIONAL akun pada periode (income_statement). `ac` = jumlah
    yang SUDAH ditutup (debit/kredit) oleh closing lain dalam periode. Baris yang
    dihasilkan hanya menutup SISA-nya. Return (line|None, debit, credit)."""
    amt = round(float(amt or 0), 2)
    acd = round(float(ac.get("debit", 0) or 0), 2)
    acc = round(float(ac.get("credit", 0) or 0), 2)
    if is_revenue:
        # pendapatan (normal kredit): ditutup dgn DEBIT. Sudah ditutup net = acd − acc.
        residual = round(amt - (acd - acc), 2)
        if residual > EPS:
            return {"account_code": code, "debit": residual, "credit": 0.0,
                    "description": f"Tutup {name}"}, residual, 0.0
        if residual < -EPS:
            return {"account_code": code, "debit": 0.0, "credit": -residual,
                    "description": f"Tutup {name}"}, 0.0, -residual
    else:
        # beban (normal debit): ditutup dgn KREDIT. Sudah ditutup net = acc − acd.
        residual = round(amt - (acc - acd), 2)
        if residual > EPS:
            return {"account_code": code, "debit": 0.0, "credit": residual,
                    "description": f"Tutup {name}"}, 0.0, residual
        if residual < -EPS:
            return {"account_code": code, "debit": -residual, "credit": 0.0,
                    "description": f"Tutup {name}"}, -residual, 0.0
    return None, 0.0, 0.0


def _build_closing_lines(stmt: Dict[str, Any],
                         already_closed: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Bangun baris jurnal penutup dari Laba-Rugi periode, kurangi yang sudah ditutup.

    - Akun pendapatan (normal kredit) → DEBIT sisa.
    - Akun beban (normal debit) → KREDIT sisa.
    - Selisih (Laba/Rugi Bersih residual) → Laba Ditahan (3-2000).
    """
    already_closed = already_closed or {}
    lines: List[Dict[str, Any]] = []
    total_debit = 0.0
    total_credit = 0.0
    for sec in stmt.get("sections", []):
        is_revenue = sec.get("key") == "revenue"
        for ln in sec.get("lines", []):
            code = ln.get("code")
            if not code:
                continue
            name = ln.get("name", code)
            amt = float(ln.get("amount", 0) or 0)
            line, d, c = _close_line(code, name, is_revenue, amt, already_closed.get(code, {}))
            if line:
                lines.append(line)
                total_debit += d
                total_credit += c

    diff = round(total_debit - total_credit, 2)  # >0 → laba (butuh kredit ke RE)
    if abs(diff) > EPS:
        if diff > 0:
            lines.append({"account_code": RETAINED_EARNINGS, "debit": 0.0, "credit": diff,
                          "description": "Laba Bersih → Laba Ditahan"})
        else:
            lines.append({"account_code": RETAINED_EARNINGS, "debit": -diff, "credit": 0.0,
                          "description": "Rugi Bersih → Laba Ditahan"})
    return lines


def _residual_net(lines: List[Dict[str, Any]]) -> float:
    """Laba/rugi bersih yang benar-benar ditutup oleh baris (dari baris Laba Ditahan)."""
    for ln in lines:
        if ln.get("account_code") == RETAINED_EARNINGS:
            return round(float(ln.get("credit", 0) or 0) - float(ln.get("debit", 0) or 0), 2)
    return 0.0


# ─── Query / list ──────────────────────────────────────────────────────────────

async def list_closings(entity_id: str) -> List[Dict[str, Any]]:
    rows = await db.period_closings.find({"entity_id": entity_id}, {"_id": 0}) \
        .sort("end_date", -1).to_list(500)
    return rows


async def _already_closed_amounts(entity_id: str, start: str, end: str,
                                  exclude_closing_id: Optional[str] = None) -> Dict[str, Dict[str, float]]:
    """Σ baris jurnal PENUTUP (source_type='closing', non-void) dalam [start,end] per akun.

    Dipakai untuk closing TAHUNAN di atas closing bulanan: tahunan hanya menutup
    sisa yang belum ditutup. `exclude_closing_id` = jangan hitung JE milik closing
    yang sedang di-tutup-ulang (reclose)."""
    q = {"entity_id": entity_id, "source_type": "closing", "status": {"$ne": "void"}}
    out: Dict[str, Dict[str, float]] = {}
    async for je in db.journal_entries.find(q, {"_id": 0, "lines": 1, "date": 1, "source_id": 1}):
        d = (je.get("date", "") or "")[:10]
        if not d or not (start <= d <= end):
            continue
        if exclude_closing_id and je.get("source_id") == exclude_closing_id:
            continue
        for l in je.get("lines", []):
            code = l.get("account_code", "")
            if not code or code == RETAINED_EARNINGS:
                continue
            acc = out.setdefault(code, {"debit": 0.0, "credit": 0.0})
            acc["debit"] += float(l.get("debit", 0) or 0)
            acc["credit"] += float(l.get("credit", 0) or 0)
    return out


async def _blocking_closing(entity_id: str, period_type: str, start: str, end: str,
                            exclude_closing_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Cari penutupan AKTIF (status closed) yang MEMBLOKIR penutupan periode ini.

    - Menutup TAHUN → hanya diblokir TAHUN lain yang overlap (bulanan di dalamnya
      DIPERBOLEHKAN, di-net-kan sebagai residual — F-9a).
    - Menutup BULAN → diblokir bulan yang sama ATAU tahun yang sudah menutupinya.
    """
    rows = await db.period_closings.find(
        {"entity_id": entity_id, "status": "closed"}, {"_id": 0}).to_list(500)
    for r in rows:
        if exclude_closing_id and r.get("id") == exclude_closing_id:
            continue
        if not _overlaps(start, end, r.get("start_date", ""), r.get("end_date", "")):
            continue
        if period_type == "year":
            if r.get("period_type") == "year":
                return r
            continue  # closing bulanan di dalam tahun → boleh (residual)
        return r  # menutup bulan → diblokir oleh bulan sama / tahun yang menutupinya
    return None


async def preview(period_type: str, period_key: str, entity_id: str) -> Dict[str, Any]:
    start, end = await period_bounds(period_type, period_key, entity_id)
    scope = {"entity_id": entity_id}
    stmt = await fs.income_statement(start=start, end=end, scope=scope)
    already = await _already_closed_amounts(entity_id, start, end)
    lines = _build_closing_lines(stmt, already)
    blocking = await _blocking_closing(entity_id, period_type, start, end)
    suspense = await gl_service.suspense_balance(entity_id, as_of=end)
    return {
        "period_type": period_type,
        "period_key": period_key,
        "period_label": _period_label(period_type, period_key),
        "start_date": start,
        "end_date": end,
        "entity_id": entity_id,
        "revenue_total": stmt.get("revenue_total", 0),
        "expense_total": round(stmt.get("cogs_total", 0) + stmt.get("opex_total", 0), 2),
        "net_income": stmt.get("net_income", 0),
        "residual_net_income": _residual_net(lines),
        "closing_lines": lines,
        "retained_earnings_account": RETAINED_EARNINGS,
        "can_close": blocking is None,
        "blocking_closing": blocking,
        "suspense_balance": suspense,
        "suspense_warning": abs(suspense) > EPS,
    }


# ─── Aksi close / reopen / reclose ───────────────────────────────────────────────

async def close_period(period_type: str, period_key: str, actor: Dict[str, Any],
                       entity_id: str, note: str = "") -> Dict[str, Any]:
    if period_type not in ("month", "year"):
        raise ValueError("period_type harus 'month' atau 'year'.")
    start, end = await period_bounds(period_type, period_key, entity_id)

    blocking = await _blocking_closing(entity_id, period_type, start, end)
    if blocking:
        raise ValueError(
            f"Periode tumpang tindih dengan penutupan aktif ({_period_label(blocking['period_type'], blocking['period_key'])}). "
            "Buka kembali (reopen) periode tersebut lebih dulu.")

    scope = {"entity_id": entity_id}
    stmt = await fs.income_statement(start=start, end=end, scope=scope)
    already = await _already_closed_amounts(entity_id, start, end)
    lines = _build_closing_lines(stmt, already)

    closing_id = new_id("close")
    je = None
    if lines:
        je = await gl_service._insert_entry(
            lines=lines,
            description=f"Jurnal Penutup — {_period_label(period_type, period_key)}",
            date=f"{end}T23:59:59",
            source_type="closing",
            source_id=closing_id,
            entity_id=entity_id,
            created_by=actor.get("name", "system"),
            source_label=f"Tutup Buku {period_key}",
        )

    rec = {
        "id": closing_id,
        "entity_id": entity_id,
        "period_type": period_type,
        "period_key": period_key,
        "period_label": _period_label(period_type, period_key),
        "start_date": start,
        "end_date": end,
        "status": "closed",
        "net_income": stmt.get("net_income", 0),
        "residual_net_income": _residual_net(lines),
        "revenue_total": stmt.get("revenue_total", 0),
        "expense_total": round(stmt.get("cogs_total", 0) + stmt.get("opex_total", 0), 2),
        "journal_entry_id": je["id"] if je else None,
        "journal_entry_number": je["number"] if je else None,
        "note": (note or "").strip(),
        "stale": False,
        "stale_at": None,
        "stale_reason": "",
        "closed_by": actor.get("name", "system"),
        "closed_at": now_iso(),
        "reopened_by": None,
        "reopened_at": None,
        "reclosed_by": None,
        "reclosed_at": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.period_closings.insert_one(rec)
    return safe_doc(rec)


async def reopen_period(closing_id: str, actor: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    rec = await db.period_closings.find_one({"id": closing_id}, {"_id": 0})
    if not rec:
        return None
    if rec.get("status") != "closed":
        raise ValueError("Periode ini tidak dalam status tertutup.")
    if rec.get("journal_entry_id"):
        await db.journal_entries.update_one(
            {"id": rec["journal_entry_id"]},
            {"$set": {"status": "void", "voided_by": actor.get("name", "system"),
                      "voided_at": now_iso(), "updated_at": now_iso()}},
        )
    await db.period_closings.update_one(
        {"id": closing_id},
        {"$set": {"status": "reopened", "stale": False, "stale_reason": "",
                  "reopened_by": actor.get("name", "system"),
                  "reopened_at": now_iso(), "updated_at": now_iso()}},
    )
    return await db.period_closings.find_one({"id": closing_id}, {"_id": 0})


async def reclose_period(closing_id: str, actor: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """F-9b — Tutup Ulang periode yang STALE (angka berubah karena posting backdate):
    void jurnal penutup lama → hitung ulang residual (kecuali JE closing ini sendiri)
    → buat jurnal penutup baru → bersihkan flag stale."""
    rec = await db.period_closings.find_one({"id": closing_id}, {"_id": 0})
    if not rec:
        return None
    if rec.get("status") != "closed":
        raise ValueError("Hanya periode berstatus tertutup yang dapat ditutup ulang.")
    entity_id = rec["entity_id"]
    start, end = rec["start_date"], rec["end_date"]
    period_type = rec["period_type"]

    if rec.get("journal_entry_id"):
        await db.journal_entries.update_one(
            {"id": rec["journal_entry_id"]},
            {"$set": {"status": "void", "voided_by": actor.get("name", "system"),
                      "voided_at": now_iso(), "updated_at": now_iso()}},
        )

    scope = {"entity_id": entity_id}
    stmt = await fs.income_statement(start=start, end=end, scope=scope)
    already = await _already_closed_amounts(entity_id, start, end, exclude_closing_id=closing_id)
    lines = _build_closing_lines(stmt, already)
    je = None
    if lines:
        je = await gl_service._insert_entry(
            lines=lines,
            description=f"Jurnal Penutup (Ulang) — {_period_label(period_type, rec['period_key'])}",
            date=f"{end}T23:59:59",
            source_type="closing",
            source_id=closing_id,
            entity_id=entity_id,
            created_by=actor.get("name", "system"),
            source_label=f"Tutup Ulang {rec['period_key']}",
        )
    await db.period_closings.update_one(
        {"id": closing_id},
        {"$set": {
            "net_income": stmt.get("net_income", 0),
            "residual_net_income": _residual_net(lines),
            "journal_entry_id": je["id"] if je else None,
            "journal_entry_number": je["number"] if je else None,
            "stale": False, "stale_at": None, "stale_reason": "",
            "reclosed_by": actor.get("name", "system"), "reclosed_at": now_iso(),
            "updated_at": now_iso()}},
    )
    # Re-close periode ini mengubah angka → periode yang MEMUAT-nya (mis. tahunan
    # yang memuat bulan ini) residualnya jadi basi → tandai STALE agar di-close ulang.
    await db.period_closings.update_many(
        {"entity_id": entity_id, "status": "closed", "id": {"$ne": closing_id},
         "stale": {"$ne": True}, "start_date": {"$lte": start}, "end_date": {"$gte": end}},
        {"$set": {"stale": True, "stale_at": now_iso(),
                  "stale_reason": f"Closing periode di dalamnya ditutup ulang ({rec.get('period_label', '')})",
                  "updated_at": now_iso()}})
    return await db.period_closings.find_one({"id": closing_id}, {"_id": 0})


async def status_for_date(date_iso: str, entity_id: str) -> Dict[str, Any]:
    """Cek apakah `date_iso` berada dalam periode tertutup (untuk warning soft)."""
    d = (date_iso or "")[:10]
    if not d:
        return {"closed": False}
    rows = await db.period_closings.find(
        {"entity_id": entity_id, "status": "closed"}, {"_id": 0}).to_list(500)
    for r in rows:
        if r.get("start_date", "") <= d <= r.get("end_date", ""):
            return {
                "closed": True,
                "period_type": r["period_type"],
                "period_key": r["period_key"],
                "period_label": r.get("period_label", r["period_key"]),
                "stale": bool(r.get("stale")),
                "closed_at": r.get("closed_at"),
            }
    return {"closed": False}
