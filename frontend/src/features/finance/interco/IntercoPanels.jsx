/**
 * FASE G-6 / G-6b — Panel tabel layar **TRANSAKSI ANTAR ENTITAS**.
 *
 * Dipisah dari `IntercoView.jsx` supaya berkas layar tetap di bawah panduan panjang
 * (validate_compliance CHECK 1) dan tiap tabel bisa dibaca sendiri:
 *   * `TransactionsPanel` — daftar dokumen kembar + langkah berikutnya
 *   * `BalancesPanel`     — saldo pasangan PT + pengingat settlement (G-6b)
 *   * `SettlementsPanel`  — riwayat netting
 */
import {
  AlertTriangle, Bell, Eye, Receipt, Truck, Undo2,
} from "lucide-react";
import { KNSelect } from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";
import {
  STATUS_CLASS, STATUS_LABEL, STATUS_FILTERS, ROLE_FILTERS,
  fmtDate, nextStep, canCancel, canReturn, taxState,
} from "./intercoApi";

export function TransactionsPanel({
  rows, fStatus, fRole, setFStatus, setFRole, onAdvance, onView, onCancel,
  onTax, onReturn, canWrite,
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <KNSelect data-testid="interco-filter-status" value={fStatus} onChange={setFStatus}
                  options={STATUS_FILTERS} className="min-w-[190px]" placeholder="Status" />
        <KNSelect data-testid="interco-filter-role" value={fRole} onChange={setFRole}
                  options={ROLE_FILTERS} className="min-w-[190px]" placeholder="Peran" />
        <div className="ml-auto text-xs text-[#6E6E73]">{rows.length} transaksi</div>
      </div>

      <div className="rounded-xl border border-[#E5E5EA] bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="interco-transactions-table">
            <thead className="bg-[#F7F7F9] text-[#3C3C43]">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Nomor</th>
                <th className="text-left px-4 py-3 font-medium">Peran</th>
                <th className="text-left px-4 py-3 font-medium">Penjual → Pembeli</th>
                <th className="text-right px-4 py-3 font-medium">Nilai</th>
                <th className="text-left px-4 py-3 font-medium">Tanggal</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Barang Fisik</th>
                <th className="text-left px-4 py-3 font-medium">Pajak</th>
                <th className="text-right px-4 py-3 font-medium">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F2F2F5]">
              {rows.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-10 text-center text-[#8E8E93]">
                  Belum ada transaksi antar-PT.
                </td></tr>
              )}
              {rows.map((r) => {
                const step = nextStep(r, r.role);
                const tax = taxState(r);
                const returned = Number(r.returned_amount || 0) > 0;
                return (
                  <tr key={r.id} data-testid={`interco-row-${r.id}`} className="hover:bg-[#FAFAFB]">
                    <td className="px-4 py-3">
                      <div className="font-medium text-[#1D1D1F]">{r.number}</div>
                      <div className="text-xs text-[#8E8E93]">↔ {r.counterpart_number}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded text-xs ${
                        r.role === "seller" ? "bg-[#EDE7FB] text-[#6B219A]"
                                            : "bg-[#EAF2FF] text-[#0058CC]"}`}>
                        {r.role === "seller" ? "Penjual" : "Pembeli"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-[#1D1D1F]">{r.seller_entity_name}</div>
                      <div className="text-xs text-[#8E8E93]">→ {r.buyer_entity_name}</div>
                    </td>
                    <td className="px-4 py-3 text-right font-medium tabular-nums text-[#1D1D1F]">
                      {formatCurrency(r.grand_total)}
                      {r.tax_apply && (
                        <div className="text-xs text-[#8E8E93]">incl. PPN {r.tax_rate}%</div>
                      )}
                      {returned && (
                        <div className="text-xs text-[#B26A00]" data-testid={`interco-returned-${r.id}`}>
                          − retur {formatCurrency(r.returned_amount)}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-[#3C3C43]">{fmtDate(r.doc_date)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded text-xs ${STATUS_CLASS[r.status] || ""}`}>
                        {STATUS_LABEL[r.status] || r.status}
                      </span>
                    </td>
                    <td className="px-4 py-3" data-testid={`interco-physical-${r.id}`}>
                      {r.warehouse_transfer_code ? (
                        <div className="text-xs">
                          <div className="inline-flex items-center gap-1 text-[#3C3C43]">
                            <Truck size={12} /> {r.warehouse_transfer_code}
                          </div>
                          <div className={
                            r.warehouse_transfer_status === "completed" ? "text-[#1B7F4B]"
                              : r.warehouse_transfer_status === "cancelled" ? "text-[#8E8E93]"
                              : "text-[#B26A00]"}>
                            {r.warehouse_transfer_status === "completed" ? "sudah berpindah"
                              : r.warehouse_transfer_status === "cancelled" ? "tugas dibatalkan"
                              : "menunggu gudang"}
                          </div>
                        </div>
                      ) : (
                        <span className="text-xs text-[#C9C9CE]">belum dikirim</span>
                      )}
                    </td>
                    <td className="px-4 py-3" data-testid={`interco-tax-cell-${r.id}`}>
                      {!r.tax_apply ? (
                        <span className="text-xs text-[#C9C9CE]">tanpa PPN</span>
                      ) : tax.issued ? (
                        <div className="text-xs">
                          <div className="text-[#3C3C43]">{tax.number}</div>
                          {tax.needsReplacement ? (
                            <div className="inline-flex items-center gap-1 text-[#C0392B]">
                              <AlertTriangle size={11} /> perlu pengganti
                            </div>
                          ) : (
                            <div className="text-[#1B7F4B]">faktur pajak terbit</div>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-[#B26A00]">belum difakturkan pajak</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-1">
                        <button onClick={() => onView?.(r)} data-testid={`interco-view-${r.id}`}
                                title="Lihat detail dokumen kembar"
                                className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md text-[#3C3C43] hover:bg-[#F2F2F5]">
                          <Eye size={13} />
                        </button>
                        {canWrite && step && (
                          <button onClick={() => step.action && onAdvance(r, step.action)}
                                  disabled={!step.action || step.disabled}
                                  title={step.hint || step.label}
                                  data-testid={`interco-advance-${r.id}`}
                                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border transition ${
                                    step.disabled
                                      ? "border-[#E5E5EA] text-[#8E8E93] bg-[#FAFBFC] cursor-default"
                                      : "border-[#0058CC] text-[#0058CC] bg-white hover:bg-[#EAF2FF]"}`}>
                            {step.action === "warehouse-task" && <Truck size={12} />}
                            {step.label}
                          </button>
                        )}
                        {canWrite && tax.show && (
                          <button onClick={() => onTax?.(r)} data-testid={`interco-tax-${r.id}`}
                                  title="Faktur pajak internal (keluaran penjual + masukan pembeli)"
                                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border transition ${
                                    tax.needsReplacement
                                      ? "border-[#E53935] text-[#C0392B] bg-white hover:bg-[#FDEDE7]"
                                      : "border-[#E5E5EA] text-[#3C3C43] bg-white hover:bg-[#F2F2F5]"}`}>
                            <Receipt size={12} /> {tax.label}
                          </button>
                        )}
                        {canWrite && canReturn(r) && (
                          <button onClick={() => onReturn?.(r)} data-testid={`interco-return-${r.id}`}
                                  title="Retur antar-PT (barangnya sudah berpindah)"
                                  className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border border-[#E5E5EA] text-[#3C3C43] bg-white hover:bg-[#F2F2F5]">
                            <Undo2 size={12} /> Retur
                          </button>
                        )}
                        {canWrite && canCancel(r) && (
                          <button onClick={() => onCancel?.(r)} data-testid={`interco-cancel-${r.id}`}
                                  title="Batalkan transaksi (wajib alasan bila sudah dikonfirmasi)"
                                  className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md text-[#C0392B] hover:bg-[#FDEDE7]">
                            <Undo2 size={12} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function BalancesPanel({ accounts, onNetting, onRemind, canWrite }) {
  return (
    <div className="space-y-3">
      <div className="text-sm text-[#6E6E73]">
        Saldo per <b>arah dagang</b> — piutang di PT penjual, utang di PT pembeli.
        INV-IC-02: kedua sisi harus sama besar. Dua PT yang berdagang <b>dua arah</b>
        (mis. lewat Permintaan Internal) punya saldo <b>terpisah</b> untuk tiap arah,
        jadi utang satu arah tidak pernah terhapus oleh arah sebaliknya. <b>Umur</b>
        dihitung dari aktivitas nyata terakhir (dokumen &amp; settlement), bukan dari
        kapan barisnya terakhir dihitung ulang.
      </div>
      <div className="rounded-xl border border-[#E5E5EA] bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="interco-accounts-table">
            <thead className="bg-[#F7F7F9] text-[#3C3C43]">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Dari</th>
                <th className="text-left px-4 py-3 font-medium">Ke</th>
                <th className="text-left px-4 py-3 font-medium">Jenis</th>
                <th className="text-left px-4 py-3 font-medium">Dasar dagang</th>
                <th className="text-right px-4 py-3 font-medium">Bruto</th>
                <th className="text-right px-4 py-3 font-medium">Terlunasi</th>
                <th className="text-right px-4 py-3 font-medium">Diretur</th>
                <th className="text-right px-4 py-3 font-medium">Sisa</th>
                <th className="text-right px-4 py-3 font-medium">Umur</th>
                <th className="text-right px-4 py-3 font-medium">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F2F2F5]">
              {accounts.length === 0 && (
                <tr><td colSpan={10} className="px-4 py-10 text-center text-[#8E8E93]">
                  Belum ada saldo antar-PT.
                </td></tr>
              )}
              {accounts.map((a) => (
                <tr key={a.id} data-testid={`interco-acc-${a.id}`} className="hover:bg-[#FAFAFB]">
                  <td className="px-4 py-3 text-[#1D1D1F]">{a.from_entity_name}</td>
                  <td className="px-4 py-3 text-[#1D1D1F]">{a.to_entity_name}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs ${
                      a.role === "receivable" ? "bg-[#E6F7F1] text-[#0F6B52]"
                                             : "bg-[#FFF4E5] text-[#B26A00]"}`}>
                      {a.role === "receivable" ? "Piutang" : "Utang"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-[#6E6E73]"
                      data-testid={`interco-acc-dir-${a.id}`}>
                    {a.seller_entity_name
                      ? `${a.seller_entity_name} menjual ke ${a.buyer_entity_name}`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(a.gross_amount)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(a.settled_amount)}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-[#B26A00]">
                    {formatCurrency(a.returned_amount || 0)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium text-[#1D1D1F]">
                    {formatCurrency(a.outstanding)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {a.aging_days || 0} hari
                    {a.reminder_active && (
                      <div className="inline-flex items-center gap-1 text-xs text-[#B26A00] ml-1"
                           title={`melewati batas ${a.reminder_limit_days || 30} hari`}>
                        <AlertTriangle size={11} /> menganggur
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      {canWrite && a.role === "payable" && a.outstanding > 0 && (
                        <>
                          <button onClick={() => onRemind?.(a)}
                                  data-testid={`interco-remind-${a.id}`}
                                  title="Kirim pengingat ke Keuangan (mengingatkan, bukan memaksa)"
                                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-[#E5E5EA] text-[#3C3C43] bg-white hover:bg-[#F2F2F5]">
                            <Bell size={12} /> Ingatkan
                          </button>
                          <button onClick={() => onNetting?.(a)}
                                  data-testid={`interco-settle-${a.id}`}
                                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-[#0058CC] text-[#0058CC] bg-white hover:bg-[#EAF2FF] transition">
                            Buat Settlement
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function SettlementsPanel({ rows }) {
  return (
    <div className="rounded-xl border border-[#E5E5EA] bg-white overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="interco-settlements-table">
          <thead className="bg-[#F7F7F9] text-[#3C3C43]">
            <tr>
              <th className="text-left px-4 py-3 font-medium">Nomor</th>
              <th className="text-left px-4 py-3 font-medium">Pembayar</th>
              <th className="text-left px-4 py-3 font-medium">Penerima</th>
              <th className="text-left px-4 py-3 font-medium">Metode</th>
              <th className="text-right px-4 py-3 font-medium">Nilai</th>
              <th className="text-left px-4 py-3 font-medium">Tanggal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#F2F2F5]">
            {rows.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-[#8E8E93]">
                Belum ada settlement.
              </td></tr>
            )}
            {rows.map((s) => (
              <tr key={s.id} data-testid={`interco-set-${s.id}`} className="hover:bg-[#FAFAFB]">
                <td className="px-4 py-3 font-medium text-[#1D1D1F]">{s.number}</td>
                <td className="px-4 py-3">{s.payer_entity_name}</td>
                <td className="px-4 py-3">{s.payee_entity_name}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex px-2 py-0.5 rounded text-xs bg-[#F2F2F5] text-[#3C3C43]">
                    {s.method}
                  </span>
                </td>
                <td className="px-4 py-3 text-right font-medium tabular-nums">
                  {formatCurrency(s.total_applied)}
                </td>
                <td className="px-4 py-3 text-[#3C3C43]">{fmtDate(s.settle_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
