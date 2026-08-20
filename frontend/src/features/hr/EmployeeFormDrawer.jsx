import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Plus, Trash2, Save } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { Switch } from "@/components/ui/switch";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

const PTKP_OPTIONS = ["TK0", "TK1", "TK2", "TK3", "K0", "K1", "K2", "K3"].map((v) => ({ value: v, label: v }));
const JKK_OPTIONS = ["", "I", "II", "III", "IV", "V"].map((v) => ({ value: v, label: v ? `Kelas ${v}` : "— pilih kelas —" }));
const GENDER_OPTIONS = [{ value: "", label: "— pilih —" }, { value: "L", label: "Laki-laki" }, { value: "P", label: "Perempuan" }];
const STATUS_OPTIONS = [{ value: "active", label: "Aktif" }, { value: "inactive", label: "Nonaktif" }, { value: "resigned", label: "Resigned" }];

const EMPTY = {
  name: "", nik: "", user_id: "", dob: "", gender: "", phone: "", email: "", address: "",
  department_id: "", position_id: "", shift_id: "", device_user_id: "",
  employment_type: "tetap", join_date: "", status: "active",
  npwp: "", ptkp_status: "TK0", bpjs_kes_enabled: false, bpjs_kes_no: "",
  bpjs_tk_enabled: false, bpjs_tk_no: "", jkk_risk_class: "",
  bank_name: "", bank_acc_no: "", bank_acc_name: "", base_salary: "", allowances: [], entity_id: "",
};

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

function Section({ title, children }) {
  return (
    <div className="space-y-3">
      <h3 className="text-[11px] font-bold uppercase tracking-wide text-[#0058CC]">{title}</h3>
      {children}
    </div>
  );
}

