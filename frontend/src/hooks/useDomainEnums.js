/**
 * useDomainEnums (Fase A · R7) — SATU-SATUNYA sumber enum domain di frontend.
 *
 * Registry backend `GET /api/enums` dikonsumsi sekali lalu di-cache di level modul
 * (semua komponen berbagi hasil yang sama). DILARANG hardcode nilai grade / stage /
 * fabric_type / process_type di komponen — pakai hook ini.
 *
 * Pemakaian:
 *   const { loading, error, options, labelOf, matrix, fieldRules, reload } = useDomainEnums();
 *   <KNSelect options={options("grade")} ... />
 */
import { useCallback, useEffect, useState } from "react";
import axios, { API } from "../services/apiClient";

let cache = null;        // snapshot registry terakhir
let inflight = null;     // promise yang sedang berjalan (hindari fetch ganda StrictMode)
const listeners = new Set();

async function fetchRegistry(force = false) {
  if (cache && !force) return cache;
  if (inflight && !force) return inflight;
  inflight = axios
    .get(`${API}/enums`)
    .then((res) => {
      cache = res.data && typeof res.data === "object" ? res.data : null;
      listeners.forEach((fn) => fn(cache));
      return cache;
    })
    .finally(() => { inflight = null; });
  return inflight;
}

/** Buang cache (dipakai tombol "Muat ulang registry"). */
export function invalidateDomainEnums() { cache = null; }

export default function useDomainEnums() {
  const [snapshot, setSnapshot] = useState(cache);
  const [loading, setLoading] = useState(!cache);
  const [error, setError] = useState("");

  const load = useCallback(async (force = false) => {
    setLoading(true); setError("");
    try {
      const data = await fetchRegistry(force);
      setSnapshot(data);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat registry enum domain.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    let alive = true;
    const onUpdate = (data) => { if (alive) setSnapshot(data); };
    listeners.add(onUpdate);
    if (!cache) load();
    return () => { alive = false; listeners.delete(onUpdate); };
  }, [load]);

  const enums = snapshot?.enums || {};

  /** Daftar item enum lengkap (value + label + metadata). */
  const items = useCallback((name) => {
    const rows = enums?.[name]?.values;
    return Array.isArray(rows) ? rows : [];
  }, [enums]);

  /** Opsi siap-pakai untuk KNSelect. `extra` mis. [{value:"",label:"Semua"}] di depan. */
  const options = useCallback((name, extra = []) => [
    ...extra,
    ...items(name).map((v) => ({ value: v.value, label: v.label || v.value })),
  ], [items]);

  const labelOf = useCallback((name, value) => {
    const hit = items(name).find((v) => v.value === value);
    return hit ? hit.label : (value || "—");
  }, [items]);

  const gradeRank = useCallback((value) => {
    const hit = items("grade").find((v) => v.value === value);
    return hit ? hit.rank : null;
  }, [items]);

  /** Aturan kelengkapan field untuk kombinasi stage × fabric_type (D-22). */
  const fieldRules = useCallback((stage, fabricType) => {
    const base = snapshot?.stage_field_rules?.[stage] || { required: [], recommended: [] };
    const relaxed = snapshot?.knit_relaxed_fields || [];
    let required = [...(base.required || [])];
    let recommended = [...(base.recommended || [])];
    if (fabricType === "knit") {
      recommended = [...recommended, ...required.filter((f) => relaxed.includes(f))];
      required = required.filter((f) => !relaxed.includes(f));
    }
    return { required, recommended };
  }, [snapshot]);

  return {
    loading, error, reload: () => load(true),
    snapshot, enums, items, options, labelOf, gradeRank, fieldRules,
    fieldLabels: snapshot?.field_labels || {},
    transitions: snapshot?.stage_transitions || [],
    matrix: snapshot?.stage_transition_matrix || [],
    decisions: snapshot?.decisions || {},
  };
}
