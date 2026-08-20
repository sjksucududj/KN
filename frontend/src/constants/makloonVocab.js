/**
 * makloonVocab (FASE T) — SATU tempat kosakata tahapan proses & aliran kain.
 *
 * KENAPA BERKAS INI ADA
 * Sebelum FASE T label proses makloon hidup sebagai `PROCESS_LABELS` di dalam
 * `components/MakloonSelect.jsx` — sebuah komponen PEMILIH MITRA. Enam layar
 * mengimpornya dari sana, dan isinya hanya 5 dari 8 jenis proses yang sungguhan:
 * `rajut`, `pre_treatment`, dan `screen` TIDAK ADA. Akibat nyatanya terlihat di data
 * demo: mitra "UD Kasa Mandiri Screen" berkemampuan `screen` tampil sebagai teks
 * mentah "screen", dan kemampuan itu **tidak bisa dicentang** saat mitranya disunting
 * (daftar centangnya tidak memuatnya) — jalan buntu yang tak berbunyi.
 *
 * Keputusan pemilik 4a: nilai proses di layar WAJIB dari master. Jadi:
 *   · daftar HIDUP dibaca dari registry (`useProcessTypes` → `/api/enums`, yang
 *     backend-nya sudah menimpa dengan master `process_stages`);
 *   · berkas ini hanya CADANGAN saat registry belum termuat (layar tidak boleh
 *     kosong di detik pertama) + label kosakata yang bukan enum (aliran kain).
 * Cadangan sengaja LENGKAP 8 nilai supaya kegagalan jaringan tidak menyembunyikan
 * kemampuan mitra.
 */

/** Cadangan label jenis proses — lengkap sesuai `domain_registry.PROCESS_TYPES`. */
export const PROCESS_TYPE_FALLBACK = {
  tenun: "Tenun",
  rajut: "Rajut",
  pre_treatment: "Pre-treatment (PFD/PFP)",
  celup: "Celup",
  screen: "Screen / kasa",
  printing: "Printing",
  finishing: "Finishing",
  lainnya: "Lainnya",
};

/** Jenis tahap (kolom `kind` master Tahapan Proses). */
export const STAGE_KIND_LABELS = {
  makloon: "Dikerjakan mitra (SPK)",
  material: "Masuk bahan",
  sampling: "Sampling/proofing",
  inspection: "Inspeksi internal",
};

/** Aliran kain (keputusan pemilik 1c) — kalimatnya sama di master, wizard & detail. */
export const MATERIAL_FLOW_LABELS = {
  moves: "Kain dikirim ke mitra",
  service_only: "Jasa murni — kain tinggal di gudang",
  either: "Boleh dua-duanya (dipilih per langkah)",
};

/** Label pendek untuk lencana di kartu langkah. */
export const MATERIAL_FLOW_BADGE = {
  moves: "Kain dikirim",
  service_only: "Jasa murni",
};

/**
 * Aksi yang akan tersedia setelah SPK disimpan, per aliran kain. Ditulis di sini
 * supaya wizard (yang menjanjikan) dan panel detail (yang menyediakan tombolnya)
 * tidak pernah menjanjikan aksi yang berbeda.
 */
export const NEXT_ACTION_LABELS = {
  issue: "Issue ke Makloon → Terima Hasil",
  record_service: "Catat Jasa (tanpa mengeluarkan kain)",
};
