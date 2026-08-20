import { Bell, Check, CheckCheck, RefreshCw, AlertTriangle, Info, X, CheckCircle2, Loader2, ArrowUpCircle, Filter } from "lucide-react";
import { useState, useRef, useEffect, useMemo } from "react";
import KNSelect from "./KNSelect";

const SEVERITY_ICON = { warning: AlertTriangle, critical: AlertTriangle, info: Info };
const ROLE_RANK = { sales: 1, warehouse: 1, manager: 2, admin: 3 };
const canActOn = (userRole, requiredRole) =>
  (ROLE_RANK[userRole] || 0) >= (ROLE_RANK[requiredRole] || 99);

// R6.6 — label ramah-manusia per tipe notifikasi (untuk filter jenis).
const TYPE_LABEL = {
  escalation: "Eskalasi",
  ar_overdue: "Piutang jatuh tempo",
  ap_due: "Hutang supplier",
  depreciation_due: "Penyusutan aset",
  budget_alert: "Anggaran",
  production_stalled: "Produksi tertunda",
  ops_stalled: "Tugas gudang",
  low_stock: "Stok menipis",
  reservation_expiring: "Reservasi kedaluwarsa",
  order_approval: "Approval order",
  po_approval: "Approval PO",
  amendment_approval: "Amandemen dokumen",
  order_split: "Order split",
  // PS-21 — notifikasi operasional baru
  po_arrival: "Barang PO datang",
  backorder_ready: "Pendingan siap",
  ar_due_soon: "Piutang mendekati jatuh tempo",
  restock_request: "Permintaan repeat/restock",
  // 2026-08-15 — pengingat harian antrean persetujuan (services/approval_reminder.py)
  approval_backlog: "Keputusan menunggu",
};
const typeLabel = (t) => TYPE_LABEL[t] || (t || "lainnya").replace(/_/g, " ");

const SEV_CHIPS = [
  { key: "", label: "Semua" },
  { key: "critical", label: "Penting" },
  { key: "warning", label: "Perhatian" },
  { key: "info", label: "Info" },
];

