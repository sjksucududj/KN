/**
 * writeScope — SATU definisi "boleh menyimpan atau tidak" untuk mode badan usaha.
 *
 * KEPUTUSAN PEMILIK (user story 7): mode **"Semua Entitas"** dipakai untuk MELIHAT
 * gabungan; membuat dokumen di mode itu dilarang karena sistem tidak tahu buku
 * badan usaha mana yang harus menerima dokumennya.
 *
 * Sebelum ini, layar membiarkan tombol "Simpan" tetap hidup dan server
 * diam-diam menstempel badan usaha HOME pengguna. Sekarang aturannya satu:
 * layar memakai `canWriteInScope()`, server memakai `entity_write_guard.py`.
 * Dua-duanya menyebut alasan yang sama supaya tidak ada pesan yang berbeda
 * untuk hal yang sama.
 */
export const GROUP_SCOPE = "all";

/** Sedang melihat gabungan semua badan usaha? */
export const isGroupScope = (selectedEntity) =>
  (selectedEntity || GROUP_SCOPE) === GROUP_SCOPE;

/** Boleh membuat/menyimpan data pada konteks badan usaha ini? */
export const canWriteInScope = (selectedEntity) => !isGroupScope(selectedEntity);

/** Kalimat yang dipakai tooltip tombol yang dimatikan. */
export const WRITE_BLOCK_HINT =
  "Pilih satu badan usaha dulu (kanan atas). Mode “Semua Entitas” hanya untuk melihat gabungan.";

/** Judul & isi pesan saat server menolak (dipakai interseptor apiClient). */
export const WRITE_BLOCK_TITLE = "Pilih satu badan usaha dulu";

/**
 * Apakah pesan galat ini berasal dari pagar mode gabungan?
 * Dicocokkan pada frasa yang dikirim server (`entity_write_guard.MESSAGE`).
 */
export const isScopeBlockedError = (err) => {
  if (err?.response?.status !== 409) return false;
  const d = err?.response?.data?.detail;
  return typeof d === "string" && d.includes("Semua Entitas");
};
