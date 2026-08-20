/**
 * FASE G-6 — **DETAIL PANEL** transaksi antar-PT.
 *
 * Menyajikan pair (dokumen kembar) berdampingan sehingga user bisa MELACAK:
 *   [KIRI]   PT PENJUAL — SO + Surat Jalan + Invoice internal
 *   [KANAN]  PT PEMBELI — PO internal + Vendor Bill internal
 *
 * Ditambah bukti yang bisa diperiksa sendiri:
 *   * Jurnal DUA BUKU (dokumen), jurnal HPP penjual & jurnal penerimaan pembeli
 *   * Jurnal PEMBALIK bila transaksi dibatalkan
 *   * Eliminasi grup (unrealized profit) — bukti US7 di layar, bukan cuma di laporan
 *   * Tugas gudang (perpindahan fisik) + catatan "jurnal at-cost dilewati" (US8)
 *   * Timeline aksi + daftar settlement yang menyentuh pair ini
 *
 * Semua diambil dari SATU endpoint `GET /api/interco/transactions/{id}/journal`.
 * (Sebelumnya layar memanggil `/api/gl/entries` yang tidak pernah ada sehingga blok
 * jurnal diam-diam kosong — user tidak pernah melihat buktinya.)
 */
import { useEffect, useState } from "react";
import {
  X, ArrowRightLeft, Clock, BookOpen, Layers, Truck, Scissors,
  Undo2, ShieldCheck, Receipt,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import DocumentActionsBar from "../../documents/DocumentActionsBar";
import {
  RETURN_STATUS_CLASS, RETURN_STATUS_LABEL, fmtDate,
} from "./intercoApi";
import {
  Section, SidePanel, JournalTable, Timeline,
} from "./IntercoDetailParts";

const EMPTY_J = {
  seller: null, buyer: null, cogs: null, receipt: null, reversals: [],
  settlement_entries: [], settlements: [], eliminations: [], warehouse_tasks: [],
  // FASE G-6b — retur antar-PT + faktur pajak internal
  returns: [], return_entries: [], tax_invoices_out: [], tax_invoices_in: [],
};

export default function IntercoDetailPanel({ intercoId, currentUser, onClose }) {
  const [pair, setPair] = useState(null);
  const [j, setJ] = useState(EMPTY_J);
  const [loading, setLoading] = useState(true);
  const [jErr, setJErr] = useState("");

  useEffect(() => {
    if (!intercoId) return;
    let cancelled = false;
    (async () => {
      setLoading(true); setJErr("");
      try {
        const r = await axios.get(`${API}/interco/transactions/${intercoId}`);
        if (cancelled) return;
        setPair(r.data);
        try {
          const rj = await axios.get(`${API}/interco/transactions/${intercoId}/journal`);
          if (!cancelled) setJ({ ...EMPTY_J, ...(rj.data || {}) });
        } catch (e) {
          if (!cancelled) {
            setJ(EMPTY_J);
            setJErr("Bukti jurnal tidak bisa dimuat. Coba muat ulang halaman.");
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [intercoId]);

  if (!intercoId) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="interco-detail-modal">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-6xl max-h-[92vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#E5E5EA]">
          <div className="flex items-center gap-3">
            <ArrowRightLeft size={18} className="text-[#0058CC]" />
            <div>
              <h2 className="text-lg font-semibold text-[#1D1D1F]">
                Detail Transaksi Antar-PT
              </h2>
              {pair && (
                <p className="text-xs text-[#6E6E73] mt-0.5">
                  {pair.seller?.number} ↔ {pair.buyer?.number} · pair {pair.pair_id}
                </p>
              )}
            </div>
          </div>
          <button onClick={onClose} data-testid="interco-detail-close" className="p-1.5 hover:bg-[#F2F2F5] rounded-lg">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-10 text-center text-[#8E8E93]" data-testid="interco-detail-loading">Memuat…</div>
          ) : !pair ? (
            <div className="p-10 text-center text-[#8E8E93]">Transaksi tidak ditemukan.</div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-[#F2F2F5]">
                <SidePanel role="seller" doc={pair.seller}
                           journal={j.seller} extraJournal={j.cogs}
                           extraLabel="Jurnal HPP (barang keluar)" />
                <SidePanel role="buyer" doc={pair.buyer}
                           journal={j.buyer} extraJournal={j.receipt}
                           extraLabel="Jurnal Penerimaan (transit → persediaan)" />
              </div>

              {jErr && (
                <div className="mx-6 mb-2 rounded-lg bg-[#FDEDE7] border border-[#F7C3B4] text-[#9B1C1C] text-[12px] px-3 py-2"
                     data-testid="interco-detail-journal-error">
                  {jErr}
                </div>
              )}

              {/* Perpindahan fisik (US8) */}
              <Section icon={Truck} title="Perpindahan Fisik (Tugas Gudang)"
                       testid="interco-detail-tasks">
                {j.warehouse_tasks.length === 0 ? (
                  <p className="text-xs text-[#8E8E93]">
                    Belum ada tugas gudang. Barang antar-PT berpindah lewat tugas gudang —
                    dari daftar transaksi tekan <b>“Buat Tugas Gudang”</b>.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {j.warehouse_tasks.map((t) => (
                      <div key={t.id} data-testid={`interco-detail-task-${t.id}`}
                           className="rounded-lg border border-[#E5E5EA] px-3 py-2.5">
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-medium text-[#1D1D1F]">{t.code}</span>
                          <span className={`inline-flex px-2 py-0.5 rounded text-xs ${
                            t.status === "completed" ? "bg-[#E8F6EE] text-[#1B7F4B]"
                              : t.status === "waiting_approval" ? "bg-[#FFF4E5] text-[#B26A00]"
                              : "bg-[#F2F2F5] text-[#5A5A60]"}`}>
                            {t.status === "completed" ? "Barang sudah berpindah"
                              : t.status === "waiting_approval" ? "Menunggu persetujuan gudang"
                              : t.status === "cancelled" ? "Tugas dibatalkan (roll dilepas)"
                              : t.status === "rejected" ? "Ditolak gudang"
                              : t.status}
                          </span>
                          {t.approved_at && (
                            <span className="text-xs text-[#6E6E73]">
                              disetujui {fmtDate(t.approved_at)} · {t.approved_by || "—"}
                            </span>
                          )}
                        </div>
                        {(t.items || []).length > 0 && (
                          <div className="mt-1.5 text-xs text-[#6E6E73] flex items-center gap-1.5">
                            <Scissors size={12} />
                            {(t.items || []).map((it, i) => (
                              <span key={i}>
                                {it.product_name || it.sku} {formatQty(it.qty)} {it.unit}
                                {(it.rolls || []).length > 0 && ` · ${it.rolls.length} roll`}
                                {i < (t.items || []).length - 1 ? " · " : ""}
                              </span>
                            ))}
                          </div>
                        )}
                        {t.je_intercompany && t.je_intercompany.posted === false && (
                          <div className="mt-2 flex items-start gap-2 rounded-md bg-[#EAF2FF] px-2.5 py-2 text-[11px] text-[#0058CC]">
                            <ShieldCheck size={13} className="mt-0.5 shrink-0" />
                            <span>
                              {t.je_intercompany.skipped_reason}
                              {t.je_intercompany.revalued_rolls > 0 && (
                                <> {" "}<b>{t.je_intercompany.revalued_rolls} roll</b> dinilai ulang
                                  ke harga beli internal (GL persediaan = subledger).</>
                              )}
                            </span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Section>

              {/* Eliminasi grup (US7) */}
              <Section icon={Layers} title="Eliminasi Konsolidasi Grup (Unrealized Profit)"
                       testid="interco-detail-eliminations">
                {j.eliminations.length === 0 ? (
                  <p className="text-xs text-[#8E8E93]">
                    Belum ada entri eliminasi (transaksi masih draf / sudah dibatalkan).
                  </p>
                ) : (
                  j.eliminations.map((e) => (
                    <div key={e.id} className="rounded-lg border border-[#E5E5EA] overflow-hidden mb-2">
                      <div className="px-3 py-2 bg-[#F7F7F9] flex flex-wrap items-center gap-2">
                        <span className="text-xs font-medium text-[#3C3C43]">{e.name}</span>
                        {e.auto_generated && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#EDE7FB] text-[#6B219A] font-semibold">
                            AUTO G-6
                          </span>
                        )}
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                          e.balanced ? "bg-[#E8F6EE] text-[#1B7F4B]" : "bg-[#FDEDE7] text-[#C0392B]"}`}>
                          {e.balanced ? "SEIMBANG" : "TIDAK SEIMBANG"}
                        </span>
                        <span className="ml-auto text-[11px] text-[#6E6E73]">
                          efektif {fmtDate(e.effective_date)}
                        </span>
                      </div>
                      <JournalTable lines={e.lines || []} />
                      <div className="px-3 py-2 text-[11px] text-[#6E6E73] bg-white border-t border-[#F2F2F5]">
                        Laba antar-PT tidak boleh menggelembungkan laba grup selama barangnya
                        belum terjual ke pihak luar (INV-IC-03).
                      </div>
                    </div>
                  ))
                )}
              </Section>

              {/* Jurnal settlement */}
              {j.settlement_entries.length > 0 && (
                <Section icon={BookOpen} title="Jurnal Settlement (Netting) di Dua Buku"
                         testid="interco-detail-settlement-journal">
                  {j.settlement_entries.map((je) => (
                    <div key={je.id} className="rounded-lg border border-[#E5E5EA] overflow-hidden mb-2">
                      <div className="px-3 py-2 bg-[#F7F7F9] text-xs font-medium text-[#3C3C43]">
                        {je.number} · {je.settlement_number} ·{" "}
                        {je.side === "payer" ? "buku PT pembayar" : "buku PT penerima"}
                      </div>
                      <JournalTable lines={je.lines || []} />
                    </div>
                  ))}
                </Section>
              )}

              {/* Jurnal pembalik (bila dibatalkan) */}
              {j.reversals.length > 0 && (
                <Section icon={Undo2} title="Jurnal Pembalik (Transaksi Dibatalkan)"
                         testid="interco-detail-reversals">
                  {j.reversals.map((je) => (
                    <div key={je.id} className="rounded-lg border border-[#F7C3B4] overflow-hidden mb-2">
                      <div className="px-3 py-2 bg-[#FDEDE7] text-xs font-medium text-[#9B1C1C]">
                        {je.number} — {je.description}
                      </div>
                      <JournalTable lines={je.lines || []} />
                    </div>
                  ))}
                </Section>
              )}

              {/* FASE G-6b — Faktur pajak internal (keluaran penjual + masukan pembeli) */}
              {(j.tax_invoices_out.length > 0 || j.tax_invoices_in.length > 0) && (
                <Section icon={Receipt} title="Faktur Pajak Internal (Keluaran & Masukan)"
                         testid="interco-detail-tax-invoices">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {[["Keluaran \u00b7 buku penjual", j.tax_invoices_out],
                      ["Masukan \u00b7 buku pembeli", j.tax_invoices_in]].map(([label, list]) => (
                      <div key={label} className="rounded-lg border border-[#E5E5EA] overflow-hidden">
                        <div className="px-3 py-2 bg-[#F7F7F9] text-xs font-medium text-[#3C3C43]">
                          {label}
                        </div>
                        <div className="p-3 space-y-2">
                          {list.length === 0 && (
                            <span className="text-xs text-[#8E8E93]">Belum ada.</span>
                          )}
                          {list.map((f) => (
                            <div key={f.id} className="text-[13px]">
                              <div className="font-semibold text-[#1D1D1F]">{f.number}</div>
                              <div className="text-[#6E6E73]">
                                DPP {formatCurrency(f.dpp)} · PPN {formatCurrency(f.ppn_amount)} ·{" "}
                                {fmtDate(f.faktur_date)}
                              </div>
                              <div className="flex flex-wrap items-center gap-1 mt-0.5">
                                <span className="px-1.5 py-0.5 rounded text-[10px] bg-[#EAF2FF] text-[#0058CC]">
                                  {f.status}
                                </span>
                                {f.needs_replacement && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-[#FDEDE7] text-[#9B1C1C] font-semibold">
                                    PERLU PENGGANTI
                                  </span>
                                )}
                              </div>
                              {/* FASE P2 — cetak / e-sign / kirim faktur pajak INTERNAL */}
                              <div className="mt-1">
                                <DocumentActionsBar docType="tax_invoice" sourceId={f.id}
                                  entityId={f.entity_id} number={f.number}
                                  currentUser={currentUser} compact />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="mt-2 text-[11px] text-[#6E6E73]">
                    INV-IC-07: PPN keluaran penjual selalu sama besar dengan PPN masukan
                    pembeli. Angka faktur yang sudah terbit tidak diedit — kalau nilainya
                    berubah (mis. ada retur), yang dipakai adalah Faktur Pengganti.
                  </p>
                </Section>
              )}

              {/* FASE G-6b — Retur antar-PT + jurnalnya */}
              {j.returns.length > 0 && (
                <Section icon={Undo2} title={`Retur Antar-PT (${j.returns.length / 2 || j.returns.length})`}
                         testid="interco-detail-returns">
                  <div className="rounded-lg border border-[#E5E5EA] overflow-hidden mb-3">
                    <table className="w-full text-sm" data-testid="interco-detail-returns-table">
                      <thead className="bg-[#F7F7F9]">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium">Nomor</th>
                          <th className="text-left px-3 py-2 font-medium">Peran</th>
                          <th className="text-right px-3 py-2 font-medium">Nilai</th>
                          <th className="text-left px-3 py-2 font-medium">Status</th>
                          <th className="text-left px-3 py-2 font-medium">Alasan</th>
                          <th className="text-left px-3 py-2 font-medium">Dokumen</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#F2F2F5]">
                        {j.returns.map((r) => (
                          <tr key={r.id}>
                            <td className="px-3 py-2 font-medium">{r.number}</td>
                            <td className="px-3 py-2">
                              {r.role === "returner" ? "Mengembalikan" : "Menerima kembali"}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {formatCurrency(r.grand_total)}
                            </td>
                            <td className="px-3 py-2">
                              <span className={`inline-flex px-2 py-0.5 rounded text-xs ${
                                RETURN_STATUS_CLASS[r.status] || ""}`}>
                                {RETURN_STATUS_LABEL[r.status] || r.status}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-[#6E6E73]">{r.reason}</td>
                            {/* FASE P2 — cetak / e-sign Nota Retur (returner) atau Nota Kredit (receiver) antar-PT */}
                            <td className="px-3 py-2">
                              <DocumentActionsBar docType="interco_return" sourceId={r.id}
                                entityId={r.entity_id} number={r.number}
                                label={r.role === "returner" ? "Nota Retur Antar-PT" : "Nota Kredit Antar-PT"}
                                esignable currentUser={currentUser} compact />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {j.return_entries.map((je) => (
                    <div key={je.id} className="rounded-lg border border-[#E5E5EA] overflow-hidden mb-2">
                      <div className="px-3 py-2 bg-[#F7F7F9] text-xs font-medium text-[#3C3C43]">
                        {je.number} — {je.description}
                      </div>
                      <JournalTable lines={je.lines || []} />
                    </div>
                  ))}
                  <p className="text-[11px] text-[#6E6E73]">
                    INV-IC-08: retur menerbitkan jurnal berpasangan di dua buku, dan roll
                    yang kembali dinilai ulang ke harga perolehan ASLI penjual supaya GL
                    persediaan tetap sejalan dengan subledger.
                  </p>
                </Section>
              )}

              <Section icon={Clock} title="Timeline" testid="interco-detail-timeline-section">
                <Timeline doc={pair.seller} />
              </Section>

              {j.settlements.length > 0 && (
                <Section icon={Layers} title={`Settlement Terkait (${j.settlements.length})`}
                         testid="interco-detail-settlements-section">
                  <div className="rounded-lg border border-[#E5E5EA] overflow-hidden">
                    <table className="w-full text-sm" data-testid="interco-detail-settlements">
                      <thead className="bg-[#F7F7F9]">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium">Nomor</th>
                          <th className="text-left px-3 py-2 font-medium">Tanggal</th>
                          <th className="text-left px-3 py-2 font-medium">Metode</th>
                          <th className="text-right px-3 py-2 font-medium">Diterapkan (pair ini)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#F2F2F5]">
                        {j.settlements.map((s) => {
                          const applied = (s.applied || []).find((a) => a.pair_id === pair.pair_id);
                          return (
                            <tr key={s.id}>
                              <td className="px-3 py-2 font-medium">{s.number}</td>
                              <td className="px-3 py-2">{fmtDate(s.settle_date)}</td>
                              <td className="px-3 py-2">{s.method}</td>
                              <td className="px-3 py-2 text-right tabular-nums">
                                {formatCurrency(applied?.applied_amount || 0)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </Section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

