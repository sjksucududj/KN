// ─── docPrint.js — Renderer cetak dokumen (FASE 5) ───────────────────────────
// Payment Voucher & Received Voucher (dari journal entry) + Purchase Requisition
// (blok TTD 6-slot). Client-side print: buka jendela + tulis HTML rapi + print.
import { formatCurrency } from "./formatters";

// ── Terbilang (angka → kata Bahasa Indonesia) ──
const SATUAN_KATA = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh", "sebelas"];
function _terbilang(n) {
  n = Math.floor(Math.abs(n));
  if (n < 12) return SATUAN_KATA[n];
  if (n < 20) return `${_terbilang(n - 10)} belas`;
  if (n < 100) return `${_terbilang(Math.floor(n / 10))} puluh ${_terbilang(n % 10)}`.trim();
  if (n < 200) return `seratus ${_terbilang(n - 100)}`.trim();
  if (n < 1000) return `${_terbilang(Math.floor(n / 100))} ratus ${_terbilang(n % 100)}`.trim();
  if (n < 2000) return `seribu ${_terbilang(n - 1000)}`.trim();
  if (n < 1000000) return `${_terbilang(Math.floor(n / 1000))} ribu ${_terbilang(n % 1000)}`.trim();
  if (n < 1000000000) return `${_terbilang(Math.floor(n / 1000000))} juta ${_terbilang(n % 1000000)}`.trim();
  if (n < 1000000000000) return `${_terbilang(Math.floor(n / 1000000000))} miliar ${_terbilang(n % 1000000000)}`.trim();
  return `${_terbilang(Math.floor(n / 1000000000000))} triliun ${_terbilang(n % 1000000000000)}`.trim();
}
export function terbilang(n) {
  const words = _terbilang(n).replace(/\s+/g, " ").trim();
  return (words ? `${words} rupiah` : "nol rupiah").replace(/^\w/, (c) => c.toUpperCase());
}

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
export const fmtDate = (s) =>
  s ? new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "long", year: "numeric" }) : "..............";

export function printHTML(title, bodyHtml) {
  const w = window.open("", "_blank", "width=900,height=1000");
  if (!w) return;
  w.document.write(`<!doctype html><html lang="id"><head><meta charset="utf-8"/><title>${title}</title>
  <style>
    *{box-sizing:border-box}
    body{font-family:'Segoe UI',Arial,sans-serif;color:#111;margin:0;padding:28px 32px;font-size:12px}
    h1{font-size:18px;margin:0;letter-spacing:.5px}
    .doc-head{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111;padding-bottom:10px;margin-bottom:14px}
    .doc-title{text-align:right}
    .doc-title .t{font-size:16px;font-weight:800;text-transform:uppercase;letter-spacing:1px}
    .doc-title .n{font-size:12px;color:#333;margin-top:2px}
    .meta{display:grid;grid-template-columns:1fr 1fr;gap:2px 24px;margin-bottom:12px}
    .meta div{display:flex;gap:8px}
    .meta .k{width:130px;color:#555}
    .meta .v{font-weight:600}
    table{width:100%;border-collapse:collapse;margin:8px 0 12px}
    th,td{border:1px solid #999;padding:6px 8px;text-align:left;font-size:11.5px}
    th{background:#f0f0f0;text-transform:uppercase;font-size:10px;letter-spacing:.4px}
    td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
    tfoot td{font-weight:800;background:#fafafa}
    .terbilang{font-style:italic;margin:-4px 0 12px;color:#333}
    .checkbox-row{display:flex;gap:22px;margin:8px 0 14px;font-size:12px}
    .cb{display:inline-flex;align-items:center;gap:6px}
    .cb .box{width:14px;height:14px;border:1.5px solid #111;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:800}
    .sign-row{display:flex;justify-content:space-between;gap:10px;margin-top:26px}
    .sign{text-align:center;flex:1;font-size:10.5px}
    .sign .role{font-weight:700;margin-bottom:52px}
    .sign .line{border-top:1px solid #111;padding-top:4px}
    .note{margin-top:8px;font-size:11px;color:#444}
    @media print{body{padding:0}.no-print{display:none}}
  </style></head><body>${bodyHtml}
  <div class="no-print" style="text-align:center;margin-top:24px">
    <button onclick="window.print()" style="padding:8px 20px;font-size:13px;cursor:pointer;background:#0058CC;color:#fff;border:none;border-radius:6px">Cetak / Simpan PDF</button>
  </div>
  <script>setTimeout(function(){window.focus()},250)</script></body></html>`);
  w.document.close();
}

