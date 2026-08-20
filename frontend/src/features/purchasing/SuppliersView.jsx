import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Truck, Plus, Search, Pencil, Power, X, BarChart3, Clock, Globe } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import GroupEntityBadge, { isGroupEntityPartner } from "../../components/GroupEntityBadge";
import Supplier360Panel from "./Supplier360Panel";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import FormModal from "../../components/FormModal";
import PaginationBar from "../../components/PaginationBar";
import { ReturnPolicyEditor } from "../../components/ReturnPolicyEditor";
import { usePagedList } from "../../hooks/usePagedList";

// FASE P6 — kolom Unduh CSV (mengikuti kolom tabel supplier).
const CSV_COLUMNS = [
  { key: "code", header: "Kode" },
  { key: "name", header: "Nama Supplier" },
  { key: "goods_type", header: "Jenis Barang" },
  { header: "Asal", get: (s) => (s.origin_type === "import" ? (s.country || "Impor") : "Lokal") },
  { key: "npwp", header: "NPWP" },
  { key: "pic_name", header: "PIC" },
  { key: "phone", header: "Telepon" },
  { key: "city", header: "Kota" },
  { key: "lead_time_days", header: "Lead Time (hari)", type: "int" },
  { key: "status", header: "Status" },
];

/**
 * SuppliersView (Fase 3 — Master Pemasok / Supplier).
 * CRUD supplier: list, search, create, edit, deactivate.
 * Depth #3 — detail panel (price-list + scorecard) + lead_time_days.
 * Koleksi kanonik: suppliers (prefix sup_).
 */
const DEFAULT_RETURN_POLICY = {
  window_days: 30, refund_modes: ["ap_credit"], returnable_to_supplier: true,
  rma_required: false, restocking_fee_pct: 0, condition_requirements: "",
  custom_fields: {}, notes: "",
};
const EMPTY_FORM = {
  name: "", npwp: "", pic_name: "", phone: "", email: "",
  address: "", city: "", goods_type: "", payment_term_code: "", lead_time_days: "",
  entity_id: "", notes: "",
  origin_type: "local", country: "", return_policy: { ...DEFAULT_RETURN_POLICY },
};

function StatusPill({ status }) {
  const cls = status === "active" ? "pill-success" : "pill-muted";
  const label = status === "active" ? "Aktif" : "Nonaktif";
  return <span data-testid={`supplier-status-${status}`} className={`status-pill ${cls}`}>{label}</span>;
}

