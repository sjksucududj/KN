import { useEffect, useMemo, useState } from "react";
import { BarChart2, FileText, Search, XCircle, Check, Route } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatCurrency } from "../../utils/formatters";
import PaginationBar from "../../components/PaginationBar";
import { usePagedList } from "../../hooks/usePagedList";

// FASE P6 — kolom Unduh CSV. Badan usaha sengaja TIDAK diikutkan: dokumen pesanan hanya
// menyimpan `entity_id`, dan menampilkan id entitas dilarang (INV-UI-02) — sebuah kolom
// berisi `ent_ksc` tidak berarti apa pun bagi yang membuka berkasnya.
import { qtyDualCsvColumns } from "../../utils/qtyDualCsv";   // FASE U — dua satuan di CSV

const CSV_COLUMNS = [
  { key: "number", header: "Nomor" },
  { key: "created_at", header: "Tanggal", type: "date" },
  { key: "customer_name", header: "Pelanggan" },
  { key: "customer_city", header: "Kota" },
  { key: "sales_name", header: "Sales" },
  { header: "Jumlah Item", type: "int", get: (r) => (r.items || []).length },
  // FASE U — dua satuan: gulungan (bisa di-SUM) + ukuran per satuan. Dokumen lama
  // tanpa `qty_rolls` menghasilkan sel KOSONG, bukan 0 (keputusan pemilik).
  ...qtyDualCsvColumns(),
  { key: "total_amount", header: "Total", type: "num" },
  { key: "paid_total", header: "Sudah Dibayar", type: "num" },
  { key: "payment_status", header: "Status Bayar" },
  { key: "stage", header: "Tahap" },
  { key: "status", header: "Status" },
  { header: "Backorder", get: (r) => Boolean(r.has_backorder) },
];
import { StagePill, SubStatusChips } from "../../components/SoStatusBadges";
import LineFilter from "../../components/LineFilter";   // FASE L
import OrderDashboard from "./OrderDashboard";
import { OrderDetailPanel } from "./OrderDetailPanel";
// FASE E-8 (E8.14 · US12) — "barang saya sampai mana?" adalah pertanyaan pelanggan yang
// paling sering mampir ke sales, dan jawabannya dulu hanya ada di layar GUDANG (403 untuk
// sales). Panel ini membawa jawabannya ke layar Pesanan, read-only.
import OrderJourneyPanel from "./OrderJourneyPanel";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import { scopeSuffix } from "../../utils/entityLabel";
import { useEntityScope } from "../../context/EntityScopeContext";

