/**
 * masterFieldsConfig (FASE L) — DEFINISI KOLOM & FIELD untuk layar Master Berlapis.
 *
 * KENAPA BERKAS INI DIPISAH
 * `EntityMastersView.jsx` memegang `COLUMNS` & `CREATE_FIELDS` per jenis master
 * secara hardcode. Dua akibatnya sudah terukur (RENCANA_EKSEKUSI_MD_ERP.md §3.3):
 *   1. Jenis master BARU (lini produk sekarang; tahapan proses, jenis sampling, dan
 *      alasan komplain pada fase berikutnya) akan muncul di daftar kelompok dengan
 *      **tabel tanpa kolom** — layarnya "ada" tetapi tidak memperlihatkan apa pun.
 *   2. Berkasnya sudah 543 baris (panduan repo 500); menambah 4 jenis mendorongnya
 *      ke ±700 baris.
 * Jadi definisinya pindah ke sini: menambah master baru = menambah SATU entri data,
 * bukan menyunting layar.
 *
 * Tipe field yang didukung form:
 *   text (bawaan) · number · select (options) · list (dipisah koma → array) ·
 *   checkbox (boolean)
 * Field boleh punya `default` — dipakai saat form "Baris baru" dibuka. Untuk master
 * yang punya invarian (mis. Tahapan Proses dijaga gate INV-DOMAIN-06), bawaan yang
 * SAH mencegah pemilik membuat baris yang langsung memerahkan gate.
 */

// FASE T — kosakata tahapan proses dipinjam dari SATU sumber (`constants/makloonVocab`)
// supaya tabel master, form master, dan wizard SPK memakai kalimat yang sama; pemilik
// tidak perlu menerjemahkan `service_only` menjadi "jasa murni" di kepalanya.
import { MATERIAL_FLOW_LABELS, STAGE_KIND_LABELS } from "../../../constants/makloonVocab";

/** Kolom yang ditampilkan per jenis master (label manusia + cara render). */
export const COLUMNS = {
  "payment-terms": [
    { key: "code", label: "Kode", mono: true },
    { key: "name", label: "Nama" },
    { key: "type", label: "Jenis" },
    { key: "net_days", label: "Jatuh tempo (hari)", align: "right" },
    { key: "dp_percent", label: "DP %", align: "right" },
  ],
  "expense-categories": [
    { key: "code", label: "Kode", mono: true },
    { key: "label", label: "Nama kategori" },
    { key: "account_code", label: "Akun buku besar", mono: true },
  ],
  "document-templates": [
    { key: "document_type", label: "Jenis dokumen", mono: true },
    { key: "name", label: "Nama template" },
    { key: "header", label: "Kop surat" },
    { key: "paper_size", label: "Kertas" },
  ],
  "sales-return-policies": [
    { key: "name", label: "Nama kebijakan" },
    { key: "scope", label: "Cakupan" },
    { key: "window_days", label: "Jendela (hari)", align: "right" },
    { key: "restocking_fee_pct", label: "Biaya restocking %", align: "right" },
  ],
  "incentive-rates": [
    { key: "category", label: "Kategori produk" },
    { key: "incentive_unit", label: "Satuan" },
    { key: "per_unit_amount", label: "Per satuan", align: "right", money: true },
    { key: "margin_cap_pct", label: "Batas margin %", align: "right" },
  ],
  "approval-rules": [
    { key: "doc_type", label: "Dokumen", mono: true },
    { key: "min_amount", label: "Dari", align: "right", money: true },
    { key: "max_amount", label: "Sampai", align: "right", money: true },
    { key: "required_role", label: "Wajib disetujui" },
  ],
  // ── FASE L — LINI PRODUK (pembagian kerja MD). Kolom dipilih supaya pemilik bisa
  // menjawab tiga pertanyaan langsung dari tabel: lini ini untuk kain apa
  // (`fabric_type_required`), satuan yang biasa dipakai, dan urutan tahapannya.
  "product-lines": [
    { key: "code", label: "Kode", mono: true },
    { key: "name", label: "Nama lini" },
    { key: "fabric_type_required", label: "Khusus jenis kain", empty: "bebas" },
    { key: "measure_unit_default", label: "Satuan usulan" },
    { key: "stage_sequence", label: "Urutan tahap", list: true },
    { key: "sort", label: "Urut", align: "right" },
  ],
  // ── FASE T — TAHAPAN PROSES (termasuk pembuatan SCREEN/kasa). Kolom dipilih supaya
  // pemilik bisa menjawab EMPAT pertanyaan langsung dari tabel, tanpa membuka baris:
  // tahap ini mesinnya apa (`process_type`), apakah kainnya BERUBAH tahap
  // (`changes_stage`), apakah kainnya benar-benar DIKIRIM (`material_flow`), dan
  // siapa yang mengerjakan (`needs_vendor`). Tiga yang terakhir itulah yang
  // menentukan aksi mana yang muncul di SPK — kalau tak terlihat di sini, pemilik
  // baru tahu akibatnya saat petugas tertahan di layar SPK.
  "process-stages": [
    { key: "code", label: "Kode", mono: true },
    { key: "name", label: "Nama tahap" },
    { key: "kind", label: "Jenis", labels: STAGE_KIND_LABELS },
    { key: "process_type", label: "Mesin tarif/estimasi", empty: "—" },
    { key: "changes_stage", label: "Mengubah kain?",
      labels: { true: "Ya — kain naik tahap", false: "Tidak — hanya jasa" } },
    { key: "material_flow", label: "Aliran kain", labels: MATERIAL_FLOW_LABELS, empty: "—" },
    { key: "needs_vendor", label: "Mitra wajib?",
      labels: { true: "Ya — dikerjakan mitra", false: "Tidak" } },
    { key: "applies_to_lines", label: "Lini", list: true, empty: "semua lini" },
    { key: "seq", label: "Urut", align: "right" },
  ],
};

