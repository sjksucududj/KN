/**
 * useDeepLinks — satu pintu semua **deep-link global** aplikasi.
 *
 * KENAPA DIGABUNG: repo ini punya beberapa jembatan "buka layar X dari mana pun" yang
 * polanya identik (event global + `nonce` + minta App berpindah view):
 *   · `kn-open-config`       → Pusat Pengaturan       (FASE G-0)
 *   · `kn-open-trace`        → Jejak Dokumen          (FASE G-4)
 *   · `kn-open-rnd`          → hub R&D & Desain       (FASE F)
 *   · `kn-open-finance-case` → Pusat Kasus Keuangan   (FASE G-9)
 * Menyatukannya membuat App.js tidak menumpuk boilerplate yang sama berkali-kali, dan
 * penambahan deep-link berikutnya cukup di SATU tempat.
 *
 * Catatan urutan hook: semuanya dipanggil dengan urutan tetap, jadi aman dipakai
 * di dalam komponen (aturan hooks tidak dilanggar).
 */
import useConfigDeepLink from "./useConfigDeepLink";
import useRndDeepLink from "./useRndDeepLink";
import useTraceDeepLink from "./useTraceDeepLink";
import useCaseDeepLink from "./useCaseDeepLink";

export default function useDeepLinks({ setActiveNavId, setActiveView, setSidebarOpen, ready }) {
  const go = (navId, view) => {
    setActiveNavId(navId);
    setActiveView(view);
    setSidebarOpen(false);
  };
  const [configFocus, clearConfigFocus] = useConfigDeepLink(
    () => go("settings-hub", "settings-config"));
  // Jangkar dari QR dokumen cetak baru boleh dibuka setelah login (`ready`).
  const [traceAnchor, clearTraceAnchor] = useTraceDeepLink(
    () => go("document-center", "doc-trace"), ready);
  const [rndFocus, clearRndFocus] = useRndDeepLink(
    (view) => go("rnd-hub", view || "rnd-samples"));
  const [caseFocus, clearCaseFocus] = useCaseDeepLink(
    () => go("finance-cases", "finance-cases"));

  return {
    configFocus, clearConfigFocus,
    traceAnchor, clearTraceAnchor,
    rndFocus, clearRndFocus,
    caseFocus, clearCaseFocus,
  };
}
