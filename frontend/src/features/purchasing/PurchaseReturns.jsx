import { useEffect, useState, useCallback, useMemo } from "react";
import axios, { API } from "../../services/apiClient";
import { RotateCcw, Plus, X, CheckCircle, XCircle, Send, FileText, Layers, Trash2, Search } from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import LineFilter from "../../components/LineFilter";   // FASE L
import PaginationBar from "../../components/PaginationBar";
import { usePagedList } from "../../hooks/usePagedList";

// FASE P6 — kolom Unduh CSV (mengikuti kolom tabel retur beli, termasuk jumlah roll
// presisi yang di layar hanya tampil sebagai keterangan kecil di bawah nama supplier).
import { qtyDualCsvColumns } from "../../utils/qtyDualCsv";   // FASE U — dua satuan di CSV

const CSV_COLUMNS = [
  { key: "number", header: "Nomor Retur" },
  { key: "supplier_name", header: "Supplier" },
  { key: "po_number", header: "No. PO" },
  { header: "Jumlah Item", type: "int", get: (r) => r.items?.length || 0 },
  // FASE U — jumlah roll dibaca dari `items[].qty_rolls` (field resminya), BUKAN lagi
  // dihitung ulang dari `roll_ids.length`. Dua cara menghitung satu fakta = dua angka
  // yang bisa berbeda (retur disetujui sebagian / roll dibatalkan) tanpa ada yang tahu
  // mana yang benar. Satu sumber, satu helper — dijaga gate INV-QTY-01.
  ...qtyDualCsvColumns({ rollHeader: "Roll Retur", measureHeader: "Jumlah Retur" }),
  { key: "total_amount", header: "Total", type: "num" },
  { key: "debit_note_number", header: "Nota Debit" },
  { key: "status", header: "Status" },
  { key: "supplier_status", header: "Status Supplier" },
  { key: "origin_sales_return_number", header: "Dari Retur Jual" },
  { key: "created_at", header: "Dibuat", type: "date" },
];
import FormModal from "../../components/FormModal";
import ConfirmModal from "../../components/ConfirmModal";
import ReturnDetailPanel from "./ReturnDetailPanel";
import RollPickerModal from "./RollPickerModal";

/**
 * PurchaseReturns (Depth #1B) — Retur Beli / Nota Debit.
 * Kembalikan barang ke supplier → kurangi roll + terbitkan nota debit.
 * S#2026-07-21: retur PRESISI — pilih roll/lot spesifik (RollPickerModal); qty & harga
 * otomatis dari roll asal, `roll_ids` dikirim ke backend untuk konsumsi roll tepat sasaran.
 */
const TABS = [
  { key: "all", label: "Semua" },
  { key: "draft", label: "Draf" },
  { key: "pending_approval", label: "Menunggu" },
  { key: "approved", label: "Disetujui" },
  { key: "rejected", label: "Ditolak" },
];
const REASONS = [
  { value: "cacat", label: "Barang Cacat" },
  { value: "salah_kirim", label: "Salah Kirim" },
  { value: "kelebihan", label: "Kelebihan Kirim" },
  { value: "lain", label: "Lain-lain" },
];

function StatusPill({ status }) {
  const map = {
    draft: ["pill-muted", "Draft"], pending_approval: ["pill-warning", "Menunggu"],
    approved: ["pill-success", "Disetujui"], rejected: ["pill-danger", "Ditolak"],
  };
  const [cls, label] = map[status] || ["pill-muted", status];
  return <span className={`status-pill ${cls}`}>{label}</span>;
}

// R4 — label ringkas supplier RMA lifecycle untuk baris list
const SUP_LABEL = {
  requested_supplier: "RMA: Diajukan",
  shipped_supplier: "RMA: Dikirim",
  accepted_supplier: "RMA: Diterima",
  rejected_supplier: "RMA: Ditolak",
  goods_back: "RMA: Barang Kembali",
};

