/**
 * feedback.js — satu bentuk baku untuk kabar **BERHASIL** (FASE P5).
 *
 * Keputusan pemilik (PERF_UX_AUDIT.md §P5): di layar operasional,
 *   · **gagal / galat** → bilah pesan yang MENEMPEL di layar (`components/ErrorNotice`),
 *     harus ditutup manual supaya operator yang sedang memegang pemindai tidak
 *     melewatkannya;
 *   · **berhasil** → *toast* yang hilang sendiri, karena keberhasilan tidak butuh
 *     tindakan lanjutan dan tidak boleh menghalangi pindaian berikutnya.
 *
 * Sengaja TIDAK menyediakan `notifyFailure()`: bila ada satu pun jalan mudah untuk
 * melaporkan kegagalan lewat toast yang menghilang sendiri, kegagalan akan dilaporkan
 * begitu — dan itu persis kebiasaan yang sedang dihapus di fase ini. Layar yang belum
 * punya bilah galat harus MENAMBAHKANNYA (lihat `components/ErrorNotice.jsx`).
 *
 * Pemakaian:
 *   import { notifySuccess } from "@/utils/feedback";
 *   notifySuccess("Transfer dibuat", "TRF-00012 menunggu persetujuan manajer.");
 */
import { toast } from "../hooks/use-toast";

/**
 * @param {string} title       kalimat pendek: APA yang berhasil ("Transfer dibuat")
 * @param {string} description opsional: nomor dokumen / akibat berikutnya
 */
export function notifySuccess(title, description = "") {
  toast({ title, description: description || undefined });
}

export default notifySuccess;
