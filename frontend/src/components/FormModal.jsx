import { useEffect, useRef } from "react";
import { X, Loader2 } from "lucide-react";
import { overlayDismiss } from "@/utils/overlayDismiss";

/**
 * FormModal — **standar pop-up "Buat/Ubah"** untuk seluruh layar KN (FASE P4).
 *
 * MASALAH YANG DISELESAIKAN (PERF_UX_AUDIT.md §P4, keluhan pemilik)
 * ================================================================
 * Tombol "+ Buat" dulu berperilaku tiga cara berbeda: memunculkan pop-up, MENYELIPKAN
 * form di tengah halaman (daftar data terdorong ke bawah — pengguna sering tak sadar
 * formnya terbuka di bawah lipatan lalu menyimpulkan "tombolnya tidak berfungsi"), atau
 * pindah halaman penuh. Komponen ini menjadikan pop-up sebagai perilaku BAKU sehingga
 * konteks (tabel/daftar di belakang) tidak pernah hilang.
 *
 * Yang sudah dibereskan di satu tempat — supaya tiap layar tidak menyelesaikannya sendiri
 * dengan cara berbeda:
 *  · **Tak tertutup salah** — backdrop memakai `overlayDismiss()` (INV-UI-01: memilih opsi
 *    pada dropdown ber-portal Radix TIDAK boleh menutup modal & membuang isian pengguna).
 *  · **Esc menutup**, dan fokus otomatis pindah ke isian pertama (tanpa itu pengguna
 *    keyboard harus men-tab dari awal halaman).
 *  · **Halaman di belakang tidak bisa ikut ter-scroll** (`overflow: hidden` saat terbuka).
 *  · **Isi panjang tetap terbaca**: badan modal yang bisa di-scroll, kepala & tombol aksi
 *    menempel (sticky) sehingga "Simpan" tak pernah hilang dari pandangan.
 *  · **Galat tampil di dalam modal** (bukan `alert`) tepat di atas tombol aksi.
 *
 * Pemakaian:
 *   <FormModal open={showCreate} onClose={() => setShowCreate(false)}
 *              title="Supplier Baru" subtitle="Data pemasok & syarat bayar"
 *              icon={Truck} testId="supplier-form"
 *              onSubmit={simpan} submitLabel="Simpan Supplier" busy={saving} error={err}>
 *     …isian form…
 *   </FormModal>
 *
 * Catatan: `onSubmit` opsional. Bila layar butuh tombol aksi khusus (mis. dua tombol
 * "Simpan draf" & "Ajukan"), kirim lewat prop `footer`.
 */
const SIZES = {
  sm: "max-w-md",
  md: "max-w-2xl",
  lg: "max-w-4xl",
  xl: "max-w-6xl",
};

export default function FormModal({
  open,
  onClose,
  title,
  subtitle = "",
  icon: Icon = null,
  size = "md",
  children,
  footer = null,
  onSubmit = null,
  submitLabel = "Simpan",
  cancelLabel = "Batal",
  busy = false,
  error = "",
  submitDisabled = false,
  testId = "form-modal",
  submitTestId = "",
  cancelTestId = "",
}) {
  const cardRef = useRef(null);

  // Esc menutup + kunci scroll halaman di belakang.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape" && !busy) onClose?.(); };
    document.addEventListener("keydown", onKey);
    const sebelumnya = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = sebelumnya;
    };
  }, [open, busy, onClose]);

  // Fokus ke isian pertama yang bisa diisi (bukan tombol) begitu modal terbuka.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      const el = cardRef.current?.querySelector(
        "input:not([type=hidden]):not([disabled]), textarea:not([disabled]), select:not([disabled])");
      el?.focus();
    }, 60);
    return () => clearTimeout(t);
  }, [open]);

  if (!open) return null;

  //: Bila layar menyerahkan aksinya ke FormModal → bungkus <form>; bila tidak, cukup <div>
  //: (isinya kemungkinan sudah komponen ber-<form> sendiri).
  const Wrapper = onSubmit ? "form" : "div";

  const submit = (e) => {
    e?.preventDefault?.();
    if (busy || submitDisabled) return;
    onSubmit?.(e);
  };

  return (
    <div className="modal-overlay fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:items-center"
      data-testid={`${testId}-overlay`} {...overlayDismiss(busy ? undefined : onClose)}>
      <div ref={cardRef} role="dialog" aria-modal="true" aria-label={title}
        data-testid={testId}
        className={`w-full ${SIZES[size] || SIZES.md} my-auto rounded-xl bg-white shadow-2xl`}
        onClick={(e) => e.stopPropagation()}>
        {/* KEPALA — menempel supaya judul tetap terlihat saat isi di-scroll */}
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 rounded-t-xl border-b border-[#EFF0F2] bg-white px-4 py-3">
          <div className="flex min-w-0 items-start gap-2">
            {Icon && (
              <span className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-[#EFF4FF] text-[#0058CC]">
                <Icon size={15} />
              </span>
            )}
            <div className="min-w-0">
              <h3 data-testid={`${testId}-title`} className="text-[13.5px] font-bold leading-tight text-[#1C1C1E]">{title}</h3>
              {subtitle && <p className="mt-0.5 text-[11px] leading-snug text-[#6B6B73]">{subtitle}</p>}
            </div>
          </div>
          <button type="button" className="icon-button flex-shrink-0" aria-label="Tutup"
            data-testid={`${testId}-close`} onClick={() => !busy && onClose?.()}>
            <X size={14} />
          </button>
        </div>

        {/* Badan modal dibungkus <form> HANYA bila layar ini menyerahkan aksinya ke
            FormModal (`onSubmit`). Bila isinya sudah komponen form sendiri (mis.
            `ApprovalRuleForm` yang punya <form> & tombolnya sendiri), membungkusnya lagi
            akan membuat FORM DI DALAM FORM — HTML tak sah dan tombol simpan bisa
            memicu submit ganda. */}
        <Wrapper {...(onSubmit ? { onSubmit: submit, noValidate: true } : {})}>
          {/* BADAN — bisa di-scroll bila isian panjang */}
          <div className="max-h-[70vh] overflow-y-auto px-4 py-3.5" data-testid={`${testId}-body`}>
            {children}
          </div>

          {/* KAKI — galat + aksi, menempel di bawah */}
          {(footer || onSubmit) && (
            <div className="sticky bottom-0 rounded-b-xl border-t border-[#EFF0F2] bg-[#FAFBFC] px-4 py-3">
              {error && (
                <p data-testid={`${testId}-error`}
                  className="mb-2 rounded-md border border-[#FCA5A5] bg-[#FEF2F2] px-2.5 py-1.5 text-[11.5px] font-semibold text-[#B91C1C]">
                  {error}
                </p>
              )}
              {footer || (
                <div className="flex items-center justify-end gap-2">
                  <button type="button" className="secondary-button"
                    data-testid={cancelTestId || `${testId}-cancel`}
                    onClick={() => !busy && onClose?.()} disabled={busy}>
                    {cancelLabel}
                  </button>
                  <button type="submit" className="primary-button"
                    data-testid={submitTestId || `${testId}-submit`}
                    disabled={busy || submitDisabled}>
                    {busy && <Loader2 size={13} className="animate-spin" />} {submitLabel}
                  </button>
                </div>
              )}
            </div>
          )}
        </Wrapper>
      </div>
    </div>
  );
}
