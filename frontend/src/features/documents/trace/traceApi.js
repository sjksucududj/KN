/**
 * traceApi — FASE G-4 · jembatan tipis ke endpoint **Relasi & Jejak Dokumen**.
 *
 * Sengaja TANPA React (pola `amendmentApi.js`) supaya panel detail mana pun bisa
 * mengimpornya tanpa menarik bundel layar Jejak Dokumen.
 *
 * Yang dicerminkan dari backend (`services/doc_refs_service.py`):
 *   relasi antar surat DISIMPAN dua arah di `refs[]`, sehingga penelusuran bisa
 *   dimulai dari dokumen mana pun — termasuk dari tengah rantai (Kwitansi, Nota).
 */
import axios, { API } from "../../../services/apiClient";

/** Relasi yang berarti "saya lahir dari dokumen itu" (arah ke hulu / asal-usul). */
export const UPSTREAM_RELS = [
  "parent", "amends", "corrects", "reverses", "settles", "fulfills", "issued_by",
  "replaces",
];

/** Nada warna per keluarga relasi — memakai palet yang sudah dipakai repo. */
export const REL_TONE = {
  upstream: { fg: "#0058CC", bg: "#EFF4FF", label: "Asal-usul" },
  downstream: { fg: "#1B7A43", bg: "#E5F6EC", label: "Turunan" },
  correction: { fg: "#9B1C1C", bg: "#FDE2E2", label: "Koreksi" },
};

export function relFamily(rel) {
  if (["corrects", "corrected_by", "reverses", "reversed_by", "amends", "amended_by",
    "replaces", "replaced_by"].includes(rel)) return "correction";
  return UPSTREAM_RELS.includes(rel) ? "upstream" : "downstream";
}

export function relTone(rel) {
  return REL_TONE[relFamily(rel)] || REL_TONE.downstream;
}

/** Pesan galat yang bisa dibaca user (backend selalu mengirim `detail`). */
export function errText(e, fallback = "Terjadi kesalahan.") {
  return e?.response?.data?.detail || e?.message || fallback;
}

// ── Panggilan API ───────────────────────────────────────────────────────────
export async function fetchTrace(docType, docId, depth = 0) {
  const r = await axios.get(`${API}/documents/trace/${docType}/${docId}`, {
    params: depth ? { depth } : {},
  });
  return r.data || {};
}

export async function fetchRefs(docType, docId) {
  const r = await axios.get(`${API}/documents/refs/${docType}/${docId}`);
  return r.data || { refs: [] };
}

export async function searchDocs(q, entityId = "", limit = 20) {
  const r = await axios.get(`${API}/documents/trace-search`, {
    params: { q, limit, ...(entityId && entityId !== "all" ? { entity_id: entityId } : {}) },
  });
  return Array.isArray(r.data) ? r.data : [];
}

export async function fetchRefTypes() {
  const r = await axios.get(`${API}/documents/ref-types`);
  return r.data || { types: [], rel_labels: {} };
}

/** Backfill relasi dokumen lama. `dry_run=true` TIDAK mengubah apa pun. */
export async function runBackfill(dryRun = true) {
  const r = await axios.post(`${API}/documents/refs/backfill`, null, {
    params: { dry_run: dryRun },
  });
  return r.data || {};
}

// ── Util tampilan ───────────────────────────────────────────────────────────
export function when(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" });
  } catch { return String(iso); }
}

export function shortDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("id-ID", { dateStyle: "medium" }); }
  catch { return String(iso); }
}

/** Tautan publik (dipakai QR pada dokumen cetak) ke layar Jejak Dokumen. */
export function traceUrl(docType, docId) {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/jejak-dokumen/${docType}/${docId}`;
}
