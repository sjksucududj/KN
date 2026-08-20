/**
 * FASE G-8 — ReconRulesPanel: aturan pencocokan yang DIPELAJARI sistem dari kebiasaan
 * Anda, tetapi baru berlaku setelah DISETUJUI manusia.
 *
 * Prinsip: tidak ada aturan yang aktif sendiri. Sistem hanya menawarkan setelah pola
 * yang sama dicocokkan manual beberapa kali (ambangnya diatur di Pusat Pengaturan).
 */
import { useState } from "react";
import { Sparkles, Check, X, PauseCircle, RefreshCw } from "lucide-react";
import axios, { API } from "../../../services/apiClient";

const STATUS = {
  suggested: ["bg-[#FFF4E5] text-[#B26A00]", "Menunggu persetujuan"],
  active: ["bg-[#EAF7EE] text-[#1B7F4B]", "Aktif"],
  rejected: ["bg-[#F0F0F2] text-[#8E8E93]", "Ditolak"],
};

export default function ReconRulesPanel({ rules, onReload, onError, onNotify }) {
  const [busy, setBusy] = useState("");

  async function decide(rule, action, label) {
    setBusy(rule.id + action);
    try {
      await axios.post(`${API}/bank-reconciliation/rules/${rule.id}/decide`, { action });
      onNotify(`Aturan “${rule.counterparty || rule.desc_key}” ${label}.`);
      await onReload();
    } catch (e) { onError(e); } finally { setBusy(""); }
  }

  return (
    <div data-testid="recon-rules-panel">
      <div className="mb-3 rounded-lg border border-[#E5E5EA] bg-[#FAFBFC] px-3 py-2 text-[12px] text-[#1C1C1E]">
        <Sparkles size={13} className="inline mr-1 text-[#0058CC]" />
        Bila Anda mencocokkan pola berita transfer yang sama beberapa kali, sistem menawarkan
        aturan. Setelah <b>Anda setujui</b>, mutasi berikutnya dari pola itu mendapat tambahan
        poin sehingga bisa tercocok otomatis. Sistem tidak pernah mengaktifkan aturan sendiri.
      </div>

      <div className="rounded-lg border border-[#E5E5EA] overflow-hidden" data-testid="recon-rules-table">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
              <th className="px-3 py-2">Pola berita transfer</th>
              <th className="px-3 py-2">Pihak</th>
              <th className="px-3 py-2">Arah</th>
              <th className="px-3 py-2 text-right">Kali dicocokkan</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2 text-right">Tindakan</th>
            </tr>
          </thead>
          <tbody>
            {(rules || []).length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-[#8E8E93]">
                  Belum ada aturan. Aturan muncul sendiri setelah Anda mencocokkan pola yang
                  sama beberapa kali secara manual.
                </td>
              </tr>
            ) : rules.map((r) => {
              const [pill, label] = STATUS[r.status] || STATUS.suggested;
              return (
                <tr key={r.id} data-testid={`recon-rule-${r.id}`}
                  className="border-b border-[#F5F5F7] last:border-0">
                  <td className="px-3 py-2 max-w-[300px]">
                    <p className="truncate" title={r.sample_desc}>{r.sample_desc || r.desc_key}</p>
                    <p className="text-[10px] text-[#8E8E93] truncate">Kunci: {r.desc_key}</p>
                  </td>
                  <td className="px-3 py-2">{r.counterparty || "—"}</td>
                  <td className="px-3 py-2">{r.direction === "in" ? "Masuk" : "Keluar"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.hits || 0}×</td>
                  <td className="px-3 py-2">
                    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${pill}`}
                      data-testid={`recon-rule-status-${r.id}`}>{label}</span>
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <div className="flex justify-end gap-2 flex-wrap">
                      {r.status !== "active" && (
                        <button data-testid={`recon-rule-activate-${r.id}`} className="link-button"
                          style={{ color: "#1B7F4B" }} disabled={busy === r.id + "activate"}
                          onClick={() => decide(r, "activate", "diaktifkan")}>
                          {busy === r.id + "activate"
                            ? <RefreshCw size={12} className="spin" /> : <Check size={12} />} Setujui
                        </button>
                      )}
                      {r.status === "active" && (
                        <button data-testid={`recon-rule-suspend-${r.id}`} className="link-button"
                          style={{ color: "#B26A00" }} disabled={busy === r.id + "suspend"}
                          onClick={() => decide(r, "suspend", "ditangguhkan")}>
                          <PauseCircle size={12} /> Tangguhkan
                        </button>
                      )}
                      {r.status !== "rejected" && (
                        <button data-testid={`recon-rule-reject-${r.id}`} className="link-button"
                          style={{ color: "#B4231F" }} disabled={busy === r.id + "reject"}
                          onClick={() => decide(r, "reject", "ditolak")}>
                          <X size={12} /> Tolak
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
