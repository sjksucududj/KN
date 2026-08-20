/**
 * SuspensePanel (Gelombang 3 F-8) — pemantauan & reklasifikasi akun Suspense (1-9999).
 * Saldo suspense harus NOL sebelum tutup buku. Sumber: /api/gl/suspense (+ /reclass).
 * Dipakai sebagai tab di GeneralLedger.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, AlertTriangle, CheckCircle2, ArrowLeftRight } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { formatCurrency } from "../../utils/formatters";

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return String(iso).slice(0, 10); }
}

export default function SuspensePanel({ refreshKey, accounts = [], entities = [], selectedEntity, onNotice, onChanged }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const entityOptions = useMemo(
    () => entities.filter((e) => !e.is_group).map((e) => ({ value: e.id, label: e.short_name || e.legal_name || e.id })),
    [entities]);
  const targetOptions = useMemo(
    () => accounts.filter((a) => a.is_postable && a.code !== "1-9999").map((a) => ({ value: a.code, label: `${a.code} — ${a.name}` })),
    [accounts]);

  const initialEntity = (selectedEntity && selectedEntity !== "all") ? selectedEntity : (entityOptions[0]?.value || "");
  const [form, setForm] = useState({ entity_id: initialEntity, amount: "", side: "credit", target_account: "", note: "" });
  const setF = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/gl/suspense`);
      setReport(res.data);
      const bal = res.data?.balance || 0;
      setForm((p) => ({
        ...p,
        entity_id: p.entity_id || initialEntity,
        side: bal < 0 ? "credit" : "debit",
        amount: p.amount || (Math.abs(bal) ? String(Math.abs(bal)) : ""),
      }));
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data suspense.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  const balance = report?.balance || 0;
  const isZero = Math.abs(balance) < 0.005;

  const submit = async () => {
    setError(""); setBusy(true);
    try {
      const amt = parseFloat(form.amount);
      if (!form.entity_id) throw new Error("Pilih entitas (PT) untuk reklasifikasi.");
      if (!(amt > 0)) throw new Error("Nominal reklasifikasi harus lebih dari 0.");
      if (!form.target_account) throw new Error("Pilih akun tujuan reklasifikasi.");
      const res = await axios.post(`${API}/gl/suspense/reclass`, {
        amount: amt, side: form.side, target_account: form.target_account,
        note: form.note, entity_id: form.entity_id,
      });
      onNotice && onNotice(`Reklasifikasi suspense berhasil. Jurnal: ${res.data?.number || "—"}.`);
      setForm((p) => ({ ...p, amount: "", note: "" }));
      await load();
      onChanged && onChanged();
    } catch (e) {
      setError(e.response?.data?.detail || e.message || "Gagal reklasifikasi suspense.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="text-[12px] text-[#8E8E93] py-6 text-center" data-testid="suspense-loading">Memuat saldo suspense…</p>;

  return (
    <div data-testid="suspense-panel">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="suspense-error" />

      {/* Banner saldo */}
      <div className={`mb-3 rounded-md border text-[12px] px-3 py-2.5 flex items-center gap-2 ${isZero ? "bg-[#E6F6EC] border-[#BDE5CC] text-[#1B7F4B]" : "bg-[#FDF3E7] border-[#F0D9B8] text-[#B9770E]"}`} data-testid="suspense-banner">
        {isZero ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
        <div>
          <span className="font-bold">Akun Suspense (1-9999): </span>
          <span data-testid="suspense-balance" className="tabular-nums font-bold">{formatCurrency(balance)}</span>
          <span className="ml-2 text-[11px] opacity-80">
            {isZero ? "Sudah nol — aman untuk tutup buku." : "Belum nol — reklasifikasi ke akun yang benar sebelum tutup buku."}
          </span>
        </div>
        <button data-testid="suspense-refresh" className="icon-button ml-auto" onClick={load} aria-label="Refresh"><RefreshCw size={13} /></button>
      </div>

      {/* Form reklasifikasi */}
      {!isZero && (
        <div className="rounded-lg border border-[#EFF0F2] p-3 mb-4 bg-[#FCFCFD]" data-testid="suspense-reclass-form">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[#8E8E93] mb-2 flex items-center gap-1"><ArrowLeftRight size={13} /> Reklasifikasi Saldo Suspense</p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <Field label="Entitas (PT)">
              <KNSelect data-testid="suspense-entity" className="field py-1.5 text-[12px]" value={form.entity_id}
                onValueChange={(v) => setF("entity_id", v)} placeholder="Pilih PT" options={entityOptions} />
            </Field>
            <Field label="Posisi Saldo">
              <KNSelect data-testid="suspense-side" className="field py-1.5 text-[12px]" value={form.side}
                onValueChange={(v) => setF("side", v)}
                options={[{ value: "credit", label: "Kredit (mis. kas masuk tak dikenal)" }, { value: "debit", label: "Debit (mis. kas keluar tak dikenal)" }]} />
            </Field>
            <Field label="Nominal">
              <input data-testid="suspense-amount" type="number" min="0" className="field py-1.5 text-[12px] w-full" value={form.amount}
                onChange={(e) => setF("amount", e.target.value)} placeholder="0" />
            </Field>
            <Field label="Akun Tujuan">
              <KNSelect data-testid="suspense-target" className="field py-1.5 text-[12px]" value={form.target_account}
                onValueChange={(v) => setF("target_account", v)} placeholder="Pilih akun" options={targetOptions} />
            </Field>
            <Field label="Catatan" className="md:col-span-2">
              <input data-testid="suspense-note" className="field py-1.5 text-[12px] w-full" value={form.note}
                onChange={(e) => setF("note", e.target.value)} placeholder="mis. Pelunasan piutang pelanggan X" />
            </Field>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button data-testid="suspense-submit" onClick={submit} disabled={busy}
              className="btn-primary text-[12px] py-1.5 px-4 inline-flex items-center gap-1">
              <ArrowLeftRight size={13} /> {busy ? "Memproses…" : "Reklasifikasi"}
            </button>
            <span className="text-[11px] text-[#9A9BA3]">
              {form.side === "credit" ? "Jurnal: Dr Suspense / Cr Akun Tujuan" : "Jurnal: Dr Akun Tujuan / Cr Suspense"}
            </span>
          </div>
        </div>
      )}

      {/* Daftar jurnal menyentuh suspense */}
      <p className="text-[11px] font-bold uppercase tracking-wide text-[#8E8E93] mb-2">
        Jurnal Menyentuh Suspense ({report?.entry_count || 0})
      </p>
      {(report?.items || []).length === 0 ? (
        <div data-testid="suspense-empty" className="py-8 text-center text-[12px] text-[#8E8E93]">Tidak ada jurnal yang menyentuh akun suspense.</div>
      ) : (
        <div className="overflow-auto rounded-md border border-[#EFF0F2]">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                <th className="px-3 py-2">No</th>
                <th className="px-3 py-2">Tanggal</th>
                <th className="px-3 py-2">Keterangan</th>
                <th className="px-3 py-2 text-right">Debit</th>
                <th className="px-3 py-2 text-right">Kredit</th>
              </tr>
            </thead>
            <tbody>
              {report.items.map((it) => (
                <tr key={it.id} data-testid={`suspense-row-${it.id}`} className="border-b border-[#F5F5F7] last:border-0">
                  <td className="px-3 py-2 font-mono text-[11px] font-semibold text-[#3C3C43]">{it.number}</td>
                  <td className="px-3 py-2 text-[#3C3C43]">{fmtDate(it.date)}</td>
                  <td className="px-3 py-2 text-[#1C1C1E] max-w-[320px] truncate">{it.description}{it.source_label ? <span className="ml-1 text-[10px] text-[#9A9BA3]">· {it.source_label}</span> : null}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{it.suspense_debit > 0 ? formatCurrency(it.suspense_debit) : "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{it.suspense_credit > 0 ? formatCurrency(it.suspense_credit) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[10.5px] text-[#8E8E93] mt-2">Akun Suspense (1-9999) menampung transaksi yang belum jelas alokasinya (mis. kas masuk tanpa identitas). Reklasifikasikan ke akun yang benar agar Laba-Rugi & Neraca akurat sebelum tutup buku.</p>
    </div>
  );
}

function Field({ label, children, className = "" }) {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</span>
      {children}
    </div>
  );
}
