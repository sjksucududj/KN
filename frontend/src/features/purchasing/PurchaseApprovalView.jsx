import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { BadgePercent, CheckCircle, XCircle, RefreshCw, ClipboardList, ChevronRight, ChevronDown, AlertCircle, Clock, Lock, Layers } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import POTimeline from "../admin/po/POTimeline";
import PODeviationBanner from "../admin/po/PODeviationBanner";
import ConfirmModal from "../../components/ConfirmModal";
import ErrorNotice from "../../components/ErrorNotice";
import QtyDual from "../../components/QtyDual";      // FASE U — dua satuan

/**
 * PurchaseApprovalView (Fase 3 + Fase 7.1 — Approval Pembelian BERJENJANG).
 * Antrian approval Purchase Order dengan:
 *  - Rantai approval multi-level (approval_chain): badge per tingkat (L1 Manager,
 *    L2 Direksi, …) + status tiap tingkat + progres "Tingkat X dari Y".
 *  - Tombol Setujui AKTIF hanya bila role user memenuhi tingkat PENDING saat ini
 *    (role_satisfies) & bukan pembuat PO (SoD). Bila tidak, tampil info "Menunggu …".
 *  - Drill-down: alasan approval, rincian item, dan timeline.
 * Endpoint: /purchase-orders/{id}/approve | /reject.
 */
const TABS = [
  { key: "waiting", label: "Menunggu" },
  { key: "approved", label: "Disetujui" },
  { key: "rejected", label: "Ditolak" },
];

// Lebar kolom tabel antrean — SATU definisi dipakai baris judul & baris data supaya
// keduanya tidak mungkin bergeser. `gap-x-4` wajib: tanpa jarak, angka Total menempel
// ke kolom Tingkat Persetujuan dan judul kolom bertabrakan pada layar biasa.
const GRID = "grid gap-x-4 grid-cols-[96px_minmax(190px,1.3fr)_140px_190px_110px_170px]";

// Hirarki peran — SATU sumber: `config/roles.js` (cermin `backend/role_registry.py`).
// Tabel lokal lama (`{sales:1, warehouse:1, manager:2, admin:3}`) tidak mengenal
// `sales_admin`/`finance`, sehingga pita "Role Anda belum memenuhi" salah menuduh.
import { roleLabel, roleSatisfies } from "../../config/roles";

/**
 * Bentuk rantai approval dari PO. Bila PO lama tidak punya `approval_chain`,
 * sintesis 1 tingkat dari `required_approval_role`/`approval_status` (backward-compatible).
 */
function getChain(po) {
  if (Array.isArray(po.approval_chain) && po.approval_chain.length) return po.approval_chain;
  const status = po.approval_status === "approved" ? "approved" : (po.status === "rejected" ? "rejected" : "pending");
  return [{
    level: 1,
    required_role: po.required_approval_role || "manager",
    label: "Persetujuan",
    status,
    approved_by: po.approved_by || "",
    approved_at: po.approved_at || "",
  }];
}

function pendingLevelOf(chain) {
  return (chain || []).find((l) => l.status !== "approved" && l.status !== "rejected") || null;
}

function matchTab(po, tab) {
  if (tab === "waiting") return po.status === "waiting_approval";
  if (tab === "approved") return po.approval_status === "approved";
  if (tab === "rejected") return po.status === "rejected";
  return true;
}