function sign(role, name) {
  return `<div class="sign"><div class="role">${escapeHtml(role)}</div><div class="line">${name ? `( ${escapeHtml(name)} )` : "( .................... )"}</div></div>`;
}
function cb(label, checked) {
  return `<span class="cb"><span class="box">${checked ? "✓" : ""}</span>${escapeHtml(label)}</span>`;
}
function fmtNum(v) { return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(Number(v) || 0); }

// ── Cetak Form Pengajuan Dana (PD) ──
export function printCashAdvance(ca, entityName) {
  const rows = (ca.lines || []).map((l, i) => `
    <tr>
      <td class="num">${i + 1}</td>
      <td>${escapeHtml(l.description || "-")}${l.catatan ? `<br/><span style="color:#777;font-size:10px">${escapeHtml(l.catatan)}</span>` : ""}</td>
      <td class="num">${fmtNum(l.qty)}</td>
      <td>${escapeHtml(l.satuan || "unit")}</td>
      <td class="num">${formatCurrency(l.unit_price)}</td>
      <td class="num">${formatCurrency(l.amount)}</td>
    </tr>`).join("");
  const pay = ca.payment_method === "transfer"
    ? `<span class="cb"><span class="box">✓</span>TRANSFER</span> ${escapeHtml(ca.bank_detail?.bank || "")} ${escapeHtml(ca.bank_detail?.no_account || "")} a.n. ${escapeHtml(ca.bank_detail?.nama || "")}`
    : `<span class="cb"><span class="box">✓</span>TUNAI</span>`;
  const approvals = {};
  (ca.approvals || []).forEach((a) => { approvals[a.stage] = a.by; });
  const body = `
    <div class="doc-head">
      <div><h1>${escapeHtml(entityName || "")}</h1><div style="font-size:11px;color:#555">Formulir Pengajuan Dana</div></div>
      <div class="doc-title"><div class="t">Pengajuan Dana</div><div class="n">No. ${escapeHtml(ca.number || "")}</div></div>
    </div>
    <div class="meta">
      <div><span class="k">Divisi</span><span class="v">${escapeHtml(ca.divisi || "-")}</span></div>
      <div><span class="k">Tanggal</span><span class="v">${fmtDate(ca.tanggal_pengajuan)}</span></div>
      <div><span class="k">Kegiatan</span><span class="v">${escapeHtml(ca.kegiatan || "-")}</span></div>
      <div><span class="k">Periode</span><span class="v">${fmtDate(ca.period_from)} — ${fmtDate(ca.period_to)}</span></div>
      <div><span class="k">Metode Bayar</span><span class="v">${pay}</span></div>
      <div><span class="k">Rekening Sumber</span><span class="v">${escapeHtml(ca.account_label || "-")}</span></div>
    </div>
    <table>
      <thead><tr><th class="num">No</th><th>Uraian</th><th class="num">Qty</th><th>Satuan</th><th class="num">Harga</th><th class="num">Jumlah</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="5">TOTAL PENGAJUAN</td><td class="num">${formatCurrency(ca.total_amount)}</td></tr></tfoot>
    </table>
    <div class="terbilang">Terbilang: <b>${terbilang(ca.total_amount)}</b></div>
    ${ca.catatan ? `<div class="note"><b>Catatan:</b> ${escapeHtml(ca.catatan)}</div>` : ""}
    <div class="sign-row">
      ${sign("Dibuat Oleh", ca.created_by)}
      ${sign("Atasan Langsung", approvals.atasan)}
      ${sign("Pimpinan", approvals.pimpinan)}
      ${sign("Bagian Keuangan", approvals.finance)}
    </div>`;
  printHTML(`PD ${ca.number || ""}`, body);
}

// ── Cetak Tanda Terima (generic, dipanggil dari disburse PD / GR / handover aset) ──
export function printTandaTerima({ dari, nama, berupa, jumlah, keterangan, kota, entityName }) {
  const body = `
    <div class="doc-head">
      <div><h1>${escapeHtml(entityName || "")}</h1></div>
      <div class="doc-title"><div class="t">Tanda Terima</div></div>
    </div>
    <div class="meta" style="grid-template-columns:1fr">
      <div><span class="k">Telah diterima dari</span><span class="v">${escapeHtml(dari || "-")}</span></div>
      <div><span class="k">Nama Penerima</span><span class="v">${escapeHtml(nama || "-")}</span></div>
      <div><span class="k">Berupa</span><span class="v">${escapeHtml(berupa || "Uang Tunai")}</span></div>
      <div><span class="k">Jumlah</span><span class="v">${formatCurrency(jumlah)}</span></div>
    </div>
    <div class="terbilang">Terbilang: <b>${terbilang(jumlah)}</b></div>
    ${keterangan ? `<div class="note"><b>Keterangan:</b> ${escapeHtml(keterangan)}</div>` : ""}
    <div class="sign-row">
      ${sign("Yang Menyerahkan", "")}
      ${sign(`Penerima${kota ? `, ${escapeHtml(kota)} ${fmtDate(new Date().toISOString())}` : ""}`, nama)}
    </div>`;
  printHTML("Tanda Terima", body);
}