export default function PurchaseReturns({ currentUser, selectedEntity }) {
  const [suppliers, setSuppliers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [products, setProducts] = useState([]);
  const [pos, setPos] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("all");
  const [showForm, setShowForm] = useState(false);
  const [detail, setDetail] = useState(null);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [rollPicker, setRollPicker] = useState(null); // { itemIndex } saat picker roll terbuka
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [search, setSearch] = useState("");
  // P2 — lencana tab dari AGREGAT server. Kalau dihitung dari isi halaman, angkanya
  // diam-diam menyusut mengikuti halaman yang sedang dibuka.
  const [statusCounts, setStatusCounts] = useState({});

  const blankItem = { product_id: "", quantity: "", price: "", reason: "cacat", condition: "damaged", roll_ids: [], rolls: [] };
  const [form, setForm] = useState({ supplier_id: "", po_id: "", warehouse_id: "", reason: "", notes: "", items: [blankItem], submit_now: true });

  const canApprove = ["admin", "manager"].includes(currentUser?.role);
  const canDelete = ["admin", "manager"].includes(currentUser?.role);

  // P2 — daftar retur beli dipaginasi di server (?page/?page_size/?q/?status).
  const [lineFilter, setLineFilter] = useState("");   // FASE L
  const listParams = useMemo(() => {
    const p = {};
    if (selectedEntity && selectedEntity !== "all") p.entity_id = selectedEntity;
    if (tab !== "all") p.status = tab;
    if (lineFilter) p.line = lineFilter;              // FASE L — disaring di server
    return p;
  }, [selectedEntity, tab, lineFilter]);
  const paged = usePagedList("/purchase-returns", { params: listParams, search, pageSize: 20 });
  const returns = paged.items;
  const loading = paged.loading;

  const loadCounts = useCallback(async () => {
    try {
      const params = (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
      const res = await axios.get(`${API}/purchase-returns/status-counts`, { params });
      setStatusCounts(res.data || {});
    } catch { /* lencana bukan alasan menggagalkan layar */ }
  }, [selectedEntity]);

  useEffect(() => { loadMasters(); }, [selectedEntity]); // eslint-disable-line
  useEffect(() => { loadCounts(); }, [loadCounts]);

  /** Muat ulang daftar + lencana (dipakai sesudah aksi yang mengubah status). */
  function loadAll() {
    paged.refresh();
    loadCounts();
  }

  async function loadMasters() {
    try {
      const [sRes, wRes, pRes, poRes] = await Promise.all([
        axios.get(`${API}/suppliers`).catch(() => ({ data: [] })),
        axios.get(`${API}/warehouses`).catch(() => ({ data: [] })),
        axios.get(`${API}/products`).catch(() => ({ data: [] })),
        axios.get(`${API}/purchase-orders`).catch(() => ({ data: [] })),
      ]);
      const asList = (d) => (Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : []));
      setSuppliers(asList(sRes.data));
      setWarehouses(asList(wRes.data));
      setProducts(asList(pRes.data));
      setPos(asList(poRes.data));
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data master retur.");
    }
  }

  function updateItem(i, patch) {
    setForm((f) => ({ ...f, items: f.items.map((it, idx) => idx === i ? { ...it, ...patch } : it) }));
  }
  // Ganti produk → reset pilihan roll (roll lama tak valid untuk produk berbeda).
  function updateItemProduct(i, productId) {
    setForm((f) => ({ ...f, items: f.items.map((it, idx) => idx === i ? { ...it, product_id: productId, roll_ids: [], rolls: [] } : it) }));
  }
  function onSelectPO(poId) {
    const po = pos.find((p) => p.id === poId);
    if (po) {
      setForm((f) => ({
        ...f, po_id: poId, warehouse_id: po.warehouse_id || f.warehouse_id,
        supplier_id: po.supplier_id || f.supplier_id,
        items: (po.items || []).map((it) => ({ product_id: it.product_id, quantity: "", price: String(it.price || ""), reason: "cacat", condition: "damaged", roll_ids: [], rolls: [] })) || [blankItem],
      }));
    } else {
      setForm((f) => ({ ...f, po_id: "" }));
    }
  }

  // === Retur presisi: konfirmasi pilihan roll dari RollPickerModal ===========
  function confirmRolls(selectedRolls) {
    if (rollPicker == null) return;
    const i = rollPicker.itemIndex;
    const roll_ids = selectedRolls.map((r) => r.roll_id);
    const totalQty = selectedRolls.reduce((a, r) => a + Number(r.qty_remaining || 0), 0);
    const costs = selectedRolls.map((r) => Number(r.unit_cost || 0)).filter((c) => c > 0);
    const avgCost = costs.length ? Math.round((costs.reduce((a, c) => a + c, 0) / costs.length) * 100) / 100 : null;
    setForm((f) => ({
      ...f,
      items: f.items.map((it, idx) => idx === i ? {
        ...it,
        roll_ids,
        rolls: selectedRolls.map((r) => ({ roll_id: r.roll_id, roll_no: r.roll_no, lot: r.lot, qty_remaining: r.qty_remaining, unit_cost: r.unit_cost })),
        quantity: roll_ids.length ? String(totalQty) : it.quantity,
        price: (roll_ids.length && avgCost != null) ? String(avgCost) : it.price,
      } : it),
    }));
    setRollPicker(null);
  }
  function clearRolls(i) {
    setForm((f) => ({ ...f, items: f.items.map((it, idx) => idx === i ? { ...it, roll_ids: [], rolls: [] } : it) }));
  }

  async function handleSubmit() {
    const items = form.items.filter((it) => it.product_id && Number(it.quantity) > 0)
      .map((it) => {
        const prod = products.find((p) => p.id === it.product_id);
        const unit = prod?.base_unit || "meter";
        return { product_id: it.product_id, quantity: Number(it.quantity), unit, price: Number(it.price || 0), reason: it.reason, condition: it.condition, roll_ids: it.roll_ids || [] };
      });
    if (!form.supplier_id) { setError("Supplier wajib dipilih."); return; }
    if (items.length === 0) { setError("Minimal satu item dengan qty > 0."); return; }
    try {
      const res = await axios.post(`${API}/purchase-returns`, { ...form, items });
      setNotice(`Retur ${res.data.number} dibuat (${res.data.status === "pending_approval" ? "menunggu approval" : "draft"}).`);
      setShowForm(false);
      setForm({ supplier_id: "", po_id: "", warehouse_id: "", reason: "", notes: "", items: [blankItem], submit_now: true });
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal membuat retur.");
    }
  }

  async function act(id, action, body) {
    try {
      const urls = {
        submit: `${API}/purchase-returns/${id}/submit`,
        approve: `${API}/purchase-returns/${id}/approve`,
        reject: `${API}/purchase-returns/${id}/reject`,
      };
      const res = await axios.post(urls[action], body || {});
      const labels = { submit: "disubmit", approve: "disetujui", reject: "ditolak" };
      setNotice(`Retur ${res.data.number} ${labels[action]}.${res.data.debit_note_number ? ` Nota debit: ${res.data.debit_note_number}` : ""}`);
      setDetail(null);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || `Gagal ${action}.`);
    }
  }

  async function handleDelete(id) {
    try {
      const res = await axios.delete(`${API}/purchase-returns/${id}`);
      setNotice(`Retur ${res.data?.number || ""} dihapus.`);
      setDetail(null);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menghapus retur.");
    }
  }

  // R4 — aksi supplier RMA lifecycle (panel tetap terbuka & refresh dgn dokumen terbaru).
  async function lifecycleAct(ret, action, body) {
    try {
      const urls = {
        ship: `${API}/purchase-returns/${ret.id}/ship-to-supplier`,
        accept: `${API}/purchase-returns/${ret.id}/supplier-accept`,
        supplier_reject: `${API}/purchase-returns/${ret.id}/supplier-reject`,
        goods_back: `${API}/purchase-returns/${ret.id}/goods-back`,
      };
      const labels = {
        ship: "dikirim ke supplier", accept: "diterima supplier",
        supplier_reject: "ditolak supplier", goods_back: "barang dikembalikan ke gudang",
      };
      const res = await axios.post(urls[action], body || {});
      setNotice(`Retur ${res.data.number} ${labels[action]}.${res.data.debit_note_number && action === "accept" ? ` Nota debit: ${res.data.debit_note_number}` : ""}`);
      setDetail(res.data);   // keep panel open with refreshed doc
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || `Gagal ${action}.`);
    }
  }

  // R5.4b — panel memanggil endpoint reverse sendiri; parent hanya refresh + notifikasi.
  const onReversed = (doc) => {
    const sum = doc?._reversal_summary || {};
    setNotice(`Retur ${doc.number} dibatalkan (reversal). Barang dikembalikan ke stok (${sum.rolls_restored || 0} roll), jurnal dibalik.`);
    setDetail(doc);
    loadAll();
  };

  const supName = (id) => suppliers.find((s) => s.id === id)?.name || "—";
  // Penyaringan tab & pencarian sudah dilakukan SERVER (?status & ?q).
  const filtered = returns;
  const counts = TABS.reduce((acc, t) => ({ ...acc, [t.key]: Number(statusCounts[t.key] || 0) }), {});
  const supplierPOs = pos.filter((p) => !form.supplier_id || p.supplier_id === form.supplier_id);

  // Data untuk RollPickerModal (item aktif)
  const pickerItem = rollPicker != null ? form.items[rollPicker.itemIndex] : null;
  const pickerProduct = pickerItem ? products.find((p) => p.id === pickerItem.product_id) : null;

  return (
    <div data-testid="purchase-returns-view">
      {notice && <div className="notice-bar success" data-testid="pret-notice"><span>{notice}</span><button onClick={() => setNotice("")}><X size={13} /></button></div>}
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="pret-error" />
      <ErrorNotice message={paged.error} onRetry={paged.refresh} testId="pret-list-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <RotateCcw size={16} className="text-[#0058CC]" />
            <h2 data-testid="purchase-returns-title">Retur Beli (Nota Debit)</h2>
          </div>
          <button data-testid="create-return-button" onClick={() => setShowForm(!showForm)} className="primary-button">
            <Plus size={13} /> Buat Retur
          </button>
        </div>
        <div className="section-body">
          <LineFilter value={lineFilter} onChange={setLineFilter} storageKey="purchase-returns"
                      allowed={currentUser?.allowed_line_codes} className="mb-2"
                      testId="pret-line-filter" />
          <div className="relative mb-2 max-w-sm">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input
              data-testid="pret-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cari nomor, supplier, PO, atau no. nota debit…"
              className="field w-full !pl-8 !py-1.5"
            />
            {search && (
              <button data-testid="pret-search-clear" onClick={() => setSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9A9BA3] hover:text-[#3C3C43]"><X size={13} /></button>
            )}
          </div>
          <div className="tab-bar">
            {TABS.map((t) => (
              <button key={t.key} data-testid={`pret-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                {t.label}<span className="tab-badge">{counts[t.key]}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Create form */}
      {/* FASE P4 — form retur beli menjadi POP-UP (dulu menyelip di atas daftar retur;
          pada layar 13" tabelnya terdorong keluar layar). Logika form tidak diubah. */}
      <FormModal
        open={showForm}
        onClose={() => setShowForm(false)}
        title="Buat Retur Beli"
        subtitle="Pilih PO & roll yang dikembalikan ke supplier"
        icon={RotateCcw}
        size="lg"
        testId="purchase-return-form"
        onSubmit={handleSubmit}
        submitLabel="Buat Retur"
        submitTestId="submit-return-button"
        error={error}
      >
        <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <Field label="Supplier" req>
                <KNSelect data-testid="return-supplier-select" value={form.supplier_id} onValueChange={(v) => setForm({ ...form, supplier_id: v, po_id: "" })} className="field" placeholder="Pilih Supplier"
                  options={suppliers.filter((s) => s.status !== "inactive").map((s) => ({ value: s.id, label: `${s.code} · ${s.name}` }))} />
              </Field>
              <Field label="PO Referensi (opsional)">
                <KNSelect data-testid="return-po-select" value={form.po_id} onValueChange={onSelectPO} className="field" placeholder="Tanpa PO"
                  options={[{ value: "", label: "— Tanpa PO —" }, ...supplierPOs.map((p) => ({ value: p.id, label: `${p.po_number} · ${formatCurrency(p.total_amount)}` }))]} />
              </Field>
              <Field label="Gudang" req>
                <KNSelect data-testid="return-warehouse-select" value={form.warehouse_id} onValueChange={(v) => setForm({ ...form, warehouse_id: v })} className="field" placeholder="Pilih Gudang"
                  options={warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }))} />
              </Field>
            </div>

            {/* Items */}
            <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
              <div className="grid grid-cols-[1.6fr_80px_110px_1fr_110px_36px] px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
                <span>Produk</span><span>Qty</span><span>Harga</span><span>Alasan</span><span>Kondisi</span><span></span>
              </div>
              {form.items.map((it, i) => {
                const picked = it.roll_ids?.length || 0;
                return (
                  <div key={i} className="border-b border-[#EFF0F2] last:border-0">
                    <div className="grid grid-cols-[1.6fr_80px_110px_1fr_110px_36px] gap-1.5 items-center px-2.5 py-1.5">
                      <KNSelect data-testid={`return-item-product-${i}`} value={it.product_id} onValueChange={(v) => updateItemProduct(i, v)} className="field !py-1" placeholder="Produk"
                        options={products.map((p) => ({ value: p.id, label: `${p.sku} · ${p.name}` }))} />
                      <input data-testid={`return-item-qty-${i}`} type="number" value={it.quantity} onChange={(e) => updateItem(i, { quantity: e.target.value })}
                        disabled={picked > 0} title={picked > 0 ? "Qty otomatis dari roll terpilih" : ""}
                        className={`field !py-1 ${picked > 0 ? "opacity-70 cursor-not-allowed" : ""}`} placeholder="0" />
                      <input type="number" value={it.price} onChange={(e) => updateItem(i, { price: e.target.value })}
                        disabled={picked > 0} title={picked > 0 ? "Harga otomatis dari roll terpilih" : ""}
                        className={`field !py-1 ${picked > 0 ? "opacity-70 cursor-not-allowed" : ""}`} placeholder="harga" />
                      <KNSelect value={it.reason} onValueChange={(v) => updateItem(i, { reason: v })} className="field !py-1" options={REASONS} />
                      <KNSelect value={it.condition} onValueChange={(v) => updateItem(i, { condition: v })} className="field !py-1"
                        options={[{ value: "damaged", label: "Rusak" }, { value: "ok", label: "Baik" }]} />
                      <button className="icon-button text-red-400" onClick={() => setForm((f) => ({ ...f, items: f.items.filter((_, idx) => idx !== i) }))}><X size={13} /></button>
                    </div>

                    {/* Retur presisi: pilih roll/lot spesifik */}
                    <div className="flex flex-wrap items-center gap-1.5 px-2.5 pb-2">
                      <button
                        type="button"
                        data-testid={`return-pick-rolls-${i}`}
                        disabled={!it.product_id}
                        onClick={() => it.product_id && setRollPicker({ itemIndex: i })}
                        className="inline-flex items-center gap-1 rounded border border-[#E4D4F0] bg-[#FBF5FF] px-2 py-0.5 text-[10.5px] font-semibold text-[#6B219A] hover:bg-[#F3E7FB] disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <Layers size={11} /> {picked ? `${picked} roll dipilih` : "Pilih Roll (retur presisi)"}
                      </button>
                      {picked > 0 && (
                        <>
                          {it.rolls.slice(0, 6).map((r) => (
                            <span key={r.roll_id} data-testid={`return-item-${i}-roll-${r.roll_id}`}
                              className="inline-flex items-center gap-1 rounded border border-[#EFF0F2] bg-white px-1.5 py-0.5 text-[10px] text-[#6B6B73]">
                              <span className="font-mono text-[#6B219A]">{r.roll_no || r.roll_id}</span>
                              {r.lot && <span className="text-[#B0B0B8]">·{r.lot}</span>}
                              <span className="tabular-nums">· {formatQty(r.qty_remaining)}</span>
                            </span>
                          ))}
                          {it.rolls.length > 6 && <span className="text-[10px] text-[#8E8E93]">+{it.rolls.length - 6} lagi</span>}
                          <button type="button" data-testid={`return-clear-rolls-${i}`} onClick={() => clearRolls(i)}
                            className="text-[10px] text-[#C0392B] underline hover:no-underline">hapus roll</button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
              <button data-testid="return-add-item" onClick={() => setForm((f) => ({ ...f, items: [...f.items, blankItem] }))} className="w-full py-1.5 text-[11px] text-[#0058CC] font-semibold hover:bg-[#F5F9FF]">+ Tambah Item</button>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Alasan Retur">
                <input data-testid="return-reason-input" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} className="field" placeholder="Keterangan retur" />
              </Field>
              <Field label="Catatan">
                <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="field" placeholder="Catatan tambahan" />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-[11.5px] text-[#3C3C43]">
              <input data-testid="return-submit-now" type="checkbox" checked={form.submit_now} onChange={(e) => setForm({ ...form, submit_now: e.target.checked })} />
              Langsung ajukan persetujuan (jika tidak dicentang, disimpan sebagai draf)
            </label>
        </div>
      </FormModal>

      {/* List */}
      <div className="section-card">
        <div className="overflow-hidden">
          <div className="grid grid-cols-[100px_1.3fr_110px_120px_110px_120px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Nomor</span><span>Supplier / PO</span><span className="text-right">Nilai</span><span>Nota Debit</span><span>Status</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat retur...</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]">
              <RotateCcw className="mx-auto mb-2 text-gray-300" size={28} />
              <p>{search.trim()
                ? `Tidak ada retur beli yang cocok dengan “${search.trim()}”.`
                : "Belum ada retur beli."}</p>
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
              {filtered.map((r) => (
                <div key={r.id} data-testid={`return-row-${r.id}`} onClick={() => setDetail(r)} className="grid grid-cols-[100px_1.3fr_110px_120px_110px_120px] items-center px-3 py-2.5 hover:bg-[#FAFBFC] cursor-pointer">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{r.number}</span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{r.supplier_name || supName(r.supplier_id)}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate">
                      {r.po_number || "Tanpa PO"} · {r.items?.length || 0} item
                      {(() => { const rc = (r.items || []).reduce((a, it) => a + ((it.roll_ids || it.rolls || []).length), 0); return rc > 0 ? ` · ${rc} roll presisi` : ""; })()}
                    </p>
                  </div>
                  <span className="text-[12px] font-bold tabular-nums text-right text-amber-700">{formatCurrency(r.total_amount)}</span>
                  <span className="text-[11px] font-semibold text-[#0058CC]">{r.debit_note_number || "—"}</span>
                  <div className="flex flex-col items-start gap-0.5">
                    <StatusPill status={r.status} />
                    {r.supplier_flow && r.supplier_status && SUP_LABEL[r.supplier_status] && (
                      <span data-testid={`pret-supplier-status-${r.id}`}
                        className="inline-flex items-center rounded px-1.5 py-0.5 text-[9px] font-semibold bg-[#F1F5FF] text-[#1B4F9C] border border-[#DBE7FF]">
                        {SUP_LABEL[r.supplier_status]}
                      </span>
                    )}
                    {r.origin_sales_return_number && (
                      <span className="text-[9px] text-[#6B219A]" title="Dari retur jual">↩ {r.origin_sales_return_number}</span>
                    )}
                  </div>
                  <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                    {r.status === "draft" && (
                      <>
                        <button data-testid={`return-submit-${r.id}`} onClick={() => act(r.id, "submit")} className="secondary-button !px-2 !py-1 text-[11px]"><Send size={11} /> Ajukan</button>
                        {canDelete && (
                          <button data-testid={`return-delete-${r.id}`} onClick={() => setDeleteTarget(r)} className="danger-button !px-2 !py-1 text-[11px]" title="Hapus retur draf"><Trash2 size={11} /></button>
                        )}
                      </>
                    )}
                    {r.status === "pending_approval" && canApprove && (
                      <>
                        <button data-testid={`return-approve-${r.id}`} onClick={() => act(r.id, "approve", { notes: "" })} className="primary-button !px-2 !py-1 text-[11px]"><CheckCircle size={11} /> Setujui</button>
                        <button data-testid={`return-reject-${r.id}`} onClick={() => setRejectTarget(r)} className="danger-button !px-2 !py-1 text-[11px]"><XCircle size={11} /></button>
                      </>
                    )}
                    {(r.status === "approved" || r.status === "rejected") && (
                      <span className="text-[10.5px] text-[#9A9BA3]">{r.approved_by || r.rejected_by || "—"}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* P2 — kontrol halaman retur beli */}
      {!loading && filtered.length > 0 && (
        <PaginationBar
          page={paged.page} pageSize={paged.pageSize} total={paged.total}
          hasMore={paged.hasMore} loading={paged.loading}
          onPrev={paged.prev} onNext={paged.next} onPageSize={paged.setPageSize}
          testId="pret-pager" label="retur beli"
          exportConfig={{ columns: CSV_COLUMNS, rows: filtered,
            fetchAll: paged.fetchAll, filename: "retur-beli" }}
        />
      )}

      <ReturnDetailPanel
        ret={detail}
        supName={supName}
        canApprove={canApprove}
        canDelete={canDelete}
        onClose={() => setDetail(null)}
        onSubmit={(r) => act(r.id, "submit")}
        onApprove={(r) => act(r.id, "approve", { notes: "" })}
        onReject={(r) => { setDetail(null); setRejectTarget(r); }}
        onDelete={(r) => { setDetail(null); setDeleteTarget(r); }}
        onShip={(r) => lifecycleAct(r, "ship", {})}
        onSupplierAccept={(r, outcome, refundAccount) => lifecycleAct(r, "accept", { outcome, refund_account_code: refundAccount || "" })}
        onSupplierReject={(r, reason) => lifecycleAct(r, "supplier_reject", { reason })}
        onGoodsBack={(r, regrade) => lifecycleAct(r, "goods_back", { regrade })}
        onReverse={onReversed}
      />

      <ConfirmModal
        open={!!rejectTarget}
        title={`Tolak ${rejectTarget?.number || "Retur"}`}
        message="Berikan alasan penolakan retur (tersimpan di riwayat)."
        confirmLabel="Tolak Retur"
        danger
        withReason
        reasonLabel="Alasan penolakan"
        reasonPlaceholder="Mis. barang tidak memenuhi syarat retur supplier."
        onConfirm={async (reason) => { await act(rejectTarget.id, "reject", { notes: reason }); setRejectTarget(null); }}
        onCancel={() => setRejectTarget(null)}
        testId="return-reject-modal"
      />

      <ConfirmModal
        open={!!deleteTarget}
        title={`Hapus ${deleteTarget?.number || "Retur"}`}
        message="Retur draf ini akan dihapus permanen. Tindakan tidak dapat dibatalkan."
        confirmLabel="Hapus Retur"
        danger
        onConfirm={async () => { await handleDelete(deleteTarget.id); setDeleteTarget(null); }}
        onCancel={() => setDeleteTarget(null)}
        testId="return-delete-modal"
      />

      <RollPickerModal
        open={rollPicker != null}
        productId={pickerItem?.product_id || null}
        productLabel={pickerProduct ? `${pickerProduct.sku} · ${pickerProduct.name}` : ""}
        supplierId={form.supplier_id || undefined}
        poId={form.po_id || undefined}
        warehouseId={form.warehouse_id || undefined}
        entityId={selectedEntity}
        initialSelected={pickerItem?.roll_ids || []}
        onClose={() => setRollPicker(null)}
        onConfirm={confirmRolls}
      />
    </div>
  );
}

function Field({ label, req, children }) {
  return (
    <div>
      <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">{label} {req && <span className="req">*</span>}</label>
      {children}
    </div>
  );
}
