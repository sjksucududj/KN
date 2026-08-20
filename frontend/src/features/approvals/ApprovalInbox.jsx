import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  Inbox, ShoppingCart, Tag, ArrowRight, Clock, RefreshCw, CheckSquare,
  RotateCcw, ClipboardCheck, ShieldCheck, CreditCard, FileEdit,
} from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
// Tujuan navigasi yang SAH untuk peran ini (sumber sama dengan Ctrl+K & deep-link) —
// dipakai ringkasan antrean agar tidak pernah menawarkan tautan yang buntu.
import { resolveDeepLinkTarget } from "../../config/navigationConfig";

/**
 * ApprovalInbox — "Pusat Persetujuan" (FASE 5 — terpadu).
 * Hub lintas-modul: menampilkan SEMUA persetujuan yang menunggu keputusan dalam satu tempat:
 *  - Sales Order (SSOT `pending_approvals`: nilai / kredit / harga khusus) → deep-link ke DETAIL SO.
 *  - PO pembelian, retur jual/beli, cycle count → deep-link ke antrian modul terkait.
 * Read-only di sini — keputusan dilakukan di view yang kaya konteks (detail SO / view modul).
 */

// kind → tampilan (label, ikon, warna) + tab grup
const KIND_META = {
  so_nilai:         { label: "SO · Nilai Pesanan",  icon: ShieldCheck,    fg: "#4F46E5", bg: "#EEF0FF", group: "sales_order" },
  so_kredit:        { label: "SO · Kredit",       icon: CreditCard,     fg: "#DC2626", bg: "#FEE2E2", group: "sales_order" },
  so_special_price: { label: "SO · Harga Khusus", icon: Tag,            fg: "#B45309", bg: "#FEF3C7", group: "sales_order" },
  po:              { label: "PO Pembelian",  icon: ShoppingCart,   fg: "#0058CC", bg: "#EFF4FF", group: "po" },
  price:           { label: "Harga Khusus",  icon: Tag,            fg: "#6D28D9", bg: "#F3EEFF", group: "price" },
  sales_return:    { label: "Retur Jual",    icon: RotateCcw,      fg: "#B45309", bg: "#FEF3C7", group: "returns" },
  purchase_return: { label: "Retur Beli",    icon: RotateCcw,      fg: "#0E7490", bg: "#E0F2FE", group: "returns" },
  cycle:           { label: "Stock Opname",   icon: ClipboardCheck, fg: "#15803D", bg: "#DCFCE7", group: "cycle" },
  // FASE G-1 — koreksi angka dokumen keuangan (amandemen ber-alasan & ber-dampak).
  amendment:       { label: "Amandemen Dokumen", icon: FileEdit,   fg: "#7A2CA0", bg: "#F3E9FA", group: "amendment" },
};

const SO_KIND_BY_TYPE = { nilai: "so_nilai", kredit: "so_kredit", special_price: "so_special_price" };

const TABS = [
  { key: "all",         label: "Semua" },
  { key: "sales_order", label: "Pesanan Penjualan" },
  { key: "amendment",   label: "Amandemen" },
  { key: "po",          label: "Pembelian (PO)" },
  { key: "price",       label: "Harga Khusus" },
  { key: "returns",     label: "Retur" },
  { key: "cycle",       label: "Stock Opname" },
];