export default function SuppliersView({ currentUser, selectedEntity }) {
  const [entities, setEntities] = useState([]);
  const [terms, setTerms] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [detailId, setDetailId] = useState(null);
  const [deactivateTarget, setDeactivateTarget] = useState(null);

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  // P2 — paginasi server-side + pencarian q server-side.
  const params = useMemo(() => (
    (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {}
  ), [selectedEntity]);
  const paged = usePagedList("/suppliers", { pageSize: 20, params, search });
  const suppliers = paged.items;
  const loading = paged.loading;
  const loadAll = paged.refresh;

  useEffect(() => { loadMeta(); }, []); // eslint-disable-line

  async function loadMeta() {
    try {
      const [eRes, tRes] = await Promise.all([
        axios.get(`${API}/entities`).catch(() => ({ data: [] })),
        axios.get(`${API}/payment-terms`).catch(() => ({ data: [] })),
      ]);
      setEntities(Array.isArray(eRes.data) ? eRes.data : []);
      setTerms(Array.isArray(tRes.data) ? tRes.data.filter((t) => t.active !== false) : []);
    } catch (e) { /* non-blocking */ }
  }

  function openCreate() {
    setEditId(null);
    setForm({ ...EMPTY_FORM, entity_id: (selectedEntity && selectedEntity !== "all") ? selectedEntity : "" });
    setShowForm(true);
  }

  function openEdit(s) {
    setEditId(s.id);
    setForm({
      name: s.name || "", npwp: s.npwp || "", pic_name: s.pic_name || "", phone: s.phone || "",
      email: s.email || "", address: s.address || "", city: s.city || "",
      goods_type: s.goods_type || "", payment_term_code: s.payment_term_code || "",
      lead_time_days: s.lead_time_days != null ? String(s.lead_time_days) : "",
      entity_id: s.entity_id || "", notes: s.notes || "",
      origin_type: s.origin_type || "local", country: s.country || "",
      return_policy: { ...DEFAULT_RETURN_POLICY, ...(s.return_policy || {}) },
    });
    setShowForm(true);
  }

  async function handleSubmit() {
    if (!form.name.trim()) { setError("Nama supplier wajib diisi."); return; }
    const payload = { ...form, lead_time_days: parseInt(form.lead_time_days, 10) || 0 };
    try {
      if (editId) {
        await axios.patch(`${API}/suppliers/${editId}`, { data: payload });
        setNotice(`Supplier ${form.name} diperbarui.`);
      } else {
        const res = await axios.post(`${API}/suppliers`, payload);
        setNotice(`Supplier ${res.data.code} — ${res.data.name} dibuat.`);
      }
      setShowForm(false);
      setForm(EMPTY_FORM);
      setEditId(null);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyimpan supplier.");
    }
  }

  async function handleDeactivate(s) {
    setDeactivateTarget(s);
  }

  async function doDeactivate(s) {
    try {
      await axios.delete(`${API}/suppliers/${s.id}`);
      setNotice(`Supplier ${s.name} dinonaktifkan.`);
      setDeactivateTarget(null);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menonaktifkan supplier.");
      setDeactivateTarget(null);
    }
  }

  const filtered = suppliers;

  if (detailId) {
    return <Supplier360Panel supplierId={detailId} currentUser={currentUser} onError={setError}
      onBack={() => { setDetailId(null); loadAll(); }}
      onEdit={(s) => { setDetailId(null); openEdit(s); }} />;
  }

  return (
    <div data-testid="suppliers-view">
      {notice && (
        <div className="notice-bar success" data-testid="supplier-notice">
          <span>{notice}</span><button onClick={() => setNotice("")}><X size={13} /></button>
        </div>
      )}
      <ErrorNotice message={error || paged.error} onRetry={loadAll} onDismiss={() => setError("")} testId="supplier-error" />

      {/* Header */}
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Truck size={16} className="text-[#0058CC]" />
            <h2 data-testid="suppliers-title">Master Pemasok (Supplier)</h2>
          </div>
          {canManage && (
            <button data-testid="create-supplier-button" onClick={openCreate} className="primary-button">
              <Plus size={13} /> Buat Supplier
            </button>
          )}
        </div>
        <div className="section-body">
          <div className="relative max-w-sm">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="supplier-search" value={search} onChange={(e) => setSearch(e.target.value)}
              className="field !pl-8" placeholder="Cari nama / kode / NPWP / kota..." />
          </div>
        </div>
      </div>

      {/* FASE P4 — form Buat/Ubah menjadi POP-UP.
          Sebelumnya form ini menyelip di antara kartu ringkasan dan tabel: daftar supplier
          terdorong ke bawah lipatan sehingga pengguna sering tak sadar formnya sudah terbuka
          (lalu menyimpulkan tombolnya tidak berfungsi). Logika form tidak diubah. */}
      <FormModal
        open={showForm && canManage}
        onClose={() => { setShowForm(false); setEditId(null); }}
        title={editId ? "Ubah Supplier" : "Supplier Baru"}
        subtitle="Data pemasok, termin pembayaran & kebijakan retur"
        icon={Truck}
        size="lg"
        testId="supplier-form"
        onSubmit={handleSubmit}
        submitLabel={editId ? "Simpan Perubahan" : "Buat Supplier"}
        submitTestId="submit-supplier-button"
        cancelTestId="cancel-supplier-button"
        error={error}
      >
        <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Nama Supplier" req>
                <input data-testid="supplier-name-input" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} className="field" placeholder="PT Pemasok Benang" />
              </Field>
              <Field label="NPWP">
                <input data-testid="supplier-npwp-input" value={form.npwp}
                  onChange={(e) => setForm({ ...form, npwp: e.target.value })} className="field" placeholder="00.000.000.0-000.000" />
              </Field>
              <Field label="Nama PIC">
                <input data-testid="supplier-pic-input" value={form.pic_name}
                  onChange={(e) => setForm({ ...form, pic_name: e.target.value })} className="field" placeholder="Nama kontak" />
              </Field>
              <Field label="Telepon">
                <input data-testid="supplier-phone-input" value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })} className="field" placeholder="0812xxxx" />
              </Field>
              <Field label="Email">
                <input data-testid="supplier-email-input" value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })} className="field" placeholder="sales@pemasok.co.id" />
              </Field>
              <Field label="Kota">
                <input data-testid="supplier-city-input" value={form.city}
                  onChange={(e) => setForm({ ...form, city: e.target.value })} className="field" placeholder="Bandung" />
              </Field>
              <Field label="Jenis Barang">
                <input data-testid="supplier-goods-input" value={form.goods_type}
                  onChange={(e) => setForm({ ...form, goods_type: e.target.value })} className="field" placeholder="Benang / Kain / Bahan Printing" />
              </Field>
              <Field label="Termin Pembayaran">
                <KNSelect data-testid="supplier-term-select" value={form.payment_term_code}
                  onValueChange={(v) => setForm({ ...form, payment_term_code: v })} className="field" placeholder="Pilih Termin"
                  options={[{ value: "", label: "— Tidak ditentukan —" }, ...terms.map((t) => ({ value: t.code, label: t.name }))]} />
              </Field>
              <Field label="Lead Time Default (hari)">
                <input data-testid="supplier-leadtime-input" type="number" value={form.lead_time_days}
                  onChange={(e) => setForm({ ...form, lead_time_days: e.target.value })} className="field" placeholder="mis. 7" />
              </Field>
              <Field label="Entitas">
                <KNSelect data-testid="supplier-entity-select" value={form.entity_id}
                  onValueChange={(v) => setForm({ ...form, entity_id: v })} className="field" placeholder="Pilih Entitas"
                  options={[{ value: "", label: "— Default (PT Kain Suka Cita) —" }, ...entities.map((e) => ({ value: e.id, label: e.short_name || e.legal_name }))]} />
              </Field>
              <Field label="Alamat">
                <input data-testid="supplier-address-input" value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })} className="field" placeholder="Alamat lengkap" />
              </Field>
              <Field label="Asal Barang">
                <KNSelect data-testid="supplier-origin-select" value={form.origin_type}
                  onValueChange={(v) => setForm({ ...form, origin_type: v })} className="field" placeholder="Pilih Asal"
                  options={[{ value: "local", label: "Lokal (Dalam Negeri)" }, { value: "import", label: "Impor (Luar Negeri)" }]} />
              </Field>
              {form.origin_type === "import" && (
                <Field label="Negara Asal">
                  <div className="relative">
                    <Globe size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
                    <input data-testid="supplier-country-input" value={form.country}
                      onChange={(e) => setForm({ ...form, country: e.target.value })} className="field !pl-8" placeholder="mis. China / India" />
                  </div>
                </Field>
              )}
            </div>
            <ReturnPolicyEditor
              value={form.return_policy}
              isImport={form.origin_type === "import"}
              onChange={(rp) => setForm({ ...form, return_policy: rp })} />
            <Field label="Catatan">
              <textarea data-testid="supplier-notes-input" value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })} className="field" rows="2" placeholder="Catatan tambahan..." />
            </Field>
        </div>
      </FormModal>

      {/* Table */}
      <div className="section-card">
        <div className="overflow-hidden">
          <div className="grid grid-cols-[90px_1.4fr_1fr_120px_90px_120px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Kode</span><span>Nama / Jenis</span><span>NPWP / Kontak</span><span>Kota / Lead</span><span>Status</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat supplier...</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]">
              <Truck className="mx-auto mb-2 text-gray-300" size={28} />
              <p>{search ? "Tidak ada supplier cocok." : "Belum ada supplier. Buat supplier pertama."}</p>
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2]">
              {filtered.map((s) => (
                <div key={s.id} data-testid={`supplier-row-${s.id}`}
                  className="grid grid-cols-[90px_1.4fr_1fr_120px_90px_120px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{s.code}</span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{s.name}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate flex items-center gap-1">
                      <EntityBadge entityId={s.entity_id} />
                      {/* E7.2/E7.7 — badan usaha grup memang MUNCUL di daftar pemasok
                          (keputusan pemilik), jadi harus jelas bedanya dari pemasok luar. */}
                      <GroupEntityBadge partner={s} />
                      {s.origin_type === "import" && (
                        <span data-testid={`supplier-origin-${s.id}`} className="status-pill pill-muted shrink-0" title={s.country || "Impor"}>
                          <Globe size={9} className="inline" /> Impor
                        </span>
                      )}
                      <span className="truncate">{s.goods_type || "—"}</span>
                    </p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11px] tabular-nums truncate">{s.npwp || "—"}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate">{s.pic_name} {s.phone ? `· ${s.phone}` : ""}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11px] truncate">{s.city || "—"}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate flex items-center gap-1"><Clock size={10} />{s.lead_time_days || 0} hari</p>
                  </div>
                  <StatusPill status={s.status} />
                  <div className="flex items-center justify-end gap-1">
                    <button data-testid={`detail-supplier-${s.id}`} onClick={() => setDetailId(s.id)} className="icon-button text-[#0058CC]" title="Supplier 360°"><BarChart3 size={13} /></button>
                    {canManage && !isGroupEntityPartner(s) && (
                      <>
                        <button data-testid={`edit-supplier-${s.id}`} onClick={() => openEdit(s)} className="icon-button" title="Ubah"><Pencil size={13} /></button>
                        {s.status === "active" && (
                          <button data-testid={`deactivate-supplier-${s.id}`} onClick={() => handleDeactivate(s)} className="icon-button text-red-400 hover:text-red-600" title="Nonaktifkan"><Power size={13} /></button>
                        )}
                      </>
                    )}
                    {canManage && isGroupEntityPartner(s) && (
                      // Baris ini CERMIN `business_entities`: identitas & statusnya diubah
                      // dari layar Badan Usaha & Akses, bukan dari sini — kalau tidak,
                      // cermin dan aslinya bisa berbeda dan pagar PO ikut salah menilai.
                      <span data-testid={`group-entity-locked-${s.id}`}
                        title="Diubah dari menu Badan Usaha & Akses (baris ini cerminnya)"
                        className="text-[9.5px] text-[#8E8E93] italic">dari Badan Usaha</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="px-3 py-2 border-t border-[#EFF0F2]">
          <PaginationBar
            testId="supplier-pager" label="supplier"
            page={paged.page} pageSize={paged.pageSize} total={paged.total}
            hasMore={paged.hasMore} loading={paged.loading}
            onPrev={paged.prev} onNext={paged.next} onPageSize={paged.setPageSize}
            exportConfig={{ columns: CSV_COLUMNS, rows: filtered,
              fetchAll: paged.fetchAll, filename: "supplier" }}
          />
        </div>
      </div>

      <ConfirmModal
        open={!!deactivateTarget}
        title={`Nonaktifkan ${deactivateTarget?.name || "Supplier"}`}
        message="Supplier yang dinonaktifkan tidak akan muncul saat membuat PO/PR baru. Anda dapat mengaktifkannya kembali nanti."
        confirmLabel="Nonaktifkan"
        danger
        onConfirm={() => doDeactivate(deactivateTarget)}
        onCancel={() => setDeactivateTarget(null)}
        testId="supplier-deactivate-modal"
      />
    </div>
  );
}

function Field({ label, req, children }) {
  return (
    <div>
      <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">
        {label} {req && <span className="req">*</span>}
      </label>
      {children}
    </div>
  );
}
