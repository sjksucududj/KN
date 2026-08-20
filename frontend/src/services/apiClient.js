import axios from "axios";

import { toast } from "../hooks/use-toast";
import { isScopeBlockedError, WRITE_BLOCK_TITLE } from "../utils/writeScope";

// SEC-2 — kirim/terima HttpOnly session cookie (same-origin via ingress)
axios.defaults.withCredentials = true;

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const setAuthToken = (token) => {
  if (token) axios.defaults.headers.common.Authorization = `Bearer ${token}`;
  else delete axios.defaults.headers.common.Authorization;
};

// Multi-Entity (F0-B): konteks entitas aktif dikirim via header X-Entity-Id.
// Nilai "all" = mode oversight lintas-PT (hanya dihormati untuk role admin/manager).
export const setActiveEntity = (entityId) => {
  if (entityId) axios.defaults.headers.common["X-Entity-Id"] = entityId;
  else delete axios.defaults.headers.common["X-Entity-Id"];
};

/**
 * FASE E-3 (user story 7) — satu jaring pengaman untuk pagar mode gabungan.
 *
 * Server menolak pembuatan data selagi pengguna berada di mode "Semua Entitas"
 * (`entity_write_guard.py` → 409). Tanpa penangan pusat, penolakan itu akan
 * muncul berbeda-beda di ~50 layar (atau bahkan senyap di layar yang lupa
 * menampilkan galat). Interseptor ini menjamin: **selalu** ada pesan yang
 * menjelaskan sebabnya + isyarat ke pita pemilih badan usaha, di layar mana pun.
 *
 * Galat tetap DILEMPARKAN ULANG supaya layar bisa menampilkan galatnya sendiri
 * (aturan INV-UI-03: kegagalan backend tidak boleh senyap).
 */
axios.interceptors.response.use(
  (res) => res,
  (err) => {
    if (isScopeBlockedError(err)) {
      toast({
        title: WRITE_BLOCK_TITLE,
        description: err.response.data.detail,
        variant: "destructive",
      });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("kn:scope-blocked"));
      }
    }
    return Promise.reject(err);
  },
);

export default axios;
