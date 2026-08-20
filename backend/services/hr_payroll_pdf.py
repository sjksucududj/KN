"""HRD H4 — Payslip PDF (reportlab). Slip gaji ringkas, profesional, Bahasa Indonesia."""
from io import BytesIO
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from core_utils import rupiah

NAVY = colors.HexColor("#0058CC")
GRAY = colors.HexColor("#6B6B73")
DARK = colors.HexColor("#1A1A1F")
LINE = colors.HexColor("#E1E4E8")


def _rp(v: Any) -> str:
    """Alias tipis ke `core_utils.rupiah` — satu sumber format uang untuk seluruh backend."""
    return rupiah(v)


def payslip_pdf_bytes(slip: Dict[str, Any], entity_name: str = "Kain Nusantara") -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    x0 = 18 * mm
    y = h - 20 * mm

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x0, y, "SLIP GAJI")
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 9)
    c.drawRightString(w - 18 * mm, y, entity_name)
    c.drawRightString(w - 18 * mm, y - 12, f"No. {slip.get('number', '')}")
    y -= 26
    c.setStrokeColor(NAVY)
    c.setLineWidth(2)
    c.line(x0, y, w - 18 * mm, y)
    y -= 18

    # Info karyawan
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x0, y, slip.get("employee_name", ""))
    c.setFont("Helvetica", 9)
    c.setFillColor(GRAY)
    c.drawString(x0, y - 13, f"Periode: {slip.get('period', '')}   ·   PTKP: {slip.get('ptkp_status', '')}   ·   TER-{slip.get('ter_category', '')}")
    bank = slip.get("bank", {}) or {}
    if bank.get("acc_no"):
        c.drawString(x0, y - 26, f"Bank: {bank.get('bank_name', '')} {bank.get('acc_no', '')} a.n. {bank.get('acc_name', '')}")
    y -= 44

    def section(title: str, yy: float) -> float:
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x0, yy, title)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(x0, yy - 4, w - 18 * mm, yy - 4)
        return yy - 18

    def row(label: str, value: Any, yy: float, bold: bool = False) -> float:
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9.5)
        c.drawString(x0 + 4, yy, label)
        c.drawRightString(w - 18 * mm, yy, _rp(value))
        return yy - 15

    # Penerimaan
    y = section("PENERIMAAN (EARNINGS)", y)
    y = row("Gaji Pokok", slip.get("base_salary"), y)
    y = row("Tunjangan", slip.get("allowances"), y)
    y = row("Lembur", slip.get("overtime"), y)
    if float(slip.get("commission", 0) or 0) > 0:
        y = row("Komisi / Insentif Penjualan", slip.get("commission"), y)
    y = row("Penghasilan Bruto (Gross)", slip.get("gross"), y, bold=True)
    y -= 8

    # Potongan
    emp_b = slip.get("bpjs_emp", {}) or {}
    y = section("POTONGAN (DEDUCTIONS)", y)
    y = row("BPJS Kesehatan (1%)", emp_b.get("kesehatan"), y)
    y = row("BPJS JHT (2%)", emp_b.get("jht"), y)
    y = row("BPJS JP (1%)", emp_b.get("jp"), y)
    y = row(f"PPh 21 (TER {float(slip.get('pph21_rate', 0)) * 100:.2f}%)", slip.get("pph21"), y)
    y = row("Total Potongan", round(float(slip.get("bpjs_emp_total", 0)) + float(slip.get("pph21", 0)), 2), y, bold=True)
    y -= 10

    # Take-home
    c.setFillColor(NAVY)
    c.rect(x0, y - 6, w - 36 * mm, 24, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x0 + 6, y + 2, "TAKE-HOME PAY (NET)")
    c.drawRightString(w - 20 * mm, y + 2, _rp(slip.get("net")))
    y -= 34

    # Kontribusi perusahaan (informasi)
    er_b = slip.get("bpjs_er", {}) or {}
    y = section("KONTRIBUSI PERUSAHAAN (INFO)", y)
    y = row("BPJS Kesehatan (4%)", er_b.get("kesehatan"), y)
    y = row("BPJS JHT (3,7%) + JP (2%)", round(float(er_b.get("jht", 0)) + float(er_b.get("jp", 0)), 2), y)
    y = row("BPJS JKK + JKM", round(float(er_b.get("jkk", 0)) + float(er_b.get("jkm", 0)), 2), y)

    c.setFillColor(GRAY)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(x0, 18 * mm, "Slip ini dihasilkan otomatis oleh sistem ERP Kain Nusantara. Rahasia & hanya untuk karyawan bersangkutan.")
    c.showPage()
    c.save()
    return buf.getvalue()
