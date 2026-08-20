/**
 * StockBucketsView (F2) — Multi-bucket Stock: WIP, In-transit, Hold (Pending SO).
 * Papan ringkasan bucket per produk + operasi Tahan(Hold)/Lepas & WIP Mulai/Selesai.
 * Akses: admin/manager/warehouse (permission inventory). Sumber: /api/stock/*.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Boxes, RefreshCw, X, CheckCircle2, PauseCircle, Hammer, ChevronRight, ChevronDown,
  Hand, PlayCircle, Layers, PackageSearch,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import EntityBadge from "../../components/EntityBadge";
import KNSelect from "../../components/KNSelect";
import { formatQty } from "../../utils/formatters";
import PendingSoTab from "./PendingSoTab";
import AtpDetailPanel from "./AtpDetailPanel";

const HOLD_TYPES = [
  { value: "general", label: "Umum" },
  { value: "delivery", label: "Pengiriman (permintaan pelanggan / kredit)" },
  { value: "reservation", label: "Reservasi" },
];

const CHIPS = [
  { key: "available_qty", label: "Tersedia", tone: "bg-[#E6F6EC] text-[#1B7F4B]" },
  { key: "reserved_qty", label: "Dipesan", tone: "bg-[#E7F0FF] text-[#0058CC]" },
  { key: "hold_qty", label: "Ditahan", tone: "bg-[#FFF3DC] text-[#9A6700]" },
  { key: "wip_qty", label: "WIP", tone: "bg-[#F0EAFB] text-[#6B2FB3]" },
  { key: "subcon_qty", label: "Di Makloon (WIP-Vendor)", tone: "bg-[#E7EEFF] text-[#0058CC]" },
  { key: "committed_qty", label: "Dialokasikan", tone: "bg-[#E7F0FF] text-[#0058CC]" },
  { key: "in_transit_qty", label: "Dalam Perjalanan", tone: "bg-[#E0F7FA] text-[#00838F]" },
  { key: "quarantine_qty", label: "Karantina", tone: "bg-[#FDEDE7] text-[#C0392B]" },
  { key: "blocked_qty", label: "Blokir", tone: "bg-[#F5F5F7] text-[#6B6B73]" },
  { key: "damaged_qty", label: "Rusak", tone: "bg-[#FDEDE7] text-[#C0392B]" },
];

export default function StockBucketsView({ entities = [], currentUser }) {
  const canManage = ["admin", "manager", "warehouse"].includes(currentUser?.role);
  const [tab, setTab] = useState("board");
  const [board, setBoard] = useState([]);
  const [holds, setHolds] = useState([]);
  const [wips, setWips] = useState([]);
  const [pendingSo, setPendingSo] = useState([]);
  const [expanded, setExpanded] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [opModal, setOpModal] = useState(null); // {type:'hold'|'wip', row, product}

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [b, h, w, ps] = await Promise.all([
        axios.get(`${API}/stock/buckets`),
        axios.get(`${API}/stock/holds`),
        axios.get(`${API}/stock/wip`),
        axios.get(`${API}/stock/pending-so`),
      ]);
      setBoard(b.data || []); setHolds(h.data || []); setWips(w.data || []); setPendingSo(ps.data || []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data stok.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const totals = useMemo(() => {
    const t = { available_qty: 0, hold_qty: 0, wip_qty: 0, atp_qty: 0 };
    board.forEach((p) => { Object.keys(t).forEach((k) => { t[k] += p.totals?.[k] || 0; }); });
    t.pending_qty = pendingSo.reduce((s, r) => s + (r.backorder_qty || 0), 0);
    return t;
  }, [board, pendingSo]);

  const releaseHold = async (id) => {
    try { await axios.post(`${API}/stock/hold/${id}/release`); setNotice("Hold dilepas — stok kembali tersedia."); load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal melepas hold."); }
  };
  const completeWip = async (id) => {
    try { await axios.post(`${API}/stock/wip/${id}/complete`); setNotice("WIP selesai — stok kembali tersedia."); load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menyelesaikan WIP."); }
  };

  return (
    <div data-testid="stock-buckets-view">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-3">
        <Kpi testId="sb-kpi-available" label="Total Tersedia" value={formatQty(totals.available_qty)} icon={Boxes} tone="text-[#1B7F4B]" />
        <Kpi testId="sb-kpi-hold" label="Ditahan" value={formatQty(totals.hold_qty)} icon={PauseCircle} tone="text-[#9A6700]" />
        <Kpi testId="sb-kpi-wip" label="WIP (Proses)" value={formatQty(totals.wip_qty)} icon={Hammer} tone="text-[#6B2FB3]" />
        <Kpi testId="sb-kpi-atp" label="ATP (Janji Jual)" value={formatQty(totals.atp_qty)} icon={Layers} tone="text-[#0058CC]" />
        <Kpi testId="sb-kpi-pending" label="SO Menunggu" value={formatQty(totals.pending_qty)} icon={PackageSearch} tone="text-[#C0392B]" />
      </div>

      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-1.5">
            <Tab id="board" tab={tab} setTab={setTab} testId="sb-tab-board">Ringkasan Bucket</Tab>
            <Tab id="holds" tab={tab} setTab={setTab} testId="sb-tab-holds">Tahanan Aktif {holds.length ? `(${holds.length})` : ""}</Tab>
            <Tab id="wip" tab={tab} setTab={setTab} testId="sb-tab-wip">WIP Aktif {wips.length ? `(${wips.length})` : ""}</Tab>
            <Tab id="pending" tab={tab} setTab={setTab} testId="sb-tab-pending">SO Menunggu {pendingSo.length ? `(${pendingSo.length})` : ""}</Tab>
          </div>
          <button data-testid="sb-refresh" className="icon-button ml-auto" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="sb-error" />
          {notice && (
            <div data-testid="sb-notice" className="mb-3 rounded-md bg-[#E6F6EC] border border-[#BDE5CC] text-[#1B7F4B] text-[12px] px-3 py-2 flex items-center gap-2">
              <CheckCircle2 size={14} />{notice}<button className="ml-auto" onClick={() => setNotice("")} aria-label="Tutup"><X size={13} /></button>
            </div>
          )}

          {loading ? (
            <div className="grid gap-2">{[0, 1, 2, 3].map((i) => <div key={i} className="h-14 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
          ) : tab === "board" ? (
            <BoardTab board={board} entities={entities} expanded={expanded} setExpanded={setExpanded} canManage={canManage} onOp={setOpModal} />
          ) : tab === "holds" ? (
            <RefList items={holds} entities={entities} canManage={canManage} action={releaseHold} actionLabel="Lepas Tahanan" icon={PauseCircle} emptyText="Tidak ada tahanan aktif." testIdPrefix="sb-hold" metaKey="reason" />
          ) : tab === "pending" ? (
            <PendingSoTab rows={pendingSo} entities={entities} loading={loading} />
          ) : (
            <RefList items={wips} entities={entities} canManage={canManage} action={completeWip} actionLabel="Selesaikan WIP" icon={Hammer} emptyText="Tidak ada WIP aktif." testIdPrefix="sb-wip" metaKey="note" />
          )}
        </div>
      </div>

      {opModal && (
        <OpModal data={opModal} entities={entities}
          onClose={() => setOpModal(null)} onError={setError}
          onDone={(msg) => { setOpModal(null); setNotice(msg); load(); }} />
      )}
    </div>
  );
}

function BoardTab({ board, entities, expanded, setExpanded, canManage, onOp }) {
  if (board.length === 0) return <div data-testid="sb-board-empty" className="py-12 text-center text-[12px] text-[#8E8E93]"><Boxes size={26} className="mx-auto mb-2 text-gray-300" />Belum ada stok.</div>;
  return (
    <div className="space-y-2" data-testid="sb-board">
      {board.map((p) => {
        const open = expanded[p.product_id];
        return (
          <div key={p.product_id} className="rounded-lg border border-[#EFF0F2]">
            <button data-testid={`sb-product-${p.product_id}`} onClick={() => setExpanded({ ...expanded, [p.product_id]: !open })} className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-[#FAFBFC]">
              {open ? <ChevronDown size={15} className="text-[#9A9BA3]" /> : <ChevronRight size={15} className="text-[#9A9BA3]" />}
              <div className="min-w-0 flex-1">
                <span className="font-bold text-[12px] text-[#1C1C1E]">{p.product_name}</span>
                <span className="text-[10px] text-[#9A9BA3] ml-2 font-mono">{p.sku}</span>
              </div>
              <div className="flex flex-wrap gap-1 justify-end">
                {CHIPS.filter((c) => (p.totals?.[c.key] || 0) > 0).map((c) => (
                  <span key={c.key} className={`text-[10px] rounded px-1.5 py-0.5 ${c.tone}`}>{c.label}: {formatQty(p.totals[c.key])}</span>
                ))}
                <span className="text-[10px] rounded px-1.5 py-0.5 bg-[#1C1C1E] text-white font-bold" data-testid={`sb-atp-${p.product_id}`}>ATP {formatQty(p.totals.atp_qty)}</span>
              </div>
            </button>
            {open && (
              <div className="border-t border-[#EFF0F2]">
                <div className="overflow-auto">
                  <table className="w-full text-[11px]">
                    <thead><tr className="text-left text-[9px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC]">
                      <th className="px-3 py-1.5">Gudang</th><th className="px-3 py-1.5">Pemilik</th>
                      <th className="px-3 py-1.5 text-right">Tersedia</th><th className="px-3 py-1.5 text-right">Ditahan</th>
                      <th className="px-3 py-1.5 text-right">WIP</th><th className="px-3 py-1.5 text-right">Stok fisik</th>
                      <th className="px-3 py-1.5 text-right">ATP</th>{canManage && <th className="px-3 py-1.5"></th>}
                    </tr></thead>
                    <tbody>
                      {p.warehouses.map((w, i) => (
                        <tr key={i} data-testid={`sb-seg-${p.product_id}-${w.warehouse_id}`} className="border-t border-[#F5F5F7]">
                          <td className="px-3 py-2">{w.warehouse_name}</td>
                          <td className="px-3 py-2"><EntityBadge entityId={w.owner_entity_id} entities={entities} /></td>
                          <td className="px-3 py-2 text-right tabular-nums text-[#1B7F4B] font-semibold">{formatQty(w.available_qty)}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-[#9A6700]">{formatQty(w.hold_qty)}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-[#6B2FB3]">{formatQty(w.wip_qty)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatQty(w.on_hand_qty)}</td>
                          <td className="px-3 py-2 text-right tabular-nums font-bold">{formatQty(w.atp_qty)}</td>
                          {canManage && (
                            <td className="px-3 py-2 text-right whitespace-nowrap">
                              <button data-testid={`sb-hold-btn-${p.product_id}-${w.warehouse_id}`} disabled={w.available_qty <= 0} className="text-[10px] rounded border border-[#EFD9A8] text-[#9A6700] px-2 py-1 hover:bg-[#FFF3DC] disabled:opacity-30 inline-flex items-center gap-1" onClick={() => onOp({ type: "hold", row: w, product: p })}><Hand size={11} /> Tahan</button>
                              <button data-testid={`sb-wip-btn-${p.product_id}-${w.warehouse_id}`} disabled={w.available_qty <= 0} className="text-[10px] rounded border border-[#D9C4EC] text-[#6B2FB3] px-2 py-1 ml-1 hover:bg-[#F0EAFB] disabled:opacity-30 inline-flex items-center gap-1" onClick={() => onOp({ type: "wip", row: w, product: p })}><PlayCircle size={11} /> WIP</button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <AtpDetailPanel productId={p.product_id} ownerEntityId={p.warehouses?.[0]?.owner_entity_id} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function RefList({ items, entities, canManage, action, actionLabel, icon: Icon, emptyText, testIdPrefix, metaKey }) {
  if (items.length === 0) return <div data-testid={`${testIdPrefix}-empty`} className="py-12 text-center text-[12px] text-[#8E8E93]"><Icon size={26} className="mx-auto mb-2 text-gray-300" />{emptyText}</div>;
  return (
    <div className="overflow-auto rounded-md border border-[#EFF0F2]">
      <table className="w-full text-[12px]">
        <thead><tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
          <th className="px-3 py-2">Produk</th><th className="px-3 py-2">Gudang</th><th className="px-3 py-2">Pemilik</th>
          <th className="px-3 py-2 text-right">Qty</th><th className="px-3 py-2">Keterangan</th>
          {canManage && <th className="px-3 py-2"></th>}
        </tr></thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.ref_id} data-testid={`${testIdPrefix}-row-${it.ref_id}`} className="border-b border-[#F5F5F7] last:border-0">
              <td className="px-3 py-2"><span className="font-medium text-[#1C1C1E]">{it.product_name}</span><span className="block text-[10px] font-mono text-[#9A9BA3]">{it.sku}</span></td>
              <td className="px-3 py-2">{it.warehouse_name}</td>
              <td className="px-3 py-2"><EntityBadge entityId={it.owner_entity_id} entities={entities} /></td>
              <td className="px-3 py-2 text-right tabular-nums font-semibold">{formatQty(it.quantity)} {it.unit}</td>
              <td className="px-3 py-2 text-[#6B6B73]">
                {it.hold_type && it.hold_type !== "general" ? (
                  <span className="inline-block mb-0.5 text-[10px] rounded px-1.5 py-0.5 bg-[#FDEDE7] text-[#C0392B] border border-[#F3C9BD] capitalize">{it.hold_type}</span>
                ) : null}
                <span className="block">{it[metaKey] || "—"}</span>
                {it.ref_doc_id ? <span className="block text-[10px] text-[#0058CC]">Menunggu: {it.ref_doc_id}</span> : null}
              </td>
              {canManage && (
                <td className="px-3 py-2 text-right">
                  <button data-testid={`${testIdPrefix}-action-${it.ref_id}`} className="btn-secondary text-[11px] py-1 px-2.5 inline-flex items-center gap-1" onClick={() => action(it.ref_id)}><CheckCircle2 size={12} /> {actionLabel}</button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OpModal({ data, entities, onClose, onDone, onError }) {
  const isHold = data.type === "hold";
  const { row, product } = data;
  const [qty, setQty] = useState("");
  const [text, setText] = useState("");
  const [refDoc, setRefDoc] = useState("");
  const [holdType, setHoldType] = useState("general");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const q = parseFloat(qty);
    if (!q || q <= 0) { onError("Qty harus lebih dari 0."); return; }
    if (q > row.available_qty + 0.01) { onError(`Qty melebihi stok tersedia (${row.available_qty}).`); return; }
    setSaving(true);
    try {
      if (isHold) {
        await axios.post(`${API}/stock/hold`, {
          product_id: product.product_id, warehouse_id: row.warehouse_id, owner_entity_id: row.owner_entity_id,
          quantity: q, reason: text, hold_type: holdType,
          ref_type: refDoc ? "sales_order" : "", ref_id: refDoc,
        });
        onDone(`${q} ${product.base_unit} ditahan (hold).`);
      } else {
        await axios.post(`${API}/stock/wip/start`, {
          product_id: product.product_id, warehouse_id: row.warehouse_id, owner_entity_id: row.owner_entity_id,
          quantity: q, note: text,
        });
        onDone(`${q} ${product.base_unit} masuk WIP (proses).`);
      }
    } catch (e) {
      onError(e.response?.data?.detail || "Operasi gagal.");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="sb-op-modal">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[#EFF0F2]">
          {isHold ? <Hand size={16} className="text-[#9A6700]" /> : <Hammer size={16} className="text-[#6B2FB3]" />}
          <h3 className="font-bold text-[14px]">{isHold ? "Tahan Stok (Hold)" : "Mulai WIP (Proses)"}</h3>
          <button data-testid="sb-op-close" className="icon-button ml-auto" onClick={onClose} aria-label="Tutup"><X size={15} /></button>
        </div>
        <div className="p-4 space-y-3 text-[12px]">
          <div className="rounded-md bg-[#FAFBFC] border border-[#EFF0F2] px-3 py-2">
            <p className="font-semibold text-[#1C1C1E]">{product.product_name}</p>
            <p className="text-[11px] text-[#9A9BA3]">{product.sku} · {row.warehouse_name} · <EntityBadge entityId={row.owner_entity_id} entities={entities} /></p>
            <p className="text-[11px] text-[#1B7F4B] mt-1">Tersedia: <b>{formatQty(row.available_qty)} {product.base_unit}</b></p>
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">Qty ({product.base_unit})</label>
            <input data-testid="sb-op-qty" type="number" className="field py-2 text-[13px]" value={qty} onChange={(e) => setQty(e.target.value)} max={row.available_qty} autoFocus />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">{isHold ? "Alasan" : "Catatan Proses"} <span className="text-[#9A9BA3] font-normal">(opsional)</span></label>
            <input data-testid="sb-op-text" className="field py-2 text-[13px]" value={text} onChange={(e) => setText(e.target.value)} placeholder={isHold ? "Mis. tahan untuk pelanggan X" : "Mis. potong & jahit"} />
          </div>
          {isHold && (
            <div>
              <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">Jenis Tahanan</label>
              <KNSelect data-testid="sb-op-hold-type" className="field py-2 text-[13px]" value={holdType} onValueChange={setHoldType}
                options={HOLD_TYPES.map((h) => ({ value: h.value, label: h.label }))} />
            </div>
          )}
          {isHold && (
            <div>
              <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">No. SO Menunggu <span className="text-[#9A9BA3] font-normal">(opsional)</span></label>
              <input data-testid="sb-op-ref" className="field py-2 text-[13px]" value={refDoc} onChange={(e) => setRefDoc(e.target.value)} placeholder="Mis. KSC/SO-00099" />
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2]">
          <button className="btn-secondary text-[12px] py-1.5 px-4" onClick={onClose}>Batal</button>
          <button data-testid="sb-op-submit" className="btn-primary text-[12px] py-1.5 px-4" onClick={submit} disabled={saving}>{saving ? "Memproses…" : (isHold ? "Tahan" : "Mulai WIP")}</button>
        </div>
      </div>
    </div>
  );
}

function Tab({ id, tab, setTab, children, testId }) {
  return (
    <button data-testid={testId} onClick={() => setTab(id)}
      className={`text-[12px] font-semibold rounded-lg px-3 py-1.5 border ${tab === id ? "bg-[#6B219A] text-white border-[#6B219A]" : "bg-white border-[#EFF0F2] text-[#6B6B73] hover:border-[#D9C4EC]"}`}>{children}</button>
  );
}

function Kpi({ label, value, icon: Icon, tone = "", testId }) {
  return (
    <div className="section-card" data-testid={testId}>
      <div className="section-body flex items-center gap-3 py-3">
        <div className="w-9 h-9 rounded-lg bg-[#F3EAFB] flex items-center justify-center"><Icon size={17} className="text-[#6B219A]" /></div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`text-[17px] font-bold tabular-nums truncate ${tone || "text-[#1C1C1E]"}`} data-testid={`${testId}-value`}>{value}</p>
        </div>
      </div>
    </div>
  );
}
