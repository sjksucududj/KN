/**
 * EntityReadinessPanel (FASE E-3 / E1.9) — “apa lagi yang kurang?” per badan usaha.
 *
 * Badan usaha baru sering “lahir setengah jadi”: ada di daftar, tetapi belum punya
 * pengguna/rekening/harga — lalu orang menyimpulkan aplikasinya rusak karena
 * layarnya kosong. Panel ini menjawabnya dengan angka terhitung dan tombol yang
 * MENGANTAR ke layar penyelesaiannya, bukan sekadar daftar centang statis.
 */
import { useCallback, useEffect, useState } from "react";
import { ClipboardCheck, CheckCircle2, XCircle, ExternalLink, RefreshCw } from "lucide-react";

import { getReadiness, errText } from "./entityApi";

export default function EntityReadinessPanel({ entities = [], onNavigate, onError }) {
  const active = entities.filter((e) => e.status === "active");
  const [entityId, setEntityId] = useState(active[0]?.id || "");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!entityId && active.length) setEntityId(active[0].id);
  }, [active, entityId]);

  const load = useCallback(async () => {
    if (!entityId) return;
    setLoading(true);
    try {
      setData(await getReadiness(entityId));
    } catch (e) {
      onError?.(errText(e, "Gagal memuat daftar kesiapan."));
    } finally {
      setLoading(false);
    }
  }, [entityId, onError]);

  useEffect(() => { load(); }, [load]);

  const pct = data?.percent ?? 0;
  const tone = pct === 100 ? "#1B7F4B" : pct >= 60 ? "#B45309" : "#C0392B";

  return (
    <div className="section-card" data-testid="entity-readiness-panel">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <ClipboardCheck size={15} className="text-[#6B219A]" />
          <h2 data-testid="entity-readiness-title">Kesiapan Badan Usaha</h2>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {active.map((e) => (
            <button key={e.id} type="button" data-testid={`readiness-pick-${e.id}`}
                    onClick={() => setEntityId(e.id)}
                    className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                      entityId === e.id ? "bg-[#6B219A] text-white"
                        : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
              {e.short_name || e.legal_name}
            </button>
          ))}
          <button type="button" className="icon-button" aria-label="Muat ulang"
                  data-testid="readiness-refresh" onClick={load}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <div className="section-body">
        {loading && !data ? (
          <div className="grid gap-2" data-testid="readiness-loading">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-[#F5F5F7]" />
            ))}
          </div>
        ) : !data ? (
          <p className="py-8 text-center text-[12px] text-[#8E8E93]" data-testid="readiness-empty">
            Pilih badan usaha untuk melihat daftar kesiapannya.
          </p>
        ) : (
          <>
            <div className="mb-3 rounded-md border px-3 py-2"
                 data-testid="readiness-summary"
                 style={{ borderColor: pct === 100 ? "#BFE3CC" : "#F0C88A",
                          background: pct === 100 ? "#EEF9F1" : "#FEF7EC" }}>
              <p className="text-[12px] font-bold text-[#1C1C1E]">
                {data.ready} dari {data.total} hal sudah siap
                <span className="ml-2 tabular-nums" style={{ color: tone }}>({pct}%)</span>
              </p>
              <p className="text-[10.5px] text-[#6B6B73]">
                {pct === 100
                  ? "Badan usaha ini sudah lengkap dan siap dipakai transaksi sehari-hari."
                  : "Selesaikan baris bertanda merah di bawah. Selama belum lengkap, sebagian "
                    + "layar bisa terlihat kosong — bukan karena rusak, tetapi karena datanya "
                    + "memang belum ada."}
              </p>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white">
                <div style={{ width: `${pct}%`, background: tone }} className="h-full" />
              </div>
            </div>

            <div className="grid gap-1.5">
              {(data.items || []).map((it) => (
                <div key={it.key}
                     data-testid={`readiness-item-${it.key}`}
                     className={`flex flex-wrap items-start gap-2 rounded-md border px-3 py-2 ${
                       it.ready ? "border-[#EFF0F2] bg-white"
                                : "border-[#F0B5AE] bg-[#FFF8F7]"}`}>
                  {it.ready
                    ? <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-[#1B7F4B]" />
                    : <XCircle size={14} className="mt-0.5 shrink-0 text-[#C0392B]" />}
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-bold text-[#1C1C1E]">{it.label}</p>
                    <p className="text-[11px] text-[#3C3C43]">{it.detail}</p>
                    {!it.ready && (
                      <p className="text-[10.5px] text-[#6B6B73]">{it.how_to}</p>
                    )}
                  </div>
                  {it.view && onNavigate && (
                    <button type="button"
                            data-testid={`readiness-goto-${it.key}`}
                            className="secondary-button !py-1 !px-2 !text-[10.5px]"
                            onClick={() => onNavigate(it.view)}>
                      {it.ready ? "Lihat" : "Lengkapi"} <ExternalLink size={10} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
