/**
 * InventoryReconTab (Gelombang 1 F-3) — rekonsiliasi GL Persediaan (1-1300) vs nilai
 * fisik roll (subledger) per entitas + posting saldo awal / true-up.
 * Diekstrak dari GeneralLedger.jsx (jaga batas ukuran file). Sumber: /api/gl/*.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatCurrency } from "../../utils/formatters";
import { askReason } from "@/services/confirmService";

export default function InventoryReconTab({ refreshKey, onError, onNotice, onChanged }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [posting, setPosting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/gl/inventory-reconciliation`);
      setData(res.data);
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal memuat rekonsiliasi persediaan.");
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const postOpening = async () => {
    // Berdampak UANG + STOK: menerbitkan jurnal true-up terhadap ekuitas saldo awal.
    const reason = await askReason({
      title: "Posting saldo awal / true-up persediaan?",
      message: "GL Persediaan (1-1300) akan disamakan dengan nilai fisik roll per badan usaha, "
        + "dengan lawan akun 3-2900 Ekuitas Saldo Awal. Jurnalnya nyata dan masuk buku besar.",
      reasonLabel: "Alasan / dasar penyesuaian",
      reasonPlaceholder: "Contoh: hasil stock opname 31 Juli, selisih 12 roll grade B",
      confirmLabel: "Posting True-Up",
      testId: "recon-post-confirm",
    });
    if (reason === null) return;
    setPosting(true);
    try {
      const res = await axios.post(`${API}/gl/inventory-opening-balance`, null, { params: { reason } });
      const n = res.data?.count || 0;
      onNotice(n > 0 ? `Saldo awal diposting: ${n} jurnal (${(res.data.posted || []).map((p) => p.journal_number).join(", ")}).` : "Tidak ada selisih — GL sudah sinkron dengan subledger.");
      await load();
      onChanged();
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal posting saldo awal persediaan.");
    } finally {
      setPosting(false);
    }
  };

  const totalDiff = Math.abs(data?.total_difference || 0);
  if (loading) return <p className="text-[12px] text-[#8E8E93] py-6 text-center" data-testid="recon-loading">Memuat rekonsiliasi…</p>;

  return (
    <div data-testid="inventory-recon-tab">
      <div className={`mb-3 rounded-md border text-[12px] px-3 py-2 flex items-center gap-2 ${totalDiff > 0.01 ? "bg-[#FDF3E7] border-[#F0D9B8] text-[#B9770E]" : "bg-[#E6F6EC] border-[#BDE5CC] text-[#1B7F4B]"}`} data-testid="recon-status-banner">
        {totalDiff > 0.01 ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
        {totalDiff > 0.01
          ? `Selisih total GL vs fisik: ${formatCurrency(data?.total_difference)} — posting saldo awal / telusuri penyebabnya.`
          : "GL Persediaan sinkron dengan subledger roll."}
        <button data-testid="recon-post-opening" className="btn-primary text-[12px] py-1 px-3 ml-auto" onClick={postOpening} disabled={posting || totalDiff <= 0.01}>
          {posting ? "Memposting…" : "Posting Saldo Awal"}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93] border-b border-[#EFF0F2]">
              <th className="py-2 pr-3">Entitas</th>
              <th className="py-2 pr-3 text-right">Nilai Fisik (Roll × HPP)</th>
              <th className="py-2 pr-3 text-right">Saldo GL 1-1300</th>
              <th className="py-2 pr-3 text-right">Selisih</th>
            </tr>
          </thead>
          <tbody>
            {(data?.rows || []).map((r) => (
              <tr key={r.entity_id} className="border-b border-[#F6F6F8]" data-testid={`recon-row-${r.entity_id}`}>
                <td className="py-2 pr-3 font-semibold">{r.entity_name}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{formatCurrency(r.subledger_value)}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{formatCurrency(r.gl_balance)}</td>
                <td className={`py-2 pr-3 text-right tabular-nums font-bold ${Math.abs(r.difference) > 0.01 ? "text-[#C0392B]" : "text-[#1B7F4B]"}`} data-testid={`recon-diff-${r.entity_id}`}>{formatCurrency(r.difference)}</td>
              </tr>
            ))}
            {(data?.rows || []).length === 0 && (
              <tr><td colSpan={4} className="py-6 text-center text-[#8E8E93]" data-testid="recon-empty">Belum ada entitas untuk direkonsiliasi.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-[10.5px] text-[#8E8E93] mt-2">Nilai fisik = Σ (sisa panjang roll × HPP/unit) status available/reserved/committed/picked/packed/quarantine/hold. Penerimaan barang (GR) baru otomatis berjurnal Dr Persediaan / Cr GR-IR — selisih historis diselesaikan lewat Posting Saldo Awal.</p>
    </div>
  );
}
