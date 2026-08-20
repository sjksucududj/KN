/**
 * FASE G-6b — Tab **RAPOR MARGIN GRUP** antar-PT.
 *
 * Menjawab pertanyaan yang sebelumnya tidak bisa dijawab layar mana pun:
 * *“berapa margin antar-PT kami, dan berapa yang sudah benar-benar jadi uang dari
 * pihak luar?”* Bagian yang belum terjual keluar (“belum terealisasi”) dihitung dari
 * sisa panjang roll bertanda transaksi itu di gudang pembeli — data nyata, bukan
 * taksiran — dan angka itulah yang dieliminasi di Konsolidasi Grup (INV-IC-03).
 */
import { useCallback, useEffect, useState } from "react";
import { TrendingUp, Layers, AlertTriangle, Package, Filter } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import { fmtDate, STATUS_CLASS, STATUS_LABEL } from "./intercoApi";
import KNSelect from "../../../components/KNSelect";

export default function IntercoMarginPanel({ report, entityId = "" }) {
  const t = report?.totals || {};
  const pairs = report?.pairs || [];
  const rows = report?.rows || [];
  const gap = Math.abs(t.elimination_gap || 0) > 0.01;

  // FASE P3 — Rapor margin PER BARANG (urut margin terbesar) + penyaring pasangan PT.
  const [byProduct, setByProduct] = useState(null);
  const [pairFilter, setPairFilter] = useState("");
  const [loadingBP, setLoadingBP] = useState(false);

  const loadByProduct = useCallback(async () => {
    setLoadingBP(true);
    try {
      const res = await axios.get(`${API}/interco/margin-by-product`, {
        params: { entity_id: entityId || "all", pair: pairFilter || "" },
      });
      setByProduct(res.data || null);
    } catch {
      setByProduct(null);
    } finally {
      setLoadingBP(false);
    }
  }, [entityId, pairFilter]);

  useEffect(() => { loadByProduct(); }, [loadByProduct]);

  const bpRows = byProduct?.rows || [];
  const bpPairs = byProduct?.pairs || [];
  const bpTot = byProduct?.totals || {};

  return (
    <div className="space-y-4" data-testid="interco-margin-panel">
      <div className="text-sm text-[#6E6E73]">
        Margin antar-PT = harga internal − HPP penjual. Selama barangnya masih di gudang
        pembeli, margin itu <b>belum nyata bagi grup</b> dan dieliminasi di konsolidasi.
        Begitu pembeli menjualnya ke pihak luar, margin berpindah ke kolom
        {" "}<b>sudah terealisasi</b> dan tidak dieliminasi lagi.
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Kpi label="Margin Antar-PT" value={formatCurrency(t.margin || 0)}
             hint={`${t.doc_count || 0} dokumen · ${t.margin_pct || 0}% dari nilai jual`}
             testid="interco-margin-kpi-total" />
        <Kpi label="Belum Terealisasi" value={formatCurrency(t.unrealized_margin || 0)}
             hint="masih menempel di persediaan pembeli"
             testid="interco-margin-kpi-unrealized" />
        <Kpi label="Sudah Terealisasi" value={formatCurrency(t.realized_margin || 0)}
             hint="barangnya sudah terjual ke pihak luar"
             testid="interco-margin-kpi-realized" />
        <Kpi label="Dieliminasi di Konsolidasi"
             value={formatCurrency(t.eliminated_unrealized || 0)}
             hint={gap ? "tidak sama dengan angka belum terealisasi"
                       : "sama dengan angka belum terealisasi"}
             testid="interco-margin-kpi-eliminated" />
      </div>

      {gap && (
        <div className="flex items-start gap-2 rounded-lg bg-[#FFF4E5] px-3 py-2.5 text-[13px] text-[#8A5300]"
             data-testid="interco-margin-gap-warning">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>
            Selisih {formatCurrency(t.elimination_gap)} antara yang dieliminasi dan yang
            belum terealisasi. Buka <b>Keuangan → Laporan &amp; Analitik → Konsolidasi Grup</b>
            {" "}lalu tekan <b>Sinkron Antar-PT (G-6)</b> untuk menghitung ulang.
          </span>
        </div>
      )}

      {/* FASE E-7 (E7.3) — keputusan pemilik 4b: HPP taksiran boleh, TAPI wajib berlabel.
          Pita ini muncul hanya bila ada dokumen yang HPP-nya belum diposting. */}
      {t.cost_estimated && (
        <div className="flex items-start gap-2 rounded-lg bg-[#FFF4E5] px-3 py-2.5 text-[13px] text-[#8A5300]"
             data-testid="interco-margin-estimated-warning">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>
            <b>{t.estimated_doc_count} dokumen memakai HPP taksiran</b> — jurnal HPP penjual
            baru terbit saat barang keluar gudang. Margin bila taksiran itu dipakai:{" "}
            <b>{formatCurrency(t.margin_estimate || 0)}</b> (angka resmi di kartu atas
            memakai HPP yang sudah diposting saja). Jangan pakai angka ini untuk keputusan
            harga sebelum barangnya benar-benar dikirim.
          </span>
        </div>
      )}

      <div className="rounded-xl border border-[#E5E5EA] bg-white overflow-hidden">
        <div className="px-4 py-3 bg-[#F7F7F9] text-sm font-medium text-[#3C3C43] flex items-center gap-2">
          <Layers size={15} /> Per Pasangan PT
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="interco-margin-pairs-table">
            <thead className="bg-white text-[#6E6E73] border-b border-[#F2F2F5]">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Penjual → Pembeli</th>
                <th className="text-right px-4 py-2.5 font-medium">Dokumen</th>
                <th className="text-right px-4 py-2.5 font-medium">Nilai Jual Internal</th>
                <th className="text-right px-4 py-2.5 font-medium">HPP Penjual</th>
                <th className="text-right px-4 py-2.5 font-medium">Margin</th>
                <th className="text-right px-4 py-2.5 font-medium">Belum Terealisasi</th>
                <th className="text-right px-4 py-2.5 font-medium">Sudah Terealisasi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F2F2F5]">
              {pairs.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-[#8E8E93]">
                  Belum ada transaksi antar-PT yang menghasilkan margin.
                </td></tr>
              )}
              {pairs.map((p) => (
                <tr key={p.key} data-testid={`interco-margin-pair-${p.key}`} className="hover:bg-[#FAFAFB]">
                  <td className="px-4 py-3">
                    <div className="text-[#1D1D1F]">{p.seller_entity_name}</div>
                    <div className="text-xs text-[#8E8E93]">→ {p.buyer_entity_name}</div>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{p.doc_count}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(p.subtotal)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {formatCurrency(p.cost)}
                    {p.cost_estimated && (
                      <div data-testid={`interco-margin-pair-est-${p.key}`}
                           title={`${p.estimated_doc_count} dokumen HPP-nya belum diposting — taksiran WAC ${formatCurrency(p.cost_estimate || 0)}`}
                           className="text-[10px] text-[#B26A00]">
                        + {p.estimated_doc_count} dok. HPP taksiran (≈ {formatCurrency(p.cost_estimate || 0)})
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium text-[#1D1D1F]">
                    {formatCurrency(p.margin)}
                    <div className="text-xs text-[#8E8E93]">{p.margin_pct}%</div>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-[#B26A00]">
                    {formatCurrency(p.unrealized_margin)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-[#1B7F4B]">
                    {formatCurrency(p.realized_margin)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-[#E5E5EA] bg-white overflow-hidden">
        <div className="px-4 py-3 bg-[#F7F7F9] text-sm font-medium text-[#3C3C43] flex items-center gap-2">
          <TrendingUp size={15} /> Per Transaksi
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="interco-margin-rows-table">
            <thead className="bg-white text-[#6E6E73] border-b border-[#F2F2F5]">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Nomor</th>
                <th className="text-left px-4 py-2.5 font-medium">Status</th>
                <th className="text-right px-4 py-2.5 font-medium">Nilai Jual</th>
                <th className="text-right px-4 py-2.5 font-medium">HPP</th>
                <th className="text-right px-4 py-2.5 font-medium">Margin</th>
                <th className="text-right px-4 py-2.5 font-medium">Masih di Pembeli</th>
                <th className="text-right px-4 py-2.5 font-medium">Belum Terealisasi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F2F2F5]">
              {rows.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-[#8E8E93]">
                  Belum ada data.
                </td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.pair_id} data-testid={`interco-margin-row-${r.pair_id}`} className="hover:bg-[#FAFAFB]">
                  <td className="px-4 py-3">
                    <div className="font-medium text-[#1D1D1F]">{r.number}</div>
                    <div className="text-xs text-[#8E8E93]">{fmtDate(r.doc_date)}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs ${STATUS_CLASS[r.status] || ""}`}>
                      {STATUS_LABEL[r.status] || r.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {formatCurrency(r.subtotal)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {/* E7.3 — HPP taksiran WAJIB berlabel: yang dulu tampil "Rp 0 · margin
                        100%" sekarang menampilkan taksiran WAC + alasannya. */}
                    {r.cost_estimated ? (
                      <>
                        <span data-testid={`interco-margin-cost-est-${r.pair_id}`}
                              title={r.cost_estimate_reason || ""}
                              className="inline-flex items-center gap-1 rounded bg-[#FFF4E5] px-1.5 py-0.5 text-[11px] font-semibold text-[#8A5300]">
                          ≈ {formatCurrency(r.cost_estimate || 0)}
                        </span>
                        <div className="text-[10px] text-[#B26A00]">
                          HPP taksiran (WAC) — jurnal HPP belum ada
                        </div>
                      </>
                    ) : formatCurrency(r.cost)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium">
                    {r.cost_estimated ? (
                      <>
                        <span title={r.cost_estimate_reason || ""}>
                          ≈ {formatCurrency(r.margin_estimate || 0)}
                        </span>
                        <div className="text-[10px] text-[#B26A00]">
                          belum final ({r.margin_pct_estimate || 0}%)
                        </div>
                      </>
                    ) : formatCurrency(r.margin)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {formatQty(r.qty_remaining)} / {formatQty(r.qty_base)}
                    <div className="text-[11px] text-[#8E8E93]">
                      {Math.round((r.unsold_ratio || 0) * 100)}% belum terjual keluar
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-[#B26A00]">
                    {formatCurrency(r.unrealized_margin)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* FASE P3 — RAPOR MARGIN PER BARANG (urut margin terbesar) + penyaring pasangan PT */}
      <div className="rounded-xl border border-[#E5E5EA] bg-white overflow-hidden" data-testid="interco-margin-by-product">
        <div className="px-4 py-3 bg-[#F7F7F9] text-sm font-medium text-[#3C3C43] flex items-center gap-2 flex-wrap">
          <Package size={15} /> Per Barang — margin terbesar dulu
          <div className="ml-auto flex items-center gap-1.5">
            <Filter size={13} className="text-[#8E8E93]" />
            <KNSelect
              data-testid="interco-margin-pair-filter"
              className="text-xs border border-[#E5E5EA] rounded-md px-2 py-1 bg-white"
              value={pairFilter}
              onValueChange={setPairFilter}
              aria-label="Filter pasangan badan usaha"
              placeholder="Semua pasangan PT"
              options={[
                { value: "", label: "Semua pasangan PT" },
                ...bpPairs.map((p) => ({ value: p.key, label: p.label })),
              ]}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3">
          <MiniKpi label="Produk" value={bpTot.product_count || 0} testid="bp-kpi-count" />
          <MiniKpi label="Nilai Jual Internal" value={formatCurrency(bpTot.revenue || 0)} testid="bp-kpi-revenue" />
          <MiniKpi label="HPP Penjual" value={formatCurrency(bpTot.cost || 0)} testid="bp-kpi-cost" />
          <MiniKpi label="Margin" value={formatCurrency(bpTot.margin || 0)} hint={`${bpTot.margin_pct || 0}% dari nilai jual`} testid="bp-kpi-margin" />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="interco-margin-product-table">
            <thead className="bg-white text-[#6E6E73] border-b border-[#F2F2F5]">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">#</th>
                <th className="text-left px-4 py-2.5 font-medium">Barang</th>
                <th className="text-right px-4 py-2.5 font-medium">Qty</th>
                <th className="text-right px-4 py-2.5 font-medium">Nilai Jual Internal</th>
                <th className="text-right px-4 py-2.5 font-medium">HPP</th>
                <th className="text-right px-4 py-2.5 font-medium">Margin</th>
                <th className="text-right px-4 py-2.5 font-medium">Margin %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F2F2F5]">
              {loadingBP && (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-[#8E8E93]">Memuat…</td></tr>
              )}
              {!loadingBP && bpRows.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-[#8E8E93]">
                  Belum ada barang antar-PT pada penyaring ini.
                </td></tr>
              )}
              {!loadingBP && bpRows.map((r, i) => (
                <tr key={r.product_id} data-testid={`bp-row-${r.product_id}`} className="hover:bg-[#FAFAFB]">
                  <td className="px-4 py-3 tabular-nums text-[#8E8E93]">{i + 1}</td>
                  <td className="px-4 py-3">
                    <div className="text-[#1D1D1F]">{r.product_name}</div>
                    <div className="text-xs text-[#8E8E93]">
                      {r.sku ? `${r.sku} · ` : ""}{(r.pairs || []).join(", ")}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatQty(r.qty)} {r.unit}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(r.revenue)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {formatCurrency(r.cost)}
                    {r.cost_estimated && (
                      <div className="text-[10px] text-[#B26A00]">estimasi WAC (HPP belum posting)</div>
                    )}
                  </td>
                  <td className={`px-4 py-3 text-right tabular-nums font-semibold ${r.margin >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}>
                    {formatCurrency(r.margin)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-[#6E6E73]">{r.margin_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2 text-[11px] text-[#9A9BA3]">
          Nilai jual = harga internal penjual (sebelum retur). HPP dipecah proporsional dari HPP transaksi
          (otoritatif); bila HPP belum diposting (barang belum jalan) dipakai <b>estimasi WAC</b>.
        </div>
      </div>
    </div>
  );
}

function MiniKpi({ label, value, hint, testid }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] px-3 py-2" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-wide text-[#8E8E93]">{label}</div>
      <div className="mt-0.5 text-[15px] font-semibold text-[#1D1D1F] tabular-nums">{value}</div>
      {hint && <div className="text-[10px] text-[#9A9BA3]">{hint}</div>}
    </div>
  );
}

function Kpi({ label, value, hint, testid }) {
  return (
    <div className="rounded-xl border border-[#E5E5EA] bg-white p-4" data-testid={testid}>
      <div className="text-xs uppercase tracking-wide text-[#6E6E73]">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold text-[#1D1D1F] tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-[#8E8E93]">{hint}</div>
    </div>
  );
}
