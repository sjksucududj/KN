/**
 * useTraceDeepLink — FASE G-4 · state jangkar untuk layar **Jejak Dokumen**.
 *
 * Dua sumber jangkar:
 *   1. Event global `kn-open-trace` (tombol "Jejak Dokumen" di panel detail /
 *      Pusat Dokumen) — tanpa prop drilling.
 *   2. URL `/jejak-dokumen/{doc_type}/{doc_id}` — dipakai **QR pada dokumen cetak**.
 *      Halaman ini butuh login (RBAC `document:view`), jadi jangkar disimpan dulu
 *      dan tetap berlaku setelah user masuk.
 *
 * `nonce` membuat deep-link ke dokumen yang SAMA dua kali tetap memicu muat ulang.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { TRACE_EVENT, anchorFromLocation } from "../features/documents/trace/traceDeepLink";

export default function useTraceDeepLink(onNavigate, ready = true) {
  const [traceAnchor, setTraceAnchor] = useState(() => anchorFromLocation());

  const navRef = useRef(onNavigate);
  navRef.current = onNavigate;

  // Jangkar dari URL (QR dokumen cetak). Halaman ini di balik login, jadi navigasi
  // ditunda sampai `ready` (user sudah masuk) \u2014 kalau tidak, `login()` yang menetapkan
  // view default per role akan menimpa tujuan QR dan user mendarat di Beranda.
  const pendingUrl = useRef(Boolean(traceAnchor));
  useEffect(() => {
    if (!pendingUrl.current || !ready) return;
    pendingUrl.current = false;
    if (typeof navRef.current === "function") navRef.current();
    // Bersihkan path supaya refresh berikutnya tidak selalu melompat ke jejak.
    try { window.history.replaceState({}, "", "/"); } catch { /* noop */ }
  }, [ready]);

  useEffect(() => {
    const handler = (e) => {
      const d = (e && e.detail) || {};
      if (!d.docType || !d.docId) return;
      if (typeof navRef.current === "function") navRef.current();
      setTraceAnchor({ docType: d.docType, docId: d.docId, number: d.number || "", nonce: Date.now() });
    };
    window.addEventListener(TRACE_EVENT, handler);
    return () => window.removeEventListener(TRACE_EVENT, handler);
  }, []);

  const clearTraceAnchor = useCallback(() => setTraceAnchor(null), []);
  return [traceAnchor, clearTraceAnchor];
}
