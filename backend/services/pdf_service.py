"""
pdf_service.py — Orkestrasi render dokumen: template config + branding entitas +
resolver context + (opsional) blok e-sign → HTML → PDF.
"""
from __future__ import annotations
import base64
import io
from db import db
from services.pdf_engine import render_html, render_pdf
from services.pdf_resolvers import DOC_REGISTRY

# ─── Default template config per dokumen ─────────────────────────────────────
DEFAULT_TEMPLATE_CFG = {
    "paper_size": "A4", "orientation": "portrait",
    "margin_top": 16, "margin_right": 14, "margin_bottom": 16, "margin_left": 14,
    "font_family": "'DejaVu Sans'", "font_size": 10,
    "color_primary": "#0058CC", "color_accent": "#1a1a1a",
    "show_logo": True, "show_terbilang": True,
    "watermark_text": "", "footer_text": "",
    "title_override": "",
    "custom_fields": [],       # [{label, value}]
    "signature_slots": [],     # override doc.signatures bila diisi [{label, role, name}]
    "hidden_fields": [],       # label meta yang disembunyikan
}


def qr_data_url(payload: str) -> str:
    import qrcode
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def get_template_cfg(doc_type: str) -> dict:
    row = await db.pdf_templates.find_one({"doc_type": doc_type}, {"_id": 0})
    cfg = dict(DEFAULT_TEMPLATE_CFG)
    if row and isinstance(row.get("config"), dict):
        cfg.update(row["config"])
    return cfg


async def save_template_cfg(doc_type: str, config: dict, actor: str = "") -> dict:
    clean = dict(DEFAULT_TEMPLATE_CFG)
    clean.update({k: v for k, v in (config or {}).items() if k in DEFAULT_TEMPLATE_CFG})
    await db.pdf_templates.update_one(
        {"doc_type": doc_type},
        {"$set": {"doc_type": doc_type, "config": clean, "updated_by": actor}},
        upsert=True,
    )
    return clean


async def get_branding(entity_id: str | None) -> dict:
    ent = await db.business_entities.find_one({"id": entity_id}, {"_id": 0}) if entity_id else None
    ent = ent or {}
    row = await db.document_branding.find_one({"entity_id": entity_id}, {"_id": 0}) if entity_id else None
    row = row or {}
    logo_src = ""
    if row.get("logo_b64"):
        logo_src = f"data:image/png;base64,{row['logo_b64']}" if not str(row["logo_b64"]).startswith("data:") else row["logo_b64"]
    elif ent.get("logo_url"):
        logo_src = ent["logo_url"]
    addr = row.get("address") or ", ".join(x for x in [ent.get("address"), ent.get("city")] if x)
    return {
        "entity_id": entity_id,
        "company_name": row.get("company_name") or ent.get("legal_name") or ent.get("short_name") or "Perusahaan",
        "address": addr or "-",
        "phone": row.get("phone") or "",
        "npwp": row.get("npwp") or ent.get("npwp") or "",
        "logo_src": logo_src,
        "signatures": row.get("signatures") or [],   # [{label, role, name, signature_b64}]
    }


async def save_branding(entity_id: str, data: dict, actor: str = "") -> dict:
    allowed = {k: data.get(k) for k in ["company_name", "address", "phone", "npwp", "logo_b64", "signatures"]}
    await db.document_branding.update_one(
        {"entity_id": entity_id},
        {"$set": {"entity_id": entity_id, **allowed, "updated_by": actor}},
        upsert=True,
    )
    return await get_branding(entity_id)


def _apply_cfg_to_doc(doc: dict, cfg: dict, branding: dict) -> dict:
    if cfg.get("title_override"):
        doc["title"] = cfg["title_override"]
    # custom fields → tambah ke meta
    meta = list(doc.get("meta") or [])
    for cf in cfg.get("custom_fields") or []:
        if cf.get("label"):
            meta.append({"label": cf["label"], "value": cf.get("value", "")})
    # sembunyikan field tertentu
    hidden = set(cfg.get("hidden_fields") or [])
    doc["meta"] = [m for m in meta if m["label"] not in hidden]
    # override signature slots dari config, jika tidak ada pakai default doc + isi nama dari branding
    if cfg.get("signature_slots"):
        doc["signatures"] = cfg["signature_slots"]
    # tempel gambar TTD dari branding (match by role/label)
    brand_sig = {(s.get("role") or s.get("label") or "").lower(): s for s in (branding.get("signatures") or [])}
    for s in doc.get("signatures") or []:
        key = (s.get("role") or s.get("label") or "").lower()
        if key in brand_sig and brand_sig[key].get("signature_b64"):
            b = brand_sig[key]["signature_b64"]
            s["signature_src"] = b if str(b).startswith("data:") else f"data:image/png;base64,{b}"
            if not s.get("name") and brand_sig[key].get("name"):
                s["name"] = brand_sig[key]["name"]
    return doc


