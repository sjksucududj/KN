/**
 * InternalRequestsView — FASE E-7 (E7d) · **PERMINTAAN INTERNAL** (`<ENT>/PIN-#####`).
 *
 * Layar dua peran dalam satu tempat, karena keduanya membicarakan dokumen yang sama:
 *  - **Sales**: mengajukan permintaan barang dari badan usaha lain (papan stok memberi
 *    isyarat “tersedia di badan usaha lain”, dan dulu isyarat itu berakhir buntu),
 *    melihat statusnya, membatalkan miliknya.
 *  - **Admin/Manajer**: ANTREAN — memilih badan usaha sumber (lengkap dengan bukti stok
 *    & kesiapan harga internalnya) lalu menjadikannya **transaksi Antar-PT** (mesin G-6),
 *    atau menolak dengan alasan yang terbaca peminta.
 *
 * Di FASE E-8 antrean ini pindah ke Meja Admin Sales (`sales_admin`) — mesinnya
 * JANGAN ditulis ulang, cukup dipindah tempat tampilnya.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeftRight, ArrowLeft, Plus, RefreshCw, Inbox, CheckCircle2, XCircle,
  Ban, Building2, AlertTriangle, PackageCheck, Clock3,
} from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import QtyDual from "../../components/QtyDual";      // FASE U — dua satuan
import { formatCurrency, formatQty } from "../../utils/formatters";
import InternalRequestCreateModal from "./InternalRequestCreateModal";
import {
  apiText, cancelInternalRequest, convertInternalRequest, getInternalRequest,
  internalRequestSources, listInternalRequests, PIN_STATUS_CLASS, PIN_STATUS_LABEL,
  pinMeta, rejectInternalRequest,
} from "./internalRequestsApi";

export default function InternalRequestsView({ currentUser, selectedEntity = "all" }) {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState({});
  const [meta, setMeta] = useState({ can_decide: false, can_pick_source: false });
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [detail, setDetail] = useState(null);
  const [showCreate, setShowCreate] = useState(false);

  const canDecide = !!meta.can_decide;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const res = await listInternalRequests(params);
      setItems(res.items || []);
      setSummary(res.summary || {});
      setError("");
    } catch (e) {
      setError(apiText(e, "Gagal memuat permintaan internal."));
    } finally { setLoading(false); }
  }, [statusFilter, selectedEntity]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { pinMeta().then(setMeta).catch(() => {}); }, []);

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 4000); }

  async function openDetail(id) {
    try { setDetail(await getInternalRequest(id)); }
    catch (e) { flash(apiText(e, "Gagal memuat detail permintaan.")); }
  }

  const tabs = [
    { key: "", label: "Semua" },
    { key: "submitted", label: "Antrean" },
    { key: "converted", label: "Jadi transaksi antar-PT" },
    { key: "rejected", label: "Ditolak" },
    { key: "cancelled", label: "Dibatalkan" },
  ];

  if (detail) {
    return (
      <DetailPanel
        req={detail} canDecide={canDecide} currentUser={currentUser}
        onBack={() => { setDetail(null); load(); }}
        onChanged={(msg, fresh) => { flash(msg); if (fresh) setDetail(fresh); load(); }}
      />
    );
  }

  return (
    <div data-testid="internal-requests-view" className="grid gap-4">
      {toast && (
        <div className="notice-bar success" data-testid="pin-toast">
          <span>{toast}</span><button onClick={() => setToast("")}>×</button>
        </div>
      )}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="pin-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex min-w-0 items-center gap-2">
            <ArrowLeftRight size={15} className="text-[#0058CC]" />
            <span className="kicker">Antar Entitas</span>
            <h2 data-testid="pin-title">Permintaan Internal (PIN)</h2>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="pin-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
            <button data-testid="pin-create-btn" className="btn-primary" onClick={() => setShowCreate(true)}>
              <Plus size={14} /> Permintaan Baru
            </button>
          </div>
        </div>

        <p className="px-3 pt-2 text-[11.5px] leading-relaxed text-[#6B6B73]">
          Minta barang dari badan usaha lain di dalam grup. Permintaan yang disetujui menjadi
          <b> transaksi Antar-PT</b>: dokumen kembar di kedua badan usaha, harga dari kontrak
          internal, PPN &amp; faktur pajak berpasangan, dan margin grup ikut dieliminasi di
          laporan konsolidasi. {canDecide
            ? "Anda berwenang memilih badan usaha sumber & menindak antrean ini."
            : "Admin/manajer yang menentukan barang diambil dari badan usaha mana."}
        </p>

        <section data-testid="pin-metrics" className="grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric icon={Inbox} label="Antrean" value={summary.open_count || 0}
                  tone="rgba(255,149,0,.16)" testId="pin-metric-open" />
          <Metric icon={Clock3} label="Nilai Taksiran Antrean" value={formatCurrency(summary.open_value || 0)}
                  tone="rgba(0,122,255,.12)" testId="pin-metric-open-value" />
          <Metric icon={PackageCheck} label="Jadi Transaksi Antar-PT"
                  value={(summary.by_status || {}).converted || 0}
                  tone="rgba(52,199,89,.15)" testId="pin-metric-converted" />
          <Metric icon={XCircle} label="Ditolak" value={(summary.by_status || {}).rejected || 0}
                  tone="rgba(255,59,48,.14)" testId="pin-metric-rejected" />
        </section>

        <div className="flex flex-wrap gap-1.5 px-3 pb-3">
          {tabs.map((t) => (
            <button key={t.key || "all"} data-testid={`pin-tab-${t.key || "all"}`}
              className={`tab-button ${statusFilter === t.key ? "active" : ""}`}
              onClick={() => setStatusFilter(t.key)}>{t.label}</button>
          ))}
        </div>
      </section>

      <section className="section-card">
        <div className="overflow-x-auto">
          <div className="grid grid-cols-[110px_1.4fr_150px_140px_170px_100px] border-b border-[#EFF0F2] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
            <span>Nomor</span><span>Barang</span><span>Sumber / Hasil</span>
            <span className="text-right pr-3">Taksiran</span><span className="pl-1">Status</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div data-testid="pin-loading" className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
          ) : items.length === 0 ? (
            <div data-testid="pin-empty" className="py-12 text-center text-[12px] text-[#6B6B73]">
              Belum ada permintaan internal. Papan Stok akan menandai barang yang
              <b> tersedia di badan usaha lain</b> — dari sana Anda bisa langsung meminta.
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2]">
              {items.map((r) => (
                <div key={r.id} data-testid={`pin-row-${r.id}`}
                     className="grid grid-cols-[110px_1.4fr_150px_140px_170px_100px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{r.number}</span>
                  <div className="min-w-0">
                    <p className="truncate text-[12px] font-semibold">
                      {r.items?.[0]?.product_name || "—"}
                      {r.items?.length > 1 ? ` +${r.items.length - 1}` : ""}
                    </p>
                    <p className="truncate text-[10.5px] text-[#9A9BA3]">
                      {r.requested_by} · {r.reason}
                      {r.source_order_number ? ` · untuk ${r.source_order_number}` : ""}
                    </p>
                  </div>
                  <div className="min-w-0 text-[10.5px]">
                    {r.interco_number_buyer ? (
                      <span data-testid={`pin-ic-${r.id}`} className="font-semibold text-[#1B7F4B]">
                        {r.interco_number_buyer}
                      </span>
                    ) : r.source_entity_name ? (
                      <span className="text-[#6B6B73]">{r.source_entity_name}</span>
                    ) : (
                      <span className="text-[#9A9BA3] italic">belum ditentukan</span>
                    )}
                  </div>
                  <span className="pr-3 text-right text-[12px] font-semibold tabular-nums">
                    ≈ {formatCurrency(r.est_value)}
                  </span>
                  <PinStatus status={r.status} />
                  <div className="text-right">
                    <button data-testid={`pin-open-${r.id}`} className="btn-secondary btn-xs"
                            onClick={() => openDetail(r.id)}>Detail</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <InternalRequestCreateModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={(doc) => { setShowCreate(false); flash(`${doc.number} diajukan — menunggu ditindak admin/manajer.`); load(); }}
      />
    </div>
  );
}

export function PinStatus({ status }) {
  return (
    <span data-testid={`pin-status-${status}`}
          className={`inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-[10px] font-bold ${PIN_STATUS_CLASS[status] || ""}`}>
      {PIN_STATUS_LABEL[status] || status}
    </span>
  );
}

function Metric({ icon: Icon, label, value, tone, testId }) {
  return (
    <div data-testid={testId} className="metric-card">
      <div className="metric-icon" style={{ background: tone }}><Icon size={16} className="text-[#1C1C1E]" /></div>
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
        <p className="text-[15px] font-bold tabular-nums">{value}</p>
      </div>
    </div>
  );
}

/* ═════════════════════════════════════════════════════════════════════
   DETAIL + KEPUTUSAN
   ════════════════════════════════════════════════════════════════════ */
