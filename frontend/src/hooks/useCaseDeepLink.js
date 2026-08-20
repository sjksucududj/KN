/**
 * useCaseDeepLink — FASE G-9 · state fokus untuk **Pusat Kasus Keuangan**.
 *
 * Layar mana pun bisa memanggil `openFinanceCase({ caseId })`
 * (lihat `features/finance/cases/caseDeepLink.js`) yang mengirim event global
 * `kn-open-finance-case` — pola yang sama dengan `kn-open-config` (G-0),
 * `kn-open-trace` (G-4), dan `kn-open-rnd` (FASE F).
 *
 * Hook ini mendengarkan event tersebut, meminta App berpindah view, lalu menyimpan
 * fokusnya. `nonce` membuat deep-link ke kasus yang SAMA dua kali berturut-turut
 * tetap memicu aksi (mis. petugas menekan "Buka kasus" lagi setelah kembali).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { CASE_EVENT } from "../features/finance/cases/caseDeepLink";

export default function useCaseDeepLink(onNavigate) {
  const [caseFocus, setCaseFocus] = useState(null);

  // Callback disimpan di ref supaya listener cukup dipasang SEKALI walau fungsi
  // navigasi dibuat ulang setiap render App.
  const navRef = useRef(onNavigate);
  navRef.current = onNavigate;

  useEffect(() => {
    const handler = (e) => {
      const d = (e && e.detail) || {};
      if (typeof navRef.current === "function") navRef.current();
      setCaseFocus({
        caseId: d.caseId || "", number: d.number || "", note: d.note || "",
        noteKind: d.noteKind || "success", nonce: Date.now(),
      });
    };
    window.addEventListener(CASE_EVENT, handler);
    return () => window.removeEventListener(CASE_EVENT, handler);
  }, []);

  const clearCaseFocus = useCallback(() => setCaseFocus(null), []);
  return [caseFocus, clearCaseFocus];
}
