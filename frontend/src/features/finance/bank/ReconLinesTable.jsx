/**
 * FASE G-8 — ReconLinesTable: daftar mutasi bank dengan SKOR + ALASANNYA, usulan
 * 1-klik, gabung N:1 (beberapa mutasi → satu transaksi buku), titipan dana, dan
 * abaikan/lepas.
 *
 * Prinsip layar ini: pengguna harus tahu KENAPA sistem menganggap sesuatu cocok.
 * Karena itu skor selalu ditampilkan bersama daftar alasan berpoin.
 */
import { useMemo, useState } from "react";
import {
  Link2, Unlink, EyeOff, Eye, ArrowDownLeft, ArrowUpRight, PiggyBank, Info, Layers, X,
  Receipt, Percent,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { formatCurrency } from "../../../utils/formatters";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import ErrorNotice from "../../../components/ErrorNotice";
import { apiErrorText } from "../../../utils/apiError";
import ReconContraBonModal from "./ReconContraBonModal";

const fmtDate = (s) => {
  if (!s) return "—";
  try {
    return new Date(String(s).length <= 10 ? `${s}T00:00:00` : s)
      .toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return s; }
};

const STATUS_PILL = {
  unmatched: ["bg-[#FFF4E5] text-[#B26A00]", "Perlu keputusan"],
  matched: ["bg-[#EAF7EE] text-[#1B7F4B]", "Tercocok"],
  ignored: ["bg-[#F0F0F2] text-[#8E8E93]", "Diabaikan"],
  holding: ["bg-[#E8F1FF] text-[#0058CC]", "Dititipkan"],
};

const KIND_LABEL = { "1:1": "satu-satu", "1:N": "1 transfer → banyak", "N:1": "banyak → 1" };
function ScoreBadge({ score, explain, testId }) {
  const [open, setOpen] = useState(false);
  const s = Number(score || 0);
  const tone = s >= 80 ? "bg-[#EAF7EE] text-[#1B7F4B]"
    : s >= 60 ? "bg-[#FFF4E5] text-[#B26A00]" : "bg-[#F0F0F2] text-[#8E8E93]";
  return (
    <div className="relative">
      <button type="button" data-testid={testId} onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold ${tone}`}>
        {s ? s.toFixed(0) : "—"} <Info size={10} />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-[260px] rounded-lg border border-[#E5E5EA] bg-white p-2 shadow-lg"
          data-testid={`${testId}-explain`}>
          <p className="text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Alasan skor</p>
          {(explain || []).length === 0 ? (
            <p className="text-[11px] text-[#8E8E93]">Belum dihitung — tekan “Cocokkan otomatis”.</p>
          ) : (explain || []).map((e, i) => (
            <div key={i} className="flex items-start justify-between gap-2 text-[11px] py-0.5">
              <span className="text-[#1C1C1E]">{e.label}</span>
              <span className="font-semibold text-[#0058CC] tabular-nums">
                +{Number(e.points || 0).toFixed(0)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ReconLinesTable({ lines, busy, onAction, onOpenMatch, onReload,
  onError, onNotify }) {
  const [picked, setPicked] = useState([]);
  const [groupTxn, setGroupTxn] = useState(null);   // { candidates, total }
  // FASE G-7 US8 — baris dana KELUAR bisa langsung melunasi satu kontrabon.
  const [cbLine, setCbLine] = useState(null);
  // INV-UI-03 — modal WAJIB menampilkan penolakannya sendiri: bilah error layar
  // induk berada di belakang lapisan modal ini, jadi tak terlihat pengguna.
  const [mErr, setMErr] = useState("");

  const selectable = useMemo(
    () => (lines || []).filter((l) => l.status === "unmatched"), [lines]);
  const pickedLines = useMemo(
    () => selectable.filter((l) => picked.includes(l.id)), [selectable, picked]);
  const pickedTotal = useMemo(
    () => pickedLines.reduce((a, l) => a + Number(l.amount || 0), 0), [pickedLines]);

  function toggle(id) {
    setPicked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }

  async function openGroup() {
    try {
      const first = pickedLines[0];
      const r = await axios.get(`${API}/bank-reconciliation/lines/${first.id}/candidates`,
        { params: { limit: 25 } });
      setGroupTxn({ candidates: r.data?.candidates || [], total: pickedTotal });
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); }
  }

  async function doGroup(txnId) {
    try {
      const r = await axios.post(`${API}/bank-reconciliation/match-group`,
        { line_ids: pickedLines.map((l) => l.id), txn_id: txnId });
      onNotify(`${r.data.lines} mutasi digabung ke transaksi ${r.data.txn_number} `
        + `(${formatCurrency(r.data.allocated_total)}).`);
      setPicked([]); setGroupTxn(null);
      await onReload();
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); }
  }

  async function acceptSuggestion(line, sug) {
    await onAction(line.id, "match", { txn_id: sug.id },
      `Mutasi ditautkan ke ${sug.number} (skor ${Number(sug.score).toFixed(0)}).`);
  }

  return (
    <>
      {pickedLines.length >= 2 && (
        <div className="mb-2 flex items-center justify-between gap-3 rounded-lg border border-[#CBDCF7] bg-[#F2F7FF] px-3 py-2"
          data-testid="recon-group-bar">
          <span className="text-[12px] text-[#1C1C1E]">
            <b>{pickedLines.length} mutasi</b> dipilih · total{" "}
            <b>{formatCurrency(pickedTotal)}</b> — bisa digabung ke SATU transaksi buku.
          </span>
          <div className="flex gap-2">
            <button className="secondary-button" data-testid="recon-group-clear"
              onClick={() => setPicked([])}>Bersihkan</button>
            <button className="primary-button" data-testid="recon-group-open" onClick={openGroup}>
              <Layers size={14} /> Gabung ke 1 transaksi
            </button>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-[#E5E5EA] overflow-hidden" data-testid="recon-lines-table">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
              <th className="px-2 py-2 w-8"> </th>
              <th className="px-3 py-2">Tanggal</th>
              <th className="px-3 py-2">Keterangan</th>
              <th className="px-3 py-2 text-right">Nominal</th>
              <th className="px-3 py-2">Skor</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Transaksi buku</th>
              <th className="px-3 py-2 text-right">Tindakan</th>
            </tr>
          </thead>
          <tbody>
            {(lines || []).length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-[#8E8E93]">
                  Belum ada mutasi untuk akun ini. Tekan “Impor mutasi bank” untuk menempel
                  atau mengunggah rekening koran.
                </td>
              </tr>
            ) : lines.map((l) => {
              const [pill, plabel] = STATUS_PILL[l.status] || STATUS_PILL.unmatched;
              const sugs = l.suggestions || [];
              return (
                <tr key={l.id} data-testid={`recon-line-${l.id}`}
                  className="border-b border-[#F5F5F7] last:border-0 align-top">
                  <td className="px-2 py-2">
                    {l.status === "unmatched" && (
                      <input type="checkbox" data-testid={`recon-pick-${l.id}`}
                        checked={picked.includes(l.id)} onChange={() => toggle(l.id)} />
                    )}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{fmtDate(l.stmt_date)}</td>
                  <td className="px-3 py-2 max-w-[260px]">
                    <p className="truncate" title={l.description}>{l.description || "—"}</p>
                    {l.counterparty && (
                      <p className="text-[10px] text-[#8E8E93] truncate">Pihak: {l.counterparty}</p>
                    )}
                    {l.ref && <p className="text-[10px] text-[#0058CC]">Referensi: {l.ref}</p>}
                    {sugs.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1" data-testid={`recon-suggestions-${l.id}`}>
                        {sugs.map((s) => (
                          <button key={s.id} data-testid={`recon-accept-${l.id}-${s.id}`}
                            className="rounded border border-[#CBDCF7] bg-[#F2F7FF] px-1.5 py-0.5 text-[10px] text-[#0058CC] hover:bg-[#E4EEFC]"
                            disabled={busy === l.id + "match"}
                            onClick={() => acceptSuggestion(l, s)}>
                            Terima usulan: {s.number} · {formatCurrency(s.amount)} (skor{" "}
                            {Number(s.score).toFixed(0)})
                          </button>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums whitespace-nowrap">
                    <span className={`inline-flex items-center gap-1 ${
                      l.direction === "in" ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}>
                      {l.direction === "in" ? <ArrowDownLeft size={12} /> : <ArrowUpRight size={12} />}
                      {formatCurrency(l.amount)}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <ScoreBadge score={l.score} explain={l.score_explain}
                      testId={`recon-score-${l.id}`} />
                  </td>
                  <td className="px-3 py-2">
                    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${pill}`}
                      data-testid={`recon-status-${l.id}`}>{plabel}</span>
                    {l.match_kind && (
                      <p className="mt-0.5 text-[10px] text-[#8E8E93]">
                        {l.match_type === "charge"
                          ? `${l.charge?.label || "Biaya bank"} · akun ${l.charge?.account_code || ""}`
                          : `${KIND_LABEL[l.match_kind] || l.match_kind}${
                            l.match_type === "auto" ? " · otomatis" : ""}`}
                      </p>
                    )}
                    {l.status === "holding" && (
                      <p className="mt-0.5 text-[10px] text-[#0058CC]">
                        Sisa {formatCurrency(l.holding_remaining || 0)}
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-2 text-[11px]">
                    {(l.matched_txns || []).length > 0 ? (l.matched_txns || []).map((t) => (
                      <p key={t.id} className="text-[#1B7F4B]">
                        {t.number} · {formatCurrency(t.allocated)}
                      </p>
                    )) : l.status === "holding" ? (
                      <p className="text-[#0058CC]">{l.holding?.cash_number || "titipan"}</p>
                    ) : <span className="text-[#C7C7CC]">—</span>}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {l.status === "matched" && (
                      <button data-testid={`recon-unmatch-${l.id}`} className="link-button"
                        style={{ color: "#B4231F" }} disabled={busy === l.id + "unmatch"}
                        onClick={() => onAction(l.id, "unmatch", {}, "Tautan dilepas.")}>
                        <Unlink size={12} /> Lepas
                      </button>
                    )}
                    {l.status === "ignored" && (
                      <button data-testid={`recon-unignore-${l.id}`} className="link-button"
                        disabled={busy === l.id + "unignore"}
                        onClick={() => onAction(l.id, "unignore", {}, "Baris dikembalikan ke antrean.")}>
                        <Eye size={12} /> Batal abaikan
                      </button>
                    )}
                    {l.status === "unmatched" && (
                      <div className="flex items-center gap-2 justify-end flex-wrap">
                        <button data-testid={`recon-matchbtn-${l.id}`} className="link-button"
                          onClick={() => onOpenMatch(l)}>
                          <Link2 size={12} /> Cocokkan
                        </button>
                        {l.direction === "in" && (
                          <button data-testid={`recon-holding-${l.id}`} className="link-button"
                            style={{ color: "#0058CC" }} disabled={busy === l.id + "holding"}
                            onClick={() => onAction(l.id, "holding", { note: "" },
                              "Dana dititipkan (jurnal Dr Bank / Cr Titipan terbit).")}>
                            <PiggyBank size={12} /> Titipkan
                          </button>
                        )}
                        {/* Baris yang MEMANG tidak ada di buku: biaya adm bank & bunga/jasa
                            giro. Tanpa jalur ini satu-satunya pilihan adalah "Abaikan",
                            sehingga bebannya hilang dari laba rugi dan selisih rekening vs
                            buku tidak pernah bisa nol. */}
                        {l.direction === "out" ? (
                          <>
                            <button data-testid={`recon-charge-${l.id}`} className="link-button"
                              style={{ color: "#B26A00" }} disabled={busy === l.id + "book-charge"}
                              onClick={() => onAction(l.id, "book-charge", { kind: "charge" },
                                "Biaya bank dibukukan (Dr Beban Adm Bank / Cr Bank).")}>
                              <Receipt size={12} /> Catat biaya bank
                            </button>
                            {/* FASE G-7 US8 — uang keluar untuk siklus tukar faktur supplier:
                                tunjuk kontrabonnya, sistem membuat kas + menautkan barisnya. */}
                            <button data-testid={`recon-contrabon-${l.id}`} className="link-button"
                              style={{ color: "#6B219A" }} onClick={() => setCbLine(l)}>
                              <Receipt size={12} /> Bayar kontrabon
                            </button>
                          </>
                        ) : (
                          <button data-testid={`recon-interest-${l.id}`} className="link-button"
                            style={{ color: "#1B7F4B" }} disabled={busy === l.id + "book-charge"}
                            onClick={() => onAction(l.id, "book-charge", { kind: "interest" },
                              "Bunga · jasa giro dibukukan (Dr Bank / Cr Pendapatan Bunga).")}>
                            <Percent size={12} /> Catat bunga bank
                          </button>
                        )}
                        <button data-testid={`recon-ignore-${l.id}`} className="link-button"
                          style={{ color: "#8E8E93" }} disabled={busy === l.id + "ignore"}
                          onClick={() => onAction(l.id, "ignore", { note: "" }, "Baris diabaikan.")}>
                          <EyeOff size={12} /> Abaikan
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {groupTxn && (
        <div className="modal-overlay" data-testid="recon-group-modal"
          {...overlayDismiss(() => setGroupTxn(null))}>
          <div className="modal-card">
            <div className="flex items-center justify-between mb-2">
              <h3 className="modal-title flex items-center gap-1.5">
                <Layers size={15} /> Gabung {pickedLines.length} mutasi ke satu transaksi buku
              </h3>
              <button className="icon-button" data-testid="recon-group-close"
                onClick={() => setGroupTxn(null)}><X size={15} /></button>
            </div>
            {mErr && (
              <ErrorNotice message={mErr} onDismiss={() => setMErr("")}
                testId="recon-group-error" />
            )}
            <p className="modal-subtitle">
              Total mutasi terpilih <b>{formatCurrency(groupTxn.total)}</b> — pilih transaksi buku
              yang nilainya mencukupi.
            </p>
            <div className="mt-2 max-h-[320px] overflow-auto rounded border border-[#EFF0F2]">
              {groupTxn.candidates.length === 0 ? (
                <div className="p-4 text-center text-[12px] text-[#8E8E93]">
                  Tidak ada transaksi buku yang cocok arah & rentang tanggalnya.
                </div>
              ) : groupTxn.candidates.map((t) => (
                <button key={t.id} data-testid={`recon-group-cand-${t.id}`}
                  className="w-full text-left px-3 py-2 border-b border-[#F5F5F7] hover:bg-[#F7F8FA] flex items-center justify-between"
                  disabled={Number(t.outstanding) + 0.01 < groupTxn.total}
                  onClick={() => doGroup(t.id)}>
                  <span className="text-[12px]">
                    <b>{t.number}</b> · {fmtDate(t.txn_date)}{" "}
                    <span className="text-[#8E8E93]">{t.description || ""}</span>
                  </span>
                  <span className="text-[12px] font-semibold">
                    sisa {formatCurrency(t.outstanding)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
      {cbLine && (
        <ReconContraBonModal line={cbLine} onClose={() => setCbLine(null)}
          onDone={(note) => { setCbLine(null); onNotify(note); onReload?.(); }}
          onError={onError} />
      )}
    </>
  );
}
