/**
 * confirmService — SATU pintu untuk pertanyaan "yakin?" di seluruh aplikasi (FASE P5).
 *
 * MASALAH YANG DISELESAIKAN (PERF_UX_AUDIT.md §P5, keputusan pemilik)
 * ==================================================================
 * Aplikasi memakai **dialog bawaan peramban** (`window.confirm` 21× · `window.prompt` 4×)
 * untuk keputusan yang menyentuh uang & stok. Itu bermasalah, bukan cuma "kurang cantik":
 *
 *  1. **Memblokir seluruh thread JavaScript.** Selama kotak itu terbuka, tidak ada yang
 *     bisa dirender — termasuk indikator "sedang menyimpan". Operator gudang yang sedang
 *     memindai menganggap aplikasi hang lalu menekan tombol dua kali.
 *  2. **Tak bisa diberi konteks.** `confirm()` hanya menerima teks polos: tak ada nomor
 *     dokumen tebal, tak ada nominal ber-format, tak ada peringatan merah. Untuk
 *     "Batalkan penerimaan X (Rp 12.500.000)?" konteks itu justru yang menentukan.
 *  3. **Tak bisa MENUNTUT ALASAN.** Aksi yang membalik uang/stok wajib tercatat alasannya.
 *     `confirm()` cuma Ya/Batal; `prompt()` bisa diisi spasi, tak bisa divalidasi, dan di
 *     `AccountList` malah dipakai meminta **kata sandi tanpa penyamaran karakter**.
 *  4. **Bisa dibungkam permanen.** Peramban menampilkan "jangan tampilkan dialog lagi"
 *     setelah beberapa kali; sesudah itu `confirm()` mengembalikan `false` **tanpa
 *     bertanya** → tombol tampak mati. Di iOS/PWA sebagian sudah diabaikan diam-diam.
 *
 * BENTUK PEMAKAIAN (sengaja seperti `toast()` — satu fungsi, tanpa state per layar)
 * ---------------------------------------------------------------------------------
 *   import { askConfirm, askReason } from "@/services/confirmService";
 *
 *   if (!(await askConfirm({ title: `Hapus lead "${lead.name}"?`, danger: true }))) return;
 *
 *   const alasan = await askReason({ title: "Batalkan transfer ini?", danger: true,
 *                                    reasonLabel: "Alasan pembatalan" });
 *   if (alasan === null) return;            // ← pengguna menutup dialog
 *
 * KONTRAK NILAI KEMBALI (dibuat berbeda tipe supaya MUSTAHIL tertukar):
 *   · `askConfirm` → `true` (lanjut) | `false` (batal)
 *   · `askReason`  → `string` berisi alasan (dijamin tidak kosong bila `reasonRequired`)
 *                    | `null` (batal). Sengaja BUKAN `""` untuk batal — string kosong itu
 *                    falsy, jadi `if (!alasan)` akan salah menganggap "lanjut tanpa alasan"
 *                    sebagai "batal". Kelas bug ini dihindari di tingkat kontrak.
 *   · `askText`    → sama seperti `askReason`, untuk isian satu baris / kata sandi
 *                    (`inputType: "password"` → karakter disamarkan).
 *   · `askChoice`  → `string` kunci pilihan | `null` (batal). Untuk pertanyaan yang
 *                    jawabannya BUKAN ya/tidak (mis. "Halaman ini" vs "Semua hasil
 *                    filter"); memeras pilihan begitu menjadi Ya/Tidak membuat arti
 *                    tombol "Tidak" harus ditebak.
 *
 * Kenapa modul-level (bukan React context)? Karena pemanggilnya sering **bukan komponen**
 * (`hooks/useAppActions.js`, handler di dalam `services/`). Pola ini identik dengan
 * `hooks/use-toast.js` yang sudah dipakai repo, jadi tidak menambah cara baru.
 *
 * Dijaga penjaga `scripts/guardrails/verify_blocking_dialogs.py` (INV-UI-06):
 * `alert(`/`confirm(`/`prompt(` bawaan peramban = MERAH.
 */

