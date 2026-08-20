import { useEffect, useState, useCallback } from "react";
import {
  Banknote, TrendingUp, ArrowUpRight, Receipt, AlertTriangle,
  Clock, PackageX, Award, RefreshCw, Trophy,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import PeriodUnlockCard from "../../components/PeriodUnlockCard";
import ErrorNotice from "../../components/ErrorNotice";

const fmt = new Intl.NumberFormat("id-ID");
const fmtCur = (v) => `Rp ${fmt.format(Math.round(v || 0))}`;

function KPICard({ icon: Icon, label, value, sub, color = "#007AFF", loading, onClick, testId }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag data-testid={testId || `kpi-${label.toLowerCase().replace(/\s+/g, "-")}`}
      onClick={onClick} type={onClick ? "button" : undefined}
      className={`rounded-xl border border-[#EFF0F2] bg-white p-4 flex flex-col gap-2 text-left${
        onClick ? " hover:border-[#C9D6E8] hover:shadow-sm transition" : ""}`}>
      <div className="flex items-center gap-2">
        <div className="rounded-lg p-1.5" style={{ background: `${color}18` }}>
          <Icon size={16} style={{ color }} />
        </div>
        <span className="text-[12px] font-semibold text-[#6B6B73]">{label}</span>
      </div>
      {loading ? (
        <div className="h-7 bg-[#F5F5F7] rounded animate-pulse" />
      ) : (
        <p className="text-2xl font-bold text-[#1C1C1E] tabular-nums">{value}</p>
      )}
      {sub && <p className="text-[11px] text-[#6B6B73]">{sub}</p>}
    </Tag>
  );
}

