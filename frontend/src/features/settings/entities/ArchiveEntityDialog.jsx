/**
 * ArchiveEntityDialog (FASE E-3 / E1.6) — arsipkan badan usaha dengan MATA TERBUKA.
 *
 * Prinsipnya: jangan pernah menutup badan usaha lalu membuat pengguna bertanya-tanya
 * kenapa layarnya kosong. Dialog ini memuat PRATINJAU DAMPAK dari server dulu
 * (pengguna aktif, dokumen terbuka, saldo hidup, periode belum tutup); tombol
 * “Arsipkan” baru aktif kalau bersih. Bila memang harus dipaksa, alasan WAJIB dan
 * hanya admin yang boleh — sama seperti aturan servernya, jadi tidak ada kejutan.
 */
import { useEffect, useState } from "react";
import { AlertTriangle, Archive, Loader2, X, Users, FileText, Wallet, CalendarClock } from "lucide-react";

import { getDeactivationImpact, archiveEntity, errText, errBlockers } from "./entityApi";
import { formatCurrency } from "../../../utils/formatters";

const ICONS = { pengguna: Users, dokumen: FileText, saldo: Wallet, periode: CalendarClock };

export default function ArchiveEntityDialog({ entity, onClose, onDone }) {
  const [impact, setImpact] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState("");
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [blockers, setBlockers] = useState([]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await getDeactivationImpact(entity.id);
        if (alive) setImpact(d);
      } catch (e) {
        if (alive) setError(errText(e, "Gagal memuat pratinjau dampak."));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [entity.id]);

  const submit = async () => {
    setBusy(true);
    setError("");
    setBlockers([]);
    try {
      const res = await archiveEntity(entity.id, { reason, force });
      onDone?.(
        `“${entity.legal_name || entity.short_name}” diarsipkan. ` +
        `${res.sessions_revoked || 0} sesi pengguna dicabut — badan usaha ini tidak bisa ` +
        "lagi menerima transaksi baru, tetapi datanya tetap bisa dibaca."
      );
    } catch (e) {
      setError(errText(e, "Gagal mengarsipkan badan usaha."));
      setBlockers(errBlockers(e));
    } finally {
      setBusy(false);
    }
  };

  const clean = impact?.can_archive;

  return (
    <div className="modal-overlay" data-testid="entity-archive-dialog"
         onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="modal-card" style={{ maxWidth: 640, width: "94vw" }}>
        <div className="flex items-start gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <Archive size={16} className="mt-0.5 text-[#8C4A00]" />
          <div className="min-w-0 flex-1">
            <h3 className="text-[13.5px] font-bold">
              Arsipkan “{entity.legal_name || entity.short_name}”?
            </h3>
            <p className="text-[11px] text-[#6B6B73]">
              Badan usaha yang diarsipkan <b>tidak bisa lagi menerima transaksi baru</b>.
              Data lamanya tetap tersimpan dan bisa dibaca, jadi ini bukan penghapusan.
            </p>
          </div>
          <button type="button" className="icon-button" aria-label="Tutup"
                  data-testid="entity-archive-close" onClick={onClose}>
            <X size={14} />
          </button>
        </div>

        <div className="space-y-3 p-4">
          {loading ? (
            <div className="grid gap-2" data-testid="entity-archive-loading">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-9 animate-pulse rounded bg-[#F5F5F7]" />
              ))}
            </div>
          ) : (
            <>
              <div
                data-testid="entity-archive-verdict"
                className={`rounded-md border px-3 py-2 ${
                  clean ? "border-[#BFE3CC] bg-[#EEF9F1]" : "border-[#F0C88A] bg-[#FEF7EC]"
                }`}
              >
                <p className="flex items-center gap-1.5 text-[11.5px] font-bold text-[#1C1C1E]">
                  {clean ? "Aman diarsipkan — tidak ada yang tertinggal."
                         : "Belum bisa diarsipkan — masih dipakai:"}
                </p>
                {!clean && (
                  <ul className="mt-1 space-y-1" data-testid="entity-archive-blockers">
                    {(impact?.blockers || []).map((b, i) => {
                      const key = Object.keys(ICONS).find((k) => b.toLowerCase().includes(k));
                      const Icon = ICONS[key] || AlertTriangle;
                      return (
                        <li key={i} className="flex items-start gap-1.5 text-[11px] text-[#3C3C43]"
                            data-testid={`entity-archive-blocker-${i}`}>
                          <Icon size={12} className="mt-0.5 shrink-0 text-[#8C4A00]" />
                          <span>{b}</span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <div className="grid gap-2 sm:grid-cols-2">
                <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5"
                     data-testid="entity-archive-users">
                  <p className="kicker">Pengguna aktif</p>
                  <p className="text-[15px] font-bold tabular-nums">
                    {(impact?.active_users || []).length}
                  </p>
                  <p className="text-[10px] text-[#6B6B73]">
                    {(impact?.home_users || []).length} di antaranya berbadan-usaha utama di sini
                    {(impact?.home_users || []).length > 0
                      ? " — sesinya akan dicabut dan mereka tidak bisa masuk lagi"
                      : ""}
                  </p>
                </div>
                <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5"
                     data-testid="entity-archive-docs">
                  <p className="kicker">Dokumen terbuka</p>
                  <p className="text-[15px] font-bold tabular-nums">
                    {impact?.open_documents_total ?? 0}
                  </p>
                  <p className="text-[10px] text-[#6B6B73]">
                    {(impact?.open_documents || []).slice(0, 3)
                      .map((d) => `${d.label} (${d.count})`).join(" · ") || "Tidak ada"}
                  </p>
                </div>
              </div>

              {(impact?.balances || []).length > 0 && (
                <div className="rounded-md border border-[#EFF0F2] p-2.5"
                     data-testid="entity-archive-balances">
                  <p className="kicker mb-1">Saldo yang masih hidup</p>
                  {impact.balances.map((b) => (
                    <p key={b.key} className="flex justify-between text-[11.5px]"
                       data-testid={`entity-archive-balance-${b.key}`}>
                      <span className="text-[#3C3C43]">{b.label}</span>
                      <b className="tabular-nums">
                        {b.unit ? `${b.amount} ${b.unit}` : formatCurrency(b.amount)}
                      </b>
                    </p>
                  ))}
                </div>
              )}

              {impact?.first_document && (
                <p className="text-[10.5px] text-[#6B6B73]" data-testid="entity-archive-first-doc">
                  Badan usaha ini sudah menerbitkan dokumen — yang pertama:{" "}
                  <b>{impact.first_document.number}</b> ({impact.first_document.label}).
                  Karena itu kode dokumennya tidak bisa diubah lagi.
                </p>
              )}

              {!clean && (
                <div className="rounded-md border border-[#F0B5AE] bg-[#FCEBEA] p-2.5">
                  <label className="flex items-start gap-2 text-[11.5px] font-semibold text-[#A8221A]">
                    <input
                      type="checkbox"
                      data-testid="entity-archive-force"
                      checked={force}
                      onChange={(e) => setForce(e.target.checked)}
                      className="mt-0.5"
                    />
                    <span>
                      Saya tetap ingin mengarsipkan sekarang (paksa). Hanya admin, dan
                      alasannya dicatat di jejak audit.
                    </span>
                  </label>
                  {force && (
                    <textarea
                      className="field mt-2"
                      rows={2}
                      data-testid="entity-archive-reason"
                      placeholder="Alasan (wajib) — mis. badan usaha digabung ke PT lain per 1 Januari…"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  )}
                </div>
              )}

              {error && (
                <div className="notice-bar danger !py-1.5" data-testid="entity-archive-error">
                  <span className="text-[11.5px]">{error}</span>
                </div>
              )}
              {blockers.length > 0 && (
                <ul className="space-y-1" data-testid="entity-archive-error-blockers">
                  {blockers.map((b, i) => (
                    <li key={i} className="text-[11px] text-[#A8221A]">• {b}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button type="button" className="secondary-button"
                  data-testid="entity-archive-cancel" onClick={onClose}>
            Batal
          </button>
          <button
            type="button"
            className="danger-button"
            data-testid="entity-archive-submit"
            disabled={busy || loading || (!clean && (!force || !reason.trim()))}
            onClick={submit}
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Archive size={13} />}
            {clean ? "Arsipkan" : "Arsipkan (paksa)"}
          </button>
        </div>
      </div>
    </div>
  );
}
