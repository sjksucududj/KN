"""SATU definisi “cara membaca angka rupiah dari CSV” untuk seluruh sistem.

Kenapa dipisah: dua layar harga (harga per badan usaha & harga per pelanggan)
sama-sama mengimpor CSV buatan orang, dan file dari lapangan datang dalam dua
gaya penulisan sekaligus. Kalau tiap layar menebak sendiri, satu layar akan
membaca `126.540` sebagai 1.265.400 — pernah terjadi dan mahal.

Kasus nyata yang WAJIB benar:
    "126.540"    → 126540    (titik = pemisah ribuan, gaya Indonesia)
    "1.265.400"  → 1265400   (banyak titik = ribuan)
    "126540.00"  → 126540.0  (titik = desimal, hasil ekspor sistem)
    "126.540,50" → 126540.5  (titik ribuan + koma desimal)
    "126540,5"   → 126540.5  (koma desimal)
    "Rp 126.540" → 126540    (orang menempel “Rp”)
"""
from __future__ import annotations


def parse_money(text: str) -> float:
    """Angka rupiah dari sel CSV. `ValueError` bila bukan angka."""
    raw = (text or "").strip().replace(" ", "").replace("Rp", "").replace("rp", "")
    if not raw:
        raise ValueError("kosong")
    if "," in raw and "." in raw:            # 126.540,50
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:                          # 126540,5
        raw = raw.replace(",", ".")
    elif raw.count(".") > 1:                  # 1.265.400
        raw = raw.replace(".", "")
    elif raw.count(".") == 1:
        head, _, frac = raw.partition(".")
        if len(frac) == 3 and head:           # 126.540 → ribuan
            raw = head + frac
    return float(raw)


def sniff_delimiter(first_line: str) -> str:
    """Excel Indonesia menulis `;`, Excel English menulis `,`. Terima keduanya."""
    return ";" if (first_line or "").count(";") >= (first_line or "").count(",") else ","
