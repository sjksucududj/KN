/**
 * FASE G-6b — Tab **RETUR ANTAR-PT**: daftar + aksi siklus.
 *
 * Siklus yang terlihat di layar: Draf → Disetujui (jurnal pembalik terbit di dua
 * buku) → Barang Sudah Kembali (tugas gudang arah balik selesai; roll dinilai ulang
 * ke harga perolehan asli penjual).
 */
import { useState } from "react";
import { CheckCircle2, Truck, Undo2, Ban, Route } from "lucide-react";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import { fmtDate, RETURN_STATUS_CLASS, RETURN_STATUS_LABEL } from "./intercoApi";
import ReturnChainPanel from "../../sales/ReturnChainPanel";

export default function IntercoReturnsPanel({ rows, canWrite, onApprove, onTask, onCancel }) {
  const [chainFor, setChainFor] = useState("");
  const [askCancel, setAskCancel] = useState(null);
  const [reason, setReason] = useState("");

  return (
    <div className="space-y-3">
      <div className="text-sm text-[#6E6E73]">
        Retur antar-PT adalah jalan resmi ketika barangnya <b>sudah berpindah</b>
        {" "}(pembatalan dokumen sengaja ditolak saat itu). Setiap retur menerbitkan
        nota retur di PT pembeli dan nota kredit di PT penjual — dokumen kembar,
        jurnalnya berpasangan di dua buku (INV-IC-08).
      </div>

      <div className="rounded-xl border border-[#E5E5EA] bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="interco-returns-table">
            <thead className="bg-[#F7F7F9] text-[#3C3C43]">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Nomor</th>
                <th className="text-left px-4 py-3 font-medium">Peran</th>
                <th className="text-left px-4 py-3 font-medium">Atas Transaksi</th>
                <th className="text-left px-4 py-3 font-medium">Barang</th>
                <th className="text-right px-4 py-3 font-medium">Nilai</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Barang Fisik</th>
                <th className="text-right px-4 py-3 font-medium">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F2F2F5]">
              {rows.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-[#8E8E93]">
                  Belum ada retur antar-PT. Buka tab <b>Daftar Transaksi</b>, lalu tekan
                  tombol <b>Retur</b> pada transaksi yang barangnya sudah berpindah.
                </td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} data-testid={`interco-ret-${r.id}`} className="hover:bg-[#FAFAFB]">
                  <td className="px-4 py-3">
                    <div className="font-medium text-[#1D1D1F]">{r.number}</div>
                    <div className="text-xs text-[#8E8E93]">↔ {r.counterpart_number}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs ${
                      r.role === "returner" ? "bg-[#EAF2FF] text-[#0058CC]"
                                            : "bg-[#EDE7FB] text-[#6B219A]"}`}>
                      {r.role === "returner" ? "Mengembalikan" : "Menerima kembali"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-[#1D1D1F]">{r.origin_number}</div>
                    <div className="text-xs text-[#8E8E93]">{fmtDate(r.doc_date)}</div>
                    {/* E9.6 — sambungan ke retur PELANGGAN yang memicu retur ini. */}
                    {r.source_sales_return_number && (
                      <div data-testid={`interco-ret-source-sr-${r.id}`}
                           className="mt-0.5 text-[10.5px] text-[#8C4A00] bg-[#FFF7EF] border border-[#F5C9A6] rounded px-1.5 py-0.5 w-fit">
                        dari retur pelanggan {r.source_sales_return_number}
                      </div>
                    )}
                    <button data-testid={`interco-ret-chain-${r.id}`}
                            onClick={() => setChainFor(chainFor === r.id ? "" : r.id)}
                            className="mt-1 inline-flex items-center gap-1 text-[10.5px] text-[#0058CC] hover:underline">
                      <Route size={11} /> {chainFor === r.id ? "Sembunyikan" : "Jejak Retur"}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    {(r.items || []).map((it) => (
                      <div key={it.product_id} className="text-xs text-[#3C3C43]">
                        {it.sku} · {formatQty(it.quantity)} {it.unit}
                      </div>
                    ))}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium text-[#1D1D1F]">
                    {formatCurrency(r.grand_total)}
                    {r.tax_apply && (
                      <div className="text-xs text-[#8E8E93]">incl. PPN {r.tax_rate}%</div>
                    )}
                    {/* FASE E-9 (E9.4) — nilai UANG retur bisa berbeda dari nilai BARANG
                        yang benar-benar berpindah: barang hasil retur pelanggan yang
                        rusak sudah dihapus-bukukan menjadi Rp 0. Finance harus melihat
                        selisih ini, bukan menemukannya belakangan di buku besar. */}
                    {r.status === "completed" && Math.abs(Number(r.goods_value_gap || 0)) > 0.01 && (
                      <div data-testid={`interco-ret-gap-${r.id}`}
                           className="mt-1 text-[10.5px] text-left text-[#9A6700] bg-[#FFF3DC] border border-[#EFD9A8] rounded px-1.5 py-1">
                        Nilai barang yang berpindah {formatCurrency(r.goods_out_value || 0)} —
                        beda {formatCurrency(r.goods_value_gap)} dari nilai retur karena
                        barangnya sudah dihapus-bukukan saat retur pelanggan.
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs ${
                      RETURN_STATUS_CLASS[r.status] || ""}`}>
                      {RETURN_STATUS_LABEL[r.status] || r.status}
                    </span>
                    {r.reason && (
                      <div className="text-[11px] text-[#8E8E93] mt-0.5 max-w-[220px]">{r.reason}</div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {r.warehouse_transfer_code ? (
                      <div className="text-xs">
                        <div className="inline-flex items-center gap-1 text-[#3C3C43]">
                          <Truck size={12} /> {r.warehouse_transfer_code}
                        </div>
                        <div className={r.warehouse_transfer_status === "completed"
                          ? "text-[#1B7F4B]" : "text-[#B26A00]"}>
                          {r.warehouse_transfer_status === "completed"
                            ? "sudah kembali" : "menunggu gudang"}
                        </div>
                      </div>
                    ) : (
                      <span className="text-xs text-[#C9C9CE]">belum dikirim balik</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      {canWrite && r.status === "draft" && r.role === "returner" && (
                        <>
                          <button onClick={() => onApprove?.(r)}
                                  data-testid={`interco-ret-approve-${r.id}`}
                                  title="Setujui retur (pembuat ≠ penyetuju)"
                                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-[#0058CC] text-[#0058CC] bg-white hover:bg-[#EAF2FF]">
                            <CheckCircle2 size={12} /> Setujui
                          </button>
                          <button onClick={() => { setAskCancel(r); setReason(""); }}
                                  data-testid={`interco-ret-cancel-${r.id}`}
                                  title="Batalkan draf retur"
                                  className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md text-[#C0392B] hover:bg-[#FDEDE7]">
                            <Ban size={12} />
                          </button>
                        </>
                      )}
                      {canWrite && r.status === "approved" && r.role === "returner"
                        && !r.warehouse_transfer_id && (
                        <button onClick={() => onTask?.(r)}
                                data-testid={`interco-ret-task-${r.id}`}
                                title="Kirim barangnya kembali lewat gudang"
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border border-[#0058CC] text-[#0058CC] bg-white hover:bg-[#EAF2FF]">
                          <Truck size={12} /> Tugas Gudang Balik
                        </button>
                      )}
                      {r.status === "approved" && r.warehouse_transfer_id
                        && r.warehouse_transfer_status !== "completed" && (
                        <span className="text-xs text-[#B26A00]"
                              data-testid={`interco-ret-waiting-${r.id}`}>
                          Menunggu gudang menyetujui
                        </span>
                      )}
                      {r.status === "completed" && (
                        <span className="inline-flex items-center gap-1 text-xs text-[#1B7F4B]"
                              data-testid={`interco-ret-done-${r.id}`}>
                          <Undo2 size={12} /> selesai
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {chainFor && (
                <tr data-testid={`interco-ret-chain-row-${chainFor}`}>
                  <td colSpan={8} className="px-4 py-3 bg-[#FAFAFB]">
                    <ReturnChainPanel docId={chainFor} />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {askCancel && (
        <div className="fixed inset-0 z-50 bg-[rgba(15,23,42,0.45)] flex items-center justify-center p-4"
             data-testid="interco-ret-cancel-modal"
             onClick={(e) => { if (e.target === e.currentTarget) setAskCancel(null); }}>
          <div className="w-full max-w-md rounded-2xl bg-white shadow-xl p-6 space-y-3">
            <h3 className="text-base font-semibold text-[#1D1D1F]">
              Batalkan draf retur {askCancel.number}
            </h3>
            <p className="text-[13px] text-[#6E6E73]">
              Hanya draf yang bisa dibatalkan — retur yang sudah disetujui jurnalnya sudah
              hidup di dua buku.
            </p>
            <textarea
              rows={2} value={reason} onChange={(e) => setReason(e.target.value)}
              data-testid="interco-ret-cancel-reason"
              placeholder="Alasan pembatalan (minimal 5 huruf)"
              className="w-full rounded-lg border border-[#E5E5EA] bg-white px-3 py-2 text-sm text-[#1D1D1F]"
            />
            <div className="flex items-center justify-end gap-2">
              <button onClick={() => setAskCancel(null)}
                      data-testid="interco-ret-cancel-close"
                      className="px-3.5 py-2 text-sm rounded-lg border border-[#E5E5EA] bg-white text-[#3C3C43] hover:bg-[#F2F2F5]">
                Tutup
              </button>
              <button
                onClick={() => { onCancel?.(askCancel, reason.trim()); setAskCancel(null); }}
                disabled={reason.trim().length < 5}
                data-testid="interco-ret-cancel-confirm"
                className="px-3.5 py-2 text-sm rounded-lg bg-[#C0392B] text-white hover:bg-[#A93226] disabled:opacity-40">
                Batalkan Retur
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
