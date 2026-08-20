/**
 * RestockPanel (PS-21a) — status **pendingan** + aksi **Repeat/Restock 1 klik**.
 *
 * Masalah yang dijawab (KN_18 §A.3 PS-21): sales tahu barang tidak ready tetapi
 * harus pindah modul & mengetik ulang untuk minta pengadaan, dan status pendingan
 * tidak terlihat. Panel ini menyatukan ketiganya di layar order:
 *   1) daftar PENDINGAN (backorder) + stok yang sudah tersedia,
 *   2) pilih item → 1 klik → **PR** dibuat (jalur PR → PO) + MD dinotifikasi,
 *   3) riwayat permintaan (nomor PR + status) supaya tidak minta dua kali.
 *
 * Props: order, currentUser, onNavigate(view), onChanged()
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { PackagePlus, RefreshCw, Send, ShoppingCart, X } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { can } from "../../config/roles";
import DecimalInput from "../../components/DecimalInput";
import { parseDecimal, toDecimalText } from "../../utils/decimalInput";
import { formatCurrency, formatQty } from "../../utils/formatters";

const PR_TONE = {
  draft: "pill-muted",
  pending_approval: "pill-warning",
  approved: "pill-success",
  converted: "pill-info",
  rejected: "pill-danger",
  cancelled: "pill-muted",
};
const PR_LABEL = {
  draft: "Draft",
  pending_approval: "Menunggu persetujuan",
  approved: "Disetujui",
  converted: "Jadi PO",
  rejected: "Ditolak",
  cancelled: "Dibatalkan",
};
const BO_LABEL = {
  waiting_stock: "Menunggu stok",
  partial: "Terpenuhi sebagian",
  fulfilled: "Sudah terpenuhi",
};

export default function RestockPanel({ order, currentUser, onNavigate, onChanged }) {
  const orderId = order?.id;
  // FASE E-8 (E8.1) — wewenang dari IZIN, bukan daftar peran. `sales_admin` adalah
  // pemilik keputusan pemenuhan (E8.10b#4) sehingga dia WAJIB punya tombol ini;
  // dengan daftar peran lama dia justru satu-satunya yang tidak punya.
  const perms = currentUser?.permissions || {};
  // Endpoint `repeat-restock` dipagari `order.update` di server — jadi itulah izin
  // yang harus dipakai layar. (Memakai `purchase_requisition.create` di sini akan
  // MENYEMBUNYIKAN tombol dari sales yang justru berhak memakainya.)
  const canRequest = can(perms, "order", "update");
  // Layar PR hanya bisa dibuka oleh yang menu-nya memuatnya; kalau tidak, nomor PR
  // ditampilkan sebagai teks agar tidak mengarahkan ke layar yang gagal dibuka.
  const canOpenPR = can(perms, "purchase_requisition", "view");

  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [picked, setPicked] = useState({});   // product_id → { on, qty }

  const load = useCallback(async () => {
    if (!orderId) return;
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/sales-orders/${orderId}/restock-state`);
      setState(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat status pendingan & restock.");
    } finally { setLoading(false); }
  }, [orderId]);

  useEffect(() => { load(); }, [load]);

  const candidates = useMemo(
    () => (Array.isArray(state?.candidates) ? state.candidates : []), [state]);
  const pendingan = useMemo(
    () => (Array.isArray(state?.pendingan) ? state.pendingan : []), [state]);
  const riwayat = useMemo(
    () => (Array.isArray(state?.restock_requests) ? state.restock_requests : []), [state]);
  const prMap = useMemo(() => {
    const m = {};
    (state?.purchase_requisitions || []).forEach((p) => { m[p.number] = p.status; });
    return m;
  }, [state]);
  const lockedRows = useMemo(
    () => candidates.filter((c) => Boolean(c.open_pr_number)), [candidates]);
  const allLocked = candidates.length > 0 && lockedRows.length === candidates.length;

  function openModal() {
    const next = {};
    candidates.forEach((c) => {
      if (!c.open_pr_number) {
        next[c.product_id] = {
          on: Number(c.backorder_qty) > 0,
          qty: toDecimalText(c.suggest_qty || c.backorder_qty || c.ordered_qty || 0),
        };
      }
    });
    setPicked(next);
    setReason("");
    setError("");
    setOpen(true);
  }

  const chosen = Object.entries(picked)
    .filter(([, v]) => v?.on && parseDecimal(v.qty) > 0)
    .map(([pid, v]) => ({ product_id: pid, quantity: v.qty }));

  const estimasi = chosen.reduce((sum, it) => {
    const c = candidates.find((x) => x.product_id === it.product_id);
    return sum + parseDecimal(it.quantity) * Number(c?.est_price || 0);
  }, 0);

  async function submit() {
    setBusy(true); setError(""); setOkMsg("");
    try {
      const res = await axios.post(`${API}/sales-orders/${orderId}/repeat-restock`, {
        items: chosen.map((it) => ({ ...it, note: "" })),
        reason,
      });
      setOkMsg(res.data?.message || "Permintaan restock terkirim.");
      setOpen(false);
      await load();
      if (onChanged) onChanged();
    } catch (e) {
      setError(e.response?.data?.detail || "Permintaan restock gagal dibuat.");
    } finally { setBusy(false); }
  }

  if (!orderId) return null;

  return (
    <div data-testid="restock-panel" className="rounded-md border border-[#EFF0F2] overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
        <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          <PackagePlus size={12} /> Pendingan & Repeat/Restock
        </span>
        <div className="flex items-center gap-1">
          <button data-testid="restock-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
            <RefreshCw size={12} />
          </button>
          {canRequest && (
            <button data-testid="restock-open" className="primary-button !px-2 !py-1 !text-[10.5px]"
              onClick={openModal} disabled={loading || candidates.length === 0}>
              Minta Repeat/Restock
            </button>
          )}
        </div>
      </div>

      <div className="space-y-2 px-2.5 py-2">
        {error && (
          <div className="notice-bar danger" data-testid="restock-error">
            <span>{error}</span><button onClick={() => setError("")}>×</button>
          </div>
        )}
        {okMsg && (
          <div className="notice-bar" data-testid="restock-success">
            <span>{okMsg}</span><button onClick={() => setOkMsg("")}>×</button>
          </div>
        )}
        {loading && <p data-testid="restock-loading" className="text-[11px] text-[#6B6B73]">Memuat…</p>}

        {!loading && pendingan.length === 0 && (
          <p data-testid="restock-no-pendingan" className="text-[11px] text-[#6B6B73]">
            Tidak ada barang pendingan pada pesanan ini. Anda tetap bisa meminta
            <b> repeat/restock</b> bila pelanggan ingin pesan ulang.
          </p>
        )}

        {pendingan.map((b) => {
          const siap = Number(b.available_qty) > 0 && Number(b.backorder_qty) > 0;
          return (
            <div key={b.product_id} data-testid={`restock-pendingan-${b.product_id}`}
              className="rounded border border-[#F5C9A6] bg-[#FFF7EF] px-2 py-1.5">
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <span className="truncate text-[11px] font-semibold text-[#1C1C1E]">
                  {b.product_name || b.sku}
                </span>
                <span className={`status-pill ${siap ? "pill-success" : "pill-warning"}`}>
                  {siap ? "Stok tersedia — siap dialokasikan" : (BO_LABEL[b.status] || b.status)}
                </span>
              </div>
              <div className="mt-0.5 flex flex-wrap gap-3 text-[10.5px] tabular-nums text-[#8C4A00]">
                <span>Diminta {formatQty(b.requested_qty)}</span>
                <span className="text-[#126E2C]">Ter-reservasi {formatQty(b.reserved_qty)}</span>
                <span className="font-bold">Pendingan {formatQty(b.backorder_qty)}</span>
                <span>Stok gudang {formatQty(b.available_qty)}</span>
              </div>
            </div>
          );
        })}

        {riwayat.length > 0 && (
          <div data-testid="restock-history" className="rounded border border-[#EFF0F2] bg-white">
            <p className="border-b border-[#EFF0F2] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
              Riwayat Permintaan Pengadaan
            </p>
            <div className="divide-y divide-[#F2F3F5]">
              {riwayat.slice().reverse().map((r, i) => {
                const st = prMap[r.pr_number] || r.status;
                return (
                  <div key={r.pr_id || i} data-testid={`restock-history-${r.pr_number}`}
                    className="px-2 py-1.5 text-[10.5px]">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {canOpenPR ? (
                        <button className="font-mono text-[10.5px] font-semibold text-[#0058CC] underline decoration-dotted"
                          data-testid={`restock-open-pr-${r.pr_number}`}
                          onClick={() => onNavigate && onNavigate({ view: "purchase-requisitions" })}>
                          {r.pr_number}
                        </button>
                      ) : (
                        <span data-testid={`restock-pr-${r.pr_number}`}
                          className="font-mono text-[10.5px] font-semibold text-[#1C1C1E]">
                          {r.pr_number}
                        </span>
                      )}
                      <span className={`status-pill ${PR_TONE[st] || "pill-muted"}`}>
                        {PR_LABEL[st] || st}
                      </span>
                      <span className="ml-auto text-[#8E8E93]">
                        {r.requested_at ? new Date(r.requested_at).toLocaleString("id-ID") : ""}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[#3C3C43]">
                      {(r.items || []).map((it) => `${it.product_name} ${formatQty(it.quantity)} ${it.unit}`).join(" · ")}
                      {" · est "}{formatCurrency(r.total_est_amount)}
                      {r.requested_by ? ` · oleh ${r.requested_by}` : ""}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {open && (
        <div className="modal-overlay" data-testid="restock-modal">
          <div className="modal-card wide">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="modal-title">Minta Repeat/Restock — {state?.number}</p>
                <p className="modal-subtitle">
                  Sistem membuat <b>Permintaan Pembelian</b> (jalur PR → PO) dan memberi tahu
                  MD/manager. Barang yang belum tersedia tetap tercatat sebagai pendingan.
                </p>
              </div>
              <button data-testid="restock-modal-close" className="icon-button"
                onClick={() => setOpen(false)} aria-label="Tutup"><X size={15} /></button>
            </div>

            {error && (
              <div className="notice-bar danger" data-testid="restock-modal-error">
                <span>{error}</span><button onClick={() => setError("")}>×</button>
              </div>
            )}

            {lockedRows.length > 0 && (
              <div data-testid="restock-locked-note"
                className="mt-2 rounded-md border border-[#FFE2B8] bg-[#FFF8EE] px-2.5 py-2 text-[10.5px] text-[#8C4A00]">
                <b>{lockedRows.length} produk terkunci</b> karena sudah punya permintaan pengadaan
                terbuka:{" "}
                {lockedRows.map((c) => `${c.product_name || c.sku} (${c.open_pr_number})`).join(", ")}.
                {" "}Selesaikan atau batalkan PR tersebut dulu agar tidak dobel.
              </div>
            )}
            {allLocked && (
              <div data-testid="restock-all-locked" className="notice-bar mt-2">
                <span>
                  Semua produk pada pesanan ini sudah diminta. Buka layar <b>Permintaan Pembelian</b>
                  {" "}untuk memantau atau membatalkan permintaan yang masih terbuka.
                </span>
              </div>
            )}

            <div className="mt-2 overflow-hidden rounded-md border border-[#EFF0F2]">
              <div className="grid grid-cols-[32px_1fr_110px_110px_150px] gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[9.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
                <span />
                <span>Produk</span>
                <span className="text-right">Stok gudang</span>
                <span className="text-right">Pendingan</span>
                <span className="text-right">Qty dibeli</span>
              </div>
              {candidates.map((c) => {
                const row = picked[c.product_id] || { on: false, qty: "" };
                const locked = Boolean(c.open_pr_number);
                return (
                  <div key={c.product_id} data-testid={`restock-row-${c.product_id}`}
                    className={`grid grid-cols-[32px_1fr_110px_110px_150px] items-center gap-2 border-b border-[#F2F3F5] px-2.5 py-2 last:border-0 ${locked ? "bg-[#FCFCFD]" : ""}`}>
                    <input type="checkbox" data-testid={`restock-check-${c.product_id}`}
                      className="h-3.5 w-3.5"
                      title={locked
                        ? `Sudah ada permintaan terbuka ${c.open_pr_number}`
                        : "Pilih untuk diminta"}
                      checked={Boolean(row.on)} disabled={locked}
                      onChange={(e) => setPicked((p) => ({
                        ...p,
                        [c.product_id]: {
                          qty: p[c.product_id]?.qty || toDecimalText(c.suggest_qty || 0),
                          on: e.target.checked,
                        },
                      }))} />
                    <div className="min-w-0">
                      <p className="truncate text-[11.5px] font-semibold text-[#1C1C1E]">
                        {c.product_name || c.sku}
                      </p>
                      <p className="truncate text-[10px] text-[#8E8E93]">
                        {c.sku}{c.est_price ? ` · est ${formatCurrency(c.est_price)}/${c.unit}` : ""}
                      </p>
                      {locked && (
                        <p className="mt-0.5 text-[10px] font-semibold text-[#B23B14]">
                          sudah ada {c.open_pr_number} ({PR_LABEL[c.open_pr_status] || c.open_pr_status})
                        </p>
                      )}
                    </div>
                    <span className="text-right text-[11px] tabular-nums text-[#126E2C]">
                      {formatQty(c.available_qty)} {c.unit}
                    </span>
                    <span className="text-right text-[11px] tabular-nums font-semibold text-[#B23B14]">
                      {formatQty(c.backorder_qty)} {c.unit}
                    </span>
                    <DecimalInput data-testid={`restock-qty-${c.product_id}`}
                      className="field !py-1 !text-[11px]" suffix={c.unit}
                      disabled={locked || !row.on} min={0}
                      value={row.qty}
                      onChange={(v) => setPicked((p) => ({
                        ...p, [c.product_id]: { on: true, qty: v },
                      }))} />
                  </div>
                );
              })}
              {candidates.length === 0 && (
                <p data-testid="restock-no-candidate" className="px-2 py-2 text-[11px] text-[#6B6B73]">
                  Tidak ada produk yang bisa diminta dari pesanan ini.
                </p>
              )}
            </div>

            <div className="mt-2 grid gap-2">
              <input data-testid="restock-reason" className="field"
                placeholder="Alasan / catatan untuk MD (opsional) — mis. pelanggan minta repeat 2 roll"
                value={reason} onChange={(e) => setReason(e.target.value)} />
              <p className="text-[10.5px] text-[#6B6B73]">
                {chosen.length} item dipilih · estimasi nilai <b>{formatCurrency(estimasi)}</b>
                {" "}· PR akan langsung diajukan sesuai matriks persetujuan.
              </p>
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setOpen(false)}>Batal</button>
              <button data-testid="restock-submit" className="primary-button"
                disabled={busy || chosen.length === 0} onClick={submit}>
                {busy ? "Mengirim…" : (
                  <span className="flex items-center gap-1"><Send size={12} /> Buat PR & beri tahu MD</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {!canRequest && !loading && (
        <p data-testid="restock-readonly" className="border-t border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[10.5px] text-[#6B6B73]">
          <ShoppingCart size={11} className="mr-1 inline" />
          Hanya sales/manager/admin yang dapat membuat permintaan repeat/restock.
        </p>
      )}
    </div>
  );
}
