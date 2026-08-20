/**
 * DeskQueueCard — satu ANTREAN meja kerja (dipakai Meja Admin Sales & Meja Finance).
 *
 * Aturan desain yang dijaga komponen ini (US15):
 *  1. Setiap antrean membawa **JUMLAH · NILAI · UMUR TERTUA** di kepalanya. Antrean
 *     tanpa tiga angka itu memaksa pengguna membuka isinya untuk tahu apakah perlu
 *     dibuka — itu bukan meja kerja, itu daftar.
 *  2. **Satu tindakan jelas per baris.** Bukan menu tiga titik: pengguna meja kerja
 *     mengerjakan satu hal berulang kali, jadi tombolnya harus langsung terlihat.
 *  3. Satuannya ikut jenis nilainya. Antrean "perlu dipenuhi" menghitung YARD, bukan
 *     rupiah; menulis `Rp 200` untuk 200 yard adalah cara tercepat kehilangan
 *     kepercayaan pengguna pada seluruh ringkasan.
 */
import { useState } from "react";
import { ChevronDown, ChevronRight, Inbox } from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { ageTone, badgeClass, badgeLabel, queueMeta } from "./workDeskApi";

export default function DeskQueueCard({
  queue, onAction, busyRef = "", testPrefix = "desk", defaultOpen, loading = false,
}) {
  const [open, setOpen] = useState(
    defaultOpen === undefined ? (queue?.count || 0) > 0 : defaultOpen);
  const meta = queueMeta(queue?.id);
  const Icon = meta.icon;
  const isQty = queue?.value_kind === "qty";
  const rows = Array.isArray(queue?.rows) ? queue.rows : [];
  const oldest = ageTone(queue?.oldest_age_days);

  const totalText = isQty
    ? `${formatQty(queue?.total_value)} ${rows[0]?.unit || ""}`.trim()
    : formatCurrency(queue?.total_value);

  return (
    <section className="section-card" data-testid={`${testPrefix}-queue-${queue?.id}`}>
      <button
        type="button"
        data-testid={`${testPrefix}-queue-toggle-${queue?.id}`}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left hover:bg-[#FAFBFC]"
      >
        <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg"
              style={{ background: meta.bg }}>
          <Icon size={16} style={{ color: meta.tone }} />
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-bold text-[#1C1C1E]">{queue?.label}</span>
            <span data-testid={`${testPrefix}-count-${queue?.id}`}
                  className="rounded-full px-2 py-0.5 text-[10.5px] font-bold tabular-nums"
                  style={{ background: meta.bg, color: meta.tone }}>
              {queue?.count || 0}
            </span>
            {(queue?.count || 0) > 0 && (
              <span data-testid={`${testPrefix}-oldest-${queue?.id}`}
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${oldest.cls}`}
                    title="Umur baris tertua di antrean ini">
                tertua {oldest.label}
              </span>
            )}
          </span>
          <span className="mt-1 block text-[10.5px] leading-relaxed text-[#6B6B73]">
            {queue?.hint}
          </span>
        </span>

        <span className="shrink-0 pl-2 text-right">
          <span className="block text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
            {queue?.value_label || "Nilai"}
          </span>
          <span data-testid={`${testPrefix}-total-${queue?.id}`}
                className="block text-[12.5px] font-bold tabular-nums text-[#1C1C1E]">
            {totalText}
          </span>
        </span>
        <span className="mt-1 shrink-0 text-[#9A9BA3]">
          {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </span>
      </button>

      {/* Saat antrean sedang dimuat ulang, angka lama masih terpampang. Tanpa
          penanda ini pengguna menindak baris yang mungkin sudah berpindah antrean. */}
      {open && loading && rows.length > 0 && (
        <p data-testid={`${testPrefix}-refreshing-${queue?.id}`}
           className="border-t border-[#EFF0F2] bg-[#FAFBFC] px-3 py-1 text-[10.5px] text-[#8E8E93]">
          Memuat ulang antrean…
        </p>
      )}

      {open && (
        loading && rows.length === 0 ? (
          <p data-testid={`${testPrefix}-loading-${queue?.id}`}
             className="border-t border-[#EFF0F2] px-3 py-7 text-center text-[11.5px] text-[#6B6B73]">
            Memuat antrean…
          </p>
        ) : rows.length === 0 ? (
          <div data-testid={`${testPrefix}-empty-${queue?.id}`}
               className="border-t border-[#EFF0F2] px-3 py-7 text-center text-[11.5px] text-[#6B6B73]">
            <Inbox size={22} className="mx-auto mb-1.5 text-[#D6D6DB]" />
            Antrean ini bersih — tidak ada yang perlu ditindak.
          </div>
        ) : (
          <div className="divide-y divide-[#F4F5F7] border-t border-[#EFF0F2]">
            {rows.map((row) => (
              <QueueRow key={`${row.ref_type}-${row.ref_id}`} row={row} queue={queue}
                        isQty={isQty} busy={busyRef === row.ref_id}
                        testPrefix={testPrefix}
                        onAction={() => onAction?.(row, queue)} />
            ))}
          </div>
        )
      )}
    </section>
  );
}

function QueueRow({ row, queue, isQty, busy, onAction, testPrefix }) {
  const age = ageTone(row.age_days);
  const value = isQty
    ? `${formatQty(row.value)} ${row.unit || ""}`.trim()
    : formatCurrency(row.value);

  return (
    <div data-testid={`${testPrefix}-row-${row.ref_id}`}
         className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-2.5 hover:bg-[#FAFBFC]">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span data-testid={`${testPrefix}-number-${row.ref_id}`}
                className="text-[11.5px] font-bold text-[#0058CC]">{row.number}</span>
          {row.badge && (
            <span data-testid={`${testPrefix}-badge-${row.ref_id}`}
                  className={`rounded-full border px-1.5 py-0.5 text-[9.5px] font-bold ${badgeClass(row.badge)}`}>
              {badgeLabel(row.badge)}
            </span>
          )}
          <span className={`rounded-full border px-1.5 py-0.5 text-[9.5px] font-bold ${age.cls}`}
                title="Umur baris ini">{age.label}</span>
        </div>
        <p className="truncate text-[12px] font-semibold text-[#1C1C1E]">{row.title}</p>
        {row.subtitle && (
          <p className="truncate text-[10.5px] text-[#8E8E93]">{row.subtitle}</p>
        )}
      </div>

      <span data-testid={`${testPrefix}-value-${row.ref_id}`}
            className="w-[130px] shrink-0 text-right text-[12px] font-semibold tabular-nums">
        {value}
      </span>

      <button type="button" data-testid={`${testPrefix}-action-${row.ref_id}`}
              className="btn-secondary btn-xs shrink-0" disabled={busy} onClick={onAction}
              title={queue?.hint || ""}>
        {busy ? "Memproses…" : (row.action || queue?.action_label || "Buka")}
      </button>
    </div>
  );
}
