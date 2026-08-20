/**
 * inventoryConstants — shared formatters, movement-type map, and stock-status
 * helpers used across the Inventory (WMS Stock tab) sub-components.
 */
import { AlertTriangle, ArrowDownLeft, ArrowUpRight } from "lucide-react";

export const formatQty = (v) => {
  if (v === undefined || v === null) return "0";
  return Number(v).toLocaleString("id-ID", { maximumFractionDigits: 2 });
};

export const formatDate = (iso) => {
  if (!iso) return "-";
  return new Date(iso).toLocaleDateString("id-ID", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
};

export const MOV_TYPE_MAP = {
  initial_stock:       { label: "Stok Awal",            color: "text-gray-600",  dot: "bg-gray-400" },
  inbound_receiving:   { label: "Penerimaan Barang",    color: "text-green-700", dot: "bg-green-500" },
  outbound_dispatch:   { label: "Pengiriman Keluar",    color: "text-red-600",   dot: "bg-red-500" },
  outbound_ship:       { label: "Pengiriman Keluar",    color: "text-red-600",   dot: "bg-red-500" },
  transfer_out:        { label: "Transfer Keluar",      color: "text-orange-600",dot: "bg-orange-400" },
  transfer_in:         { label: "Transfer Masuk",       color: "text-blue-600",  dot: "bg-blue-500" },
  cycle_count_adjust:  { label: "Penyesuaian Stock Opname", color: "text-purple-600", dot: "bg-purple-400" },
  cycle_count_adjustment: { label: "Penyesuaian Stock Opname", color: "text-purple-600", dot: "bg-purple-400" },
  // FASE F — bahan keluar untuk membuat sample (berjurnal Dr 6-7000 / Cr 1-1300)
  sample_issue:        { label: "Ambil Bahan Sample (R&D)", color: "text-amber-700", dot: "bg-amber-500" },
  // Produksi in-house (R6.4)
  production_consume:  { label: "Konsumsi Produksi",    color: "text-orange-700",dot: "bg-orange-500" },
  production_output:   { label: "Hasil Produksi",       color: "text-green-700", dot: "bg-green-600" },
  // Makloon / subkontrak (Fase D)
  subcon_issue:        { label: "Kirim ke Makloon",     color: "text-indigo-600",dot: "bg-indigo-400" },
  subcon_consume:      { label: "Konsumsi Makloon",     color: "text-indigo-700",dot: "bg-indigo-500" },
  subcon_receipt:      { label: "Terima dari Makloon",  color: "text-teal-700",  dot: "bg-teal-500" },
  subcon_receipt_byproduct: { label: "Sisa/Hasil Samping Makloon", color: "text-teal-600", dot: "bg-teal-400" },
  // Retur & koreksi
  return_out:          { label: "Retur Keluar",         color: "text-red-700",   dot: "bg-red-600" },
  return_out_reversal: { label: "Pembalikan Retur",     color: "text-blue-700",  dot: "bg-blue-600" },
  goods_back:          { label: "Barang Kembali",       color: "text-blue-700",  dot: "bg-blue-500" },
  writeoff_reversal:   { label: "Pembalikan Penghapusan", color: "text-blue-700", dot: "bg-blue-600" },
  // Retur PELANGGAN (FASE E-9): barang masuk KARANTINA dulu, baru dilepas/di-scrap.
  // Tiga jenis ini sudah lama ditulis buku mutasi tetapi belum pernah punya label —
  // di layar Mutasi barisnya tampil tanpa jenis sampai data demo punya retur pelanggan.
  return_quarantine_in: { label: "Retur Masuk Karantina", color: "text-amber-700", dot: "bg-amber-500" },
  quarantine_release:  { label: "Lepas Karantina",      color: "text-green-700", dot: "bg-green-500" },
  quarantine_scrap:    { label: "Karantina Dimusnahkan", color: "text-red-700",  dot: "bg-red-600" },
  return_reversal_out: { label: "Pembalikan Retur Jual", color: "text-blue-700", dot: "bg-blue-600" },
  putaway:             { label: "Penempatan Rak",              color: "text-gray-700",  dot: "bg-gray-500" },
  reservation:         { label: "Reservasi",            color: "text-amber-600", dot: "bg-amber-400" },
  release_reservation: { label: "Lepas Reservasi",      color: "text-gray-600",  dot: "bg-gray-400" },
  ownership_transfer_in:  { label: "Alih Kepemilikan Masuk",  color: "text-blue-600", dot: "bg-blue-500" },
  ownership_transfer_out: { label: "Alih Kepemilikan Keluar", color: "text-orange-600", dot: "bg-orange-400" },
  transfer_cancelled:  { label: "Transfer Dibatalkan",  color: "text-gray-600",  dot: "bg-gray-400" },
};

/**
 * Pilihan penyaring "Jenis Mutasi" untuk tab Mutasi (US11).
 * Label Bahasa Indonesia — pengguna gudang tidak perlu tahu kode mentah
 * (`sample_issue`, `subcon_issue`, …). Label ganda (mis. dua kode dengan label
 * "Pengiriman Keluar") digabung menjadi satu pilihan berdasarkan kode pertama.
 */
export const MOV_TYPE_OPTIONS = (() => {
  const seen = new Set();
  const out = [];
  Object.entries(MOV_TYPE_MAP).forEach(([code, meta]) => {
    if (seen.has(meta.label)) return;
    seen.add(meta.label);
    out.push({ value: code, label: meta.label });
  });
  out.sort((a, b) => a.label.localeCompare(b.label, "id-ID"));
  return [{ value: "", label: "Semua jenis mutasi" }, ...out];
})();

/** Label Bahasa Indonesia untuk satu kode mutasi (tanpa pernah memunculkan kode mentah). */
export const movTypeLabel = (code) => MOV_TYPE_MAP[code]?.label || code || "-";

/**
 * FASE E-5 · E5.3 — **lencana badan usaha lawan** pada mutasi pindah-kepemilikan.
 *
 * Kenapa ada: mutasi antar badan usaha wajib tetap terlihat (jejak), tetapi dulu
 * layar hanya menulis "Alih Kepemilikan Masuk" tanpa menyebut asalnya — petugas
 * tidak bisa menindaknya, sedangkan responsnya justru membawa id teknis
 * `ent_kanda` yang tak berarti bagi manusia. Sekarang server mengirim
 * `counterparty_entity_name` berisi **nama singkat saja** ("Kanda"); rincian
 * stok/gudang badan usaha lawan memang tidak boleh bocor (Keputusan #1 pemilik).
 */
export const CounterpartyBadge = ({ movement, className = "" }) => {
  const name = movement?.counterparty_entity_name;
  if (!name) return null;
  const isIn = movement.counterparty_direction === "in";
  const Icon = isIn ? ArrowDownLeft : ArrowUpRight;
  return (
    <span
      data-testid={`movement-counterparty-${movement.id}`}
      data-counterparty={name}
      data-counterparty-direction={movement.counterparty_direction}
      title={isIn
        ? `Kepemilikan berpindah dari ${name} ke badan usaha Anda — rincian stok ${name} tidak ditampilkan`
        : `Kepemilikan berpindah dari badan usaha Anda ke ${name}`}
      className={`inline-flex items-center gap-0.5 rounded px-1.5 py-[1px] text-[9.5px] font-semibold whitespace-nowrap border ${
        isIn
          ? "bg-blue-50 text-blue-700 border-blue-200"
          : "bg-orange-50 text-orange-700 border-orange-200"
      } ${className}`}
    >
      <Icon size={9} />
      {movement.counterparty_label || (isIn ? `dari ${name}` : `ke ${name}`)}
    </span>
  );
};

// Stock status berdasarkan available_qty
export const stockStatus = (b) => {
  if (b.available_qty <= 0) return "empty";
  if (b.available_qty < 100) return "low";
  return "ok";
};

export const ROW_CLASSES = {
  ok:    "hover:bg-[#FAFBFC]",
  low:   "bg-amber-50 hover:bg-amber-100",
  empty: "bg-red-50 hover:bg-red-100",
};

export const STATUS_BADGE = {
  ok:    <span data-testid="stock-status-ok" className="rounded px-1.5 py-0.5 text-[10px] font-semibold bg-green-100 text-green-700">OK</span>,
  low:   <span data-testid="stock-status-low" className="rounded px-1.5 py-0.5 text-[10px] font-semibold bg-amber-100 text-amber-700 flex items-center gap-1"><AlertTriangle size={9} />Rendah</span>,
  empty: <span data-testid="stock-status-empty" className="rounded px-1.5 py-0.5 text-[10px] font-semibold bg-red-100 text-red-700">Habis</span>,
};

// ── Roll-as-SSOT (Fase 0.5) ────────────────────────────────────────────────
export const ROLL_STATUS_META = {
  available:                { label: "Tersedia",   cls: "bg-green-100 text-green-700" },
  reserved:                 { label: "Dipesan",    cls: "bg-orange-100 text-orange-700" },
  committed:                { label: "Dialokasikan",   cls: "bg-purple-100 text-purple-700" },
  picked:                   { label: "Sudah Diambil",      cls: "bg-blue-100 text-blue-700" },
  packed:                   { label: "Sudah Dikemas",      cls: "bg-indigo-100 text-indigo-700" },
  quarantine:               { label: "Karantina",  cls: "bg-amber-100 text-amber-700" },
  blocked:                  { label: "Diblokir",     cls: "bg-amber-100 text-amber-800" },
  damaged:                  { label: "Rusak",     cls: "bg-red-100 text-red-700" },
  sold:                     { label: "Terjual",        cls: "bg-gray-200 text-gray-600" },
  in_transit_inbound:       { label: "Dalam Perjalanan (Masuk)",  cls: "bg-cyan-100 text-cyan-700" },
  in_transit_transfer:      { label: "Dalam Perjalanan (Transfer)", cls: "bg-cyan-100 text-cyan-700" },
  in_transit_intercompany:  { label: "Dalam Perjalanan (Antar-PT)", cls: "bg-teal-100 text-teal-700" },
  in_transit_sales:         { label: "Dalam Perjalanan (Penjualan)",    cls: "bg-cyan-100 text-cyan-700" },
};

export const RollStatusBadge = ({ status }) => {
  const m = ROLL_STATUS_META[status] || { label: status, cls: "bg-gray-100 text-gray-600" };
  return (
    <span data-testid={`roll-status-${status}`} className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${m.cls}`}>
      {m.label}
    </span>
  );
};