export default function PurchaseApprovalView({ currentUser, selectedEntity }) {
  const [pos, setPos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("waiting");
  const [busyId, setBusyId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [rejectTarget, setRejectTarget] = useState(null);

  const role = currentUser?.role;
  // Apakah user boleh menyetujui tingkat PENDING saat ini pada PO ini?
  function canApproveNow(po) {
    if (po.status !== "waiting_approval") return false;
    const chain = getChain(po);
    const pending = pendingLevelOf(chain);
    if (!pending) return false;
    if (!roleSatisfies(role, pending.required_role)) return false;
    // SoD — pembuat tidak boleh menyetujui PO sendiri.
    if (po.created_by_id && currentUser?.id && po.created_by_id === currentUser.id) return false;
    return true;
  }
  // Apakah user secara role bisa menolak (role memenuhi tingkat pending)?
  function canRejectNow(po) {
    if (po.status !== "waiting_approval") return false;
    const pending = pendingLevelOf(getChain(po));
    return !!pending && roleSatisfies(role, pending.required_role);
  }

  useEffect(() => { loadPOs(); }, [selectedEntity]); // eslint-disable-line

  async function loadPOs() {
    setLoading(true);
    try {
      const params = (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
      const res = await axios.get(`${API}/purchase-orders`, { params });
      setPos(Array.isArray(res.data) ? res.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat purchase order.");
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove(po) {
    setBusyId(po.id);
    try {
      const res = await axios.post(`${API}/purchase-orders/${po.id}/approve`);
      const updated = res.data || {};
      if (updated.status === "waiting_approval") {
        const next = pendingLevelOf(getChain(updated));
        setNotice(`PO ${po.po_number}: tingkat disetujui. Lanjut menunggu persetujuan ${roleLabel(next?.required_role)}.`);
      } else {
        setNotice(`PO ${po.po_number} disetujui penuh. Inbound task otomatis dibuat.`);
      }
      await loadPOs();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal approve PO.");
    } finally {
      setBusyId(null);
    }
  }

  async function doReject(reason) {
    const po = rejectTarget;
    if (!po) return;
    setBusyId(po.id);
    try {
      await axios.post(`${API}/purchase-orders/${po.id}/reject`, { reason });
      setNotice(`PO ${po.po_number} ditolak.`);
      setRejectTarget(null);
      await loadPOs();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal reject PO.");
      setRejectTarget(null);
    } finally {
      setBusyId(null);
    }
  }

  const counts = {
    waiting: pos.filter((p) => matchTab(p, "waiting")).length,
    approved: pos.filter((p) => matchTab(p, "approved")).length,
    rejected: pos.filter((p) => matchTab(p, "rejected")).length,
  };
  const filtered = pos.filter((p) => matchTab(p, tab));

  return (
    <div data-testid="purchase-approval-view">
      {notice && <div className="notice-bar success" data-testid="po-approval-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={loadPOs} onDismiss={() => setError("")} testId="po-approval-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <BadgePercent size={16} className="text-[#0058CC]" />
            <h2 data-testid="purchase-approval-title">Persetujuan Pembelian</h2>
          </div>
          <button data-testid="po-approval-refresh" onClick={loadPOs} className="secondary-button">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat Ulang
          </button>
        </div>
        <div className="section-body">
          <div className="tab-bar">
            {TABS.map((t) => (
              <button key={t.key} data-testid={`po-approval-tab-${t.key}`}
                className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                {t.label}<span className="tab-badge">{counts[t.key]}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="section-card">
        {/* Tabel lebar: beri jarak antar kolom + izinkan geser mendatar pada layar
            sempit. Sebelumnya `overflow-hidden` tanpa `gap` membuat angka Total
            menempel ke kolom Tingkat Persetujuan ("Rp 588.000.000MANAGER") dan
            judul kolom ikut bertabrakan ("TOTALTINGKAT PERSETUJUAN"). */}
        <div className="overflow-x-auto">
          <div className={`${GRID} min-w-[980px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]`}>
            <span>Nomor</span><span>Supplier / Gudang</span><span className="text-right">Total</span><span>Tingkat Persetujuan</span><span>Status</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat pesanan pembelian…</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]">
              <ClipboardList className="mx-auto mb-2 text-gray-300" size={28} />
              <p>Tidak ada PO {TABS.find((t) => t.key === tab)?.label.toLowerCase()}.</p>
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[600px] overflow-y-auto">
              {filtered.map((po) => {
                const open = expandedId === po.id;
                const chain = getChain(po);
                const pending = pendingLevelOf(chain);
                const totalLevels = po.approval_levels_total || chain.length;
                const approveOk = canApproveNow(po);
                const rejectOk = canRejectNow(po);
                return (
                  <div key={po.id}>
                    <div data-testid={`po-approval-row-${po.id}`}
                      className={`${GRID} min-w-[980px] items-center px-3 py-2.5 hover:bg-[#FAFBFC] cursor-pointer`}
                      onClick={() => setExpandedId(open ? null : po.id)}>
                      <span className="flex items-center gap-0.5 text-[11.5px] font-bold text-[#0058CC]">
                        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}{po.po_number}
                      </span>
                      <div className="min-w-0">
                        <p className="text-[12px] font-semibold truncate">{po.supplier_name}</p>
                        <p className="text-[10.5px] text-[#6B6B73] truncate">{po.warehouse_name} · {po.items?.length || 0} item</p>
                      </div>
                      <span className="whitespace-nowrap text-right text-[12px] font-bold tabular-nums">{formatCurrency(po.total_amount)}</span>
                      <ApprovalLevelCell po={po} chain={chain} pending={pending} totalLevels={totalLevels} />
                      <ApprovalStatusPill po={po} />
                      <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                        {po.status === "waiting_approval" ? (
                          approveOk ? (
                            <>
                              <button data-testid={`po-approve-${po.id}`} disabled={busyId === po.id}
                                onClick={() => handleApprove(po)} className="primary-button !px-2.5 !py-1 text-[11px]">
                                <CheckCircle size={12} /> Setujui
                              </button>
                              <button data-testid={`po-reject-${po.id}`} disabled={busyId === po.id}
                                onClick={() => setRejectTarget(po)} className="danger-button !px-2.5 !py-1 text-[11px]">
                                <XCircle size={12} /> Tolak
                              </button>
                            </>
                          ) : (
                            <span data-testid={`po-approve-locked-${po.id}`}
                              className="flex items-center gap-1 text-[10.5px] text-[#9A5B00] text-right leading-tight">
                              <Lock size={11} className="shrink-0" />
                              {rejectOk ? "—" : `Menunggu ${roleLabel(pending?.required_role)}`}
                            </span>
                          )
                        ) : (
                          <span className="text-[10.5px] text-[#9A9BA3]">
                            {po.approved_by ? `oleh ${po.approved_by}` : po.rejected_by ? `oleh ${po.rejected_by}` : "—"}
                          </span>
                        )}
                      </div>
                    </div>

                    {open && (
                      <ApprovalDetail po={po} chain={chain} pending={pending} totalLevels={totalLevels}
                        currentUser={currentUser}
                        approveOk={approveOk}
                        busy={busyId === po.id}
                        onApprove={() => handleApprove(po)}
                        onReject={() => setRejectTarget(po)} />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <ConfirmModal
        open={!!rejectTarget}
        title={`Tolak ${rejectTarget?.po_number || "PO"}`}
        message="Berikan alasan penolakan (tersimpan di riwayat & audit PO)."
        confirmLabel="Tolak PO"
        danger
        withReason
        reasonLabel="Alasan penolakan"
        reasonPlaceholder="Mis. harga di atas anggaran, supplier belum disetujui, dsb."
        onConfirm={doReject}
        onCancel={() => setRejectTarget(null)}
        testId="po-reject-modal"
      />
    </div>
  );
}

/** Sel kolom tabel: ringkas tingkat pending + progres "Tingkat X/Y". */
function ApprovalLevelCell({ po, chain, pending, totalLevels }) {
  if (po.status !== "waiting_approval") {
    if (po.approval_status === "approved") {
      return <span className="text-[10.5px] text-[#1B7A43] font-semibold">Selesai · {totalLevels} tingkat</span>;
    }
    return <span className="text-[10.5px] text-[#9A9BA3]">—</span>;
  }
  const currentLevelNo = pending?.level || 1;
  return (
    <div className="min-w-0" data-testid={`po-approval-levelcell-${po.id}`}>
      <p className="text-[11px] uppercase font-semibold text-[#A05000] truncate">
        {roleLabel(pending?.required_role)}
        {pending?.label && pending.label !== "Approval" && pending.label !== roleLabel(pending.required_role) ? ` · ${pending.label}` : ""}
      </p>
      <p className="text-[10px] text-[#6B6B73]">Tingkat {currentLevelNo} dari {totalLevels}</p>
    </div>
  );
}

/** Stepper rantai approval — badge per tingkat dengan status & approver. */
function ApprovalChainSteps({ po, chain, pending, totalLevels }) {
  return (
    <div className="rounded-md border border-[#EFF0F2] overflow-hidden" data-testid={`po-approval-chain-${po.id}`}>
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
        <Layers size={12} /> Alur Persetujuan Berjenjang
        <span className="ml-auto normal-case font-semibold text-[#0058CC]">
          {po.status === "waiting_approval" ? `Tingkat ${pending?.level || 1} dari ${totalLevels}` : `${totalLevels} tingkat`}
        </span>
      </div>
      <div className="flex flex-wrap items-stretch gap-2 px-2.5 py-2.5">
        {chain.map((lv, idx) => {
          const isApproved = lv.status === "approved";
          const isRejected = lv.status === "rejected" || po.status === "rejected";
          const isCurrent = po.status === "waiting_approval" && pending && lv.level === pending.level;
          let cls = "border-[#E3E4E8] bg-white text-[#6B6B73]"; // antri/future
          let Icon = Clock;
          let stateText = "Antri";
          if (isApproved) { cls = "border-[#BFE6CD] bg-[#EFFBF3] text-[#1B7A43]"; Icon = CheckCircle; stateText = "Disetujui"; }
          else if (isRejected && isCurrent) { cls = "border-[#F3C2C2] bg-[#FDF1F1] text-[#9B1C1C]"; Icon = XCircle; stateText = "Ditolak"; }
          else if (isCurrent) { cls = "border-[#FFD9A8] bg-[#FFF7EC] text-[#9A5B00]"; Icon = Clock; stateText = "Menunggu"; }
          return (
            <div key={lv.level} className="flex items-center gap-2">
              <div data-testid={`po-approval-step-${po.id}-${lv.level}`}
                className={`min-w-[140px] rounded-md border px-2.5 py-1.5 ${cls}`}>
                <div className="flex items-center gap-1 text-[11px] font-bold">
                  <Icon size={12} className="shrink-0" />
                  <span>L{lv.level} · {roleLabel(lv.required_role)}</span>
                </div>
                <div className="mt-0.5 text-[10px] font-semibold">{stateText}{isCurrent ? " (sekarang)" : ""}</div>
                {isApproved && (
                  <div className="text-[9.5px] opacity-80 truncate">
                    {lv.approved_by || "—"}{lv.approved_at ? ` · ${String(lv.approved_at).slice(0, 10)}` : ""}
                  </div>
                )}
              </div>
              {idx < chain.length - 1 && <ChevronRight size={14} className="text-[#C7C8CE] shrink-0" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ApprovalDetail({ po, chain, pending, totalLevels, currentUser, approveOk, busy, onApprove, onReject }) {
  const flagged = po.price_deviation?.flagged;
  const isCreator = po.created_by_id && currentUser?.id && po.created_by_id === currentUser.id;
  const roleBlocked = po.status === "waiting_approval" && !approveOk && !isCreator;
  return (
    <div data-testid={`po-approval-detail-${po.id}`} className="bg-[#FCFCFD] border-t border-[#EFF0F2] px-3 py-3 space-y-2.5">
      {/* Rantai approval berjenjang */}
      {po.status !== "rejected" && (
        <ApprovalChainSteps po={po} chain={chain} pending={pending} totalLevels={totalLevels} />
      )}

      {/* Alasan kenapa butuh approval */}
      {flagged ? (
        <PODeviationBanner deviation={po.price_deviation} />
      ) : po.status === "waiting_approval" ? (
        <div className="flex items-center gap-1.5 rounded-md border border-[#FFE2B8] bg-[#FFF7EC] px-2.5 py-1.5 text-[11px] text-[#9A5B00]">
          <AlertCircle size={13} />
          <span>Nilai PO <b className="tabular-nums">{formatCurrency(po.total_amount)}</b> butuh persetujuan tingkat <b>{pending?.level || 1}/{totalLevels}</b> — role <b className="uppercase">{roleLabel(pending?.required_role)}</b>.</span>
        </div>
      ) : null}

      {/* Rincian item */}
      <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
        <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
          Rincian Item ({po.items?.length || 0})
        </div>
        {(po.items || []).map((it, i) => (
          <div key={i} data-testid={`po-approval-item-${po.id}-${i}`}
            className="grid grid-cols-[1fr_90px_120px] gap-2 px-2.5 py-1.5 border-b border-[#EFF0F2] last:border-0 text-[11px]">
            <div className="min-w-0">
              <p className="font-semibold truncate">{it.sku}</p>
              <p className="text-[10px] text-[#6B6B73] truncate">{it.product_name}</p>
            </div>
            <span className="tabular-nums text-[#3C3C43] text-right self-center"><QtyDual rolls={it.qty_rolls} measure={it.quantity} unit={it.unit} factor={it.unit_factor} factorTo={it.unit_factor_to} /></span>
            <span className="tabular-nums font-semibold text-right self-center">{formatCurrency(it.subtotal || (it.quantity || 0) * (it.price || 0))}</span>
          </div>
        ))}
      </div>

      {/* Riwayat / timeline */}
      <POTimeline po={po} />

      {/* Aksi kontekstual */}
      {po.status === "waiting_approval" && (
        approveOk ? (
          <div className="flex justify-end gap-1.5">
            <button data-testid={`po-approve-detail-${po.id}`} disabled={busy} onClick={onApprove}
              className="primary-button !px-3 !py-1 text-[11px]"><CheckCircle size={12} /> Setujui Tingkat {pending?.level || 1}</button>
            <button data-testid={`po-reject-detail-${po.id}`} disabled={busy} onClick={onReject}
              className="danger-button !px-3 !py-1 text-[11px]"><XCircle size={12} /> Tolak PO</button>
          </div>
        ) : (
          <div data-testid={`po-approval-blocked-${po.id}`}
            className="flex items-center gap-1.5 rounded-md border border-[#E3E4E8] bg-[#F7F8FA] px-2.5 py-1.5 text-[11px] text-[#6B6B73]">
            <Lock size={13} className="shrink-0" />
            {isCreator ? (
              <span>Anda pembuat PO ini — pemisahan tugas (SoD) melarang menyetujui PO sendiri.</span>
            ) : (
              <span>Tingkat berjalan butuh peran <b className="uppercase">{roleLabel(pending?.required_role)}</b>. Role Anda (<b className="uppercase">{roleLabel(currentUser?.role)}</b>) belum memenuhi — menunggu approver yang sesuai.</span>
            )}
          </div>
        )
      )}
    </div>
  );
}

function ApprovalStatusPill({ po }) {
  let cls = "pill-muted", label = "—";
  if (po.status === "waiting_approval") { cls = "pill-warning"; label = "Menunggu"; }
  else if (po.status === "rejected") { cls = "pill-danger"; label = "Ditolak"; }
  else if (po.approval_status === "approved") { cls = "pill-success"; label = "Disetujui"; }
  return <span data-testid={`po-approval-pill-${po.id}`} className={`status-pill ${cls}`}>{label}</span>;
}