async def _attach_esign(doc: dict, doc_type: str, source_id: str, public_base: str):
    """Bila ada tanda tangan elektronik final → tempel blok e-sign + QR ke dokumen."""
    sigs = await db.document_signatures.find(
        {"doc_type": doc_type, "source_id": source_id, "status": "signed"}, {"_id": 0}
    ).sort("signed_at", 1).to_list(20)
    if not sigs:
        return doc
    last = sigs[-1]
    code = last.get("verification_code")
    verify_url = f"{public_base}/verify-document/{code}"
    # FASE G-4 — blok tanda tangan harus BERNAMA: siapa, JABATAN apa, dan KAPAN.
    # Nama saja tidak cukup untuk dokumen kertas yang dipegang pihak luar.
    people = []
    for s in sigs:
        people.append({
            "name": s.get("signer_name") or "-",
            "role": s.get("signer_role") or "",
            "at": (s.get("signed_at") or "")[:19].replace("T", " "),
        })
    doc["esign"] = {
        "code": code,
        "signers": ", ".join(p["name"] for p in people),
        "people": people,
        "signed_at": (last.get("signed_at") or "")[:19].replace("T", " "),
        "hash_short": (last.get("doc_hash") or "")[:24] + "…",
        "verify_url": verify_url,
        "qr_src": qr_data_url(verify_url),
    }
    return doc


async def attach_document_refs(doc: dict, doc_type: str, source_id: str,
                               source: dict, public_base: str) -> dict:
    """FASE G-4 — tempelkan blok **Referensi Dokumen** (+ QR Jejak Dokumen).

    Dipasang di SATU tempat (bukan di 21 resolver) supaya setiap dokumen cetak —
    apa pun jenisnya — otomatis menyebut surat-surat yang berkaitan. Tanpa ini,
    penerima kertas tidak bisa menghubungkan Surat Jalan dengan pesanannya.

    Aturannya configurable lewat Pusat Pengaturan (kelompok "Dokumen, Referensi &
    Tanda Tangan"): tampil/tidak, pakai QR/tidak, dan berapa nomor yang dicetak.

    Kunci yang mengatur blok ini (dibaca lewat `doc_refs_service.pdf_options`):
    `docref.show_in_pdf` · `docref.qr_in_pdf` · `docref.pdf_max_refs`.
    """
    from services import doc_refs_service as refs

    entity_id = source.get("entity_id") or ""
    try:
        opts = await refs.pdf_options(entity_id)
    except Exception:  # noqa: BLE001 — konfigurasi belum ter-seed → pakai bawaan aman
        opts = {"show": True, "qr": True, "max": 6}
    if not opts.get("show"):
        return doc

    # doc_type PDF bisa berbagi koleksi (invoice/delivery_note/picking_list → sales_orders);
    # relasi selalu dibaca dari doc_type KANONIK koleksinya.
    reg = DOC_REGISTRY.get(doc_type) or {}
    canon = (doc_type if doc_type in refs.DOC_TYPES
             else refs.type_of_collection(reg.get("collection", "")))
    if not canon:
        return doc
    line = await refs.reference_line(canon, source_id, limit=int(opts.get("max") or 6))
    if not line.get("items"):
        return doc
    trace_url = f"{public_base}/jejak-dokumen/{canon}/{source_id}" if public_base else ""
    doc["refs_block"] = {
        "text": line["text"],
        "items": line["items"],
        "hidden": line.get("hidden", 0),
        "trace_url": trace_url,
        "qr_src": qr_data_url(trace_url) if (opts.get("qr") and trace_url) else "",
    }
    return doc


async def build_document(doc_type: str, source_id: str, entity_id: str | None,
                         cfg_override: dict | None = None, public_base: str = "") -> dict:
    """Return {source, cfg, branding, doc} — dipakai render html/pdf.

    FASE G-4 — `public_base` kosong (render dari job/penjadwal/WhatsApp/skrip) TIDAK
    boleh menghasilkan QR tanpa host: kertas yang dipegang orang jadi tidak bisa
    dibuka. Karena itu di sini ada fallback ke URL aplikasi yang terkonfigurasi.
    """
    from services.app_url import configured_app_url
    public_base = (public_base or configured_app_url() or "").rstrip("/")
    reg = DOC_REGISTRY.get(doc_type)
    if not reg:
        raise ValueError(f"doc_type '{doc_type}' tidak dikenal")
    source = await db[reg["collection"]].find_one({"id": source_id}, {"_id": 0})
    if not source:
        raise LookupError(f"Dokumen sumber {doc_type}/{source_id} tidak ditemukan")
    eid = entity_id or source.get("entity_id")
    # FASE G-0 — `finance.base_currency` kini benar-benar dipakai: seluruh nominal pada
    # dokumen cetak (invoice, surat jalan, PO) mengikuti mata uang pembukuan entitas.
    from services.config_currency import base_currency
    from services.pdf_engine import set_document_currency
    set_document_currency(await base_currency(eid))
    cfg = await get_template_cfg(doc_type)
    if cfg_override:
        cfg.update({k: v for k, v in cfg_override.items() if k in DEFAULT_TEMPLATE_CFG})
    branding = await get_branding(eid)
    doc = await reg["resolver"](source, db)
    doc = _apply_cfg_to_doc(doc, cfg, branding)
    doc = await _attach_esign(doc, doc_type, source_id, public_base)
    doc = await attach_document_refs(doc, doc_type, source_id, source, public_base)
    return {"source": source, "cfg": cfg, "branding": branding, "doc": doc, "reg": reg}


async def render_document(doc_type: str, source_id: str, entity_id: str | None,
                          fmt: str = "pdf", cfg_override: dict | None = None, public_base: str = ""):
    built = await build_document(doc_type, source_id, entity_id, cfg_override, public_base)
    html = render_html(built["cfg"], built["branding"], built["doc"])
    if fmt == "html":
        return html, "text/html", built
    pdf, engine = render_pdf(html)
    return pdf, "application/pdf", built
