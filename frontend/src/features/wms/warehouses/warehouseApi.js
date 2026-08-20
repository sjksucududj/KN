/**
 * warehouseApi (FASE E-4 · E4.1) — satu pintu panggilan API gudang.
 *
 * Kenapa terpusat: layar master gudang, drawer mode pemakaian, dan panel isi
 * gudang memakai endpoint yang sama. Kalau tiap komponen memanggil axios
 * sendiri, satu perubahan kontrak harus dikejar ke banyak berkas.
 */
import axios, { API } from "../../../services/apiClient";

/** Semua gudang beserta lencana modenya (untuk layar MASTER, termasuk yang tak boleh dipakai). */
export const listAllWarehouses = () =>
  axios.get(`${API}/warehouses`, { params: { scope: "all" } }).then((r) => r.data || []);

/** Hanya gudang yang boleh dipakai badan usaha aktif (dipakai pemilih gudang). */
export const listUsableWarehouses = () =>
  axios.get(`${API}/warehouses`).then((r) => r.data || []);

export const createWarehouse = (payload) =>
  axios.post(`${API}/warehouses`, payload).then((r) => r.data);

export const patchWarehouse = (id, data) =>
  axios.patch(`${API}/warehouses/${id}`, { data }).then((r) => r.data);

export const deactivateWarehouse = (id) =>
  axios.delete(`${API}/warehouses/${id}`).then((r) => r.data);

/** Isi gudang per badan usaha — dipakai untuk menjelaskan penolakan mode "khusus". */
export const warehouseOccupancy = (id) =>
  axios.get(`${API}/warehouses/${id}/occupancy`).then((r) => r.data);

/** Pesan galat yang layak dibaca (jangan pernah menampilkan "[object Object]"). */
export const errText = (e, fallback = "Terjadi kesalahan.") => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string" && d.trim()) return d;
  if (Array.isArray(d) && d.length) return d.map((x) => x?.msg || "").join(" ") || fallback;
  return e?.message || fallback;
};
