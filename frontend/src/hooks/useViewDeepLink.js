/**
 * useViewDeepLink — deep-link UNIVERSAL `?view=<viewId>[&tab=<tab>][&entity=<entityId>]`.
 *
 * KENAPA ADA (FASE E-4):
 * SPA ini sengaja dibangun tanpa react-router: seluruh navigasi lewat state `activeView`
 * di `App.js`. Konsekuensinya SATU layar tidak punya alamat — pengguna tidak bisa
 * mem-bookmark "Pricelist per-PT", tidak bisa mengirim tautan ke rekan ("buka layar ini"),
 * menyegarkan halaman selalu melempar balik ke halaman depan peran, dan alat uji otomatis
 * tidak punya jalan masuk selain menebak-nebak klik menu. Iterasi uji 213 gagal 70% justru
 * karena hal terakhir ini.
 *
 * Yang dilakukan hook ini — SATU arah baca, SATU arah tulis:
 *   1. BACA (sekali, setelah pengguna masuk): `?view=md-warehouses` → pindah ke layar itu.
 *      Nilai divalidasi terhadap menu peran (`resolveDeepLinkTarget`) sehingga tautan
 *      ke layar yang tidak boleh dilihat peran ini diabaikan begitu saja — bukan pintu
 *      belakang RBAC (server tetap penjaga terakhir).
 *   2. TULIS: setiap kali layar aktif berganti, alamat disegarkan dengan `replaceState`
 *      supaya bilah alamat selalu mencerminkan layar yang dilihat (bisa dibagikan).
 *      `replaceState` DIPILIH sadar: `pushState` akan menumpuk riwayat sehingga tombol
 *      "kembali" pada peramban terasa rusak (harus ditekan 10× untuk keluar).
 *
 * CATATAN: hook deep-link khusus yang sudah ada (`useConfigDeepLink`, `useTraceDeepLink`,
 * `useRndDeepLink`, `useCaseDeepLink`) tidak diganggu — parameter lain di query string
 * dipertahankan apa adanya.
 */
import { useEffect, useRef } from "react";
import { resolveDeepLinkTarget } from "../config/navigationConfig";

const ENTITY_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

export default function useViewDeepLink({ role, ready, activeView, onNavigate, onPickEntity }) {
  const consumed = useRef(false);
  const navRef = useRef(onNavigate);
  const entRef = useRef(onPickEntity);
  navRef.current = onNavigate;
  entRef.current = onPickEntity;

  // ─── 1) BACA alamat sekali saat sesi siap ──────────────────────────────────
  useEffect(() => {
    if (!ready || consumed.current) return;
    consumed.current = true;
    let params;
    try {
      params = new URLSearchParams(window.location.search);
    } catch (_) {
      return;
    }
    // Badan usaha aktif boleh ikut ditautkan (mis. tautan "lihat Pricelist Kanda").
    const ent = params.get("entity");
    if (ent && ENTITY_ID_RE.test(ent)) entRef.current?.(ent);

    const wanted = params.get("view");
    if (!wanted) return;
    const target = resolveDeepLinkTarget(wanted, role);
    if (!target) return;
    navRef.current?.(target.navId, target.view, params.get("tab") || target.tab);
  }, [ready, role]);

  // ─── 2) TULIS alamat agar layar aktif selalu bisa dibagikan ────────────────
  useEffect(() => {
    if (!ready || !activeView) return;
    try {
      const url = new URL(window.location.href);
      // Halaman verifikasi dokumen publik punya path sendiri — jangan disentuh.
      if (url.pathname.startsWith("/verify-document/")) return;
      if (url.searchParams.get("view") === activeView) return;
      url.searchParams.set("view", activeView);
      window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    } catch (_) {
      /* peramban tanpa History API — abaikan, navigasi tetap jalan */
    }
  }, [ready, activeView]);
}
