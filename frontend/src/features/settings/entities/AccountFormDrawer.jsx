/**
 * AccountFormDrawer (FASE E-3 / E2.1–E2.2) — buat & ubah akun.
 *
 * Aturan yang DITAMPILKAN, bukan disembunyikan:
 *  · Kalau akun ditautkan ke karyawan HR, badan usaha utamanya HANYA-BACA dan
 *    diambil dari HR — supaya penggajian dan hak akses tidak pernah bertentangan.
 *  · Peran sales/gudang terkunci di badan usahanya; penugasan tambahan harus
 *    disebut satu per satu (bukan “semua badan usaha” diam-diam).
 *  · Mengubah peran/penugasan MENCABUT sesi — dikatakan sebelum disimpan supaya
 *    admin tidak bingung kenapa orangnya tiba-tiba diminta masuk lagi.
 */
import { useEffect, useMemo, useState } from "react";
import { X, Save, Loader2, UserCog, Info, Search, Link2, Star } from "lucide-react";

import KNSelect from "../../../components/KNSelect";
import useDomainEnums from "../../../hooks/useDomainEnums";
import { entityFull } from "../../../utils/entityLabel";
import { createUser, patchUser, availableEmployees, ROLE_OPTIONS, CROSS_ROLES,
  errText } from "./entityApi";

