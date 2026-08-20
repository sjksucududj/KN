/**
 * FASE G-7 · US7 — modal **BAYAR KONTRABON**: satu kas keluar melunasi banyak faktur.
 *
 * Potongan diterapkan sebagai pelunasan NON-KAS pada pembayaran pertama, sehingga
 * subledger hutang (`vendor_bills`) dan buku besar akhirnya rekonsiliasi — celah
 * nyata yang ada sebelum fase ini.
 */
import { useEffect, useMemo, useState } from "react";
import { X, Banknote, Info } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { apiErrorText } from "../../../utils/apiError";
import { CASH_TYPE_OPTIONS, METHOD_OPTIONS, todayISO } from "./contraBonApi";

export default function PayModal({ cb, onClose, onPaid, onError }) {
  const t = cb.totals || {};
  const firstPayment = !(cb.payments || []).length;
  const [amount, setAmount] = useState(String(t.outstanding ?? ""));
  const [method, setMethod] = useState((cb.schedule || {}).method || "transfer");
  const [cashType, setCashType] = useState("kas_besar");
  const [accountId, setAccountId] = useState((cb.schedule || {}).bank_account_id || "");
  const [paidAt, setPaidAt] = useState(todayISO());
  const [notes, setNotes] = useState("");
  const [accounts, setAccounts] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/bank-accounts`);
        const list = Array.isArray(r.data) ? r.data : (r.data?.items || []);
        if (alive) setAccounts(list);
      } catch (e) { if (alive) setErr(apiErrorText(e)); }
    })();
    return () => { alive = false; };
  }, []);

  const accountOptions = useMemo(() => accounts.map((a) => ({
    value: a.id,
    label: `${a.name}${a.bank_name ? ` · ${a.bank_name}` : ""}${
      a.account_number ? ` · ${a.account_number}` : ""}`,
  })), [accounts]);

  async function pay() {
    setSaving(true); setErr("");
    try {
      const r = await axios.post(`${API}/contra-bons/${cb.id}/pay`, {
        amount: amount === "" ? null : Number(amount),
        method,
        cash_type: cashType,
        bank_account_id: accountId,
        paid_at: paidAt,
        notes: notes.trim(),
      });
      onPaid(r.data);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-overlay" data-testid="cb-pay-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card wide">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="modal-title flex items-center gap-1.5">
            <Banknote size={15} /> Bayar kontrabon
          </h3>
          <button className="icon-button" data-testid="cb-pay-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        <p className="modal-subtitle">
          {cb.number} · {cb.supplier_name} — {(cb.bills || []).length} faktur dilunasi oleh
          SATU transaksi kas.
        </p>

        {err && <ErrorNotice message={err} onDismiss={() => setErr("")} testId="cb-pay-error" />}

        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="stat-card">
            <p className="stat-label">Nilai faktur</p>
            <p className="stat-value tabular-nums">{formatCurrency(t.bills_total)}</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Potongan</p>
            <p className="stat-value text-[#B26A00] tabular-nums">{formatCurrency(t.deductions_total)}</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Nilai bersih</p>
            <p className="stat-value text-[#0058CC] tabular-nums">{formatCurrency(t.net_payable)}</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Sisa dibayar</p>
            <p className="stat-value text-[#C0392B]" data-testid="cb-pay-outstanding">
              {formatCurrency(t.outstanding)}
            </p>
          </div>
        </div>

        {firstPayment && Number(t.deductions_total) > 0 && (
          <p className="mt-2 flex items-start gap-1 rounded-md bg-[#F2F7FF] px-2 py-1.5 text-[11px] text-[#1C1C1E]"
            data-testid="cb-pay-deduction-note">
            <Info size={11} className="mt-[2px] shrink-0" />
            Pada pembayaran pertama, potongan {formatCurrency(t.deductions_total)} ikut diterapkan
            sebagai pelunasan non-kas pada faktur-faktur di kontrabon ini — uang yang keluar dari
            kas hanya nilai bersihnya.
          </p>
        )}

        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Nominal dibayar (Rp)
              </label>
              <input data-testid="cb-pay-amount" type="number" min={0} step={1000}
                className="input-field w-full" value={amount}
                onChange={(e) => setAmount(e.target.value)} />
              <p className="mt-1 text-[10px] text-[#8E8E93]">
                Kosongkan untuk melunasi seluruh sisa bersih. Pembayaran sebagian diizinkan.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Tanggal pembayaran
              </label>
              <input data-testid="cb-pay-date" type="date" className="input-field w-full"
                value={paidAt} onChange={(e) => setPaidAt(e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Cara bayar</label>
              <KNSelect data-testid="cb-pay-method" value={method} onValueChange={setMethod}
                options={METHOD_OPTIONS} className="field" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Sumber kas</label>
              <KNSelect data-testid="cb-pay-cashtype" value={cashType} onValueChange={setCashType}
                options={CASH_TYPE_OPTIONS} className="field" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Rekening / kas
              </label>
              <KNSelect data-testid="cb-pay-account" value={accountId} onValueChange={setAccountId}
                options={accountOptions} className="field" placeholder="Pilih rekening" />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Catatan</label>
            <textarea data-testid="cb-pay-notes" className="textarea w-full" rows={2}
              value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Mis. transfer BCA jam 14:10, bukti dikirim ke WhatsApp supplier." />
          </div>

          <p className="text-[10.5px] text-[#9A9BA3]">
            Transaksi kas yang lahir memuat nomor kontrabon di keterangannya, sehingga langsung
            menjadi kandidat pada Rekonsiliasi Bank.
          </p>
        </div>

        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" data-testid="cb-pay-submit"
            disabled={saving} onClick={pay}>
            {saving ? "Memproses…" : "Catat pembayaran"}
          </button>
        </div>
      </div>
    </div>
  );
}
