/**
 * FulfillmentDecisionDialog — FASE E-8 (E8.10b#4 · US16/US22) · **KEPUTUSAN PEMENUHAN**.
 *
 * Tiga jalan disajikan SEKALIGUS, masing-masing dengan kelayakannya dan — bila mati —
 * ALASAN tertulisnya. Tombol mati tanpa alasan adalah teka-teki, dan teka-teki di layar
 * yang mengurus barang pelanggan berakhir dengan telepon ke atasan.
 *
 * Wewenang penuh Admin Sales (tanpa persetujuan manajer). Satu-satunya penahan adalah
 * ambang rupiah antar-PT di Pusat Pengaturan (US22): di atas ambang, server menolak
 * dengan menyebut peran penyetuju yang dibutuhkan — penolakan itu ditampilkan utuh.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeftRight, Building2, CheckCircle2, Clock3, PackageSearch, ShoppingCart, XCircle,
} from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import { formatQty } from "../../utils/formatters";
import { apiErrorText } from "../../utils/apiError";
import { fulfillmentDecision, fulfillmentOptions } from "./workDeskApi";

const MODE_META = {
  interco: {
    icon: ArrowLeftRight, label: "Ambil dari PT lain",
    hint: "Lahir transaksi antar-PT bertaut pesanan ini (harga dari kontrak internal).",
  },
  reorder: {
    icon: ShoppingCart, label: "Reorder ke supplier",
    hint: "Lahir Permintaan Pembelian (PR) bertaut pesanan ini.",
  },
  wait: {
    icon: Clock3, label: "Tahan untuk barang masuk",
    hint: "Kekurangan dipegang untuk kiriman yang sudah di jalan (pegging).",
  },
};

export default function FulfillmentDecisionDialog({
  orderId, orderNumber, customerName, onClose, onDecided,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("");
  const [source, setSource] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fulfillmentOptions(orderId);
      setData(res);
      const first = ["interco", "reorder", "wait"]
        .find((m) => res?.options?.[m]?.available);
      setMode((cur) => cur || first || "");
      setError("");
    } catch (e) { setError(apiErrorText(e, "Gagal memuat pilihan pemenuhan.")); }
    finally { setLoading(false); }
  }, [orderId]);

  useEffect(() => { load(); }, [load]);

  const opts = data?.options || {};
  const shortages = Array.isArray(data?.shortages) ? data.shortages : [];
  const candidates = Array.isArray(opts.interco?.candidates) ? opts.interco.candidates : [];
  const picked = useMemo(() => candidates.find((c) => c.entity_id === source) || null,
    [candidates, source]);
  const already = data?.decision || null;

  const blockReason = (() => {
    if (!mode) return "Pilih salah satu jalan pemenuhan dulu.";
    if (!opts[mode]?.available) return opts[mode]?.reason || "Jalan ini belum bisa dipakai.";
    if (mode === "interco" && !source) {
      return "Pilih badan usaha sumber dulu — daftar kandidat beserta stoknya ada di bawah.";
    }
    if (mode === "interco" && picked && !picked.enough) {
      return `Stok ${picked.entity_name} belum cukup untuk semua baris.`;
    }
    return "";
  })();

  async function submit() {
    setBusy(true); setError("");
    try {
      const res = await fulfillmentDecision(orderId, {
        mode, source_entity_id: mode === "interco" ? source : "", note, product_ids: [],
      });
      const dec = res?.decision || {};
      onDecided?.(`${res?.order_number || orderNumber}: ${dec.summary
        || "keputusan pemenuhan tercatat."}`);
    } catch (e) {
      setError(apiErrorText(e, "Gagal menyimpan keputusan pemenuhan."));
    } finally { setBusy(false); }
  }

  return (
    <div className="modal-overlay" data-testid="fulfill-dialog"
         onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}
           style={{ maxWidth: 760, maxHeight: "88vh", overflowY: "auto" }}>
        <div className="flex items-start gap-2">
          <PackageSearch size={17} className="mt-0.5 text-[#B23B14]" />
          <div className="min-w-0">
            <p className="modal-title" data-testid="fulfill-dialog-title">
              Keputusan pemenuhan {orderNumber}
            </p>
            <p className="modal-subtitle">
              {customerName} · wewenang Anda — tanpa menunggu manajer, kecuali nilainya
              melewati ambang yang dipasang pemilik di Pusat Pengaturan.
            </p>
          </div>
        </div>

        <ErrorNotice message={error} onDismiss={() => setError("")} testId="fulfill-error" />

        {loading ? (
          <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="fulfill-loading">
            Menghitung kekurangan & pilihan…
          </div>
        ) : (
          <>
            {already && (
              <div data-testid="fulfill-existing"
                   className="mt-2 rounded-lg border border-[#CBDFFF] bg-[#EAF2FF] px-3 py-2">
                <p className="text-[11.5px] font-bold text-[#0058CC]">
                  Sudah ada keputusan: {already.summary}
                </p>
                <p className="text-[10.5px] text-[#31465F]">
                  oleh {already.by || "—"} · memutuskan ulang akan menambah jejak baru.
                </p>
              </div>
            )}

            {/* Kekurangannya — dalam SATUAN barang, bukan rupiah */}
            <div className="mt-3 rounded-lg border border-[#EFF0F2]" data-testid="fulfill-shortages">
              <div className="grid grid-cols-[1.6fr_90px_90px_100px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
                <span>Barang</span><span className="text-right">Diminta</span>
                <span className="text-right">Dipesan</span><span className="text-right">Kurang</span>
              </div>
              {shortages.length === 0 ? (
                <p className="px-3 py-6 text-center text-[11.5px] text-[#6B6B73]">
                  Tidak ada kekurangan tercatat pada pesanan ini.
                </p>
              ) : shortages.map((s) => (
                <div key={s.backorder_id || s.product_id}
                     data-testid={`fulfill-shortage-${s.product_id}`}
                     className="grid grid-cols-[1.6fr_90px_90px_100px] items-center border-t border-[#F4F5F7] px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-[12px] font-semibold">{s.product_name}</p>
                    <p className="truncate text-[10.5px] text-[#9A9BA3]">{s.sku}</p>
                  </div>
                  <span className="text-right text-[11.5px] tabular-nums">
                    {formatQty(s.requested_qty)}
                  </span>
                  <span className="text-right text-[11.5px] tabular-nums">
                    {formatQty(s.reserved_qty)}
                  </span>
                  <span className="text-right text-[12px] font-bold tabular-nums text-[#B23B14]">
                    {formatQty(s.backorder_qty)} {s.unit}
                  </span>
                </div>
              ))}
            </div>

            {/* TIGA jalan — kelayakan + alasan bila mati */}
            <div className="mt-3 grid gap-2" data-testid="fulfill-options">
              {["interco", "reorder", "wait"].map((key) => (
                <ModeCard key={key} modeKey={key} option={opts[key] || {}}
                          selected={mode === key} onSelect={() => setMode(key)} />
              ))}
            </div>

            {/* Kandidat badan usaha sumber (bukti stok per baris) */}
            {mode === "interco" && (
              <div className="mt-3" data-testid="fulfill-candidates">
                <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">
                  <Building2 size={12} /> Ambil dari badan usaha mana?
                </p>
                {candidates.length === 0 ? (
                  <p className="rounded-lg border border-[#EFF0F2] px-3 py-5 text-center text-[11.5px] text-[#6B6B73]">
                    Tidak ada badan usaha grup yang bisa dinilai untuk pesanan ini.
                  </p>
                ) : (
                  <div className="grid gap-2">
                    {candidates.map((c) => (
                      <CandidateCard key={c.entity_id} cand={c} selected={source === c.entity_id}
                                     onSelect={() => setSource(c.entity_id)} />
                    ))}
                  </div>
                )}
              </div>
            )}

            <textarea data-testid="fulfill-note" className="field mt-3" rows={2}
              value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="Catatan keputusan (opsional) — mis. pelanggan setuju kirim bertahap" />
          </>
        )}

        <div className="modal-actions">
          <button className="btn-secondary" data-testid="fulfill-cancel" onClick={onClose}>Batal</button>
          <button data-testid="fulfill-submit" className="btn-primary"
                  disabled={busy || loading || !!blockReason} title={blockReason}
                  onClick={submit}>
            {busy ? "Memproses…" : "Simpan Keputusan"}
          </button>
        </div>
        {!loading && blockReason && (
          <p data-testid="fulfill-block-reason"
             className="px-1 pb-1 text-right text-[10.5px] text-[#8A5300]">{blockReason}</p>
        )}
      </div>
    </div>
  );
}

