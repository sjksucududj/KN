/**
 * useConfigDeepLink — FASE G-0 · state fokus untuk Pusat Pengaturan.
 *
 * Editor konfigurasi lama sudah DIHAPUS. Sebagai gantinya, layar mana pun bisa
 * memanggil `openConfig({ key })` (lihat `features/settings/config/configDeepLink.js`)
 * yang mengirim event global `kn-open-config` — pola yang sama dengan
 * `kn-open-palette` untuk Command Palette.
 *
 * Hook ini yang mendengarkan event tersebut, meminta App berpindah view, dan
 * menyimpan fokusnya. `nonce` membuat deep-link ke kunci yang SAMA dua kali
 * berturut-turut tetap memicu fokus ulang.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { CONFIG_EVENT, groupForKey } from "../features/settings/config/configDeepLink";

export default function useConfigDeepLink(onNavigate) {
  const [configFocus, setConfigFocus] = useState(null);

  // Simpan callback di ref supaya listener cukup dipasang SEKALI, walau fungsi
  // navigasi dibuat ulang pada setiap render App.
  const navRef = useRef(onNavigate);
  navRef.current = onNavigate;

  useEffect(() => {
    const handler = (e) => {
      const detail = (e && e.detail) || {};
      const key = detail.key || "";
      if (typeof navRef.current === "function") navRef.current();
      setConfigFocus({ key, group: detail.group || groupForKey(key), nonce: Date.now() });
    };
    window.addEventListener(CONFIG_EVENT, handler);
    return () => window.removeEventListener(CONFIG_EVENT, handler);
  }, []);

  const clearConfigFocus = useCallback(() => setConfigFocus(null), []);
  return [configFocus, clearConfigFocus];
}
