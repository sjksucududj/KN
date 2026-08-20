/**
 * MyApprovalsView (PS-20 / D-14) — layar **Pusat Persetujuan › Persetujuan Saya**.
 *
 * Menjawab keputusan pemilik: matriks persetujuan divisi kini MENGIKAT, dan approver
 * butuh SATU antrean yang bisa langsung ditindak:
 *   • 4 tahap: ACC Desain · ACC Sample · PO Custom (2 tingkat) · Permintaan Pembelian.
 *   • Setiap baris jujur: bila tidak boleh diputuskan, alasannya ditulis (peran salah,
 *     pemisahan tugas, atau sample belum punya round ACC) — tombol tidak disembunyikan.
 *   • Jejak persetujuan (siapa memutus apa, termasuk percobaan yang ditolak sistem).
 *
 * ACC Sample sengaja TIDAK diputuskan dari sini: keputusannya memerlukan pemenang
 * supplier + harga kesepakatan, jadi barisnya membuka layar Permintaan Sample.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowRight, Check, ClipboardCheck, FileCheck2, Layers3,
  RefreshCw, ScrollText, ShieldCheck, ShoppingBag, Users2, X,
} from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import {
  apiErr, approvalMatrixLog, approvePr, approveSpec, approveSpecialOrder,
  myApprovalQueue, rejectPr, rejectSpec, rejectSpecialOrder,
} from "./approvalsMatrixApi";

const STAGE_META = {
  design_acc: { label: "ACC Desain", icon: FileCheck2, fg: "#6B219A", bg: "#F3E9FA" },
  sample_acc: { label: "ACC Sample", icon: Layers3, fg: "#0E7490", bg: "#E0F2FE" },
  po_custom: { label: "PO Custom", icon: ShoppingBag, fg: "#B45309", bg: "#FEF3C7" },
  purchase_request: { label: "Permintaan Pembelian", icon: ClipboardCheck, fg: "#1B7F4B", bg: "#E9F7EF" },
};

const MODE_TONE = {
  enforce: "bg-[#E9F7EF] text-[#1B7F4B]",
  warn: "bg-[#FEF3C7] text-[#B45309]",
  off: "bg-[#F5F5F7] text-[#8E8E93]",
};

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("id-ID",
      { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return "—"; }
}

function fmtWaktu(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("id-ID",
      { timeZone: "Asia/Jakarta", day: "2-digit", month: "short",
        hour: "2-digit", minute: "2-digit" });
  } catch { return "—"; }
}

/** Kartu ringkas satu tahap (juga berfungsi sebagai saringan). */
function StageCard({ stage, count, active, onClick }) {
  const meta = STAGE_META[stage] || {};
  const Icon = meta.icon || ShieldCheck;
  return (
    <button type="button" onClick={onClick}
      data-testid={`my-approvals-stage-${stage}`}
      className={`rounded-xl border p-3 text-left transition-colors ${
        active ? "border-[#0058CC] bg-[#EFF4FF]" : "border-[#E5E5EA] bg-white hover:border-[#0058CC]"}`}>
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-[12px] font-bold text-[#1C1C1E]">
          <Icon size={13} style={{ color: meta.fg }} /> {meta.label || stage}
        </span>
        <span className="rounded-full px-2 py-0.5 text-[10.5px] font-bold"
          style={{ background: meta.bg, color: meta.fg }}
          data-testid={`my-approvals-count-${stage}`}>{count}</span>
      </div>
      <p className="mt-1 text-[10.5px] text-[#6B6B73]">menunggu keputusan</p>
    </button>
  );
}

/** Rantai tingkat persetujuan (mis. Manager → Direksi). */
function ChainPills({ chain = [], level = 1, total = 1, label = "" }) {
  if (!chain.length) {
    return (
      <span className="inline-block rounded-full bg-[#EEF1F5] px-2 py-0.5 text-[10px] font-semibold text-[#4A4B52]">
        Tingkat {level}/{total}{label ? ` · ${label}` : ""}
      </span>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-1">
      {chain.map((lv) => (
        <span key={lv.level}
          className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${
            lv.status === "approved"
              ? "bg-[#E9F7EF] text-[#1B7F4B]"
              : "bg-[#FFF4E5] text-[#B45309]"}`}>
          {lv.status === "approved" ? "✓ " : "○ "}{lv.level}. {lv.label}
        </span>
      ))}
    </span>
  );
}

export default function MyApprovalsView({ currentUser, selectedEntity, onNavigate }) {
  const [data, setData] = useState(null);
  const [logRows, setLogRows] = useState([]);
  const [onlyViolations, setOnlyViolations] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [stage, setStage] = useState("");
  const [msg, setMsg] = useState(null);
  const [modal, setModal] = useState(null);   // {item, action:'approve'|'reject'}
  const [form, setForm] = useState({ sku: "", name: "", note: "", reason: "" });
  const [busy, setBusy] = useState(false);

  const params = useMemo(() => {
    const p = {};
    if (selectedEntity && selectedEntity !== "all") p.entity_id = selectedEntity;
    return p;
  }, [selectedEntity]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [q, lg] = await Promise.all([
        myApprovalQueue(params),
        approvalMatrixLog({ ...params, limit: 40, only_violations: onlyViolations }),
      ]);
      setData(q || null);
      setLogRows((lg && lg.items) || []);
      setError("");
    } catch (e) {
      setError(apiErr(e, "Gagal memuat antrean persetujuan."));
    } finally {
      setLoading(false);
    }
  }, [params, onlyViolations]);

  useEffect(() => { load(); }, [load]);

  const cfg = data?.config || {};
  const items = (data?.items || []).filter((it) => !stage || it.stage === stage);
  const counts = data?.counts || {};

  function openModal(item, action) {
    setForm({ sku: "", name: item.title || "", note: "", reason: "" });
    setModal({ item, action });
  }

  async function submitDecision() {
    if (!modal) return;
    const { item, action } = modal;
    setBusy(true);
    setMsg(null);
    try {
      if (action === "approve") {
        if (item.stage === "design_acc") {
          await approveSpec(item.id, { sku: form.sku.trim(), name: form.name.trim(),
            note: form.note });
        } else if (item.stage === "purchase_request") {
          await approvePr(item.id, { notes: form.note });
        } else if (item.stage === "po_custom") {
          await approveSpecialOrder(item.id, { notes: form.note });
        }
      } else {
        if (item.stage === "design_acc") {
          await rejectSpec(item.id, { reason: form.reason });
        } else if (item.stage === "purchase_request") {
          await rejectPr(item.id, { notes: form.reason });
        } else if (item.stage === "po_custom") {
          await rejectSpecialOrder(item.id, { reason: form.reason });
        }
      }
      setModal(null);
      setMsg({ ok: true, text: `${item.number} — ${action === "approve" ? "disetujui" : "ditolak"}.` });
      await load();
    } catch (e) {
      setMsg({ ok: false, text: apiErr(e, "Keputusan gagal disimpan.") });
    } finally {
      setBusy(false);
    }
  }

  const modalItem = modal?.item;
  const needSku = modal?.action === "approve" && modalItem?.stage === "design_acc";
  const canSubmit = modal?.action === "approve"
    ? (!needSku || form.sku.trim().length >= 3)
    : form.reason.trim().length >= 3;

  return (
    <div className="grid gap-3" data-testid="my-approvals-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
        testId="my-approvals-error" />

      {/* ── Kepala + status penegakan ──────────────────────────────── */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <ShieldCheck size={16} className="text-[#1B7F4B]" />
            <h2 data-testid="my-approvals-title">Persetujuan Saya</h2>
          </div>
          <button className="secondary-button" onClick={load} data-testid="my-approvals-refresh">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
          </button>
        </div>
        <div className="section-body">
          <p className="text-[11.5px] text-[#6B6B73]">
            Semua dokumen R&amp;D yang menunggu keputusan Anda menurut <strong>matriks
            persetujuan divisi</strong>. Keputusan tercatat di jejak persetujuan.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5"
            data-testid="my-approvals-enforcement">
            <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ${
              MODE_TONE[cfg.mode] || MODE_TONE.off}`}>
              Penegakan: {cfg.mode_label || "—"}
            </span>
            <span className="rounded-full bg-[#EFF4FF] px-2 py-0.5 text-[10.5px] font-semibold text-[#0058CC]">
              Cakupan: {cfg.scope_label || "—"}
            </span>
            <span className="rounded-full bg-[#F3E9FA] px-2 py-0.5 text-[10.5px] font-semibold text-[#6B219A]">
              Pemisahan tugas: {cfg.sod ? "aktif" : "nonaktif"}
            </span>
            <span className="rounded-full bg-[#FEF3C7] px-2 py-0.5 text-[10.5px] font-semibold text-[#B45309]">
              PO Custom → Direksi ≥ {formatCurrency(cfg.po_custom_direksi_min || 0)}
            </span>
            <span className="rounded-full bg-[#EEF1F5] px-2 py-0.5 text-[10.5px] font-semibold text-[#4A4B52]">
              <Users2 size={10} className="mr-1 inline" />
              Anda: {data?.actor?.role_label || currentUser?.role || "—"}
            </span>
          </div>
          {msg && (
            <p data-testid="my-approvals-msg"
              className={`mt-2 rounded-md px-2.5 py-1.5 text-[11.5px] font-medium ${
                msg.ok ? "bg-[#E9F7EF] text-[#1B7F4B]" : "bg-[#FDECEA] text-[#C0392B]"}`}>
              {msg.text}
            </p>
          )}
        </div>
      </section>

      {/* ── Kartu per tahap (saringan) ─────────────────────────────── */}
      <section className="section-card">
        <div className="section-head">
          <h2>Antrean per Tahap</h2>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-[#6B6B73]" data-testid="my-approvals-summary">
              {data?.total || 0} menunggu · {data?.actionable || 0} bisa Anda putuskan
            </span>
            {stage && (
              <button className="secondary-button" data-testid="my-approvals-clear-filter"
                onClick={() => setStage("")}>Tampilkan semua</button>
            )}
          </div>
        </div>
        <div className="section-body">
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {(data?.stages || []).map((s) => (
              <StageCard key={s.stage} stage={s.stage} count={counts[s.stage] || 0}
                active={stage === s.stage}
                onClick={() => setStage(stage === s.stage ? "" : s.stage)} />
            ))}
          </div>
        </div>
      </section>

      {/* ── Daftar antrean ─────────────────────────────────────── */}
      <section className="section-card">
        <div className="section-head"><h2>Dokumen Menunggu ({items.length})</h2></div>
        <div className="section-body">
          {loading && !data ? (
            <p className="py-8 text-center text-[12px] text-[#6B6B73]">Memuat antrean…</p>
          ) : items.length === 0 ? (
            <p className="py-8 text-center text-[12px] text-[#9A9BA3]"
              data-testid="my-approvals-empty">
              Tidak ada dokumen yang menunggu keputusan pada saringan ini. 🎉
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] text-left text-[12px]"
                data-testid="my-approvals-list">
                <thead>
                  <tr className="text-[10px] uppercase text-[#8E8E93]">
                    <th className="py-1.5 pr-3 font-bold">Tahap</th>
                    <th className="py-1.5 pr-3 font-bold">Dokumen</th>
                    <th className="py-1.5 pr-3 font-bold">Pengaju</th>
                    <th className="py-1.5 pr-3 text-right font-bold">Nilai</th>
                    <th className="py-1.5 pr-3 font-bold">Menunggu</th>
                    <th className="py-1.5 pr-3 font-bold">Tingkat</th>
                    <th className="py-1.5 font-bold">Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#F4F5F7]">
                  {items.map((it) => {
                    const meta = STAGE_META[it.stage] || {};
                    const Icon = meta.icon || ShieldCheck;
                    const isSample = it.stage === "sample_acc";
                    return (
                      <tr key={`${it.stage}-${it.id}`} data-testid={`my-approvals-row-${it.id}`}
                        className="align-top">
                        <td className="py-2 pr-3">
                          <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-bold"
                            style={{ background: meta.bg, color: meta.fg }}>
                            <Icon size={11} /> {meta.label || it.stage}
                          </span>
                        </td>
                        <td className="py-2 pr-3">
                          <div className="font-semibold text-[#1C1C1E]">{it.number}</div>
                          <div className="text-[11px] text-[#6B6B73]">{it.title}</div>
                          {it.customer_name && (
                            <div className="text-[10.5px] text-[#8E8E93]">{it.customer_name}</div>
                          )}
                        </td>
                        <td className="py-2 pr-3 text-[11.5px] text-[#4A4B52]">
                          {it.requester || "—"}
                          <div className="text-[10.5px] text-[#9A9BA3]">{fmtDate(it.created_at)}</div>
                        </td>
                        <td className="py-2 pr-3 text-right font-semibold text-[#1C1C1E]">
                          {it.amount ? formatCurrency(it.amount) : "—"}
                        </td>
                        <td className="py-2 pr-3">
                          <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ${
                            it.days_waiting >= 3 ? "bg-[#FDECEA] text-[#C0392B]"
                              : "bg-[#EEF1F5] text-[#4A4B52]"}`}>
                            {it.days_waiting} hari
                          </span>
                        </td>
                        <td className="py-2 pr-3">
                          <ChainPills chain={it.approval_chain} level={it.level}
                            total={it.levels_total} label={it.level_label} />
                          <div className="mt-1 text-[10px] text-[#8E8E93]">
                            perlu: {it.required_roles_label}
                          </div>
                        </td>
                        <td className="py-2">
                          <div className="flex flex-wrap items-center gap-1.5">
                            {!isSample && (
                              <>
                                <button className="primary-button !h-7 !px-2 !text-[11px]"
                                  disabled={!it.can_decide}
                                  data-testid={`my-approvals-approve-${it.id}`}
                                  onClick={() => openModal(it, "approve")}>
                                  <Check size={12} /> Setujui
                                </button>
                                <button className="danger-button !h-7 !px-2 !text-[11px]"
                                  disabled={!it.can_decide}
                                  data-testid={`my-approvals-reject-${it.id}`}
                                  onClick={() => openModal(it, "reject")}>
                                  <X size={12} /> Tolak
                                </button>
                              </>
                            )}
                            <button className="secondary-button !h-7 !px-2 !text-[11px]"
                              data-testid={`my-approvals-open-${it.id}`}
                              onClick={() => onNavigate && onNavigate(it.view)}>
                              Buka <ArrowRight size={12} />
                            </button>
                          </div>
                          {isSample && (
                            <p className="mt-1 max-w-[240px] text-[10px] text-[#8E8E93]">
                              Keputusan sample memilih pemenang + harga — dilakukan di layar
                              Permintaan Sample.
                            </p>
                          )}
                          {!it.can_decide && (it.block_reasons || []).length > 0 && (
                            <p className="mt-1 max-w-[260px] text-[10px] font-medium text-[#C0392B]"
                              data-testid={`my-approvals-blocked-${it.id}`}>
                              <AlertTriangle size={10} className="mr-1 inline" />
                              {it.block_reasons[0]}
                            </p>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* ── Jejak persetujuan ──────────────────────────────────── */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <ScrollText size={15} className="text-[#6B219A]" />
            <h2>Jejak Persetujuan</h2>
          </div>
          <label className="flex items-center gap-1.5 text-[11px] text-[#4A4B52]">
            <input type="checkbox" checked={onlyViolations}
              data-testid="my-approvals-log-violations"
              onChange={(e) => setOnlyViolations(e.target.checked)} />
            hanya percobaan yang ditolak
          </label>
        </div>
        <div className="section-body">
          {logRows.length === 0 ? (
            <p className="py-6 text-center text-[12px] text-[#9A9BA3]"
              data-testid="my-approvals-log-empty">Belum ada jejak keputusan.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-[12px]"
                data-testid="my-approvals-log">
                <thead>
                  <tr className="text-[10px] uppercase text-[#8E8E93]">
                    <th className="py-1.5 pr-3 font-bold">Waktu (WIB)</th>
                    <th className="py-1.5 pr-3 font-bold">Tahap</th>
                    <th className="py-1.5 pr-3 font-bold">Dokumen</th>
                    <th className="py-1.5 pr-3 font-bold">Oleh</th>
                    <th className="py-1.5 font-bold">Hasil</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#F4F5F7]">
                  {logRows.map((r) => (
                    <tr key={r.id} data-testid={`my-approvals-log-row-${r.id}`}>
                      <td className="py-2 pr-3 text-[11px] text-[#6B6B73]">{fmtWaktu(r.created_at)}</td>
                      <td className="py-2 pr-3 text-[11.5px] font-semibold text-[#1C1C1E]">
                        {r.stage_label}
                        <span className="ml-1 text-[10px] font-normal text-[#8E8E93]">
                          tingkat {r.level}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-[11.5px]">{r.doc_number || "—"}</td>
                      <td className="py-2 pr-3 text-[11.5px]">
                        {r.actor_name}
                        <span className="ml-1 text-[10px] text-[#8E8E93]">({r.actor_role})</span>
                      </td>
                      <td className="py-2 text-[11.5px]">
                        <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${
                          r.violation ? "bg-[#FDECEA] text-[#C0392B]" : "bg-[#E9F7EF] text-[#1B7F4B]"}`}>
                          {r.outcome || r.action}
                        </span>
                        {r.note && (
                          <div className="mt-0.5 max-w-[360px] text-[10px] text-[#8E8E93]">{r.note}</div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* ── Modal keputusan ───────────────────────────────────── */}
      {modal && (
        <div className="modal-overlay" data-testid="my-approvals-modal"
          onClick={(e) => { if (e.target === e.currentTarget && !busy) setModal(null); }}>
          <div className="modal-card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="modal-title">
                  {modal.action === "approve" ? "Setujui" : "Tolak"}{" "}
                  {STAGE_META[modalItem.stage]?.label} · {modalItem.number}
                </p>
                <p className="modal-subtitle">
                  {modalItem.title}
                  {modalItem.amount ? ` · ${formatCurrency(modalItem.amount)}` : ""}
                  {" · diajukan "}{modalItem.requester || "—"}
                </p>
              </div>
              <button className="secondary-button !h-7 !px-2" onClick={() => setModal(null)}
                data-testid="my-approvals-modal-close"><X size={13} /></button>
            </div>
            <div className="mt-3 grid gap-2.5">
              {needSku && (
                <>
                  <label className="grid gap-1 text-[11px] font-semibold text-[#4A4B52]">
                    Kode SKU produk baru (wajib, min. 3 huruf)
                    <input className="field" data-testid="my-approvals-sku"
                      value={form.sku} placeholder="mis. KN-RAYON-PARANG"
                      onChange={(e) => setForm({ ...form, sku: e.target.value.toUpperCase() })} />
                  </label>
                  <label className="grid gap-1 text-[11px] font-semibold text-[#4A4B52]">
                    Nama produk
                    <input className="field" data-testid="my-approvals-name"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  </label>
                  <p className="text-[10.5px] text-[#8E8E93]">
                    ACC desain melahirkan produk berstatus <strong>disetujui</strong> — belum
                    boleh dijual sampai dirilis ke produksi.
                  </p>
                </>
              )}
              {modal.action === "approve" ? (
                <label className="grid gap-1 text-[11px] font-semibold text-[#4A4B52]">
                  Catatan (opsional)
                  <textarea className="field !h-16" data-testid="my-approvals-note"
                    value={form.note}
                    onChange={(e) => setForm({ ...form, note: e.target.value })} />
                </label>
              ) : (
                <label className="grid gap-1 text-[11px] font-semibold text-[#4A4B52]">
                  Alasan penolakan (wajib, min. 3 huruf)
                  <textarea className="field !h-16" data-testid="my-approvals-reason"
                    value={form.reason}
                    onChange={(e) => setForm({ ...form, reason: e.target.value })} />
                </label>
              )}
            </div>
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => setModal(null)}
                disabled={busy}>Batal</button>
              <button
                className={modal.action === "approve" ? "primary-button" : "danger-button"}
                disabled={!canSubmit || busy}
                data-testid="my-approvals-modal-submit"
                onClick={submitDecision}>
                {busy ? "Menyimpan…" : (modal.action === "approve" ? "Setujui" : "Tolak")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
