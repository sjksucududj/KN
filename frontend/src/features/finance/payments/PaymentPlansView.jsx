/**
 * PaymentPlansView — FASE G-2 · layar **Rencana Pembayaran & Denda** (hub Keuangan).
 *
 * Finance butuh satu tempat untuk: melihat semua jadwal bayar pelanggan, menemukan
 * baris yang telat, dan memutus antrean usulan denda — tanpa harus membuka pesanan
 * satu per satu.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { BadgeDollarSign, CalendarClock, ExternalLink, RefreshCw, Scale, Search, Settings2 } from "lucide-react";
import EntityBadge from "../../../components/EntityBadge";
import ErrorNotice from "../../../components/ErrorNotice";
import { openConfig } from "../../settings/config/configDeepLink";
import { openTrace } from "../../documents/trace/traceDeepLink";
import PenaltyPanel from "./PenaltyPanel";
import PaymentVarianceQueue from "./PaymentVarianceQueue";
import { errText, listPenalties, listPlans, listVariances, money, penaltyMeta } from "./paymentApi";

const PEN_TABS = [
  { key: "", label: "Semua" },
  { key: "draft", label: "Usulan (draf)" },
  { key: "issued", label: "Terbit" },
  { key: "adjusted", label: "Diubah" },
  { key: "waived", label: "Dibebaskan" },
  { key: "paid", label: "Dibayar" },
];

function Kpi({ label, value, tone = "#1C1C1E", testId }) {
  return (
    <div data-testid={testId} className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
      <p className="text-[14px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
    </div>
  );
}

export default function PaymentPlansView({ currentUser, selectedEntity, onOpenDocument }) {
  const [tab, setTab] = useState("denda");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [plans, setPlans] = useState([]);
  const [pen, setPen] = useState({ items: [], stats: {} });
  const [vstats, setVstats] = useState({ pending: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const isAdmin = ["admin", "manager"].includes(currentUser?.role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const [pl, pn, vr] = await Promise.all([
        listPlans({ ...params, q: q || undefined }),
        listPenalties({ ...params, status: status || undefined, q: q || undefined }),
        listVariances({ ...params, limit: 1 }).catch(() => ({ stats: {} })),
      ]);
      setPlans(pl.items || []);
      setPen(pn || { items: [], stats: {} });
      setVstats(vr.stats || { pending: 0 });
      setError("");
    } catch (e) { setError(errText(e, "Gagal memuat rencana pembayaran & denda.")); }
    finally { setLoading(false); }
  }, [selectedEntity, status, q]);

  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [load]);

  const stats = pen.stats || {};
  const overduePlans = useMemo(() => plans.filter((p) => (p.overdue_count || 0) > 0), [plans]);

  return (
    <div data-testid="payment-plans-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="pp-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex min-w-0 items-center gap-2">
            <CalendarClock size={16} className="text-[#0058CC]" />
            <div className="min-w-0">
              <h2 data-testid="pp-title">Rencana Pembayaran & Denda</h2>
              <p className="text-[11px] text-[#6B6B73]">
                Jadwal bayar pelanggan (DP · cicilan · milestone) dan antrean denda keterlambatan.
                Denda lahir sebagai <b>usulan</b> — bisa dinegosiasikan sebelum masuk pembukuan.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isAdmin && (
              <button className="secondary-button" data-testid="pp-open-config"
                onClick={() => openConfig({ group: "uang-masuk" })}>
                <Settings2 size={13} /> Aturan Bayar & Denda
              </button>
            )}
            <button className="secondary-button" onClick={load} data-testid="pp-refresh">
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
            </button>
          </div>
        </div>
        <div className="section-body space-y-2.5">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5" data-testid="pp-kpis">
            <Kpi testId="pp-kpi-plans" label="Rencana aktif" value={String(plans.filter((p) => p.status === "active").length)} />
            <Kpi testId="pp-kpi-overdue" label="Rencana ada baris telat" value={String(overduePlans.length)} tone="#9B1C1C" />
            <Kpi testId="pp-kpi-draft" label="Usulan denda" value={money(stats.draft_amount)} tone="#B26A00" />
            <Kpi testId="pp-kpi-issued" label="Denda terbit (belum dibayar)" value={money(stats.issued_outstanding)} tone="#0058CC" />
            <Kpi testId="pp-kpi-waived" label="Denda dibebaskan" value={money(stats.waived_amount)} tone="#6B6B73" />
          </div>
          <div className="tab-bar">
            <button data-testid="pp-tab-denda" className={`tab-button ${tab === "denda" ? "active" : ""}`}
              onClick={() => setTab("denda")}>
              <BadgeDollarSign size={12} className="mr-1 inline" /> Antrean Denda
              <span className="tab-badge">{(pen.items || []).length}</span>
            </button>
            <button data-testid="pp-tab-jadwal" className={`tab-button ${tab === "jadwal" ? "active" : ""}`}
              onClick={() => setTab("jadwal")}>
              <CalendarClock size={12} className="mr-1 inline" /> Jadwal Pembayaran
              <span className="tab-badge">{plans.length}</span>
            </button>
            <button data-testid="pp-tab-selisih" className={`tab-button ${tab === "selisih" ? "active" : ""}`}
              onClick={() => setTab("selisih")}>
              <Scale size={12} className="mr-1 inline" /> Selisih Bayar
              <span className="tab-badge">{vstats.pending || 0}</span>
            </button>
          </div>
          <div className={`flex flex-wrap items-center gap-2 ${tab === "selisih" ? "hidden" : ""}`}>
            <div className="relative max-w-sm flex-1">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="pp-search" value={q} onChange={(e) => setQ(e.target.value)}
                className="field !pl-8" placeholder="Cari nomor / pesanan / pelanggan…" />
            </div>
            {tab === "denda" && (
              <div className="flex flex-wrap gap-1.5" data-testid="pp-status-filters">
                {PEN_TABS.map((f) => (
                  <button key={f.key} data-testid={`pp-filter-${f.key || "all"}`} onClick={() => setStatus(f.key)}
                    className={`rounded-full border px-3 py-1 text-[11px] font-medium ${status === f.key
                      ? "border-[#0058CC] bg-[#0058CC] text-white"
                      : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>
                    {f.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {tab === "selisih" ? (
        <PaymentVarianceQueue currentUser={currentUser} selectedEntity={selectedEntity}
          onOpenDocument={onOpenDocument} />
      ) : tab === "denda" ? (
        <section className="section-card">
          <div className="section-head">
            <h3 className="text-[12.5px] font-bold">Antrean denda keterlambatan</h3>
            <span className="text-[10.5px] text-[#8E8E93]">{(pen.items || []).length} nota</span>
          </div>
          <div className="section-body">
            {loading && (pen.items || []).length === 0 && (
              <p className="animate-pulse py-8 text-center text-[12px] text-[#6B6B73]">Memuat denda…</p>
            )}
            {!loading && (pen.items || []).length === 0 && (
              <div data-testid="pp-penalty-empty" className="py-10 text-center">
                <BadgeDollarSign size={26} className="mx-auto mb-2 text-[#C4C5CC]" />
                <p className="text-[12.5px] font-semibold text-[#3C3C43]">Tidak ada nota denda pada filter ini.</p>
                <p className="text-[11.5px] text-[#6B6B73]">
                  Usulan denda muncul otomatis dari job harian bila ada baris jadwal yang telat.
                </p>
              </div>
            )}
            {(pen.items || []).length > 0 && (
              <PenaltyPanel rows={pen.items} currentUser={currentUser}
                entityId={selectedEntity} onChanged={load} />
            )}
          </div>
        </section>
      ) : (
        <section className="section-card">
          <div className="section-head">
            <h3 className="text-[12.5px] font-bold">Jadwal pembayaran pelanggan</h3>
            <span className="text-[10.5px] text-[#8E8E93]">{plans.length} rencana</span>
          </div>
          <div className="section-body overflow-x-auto">
            {loading && plans.length === 0 && (
              <p className="animate-pulse py-8 text-center text-[12px] text-[#6B6B73]">Memuat jadwal…</p>
            )}
            {!loading && plans.length === 0 && (
              <div data-testid="pp-plans-empty" className="py-10 text-center">
                <CalendarClock size={26} className="mx-auto mb-2 text-[#C4C5CC]" />
                <p className="text-[12.5px] font-semibold text-[#3C3C43]">Belum ada rencana pembayaran.</p>
                <p className="text-[11.5px] text-[#6B6B73]">
                  Susun jadwal dari panel <b>Jadwal Pembayaran & Denda</b> di detail pesanan.
                </p>
              </div>
            )}
            {plans.length > 0 && (
              <table className="w-full text-[12px]" data-testid="pp-plans-table">
                <thead>
                  <tr className="border-b border-[#EDEEF1] text-left text-[10px] uppercase tracking-wide text-[#8E8E93]">
                    <th className="px-2 py-2">Nomor</th><th className="px-2 py-2">Pesanan</th>
                    <th className="px-2 py-2">Pelanggan</th><th className="px-2 py-2">Mode</th>
                    <th className="px-2 py-2 text-right">Nilai</th><th className="px-2 py-2 text-right">Terbayar</th>
                    <th className="px-2 py-2">Berikutnya</th><th className="px-2 py-2">Status</th>
                    <th className="px-2 py-2 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {plans.map((p) => (
                    <tr key={p.id} className="border-b border-[#F5F5F7] hover:bg-[#FAFBFC]"
                      data-testid={`pp-plan-row-${p.id}`}>
                      <td className="px-2 py-2 font-semibold text-[#0058CC]">
                        <button type="button" data-testid={`pp-plan-trace-${p.id}`}
                          onClick={() => openTrace({ docType: "payment_plan", docId: p.id, number: p.number })}
                          className="hover:underline">{p.number}</button>
                      </td>
                      <td className="px-2 py-2">{p.doc_number} <EntityBadge entityId={p.entity_id} /></td>
                      <td className="px-2 py-2">{p.customer_name || "—"}</td>
                      <td className="px-2 py-2 text-[#6B6B73]">{p.mode_label}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{money(p.total_amount)}</td>
                      <td className="px-2 py-2 text-right tabular-nums text-[#1B7A43]">{money(p.paid_total)}</td>
                      <td className="px-2 py-2 text-[#6B6B73]">
                        {p.next_due_date ? `${p.next_due_date} · ${money(p.next_due_amount)}` : "—"}
                        {(p.overdue_count || 0) > 0 && (
                          <span className="ml-1 rounded bg-[#FDE2E2] px-1 text-[9px] font-bold text-[#9B1C1C]">
                            {p.overdue_count} telat
                          </span>
                        )}
                      </td>
                      <td className="px-2 py-2">
                        <span className="rounded-full bg-[#F1F2F4] px-2 py-0.5 text-[10px] font-medium capitalize text-[#4A4B52]">
                          {p.status}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-right">
                        {onOpenDocument && (
                          <button type="button" title="Buka pesanan" data-testid={`pp-open-so-${p.id}`}
                            onClick={() => onOpenDocument({ view: "orders", focus_type: "sales_order", focus_id: p.doc_id })}
                            className="rounded-md border border-[#EDEEF1] p-1 text-[#4A4B52] hover:bg-[#F2F3F5]">
                            <ExternalLink size={13} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
