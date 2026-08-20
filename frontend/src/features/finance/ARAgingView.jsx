/**
 * ARAgingView (EPIC7-A) — Piutang / Accounts Receivable Aging.
 * Akses admin/manager. Sumber: GET /api/ar/aging (+ /ar/aging/{customer_id}).
 * Aging buckets: Lancar / 1-30 / 31-60 / 61-90 / 90+ hari.
 *
 * FASE G-3 (permintaan #2 pemilik) — kolom denda **tidak lagi angka mati**:
 *   • estimasi tetap ditampilkan (informasional, dari kebijakan bunga & tenggang);
 *   • di sampingnya muncul **nota denda NYATA** (FASE G-2) yang bisa diklik ke dokumennya
 *     — lengkap status usulan / terbit / dibebaskan / dibayar;
 *   • yang belum pernah dibuatkan nota ditandai jelas, dan bisa **dibuatkan sekarang**
 *     lewat tombol “Buat Nota Denda” (nota lahir sebagai usulan, belum menyentuh buku besar).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, Search, Wallet, AlertTriangle, TrendingDown, Clock3, Users, X, FileText,
  BadgeDollarSign, Loader2, Receipt, Building2 } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import { CreditStatusPill } from "../crm/crmUtils";
import StoreCreditBadge from "../../components/StoreCreditBadge";
import PenaltyPanel from "./payments/PenaltyPanel";
import { openTrace } from "../documents/trace/traceDeepLink";
import { penaltyMeta } from "./payments/paymentApi";
// INV-ROLE-01 — wewenang dibaca dari IZIN, bukan dari daftar nama peran.
import { can } from "../../config/roles";
import DetailModal from "../../components/DetailModal";

const BUCKETS = [
  { key: "current", label: "Lancar", tone: "#1B7F4B", bg: "#E6F6EC" },
  { key: "b1_30", label: "1-30 hr", tone: "#B45309", bg: "#FDF3E7" },
  { key: "b31_60", label: "31-60 hr", tone: "#B45309", bg: "#FDF3E7" },
  { key: "b61_90", label: "61-90 hr", tone: "#C0392B", bg: "#FCEBEA" },
  { key: "b90_plus", label: "90+ hr", tone: "#C0392B", bg: "#FCEBEA" },
];

const BASE_LABEL = {
  installment: "nilai cicilan yang telat",
  outstanding: "seluruh sisa piutang pesanan",
};

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" }); }
  catch { return "—"; }
}

export default function ARAgingView({ selectedEntity, currentUser }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [onlyOverdue, setOnlyOverdue] = useState(false);
  const [selected, setSelected] = useState(null);   // customer_id
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [accruing, setAccruing] = useState("");
  const [flash, setFlash] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const res = await axios.get(`${API}/ar/aging`, { params });
      setData(res.data || null);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data piutang (AR aging).");
    } finally {
      setLoading(false);
    }
  }, [selectedEntity]);

  useEffect(() => { load(); }, [load]);

  const openDetail = useCallback(async (cid) => {
    setSelected(cid);
    setDetail(null);
    setDetailLoading(true);
    try {
      const res = await axios.get(`${API}/ar/aging/${cid}`);
      setDetail(res.data || null);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // FASE G-3 — ubah estimasi denda menjadi NOTA DENDA nyata (usulan, belum berjurnal).
  const accrue = useCallback(async (cid) => {
    setAccruing(cid);
    setFlash("");
    try {
      const res = await axios.post(`${API}/ar/aging/${cid}/accrue-penalties`);
      const n = res.data?.count || 0;
      setDetail(res.data?.detail || null);
      setSelected(cid);
      setFlash(n > 0
        ? `${n} nota denda siap: ${(res.data.penalties || []).map((p) => p.number).join(", ")}. Nota masih USULAN — belum menyentuh buku besar.`
        : "Tidak ada denda yang layak dibuatkan nota (masih dalam tenggang, di bawah minimum, atau kebijakan denda dimatikan).");
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal membuat nota denda.");
    } finally { setAccruing(""); }
  }, [load]);

  const totals = data?.totals || {};
  const dendaRate = data?.config?.denda_rate_pct_per_month || 0;
  const penaltyPolicy = data?.penalty_policy || {};

  const rows = useMemo(() => {
    let r = data?.customers || [];
    const term = q.trim().toLowerCase();
    if (term) r = r.filter((c) => `${c.customer_name} ${c.assigned_sales_name}`.toLowerCase().includes(term));
    if (onlyOverdue) r = r.filter((c) => (c.overdue || 0) > 0.01);
    return r;
  }, [data, q, onlyOverdue]);

  const overduePct = totals.total > 0 ? Math.round((totals.overdue / totals.total) * 100) : 0;
  /**
   * INV-ROLE-01 (AUDIT PERAN 2026-08-15) — dulu `["admin","manager"].includes(role)`.
   * Peran `finance` justru pemegang izin `penalty.issue` (E8.1b: "denda perlu
   * diterbitkan" ada di Meja Finance), tetapi daftar nama peran ini menyembunyikan
   * tombolnya — server mengizinkan, layar melarang. Wewenang dibaca dari IZIN.
   */
  const canAccrue = can(currentUser?.permissions || {}, "penalty", "issue");

  return (
    <div data-testid="ar-aging-view">
      {/* FASE E-0 (L9 · user story 10) — laporan piutang WAJIB menyebut entitasnya.
          Dulu `entity_id` selalu "all" dan total KSC/Kanda identik (dua PT dicampur). */}
      {data && (
        <div
          data-testid="ar-aging-entity-banner"
          className={`mb-3 flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 ${
            data.is_consolidated
              ? "border-[#F0C88A] bg-[#FEF7EC]"
              : "border-[#C9DBF7] bg-[#F2F7FF]"
          }`}
        >
          <Building2 size={14} className={data.is_consolidated ? "text-[#8C4A00]" : "text-[#0058CC]"} />
          <span className="text-[11.5px] font-bold text-[#1C1C1E]" data-testid="ar-aging-entity-name">
            {data.is_consolidated ? "Mode Gabungan" : "Entitas"}: {data.entity_name || "—"}
          </span>
          <span className="text-[10.5px] text-[#6B6B73]">
            {data.is_consolidated
              ? "Angka di bawah adalah GABUNGAN beberapa badan usaha — bukan piutang satu PT."
              : "Seluruh angka di bawah milik badan usaha ini saja."}
          </span>
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-3">
        <Kpi testId="ar-kpi-total" label="Total Piutang" value={formatCurrency(totals.total)} icon={Wallet} />
        <Kpi testId="ar-kpi-overdue" label={`Jatuh Tempo (${overduePct}%)`} value={formatCurrency(totals.overdue)} icon={AlertTriangle} tone={totals.overdue > 0 ? "text-[#C0392B]" : ""} />
        <Kpi testId="ar-kpi-current" label="Lancar (Belum JT)" value={formatCurrency(totals.current)} icon={Clock3} tone="text-[#1B7F4B]" />
        <Kpi testId="ar-kpi-denda" label={`Est. Denda (${dendaRate}%/bln)`} value={formatCurrency(totals.denda)} icon={TrendingDown} tone={totals.denda > 0 ? "text-[#B45309]" : ""} />
        <Kpi testId="ar-kpi-denda-doc" label={`Nota Denda (${totals.penalty_docs || 0} dok)`} value={formatCurrency(totals.penalty_actual)} icon={BadgeDollarSign} tone={totals.penalty_actual > 0 ? "text-[#0058CC]" : ""} />
      </div>

      {/* Aging bucket strip */}
      <div className="section-card mb-3">
        <div className="section-body py-3">
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown size={15} className="text-[#6B219A]" />
            <h3 className="text-[12px] font-bold text-[#1C1C1E]">Sebaran Umur Piutang</h3>
            <span className="text-[10.5px] text-[#9A9BA3] ml-auto" data-testid="ar-aging-customers">{totals.customers || 0} pelanggan · {totals.orders || 0} pesanan</span>
          </div>
          <AgingBar totals={totals} />
        </div>
      </div>

      {/* Master table */}
      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2"><Wallet size={16} className="text-[#6B219A]" /><h2 data-testid="ar-aging-title">Piutang per Pelanggan</h2></div>
          <div className="flex items-center gap-2 ml-auto">
            <button
              data-testid="ar-aging-overdue-toggle"
              className={`text-[11px] font-semibold rounded-md px-2.5 py-1.5 border transition-colors ${onlyOverdue ? "bg-[#FCEBEA] border-[#F0B5AE] text-[#C0392B]" : "bg-white border-[#EFF0F2] text-[#6B6B73] hover:border-[#C9DBF7]"}`}
              onClick={() => setOnlyOverdue((v) => !v)}
            >
              {onlyOverdue ? "Hanya Overdue ✓" : "Hanya Overdue"}
            </button>
            <div className="relative">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="ar-aging-search" className="field pl-7 py-1 text-[12px]" placeholder="Cari pelanggan / sales..." value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <button data-testid="ar-aging-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="ar-aging-error" />
          {flash && (
            <div className="notice-bar success !py-1.5 mb-2" data-testid="ar-aging-flash">
              <span className="text-[11.5px]">{flash}</span>
            </div>
          )}
          {loading ? (
            <div className="grid gap-2" data-testid="ar-aging-loading">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-10 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
          ) : rows.length === 0 ? (
            <div data-testid="ar-aging-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">
              <Users size={26} className="mx-auto mb-2 text-gray-300" />
              {onlyOverdue ? "Tidak ada piutang jatuh tempo. 🎉" : "Tidak ada piutang terbuka."}
            </div>
          ) : (
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]" data-testid="ar-aging-table">
                <thead>
                  <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                    <th className="px-3 py-2">Pelanggan</th>
                    <th className="px-3 py-2 text-right">Lancar</th>
                    <th className="px-3 py-2 text-right">1-30</th>
                    <th className="px-3 py-2 text-right">31-60</th>
                    <th className="px-3 py-2 text-right">61-90</th>
                    <th className="px-3 py-2 text-right">90+</th>
                    <th className="px-3 py-2 text-right">Belum Lunas</th>
                    <th className="px-3 py-2 text-right">Denda</th>
                    <th className="px-3 py-2 text-center">Kredit</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr
                      key={c.customer_id}
                      data-testid={`ar-aging-row-${c.customer_id}`}
                      className={`border-b border-[#F5F5F7] last:border-0 cursor-pointer hover:bg-[#FAFBFF] ${selected === c.customer_id ? "bg-[#EFF4FF]" : ""}`}
                      onClick={() => openDetail(c.customer_id)}
                    >
                      <td className="px-3 py-2">
                        <p className="font-semibold text-[#1C1C1E]">{c.customer_name}</p>
                        <p className="text-[10px] text-[#9A9BA3]">{c.assigned_sales_name || "—"}{c.oldest_days > 0 ? ` · telat ${c.oldest_days} hr` : ""}</p>
                      </td>
                      <Cell v={c.current} />
                      <Cell v={c.b1_30} warn />
                      <Cell v={c.b31_60} warn />
                      <Cell v={c.b61_90} danger />
                      <Cell v={c.b90_plus} danger />
                      <td className="px-3 py-2 text-right tabular-nums font-bold text-[#1C1C1E]">{formatCurrency(c.outstanding)}</td>
                      <td className="px-3 py-2 text-right" data-testid={`ar-denda-cell-${c.customer_id}`}>
                        {(c.penalty_docs || 0) > 0 ? (
                          <button type="button" className="group text-right"
                            data-testid={`ar-denda-link-${c.customer_id}`}
                            onClick={(e) => { e.stopPropagation(); openDetail(c.customer_id); }}>
                            <span className="block font-bold tabular-nums text-[#0058CC] group-hover:underline">
                              {formatCurrency(c.penalty_actual)}
                            </span>
                            <span className="block text-[9.5px] text-[#6B6B73]">
                              {c.penalty_docs} nota{(c.denda_undocumented || 0) > 0.01
                                ? ` · est. +${formatCurrency(c.denda_undocumented)}` : ""}
                            </span>
                          </button>
                        ) : (c.denda || 0) > 0.01 ? (
                          <div className="flex flex-col items-end gap-0.5">
                            <span className="tabular-nums text-[#B45309]">{formatCurrency(c.denda)}</span>
                            <span className="text-[9.5px] font-semibold text-[#9A9BA3]">est. — belum jadi nota</span>
                            {canAccrue && (
                              <button type="button" data-testid={`ar-denda-accrue-${c.customer_id}`}
                                className="secondary-button !py-0.5 !px-1.5 !text-[10px]"
                                disabled={accruing === c.customer_id}
                                onClick={(e) => { e.stopPropagation(); accrue(c.customer_id); }}>
                                {accruing === c.customer_id
                                  ? <Loader2 size={10} className="animate-spin" />
                                  : <Receipt size={10} />} Buat Nota
                              </button>
                            )}
                          </div>
                        ) : <span className="text-[#C7C7CC]">—</span>}
                      </td>
                      <td className="px-3 py-2 text-center"><CreditStatusPill status={c.credit_status} testId={`ar-credit-${c.customer_id}`} /></td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-[#FAFBFC] border-t border-[#EFF0F2] text-[11px] font-bold">
                    <td className="px-3 py-2 text-[#6B6B73] uppercase text-[10px]">Total</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(totals.current)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(totals.b1_30)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(totals.b31_60)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(totals.b61_90)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(totals.b90_plus)}</td>
                    <td className="px-3 py-2 text-right tabular-nums" data-testid="ar-aging-total">{formatCurrency(totals.total)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-[#0058CC]" data-testid="ar-aging-denda-total">
                      {formatCurrency(totals.penalty_actual)}
                      <span className="block text-[9.5px] font-semibold text-[#B45309]">
                        est. {formatCurrency(totals.denda)}
                      </span>
                    </td>
                    <td className="px-3 py-2" />
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
          <p className="text-[10.5px] text-[#9A9BA3] mt-2">
            Umur dihitung dari tanggal pesanan + termin pembayaran. Kolom <b>Denda</b> menampilkan
            <b> nota denda nyata</b> (dokumen yang bisa ditagih/dinegosiasikan); angka{" "}
            <i>est.</i> adalah estimasi {dendaRate}%/bulan yang <b>belum</b> dibuatkan nota.
            Nota denda dihitung atas dasar <b>{BASE_LABEL[penaltyPolicy.base] || penaltyPolicy.base || "kebijakan"}</b>
            {Number(penaltyPolicy.grace_days || 0) > 0 ? ` dengan tenggang ${penaltyPolicy.grace_days} hari` : ""} —
            karena itu nilainya bisa berbeda dari estimasi kasar di kolom ini.
          </p>
        </div>
      </div>

      {/* FASE P7 — rincian tampil sebagai POP-UP. Dulu dirender sebagai saudara di bawah
          tabel: setelah mengklik baris tidak ada perubahan yang terlihat karena panelnya
          berada di bawah tabel ringkasan + catatan kaki (di luar pandangan). */}
      {selected && (
        <DetailModal onClose={() => { setSelected(null); setDetail(null); }}
          label="Rincian piutang pelanggan" testId="ar-aging-detail-modal">
          <CustomerDetail
            detail={detail}
            customerId={selected}
            loading={detailLoading}
            currentUser={currentUser}
            accruing={accruing === selected}
            onAccrue={() => accrue(selected)}
            onRefresh={() => openDetail(selected)}
            onClose={() => { setSelected(null); setDetail(null); }}
          />
        </DetailModal>
      )}
    </div>
  );
}

function Cell({ v, warn, danger }) {
  const tone = (v || 0) <= 0.01 ? "text-[#C7C7CC]" : danger ? "text-[#C0392B]" : warn ? "text-[#B45309]" : "text-[#3C3C43]";
  return <td className={`px-3 py-2 text-right tabular-nums ${tone}`}>{(v || 0) > 0.01 ? formatCurrency(v) : "—"}</td>;
}

function AgingBar({ totals }) {
  const total = totals.total || 0;
  return (
    <div data-testid="ar-aging-bar">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-[#F2F2F7]">
        {BUCKETS.map((b) => {
          const v = totals[b.key] || 0;
          const pct = total > 0 ? (v / total) * 100 : 0;
          if (pct <= 0) return null;
          return <div key={b.key} title={`${b.label}: ${formatCurrency(v)}`} style={{ width: `${pct}%`, background: b.tone }} />;
        })}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {BUCKETS.map((b) => (
          <span key={b.key} className="flex items-center gap-1.5 text-[10.5px] text-[#6B6B73]" data-testid={`ar-bucket-${b.key}`}>
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: b.tone }} />
            {b.label}: <b className="tabular-nums text-[#1C1C1E]">{formatCurrency(totals[b.key])}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

function CustomerDetail({ detail, customerId, loading, currentUser, accruing, onAccrue, onRefresh, onClose }) {
  // INV-ROLE-01 — sama seperti di layar induk: izin, bukan nama peran.
  const canAccrue = can(currentUser?.permissions || {}, "penalty", "issue");
  const t = detail?.totals || {};
  return (
    <div className="section-card mt-3" data-testid="ar-aging-detail">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <FileText size={15} className="text-[#0058CC]" />
          <h2>{detail?.customer_name || "Rincian Piutang"}</h2>
          {detail && <span className="text-[11px] text-[#6B6B73]">· Outstanding <b className="tabular-nums">{formatCurrency(t.total)}</b></span>}
          <StoreCreditBadge customerId={customerId} testId="ar-aging-store-credit" />
        </div>
        <div className="ml-auto flex items-center gap-2">
          {canAccrue && (
            <button type="button" className="secondary-button" data-testid="ar-aging-accrue"
              disabled={accruing} onClick={onAccrue}>
              {accruing ? <Loader2 size={13} className="animate-spin" /> : <Receipt size={13} />}
              Buat Nota Denda
            </button>
          )}
          <button data-testid="ar-aging-detail-close" className="icon-button" onClick={onClose} aria-label="Tutup"><X size={14} /></button>
        </div>
      </div>
      <div className="section-body space-y-3">
        {loading ? (
          <div className="grid gap-2" data-testid="ar-aging-detail-loading">{[0, 1, 2].map((i) => <div key={i} className="h-9 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
        ) : !detail || (detail.items || []).length === 0 ? (
          <div className="py-8 text-center text-[12px] text-[#8E8E93]" data-testid="ar-aging-detail-empty">Tidak ada pesanan terbuka.</div>
        ) : (
          <>
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                    <th className="px-3 py-2">Pesanan</th>
                    <th className="px-3 py-2">Jatuh Tempo</th>
                    <th className="px-3 py-2 text-center">Umur</th>
                    <th className="px-3 py-2 text-right">Total</th>
                    <th className="px-3 py-2 text-right">Terbayar</th>
                    <th className="px-3 py-2 text-right">Belum Lunas</th>
                    <th className="px-3 py-2 text-right">Est. Denda</th>
                    <th className="px-3 py-2">Nota Denda</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.map((it) => (
                    <tr key={it.order_id} data-testid={`ar-detail-row-${it.order_id}`} className="border-b border-[#F5F5F7] last:border-0">
                      <td className="px-3 py-2 font-semibold text-[#0058CC]">
                        {it.order_number}
                        {it.has_plan && (
                          <span className="ml-1 rounded bg-[#EFF4FF] px-1 text-[9px] font-bold text-[#0058CC]"
                            title={`Rencana pembayaran ${it.plan_number}`}>RPB</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-[#3C3C43]">{fmtDate(it.due_date)}</td>
                      <td className="px-3 py-2 text-center">
                        {it.overdue
                          ? <span className="rounded bg-[#FCEBEA] px-1.5 py-0.5 text-[10px] font-bold text-[#C0392B]">telat {it.days_late} hr</span>
                          : <span className="rounded bg-[#E6F6EC] px-1.5 py-0.5 text-[10px] font-bold text-[#1B7F4B]">lancar</span>}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(it.grand_total)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#1B7F4B]">{formatCurrency(it.paid_total)}</td>
                      <td className="px-3 py-2 text-right tabular-nums font-bold">{formatCurrency(it.outstanding)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#B45309]">{it.denda_estimate > 0 ? formatCurrency(it.denda_estimate) : "—"}</td>
                      <td className="px-3 py-2" data-testid={`ar-detail-penalties-${it.order_id}`}>
                        {(it.penalties || []).length === 0 ? (
                          it.denda_estimate > 0
                            ? <span className="text-[10.5px] font-semibold text-[#9A9BA3]">belum jadi nota</span>
                            : <span className="text-[#C7C7CC]">—</span>
                        ) : (
                          <div className="flex flex-wrap items-center gap-1">
                            {(it.penalties || []).map((p) => {
                              const pm = penaltyMeta(p.status);
                              return (
                                <button key={p.id} type="button"
                                  data-testid={`ar-detail-penalty-${p.id}`}
                                  title={`${p.line_label || ""} · ${formatCurrency(p.amount)}${p.je_number ? ` · jurnal ${p.je_number}` : ""}`}
                                  onClick={() => openTrace({ docType: "penalty", docId: p.id, number: p.number })}
                                  className="rounded px-1.5 py-0.5 text-[9.5px] font-bold hover:underline"
                                  style={{ background: pm.bg, color: pm.fg }}>
                                  {p.number} · {formatCurrency(p.amount)}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Nota denda nyata + keputusannya (terbitkan / ubah / bebaskan / catat bayar) */}
            <div>
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <BadgeDollarSign size={14} className="text-[#B45309]" />
                <h3 className="text-[12px] font-bold text-[#1C1C1E]">Nota Denda Pelanggan Ini</h3>
                <span className="text-[10.5px] text-[#6B6B73]">
                  usulan {formatCurrency(t.penalty_draft)} · terbit belum dibayar{" "}
                  {formatCurrency(t.penalty_issued)} · dibebaskan {formatCurrency(t.penalty_waived)}
                </span>
                {(t.denda_undocumented || 0) > 0.01 && (
                  <span className="rounded bg-[#FFF3CD] px-1.5 py-0.5 text-[9.5px] font-bold text-[#8A6D00]"
                    data-testid="ar-aging-undocumented">
                    est. {formatCurrency(t.denda_undocumented)} belum jadi nota
                  </span>
                )}
              </div>
              <PenaltyPanel rows={detail.penalties || []} currentUser={currentUser}
                entityId={detail.entity_id || ""} onChanged={onRefresh} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Kpi({ label, value, icon: Icon, tone = "", testId }) {
  return (
    <div className="section-card" data-testid={testId}>
      <div className="section-body flex items-center gap-3 py-3">
        <div className="w-9 h-9 rounded-lg bg-[#F3EAFB] flex items-center justify-center"><Icon size={17} className="text-[#6B219A]" /></div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`text-[17px] font-bold tabular-nums truncate ${tone || "text-[#1C1C1E]"}`} data-testid={`${testId}-value`}>{value}</p>
        </div>
      </div>
    </div>
  );
}
