/**
 * FASE G-7 · US1 — **JADWAL TUKAR FAKTUR** per supplier.
 *
 * Supplier tekstil datang pada hari tetap (mis. "setiap Selasa"). Kalau harinya
 * terlewat, fakturnya menumpuk satu siklus penuh dan pembayaran ikut tertunda.
 * Layar ini menyimpan jadwalnya, menghitung siklus berikutnya, dan menunjukkan
 * ANGKA yang bisa ditindak (siap dikontrabon · belum ditagih) supaya pengingat
 * H-n bukan basa-basi.
 */
import { CalendarClock, BellRing, Plus, Pencil, AlertTriangle } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import { fmtDate, humanDays } from "./contraBonApi";

export default function ExchangeSchedulesTab({ data, loading, onEdit, onCreateFor, onRunReminder,
  busy, canWrite = true }) {
  const rows = data?.rows || [];
  const dueSoon = data?.due_soon || [];

  return (
    <div data-testid="cb-schedules-tab">
      <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="stat-card">
          <p className="stat-label">Supplier terjadwal</p>
          <p className="stat-value text-[#0058CC]" data-testid="cb-sched-count">
            {data?.scheduled_count || 0}
          </p>
          <p className="text-[10px] text-[#8E8E93]">
            {data?.unscheduled_count || 0} supplier belum punya jadwal
          </p>
        </div>
        <div className={`stat-card ${dueSoon.length ? "ring-1 ring-[#FFE0B2]" : ""}`}>
          <p className="stat-label">Perlu diingatkan</p>
          <p className={`stat-value ${dueSoon.length ? "text-[#B26A00]" : "text-[#1B7F4B]"}`}
            data-testid="cb-sched-duesoon">{dueSoon.length}</p>
          <p className="text-[10px] text-[#8E8E93]">
            H-{data?.reminder_days_before ?? 1} dari Pusat Pengaturan
          </p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Siap dikontrabon</p>
          <p className="stat-value" data-testid="cb-sched-billable">
            {formatCurrency(rows.reduce((a, r) => a + Number(r.billable_value || 0), 0))}
          </p>
          <p className="text-[10px] text-[#8E8E93]">tagihan supplier yang masih menggantung</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Belum ditagih supplier</p>
          <p className="stat-value" data-testid="cb-sched-unbilled">
            {formatCurrency(rows.reduce((a, r) => a + Number(r.unbilled_gr_value || 0), 0))}
          </p>
          <p className="text-[10px] text-[#8E8E93]">barang sudah diterima, faktur belum datang</p>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#CBDCF7] bg-[#F2F7FF] px-3 py-2">
        <p className="text-[11.5px] text-[#1C1C1E]">
          Pengingat otomatis berjalan harian 07:30 WIB. Isinya menyebut jumlah tagihan siap
          dikontrabon dan nilai penerimaan yang belum ditagih — bukan sekadar “jangan lupa”.
        </p>
        <button className="secondary-button" data-testid="cb-run-reminder"
          disabled={busy === "reminder" || !canWrite} onClick={onRunReminder}>
          <BellRing size={14} className={busy === "reminder" ? "spin" : ""} />
          Jalankan pengingat sekarang
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-[#E5E5EA] bg-white">
        <div className="max-h-[520px] overflow-auto">
          <table className="data-table w-full text-[12px]">
            <thead className="sticky top-0 z-10 bg-[#FAFBFC]">
              <tr className="text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93]">
                <th className="px-3 py-2">Supplier</th>
                <th className="px-3 py-2">Jadwal tukar faktur</th>
                <th className="px-3 py-2">Siklus berikutnya</th>
                <th className="px-3 py-2 text-right">Siap dikontrabon</th>
                <th className="px-3 py-2 text-right">Belum ditagih</th>
                <th className="px-3 py-2 text-right">Tindakan</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-[#8E8E93]">
                  Memuat jadwal tukar faktur…
                </td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-[#6B6B73]"
                  data-testid="cb-sched-empty">
                  Belum ada supplier pada PT ini.
                </td></tr>
              )}
              {!loading && rows.map((r) => {
                const scheduled = (r.invoice_exchange || {}).mode !== "none";
                return (
                  <tr key={r.supplier_id} data-testid={`cb-sched-row-${r.supplier_id}`}
                    className={`border-t border-[#F2F2F5] hover:bg-[#F7F9FC] ${
                      r.due_reminder ? "bg-[#FFFBF3]" : ""}`}>
                    <td className="px-3 py-2">
                      <p className="font-semibold text-[#1C1C1E]">{r.supplier_name}</p>
                      <p className="text-[10px] text-[#8E8E93]">
                        {r.supplier_code}{r.payment_term_code ? ` · termin ${r.payment_term_code}` : ""}
                      </p>
                    </td>
                    <td className="px-3 py-2">
                      {scheduled
                        ? (
                          <>
                            <p className="font-semibold">{r.schedule_label}</p>
                            <p className="text-[10px] text-[#8E8E93]">
                              {(r.invoice_exchange || {}).pic_name
                                ? `PIC ${(r.invoice_exchange || {}).pic_name}`
                                : "tanpa PIC supplier"}
                            </p>
                          </>
                        )
                        : <span className="text-[#C7C7CC]">belum dijadwalkan</span>}
                    </td>
                    <td className="px-3 py-2">
                      {r.next_exchange_date
                        ? (
                          <>
                            <p className="font-semibold">{fmtDate(r.next_exchange_date)}</p>
                            <p className={`flex items-center gap-1 text-[10px] ${
                              r.due_reminder ? "font-bold text-[#B26A00]" : "text-[#8E8E93]"}`}>
                              {r.due_reminder && <AlertTriangle size={9} />}
                              {humanDays(r.days_left)} lagi
                            </p>
                          </>
                        )
                        : <span className="text-[#C7C7CC]">—</span>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {formatCurrency(r.billable_value)}
                      <p className="text-[10px] text-[#8E8E93]">{r.billable_count} faktur</p>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {formatCurrency(r.unbilled_gr_value)}
                      <p className="text-[10px] text-[#8E8E93]">{r.unbilled_gr_po_count} PO</p>
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {canWrite ? (
                        <>
                          <button className="link-button"
                            data-testid={`cb-sched-edit-${r.supplier_id}`}
                            onClick={() => onEdit(r)}>
                            <Pencil size={11} /> {scheduled ? "Ubah jadwal" : "Atur jadwal"}
                          </button>
                          {r.billable_count > 0 && (
                            <button className="link-button"
                              data-testid={`cb-sched-make-${r.supplier_id}`}
                              onClick={() => onCreateFor(r.supplier_id)}>
                              <Plus size={11} /> Kontrabon
                            </button>
                          )}
                        </>
                      ) : (
                        <span className="text-[10px] text-[#C7C7CC]">diatur Keuangan</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <p className="mt-2 flex items-start gap-1 text-[11px] text-[#9A9BA3]">
        <CalendarClock size={11} className="mt-[2px] shrink-0" />
        Jadwal tersimpan sebagai atribut supplier, bukan tabel terpisah — satu supplier
        satu ritme, dan pengingatnya memakai jadwal yang sama dengan yang Anda lihat di sini.
      </p>
    </div>
  );
}
