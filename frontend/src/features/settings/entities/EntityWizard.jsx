/**
 * EntityWizard (FASE E-3) — tambah badan usaha dalam 4 langkah yang bisa dimundurkan.
 *
 * Kenapa wizard, bukan satu formulir panjang: membuka badan usaha baru menyangkut
 * empat keputusan yang berbeda sifatnya (identitas legal · pajak & keuangan ·
 * penomoran dokumen · akses). Dicampur jadi satu layar, orang mengisi NPWP di
 * badan usaha non-PKP atau salah kode dokumen — dan kode dokumen TIDAK BISA
 * diubah setelah dokumen pertama terbit. Karena itu langkah 3 menampilkan
 * pratinjau nomor langsung dan peringatan bahwa kode akan terkunci.
 */
import { useEffect, useMemo, useState } from "react";
import { Building2, Loader2, X, ArrowLeft, ArrowRight, Save, ShieldCheck,
  Hash, ClipboardCheck, AlertTriangle } from "lucide-react";

import KNSelect from "../../../components/KNSelect";
import { createEntity, entityTypes, errText } from "./entityApi";

const STEPS = [
  { key: 1, label: "Identitas", icon: Building2 },
  { key: 2, label: "Pajak & Keuangan", icon: ShieldCheck },
  { key: 3, label: "Penomoran & Dokumen", icon: Hash },
  { key: 4, label: "Ringkasan & Kesiapan", icon: ClipboardCheck },
];

const PERSONAL_TYPES = ["Perorangan", "UD"];

const EMPTY = {
  type: "PT",
  legal_name: "",
  short_name: "",
  owner_name: "",
  business_label: "",
  address: "",
  city: "",
  phone: "",
  email: "",
  logo_url: "",
  npwp: "",
  default_tax_mode: "ppn",
  currency: "IDR",
  fiscal_year_start: "01-01",
  coa_template: "id_standard",
  incentive_payer: "sales_entity",
  doc_prefix: "",
  numbering_scheme: "per_entity_prefix",
};

function slugPrefix(shortName) {
  return (shortName || "").replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 6);
}

function Field({ label, hint, children, testId }) {
  return (
    <div className="grid gap-1" data-testid={testId}>
      <label className="kicker">{label}</label>
      {children}
      {hint && <p className="text-[10px] text-[#8E8E93]">{hint}</p>}
    </div>
  );
}