function timeAgo(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 3600) return `${Math.max(1, Math.floor(diff / 60))} mnt lalu`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} jam lalu`;
  return `${Math.floor(diff / 86400)} hari lalu`;
}

const arr = (d) => (Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : []));

export default function ApprovalInbox({ currentUser, onNavigate, onOpenDocument }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("all");
  /**
   * RINGKASAN SELURUH ANTREAN (F-3, 2026-08-15) — dari `GET /approvals/backlog`,
   * sumber yang SAMA dengan KPI beranda. Sebelum ini layar ini menghitung
   * antreannya sendiri dari 7 permintaan di browser, sementara beranda memakai
   * sumber lain: satu pertanyaan, tiga angka berbeda (dan yang di beranda selalu 0).
   * Antrean yang TIDAK ditampilkan layar ini (PR · spesifikasi/sample · pesanan
   * khusus · antar-PT di atas ambang) tetap disebut di sini beserta jalannya,
   * supaya "Pusat Persetujuan" berhenti mengaku kosong untuk pekerjaan yang
   * sebenarnya menumpuk di tab sebelah.
   */
  const [backlog, setBacklog] = useState(null);
  // AUDIT SALES vs ADMIN SALES (2026-08-15) — kategori yang GAGAL dimuat.
  // Sebelumnya setiap panggilan memakai `.catch(() => ({ data: [] }))` sehingga
  // penolakan izin berubah menjadi "tidak ada yang menunggu persetujuan" —
  // kalimat yang TIDAK BENAR dan berbahaya di layar yang dipakai untuk memutuskan.
  // Sejak layar ini juga dibuka untuk Admin Sales (read-only), kategori di luar
  // wilayahnya wajar tak terbaca; yang tidak boleh adalah menyembunyikannya.
  const [unavailable, setUnavailable] = useState([]);

  useEffect(() => { load(); }, []); // eslint-disable-line

  async function load() {
    setLoading(true);
    const gagal = [];
    /** Ambil satu sumber; catat namanya bila tak boleh/gagal (bukan diam-diam kosong). */
    const grab = (label, promise) => promise.catch((e) => {
      gagal.push(label);
      return { data: [], _failed: e };
    });
    try {
      const [queueRes, poRes, prRes, srRes, purRes, ccRes, amdRes, blRes] = await Promise.all([
        grab("Pesanan Penjualan", axios.get(`${API}/approvals/queue`)),
        grab("Pembelian (PO)", axios.get(`${API}/purchase-orders`)),
        grab("Harga Khusus", axios.get(`${API}/price-approvals`, { params: { status: "pending" } })),
        grab("Retur Jual", axios.get(`${API}/sales-returns`, { params: { status: "pending_approval" } })),
        grab("Retur Beli", axios.get(`${API}/purchase-returns`)),
        grab("Stock Opname", axios.get(`${API}/cycle-count/sessions`)),
        grab("Amandemen", axios.get(`${API}/amendments`, { params: { status: "pending_approval" } })),
        // FASE F-6 — `?oldest=15` sekalian membawa DOKUMEN paling lama menunggu dari
        // SEMUA antrean (termasuk 14 antrean yang layar ini tidak muat: transfer gudang,
        // kontrabon, permintaan internal, cuti, lembur, uang muka, klaim makloon, …).
        // Tanpa ini antrean-antrean itu hanya jadi angka di chip; sekarang orangnya bisa
        // melihat NOMOR dokumen + sudah berapa lama menunggu, lalu melompat ke layarnya.
        grab("Ringkasan Antrean", axios.get(`${API}/approvals/backlog`, { params: { oldest: 15 } })),
      ]);
      setUnavailable(gagal);
      setBacklog(blRes?.data && !Array.isArray(blRes.data) ? blRes.data : null);

      // FASE 5 — Sales Order approvals (SSOT pending_approvals): nilai / kredit / harga khusus.
      const soApprovals = arr(queueRes.data).map((q) => ({
        kind: SO_KIND_BY_TYPE[q.type] || "so_nilai",
        id: q.id, orderId: q.order_id,
        title: q.order_number || "Sales Order",
        subtitle: q.customer_name || "Customer",
        meta: q.type === "special_price"
          ? `${q.product_name || "Item"} · ${formatCurrency(q.normal_price)} → ${formatCurrency(q.requested_price)}`
          : (q.reason || q.type_label || ""),
        amount: q.type === "special_price" ? q.requested_price : (q.amount ?? q.grand_total),
        requester: q.requested_by, role: q.required_role || "manager",
        at: q.requested_at, isSO: true,
      }));
      // ID SO yang punya approval khusus harga lewat SSOT (untuk dedup dgn price_approvals lama).
      const soPriceRefIds = new Set(arr(queueRes.data).filter((q) => q.type === "special_price").map((q) => q.ref_id));

      const pos = arr(poRes.data)
        .filter((p) => p.status === "waiting_approval")
        .map((p) => ({
          kind: "po", id: p.id, title: p.po_number, subtitle: p.supplier_name,
          meta: `${p.warehouse_name || ""} · ${p.items?.length || 0} item`,
          amount: p.total_amount, requester: p.created_by, role: p.required_approval_role,
          at: p.created_at, target: "purchase-approval",
        }));

      // Harga khusus STANDALONE saja (yang TIDAK tertaut SO) — yang tertaut SO tampil di grup Sales Order.
      const prices = arr(prRes.data)
        .filter((p) => !p.so_id && !soPriceRefIds.has(p.id))
        .map((p) => ({
          kind: "price", id: p.id, title: p.product_name || p.sku, subtitle: p.customer_name,
          meta: `${formatCurrency(p.normal_price)} → ${formatCurrency(p.requested_price)}${p.discount_percent ? ` (-${p.discount_percent}%)` : ""}`,
          amount: p.requested_price, requester: p.requested_by_name || p.requested_by, role: "manager",
          at: p.created_at, target: "price-approvals",
        }));

      const salesReturns = arr(srRes.data)
        .filter((r) => r.status === "pending_approval")
        .map((r) => ({
          kind: "sales_return", id: r.id, title: r.number, subtitle: r.customer_name || "Customer",
          meta: `Order ${r.order_number || "—"} · ${r.items?.length || 0} item`,
          amount: null, requester: r.created_by, role: "manager",
          at: r.created_at, target: "returns",
        }));

      const purchaseReturns = arr(purRes.data)
        .filter((r) => r.status === "pending_approval")
        .map((r) => ({
          kind: "purchase_return", id: r.id, title: r.number, subtitle: r.supplier_name || "Supplier",
          meta: `${r.po_number ? `dari ${r.po_number} · ` : ""}${r.items?.length || 0} item`,
          amount: r.total_amount, requester: r.created_by, role: "manager",
          at: r.created_at, target: "purchase-returns",
        }));

      const cycleCounts = arr(ccRes.data)
        .filter((s) => s.status === "submitted")
        .map((s) => ({
          kind: "cycle", id: s.id, title: s.name || "Cycle Count", subtitle: s.warehouse_name || "Gudang",
          meta: `${s.items?.length || 0} item dihitung`,
          amount: null, requester: s.submitted_by || s.created_by, role: "manager",
          at: s.submitted_at || s.created_at, target: "wms-cycle", targetView: "operations", targetTab: "cycle",
        }));

      const all = [...soApprovals, ...pos, ...prices, ...salesReturns, ...purchaseReturns, ...cycleCounts]
        .sort((a, b) => new Date(a.at || 0) - new Date(b.at || 0));
      // FASE G-1 — usulan koreksi angka dokumen yang menunggu keputusan.
      const amendments = arr(amdRes.data).map((a) => ({
        kind: "amendment", id: a.id, title: a.number,
        subtitle: `${a.doc_number || "Dokumen"} · ${a.reason_label || ""}`.trim(),
        meta: a.method_label || "",
        amount: Math.abs(Number(a.impact?.delta || 0)),
        requester: a.proposed_by, role: a.required_role || "manager",
        at: a.proposed_at, target: "sales-orders", targetView: "amendments",
      }));
      all.push(...amendments);
      all.sort((a, b) => new Date(a.at || 0) - new Date(b.at || 0));
      setItems(all);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat antrian persetujuan.");
    } finally {
      setLoading(false);
    }
  }

  const groupOf = (it) => KIND_META[it.kind]?.group;
  const counts = TABS.reduce((acc, t) => {
    acc[t.key] = t.key === "all" ? items.length : items.filter((i) => groupOf(i) === t.key).length;
    return acc;
  }, {});
  const filtered = items.filter((i) => tab === "all" || groupOf(i) === tab);
  /**
   * Berapa dari total antrean yang TIDAK diurus daftar layar ini (transfer gudang,
   * kontrabon, permintaan internal & retur antar-PT, tagihan supplier, biaya masuk,
   * uang muka, klaim makloon, buka periode, cuti, lembur, PR, spesifikasi/sample,
   * pesanan khusus, antar-PT di atas ambang). Angka ini yang dulu hilang: layar ini
   * berkata "tidak ada yang menunggu" sementara pekerjaan itu duduk di layar sebelah
   * tanpa satu pun petunjuk. FASE F-6 menambahkan DAFTAR dokumennya (bukan cuma angka).
   */
  const DITAMPILKAN_DI_SINI = ["sales_order", "purchase_order", "price", "sales_return",
                               "purchase_return", "cycle_count", "amendment"];
  const elsewhere = (backlog?.all_items || [])
    .filter((q) => !DITAMPILKAN_DI_SINI.includes(q.key))
    .reduce((s, q) => s + (q.count || 0), 0);
  //: dokumen NYATA dari antrean-antrean itu (paling lama menunggu lebih dulu).
  const othersOldest = (backlog?.oldest || [])
    .filter((o) => !DITAMPILKAN_DI_SINI.includes(o.key));

  const handleReview = (it) => {
    if (it.isSO && onOpenDocument) {
      onOpenDocument({ nav_id: "orders", view: "orders", focus_type: "sales_order", focus_id: it.orderId });
      return;
    }
    onNavigate?.(it.target, it.targetView, it.targetTab);
  };

  return (
    <div data-testid="approval-inbox-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="approval-inbox-error" />

      {unavailable.length > 0 && (
        <div className="notice-bar warning !py-1.5 mb-2" data-testid="approval-inbox-partial">
          <span className="text-[11.5px]">
            Daftar ini <strong>belum lengkap</strong>: {unavailable.length} kategori tidak
            bisa ditampilkan untuk peran Anda ({unavailable.join(", ")}). Angka di tab
            terkait karena itu bukan nol sungguhan.
          </span>
        </div>
      )}

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Inbox size={16} className="text-[#0058CC]" />
            <div className="min-w-0">
              <h2 data-testid="approval-inbox-title">Pusat Persetujuan</h2>
              <p className="text-[11px] text-[#6B6B73]">Semua persetujuan yang menunggu keputusan — daftar rinci untuk Pesanan Penjualan (nilai/kredit/harga), PO, retur, amandemen &amp; stock opname; antrean lain (transfer gudang, kontrabon, cuti, uang muka, …) tampil beserta nomor dokumen &amp; umur tunggunya.</p>
            </div>
          </div>
          <button data-testid="approval-inbox-refresh" onClick={load} className="secondary-button">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat Ulang
          </button>
        </div>
        <div className="section-body">
          {/* RINGKASAN SELURUH ANTREAN — angka yang sama dengan KPI beranda (INV-HOME-01).
              Yang tidak ditampilkan daftar di bawah tetap disebut di sini + jalannya. */}
          {backlog && (
            <div className="mb-3 rounded-lg border border-[#E4E9F2] bg-[#F8FAFD] p-3"
              data-testid="approval-inbox-backlog">
              <div className="flex items-center justify-between gap-2 mb-2">
                <p className="text-[12px] font-semibold text-[#3A3A3C]">
                  Menunggu keputusan (semua jenis):{" "}
                  <span className="tabular-nums text-[#0058CC]"
                    data-testid="approval-inbox-backlog-total">{backlog.total}</span>
                </p>
                {elsewhere > 0 && (
                  <span className="text-[11px] text-[#6B6B73]"
                    data-testid="approval-inbox-backlog-elsewhere">
                    {elsewhere} di antaranya ditangani di layar lain
                  </span>
                )}
              </div>
              {(backlog.items || []).length === 0 ? (
                <p className="text-[11.5px] text-[#6B6B73]" data-testid="approval-inbox-backlog-empty">
                  Tidak ada satu pun dokumen yang menunggu keputusan.
                </p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {(backlog.items || []).map((q) => {
                    const target = resolveDeepLinkTarget(q.view, currentUser?.role);
                    return (
                      <button key={q.key} type="button"
                        data-testid={`approval-inbox-backlog-${q.key}`}
                        disabled={!target}
                        title={target ? `Buka ${q.label}` : "Antrean ini bukan wilayah peran Anda"}
                        onClick={() => target && onNavigate?.(target.navId, target.view, target.tab)}
                        className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] ${
                          target
                            ? "border-[#CFDBEC] bg-white text-[#1C1C1E] hover:border-[#0058CC] hover:text-[#0058CC]"
                            : "border-[#E5E5EA] bg-[#F2F2F7] text-[#8E8E93] cursor-not-allowed"}`}>
                        <span className="truncate max-w-[15rem]">{q.label.replace(" menunggu ACC", "")}</span>
                        <span className="font-bold tabular-nums">{q.count}</span>
                        {target && <ArrowRight size={11} />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          <div className="tab-bar">
            {TABS.map((t) => (
              <button key={t.key} data-testid={`approval-inbox-tab-${t.key}`}
                className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                {t.label}<span className="tab-badge">{counts[t.key]}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── FASE F-6 — ANTREAN LAIN SEBAGAI DOKUMEN, BUKAN CUMA ANGKA ──────────────
          Sebelum ini "X di antaranya ditangani di layar lain" jujur tetapi tak bisa
          dikerjakan: orangnya tahu ADA pekerjaan, tanpa tahu MANA. Baris di bawah datang
          dari sumber yang sama dengan KPI beranda (`/approvals/backlog?oldest=15`) dan
          menyebut nomor dokumen + umur tunggu + jalan ke tempat keputusannya. */}
      {othersOldest.length > 0 && (
        <div className="section-card mb-3" data-testid="approval-inbox-others">
          <div className="section-head">
            <div className="flex items-center gap-2 min-w-0">
              <Clock size={15} className="text-[#B45309]" />
              <div className="min-w-0">
                <h2>Menunggu di layar lain — paling lama dulu</h2>
                <p className="text-[11px] text-[#6B6B73]">
                  Keputusan yang tempat kerjanya bukan daftar di bawah: transfer gudang,
                  kontrabon, permintaan internal &amp; retur antar-PT, tagihan supplier,
                  uang muka, klaim makloon, buka periode, cuti &amp; lembur.
                </p>
              </div>
            </div>
          </div>
          <div className="divide-y divide-[#EFF0F2]">
            {othersOldest.map((o) => {
              const target = resolveDeepLinkTarget(o.view, currentUser?.role);
              return (
                <div key={`${o.key}-${o.id}`} data-testid={`approval-inbox-other-${o.id}`}
                  className="flex items-center gap-3 px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[#FEF3C7] text-[#B45309]">
                    <Clock size={14} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-bold text-[#1C1C1E] truncate">{o.number}</span>
                      <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-[#F2F2F7] text-[#6B6B73]">
                        {o.queue_label.replace(" menunggu ACC", "")}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#6B6B73] truncate">{o.title || "—"}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-[11px] font-semibold tabular-nums text-[#B45309]">
                      {o.days_waiting === 0 ? "hari ini" : `menunggu ${o.days_waiting} hari`}
                    </p>
                    <button data-testid={`approval-inbox-other-open-${o.id}`}
                      disabled={!target}
                      title={target ? `Buka ${o.queue_label}` : "Antrean ini bukan wilayah peran Anda"}
                      onClick={() => target && onNavigate?.(target.navId, target.view, target.tab)}
                      className={`mt-1 inline-flex items-center gap-1 text-[11px] font-bold ${
                        target ? "text-[#0058CC] hover:underline" : "text-[#8E8E93] cursor-not-allowed"}`}>
                      Buka layarnya <ArrowRight size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="section-card">
        {loading ? (
          <div className="py-12 text-center text-[12px] text-[#6B6B73]">Memuat antrian persetujuan...</div>
        ) : filtered.length === 0 ? (
          <div className="py-14 text-center text-[12px] text-[#6B6B73]" data-testid="approval-inbox-empty">
            <CheckSquare className="mx-auto mb-2 text-gray-300" size={30} />
            <p className="font-semibold text-[#3C3C43]">Tidak ada yang menunggu persetujuan.</p>
            <p>Semua keputusan sudah ditindaklanjuti.</p>
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F2]">
            {filtered.map((it) => {
              const m = KIND_META[it.kind] || KIND_META.po;
              const Icon = m.icon;
              return (
                <div key={`${it.kind}-${it.id}`} data-testid={`approval-inbox-item-${it.id}`}
                  className="flex items-center gap-3 px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full"
                    style={{ background: m.bg, color: m.fg }}>
                    <Icon size={15} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-bold text-[#1C1C1E] truncate">{it.title}</span>
                      <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded"
                        style={{ background: m.bg, color: m.fg }}>
                        {m.label}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#6B6B73] truncate">{it.subtitle}{it.meta ? ` · ${it.meta}` : ""}</p>
                    <p className="text-[10px] text-[#9A9BA3] flex items-center gap-1 mt-0.5">
                      <Clock size={10} /> {timeAgo(it.at)} · diajukan {it.requester || "—"} · butuh <b className="uppercase">{it.role || "manager"}</b>
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    {it.amount != null && (
                      <p className="text-[13px] font-bold tabular-nums text-[#1C1C1E]">{formatCurrency(it.amount)}</p>
                    )}
                    <button data-testid={`approval-inbox-review-${it.id}`}
                      onClick={() => handleReview(it)}
                      className="mt-1 inline-flex items-center gap-1 text-[11px] font-bold text-[#0058CC] hover:underline">
                      Tinjau & Putuskan <ArrowRight size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