export default function AccountFormDrawer({ user, entities = [], selectedEntity,
  onClose, onSaved, onError }) {
  const editing = Boolean(user?.id);
  const [form, setForm] = useState(() => ({
    name: user?.name || "",
    email: user?.email || "",
    phone: user?.phone || "",
    role: user?.role || "sales",
    password: "",
    employee_id: user?.employee_id || "",
    home_entity_id: user?.home_entity_id
      || (selectedEntity && selectedEntity !== "all" ? selectedEntity : (entities[0]?.id || "")),
    allowed_entity_ids: user?.allowed_entity_ids || [],
    // FASE L — lini produk yang boleh dikerjakan. KOSONG = SEMUA LINI (bawaan).
    allowed_line_codes: user?.allowed_line_codes || [],
  }));
  const [empQuery, setEmpQuery] = useState("");
  const [employees, setEmployees] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const isCross = CROSS_ROLES.includes(form.role);

  useEffect(() => {
    let alive = true;
    availableEmployees({ q: empQuery, entity_id: "" })
      .then((rows) => { if (alive) setEmployees(rows); })
      .catch(() => { if (alive) setEmployees([]); });
    return () => { alive = false; };
  }, [empQuery]);

  const linkedEmployee = useMemo(
    () => employees.find((e) => e.id === form.employee_id) || user?.employee || null,
    [employees, form.employee_id, user]
  );
  const homeFromHr = Boolean(form.employee_id && linkedEmployee?.entity_id);
  const effectiveHome = homeFromHr ? linkedEmployee.entity_id : form.home_entity_id;

  const willRevoke = editing && (
    form.role !== user.role
    || effectiveHome !== user.home_entity_id
    || JSON.stringify([...(form.allowed_entity_ids || [])].sort())
       !== JSON.stringify([...(user.allowed_entity_ids || [])].sort())
    // FASE L — mengubah hak lini juga mencabut sesi (hak baca berubah).
    || JSON.stringify([...(form.allowed_line_codes || [])].sort())
       !== JSON.stringify([...(user.allowed_line_codes || [])].sort())
    || Boolean(form.password)
  );

  const errors = useMemo(() => {
    const out = [];
    if (!form.name.trim()) out.push("Nama wajib diisi.");
    if (!form.email.trim()) out.push("Email wajib diisi (dipakai untuk masuk).");
    if (!editing && form.password && form.password.length < 8) {
      out.push("Password minimal 8 karakter.");
    }
    if (!effectiveHome) out.push("Badan usaha utama wajib dipilih.");
    return out;
  }, [form, editing, effectiveHome]);

  const toggleAllowed = (id) => {
    setForm((f) => {
      const cur = new Set(f.allowed_entity_ids || []);
      if (cur.has(id)) cur.delete(id); else cur.add(id);
      return { ...f, allowed_entity_ids: Array.from(cur) };
    });
  };

  // FASE L — pilihan lini datang dari MASTER (`/api/enums` → product_line), bukan
  // daftar hardcode: lini keempat yang ditambah pemilik langsung bisa diberikan
  // ke akun tanpa perubahan kode.
  const { options } = useDomainEnums();
  const lineOptions = useMemo(() => options("product_line"), [options]);

  const toggleLine = (code) => {
    setForm((f) => {
      const cur = new Set(f.allowed_line_codes || []);
      if (cur.has(code)) cur.delete(code); else cur.add(code);
      return { ...f, allowed_line_codes: Array.from(cur) };
    });
  };

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      if (editing) {
        const data = {
          name: form.name, email: form.email, phone: form.phone, role: form.role,
          employee_id: form.employee_id,
          ...(homeFromHr ? {} : { home_entity_id: form.home_entity_id }),
          ...(isCross ? {} : { allowed_entity_ids: form.allowed_entity_ids }),
          allowed_line_codes: form.allowed_line_codes || [],   // FASE L
          ...(form.password ? { password: form.password } : {}),
        };
        const res = await patchUser(user.id, data);
        onSaved?.(
          `Akun ${res.name} diperbarui.`
          + (res.sessions_revoked
            ? ` ${res.sessions_revoked} sesi dicabut (${(res.revoke_reasons || []).join(", ")}) —`
              + " dia perlu masuk lagi."
            : "")
        );
      } else {
        const res = await createUser({
          name: form.name, email: form.email, phone: form.phone, role: form.role,
          password: form.password || "demo12345",
          employee_id: form.employee_id,
          home_entity_id: form.home_entity_id,
          allowed_entity_ids: form.allowed_entity_ids,
          allowed_line_codes: form.allowed_line_codes || [],   // FASE L
        });
        onSaved?.(
          // INV-UI-02 — nama badan usaha lewat helper bersama; id teknis (`ent_ksc`)
          // TIDAK BOLEH muncul ke pengguna walau sebagai cadangan.
          `Akun ${res.name} dibuat di ${entityFull(res.home_entity)}.`
          + (res.home_from_hr ? " Badan usaha utamanya diambil dari data karyawan (HR)." : "")
        );
      }
    } catch (e) {
      setError(errText(e, "Gagal menyimpan akun."));
      onError?.(errText(e, "Gagal menyimpan akun."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" data-testid="account-form-drawer"
         onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="modal-card" style={{ maxWidth: 620, width: "94vw" }}>
        <div className="flex items-start gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <UserCog size={16} className="mt-0.5 text-[#0058CC]" />
          <div className="min-w-0 flex-1">
            <h3 className="text-[13.5px] font-bold">
              {editing ? `Ubah Akun · ${user.name}` : "Buat Akun Baru"}
            </h3>
            <p className="text-[11px] text-[#6B6B73]">
              Akun menentukan data badan usaha mana yang boleh dilihat orang ini.
            </p>
          </div>
          <button type="button" className="icon-button" aria-label="Tutup"
                  data-testid="account-form-close" onClick={onClose}>
            <X size={14} />
          </button>
        </div>

        <div className="space-y-2.5 p-4" style={{ maxHeight: "62vh", overflowY: "auto" }}>
          <div className="grid gap-2.5 sm:grid-cols-2">
            <div className="grid gap-1">
              <label className="kicker">Nama</label>
              <input className="field" data-testid="account-form-name"
                     value={form.name} onChange={(e) => set({ name: e.target.value })} />
            </div>
            <div className="grid gap-1">
              <label className="kicker">Email (untuk masuk)</label>
              <input className="field" data-testid="account-form-email"
                     value={form.email} onChange={(e) => set({ email: e.target.value })} />
            </div>
            <div className="grid gap-1">
              <label className="kicker">Telepon / WhatsApp</label>
              <input className="field" data-testid="account-form-phone"
                     value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
            </div>
            <div className="grid gap-1">
              <label className="kicker">{editing ? "Password baru (opsional)" : "Password awal"}</label>
              <input className="field" type="password" data-testid="account-form-password"
                     placeholder={editing ? "biarkan kosong = tidak diubah" : "minimal 8 karakter"}
                     value={form.password}
                     onChange={(e) => set({ password: e.target.value })} />
            </div>
          </div>

          <div className="grid gap-1">
            <label className="kicker">Peran</label>
            <KNSelect className="field" data-testid="account-form-role"
                      value={form.role} onValueChange={(v) => set({ role: v })}
                      options={ROLE_OPTIONS.map((r) => ({
                        value: r.value, label: `${r.label} — ${r.scope}` }))} />
            <p className="text-[10px] text-[#8E8E93]">
              {isCross
                ? "Peran ini otomatis boleh melihat SEMUA badan usaha aktif (pengawasan grup)."
                : "Peran ini terkunci di badan usahanya. Penugasan tambahan harus dipilih di bawah."}
            </p>
          </div>

          {/* E2.1 — taut karyawan HR */}
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5"
               data-testid="account-form-hr">
            <div className="mb-1.5 flex items-center gap-1.5">
              <Link2 size={13} className="text-[#0058CC]" />
              <p className="kicker !mb-0">Tautkan ke karyawan (HR)</p>
            </div>
            <div className="relative mb-1.5">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input className="field pl-7 py-1 text-[12px]" data-testid="account-form-hr-search"
                     placeholder="Cari nama karyawan…" value={empQuery}
                     onChange={(e) => setEmpQuery(e.target.value)} />
            </div>
            <div className="max-h-28 overflow-auto">
              <button type="button" data-testid="account-form-hr-none"
                      onClick={() => set({ employee_id: "" })}
                      className={`mb-1 w-full rounded-md border px-2 py-1 text-left text-[11px] ${
                        !form.employee_id ? "border-[#0058CC] bg-[#EAF2FF] font-semibold"
                          : "border-[#E5E5EA] bg-white"}`}>
                Tidak ditautkan (isi badan usaha manual)
              </button>
              {employees.map((e) => (
                <button key={e.id} type="button" data-testid={`account-form-hr-${e.id}`}
                        onClick={() => set({ employee_id: e.id })}
                        className={`mb-1 w-full rounded-md border px-2 py-1 text-left text-[11px] ${
                          form.employee_id === e.id
                            ? "border-[#0058CC] bg-[#EAF2FF] font-semibold"
                            : "border-[#E5E5EA] bg-white"}`}>
                  {e.code} · {e.name}
                  <span className="ml-1 text-[10px] text-[#6B6B73]">({e.entity_name})</span>
                </button>
              ))}
              {employees.length === 0 && (
                <p className="text-[10.5px] text-[#8E8E93]" data-testid="account-form-hr-empty">
                  Tidak ada karyawan tanpa akun yang cocok. Tambahkan karyawan lewat menu SDM
                  bila perlu.
                </p>
              )}
            </div>
            {!form.employee_id && (
              <p className="mt-1 flex items-start gap-1 text-[10.5px] text-[#B45309]">
                <Info size={11} className="mt-0.5 shrink-0" />
                Akun tanpa tautan HR berisiko: badan usaha akun bisa berbeda dari data
                penggajian. Tautkan bila orangnya memang karyawan.
              </p>
            )}
          </div>

          {/* Badan usaha utama */}
          <div className="grid gap-1" data-testid="account-form-home">
            <label className="kicker">Badan usaha utama (home)</label>
            {homeFromHr ? (
              <div className="flex items-center gap-2 rounded-md border border-[#BFE3CC] bg-[#EEF9F1] px-2.5 py-1.5"
                   data-testid="account-form-home-locked">
                <Star size={12} className="text-[#1B7F4B]" />
                <span className="text-[11.5px] font-semibold text-[#1C1C1E]">
                  {entities.find((x) => x.id === effectiveHome)?.legal_name || effectiveHome}
                </span>
                <span className="ml-auto text-[10px] text-[#1B7F4B]">
                  diisi otomatis dari HR — tidak bisa diubah di sini
                </span>
              </div>
            ) : (
              <KNSelect className="field" data-testid="account-form-home-select"
                        value={form.home_entity_id}
                        onValueChange={(v) => set({
                          home_entity_id: v,
                          allowed_entity_ids: Array.from(
                            new Set([...(form.allowed_entity_ids || []), v])) })}
                        options={entities.map((e) => ({
                          value: e.id, label: e.legal_name || e.short_name }))}
                        placeholder="Pilih badan usaha…" />
            )}
          </div>

          {/* Penugasan tambahan (hanya untuk peran non-lintas) */}
          {!isCross && (
            <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5"
                 data-testid="account-form-allowed">
              <p className="kicker mb-1">Badan usaha tambahan yang boleh diakses</p>
              <div className="flex flex-wrap gap-1.5">
                {entities.map((e) => {
                  const isHome = e.id === effectiveHome;
                  const on = isHome || (form.allowed_entity_ids || []).includes(e.id);
                  return (
                    <button key={e.id} type="button"
                            data-testid={`account-form-allowed-${e.id}`}
                            disabled={isHome}
                            onClick={() => toggleAllowed(e.id)}
                            className={`rounded-md border px-2 py-1 text-[11px] font-semibold disabled:opacity-70 ${
                              on ? "border-[#0058CC] bg-[#EAF2FF] text-[#0058CC]"
                                 : "border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
                      {isHome && <Star size={9} className="mr-1 inline" />}
                      {e.short_name || e.legal_name}
                    </button>
                  );
                })}
              </div>
              <p className="mt-1 text-[10px] text-[#8E8E93]">
                Badan usaha utama (★) selalu termasuk. Yang tidak dipilih benar-benar TIDAK
                terlihat oleh orang ini — termasuk pesanan, pelanggan, stok, dan laporannya.
              </p>
            </div>
          )}

          {/* FASE L — LINI PRODUK yang boleh dikerjakan. Ditaruh SESUDAH penugasan
              badan usaha karena urutannya memang begitu di kepala admin: "orang ini
              di PT mana" → "mengerjakan lini apa". Kosong = SEMUA lini (bawaan). */}
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5"
               data-testid="account-form-lines">
            <p className="kicker mb-1">Lini produk yang boleh diakses</p>
            {lineOptions.length === 0 ? (
              <p className="text-[10.5px] text-[#8E8E93]" data-testid="account-form-lines-empty">
                Belum ada master Lini Produk. Tambahkan di Pengaturan → Master → Lini Produk.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                <button type="button" data-testid="account-form-line-all"
                        onClick={() => set({ allowed_line_codes: [] })}
                        className={`rounded-md border px-2 py-1 text-[11px] font-semibold ${
                          (form.allowed_line_codes || []).length === 0
                            ? "border-[#0058CC] bg-[#EAF2FF] text-[#0058CC]"
                            : "border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
                  Semua lini
                </button>
                {lineOptions.map((o) => {
                  const on = (form.allowed_line_codes || []).includes(o.value);
                  return (
                    <button key={o.value} type="button"
                            data-testid={`account-form-line-${o.value}`}
                            onClick={() => toggleLine(o.value)}
                            className={`rounded-md border px-2 py-1 text-[11px] font-semibold ${
                              on ? "border-[#6B219A] bg-[#F3E9FA] text-[#6B219A]"
                                 : "border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
                      {o.label}
                    </button>
                  );
                })}
              </div>
            )}
            <p className="mt-1 text-[10px] text-[#8E8E93]">
              Kosong (<b>Semua lini</b>) adalah bawaannya. Bila dipilih, orang ini hanya
              melihat produk, pesanan, roll, dan pekerjaan lini itu — dan ditolak saat
              menambahkan kain lini lain ke dokumen. Data lama yang belum bergolong lini
              tetap terlihat, jadi tidak ada layar yang mendadak kosong.
            </p>
          </div>

          {willRevoke && (
            <div className="flex items-start gap-1.5 rounded-md border border-[#F0C88A] bg-[#FEF7EC] p-2.5"
                 data-testid="account-form-revoke-warning">
              <Info size={13} className="mt-0.5 shrink-0 text-[#8C4A00]" />
              <p className="text-[11px] text-[#3C3C43]">
                Perubahan ini <b>mencabut sesi</b> {user?.name} sehingga dia harus masuk lagi.
                Ini disengaja: tanpa itu, tab yang masih terbuka tetap memakai hak akses lama.
              </p>
            </div>
          )}

          {errors.length > 0 && (
            <ul className="space-y-1 rounded-md border border-[#F0B5AE] bg-[#FCEBEA] p-2.5"
                data-testid="account-form-errors">
              {errors.map((e, i) => (
                <li key={i} className="text-[11px] text-[#A8221A]">• {e}</li>
              ))}
            </ul>
          )}
          {error && (
            <div className="notice-bar danger !py-1.5" data-testid="account-form-error">
              <span className="text-[11.5px]">{error}</span>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button type="button" className="secondary-button" data-testid="account-form-cancel"
                  onClick={onClose}>Batal</button>
          <button type="button" className="primary-button" data-testid="account-form-submit"
                  disabled={busy || errors.length > 0} onClick={submit}>
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            {editing ? "Simpan Perubahan" : "Buat Akun"}
          </button>
        </div>
      </div>
    </div>
  );
}
