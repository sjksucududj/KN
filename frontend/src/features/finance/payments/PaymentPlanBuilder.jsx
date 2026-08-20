/**
 * PaymentPlanBuilder — FASE G-2 · penyusun **jadwal pembayaran** yang benar-benar bebas.
 *
 * Pemilik menolak template kaku. Karena itu template hanya tombol "titik awal":
 * DP + cicilan, milestone, atau NET — lalu setiap baris (label, nominal, jatuh tempo)
 * bisa diubah, ditambah, dan dihapus. Validasi Σ ditampilkan LIVE supaya user tahu
 * sebelum menyimpan, bukan setelah ditolak server.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Loader2, Plus, Trash2, Wand2 } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { createPlan, errText, money, previewPlan, updatePlan } from "./paymentApi";

const KIND_OPTS = [
  { value: "dp", label: "Uang Muka (DP)" },
  { value: "installment", label: "Cicilan" },
  { value: "milestone", label: "Milestone" },
  { value: "retention", label: "Retensi" },
];
const RULE_OPTS = [
  { value: "fixed_date", label: "Tanggal tetap" },
  { value: "net_days", label: "N hari dari dokumen" },
  { value: "monthly", label: "Bulanan" },
  { value: "weekly", label: "Mingguan" },
];

export default function PaymentPlanBuilder({
  docType = "sales_order", docId, total = 0, plan, tolerance = 1, onSaved, onCancel,
}) {
  const [mode, setMode] = useState(plan?.mode || "dp_installment");
  const [lines, setLines] = useState(plan?.lines || []);
  const [dpPercent, setDpPercent] = useState(15);
  const [installments, setInstallments] = useState(6);
  const [interval, setInterval_] = useState("monthly");
  const [netDays, setNetDays] = useState(30);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const sum = useMemo(
    () => lines.reduce((a, l) => a + Number(l.amount || 0), 0), [lines]);
  const diff = useMemo(() => Math.round((Number(total || 0) - sum) * 100) / 100, [sum, total]);
  const balanced = Math.abs(diff) <= Number(tolerance || 1) + 0.0001;

  const applyTemplate = useCallback(async () => {
    setBusy("tpl"); setErr("");
    try {
      const res = await previewPlan({
        doc_type: docType, doc_id: docId, mode,
        dp_percent: Number(dpPercent), installments: Number(installments),
        interval, net_days: Number(netDays),
      });
      setLines(res.lines || []);
    } catch (e) { setErr(errText(e, "Gagal membentuk jadwal dari template.")); }
    finally { setBusy(""); }
  }, [docType, docId, mode, dpPercent, installments, interval, netDays]);

  useEffect(() => { if (!plan) applyTemplate(); /* titik awal saat pertama dibuka */ },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []);

  const patch = (i, field, value) => setLines((ls) => ls.map((l, idx) => (
    idx === i ? { ...l, [field]: field === "amount" ? Number(value || 0) : value } : l)));
  const addLine = () => setLines((ls) => [...ls, {
    seq: ls.length + 1, kind: "installment", label: `Pembayaran ${ls.length + 1}`,
    basis: "amount", amount: Math.max(0, diff), due_rule: "fixed_date",
    due_date: new Date().toISOString().slice(0, 10), status: "open", paid_amount: 0,
  }]);
  const removeLine = (i) => setLines((ls) => ls.filter((_, idx) => idx !== i));
  const fillRest = (i) => setLines((ls) => ls.map((l, idx) => (
    idx === i ? { ...l, amount: Math.round((Number(l.amount || 0) + diff) * 100) / 100 } : l)));

  const save = async () => {
    setBusy("save"); setErr("");
    try {
      const body = { mode, lines: lines.map((l, i) => ({ ...l, seq: i + 1, basis: "amount" })) };
      const saved = plan?.id
        ? await updatePlan(plan.id, body)
        : await createPlan({ doc_type: docType, doc_id: docId, ...body });
      if (onSaved) onSaved(saved);
    } catch (e) { setErr(errText(e, "Gagal menyimpan rencana pembayaran.")); }
    finally { setBusy(""); }
  };

  return (
    <div data-testid="payment-plan-builder" className="rounded-lg border border-[#EDEEF1] bg-white p-2.5">
      <div className="mb-2 flex flex-wrap items-end gap-2">
        <div className="grid gap-1">
          <label className="kicker">Titik awal</label>
          <KNSelect value={mode} onValueChange={setMode} className="field !w-[190px]"
            data-testid="ppb-mode" options={[
              { value: "dp_installment", label: "DP + Cicilan" },
              { value: "milestone", label: "Milestone" },
              { value: "net", label: "Sekali bayar (NET)" },
              { value: "custom", label: "Bebas" },
            ]} />
        </div>
        {mode === "dp_installment" && (
          <>
            <div className="grid gap-1">
              <label className="kicker">DP %</label>
              <input data-testid="ppb-dp" className="field !w-[80px]" type="number" value={dpPercent}
                onChange={(e) => setDpPercent(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <label className="kicker">Jumlah cicilan</label>
              <input data-testid="ppb-installments" className="field !w-[90px]" type="number"
                value={installments} onChange={(e) => setInstallments(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <label className="kicker">Jarak</label>
              <KNSelect value={interval} onValueChange={setInterval_} className="field !w-[120px]"
                data-testid="ppb-interval"
                options={[{ value: "monthly", label: "Bulanan" }, { value: "weekly", label: "Mingguan" }]} />
            </div>
          </>
        )}
        {mode === "net" && (
          <div className="grid gap-1">
            <label className="kicker">NET (hari)</label>
            <input data-testid="ppb-netdays" className="field !w-[90px]" type="number" value={netDays}
              onChange={(e) => setNetDays(e.target.value)} />
          </div>
        )}
        <button type="button" className="secondary-button" onClick={applyTemplate}
          disabled={busy !== ""} data-testid="ppb-apply-template">
          {busy === "tpl" ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />}
          Bentuk jadwal
        </button>
      </div>

      {err && (
        <div className="notice-bar danger !py-1.5" data-testid="ppb-error">
          <span className="text-[11.5px]">{err}</span>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-[11.5px]" data-testid="ppb-table">
          <thead>
            <tr className="border-b border-[#EDEEF1] text-left text-[9.5px] uppercase tracking-wide text-[#8E8E93]">
              <th className="px-1 py-1">#</th><th className="px-1 py-1">Jenis</th>
              <th className="px-1 py-1">Keterangan</th><th className="px-1 py-1">Aturan</th>
              <th className="px-1 py-1">Jatuh tempo</th>
              <th className="px-1 py-1 text-right">Nominal</th><th className="px-1 py-1"></th>
            </tr>
          </thead>
          <tbody>
            {lines.length === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-[11.5px] text-[#6B6B73]"
                data-testid="ppb-empty">Belum ada baris — pilih titik awal lalu tekan “Bentuk jadwal”.</td></tr>
            )}
            {lines.map((l, i) => (
              <tr key={i} className="border-b border-[#F5F5F7]" data-testid={`ppb-row-${i}`}>
                <td className="px-1 py-1 text-[#8E8E93]">{i + 1}</td>
                <td className="px-1 py-1">
                  <KNSelect value={l.kind} onValueChange={(v) => patch(i, "kind", v)}
                    className="field !w-[130px] !py-0.5" data-testid={`ppb-kind-${i}`} options={KIND_OPTS} />
                </td>
                <td className="px-1 py-1">
                  <input className="field !py-0.5" value={l.label || ""} data-testid={`ppb-label-${i}`}
                    onChange={(e) => patch(i, "label", e.target.value)} />
                </td>
                <td className="px-1 py-1">
                  <KNSelect value={l.due_rule || "fixed_date"} onValueChange={(v) => patch(i, "due_rule", v)}
                    className="field !w-[150px] !py-0.5" data-testid={`ppb-rule-${i}`} options={RULE_OPTS} />
                </td>
                <td className="px-1 py-1">
                  <input type="date" className="field !py-0.5 !w-[135px]" value={(l.due_date || "").slice(0, 10)}
                    data-testid={`ppb-due-${i}`} onChange={(e) => patch(i, "due_date", e.target.value)} />
                </td>
                <td className="px-1 py-1 text-right">
                  <input type="number" className="field !py-0.5 !w-[130px] text-right tabular-nums"
                    value={l.amount} data-testid={`ppb-amount-${i}`}
                    onChange={(e) => patch(i, "amount", e.target.value)} />
                </td>
                <td className="px-1 py-1">
                  <div className="flex items-center gap-1">
                    {!balanced && (
                      <button type="button" title="Bebankan sisa ke baris ini" data-testid={`ppb-fill-${i}`}
                        onClick={() => fillRest(i)}
                        className="rounded border border-[#BBD3FF] bg-[#EAF2FF] px-1 text-[9px] font-bold text-[#0058CC]">
                        sisa
                      </button>
                    )}
                    <button type="button" title="Hapus baris" data-testid={`ppb-del-${i}`}
                      onClick={() => removeLine(i)} className="text-[#9B1C1C] hover:opacity-70">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <button type="button" className="secondary-button" onClick={addLine} data-testid="ppb-add-line">
          <Plus size={13} /> Tambah baris
        </button>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Nilai dokumen</p>
            <p className="text-[12px] font-bold tabular-nums">{money(total)}</p>
          </div>
          <div className="text-right" data-testid="ppb-sum">
            <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Σ jadwal</p>
            <p className={`text-[12px] font-bold tabular-nums ${balanced ? "text-[#1B7A43]" : "text-[#9B1C1C]"}`}>
              {money(sum)}
            </p>
          </div>
          {balanced ? (
            <span data-testid="ppb-balanced"
              className="inline-flex items-center gap-1 rounded-full bg-[#E5F6EC] px-2 py-0.5 text-[10.5px] font-semibold text-[#1B7A43]">
              <CheckCircle2 size={12} /> Sudah pas
            </span>
          ) : (
            <span data-testid="ppb-unbalanced"
              className="rounded-full bg-[#FDE2E2] px-2 py-0.5 text-[10.5px] font-semibold text-[#9B1C1C]">
              Selisih {money(diff)}
            </span>
          )}
          {onCancel && (
            <button type="button" className="secondary-button" onClick={onCancel} data-testid="ppb-cancel">
              Batal
            </button>
          )}
          <button type="button" className="primary-button" onClick={save}
            disabled={!balanced || busy !== "" || lines.length === 0} data-testid="ppb-save">
            {busy === "save" ? <Loader2 size={13} className="animate-spin" /> : null}
            {plan?.id ? "Simpan perubahan" : "Simpan rencana"}
          </button>
        </div>
      </div>
    </div>
  );
}
