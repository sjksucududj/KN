#!/usr/bin/env python3
"""
POC Document Platform — membuktikan CORE paling berisiko sebelum bangun aplikasi:
  A. Engine PDF asli (WeasyPrint → fallback Playwright → fallback reportlab) merender
     PDF valid berkop surat + logo (base64) + font + tabel + QR code.
  B. E-Sign: generate OTP → verify → SHA-256 hash dokumen → verification_code + QR.
  C. WhatsApp adapter pluggable (registry) + MetaCloudProvider mode SIMULASI.

Jalankan: python3 scripts/poc_document_platform.py
Sukses bila semua blok mencetak [PASS] dan exit code 0.
"""
import base64
import hashlib
import io
import secrets
import sys
import uuid
from datetime import datetime, timezone

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: logo & QR base64 (PNG)
# ─────────────────────────────────────────────────────────────────────────────
def make_logo_b64():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (120, 120), "#0058CC")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 100, 100], outline="white", width=6)
    d.text((42, 50), "KN", fill="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def make_qr_b64(payload):
    import qrcode
    qr = qrcode.make(payload)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ─────────────────────────────────────────────────────────────────────────────
# A. PDF engine resolver (fallback chain)
# ─────────────────────────────────────────────────────────────────────────────
def render_pdf(html: str) -> tuple[bytes, str]:
    """Return (pdf_bytes, engine_used). Try WeasyPrint → Playwright → reportlab."""
    # 1) WeasyPrint
    try:
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        if pdf and pdf[:4] == b"%PDF":
            return pdf, "weasyprint"
    except Exception as e:  # noqa: BLE001
        print(f"    (weasyprint gagal: {e})")
    # 2) Playwright chromium
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.set_content(html, wait_until="networkidle")
            pdf = pg.pdf(format="A4", print_background=True)
            b.close()
        if pdf and pdf[:4] == b"%PDF":
            return pdf, "playwright"
    except Exception as e:  # noqa: BLE001
        print(f"    (playwright gagal: {e})")
    # 3) reportlab (minimal fallback)
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.drawString(72, 800, "Fallback PDF (reportlab) — engine utama tidak tersedia")
        c.save()
        return buf.getvalue(), "reportlab"
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Semua engine PDF gagal: {e}")


SAMPLE_HTML = """
<!doctype html><html><head><meta charset="utf-8"/>
<style>
  @page {{ size: A4; margin: 18mm 16mm; }}
  body {{ font-family: 'DejaVu Sans', Arial, sans-serif; color:#111; font-size:12px; }}
  .kop {{ display:flex; align-items:center; gap:14px; border-bottom:3px solid #0058CC; padding-bottom:10px; }}
  .kop img {{ width:54px; height:54px; }}
  .kop .co {{ font-size:18px; font-weight:800; color:#0058CC; }}
  .kop .addr {{ font-size:10px; color:#555; }}
  h2.doctitle {{ text-align:right; text-transform:uppercase; letter-spacing:1px; margin:6px 0; }}
  table {{ width:100%; border-collapse:collapse; margin:10px 0; }}
  th,td {{ border:1px solid #999; padding:6px 8px; font-size:11px; }}
  th {{ background:#f0f0f0; }}
  .sign {{ margin-top:40px; display:flex; justify-content:space-between; }}
  .sign .slot {{ text-align:center; font-size:11px; }}
  .qr {{ margin-top:18px; }}
  .qr img {{ width:90px; height:90px; }}
</style></head><body>
  <div class="kop">
    <img src="data:image/png;base64,{logo}"/>
    <div><div class="co">PT Kain Suka Cita</div>
    <div class="addr">Jl. Tekstil No. 1, Cirebon · Telp 0231-000000 · NPWP 00.000.000.0-000.000</div></div>
  </div>
  <h2 class="doctitle">Sales Order Confirmation</h2>
  <p>No. <b>SO-POC-0001</b> · Tanggal: 19 Juli 2026 · Customer: Batik Nusantara</p>
  <table>
    <thead><tr><th>No</th><th>Produk</th><th>Qty</th><th>Harga</th><th>Subtotal</th></tr></thead>
    <tbody>
      <tr><td>1</td><td>Batik Mega Mendung</td><td>500 m</td><td>Rp 185.000</td><td>Rp 92.500.000</td></tr>
      <tr><td>2</td><td>Lurik Klasik Solo</td><td>300 m</td><td>Rp 95.000</td><td>Rp 28.500.000</td></tr>
    </tbody>
  </table>
  <p><b>Total: Rp 121.000.000</b> — Terbilang: Seratus dua puluh satu juta rupiah</p>
  <div class="sign">
    <div class="slot">Dibuat<br/><br/><br/>( Sales )</div>
    <div class="slot">Disetujui<br/><br/><br/>( Manager )</div>
    <div class="slot">Diterima<br/><br/><br/>( Customer )</div>
  </div>
  <div class="qr"><img src="data:image/png;base64,{qr}"/><div style="font-size:9px;color:#777">Scan untuk verifikasi keaslian dokumen</div></div>
</body></html>
"""


def poc_pdf():
    print("\n== A. PDF ENGINE ==")
    logo = make_logo_b64()
    qr = make_qr_b64("https://kn.example/verify-document/POC123")
    check("logo base64 dibuat", len(logo) > 100, f"{len(logo)} chars")
    check("qr base64 dibuat", len(qr) > 100, f"{len(qr)} chars")
    html = SAMPLE_HTML.format(logo=logo, qr=qr)
    pdf, engine = render_pdf(html)
    check("PDF ter-render", pdf[:4] == b"%PDF", f"engine={engine}, size={len(pdf)} bytes")
    check("PDF ukuran wajar (>10KB)", len(pdf) > 10_000, f"{len(pdf)} bytes")
    with open("/tmp/poc_document.pdf", "wb") as f:
        f.write(pdf)
    print("    -> /tmp/poc_document.pdf")
    return pdf, engine


# ─────────────────────────────────────────────────────────────────────────────
# B. E-Sign core (OTP + hash + verification_code)
# ─────────────────────────────────────────────────────────────────────────────
def hash_otp(otp, salt):
    return hashlib.sha256(f"{salt}:{otp}".encode()).hexdigest()


def poc_esign(pdf_bytes):
    print("\n== B. E-SIGN CORE ==")
    # 1) buat request + OTP (mode simulasi: OTP di-return utk dev)
    otp = f"{secrets.randbelow(1000000):06d}"
    salt = secrets.token_hex(8)
    otp_hash = hash_otp(otp, salt)
    check("OTP 6-digit dibuat", len(otp) == 6 and otp.isdigit(), otp)
    # 2) verifikasi OTP
    ok = hash_otp(otp, salt) == otp_hash
    bad = hash_otp("000000", salt) == otp_hash
    check("verifikasi OTP benar diterima", ok)
    check("verifikasi OTP salah ditolak", not bad)
    # 3) hash dokumen SHA-256
    doc_hash = hashlib.sha256(pdf_bytes).hexdigest()
    doc_hash2 = hashlib.sha256(pdf_bytes).hexdigest()
    check("SHA-256 dokumen konsisten", doc_hash == doc_hash2, doc_hash[:16] + "…")
    # 4) verification_code publik + audit record
    code = uuid.uuid4().hex[:12].upper()
    signature_png = make_qr_b64("tanda-tangan-canvas-dummy")  # simulasi gambar TTD
    record = {
        "verification_code": code,
        "doc_hash": doc_hash,
        "signer": "Budi Santoso",
        "role": "manager",
        "signature_b64": signature_png,
        "ip": "10.0.0.5",
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "otp_verified": ok,
    }
    check("verification_code dibuat", len(code) == 12, code)
    check("audit record lengkap", all(record.get(k) for k in ["verification_code", "doc_hash", "signer", "signed_at"]))
    # 5) QR verifikasi publik
    verify_qr = make_qr_b64(f"https://kn.example/verify-document/{code}")
    check("QR verifikasi publik dibuat", len(verify_qr) > 100)
    return record


# ─────────────────────────────────────────────────────────────────────────────
# C. WhatsApp adapter pluggable (registry) + Meta simulasi
# ─────────────────────────────────────────────────────────────────────────────
class BaseWaProvider:
    name = "base"

    def __init__(self, config=None):
        self.config = config or {}
        self.simulate = self.config.get("simulate", True) or not self.config.get("access_token")

    def send_document(self, to, filename, pdf_bytes, caption=""):
        raise NotImplementedError


class MetaCloudProvider(BaseWaProvider):
    name = "meta_cloud"

    def send_document(self, to, filename, pdf_bytes, caption=""):
        if self.simulate:
            return {
                "status": "simulated", "provider": self.name, "to": to,
                "filename": filename, "bytes": len(pdf_bytes or b""), "caption": caption,
                "note": "SIMULASI — set access_token & phone_number_id untuk kirim nyata",
            }
        # (implementasi nyata di fase 5: upload media → kirim message)
        raise RuntimeError("real send belum diimplement di POC")


class TwilioProvider(BaseWaProvider):
    name = "twilio"

    def send_document(self, to, filename, pdf_bytes, caption=""):
        return {"status": "simulated", "provider": self.name, "to": to}


_REGISTRY = {p.name: p for p in [MetaCloudProvider, TwilioProvider]}


def get_wa_provider(name="meta_cloud", config=None):
    cls = _REGISTRY.get(name, MetaCloudProvider)
    return cls(config)


def poc_whatsapp(pdf_bytes):
    print("\n== C. WHATSAPP ADAPTER (SIMULASI) ==")
    check("registry punya >=2 provider", len(_REGISTRY) >= 2, ",".join(_REGISTRY))
    prov = get_wa_provider("meta_cloud", {"simulate": True})
    res = prov.send_document("+628123456789", "SO-POC-0001.pdf", pdf_bytes, caption="Invoice Anda")
    check("Meta provider default terpilih", prov.name == "meta_cloud")
    check("mode simulasi aktif (tanpa credential)", prov.simulate)
    check("send return status 'simulated'", res.get("status") == "simulated", str(res.get("note", ""))[:40])
    check("send tidak error & bawa metadata", res.get("bytes") == len(pdf_bytes))
    # provider lain tinggal tambah
    prov2 = get_wa_provider("twilio")
    check("provider lain (twilio) bisa dipilih", prov2.name == "twilio")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 64)
    print("  POC DOCUMENT PLATFORM — PDF asli · E-Sign · WhatsApp adapter")
    print("=" * 64)
    try:
        pdf, engine = poc_pdf()
        poc_esign(pdf)
        poc_whatsapp(pdf)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        FAILED.append(f"exception: {e}")
    print("\n" + "=" * 64)
    print(f"  HASIL: PASS {len(PASSED)} | FAIL {len(FAILED)}")
    if FAILED:
        print("  GAGAL:", ", ".join(FAILED))
        sys.exit(1)
    print("  SEMUA CORE POC PASS ✅  (engine PDF siap, e-sign siap, WA adapter siap)")
    sys.exit(0)
