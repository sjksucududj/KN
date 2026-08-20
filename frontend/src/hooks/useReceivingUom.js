/**
 * useReceivingUom (FASE F-1) — SATU pintu FE ke penerimaan berbasis **satuan supplier**.
 *
 * Kenapa ada: sebelum F-1 layar Inbound hanya punya kotak “Actual Qty” dalam satuan KN,
 * sehingga operator gudang mengalikan sendiri angka surat jalan supplier
 * (25 cone × 1,89 kg). Hook ini mengambil **opsi satuan yang sah** + **pratinjau
 * konversi dari server** supaya angka di layar = angka yang tersimpan (SSOT).
 *
 *   GET  /api/inbound/tasks/{id}/uom-options   → satuan task/base + barang supplier +
 *                                                opsi satuan (faktor & hint) + sisa 2 satuan
 *   POST /api/inbound/tasks/{id}/preview-uom   → jejak konversi + level toleransi (read-only)
 *
 * Komponen DILARANG menghitung faktor sendiri (aturan repo R3/R7).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import axios, { API } from "../services/apiClient";

/** Label sumber faktor — dipakai UI agar operator tahu dari mana angkanya. */
export const RECEIVE_SOURCE_LABEL = {
  same_unit: "satuan PO",
  supplier_item: "barang supplier",
  fixed_uom: "master satuan (UOM)",
  product_override: "master produk",
  global_rule: "aturan global",
  formula_gsm_width: "formula GSM × lebar",
  hop_base: "lewat satuan dasar",
};

export default function useReceivingUom(taskId) {
  const [options, setOptions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const timer = useRef(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!taskId) { setOptions(null); return; }
    setLoading(true); setError("");
    try {
      const r = await axios.get(`${API}/inbound/tasks/${taskId}/uom-options`);
      setOptions(r.data || null);
    } catch (e) {
      setOptions(null);
      setError(e.response?.data?.detail || "Gagal memuat opsi satuan penerimaan.");
    } finally { setLoading(false); }
  }, [taskId]);

  useEffect(() => {
    setPreview(null); setPreviewError("");
    load();
  }, [load]);

  /** Pratinjau konversi (debounce) — tidak menulis apa pun di server. */
  const runPreview = useCallback((docUom, docQty) => {
    if (timer.current) clearTimeout(timer.current);
    const qty = Number(docQty);
    if (!taskId || !docUom || !Number.isFinite(qty) || qty <= 0) {
      setPreview(null); setPreviewError(""); setPreviewing(false);
      return;
    }
    setPreviewing(true);
    const mine = ++seq.current;
    timer.current = setTimeout(async () => {
      try {
        const r = await axios.post(`${API}/inbound/tasks/${taskId}/preview-uom`,
          { doc_uom: docUom, doc_qty: qty });
        if (mine !== seq.current) return;
        setPreview(r.data || null); setPreviewError("");
      } catch (e) {
        if (mine !== seq.current) return;
        setPreview(null);
        setPreviewError(e.response?.data?.detail || "Konversi satuan belum tersedia.");
      } finally {
        if (mine === seq.current) setPreviewing(false);
      }
    }, 320);
  }, [taskId]);

  const clearPreview = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    seq.current += 1;
    setPreview(null); setPreviewError(""); setPreviewing(false);
  }, []);

  useEffect(() => () => timer.current && clearTimeout(timer.current), []);

  return { options, loading, error, reload: load,
           preview, previewError, previewing, runPreview, clearPreview };
}
