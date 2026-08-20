/**
 * Bagian-bagian layar Daftar Harga per Pelanggan (F1b) — dipisah dari view utama
 * agar tiap berkas tetap di bawah batas panjang guardrail.
 *
 * Berisi: kartu KPI, pita kebijakan penjagaan harga, lencana sumber harga,
 * dan baris tabel harga per produk.
 */
import { AlertTriangle, Clock3, History, Plus, ShieldCheck, ShieldOff } from "lucide-react";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import { sourceMeta } from "../../../hooks/useEffectivePrices";

export function Kpi({ label, value, icon: Icon, tone = "", testId, hint = "" }) {
  return (
    <div className="section-card" data-testid={testId}>
      <div className="section-body flex items-center gap-3 py-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#E7F0FF]">
          <Icon size={17} className="text-[#0058CC]" />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`truncate text-[17px] font-bold tabular-nums ${tone || "text-[#1C1C1E]"}`}
            data-testid={`${testId}-value`}>{value}</p>
          {hint && <p className="truncate text-[10px] text-[#9A9BA3]">{hint}</p>}
        </div>
      </div>
    </div>
  );
}

/** Pita jujur: apakah penjagaan harga menyala, dan dasar batasnya apa. */
export function GuardBanner({ guard }) {
  if (!guard) return null;
  const on = !!guard.guard_on;
  const Icon = on ? ShieldCheck : ShieldOff;
  return (
    <div data-testid="cpl-guard-banner"
      className={`mb-3 flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-[11.5px] ${
        on ? "border-[#BDE5CC] bg-[#E6F6EC] text-[#1B6E3C]"
           : "border-[#F3D7A0] bg-[#FFF6E5] text-[#8C4A00]"}`}>
      <Icon size={14} className="shrink-0" />
      {on ? (
        <span>
          <b>Penjagaan harga aktif.</b> Harga pelanggan di bawah batas bawah
          {" "}({guard.basis_label}) tidak langsung berlaku — masuk antrean
          {" "}<b>Persetujuan Harga</b> lebih dulu.
          {Number(guard.tolerance_pct) > 0 && (
            <> Toleransi {formatQty(guard.tolerance_pct)}% masih dimaafkan.</>
          )}
        </span>
      ) : (
        <span>
          <b>Penjagaan harga DIMATIKAN</b> di Pusat Pengaturan — harga di bawah
          {" "}{guard.basis_label} akan langsung berlaku tanpa persetujuan.
        </span>
      )}
    </div>
  );
}

export function SourcePill({ source, testId }) {
  const meta = sourceMeta(source);
  return (
    <span data-testid={testId}
      className="inline-block rounded px-1.5 py-0.5 text-[9px] font-bold"
      style={{ background: meta.bg, color: meta.fg }}>{meta.short}</span>
  );
}

export function PriceRow({ row, canManage, onSetPrice, onHistory, onOpenApprovals }) {
  const pid = row.product_id;
  const pending = row.pending_price != null;
  return (
    <tr data-testid={`cpl-row-${pid}`}
      className="border-b border-[#F5F5F7] last:border-0 hover:bg-[#F7FAFF]">
      <td className="px-3 py-2 font-mono text-[11px] text-[#6B6B73]">{row.sku}</td>
      <td className="px-3 py-2">
        <span className="font-medium text-[#1C1C1E]">{row.product_name}</span>
        <span className="block text-[10px] text-[#9A9BA3]">{row.category} · /{row.base_unit}</span>
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-[#8E8E93]">
        {formatCurrency(row.global_price)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-[#3C3C43]">
        {row.entity_price != null ? formatCurrency(row.entity_price)
          : <span className="text-[#C7C7CC]">—</span>}
      </td>
      <td className="px-3 py-2 text-right font-semibold tabular-nums"
        data-testid={`cpl-custprice-${pid}`}>
        {row.customer_price != null
          ? <span className="text-[#0058CC]">{formatCurrency(row.customer_price)}</span>
          : <span className="text-[#C7C7CC]">belum diatur</span>}
        {pending && (
          <button type="button" onClick={onOpenApprovals}
            data-testid={`cpl-pending-${pid}`}
            className="mt-0.5 flex w-full items-center justify-end gap-1 text-[10px] font-semibold text-[#B26A00] hover:underline">
            <Clock3 size={10} /> menunggu {formatCurrency(row.pending_price)}
          </button>
        )}
      </td>
      <td className="px-3 py-2 text-right tabular-nums" data-testid={`cpl-eff-${pid}`}>
        <span className="font-bold text-[#1C1C1E]">{formatCurrency(row.effective_price)}</span>
        <span className="ml-1"><SourcePill source={row.price_source} testId={`cpl-source-${pid}`} /></span>
        {row.special_price != null && row.min_quantity > 0 && (
          <span className="block text-[9.5px] text-[#6B219A]">
            min {formatQty(row.min_quantity)} {row.base_unit}
          </span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-right">
        <button data-testid={`cpl-history-${pid}`} className="icon-button" title="Riwayat harga"
          onClick={onHistory}><History size={14} /></button>
        {canManage && (
          <button data-testid={`cpl-setprice-${pid}`} onClick={onSetPrice}
            className="btn-primary ml-1 inline-flex items-center gap-1 px-2.5 py-1 text-[11px]">
            <Plus size={12} /> {row.customer_price != null ? "Ubah" : "Tetapkan"}
          </button>
        )}
      </td>
    </tr>
  );
}

export function EmptyCustomer() {
  return (
    <div data-testid="cpl-no-customer" className="py-14 text-center">
      <AlertTriangle size={26} className="mx-auto mb-2 text-[#D8D8DC]" />
      <p className="text-[13px] font-semibold text-[#3C3C43]">Pilih pelanggan lebih dulu</p>
      <p className="mt-1 text-[11.5px] text-[#8E8E93]">
        Daftar harga bersifat per pelanggan — pilih pelanggan di kotak atas untuk melihat
        dan menetapkan harga langganannya.
      </p>
    </div>
  );
}
