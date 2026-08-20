"""
pdf_engine.py — Mesin render PDF asli (server-side) untuk semua dokumen bisnis.

Alur: context ternormalisasi + template config + branding entitas
      → Jinja2 (MASTER_TEMPLATE) → HTML → engine PDF (WeasyPrint→Playwright→reportlab).

Dipakai oleh services/pdf_service.py. Semua dokumen memakai SATU master template
yang dikendalikan oleh `cfg` (template config) sehingga bisa dikustomisasi penuh.
"""
from __future__ import annotations
import io
from jinja2 import Environment, BaseLoader, select_autoescape

# ─── Format uang & terbilang (Bahasa Indonesia) ──────────────────────────────
# FASE G-0 — mata uang aktif untuk dokumen yang sedang dirender. Diisi `pdf_service`
# dari `finance.base_currency` (setting yang DULU tombol palsu tanpa consumer).
_ACTIVE_CURRENCY = ["IDR"]


def set_document_currency(currency: str) -> None:
    """Tetapkan mata uang untuk rendering dokumen berikutnya (dipakai pdf_service)."""
    _ACTIVE_CURRENCY[0] = (currency or "IDR").upper()


def fmt_rp(v, currency: str = "") -> str:
    """Format nominal mengikuti `finance.base_currency` (default Rupiah).

    Tetap menerima 1 argumen agar 30+ pemakaian lama tidak berubah.
    """
    from services.config_currency import format_money_with
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        n = 0.0
    cur = (currency or _ACTIVE_CURRENCY[0] or "IDR").upper()
    neg = n < 0
    s = format_money_with(abs(n), cur)
    return f"-{s}" if neg else s


_SATUAN = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh", "sebelas"]


def _terbilang(n: int) -> str:
    n = int(abs(n))
    if n < 12:
        return _SATUAN[n]
    if n < 20:
        return f"{_terbilang(n - 10)} belas"
    if n < 100:
        return f"{_terbilang(n // 10)} puluh {_terbilang(n % 10)}".strip()
    if n < 200:
        return f"seratus {_terbilang(n - 100)}".strip()
    if n < 1000:
        return f"{_terbilang(n // 100)} ratus {_terbilang(n % 100)}".strip()
    if n < 2000:
        return f"seribu {_terbilang(n - 1000)}".strip()
    if n < 1_000_000:
        return f"{_terbilang(n // 1000)} ribu {_terbilang(n % 1000)}".strip()
    if n < 1_000_000_000:
        return f"{_terbilang(n // 1_000_000)} juta {_terbilang(n % 1_000_000)}".strip()
    if n < 1_000_000_000_000:
        return f"{_terbilang(n // 1_000_000_000)} miliar {_terbilang(n % 1_000_000_000)}".strip()
    return f"{_terbilang(n // 1_000_000_000_000)} triliun {_terbilang(n % 1_000_000_000_000)}".strip()


def terbilang(n) -> str:
    try:
        words = " ".join(_terbilang(int(float(n or 0))).split())
    except (TypeError, ValueError):
        words = ""
    out = f"{words} rupiah" if words else "nol rupiah"
    return out[:1].upper() + out[1:]


