import { useCallback, useEffect, useMemo, useState } from "react";
import axios, { API } from "../services/apiClient";
import { Layers, ChevronLeft, ChevronRight, Check, Loader2, Building2, AlertTriangle } from "lucide-react";
import { formatCurrency, formatQty } from "../utils/formatters";

const PAGE_SIZE = 8;

/**
 * RollPicker — SALES REVAMP V2 "Beli per Roll".
 * Daftar roll available (FEFO + paginasi), multi-pilih unik (roll utuh),
 * badge entitas (pembeda) + tanda lintas-entitas. Memanggil onConfirm(rollLines, snapshot, totalQty).
 */
export default function RollPicker({ productId, entityId, unitPrice = 0, baseUnit = "meter", onConfirm }) {
  const [page, setPage] = useState(0);
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState({}); // roll_id -> roll object

  const load = useCallback(async (p) => {
    setLoading(true); setError("");
    const effEntity = entityId && entityId !== "all" ? entityId : "";
    try {
      const res = await axios.get(`${API}/inventory/rolls/available`, {
        params: { product_id: productId, entity_id: effEntity, all_entities: true,
                  sort: "fefo", skip: p * PAGE_SIZE, limit: PAGE_SIZE },
      });
      setData(res.data || { items: [], total: 0 });
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat daftar roll.");
      setData({ items: [], total: 0 });
    } finally { setLoading(false); }
  }, [productId, entityId]);

  useEffect(() => { load(page); }, [load, page]);

  const totalPages = Math.max(1, Math.ceil((data.total || 0) / PAGE_SIZE));
  const selList = useMemo(() => Object.values(selected), [selected]);
  const totalQty = useMemo(() => selList.reduce((s, r) => s + Number(r.length_remaining || 0), 0), [selList]);
  const subtotal = Math.round(totalQty * unitPrice * 100) / 100;
  const hasCross = selList.some((r) => r.is_cross_entity);

  const toggle = (roll) => {
    setSelected((cur) => {
      const next = { ...cur };
      if (next[roll.id]) delete next[roll.id]; else next[roll.id] = roll;
      return next;
    });
  };

  const confirm = () => {
    if (!selList.length) return;
    const rollLines = selList.map((r) => ({ roll_id: r.id, take_qty: Number(r.length_remaining) }));
    const snapshot = selList.map((r) => ({
      roll_id: r.id, roll_no: r.roll_no, length: Number(r.length_remaining), lot: r.lot,
      owner_entity_name: r.owner_entity_name, owner_entity_id: r.owner_entity_id,
      is_cross_entity: !!r.is_cross_entity, warehouse_name: r.warehouse_name,
    }));
    onConfirm?.(rollLines, snapshot, Math.round(totalQty * 100) / 100);
  };

  return (
    <div data-testid="roll-picker" className="rounded-md border border-[#E5E5EA] bg-white">
      <div className="flex items-center gap-2 border-b border-[#EFF0F2] px-3 py-2">
        <Layers size={14} className="text-[#0058CC]" />
        <span className="text-[11.5px] font-bold text-[#1C1C1E]">Pilih Roll (FEFO — tertua dulu)</span>
        <span className="ml-auto text-[10.5px] text-[#8E8E93] tabular-nums">{data.total} roll tersedia</span>
      </div>

      <div className="max-h-[280px] overflow-y-auto">
        {loading ? (
          <div data-testid="roll-picker-loading" className="flex items-center justify-center gap-2 py-8 text-[12px] text-[#6B6B73]"><Loader2 size={15} className="animate-spin" /> Memuat roll…</div>
        ) : error ? (
          <div data-testid="roll-picker-error" className="px-3 py-6 text-center text-[12px] text-[#C0392B]">{error}</div>
        ) : data.items.length === 0 ? (
          <div data-testid="roll-picker-empty" className="px-3 py-6 text-center text-[12px] text-[#8E8E93]">Tidak ada roll tersedia untuk produk ini.</div>
        ) : (
          <ul className="divide-y divide-[#F2F3F5]">
            {data.items.map((r) => {
              const on = !!selected[r.id];
              return (
                <li key={r.id} data-testid={`roll-row-${r.id}`}>
                  <button type="button" onClick={() => toggle(r)} data-testid={`roll-toggle-${r.id}`}
                    className={`flex w-full items-center gap-2.5 px-3 py-2 text-left transition ${on ? "bg-[#EAF2FF]" : "hover:bg-[#FAFBFC]"}`}>
                    <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${on ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#C7C7CC] bg-white"}`}>
                      {on && <Check size={11} />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[12px] font-semibold text-[#1C1C1E]">{r.roll_no || r.id}</span>
                        <span className="text-[10px] text-[#8E8E93]">· Lot {r.lot || "—"}</span>
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1">
                        <span className="text-[10.5px] text-[#6B6B73]">{r.warehouse_name}</span>
                        {r.is_cross_entity ? (
                          <span data-testid={`roll-badge-cross-${r.id}`} className="inline-flex items-center gap-0.5 rounded-full bg-[#FFF3E0] px-1.5 py-0.5 text-[9px] font-bold text-[#9A5B00]">
                            <AlertTriangle size={9} /> {r.owner_entity_name} · transfer
                          </span>
                        ) : (
                          <span data-testid={`roll-badge-own-${r.id}`} className="inline-flex items-center gap-0.5 rounded-full bg-[#EEF1F4] px-1.5 py-0.5 text-[9px] font-semibold text-[#3C3C43]">
                            <Building2 size={9} /> {r.owner_entity_name}
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="shrink-0 text-right">
                      <span className="block text-[12.5px] font-bold tabular-nums text-[#1C1C1E]">{formatQty(r.length_remaining)}</span>
                      <span className="block text-[9px] text-[#8E8E93]">{baseUnit}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Pager */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-[#EFF0F2] px-3 py-1.5">
          <button type="button" data-testid="roll-picker-prev" disabled={page <= 0 || loading} onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="icon-button text-[11px] disabled:opacity-40"><ChevronLeft size={14} /> Sebelumnya</button>
          <span className="text-[10.5px] text-[#8E8E93] tabular-nums">Hal {page + 1}/{totalPages}</span>
          <button type="button" data-testid="roll-picker-next" disabled={page >= totalPages - 1 || loading} onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            className="icon-button text-[11px] disabled:opacity-40">Berikutnya <ChevronRight size={14} /></button>
        </div>
      )}

      {/* Footer summary */}
      <div className="border-t border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2.5">
        {hasCross && (
          <p data-testid="roll-picker-cross-note" className="mb-1.5 flex items-start gap-1.5 rounded-md bg-[#FFF3E0] px-2 py-1.5 text-[10px] text-[#9A5B00]">
            <AlertTriangle size={11} className="mt-0.5 shrink-0" /> Sebagian roll milik entitas lain — sistem akan otomatis membuat permintaan transfer antar-entitas saat pesanan dibuat.
          </p>
        )}
        <div className="flex items-center justify-between">
          <div className="text-[11px] text-[#6B6B73]">
            <span data-testid="roll-picker-count" className="font-semibold text-[#1C1C1E]">{selList.length}</span> roll dipilih ·{" "}
            <span data-testid="roll-picker-total-qty" className="font-semibold tabular-nums text-[#1C1C1E]">{formatQty(Math.round(totalQty * 100) / 100)} {baseUnit}</span>
          </div>
          <div className="text-right text-[12px] font-bold tabular-nums text-[#0058CC]" data-testid="roll-picker-subtotal">{formatCurrency(subtotal)}</div>
        </div>
        <button type="button" data-testid="roll-picker-confirm" disabled={!selList.length} onClick={confirm}
          className="primary-button mt-2 w-full justify-center py-2 text-[12px] disabled:opacity-50">
          <Check size={14} /> Tambah {selList.length || ""} Roll ke Keranjang
        </button>
      </div>
    </div>
  );
}
