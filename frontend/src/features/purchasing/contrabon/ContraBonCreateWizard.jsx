/**
 * FASE G-7 · US2 — **wizard buat kontrabon** (3 langkah).
 *
 * Ritual nyatanya: supplier datang membawa setumpuk faktur → kita pilih faktur mana
 * yang masuk siklus ini → terbit SATU tanda terima bernomor `<ENT>/CB-#####`.
 * Kandidat faktur, potongan tersedia, dan usulan jatuh tempo semuanya datang dari
 * `GET /contra-bons/prepare` supaya layar tidak pernah menawarkan faktur yang sudah
 * dipegang kontrabon lain (INV-CB-01).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { X, Plus, ChevronRight, ChevronLeft, Info, AlertTriangle, PackageSearch } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { apiErrorText } from "../../../utils/apiError";
import WizardCreditPicker from "./WizardCreditPicker";
import { fmtDate } from "./contraBonApi";

const STEPS = [
  { n: 1, label: "Pilih supplier" },
  { n: 2, label: "Pilih faktur" },
  { n: 3, label: "Periksa & terbitkan" },
];

export default function ContraBonCreateWizard({ suppliers, presetSupplierId, selectedEntity,
  onClose, onCreated, onError }) {
  const [step, setStep] = useState(presetSupplierId ? 2 : 1);
  const [supplierId, setSupplierId] = useState(presetSupplierId || "");
  const [prep, setPrep] = useState(null);
  const [picked, setPicked] = useState({});          // bill_id -> true
  const [amounts, setAmounts] = useState({});        // bill_id -> nominal (opsional)
  const [credPick, setCredPick] = useState({});      // ref_id -> true (potongan otomatis)
  const [credAmt, setCredAmt] = useState({});        // ref_id -> nominal (opsional)
  const [cycleDate, setCycleDate] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [pic, setPic] = useState("");
  const [notes, setNotes] = useState("");
  const [submitNow, setSubmitNow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const supplierOptions = useMemo(
    () => (suppliers || []).map((s) => ({
      value: s.id, label: `${s.name}${s.code ? ` · ${s.code}` : ""}`,
    })), [suppliers]);

  const loadPrepare = useCallback(async (sid) => {
    if (!sid) return;
    setLoading(true); setErr("");
    try {
      const r = await axios.get(`${API}/contra-bons/prepare`, {
        params: { supplier_id: sid, ...(selectedEntity && selectedEntity !== "all"
          ? { entity_id: selectedEntity } : {}) },
      });
      const d = r.data || {};
      setPrep(d);
      setCycleDate((d.suggested || {}).cycle_date || "");
      setDueDate((d.suggested || {}).due_date || "");
      setPic(((d.supplier || {}).invoice_exchange || {}).pic_name || "");
      // Semua faktur yang tersedia dicentang lebih dulu: itulah kebiasaan lapangan
      // (supplier membawa SEMUA fakturnya), petugas hanya perlu membatalkan yang ditunda.
      const all = {};
      (d.bills || []).forEach((b) => { all[b.bill_id] = true; });
      setPicked(all);
      setAmounts({});
      setCredPick({});
      setCredAmt({});
    } catch (e) {
      setPrep(null);
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setLoading(false); }
  }, [selectedEntity, onError]);

  useEffect(() => { if (supplierId) loadPrepare(supplierId); }, [supplierId, loadPrepare]);

  const bills = prep?.bills || [];
  const chosen = bills.filter((b) => picked[b.bill_id]);
  const chosenTotal = chosen.reduce(
    (a, b) => a + (amounts[b.bill_id] === undefined || amounts[b.bill_id] === ""
      ? Number(b.outstanding || 0) : Number(amounts[b.bill_id] || 0)), 0);
  const poCount = new Set(chosen.map((b) => b.po_number).filter(Boolean)).size;
  const credits = prep?.credits || { purchase_returns: [], supplier_advances: [] };
  const creditList = [...credits.purchase_returns, ...credits.supplier_advances];
  const creditCount = creditList.length;
  const takenCredits = creditList.filter((c) => credPick[c.ref_id]);
  const creditsTotal = takenCredits.reduce(
    (a, c) => a + (credAmt[c.ref_id] === undefined || credAmt[c.ref_id] === ""
      ? Number(c.amount || 0) : Number(credAmt[c.ref_id] || 0)), 0);
  const netAfter = Math.round((chosenTotal - creditsTotal) * 100) / 100;

  /**
   * Terbitkan kontrabon LALU tempelkan potongan yang dipilih.
   *
   * Urutannya sengaja begini: nomor kontrabon & penjaga faktur (INV-CB-01) lahir dari
   * `POST /contra-bons`, sedangkan tiap potongan punya penjaganya sendiri (INV-CB-04:
   * satu nota debit / uang muka hanya boleh dipakai sekali) yang HARUS dijalankan
   * backend, bukan ditebak layar. Karena itu "Ajukan langsung" ditunda sampai seluruh
   * potongan menempel — kalau tidak, kontrabon sudah berpindah status dan potongan
   * ditolak ("hanya boleh sebelum verifikasi").
   */
  async function create() {
    setSaving(true); setErr("");
    let made = null;
    try {
      const r = await axios.post(`${API}/contra-bons`, {
        supplier_id: supplierId,
        entity_id: prep?.entity_id || "",
        bills: chosen.map((b) => ({
          bill_id: b.bill_id,
          applied_amount: amounts[b.bill_id] === undefined || amounts[b.bill_id] === ""
            ? null : Number(amounts[b.bill_id]),
        })),
        cycle_date: cycleDate,
        due_date: dueDate,
        supplier_pic: pic.trim(),
        notes: notes.trim(),
        submit_now: false,
      });
      made = r.data;
      const failed = [];
      for (const c of takenCredits) {
        try {
          const d = await axios.post(`${API}/contra-bons/${made.id}/deductions`, {
            kind: c.kind,
            ref_id: c.ref_id,
            amount: credAmt[c.ref_id] === undefined || credAmt[c.ref_id] === ""
              ? null : Number(credAmt[c.ref_id]),
            note: `Dipotong saat tukar faktur — ${c.label}`,
          });
          made = d.data;
        } catch (e) {
          failed.push(`${c.ref_number || c.label}: ${apiErrorText(e)}`);
        }
      }
      if (submitNow) {
        try {
          const s = await axios.post(`${API}/contra-bons/${made.id}/submit`, {});
          made = s.data;
        } catch (e) { failed.push(`Pengajuan: ${apiErrorText(e)}`); }
      }
      onCreated(made, failed);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-overlay" data-testid="cb-create-wizard" {...overlayDismiss(onClose)}>
      <div className="modal-panel max-h-[92vh] w-[860px] max-w-[96vw] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h3 className="flex items-center gap-2 text-[14px] font-bold text-[#1C1C1E]">
            <Plus size={15} className="text-[#0058CC]" /> Kontrabon baru · tukar faktur supplier
          </h3>
          <button className="icon-button" data-testid="cb-create-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>

        <div className="flex items-center gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-4 py-2">
          {STEPS.map((s) => (
            <div key={s.n} className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] ${
              step === s.n ? "bg-[#EAF2FF] font-bold text-[#0058CC]"
                : step > s.n ? "text-[#1B7F4B]" : "text-[#8E8E93]"}`}
              data-testid={`cb-create-step-${s.n}`}>
              <span className={`flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold ${
                step >= s.n ? "bg-[#0058CC] text-white" : "bg-[#E5E5EA] text-[#8E8E93]"}`}>
                {s.n}
              </span>
              {s.label}
            </div>
          ))}
        </div>

        <div className="px-4 py-4">
          {err && (
            <ErrorNotice message={err} onRetry={supplierId ? () => loadPrepare(supplierId) : undefined}
              onDismiss={() => setErr("")} testId="cb-create-error" />
          )}

          {step === 1 && (
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                  Supplier yang datang menukar faktur
                </label>
                <KNSelect data-testid="cb-create-supplier" value={supplierId}
                  onValueChange={setSupplierId} options={supplierOptions} className="field"
                  placeholder="Pilih supplier" />
              </div>
              {loading && <p className="text-[12px] text-[#8E8E93]">Merakit kandidat faktur…</p>}
              {prep && (
                <div className="space-y-2" data-testid="cb-create-prep-summary">
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                    <div className="stat-card">
                      <p className="stat-label">Tagihan siap</p>
                      <p className="stat-value text-[#0058CC]">{bills.length}</p>
                      <p className="text-[10px] text-[#8E8E93]">
                        {formatCurrency(prep.bills_total)}
                      </p>
                    </div>
                    <div className="stat-card">
                      <p className="stat-label">Potongan tersedia</p>
                      <p className="stat-value text-[#B26A00]">{creditCount}</p>
                      <p className="text-[10px] text-[#8E8E93]">
                        {formatCurrency(prep.credits_total)}
                      </p>
                    </div>
                    <div className="stat-card">
                      <p className="stat-label">Belum ditagih</p>
                      <p className="stat-value">
                        {formatCurrency((prep.unbilled_receipts || {}).total_value)}
                      </p>
                      <p className="text-[10px] text-[#8E8E93]">
                        {(prep.unbilled_receipts || {}).po_count || 0} PO
                      </p>
                    </div>
                    <div className="stat-card">
                      <p className="stat-label">Termin</p>
                      <p className="stat-value">
                        {(prep.supplier || {}).payment_term_code || "—"}
                      </p>
                      <p className="text-[10px] text-[#8E8E93]">
                        jatuh tempo diusulkan {fmtDate((prep.suggested || {}).due_date)}
                      </p>
                    </div>
                  </div>
                  {((prep.supplier || {}).invoice_exchange || {}).mode !== "none" && (
                    <p className="flex items-start gap-1 rounded-md bg-[#F2F7FF] px-2 py-1.5 text-[11px] text-[#1C1C1E]">
                      <Info size={11} className="mt-[2px] shrink-0" />
                      Supplier ini punya jadwal tukar faktur tersimpan — pengingat H-n akan terbit
                      otomatis menjelang siklusnya.
                    </p>
                  )}
                  {(prep.unbilled_receipts || {}).overdue_count > 0 && (
                    <p className="flex items-start gap-1 rounded-md bg-[#FFF4E5] px-2 py-1.5 text-[11px] text-[#8C4A00]">
                      <PackageSearch size={11} className="mt-[2px] shrink-0" />
                      {(prep.unbilled_receipts || {}).overdue_count} PO sudah tertunggak: barang
                      diterima tapi fakturnya belum datang. Tagih supplier saat tukar faktur ini.
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              {bills.length === 0
                ? (
                  <p className="rounded-md bg-[#FFF4E5] px-3 py-2 text-[12px] text-[#8C4A00]"
                    data-testid="cb-create-no-bills">
                    Tidak ada tagihan supplier yang siap dikontrabon. Tagihan harus berstatus
                    “posted”, masih ada sisa hutang, dan belum dipegang kontrabon lain.
                  </p>
                )
                : (
                  <div className="overflow-hidden rounded-lg border border-[#E5E5EA]">
                    <table className="w-full text-[12px]">
                      <thead className="bg-[#FAFBFC]">
                        <tr className="text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93]">
                          <th className="px-3 py-2">Pilih</th>
                          <th className="px-3 py-2">Tagihan</th>
                          <th className="px-3 py-2">PO</th>
                          <th className="px-3 py-2">Jatuh tempo</th>
                          <th className="px-3 py-2 text-right">Sisa hutang</th>
                          <th className="px-3 py-2 text-right">Ditarik ke kontrabon</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bills.map((b) => (
                          <tr key={b.bill_id} className="border-t border-[#F2F2F5]"
                            data-testid={`cb-create-bill-${b.bill_id}`}>
                            <td className="px-3 py-2">
                              <input type="checkbox" data-testid={`cb-create-pick-${b.bill_id}`}
                                checked={!!picked[b.bill_id]}
                                onChange={(e) => setPicked((p) => ({
                                  ...p, [b.bill_id]: e.target.checked,
                                }))} />
                            </td>
                            <td className="px-3 py-2">
                              <p className="font-bold text-[#0058CC]">{b.bill_number}</p>
                              <p className="text-[10px] text-[#8E8E93]">
                                faktur supplier {b.supplier_invoice_no || "—"}
                              </p>
                            </td>
                            <td className="px-3 py-2">{b.po_number || "—"}</td>
                            <td className="px-3 py-2">{fmtDate(b.due_date)}</td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {formatCurrency(b.outstanding)}
                              {Number(b.claim_deduction) > 0 && (
                                <p className="text-[10px] text-[#B26A00]">
                                  potongan makloon {formatCurrency(b.claim_deduction)} sudah menempel
                                </p>
                              )}
                            </td>
                            <td className="px-3 py-2 text-right">
                              <input type="number" min={0} step={1000}
                                data-testid={`cb-create-amount-${b.bill_id}`}
                                className="input-field w-[140px] text-right"
                                disabled={!picked[b.bill_id]}
                                placeholder={String(Math.round(Number(b.outstanding || 0)))}
                                value={amounts[b.bill_id] ?? ""}
                                onChange={(e) => setAmounts((a) => ({
                                  ...a, [b.bill_id]: e.target.value,
                                }))} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

              {(prep?.makloon_attached || []).length > 0 && (
                <div className="rounded-md border border-[#FFE0B2] bg-[#FFFBF3] px-3 py-2"
                  data-testid="cb-create-makloon-info">
                  <p className="flex items-center gap-1 text-[11px] font-bold text-[#8C4A00]">
                    <AlertTriangle size={11} /> Potongan klaim makloon sudah menempel di faktur
                  </p>
                  {(prep.makloon_attached || []).map((m) => (
                    <p key={m.bill_id} className="mt-0.5 text-[11px] text-[#1C1C1E]">
                      {m.bill_number} · {formatCurrency(m.amount)} — {m.note}
                    </p>
                  ))}
                </div>
              )}

              <WizardCreditPicker credits={creditList} picked={credPick} amounts={credAmt}
                onTogglePick={(id, on) => setCredPick((st) => ({ ...st, [id]: on }))}
                onChangeAmount={(id, v) => setCredAmt((st) => ({ ...st, [id]: v }))} />

              <p className="text-[11.5px] text-[#6B6B73]" data-testid="cb-create-selected-summary">
                Terpilih <b>{chosen.length}</b> faktur dari <b>{poCount}</b> PO · nilai{" "}
                <b>{formatCurrency(chosenTotal)}</b>
                {takenCredits.length > 0 && (
                  <>
                    {" · potongan "}<b className="text-[#B26A00]">
                      {formatCurrency(creditsTotal)}
                    </b>
                    {" → dibayar "}<b className={netAfter < 0 ? "text-[#C0392B]" : "text-[#0058CC]"}>
                      {formatCurrency(netAfter)}
                    </b>
                  </>
                )}
              </p>
              {netAfter < 0 && (
                <p className="rounded-md bg-[#FDE2E2] px-2 py-1.5 text-[11px] text-[#9B1C1C]"
                  data-testid="cb-create-negative-warning">
                  Total potongan melebihi nilai faktur — nilai bersih kontrabon tidak boleh
                  negatif. Kurangi nominal potongan atau tambahkan faktur.
                </p>
              )}
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                    Tanggal tukar faktur
                  </label>
                  <input data-testid="cb-create-cycle-date" type="date" className="input-field w-full"
                    value={cycleDate} onChange={(e) => setCycleDate(e.target.value)} />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                    Jatuh tempo pembayaran
                  </label>
                  <input data-testid="cb-create-due-date" type="date" className="input-field w-full"
                    value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
                  <p className="mt-1 text-[10px] text-[#8E8E93]">
                    Diusulkan dari termin supplier ({(prep?.suggested || {}).term_days || 0} hari).
                  </p>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                  Yang menyerahkan faktur (pihak supplier)
                </label>
                <input data-testid="cb-create-pic" className="input-field w-full" value={pic}
                  onChange={(e) => setPic(e.target.value)}
                  placeholder="Nama pengantar faktur — tercetak di tanda terima" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Catatan</label>
                <textarea data-testid="cb-create-notes" className="textarea w-full" rows={2}
                  value={notes} onChange={(e) => setNotes(e.target.value)}
                  placeholder="Mis. 3 faktur asli diterima, 1 masih fotokopi menyusul." />
              </div>

              <div className="rounded-lg border border-[#E5E5EA] bg-[#FAFBFC] px-3 py-2"
                data-testid="cb-create-review">
                <p className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">
                  Ringkasan
                </p>
                <p className="mt-1 text-[12px] text-[#1C1C1E]">
                  {(prep?.supplier || {}).name} · <b>{chosen.length}</b> faktur dari{" "}
                  <b>{poCount}</b> PO · nilai <b>{formatCurrency(chosenTotal)}</b>
                </p>
                {takenCredits.length > 0 && (
                  <p className="mt-0.5 text-[12px] text-[#1C1C1E]"
                    data-testid="cb-create-review-credits">
                    Potongan langsung: <b>{takenCredits.length}</b> dokumen ·{" "}
                    <b className="text-[#B26A00]">{formatCurrency(creditsTotal)}</b> → yang
                    dibayar <b className="text-[#0058CC]">{formatCurrency(netAfter)}</b>
                  </p>
                )}
                <p className="mt-0.5 text-[11px] text-[#8E8E93]">
                  Nomor kontrabon terbit otomatis mengikuti kode PT.
                  {takenCredits.length > 0
                    ? " Potongan ditempelkan sesudah nomor terbit, masing-masing lewat"
                      + " penjaganya sendiri."
                    : ""}
                </p>
              </div>

              <label className="flex items-center gap-1.5 text-[12px] text-[#1C1C1E]">
                <input type="checkbox" data-testid="cb-create-submit-now" checked={submitNow}
                  onChange={(e) => setSubmitNow(e.target.checked)} />
                Langsung ajukan untuk verifikasi 3-way match
              </label>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" data-testid="cb-create-back"
            disabled={step === 1} onClick={() => setStep((s) => Math.max(1, s - 1))}>
            <ChevronLeft size={14} /> Kembali
          </button>
          <div className="flex items-center gap-2">
            <button className="secondary-button" onClick={onClose}>Batal</button>
            {step < 3
              ? (
                <button className="primary-button" data-testid="cb-create-next"
                  disabled={(step === 1 && (!supplierId || !prep))
                    || (step === 2 && chosen.length === 0)}
                  onClick={() => setStep((s) => s + 1)}>
                  Lanjut <ChevronRight size={14} />
                </button>
              )
              : (
                <button className="primary-button" data-testid="cb-create-submit"
                  disabled={saving || chosen.length === 0 || netAfter < 0} onClick={create}>
                  {saving ? "Menerbitkan…" : "Terbitkan kontrabon"}
                </button>
              )}
          </div>
        </div>
      </div>
    </div>
  );
}