# ─── MASTER TEMPLATE (Jinja2) ────────────────────────────────────────────────
MASTER_TEMPLATE = r"""
<!doctype html><html lang="id"><head><meta charset="utf-8"/>
<style>
  @page { size: {{ cfg.paper_size }} {{ cfg.orientation }}; margin: {{ cfg.margin_top }}mm {{ cfg.margin_right }}mm {{ cfg.margin_bottom }}mm {{ cfg.margin_left }}mm;
    {% if cfg.footer_text %}@bottom-center { content: "{{ cfg.footer_text }}"; font-size: 8pt; color:#888; }{% endif %}
  }
  * { box-sizing: border-box; }
  body { font-family: {{ cfg.font_family }}, Arial, sans-serif; color:#1a1a1a; font-size: {{ cfg.font_size }}pt; margin:0; position:relative; }
  {% if cfg.watermark_text or doc.watermark %}.watermark { position:fixed; top:42%; left:0; right:0; text-align:center; font-size:72pt; color:{{ cfg.color_primary }}; opacity:0.06; transform:rotate(-24deg); font-weight:800; z-index:0; }{% endif %}
  .content { position:relative; z-index:1; }
  .kop { display:flex; align-items:center; gap:14px; border-bottom:3px solid {{ cfg.color_primary }}; padding-bottom:10px; }
  .kop img { max-width:64px; max-height:64px; object-fit:contain; }
  .kop .co { font-size:16pt; font-weight:800; color:{{ cfg.color_primary }}; line-height:1.1; }
  .kop .addr { font-size:8.5pt; color:#555; margin-top:2px; }
  .doctitle { text-align:right; text-transform:uppercase; letter-spacing:1px; font-size:15pt; font-weight:800; color:{{ cfg.color_accent }}; margin:10px 0 2px; }
  .docno { text-align:right; font-size:9.5pt; color:#444; margin-bottom:8px; }
  .parties { display:flex; justify-content:space-between; gap:20px; margin:10px 0; }
  .party { font-size:9.5pt; }
  .party .lbl { font-size:8pt; text-transform:uppercase; color:#8a8a8a; letter-spacing:.4px; margin-bottom:2px; }
  .party .nm { font-weight:700; }
  .meta { display:grid; grid-template-columns:1fr 1fr; gap:2px 20px; margin:10px 0; font-size:9.5pt; }
  .meta .row { display:flex; gap:8px; }
  .meta .k { width:120px; color:#666; }
  .meta .v { font-weight:600; }
  table.items { width:100%; border-collapse:collapse; margin:10px 0; }
  table.items th, table.items td { border:1px solid #bbb; padding:5px 7px; font-size:9pt; }
  table.items th { background: {{ cfg.color_primary }}14; text-transform:uppercase; font-size:7.5pt; letter-spacing:.3px; color:#333; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  td.ctr, th.ctr { text-align:center; }
  .totals { margin-left:auto; width:46%; margin-top:6px; }
  .totals .row { display:flex; justify-content:space-between; padding:3px 0; font-size:9.5pt; }
  .totals .row.strong { border-top:2px solid #333; font-weight:800; font-size:11pt; margin-top:3px; padding-top:5px; color:{{ cfg.color_primary }}; }
  .terbilang { font-style:italic; color:#444; margin:8px 0; font-size:9pt; }
  .notes { margin-top:8px; font-size:9pt; color:#444; border-left:3px solid {{ cfg.color_primary }}44; padding-left:8px; }
  .signs { display:flex; justify-content:space-around; gap:12px; margin-top:34px; }
  .sign { text-align:center; font-size:8.5pt; flex:1; }
  .sign .role { font-weight:700; margin-bottom:2px; }
  .sign .space { height:56px; display:flex; align-items:center; justify-content:center; }
  .sign .space img { max-height:52px; max-width:120px; }
  .sign .nm { border-top:1px solid #333; padding-top:3px; }
  .esign { margin-top:16px; border:1.5px dashed {{ cfg.color_primary }}; border-radius:6px; padding:10px 12px; display:flex; gap:14px; align-items:center; background:{{ cfg.color_primary }}08; }
  .esign .qr img { width:84px; height:84px; }
  .esign .info { font-size:8.5pt; color:#333; }
  .esign .info b { color:{{ cfg.color_primary }}; }
  .status-chip { display:inline-block; border:1px solid #999; border-radius:4px; padding:1px 7px; font-size:8pt; text-transform:uppercase; letter-spacing:.4px; }
  /* FASE G-4 — kop wajib menyebut surat lain (blok jejak antar dokumen) */
  .refs { margin:8px 0 4px; border:1px solid {{ cfg.color_primary }}33; border-radius:6px; padding:7px 9px; display:flex; gap:10px; align-items:center; background:{{ cfg.color_primary }}0A; }
  .refs .qr img { width:60px; height:60px; display:block; }
  .refs .body { flex:1; font-size:8.5pt; color:#333; }
  .refs .ttl { font-size:7.5pt; text-transform:uppercase; letter-spacing:.4px; color:{{ cfg.color_primary }}; font-weight:800; margin-bottom:2px; }
  .refs .nums { font-weight:700; font-size:9.5pt; }
  .refs .rel { color:#666; }
  .refs .hint { color:#888; font-size:7.5pt; margin-top:2px; }
</style></head><body>
  {% if cfg.watermark_text or doc.watermark %}<div class="watermark">{{ cfg.watermark_text or doc.watermark }}</div>{% endif %}
  <div class="content">
    <div class="kop">
      {% if cfg.show_logo and branding.logo_src %}<img src="{{ branding.logo_src }}"/>{% endif %}
      <div style="flex:1">
        <div class="co">{{ branding.company_name }}</div>
        <div class="addr">{{ branding.address }}{% if branding.phone %} · Telp {{ branding.phone }}{% endif %}{% if branding.npwp %} · NPWP {{ branding.npwp }}{% endif %}</div>
      </div>
    </div>
    <div class="doctitle">{{ doc.title }}</div>
    <div class="docno">No. <b>{{ doc.number }}</b>{% if doc.date %} · {{ doc.date }}{% endif %}{% if doc.status %} · <span class="status-chip">{{ doc.status }}</span>{% endif %}</div>

    {% if doc.refs_block and doc.refs_block['items'] %}
    <div class="refs">
      {% if doc.refs_block.qr_src %}<div class="qr"><img src="{{ doc.refs_block.qr_src }}"/></div>{% endif %}
      <div class="body">
        <div class="ttl">Referensi Dokumen</div>
        <div class="nums">Merujuk: {{ doc.refs_block.text }}{% if doc.refs_block.hidden %} <span class="rel">+{{ doc.refs_block.hidden }} lainnya</span>{% endif %}</div>
        <div class="rel">{% for it in doc.refs_block['items'] %}{{ it.rel_label }} {{ it.label }} <b>{{ it.number }}</b>{% if not loop.last %} · {% endif %}{% endfor %}</div>
        {% if doc.refs_block.qr_src %}<div class="hint">Scan QR untuk membuka Jejak Dokumen (seluruh rantai surat terkait).{% if doc.refs_block.trace_url %} Atau buka: {{ doc.refs_block.trace_url }}{% endif %}</div>{% endif %}
      </div>
    </div>
    {% endif %}

    {% if doc.party_to %}
    <div class="parties">
      <div class="party"><div class="lbl">Dari</div><div class="nm">{{ branding.company_name }}</div><div>{{ branding.address }}</div></div>
      <div class="party" style="text-align:right"><div class="lbl">{{ doc.party_to.title or 'Kepada' }}</div><div class="nm">{{ doc.party_to.name }}</div>{% if doc.party_to.address %}<div>{{ doc.party_to.address }}</div>{% endif %}{% if doc.party_to.phone %}<div>{{ doc.party_to.phone }}</div>{% endif %}</div>
    </div>
    {% endif %}

    {% if doc.meta %}
    <div class="meta">
      {% for m in doc.meta %}<div class="row"><span class="k">{{ m.label }}</span><span class="v">{{ m.value }}</span></div>{% endfor %}
    </div>
    {% endif %}

    {% if doc.columns and doc['items'] %}
    <table class="items">
      <thead><tr>{% for c in doc.columns %}<th class="{{ c.align }}">{{ c.label }}</th>{% endfor %}</tr></thead>
      <tbody>
        {% for it in doc['items'] %}<tr>{% for c in doc.columns %}<td class="{{ c.align }}">{{ it.get(c.key, '') }}</td>{% endfor %}</tr>{% endfor %}
      </tbody>
    </table>
    {% endif %}

    {% if doc.totals %}
    <div class="totals">
      {% for t in doc.totals %}<div class="row {% if t.strong %}strong{% endif %}"><span>{{ t.label }}</span><span>{{ t.value }}</span></div>{% endfor %}
    </div>
    <div style="clear:both"></div>
    {% endif %}

    {% if cfg.show_terbilang and doc.terbilang %}<div class="terbilang">Terbilang: <b>{{ doc.terbilang }}</b></div>{% endif %}
    {% if doc.notes %}<div class="notes"><b>Catatan:</b> {{ doc.notes }}</div>{% endif %}

    {% if doc.signatures %}
    <div class="signs">
      {% for s in doc.signatures %}
      <div class="sign"><div class="role">{{ s.label }}</div><div class="space">{% if s.signature_src %}<img src="{{ s.signature_src }}"/>{% endif %}</div><div class="nm">{{ s.name or '(&nbsp;.................&nbsp;)' | safe }}{% if s.role %}<br/><span style="color:#888">{{ s.role }}</span>{% endif %}</div></div>
      {% endfor %}
    </div>
    {% endif %}

    {% if doc.esign %}
    <div class="esign">
      {% if doc.esign.qr_src %}<div class="qr"><img src="{{ doc.esign.qr_src }}"/></div>{% endif %}
      <div class="info">
        <div><b>DOKUMEN TERVERIFIKASI ELEKTRONIK</b></div>
        {% if doc.esign.people %}
        {% for p in doc.esign.people %}
        <div>Ditandatangani oleh: <b>{{ p.name }}</b>{% if p.role %} — {{ p.role }}{% endif %}{% if p.at %} · {{ p.at }}{% endif %}</div>
        {% endfor %}
        {% else %}
        <div>Ditandatangani oleh: <b>{{ doc.esign.signers }}</b></div>
        {% endif %}
        <div>Kode Verifikasi: <b>{{ doc.esign.code }}</b> · {{ doc.esign.signed_at }}</div>
        <div>Hash: {{ doc.esign.hash_short }}</div>
        <div style="color:#777">Scan QR / kunjungi {{ doc.esign.verify_url }} untuk memverifikasi keaslian.</div>
      </div>
    </div>
    {% endif %}
  </div>
</body></html>
"""

_env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html", "xml"]))
_tmpl = _env.from_string(MASTER_TEMPLATE)


def render_html(cfg: dict, branding: dict, doc: dict) -> str:
    return _tmpl.render(cfg=cfg, branding=branding, doc=doc)


# ─── Engine PDF (fallback chain) ─────────────────────────────────────────────
_ENGINE_CACHE: dict = {}


def render_pdf(html: str) -> tuple[bytes, str]:
    """Return (pdf_bytes, engine_used)."""
    # 1) WeasyPrint (utama)
    try:
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        if pdf and pdf[:4] == b"%PDF":
            return pdf, "weasyprint"
    except Exception as e:  # noqa: BLE001
        _ENGINE_CACHE["weasyprint_error"] = str(e)
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
        _ENGINE_CACHE["playwright_error"] = str(e)
    # 3) reportlab minimal
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 800, "PDF fallback (reportlab).")
    c.save()
    return buf.getvalue(), "reportlab"
