/**
 * useProcessTypes (FASE T · keputusan pemilik 4a) — label & pilihan JENIS PROSES
 * makloon dari registry hidup, bukan dari daftar hardcode di komponen pemilih mitra.
 *
 * Backend `/api/enums` sudah menimpa enum `process_type` dengan nilai yang dipakai
 * master `process_stages` (lihat `services/master_registry.process_types`), jadi jenis
 * proses yang baru ditambahkan pemilik langsung muncul di semua layar TANPA restart.
 * Cadangan `PROCESS_TYPE_FALLBACK` hanya dipakai saat registry belum termuat.
 */
import { useCallback } from "react";
import useDomainEnums from "./useDomainEnums";
import { PROCESS_TYPE_FALLBACK } from "../constants/makloonVocab";

export default function useProcessTypes() {
  const { items, loading, error } = useDomainEnums();
  const live = items("process_type");

  const options = useCallback((extra = []) => {
    const rows = live.length
      ? live.map((v) => ({ value: v.value, label: v.label || PROCESS_TYPE_FALLBACK[v.value] || v.value }))
      : Object.entries(PROCESS_TYPE_FALLBACK).map(([value, label]) => ({ value, label }));
    return [...extra, ...rows];
  }, [live]);

  const labelOf = useCallback((value) => {
    if (!value) return "—";
    const hit = live.find((v) => v.value === value);
    return hit?.label || PROCESS_TYPE_FALLBACK[value] || value;
  }, [live]);

  return { options, labelOf, loading, error, live };
}
