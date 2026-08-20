/**
 * roles.js — FASE E-8 (E8.1) · **REGISTRY PERAN sisi layar** (cermin
 * `backend/role_registry.py`).
 *
 * KENAPA ADA: label peran, beranda peran, dan "siapa boleh melihat menu apa" dulu
 * tersebar sebagai literal `"manager"`/`"sales"` di ~81 tempat. Menambah dua peran
 * baru (`sales_admin`, `finance`) dengan cara lama berarti menyunting puluhan berkas
 * dan berharap tidak ada yang terlewat.
 *
 * SATU aturan penting soal MENU: `navStructure.js`/`hubTabs.js` TIDAK disentuh untuk
 * peran baru. Alasannya bukan kemalasan — daftar `roles:` di sana adalah niat desain
 * yang sudah diaudit; menambah dua nama ke ~40 baris membuat riwayat perubahan sulit
 * dibaca dan mudah salah. Sebagai gantinya peran baru dinyatakan EKSPLISIT di satu
 * tempat (di bawah): mewarisi menu peran lain, ditambah/dikurangi daftar yang jelas.
 * Dengan begitu "Admin Sales boleh lihat apa" bisa dibaca sekali pandang.
 */

export const ROLE_REGISTRY = {
  admin: {
    label: "Admin",
    longLabel: "Admin sistem",
    rank: 4,
    crossEntity: true,
    scopeHint: "lintas badan usaha",
    order: 1,
  },
  manager: {
    label: "Manajer",
    longLabel: "Manajer",
    rank: 3,
    crossEntity: true,
    scopeHint: "lintas badan usaha",
    order: 2,
  },
  sales_admin: {
    label: "Admin Sales",
    longLabel: "Admin Sales (alur pesanan)",
    rank: 2,
    crossEntity: false,
    scopeHint: "1 badan usaha (bisa ditugaskan ke beberapa)",
    order: 3,
    newIn: "E-8",
  },
  finance: {
    label: "Finance",
    longLabel: "Kasir / Finance",
    rank: 2,
    crossEntity: false,
    scopeHint: "1 badan usaha (bisa ditugaskan ke beberapa)",
    order: 4,
    newIn: "E-8",
  },
  sales: {
    label: "Sales",
    longLabel: "Sales (lapangan)",
    rank: 1,
    crossEntity: false,
    scopeHint: "1 badan usaha",
    order: 5,
  },
  warehouse: {
    label: "Gudang",
    longLabel: "Gudang (WMS)",
    rank: 1,
    crossEntity: false,
    scopeHint: "1 badan usaha",
    order: 6,
  },
};

export const ROLE_IDS = Object.keys(ROLE_REGISTRY)
  .sort((a, b) => ROLE_REGISTRY[a].order - ROLE_REGISTRY[b].order);

export const CROSS_ENTITY_ROLES = ROLE_IDS.filter((r) => ROLE_REGISTRY[r].crossEntity);

export function roleLabel(role, long = false) {
  const e = ROLE_REGISTRY[role];
  if (!e) return role || "—";
  return long ? e.longLabel : e.label;
}

export function roleRank(role) {
  return ROLE_REGISTRY[role]?.rank || 0;
}

/** Apakah peran aktor memenuhi tuntutan peran sebuah aturan persetujuan? */
export function roleSatisfies(actorRole, requiredRole) {
  if (!requiredRole) return true;
  const need = ROLE_REGISTRY[requiredRole]?.rank ?? ROLE_REGISTRY.manager.rank;
  return roleRank(actorRole) >= need;
}

/** Pilihan peran untuk formulir akun (layar "Badan Usaha & Akses"). */
export const ROLE_OPTIONS = ROLE_IDS.map((id) => ({
  value: id,
  label: ROLE_REGISTRY[id].longLabel,
  scope: ROLE_REGISTRY[id].scopeHint,
  isNew: !!ROLE_REGISTRY[id].newIn,
}));