let emit = null;              // dipasang oleh <ConfirmHost/> saat mount
const queue = [];             // permintaan yang menunggu (dialog hanya satu pada satu saat)
let active = false;
let seq = 0;

/** Dipakai HANYA oleh components/ConfirmHost.jsx. */
export function subscribeConfirm(fn) {
  emit = fn;
  pump();
  return () => { if (emit === fn) emit = null; };
}

function pump() {
  if (active || !emit || queue.length === 0) return;
  active = true;
  emit(queue[0]);
}

/** Dipakai HANYA oleh components/ConfirmHost.jsx: selesaikan permintaan teratas. */
export function settleConfirm(value) {
  const req = queue.shift();
  active = false;
  emit?.(null);
  req?.resolve(value);
  // Beri React satu tick untuk menutup dialog sebelum yang berikutnya dibuka,
  // supaya animasi/fokus tidak bertumpuk.
  if (queue.length) setTimeout(pump, 0);
}

function request(opts) {
  return new Promise((resolve) => {
    if (typeof window === "undefined") { resolve(null); return; }
    queue.push({ id: ++seq, opts, resolve });
    if (!emit) {
      // <ConfirmHost/> belum ter-mount (mis. dipanggil dari unit test tanpa root).
      // Kita TIDAK mengembalikan false diam-diam — itu membuat tombol tampak mati.
      // eslint-disable-next-line no-console
      console.error("[confirmService] <ConfirmHost/> belum ter-mount di root aplikasi; "
        + "dialog konfirmasi tidak bisa ditampilkan.");
    }
    pump();
  });
}

/**
 * Pertanyaan Ya/Batal.
 * @returns {Promise<boolean>} true bila pengguna menekan tombol konfirmasi.
 */
export async function askConfirm(opts = {}) {
  const res = await request({ ...opts, withReason: false });
  return res === true;
}

/**
 * Pertanyaan yang MENUNTUT alasan tertulis (aksi berdampak uang/stok).
 * @returns {Promise<string|null>} alasan, atau null bila dibatalkan.
 */
export async function askReason(opts = {}) {
  const res = await request({
    reasonLabel: "Alasan",
    reasonRequired: true,
    inputType: "textarea",
    ...opts,
    withReason: true,
  });
  return typeof res === "string" ? res : null;
}

/**
 * Isian satu baris (mis. kata sandi konfirmasi). `inputType: "password"` menyamarkan
 * karakter — hal yang `window.prompt` tidak bisa lakukan sama sekali.
 * @returns {Promise<string|null>}
 */
export async function askText(opts = {}) {
  const res = await request({
    reasonLabel: "Isian",
    reasonRequired: true,
    inputType: "text",
    ...opts,
    withReason: true,
  });
  return typeof res === "string" ? res : null;
}

/**
 * Pertanyaan dengan LEBIH DARI DUA jawaban (FASE P6).
 *
 * Dibuat karena "Unduh CSV" harus menawarkan **Halaman ini** atau **Semua hasil filter**.
 * `askConfirm` hanya Ya/Batal, dan memaksa pilihan begitu ke dalam Ya/Tidak
 * ("Unduh semua? Ya/Tidak" \u2014 lalu Tidak berarti apa? batal, atau unduh halaman ini?)
 * adalah cara membuat pengguna menebak arti tombolnya. Tiap pilihan diberi tombolnya
 * sendiri dengan label yang menyebut **angka barisnya**, jadi tidak ada yang perlu ditebak.
 *
 * @param {{key:string,label:string,description?:string,danger?:boolean}[]} opts.choices
 * @returns {Promise<string|null>} kunci pilihan, atau null bila dibatalkan.
 */
export async function askChoice(opts = {}) {
  const res = await request({ ...opts, choices: opts.choices || [], withReason: false });
  return typeof res === "string" ? res : null;
}

export default { askConfirm, askReason, askText, askChoice };
