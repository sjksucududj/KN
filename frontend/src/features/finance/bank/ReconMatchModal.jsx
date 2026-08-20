/**
 * FASE G-8 — ReconMatchModal: kandidat transaksi buku BERPERINGKAT + alasan skor,
 * dengan dua mode: cocok satu-satu (1:1) atau **pecah** satu transfer ke beberapa
 * transaksi buku (1:N).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link2, X, RefreshCw, Split, Info } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { formatCurrency } from "../../../utils/formatters";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import ErrorNotice from "../../../components/ErrorNotice";
import { apiErrorText } from "../../../utils/apiError";

const fmtDate = (s) => {
  if (!s) return "—";
  try {
    return new Date(String(s).length <= 10 ? `${s}T00:00:00` : s)
      .toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return s; }
};

export default function ReconMatchModal({ line, onClose, onDone, onError }) {
  const [data, setData] = useState(null);
  const [mode, setMode] = useState("single");        // single | split
  const [alloc, setAlloc] = useState({});            // txn_id -> nominal
  const [busy, setBusy] = useState("");
  // INV-UI-03 — modal WAJIB menampilkan penolakannya sendiri: bilah error layar
  // induk berada di belakang lapisan modal ini, jadi tak terlihat pengguna.
  const [mErr, setMErr] = useState("");

  const load = useCallback(async () => {
    setBusy("load");
    try {
      const r = await axios.get(`${API}/bank-reconciliation/lines/${line.id}/candidates`,
        { params: { limit: 25 } });
      setData(r.data);
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); } finally { setBusy(""); }
  }, [line.id, onError]);

  useEffect(() => { load(); }, [load]);

  const allocTotal = useMemo(
    () => Object.values(alloc).reduce((a, v) => a + (Number(v) || 0), 0), [alloc]);
  const remaining = Number(line.amount || 0) - allocTotal;
  const allocCount = useMemo(
    () => Object.values(alloc).filter((v) => Number(v) > 0).length, [alloc]);

  async function doSingle(txnId, score) {
    setBusy(txnId);
    try {
      await axios.post(`${API}/bank-reconciliation/lines/${line.id}/match`, { txn_id: txnId });
      onDone(`Mutasi ditautkan${score ? ` (skor ${Number(score).toFixed(0)})` : ""}.`);
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); } finally { setBusy(""); }
  }

  async function doSplit() {
    const allocations = Object.entries(alloc)
      .filter(([, v]) => Number(v) > 0)
      .map(([txn_id, v]) => ({ txn_id, amount: Number(v) }));
    setBusy("split");
    try {
      const r = await axios.post(`${API}/bank-reconciliation/lines/${line.id}/match-split`,
        { allocations });
      onDone(`Satu transfer dipecah ke ${allocations.length} transaksi buku `
        + `(${formatCurrency(r.data.allocated_total)}).`);
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); } finally { setBusy(""); }
  }

  const cands = data?.candidates || [];

  return (
    <div className="modal-overlay" data-testid="recon-match-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card max-w-[720px]">
        <div className="flex items-center justify-between mb-2">
          <h3 className="modal-title flex items-center gap-1.5">
            <Link2 size={15} /> Cocokkan mutasi bank
          </h3>
          <button className="icon-button" data-testid="recon-match-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        {mErr && (
          <ErrorNotice message={mErr} onDismiss={() => setMErr("")}
            testId="recon-match-error" />
        )}
        <p className="modal-subtitle">
          {fmtDate(line.stmt_date)} · {line.direction === "in" ? "Masuk" : "Keluar"}{" "}
          <b>{formatCurrency(line.amount)}</b> — {line.description || "tanpa keterangan"}
        </p>
        {data && (
          <p className="text-[11px] text-[#8E8E93] mt-1">
            Ambang otomatis {Number(data.auto_min).toFixed(0)} · ambang usulan{" "}
            {Number(data.suggest_min).toFixed(0)}
            {data.rule_applied ? " · aturan tersimpan ikut menambah poin" : ""}
          </p>
        )}

        <div className="mt-2 flex gap-2">
          <button data-testid="recon-mode-single"
            className={mode === "single" ? "primary-button" : "secondary-button"}
            onClick={() => setMode("single")}>Satu transaksi</button>
          <button data-testid="recon-mode-split"
            className={mode === "split" ? "primary-button" : "secondary-button"}
            onClick={() => setMode("split")}>
            <Split size={14} /> Pecah ke beberapa transaksi
          </button>
        </div>

        {mode === "split" && (
          <div className="mt-2 rounded border border-[#CBDCF7] bg-[#F2F7FF] px-3 py-2 text-[11px]"
            data-testid="recon-split-info">
            Isi nominal pada transaksi yang dilunasi transfer ini. Total alokasi tidak boleh
            melebihi nominal mutasi. Sisa belum dialokasikan:{" "}
            <b className={remaining < -0.01 ? "text-[#C0392B]" : "text-[#1B7F4B]"}>
              {formatCurrency(remaining)}
            </b>
          </div>
        )}

        <div className="mt-2 max-h-[340px] overflow-auto rounded border border-[#EFF0F2]">
          {busy === "load" ? (
            <div className="p-4 text-center text-[12px] text-[#8E8E93]">
              <RefreshCw size={14} className="spin inline" /> Menghitung kandidat…
            </div>
          ) : cands.length === 0 ? (
            <div className="p-4 text-center text-[12px] text-[#8E8E93]">
              Tidak ada transaksi buku yang layak (arah dana, nominal, atau tanggalnya terlalu jauh).
              Anda bisa menitipkan dana ini bila pengirimnya belum diketahui.
            </div>
          ) : cands.map((t) => (
            <div key={t.id} data-testid={`recon-cand-${t.id}`}
              className="px-3 py-2 border-b border-[#F5F5F7] last:border-0">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[12px] truncate">
                    <b>{t.number}</b> · {fmtDate(t.txn_date)}{" "}
                    <span className="text-[#8E8E93]">{t.description || ""}</span>
                  </p>
                  <p className="text-[10px] text-[#8E8E93]">
                    Nominal {formatCurrency(t.amount)} · sisa {formatCurrency(t.outstanding)}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                    t.score >= (data?.auto_min || 80) ? "bg-[#EAF7EE] text-[#1B7F4B]"
                      : t.score >= (data?.suggest_min || 60) ? "bg-[#FFF4E5] text-[#B26A00]"
                        : "bg-[#F0F0F2] text-[#8E8E93]"}`}>
                    skor {Number(t.score).toFixed(0)}
                  </span>
                  {mode === "single" ? (
                    <button data-testid={`recon-pick-cand-${t.id}`} className="primary-button"
                      disabled={busy === t.id} onClick={() => doSingle(t.id, t.score)}>
                      Tautkan
                    </button>
                  ) : (
                    <input data-testid={`recon-alloc-${t.id}`} type="number" min={0}
                      max={Number(t.outstanding)} step={1000} className="input-field w-[140px]"
                      placeholder="Nominal"
                      value={alloc[t.id] ?? ""}
                      onChange={(e) => setAlloc((cur) => ({ ...cur, [t.id]: e.target.value }))} />
                  )}
                </div>
              </div>
              {(t.explain || []).length > 0 && (
                <p className="mt-1 flex items-start gap-1 text-[10px] text-[#6B6B73]">
                  <Info size={10} className="mt-0.5 shrink-0" />
                  {(t.explain || []).map((e) => `${e.label} (+${Number(e.points).toFixed(0)})`)
                    .join(" · ")}
                </p>
              )}
            </div>
          ))}
        </div>

        {mode === "split" && (
          <div className="flex justify-end gap-2 mt-3">
            <button className="secondary-button" onClick={onClose}>Batal</button>
            <button data-testid="recon-split-submit" className="primary-button"
              disabled={allocCount < 2 || remaining < -0.01 || busy === "split"}
              onClick={doSplit}>
              {busy === "split" ? <RefreshCw size={14} className="spin" /> : <Split size={14} />}
              Simpan pemecahan ({allocCount} transaksi)
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
