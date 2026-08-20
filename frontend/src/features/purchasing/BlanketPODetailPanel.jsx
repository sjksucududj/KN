import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { FileStack, XCircle, PackagePlus, Ban, Calendar, Truck, AlertCircle } from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { getStatusBadge } from "../admin/po/poUtils";
import { ContractStatusPill } from "./BlanketPOView";
import CallOffModal from "./CallOffModal";
import ConfirmModal from "../../components/ConfirmModal";

/**
 * BlanketPODetailPanel (P2) — detail kontrak + drawdown (called/remaining) +
 * daftar call-off (PO anak) + aksi: buat call-off (2.a) & tutup kontrak (5.a).
 */
const fmtDate = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");

export default function BlanketPODetailPanel({ blanketId, currentUser, onClose, onChanged, onError }) {
  const [po, setPo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showCallOff, setShowCallOff] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => {
    if (!blanketId) { setPo(null); return; }
    load();
  }, [blanketId]); // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/purchase-orders/${blanketId}`);
      setPo(r.data);
    } catch (e) {
      onError?.(e.response?.data?.detail || "Gagal memuat detail kontrak.");
    } finally { setLoading(false); }
  }

  function onCallOffCreated(child) {
    setShowCallOff(false);
    const msg = child.approval_required
      ? `Call-off ${child.po_number} dibuat — menunggu APPROVAL (over-call/deviasi).`
      : `Call-off ${child.po_number} dibuat — inbound task otomatis dibuat.`;
    load();
    onChanged?.(msg);
  }

  async function doClose(reason) {
    try {
      await axios.post(`${API}/purchase-orders/${blanketId}/close-contract`, { reason });
      setConfirmClose(false);
      load();
      onChanged?.(`Kontrak ${po?.po_number || ""} ditutup.`);
    } catch (e) {
      setConfirmClose(false);
      onError?.(e.response?.data?.detail || "Gagal menutup kontrak.");
    }
  }

  if (!blanketId) {
    return (
      <div className="section-card flex items-center justify-center min-h-[200px] border-dashed">
        <div className="text-center p-6">
          <FileStack size={28} className="mx-auto mb-2 text-gray-300" />
          <p className="text-[12px] text-[#6B6B73]">Pilih kontrak untuk lihat detail & call-off</p>
        </div>
      </div>
    );
  }
  if (loading && !po) {
    return <div className="section-card py-10 text-center text-[12px] text-[#6B6B73]" data-testid="blanket-detail-loading">Memuat detail...</div>;
  }
  if (!po) return null;

  const cap = Number(po.contract_value_cap || 0);
  const called = Number(po.value_called || 0);
  const remaining = Number(po.value_remaining ?? Math.max(cap - called, 0));
  const status = po.contract_status || "active";
  const isActive = status === "active";
  const callOffs = Array.isArray(po.call_offs) ? po.call_offs : [];

  return (
    <div className="section-card self-start" data-testid="blanket-detail-panel">
      <div className="section-head">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase text-[#0058CC]">{po.po_number}</p>
          <div className="mt-0.5 flex items-center gap-1.5"><ContractStatusPill status={status} /></div>
        </div>
        <button className="icon-button" onClick={onClose}><XCircle size={14} /></button>
      </div>

      <div className="section-body space-y-3">
        {/* Supplier + Gudang */}
        <div className="grid grid-cols-2 gap-2 text-[11.5px]">
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2">
            <p className="text-[10px] text-[#6B6B73] uppercase font-semibold mb-0.5">Supplier</p>
            <p className="font-semibold">{po.supplier_name}</p>
            <p className="text-[10.5px] text-[#6B6B73]">{po.supplier_contact}</p>
          </div>
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2">
            <p className="text-[10px] text-[#6B6B73] uppercase font-semibold mb-0.5">Gudang Default</p>
            <p className="font-semibold">{po.warehouse_name}</p>
            <p className="text-[10.5px] text-[#6B6B73]">{po.warehouse_city}</p>
          </div>
        </div>

        {/* Masa berlaku */}
        <div className="flex items-center gap-2 text-[11px] text-[#6B6B73]">
          <Calendar size={12} />
          <span>Berlaku: <b className="text-[#3C3C43]">{fmtDate(po.valid_from)}</b> s/d <b className="text-[#3C3C43]">{po.valid_until ? fmtDate(po.valid_until) : "tanpa batas"}</b></span>
        </div>

        {/* Ringkasan nilai (plafon/terpakai/sisa) */}
        <div className="rounded-md border border-[#EFF0F2] overflow-hidden text-[11.5px]" data-testid="blanket-value-summary">
          <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">Plafon Nilai (1.c)</div>
          <div className="p-2.5 space-y-1">
            <Row label="Plafon Kontrak" value={formatCurrency(cap)} />
            <Row label="Terpakai (call-off aktif)" value={formatCurrency(called)} tone="text-[#B45309]" testId="blanket-value-called" />
            <div className="flex justify-between border-t border-[#EFF0F2] pt-1 mt-1">
              <span className="font-bold">Sisa Nilai</span>
              <span data-testid="blanket-value-remaining" className="font-bold tabular-nums text-[#007AFF]">{formatCurrency(remaining)}</span>
            </div>
          </div>
        </div>

        {/* Item kontrak: qty / called / remaining */}
        <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
          <div className="grid grid-cols-[1fr_64px_64px_64px] px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Item ({(po.contract_items || []).length})</span>
            <span className="text-right">Kontrak</span><span className="text-right">Terpakai</span><span className="text-right">Sisa</span>
          </div>
          {(po.contract_items || []).map((it, i) => {
            const c = Number(it.contract_qty || 0);
            const used = Number(it.called_qty || 0);
            const rem = Number(it.remaining_qty ?? Math.max(c - used, 0));
            const pct = c > 0 ? Math.min(100, Math.round((used / c) * 100)) : 0;
            return (
              <div key={i} data-testid={`blanket-item-${i}`} className="px-2.5 py-1.5 border-b border-[#EFF0F2] last:border-0 text-[11px]">
                <div className="grid grid-cols-[1fr_64px_64px_64px] items-center">
                  <div className="min-w-0">
                    <p className="font-semibold truncate">{it.sku}</p>
                    <p className="text-[10px] text-[#6B6B73] truncate">{formatCurrency(it.contract_price)} / {it.unit}</p>
                  </div>
                  <span className="text-right tabular-nums">{formatQty(c)}</span>
                  <span className="text-right tabular-nums text-[#B45309]">{formatQty(used)}</span>
                  <span className="text-right tabular-nums font-semibold text-[#007AFF]">{formatQty(rem)}</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-[#EFF0F2] overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${pct}%`, background: pct >= 100 ? "#B45309" : "#0058CC" }} />
                </div>
              </div>
            );
          })}
        </div>

        {/* Daftar call-off (PO anak) */}
        <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
          <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            Call-off / Release ({callOffs.length})
          </div>
          {callOffs.length === 0 ? (
            <div className="px-2.5 py-4 text-center text-[11px] text-[#9A9BA3]" data-testid="blanket-calloff-empty">Belum ada call-off.</div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[220px] overflow-y-auto">
              {callOffs.map((co) => (
                <div key={co.id} data-testid={`blanket-calloff-${co.id}`} className="flex items-center justify-between px-2.5 py-1.5 text-[11px]">
                  <div className="min-w-0">
                    <p className="font-semibold text-[#0058CC]">{co.po_number}</p>
                    <p className="text-[10px] text-[#6B6B73]">{fmtDate(co.created_at)}{co.approval_reason ? ` · ${co.approval_reason}` : ""}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="tabular-nums font-semibold">{formatCurrency(co.total_amount)}</span>
                    {getStatusBadge(co.status)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Banner status non-aktif */}
        {!isActive && (
          <div data-testid="blanket-inactive-banner" className="flex items-center gap-2 rounded-md border border-[#FFE2B8] bg-[#FFF7EC] px-2.5 py-1.5 text-[11px] text-[#9A5B00]">
            <AlertCircle size={13} />
            <span>Kontrak <b>{status}</b> — call-off baru ditolak (aturan 5.a).{po.close_reason ? ` Alasan: ${po.close_reason}` : ""}</span>
          </div>
        )}

        {/* Aksi */}
        {canManage && (
          <div className="flex flex-col gap-1.5">
            <button data-testid="blanket-calloff-button" disabled={!isActive}
              onClick={() => setShowCallOff(true)}
              className="primary-button justify-center disabled:opacity-40 disabled:cursor-not-allowed">
              <PackagePlus size={13} /> Buat Call-off
            </button>
            {isActive && (
              <button data-testid="blanket-close-button" onClick={() => setConfirmClose(true)} className="danger-button justify-center">
                <Ban size={13} /> Tutup Kontrak
              </button>
            )}
          </div>
        )}
      </div>

      <CallOffModal open={showCallOff} blanket={po}
        onClose={() => setShowCallOff(false)} onCreated={onCallOffCreated} onError={onError} />

      <ConfirmModal
        open={confirmClose}
        title="Tutup Kontrak Blanket"
        message={`Tutup ${po.po_number}? Call-off baru tidak akan diizinkan setelah ditutup.`}
        confirmLabel="Tutup Kontrak"
        danger
        withReason
        reasonLabel="Alasan menutup"
        reasonPlaceholder="mis. kebutuhan selesai / ganti supplier"
        onConfirm={doClose}
        onCancel={() => setConfirmClose(false)}
        testId="blanket-close-confirm"
      />
    </div>
  );
}

function Row({ label, value, tone, testId }) {
  return (
    <div className="flex justify-between">
      <span className="text-[#6B6B73]">{label}</span>
      <span data-testid={testId} className={`font-semibold tabular-nums ${tone || ""}`}>{value}</span>
    </div>
  );
}
