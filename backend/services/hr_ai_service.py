"""H5 service — AI auto-tag motif via Anthropic Claude (SDK LANGSUNG, bukan Emergent).

Keputusan HR-Q5 (PLAN_HRD §10b): pakai paket `anthropic` langsung; key dari
`system_settings.integrations.anthropic`. Fitur GRACEFUL: bila key kosong / disabled
→ `autotag_image` kembalikan `{enabled: False}` (TIDAK meledak; galeri tetap jalan).

Vision: kirim gambar (base64) + prompt → Claude balas JSON {tags, summary, attributes}.
Pemanggilan SDK sinkron dibungkus thread (asyncio.to_thread) agar tak blok event loop.
"""
import asyncio
import base64
import json
import logging
from typing import Any, Dict

from services import integrations_service as integ

logger = logging.getLogger("hr_ai_service")

# Format gambar yang didukung Claude vision (subset storage lokal kita).
VISION_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/gif"}

SYSTEM_PROMPT = (
    "Anda asisten desain tekstil Indonesia. Anda diberi gambar MOTIF KAIN. "
    "Analisa motif, gaya, dan warna dominannya. "
    "Balas HANYA dengan satu objek JSON valid (tanpa teks lain), berstruktur:\n"
    '{\n'
    '  "tags": string[],            // 5-12 tag ringkas (mis. "batik", "floral", "geometris")\n'
    '  "summary": string,           // 1-2 kalimat deskripsi motif (Bahasa Indonesia)\n'
    '  "attributes": {\n'
    '    "motif_type": string,      // jenis motif utama\n'
    '    "dominant_colors": string[],\n'
    '    "style": string\n'
    '  }\n'
    '}\n'
    "Jangan tambahkan komentar atau penjelasan di luar JSON."
)


async def is_enabled() -> bool:
    """True bila integrasi Anthropic aktif DAN key terisi."""
    cfg = await integ.get_integrations()
    ant = cfg.get("anthropic", {})
    return bool(ant.get("enabled") and ant.get("api_key"))


def _parse_json(text: str) -> Dict[str, Any]:
    """Ekstrak JSON dari respons (toleran terhadap code-fence ```json)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    # ambil dari kurung kurawal pertama s/d terakhir
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        t = t[a:b + 1]
    return json.loads(t)


def _call_claude_sync(api_key: str, model: str, image_b64: str,
                      media_type: str, context: str) -> str:
    import anthropic  # lazy import (graceful bila paket belum ada)
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text":
                    f"Analisa motif kain ini dan balas JSON sesuai instruksi sistem. {context}".strip()},
            ],
        }],
    )
    parts = [getattr(b, "text", "") for b in (msg.content or [])
             if getattr(b, "type", None) == "text"]
    return "".join(parts)


async def autotag_image(image_bytes: bytes, content_type: str,
                        context: str = "") -> Dict[str, Any]:
    """Auto-tag motif via Claude vision. GRACEFUL.

    Return:
    - {enabled: False}                              → AI nonaktif/ key kosong.
    - {enabled: True, error: "..."}                 → aktif tapi gagal (format/SDK/API).
    - {enabled: True, model, tags[], summary, attributes, analyzed_at} → sukses.
    """
    cfg = await integ.get_integrations()
    ant = cfg.get("anthropic", {})
    if not (ant.get("enabled") and ant.get("api_key")):
        return {"enabled": False}
    media = (content_type or "").lower().split(";")[0].strip()
    if media not in VISION_MEDIA:
        return {"enabled": True, "error": f"Format {media or 'tidak dikenal'} tidak didukung AI vision."}
    model = ant.get("model") or integ.DEFAULT_MODEL
    try:
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        raw = await asyncio.to_thread(
            _call_claude_sync, ant["api_key"], model, image_b64, media, context)
        parsed = _parse_json(raw)
        from core_utils import now_iso
        return {
            "enabled": True,
            "model": model,
            "tags": [str(t) for t in (parsed.get("tags") or [])][:20],
            "summary": str(parsed.get("summary") or ""),
            "attributes": parsed.get("attributes") or {},
            "analyzed_at": now_iso(),
        }
    except Exception as e:  # noqa: BLE001 — JANGAN meledak; galeri harus tetap jalan
        logger.warning("[hr_ai] autotag gagal: %s", e)
        return {"enabled": True, "error": f"Analisa AI gagal: {e}"}