/** Field yang bisa diisi saat menambah baris baru, per jenis master. */
export const CREATE_FIELDS = {
  "payment-terms": [
    { key: "code", label: "Kode", required: true, placeholder: "mis. NET45" },
    { key: "name", label: "Nama", required: true, placeholder: "Kredit NET 45 Hari" },
    { key: "type", label: "Jenis", type: "select",
      options: [
        { value: "cash", label: "Tunai" }, { value: "credit", label: "Kredit" },
        { value: "dp", label: "DP + pelunasan" }, { value: "installment", label: "Bertahap" },
      ] },
    { key: "net_days", label: "Jatuh tempo (hari)", type: "number" },
    { key: "dp_percent", label: "DP (%)", type: "number" },
  ],
  "expense-categories": [
    { key: "code", label: "Kode", required: true, placeholder: "mis. bensin_operasional" },
    { key: "label", label: "Nama kategori", required: true, placeholder: "Bensin Operasional" },
    { key: "account_code", label: "Akun buku besar", required: true, placeholder: "6-4300" },
  ],
  "document-templates": [
    { key: "document_type", label: "Jenis dokumen", required: true, placeholder: "surat_jalan" },
    { key: "name", label: "Nama template", required: true, placeholder: "Template SJ Kanda" },
    { key: "header", label: "Kop surat", placeholder: "CV KANDA SUKA — Tekstil" },
    { key: "footer", label: "Catatan kaki" },
  ],
  // FASE L — menambah lini keempat (mis. "Denim") cukup lewat form ini; chipnya
  // langsung muncul di 12 layar karena nilainya dibaca dari master, bukan kode.
  "product-lines": [
    { key: "code", label: "Kode lini", required: true, placeholder: "mis. denim" },
    { key: "name", label: "Nama lini", required: true, placeholder: "Denim" },
    { key: "fabric_type_required", label: "Khusus jenis kain", type: "select",
      hint: "Kosongkan bila lini ini boleh untuk woven maupun knit (mis. printing).",
      options: [
        { value: "", label: "Bebas (woven & knit)" },
        { value: "woven", label: "Hanya woven (tenun)" },
        { value: "knit", label: "Hanya knit (rajut)" },
      ] },
    { key: "measure_unit_default", label: "Satuan usulan", type: "select",
      hint: "USULAN saat membuat produk/PO. Satuan kendali tetap dari jenis kain.",
      // FASE U — pilihannya datang dari MASTER SATUAN (`uoms`), bukan diketik di sini.
      // Dulu daftarnya 4 nilai tetap; satuan baru yang ditambah pemilik (mis. satuan
      // lokal seperti `lembar`) tidak pernah bisa dijadikan usulan, jadi masternya
      // ada tetapi tak berpengaruh — bentuk paling langsung dari keluhan pemilik.
      optionsFrom: "uom" },
    { key: "stage_sequence", label: "Urutan tahap", type: "list",
      placeholder: "yarn, tenun, celup, inspect" },
    { key: "sample_types_default", label: "Jenis sampling usulan", type: "list",
      placeholder: "labdip, proofing" },
    { key: "sort", label: "Urutan tampil", type: "number" },
    { key: "notes", label: "Catatan" },
  ],
  // ── FASE T — menambah tahap baru (mis. "Sanforize") = mengisi form ini, bukan
  // menunggu programmer (user story T.F-1). Bawaan sengaja dipilih yang PALING AMAN:
  // `changes_stage` MATI, karena tahap yang mengubah kain wajib punya pasangan di
  // `STAGE_TRANSITIONS` (gate INV-DOMAIN-06 aturan D) — bawaan yang menyala akan
  // membuat tahap baru langsung memerahkan gate dan menawarkan langkah yang mesin
  // makloon pasti menolak.
  "process-stages": [
    { key: "code", label: "Kode tahap", required: true, placeholder: "mis. sanforize",
      hint: "Huruf kecil tanpa spasi. Kode ini yang tersimpan di langkah SPK." },
    { key: "name", label: "Nama tahap", required: true, placeholder: "Sanforize (anti susut)" },
    { key: "kind", label: "Jenis tahap", type: "select", default: "makloon",
      hint: "Hanya jenis 'Dikerjakan mitra' & 'Sampling' yang bisa jadi langkah SPK.",
      options: Object.entries(STAGE_KIND_LABELS).map(([value, label]) => ({ value, label })) },
    { key: "process_type", label: "Mesin tarif/estimasi", type: "select",
      hint: "Menyambung tahap ini ke rumus tarif & estimasi yang sudah ada.",
      options: [
        { value: "", label: "— tidak memakai mesin makloon —" },
        { value: "tenun", label: "Tenun" }, { value: "rajut", label: "Rajut" },
        { value: "pre_treatment", label: "Pre-treatment (PFD/PFP)" },
        { value: "celup", label: "Celup" }, { value: "screen", label: "Screen / kasa" },
        { value: "printing", label: "Printing" }, { value: "finishing", label: "Finishing" },
        { value: "lainnya", label: "Lainnya" },
      ] },
    { key: "material_flow", label: "Aliran kain", type: "select", default: "moves",
      hint: "Menentukan aksi di SPK: kain dikirim → Issue & Terima Hasil; jasa murni → Catat Jasa.",
      options: Object.entries(MATERIAL_FLOW_LABELS).map(([value, label]) => ({ value, label })) },
    { key: "material_flow_default", label: "Bawaan bila 'boleh dua-duanya'", type: "select",
      default: "moves",
      hint: "Dipakai bila langkah SPK tidak memilih. Wajib konkret — mesin tidak boleh menebak.",
      options: [
        { value: "moves", label: MATERIAL_FLOW_LABELS.moves },
        { value: "service_only", label: MATERIAL_FLOW_LABELS.service_only },
      ] },
    { key: "changes_stage", label: "Mengubah tahap kain?", type: "checkbox", default: false,
      hint: "Centang HANYA bila kain berpindah tahap (mis. grey → PFP). Tahap seperti "
            + "pembuatan kasa tidak mengubah kain: qty keluar = qty masuk." },
    { key: "from_stage", label: "Dari tahap kain", type: "select", default: "",
      hint: "Diisi bila tahap ini mengubah kain.",
      options: [
        { value: "", label: "— tidak relevan —" }, { value: "yarn", label: "Benang" },
        { value: "grey", label: "Grey" }, { value: "pfd", label: "PFD" },
        { value: "pfp", label: "PFP" }, { value: "finished", label: "Jadi (finished)" },
      ] },
    { key: "to_stage", label: "Menjadi tahap kain", type: "select", default: "",
      options: [
        { value: "", label: "— tidak relevan —" }, { value: "yarn", label: "Benang" },
        { value: "grey", label: "Grey" }, { value: "pfd", label: "PFD" },
        { value: "pfp", label: "PFP" }, { value: "finished", label: "Jadi (finished)" },
      ] },
    { key: "needs_vendor", label: "Wajib dikerjakan mitra?", type: "checkbox", default: true,
      hint: "SPK tanpa mitra tetap bisa disimpan, tetapi membawa peringatan — dan gate "
            + "memerah bila belum ada satu pun mitra yang mencantumkan proses ini." },
    { key: "tariff_basis_default", label: "Basis tarif usulan", type: "select",
      options: [
        { value: "", label: "— ikut kontrak mitra —" }, { value: "kg", label: "Per kg" },
        { value: "yard", label: "Per yard" }, { value: "meter", label: "Per meter" },
        { value: "roll", label: "Per roll" }, { value: "pick", label: "Per pick (PPI)" },
        { value: "lumpsum", label: "Borongan / lumpsum" },
      ] },
    { key: "applies_to_lines", label: "Berlaku untuk lini", type: "list",
      placeholder: "woven, knit", hint: "Kosong = berlaku untuk SEMUA lini." },
    { key: "seq", label: "Urutan tampil", type: "number", default: 100 },
    { key: "notes", label: "Catatan" },
  ],
};

