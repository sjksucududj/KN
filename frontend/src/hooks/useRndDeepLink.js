/**
 * useRndDeepLink — FASE F · state fokus untuk hub **R&D & Desain**.
 *
 * Layar mana pun bisa memanggil `openRnd({ view, colorId, sampleNumber, ... })`
 * (lihat `features/rnd/rndDeepLink.js`) yang mengirim event global `kn-open-rnd` —
 * pola yang sama dengan `kn-open-config` (G-0) dan `kn-open-trace` (G-4).
 *
 * Hook ini yang mendengarkan event tersebut, meminta App berpindah view, lalu
 * menyimpan fokusnya. `nonce` membuat deep-link ke objek yang SAMA dua kali
 * berturut-turut tetap memicu aksi (mis. buka modal labdip lagi).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { RND_EVENT } from "../features/rnd/rndDeepLink";

export default function useRndDeepLink(onNavigate) {
  const [rndFocus, setRndFocus] = useState(null);

  // Callback disimpan di ref supaya listener cukup dipasang SEKALI walau fungsi
  // navigasi dibuat ulang setiap render App.
  const navRef = useRef(onNavigate);
  navRef.current = onNavigate;

  useEffect(() => {
    const handler = (e) => {
      const d = (e && e.detail) || {};
      const view = d.view || "rnd-samples";
      if (typeof navRef.current === "function") navRef.current(view);
      setRndFocus({ ...d, view, nonce: Date.now() });
    };
    window.addEventListener(RND_EVENT, handler);
    return () => window.removeEventListener(RND_EVENT, handler);
  }, []);

  const clearRndFocus = useCallback(() => setRndFocus(null), []);
  return [rndFocus, clearRndFocus];
}
