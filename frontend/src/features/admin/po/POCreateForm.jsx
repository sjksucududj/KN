import { useEffect, useState } from "react";
import { Plus, XCircle, Sparkles, AlertTriangle, Receipt } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import axios, { API } from "../../../services/apiClient";
import KNSelect from "../../../components/KNSelect";
import DecimalInput from "../../../components/DecimalInput";
import UomConvertHint from "../../../components/UomConvertHint";
import useUomConversions from "../../../hooks/useUomConversions";
import useDomainEnums from "../../../hooks/useDomainEnums";
import { parseDecimal } from "../../../utils/decimalInput";
import POBudgetPanel from "./POBudgetPanel";
import GroupEntityBadge, { GroupEntityNotice, isGroupEntityPartner }
  from "../../../components/GroupEntityBadge";

/**
 * POCreateForm — form buat Purchase Order baru (collapsible).
 * Props: formData, setFormData, newItem, setNewItem,
 *        products, warehouses, onSubmit, onCancel, onAddItem, onRemoveItem
 * Depth #3 — auto-isi harga & unit dari price-list supplier saat produk dipilih.
 */
export default function POCreateForm({
  formData, setFormData,
  newItem, setNewItem,
  products, warehouses, suppliers = [],
  onSubmit, onCancel,
  onAddItem, onRemoveItem,
  submitting = false,
  variant = "card",
}) {
  // FASE P5 — `variant="modal"`: kartu & judulnya sendiri dilepas karena `FormModal`
  // sudah menyediakannya (anti kartu-di-dalam-kartu & judul bertumpuk). Tombol aksi
  // TETAP milik komponen ini: label & keadaan matinya bergantung pada `supplierIsGroupEntity`
  // yang dihitung di sini (E7.2), jadi memindahkannya ke kaki FormModal akan menghapus
  // pagar "pemasok itu badan usaha grup — pakai menu Antar Entitas".
  const isModal = variant === "modal";
  const activeSuppliers = suppliers.filter((s) => s.status !== "inactive");
  // FASE E-7 (E7.2) — pemasok yang dipilih; dipakai untuk mengenali badan usaha grup
  // (lencana + pita penjelas + tombol Buat PO dimatikan sebelum ditolak server).
  const selectedSupplier = suppliers.find((s) => s.id === formData.supplier_id) || null;
  const supplierIsGroupEntity = isGroupEntityPartner(selectedSupplier);
  // Fase A · PS-09/D-19 — opsi grade dari registry; TIDAK ada nilai default.
  const { options: enumOptions } = useDomainEnums();
  const gradeOptions = enumOptions("grade");
  const [priceHint, setPriceHint] = useState("");
  const [priceRef, setPriceRef] = useState(0);   // harga acuan (untuk warning deviasi)
  const [priceSource, setPriceSource] = useState("");  // FASE F-2 — sumber harga (contract/last/master)
  const [priceBelowMoq, setPriceBelowMoq] = useState(false);  // FASE F-2 — di bawah MOQ kontrak
  // P0-1 — config pajak efektif (PPN Masukan) untuk estimasi breakdown live.
  const [taxCfg, setTaxCfg] = useState({ ppn_rate: 12, ppn_mode: "excluded", is_pkp: true, dpp_nilai_lain: false });

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/settings/effective`)
      .then((res) => {
        const t = res.data?.tax || {};
        if (alive) setTaxCfg({
          ppn_rate: Number(t.ppn_rate ?? 12),
          dpp_nilai_lain: !!t.dpp_nilai_lain,
          ppn_mode: t.ppn_mode || "excluded",
          is_pkp: t.is_pkp !== false,
        });
      })
      .catch(() => { /* default 11% excluded */ });
    return () => { alive = false; };
  }, []);

  // PS-15/R5 — nilai input boleh berupa teks berkoma ("10,5"); num() menormalkan
  // untuk semua hitungan tampilan (backend memakai parse_decimal yang setara).
  const num = (v) => { const n = parseDecimal(v); return Number.isNaN(n) ? 0 : n; };
  const round2 = (n) => Math.round((num(n) + Number.EPSILON) * 100) / 100;
  const clampPct = (v) => Math.min(Math.max(num(v), 0), 100);

  // P0-1 — estimasi breakdown harga PO (mirror compute_order_pricing backend).
  const pricing = (() => {
    let gross = 0, itemDisc = 0;
    for (const it of formData.items) {
      const sub = round2(num(it.price) * num(it.quantity));
      const da = round2(sub * clampPct(it.discount_percent) / 100);
      gross += sub; itemDisc += da;
    }
    gross = round2(gross); itemDisc = round2(itemDisc);
    const afterItem = round2(gross - itemDisc);
    const odp = clampPct(formData.order_discount_percent);
    const oda = round2(afterItem * odp / 100);
    const net = round2(afterItem - oda);
    const discTotal = round2(itemDisc + oda);
    const rate = Number(taxCfg.ppn_rate) || 0;
    const dppFactor = taxCfg.dpp_nilai_lain ? 11 / 12 : 1;
    const effRate = rate * dppFactor;
    const mode = taxCfg.ppn_mode || "excluded";
    const noTax = formData.tax_mode === "non_ppn" || !taxCfg.is_pkp || rate <= 0;
    let dpp = net, ppn = 0, grand = net;
    if (!noTax) {
      if (mode === "included") { const hj = round2(net / (1 + effRate / 100)); dpp = round2(hj * dppFactor); ppn = round2(net - hj); grand = net; }
      else { dpp = round2(net * dppFactor); ppn = round2(net * effRate / 100); grand = round2(net + ppn); }
    }
    return { gross, itemDisc, oda, discTotal, net, dpp, ppn, grand, rate: noTax ? 0 : rate, mode, noTax, dppNilaiLain: !noTax && !!taxCfg.dpp_nilai_lain };
  })();

  function handleSupplierSelect(v) {
    if (v) {
      const s = suppliers.find((x) => x.id === v);
      setFormData({
        ...formData, supplier_id: v,
        supplier_name: s?.name || "",
        supplier_contact: s ? [s.pic_name, s.phone].filter(Boolean).join(" · ") : formData.supplier_contact,
      });
    } else {
      setFormData({ ...formData, supplier_id: "", supplier_name: "" });
    }
    setPriceHint(""); setPriceRef(0);
  }

  // Depth #3 — resolusi harga supplier untuk auto-isi item (per produk & qty).
  async function resolveItemPrice(productId, qty, baseUnit) {
    if (!productId) { setPriceHint(""); setPriceRef(0); setPriceSource(""); setPriceBelowMoq(false); return; }
    try {
      // FASE F-2 — resolver terpadu (kontrak pembelian → harga terakhir → master).
      const res = await axios.get(`${API}/purchase-orders/resolve-sourcing`, {
        params: { supplier_id: formData.supplier_id || "", product_id: productId, qty: qty || 0, unit: baseUnit || "" },
      });
      const r = res.data || {};
      setPriceSource(r.source || "");
      setPriceRef(["contract", "price_list", "supplier_item"].includes(r.source) ? Number(r.price) || 0 : 0);
      if (r.price > 0) {
        setNewItem((cur) => ({ ...cur, price: r.price, unit: r.unit || cur.unit || baseUnit }));
        const map = {
          contract: `Harga KONTRAK ${r.contract_number}: ${formatCurrency(r.price)} / ${r.unit}`,
          supplier_item: `Harga beli terakhir${r.supplier_sku ? ` (${r.supplier_sku})` : ""}: ${formatCurrency(r.price)} / ${r.unit}`,
          price_list: `Harga price-list supplier: ${formatCurrency(r.price)} / ${r.unit}`,
          product_master: `Harga acuan master produk: ${formatCurrency(r.price)} / ${r.unit}`,
        };
        let hint = map[r.source] || `Harga acuan: ${formatCurrency(r.price)} / ${r.unit}`;
        setPriceHint(hint);
        setPriceBelowMoq(!!r.below_moq);
      } else {
        setPriceHint(""); setPriceSource(""); setPriceBelowMoq(false);
      }
    } catch (_) { /* diam: auto-isi opsional */ }
  }

  function handleItemProductSelect(v) {
    const prod = products.find((p) => p.id === v);
    const baseUnit = prod?.base_unit || newItem.unit || "meter";
    setNewItem({ ...newItem, product_id: v, unit: baseUnit });
    if (!v) { setPriceHint(""); return; }
    resolveItemPrice(v, newItem.quantity, baseUnit);
  }

  // Fase 8 (Catch-weight) — faktor kg per base unit & opsi satuan order per item.
  const { unitOptions: uomUnitOptions, perDocFactorUnits } = useUomConversions();
  const uomCatalogUnits = uomUnitOptions();
  const selProduct = products.find((p) => p.id === newItem.product_id);
  const selBaseUnit = selProduct?.base_unit || "meter";
  const selKgPerM = selProduct
    ? (Number(selProduct.kg_per_meter) > 0
        ? Number(selProduct.kg_per_meter)
        : (Number(selProduct.gramasi || 0) * Number(selProduct.lebar || 0)) / 1000)
    : 0;
  const catchWeight = selKgPerM > 0;
  // FASE B (D-06/D-07) — opsi satuan dari KATALOG server (bukan daftar hardcode) dan
  // konversi/pratinjau dihitung server (lihat <UomConvertHint/>), bukan rumus di FE.
  const unitOptions = (() => {
    const opts = [{ value: selBaseUnit, label: `${selBaseUnit} (satuan dasar)` }];
    (uomCatalogUnits || []).forEach((u) => {
      if (u.value !== selBaseUnit) opts.push(u);
    });
    if (newItem.unit && !opts.some((o) => o.value === newItem.unit)) {
      opts.push({ value: newItem.unit, label: newItem.unit });
    }
    return opts;
  })();

  function handleItemQtyChange(e) {
    const raw = e.target.value;
    const qty = num(raw);
    setNewItem({ ...newItem, quantity: raw });
    if (newItem.product_id) {
      const prod = products.find((p) => p.id === newItem.product_id);
      resolveItemPrice(newItem.product_id, qty, prod?.base_unit || newItem.unit || "meter");
    }
  }
  return (
    <div data-testid="create-po-form" className={isModal ? "" : "section-card mb-3"}>
      {!isModal && (
        <div className="section-head">
          <h2 className="text-[13px] font-bold">Buat Pesanan Pembelian Baru</h2>
        </div>
      )}
      <div className={isModal ? "space-y-3" : "section-body space-y-3"}>
        {/* E7.2 — jelaskan LEBIH DULU bila lawan transaksinya badan usaha grup, supaya
            tombol tidak "diam-diam gagal" dan pengguna langsung tahu jalan yang benar. */}
        {supplierIsGroupEntity && (
          <GroupEntityNotice partner={selectedSupplier} />
        )}
        {/* Header fields */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Supplier (Master)</label>
            <KNSelect data-testid="supplier-master-select" value={formData.supplier_id || ""}
              onValueChange={handleSupplierSelect}
              className="field" placeholder="Pilih dari master / isi manual"
              options={[
                { value: "", label: "— Isi manual / tanpa master —" },
                ...activeSuppliers.map((s) => ({
                  value: s.id,
                  // E7.2 — badan usaha grup ditandai SEJAK di daftar pilihan, supaya
                  // tidak ada yang memilihnya lalu ditolak tanpa penjelasan.
                  label: `${s.code} · ${s.name}${isGroupEntityPartner(s) ? "  (Entitas grup)" : ""}`,
                })),
              ]}
            />
            {selectedSupplier && isGroupEntityPartner(selectedSupplier) && (
              <div className="mt-1"><GroupEntityBadge partner={selectedSupplier} /></div>
            )}
          </div>
          <div>
            <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">
              Nama Supplier {!formData.supplier_id && <span className="req">*</span>}
            </label>
            <input data-testid="supplier-name-input" type="text" value={formData.supplier_name}
              disabled={!!formData.supplier_id}
              onChange={(e) => setFormData({ ...formData, supplier_name: e.target.value })}
              className="field disabled:bg-gray-100 disabled:text-gray-500" placeholder="PT Supplier Textile" />
          </div>
          <div>
            <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Kontak Supplier</label>
            <input data-testid="supplier-contact-input" type="text" value={formData.supplier_contact}
              onChange={(e) => setFormData({ ...formData, supplier_contact: e.target.value })}
              className="field" placeholder="081234567890" />
          </div>
          <div>
            <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Gudang *</label>
            <KNSelect data-testid="warehouse-select" value={formData.warehouse_id}
              onValueChange={v => setFormData({ ...formData, warehouse_id: v })}
              className="field" placeholder="Pilih Gudang"
              options={[
                { value: "", label: "Pilih Gudang" },
                ...warehouses.map(wh => ({ value: wh.id, label: `${wh.name} (${wh.code})` })),
              ]}
            />
          </div>
          <div>
            <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Perkiraan Pengiriman</label>
            <input data-testid="delivery-date-input" type="date" value={formData.expected_delivery_date}
              onChange={(e) => setFormData({ ...formData, expected_delivery_date: e.target.value })}
              className="field" />
          </div>
        </div>

        <div>
          <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Catatan</label>
          <textarea data-testid="po-notes-input" value={formData.notes}
            onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            className="field" rows="2" placeholder="Catatan tambahan..." />
        </div>

        {/* Add Item row */}
        <div className="bg-[#FAFBFC] rounded-md border border-[#EFF0F2] p-2.5">
          <p className="text-[10.5px] font-bold uppercase text-[#6B6B73] mb-2">Tambah Item</p>
          {/* FASE B — kolom satuan & grade dilebarkan agar label satuan (mis. "roll",
              "yard") dan grade terbaca penuh setelah katalog satuan diperluas. */}
          <div className="grid grid-cols-[1fr_72px_104px_64px_92px_56px_104px_auto] gap-2">
            <KNSelect data-testid="item-product-select" value={newItem.product_id}
              onValueChange={handleItemProductSelect}
              className="field" placeholder="Pilih Produk"
              options={[
                { value: "", label: "Pilih Produk" },
                ...products.map(p => ({ value: p.id, label: `${p.sku} - ${p.name}` })),
              ]}
            />
            <DecimalInput data-testid="item-qty-input" placeholder="Qty" min={0}
              value={newItem.quantity}
              onChange={(v) => handleItemQtyChange({ target: { value: v } })} />
            <KNSelect data-testid="item-unit-select" value={newItem.unit || selBaseUnit}
              onValueChange={(v) => setNewItem({ ...newItem, unit: v })}
              className="field" placeholder="Unit"
              options={unitOptions} />
            {/* FASE U — DUA SATUAN: jumlah roll yang dipesan (rencana). Dibiarkan
                kosong = "tidak menyebut jumlah roll" → dokumen tampil "—", bukan 0. */}
            <input data-testid="item-qty-rolls-input" type="number" min="0" placeholder="Roll"
              title="Jumlah roll (gulungan) yang dipesan — boleh dikosongkan"
              value={newItem.qty_rolls ?? ""}
              onChange={(e) => setNewItem({ ...newItem, qty_rolls: e.target.value })}
              className="field" />
            <DecimalInput data-testid="item-price-input" placeholder="Harga" min={0}
              value={newItem.price}
              onChange={(v) => setNewItem({ ...newItem, price: v })} />
            <input data-testid="item-discount-input" type="number" placeholder="Disc%" min="0" max="100"
              title="Diskon item (%)"
              value={newItem.discount_percent}
              onChange={(e) => setNewItem({ ...newItem, discount_percent: parseFloat(e.target.value) || 0 })}
              className="field" />
            <KNSelect data-testid="item-expected-grade-select" value={newItem.expected_grade || ""}
              onValueChange={(v) => setNewItem({ ...newItem, expected_grade: v })}
              className="field" placeholder="Grade *" options={gradeOptions} />
            <button data-testid="add-item-button" onClick={onAddItem}
              className="primary-button !px-3">
              <Plus size={13} />
            </button>
          </div>
          {/* Keputusan pemilik: panjang 1 PANEL berbeda per pesanan → faktornya
              ditulis di baris dokumen. Kolom ini hanya muncul untuk satuan yang
              masternya menandai "faktor per dokumen" (mis. panel). */}
          {perDocFactorUnits.includes(String(newItem.unit || selBaseUnit).toLowerCase()) && (
            <div className="mt-1.5 flex items-center gap-2">
              <span className="text-[10.5px] font-semibold text-[#6B6B73]">
                1 {newItem.unit || selBaseUnit} pada pesanan ini =
              </span>
              <DecimalInput data-testid="item-unit-factor-input" placeholder="mis. 1,6" min={0}
                value={newItem.unit_factor}
                onChange={(v) => setNewItem({ ...newItem, unit_factor: v })} />
              <span className="text-[10.5px] text-[#6B6B73]">{selBaseUnit}</span>
            </div>
          )}
          <UomConvertHint testId="po-uom-hint" productId={newItem.product_id}
            baseUnit={selBaseUnit} qty={newItem.quantity} unit={newItem.unit || selBaseUnit}
            suffix={num(newItem.price) > 0 ? ` · harga per ${newItem.unit || selBaseUnit}` : ""} />
          {priceHint && (
            <p data-testid="po-price-hint" className={`mt-1.5 text-[10.5px] flex items-center gap-1 ${priceSource === "contract" ? "text-[#1B7F4B]" : "text-[#0058CC]"}`}>
              {priceSource === "contract"
                ? <span className="text-[9px] font-bold rounded px-1 py-0.5 bg-[#E6F6EC] text-[#1B7F4B]">KONTRAK</span>
                : <Sparkles size={11} />}
              {priceHint}
            </p>
          )}
          {priceBelowMoq && (
            <p data-testid="po-moq-warning" className="mt-1 text-[10.5px] text-[#B26A00] flex items-center gap-1">
              <AlertTriangle size={11} /> Qty di bawah MOQ kontrak — cek minimum pesanan pemasok.
            </p>
          )}
          {priceRef > 0 && num(newItem.price) > priceRef && (
            <p data-testid="po-price-warning" className="mt-1 text-[10.5px] text-[#A8221A] flex items-center gap-1">
              <AlertTriangle size={11} /> Harga di atas daftar harga ({formatCurrency(priceRef)}) — PO mungkin butuh persetujuan.
            </p>
          )}
        </div>

        {/* Items list + ringkasan pajak/diskon (P0-1) */}
        {formData.items.length > 0 && (
          <>
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[1fr_72px_84px_52px_56px_88px_28px] px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Produk</span><span>Qty</span><span>Harga</span><span>Disc</span><span>Grade</span><span className="text-right">Subtotal</span><span></span>
            </div>
            {formData.items.map((item, i) => {
              const p = products.find((pr) => pr.id === item.product_id);
              const sub = round2(num(item.price) * num(item.quantity));
              const lt = round2(sub - sub * clampPct(item.discount_percent) / 100);
              return (
                <div key={i} data-testid={`po-item-row-${i}`}
                  className="grid grid-cols-[1fr_72px_84px_52px_56px_88px_28px] items-center px-2.5 py-1.5 border-b border-[#EFF0F2] last:border-0 text-[11.5px]">
                  <span className="truncate">{p?.sku} — {p?.name}</span>
                  <span className="font-semibold">{item.quantity} {item.unit}</span>
                  <span className="tabular-nums">{formatCurrency(item.price)}</span>
                  <span data-testid={`po-item-disc-${i}`} className="tabular-nums text-[#6B6B73]">{clampPct(item.discount_percent) > 0 ? `${clampPct(item.discount_percent)}%` : "—"}</span>
                  <span data-testid={`po-item-grade-${i}`} className="status-pill pill-muted">{item.expected_grade || "—"}</span>
                  <span data-testid={`po-item-linetotal-${i}`} className="tabular-nums text-right font-semibold">{formatCurrency(lt)}</span>
                  <button data-testid={`remove-item-${i}`} onClick={() => onRemoveItem(i)}
                    className="text-red-400 hover:text-red-600 justify-self-end">
                    <XCircle size={13} />
                  </button>
                </div>
              );
            })}
          </div>

          {/* Diskon order + mode PPN Masukan */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Diskon Pesanan (%)</label>
              <input data-testid="order-discount-input" type="number" min="0" max="100" placeholder="0"
                value={formData.order_discount_percent}
                onChange={(e) => setFormData({ ...formData, order_discount_percent: parseFloat(e.target.value) || 0 })}
                className="field" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Pajak (PPN Masukan)</label>
              <KNSelect data-testid="po-tax-mode-select" value={formData.tax_mode || ""}
                onValueChange={(v) => setFormData({ ...formData, tax_mode: v })}
                className="field" placeholder="Ikut konfigurasi"
                options={[
                  { value: "", label: taxCfg.is_pkp ? `PPN ${taxCfg.ppn_rate}% (ikut konfigurasi)` : "Tanpa PPN (non-PKP)" },
                  { value: "non_ppn", label: "Non-PPN (supplier non-PKP)" },
                ]}
              />
            </div>
          </div>

          {/* R6.3 — Budget Control: tag anggaran + pratinjau sisa anggaran */}
          <POBudgetPanel formData={formData} setFormData={setFormData}
            dppAmount={pricing.dpp} entityId={formData.entity_id || ""} />

          {/* Ringkasan estimasi harga PO */}
          <div data-testid="po-pricing-summary" className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3 text-[11.5px] space-y-1">
            <p className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase text-[#6B6B73] mb-1.5"><Receipt size={12} /> Ringkasan (Estimasi)</p>
            <div className="flex justify-between"><span className="text-[#6B6B73]">Subtotal</span><span data-testid="summary-subtotal" className="tabular-nums">{formatCurrency(pricing.gross)}</span></div>
            {pricing.itemDisc > 0 && <div className="flex justify-between"><span className="text-[#6B6B73]">Diskon item</span><span data-testid="summary-item-discount" className="tabular-nums text-[#A8221A]">− {formatCurrency(pricing.itemDisc)}</span></div>}
            {pricing.oda > 0 && <div className="flex justify-between"><span className="text-[#6B6B73]">Diskon pesanan</span><span data-testid="summary-order-discount" className="tabular-nums text-[#A8221A]">− {formatCurrency(pricing.oda)}</span></div>}
            <div className="flex justify-between"><span className="text-[#6B6B73]">DPP</span><span data-testid="summary-dpp" className="tabular-nums">{formatCurrency(pricing.dpp)}</span></div>
            <div className="flex justify-between"><span className="text-[#6B6B73]">PPN {pricing.rate > 0 ? `(${pricing.rate}%)` : ""}</span><span data-testid="summary-ppn" className="tabular-nums">{pricing.noTax ? "—" : formatCurrency(pricing.ppn)}</span></div>
            <div className="flex justify-between pt-1.5 mt-1 border-t border-[#E5E6E8] font-bold text-[12.5px]"><span>Total</span><span data-testid="summary-grand-total" className="tabular-nums text-[#007AFF]">{formatCurrency(pricing.grand)}</span></div>
          </div>
          </>
        )}

        <div className="flex gap-2">
          {/* E7.2 — tombol DIMATIKAN, bukan dibiarkan gagal di server: pesan pada tombol
              menjelaskan alasannya, dan pita di atas memberi satu klik ke jalan benar. */}
          <button data-testid="submit-po-button" onClick={onSubmit}
            disabled={submitting || supplierIsGroupEntity}
            title={supplierIsGroupEntity
              ? `${selectedSupplier?.name} adalah badan usaha di dalam grup — catat pembeliannya lewat menu Antar Entitas`
              : ""}
            className="flex-1 primary-button justify-center disabled:opacity-50 disabled:cursor-not-allowed">
            {supplierIsGroupEntity ? "Pakai menu Antar Entitas untuk badan usaha grup"
              : submitting ? "Memproses…" : "Buat PO & Auto-create Inbound Tasks"}
          </button>
          <button data-testid="cancel-form-button" onClick={onCancel} disabled={submitting}
            className="secondary-button">
            Batal
          </button>
        </div>
      </div>
    </div>
  );
}