// ── Cetak Laporan Pertanggungjawaban (Settlement / LPJ) ──
export function printSettlement(stl, entityName, catLabels = {}) {
  const rows = (stl.expense_lines || []).map((l, i) => `
    <tr>
      <td class="num">${i + 1}</td>
      <td>${fmtDate(l.date)}</td>
      <td>${escapeHtml(l.description || "-")}</td>
      <td>${escapeHtml(catLabels[l.category] || l.category || "-")}</td>
      <td class="num">${formatCurrency(l.amount)}</td>
    </tr>`).join("");
  const sisa = stl.sisa_kurang_dana || 0;
  const body = `
    <div class="doc-head">
      <div><h1>${escapeHtml(entityName || "")}</h1><div style="font-size:11px;color:#555">Laporan Pertanggungjawaban Dana</div></div>
      <div class="doc-title"><div class="t">Pertanggungjawaban</div><div class="n">No. ${escapeHtml(stl.number || "")}</div></div>
    </div>
    <div class="meta">
      <div><span class="k">Ref. PD</span><span class="v">${escapeHtml(stl.cash_advance_number || "-")}</span></div>
      <div><span class="k">Divisi</span><span class="v">${escapeHtml(stl.divisi || "-")}</span></div>
      <div><span class="k">Periode</span><span class="v">${escapeHtml(stl.periode || "-")}</span></div>
      <div><span class="k">Dibuat Oleh</span><span class="v">${escapeHtml(stl.dibuat_oleh || "-")}</span></div>
    </div>
    <table>
      <thead><tr><th class="num">No</th><th>Tanggal</th><th>Uraian</th><th>Kategori</th><th class="num">Jumlah</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot>
        <tr><td colspan="4">TOTAL PENGELUARAN</td><td class="num">${formatCurrency(stl.total_pengeluaran)}</td></tr>
        <tr><td colspan="4">DANA DITERIMA (PD)</td><td class="num">${formatCurrency(stl.total_pettycash)}</td></tr>
        <tr><td colspan="4">${sisa >= 0 ? "SISA DIKEMBALIKAN" : "KEKURANGAN DANA"}</td><td class="num">${formatCurrency(Math.abs(sisa))}</td></tr>
      </tfoot>
    </table>
    <div class="sign-row">
      ${sign("Dibuat Oleh", stl.dibuat_oleh)}
      ${sign("Disetujui", stl.disetujui_oleh)}
      ${sign("Bagian Keuangan", "")}
    </div>`;
  printHTML(`LPJ ${stl.number || ""}`, body);
}

// Deteksi medium kas dari baris jurnal (Kas Kecil / Bank / Kas/Tunai).
function detectMedium(lines) {
  const names = (lines || []).map((l) => `${l.account_code || ""} ${l.account_name || ""}`.toLowerCase());
  const joined = names.join(" | ");
  if (joined.includes("kecil") || joined.includes("petty")) return "petty";
  if (joined.includes("bank")) return "bank";
  return "cash";
}

