/**
 * overlayDismiss — tutup modal HANYA bila pengguna benar-benar menekan & melepas
 * klik di area gelap (backdrop) modal itu sendiri.
 *
 * MASALAH YANG DIPERBAIKI (bug kelas "modal ikut tertutup"):
 * Dropdown Radix (Select/Popover/Combobox) me-render isinya lewat **React portal**
 * ke `document.body`. Secara DOM ia di luar modal, TAPI pada React event system
 * event tetap **merembet mengikuti pohon React** — sehingga `onClick` di elemen
 * backdrop (`.modal-overlay`) ikut terpanggil saat pengguna memilih satu opsi.
 * Akibatnya: memilih supplier di modal "Impor Massal" menutup seluruh modal dan
 * isian pengguna hilang.
 *
 * Selain itu, setelah isi dropdown ter-unmount, browser masih mengirim satu event
 * `click` "nyasar" ke elemen yang ada di bawah kursor. Bila elemen itu kebetulan
 * backdrop, modal juga akan tertutup tanpa niat pengguna.
 *
 * SOLUSI: perlakukan penutupan sebagai **gestur utuh** — wajib `pointerdown` DAN
 * `click` terjadi tepat di elemen backdrop. Klik yang berasal dari portal (target
 * bukan backdrop) maupun klik nyasar (tak ada pointerdown di backdrop) diabaikan.
 *
 * Pemakaian:
 *   import { overlayDismiss } from "@/utils/overlayDismiss";
 *   <div className="modal-overlay" {...overlayDismiss(onClose)}> … </div>
 *
 * Catatan: JANGAN pasang di kartu modal (anak), cukup di elemen backdrop-nya.
 */

const ARM_ATTR = "overlayArm";

export function overlayDismiss(onClose) {
  if (typeof onClose !== "function") return {};
  return {
    onPointerDown: (e) => {
      // Hanya "arm" bila tekanan dimulai tepat di backdrop (bukan di dalam kartu
      // modal, bukan dari isi dropdown yang di-portal).
      if (e.target === e.currentTarget) {
        e.currentTarget.dataset[ARM_ATTR] = "1";
      } else {
        delete e.currentTarget.dataset[ARM_ATTR];
      }
    },
    onClick: (e) => {
      const armed = e.currentTarget.dataset[ARM_ATTR] === "1";
      delete e.currentTarget.dataset[ARM_ATTR];
      if (armed && e.target === e.currentTarget) onClose(e);
    },
  };
}

export default overlayDismiss;
