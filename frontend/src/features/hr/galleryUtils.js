// HRD H5 — util Design Gallery (motif kain). Helper murni (tanpa JSX).
// Pola fetch gambar ber-Authorization → objectURL (cermin openPayslipPdf di payrollUtils).
import axios, { API } from "../../services/apiClient";

export const ACCEPT_IMG = "image/png,image/jpeg,image/jpg,image/webp";
export const MAX_IMG_MB = 10;

// Ambil byte gambar file galeri (auth via interceptor) → object URL siap dipakai <img src>.
export async function fetchGalleryImageUrl(galleryId, fileId) {
  const res = await axios.get(`${API}/design-gallery/${galleryId}/files/${fileId}`, {
    responseType: "blob",
  });
  return URL.createObjectURL(res.data);
}

// Validasi sederhana sebelum upload (selaras storage_service backend).
export function validateImage(file) {
  if (!file) return "Tidak ada file dipilih.";
  const okType = /image\/(png|jpe?g|webp)/i.test(file.type);
  if (!okType) return "Format harus JPG, PNG, atau WEBP.";
  if (file.size > MAX_IMG_MB * 1024 * 1024) return `Ukuran maksimal ${MAX_IMG_MB}MB.`;
  return "";
}

export function fmtBytes(n) {
  const b = Number(n) || 0;
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}
