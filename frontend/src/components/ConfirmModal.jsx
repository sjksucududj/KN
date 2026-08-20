import { useState, useEffect, useRef } from "react";
import { overlayDismiss } from "@/utils/overlayDismiss";

/**
 * ConfirmModal — dialog konfirmasi generik (pengganti `window.confirm` / `window.prompt`).
 * Mendukung input alasan opsional (untuk aksi seperti tolak / tutup-kurang / batalkan).
 *
 * Biasanya TIDAK dipakai langsung: panggil `askConfirm()` / `askReason()` / `askText()`
 * dari `services/confirmService.js` — satu instansi dialog sudah dirender di root oleh
 * `components/ConfirmHost.jsx`. Pemakaian langsung tetap didukung untuk layar yang
 * memang perlu mengelola sendiri (mis. dialog dengan isi khusus).
 *
 * Props:
 *  - open, title, message
 *  - confirmLabel, cancelLabel, danger (warna tombol konfirmasi)
 *  - withReason, reasonLabel, reasonRequired, reasonPlaceholder
 *  - choices: [{key,label,description,danger}] → mode PILIHAN (FASE P6): setiap jawaban
 *    dapat tombolnya sendiri, dipakai `askChoice()`. Saat mode ini aktif tombol
 *    "Konfirmasi" tidak dirender — yang ada hanya pilihan-pilihan + Batal.
 *  - onChoose(key) -> dipanggil saat salah satu pilihan ditekan
 *  - inputType: "textarea" (baku) | "text" | "password"  ← FASE P5, menggantikan
 *    `window.prompt`. "password" menyamarkan karakter; `prompt()` tidak bisa.
 *  - onConfirm(reason) -> boleh async; busy state dikelola di sini
 *  - onCancel()
 *  - testId (prefix data-testid)
 *
 * Yang sudah dibereskan di satu tempat (FASE P5) supaya tiap pemanggil tidak
 * menyelesaikannya sendiri dengan cara berbeda:
 *  · **Esc menutup** (setara menekan Batal) — kecuali sedang memproses.
 *  · **Fokus otomatis** ke isian alasan bila ada, kalau tidak ke tombol konfirmasi,
 *    sehingga Enter langsung bekerja bagi pengguna keyboard.
 *  · **Backdrop pakai `overlayDismiss()`** (INV-UI-01: memilih opsi dropdown ber-portal
 *    Radix tidak boleh menutup dialog).
 *  · **Selalu di lapisan paling atas** (z-index inline 90 > `.modal-overlay` 60), karena
 *    dialog ini hampir selalu muncul DI ATAS modal lain — mis. "Batalkan transfer?" yang
 *    ditekan dari dalam modal detail transfer. Tanpa ini, pertanyaannya bersembunyi di
 *    belakang modal induk dan tombol tampak mati.
 *  · **Scroll halaman di belakang dikunci** selama dialog terbuka.
 */
