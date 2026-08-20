/**
 * FASE G-7 — bagian-bagian panel detail kontrabon (dipisah agar tiap berkas tetap
 * ramping): total, daftar faktur + selisih 3-way, potongan, keputusan, pembayaran,
 * penerimaan barang terkait, dan jejak waktu.
 */
import { Scissors, Trash2, Scale, Banknote, History, PackageCheck, AlertTriangle } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import { EVENT_LABEL, EXCEPTION_TYPE_LABEL, fmtDate, fmtDateTime } from "./contraBonApi";

export function TotalsGrid({ totals }) {
  const t = totals || {};
  // Kartu di panel detail lebih sempit daripada kartu KPI layar induk, jadi angkanya
  // memakai ukuran kompak sendiri (bukan `.stat-value` 19px) supaya nominal besar
  // seperti "Rp 17.662.320" tidak terpotong di tengah — sempat terlihat terpotong.
  const cell = "rounded-md border border-[#EFF0F2] bg-white px-2 py-1.5";
  const lbl = "text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]";
  const val = "mt-0.5 text-[13px] font-bold tabular-nums leading-tight break-words";
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5"
      data-testid="cb-detail-totals">
      <div className={cell}>
        <p className={lbl}>Nilai faktur</p>
        <p className={`${val} text-[#1C1C1E]`} data-testid="cb-total-bills">
          {formatCurrency(t.bills_total)}
        </p>
      </div>
      <div className={cell}>
        <p className={lbl}>Potongan</p>
        <p className={`${val} text-[#B26A00]`} data-testid="cb-total-deductions">
          {formatCurrency(t.deductions_total)}
        </p>
      </div>
      <div className={cell}>
        <p className={lbl}>Nilai bersih</p>
        <p className={`${val} text-[#0058CC]`} data-testid="cb-total-net">
          {formatCurrency(t.net_payable)}
        </p>
      </div>
      <div className={cell}>
        <p className={lbl}>Sudah dibayar</p>
        <p className={`${val} text-[#1B7F4B]`} data-testid="cb-total-paid">
          {formatCurrency(t.paid_total)}
        </p>
      </div>
      <div className={cell}>
        <p className={lbl}>Sisa</p>
        <p className={`${val} ${Number(t.outstanding) > 0 ? "text-[#C0392B]" : "text-[#1B7F4B]"}`}
          data-testid="cb-total-outstanding">
          {formatCurrency(t.outstanding)}
        </p>
      </div>
    </div>
  );
}

