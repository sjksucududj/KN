/**
 * CustomerPricelistView (F1b · D-14) — **Daftar Harga per Pelanggan**.
 *
 * Menjawab pertanyaan pemilik: "berapa harga langganan pelanggan ini untuk tiap produk,
 * dan dari mana harga itu datang?". Satu tabel memperlihatkan RANTAI harga apa adanya:
 *     harga umum → harga PT → harga pelanggan → harga khusus disetujui → harga EFEKTIF
 *
 * Harga di bawah batas bawah (harga PT / biaya pokok) TIDAK bisa diberlakukan sendiri:
 * ia masuk antrean **Persetujuan Harga** yang sudah ada (alur Harga Khusus) — satu mesin
 * persetujuan, satu jejak keputusan.
 *
 * Sumber data: `/api/customer-prices/*`. Akses: admin/manager mengelola, sales melihat.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2, Clock3, Download, RefreshCw, Search, ShoppingBag, Tag, Upload, Users, X,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import { formatCurrency } from "../../utils/formatters";
import {
  EmptyCustomer, GuardBanner, Kpi, PriceRow,
} from "./customerPricelist/CustomerPriceParts";
import SetCustomerPriceModal from "./customerPricelist/SetCustomerPriceModal";
import CustomerPriceHistoryModal from "./customerPricelist/CustomerPriceHistoryModal";
import ImportCustomerPriceModal from "./customerPricelist/ImportCustomerPriceModal";

export default function CustomerPricelistView({
  entities = [], selectedEntity, currentUser, onNavigate,
}) {
  const canManage = ["admin", "manager"].includes(currentUser?.role);
  const activeEntities = entities.filter((e) => e.status !== "inactive");
  const [entityId, setEntityId] = useState(
    selectedEntity && selectedEntity !== "all" ? selectedEntity : (activeEntities[0]?.id || ""));
  const [customers, setCustomers] = useState([]);
  const [customerId, setCustomerId] = useState("");
  const [search, setSearch] = useState("");
  const [onlyWithPrice, setOnlyWithPrice] = useState(false);
  const [grid, setGrid] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [priceModal, setPriceModal] = useState(null);
  const [historyRow, setHistoryRow] = useState(null);
  const [importOpen, setImportOpen] = useState(false);

  // ── Pelanggan (dibatasi entitas aktif) ────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get(`${API}/customers`, {
          params: entityId ? { entity_id: entityId } : {},
        });
        if (cancelled) return;
        const rows = Array.isArray(res.data) ? res.data : (res.data?.items || []);
        setCustomers(rows);
        setCustomerId((prev) => (rows.some((c) => c.id === prev) ? prev : (rows[0]?.id || "")));
      } catch (e) {
        if (!cancelled) setError(e.response?.data?.detail || "Gagal memuat daftar pelanggan.");
      }
    })();
    return () => { cancelled = true; };
  }, [entityId]);

  const load = useCallback(async () => {
    if (!customerId || !entityId) { setGrid(null); return; }
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/customer-prices`, {
        params: { customer_id: customerId, entity_id: entityId, search },
      });
      setGrid(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat daftar harga pelanggan.");
      setGrid(null);
    } finally {
      setLoading(false);
    }
  }, [customerId, entityId, search]);

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, search]);

  const entityOptions = useMemo(
    () => activeEntities.map((e) => ({ value: e.id, label: e.short_name || e.legal_name || e.id })),
    [activeEntities]);
  const customerOptions = useMemo(
    () => customers.map((c) => ({ value: c.id, label: `${c.name}${c.code ? ` · ${c.code}` : ""}` })),
    [customers]);
  const customer = customers.find((c) => c.id === customerId) || null;

  const rows = useMemo(() => {
    const all = grid?.rows || [];
    return onlyWithPrice
      ? all.filter((r) => r.customer_price != null || r.pending_price != null)
      : all;
  }, [grid, onlyWithPrice]);

  const exportCsv = async () => {
    setError(""); setNotice("");
    try {
      const res = await axios.get(`${API}/customer-prices/export`, {
        params: { customer_id: customerId, entity_id: entityId, only_with_price: onlyWithPrice },
        responseType: "blob",
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `harga-pelanggan-${(customer?.name || "pelanggan").replace(/\s+/g, "-").toLowerCase()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      setNotice("Berkas CSV harga pelanggan sudah diunduh.");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal mengunduh CSV harga pelanggan.");
    }
  };

  const goApprovals = () => {
    if (typeof onNavigate === "function") onNavigate("price-approvals");
  };

  const withCustomer = grid?.with_customer_price ?? 0;
  const pendingCount = grid?.pending_count ?? 0;
  const specialCount = grid?.with_special_price ?? 0;

  return (
    <div data-testid="customer-pricelist-view">
      <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi testId="cpl-kpi-products" label="Produk terdaftar" value={grid?.count ?? 0} icon={Tag}
          hint={customer ? customer.name : "pilih pelanggan"} />
        <Kpi testId="cpl-kpi-customer" label="Harga pelanggan aktif" value={withCustomer}
          icon={Users} tone="text-[#0058CC]" />
        <Kpi testId="cpl-kpi-pending" label="Menunggu persetujuan" value={pendingCount}
          icon={Clock3} tone={pendingCount > 0 ? "text-[#B26A00]" : ""}
          hint={pendingCount > 0 ? "klik Persetujuan Harga" : "tidak ada"} />
        <Kpi testId="cpl-kpi-special" label="Harga khusus berlaku" value={specialCount}
          icon={ShoppingBag} tone="text-[#6B219A]" />
      </div>

      <div className="section-card">
        <div className="section-head flex-wrap gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="kicker">Penjualan</span>
            <h2 data-testid="cpl-title">Daftar Harga per Pelanggan</h2>
            <EntityBadge entityId={entityId} entities={entities} />
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button data-testid="cpl-approvals-link" onClick={goApprovals}
              className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-[12px]">
              <Clock3 size={13} /> Persetujuan Harga
              {pendingCount > 0 && (
                <span className="rounded-full bg-[#FFF6E5] px-1.5 text-[10px] font-bold text-[#8C4A00]">
                  {pendingCount}
                </span>
              )}
            </button>
            <button data-testid="cpl-export" onClick={exportCsv} disabled={!customerId}
              className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-[12px] disabled:opacity-50">
              <Download size={13} /> Ekspor CSV
            </button>
            {canManage && (
              <button data-testid="cpl-import-open" onClick={() => setImportOpen(true)}
                disabled={!customerId}
                className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-[12px] disabled:opacity-50">
                <Upload size={13} /> Impor CSV
              </button>
            )}
            <button data-testid="cpl-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        <div className="section-body">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="w-[180px]">
              <KNSelect data-testid="cpl-entity-select" className="field py-1.5 text-[12px]"
                value={entityId} onValueChange={setEntityId} placeholder="Pilih entitas"
                options={entityOptions} />
            </div>
            <div className="w-[260px]">
              <KNSelect data-testid="cpl-customer-select" className="field py-1.5 text-[12px]"
                value={customerId} onValueChange={setCustomerId} placeholder="Pilih pelanggan"
                options={customerOptions} searchable />
            </div>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="cpl-search" className="field w-[220px] py-1.5 pl-8 text-[12px]"
                placeholder="Cari SKU / nama / kategori" value={search}
                onChange={(e) => setSearch(e.target.value)} />
            </div>
            <label className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-[#3C3C43]">
              <input data-testid="cpl-only-with-price" type="checkbox" checked={onlyWithPrice}
                onChange={(e) => setOnlyWithPrice(e.target.checked)} />
              Hanya yang punya harga pelanggan
            </label>
          </div>

          <GuardBanner guard={grid?.guard} />

          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
            testId="cpl-error" />
          {notice && (
            <div data-testid="cpl-notice"
              className="mb-3 flex items-center gap-2 rounded-md border border-[#BDE5CC] bg-[#E6F6EC] px-3 py-2 text-[12px] text-[#1B7F4B]">
              <CheckCircle2 size={14} />{notice}
              <button className="ml-auto" onClick={() => setNotice("")} aria-label="Tutup">
                <X size={13} />
              </button>
            </div>
          )}

          {!customerId ? (
            <EmptyCustomer />
          ) : loading ? (
            <div className="grid gap-2" data-testid="cpl-loading">
              {[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-[#F5F5F7]" />)}
            </div>
          ) : rows.length === 0 ? (
            <div data-testid="cpl-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">
              <Tag size={26} className="mx-auto mb-2 text-gray-300" />
              {onlyWithPrice
                ? "Pelanggan ini belum punya harga langganan — hilangkan filter untuk menetapkan harga."
                : "Tidak ada produk yang cocok dengan pencarian."}
            </div>
          ) : (
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
                    <th className="px-3 py-2">SKU</th>
                    <th className="px-3 py-2">Produk</th>
                    <th className="px-3 py-2 text-right">Harga Umum</th>
                    <th className="px-3 py-2 text-right">Harga PT</th>
                    <th className="px-3 py-2 text-right">Harga Pelanggan</th>
                    <th className="px-3 py-2 text-right">Efektif</th>
                    <th className="px-3 py-2 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <PriceRow key={r.product_id} row={r} canManage={canManage}
                      onSetPrice={() => setPriceModal(r)} onHistory={() => setHistoryRow(r)}
                      onOpenApprovals={goApprovals} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {rows.length > 0 && (
            <p className="mt-2 text-[11px] text-[#8E8E93]">
              Menampilkan {rows.length} produk · harga efektif dipakai otomatis saat membuat
              Pesanan Penjualan & POS untuk {customer?.name || "pelanggan ini"}. Harga khusus
              yang sudah disetujui tetap menang di atas harga langganan.
            </p>
          )}
        </div>
      </div>

      {priceModal && customer && (
        <SetCustomerPriceModal row={priceModal} customer={customer} entityId={entityId}
          onClose={() => setPriceModal(null)}
          onError={setError}
          onSaved={(rec) => {
            setPriceModal(null);
            setNotice(rec?.approval_required
              ? `Harga ${rec.product_name} ${formatCurrency(rec.sell_price)} diajukan — menunggu persetujuan manajer di Persetujuan Harga.`
              : `Harga ${rec.product_name} ${formatCurrency(rec.sell_price)} berlaku sekarang.`);
            load();
          }} />
      )}
      {historyRow && customer && (
        <CustomerPriceHistoryModal row={historyRow} customer={customer} entityId={entityId}
          canManage={canManage} onClose={() => setHistoryRow(null)} onChanged={load} />
      )}
      {importOpen && customer && (
        <ImportCustomerPriceModal customer={customer} entityId={entityId}
          onClose={() => { setImportOpen(false); load(); }}
          onDone={() => load()} />
      )}
    </div>
  );
}
