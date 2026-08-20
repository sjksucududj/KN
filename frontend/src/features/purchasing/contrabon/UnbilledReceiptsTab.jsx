/**
 * FASE G-7 · US3 — **GR BELUM DITAGIH**: barang sudah masuk gudang tetapi faktur
 * supplier belum datang. Tanpa layar ini tidak ada satu pun tempat di sistem yang
 * menjawab "penerimaan mana yang belum ditagih?" — sehingga hutang bisa lupa dicatat
 * dan supplier menagih belakangan tanpa pembanding.
 */
import { useState, Fragment } from "react";
import { PackageSearch, AlertTriangle, ChevronDown, ChevronRight, Plus } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import { fmtDate, humanDays } from "./contraBonApi";

export default function UnbilledReceiptsTab({ data, loading, canWrite = true, onCreateFor }) {
  const [open, setOpen] = useState({});
  const rows = data?.rows || [];

  return (
    <div data-testid="cb-unbilled-tab">
      <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="stat-card">
          <p className="stat-label">Nilai belum ditagih</p>
          <p className="stat-value text-[#0058CC]" data-testid="cb-unbilled-total">
            {formatCurrency(data?.total_value)}
          </p>
          <p className="text-[10px] text-[#8E8E93]">barang sudah diterima, faktur belum datang</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Pesanan pembelian</p>
          <p className="stat-value" data-testid="cb-unbilled-po-count">{data?.po_count || 0}</p>
          <p className="text-[10px] text-[#8E8E93]">PO yang masih menyisakan penerimaan</p>
        </div>
        <div className={`stat-card ${data?.overdue_count ? "ring-1 ring-[#F3C9C7]" : ""}`}>
          <p className="stat-label">Sudah tertunggak</p>
          <p className={`stat-value ${data?.overdue_count ? "text-[#C0392B]" : "text-[#1B7F4B]"}`}
            data-testid="cb-unbilled-overdue">{data?.overdue_count || 0}</p>
          <p className="text-[10px] text-[#8E8E93]">
            lewat {humanDays(data?.age_threshold_days)} sejak penerimaan terakhir
          </p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Ambang tertunggak</p>
          <p className="stat-value">{humanDays(data?.age_threshold_days)}</p>
          <p className="text-[10px] text-[#8E8E93]">
            diatur di Pengaturan → Kontrabon
          </p>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-[#E5E5EA] bg-white">
        <div className="max-h-[520px] overflow-auto">
          <table className="data-table w-full text-[12px]">
            <thead className="sticky top-0 z-10 bg-[#FAFBFC]">
              <tr className="text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93]">
                <th className="px-3 py-2">Pesanan pembelian</th>
                <th className="px-3 py-2">Supplier</th>
                <th className="px-3 py-2">Penerimaan terakhir</th>
                <th className="px-3 py-2 text-right">Nilai belum ditagih</th>
                <th className="px-3 py-2">Umur</th>
                <th className="px-3 py-2 text-right">Tindakan</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-[#8E8E93]">
                  Menghitung penerimaan yang belum tertagih…
                </td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-8 text-center"
                  data-testid="cb-unbilled-empty">
                  <p className="text-[13px] font-semibold text-[#1B7F4B]">
                    Semua penerimaan barang sudah tertagih.
                  </p>
                  <p className="mt-1 text-[11.5px] text-[#6B6B73]">
                    Tidak ada barang masuk yang menggantung tanpa faktur supplier.
                  </p>
                </td></tr>
              )}
              {!loading && rows.map((r) => (
                <Fragment key={r.po_id}>
                  <tr data-testid={`cb-unbilled-row-${r.po_id}`}
                    className="border-t border-[#F2F2F5] hover:bg-[#F7F9FC]">
                    <td className="px-3 py-2">
                      <button className="flex items-center gap-1 font-bold text-[#0058CC]"
                        data-testid={`cb-unbilled-expand-${r.po_id}`}
                        onClick={() => setOpen((o) => ({ ...o, [r.po_id]: !o[r.po_id] }))}>
                        {open[r.po_id] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        {r.po_number || r.po_id}
                      </button>
                      <p className="pl-4 text-[10px] text-[#8E8E93]">status {r.po_status}</p>
                    </td>
                    <td className="px-3 py-2 font-semibold">{r.supplier_name || "—"}</td>
                    <td className="px-3 py-2">
                      <p>{fmtDate(r.last_receipt_at)}</p>
                      <p className="text-[10px] text-[#8E8E93]">
                        {r.grn_task_id ? `tugas gudang ${r.grn_task_id.slice(-6)}` : "tanpa tugas gudang"}
                      </p>
                    </td>
                    <td className="px-3 py-2 text-right font-semibold tabular-nums">
                      {formatCurrency(r.unbilled_value)}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold ${
                        r.overdue ? "bg-[#FDE2E2] text-[#9B1C1C]" : "bg-[#F2F2F5] text-[#5A5A60]"}`}>
                        {r.overdue && <AlertTriangle size={9} />} {humanDays(r.age_days)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {canWrite ? (
                        <button className="link-button" data-testid={`cb-unbilled-make-${r.po_id}`}
                          onClick={() => onCreateFor(r.supplier_id)}>
                          <Plus size={11} /> Buat kontrabon
                        </button>
                      ) : (
                        <span className="text-[10px] text-[#C7C7CC]">tagih lewat Keuangan</span>
                      )}
                    </td>
                  </tr>
                  {open[r.po_id] && (
                    <tr className="bg-[#FAFBFC]">
                      <td colSpan={6} className="px-6 py-2">
                        <table className="w-full text-[11px]">
                          <thead>
                            <tr className="text-left text-[9.5px] uppercase text-[#8E8E93]">
                              <th className="py-1">Barang</th>
                              <th className="py-1 text-right">Diterima</th>
                              <th className="py-1 text-right">Sudah ditagih</th>
                              <th className="py-1 text-right">Belum ditagih</th>
                              <th className="py-1 text-right">Nilai</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(r.items || []).map((it) => (
                              <tr key={it.product_id} className="border-t border-[#EFF0F2]">
                                <td className="py-1">
                                  {it.product_name}
                                  <span className="text-[#8E8E93]"> · {it.sku}</span>
                                </td>
                                <td className="py-1 text-right tabular-nums">
                                  {it.received_qty} {it.unit}
                                </td>
                                <td className="py-1 text-right tabular-nums">{it.billed_qty}</td>
                                <td className="py-1 text-right font-semibold tabular-nums">
                                  {it.unbilled_qty}
                                </td>
                                <td className="py-1 text-right tabular-nums">
                                  {formatCurrency(it.unbilled_value)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="mt-2 flex items-start gap-1 text-[11px] text-[#9A9BA3]">
        <PackageSearch size={11} className="mt-[2px] shrink-0" />
        Angka di sini dihitung dari penerimaan gudang dikurangi yang sudah tertagih —
        bukan koleksi terpisah, sehingga tidak bisa berbeda dengan layar Gudang.
      </p>
    </div>
  );
}
