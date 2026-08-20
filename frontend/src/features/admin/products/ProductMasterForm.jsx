/**
 * ProductMasterForm (Fase A · PS-01/02/03/09/15) — form master produk tekstil.
 *
 * Dipisah dari `AdminView.jsx` (batas ukuran file) dan ditingkatkan agar patuh:
 *   R1  — stage/fabric_type/grade WAJIB dropdown dari registry (`useDomainEnums`)
 *   D-02 — fabric_type wajib sejak stage `yarn`
 *   D-22 — GSM + lebar wajib ≥ grey (woven); `yarn_count` wajib di stage yarn;
 *          untuk knit field terukur hanya disarankan (peringatan, tidak memblokir)
 *   PS-15 — semua input angka menerima koma-desimal via <DecimalInput>
 *
 * Props: product, setProduct, editingProductId, productError, saving,
 *        categoryOptions, onSave, onCancel, addConv, updateConv, removeConv
 */
import { AlertTriangle, CheckCircle2, Info, Plus, Save, XCircle } from "lucide-react";
import DecimalInput from "../../../components/DecimalInput";
import KNSelect from "../../../components/KNSelect";
import PantoneFinder from "../../../components/PantoneFinder";
import useDomainEnums from "../../../hooks/useDomainEnums";
import useUomConversions from "../../../hooks/useUomConversions";    // FASE U
import { uomSelectOptions } from "../../../utils/uomCatalog";        // FASE U
import { parseDecimal } from "../../../utils/decimalInput";

const TEXT_FIELDS = [
  ["sku", "SKU"], ["name", "Nama produk"], ["variant", "Varian"],
  ["motif", "Motif"], ["supplier", "Supplier"],
];
const MONEY_FIELDS = [["price", "Harga jual"], ["harga_pokok", "Harga pokok (HPP)"]];

