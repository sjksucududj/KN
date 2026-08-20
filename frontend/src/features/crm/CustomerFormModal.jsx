import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { X, UserPlus, Edit3 } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { CustomerSalesTeam, customerTeamError } from "./CustomerSalesTeam";

const METHODS = [
  { key: "tunai", label: "Tunai" },
  { key: "tempo", label: "Tempo (kredit)" },
  { key: "dp", label: "DP + Sisa" },
  { key: "bertahap", label: "Bertahap (cicilan)" },
  { key: "kontan", label: "Kontan" },
];
const SEGMENTS = ["Retail", "Wholesale", "Distributor", "VIP"];

/** Buat / edit pelanggan (CRM-lite KN_17). */
export default function CustomerFormModal({ open, editTarget, currentUser, salesUsers, selectedEntity, onClose, onSaved, onError }) {
  const isEdit = !!editTarget;
  const role = currentUser?.role;
  const isManager = role === "admin" || role === "manager";

  const [f, setF] = useState(blank());
  const [methods, setMethods] = useState(["tunai", "tempo"]);
  const [salesTeam, setSalesTeam] = useState([]);
  const [busy, setBusy] = useState(false);

  function blank() {
    return { name: "", segment: "Retail", assigned_sales_id: "", pic_name: "", phone: "", email: "",
      city: "", address: "", npwp: "", credit_limit: "", tags: "", status: "active",
      enforce_single_dye_lot: false, lot_policy: "",
      default_method: "tempo", term_days: 30, dp_percent: 30 };
  }

  useEffect(() => {
    if (!open) return;
    if (editTarget) {
      const pp = editTarget.payment_profile || {};
      setF({
        name: editTarget.name || "", segment: editTarget.segment || "Retail",
        assigned_sales_id: editTarget.assigned_sales_id || "", pic_name: editTarget.pic_name || "",
        phone: editTarget.phone || "", email: editTarget.email || "", city: editTarget.city || "",
        address: (editTarget.addresses?.[0]?.address) || "", npwp: editTarget.npwp || "",
        credit_limit: editTarget.credit_limit || "", tags: (editTarget.tags || []).join(", "),
        status: editTarget.status || "active",
        enforce_single_dye_lot: !!editTarget.enforce_single_dye_lot, lot_policy: editTarget.lot_policy || "",
        default_method: pp.default_method || "tempo", term_days: pp.term_days ?? 30, dp_percent: pp.dp_percent ?? 30,
      });
      setMethods(pp.allowed_methods || ["tunai", "tempo"]);
      setSalesTeam(Array.isArray(editTarget.sales_team) ? editTarget.sales_team : []);
    } else {
      setF(blank());
      setMethods(["tunai", "tempo"]);
      setSalesTeam([]);
    }
  }, [open, editTarget]);

  const salesOptions = useMemo(() => [
    { value: "", label: isManager ? "— Pilih Sales —" : "(otomatis: saya)" },
    ...(salesUsers || []).map((s) => ({ value: s.id, label: s.name })),
  ], [salesUsers, isManager]);

  const assignedSalesName = useMemo(
    () => (salesUsers || []).find((s) => s.id === f.assigned_sales_id)?.name || "",
    [salesUsers, f.assigned_sales_id]
  );

  function set(k, v) { setF((s) => ({ ...s, [k]: v })); }
  function setAssignedSales(v) {
    setF((s) => ({ ...s, assigned_sales_id: v }));
    setSalesTeam([]);  // ganti PIC → reset tim (hindari PIC basi)
  }
  function toggleMethod(m) {
    setMethods((arr) => (arr.includes(m) ? arr.filter((x) => x !== m) : [...arr, m]));
  }

  async function submit() {
    if (!f.name.trim()) { onError?.("Nama pelanggan wajib diisi."); return; }
    if (!isEdit && isManager && !f.assigned_sales_id) { onError?.("Pilih salesperson penanggung jawab."); return; }
    const tErr = customerTeamError(salesTeam);
    if (tErr) { onError?.(tErr); return; }
    const payment_profile = {
      allowed_methods: methods.length ? methods : ["tunai"],
      default_method: f.default_method, term_days: Number(f.term_days) || 0,
      dp_percent: Number(f.dp_percent) || 0, installment_count: 0, installment_interval_days: 30,
    };
    const tags = f.tags.split(",").map((t) => t.trim()).filter(Boolean);
    setBusy(true);
    try {
      if (isEdit) {
        const body = { data: {
          name: f.name, segment: f.segment, pic_name: f.pic_name, phone: f.phone, email: f.email,
          city: f.city, npwp: f.npwp, credit_limit: Number(f.credit_limit) || 0, tags,
          payment_profile, status: f.status,
          enforce_single_dye_lot: !!f.enforce_single_dye_lot, lot_policy: f.lot_policy || "",
          sales_team: salesTeam,
        }};
        const r = await axios.patch(`${API}/customers/${editTarget.id}`, body);
        onSaved?.(r.data, true);
      } else {
        const body = {
          name: f.name, pic_name: f.pic_name || f.name, phone: f.phone, email: f.email,
          type: f.segment, segment: f.segment, city: f.city || "-", address: f.address || "-",
          npwp: f.npwp, credit_limit: Number(f.credit_limit) || 0,
          assigned_sales_id: f.assigned_sales_id, tags, payment_profile,
          enforce_single_dye_lot: !!f.enforce_single_dye_lot, lot_policy: f.lot_policy || "",
          sales_team: salesTeam,
          entity_id: (selectedEntity && selectedEntity !== "all") ? selectedEntity : "",
        };
        const r = await axios.post(`${API}/customers`, body);
        onSaved?.(r.data, false);
      }
    } catch (e) {
      onError?.(e.response?.data?.detail || "Gagal menyimpan pelanggan.");
    } finally { setBusy(false); }
  }

  if (!open) return null;
  return (
    <div className="modal-overlay" data-testid="customer-form-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 680, width: "95vw", maxHeight: "92vh", overflowY: "auto" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2] sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2">
            {isEdit ? <Edit3 size={16} className="text-[#0058CC]" /> : <UserPlus size={16} className="text-[#0058CC]" />}
            <h2 className="text-[14px] font-bold">{isEdit ? "Edit Pelanggan" : "Pelanggan Baru"}</h2>
          </div>
          <button data-testid="customer-form-close" onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Nama Pelanggan" req>
              <input data-testid="customer-name" value={f.name} onChange={(e) => set("name", e.target.value)} className="field" placeholder="PT / Toko ..." />
            </Field>
            <Field label="Segment">
              <KNSelect value={f.segment} onValueChange={(v) => set("segment", v)} className="field"
                data-testid="customer-segment" options={SEGMENTS.map((s) => ({ value: s, label: s }))} />
            </Field>
            <Field label="Salesperson (PIC)" req={!isEdit && isManager}>
              <KNSelect value={f.assigned_sales_id} onValueChange={setAssignedSales}
                className="field" data-testid="customer-assigned-sales" disabled={isEdit || !isManager}
                options={salesOptions} placeholder="Sales" />
              {isEdit && <p className="text-[10px] text-[#9A9BA3] mt-0.5">Ubah sales via tombol Reassign di detail.</p>}
            </Field>
            <Field label="Kontak (PIC)">
              <input data-testid="customer-pic" value={f.pic_name} onChange={(e) => set("pic_name", e.target.value)} className="field" placeholder="Nama PIC" />
            </Field>
            <Field label="Telepon">
              <input data-testid="customer-phone" value={f.phone} onChange={(e) => set("phone", e.target.value)} className="field" placeholder="08..." />
            </Field>
            <Field label="Email">
              <input data-testid="customer-email" value={f.email} onChange={(e) => set("email", e.target.value)} className="field" placeholder="email@..." />
            </Field>
            <Field label="Kota">
              <input data-testid="customer-city" value={f.city} onChange={(e) => set("city", e.target.value)} className="field" placeholder="Kota" />
            </Field>
            <Field label="NPWP">
              <input data-testid="customer-npwp" value={f.npwp} onChange={(e) => set("npwp", e.target.value)} className="field" placeholder="NPWP (opsional)" />
            </Field>
            {!isEdit && (
              <Field label="Alamat">
                <input data-testid="customer-address" value={f.address} onChange={(e) => set("address", e.target.value)} className="field" placeholder="Alamat" />
              </Field>
            )}
            <Field label="Limit Kredit (Rp)">
              <input type="number" data-testid="customer-credit-limit" value={f.credit_limit} onChange={(e) => set("credit_limit", e.target.value)} className="field" placeholder="0 = tanpa limit" />
            </Field>
            {isEdit && (
              <Field label="Status">
                <KNSelect value={f.status} onValueChange={(v) => set("status", v)} className="field" data-testid="customer-status"
                  options={[{ value: "active", label: "Aktif" }, { value: "inactive", label: "Nonaktif" }, { value: "blocked", label: "Blokir" }]} />
              </Field>
            )}
            <Field label="Tags (pisah koma)">
              <input data-testid="customer-tags" value={f.tags} onChange={(e) => set("tags", e.target.value)} className="field" placeholder="grosir, premium" />
            </Field>
          </div>

          {/* SALES REVAMP V2 — Tim Sales (PIC + co-sales + split insentif) di level customer */}
          <CustomerSalesTeam
            salesUsers={salesUsers}
            assignedSalesId={f.assigned_sales_id}
            assignedSalesName={assignedSalesName}
            value={salesTeam}
            onChange={setSalesTeam}
          />

          {/* SALES REVAMP V2 — Kebijakan Lot (pindah dari quick-add POS ke Manajemen Customer) */}
          <div className="rounded-md border border-[#E5C7F5] bg-[#FBF7FF] p-3 space-y-2">
            <p className="text-[11px] font-bold uppercase text-[#6B219A]">Kebijakan Lot / Dye Lot</p>
            <label data-testid="customer-enforce-dyelot" className="flex items-start gap-2 text-[11px] text-[#3C3C43] cursor-pointer">
              <input type="checkbox" className="mt-0.5" checked={f.enforce_single_dye_lot} onChange={(e) => set("enforce_single_dye_lot", e.target.checked)} />
              <span>Paksa <b>1 dye lot</b> saat alokasi (hindari belang warna antar roll)</span>
            </label>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wide text-[#6B6B73] mb-1">Kebijakan Lot</label>
              <KNSelect data-testid="customer-lot-policy" className="field w-full" value={f.lot_policy} onValueChange={(v) => set("lot_policy", v)}
                options={[
                  { value: "", label: "Default (prefer single)" },
                  { value: "prefer_single", label: "Prefer single lot" },
                  { value: "strict_single", label: "Strict single lot" },
                  { value: "allow_mixed", label: "Boleh mixed lot" },
                ]} />
            </div>
          </div>

          {/* Payment profile */}
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3">
            <p className="text-[11px] font-bold uppercase text-[#6B6B73] mb-2">Profil Pembayaran</p>
            <div className="flex flex-wrap gap-2 mb-2">
              {METHODS.map((m) => (
                <label key={m.key} className="flex items-center gap-1.5 text-[11.5px] cursor-pointer" data-testid={`customer-method-${m.key}`}>
                  <input type="checkbox" checked={methods.includes(m.key)} onChange={() => toggleMethod(m.key)} />
                  {m.label}
                </label>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Field label="Metode Default">
                <KNSelect value={f.default_method} onValueChange={(v) => set("default_method", v)} className="field"
                  data-testid="customer-default-method" options={METHODS.filter((m) => methods.includes(m.key)).map((m) => ({ value: m.key, label: m.label }))} />
              </Field>
              <Field label="Termin (hari)">
                <input type="number" data-testid="customer-term-days" value={f.term_days} onChange={(e) => set("term_days", e.target.value)} className="field" />
              </Field>
              <Field label="DP (%)">
                <input type="number" data-testid="customer-dp-percent" value={f.dp_percent} onChange={(e) => set("dp_percent", e.target.value)} className="field" />
              </Field>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2] sticky bottom-0 bg-white">
          <button onClick={onClose} className="secondary-button">Batal</button>
          <button data-testid="customer-form-submit" disabled={busy} onClick={submit} className="primary-button">
            {busy ? "Menyimpan..." : isEdit ? "Simpan Perubahan" : "Buat Pelanggan"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, req, children }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">{label}{req && <span className="text-red-500"> *</span>}</label>
      {children}
    </div>
  );
}