export default function OrdersView({ 
  orders, 
  onApprove, 
  onConfirm, 
  onCancel, 
  onPay, 
  onGenerateDocument, 
  onShowDetail, 
  onReleaseReservation,
  onSubmitForApproval,
  onMarkDelivered,
  onIssueTaxInvoice,
  user,
  loading = false,
  focusDoc,
  onClearFocus,
  onOpenDocument,
  onRefresh,
}) {
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  // FASE E-3 — empty state WAJIB menyebut badan usaha yang sedang dilihat,
  // supaya "belum ada pesanan" tidak dikira data hilang padahal salah konteks.
  const { selectedEntity, entities } = useEntityScope();
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState("list");
  // Panel kanan punya DUA muka: "Detail & Aksi" (tindakan sesuai izin) dan
  // "Perjalanan Pesanan" (riwayat + sumber pemenuhan). Dipisah sebagai sakelar,
  // bukan digabung, supaya panel aksi tidak terdorong ke bawah lipatan layar.
  const [detailPane, setDetailPane] = useState("detail");

  // ── P2 — DAFTAR pesanan dipaginasi & dicari di SERVER ────────────────────────
  // Sebelumnya seluruh daftar (cap 200) ikut respons `/dashboard` lewat prop `orders`,
  // lalu disaring di peramban. Tab "Dasbor & Analitik" TETAP memakai prop itu karena
  // analitiknya memang butuh seluruh periode — memaksanya membaca satu halaman akan
  // membuat grafik bercerita salah. Jadi yang berpindah ke server hanya DAFTARNYA.
  // FASE L — chip lini ikut dikirim ke SERVER (bukan disaring di peramban):
  // daftar ini berhalaman, jadi menyaring di klien akan membuat "halaman 1" berisi
  // 3 baris dari 20 dan pengguna menyimpulkan datanya hilang.
  const [lineFilter, setLineFilter] = useState("");
  const listParams = useMemo(
    () => ({ ...(statusFilter === "all" ? {} : { status: statusFilter }),
             ...(lineFilter ? { line: lineFilter } : {}) }), [statusFilter, lineFilter]);
  const paged = usePagedList("/sales-orders", {
    params: listParams, search: searchQuery, pageSize: 20, enabled: viewMode === "list",
  });
  // Kartu ringkasan & label "Semua Status (N)" memakai AGREGAT server supaya angkanya
  // tidak menyusut mengikuti isi halaman (kelas bug "kartu bilang 12, daftar berisi 3").
  const [summary, setSummary] = useState(null);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/sales-orders/stats/summary`, { params: lineFilter ? { line: lineFilter } : {} })
      .then((r) => { if (alive) setSummary(r.data || null); })
      .catch(() => { if (alive) setSummary(null); });
    return () => { alive = false; };
  }, [paged.total, orders.length, lineFilter]);

  // EPIC6 — deep-link: auto-pilih order saat dinavigasi dari Document Hub.
  useEffect(() => {
    if (focusDoc?.focus_type === "sales_order" && focusDoc?.focus_id) {
      setViewMode("list");
      setStatusFilter("all");
      setSelectedOrder(focusDoc.focus_id);
      onClearFocus?.();
    }
  }, [focusDoc]); // eslint-disable-line
  
  // Pesanan terpilih dicari di halaman aktif dulu, lalu di daftar dasbor (prop) sebagai
  // cadangan — supaya deep-link dari Pusat Dokumen tetap membuka detail walau
  // dokumennya tidak berada di halaman yang sedang dibuka.
  const sel = selectedOrder
    ? (paged.items.find((o) => o.id === selectedOrder)
      || orders.find((o) => o.id === selectedOrder)
      || null)
    : null;

  // Penyaringan status & pencarian dilakukan SERVER; daftar halaman dipakai apa adanya.
  const filteredOrders = paged.items;

  const byStatus = summary?.by_status || {};
  const sCnt = (...keys) => keys.reduce((n, k) => n + Number(byStatus[k]?.count || 0), 0);

  /** Sesudah aksi yang mengubah status, HALAMAN yang sedang dibuka harus ikut dimuat
   *  ulang. Induk (`useAppActions`) hanya memperbarui daftar dasbornya sendiri, jadi
   *  tanpa pembungkus ini baris di daftar akan tetap memperlihatkan status lama. */
  const refreshBoth = () => { onRefresh?.(); paged.refresh(); };
  const withRefresh = (fn) => (fn
    ? async (...args) => { const r = await fn(...args); paged.refresh(); return r; }
    : fn);
  const stats = {
    total: Number(summary?.total_orders ?? paged.total ?? 0),
    reserved: sCnt("reserved", "waiting_approval", "approved"),
    backorder: Number(summary?.backorder_count || 0),
    confirmed: sCnt("confirmed", "partially_picked", "picked"),
    shipped: sCnt("partially_shipped", "shipped", "dispatched"),
    done: sCnt("done"),
    cancelled: sCnt("cancelled"),
  };

  return (
    <div data-testid="orders-view" className="flex flex-col gap-3">
      <div className="flex gap-2">
        <button
          onClick={() => setViewMode("dashboard")}
          className={`px-4 py-2 rounded-lg text-[13px] font-semibold transition-colors ${
            viewMode === "dashboard"
              ? "bg-[#007AFF] text-white"
              : "bg-white border border-[#E5E5EA] text-[#3C3C43] hover:bg-[#F2F2F7]"
          }`}
          data-testid="tab-dashboard"
        >
          <BarChart2 size={14} className="inline mr-1.5" />
          Dasbor & Analitik
        </button>
        <button
          onClick={() => setViewMode("list")}
          className={`px-4 py-2 rounded-lg text-[13px] font-semibold transition-colors ${
            viewMode === "list"
              ? "bg-[#007AFF] text-white"
              : "bg-white border border-[#E5E5EA] text-[#3C3C43] hover:bg-[#F2F2F7]"
          }`}
          data-testid="tab-list"
        >
          <FileText size={14} className="inline mr-1.5" />
          Daftar Pesanan
        </button>
      </div>
      
      {viewMode === "dashboard" && <OrderDashboard orders={orders} loading={loading} />}
      
      {viewMode === "list" && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
            {[
              { label: "Total", value: stats.total, color: "text-[#007AFF]", bg: "bg-[#EFF4FF]" },
              { label: "Dipesan", value: stats.reserved, color: "text-[#FF9500]", bg: "bg-orange-50" },
              { label: "Backorder", value: stats.backorder, color: "text-[#B23B14]", bg: "bg-[#FFF1EA]" },
              { label: "Diproses", value: stats.confirmed, color: "text-[#34C759]", bg: "bg-green-50" },
              { label: "Dikirim", value: stats.shipped, color: "text-[#0058CC]", bg: "bg-[#EAF2FF]" },
              { label: "Selesai", value: stats.done, color: "text-[#5856D6]", bg: "bg-purple-50" },
              { label: "Dibatalkan", value: stats.cancelled, color: "text-red-500", bg: "bg-red-50" },
            ].map(({ label, value, color, bg }) => (
              <div key={label} data-testid={`orders-stat-${label.toLowerCase()}`} className={`rounded-lg border border-[#EFF0F2] p-2.5 ${bg}`}>
                <p className="text-[9px] font-bold uppercase tracking-wide text-[#6B6B73]">{label}</p>
                <p className={`text-[20px] font-bold leading-tight ${color}`}>{value}</p>
              </div>
            ))}
          </div>
          
          <LineFilter value={lineFilter} onChange={setLineFilter} storageKey="orders"
                      allowed={user?.allowed_line_codes} testId="orders-line-filter" />

          <div className="flex items-center gap-2 rounded-lg border border-[#E5E5EA] bg-white px-3 py-2">
            <Search size={14} className="text-[#6B6B73]" />
            <input
              type="text"
              data-testid="orders-search-input"
              className="flex-1 bg-transparent text-[13px] outline-none placeholder:text-[#8E8E93]"
              placeholder="Cari nomor pesanan, pelanggan, produk…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} className="text-[#6B6B73] hover:text-black">
                <XCircle size={14} />
              </button>
            )}
          </div>
          
          <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
            <section className="section-card">
              <div className="section-head">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="kicker">Kendali Pesanan</span>
                  <h2>Sales Orders</h2>
                </div>
                <KNSelect
                  className="field !py-1 !text-[11px] w-auto"
                  value={statusFilter}
                  onValueChange={setStatusFilter}
                  options={[
                    { value: "all", label: `Semua Status (${stats.total})` },
                    { value: "waiting_approval", label: "Menunggu Persetujuan" },
                    { value: "waiting_stock", label: "Menunggu Stok (Backorder)" },
                    { value: "reserved", label: "Dipesan" },
                    { value: "approved", label: "Disetujui" },
                    { value: "confirmed", label: "Terkonfirmasi (Ditahan)" },
                    { value: "partially_picked", label: "Sebagian Diambil" },
                    { value: "picked", label: "Sudah Diambil (Siap)" },
                    { value: "partially_shipped", label: "Partially Shipped" },
                    { value: "shipped", label: "Shipped" },
                    { value: "dispatched", label: "Terkirim (lama)" },
                    { value: "done", label: "Selesai (Terkirim)" },
                    { value: "cancelled", label: "Dibatalkan" },
                  ]}
                />
              </div>
              <div className="overflow-hidden">
                <div className="grid grid-cols-[1fr_90px_90px_120px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73] border-b border-[#EFF0F2]">
                  <span>Pesanan</span><span>Pelanggan</span><span>Total</span><span>Tahap</span>
                </div>
                <div className="divide-y divide-[#EFF0F2] max-h-[600px] overflow-y-auto">
                  {(loading || paged.loading) && (
                    <div className="px-3 py-8 text-center text-[12px] text-[#6B6B73] animate-pulse">Memuat pesanan…</div>
                  )}
                  {!paged.loading && filteredOrders.length === 0 && (
                    <div data-testid="orders-empty" className="px-3 py-8 text-center text-[12px] text-[#6B6B73]">
                      {searchQuery.trim()
                        ? `Tidak ada pesanan yang cocok dengan “${searchQuery.trim()}” ${scopeSuffix(entities, selectedEntity)}.`
                        : statusFilter === "all"
                          ? `Belum ada pesanan aktif ${scopeSuffix(entities, selectedEntity)}.`
                          : `Tidak ada pesanan berstatus “${statusFilter}” ${scopeSuffix(entities, selectedEntity)}.`}
                    </div>
                  )}
                  {!paged.loading && filteredOrders.map((order) => (
                    <div 
                      data-testid={`order-card-${order.id}`} 
                      key={order.id}
                      className={`grid grid-cols-[1fr_90px_90px_120px] items-center px-3 py-2.5 cursor-pointer hover:bg-[#FAFBFC] transition-colors ${
                        selectedOrder === order.id ? 'bg-[#EFF4FF] border-l-2 border-[#007AFF]' : ''
                      }`}
                      onClick={() => setSelectedOrder(order.id === selectedOrder ? null : order.id)}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <p data-testid={`order-number-${order.id}`} className="text-[12px] font-bold text-[#007AFF]">
                            {order.number}
                          </p>
                          <EntityBadge entityId={order.entity_id} />
                          {order.has_backorder && (
                            <span
                              data-testid={`order-backorder-chip-${order.id}`}
                              className="rounded-sm bg-[#FFF1EA] px-1 py-0.5 text-[8.5px] font-bold uppercase tracking-wide text-[#B23B14]"
                            >
                              Backorder
                            </span>
                          )}
                        </div>
                        <p className="text-[10.5px] text-[#6B6B73] truncate">
                          {(order.items || []).length} item · {order.payment_status === 'paid' ? <span className="inline-flex items-center gap-0.5 text-green-600"><Check size={11} /> Lunas</span> : 'Belum bayar'}
                        </p>
                      </div>
                      <p data-testid={`order-customer-${order.id}`} className="text-[11px] text-[#3C3C43] truncate">
                        {order.customer_name}
                      </p>
                      <p data-testid={`order-total-${order.id}`} className="text-[11.5px] font-bold tabular-nums">
                        {formatCurrency(order.total_amount)}
                      </p>
                      <div className="flex flex-col items-start gap-0.5 min-w-0">
                        <StagePill order={order} testId={`order-status-${order.id}`} />
                        <SubStatusChips order={order} testIdPrefix={`order-row-substatus-${order.id}`} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {/* P2 — kontrol halaman daftar pesanan */}
              {!paged.loading && filteredOrders.length > 0 && (
                <div className="px-3 py-2 border-t border-[#EFF0F2]">
                  <PaginationBar
                    page={paged.page} pageSize={paged.pageSize} total={paged.total}
                    hasMore={paged.hasMore} loading={paged.loading}
                    onPrev={paged.prev} onNext={paged.next} onPageSize={paged.setPageSize}
                    testId="orders-pager" label="pesanan"
                    exportConfig={{ columns: CSV_COLUMNS, rows: filteredOrders,
                      fetchAll: paged.fetchAll, filename: "pesanan-penjualan" }}
                  />
                </div>
              )}
            </section>

            {sel ? (
              <div className="grid gap-2">
                <div className="flex gap-1.5" data-testid="order-pane-switch">
                  <button type="button" data-testid="order-pane-detail"
                    onClick={() => setDetailPane("detail")}
                    className={`tab-button ${detailPane === "detail" ? "active" : ""}`}>
                    <FileText size={12} className="mr-1 inline" /> Detail &amp; Aksi
                  </button>
                  <button type="button" data-testid="order-pane-journey"
                    onClick={() => setDetailPane("journey")}
                    className={`tab-button ${detailPane === "journey" ? "active" : ""}`}>
                    <Route size={12} className="mr-1 inline" /> Perjalanan Pesanan
                  </button>
                </div>

                {detailPane === "journey" ? (
                  <OrderJourneyPanel orderId={sel.id} orderNumber={sel.number} />
                ) : (
                  <OrderDetailPanel
                    order={sel}
                    user={user}
                    onRefresh={refreshBoth}
                    onApprove={withRefresh(onApprove)}
                    onConfirm={withRefresh(onConfirm)}
                    onCancel={withRefresh(onCancel)}
                    onPay={withRefresh(onPay)}
                    onGenerateDocument={onGenerateDocument}
                    onReleaseReservation={withRefresh(onReleaseReservation)}
                    onSubmitForApproval={withRefresh(onSubmitForApproval)}
                    onMarkDelivered={withRefresh(onMarkDelivered)}
                    onIssueTaxInvoice={withRefresh(onIssueTaxInvoice)}
                    onOpenDocument={onOpenDocument}
                    onClose={() => setSelectedOrder(null)}
                  />
                )}
              </div>
            ) : (
              <aside className="section-card flex items-center justify-center min-h-[200px] border-dashed">
                <div className="text-center p-6">
                  <FileText size={28} className="mx-auto mb-2 text-gray-300" />
                  <p className="text-[12px] text-[#6B6B73]">Pilih pesanan untuk lihat detail & aksi</p>
                </div>
              </aside>
            )}
          </div>
        </>
      )}
    </div>
  );
}
