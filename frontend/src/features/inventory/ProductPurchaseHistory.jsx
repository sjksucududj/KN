/**
 * ProductPurchaseHistory (S#2026-07-21) — "Kartu Asal Produk".
 * Riwayat pembelian per event penerimaan: tanggal, supplier, PO, invoice, lot,
 * qty diterima/tersisa, harga rata-rata, jumlah roll. Untuk tracking asal barang.
 * Sumber: GET /api/products/{id}/purchase-history
 */
import { useEffect, useState } from "react";
import { PackageSearch, ChevronDown, ChevronRight, FileText } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatQty } from "../../utils/formatters";

function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return s;
  }
}
function rp(v) {
  const n = Number(v || 0);
  return n ? `Rp ${n.toLocaleString("id-ID")}` : "—";
}

export default function ProductPurchaseHistory({ productId, ownerEntityId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true); setErr("");
      try {
        const params = {};
        if (ownerEntityId && ownerEntityId !== "all") params.entity_id = ownerEntityId;
        const r = await axios.get(`${API}/products/${productId}/purchase-history`, { params });
        if (alive) setData(r.data);
      } catch (e) {
        if (alive) setErr(e.response?.data?.detail || "Gagal memuat kartu asal.");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [productId, ownerEntityId]);

  if (loading) return <div className="px-3 py-2 text-[11px] text-[#9A9BA3]" data-testid="pph-loading">Memuat kartu asal…</div>;
  if (err) return <div className="px-3 py-2 text-[11px] text-[#C0392B]" data-testid="pph-error">{err}</div>;
  if (!data) return null;

  const events = data.events || [];
  const s = data.summary || {};

  return (
    <div className="mt-3 pt-3 border-t border-[#EFE6F6]" data-testid={`product-purchase-history-${productId}`}>
      <div className="flex items-center gap-2 mb-2">
        <PackageSearch size={13} className="text-[#6B219A]" />
        <span className="text-[11px] font-bold uppercase tracking-wide text-[#6B219A]">Kartu Asal / Riwayat Pembelian</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
        <Mini label="Total Diterima" value={formatQty(s.total_received)} />
        <Mini label="Sisa" value={formatQty(s.total_remaining)} />
        <Mini label="Event Beli" value={s.event_count ?? 0} />
        <Mini label="Supplier" value={s.supplier_count ?? 0} />
      </div>

      {events.length === 0 ? (
        <p className="text-[11px] text-[#9A9BA3]" data-testid="pph-empty">Belum ada riwayat penerimaan untuk produk ini.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-[#EFF0F2] bg-white">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="bg-[#FBFAFD] text-left text-[#8E8E93]">
                <th className="px-2 py-1.5 font-semibold">Tanggal</th>
                <th className="px-2 py-1.5 font-semibold">Supplier</th>
                <th className="px-2 py-1.5 font-semibold">PO</th>
                <th className="px-2 py-1.5 font-semibold">No. Faktur</th>
                <th className="px-2 py-1.5 font-semibold">Lot</th>
                <th className="px-2 py-1.5 font-semibold text-right">Qty</th>
                <th className="px-2 py-1.5 font-semibold text-right">Sisa</th>
                <th className="px-2 py-1.5 font-semibold text-right">Harga</th>
                <th className="px-2 py-1.5 font-semibold text-center">Roll</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, idx) => (
                <>
                  <tr
                    key={idx}
                    data-testid={`pph-event-${idx}`}
                    className="border-t border-[#F1F1F4] cursor-pointer hover:bg-[#FBFAFD]"
                    onClick={() => setOpen(open === idx ? null : idx)}
                  >
                    <td className="px-2 py-1.5 whitespace-nowrap">{fmtDate(e.date)}</td>
                    <td className="px-2 py-1.5">{e.supplier_name || "—"}</td>
                    <td className="px-2 py-1.5 font-mono text-[#0058CC]">{e.po_number || "—"}</td>
                    <td className="px-2 py-1.5">
                      {e.supplier_invoice_no
                        ? <span className="inline-flex items-center gap-1 text-[#1B7F4B]"><FileText size={11} />{e.supplier_invoice_no}</span>
                        : <span className="text-[#B0B0B8]">belum ditagih</span>}
                    </td>
                    <td className="px-2 py-1.5 font-mono">{e.lot || "—"}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums font-semibold">{formatQty(e.qty_received)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{formatQty(e.qty_remaining)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{rp(e.avg_unit_cost)}</td>
                    <td className="px-2 py-1.5 text-center">
                      <span className="inline-flex items-center gap-0.5">
                        {open === idx ? <ChevronDown size={12} /> : <ChevronRight size={12} />}{e.roll_count}
                      </span>
                    </td>
                  </tr>
                  {open === idx && (
                    <tr key={`${idx}-rolls`} className="bg-[#FBFAFD]">
                      <td colSpan={9} className="px-3 py-2">
                        <div className="flex flex-wrap gap-1.5" data-testid={`pph-rolls-${idx}`}>
                          {(e.rolls || []).map((r) => (
                            <span key={r.roll_id}
                              className="inline-flex items-center gap-1 rounded border border-[#E4D4F0] bg-white px-1.5 py-0.5 text-[10px]">
                              <span className="font-mono text-[#6B219A]">{r.roll_no || r.roll_id}</span>
                              <span className="text-[#8E8E93]">· {formatQty(r.qty_remaining)}/{formatQty(r.qty_received)}</span>
                              {r.grade && <span className="text-[#8E8E93]">· {r.grade}</span>}
                              <span className={`ml-0.5 rounded px-1 ${r.status === "available" ? "bg-[#E7F6EE] text-[#1B7F4B]" : "bg-[#F0F0F2] text-[#8E8E93]"}`}>{r.status}</span>
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Mini({ label, value }) {
  return (
    <div className="bg-white border border-[#EFF0F2] rounded-md px-2 py-1.5">
      <p className="text-[9px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="tabular-nums text-[13px] font-semibold text-[#3C3C43]">{value}</p>
    </div>
  );
}
