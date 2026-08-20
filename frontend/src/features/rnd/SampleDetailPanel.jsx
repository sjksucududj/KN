/**
 * SampleDetailPanel (FASE F · PS-18/PS-19) — pusat kerja SATU permintaan sample.
 *
 * Semua yang dibutuhkan pelaksana ada di satu tempat, dengan urutan kerja nyata:
 *   1. kirim permintaan ke ≥1 supplier (bisa dibandingkan),
 *   2. unggah bukti + setor hasil per round (`rnd 1 → n`),
 *   3. nilai hasil (acc / revisi / tolak) + skor,
 *   4. buka round berikutnya bila revisi,
 *   5. pilih PEMENANG → kontrak harga + barang supplier terbentuk (Fase E),
 *   6. ambil bahan dari roll → stok gudang benar-benar berkurang (PS-19).
 */
import { useCallback, useEffect, useState } from "react";
import { Ban, Beaker, GitBranch, PackageMinus, Send, Trophy, X } from "lucide-react";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { openTrace } from "../documents/trace/traceDeepLink";
import DecideModal from "./DecideModal";
import IssueMaterialModal from "./IssueMaterialModal";
import RoundActionModal from "./RoundActionModal";
import SampleRoundList from "./SampleRoundList";
import SampleSendModal from "./SampleSendModal";
import {
  assessRound, cancelSample, decideSample, getSample, issueMaterial, openRound,
  rndMeta, sendSample, submitRound, uploadRoundProof,
} from "./rndApi";
import { errMsg, ROUND_RESULT_META, SAMPLE_STATUS_META, SAMPLE_TYPE_LABEL } from "./rndMeta";

