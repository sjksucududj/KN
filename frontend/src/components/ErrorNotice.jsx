import { useEffect, useRef } from "react";
import { RefreshCw } from "lucide-react";
import { apiErrorText } from "../utils/apiError";

/**
 * ErrorNotice — bilah error konsisten dengan tombol "Coba lagi" (retry) opsional.
 * Dipakai di seluruh aplikasi agar kegagalan bisa dicoba ulang tanpa reload halaman
 * (sesuai KN_08 — error state harus punya retry).
 *
 * KONTRAK PROP (dijaga `scripts/guardrails/verify_error_notice.py` · INV-UI-03):
 *   · `message`  — WAJIB. Boleh string, boleh objek error axios/Error: dinormalkan di
 *                  sini lewat `utils/apiError.apiErrorText`.
 *   · `onRetry`  — opsional, memunculkan tombol "Coba lagi".
 *   · `onAction`/`actionLabel` — opsional, satu tombol lanjutan yang MENUNTUN
 *                  (mis. "Buka kasusnya" saat backend menolak karena kasusnya sudah ada).
 *   · `onDismiss`— opsional, tombol tutup.
 *
 * KENAPA IA MENERIMA OBJEK JUGA (pertahanan berlapis, bug KN-G9-ERR-SILENT):
 *   Dulu komponen ini hanya menerima string dan `return null` bila kosong. Layar G-8/G-9
 *   mengirim objek error axios lewat prop bernama `error` → `message` undefined → bilah
 *   TIDAK PERNAH tampil, sehingga setiap penolakan backend (alasan wajib, bukti wajib,
 *   entitas lain, kasus kembar) hilang tanpa jejak di layar. Sekarang: nama prop salah
 *   ditangkap guardrail, dan objek error tetap dirender jadi kalimat manusia.
 */
export default function ErrorNotice({ message, onRetry, onDismiss, onAction, actionLabel,
  testId = "error-notice" }) {
  const text = typeof message === "string" ? message : apiErrorText(message, "");
  const ref = useRef(null);

  // FASE P5 — bilah galat tidak boleh "ada tapi tak terlihat".
  // Keputusan pemilik: kegagalan tampil sebagai bilah yang MENEMPEL (bukan toast yang
  // hilang sendiri). Konsekuensinya bilah itu sering berada di ATAS halaman sementara
  // pengguna sedang bekerja di bagian bawah (mis. panel pindai gudang, tabel panjang) —
  // pesannya ada, tapi di luar pandangan, jadi efeknya sama saja dengan senyap.
  // `block: "nearest"` = geser SEMINIMAL mungkin: kalau bilah sudah terlihat, layar
  // tidak bergerak sama sekali.
  useEffect(() => {
    if (!text) return;
    ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [text]);

  if (!text) return null;
  return (
    <div ref={ref} className="notice-bar danger" data-testid={testId}>
      <span>{text}</span>
      <span style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center" }}>
        {onAction && actionLabel && (
          <button data-testid={`${testId}-action`} onClick={onAction}
            style={{ marginLeft: 0, fontWeight: 700 }}>
            {actionLabel}
          </button>
        )}
        {onRetry && (
          <button data-testid={`${testId}-retry`} onClick={onRetry}
            style={{ marginLeft: 0, fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 4 }}>
            <RefreshCw size={12} /> Coba lagi
          </button>
        )}
        {onDismiss && <button onClick={onDismiss} style={{ marginLeft: 0 }}>×</button>}
      </span>
    </div>
  );
}