/** Nilai sel → teks. Dipakai tabel (list dirender "a · b · c"). */
export function cellText(col, row, formatCurrency) {
  const v = row[col.key];
  if (Array.isArray(v)) return v.length ? v.join(" · ") : (col.empty || "—");
  // `labels` mendahului pemformatan bawaan: "Tidak" tidak memberi tahu apa pun,
  // sedangkan "Tidak — hanya jasa" menjelaskan akibatnya di layar SPK.
  if (col.labels && v !== null && v !== undefined && v !== "") {
    const hit = col.labels[String(v)];
    if (hit) return hit;
  }
  if (v === null || v === undefined || v === "") return col.empty || "—";
  if (col.money && typeof formatCurrency === "function") return formatCurrency(v);
  if (typeof v === "boolean") return v ? "Ya" : "Tidak";
  return String(v);
}

/** Nilai bawaan form "Baris baru" per jenis master (kosong bila tak didefinisikan). */
export function defaultsFor(kind) {
  const out = {};
  for (const f of CREATE_FIELDS[kind] || []) {
    if (f.default !== undefined) out[f.key] = f.default;
  }
  return out;
}

/** Nilai form → bentuk yang dikirim API (list: "a, b" → ["a","b"]). */
export function parseFieldValue(field, raw) {
  if (!field) return raw;
  if (field.type === "number") return raw === "" || raw === null ? "" : Number(raw);
  if (field.type === "list") {
    return String(raw || "").split(",").map((s) => s.trim()).filter(Boolean);
  }
  if (field.type === "checkbox") return Boolean(raw);
  return raw;
}

/** Bentuk API → nilai yang bisa diketik di form (array → "a, b"). */
export function toInputValue(field, value) {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined) return "";
  return value;
}

/** Definisi field (untuk sel yang bisa disunting inline). */
export function fieldOf(kind, key) {
  return (CREATE_FIELDS[kind] || []).find((f) => f.key === key) || null;
}