function DetailPanel({ req, canDecide, currentUser, onBack, onChanged }) {
  const [sources, setSources] = useState(null);
  const [loadingSrc, setLoadingSrc] = useState(false);
  const [pickedEntity, setPickedEntity] = useState(req.source_entity_id || "");
  const [submitNow, setSubmitNow] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const isOpen = req.status === "submitted";
  const isOwner = req.requested_by_id && req.requested_by_id === currentUser?.id;

  const loadSources = useCallback(async () => {
    if (!canDecide || !isOpen) return;
    setLoadingSrc(true);
    try { setSources(await internalRequestSources(req.id)); }
    catch (e) { setErr(apiText(e, "Gagal memuat kandidat badan usaha sumber.")); }
    finally { setLoadingSrc(false); }
  }, [canDecide, isOpen, req.id]);

  useEffect(() => { loadSources(); }, [loadSources]);

  const candidates = sources?.candidates || [];
  const picked = useMemo(() => candidates.find((c) => c.entity_id === pickedEntity) || null,
    [candidates, pickedEntity]);

  async function doConvert() {
    if (!pickedEntity) { setErr("Pilih badan usaha sumber dulu."); return; }
    setBusy(true); setErr("");
    try {
      const res = await convertInternalRequest(req.id, {
        source_entity_id: pickedEntity, submit_now: submitNow,
      });
      onChanged?.(
        `${req.number} menjadi transaksi antar-PT ${res.request.interco_number_buyer} ⇄ ${res.request.interco_number_seller}.`,
        res.request);
    } catch (e) { setErr(apiText(e, "Gagal mengubah menjadi transaksi antar-PT.")); }
    finally { setBusy(false); }
  }

  async function doReject() {
    setBusy(true); setErr("");
    try {
      const fresh = await rejectInternalRequest(req.id, rejectReason);
      setShowReject(false);
      onChanged?.(`${req.number} ditolak.`, fresh);
    } catch (e) { setErr(apiText(e, "Gagal menolak permintaan.")); }
    finally { setBusy(false); }
  }

  async function doCancel() {
    setBusy(true); setErr("");
    try {
      const fresh = await cancelInternalRequest(req.id, "dibatalkan pengaju");
      onChanged?.(`${req.number} dibatalkan.`, fresh);
    } catch (e) { setErr(apiText(e, "Gagal membatalkan permintaan.")); }
    finally { setBusy(false); }
  }

  return (
    <div data-testid="pin-detail" className="grid gap-4">
      <section className="section-card">
        <div className="section-head">
          <div className="flex min-w-0 items-center gap-2">
            <button className="icon-button" onClick={onBack} aria-label="Kembali"><ArrowLeft size={15} /></button>
            <h2 data-testid="pin-detail-number">{req.number}</h2>
            <PinStatus status={req.status} />
          </div>
          <div className="flex items-center gap-2">
            {isOpen && (isOwner || canDecide) && (
              <button data-testid="pin-cancel-btn" className="btn-secondary" disabled={busy} onClick={doCancel}>
                <Ban size={13} /> Batalkan
              </button>
            )}
            {isOpen && canDecide && (
              <button data-testid="pin-reject-btn" className="btn-secondary" disabled={busy}
                      onClick={() => setShowReject(true)}>
                <XCircle size={13} /> Tolak
              </button>
            )}
          </div>
        </div>

        {err && <div className="notice-bar danger" data-testid="pin-detail-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}

        <div className="grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Peminta" value={`${req.requested_by} (${req.requester_entity_name})`} testId="pin-f-requester" />
          <Field label="Alasan" value={req.reason} testId="pin-f-reason" />
          <Field label="Dibutuhkan Sebelum" value={req.needed_date || "—"} testId="pin-f-needed" />
          <Field label="Untuk Pesanan" value={req.source_order_number || "—"} testId="pin-f-order" />
          <Field label="Badan Usaha Sumber" value={req.source_entity_name || "belum ditentukan"} testId="pin-f-source" />
          <Field label="Taksiran Nilai" value={`≈ ${formatCurrency(req.est_value)}`} testId="pin-f-est"
                 hint="HPP/harga master × jumlah — harga final memakai kontrak internal" />
          {req.interco_number_buyer && (
            <Field label="Transaksi Antar-PT" testId="pin-f-interco"
                   value={`${req.interco_number_buyer} ⇄ ${req.interco_number_seller}`} />
          )}
          {req.decision_reason && (
            <Field label="Alasan Keputusan" value={req.decision_reason} testId="pin-f-decision" />
          )}
        </div>
      </section>

      {/* Barang yang diminta + bukti ketersediaan saat diajukan */}
      <section className="section-card">
        <div className="section-head"><h2>Barang Diminta</h2></div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]" data-testid="pin-items-table">
            <thead className="bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73]">
              <tr>
                <th className="px-3 py-1.5 text-left">Barang</th>
                <th className="px-3 py-1.5 text-right">Diminta</th>
                <th className="px-3 py-1.5 text-right">Saat diajukan: di badan usaha lain</th>
                <th className="px-3 py-1.5 text-right">Taksiran</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F4F5F7]">
              {(req.items || []).map((it) => {
                const snap = (req.availability_snapshot || []).find((s) => s.product_id === it.product_id);
                return (
                  <tr key={it.product_id} data-testid={`pin-item-${it.product_id}`}>
                    <td className="px-3 py-2">
                      <p className="font-semibold">{it.product_name}</p>
                      <p className="text-[10.5px] text-[#8E8E93]">{it.sku}{it.notes ? ` · ${it.notes}` : ""}</p>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums"><QtyDual rolls={it.qty_rolls} measure={it.quantity} unit={it.unit} /></td>
                    <td className="px-3 py-2 text-right tabular-nums text-[#6B6B73]">
                      {snap ? formatQty(snap.other_entities_available) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">≈ {formatCurrency(it.est_value)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="px-3 py-2 text-[10.5px] text-[#9A9BA3]">
          Kolom ketiga adalah <b>cuplikan saat permintaan diajukan</b> — stok bergerak, dan
          tanpa cuplikan ini permintaan yang ditolak dua hari kemudian terlihat seperti
          permintaan ngawur.
        </p>
      </section>

      {/* ANTREAN: pilih badan usaha sumber (bukti stok + kesiapan harga internal) */}
      {canDecide && isOpen && (
        <section className="section-card" data-testid="pin-sources">
          <div className="section-head">
            <div className="flex items-center gap-2">
              <Building2 size={15} className="text-[#0058CC]" />
              <h2>Ambil dari Badan Usaha Mana?</h2>
            </div>
            <button className="icon-button" onClick={loadSources} aria-label="Muat ulang kandidat">
              <RefreshCw size={14} className={loadingSrc ? "animate-spin" : ""} />
            </button>
          </div>

          {loadingSrc && <div className="py-8 text-center text-[12px] text-[#6B6B73]">Memeriksa stok &amp; harga internal…</div>}

          {!loadingSrc && candidates.length === 0 && (
            <div className="py-8 text-center text-[12px] text-[#6B6B73]">
              Tidak ada badan usaha lain yang bisa dinilai.
            </div>
          )}

          <div className="grid gap-2 p-3">
            {candidates.map((c) => (
              <label key={c.entity_id} data-testid={`pin-candidate-${c.entity_id}`}
                className={`flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 ${
                  pickedEntity === c.entity_id ? "border-[#0058CC] bg-[#F2F7FF]" : "border-[#EFF0F2]"}`}>
                <input type="radio" name="pin-source" className="mt-1" checked={pickedEntity === c.entity_id}
                  onChange={() => setPickedEntity(c.entity_id)} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[12.5px] font-bold">{c.entity_name}</span>
                    <span className="text-[10.5px] text-[#8E8E93]">{c.legal_name}</span>
                    {c.can_fulfill ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-[#BFE6CE] bg-[#E6F6EC] px-2 py-0.5 text-[10px] font-bold text-[#1B7F4B]">
                        <CheckCircle2 size={10} /> Siap dipenuhi
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full border border-[#F5D9A8] bg-[#FFF4E5] px-2 py-0.5 text-[10px] font-bold text-[#8A5300]">
                        <AlertTriangle size={10} /> Ada yang perlu dibereskan
                      </span>
                    )}
                    {!c.active && (
                      <span className="text-[10px] font-bold text-[#C0392B]">badan usaha tidak aktif</span>
                    )}
                  </div>

                  <div className="mt-1.5 overflow-x-auto">
                    <table className="w-full text-[11px]">
                      <thead className="text-[9.5px] font-bold uppercase text-[#9A9BA3]">
                        <tr><th className="text-left">Barang</th><th className="text-right">Diminta</th>
                          <th className="text-right">Stok di sana</th><th className="text-right">Cukup?</th></tr>
                      </thead>
                      <tbody>
                        {(c.lines || []).map((l) => (
                          <tr key={l.product_id}>
                            <td className="truncate py-0.5">{l.sku || l.product_name}</td>
                            <td className="py-0.5 text-right tabular-nums">{formatQty(l.needed)}</td>
                            <td className="py-0.5 text-right tabular-nums">{formatQty(l.available)}</td>
                            <td className={`py-0.5 text-right font-bold ${l.enough ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}>
                              {l.enough ? "ya" : "kurang"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <p className="mt-1 text-[10.5px] text-[#6B6B73]">
                    Mode harga <b>{c.pricing_mode}</b> · pratinjau nilai{" "}
                    <b className="tabular-nums">{formatCurrency(c.price_preview || 0)}</b>
                  </p>
                  {(c.price_issues || []).map((msg, i) => (
                    <p key={i} data-testid={`pin-price-issue-${c.entity_id}-${i}`}
                       className="mt-1 rounded border border-[#F5D9A8] bg-[#FFF9EF] px-2 py-1 text-[10.5px] text-[#8A5300]">
                      {msg}
                    </p>
                  ))}
                </div>
              </label>
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#EFF0F2] px-3 py-3">
            <label className="flex items-center gap-2 text-[11.5px]">
              <input type="checkbox" data-testid="pin-submit-now" checked={submitNow}
                     onChange={(e) => setSubmitNow(e.target.checked)} />
              Langsung konfirmasi transaksinya (jurnal &amp; saldo antar-PT terbentuk sekarang) —
              bila di atas ambang persetujuan, sistem akan meminta peran yang berwenang
            </label>
            <button data-testid="pin-convert-btn" className="btn-primary"
                    disabled={busy || !pickedEntity || (picked && !picked.can_fulfill)}
                    title={picked && !picked.can_fulfill
                      ? "Bereskan dulu stok / harga internalnya — kalau dipaksa, transaksinya akan ditolak mesin antar-PT"
                      : ""}
                    onClick={doConvert}>
              {busy ? "Memproses…" : "Jadikan Transaksi Antar-PT"}
            </button>
          </div>
        </section>
      )}

      {/* Riwayat */}
      <section className="section-card">
        <div className="section-head"><h2>Riwayat</h2></div>
        <div className="divide-y divide-[#F4F5F7]" data-testid="pin-timeline">
          {(req.timeline || []).map((t, i) => (
            <div key={i} className="flex items-start gap-2 px-3 py-2">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[#0058CC]" />
              <div className="min-w-0">
                <p className="text-[11.5px] font-semibold">{t.label || t.event}</p>
                <p className="text-[10.5px] text-[#8E8E93]">
                  {(t.at || t.timestamp || "").slice(0, 16).replace("T", " ")}
                  {t.actor ? ` · ${t.actor}` : ""}{t.note ? ` · ${t.note}` : ""}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {showReject && (
        <div className="modal-overlay" data-testid="pin-reject-modal"
             onClick={(e) => { if (e.target === e.currentTarget) setShowReject(false); }}>
          <div className="modal-card small" onClick={(e) => e.stopPropagation()}>
            <p className="modal-title">Tolak {req.number}</p>
            <p className="modal-subtitle">
              Alasan penolakan dikirim ke peminta — tulis langkah berikutnya yang jelas
              (beli ke pemasok? tunggu? ubah jumlah?).
            </p>
            <textarea data-testid="pin-reject-reason" className="field mt-2" rows={3}
              value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
              placeholder="mis. stok Kanda dipakai pesanan sendiri — ajukan PR ke pemasok" />
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowReject(false)}>Batal</button>
              <button data-testid="pin-reject-confirm" className="btn-primary" disabled={busy}
                      onClick={doReject}>{busy ? "Memproses…" : "Tolak Permintaan"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, hint, testId }) {
  return (
    <div data-testid={testId} className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] px-3 py-2">
      <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
      <p className="text-[12px] font-semibold text-[#1C1C1E]">{value}</p>
      {hint && <p className="text-[10px] text-[#9A9BA3]">{hint}</p>}
    </div>
  );
}
