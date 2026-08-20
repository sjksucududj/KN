import { useEffect } from "react";
import { overlayDismiss } from "@/utils/overlayDismiss";

/**
 * DetailModal — **standar pop-up untuk PANEL RINCIAN** (klik baris → detail), FASE P7.
 *
 * MASALAH YANG DISELESAIKAN (keluhan pemilik, berulang)
 * =====================================================
 * FASE P4 sudah mewajibkan tombol **"Buat/Ubah"** memakai pop-up (`FormModal`), dengan
 * alasan yang ditulis di berkas itu: form yang diselipkan di tengah halaman mendorong
 * daftar data ke bawah lipatan, pengguna tak sadar formnya terbuka, lalu menyimpulkan
 * "tombolnya tidak berfungsi".
 *
 * Persoalan yang SAMA masih ada untuk **panel rincian**, dan tidak pernah tercakup:
 * pada 9 layar, mengklik satu baris tabel merender panel detail sebagai **saudara di
 * bawah tabelnya**. Diukur pada `ar-aging` (layar yang dilaporkan pemilik): tabel
 * "Piutang per Pelanggan" + tabel ringkasan + catatan kaki berada di antara baris yang
 * diklik dan panel yang muncul — jadi setelah mengklik, **tidak ada perubahan apa pun
 * yang terlihat di layar**; rinciannya ada, tetapi di luar pandangan. Semakin panjang
 * tabelnya, semakin jauh. Pengguna menyimpulkan kliknya tidak berfungsi, lalu mengklik
 * baris lain — dan panel di bawah diam-diam berganti isi.
 *
 * KENAPA SHELL INI TIDAK PUNYA KEPALA SENDIRI (beda dari `FormModal`)
 * ------------------------------------------------------------------
 * Kesembilan panel itu SUDAH punya `section-head` sendiri: judul, ringkasan nominal,
 * lencana, tombol aksi kontekstual (mis. "Buat Nota Denda"), dan tombol tutup. Bila
 * shell ini menambahkan kepala lagi, hasilnya dua baris judul dan dua tombol tutup.
 * Jadi ia sengaja hanya menyediakan **lapisan + posisi + perilaku**, dan membiarkan
 * panelnya tetap menjadi kartu yang sudah ada. Akibatnya konversi tiap layar = satu
 * pembungkus, tanpa menyentuh isi panelnya — perubahan kecil, risiko kecil.
 *
 * Yang dibereskan di satu tempat (sama seperti `FormModal`, supaya perilaku pop-up di
 * aplikasi ini hanya ada SATU macam):
 *  · **Esc menutup**;
 *  · **backdrop pakai `overlayDismiss()`** — INV-UI-01: memilih opsi pada dropdown
 *    ber-portal Radix di dalam panel TIDAK boleh menutup pop-upnya;
 *  · **scroll halaman di belakang dikunci**, isi panjang di-scroll di dalam lapisan;
 *  · `role="dialog"` + `aria-modal` + nama yang terbacakan.
 *
 * Dijaga `scripts/guardrails/verify_detail_modal.py` (INV-UI-08).
 */
const SIZES = {
  md: "max-w-2xl",
  lg: "max-w-4xl",
  xl: "max-w-6xl",
  full: "max-w-[1400px]",
};

export default function DetailModal({
  open = true,
  onClose,
  size = "xl",
  label = "Rincian",
  testId = "detail-modal",
  children,
}) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    document.addEventListener("keydown", onKey);
    const sebelumnya = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = sebelumnya;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="modal-overlay fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:items-center"
      data-testid={`${testId}-overlay`}
      {...overlayDismiss(onClose)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        data-testid={testId}
        className={`w-full ${SIZES[size] || SIZES.xl} my-auto`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