// ── Payment / Received Voucher (dari journal entry) ──
function voucherHtml(je, entityName, kind) {
  const isPayment = kind === "payment";
  const title = isPayment ? "Payment Voucher" : "Received Voucher";
  const medium = detectMedium(je.lines);
  const rows = (je.lines || []).map((l) => `
    <tr>
      <td>${escapeHtml(l.account_code || "")} — ${escapeHtml(l.account_name || "")}</td>
      <td>${escapeHtml(l.memo || l.description || "-")}</td>
      <td class="num">${l.debit > 0 ? formatCurrency(l.debit) : "-"}</td>
      <td class="num">${l.credit > 0 ? formatCurrency(l.credit) : "-"}</td>
    </tr>`).join("");
  const total = je.total_debit || je.total_credit || 0;
  const signs = isPayment
    ? sign("Dibuat", je.created_by) + sign("Diperiksa", "") + sign("Disetujui", "") + sign("Diposting", "") + sign("Diterima", "")
    : sign("Dibuat", je.created_by) + sign("Diperiksa", "") + sign("Disetujui", "") + sign("Diposting", "") + sign("Penyetor", "");
  const body = `
    <div class="doc-head">
      <div><h1>${escapeHtml(entityName || "")}</h1><div style="font-size:11px;color:#555">${isPayment ? "Bukti Kas/Bank Keluar" : "Bukti Kas/Bank Masuk"}</div></div>
      <div class="doc-title"><div class="t">${title}</div><div class="n">No. ${escapeHtml(je.number || "")}</div></div>
    </div>
    <div class="meta">
      <div><span class="k">Tanggal</span><span class="v">${fmtDate(je.date)}</span></div>
      <div><span class="k">Sumber</span><span class="v">${escapeHtml(je.source_label || je.source_type || "-")}</span></div>
      <div><span class="k">Keterangan</span><span class="v">${escapeHtml(je.description || "-")}</span></div>
      <div><span class="k">Dibuat oleh</span><span class="v">${escapeHtml(je.created_by || "-")}</span></div>
    </div>
    <div class="checkbox-row">
      <b>Metode:</b>
      ${cb("Cash / Tunai", medium === "cash")}
      ${cb("Bank / Transfer", medium === "bank")}
      ${cb("Petty Cash / Kas Kecil", medium === "petty")}
    </div>
    <table>
      <thead><tr><th>Akun</th><th>Memo</th><th class="num">Debit</th><th class="num">Kredit</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="2">TOTAL</td><td class="num">${formatCurrency(je.total_debit)}</td><td class="num">${formatCurrency(je.total_credit)}</td></tr></tfoot>
    </table>
    <div class="terbilang">Terbilang: <b>${terbilang(total)}</b></div>
    <div class="sign-row">${signs}</div>`;
  printHTML(`${title} ${je.number || ""}`, body);
}
export const printPaymentVoucher = (je, entityName) => voucherHtml(je, entityName, "payment");
export const printReceivedVoucher = (je, entityName) => voucherHtml(je, entityName, "received");

// ── Purchase Requisition (blok TTD 6-slot untuk cetak) ──
export function printPurchaseRequisition(pr, entityName) {
  const rows = (pr.items || []).map((it, i) => `
    <tr>
      <td class="num">${i + 1}</td>
      <td>${escapeHtml(it.product_name || it.description || "-")}${it.product_id ? `<br/><span style="color:#777;font-size:10px">${escapeHtml(it.sku || "")}</span>` : `<br/><span style="color:#8C4A00;font-size:10px">Non-katalog</span>`}</td>
      <td class="num">${it.quantity ?? "-"}</td>
      <td>${escapeHtml(it.unit || "-")}</td>
      <td class="num">${formatCurrency(it.est_price)}</td>
      <td class="num">${formatCurrency(it.subtotal)}</td>
    </tr>`).join("");
  const body = `
    <div class="doc-head">
      <div><h1>${escapeHtml(entityName || "")}</h1><div style="font-size:11px;color:#555">Permintaan Pembelian (PR)</div></div>
      <div class="doc-title"><div class="t">Permintaan Pembelian</div><div class="n">No. ${escapeHtml(pr.number || "")}</div></div>
    </div>
    <div class="meta">
      <div><span class="k">Tanggal Dibutuhkan</span><span class="v">${escapeHtml(pr.needed_by_date || "-")}</span></div>
      <div><span class="k">Gudang</span><span class="v">${escapeHtml(pr.warehouse_name || "-")}</span></div>
      <div><span class="k">Supplier Preferensi</span><span class="v">${escapeHtml(pr.preferred_supplier_name || "-")}</span></div>
      <div><span class="k">Dibuat oleh</span><span class="v">${escapeHtml(pr.created_by || "-")}</span></div>
      <div><span class="k">Sumber</span><span class="v">${escapeHtml(pr.source || "-")}</span></div>
      <div><span class="k">Total Estimasi</span><span class="v">${formatCurrency(pr.total_est_amount)}</span></div>
    </div>
    <table>
      <thead><tr><th class="num">No</th><th>Item</th><th class="num">Qty</th><th>Satuan</th><th class="num">Est. Harga</th><th class="num">Subtotal</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="5">TOTAL ESTIMASI</td><td class="num">${formatCurrency(pr.total_est_amount)}</td></tr></tfoot>
    </table>
    ${pr.reason ? `<div class="note"><b>Alasan / Justifikasi:</b> ${escapeHtml(pr.reason)}</div>` : ""}
    <div class="sign-row">
      ${sign("Prepared By", pr.created_by)}
      ${sign("Divisi Head", "")}
      ${sign("Logistic Head", "")}
    </div>
    <div class="sign-row" style="margin-top:20px">
      ${sign("Manager Accounting", "")}
      ${sign("General Manager", "")}
      ${sign("Director", "")}
    </div>`;
  printHTML(`PR ${pr.number || ""}`, body);
}
