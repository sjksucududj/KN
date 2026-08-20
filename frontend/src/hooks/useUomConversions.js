/**
 * useUomConversions (FASE B · D-06/D-07) — SATU pintu FE ke registry konversi satuan.
 *
 * Aturan repo (R3/R7): komponen DILARANG menghitung faktor konversi sendiri atau
 * menghardcode daftar satuan. Semua angka berasal dari server:
 *   GET  /api/uom-conversions/catalog   → satuan, dimensi, jenis aturan, formula, setting
 *   GET  /api/uom-conversions/rules     → aturan global (fixed | pack | formula)
 *   POST /api/uom-conversions/convert   → hasil + JEJAK konversi (faktor & sumber)
 *   POST /api/uom-conversions/check-variance → level toleransi (ok | warn | block)
 *
 * Cache di level modul supaya berpindah layar tidak memicu request berulang.
 */
import { useCallback, useEffect, useState } from "react";
import axios, { API } from "../services/apiClient";
import { setUomCatalogUnits } from "../utils/uomCatalog";

let _catalogCache = null;
let _inflight = null;

async function fetchCatalog(force = false) {
  if (_catalogCache && !force) return _catalogCache;
  if (_inflight && !force) return _inflight;
  _inflight = axios.get(`${API}/uom-conversions/catalog`)
    .then((r) => {
      _catalogCache = r.data || {};
      // FASE U — katalog dibagikan ke util MURNI (`utils/uom.js`) lewat penyimpan
      // level modul. Tanpa ini util itu harus menyimpan daftar satuannya sendiri,
      // dan satuan yang ditambah pemilik di master TIDAK pernah muncul di pemilih
      // satuan POS / amandemen PO — keluhan asli pemilik ("menambah KG tidak
      // mengubah apa pun di layar").
      setUomCatalogUnits(_catalogCache.units || []);
      return _catalogCache;
    })
    .finally(() => { _inflight = null; });
  return _inflight;
}

export function invalidateUomCache() { _catalogCache = null; }

export default function useUomConversions() {
  const [catalog, setCatalog] = useState(_catalogCache);
  const [loading, setLoading] = useState(!_catalogCache);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    if (_catalogCache) {
      setCatalog(_catalogCache);
      setUomCatalogUnits(_catalogCache.units || []);
      setLoading(false);
      return () => { alive = false; };
    }
    fetchCatalog()
      .then((c) => { if (alive) { setCatalog(c); setLoading(false); } })
      .catch((e) => {
        if (alive) {
          setError(e.response?.data?.detail || "Gagal memuat katalog satuan.");
          setLoading(false);
        }
      });
    return () => { alive = false; };
  }, []);

  const unitOptions = useCallback((dimension = "") => {
    const units = catalog?.units || [];
    return units
      .filter((u) => !dimension || u.dimension === dimension)
      .map((u) => ({ value: u.code, label: u.label }));
  }, [catalog]);

  const dimensionOf = useCallback((code) => {
    const hit = (catalog?.units || []).find((u) => u.code === String(code || "").toLowerCase());
    return hit?.dimension || "";
  }, [catalog]);

  const convert = useCallback(async (body) => {
    const res = await axios.post(`${API}/uom-conversions/convert`, body);
    return res.data;
  }, []);

  const checkVariance = useCallback(async (expected, actual, label = "hasil konversi") => {
    const res = await axios.post(`${API}/uom-conversions/check-variance`,
      { expected: String(expected), actual: String(actual), label });
    return res.data;
  }, []);

  const reload = useCallback(async () => {
    const c = await fetchCatalog(true);
    setCatalog(c);
    return c;
  }, []);

  return {
    catalog, loading, error, reload,
    units: catalog?.units || [],
    dimensions: catalog?.dimensions || [],
    kinds: catalog?.kinds || [],
    formulas: catalog?.formulas || [],
    settings: catalog?.settings || {},
    unitOptions, dimensionOf, convert, checkVariance,
    // FASE U — satuan yang MASTERNYA menandai "faktor per dokumen" (mis. panel:
    // panjang 1 panel berbeda per pesanan). Daftar ini datang dari server supaya
    // layar tidak pernah menghardcode nama satuan (aturan R7).
    perDocFactorUnits: [
      ...((catalog?.units || []).filter((u) => u.factor_per_document).map((u) => String(u.code).toLowerCase())),
      ...((catalog?.units_master || [])
        .filter((u) => u.factor_per_document && (u.status || "active") === "active")
        .flatMap((u) => [String(u.code || "").toLowerCase(),
                         ...((u.aliases || []).map((a) => String(a).toLowerCase()))])),
    ].filter(Boolean),
  };
}

/** Label sumber faktor (dipakai UI agar user tahu dari mana angkanya). */
export const SOURCE_LABEL = {
  same_unit: "satuan sama",
  fixed_uom: "master satuan (UOM)",
  product_override: "master produk",
  global_rule: "aturan global",
  formula_gsm_width: "formula GSM × lebar",
  hop_base: "lewat satuan dasar",
  unresolved: "belum ada aturan",
};
