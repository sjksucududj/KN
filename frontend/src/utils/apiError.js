/**
 * apiError.js — ubah kegagalan panggilan API menjadi **satu kalimat Bahasa Indonesia**
 * yang bisa langsung ditampilkan ke pengguna.
 *
 * KENAPA MODUL INI ADA (kelas bug nyata, ditemukan saat penutupan FASE G-9):
 *   `components/ErrorNotice.jsx` menerima prop `message` berupa STRING. Dua layar
 *   terbaru (Rekonsiliasi Bank G-8 & Pusat Kasus Keuangan G-9) menyimpan objek error
 *   axios mentah lalu mengirimnya sebagai `error={err}`. Akibatnya `message` undefined,
 *   `ErrorNotice` mengembalikan `null`, dan **SEMUA penolakan backend jadi tak terlihat**:
 *   petugas menekan "Jalankan & selesaikan", backend menolak dengan alasan yang jelas
 *   (400 "wajib pilih alasan" / 403 "entitas lain"), tetapi di layar tidak terjadi apa pun.
 *   Bug KN-G9-ERR-SILENT. Penjaganya: `scripts/guardrails/verify_error_notice.py`.
 *
 * Modul ini sengaja TANPA dependensi (tidak impor React/axios) supaya murah dipakai
 * di komponen mana pun, termasuk yang di-`lazy()`.
 */

const DEFAULT_FALLBACK = "Terjadi kesalahan. Coba lagi, atau hubungi admin bila berulang.";

/** Pesan khusus per kode HTTP — supaya pengguna tahu HARUS berbuat apa. */
const BY_STATUS = {
  401: "Sesi Anda sudah berakhir. Masuk ulang untuk melanjutkan.",
  403: "Anda tidak punya izin untuk tindakan ini.",
  404: "Data yang diminta tidak ditemukan (mungkin sudah dihapus atau dipindah).",
  409: "Data sudah berubah di tempat lain. Muat ulang dulu, lalu ulangi tindakan Anda.",
  413: "Berkas terlalu besar untuk diunggah.",
  429: "Terlalu banyak permintaan berurutan. Tunggu sebentar lalu coba lagi.",
  500: "Server gagal memproses permintaan ini. Laporkan ke admin bila berulang.",
  502: "Server tidak menjawab (gateway). Coba lagi beberapa saat.",
  503: "Layanan sedang tidak tersedia. Coba lagi beberapa saat.",
  504: "Server terlalu lama menjawab. Coba lagi beberapa saat.",
};

/**
 * FastAPI mengirim `detail` dalam TIGA bentuk:
 *   1. string  → `{"detail": "Wajib pilih alasan…"}`                    (HTTPException)
 *   2. daftar  → `[{loc, msg, type}, …]`                               (validasi 422)
 *   3. objek   → `{"detail": {"message": "…"}}`                        (beberapa router)
 */
function fromDetail(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d === "string") return d;
        const field = Array.isArray(d?.loc)
          ? d.loc.filter((x) => x !== "body" && x !== "query").join(".")
          : "";
        const msg = d?.msg || d?.message || "";
        return field ? `${field}: ${msg}` : msg;
      })
      .filter(Boolean);
    return parts.length ? `Isian belum benar — ${parts.join(" · ")}` : "";
  }
  if (typeof detail === "object") {
    return detail.message || detail.detail || detail.error || "";
  }
  return "";
}

/**
 * Ambil kalimat yang layak dibaca manusia dari apa pun yang dilempar `catch`.
 *
 * @param {unknown} e         error axios / Error / string / objek respons
 * @param {string}  fallback  kalimat cadangan bila error tidak bercerita apa pun
 * @returns {string} selalu STRING (mungkin kosong bila `e` memang kosong)
 */
export function apiErrorText(e, fallback = DEFAULT_FALLBACK) {
  if (!e) return "";
  if (typeof e === "string") return e;

  // Sudah berupa respons axios yang dibawa manual.
  const resp = e.response || e;
  const data = resp?.data;

  const fromBody = fromDetail(data?.detail) || fromDetail(data)
    || (typeof data === "string" && !data.trim().startsWith("<") ? data : "");
  if (fromBody) return String(fromBody);

  const status = Number(resp?.status || e?.status || 0);
  if (status && BY_STATUS[status]) return BY_STATUS[status];

  // Jaringan mati / permintaan tak pernah sampai.
  if (e.code === "ERR_NETWORK" || e.message === "Network Error") {
    return "Tidak bisa menghubungi server. Periksa koneksi lalu coba lagi.";
  }
  if (e.code === "ECONNABORTED" || String(e.message || "").includes("timeout")) {
    return "Permintaan terlalu lama dan dibatalkan. Coba lagi.";
  }

  if (status) return `${BY_STATUS[500]} (kode ${status})`;
  return e.message ? String(e.message) : fallback;
}

export default apiErrorText;
