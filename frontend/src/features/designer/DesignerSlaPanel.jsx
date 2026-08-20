/**
 * DesignerSlaPanel (PS-18) — papan **eskalasi SLA** yang AKTIF.
 *
 * Bedanya dengan papan SLA lama di Laporan R&D: papan itu pasif (hanya menandai merah).
 * Di sini setiap baris menyebut sudah berapa hari terlambat DAN ke siapa peringatannya
 * dikirim otomatis (manager, lalu ikut ke admin bila sudah melewati ambang kebijakan).
 * Tombol "Kirim peringatan sekarang" hanya mempercepat job harian — idempotent, jadi
 * menekannya berulang kali tidak membanjiri siapa pun.
 */
import { AlertTriangle, BellRing, Clock, ShieldAlert } from "lucide-react";
import { SAMPLE_TYPE_LABEL } from "../rnd/rndMeta";
import { tierMeta } from "./designerMeta";

export default function DesignerSlaPanel({ board, filterDesigner, busy, canManage,
                                           onEscalate, runInfo }) {
  const items = (board?.items || []).filter(
    (r) => !filterDesigner || r.designer === filterDesigner);
  const adminDays = board?.escalate_admin_days ?? 3;

  return (
    <div className="section-card" data-testid="designer-sla-panel">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <ShieldAlert size={16} className="text-[#C0392B]" />
          <h2>Eskalasi SLA — round yang lewat tenggat</h2>
        </div>
        {canManage && (
          <button className="secondary-button" onClick={onEscalate} disabled={busy}
            data-testid="designer-sla-escalate-button">
            <BellRing size={13} className={busy ? "animate-pulse" : ""} />
            {busy ? "Mengirim…" : "Kirim peringatan sekarang"}
          </button>
        )}
      </div>
      <div className="section-body space-y-2">
        <p className="text-[11px] leading-relaxed text-[#6B6B73]"
          data-testid="designer-sla-policy-note">
          Setiap hari pukul <b>07:35</b> sistem memeriksa round sample yang belum selesai.
          Yang sudah lewat tenggat diberitahukan ke <b>manajer</b>; bila keterlambatannya
          mencapai <b>{adminDays} hari</b> peringatannya <b>ikut dinaikkan ke admin/pemilik</b>.
          Satu round hanya menghasilkan satu peringatan per hari (tidak berisik), dan
          pesannya juga terkirim lewat WhatsApp bila kanal itu aktif.
        </p>

        {runInfo && (
          <div className={`notice-bar ${runInfo.ok ? "success" : "danger"} !mb-0 !py-1.5`}
            data-testid="designer-sla-run-result">
            <span className="text-[11.5px]">{runInfo.message}</span>
          </div>
        )}

        {items.length === 0 ? (
          <div className="py-8 text-center" data-testid="designer-sla-empty">
            <Clock size={24} className="mx-auto mb-2 text-[#C7C9CF]" />
            <p className="text-[12.5px] font-semibold text-[#1B7F4B]">
              Tidak ada round yang lewat tenggat
            </p>
            <p className="mt-0.5 text-[11.5px] text-[#6B6B73]">
              {filterDesigner
                ? `${filterDesigner} tidak punya round yang menggantung saat ini.`
                : "Semua round sample masih dalam tenggat. Tidak ada peringatan yang perlu dikirim."}
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-2">
              <Mini label="Round terlambat" value={items.length} tone="#C0392B"
                testId="designer-sla-count" />
              <Mini label="Sudah naik ke admin" value={board?.admin_count ?? 0}
                tone="#8C1C13" testId="designer-sla-admin-count" />
              <Mini label="Terlama (hari)" value={board?.worst_days_late ?? 0}
                tone="#B26A00" testId="designer-sla-worst" />
            </div>
            <div className="max-h-[300px] divide-y divide-[#F4F5F7] overflow-y-auto">
              {items.map((r) => {
                const t = tierMeta(r.tier);
                return (
                  <div key={r.round_id} data-testid={`designer-sla-row-${r.round_id}`}
                    className="flex flex-wrap items-center gap-x-2 gap-y-1 py-1.5 text-[11.5px]">
                    <AlertTriangle size={12} className="shrink-0 text-[#C0392B]" />
                    <span className="font-bold text-[#0058CC]">{r.number}</span>
                    <span className="text-[#9A9BA3]">rnd {r.round_no}</span>
                    <span className="min-w-0 flex-1 truncate">
                      {r.title}
                      <span className="text-[#9A9BA3]">
                        {" · "}{SAMPLE_TYPE_LABEL[r.sample_type] || r.sample_type}
                        {r.supplier_name ? ` · ${r.supplier_name}` : ""}
                      </span>
                    </span>
                    <span className="truncate text-[#3C3C43]">{r.designer}</span>
                    <span className="tabular-nums text-[#6B6B73]">tenggat {r.due_date}</span>
                    <span className="font-bold tabular-nums text-[#C0392B]">
                      {r.days_late} hari
                    </span>
                    <span className={`status-pill ${t.cls}`}>{t.label}</span>
                    <span className="text-[10.5px] text-[#9A9BA3]">{r.state_label}</span>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Mini({ label, value, tone, testId }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2" data-testid={testId}>
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[14px] font-bold leading-tight tabular-nums" style={{ color: tone }}>
        {value}
      </p>
    </div>
  );
}
