/**
 * FASE G-6b — Wizard **RETUR ANTAR-PT** (setelah barangnya sudah berpindah).
 *
 * Pembatalan sengaja ditolak begitu barang berpindah; jalan resminya adalah retur.
 * Layar ini hanya menawarkan baris yang MASIH bisa diretur (jumlah asal − yang sudah
 * diretur), memaksa alasan tercatat, dan menunjukkan dampak uangnya sebelum disimpan.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { X, Undo2, AlertTriangle, PackageCheck } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import { apiErrorText } from "../../../utils/apiError";

export default function IntercoReturnModal({ doc, onClose, onCreated }) {
  const [info, setInfo] = useState(null);
  const [qty, setQty] = useState({});
  // E9.4 — roll yang DIPILIH per produk. Kalau kosong, mesin mengutamakan roll hasil
  // retur pelanggan (lot RTN-…) sebelum FEFO biasa — tetapi memilih sendiri jauh lebih
  // jujur: yang dikembalikan ke PT penjual harus barang yang MEMANG diretur pelanggan.
  const [pickedRolls, setPickedRolls] = useState({});
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setBusy(true); setErr("");
    try {
      const r = await axios.get(`${API}/interco/transactions/${doc.id}/returnable`);
      setInfo(r.data);
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  }, [doc.id]);

  useEffect(() => { load(); }, [load]);

  const lines = useMemo(
    () => (info?.lines || []).filter((l) => l.qty_returnable > 0), [info]);

  const totals = useMemo(() => {
    const sub = lines.reduce(
      (a, l) => a + (parseFloat(qty[l.product_id] || 0) || 0) * l.unit_price, 0);
    const rate = info?.tax_apply ? (info?.tax_rate || 0) : 0;
    const tax = Math.round(sub * rate) / 100;
    return { sub: Math.round(sub * 100) / 100, tax, total: Math.round((sub + tax) * 100) / 100 };
  }, [lines, qty, info]);

  const picked = lines.filter((l) => (parseFloat(qty[l.product_id] || 0) || 0) > 0);
  const overflow = lines.some(
    (l) => (parseFloat(qty[l.product_id] || 0) || 0) > l.qty_returnable + 0.0001);
  const canSubmit = picked.length > 0 && reason.trim().length >= 5 && !overflow && !busy;

  // Memilih roll = menentukan jumlahnya. Menyimpan dua angka yang bisa berbeda
  // (jumlah vs roll) hanya melahirkan dokumen yang tidak cocok dengan barangnya.
  const toggleRoll = (line, roll) => {
    setPickedRolls((s) => {
      const cur = s[line.product_id] || [];
      const next = cur.includes(roll.roll_id)
        ? cur.filter((x) => x !== roll.roll_id)
        : [...cur, roll.roll_id];
      const sum = (line.rolls || [])
        .filter((r) => next.includes(r.roll_id))
        .reduce((a, r) => a + Number(r.qty || 0), 0);
      setQty((q) => ({ ...q, [line.product_id]: next.length ? String(Math.round(sum * 100) / 100) : "" }));
      return { ...s, [line.product_id]: next };
    });
  };

  const submit = async () => {
    setBusy(true); setErr("");
    try {
      const r = await axios.post(`${API}/interco/returns`, {
        interco_id: doc.id,
        items: picked.map((l) => ({
          product_id: l.product_id,
          quantity: parseFloat(qty[l.product_id]),
          roll_ids: pickedRolls[l.product_id] || [],
        })),
        reason: reason.trim(),
        notes: notes.trim(),
      });
      onCreated?.(r.data);
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-[rgba(15,23,42,0.45)] flex items-center justify-center p-4"
         data-testid="interco-return-modal"
         onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="w-full max-w-3xl rounded-2xl bg-white shadow-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E5E5EA] flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[#1D1D1F] flex items-center gap-2">
              <Undo2 size={17} /> Retur Antar-PT
            </h2>
            <p className="text-xs text-[#6E6E73] mt-0.5">
              atas {info?.origin_number || doc.number} · {info?.buyer_entity_name} →{" "}
              {info?.seller_entity_name}
            </p>
          </div>
          <button onClick={onClose} data-testid="interco-return-close"
                  className="p-1.5 rounded-md text-[#6E6E73] hover:bg-[#F2F2F5]" aria-label="Tutup">
            <X size={17} />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4 max-h-[70vh] overflow-y-auto">
          {err && <ErrorNotice message={err} onDismiss={() => setErr("")} />}

          {info && !info.can_return && (
            <div className="flex items-start gap-2 rounded-lg bg-[#FFF4E5] px-3 py-2.5 text-[13px] text-[#8A5300]"
                 data-testid="interco-return-blocked">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              <span>{info.blocked_reason}</span>
            </div>
          )}

          {info?.can_return && (
            <>
              <div className="rounded-xl border border-[#E5E5EA] overflow-hidden">
                <table className="w-full text-sm" data-testid="interco-return-lines">
                  <thead className="bg-[#F7F7F9] text-[#3C3C43]">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Barang</th>
                      <th className="text-right px-3 py-2 font-medium">Harga internal</th>
                      <th className="text-right px-3 py-2 font-medium">Dikirim</th>
                      <th className="text-right px-3 py-2 font-medium">Sudah diretur</th>
                      <th className="text-right px-3 py-2 font-medium">Retur sekarang</th>
                      <th className="text-left px-3 py-2 font-medium">Roll yang dikirim balik</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#F2F2F5]">
                    {lines.map((l) => {
                      const v = qty[l.product_id] || "";
                      const bad = (parseFloat(v || 0) || 0) > l.qty_returnable + 0.0001;
                      return (
                        <tr key={l.product_id} data-testid={`interco-return-line-${l.product_id}`}>
                          <td className="px-3 py-2">
                            <div className="text-[#1D1D1F]">{l.product_name}</div>
                            <div className="text-xs text-[#8E8E93]">{l.sku}</div>
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {formatCurrency(l.unit_price)}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {formatQty(l.qty_total)} {l.unit}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums text-[#6E6E73]">
                            {formatQty(l.qty_returned)}
                          </td>
                          <td className="px-3 py-2 text-right">
                            <input
                              type="number" min="0" step="0.01" max={l.qty_returnable}
                              value={v}
                              onChange={(e) => setQty((s) => ({ ...s, [l.product_id]: e.target.value }))}
                              data-testid={`interco-return-qty-${l.product_id}`}
                              className={`w-24 rounded-lg border px-2 py-1.5 text-sm text-right tabular-nums bg-white ${
                                bad ? "border-[#E53935] text-[#C0392B]" : "border-[#E5E5EA] text-[#1D1D1F]"}`}
                              placeholder={`max ${formatQty(l.qty_returnable)}`}
                            />
                          </td>
                          <td className="px-3 py-2">
                            {(l.rolls || []).length === 0 ? (
                              <span className="text-[11px] text-[#8E8E93]">
                                Tidak ada roll tersedia di gudang.
                              </span>
                            ) : (
                              <div className="space-y-1 max-h-32 overflow-y-auto pr-1"
                                   data-testid={`interco-return-rolls-${l.product_id}`}>
                                {(l.rolls || []).map((rr) => {
                                  const on = (pickedRolls[l.product_id] || []).includes(rr.roll_id);
                                  return (
                                    <label key={rr.roll_id}
                                           data-testid={`interco-return-roll-${rr.roll_id}`}
                                           className={`flex items-center gap-1.5 text-[11px] rounded px-1.5 py-1 border cursor-pointer ${
                                             on ? "border-[#0058CC] bg-[#EAF2FF]" : "border-[#E5E5EA] bg-white"}`}>
                                      <input type="checkbox" checked={on}
                                             onChange={() => toggleRoll(l, rr)} />
                                      <span className="font-mono">{rr.roll_no || rr.roll_id.slice(-6)}</span>
                                      <span className="text-[#6E6E73]">{rr.lot}</span>
                                      <span className="tabular-nums">{formatQty(rr.qty)} {rr.unit}</span>
                                      {rr.grade ? <span className="text-[#8E8E93]">gr {rr.grade}</span> : null}
                                      {rr.is_customer_return && (
                                        <span className="inline-flex items-center gap-0.5 text-[9.5px] rounded px-1 py-0.5 bg-[#FFF7EF] text-[#8C4A00] border border-[#F5C9A6]">
                                          <PackageCheck size={9} /> retur pelanggan
                                        </span>
                                      )}
                                    </label>
                                  );
                                })}
                              </div>
                            )}
                            {l.warning && (
                              <p data-testid={`interco-return-warning-${l.product_id}`}
                                 className="mt-1 text-[10.5px] text-[#8A5300] bg-[#FFF4E5] border border-[#F1D9AE] rounded px-1.5 py-1 leading-snug">
                                {l.warning}
                              </p>
                            )}
                            <p className="mt-1 text-[10px] text-[#8E8E93]">
                              di gudang {formatQty(l.qty_on_hand || 0)} {l.unit} · dari retur
                              pelanggan {formatQty(l.qty_from_customer_return || 0)} {l.unit}
                            </p>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="grid grid-cols-3 gap-3" data-testid="interco-return-totals">
                <Box label="Nilai barang" value={formatCurrency(totals.sub)} />
                <Box label={`PPN ${info.tax_apply ? `${info.tax_rate}%` : "—"}`}
                     value={formatCurrency(totals.tax)} />
                <Box label="Utang antar-PT berkurang" value={formatCurrency(totals.total)} />
              </div>

              <div className="space-y-2">
                <label className="block text-xs font-medium text-[#3C3C43]">
                  Alasan retur (wajib, minimal 5 huruf)
                </label>
                <textarea
                  rows={2} value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  data-testid="interco-return-reason"
                  placeholder="mis. warna kain tidak sesuai contoh yang disetujui"
                  className="w-full rounded-lg border border-[#E5E5EA] bg-white px-3 py-2 text-sm text-[#1D1D1F]"
                />
                <label className="block text-xs font-medium text-[#3C3C43]">Catatan (opsional)</label>
                <input
                  value={notes} onChange={(e) => setNotes(e.target.value)}
                  data-testid="interco-return-notes"
                  className="w-full rounded-lg border border-[#E5E5EA] bg-white px-3 py-2 text-sm text-[#1D1D1F]"
                />
              </div>

              <p className="text-[11px] text-[#8E8E93]">
                Retur terbit sebagai <b>draf</b>. Jurnal pembalik di dua buku baru terbit
                setelah <b>disetujui rekan lain</b> (pembuat ≠ penyetuju), dan barangnya baru
                keluar dari gudang pembeli setelah <b>tugas gudang</b> arah balik disetujui.
              </p>
            </>
          )}
        </div>

        <div className="px-6 py-4 border-t border-[#E5E5EA] flex items-center justify-end gap-2 bg-[#FAFBFC]">
          <button onClick={onClose} data-testid="interco-return-cancel-btn"
                  className="px-3.5 py-2 text-sm rounded-lg border border-[#E5E5EA] bg-white text-[#3C3C43] hover:bg-[#F2F2F5]">
            Batal
          </button>
          <button onClick={submit} disabled={!canSubmit}
                  data-testid="interco-return-submit"
                  className="px-3.5 py-2 text-sm rounded-lg bg-[#0F172A] text-white hover:bg-black disabled:opacity-40">
            {busy ? "Menyimpan…" : "Buat Retur"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Box({ label, value }) {
  return (
    <div className="rounded-lg border border-[#E5E5EA] bg-white p-3">
      <div className="text-[10px] uppercase tracking-wide text-[#8E8E93]">{label}</div>
      <div className="mt-1 text-[15px] font-semibold text-[#1D1D1F] tabular-nums">{value}</div>
    </div>
  );
}