export default function ProductMasterForm({
  product, setProduct, editingProductId, productError, saving = false,
  categoryOptions = [], salesOwners = [], onSave, onCancel, addConv, updateConv, removeConv,
}) {
  const { loading, error: enumError, options, labelOf, fieldRules, fieldLabels } = useDomainEnums();
  // FASE U — SATUAN DASAR produk dari MASTER SATUAN (`uoms`). Ini pemilih satuan yang
  // paling penting di seluruh aplikasi: `products.base_unit` adalah satuan kendali yang
  // dipakai stok, PO, SO, dan konversi. Sebelum ini daftarnya diketik 7 nilai di berkas
  // ini, sehingga pemilik yang menambah `PANEL` di master TIDAK bisa membuat satu pun
  // produk ber-satuan panel — masternya ada, gunanya tidak.
  useUomConversions();
  const baseUnitOptions = uomSelectOptions({
    dimensions: ["length", "weight", "count"],
    extra: [product.base_unit].filter(Boolean),
  });
  const set = (patch) => setProduct({ ...product, ...patch });

  const isExclusive = (product.exclusivity || "umum") === "sales_tertentu";
  const ownerIds = product.owner_sales_ids || [];
  const toggleOwner = (id) => {
    const next = ownerIds.includes(id) ? ownerIds.filter((x) => x !== id) : [...ownerIds, id];
    set({ owner_sales_ids: next });
  };

  const stage = product.stage || "finished";
  const fabric = product.fabric_type || "";
  const rules = fieldRules(stage, fabric);
  const isYarn = stage === "yarn";
  const gsm = parseDecimal(product.gramasi);
  const lebar = parseDecimal(product.lebar);
  const kgPerMeter = (gsm || 0) * (lebar || 0) / 1000;

  const valueOf = (f) => (f === "gramasi" ? gsm : f === "lebar" ? lebar : product[f]);
  const missing = rules.required.filter((f) => {
    const v = valueOf(f);
    return typeof v === "number" ? !(v > 0) : !String(v || "").trim();
  });
  const advisory = rules.recommended.filter((f) => {
    const v = valueOf(f);
    return typeof v === "number" ? !(v > 0) : !String(v || "").trim();
  });
  const req = (f) => rules.required.includes(f);
  const lbl = (f) => fieldLabels[f] || f;

  return (
    <div className="grid gap-2" data-testid="admin-product-form">
      {TEXT_FIELDS.map(([key, ph]) => (
        <input key={key} data-testid={`admin-product-${key}-input`} className="field" type="text"
          placeholder={ph} value={product[key] ?? ""}
          onChange={(e) => set({ [key]: e.target.value })} />
      ))}
      <KNSelect data-testid="admin-product-category-input" className="field"
        value={product.category ?? ""} placeholder="Pilih kategori"
        onValueChange={(v) => set({ category: v })} options={categoryOptions} />
      <KNSelect data-testid="admin-product-base_unit-input" className="field"
        value={product.base_unit ?? "meter"} placeholder="Satuan Dasar"
        onValueChange={(v) => set({ base_unit: v })} options={baseUnitOptions} />
      {MONEY_FIELDS.map(([key, ph]) => (
        <DecimalInput key={key} data-testid={`admin-product-${key}-input`} placeholder={ph}
          value={product[key] ?? ""} min={0} onChange={(v) => set({ [key]: v })} />
      ))}

      {/* ── Panel domain tekstil (Fase A) ─────────────────────────────────── */}
      <div data-testid="admin-product-domain-panel"
        className="grid gap-2 rounded-md border border-[#DCE7FA] bg-[#F6F9FF] p-2.5">
        <p className="text-[11px] font-bold uppercase tracking-wide text-[#0058CC]">
          Domain Tekstil (wajib · KN_18 Fase A)
        </p>
        {enumError && (
          <p data-testid="admin-product-enum-error"
            className="text-[11px] font-semibold text-[#D14343]">{enumError}</p>
        )}
        {loading ? (
          <p data-testid="admin-product-domain-loading" className="text-[11px] text-[#6B6B73]">
            Memuat registry enum domain…
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  Tahap Bahan (stage) *
                </label>
                <KNSelect data-testid="admin-product-stage-input" className="field"
                  value={stage} onValueChange={(v) => set({ stage: v })}
                  options={options("stage")} />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  Jenis Kain (fabric_type) {req("fabric_type") ? "*" : ""}
                </label>
                <KNSelect data-testid="admin-product-fabric_type-input" className="field"
                  value={fabric} placeholder="Pilih woven / knit"
                  onValueChange={(v) => set({ fabric_type: v })} options={options("fabric_type")} />
              </div>
            </div>
            {/* FASE L — LINI PRODUK: pembagian kerja MD (siapa yang mengerjakan &
                papan mana). Sengaja berdampingan dengan Jenis Kain supaya bedanya
                terlihat: jenis kain = FISIKA (menentukan rumus & satuan kendali),
                lini = PEMBAGIAN KERJA. Nilainya dari master (bisa ditambah pemilik),
                dan server menolak kombinasi yang bertentangan (INV-LINE-02). */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  Lini Produk (pembagian kerja)
                </label>
                <KNSelect data-testid="admin-product-line_code-input" className="field"
                  value={product.line_code ?? ""} placeholder="Belum bergolong lini"
                  onValueChange={(v) => set({ line_code: v })}
                  options={options("product_line", [{ value: "", label: "— belum bergolong —" }])} />
                <p className="mt-1 text-[10px] text-[#8E8E93]">
                  Menentukan siapa yang boleh mengerjakannya & chip penyaring di 12 layar.
                  Bukan pengganti Jenis Kain. Tambah lini baru di Pengaturan → Master →
                  Lini Produk.
                </p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  Grade *
                </label>
                <KNSelect data-testid="admin-product-grade-input" className="field"
                  value={product.grade ?? ""} placeholder="Pilih grade"
                  onValueChange={(v) => set({ grade: v })} options={options("grade")} />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  Gramasi (gsm) {req("gramasi") ? "*" : ""}
                </label>
                <DecimalInput data-testid="admin-product-gramasi-input" placeholder="mis. 180,5"
                  suffix="gsm" min={0} value={product.gramasi ?? ""}
                  invalid={missing.includes("gramasi")}
                  onChange={(v) => set({ gramasi: v })} />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  Lebar (meter) {req("lebar") ? "*" : ""}
                </label>
                <DecimalInput data-testid="admin-product-lebar-input" placeholder="mis. 1,15"
                  suffix="m" min={0} value={product.lebar ?? ""}
                  invalid={missing.includes("lebar")}
                  onChange={(v) => set({ lebar: v })} />
              </div>
            </div>
            {isYarn && (
              <div className="grid grid-cols-2 gap-2" data-testid="admin-product-yarn-fields">
                <div>
                  <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                    Nomor Benang {req("yarn_count") ? "*" : ""}
                  </label>
                  <input data-testid="admin-product-yarn_count-input" className="field"
                    placeholder="mis. 30s / 150D" value={product.yarn_count ?? ""}
                    onChange={(e) => set({ yarn_count: e.target.value })} />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                    Sistem Nomor Benang
                  </label>
                  <KNSelect data-testid="admin-product-yarn_count_system-input" className="field"
                    value={product.yarn_count_system ?? ""} placeholder="Ne / Nm / Denier / Tex"
                    onValueChange={(v) => set({ yarn_count_system: v })}
                    options={options("yarn_count_system")} />
                </div>
              </div>
            )}
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                Warna
              </label>
              <PantoneFinder triggerTestId="admin-product-color-input"
                value={product.color_code} valueName={product.color_name || product.color}
                valueHex={product.color_hex}
                onSelect={(c) => set({ color_code: c.code, color_name: c.name, color_hex: c.hex, color: c.name })}
                label="Pilih warna dari pustaka…" />
            </div>

            {missing.length > 0 ? (
              <p data-testid="admin-product-domain-missing"
                className="flex items-start gap-1 text-[11px] font-semibold text-[#D14343]">
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                Wajib dilengkapi untuk stage “{labelOf("stage", stage)}”: {missing.map(lbl).join(", ")}.
              </p>
            ) : (
              <p data-testid="admin-product-domain-ok"
                className="flex items-center gap-1 text-[11px] font-semibold text-[#1E7B34]">
                <CheckCircle2 size={12} /> Kelengkapan domain untuk stage “{labelOf("stage", stage)}” terpenuhi.
              </p>
            )}
            {advisory.length > 0 && (
              <p data-testid="admin-product-domain-advisory"
                className="flex items-start gap-1 text-[11px] text-[#8C4A00]">
                <Info size={12} className="mt-0.5 shrink-0" />
                Disarankan (tidak memblokir{fabric === "knit" ? " — knit dikendalikan kg" : ""}): {advisory.map(lbl).join(", ")}.
              </p>
            )}
          </>
        )}
      </div>

      {/* ── Kepemilikan / Eksklusivitas (PS-20 · "PO sendiri") ──────────────── */}
      <div data-testid="admin-product-exclusivity-panel"
        className="grid gap-2 rounded-md border border-[#E6DCFA] bg-[#F8F5FF] p-2.5">
        <p className="text-[11px] font-bold uppercase tracking-wide text-[#6D4AC0]">
          Kepemilikan Produk (PS-20 · "PO sendiri")
        </p>
        <div className="flex gap-1.5" role="group" aria-label="Eksklusivitas produk">
          <button type="button" data-testid="admin-product-excl-umum"
            onClick={() => set({ exclusivity: "umum", owner_sales_ids: [] })}
            className={`flex-1 rounded-md border px-2.5 py-1.5 text-[12px] font-semibold transition ${
              !isExclusive
                ? "border-[#6D4AC0] bg-[#6D4AC0] text-white"
                : "border-[#DcD3F0] bg-white text-[#6E6E73] hover:border-[#B9A6E8]"}`}>
            Umum (semua sales)
          </button>
          <button type="button" data-testid="admin-product-excl-exclusive"
            onClick={() => set({ exclusivity: "sales_tertentu" })}
            className={`flex-1 rounded-md border px-2.5 py-1.5 text-[12px] font-semibold transition ${
              isExclusive
                ? "border-[#6D4AC0] bg-[#6D4AC0] text-white"
                : "border-[#DcD3F0] bg-white text-[#6E6E73] hover:border-[#B9A6E8]"}`}>
            Eksklusif (sales tertentu)
          </button>
        </div>
        {isExclusive && (
          <div data-testid="admin-product-owner-picker" className="grid gap-1.5">
            <p className="text-[11px] text-[#6E6E73]">
              Pilih sales pemilik. Hanya mereka (dan admin/manajer) yang dapat <b>melihat</b> &
              <b> membuat SO</b> untuk produk ini — sales lain tidak melihat kodenya.
            </p>
            {salesOwners.length === 0 ? (
              <p className="text-[11px] text-[#8C4A00]">
                Daftar sales belum termuat (butuh hak akses admin).
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-1.5">
                {salesOwners.map((s) => {
                  const checked = ownerIds.includes(s.id);
                  return (
                    <label key={s.id} data-testid={`admin-product-owner-${s.id}`}
                      className={`flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-[12px] transition ${
                        checked ? "border-[#6D4AC0] bg-white" : "border-[#EAE3F7] bg-white hover:border-[#C9BAF0]"}`}>
                      <input type="checkbox" checked={checked} onChange={() => toggleOwner(s.id)}
                        className="h-3.5 w-3.5 accent-[#6D4AC0]" />
                      <span className="truncate font-medium text-[#1D1D1F]">{s.name}</span>
                    </label>
                  );
                })}
              </div>
            )}
            {ownerIds.length === 0 && salesOwners.length > 0 && (
              <p data-testid="admin-product-owner-warning"
                className="flex items-center gap-1 text-[11px] font-semibold text-[#D14343]">
                <AlertTriangle size={12} /> Pilih minimal 1 sales pemilik untuk produk eksklusif.
              </p>
            )}
          </div>
        )}
      </div>

      <p className="-mt-0.5 text-[11px] text-[#6B6B73]">
        <b>Satuan Dasar</b>: 1 produk = 1 satuan untuk semua roll-nya. Tiap roll beda <b>panjang</b>,
        bukan beda satuan. POS menjual per satuan dasar (tampil “X roll / Y {product.base_unit || "meter"}”).
      </p>
      {kgPerMeter > 0 ? (
        <p data-testid="admin-product-kgm-info" className="-mt-0.5 text-[11px] text-[#3A7D44]">
          Catch-weight aktif: 1 {product.base_unit || "meter"} ≈ {kgPerMeter.toFixed(3)} kg
          <span className="text-[#8E8E93]"> (kg/m = gramasi × lebar ÷ 1000) · unit “kg” tersedia di penjualan</span>
        </p>
      ) : (
        <p data-testid="admin-product-kgm-info" className="-mt-0.5 text-[11px] text-[#8E8E93]">
          Isi Gramasi (gsm) & Lebar (meter) untuk mengaktifkan penjualan per “kg” (catch-weight).
        </p>
      )}

      {/* Gambar & deskripsi */}
      <div data-testid="admin-product-media" className="space-y-2 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
        <p className="text-[11px] font-bold uppercase tracking-wide text-[#8E8E93]">Gambar Varian & Deskripsi</p>
        <div className="flex gap-2.5">
          {product.image ? (
            <img data-testid="admin-product-image-preview" src={product.image} alt="preview varian"
              className="h-16 w-16 shrink-0 rounded-md border border-[#EFF0F2] object-cover" />
          ) : (
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-md border border-dashed border-[#D9DBE0] text-[10px] text-[#B0B2BA]">
              Tanpa gambar
            </div>
          )}
          <input data-testid="admin-product-image-input" className="field flex-1"
            placeholder="URL gambar varian (https://...)" value={product.image ?? ""}
            onChange={(e) => set({ image: e.target.value })} />
        </div>
        <textarea data-testid="admin-product-description-input" className="field min-h-[70px] resize-y"
          placeholder="Deskripsi produk (mis. komposisi, motif, perawatan) — tampil di popup detail POS"
          value={product.description ?? ""} onChange={(e) => set({ description: e.target.value })} />
      </div>

      {/* Konversi UOM */}
      <div data-testid="admin-product-uom-editor" className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[#8E8E93]">Konversi UOM (mis. roll → meter)</p>
          <button type="button" data-testid="admin-product-add-conv-button" className="secondary-button" onClick={addConv}>
            <Plus size={13} /> Konversi
          </button>
        </div>
        {(product.uom_conversions || []).length === 0 && (
          <p className="mt-1 text-[11px] text-[#6B6B73]">
            Belum ada konversi variabel. Length (yard/cm/inch) otomatis; kg otomatis bila gramasi & lebar terisi.
          </p>
        )}
        {(product.uom_conversions || []).map((c, i) => (
          <div key={i} className="mt-2 grid grid-cols-[1fr_1fr_1fr_30px] items-center gap-1.5">
            <input data-testid={`admin-product-conv-from-${i}`} className="field" placeholder="Dari (roll)"
              value={c.from_unit} onChange={(e) => updateConv(i, "from_unit", e.target.value)} />
            <input data-testid={`admin-product-conv-to-${i}`} className="field" placeholder="Ke (meter)"
              value={c.to_unit} onChange={(e) => updateConv(i, "to_unit", e.target.value)} />
            <DecimalInput data-testid={`admin-product-conv-factor-${i}`} placeholder="Faktor (50)"
              min={0} value={c.factor} onChange={(v) => updateConv(i, "factor", v)} />
            <button type="button" data-testid={`admin-product-conv-remove-${i}`} className="icon-button"
              onClick={() => removeConv(i)} aria-label="Hapus konversi"><XCircle size={14} /></button>
          </div>
        ))}
      </div>

      {productError && (
        <p data-testid="admin-product-error" className="text-[12px] font-semibold text-[#D14343]">{productError}</p>
      )}
      <div className="flex gap-2">
        <button data-testid="admin-create-product-button" className="primary-button"
          disabled={saving} onClick={onSave}>
          <Save size={14} /> {saving ? "Menyimpan…" : editingProductId ? "Update Product" : "Simpan Product"}
        </button>
        {editingProductId && (
          <button data-testid="admin-cancel-edit-product-button" className="secondary-button" onClick={onCancel}>
            Batal Ubah
          </button>
        )}
      </div>
    </div>
  );
}
