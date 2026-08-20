/**
 * DocTraceView — FASE G-4 · layar **JEJAK DOKUMEN**.
 *
 * Masalah nyata pemilik: "SO customer pending → KN harus PO ke supplier → banyak
 * surat lahir tapi saling tidak mereferensikan → tracking & penelusuran retur susah."
 *
 * Layar ini menjawabnya: mulai dari surat MANA PUN (termasuk dari tengah rantai),
 * lihat seluruh dokumen yang berkaitan, lompat ke dokumennya, dan bagikan tautan
 * (QR pada dokumen cetak mengarah ke halaman ini).
 *
 * Semua angka & urutan tahap berasal dari `GET /documents/trace/...` (backend),
 * bukan hitungan ulang di browser — supaya kertas, layar, dan invarian satu cerita.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Copy, ExternalLink, GitBranch, Link as LinkIcon, Loader2, QrCode, RefreshCw, Route, Settings2,
} from "lucide-react";
import EntityBadge from "../../../components/EntityBadge";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency } from "../../../utils/formatters";
import { openConfig } from "../../settings/config/configDeepLink";
import TraceBackfill from "./TraceBackfill";
import TraceGraph from "./TraceGraph";
import TraceSearch from "./TraceSearch";
import { errText, fetchTrace, shortDate, traceUrl } from "./traceApi";

const DEPTHS = [1, 2, 3, 4, 6, 8];

function Kpi({ label, value, tone = "#1C1C1E", testId }) {
  return (
    <div data-testid={testId} className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
      <p className="text-[14px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
    </div>
  );
}

export default function DocTraceView({
  currentUser, selectedEntity, anchor, anchorNonce, onOpenDocument, onAnchorConsumed,
}) {
  const [cur, setCur] = useState(null);          // {docType, docId}
  const [trace, setTrace] = useState(null);
  const [depth, setDepth] = useState(0);          // 0 = pakai aturan admin
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState([]);

  const isAdmin = currentUser?.role === "admin";

  const load = useCallback(async (target, d) => {
    if (!target?.docType || !target?.docId) return;
    setLoading(true);
    try {
      const res = await fetchTrace(target.docType, target.docId, d || 0);
      setTrace(res);
      setError("");
    } catch (e) {
      setTrace(null);
      setError(errText(e, "Gagal memuat jejak dokumen."));
    } finally { setLoading(false); }
  }, []);

  // Jangkar dari deep-link (tombol panel detail / QR dokumen cetak).
  useEffect(() => {
    if (!anchor?.docType || !anchor?.docId) return;
    setCur({ docType: anchor.docType, docId: anchor.docId });
    setHistory([]);
    load({ docType: anchor.docType, docId: anchor.docId }, depth);
    if (onAnchorConsumed) onAnchorConsumed();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchorNonce, anchor?.docId]);

  const pick = (node) => {
    const next = { docType: node.doc_type, docId: node.doc_id };
    if (cur && cur.docId === next.docId) return;      // sudah jadi jangkar
    if (cur) setHistory((h) => [...h.slice(-8), cur]); // riwayat maks 9 langkah
    setCur(next);
    load(next, depth);
  };

  const back = () => {
    const prev = history[history.length - 1];
    if (!prev) return;
    setHistory((h) => h.slice(0, -1));
    setCur(prev);
    load(prev, depth);
  };

  const changeDepth = (d) => {
    setDepth(d);
    if (cur) load(cur, d);
  };

  const copyLink = async () => {
    if (!cur) return;
    const url = traceUrl(cur.docType, cur.docId);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { setError(`Tautan: ${url}`); }
  };

  const a = trace?.anchor;

  return (
    <div data-testid="doc-trace-view">
      <ErrorNotice message={error} onRetry={() => cur && load(cur, depth)}
        onDismiss={() => setError("")} testId="trace-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex min-w-0 items-center gap-2">
            <Route size={16} className="text-[#0058CC]" />
            <div className="min-w-0">
              <h2 data-testid="trace-title">Jejak Dokumen</h2>
              <p className="text-[11px] text-[#6B6B73]">
                Telusuri seluruh surat yang berkaitan — dari pesanan, surat jalan, faktur,
                kwitansi, sampai retur & tagihan supplier. Bisa dimulai dari dokumen mana pun.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isAdmin && (
              <button className="secondary-button" data-testid="trace-open-config"
                onClick={() => openConfig({ group: "dokumen" })}>
                <Settings2 size={13} /> Aturan Relasi & Cetak
              </button>
            )}
            <button className="secondary-button" data-testid="trace-refresh"
              onClick={() => cur && load(cur, depth)} disabled={!cur}>
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[380px_1fr] lg:items-start">
        <div className="grid gap-3">
          <TraceSearch entityId={selectedEntity} onPick={pick} onError={setError} />
          {isAdmin && <TraceBackfill onDone={() => cur && load(cur, depth)} />}
        </div>

        <div className="grid gap-3">
          {!cur && !loading && (
            <section className="section-card" data-testid="trace-idle">
              <div className="section-body flex flex-col items-center justify-center gap-2 py-16 text-center">
                <GitBranch size={30} className="text-[#C4C5CC]" />
                <p className="text-[12.5px] font-semibold text-[#3C3C43]">Pilih dokumen untuk ditelusuri</p>
                <p className="max-w-md text-[11.5px] text-[#6B6B73]">
                  Cari nomor surat di panel kiri, atau tekan tombol <b>Jejak Dokumen</b> pada
                  detail Pesanan, Purchase Order, Tagihan Supplier, Kwitansi, dan Penerimaan Barang.
                  QR pada dokumen cetak juga membuka halaman ini.
                </p>
              </div>
            </section>
          )}

          {loading && (
            <section className="section-card" data-testid="trace-loading">
              <div className="section-body flex items-center justify-center gap-2 py-16 text-[12px] text-[#6B6B73]">
                <Loader2 size={18} className="animate-spin text-[#0058CC]" /> Menelusuri rantai dokumen…
              </div>
            </section>
          )}

          {!loading && a && (
            <>
              <section className="section-card" data-testid="trace-anchor-card">
                <div className="section-head">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="rounded bg-[#EFF4FF] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[#0058CC]">
                      {a.label}
                    </span>
                    <h3 data-testid="trace-anchor-number" className="truncate text-[13px] font-bold text-[#0B1B3B]">
                      {a.number}
                    </h3>
                    <EntityBadge entityId={a.entity_id} />
                  </div>
                  <div className="flex items-center gap-2">
                    {history.length > 0 && (
                      <button className="secondary-button" onClick={back} data-testid="trace-back">
                        Kembali
                      </button>
                    )}
                    {a.link?.view && onOpenDocument && (
                      <button className="secondary-button" data-testid="trace-open-anchor"
                        onClick={() => onOpenDocument(a.link)}>
                        <ExternalLink size={13} /> Buka dokumen
                      </button>
                    )}
                    <button className="secondary-button" data-testid="trace-copy-link" onClick={copyLink}>
                      {copied ? <QrCode size={13} /> : <Copy size={13} />} {copied ? "Tersalin" : "Salin tautan"}
                    </button>
                  </div>
                </div>
                <div className="section-body space-y-2.5">
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-5" data-testid="trace-kpis">
                    <Kpi testId="trace-kpi-docs" label="Dokumen terkait" value={String(trace.node_count || 0)} />
                    <Kpi testId="trace-kpi-edges" label="Relasi" value={String(trace.edge_count || 0)} tone="#0058CC" />
                    <Kpi testId="trace-kpi-depth" label="Kedalaman" value={String(trace.depth || 0)} />
                    <Kpi testId="trace-kpi-status" label="Status dokumen" value={a.status || "—"} />
                    <Kpi testId="trace-kpi-amount" label="Nilai dokumen"
                      value={Number(a.amount) > 0 ? formatCurrency(a.amount) : "—"} tone="#1B7A43" />
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-[11px] text-[#6B6B73]">
                      {a.title || "—"} · {shortDate(a.date)}
                    </p>
                    <div className="flex items-center gap-1.5" data-testid="trace-depth-picker">
                      <span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Kedalaman</span>
                      <button type="button" data-testid="trace-depth-auto" onClick={() => changeDepth(0)}
                        className={`rounded-full border px-2.5 py-0.5 text-[10.5px] font-medium ${depth === 0
                          ? "border-[#0058CC] bg-[#0058CC] text-white"
                          : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>
                        Aturan admin
                      </button>
                      {DEPTHS.map((d) => (
                        <button key={d} type="button" data-testid={`trace-depth-${d}`} onClick={() => changeDepth(d)}
                          className={`rounded-full border px-2.5 py-0.5 text-[10.5px] font-medium ${depth === d
                            ? "border-[#0058CC] bg-[#0058CC] text-white"
                            : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>
                          {d}
                        </button>
                      ))}
                    </div>
                  </div>
                  {Number(trace.truncated) > 0 && (
                    <div className="notice-bar warning !py-1.5" data-testid="trace-truncated">
                      <span className="text-[11.5px]">
                        Masih ada {trace.truncated} tautan di luar kedalaman ini — naikkan kedalaman untuk melihat lebih jauh.
                      </span>
                    </div>
                  )}
                  <p className="flex items-center gap-1 text-[10.5px] text-[#8E8E93]">
                    <LinkIcon size={11} /> QR pada dokumen cetak mengarah ke halaman ini:
                    <code className="rounded bg-[#F2F3F5] px-1" data-testid="trace-public-url">
                      /jejak-dokumen/{cur?.docType}/{cur?.docId}
                    </code>
                  </p>
                </div>
              </section>

              {/* Dokumen yang benar-benar berdiri sendiri: katakan apa adanya + jalan keluarnya. */}
              {Number(trace.node_count) <= 1 && (
                <section className="section-card" data-testid="trace-no-relations">
                  <div className="section-body py-10 text-center">
                    <GitBranch size={26} className="mx-auto mb-2 text-[#C4C5CC]" />
                    <p className="text-[12.5px] font-semibold text-[#3C3C43]">
                      Belum ada surat lain yang tertaut ke dokumen ini.
                    </p>
                    <p className="mx-auto mt-1 max-w-md text-[11.5px] text-[#6B6B73]">
                      Dokumen turunan akan menaut otomatis saat lahir. Untuk dokumen lama,
                      admin dapat menjalankan <b>Susun Ulang Relasi</b> di panel kiri.
                    </p>
                  </div>
                </section>
              )}

              <TraceGraph trace={trace} loading={loading} onAnchor={pick}
                onOpen={(n) => onOpenDocument && onOpenDocument(n.link)} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