export default function EntityWizard({ entities = [], onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(EMPTY);
  const [types, setTypes] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    entityTypes().then(setTypes).catch(() => setTypes([]));
  }, []);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const isPersonal = PERSONAL_TYPES.includes(form.type);
  const isPkp = form.default_tax_mode === "ppn";
  const typeMeta = useMemo(
    () => types.find((t) => t.value === form.type),
    [types, form.type]
  );

  const effectiveLegalName = isPersonal
    ? [form.owner_name.trim(), form.business_label.trim() ? `(${form.business_label.trim()})` : ""]
      .filter(Boolean).join(" ")
    : form.legal_name.trim();
  const effectivePrefix = (form.doc_prefix || slugPrefix(form.short_name)).toUpperCase();

  const prefixTaken = entities.some(
    (e) => (e.doc_prefix || "").toUpperCase() === effectivePrefix && effectivePrefix
  );
  const shortTaken = entities.some(
    (e) => (e.short_name || "").toLowerCase() === form.short_name.trim().toLowerCase()
      && form.short_name.trim()
  );

  const stepErrors = useMemo(() => {
    const errs = [];
    if (step === 1) {
      if (isPersonal && !form.owner_name.trim()) {
        errs.push("Nama pemilik wajib — usaha perorangan tidak punya badan hukum "
          + "terpisah, jadi nama legalnya adalah nama orangnya.");
      }
      if (!isPersonal && !form.legal_name.trim()) errs.push("Nama legal wajib diisi.");
      if (!form.short_name.trim()) errs.push("Nama singkat wajib diisi.");
      if (shortTaken) errs.push(`Nama singkat “${form.short_name}” sudah dipakai badan usaha lain.`);
    }
    if (step === 2 && isPkp && !form.npwp.trim()) {
      errs.push("Badan usaha PKP wajib mengisi NPWP karena akan menerbitkan faktur pajak. "
        + "Kalau belum PKP, pilih “Non-PKP”.");
    }
    if (step === 3) {
      if (!effectivePrefix) errs.push("Kode dokumen wajib diisi.");
      if (effectivePrefix && !/^[A-Z0-9]{2,10}$/.test(effectivePrefix)) {
        errs.push("Kode dokumen hanya boleh huruf/angka, 2–10 karakter.");
      }
      if (prefixTaken) errs.push(`Kode dokumen “${effectivePrefix}” sudah dipakai badan usaha lain.`);
    }
    return errs;
  }, [step, form, isPersonal, isPkp, effectivePrefix, prefixTaken, shortTaken]);

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const body = { ...form, doc_prefix: effectivePrefix };
      if (isPersonal) body.legal_name = "";   // server yang menyusun dari nama pemilik
      const created = await createEntity(body);
      onCreated?.(created);
    } catch (e) {
      setError(errText(e, "Gagal membuat badan usaha."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" data-testid="entity-wizard"
         onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="modal-card" style={{ maxWidth: 720, width: "95vw" }}>
        <div className="flex items-start gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <Building2 size={16} className="mt-0.5 text-[#0058CC]" />
          <div className="min-w-0 flex-1">
            <h3 className="text-[13.5px] font-bold">Tambah Badan Usaha</h3>
            <p className="text-[11px] text-[#6B6B73]">
              Langkah {step} dari 4 · {STEPS[step - 1].label}
            </p>
          </div>
          <button type="button" className="icon-button" aria-label="Tutup"
                  data-testid="entity-wizard-close" onClick={onClose}>
            <X size={14} />
          </button>
        </div>

        {/* Progres: jelas di mana kita, dan bisa mundur ke langkah yang sudah dilewati */}
        <div className="flex flex-wrap gap-1.5 border-b border-[#EFF0F2] px-4 py-2"
             data-testid="entity-wizard-steps">
          {STEPS.map((s) => {
            const Icon = s.icon;
            const done = s.key < step;
            const active = s.key === step;
            return (
              <button
                key={s.key}
                type="button"
                data-testid={`entity-wizard-step-${s.key}`}
                disabled={s.key > step}
                onClick={() => setStep(s.key)}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold disabled:opacity-45 ${
                  active ? "border-[#0058CC] bg-[#EAF2FF] text-[#0058CC]"
                    : done ? "border-[#BFE3CC] bg-[#EEF9F1] text-[#1B7F4B]"
                      : "border-[#E5E5EA] bg-white text-[#8E8E93]"
                }`}
              >
                <Icon size={11} /> {s.key}. {s.label}
              </button>
            );
          })}
        </div>

        <div className="space-y-3 p-4" style={{ maxHeight: "58vh", overflowY: "auto" }}>
          {step === 1 && (
            <div className="grid gap-2.5" data-testid="entity-wizard-panel-1">
              <Field label="Jenis badan usaha" testId="entity-wizard-type"
                     hint={typeMeta?.description
                       || "Jenis TIDAK menentukan PKP — status PKP diatur di langkah berikutnya."}>
                <KNSelect
                  className="field"
                  data-testid="entity-wizard-type-select"
                  value={form.type}
                  onValueChange={(v) => set({ type: v })}
                  options={(types.length ? types : [{ value: "PT", label: "PT" }])
                    .map((t) => ({ value: t.value, label: t.label }))}
                  placeholder="Pilih jenis…"
                />
              </Field>

              {isPersonal ? (
                <>
                  <Field label="Nama pemilik (wajib)" testId="entity-wizard-owner"
                         hint="Usaha perorangan tidak berbadan hukum terpisah — nama legalnya nama Anda.">
                    <input className="field" data-testid="entity-wizard-owner-input"
                           placeholder="mis. Sutrisno"
                           value={form.owner_name}
                           onChange={(e) => set({ owner_name: e.target.value })} />
                  </Field>
                  <Field label="Label usaha / nama dagang" testId="entity-wizard-business-label">
                    <input className="field" data-testid="entity-wizard-business-label-input"
                           placeholder="mis. Toko Kain Berkah"
                           value={form.business_label}
                           onChange={(e) => set({ business_label: e.target.value })} />
                  </Field>
                  <p className="rounded-md bg-[#F2F7FF] px-2.5 py-1.5 text-[11px] text-[#0058CC]"
                     data-testid="entity-wizard-legal-preview">
                    Nama legal yang akan tersimpan: <b>{effectiveLegalName || "—"}</b>
                  </p>
                </>
              ) : (
                <Field label="Nama legal (sesuai dokumen resmi)" testId="entity-wizard-legal">
                  <input className="field" data-testid="entity-wizard-legal-input"
                         placeholder="mis. PT Kain Suka Cita"
                         value={form.legal_name}
                         onChange={(e) => set({ legal_name: e.target.value })} />
                </Field>
              )}

              <Field label="Nama singkat (dipakai di layar)" testId="entity-wizard-short">
                <input className="field" data-testid="entity-wizard-short-input"
                       placeholder="mis. KSC"
                       value={form.short_name}
                       onChange={(e) => set({ short_name: e.target.value })} />
              </Field>
              <div className="grid gap-2.5 sm:grid-cols-2">
                <Field label="Kota" testId="entity-wizard-city">
                  <input className="field" data-testid="entity-wizard-city-input"
                         value={form.city} onChange={(e) => set({ city: e.target.value })} />
                </Field>
                <Field label="Telepon" testId="entity-wizard-phone">
                  <input className="field" data-testid="entity-wizard-phone-input"
                         value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
                </Field>
              </div>
              <Field label="Alamat" testId="entity-wizard-address">
                <input className="field" data-testid="entity-wizard-address-input"
                       value={form.address} onChange={(e) => set({ address: e.target.value })} />
              </Field>
              <Field label="URL logo (opsional)" testId="entity-wizard-logo"
                     hint="Dipakai di kop dokumen cetak. Bisa diatur belakangan.">
                <input className="field" data-testid="entity-wizard-logo-input"
                       value={form.logo_url} onChange={(e) => set({ logo_url: e.target.value })} />
              </Field>
            </div>
          )}

          {step === 2 && (
            <div className="grid gap-2.5" data-testid="entity-wizard-panel-2">
              <Field label="Status pajak" testId="entity-wizard-tax-mode">
                <div className="grid gap-2 sm:grid-cols-2">
                  {[
                    { v: "ppn", t: "PKP (memungut PPN)",
                      d: "Menerbitkan faktur pajak. NPWP wajib. PPN mengikuti tarif di Pusat Pengaturan." },
                    { v: "non_ppn", t: "Non-PKP (tanpa PPN)",
                      d: "Tidak memungut PPN. Harga jual biasanya lebih bersaing untuk pelanggan kecil." },
                  ].map((o) => (
                    <button
                      key={o.v}
                      type="button"
                      data-testid={`entity-wizard-tax-${o.v}`}
                      onClick={() => set({ default_tax_mode: o.v })}
                      className={`rounded-md border p-2.5 text-left transition-colors ${
                        form.default_tax_mode === o.v
                          ? "border-[#0058CC] bg-[#EAF2FF]"
                          : "border-[#E5E5EA] bg-white hover:border-[#0058CC]/40"
                      }`}
                    >
                      <p className="text-[12px] font-bold text-[#1C1C1E]">{o.t}</p>
                      <p className="text-[10.5px] text-[#6B6B73]">{o.d}</p>
                    </button>
                  ))}
                </div>
              </Field>
              <Field label={`NPWP ${isPkp ? "(wajib untuk PKP)" : "(opsional)"}`}
                     testId="entity-wizard-npwp">
                <input className="field" data-testid="entity-wizard-npwp-input"
                       placeholder="00.000.000.0-000.000"
                       value={form.npwp} onChange={(e) => set({ npwp: e.target.value })} />
              </Field>
              <div className="grid gap-2.5 sm:grid-cols-2">
                <Field label="Mata uang" testId="entity-wizard-currency">
                  <input className="field" data-testid="entity-wizard-currency-input"
                         value={form.currency}
                         onChange={(e) => set({ currency: e.target.value.toUpperCase() })} />
                </Field>
                <Field label="Awal tahun fiskal (MM-DD)" testId="entity-wizard-fiscal"
                       hint="Menentukan periode laporan & tutup buku.">
                  <input className="field" data-testid="entity-wizard-fiscal-input"
                         placeholder="01-01"
                         value={form.fiscal_year_start}
                         onChange={(e) => set({ fiscal_year_start: e.target.value })} />
                </Field>
              </div>
              <Field label="Penanggung insentif sales" testId="entity-wizard-incentive"
                     hint="Model 1: insentif ditanggung badan usaha yang membukukan penjualannya.">
                <KNSelect
                  className="field"
                  data-testid="entity-wizard-incentive-select"
                  value={form.incentive_payer}
                  onValueChange={(v) => set({ incentive_payer: v })}
                  options={[
                    { value: "sales_entity", label: "Badan usaha yang menjual" },
                    { value: "group", label: "Tingkat grup" },
                  ]}
                />
              </Field>
              <p className="text-[10.5px] text-[#6B6B73]">
                Bagan akun (CoA) memakai template bersama <b>{form.coa_template}</b> — kode akun
                sama di semua badan usaha, tetapi bukunya terpisah. Ini membuat laporan
                konsolidasi grup bisa dijumlahkan tanpa pemetaan manual.
              </p>
            </div>
          )}

          {step === 3 && (
            <div className="grid gap-2.5" data-testid="entity-wizard-panel-3">
              <Field label="Kode dokumen" testId="entity-wizard-prefix"
                     hint="Dipakai sebagai awalan SEMUA nomor dokumen badan usaha ini.">
                <input className="field font-mono" data-testid="entity-wizard-prefix-input"
                       placeholder={slugPrefix(form.short_name) || "KSC"}
                       value={form.doc_prefix}
                       onChange={(e) => set({ doc_prefix: e.target.value.toUpperCase() })} />
              </Field>
              <div className="rounded-md border border-[#C9DBF7] bg-[#F2F7FF] p-2.5"
                   data-testid="entity-wizard-number-preview">
                <p className="kicker mb-1">Pratinjau nomor dokumen</p>
                <div className="grid gap-1 sm:grid-cols-2">
                  {[["Pesanan penjualan", "SO-00001"], ["Pesanan pembelian", "PO-00001"],
                    ["Faktur pajak", "FKT-00001"], ["Kwitansi", "AR-00001"]].map(([l, n]) => (
                    <p key={n} className="text-[11.5px] text-[#3C3C43]">
                      {l}: <b className="font-mono">{effectivePrefix || "KODE"}/{n}</b>
                    </p>
                  ))}
                </div>
              </div>
              <div className="flex items-start gap-1.5 rounded-md border border-[#F0C88A] bg-[#FEF7EC] p-2.5">
                <AlertTriangle size={13} className="mt-0.5 shrink-0 text-[#8C4A00]" />
                <p className="text-[11px] text-[#3C3C43]">
                  <b>Kode ini akan TERKUNCI</b> begitu badan usaha menerbitkan dokumen
                  pertamanya. Alasannya: kalau kode berubah di tengah jalan, nomor dokumen
                  lama dan baru tidak bisa dibedakan lagi saat audit pajak. Pastikan sekarang.
                </p>
              </div>
              <Field label="Skema penomoran" testId="entity-wizard-scheme">
                <KNSelect
                  className="field"
                  data-testid="entity-wizard-scheme-select"
                  value={form.numbering_scheme}
                  onValueChange={(v) => set({ numbering_scheme: v })}
                  options={[
                    { value: "per_entity_prefix", label: "Per badan usaha (KODE/SO-00001) — disarankan" },
                    { value: "shared", label: "Deret bersama grup (SO-00001)" },
                  ]}
                />
              </Field>
            </div>
          )}

          {step === 4 && (
            <div className="grid gap-2.5" data-testid="entity-wizard-panel-4">
              <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3"
                   data-testid="entity-wizard-summary">
                <p className="kicker mb-1.5">Ringkasan sebelum disimpan</p>
                {[
                  ["Jenis", form.type],
                  ["Nama legal", effectiveLegalName || "—"],
                  ["Nama singkat", form.short_name || "—"],
                  ["Kota", form.city || "—"],
                  ["Status pajak", isPkp ? "PKP (memungut PPN)" : "Non-PKP"],
                  ["NPWP", form.npwp || "—"],
                  ["Mata uang", form.currency],
                  ["Awal tahun fiskal", form.fiscal_year_start],
                  ["Kode dokumen", effectivePrefix],
                  ["Contoh nomor", `${effectivePrefix}/SO-00001`],
                ].map(([k, v]) => (
                  <p key={k} className="flex justify-between gap-2 border-b border-[#F5F5F7] py-1 text-[11.5px] last:border-0">
                    <span className="text-[#6B6B73]">{k}</span>
                    <b className="text-right text-[#1C1C1E]">{v}</b>
                  </p>
                ))}
              </div>
              <div className="rounded-md border border-[#C9DBF7] bg-[#F2F7FF] p-2.5">
                <p className="text-[11.5px] font-bold text-[#1C1C1E]">Setelah disimpan</p>
                <p className="text-[10.5px] text-[#6B6B73]">
                  Badan usaha langsung siap dipakai: bagan akun tersedia, penomoran aktif,
                  dan lapisan konfigurasinya dibuat. Layar berikutnya menampilkan
                  <b> daftar kesiapan</b> — pengguna, gudang, rekening, harga jual, saldo awal,
                  dan kop surat — supaya Anda tahu apa lagi yang perlu dilengkapi.
                </p>
              </div>
            </div>
          )}

          {stepErrors.length > 0 && (
            <ul className="space-y-1 rounded-md border border-[#F0B5AE] bg-[#FCEBEA] p-2.5"
                data-testid="entity-wizard-step-errors">
              {stepErrors.map((e, i) => (
                <li key={i} className="text-[11px] text-[#A8221A]">• {e}</li>
              ))}
            </ul>
          )}
          {error && (
            <div className="notice-bar danger !py-1.5" data-testid="entity-wizard-error">
              <span className="text-[11.5px]">{error}</span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button type="button" className="secondary-button"
                  data-testid="entity-wizard-back"
                  disabled={step === 1}
                  onClick={() => setStep((s) => Math.max(1, s - 1))}>
            <ArrowLeft size={13} /> Kembali
          </button>
          <div className="flex gap-2">
            <button type="button" className="secondary-button"
                    data-testid="entity-wizard-cancel" onClick={onClose}>
              Batal
            </button>
            {step < 4 ? (
              <button type="button" className="primary-button"
                      data-testid="entity-wizard-next"
                      disabled={stepErrors.length > 0}
                      onClick={() => setStep((s) => Math.min(4, s + 1))}>
                Lanjut <ArrowRight size={13} />
              </button>
            ) : (
              <button type="button" className="primary-button"
                      data-testid="entity-wizard-submit"
                      disabled={busy || stepErrors.length > 0}
                      onClick={submit}>
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                Simpan Badan Usaha
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
