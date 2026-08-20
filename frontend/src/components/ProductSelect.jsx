/**
 * ProductSelect (M1 — Master-Inline) — pemilih produk (searchable), filter stage opsional.
 * onSelect(product). Untuk memilih input/output resep proses.
 *
 * KENAPA MODALNYA LEWAT PORTAL (bug nyata, terukur 2026-08-19)
 * Pemicu (tombol) dan modalnya lahir di komponen yang sama, dan komponen ini dipakai
 * di dalam `<Field>` yang merender **`<label>`** (Wizard Makloon, Order Makloon, Resep
 * Proses, Kontrak Mitra …). Klik di dalam sebuah `<label>` **diteruskan peramban** ke
 * kontrol yang dilabeli — yaitu tombol pemicu ini. Akibatnya: memilih produk berhasil,
 * tetapi label langsung "mengklik" pemicunya lagi sehingga **modal terbuka kembali
 * dengan kotak cari kosong**; pemakai wajib menekan × setiap kali memilih, dan aksi
 * berikutnya (mis. tombol Lanjut) tertutup lapisan modal. `e.stopPropagation()` di
 * kartu modal TIDAK menolong karena React memasang pendengarnya di akar dokumen —
 * peristiwa nyata sudah melewati `<label>` lebih dulu. Satu-satunya perbaikan yang
 * benar secara struktural: modal dirender **di luar** `<label>` lewat portal
 * (`createPortal` ke `document.body`). Dijaga gate `INV-UI-09`.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Package, Search, X, Check, ChevronDown } from "lucide-react";
import axios, { API } from "../services/apiClient";
import { overlayDismiss } from "@/utils/overlayDismiss";

export const STAGE_LABELS = { yarn: "Benang", grey: "Grey", finished: "Finished", remnant: "Barang Sisa" };

export default function ProductSelect({
  value = "", valueName = "", onSelect, stage = "",
  label = "Pilih produk…", triggerTestId = "product-select-trigger", disabled = false,
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" data-testid={triggerTestId} disabled={disabled} onClick={() => setOpen(true)}
        className="field flex w-full items-center gap-2 text-left disabled:opacity-50">
        <Package size={14} className="shrink-0 text-[#6B219A]" />
        <span className={`min-w-0 flex-1 truncate ${value ? "text-[#1C1C1E]" : "text-[#9A9BA3]"}`}>{value ? valueName : label}</span>
        <ChevronDown size={14} className="text-[#9A9BA3]" />
      </button>
      {open && createPortal(
        <ProductPickerModal stage={stage} selectedId={value}
          onClose={() => setOpen(false)} onPick={(p) => { onSelect?.(p); setOpen(false); }} />,
        document.body)}
    </>
  );
}

function ProductPickerModal({ stage, selectedId, onClose, onPick }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/products`);
      setRows(Array.isArray(res.data) ? res.data : []);
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat produk."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return rows.filter((p) => {
      if (stage && (p.stage || "finished") !== stage) return false;
      if (s && !`${p.sku}${p.name}${p.category}`.toLowerCase().includes(s)) return false;
      return true;
    });
  }, [rows, q, stage]);

  return (
    <div data-testid="product-select-modal" className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="flex max-h-[85vh] w-full max-w-[560px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold"><Package size={16} className="text-[#6B219A]" /> Pilih Produk {stage && <span className="rounded bg-[#F3E9FA] px-1.5 text-[10px] font-bold text-[#6B219A]">{STAGE_LABELS[stage] || stage}</span>}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={18} /></button>
        </div>
        <div className="border-b border-[#EFF0F2] px-4 py-2.5">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="product-select-search" autoFocus className="field w-full pl-8" placeholder="Cari SKU / nama produk…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {loading ? <div className="py-8 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
           : error ? <div data-testid="product-select-error" className="py-8 text-center text-[12px] text-[#D14343]">{error}</div>
           : filtered.length === 0 ? <div data-testid="product-select-empty" className="py-8 text-center text-[12px] text-[#8E8E93]">Tidak ada produk{stage ? ` tahap ${STAGE_LABELS[stage] || stage}` : ""}.</div>
           : filtered.map((p) => (
            <button key={p.id} data-testid={`product-select-item-${p.id}`} onClick={() => onPick(p)}
              className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left transition ${p.id === selectedId ? "border-[#0058CC] bg-[#EAF2FF]" : "border-transparent hover:bg-[#FAFBFC]"}`}>
              <span className="h-6 w-6 shrink-0 rounded border border-[#E5E5EA]" style={{ backgroundColor: p.color_hex || "#F5F5F7" }} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12.5px] font-semibold">{p.name} <span className="text-[10.5px] font-normal text-[#0058CC]">{p.sku}</span></p>
                <p className="truncate text-[10.5px] text-[#6B6B73]">{p.category} · {STAGE_LABELS[p.stage || "finished"]} · {p.base_unit}</p>
              </div>
              {p.id === selectedId && <Check size={15} className="text-[#0058CC]" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
