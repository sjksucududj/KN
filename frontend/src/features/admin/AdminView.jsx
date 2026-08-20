import { useState, useEffect, useCallback, useMemo } from "react";
import { RefreshCw, Settings, Plus, Save, ShieldCheck, UserCog, Check, AlertTriangle, ChevronUp, ChevronDown } from "lucide-react";
import CategoryManager from "./CategoryManager";
import IntegrationsPanel from "./IntegrationsPanel";
import PermissionMatrixRecords from "./PermissionMatrixRecords";
import KNSelect from "../../components/KNSelect";
import FormModal from "../../components/FormModal";
import ProductMasterForm from "./products/ProductMasterForm";
import LineFilter from "../../components/LineFilter";   // FASE L — chip penyaring lini
import ProductLifecycleCell from "../rnd/ProductLifecycleCell";
import axios, { API } from "../../services/apiClient";
import { useEntityScope } from "../../context/EntityScopeContext";
import { scopeSuffix } from "../../utils/entityLabel";
// INV-ROLE-01 — wewenang layar dibaca dari IZIN pengguna, bukan nama peran.
import { can } from "../../config/roles";

export default function AdminView({
  data,
  uoms,
  templates,
  permissions,
  previewHtml,
  auditLogs,
  auditFilters,
  setAuditFilters,
  onAdminCreate,
  onAdminPatch,
  onAdminDelete,
  onImportMaster,
  onExportMaster,
  onUpdatePermissions,
  onPreviewTemplate,
  onRefreshAudit,
  onShowDetail,
  onSeedDemo,
  onReload,   // FASE F — muat ulang data master setelah produk dirilis ke produksi
  currentUser,
  only,   // opsional: array tab id (mis. ["products"]) untuk embed master data di domain hub
}) {
  const [tab, setTab] = useState(Array.isArray(only) && only.length ? only[0] : "products");
  // FASE E-3 (user story 7) — di mode "Semua Entitas" pembuatan data DIMATIKAN
  // (pelanggan ber-badan-usaha). Master bersama (produk/UOM/template/gudang)
  // tetap boleh karena tidak punya kolom badan usaha.
  const { canWrite, writeBlockHint,
    selectedEntity: scopeEntityId, entities: scopeEntities } = useEntityScope();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [categories, setCategories] = useState([]);
  const [salesOwners, setSalesOwners] = useState([]);   // PS-20 — daftar sales utk produk eksklusif
  const loadCategories = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/product-categories`);
      setCategories(Array.isArray(res.data) ? res.data : []);
    } catch (_) { /* non-blocking: form produk fallback ke daftar baku */ }
  }, []);
  useEffect(() => { loadCategories(); }, [loadCategories]);
  const loadSalesOwners = useCallback(async () => {
    /**
     * AUDIT PERAN (2026-08-15) — JANGAN memanggil apa yang tak boleh dipakai.
     * `GET /products/sales-owners` digerbang `product.update` (hanya admin — sengaja,
     * supaya daftar akun sales tidak bocor). Peran manajer membuka Master Produk
     * hanya untuk MELIHAT, jadi panggilan ini dulu selalu 403 lalu ditelan `catch`:
     * bersih di layar, tetapi setiap pembukaan layar meninggalkan 403 di jaringan &
     * log server, dan audit peran menandainya sebagai "panel mati" tiap kali dijalankan.
     * Pemilih "pemilik produk eksklusif" pun hanya dirender bagi yang boleh menyunting.
     */
    if (!can(currentUser?.permissions || {}, "product", "update")) {
      setSalesOwners([]);
      return;
    }
    try {
      const res = await axios.get(`${API}/products/sales-owners`);
      setSalesOwners(Array.isArray(res.data) ? res.data : []);
    } catch (_) { /* non-blocking: hanya admin (product:update) yang berhak */ }
  }, [currentUser]);
  useEffect(() => { loadSalesOwners(); }, [loadSalesOwners]);
  // Opsi dropdown kategori (aktif saja) untuk form produk; fallback 7 kategori baku.
  const categoryOptions = (categories.length
    ? categories.filter((c) => c.status === "active")
    : ["Batik", "Tenun", "Lurik", "Songket", "Ulos", "Jumputan", "Endek"].map((n) => ({ name: n })))
    .map((c) => ({ value: c.name, label: c.name }));
  // Fase A (PS-01/02/03/09) — field domain tekstil wajib ada di state form.
  const [product, setProduct] = useState({ sku: "", name: "", category: "Batik", variant: "Regular", color: "", color_code: "", color_name: "", color_hex: "", stage: "finished", fabric_type: "woven", line_code: "", yarn_count: "", yarn_count_system: "", motif: "", grade: "A", supplier: "", base_unit: "meter", price: 0, harga_pokok: 0, gramasi: 0, lebar: 0, image: "", description: "", uom_conversions: [] });
  const [savingProduct, setSavingProduct] = useState(false);
  const [editingProductId, setEditingProductId] = useState(null);
  const [productError, setProductError] = useState("");
  const [customer, setCustomer] = useState({ name: "", pic_name: "", phone: "", city: "Jakarta", address: "", npwp: "", credit_limit: 0, sales_pic: "" });
  const [entity, setEntity] = useState({ legal_name: "", short_name: "", type: "PT", npwp: "", address: "", city: "Bandung", default_tax_mode: "ppn", doc_prefix: "", logo_url: "" });
  // FASE U (D1) — master satuan kini membawa `aliases`: kata satuan yang BENAR-BENAR
  // tersimpan di dokumen (`yard`, `kg`, `meter`, `panel`). Tanpa alias, baris master
  // tidak pernah cocok dengan isi dokumen sehingga menambah satuan tidak mengubah
  // apa pun di layar. `factor_per_document` = satuan yang faktornya boleh ditulis
  // per baris dokumen (keputusan pemilik: panjang 1 panel berbeda per pesanan).
  const [uom, setUom] = useState({ code: "", name: "", base_type: "length", precision: 2, factor_to_base: 1, aliases: "", factor_per_document: false });
  const [template, setTemplate] = useState({ document_type: "surat_jalan", name: "", header: "Kain Nusantara", footer: "", columns: "SKU,Nama Barang,Qty,Unit", logo_url: "", paper_size: "A4", orientation: "portrait", margin_mm: 12, signature_left: "Dibuat Oleh", signature_right: "Disetujui Oleh", section_order: ["header", "customer", "items", "allocation", "signature", "footer"] });
  const [userForm, setUserForm] = useState({ name: "", email: "", role: "sales", password: "demo12345", home_entity_id: "", allowed_entity_ids: [] });
  // FASE L — penyaring lini pada Master Produk. Daftar `records` sudah datang
  // ter-pagar dari server (`line_scope` di GET /api/products); chip ini hanya
  // mempersempit tampilan, jadi tidak ada pintu kedua yang bisa berbeda arti.
  const [lineFilter, setLineFilter] = useState("");
  const [importFile, setImportFile] = useState(null);
  const [importPreview, setImportPreview] = useState(null);
  const [importLoading, setImportLoading] = useState(false);

  // Sub-fase 1.13 — helper form produk (uom_conversions + create/edit)
  const emptyProduct = { sku: "", name: "", category: "Batik", variant: "Regular", color: "", color_code: "", color_name: "", color_hex: "", stage: "finished", fabric_type: "woven", line_code: "", yarn_count: "", yarn_count_system: "", motif: "", grade: "A", supplier: "", base_unit: "meter", price: 0, harga_pokok: 0, gramasi: 0, lebar: 0, image: "", description: "", uom_conversions: [], exclusivity: "umum", owner_sales_ids: [] };
  const resetProductForm = () => { setProduct(emptyProduct); setEditingProductId(null); setProductError(""); };
  const updateConv = (idx, key, val) => setProduct({
    ...product,
    uom_conversions: (product.uom_conversions || []).map((c, i) => i === idx ? { ...c, [key]: val } : c),
  });
  const addConv = () => setProduct({ ...product, uom_conversions: [...(product.uom_conversions || []), { from_unit: "", to_unit: product.base_unit || "meter", factor: 0 }] });
  const removeConv = (idx) => setProduct({ ...product, uom_conversions: (product.uom_conversions || []).filter((_, i) => i !== idx) });
  // Sub-fase 1.13 — validasi konversi: unit wajib diisi, factor > 0, from != to.
  const validateConversions = () => {
    const rows = product.uom_conversions || [];
    for (let i = 0; i < rows.length; i++) {
      const from = String(rows[i].from_unit || "").trim();
      const to = String(rows[i].to_unit || "").trim();
      const factor = Number(rows[i].factor);
      if (!from || !to) return `Konversi #${i + 1}: unit "Dari" dan "Ke" wajib diisi.`;
      if (from.toLowerCase() === to.toLowerCase()) return `Konversi #${i + 1}: unit "Dari" dan "Ke" tidak boleh sama.`;
      if (!(factor > 0)) return `Konversi #${i + 1}: faktor harus lebih besar dari 0.`;
    }
    return "";
  };
  const visibleRecords = useMemo(() => {
    if (tab !== "products" || !lineFilter) return records;
    const want = lineFilter.split(",").map((s) => s.trim()).filter(Boolean);
    return (records || []).filter((r) => want.includes(String(r.line_code || "")));
  }, [records, tab, lineFilter]);

  const saveProduct = async () => {
    const err = validateConversions();
    if (err) { setProductError(err); return; }
    setProductError(""); setSavingProduct(true);
    // Fase A — form TIDAK direset bila server menolak (mis. GSM/fabric_type belum
    // lengkap) supaya isian pengguna tidak hilang & pesan validasi terbaca.
    const res = editingProductId
      ? await onAdminPatch("products", editingProductId, product)
      : await onAdminCreate("products", product);
    setSavingProduct(false);
    if (res && res.ok === false) { setProductError(res.error || "Gagal menyimpan produk."); return; }
    resetProductForm();
  };
  const loadProductForEdit = (row) => {
    setProduct({
      sku: row.sku || "", name: row.name || "", category: row.category || "", variant: row.variant || "",
      color: row.color || "", color_code: row.color_code || "", color_name: row.color_name || "", color_hex: row.color_hex || "",
      stage: row.stage || "finished", fabric_type: row.fabric_type || "",
      line_code: row.line_code || "",          // FASE L — lini kerja MD
      yarn_count: row.yarn_count || "", yarn_count_system: row.yarn_count_system || "",
      motif: row.motif || "", grade: row.grade || "", supplier: row.supplier || "",
      base_unit: row.base_unit || "meter", price: Number(row.price || 0), harga_pokok: Number(row.harga_pokok || 0),
      gramasi: Number(row.gramasi || 0), lebar: Number(row.lebar || 0), image: row.image || "", description: row.description || "", uom_conversions: row.uom_conversions || [],
      exclusivity: row.exclusivity || "umum", owner_sales_ids: row.owner_sales_ids || [],
    });
    setEditingProductId(row.id);
    setShowCreateForm(true);  // F3 — buka form saat Edit (sebelumnya tetap tertutup)
  };

  // FASE G-0 — tab "Pengaturan" DIHAPUS dari sini. Seluruh setting kini hanya ada di
  // "Pusat Pengaturan" (menu tetangga pada hub yang sama) supaya tidak ada dua form
  // yang bisa menyimpan kunci yang sama dengan cara berbeda.
  // FASE E-3 — tab "Entities" & "Users" DIHAPUS dari sini. Keduanya pindah ke layar
  // "Badan Usaha & Akses" (satu pintu). Dulu formulir di sini bisa mengetik
  // `home_entity_id` bebas sehingga bertentangan dengan data HR, dan tidak punya
  // pagar kunci prefix / pratinjau dampak arsip. Dua pintu untuk satu urusan =
  // aturan yang berlaku tergantung pintu mana yang dipakai.
  // FASE E-4 (E4.1) — tab "Warehouse" DIHAPUS dari sini. Gudang kini punya aturan
  // pemakaian per badan usaha (bersama / khusus + pagar agar stok tidak terkurung),
  // dan formulir generik di sini tidak punya pagar itu: gudang bisa lahir tanpa mode.
  // Satu pintu saja → layar "Gudang (Master)" (`features/wms/warehouses`).
  const ALL_TABS = [
    ["products", "Product"], ["categories", "Kategori"], ["customers", "Customer"], ["uoms", "UOM"], ["integrations", "Integrasi AI"], ["templates", "Templates"], ["permissions", "Permissions"], ["audit", "Audit"],
  ];
  const tabs = Array.isArray(only) && only.length ? ALL_TABS.filter(([id]) => only.includes(id)) : ALL_TABS;
  // Embedded (1 tab): sembunyikan header + tab-bar internal — konteks sudah dari HubTabs + PageMeta.
  const embedded = Array.isArray(only) && only.length === 1;
  const currentResource = tab === "templates" ? "templates" : tab;
  // FASE E-3 — daftar record per tab. Dulu memakai rantai ternary yang JATUH ke
  // `users` untuk tab yang tidak dikenal, sehingga tab "Integrasi AI" menampilkan
  // daftar pengguna. Sekarang eksplisit: tab tanpa daftar mengembalikan [].
  // Tab `users` & `entities` SUDAH TIDAK ADA di sini (pindah ke "Badan Usaha & Akses"),
  // jadi prop `users`/`entities` pun tidak lagi diterima komponen ini.
  const RECORDS_BY_TAB = {
    products: data.products, customers: data.customers,
    uoms, templates,
  };
  const records = RECORDS_BY_TAB[tab] || [];

  const handleDryRunImport = async () => {
    if (!importFile) return;
    setImportLoading(true);
    const result = await onImportMaster(currentResource, importFile, true);
    setImportPreview(result);
    setImportLoading(false);
  };

  const moveSection = (section, direction) => {
    const next = [...template.section_order];
    const index = next.indexOf(section);
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setTemplate({ ...template, section_order: next });
  };

  return (
    <div data-testid="admin-view">
      {!embedded && (
      <section className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-3 min-w-0">
            <span className="kicker">Admin Master Data</span>
            <h2>Kelola produk · pelanggan · gudang · UOM · template · pengguna</h2>
          </div>
          {onSeedDemo && (
            <button
              data-testid="admin-seed-demo-button"
              onClick={onSeedDemo}
              className="ml-auto secondary-button text-orange-700 border-orange-200 hover:bg-orange-50"
              title="Reset database & isi ulang dengan demo data (DESTRUCTIVE)"
            >
              <RefreshCw size={13} /> Reset Demo Data
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5 px-3 pb-3">
          {tabs.map(([id, label]) => <button key={id} data-testid={`admin-tab-${id}-button`} className={`nav-button ${tab === id ? "active" : ""}`} onClick={() => setTab(id)}><Settings size={13} /> {label}</button>)}
        </div>
      </section>
      )}
      {tab === "categories" && <CategoryManager onChanged={loadCategories} />}
      {tab === "integrations" && <IntegrationsPanel />}
      {tab !== "categories" && tab !== "integrations" && (
      <section className="grid gap-3 lg:grid-cols-[360px_1fr]">
        {/* FASE P4 — form master data menjadi POP-UP. Dua perbaikan sekaligus:
            (1) tombolnya SELALU terlihat (dulu ia menghilang begitu form terbuka, jadi
            pengguna tak punya penanda apa pun bahwa "form"-nya adalah kolom di sebelah),
            (2) daftar Records tidak lagi terhimpit kolom 360px saat mengisi. */}
        <button
          data-testid="toggle-admin-create-form-button"
          className="secondary-button"
          onClick={() => setShowCreateForm(true)}
        >
          <Plus size={14} /> Tampilkan Formulir Buat
        </button>
        <FormModal
          open={showCreateForm}
          onClose={() => setShowCreateForm(false)}
          title="Buat Data Master"
          subtitle="Isian untuk tab yang sedang dibuka — termasuk impor/ekspor CSV"
          icon={Plus}
          size="md"
          testId="admin-create-form"
        >
          {!["permissions", "audit"].includes(tab) && <div data-testid="admin-import-export-panel" className="mb-3 grid gap-2 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
            <p className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Impor / Ekspor {currentResource}</p>
            <input data-testid="admin-import-file-input" className="field" type="file" accept=".csv,.xlsx" onChange={(e) => setImportFile(e.target.files?.[0] || null)} />
            <div className="flex flex-wrap gap-1.5">
              <button data-testid="admin-dry-run-button" className="secondary-button" disabled={importLoading} onClick={handleDryRunImport}>{importLoading ? "..." : "Preview Dry-Run"}</button>
              <button data-testid="admin-import-button" className="secondary-button" onClick={() => { onImportMaster(currentResource, importFile, false); setImportPreview(null); }}>Impor</button>
              <button data-testid="admin-export-csv-button" className="secondary-button" onClick={() => onExportMaster(currentResource, "csv")}>Ekspor CSV</button>
            </div>
            {importPreview && (
              <div data-testid="import-preview-result" className="rounded-md border border-[#EFF0F2] bg-white p-2 text-[11.5px]">
                <p className="font-bold mb-1">Preview: {importPreview.total} baris</p>
                <p className="text-green-700 inline-flex items-center gap-1"><Check size={12} /> Akan dibuat: {importPreview.created}</p>
                <p className="text-blue-700">~ Akan diupdate: {importPreview.updated}</p>
                {(importPreview.errors || []).length > 0 && (
                  <div className="mt-1 max-h-24 overflow-auto">
                    <p className="text-red-700 font-bold inline-flex items-center gap-1"><AlertTriangle size={12} /> {importPreview.errors.length} error:</p>
                    {(importPreview.errors || []).map((e, i) => <p key={i} className="text-red-600 text-[10.5px]">{e}</p>)}
                  </div>
                )}
                <button data-testid="confirm-import-button" className="mt-1 primary-button text-[11px]" onClick={() => { onImportMaster(currentResource, importFile, false); setImportPreview(null); }}>Konfirmasi Impor</button>
              </div>
            )}
          </div>}
          {tab === "products" && (
            <ProductMasterForm
              product={product}
              setProduct={setProduct}
              editingProductId={editingProductId}
              productError={productError}
              saving={savingProduct}
              categoryOptions={categoryOptions}
              salesOwners={salesOwners}
              onSave={saveProduct}
              onCancel={resetProductForm}
              addConv={addConv}
              updateConv={updateConv}
              removeConv={removeConv}
            />
          )}
          {tab === "customers" && <div className="grid gap-2">
            {[["name", "Nama customer"], ["pic_name", "PIC"], ["phone", "Phone"], ["city", "Kota"], ["address", "Alamat"], ["npwp", "NPWP"], ["sales_pic", "Sales PIC"]].map(([key, ph]) => <input key={key} data-testid={`admin-customer-${key}-input`} className="field" placeholder={ph} value={customer[key]} onChange={(e) => setCustomer({ ...customer, [key]: e.target.value })} />)}
            <input data-testid="admin-customer-credit_limit-input" className="field" type="number" placeholder="Batas kredit (Rp)" value={customer.credit_limit} onChange={(e) => setCustomer({ ...customer, credit_limit: Number(e.target.value) })} />
            <button data-testid="admin-create-customer-button" className="primary-button" disabled={!canWrite} title={writeBlockHint} onClick={() => onAdminCreate("customers", customer)}><Save size={14} /> Simpan Pelanggan</button>
            {!canWrite && <p data-testid="admin-customer-scope-note" className="text-[10.5px] text-[#8C4A00]">{writeBlockHint}</p>}
          </div>}
          {tab === "uoms" && <div className="grid gap-2">
            {[["code", "Kode UOM (mis. PANEL)"], ["name", "Nama UOM"], ["base_type", "Base type (length/weight/count)"], ["precision", "Precision"], ["factor_to_base", "Faktor ke satuan dasar"]].map(([key, ph]) => <input key={key} data-testid={`admin-uom-${key}-input`} className="field" placeholder={ph} value={uom[key]} onChange={(e) => setUom({ ...uom, [key]: ["precision", "factor_to_base"].includes(key) ? Number(e.target.value) : e.target.value })} />)}
            <input data-testid="admin-uom-aliases-input" className="field"
              placeholder="Alias dipisah koma — kata yang dipakai dokumen (mis. panel, pnl)"
              title="Kata satuan yang tersimpan di dokumen. Tanpa alias, satuan ini tidak akan dikenali dokumen yang sudah ada."
              value={uom.aliases} onChange={(e) => setUom({ ...uom, aliases: e.target.value })} />
            <label className="flex items-center gap-2 text-[11.5px] text-[#3C3C43]">
              <input data-testid="admin-uom-factor-per-document-input" type="checkbox"
                checked={!!uom.factor_per_document}
                onChange={(e) => setUom({ ...uom, factor_per_document: e.target.checked })} />
              Faktor berbeda per dokumen (mis. panjang 1 panel berbeda tiap pesanan)
            </label>
            <button data-testid="admin-create-uom-button" className="primary-button" onClick={() => onAdminCreate("uoms", { ...uom, aliases: String(uom.aliases || "").split(",").map((a) => a.trim()).filter(Boolean) })}><Save size={14} /> Simpan UOM</button>
          </div>}
          {tab === "templates" && <div className="grid gap-2">
            {[["document_type", "Tipe dokumen"], ["name", "Nama template"], ["header", "Header"], ["footer", "Footer"], ["columns", "Kolom dipisah koma"], ["logo_url", "Logo URL"], ["paper_size", "Ukuran kertas"], ["orientation", "Orientasi"], ["margin_mm", "Margin mm"], ["signature_left", "TTD kiri"], ["signature_right", "TTD kanan"]].map(([key, ph]) => <input key={key} data-testid={`admin-template-${key}-input`} className="field" placeholder={ph} value={template[key]} onChange={(e) => setTemplate({ ...template, [key]: key === "margin_mm" ? Number(e.target.value) : e.target.value })} />)}
            <div data-testid="template-section-order-editor" className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
              <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Urutan section</p>
              {template.section_order.map((section) => <div key={section} data-testid={`template-section-${section}`} draggable className="mb-1.5 flex items-center justify-between rounded-md bg-white px-2 py-1 text-[12px] font-semibold border border-[#EFF0F2]"><span>{section}</span><span className="flex gap-1"><button data-testid={`template-section-${section}-up-button`} className="secondary-button" onClick={() => moveSection(section, -1)}><ChevronUp size={13} /></button><button data-testid={`template-section-${section}-down-button`} className="secondary-button" onClick={() => moveSection(section, 1)}><ChevronDown size={13} /></button></span></div>)}
            </div>
            <button data-testid="admin-create-template-button" className="primary-button" onClick={() => onAdminCreate("document-templates", { ...template, columns: template.columns.split(",").map((c) => c.trim()).filter(Boolean) })}><Save size={14} /> Simpan Template</button>
          </div>}
          {tab === "permissions" && <div data-testid="permission-matrix-editor" className="grid gap-2">
            <p className="text-[12px] text-[#3C3C43]">Klik kotak centang untuk ubah izin. Perubahan tersimpan otomatis.</p>
            <button data-testid="save-permissions-button" className="primary-button" onClick={() => onUpdatePermissions(permissions.matrix)}><ShieldCheck size={14} /> Simpan ke Database</button>
            <p className="text-[10.5px] text-[#8E8E93]">Semua perubahan di-preview dulu, klik Simpan untuk persisten.</p>
          </div>}
          {tab === "audit" && <div data-testid="audit-filter-panel" className="grid gap-2">
            <input data-testid="audit-actor-filter-input" className="field" placeholder="Filter actor" value={auditFilters.actor} onChange={(e) => setAuditFilters({ ...auditFilters, actor: e.target.value })} />
            <input data-testid="audit-module-filter-input" className="field" placeholder="Filter module/entity" value={auditFilters.module} onChange={(e) => setAuditFilters({ ...auditFilters, module: e.target.value })} />
            <input data-testid="audit-action-filter-input" className="field" placeholder="Filter action" value={auditFilters.action} onChange={(e) => setAuditFilters({ ...auditFilters, action: e.target.value })} />
            <div className="grid grid-cols-2 gap-2">
              <input data-testid="audit-date-from-input" className="field" type="date" value={auditFilters.date_from} onChange={(e) => setAuditFilters({ ...auditFilters, date_from: e.target.value })} />
              <input data-testid="audit-date-to-input" className="field" type="date" value={auditFilters.date_to} onChange={(e) => setAuditFilters({ ...auditFilters, date_to: e.target.value })} />
            </div>
            <button data-testid="refresh-audit-button" className="primary-button" onClick={onRefreshAudit}><RefreshCw size={14} /> Refresh Audit</button>
          </div>}
        </FormModal>
        <div className="section-card">
          <div className="section-head"><h2>Records</h2></div>
          <div className="section-body">
          {tab === "permissions" && <PermissionMatrixRecords matrix={permissions.matrix} onUpdatePermissions={onUpdatePermissions} />}
          {tab === "audit" && <div data-testid="audit-history-records" className="grid gap-2">
            {(auditLogs || []).map((log) => <button data-testid={`audit-row-${log.id}`} key={log.id} className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] interactive-card p-2.5 text-left" onClick={() => onShowDetail({ title: log.action, body: `Dicatat oleh ${log.actor} pada ${log.entity_type}.`, facts: [{ label: "Sumber Daya", value: `${log.entity_type} · ${log.entity_id}` }, { label: "Badan Usaha", value: log.scope_entity_name || log.scope_entity_id || "Tingkat grup" }, { label: "Peran", value: log.role || "—" }, { label: "Waktu", value: new Date(log.timestamp).toLocaleString("id-ID") }], target: "admin", cta: "Tetap di Audit" })}><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-[12.5px] font-semibold">{log.action}</p><p className="text-[10.5px] font-semibold text-[#0058CC]">{new Date(log.timestamp).toLocaleString("id-ID")}</p></div><p className="mt-0.5 text-[11.5px] text-[#3C3C43]">{log.actor} • {log.entity_type} • {log.entity_id}{log.scope_entity_name ? ` • ${log.scope_entity_name}` : ""}</p><p className="mt-1 line-clamp-2 text-[10.5px] text-[#3C3C43]">{JSON.stringify(log.after).slice(0, 240)}</p></button>)}
          </div>}
          {!['permissions', 'audit', 'integrations'].includes(tab) && <>
          <div className="grid gap-2">
            {tab === "products" && (
              <LineFilter value={lineFilter} onChange={setLineFilter} storageKey="admin-products"
                          allowed={currentUser?.allowed_line_codes} className="mb-1"
                          testId="admin-products-line-filter" />
            )}
            {visibleRecords.length === 0 && (
              <div data-testid={`admin-records-empty-${tab}`} className="px-3 py-8 text-center text-[12px] text-[#6B6B73]">Belum ada data {tab} {scopeSuffix(scopeEntities, scopeEntityId)}.</div>
            )}
            {visibleRecords.map((row) => (
              <div data-testid={`admin-record-${tab}-${row.id}`} key={row.id} role="button" tabIndex={0} className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] interactive-card flex flex-col gap-2 p-2.5 md:flex-row md:items-center md:justify-between" onClick={() => onShowDetail({ title: row.name || row.legal_name || row.code || row.email, body: `Record ${tab} ini dapat diupdate, dinonaktifkan, atau diexport dari Admin CRUD.`, facts: [{ label: "Module", value: tab }, { label: "Status", value: row.status || (row.active === false ? "inactive" : "active") }], target: "admin", cta: "Tetap di Admin" })}>
                <div className="min-w-0">
                  <p data-testid={`admin-record-title-${row.id}`} className="text-[12.5px] font-semibold truncate">{row.name || row.legal_name || row.code || row.email}</p>
                  <p data-testid={`admin-record-meta-${row.id}`} className="text-[11px] text-[#3C3C43] truncate">{row.sku || row.code || row.document_type || row.role || row.short_name || row.city} • {row.status || (row.active === false ? "inactive" : "active")}</p>
                  {tab === "products" && (
                    <div data-testid={`admin-product-domain-${row.id}`} className="mt-1 flex flex-wrap items-center gap-1">
                      <ProductLifecycleCell product={row}
                        canManage={["admin", "manager"].includes(currentUser?.role)}
                        onPatch={(id, patch) => onAdminPatch("products", id, patch)}
                        onDone={onReload} />
                      <span className="status-pill pill-muted">{row.stage || "finished"}</span>
                      <span className="status-pill pill-muted">{row.fabric_type || "fabric_type?"}</span>
                      {/* FASE L — lini kerja MD. Dibedakan warnanya dari `fabric_type`
                          supaya tidak terbaca sebagai dua nama untuk hal yang sama. */}
                      <span data-testid={`admin-product-line-${row.id}`} className="status-pill"
                        style={row.line_code ? { background: "#F3E9FA", color: "#6B219A" }
                                             : { background: "#F5F5F7", color: "#8E8E93" }}>
                        {row.line_code ? `Lini ${row.line_code}` : "Lini belum diisi"}
                      </span>
                      <span className="status-pill pill-success">Grade {row.grade || "—"}</span>
                      {Number(row.gramasi) > 0 && <span className="status-pill pill-muted tabular-nums">{row.gramasi} gsm</span>}
                      {row.needs_review && (
                        <span data-testid={`admin-product-needs-review-${row.id}`} className="status-pill pill-warning">
                          <AlertTriangle size={10} /> Perlu dilengkapi
                        </span>
                      )}
                      {row.exclusivity === "sales_tertentu" && (
                        <span data-testid={`admin-product-exclusive-${row.id}`}
                          className="status-pill" style={{ background: "#EDE6FB", color: "#6D4AC0" }}>
                          Eksklusif · {(row.owner_sales_ids || []).length} sales
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {tab === "products" && <button data-testid={`admin-edit-products-${row.id}-button`} className="secondary-button" onClick={(e) => { e.stopPropagation(); loadProductForEdit(row); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Ubah</button>}
                  {tab !== "products" && <button data-testid={`admin-update-${tab}-${row.id}-button`} className="secondary-button" onClick={(e) => { e.stopPropagation(); onAdminPatch(tab === "templates" ? "document-templates" : tab, row.id, tab === "uoms" ? { precision: row.precision } : { status: row.status || "active" }); }}>Update</button>}
                  {tab === "templates" && data.orders?.[0] && <button data-testid={`admin-preview-template-${row.id}-button`} className="secondary-button" onClick={(e) => { e.stopPropagation(); onPreviewTemplate(row.id, data.orders[0].id); }}>Preview</button>}
                  <button data-testid={`admin-delete-${tab}-${row.id}-button`} className="danger-button" onClick={(e) => { e.stopPropagation(); onAdminDelete(tab === "templates" ? "document-templates" : tab, row.id); }}>Deactivate</button>
                </div>
              </div>
            ))}
          </div>
          {tab === "templates" && previewHtml && <iframe data-testid="template-live-preview-frame" title="Template Preview" className="mt-4 h-[480px] w-full rounded-md border border-[#EFF0F2] bg-white" srcDoc={previewHtml} />}
          </>}
          </div>
        </div>
      </section>
      )}
    </div>
  );
}
