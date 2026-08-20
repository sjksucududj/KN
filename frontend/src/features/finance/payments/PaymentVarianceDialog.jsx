/**
 * PaymentVarianceDialog — FASE G-3 · dialog **Selisih Pembayaran** (lebih / kurang bayar).
 *
 * Bahasa manusia lebih dulu:
 *   “Dibayar Rp 9.950.000, seharusnya Rp 10.000.000. Kurang Rp 50.000 — mau bagaimana?”
 *
 * Lalu 3 kartu pilihan dengan DAMPAK masing-masing, label alasan WAJIB, dan input
 * tambahan sesuai pilihan (tanggal baru untuk ubah jadwal · pesanan tujuan untuk alokasi ·
 * cara pengembalian untuk refund). Dipakai dua tempat dengan komponen yang sama:
 *   • saat kwitansi dibuat (`onConfirm` mengembalikan payload ke form kwitansi);
 *   • saat diputus belakangan dari antrean Selisih Bayar.
 */
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowRightLeft, CalendarClock, Coins, Eraser, HandCoins, Loader2, PiggyBank, X,
} from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { money } from "./paymentApi";

const ICONS = {
  outstanding: Coins,
  reschedule: CalendarClock,
  writeoff: Eraser,
  deposit: PiggyBank,
  allocate: ArrowRightLeft,
  refund: HandCoins,
};

const METHODS = [
  { value: "transfer", label: "Transfer bank (Kas Besar)" },
  { value: "cash", label: "Tunai (Kas Kecil)" },
];

function Sentence({ a }) {
  const gap = Math.abs(Number(a?.delta || 0));
  const under = Number(a?.delta || 0) < 0;
  return (
    <p className="text-[13px] leading-relaxed text-[#1C1C1E]" data-testid="pv-sentence">
      Dibayar <b className="tabular-nums">{money(a?.funds)}</b>, seharusnya{" "}
      <b className="tabular-nums">{money(a?.boundary ?? a?.expected)}</b>{" "}
      <span className="text-[#6B6B73]">({a?.boundary_label || "tagihan yang jatuh tempo"})</span>.{" "}
      <b className={under ? "text-[#9B1C1C]" : "text-[#8A6D00]"}>
        {under ? "Kurang" : "Lebih"} {money(gap)}
      </b>{" "}
      — mau bagaimana?
    </p>
  );
}