function timeAgo(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "baru saja";
  if (diff < 3600) return `${Math.floor(diff / 60)} mnt lalu`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} jam lalu`;
  return `${Math.floor(diff / 86400)} hari lalu`;
}

/**
 * Notification Center (Fase 0) — bell + dropdown daftar notifikasi in-app.
 * Depth #3 — aksi inline "Setujui" untuk notifikasi PO approval (po_approve).
 * R6.6 — filter tingkat kepentingan + jenis + "belum dibaca", serta penanda ESKALASI
 *        agar alert yang dinaikkan atasan langsung terlihat.
 */
export default function NotificationCenter({
  notifications = [], unreadCount = 0, canGenerate = false, currentUserRole = "",
  onMarkRead, onMarkAll, onGenerate, onNavigate, onApprove,
}) {
  const [open, setOpen] = useState(false);
  const [approving, setApproving] = useState(null);
  const [sev, setSev] = useState("");
  const [type, setType] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Jenis yang tersedia (hanya yang benar-benar ada di daftar) + jumlahnya.
  const types = useMemo(() => {
    const counts = {};
    notifications.forEach((n) => { counts[n.type] = (counts[n.type] || 0) + 1; });
    return Object.entries(counts)
      .map(([k, v]) => ({ value: k, label: `${typeLabel(k)} (${v})` }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [notifications]);

  const filtered = useMemo(() => notifications.filter((n) => {
    if (sev && (n.severity || "info") !== sev) return false;
    if (type && n.type !== type) return false;
    if (unreadOnly && n.read) return false;
    return true;
  }), [notifications, sev, type, unreadOnly]);

  const hasFilter = Boolean(sev || type || unreadOnly);
  const resetFilters = () => { setSev(""); setType(""); setUnreadOnly(false); };

  async function handleApprove(e, n) {
    e.stopPropagation();
    setApproving(n.id);
    try { await onApprove?.(n); } finally { setApproving(null); }
  }

  return (
    <div className="notif-center" ref={ref}>
      <button
        type="button"
        data-testid="notif-bell"
        className="icon-button notif-bell"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifikasi"
        title="Notifikasi"
      >
        <Bell size={15} />
        {unreadCount > 0 && (
          <span data-testid="notif-badge" className="notif-badge">{unreadCount > 99 ? "99+" : unreadCount}</span>
        )}
      </button>
      {open && (
        <div className="notif-panel" data-testid="notif-panel">
          <div className="notif-panel-head">
            <span className="notif-panel-title">Notifikasi</span>
            <div className="flex items-center gap-1">
              {canGenerate && (
                <button data-testid="notif-generate-button" className="notif-mini-button" title="Pindai event sistem" onClick={() => onGenerate?.()}>
                  <RefreshCw size={12} /> Scan
                </button>
              )}
              <button data-testid="notif-mark-all-button" className="notif-mini-button" title="Tandai semua dibaca" onClick={() => onMarkAll?.()}>
                <CheckCheck size={12} /> Semua
              </button>
              <button className="icon-button" aria-label="Tutup" onClick={() => setOpen(false)}><X size={14} /></button>
            </div>
          </div>

          {/* R6.6 — filter cepat: tingkat kepentingan, jenis, belum dibaca */}
          <div className="notif-filters" data-testid="notif-filters">
            {SEV_CHIPS.map((c) => (
              <button
                key={c.key || "all"}
                type="button"
                data-testid={`notif-filter-sev-${c.key || "all"}`}
                className={`notif-chip ${sev === c.key ? `active sev-${c.key || "all"}` : ""}`}
                onClick={() => setSev(c.key)}
              >
                {c.label}
              </button>
            ))}
            <button
              type="button"
              data-testid="notif-filter-unread"
              className={`notif-chip ${unreadOnly ? "active" : ""}`}
              onClick={() => setUnreadOnly((v) => !v)}
              title="Tampilkan hanya yang belum dibaca"
            >
              Belum dibaca
            </button>
            <KNSelect
              data-testid="notif-filter-type"
              className="notif-type-select"
              value={type}
              onValueChange={setType}
              aria-label="Filter jenis notifikasi"
              placeholder="Semua jenis"
              options={[{ value: "", label: "Semua jenis" }, ...types]}
            />
            <span className="notif-filter-count" data-testid="notif-filter-count">
              <Filter size={9} style={{ display: "inline", marginRight: 3, verticalAlign: "-1px" }} />
              Menampilkan {filtered.length} dari {notifications.length} notifikasi
              {hasFilter && (
                <button type="button" data-testid="notif-filter-reset"
                        onClick={resetFilters}
                        style={{ marginLeft: 6, color: "#0058CC", fontWeight: 700, cursor: "pointer" }}>
                  Reset filter
                </button>
              )}
            </span>
          </div>

          <div className="notif-list" data-testid="notif-list">
            {notifications.length === 0 && (
              <div data-testid="notif-empty" className="notif-empty">Tidak ada notifikasi. Sistem dalam kondisi baik.</div>
            )}
            {notifications.length > 0 && filtered.length === 0 && (
              <div data-testid="notif-empty-filter" className="notif-empty">
                Tidak ada notifikasi yang cocok dengan filter ini.
              </div>
            )}
            {filtered.map((n) => {
              const Icon = n.type === "escalation" ? ArrowUpCircle : (SEVERITY_ICON[n.severity] || Info);
              const canApprove = n.action_type === "po_approve" && !n.read &&
                onApprove && canActOn(currentUserRole, n.action_role || "manager");
              return (
                <div
                  key={n.id}
                  data-testid={`notif-item-${n.id}`}
                  className={`notif-item sev-${n.severity || "info"} ${n.read ? "read" : "unread"}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => { if (!n.read) onMarkRead?.(n.id); if (n.link) onNavigate?.(n.link); setOpen(false); }}
                >
                  <div className="notif-item-icon"><Icon size={15} /></div>
                  <div className="notif-item-body">
                    <div className="notif-item-title">
                      {n.title}
                      {n.type === "escalation" && (
                        <span className="notif-escal-tag" data-testid={`notif-escalation-tag-${n.id}`}>
                          <ArrowUpCircle size={9} /> Eskalasi
                        </span>
                      )}
                    </div>
                    <div className="notif-item-text">{n.body}</div>
                    <div className="notif-item-foot">
                      <span className="notif-item-time">
                        {timeAgo(n.created_at)} · {typeLabel(n.type)}
                      </span>
                      {canApprove && (
                        <button
                          data-testid={`notif-approve-${n.id}`}
                          className="notif-approve-button"
                          title="Setujui PO langsung"
                          disabled={approving === n.id}
                          onClick={(e) => handleApprove(e, n)}
                        >
                          {approving === n.id ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                          {approving === n.id ? "Memproses..." : "Setujui"}
                        </button>
                      )}
                    </div>
                  </div>
                  {!n.read && (
                    <button
                      data-testid={`notif-read-${n.id}`}
                      className="notif-read-dot"
                      title="Tandai dibaca"
                      onClick={(e) => { e.stopPropagation(); onMarkRead?.(n.id); }}
                    >
                      <Check size={12} />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
