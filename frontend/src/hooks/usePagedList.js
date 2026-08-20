import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios, { API } from "../services/apiClient";

/**
 * usePagedList — P2 server-side pagination hook (kontrak {items,total,page,page_size,has_more}).
 *
 * Fitur:
 *  - fetch halaman via ?page=&page_size=&q=  (plus params filter tambahan)
 *  - state loading / error / empty
 *  - debounced search (default 350ms) → reset ke halaman 1
 *  - auto reset ke halaman 1 saat params filter berubah
 *  - kompatibel mundur: bila BE balikan array telanjang, tetap ditangani.
 *  - `fetchAll()` (FASE P6) → seluruh baris hasil filter, untuk Unduh CSV.
 *
 * @param {string} endpoint  path relatif setelah /api, mis. "/inventory/rolls"
 * @param {object} opts      { pageSize, params, search, enabled, debounceMs }
 */

//: Sama dengan `MAX_PAGE_SIZE` di backend/pagination.py. Dipakai `fetchAll` supaya
//: jumlah permintaan seminimal mungkin (5.000 baris → 25 permintaan, bukan 250).
const MAX_PAGE_SIZE = 200;
//: Batas aman: daftar sebesar ini sudah pasti bukan yang dimaksud pengguna saat menekan
//: "Unduh". Tanpa batas, satu klik pada filter yang salah bisa menggantung peramban
//: tanpa kabar. Bila tercapai, pemanggil diberi tahu lewat `onProgress` (capped=true).
const FETCH_ALL_HARD_CAP = 50000;

export function usePagedList(endpoint, opts = {}) {
  const {
    pageSize: initialSize = 20,
    params = {},
    search = "",
    enabled = true,
    debounceMs = 350,
  } = opts;

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialSize);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [debSearch, setDebSearch] = useState(search);

  const paramsKey = useMemo(() => JSON.stringify(params || {}), [params]);
  const debTimer = useRef(null);
  const reqSeq = useRef(0);

  // Debounce search input.
  useEffect(() => {
    if (debTimer.current) clearTimeout(debTimer.current);
    debTimer.current = setTimeout(() => setDebSearch(search), debounceMs);
    return () => debTimer.current && clearTimeout(debTimer.current);
  }, [search, debounceMs]);

  // Reset ke halaman 1 saat query pencarian / filter / ukuran halaman berubah.
  useEffect(() => { setPage(1); }, [debSearch, paramsKey, pageSize]);

  const fetchPage = useCallback(async () => {
    if (!enabled) return;
    const seq = ++reqSeq.current;   // guard urutan respons (hindari data basi)
    setLoading(true);
    try {
      const res = await axios.get(`${API}${endpoint}`, {
        params: {
          ...(JSON.parse(paramsKey) || {}),
          page,
          page_size: pageSize,
          ...(debSearch ? { q: debSearch } : {}),
        },
      });
      if (seq !== reqSeq.current) return;   // respons kadaluarsa → abaikan
      const d = res.data;
      if (Array.isArray(d)) {
        setItems(d);
        setTotal(d.length);
        setHasMore(false);
      } else {
        const list = Array.isArray(d?.items) ? d.items : [];
        setItems(list);
        setTotal(Number.isFinite(d?.total) ? d.total : list.length);
        setHasMore(Boolean(d?.has_more));
      }
      setError("");
    } catch (e) {
      if (seq !== reqSeq.current) return;
      setError(e.response?.data?.detail || "Gagal memuat data.");
      setItems([]);
      setTotal(0);
      setHasMore(false);
    } finally {
      if (seq === reqSeq.current) setLoading(false);
    }
  }, [endpoint, page, pageSize, debSearch, paramsKey, enabled]);

  useEffect(() => { fetchPage(); }, [fetchPage]);

  /**
   * SELURUH baris hasil filter — untuk "Unduh CSV → Semua hasil filter" (FASE P6).
   *
   * KENAPA MENYUSURI ENDPOINT DAFTAR YANG SAMA, bukan endpoint `/export.csv` baru:
   * endpoint ekspor tersendiri menciptakan **dua sumber kebenaran untuk satu filter**.
   * Begitu filter di layar berubah dan query di endpoint ekspor tidak, berkas unduhan
   * berisi jumlah baris yang BERBEDA dari yang dilihat pengguna — dan tak ada yang tahu
   * sampai seseorang menyelisihkan angkanya. Di sini `endpoint`, `params`, dan `q` yang
   * dipakai **persis sama** dengan yang dipakai `fetchPage`, jadi paritas filter bukan
   * sesuatu yang harus dijaga: ia mustahil melenceng.
   *
   * TIDAK menyentuh `page`/`items` milik komponen — daftar di layar tidak boleh bergeser
   * hanya karena pengguna mengunduh.
   *
   * @param {(done:number,total:number)=>void} [onProgress]
   * @param {() => boolean} [isCancelled] dipanggil tiap halaman; true = berhenti
   * @returns {Promise<Array>} baris (urutannya sama dengan urutan di layar)
   */
  const fetchAll = useCallback(async ({ onProgress, isCancelled } = {}) => {
    const baseParams = JSON.parse(paramsKey) || {};
    const out = [];
    let p = 1;
    for (;;) {
      const res = await axios.get(`${API}${endpoint}`, {
        params: {
          ...baseParams,
          page: p,
          page_size: MAX_PAGE_SIZE,
          ...(debSearch ? { q: debSearch } : {}),
        },
      });
      const d = res.data;
      const bare = Array.isArray(d);
      const list = bare ? d : (Array.isArray(d?.items) ? d.items : []);
      out.push(...list);

      const grandTotal = bare
        ? out.length
        : (Number.isFinite(d?.total) ? d.total : out.length);
      if (typeof onProgress === "function") onProgress(out.length, grandTotal);

      const more = bare ? false : Boolean(d?.has_more);
      if (!more || list.length === 0) break;
      if (typeof isCancelled === "function" && isCancelled()) break;
      if (out.length >= FETCH_ALL_HARD_CAP) break;
      p += 1;
    }
    return out;
  }, [endpoint, paramsKey, debSearch]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return {
    items, total, page, pageSize, hasMore, loading, error, totalPages,
    setPage, setPageSize,
    next: () => setPage((p) => (hasMore ? p + 1 : p)),
    prev: () => setPage((p) => Math.max(1, p - 1)),
    refresh: fetchPage,
    fetchAll,
    isEmpty: !loading && items.length === 0,
  };
}

export default usePagedList;
