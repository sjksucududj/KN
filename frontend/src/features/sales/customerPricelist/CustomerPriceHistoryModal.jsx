/**
 * CustomerPriceHistoryModal (F1b) — riwayat harga langganan satu produk untuk satu
 * pelanggan: nominal, masa berlaku, status (berlaku / terjadwal / menunggu persetujuan /
 * ditolak / kadaluarsa) dan siapa yang menetapkannya.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, History, X } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { formatCurrency } from "../../../utils/formatters";

const STATUS_META = {
  current: { label: "Berlaku", tone: "bg-[#E6F6EC] text-[#1B7F4B]" },
  scheduled: { label: "Terjadwal", tone: "bg-[#E7F0FF] text-[#0058CC]" },
  pending_approval: { label: "Menunggu persetujuan", tone: "bg-[#FFF6E5] text-[#8C4A00]" },
  rejected: { label: "Ditolak", tone: "bg-[#FDEDE7] text-[#C0392B]" },
  expired: { label: "Kadaluarsa", tone: "bg-[#F5F5F7] text-[#8E8E93]" },
  inactive: { label: "Nonaktif", tone: "bg-[#F5F5F7] text-[#8E8E93]" },
};

const fmtDate = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("id-ID",
      { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return "—"; }
};

export default function CustomerPriceHistoryModal({
  row, customer, entityId, canManage, onClose, onChanged,
}) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const res = await axios.get(`${API}/customer-prices/records`, {
        params: { customer_id: customer.id, product_id: row.product_id, entity_id: entityId },
      });
      setRecords(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal memuat riwayat harga.");
    } finally {
      setLoading(false);
    }
  }, [customer.id, row.product_id, entityId]);

  useEffect(() => { load(); }, [load]);

  const deactivate = async (id) => {
    try {
      await axios.delete(`${API}/customer-prices/${id}`);
      await load();
      onChanged();
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal menonaktifkan harga.");
    }
  };

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4"
      data-testid="cpl-history-modal">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl bg-white shadow-xl">
        <div className="flex items-center gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <History size={16} className="text-[#0058CC]" />
          <h3 className="truncate text-[14px] font-bold">Riwayat Harga · {row.product_name}</h3>
          <button data-testid="cpl-history-close" className="icon-button ml-auto" onClick={onClose}
            aria-label="Tutup"><X size={15} /></button>
        </div>
        <div className="overflow-auto p-4">
          <p className="mb-2 text-[11.5px] text-[#6B6B73]">
            Pelanggan <b>{customer.name}</b> · {row.sku} · harga umum{" "}
            {formatCurrency(row.global_price)}/{row.base_unit}
          </p>
          {err && (
            <div className="mb-2 flex items-center gap-1 text-[12px] text-[#C0392B]">
              <AlertTriangle size={13} />{err}
            </div>
          )}
          {loading ? (
            <div className="grid gap-2">
              {[0, 1, 2].map((i) => <div key={i} className="h-9 animate-pulse rounded bg-[#F5F5F7]" />)}
            </div>
          ) : records.length === 0 ? (
            <div data-testid="cpl-history-empty" className="py-8 text-center text-[12px] text-[#8E8E93]">
              Belum ada harga langganan untuk produk ini — pesanan memakai harga PT/umum.
            </div>
          ) : (
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
                    <th className="px-3 py-2 text-right">Harga</th>
                    <th className="px-3 py-2">Mulai</th>
                    <th className="px-3 py-2">Sampai</th>
                    <th className="px-3 py-2 text-center">Status</th>
                    <th className="px-3 py-2">Catatan</th>
                    {canManage && <th className="px-3 py-2" />}
                  </tr>
                </thead>
                <tbody>
                  {records.map((r) => {
                    const sm = STATUS_META[r.effective_status] || STATUS_META.inactive;
                    return (
                      <tr key={r.id} data-testid={`cpl-hist-row-${r.id}`}
                        className="border-b border-[#F5F5F7] last:border-0">
                        <td className="px-3 py-2 text-right font-semibold tabular-nums text-[#0058CC]">
                          {formatCurrency(r.sell_price)}
                        </td>
                        <td className="px-3 py-2">{fmtDate(r.valid_from)}</td>
                        <td className="px-3 py-2">{r.valid_until ? fmtDate(r.valid_until) : "∞"}</td>
                        <td className="px-3 py-2 text-center">
                          <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${sm.tone}`}>
                            {sm.label}
                          </span>
                        </td>
                        <td className="max-w-[180px] truncate px-3 py-2 text-[#6B6B73]" title={r.note}>
                          {r.note || "—"}
                          {r.created_by && (
                            <span className="block text-[9.5px] text-[#9A9BA3]">oleh {r.created_by}</span>
                          )}
                        </td>
                        {canManage && (
                          <td className="px-3 py-2 text-right">
                            {r.status !== "inactive" && r.status !== "rejected" && (
                              <button data-testid={`cpl-deactivate-${r.id}`}
                                className="text-[11px] text-[#C0392B] hover:underline"
                                onClick={() => deactivate(r.id)}>Nonaktifkan</button>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="flex justify-end border-t border-[#EFF0F2] px-4 py-3">
          <button className="btn-primary px-4 py-1.5 text-[12px]" onClick={onClose}>Tutup</button>
        </div>
      </div>
    </div>
  );
}