export function EmployeeFormDrawer({ open, onClose, onSaved, editEmployee, departments = [], positions = [], entities = [], users = [], settings = {}, shifts = [], defaultEntity }) {
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const editId = editEmployee?.id || null;
  const toggles = settings?.feature_toggles || {};
  const empTypes = settings?.employment_types || ["tetap", "kontrak", "harian", "borongan"];

  useEffect(() => {
    if (!open) return;
    if (editEmployee) {
      setForm({
        ...EMPTY, ...editEmployee,
        base_salary: editEmployee.base_salary != null ? String(editEmployee.base_salary) : "",
        allowances: Array.isArray(editEmployee.allowances) ? editEmployee.allowances : [],
      });
    } else {
      setForm({ ...EMPTY, entity_id: defaultEntity && defaultEntity !== "all" ? defaultEntity : "" });
    }
    setError("");
  }, [open, editEmployee]); // eslint-disable-line

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const deptPositions = positions.filter((p) => p.parent_id === form.department_id);

  const addAllowance = () => set("allowances", [...(form.allowances || []), { name: "", amount: 0 }]);
  const updAllowance = (i, k, v) => {
    const a = [...form.allowances];
    a[i] = { ...a[i], [k]: k === "amount" ? (parseFloat(v) || 0) : v };
    set("allowances", a);
  };
  const delAllowance = (i) => set("allowances", form.allowances.filter((_, idx) => idx !== i));

  async function submit() {
    if (!form.name.trim()) { setError("Nama karyawan wajib diisi."); return; }
    if (toggles.npwp_required && !String(form.npwp || "").trim()) { setError("NPWP wajib diisi (sesuai pengaturan HR)."); return; }
    const payload = {
      ...form,
      base_salary: parseFloat(form.base_salary) || 0,
      allowances: (form.allowances || []).filter((a) => a.name).map((a) => ({ name: a.name, amount: parseFloat(a.amount) || 0 })),
    };
    setSaving(true);
    try {
      if (editId) await axios.patch(`${API}/hr/employees/${editId}`, { data: payload });
      else await axios.post(`${API}/hr/employees`, payload);
      setSaving(false);
      onSaved?.(editId ? "Data karyawan diperbarui." : "Karyawan baru dibuat.");
      onClose?.();
    } catch (e) {
      setSaving(false);
      setError(e.response?.data?.detail || "Gagal menyimpan karyawan.");
    }
  }

  const userOptions = [{ value: "", label: "— Tanpa akun pengguna —" }, ...users.map((u) => ({ value: u.id, label: `${u.name} (${u.role})` }))];
  const entityOptions = [{ value: "", label: "— Entitas default —" }, ...entities.map((e) => ({ value: e.id, label: e.short_name || e.legal_name || e.id }))];

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose?.(); }}>
      <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto p-0" data-testid="employee-form-drawer">
        <SheetHeader className="px-5 py-4 border-b border-[#EFF0F2]">
          <SheetTitle data-testid="employee-form-title">{editId ? `Edit Karyawan · ${editEmployee?.code || ""}` : "Tambah Karyawan"}</SheetTitle>
        </SheetHeader>

        <div className="px-5 py-4 space-y-6">
          {error && <div className="notice-bar danger" data-testid="employee-form-error"><span>{error}</span></div>}

          <Section title="Data Pribadi">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Nama Lengkap" req>
                <input data-testid="employee-name-input" value={form.name} onChange={(e) => set("name", e.target.value)} className="field" placeholder="Nama karyawan" />
              </Field>
              <Field label="NIK / No. Identitas">
                <input data-testid="employee-nik-input" value={form.nik} onChange={(e) => set("nik", e.target.value)} className="field" placeholder="NIK KTP" />
              </Field>
              <Field label="Jenis Kelamin">
                <KNSelect data-testid="employee-gender-select" value={form.gender} onValueChange={(v) => set("gender", v)} className="field" placeholder="Pilih" options={GENDER_OPTIONS} />
              </Field>
              <Field label="Tanggal Lahir">
                <input data-testid="employee-dob-input" type="date" value={form.dob} onChange={(e) => set("dob", e.target.value)} className="field" />
              </Field>
              <Field label="Telepon">
                <input data-testid="employee-phone-input" value={form.phone} onChange={(e) => set("phone", e.target.value)} className="field" placeholder="0812xxxx" />
              </Field>
              <Field label="Email">
                <input data-testid="employee-email-input" value={form.email} onChange={(e) => set("email", e.target.value)} className="field" placeholder="nama@email.id" />
              </Field>
              <div className="col-span-2">
                <Field label="Alamat">
                  <textarea data-testid="employee-address-input" value={form.address} onChange={(e) => set("address", e.target.value)} className="field" rows="2" placeholder="Alamat domisili" />
                </Field>
              </div>
            </div>
          </Section>

          <Section title="Kepegawaian">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Departemen">
                <KNSelect data-testid="employee-department-select" value={form.department_id} onValueChange={(v) => setForm((f) => ({ ...f, department_id: v, position_id: "" }))} className="field" placeholder="Pilih departemen"
                  options={[{ value: "", label: "— Tidak ditentukan —" }, ...departments.map((d) => ({ value: d.id, label: d.name }))]} />
              </Field>
              <Field label="Jabatan / Posisi">
                <KNSelect data-testid="employee-position-select" value={form.position_id} onValueChange={(v) => set("position_id", v)} className="field" placeholder="Pilih jabatan"
                  options={[{ value: "", label: "— Tidak ditentukan —" }, ...deptPositions.map((p) => ({ value: p.id, label: p.name }))]} />
              </Field>
              <Field label="Status Kepegawaian">
                <KNSelect data-testid="employee-emptype-select" value={form.employment_type} onValueChange={(v) => set("employment_type", v)} className="field" placeholder="Pilih"
                  options={empTypes.map((t) => ({ value: t, label: t.charAt(0).toUpperCase() + t.slice(1) }))} />
              </Field>
              <Field label="Tanggal Masuk">
                <input data-testid="employee-joindate-input" type="date" value={form.join_date} onChange={(e) => set("join_date", e.target.value)} className="field" />
              </Field>
              <Field label="Status">
                <KNSelect data-testid="employee-status-select" value={form.status} onValueChange={(v) => set("status", v)} className="field" placeholder="Pilih" options={STATUS_OPTIONS} />
              </Field>
              <Field label="Entitas (PT/CV)">
                <KNSelect data-testid="employee-entity-select" value={form.entity_id} onValueChange={(v) => set("entity_id", v)} className="field" placeholder="Pilih entitas" options={entityOptions} />
              </Field>
              <Field label="Shift Default (Absensi)">
                <KNSelect data-testid="employee-shift-select" value={form.shift_id} onValueChange={(v) => set("shift_id", v)} className="field" placeholder="Shift default entitas"
                  options={[{ value: "", label: "— Shift default entitas —" }, ...shifts.map((s) => ({ value: s.id, label: `${s.name} (${s.jam_in}–${s.jam_out})` }))]} />
              </Field>
              <Field label="ID Mesin Fingerprint">
                <input data-testid="employee-deviceid-input" value={form.device_user_id} onChange={(e) => set("device_user_id", e.target.value)} className="field tabular-nums" placeholder="cth: 1001 (enroll ID ZKTeco)" />
              </Field>
              <div className="col-span-2">
                <Field label="Tautkan ke Akun Pengguna (opsional)">
                  <KNSelect data-testid="employee-user-select" value={form.user_id} onValueChange={(v) => set("user_id", v)} className="field" placeholder="Pilih akun" searchable options={userOptions} />
                </Field>
              </div>
            </div>
          </Section>

          <Section title="Pajak & Statutory">
            <div className="grid grid-cols-2 gap-3">
              <Field label="NPWP" req={!!toggles.npwp_required}>
                <input data-testid="employee-npwp-input" value={form.npwp} onChange={(e) => set("npwp", e.target.value)} className="field" placeholder="00.000.000.0-000.000" />
              </Field>
              <Field label="Status PTKP">
                <KNSelect data-testid="employee-ptkp-select" value={form.ptkp_status} onValueChange={(v) => set("ptkp_status", v)} className="field" placeholder="PTKP" options={PTKP_OPTIONS} />
              </Field>
            </div>
            {toggles.bpjs_kesehatan !== false && (
              <div className="rounded-lg border border-[#EFF0F2] p-3 space-y-2">
                <label className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-semibold">BPJS Kesehatan</span>
                  <Switch data-testid="employee-bpjs-kes-switch" checked={!!form.bpjs_kes_enabled} onCheckedChange={(v) => set("bpjs_kes_enabled", v)} />
                </label>
                {form.bpjs_kes_enabled && (
                  <Field label="No. BPJS Kesehatan">
                    <input data-testid="employee-bpjs-kes-input" value={form.bpjs_kes_no} onChange={(e) => set("bpjs_kes_no", e.target.value)} className="field" placeholder="0001234567890" />
                  </Field>
                )}
              </div>
            )}
            {toggles.bpjs_ketenagakerjaan !== false && (
              <div className="rounded-lg border border-[#EFF0F2] p-3 space-y-2">
                <label className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-semibold">BPJS Ketenagakerjaan (JHT/JP/JKK/JKM)</span>
                  <Switch data-testid="employee-bpjs-tk-switch" checked={!!form.bpjs_tk_enabled} onCheckedChange={(v) => set("bpjs_tk_enabled", v)} />
                </label>
                {form.bpjs_tk_enabled && (
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="No. BPJS Ketenagakerjaan">
                      <input data-testid="employee-bpjs-tk-input" value={form.bpjs_tk_no} onChange={(e) => set("bpjs_tk_no", e.target.value)} className="field" placeholder="00001234567" />
                    </Field>
                    <Field label="Kelas Risiko JKK">
                      <KNSelect data-testid="employee-jkk-select" value={form.jkk_risk_class} onValueChange={(v) => set("jkk_risk_class", v)} className="field" placeholder="Kelas" options={JKK_OPTIONS} />
                    </Field>
                  </div>
                )}
              </div>
            )}
          </Section>

          <Section title="Bank & Komponen Gaji">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Nama Bank">
                <input data-testid="employee-bank-name-input" value={form.bank_name} onChange={(e) => set("bank_name", e.target.value)} className="field" placeholder="Bank BCA" />
              </Field>
              <Field label="No. Rekening">
                <input data-testid="employee-bank-acc-input" value={form.bank_acc_no} onChange={(e) => set("bank_acc_no", e.target.value)} className="field" placeholder="1234567890" />
              </Field>
              <Field label="Atas Nama">
                <input data-testid="employee-bank-name-acc-input" value={form.bank_acc_name} onChange={(e) => set("bank_acc_name", e.target.value)} className="field" placeholder="Nama pemilik rekening" />
              </Field>
              <Field label="Gaji Pokok (Rp)">
                <input data-testid="employee-salary-input" type="number" value={form.base_salary} onChange={(e) => set("base_salary", e.target.value)} className="field tabular-nums" placeholder="5000000" />
              </Field>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-[#6B6B73]">Tunjangan</span>
                <button type="button" data-testid="employee-add-allowance" onClick={addAllowance} className="icon-button text-[#0058CC]" title="Tambah tunjangan"><Plus size={14} /></button>
              </div>
              {(form.allowances || []).map((a, i) => (
                <div key={i} className="grid grid-cols-[1.4fr_1fr_36px] gap-2 items-center" data-testid={`allowance-row-${i}`}>
                  <input data-testid={`allowance-name-${i}`} value={a.name} onChange={(e) => updAllowance(i, "name", e.target.value)} className="field" placeholder="Tunjangan transport" />
                  <input data-testid={`allowance-amount-${i}`} type="number" value={a.amount} onChange={(e) => updAllowance(i, "amount", e.target.value)} className="field tabular-nums" placeholder="0" />
                  <button type="button" data-testid={`allowance-del-${i}`} onClick={() => delAllowance(i)} className="icon-button text-red-400 hover:text-red-600"><Trash2 size={13} /></button>
                </div>
              ))}
              {(form.allowances || []).length === 0 && <p className="text-[11px] text-[#9A9BA3]">Belum ada tunjangan tambahan.</p>}
            </div>
          </Section>
        </div>

        <div className="sticky bottom-0 bg-white border-t border-[#EFF0F2] px-5 py-3 flex gap-2">
          <button data-testid="employee-save-button" disabled={saving} onClick={submit} className="primary-button flex-1 justify-center">
            <Save size={14} /> {saving ? "Menyimpan..." : editId ? "Simpan Perubahan" : "Buat Karyawan"}
          </button>
          <button data-testid="employee-cancel-button" onClick={() => onClose?.()} className="secondary-button">Batal</button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