function ModeCard({ modeKey, option, selected, onSelect }) {
  const meta = MODE_META[modeKey];
  const Icon = meta.icon;
  const available = !!option.available;
  const extra = modeKey === "wait" && option.promise_date
    ? `Barang masuk ${formatQty(option.incoming_total)} · janji ${String(option.promise_date).slice(0, 10)}`
    : modeKey === "reorder" && option.open_pr_number
      ? `Sudah ada PR terbuka: ${option.open_pr_number}`
      : "";

  return (
    <label data-testid={`fulfill-mode-${modeKey}`}
           className={`flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 ${
             selected ? "border-[#0058CC] bg-[#F2F7FF]" : "border-[#EFF0F2]"} ${
             available ? "" : "opacity-70"}`}>
      <input type="radio" name="fulfill-mode" className="mt-1" checked={selected}
             disabled={!available} onChange={onSelect}
             data-testid={`fulfill-mode-radio-${modeKey}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Icon size={14} className="text-[#0058CC]" />
          <span className="text-[12.5px] font-bold">{meta.label}</span>
          {available ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#BFE6CE] bg-[#E6F6EC] px-2 py-0.5 text-[10px] font-bold text-[#1B7F4B]">
              <CheckCircle2 size={10} /> Bisa dipakai
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#F5C9BC] bg-[#FDEDE7] px-2 py-0.5 text-[10px] font-bold text-[#C0392B]">
              <XCircle size={10} /> Belum bisa
            </span>
          )}
        </div>
        <p className="mt-0.5 text-[11px] text-[#6B6B73]">{meta.hint}</p>
        {extra && <p className="mt-0.5 text-[10.5px] font-semibold text-[#0058CC]">{extra}</p>}
        {!available && option.reason && (
          <p data-testid={`fulfill-reason-${modeKey}`}
             className="mt-1 rounded border border-[#F5D9A8] bg-[#FFF9EF] px-2 py-1 text-[10.5px] text-[#8A5300]">
            {option.reason}
          </p>
        )}
      </div>
    </label>
  );
}

function CandidateCard({ cand, selected, onSelect }) {
  return (
    <label data-testid={`fulfill-candidate-${cand.entity_id}`}
           className={`flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 ${
             selected ? "border-[#0058CC] bg-[#F2F7FF]" : "border-[#EFF0F2]"}`}>
      <input type="radio" name="fulfill-source" className="mt-1" checked={selected}
             onChange={onSelect} data-testid={`fulfill-candidate-radio-${cand.entity_id}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12.5px] font-bold">{cand.entity_name}</span>
          {cand.enough ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#BFE6CE] bg-[#E6F6EC] px-2 py-0.5 text-[10px] font-bold text-[#1B7F4B]">
              <CheckCircle2 size={10} /> Stok cukup
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#F5D9A8] bg-[#FFF4E5] px-2 py-0.5 text-[10px] font-bold text-[#8A5300]">
              Stok belum cukup
            </span>
          )}
        </div>
        <table className="mt-1.5 w-full text-[11px]">
          <thead className="text-[9.5px] font-bold uppercase text-[#9A9BA3]">
            <tr>
              <th className="text-left">Barang</th>
              <th className="text-right">Butuh</th>
              <th className="text-right">Stok di sana</th>
              <th className="text-right">Cukup?</th>
            </tr>
          </thead>
          <tbody>
            {(cand.lines || []).map((l) => (
              <tr key={l.product_id} data-testid={`fulfill-cand-line-${cand.entity_id}-${l.product_id}`}>
                <td className="truncate py-0.5">{l.product_name}</td>
                <td className="py-0.5 text-right tabular-nums">{formatQty(l.needed)}</td>
                <td className="py-0.5 text-right tabular-nums">{formatQty(l.available)}</td>
                <td className={`py-0.5 text-right font-bold ${
                  l.enough ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}>
                  {l.enough ? "ya" : "kurang"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </label>
  );
}
