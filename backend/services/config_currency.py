"""FASE G-0 — Konsumen nyata untuk `finance.base_currency` & `finance.fiscal_year_end_month`.

Dua setting tersebut sebelumnya adalah **"tombol palsu"**: tampil di layar pengaturan
tetapi TIDAK ADA satu baris kode pun yang membacanya (audit 2026-07-26 → ORPHAN_UI).
Modul ini menjadikannya berfungsi:

- `money_format()`   — format uang mengikuti mata uang pembukuan (dipakai PDF & laporan)
- `fiscal_year_of()` — tahun buku sebuah periode mengikuti bulan tutup tahun buku
"""
from typing import Any, Dict, Optional, Tuple

CURRENCIES: Dict[str, Dict[str, Any]] = {
    "IDR": {"symbol": "Rp", "decimals": 0, "thousands": ".", "decimal": ",", "space": " "},
    "USD": {"symbol": "$", "decimals": 2, "thousands": ",", "decimal": ".", "space": " "},
}


def format_money_with(amount: Any, currency: str = "IDR") -> str:
    """Format nominal memakai definisi mata uang (pure function, mudah diuji)."""
    spec = CURRENCIES.get((currency or "IDR").upper(), CURRENCIES["IDR"])
    try:
        num = float(amount or 0)
    except (TypeError, ValueError):
        num = 0.0
    body = f"{num:,.{spec['decimals']}f}"
    if spec["thousands"] != "," or spec["decimal"] != ".":
        body = body.replace(",", "\x00").replace(".", spec["decimal"]).replace("\x00", spec["thousands"])
    return f"{spec['symbol']}{spec['space']}{body}"


async def base_currency(entity_id: Optional[str] = None) -> str:
    from services.config_resolver import value_of
    return str(await value_of("finance.base_currency", {"entity_id": entity_id}) or "IDR")


async def money_format(amount: Any, entity_id: Optional[str] = None) -> str:
    """Format uang sesuai `finance.base_currency` yang berlaku untuk entitas tersebut."""
    return format_money_with(amount, await base_currency(entity_id))


def fiscal_year_bounds(period: str, end_month: int = 12) -> Tuple[str, str, str]:
    """(label tahun buku, periode awal, periode akhir) untuk sebuah `YYYY-MM`.

    `end_month=12` → tahun buku = tahun kalender. `end_month=3` → April..Maret.
    """
    try:
        year, month = (int(x) for x in (period or "").split("-")[:2])
    except (ValueError, TypeError):
        raise ValueError("Periode harus berformat YYYY-MM")
    end_month = max(1, min(12, int(end_month or 12)))
    fy_end_year = year if month <= end_month else year + 1
    start_month = end_month + 1 if end_month < 12 else 1
    start_year = fy_end_year - 1 if end_month < 12 else fy_end_year
    label = str(fy_end_year) if end_month == 12 else f"{start_year}/{fy_end_year}"
    return label, f"{start_year}-{start_month:02d}", f"{fy_end_year}-{end_month:02d}"


async def fiscal_year_of(period: str, entity_id: Optional[str] = None) -> Dict[str, str]:
    """Tahun buku sebuah periode, mengikuti `finance.fiscal_year_end_month`."""
    from services.config_resolver import value_of
    end_month = int(await value_of("finance.fiscal_year_end_month", {"entity_id": entity_id}) or 12)
    label, start, end = fiscal_year_bounds(period, end_month)
    return {"fiscal_year": label, "start_period": start, "end_period": end,
            "end_month": str(end_month)}