// ─── VISIBILITAS MENU UNTUK PERAN BARU ───────────────────────────────────────
// `inherit` : mulai dari menu peran ini (biar tidak menulis ulang puluhan id).
// `add`     : id menu / id grup / `view` tab hub yang DITAMBAHKAN.
// `remove`  : yang DICABUT walau ikut terwarisi (pemisahan tugas E8.2).
export const ROLE_NAV = {
  sales_admin: {
    // Admin Sales bekerja di wilayah yang sama dengan sales, plus wewenang
    // pemenuhan: mengajukan pembelian (PR) & mengurus transaksi antar-PT.
    inherit: "sales",
    add: [
      "sales-admin-desk",          // Meja Admin Sales (gelombang 2)
      // E8.3 — sales DICABUT dari "Operasi Gudang" (layar mati: `/api/wms/tasks` 403),
      // tetapi Admin Sales PUNYA izin `wms.view` untuk memantau progres tanpa aksi.
      // Tanpa baris ini ia ikut kehilangan menu itu karena mewarisi menu sales.
      "wms-operations",
      "pembelian", "sourcing", "purchase-requisitions",
      "interco-transactions",
      "return-policies",           // perlu membaca kebijakan retur saat memproses retur
      "document-center", "doc-trace",
      // AUDIT SALES vs ADMIN SALES (sesi 2026-08-15) — keputusan pemilik E8.1b memberi
      // peran ini `approval: ["view"]` ("melihat antrean, tanpa menyetujui"). Izin itu
      // dulu TANPA PINTU: tabnya hanya untuk admin/manager, jadi Admin Sales tak punya
      // cara melihat persetujuan yang nyangkut padahal mengejarnya adalah tugasnya.
      // Layar ini read-only (keputusan tetap di layar kaya konteks milik manajer).
      "approval-inbox",
    ],
    remove: [
      // "Hutang Supplier" (accounts-payable) DICABUT. Menunya dulu ada di sini,
      // tetapi `GET /vendor-bills` menuntut `vendor_bill.view` yang SENGAJA tidak
      // dimiliki peran ini (plan.md E8.1b: "sisi HUTANG tetap manager/admin —
      // jangan diperluas sendiri"). Hasilnya layar mati. Obat yang benar =
      // mencabut menunya, BUKAN melebarkan izinnya.
      "accounts-payable",
      // "Kunjungan Sales" DICABUT. `VisitsView` bercabang: peran `sales` melihat
      // kunjungan MILIKNYA (`/hr/visits/mine`), peran lain masuk ke Log Kunjungan
      // yang memanggil `/hr/visits` + `/hr/employees` (izin HR — bukan milik peran
      // ini). Karena menunya terwarisi dari `sales`, Admin Sales mendarat di layar
      // yang selalu 403. Kunjungan lapangan memang bukan wilayahnya.
      "hr-visits",
    ],
  },
  finance: {
    // Finance TIDAK mewarisi siapa pun: wilayahnya sempit & spesifik supaya
    // "kasir" tidak diam-diam mendapat layar operasional/master.
    inherit: null,
    add: [
      "finance-desk",              // Meja Finance (gelombang 2) — beranda perannya
      "home", "hr-my-profile", "documents",
      "document-center", "doc-trace",
      // Penjualan: hanya MELIHAT pesanan & retur (untuk menagih & mencocokkan)
      "penjualan", "sales-orders", "orders", "returns",
      "customers-crm",
      // Keuangan: uang masuk, piutang, denda, kas, pajak keluaran
      "keuangan", "finance-tower", "ar-aging", "payment-plans", "finance-cases",
      "cash-bank", "cash-management",
      "tax-hub", "tax-invoices",
      "store-credit",
    ],
    remove: [],
  },
};

/**
 * SATU definisi "boleh lihat menu ini?" — dipakai `navigationConfig.js`
 * (sidebar, tab hub, command palette, deep-link) supaya keempatnya tidak
 * pernah berbeda pendapat.
 *
 * @param {string[]|undefined} roles daftar peran pada entri menu/tab
 * @param {string} role peran pengguna
 * @param {string} id id menu / groupId / view tab
 */
export function roleCanSee(roles, role, id) {
  const rule = ROLE_NAV[role];
  if (rule && id && rule.remove.includes(id)) return false;
  if (!Array.isArray(roles)) return true;      // tab tanpa `roles` = semua peran
  if (roles.includes(role)) return true;
  if (!rule) return false;
  if (id && rule.add.includes(id)) return true;
  return !!(rule.inherit && roles.includes(rule.inherit));
}

/** Izin efektif pengguna (dikirim server saat login) → `can(perms, "interco", "create")`. */
export function can(perms, module, action) {
  const actions = (perms || {})[module] || [];
  return actions.includes(action) || actions.includes("*");
}
