/**
 * FASE G-6 / G-6b — Bagian presentasi **DETAIL PANEL** transaksi antar-PT.
 *
 * Dipisah dari `IntercoDetailPanel.jsx` (pola `ContraBonParts` di G-7) supaya
 * berkas layar tetap di bawah panduan panjang dan tiap blok bukti bisa dibaca
 * sendiri: kartu per PT, blok jurnal, tabel jurnal, dan timeline.
 */
import { FileText, BookOpen, Scissors, ShieldCheck } from "lucide-react";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import { STATUS_CLASS, STATUS_LABEL, ACC_LABEL, fmtDate } from "./intercoApi";
import QtyDual from "../../../components/QtyDual";      // FASE U — dua satuan

export function Section({ icon: Icon, title, testid, children }) {
  return (
    <div className="border-t border-[#E5E5EA] px-6 py-4" data-testid={testid}>
      <h3 className="text-sm font-semibold text-[#1D1D1F] flex items-center gap-2 mb-3">
        <Icon size={15} /> {title}
      </h3>
      {children}
    </div>
  );
}

export function SidePanel({ role, doc, journal, extraJournal, extraLabel }) {
  if (!doc) return <div className="p-6 text-[#8E8E93]">-</div>;
  const isSeller = role === "seller";
  return (
    <div className="p-6" data-testid={`interco-detail-${role}`}>
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wider text-[#6E6E73]">
            {isSeller ? "PT Penjual" : "PT Pembeli"}
          </div>
          <div className="text-base font-semibold text-[#1D1D1F] mt-0.5">
            {isSeller ? doc.seller_entity_name : doc.buyer_entity_name}
          </div>
        </div>
        <span className={`inline-flex px-2 py-0.5 rounded text-xs ${STATUS_CLASS[doc.status] || ""}`}>
          {STATUS_LABEL[doc.status] || doc.status}
        </span>
      </div>
      <div className="text-xs text-[#8E8E93] mb-3">
        Dokumen: <span className="font-medium text-[#3C3C43]">{doc.number}</span>
        {" · "}
        <span>lawan: {doc.counterpart_number}</span>
        {doc.warehouse_transfer_code && (
          <> {" · "}<span>tugas gudang: {doc.warehouse_transfer_code}</span></>
        )}
      </div>

      <div className="rounded-lg border border-[#E5E5EA] overflow-hidden mb-4">
        <div className="px-3 py-2 bg-[#F7F7F9] text-xs font-medium text-[#3C3C43] flex items-center gap-2">
          <FileText size={13} /> {isSeller ? "SO / Surat Jalan / Invoice Internal" : "PO Internal / Vendor Bill"}
        </div>
        <table className="w-full text-sm">
          <thead className="bg-white text-[#6E6E73]">
            <tr className="text-xs">
              <th className="text-left px-3 py-1.5 font-normal">Barang</th>
              <th className="text-right px-3 py-1.5 font-normal">Qty</th>
              <th className="text-right px-3 py-1.5 font-normal">Harga</th>
              <th className="text-right px-3 py-1.5 font-normal">Jumlah</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#F2F2F5]">
            {(doc.items || []).map((it, i) => (
              <tr key={i}>
                <td className="px-3 py-1.5">
                  <div className="font-medium text-[#1D1D1F]">{it.product_name || it.sku}</div>
                  <div className="text-xs text-[#8E8E93]">
                    {it.sku}
                    {it.price_source === "fixed_price" && " · harga kontrak internal"}
                    {it.price_source === "at_cost" && " · sesuai HPP penjual"}
                    {it.price_source === "override" && " · harga manual"}
                  </div>
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums"><QtyDual rolls={it.qty_rolls} measure={it.quantity} unit={it.unit} /></td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatCurrency(it.unit_price)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatCurrency(it.line_subtotal)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-[#FAFAFB] text-[#3C3C43]">
            <tr className="text-xs">
              <td colSpan={3} className="px-3 py-1.5 text-right">Subtotal</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{formatCurrency(doc.subtotal)}</td>
            </tr>
            {doc.tax_apply && (
              <tr className="text-xs">
                <td colSpan={3} className="px-3 py-1.5 text-right">PPN {doc.tax_rate}%</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatCurrency(doc.tax_amount)}</td>
              </tr>
            )}
            <tr className="text-sm font-medium">
              <td colSpan={3} className="px-3 py-2 text-right">Total</td>
              <td className="px-3 py-2 text-right tabular-nums text-[#1D1D1F]">{formatCurrency(doc.grand_total)}</td>
            </tr>
            {doc.settled_amount > 0 && (
              <tr className="text-xs">
                <td colSpan={3} className="px-3 py-1.5 text-right text-[#1B7F4B]">Terlunasi</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-[#1B7F4B]">−{formatCurrency(doc.settled_amount)}</td>
              </tr>
            )}
          </tfoot>
        </table>
      </div>

      {journal ? (
        <JournalBlock
          title={isSeller ? "Jurnal Buku Penjual" : "Jurnal Buku Pembeli"}
          je={journal}
          testid={`interco-detail-journal-${role}`}
        />
      ) : (
        <div className="rounded-lg border border-dashed border-[#E5E5EA] px-3 py-3 text-xs text-[#8E8E93]"
             data-testid={`interco-detail-journal-${role}-empty`}>
          Belum ada jurnal — dokumen masih draf (jurnal terbit saat dikonfirmasi).
        </div>
      )}
      {extraJournal && (
        <div className="mt-2">
          <JournalBlock title={extraLabel} je={extraJournal}
                        testid={`interco-detail-journal-${role}-extra`} />
        </div>
      )}
    </div>
  );
}

export function JournalBlock({ title, je, testid }) {
  const balanced = Math.abs((je.total_debit || 0) - (je.total_credit || 0)) < 0.01;
  return (
    <div className="rounded-lg border border-[#E5E5EA] overflow-hidden" data-testid={testid}>
      <div className="px-3 py-2 bg-[#F7F7F9] text-xs font-medium text-[#3C3C43] flex items-center gap-2">
        <BookOpen size={13} /> {title}
        <span className="text-[#8E8E93] font-normal">{je.number}</span>
        <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded font-semibold ${
          balanced ? "bg-[#E8F6EE] text-[#1B7F4B]" : "bg-[#FDEDE7] text-[#C0392B]"}`}>
          {balanced ? "SEIMBANG" : "TIDAK SEIMBANG"}
        </span>
      </div>
      <JournalTable lines={je.lines || []} />
    </div>
  );
}

export function JournalTable({ lines }) {
  const td = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  const tc = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
  return (
    <table className="w-full text-xs">
      <thead className="text-[#6E6E73]">
        <tr>
          <th className="text-left px-3 py-1 font-normal">Akun</th>
          <th className="text-right px-3 py-1 font-normal">Debit</th>
          <th className="text-right px-3 py-1 font-normal">Kredit</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-[#F2F2F5]">
        {lines.map((l, i) => (
          <tr key={i}>
            <td className="px-3 py-1 text-[#3C3C43]">
              <span className="font-mono text-[11px] text-[#6E6E73]">{l.account_code}</span>{" "}
              <span className="text-[#1D1D1F]">
                {l.account_name || ACC_LABEL[l.account_code] || ""}
              </span>
              {l.description && (
                <div className="text-[10px] text-[#8E8E93]">{l.description}</div>
              )}
            </td>
            <td className="px-3 py-1 text-right tabular-nums">
              {Number(l.debit) > 0 ? formatCurrency(l.debit) : "—"}
            </td>
            <td className="px-3 py-1 text-right tabular-nums">
              {Number(l.credit) > 0 ? formatCurrency(l.credit) : "—"}
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot className="bg-[#FAFAFB] font-medium text-[#3C3C43]">
        <tr>
          <td className="px-3 py-1.5 text-right">Total</td>
          <td className="px-3 py-1.5 text-right tabular-nums">{formatCurrency(td)}</td>
          <td className="px-3 py-1.5 text-right tabular-nums">{formatCurrency(tc)}</td>
        </tr>
      </tfoot>
    </table>
  );
}

export function Timeline({ doc }) {
  const steps = [
    { key: "created_at",   label: "Dibuat" },
    { key: "confirmed_at", label: "Dikonfirmasi" },
    { key: "shipped_at",   label: "Dikirim" },
    { key: "received_at",  label: "Diterima (barang berpindah di gudang)" },
    { key: "invoiced_at",  label: "Difakturkan" },
    { key: "settled_at",   label: "Lunas" },
    { key: "cancelled_at", label: "Dibatalkan" },
  ].filter((s) => doc?.[s.key]);
  if (steps.length === 0) return <div className="text-xs text-[#8E8E93]">Belum ada jejak waktu.</div>;
  return (
    <ol className="relative border-l border-[#E5E5EA] ml-2 space-y-3" data-testid="interco-detail-timeline">
      {steps.map((s) => (
        <li key={s.key} className="ml-4">
          <div className="absolute -left-1.5 w-3 h-3 rounded-full bg-[#0058CC] border border-white" />
          <div className="text-sm font-medium text-[#1D1D1F]">{s.label}</div>
          <div className="text-xs text-[#6E6E73]">
            {fmtDate(doc[s.key])} · {doc[`${s.key.replace("_at", "")}_by`] || doc.created_by || "—"}
          </div>
          {s.key === "cancelled_at" && doc.cancel_reason && (
            <div className="text-xs text-[#9B1C1C] mt-0.5">Alasan: {doc.cancel_reason}</div>
          )}
        </li>
      ))}
    </ol>
  );
}
