/**
 * supplierItemsApi (FASE E) — satu pintu akses API Barang Supplier & sourcing PR.
 * Semua endpoint ber-prefix /api (REACT_APP_BACKEND_URL) via apiClient.
 */
import axios, { API } from "../../../services/apiClient";

// ── Barang Supplier (`supplier_items`) ───────────────────────────────────────
export const listSupplierItems = (params) =>
  axios.get(`${API}/supplier-items`, { params }).then((r) => r.data);

export const supplierItemStats = (params) =>
  axios.get(`${API}/supplier-items/stats`, { params }).then((r) => r.data);

export const createSupplierItem = (body) =>
  axios.post(`${API}/supplier-items`, body).then((r) => r.data);

export const patchSupplierItem = (id, body) =>
  axios.patch(`${API}/supplier-items/${id}`, body).then((r) => r.data);

export const deleteSupplierItem = (id) =>
  axios.delete(`${API}/supplier-items/${id}`).then((r) => r.data);

/** Cari barang KN dari KODE SUPPLIER (kasus nyata: operator hanya pegang kode supplier). */
export const lookupSupplierSku = (params) =>
  axios.get(`${API}/supplier-items/lookup`, { params }).then((r) => r.data);

/** Impor via JSON (`csv_text`) — dipakai mode "tempel CSV". */
export const importSupplierItems = (body) =>
  axios.post(`${API}/supplier-items/import`, body).then((r) => r.data);

/** Impor via UNGGAH berkas CSV/XLSX (multipart). */
export const importSupplierItemsFile = (file, params) => {
  const form = new FormData();
  form.append("file", file);
  return axios
    .post(`${API}/supplier-items/import-file`, form, {
      params,
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
};

/** Unduh template CSV (blob → objectURL, tetap membawa header Authorization). */
export const downloadImportTemplate = async () => {
  const res = await axios.get(`${API}/supplier-items/import-template`, { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "template_barang_supplier.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
};

// ── Sourcing PR (routing & realisasi · FASE E) ───────────────────────────────
export const prSourcing = (prId) =>
  axios.get(`${API}/purchase-requisitions/${prId}/sourcing`).then((r) => r.data);

export const realizePo = (prId, body) =>
  axios.post(`${API}/purchase-requisitions/${prId}/realize-po`, body).then((r) => r.data);

export const makloonPrefill = (prId, lineNo) =>
  axios
    .get(`${API}/purchase-requisitions/${prId}/makloon-prefill`, { params: { line_no: lineNo } })
    .then((r) => r.data);

export const realizeMakloon = (prId, body) =>
  axios.post(`${API}/purchase-requisitions/${prId}/realize-makloon`, body).then((r) => r.data);

// ── Label & meta ─────────────────────────────────────────────────────────────
export const FULFILLMENT_OPTIONS = [
  { value: "purchase", label: "Beli ke Supplier" },
  { value: "makloon", label: "Proses via Makloon" },
];

export const FULFILLMENT_META = {
  purchase: { label: "Beli", cls: "pill-info" },
  makloon: { label: "Makloon", cls: "pill-warning" },
};

export const REALIZATION_META = {
  open: { label: "Belum Direalisasi", cls: "pill-muted" },
  partially_realized: { label: "Realisasi Sebagian", cls: "pill-warning" },
  realized: { label: "Terealisasi Penuh", cls: "pill-success" },
};

export const PRICE_SOURCE_LABEL = {
  contract: "Kontrak pembelian",
  pr_estimate: "Estimasi PR",
  supplier_item: "Harga terakhir barang supplier",
  price_list: "Price-list supplier",
  product_master: "Master produk",
};