export function BillsSection({ cb, canDecide, onDecide }) {
  const decided = new Set((cb.decisions || []).map((d) => d.exception_key));
  return (
    <div data-testid="cb-detail-bills">
      <p className="mb-1 text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
        Faktur yang ditukar ({(cb.bills || []).length})
      </p>
      <div className="overflow-hidden rounded-lg border border-[#EFF0F2]">
        <table className="w-full text-[11.5px]">
          <thead className="bg-[#FAFBFC]">
            <tr className="text-left text-[9.5px] uppercase tracking-wide text-[#8E8E93]">
              <th className="px-2 py-1.5">Tagihan</th>
              <th className="px-2 py-1.5">PO</th>
              <th className="px-2 py-1.5">Jatuh tempo</th>
              <th className="px-2 py-1.5 text-right">Ditarik</th>
              <th className="px-2 py-1.5">3-way match</th>
            </tr>
          </thead>
          <tbody>
            {(cb.bills || []).map((b) => {
              const exc = (b.match || {}).exceptions || [];
              return (
                <tr key={b.bill_id} className="border-t border-[#F2F2F5] align-top"
                  data-testid={`cb-bill-${b.bill_id}`}>
                  <td className="px-2 py-1.5">
                    <p className="font-bold text-[#0058CC]">{b.bill_number}</p>
                    <p className="text-[9.5px] text-[#8E8E93]">
                      faktur supplier {b.supplier_invoice_no || "—"}
                    </p>
                    {Number(b.claim_deduction_info) > 0 && (
                      <p className="text-[9.5px] text-[#B26A00]">
                        potongan makloon {formatCurrency(b.claim_deduction_info)} sudah menempel
                      </p>
                    )}
                  </td>
                  <td className="px-2 py-1.5">{b.po_number || "—"}</td>
                  <td className="px-2 py-1.5">{fmtDate(b.due_date)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    <p className="font-semibold">{formatCurrency(b.applied_amount)}</p>
                    <p className="text-[9.5px] text-[#8E8E93]">
                      dari {formatCurrency(b.grand_total)}
                    </p>
                  </td>
                  <td className="px-2 py-1.5">
                    {exc.length === 0
                      ? (
                        <span className="rounded bg-[#E8F6EE] px-1.5 py-0.5 text-[9.5px] font-bold text-[#1B7F4B]">
                          cocok
                        </span>
                      )
                      : (
                        <div className="space-y-1">
                          {exc.map((e) => (
                            <div key={e.key}
                              className={`rounded border px-1.5 py-1 ${decided.has(e.key)
                                ? "border-[#D8E6D9] bg-[#F4FAF5]" : "border-[#FFE0B2] bg-[#FFFBF3]"}`}
                              data-testid={`cb-exception-${e.key}`}>
                              <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8C4A00]">
                                {EXCEPTION_TYPE_LABEL[e.type] || "Selisih"}
                              </p>
                              <p className="text-[10.5px] text-[#1C1C1E]">{e.detail}</p>
                              {decided.has(e.key)
                                ? (
                                  <p className="text-[9.5px] font-semibold text-[#1B7F4B]">
                                    sudah diputus
                                  </p>
                                )
                                : canDecide && (
                                  <button className="link-button" onClick={() => onDecide(e)}
                                    data-testid={`cb-decide-${e.key}`}>
                                    <Scale size={10} /> Putuskan selisih
                                  </button>
                                )}
                            </div>
                          ))}
                        </div>
                      )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function DeductionsSection({ cb, canEdit, onAdd, onRemove, busy }) {
  const rows = cb.deductions || [];
  return (
    <div data-testid="cb-detail-deductions">
      <div className="mb-1 flex items-center justify-between">
        <p className="text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
          Potongan ({rows.length})
        </p>
        {canEdit && (
          <button className="link-button" data-testid="cb-add-deduction" onClick={onAdd}>
            <Scissors size={11} /> Tambah potongan
          </button>
        )}
      </div>
      {rows.length === 0
        ? (
          <p className="rounded-md border border-dashed border-[#E5E5EA] px-2 py-2 text-[11px] text-[#8E8E93]"
            data-testid="cb-deductions-empty">
            Belum ada potongan. Retur beli, uang muka, denda supplier, dan selisih 3-way bisa
            dipotong di sini — semuanya menunjuk dokumen nyata.
          </p>
        )
        : (
          <div className="space-y-1">
            {rows.map((d) => (
              <div key={d.id} data-testid={`cb-deduction-${d.id}`}
                className="flex items-start justify-between gap-2 rounded-md border border-[#EFF0F2] bg-white px-2 py-1.5">
                <div className="min-w-0">
                  <p className="text-[11.5px] font-semibold text-[#1C1C1E]">
                    {d.label} · {formatCurrency(d.amount)}
                  </p>
                  <p className="text-[9.5px] text-[#8E8E93]">
                    {d.ref_number ? `${d.ref_number} · ` : ""}
                    {d.posts_gl ? "berjurnal saat dibayar" : "tanpa jurnal baru (sudah ada di sumber)"}
                    {d.applied_at ? " · sudah diterapkan" : ""}
                  </p>
                  {d.note && <p className="text-[9.5px] text-[#6B6B73]">{d.note}</p>}
                </div>
                {canEdit && !d.applied_at && (
                  <button className="link-button" style={{ color: "#B4231F" }}
                    data-testid={`cb-remove-deduction-${d.id}`}
                    disabled={busy === `ded-${d.id}`} onClick={() => onRemove(d.id)}>
                    <Trash2 size={11} /> Hapus
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
    </div>
  );
}

export function DecisionsSection({ cb }) {
  const rows = cb.decisions || [];
  if (!rows.length) return null;
  return (
    <div data-testid="cb-detail-decisions">
      <p className="mb-1 text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
        Keputusan selisih ({rows.length})
      </p>
      <div className="space-y-1">
        {rows.map((d, i) => (
          <div key={`${d.exception_key}-${i}`}
            className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-2 py-1.5"
            data-testid={`cb-decision-row-${d.exception_key}`}>
            <p className="text-[11px] font-semibold text-[#1C1C1E]">
              {d.action === "accept" ? "Selisih diterima"
                : d.action === "deduct" ? "Selisih dipotong" : "Disengketakan"}
              {" · "}{formatCurrency(d.amount)}
            </p>
            <p className="text-[9.5px] text-[#8E8E93]">
              {d.reason_label || d.reason_code} · {d.by} · {fmtDateTime(d.at)}
            </p>
            {d.exception_detail && (
              <p className="text-[9.5px] text-[#6B6B73]">{d.exception_detail}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function PaymentsSection({ cb }) {
  const rows = cb.payments || [];
  const sch = cb.schedule || {};
  return (
    <div data-testid="cb-detail-payments">
      <p className="mb-1 text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
        Pembayaran ({rows.length})
      </p>
      {sch.planned_payment_date && (
        <p className="mb-1 rounded-md bg-[#F2F7FF] px-2 py-1.5 text-[11px] text-[#1C1C1E]"
          data-testid="cb-detail-schedule">
          Dijadwalkan {fmtDate(sch.planned_payment_date)} · {sch.method || "transfer"}
          {sch.notes ? ` · ${sch.notes}` : ""}
        </p>
      )}
      {rows.length === 0
        ? (
          <p className="rounded-md border border-dashed border-[#E5E5EA] px-2 py-2 text-[11px] text-[#8E8E93]">
            Belum ada pembayaran. Satu kontrabon dibayar SEKALI untuk seluruh fakturnya.
          </p>
        )
        : (
          <div className="space-y-1">
            {rows.map((p) => (
              <div key={p.id} data-testid={`cb-payment-${p.id}`}
                className="rounded-md border border-[#EFF0F2] bg-white px-2 py-1.5">
                <p className="flex items-center gap-1 text-[11.5px] font-semibold text-[#1C1C1E]">
                  <Banknote size={11} className="text-[#1B7F4B]" />
                  {formatCurrency(p.amount)} · {p.method}
                </p>
                <p className="text-[9.5px] text-[#8E8E93]">
                  kas {p.cash_txn_number || "—"} · {fmtDateTime(p.paid_at)} · oleh {p.paid_by}
                  {p.bank_line_id ? " · dari mutasi bank" : ""}
                </p>
                {(p.allocations || []).length > 0 && (
                  <p className="text-[9.5px] text-[#6B6B73]">
                    melunasi {(p.allocations || []).map((a) => `${a.bill_number} `
                      + `${formatCurrency(a.amount)}`).join(" · ")}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
    </div>
  );
}

export function ReceiptSection({ receipt, loading }) {
  const rows = receipt?.goods_receipts || [];
  return (
    <div data-testid="cb-detail-grn">
      <p className="mb-1 text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
        Penerimaan barang terkait ({rows.length})
      </p>
      {loading && <p className="text-[11px] text-[#8E8E93]">Memuat penerimaan barang…</p>}
      {!loading && rows.length === 0 && (
        <p className="rounded-md border border-dashed border-[#E5E5EA] px-2 py-2 text-[11px] text-[#8E8E93]">
          Tidak ada tugas penerimaan gudang yang tercatat untuk PO di kontrabon ini.
        </p>
      )}
      {!loading && rows.length > 0 && (
        <div className="space-y-1">
          {rows.map((g) => (
            <p key={`${g.grn_task_id}-${g.bill_number}`}
              className="flex items-center gap-1 rounded-md border border-[#EFF0F2] bg-white px-2 py-1 text-[11px]">
              <PackageCheck size={11} className="text-[#0058CC]" />
              {g.po_number} · tugas {String(g.grn_task_id).slice(-6)} · {g.status}
              <span className="text-[#8E8E93]">
                {g.completed_at ? ` · ${fmtDate(g.completed_at)}` : ""}
              </span>
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export function TimelineSection({ cb }) {
  const rows = [...(cb.timeline || [])].reverse();
  return (
    <div data-testid="cb-detail-timeline">
      <p className="mb-1 flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
        <History size={11} /> Jejak waktu ({rows.length})
      </p>
      {rows.length === 0
        ? <p className="text-[11px] text-[#8E8E93]">Belum ada jejak.</p>
        : (
          <div className="space-y-1">
            {rows.map((e, i) => (
              <div key={`${e.at}-${i}`} className="flex gap-2">
                <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-[#0058CC]" />
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold text-[#1C1C1E]">
                    {e.label || EVENT_LABEL[e.event] || e.event}
                  </p>
                  <p className="text-[9.5px] text-[#8E8E93]">
                    {fmtDateTime(e.at)}{e.actor ? ` · ${e.actor}` : ""}
                  </p>
                  {e.note && <p className="text-[9.5px] text-[#6B6B73]">{e.note}</p>}
                </div>
              </div>
            ))}
          </div>
        )}
    </div>
  );
}

export function DisputeBanner({ cb }) {
  if (cb.status !== "disputed") return null;
  return (
    <div className="flex items-start gap-1.5 rounded-md border border-[#F5C2C7] bg-[#FDE2E2] px-2 py-1.5"
      data-testid="cb-dispute-banner">
      <AlertTriangle size={12} className="mt-[2px] shrink-0 text-[#9B1C1C]" />
      <p className="text-[11px] text-[#9B1C1C]">
        Kontrabon disengketakan{cb.dispute_note ? ` — ${cb.dispute_note}` : ""}. Setelah supplier
        mengoreksi fakturnya, ajukan ulang dari tombol di atas.
      </p>
    </div>
  );
}