export default function AdminHome({ token, selectedEntity = "all", onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);

  const headers = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {};
      const res = await axios.get(`${API}/home/admin`, { headers, params });
      setData(res.data);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Control Tower. Coba lagi.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selectedEntity]);

  useEffect(() => { load(); }, [load]);

  const sales = data?.sales || {};
  const ar = data?.ar || {};
  const lowStock = data?.low_stock || {};
  const board = data?.leaderboard_top || [];
  const overdue = data?.top_overdue || [];
  // Jenis persetujuan terbanyak → dipakai teks bantu & tujuan klik KPI.
  const approvalItems = (data?.approvals?.items || []);
  const oldestWaiting = (data?.approvals?.oldest || []);
  const topApproval = approvalItems.slice().sort((a, b) => b.count - a.count)[0] || null;
  const approvalSub = (data?.approvals_pending || 0) === 0
    ? "Tidak ada yang menunggu"
    : (topApproval
      ? `Terbanyak: ${topApproval.label.replace(" menunggu ACC", "")} (${topApproval.count}) · klik untuk buka`
      : "Perlu ditindak");

  return (
    <section data-testid="admin-home" className="section-card">
      <div className="section-head">
        <p className="text-[12px] text-[#6B6B73] min-w-0 truncate">Pantauan penjualan, piutang & stok — real-time</p>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={load} className="secondary-button" data-testid="admin-home-refresh">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
          </button>
        </div>
      </div>

      <div className="section-body">
        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="admin-home-error" />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KPICard icon={Banknote} label="Penjualan Hari Ini" value={fmtCur(sales.today)} sub={`${sales.today_orders || 0} pesanan`} color="#007AFF" loading={loading} />
          <KPICard icon={TrendingUp} label="Penjualan MTD" value={fmtCur(sales.mtd)} sub="Bulan berjalan" color="#34C759" loading={loading} />
          <KPICard icon={ArrowUpRight} label="Tertagih MTD" value={fmtCur(sales.collected_mtd)} sub="Kas masuk" color="#30D158" loading={loading} />
          <KPICard icon={Receipt} label="Piutang Belum Lunas" value={fmtCur(ar.outstanding)} sub="Total piutang" color="#5856D6" loading={loading} />
          <KPICard icon={AlertTriangle} label="Piutang Lewat Tempo" value={fmtCur(ar.overdue)} sub="Jatuh tempo lewat" color="#FF3B30" loading={loading} />
          {/* AUDIT PERAN 2026-08-15 — KPI ini dulu SELALU 0 (menghitung koleksi
              `approval_requests` yang tak pernah diisi siapa pun), padahal 16 dokumen
              memang menunggu keputusan. Sekarang angkanya = antrean nyata, `sub`
              menyebut jenis terbanyak, dan kartunya BISA DIKLIK ke tempat kerjanya —
              angka tanpa jalan ke pekerjaannya hanya membuat orang menebak. */}
          <KPICard icon={Clock} label="Persetujuan Menunggu"
            value={data?.approvals_pending ?? "—"}
            sub={approvalSub}
            color="#FF9500" loading={loading}
            testId="kpi-persetujuan-menunggu"
            onClick={() => onNavigate && onNavigate(topApproval?.view || "approval-inbox")} />
          <KPICard icon={PackageX} label="Stok Rendah" value={lowStock.count ?? "—"} sub="Perlu reorder" color="#FF6B00" loading={loading} />
          <KPICard icon={Award} label="Payout Insentif" value={fmtCur(data?.incentive_payout)} sub="Estimasi MTD" color="#AF52DE" loading={loading} />
        </div>

        {/* FASE G-5 — ringkasan periode yang sedang dibuka (unlock) + sisa waktu */}
        <PeriodUnlockCard onNavigate={onNavigate} />

        {/* AUDIT PERAN 2026-08-15 — RINCIAN antrean persetujuan.
            KPI di atas tadinya satu angka buram (dan salah). Angka saja tidak membuat
            orang bertindak: yang menolong adalah "3 PO menunggu ACC" + jalan ke
            layarnya. Baris hanya muncul bila memang ada yang menunggu. */}
        {approvalItems.length > 0 && (
          <div className="mt-4 rounded-xl border border-[#FFE2BE] bg-[#FFFBF5] p-4"
            data-testid="admin-home-approval-backlog">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <Clock size={15} className="text-[#FF9500]" />
                <h3 className="text-[14px] font-bold">Antrean Persetujuan ({data?.approvals_pending || 0})</h3>
              </div>
              <button type="button" className="text-[12px] font-semibold text-[#007AFF]"
                onClick={() => onNavigate && onNavigate("approval-inbox")}
                data-testid="admin-home-goto-approval-inbox">Pusat Persetujuan →</button>
            </div>
            <div className="grid gap-1 sm:grid-cols-2">
              {approvalItems.map((a) => (
                <button key={a.key} type="button"
                  data-testid={`admin-home-approval-${a.key}`}
                  onClick={() => onNavigate && onNavigate(a.view)}
                  className="flex items-center justify-between gap-3 rounded-lg bg-white border border-[#F0E3D2] px-3 py-2 text-left hover:border-[#FFB25A] transition">
                  <span className="text-[12px] text-[#3A3A3C] truncate">{a.label}</span>
                  <span className="text-[13px] font-bold tabular-nums text-[#B26A00]">{a.count}</span>
                </button>
              ))}
            </div>

            {/* PALING LAMA MENUNGGU — angka membuat orang tahu ADA pekerjaan; ini yang
                membuat orang BERTINDAK. Sumbernya `approvals.oldest` (umur tunggu dari
                tanggal dokumen mulai menunggu), sama dengan isi pengingat harian. */}
            {oldestWaiting.length > 0 && (
              <div className="mt-3 border-t border-[#F0E3D2] pt-2" data-testid="admin-home-approval-oldest">
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-[#8E8E93]">
                  Paling lama menunggu
                </p>
                <div className="grid gap-1">
                  {oldestWaiting.map((o) => (
                    <button key={`${o.key}-${o.id}`} type="button"
                      data-testid={`admin-home-oldest-${o.id || o.number}`}
                      onClick={() => onNavigate && onNavigate(o.view)}
                      className="flex items-center gap-2 rounded-lg bg-white border border-[#F0E3D2] px-3 py-1.5 text-left hover:border-[#FFB25A] transition">
                      <span className="text-[12px] font-semibold text-[#1C1C1E] shrink-0">{o.number}</span>
                      <span className="text-[11.5px] text-[#6B6B73] truncate flex-1">
                        {o.queue_label.replace(" menunggu ACC", "")} · {o.title}
                      </span>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold tabular-nums ${
                        o.days_waiting >= 7 ? "bg-[#FFE5E5] text-[#C62828]" : "bg-[#FFF1DB] text-[#B26A00]"}`}>
                        {o.days_waiting} hari
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {/* Leaderboard */}
          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4" data-testid="admin-home-leaderboard">
            <div className="flex items-center gap-2 mb-3"><Trophy size={15} className="text-[#FF9500]" /><h3 className="text-[14px] font-bold">Top Sales (MTD)</h3></div>
            {board.length > 0 ? (
              <div className="grid gap-1.5">
                {board.map((r, idx) => (
                  <div key={r.sales_id || idx} className="flex items-center gap-2 py-1.5 border-b border-[#F5F5F7] last:border-0">
                    <span className="text-[11px] font-bold text-[#8E8E93] w-5">{idx + 1}</span>
                    <div className="flex-1 min-w-0"><p className="text-[12px] font-semibold truncate">{r.sales_name}</p>
                      <p className="text-[10.5px] text-[#8E8E93]">{r.orders_count || 0} order • {r.collection_rate || 0}% tertagih</p></div>
                    <span className="text-[12px] font-bold text-[#007AFF] tabular-nums">{fmtCur(r.total_sales)}</span>
                  </div>
                ))}
              </div>
            ) : <div className="h-20 flex items-center justify-center text-[13px] text-[#8E8E93]">Belum ada data penjualan</div>}
          </div>

          {/* Top overdue */}
          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4" data-testid="admin-home-overdue">
            <div className="flex items-center gap-2 mb-3"><AlertTriangle size={15} className="text-[#FF3B30]" /><h3 className="text-[14px] font-bold">Lewat Tempo per Sales</h3></div>
            {overdue.length > 0 && overdue.some((o) => o.overdue_amount > 0) ? (
              <div className="grid gap-1.5">
                {overdue.filter((o) => o.overdue_amount > 0).map((o, idx) => (
                  <div key={idx} className="flex items-center gap-2 py-1.5 border-b border-[#F5F5F7] last:border-0">
                    <div className="flex-1 min-w-0"><p className="text-[12px] font-semibold truncate">{o.sales_name}</p>
                      <p className="text-[10.5px] text-[#8E8E93]">AR {fmtCur(o.ar_outstanding)}</p></div>
                    <span className="text-[12px] font-bold text-red-600 tabular-nums">{fmtCur(o.overdue_amount)}</span>
                  </div>
                ))}
              </div>
            ) : <div className="h-20 flex items-center justify-center text-[13px] text-[#8E8E93]">Tidak ada tagihan lewat tempo 🎉</div>}
          </div>
        </div>

        {/* Low stock */}
        <div className="mt-4 rounded-xl border border-[#EFF0F2] bg-white p-4" data-testid="admin-home-lowstock">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2"><PackageX size={15} className="text-[#FF6B00]" /><h3 className="text-[14px] font-bold">Stok Perlu Reorder</h3></div>
            <button onClick={() => onNavigate && onNavigate("reorder")} className="text-[12px] font-semibold text-[#007AFF]" data-testid="admin-home-goto-reorder">Lihat semua →</button>
          </div>
          {(lowStock.items || []).length > 0 ? (
            <div className="grid gap-1 max-h-64 overflow-auto">
              {lowStock.items.map((it, idx) => (
                <div key={it.product_id || idx} className="grid grid-cols-[1fr_90px_90px] gap-2 text-[12px] py-1.5 border-b border-[#F5F5F7] last:border-0 items-center">
                  <div className="min-w-0"><p className="font-semibold truncate">{it.product_name || it.name}</p>
                    <p className="text-[10px] text-[#8E8E93]">{it.sku || ""}</p></div>
                  <span className="text-right tabular-nums text-[#6B6B73]">Stok fisik {fmt.format(it.on_hand ?? it.available_qty ?? 0)}</span>
                  <span className="text-right tabular-nums font-bold text-[#FF6B00]">ROP {fmt.format(it.reorder_point ?? 0)}</span>
                </div>
              ))}
            </div>
          ) : <div className="h-20 flex items-center justify-center text-[13px] text-[#8E8E93]">Semua stok di atas titik reorder</div>}
        </div>
      </div>
    </section>
  );
}