export default function SampleDetailPanel({ sampleId, currentUser, onClose, onChanged }) {
  const [sample, setSample] = useState(null);
  const [policy, setPolicy] = useState({});
  const [reasons, setReasons] = useState([]);
  const [err, setErr] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);   // { kind, round, participant }
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");

  const role = currentUser?.role;
  const canSubmit = ["admin", "manager", "warehouse"].includes(role);
  const canAssess = ["admin", "manager"].includes(role);
  const canDecide = ["admin", "manager"].includes(role);
  const canCancel = ["admin", "manager"].includes(role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await getSample(sampleId);
      setSample(d);
      setErr("");
    } catch (e) { setErr(errMsg(e, "Gagal memuat permintaan sample.")); }
    finally { setLoading(false); }
  }, [sampleId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    rndMeta().then((m) => { setPolicy(m?.policy || {}); setReasons(m?.reasons || []); })
      .catch(() => { /* meta opsional — layar tetap berfungsi */ });
  }, []);

  /** Jalankan satu aksi server, muat ulang, dan tampilkan pesan yang manusiawi. */
  const act = async (fn, done) => {
    setBusy(true); setErr(""); setOkMsg("");
    try {
      await fn();
      await load();
      onChanged?.();
      setModal(null);
      setCancelOpen(false);
      if (done) setOkMsg(done);
    } catch (e) {
      setErr(errMsg(e, "Aksi gagal dijalankan."));
    } finally { setBusy(false); }
  };

  const uploadProof = async (round, file) => {
    setBusy(true); setErr(""); setOkMsg("");
    try {
      await uploadRoundProof(sample.id, round.id, file);
      await load();
      setOkMsg(`Bukti "${file.name}" terunggah pada rnd ${round.round_no}.`);
    } catch (e) {
      setErr(errMsg(e, "Berkas gagal diunggah."));
    } finally { setBusy(false); }
  };

  const meta = SAMPLE_STATUS_META[sample?.status] || SAMPLE_STATUS_META.draft;
  const decided = sample?.status === "decided";
  const canSend = !!sample && ["draft", "sent", "in_progress", "assessed"].includes(sample.status);
  const hasAcc = (sample?.rounds || []).some((r) => r.result === "acc");
  const issues = sample?.material_issues || [];

  return (
    <div data-testid="sample-detail-panel"
      className="fixed inset-0 z-[168] flex items-center justify-center bg-black/50 p-4"
      {...overlayDismiss(onClose)}>
      <div className="flex max-h-[94vh] w-full max-w-[980px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        {/* ── Header ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <div className="min-w-0">
            <h2 className="flex flex-wrap items-center gap-2 text-[15px] font-bold">
              <Beaker size={16} className="text-[#0058CC]" />
              <span data-testid="sample-detail-number">{sample?.number || "…"}</span>
              <span className={`status-pill ${meta.cls}`}
                data-testid="sample-detail-status">{meta.label}</span>
              <span className="status-pill pill-muted">
                {SAMPLE_TYPE_LABEL[sample?.sample_type] || sample?.sample_type}
              </span>
            </h2>
            <p className="truncate text-[11.5px] text-[#6B6B73]">
              {sample?.title}
              {sample?.spec_number ? ` · dari ${sample.spec_number}` : ""}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button className="secondary-button !px-2 !py-1 text-[10.5px]"
              data-testid="sample-trace-button" disabled={!sample}
              title="Lihat rantai dokumen: spesifikasi → sample → kontrak → PO"
              onClick={() => {
                openTrace({ docType: "md_sample", docId: sample.id, number: sample.number });
                onClose?.();
              }}>
              <GitBranch size={12} /> Jejak dokumen
            </button>
            <button className="icon-button" onClick={onClose} data-testid="sample-detail-close">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* ── Isi ────────────────────────────────────────────────── */}
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {err && (
            <div className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]"
              data-testid="sample-detail-error">{err}</div>
          )}
          {okMsg && (
            <div className="rounded-lg bg-[#EAF7EF] px-3 py-2 text-[11.5px] text-[#1A7A3A]"
              data-testid="sample-detail-ok">{okMsg}</div>
          )}

          <div className="grid gap-2 md:grid-cols-4">
            <Box label="Warna target" testId="sample-detail-color"
              swatch={sample?.color_target?.hex}
              value={`${sample?.color_target?.name || "—"}${sample?.color_target?.code
                ? ` (${sample.color_target.code})` : ""}`} />
            <Box label="Desain / pattern" testId="sample-detail-design"
              value={sample?.design_code
                ? `${sample.design_code} v${sample.design_version || 1}` : "—"} />
            <Box label="Target selesai" value={sample?.target_date || "—"} />
            <Box label="Biaya sample" testId="sample-detail-cost"
              value={formatCurrency(sample?.cost_total || 0)} />
          </div>

          {sample?.brief && (
            <p className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2 text-[11.5px] text-[#3C3C43]"
              data-testid="sample-detail-brief">
              <b>Brief:</b> {sample.brief}
            </p>
          )}

          {/* Perbandingan supplier — inti user story "kirim ke 2 supplier lalu bandingkan" */}
          {(sample?.participants || []).length > 1 && (
            <div className="rounded-lg border border-[#EFF0F2]" data-testid="sample-compare">
              <p className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-3 py-1.5 text-[10.5px] font-bold uppercase text-[#8E8E93]">
                Perbandingan supplier
              </p>
              <div className="grid grid-cols-[1.4fr_90px_90px_1fr_110px] px-3 py-1 text-[9.5px] font-bold uppercase text-[#8E8E93]">
                <span>Supplier</span><span>Round</span><span>Skor terbaik</span>
                <span>Hasil terakhir</span><span className="text-right">Biaya round</span>
              </div>
              <div className="divide-y divide-[#F4F5F7]">
                {(sample.participants || []).map((p) => {
                  const rs = (sample.rounds || []).filter((r) => r.supplier_id === p.supplier_id);
                  const last = rs[rs.length - 1] || {};
                  const rm = ROUND_RESULT_META[last.result || ""] || ROUND_RESULT_META[""];
                  const cost = rs.reduce((a, r) => a + Number(r.cost || 0), 0);
                  return (
                    <div key={p.supplier_id}
                      data-testid={`sample-compare-row-${p.supplier_id}`}
                      className="grid grid-cols-[1.4fr_90px_90px_1fr_110px] items-center px-3 py-1.5 text-[11.5px]">
                      <span className="truncate font-semibold">{p.supplier_name}</span>
                      <span className="tabular-nums">{rs.length}</span>
                      <span className="tabular-nums font-bold">
                        {p.best_score == null ? "—" : p.best_score}
                      </span>
                      <span className="font-semibold" style={{ color: rm.tone }}>
                        {rm.label}
                        {last.measurements?.delta_e != null
                          ? ` · ΔE ${last.measurements.delta_e}` : ""}
                      </span>
                      <span className="text-right tabular-nums">{formatCurrency(cost)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Keputusan pemenang + dokumen yang lahir darinya */}
          {sample?.decision?.supplier_id && (
            <div className="rounded-lg border border-[#CDE9D6] bg-[#F4FCF6] p-3"
              data-testid="sample-decision-box">
              <p className="flex items-center gap-1.5 text-[12px] font-bold text-[#1A7A3A]">
                <Trophy size={14} /> Pemenang: {sample.decision.supplier_name}
                {sample.decision.score != null ? ` · skor ${sample.decision.score}` : ""}
              </p>
              <p className="mt-1 text-[11.5px] text-[#3C3C43]">
                Alasan: <b>{sample.decision.reason_label || sample.decision.reason_code}</b>
                {" · "}harga kesepakatan <b>{formatCurrency(sample.decision.price || 0)}</b>
                {sample.decision.note ? ` — “${sample.decision.note}”` : ""}
              </p>
              <p className="mt-1 text-[11.5px]" data-testid="sample-decision-contract">
                {sample.decision.contract_number
                  ? <>Kontrak harga terbit: <b>{sample.decision.contract_number}</b>
                    {sample.decision.supplier_item_id ? " · barang supplier terdaftar" : ""}
                    {" — cek di Pembelian → Master Pembelian."}</>
                  : "Kontrak otomatis sedang dimatikan di Pusat Pengaturan; harga perlu dibuat manual."}
              </p>
            </div>
          )}

          {/* Timeline round per supplier (komponen terpisah) */}
          <SampleRoundList sample={sample || {}} busy={busy} loading={loading && !sample}
            canSubmit={canSubmit} canAssess={canAssess}
            onUpload={uploadProof}
            onSubmit={(r) => setModal({ kind: "submit", round: r })}
            onAssess={(r) => setModal({ kind: "assess", round: r })}
            onOpenRound={(p) => setModal({ kind: "round", participant: p })} />

          {/* Pengambilan bahan (PS-19) — stok gudang, bukan stok sample kedua */}
          <div className="rounded-lg border border-[#EFF0F2]" data-testid="sample-material-box">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-3 py-1.5">
              <p className="text-[10.5px] font-bold uppercase text-[#8E8E93]">
                Bahan yang diambil dari gudang
              </p>
              {!decided && sample?.status !== "cancelled" && canSubmit && (
                <button className="secondary-button !px-2 !py-1 text-[10.5px]" disabled={busy}
                  data-testid="sample-issue-button" onClick={() => setModal({ kind: "issue" })}>
                  <PackageMinus size={12} /> Ambil bahan
                </button>
              )}
            </div>
            {issues.length === 0 ? (
              <p className="px-3 py-3 text-[11.5px] text-[#6B6B73]" data-testid="sample-no-material">
                Belum ada bahan diambil. Bila sample dibuat dari stok sendiri, ambil dari roll —
                stok gudang akan <b>berkurang nyata</b> (mutasi <b>Ambil Bahan Sample (R&D)</b>) dan
                nilainya dibebankan ke <b>6-7000 Beban Sample & Pengembangan</b>, bukan
                dicatat sebagai stok sample terpisah.
              </p>
            ) : (
              <div className="divide-y divide-[#F4F5F7]">
                {issues.map((m) => (
                  <div key={m.id} data-testid={`sample-material-row-${m.id}`}
                    className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-[11.5px]">
                    <span className="font-semibold">
                      {m.roll_no} · {m.product_name || m.product_id}
                    </span>
                    <span className="tabular-nums text-[#6B6B73]">
                      {formatQty(m.qty)} {m.unit} · {formatCurrency(m.cost || 0)}
                      {m.journal_number ? ` · jurnal ${m.journal_number}` : ""}
                      {m.note ? ` · ${m.note}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {(sample?.timeline || []).length > 0 && (
            <div className="rounded-lg border border-[#EFF0F2] p-3" data-testid="sample-timeline">
              <p className="mb-1.5 text-[10.5px] font-bold uppercase text-[#8E8E93]">Riwayat</p>
              <ul className="space-y-1">
                {sample.timeline.slice().reverse().map((t, i) => (
                  <li key={i} className="text-[11px] text-[#3C3C43]">
                    <b>{t.label}</b>
                    {t.actor ? ` · ${t.actor}` : ""}
                    {t.note ? ` — ${t.note}` : ""}
                    <span className="text-[#9A9BA3]">
                      {" · "}{String(t.at || "").slice(0, 16).replace("T", " ")}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* ── Aksi utama ─────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          {cancelOpen ? (
            <>
              <input className="field max-w-[260px]" data-testid="sample-cancel-reason"
                placeholder="Alasan pembatalan (wajib)…" value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)} />
              <button className="secondary-button" onClick={() => setCancelOpen(false)}>
                Kembali
              </button>
              <button className="danger-button" disabled={busy || cancelReason.trim().length < 3}
                data-testid="sample-cancel-confirm"
                onClick={() => act(() => cancelSample(sample.id, cancelReason),
                  "Permintaan sample dibatalkan.")}>
                <Ban size={13} /> Batalkan permintaan
              </button>
            </>
          ) : (
            <>
              {canCancel && !decided && sample?.status !== "cancelled" && (
                <button className="secondary-button" data-testid="sample-cancel-button"
                  onClick={() => setCancelOpen(true)}>
                  <Ban size={13} /> Batalkan
                </button>
              )}
              {canSend && canSubmit && (
                <button className="secondary-button" disabled={busy}
                  data-testid="sample-send-button" onClick={() => setModal({ kind: "send" })}>
                  <Send size={13} /> Kirim ke supplier
                </button>
              )}
              {!decided && sample?.status !== "cancelled" && canDecide && (
                <button className="primary-button" disabled={busy || !hasAcc}
                  data-testid="sample-decide-button"
                  title={hasAcc ? "Pilih supplier pemenang"
                    : "Belum ada round yang ACC — nilai dulu hasil sample-nya"}
                  onClick={() => setModal({ kind: "decide" })}>
                  <Trophy size={13} /> Pilih pemenang
                </button>
              )}
              <button className="secondary-button" onClick={onClose}>Tutup</button>
            </>
          )}
        </div>
      </div>

      {/* ── Modal turunan ──────────────────────────────────────────── */}
      {modal?.kind === "send" && (
        <SampleSendModal mode="send" sample={sample} policy={policy} busy={busy}
          onClose={() => setModal(null)}
          onConfirm={(body) => act(() => sendSample(sample.id, body),
            "Permintaan terkirim — round 1 dibuka untuk tiap supplier.")} />
      )}
      {modal?.kind === "round" && (
        <SampleSendModal mode="round" sample={sample} participant={modal.participant}
          policy={policy} busy={busy} onClose={() => setModal(null)}
          onConfirm={(body) => act(() => openRound(sample.id, body), "Round berikutnya dibuka.")} />
      )}
      {modal?.kind === "submit" && (
        <RoundActionModal mode="submit" round={modal.round} busy={busy}
          onClose={() => setModal(null)}
          onConfirm={(body) => act(() => submitRound(sample.id, modal.round.id, body),
            "Hasil round tersimpan — menunggu penilaian.")} />
      )}
      {modal?.kind === "assess" && (
        <RoundActionModal mode="assess" round={modal.round} busy={busy}
          onClose={() => setModal(null)}
          onConfirm={(body) => act(() => assessRound(sample.id, modal.round.id, body),
            "Penilaian tersimpan.")} />
      )}
      {modal?.kind === "decide" && (
        <DecideModal sample={sample} reasons={reasons} busy={busy}
          onClose={() => setModal(null)}
          onConfirm={(body) => act(() => decideSample(sample.id, body),
            "Pemenang diputuskan — kontrak harga & barang supplier terbentuk.")} />
      )}
      {modal?.kind === "issue" && (
        <IssueMaterialModal busy={busy} onClose={() => setModal(null)}
          onConfirm={(body) => act(() => issueMaterial(sample.id, body),
            "Bahan diambil — stok gudang berkurang & biaya sample bertambah.")} />
      )}
    </div>
  );
}

function Box({ label, value, tone = "#1C1C1E", swatch, testId }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2" data-testid={testId}>
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="flex items-center gap-1.5 text-[12px] font-bold leading-tight"
        style={{ color: tone }}>
        {swatch && (
          <span className="inline-block h-3.5 w-3.5 rounded-full border border-[#E5E5EA]"
            style={{ background: swatch }} />
        )}
        {value}
      </p>
    </div>
  );
}