export default function PaymentVarianceDialog({
  assessment,
  reasons = [],
  busy = false,
  error = "",
  submitLabel = "Simpan keputusan",
  onCancel,
  onConfirm,
}) {
  const a = assessment || {};
  const options = useMemo(() => a.options || [], [a.options]);
  const [kind, setKind] = useState("");
  const [reasonCode, setReasonCode] = useState("");
  const [note, setNote] = useState("");
  const [dueDate, setDueDate] = useState(a.suggested_due_date || "");
  const [method, setMethod] = useState(a?.policy?.refund_method || "transfer");
  const [alloc, setAlloc] = useState({});

  const gap = Math.round(Math.abs(Number(a.delta || 0)) * 100) / 100;
  const under = Number(a.delta || 0) < 0;

  useEffect(() => {
    const dflt = options.find((o) => o.default && o.available) || options.find((o) => o.available);
    setKind(dflt?.value || "");
    setDueDate(a.suggested_due_date || "");
    setMethod(a?.policy?.refund_method || "transfer");
    // Alokasi diisi otomatis serakah (tertua dulu) supaya petugas cukup memeriksa.
    const next = {};
    let left = gap;
    (a.others || []).forEach((o) => {
      const take = Math.min(left, Number(o.outstanding || 0));
      if (take > 0) { next[o.order_id] = Math.round(take * 100) / 100; left = Math.round((left - take) * 100) / 100; }
    });
    setAlloc(next);
    // Alasan bawaan yang paling lazim untuk arah selisihnya.
    const prefer = under ? ["bank_charge", "partial_payment_agreed"] : ["customer_overtransfer"];
    const hit = prefer.find((c) => reasons.some((r) => r.code === c));
    setReasonCode(hit || "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a.direction, a.delta, options.length, reasons.length]);

  const allocTotal = useMemo(
    () => Math.round(Object.values(alloc).reduce((s, v) => s + (Number(v) || 0), 0) * 100) / 100,
    [alloc],
  );

  const picked = options.find((o) => o.value === kind);
  const allocInvalid = kind === "allocate" && (allocTotal <= 0 || allocTotal > gap + 0.01);
  const canSubmit = !!kind && !!reasonCode && !busy && !allocInvalid
    && (kind !== "reschedule" || !!dueDate);

  function submit() {
    const payload = { kind, reason_code: reasonCode, note };
    if (kind === "reschedule") payload.due_date = dueDate;
    if (kind === "refund") { payload.method = method; payload.amount = gap; }
    if (kind === "allocate") {
      payload.allocations = Object.entries(alloc)
        .filter(([, v]) => Number(v) > 0)
        .map(([order_id, v]) => ({ order_id, amount: Number(v) }));
      payload.amount = allocTotal;
    }
    onConfirm?.(payload);
  }

  return (
    <div className="modal-overlay" data-testid="payment-variance-dialog"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel?.(); }}>
      <div className="modal-card" style={{ maxWidth: 620, width: "95vw" }}>
        <div className="flex items-start justify-between gap-3 border-b border-[#EFF0F2] px-4 py-3">
          <div>
            <h3 className="text-[14px] font-bold text-[#1C1C1E]">
              Selisih Pembayaran · {under ? "Kurang bayar" : "Lebih bayar"}
            </h3>
            <p className="text-[11px] text-[#6B6B73]">
              {a.customer_name || "Pelanggan"} · toleransi otomatis {money(a.tolerance)}.
              Setiap selisih di luar toleransi wajib punya keputusan berlabel.
            </p>
          </div>
          <button type="button" className="icon-button" onClick={onCancel} data-testid="pv-close">
            <X size={15} />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-3 overflow-y-auto p-4">
          <div className="rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] p-3">
            <Sentence a={a} />
            {(a.explain || []).length > 0 && (
              <ul className="mt-1.5 space-y-0.5" data-testid="pv-explain">
                {(a.explain || []).map((e, i) => (
                  <li key={i} className="text-[10.5px] text-[#6B6B73]">• {e}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="grid gap-2" data-testid="pv-options">
            {options.map((o) => {
              const Icon = ICONS[o.value] || Coins;
              const active = kind === o.value;
              return (
                <button key={o.value} type="button" disabled={!o.available}
                  data-testid={`pv-option-${o.value}`} data-selected={active ? "1" : "0"}
                  onClick={() => o.available && setKind(o.value)}
                  className={`flex w-full items-start gap-2.5 rounded-lg border p-2.5 text-left transition-colors ${
                    active ? "border-[#0058CC] bg-[#F5F9FF]"
                      : o.available ? "border-[#EDEEF1] bg-white hover:border-[#C9DBF7]"
                        : "border-[#F0F0F2] bg-[#FAFAFB] opacity-60"}`}>
                  <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
                    active ? "bg-[#0058CC] text-white" : "bg-[#F1F2F4] text-[#4A4B52]"}`}>
                    <Icon size={14} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <b className="text-[12.5px] text-[#1C1C1E]">{o.label}</b>
                      {o.default && (
                        <span className="rounded bg-[#E5F6EC] px-1.5 py-0.5 text-[9px] font-bold uppercase text-[#1B7A43]">
                          disarankan
                        </span>
                      )}
                      {o.requires_role && (
                        <span className="rounded bg-[#FFF3CD] px-1.5 py-0.5 text-[9px] font-bold uppercase text-[#8A6D00]">
                          wajib {o.requires_role}
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-[#4A4B52]">{o.help}</span>
                    <span className="mt-0.5 block text-[10.5px] text-[#6B6B73]">Dampak: {o.impact}</span>
                    {!o.available && o.unavailable_reason && (
                      <span className="mt-0.5 block text-[10.5px] font-semibold text-[#9B1C1C]">
                        {o.unavailable_reason}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>

          {kind === "reschedule" && (
            <div className="grid gap-1 rounded-lg border border-[#EDEEF1] bg-white p-2.5">
              <label className="kicker">Jatuh tempo baru untuk sisa {money(gap)}</label>
              <input type="date" className="field" value={dueDate} data-testid="pv-due-date"
                onChange={(e) => setDueDate(e.target.value)} />
              <p className="text-[10.5px] text-[#6B6B73]">
                Baris jadwal akan dipecah: bagian yang sudah dibayar tetap, sisanya pindah ke
                tanggal ini. Jumlah seluruh rencana tidak berubah.
              </p>
            </div>
          )}

          {kind === "refund" && (
            <div className="grid gap-1 rounded-lg border border-[#EDEEF1] bg-white p-2.5">
              <label className="kicker">Cara pengembalian {money(gap)}</label>
              <KNSelect className="field" value={method} onValueChange={setMethod}
                data-testid="pv-refund-method" options={METHODS} />
              <p className="text-[10.5px] text-[#6B6B73]">
                Kas keluar dicatat di buku kas & berjurnal (Uang Muka Pelanggan turun).
              </p>
            </div>
          )}

          {kind === "allocate" && (
            <div className="rounded-lg border border-[#EDEEF1] bg-white p-2.5">
              <div className="mb-1.5 flex items-center justify-between">
                <label className="kicker">Pesanan terbuka lain</label>
                <span className={`text-[11px] font-bold tabular-nums ${
                  allocInvalid ? "text-[#9B1C1C]" : "text-[#1B7A43]"}`} data-testid="pv-alloc-total">
                  {money(allocTotal)} / {money(gap)}
                </span>
              </div>
              <div className="max-h-[180px] space-y-1 overflow-y-auto">
                {(a.others || []).length === 0 && (
                  <p className="py-2 text-center text-[11px] text-[#6B6B73]">
                    Tidak ada pesanan terbuka lain.
                  </p>
                )}
                {(a.others || []).map((o) => (
                  <div key={o.order_id} className="flex items-center gap-2 text-[11.5px]"
                    data-testid={`pv-alloc-row-${o.order_id}`}>
                    <span className="min-w-0 flex-1">
                      <b className="text-[#0058CC]">{o.number}</b>
                      <span className="ml-1 text-[10.5px] text-[#6B6B73]">
                        sisa {money(o.outstanding)}
                      </span>
                    </span>
                    <input type="number" className="field w-36 !py-1 text-[11.5px] tabular-nums"
                      data-testid={`pv-alloc-input-${o.order_id}`}
                      value={alloc[o.order_id] ?? ""} placeholder="0"
                      onChange={(e) => {
                        const v = Math.max(0, Math.min(Number(e.target.value) || 0,
                          Number(o.outstanding || 0)));
                        setAlloc((p) => ({ ...p, [o.order_id]: v }));
                      }} />
                  </div>
                ))}
              </div>
              {allocInvalid && (
                <p className="mt-1 flex items-center gap-1 text-[10.5px] font-semibold text-[#9B1C1C]">
                  <AlertTriangle size={11} /> Total alokasi harus lebih dari 0 dan tidak melebihi
                  kelebihan bayar {money(gap)}.
                </p>
              )}
            </div>
          )}

          <div className="grid gap-2 md:grid-cols-2">
            <div className="grid gap-1">
              <label className="kicker">Label alasan (wajib)</label>
              <KNSelect className="field" value={reasonCode} onValueChange={setReasonCode}
                data-testid="pv-reason" placeholder="Pilih alasan…"
                options={(reasons || []).map((r) => ({ value: r.code, label: r.label }))} />
            </div>
            <div className="grid gap-1">
              <label className="kicker">Catatan</label>
              <input className="field" value={note} data-testid="pv-note"
                onChange={(e) => setNote(e.target.value)}
                placeholder="Mis. hasil pembicaraan dengan pelanggan…" />
            </div>
          </div>

          {!reasonCode && (
            <p className="flex items-center gap-1 text-[10.5px] text-[#8C4A00]" data-testid="pv-reason-hint">
              <AlertTriangle size={11} /> Pilih label alasan dulu — server menolak keputusan tanpa alasan.
            </p>
          )}
          {picked?.requires_role && (
            <p className="text-[10.5px] text-[#6B6B73]">
              Keputusan ini hanya bisa disimpan oleh <b>{picked.requires_role}</b> / admin
              {Number(picked.max_amount || 0) > 0
                ? ` dan maksimum ${money(picked.max_amount)} untuk ${picked.requires_role}.`
                : "."}
            </p>
          )}
          {error && (
            <div className="notice-bar danger !py-1.5" data-testid="pv-error">
              <span className="text-[11.5px]">{error}</span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <span className="text-[10.5px] text-[#9A9BA3]">
            Keputusan tercatat sebagai dokumen bernomor beserta nama pemutus.
          </span>
          <div className="flex gap-2">
            <button type="button" className="secondary-button" onClick={onCancel}
              data-testid="pv-cancel">Batal</button>
            <button type="button" className="primary-button" onClick={submit}
              disabled={!canSubmit} data-testid="pv-submit">
              {busy ? <Loader2 size={13} className="animate-spin" /> : null} {submitLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