export default function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Konfirmasi",
  cancelLabel = "Batal",
  danger = false,
  withReason = false,
  reasonLabel = "Alasan",
  reasonRequired = true,
  reasonPlaceholder = "",
  inputType = "textarea",
  choices = null,
  onChoose,
  onConfirm,
  onCancel,
  testId = "confirm-modal",
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  const confirmRef = useRef(null);
  const firstChoiceRef = useRef(null);
  const hasChoices = Array.isArray(choices) && choices.length > 0;

  useEffect(() => {
    if (open) { setReason(""); setBusy(false); }
  }, [open]);

  // Esc = Batal + kunci scroll latar (sama seperti FormModal, supaya perilaku pop-up
  // di aplikasi ini hanya ada SATU macam).
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape" && !busy) onCancel?.(); };
    document.addEventListener("keydown", onKey);
    const sebelumnya = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = sebelumnya;
    };
  }, [open, busy, onCancel]);

  // Fokus otomatis: isian alasan bila ada, lalu pilihan pertama (mode PILIHAN — tombol
  // "Konfirmasi" tidak dirender di mode itu, jadi tanpa ini tak ada yang menerima fokus
  // dan Enter/Tab pengguna keyboard jatuh ke luar dialog), kalau tidak tombol konfirmasi.
  useEffect(() => {
    if (!open) return undefined;
    const t = setTimeout(() => {
      (inputRef.current || firstChoiceRef.current || confirmRef.current)?.focus();
    }, 50);
    return () => clearTimeout(t);
  }, [open]);

  if (!open) return null;

  const blocked = busy || (withReason && reasonRequired && !reason.trim());

  async function handleConfirm() {
    if (blocked) return;
    setBusy(true);
    try {
      await onConfirm?.(reason.trim());
    } finally {
      setBusy(false);
    }
  }

  async function handleChoose(key) {
    if (busy) return;
    setBusy(true);
    try {
      await onChoose?.(key);
    } finally {
      setBusy(false);
    }
  }

  // Enter pada isian satu baris = konfirmasi (kebiasaan `prompt()` yang memang enak).
  function onInputKeyDown(e) {
    if (inputType !== "textarea" && e.key === "Enter") {
      e.preventDefault();
      handleConfirm();
    }
  }

  return (
    <div className="modal-overlay" style={{ zIndex: 90 }} data-testid={testId} {...overlayDismiss(busy ? undefined : onCancel)}>
      <div className="modal-card small" role="dialog" aria-modal="true" aria-label={title}>
        <p className="modal-title">{title}</p>
        {message && <p className="modal-subtitle" data-testid={`${testId}-message`}>{message}</p>}
        {withReason && (
          <div className="grid gap-1.5 mt-2">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]" htmlFor={`${testId}-reason`}>
              {reasonLabel}{reasonRequired ? " *" : ""}
            </label>
            {inputType === "textarea" ? (
              <textarea
                id={`${testId}-reason`}
                ref={inputRef}
                data-testid={`${testId}-reason`}
                className="form-input"
                rows="3"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={reasonPlaceholder}
              />
            ) : (
              <input
                id={`${testId}-reason`}
                ref={inputRef}
                data-testid={`${testId}-reason`}
                type={inputType === "password" ? "password" : "text"}
                className="form-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                onKeyDown={onInputKeyDown}
                placeholder={reasonPlaceholder}
                autoComplete={inputType === "password" ? "current-password" : "off"}
              />
            )}
          </div>
        )}
        {hasChoices && (
          <div className="grid gap-2 mt-3" data-testid={`${testId}-choices`}>
            {choices.map((c, i) => (
              <button
                key={c.key}
                ref={i === 0 ? firstChoiceRef : undefined}
                type="button"
                data-testid={`${testId}-choice-${c.key}`}
                disabled={busy}
                onClick={() => handleChoose(c.key)}
                className={`w-full rounded-lg border px-3 py-2 text-left transition-colors
                  disabled:opacity-50 disabled:cursor-not-allowed ${
                  c.danger
                    ? "border-[#F3C7C4] bg-[#FDF3F2] hover:border-[#C0241B]"
                    : "border-[#E5E5EA] bg-white hover:border-[#007AFF] hover:bg-[#F5F9FF]"
                }`}
              >
                <span className="block text-[12.5px] font-bold text-[#1C1C1E]">{c.label}</span>
                {c.description && (
                  <span className="mt-0.5 block text-[10.5px] leading-snug text-[#6B6B73]">
                    {c.description}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
        <div className="modal-actions">
          <button className="btn-secondary" onClick={onCancel} disabled={busy}
            data-testid={`${testId}-cancel`}>{cancelLabel}</button>
          {!hasChoices && (
            <button
              ref={confirmRef}
              data-testid={`${testId}-confirm`}
              className={danger ? "btn-danger" : "btn-primary"}
              onClick={handleConfirm}
              disabled={blocked}
            >
              {busy ? "Memproses…" : confirmLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
