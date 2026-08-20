/**
 * FASE G-7 · US5 — modal **POTONGAN TERSTRUKTUR**.
 *
 * Lima jenis potongan; yang menunjuk dokumen (retur beli & uang muka) hanya boleh
 * memilih dokumen yang MEMANG tersedia (dikirim backend lewat `prepare`), sehingga
 * layar tidak pernah menawarkan nota yang sudah terpakai. Potongan klaim makloon
 * sengaja TIDAK ada di daftar — nilainya sudah menempel di faktur (Fase D) dan
 * backend menolaknya dengan alasan.
 */
import { useEffect, useMemo, useState } from "react";
import { X, Scissors, Info } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { apiErrorText } from "../../../utils/apiError";
import { fmtDate } from "./contraBonApi";

export default function DeductionModal({ cb, meta, onClose, onSaved, onError }) {
  const kinds = meta?.deduction_kinds || [];
  const reasons = meta?.reasons || [];
  const [kind, setKind] = useState(kinds[0]?.kind || "purchase_return");
  const [refId, setRefId] = useState("");
  const [billId, setBillId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [credits, setCredits] = useState({ purchase_returns: [], supplier_advances: [] });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const spec = useMemo(() => kinds.find((k) => k.kind === kind) || null, [kinds, kind]);

  // Dokumen potongan yang tersedia diambil dari `prepare` supaya daftarnya sama
  // dengan yang dipakai penjaga backend (INV-CB-04): satu nota hanya sekali pakai.
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const r = await axios.get(`${API}/contra-bons/prepare`, {
          params: { supplier_id: cb.supplier_id, entity_id: cb.entity_id, exclude_cb_id: cb.id },
        });
        if (alive) setCredits(r.data?.credits || { purchase_returns: [], supplier_advances: [] });
      } catch (e) {
        if (alive) setErr(apiErrorText(e));
      } finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [cb.supplier_id, cb.entity_id, cb.id]);

  const refOptions = useMemo(() => {
    const pool = kind === "purchase_return" ? credits.purchase_returns
      : kind === "supplier_advance" ? credits.supplier_advances : [];
    return pool.map((c) => ({
      value: c.ref_id,
      label: `${c.label} · sisa ${formatCurrency(c.amount)}${c.date ? ` · ${fmtDate(c.date)}` : ""}`,
    }));
  }, [kind, credits]);

  const picked = useMemo(() => {
    const pool = [...credits.purchase_returns, ...credits.supplier_advances];
    return pool.find((c) => c.ref_id === refId) || null;
  }, [credits, refId]);

  const billOptions = useMemo(() => (cb.bills || []).map((b) => ({
    value: b.bill_id,
    label: `${b.bill_number}${b.po_number ? ` · ${b.po_number}` : ""} · ${formatCurrency(b.applied_amount)}`,
  })), [cb.bills]);

  const reasonOptions = useMemo(
    () => reasons.map((r) => ({ value: r.code, label: r.label })), [reasons]);

  const room = Math.max(0, Number((cb.totals || {}).bills_total || 0)
    - Number((cb.totals || {}).deductions_total || 0));

  async function save() {
    setSaving(true); setErr("");
    try {
      const r = await axios.post(`${API}/contra-bons/${cb.id}/deductions`, {
        kind,
        ref_id: spec?.needs_ref ? refId : "",
        bill_id: kind === "match_variance" ? billId : "",
        amount: amount === "" ? null : Number(amount),
        reason_code: reason,
        note: note.trim(),
      });
      onSaved(r.data);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setSaving(false); }
  }

  const blocked = saving
    || (spec?.needs_ref && !refId)
    || (kind === "match_variance" && !billId)
    || (spec?.reason_required && !reason)
    || (!spec?.needs_ref && (amount === "" || Number(amount) <= 0));

  return (
    <div className="modal-overlay" data-testid="cb-deduction-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card wide">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="modal-title flex items-center gap-1.5">
            <Scissors size={15} /> Tambah potongan kontrabon
          </h3>
          <button className="icon-button" data-testid="cb-deduction-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        <p className="modal-subtitle">
          {cb.number} · {cb.supplier_name} — sisa ruang potongan <b>{formatCurrency(room)}</b>{" "}
          (nilai bersih kontrabon tidak boleh negatif).
        </p>

        {err && (
          <ErrorNotice message={err} onDismiss={() => setErr("")} testId="cb-deduction-error" />
        )}

        <div className="mt-3 space-y-3">
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Jenis potongan</label>
            <KNSelect data-testid="cb-deduction-kind" value={kind}
              onValueChange={(v) => { setKind(v); setRefId(""); setAmount(""); setReason(""); }}
              options={kinds.map((k) => ({ value: k.kind, label: k.label }))} className="field" />
            {spec && (
              <p className="mt-1 flex items-start gap-1 rounded-md bg-[#F2F7FF] px-2 py-1.5 text-[11px] text-[#1C1C1E]">
                <Info size={11} className="mt-[2px] shrink-0" /> {spec.help}
              </p>
            )}
            {spec && !spec.posts_gl && (
              <p className="mt-1 text-[10px] text-[#B26A00]">
                Tidak dijurnal ulang — jurnalnya sudah lahir di dokumen sumbernya. Di sini ia
                diterapkan sebagai pelunasan non-kas pada faktur.
              </p>
            )}
          </div>

          {spec?.needs_ref && (
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Dokumen sumber (wajib)
              </label>
              {loading
                ? <p className="text-[11.5px] text-[#8E8E93]">Memuat dokumen yang tersedia…</p>
                : refOptions.length === 0
                  ? (
                    <p className="rounded-md bg-[#FFF4E5] px-2 py-1.5 text-[11px] text-[#8C4A00]"
                      data-testid="cb-deduction-no-ref">
                      Tidak ada dokumen tersedia untuk jenis ini. Nota debit harus sudah disetujui
                      dengan konsekuensi potong hutang, dan uang muka belum terpakai di kontrabon lain.
                    </p>
                  )
                  : (
                    <KNSelect data-testid="cb-deduction-ref" value={refId} onValueChange={setRefId}
                      options={refOptions} className="field" placeholder="Pilih dokumen" />
                  )}
              {picked && (
                <p className="mt-1 text-[10px] text-[#8E8E93]">
                  Sisa nilai dokumen {formatCurrency(picked.amount)} dari total{" "}
                  {formatCurrency(picked.total_amount)}
                  {picked.po_number ? ` · ${picked.po_number}` : ""}
                  {picked.reason ? ` · ${picked.reason}` : ""}
                </p>
              )}
            </div>
          )}

          {kind === "match_variance" && (
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Tagihan yang selisihnya dipotong (wajib)
              </label>
              <KNSelect data-testid="cb-deduction-bill" value={billId} onValueChange={setBillId}
                options={billOptions} className="field" placeholder="Pilih tagihan" />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Nominal potongan (Rp)
              </label>
              <input data-testid="cb-deduction-amount" type="number" min={0} step={1000}
                className="input-field w-full" value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder={spec?.needs_ref ? "Kosongkan = seluruh sisa dokumen" : "0"} />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Alasan berlabel {spec?.reason_required ? "(wajib)" : "(otomatis bila dikosongkan)"}
              </label>
              <KNSelect data-testid="cb-deduction-reason" value={reason} onValueChange={setReason}
                options={reasonOptions} className="field" placeholder="Pilih alasan" />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Catatan</label>
            <textarea data-testid="cb-deduction-note" className="textarea w-full" rows={2}
              value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="Mis. kain cacat 3 roll sudah diambil kurir supplier tanggal 12." />
          </div>
        </div>

        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" data-testid="cb-deduction-save"
            disabled={blocked} onClick={save}>
            {saving ? "Menyimpan…" : "Tambah potongan"}
          </button>
        </div>
      </div>
    </div>
  );
}
