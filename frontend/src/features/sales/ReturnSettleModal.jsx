/** R1/R3 — Modal penyelesaian retur (settle). inspected → refund/credit/nego settled.
 *  Empat outcome + partial per item (kecualikan item / sebagian qty).
 *  R3 — untuk outcome yang mengembalikan barang ke stok (refund/store_credit),
 *  user memilih LOKASI gudang penerimaan (return_warehouse_id). Kepemilikan (owner)
 *  tetap = entitas SO agar rekonsiliasi subledger↔GL persediaan aman; perpindahan
 *  kepemilikan lintas-PT dilakukan via aksi "Transfer Kepemilikan" di panel karantina. */
import { useState, useEffect } from "react";
import axios, { API } from "../../services/apiClient";
import { CheckCircle2, Loader2, X, Wallet, Coins, Percent, Warehouse, Info } from "lucide-react";
import { fmtNum } from "./ReturnShared";
import KNSelect from "../../components/KNSelect";

const OUTCOMES = [
  { value: "refund", label: "Pengembalian Dana", desc: "Kembalikan dana (tunai/piutang) + barang masuk stok", icon: Wallet },
  { value: "store_credit", label: "Store Credit", desc: "Tambah saldo pelanggan (potong bon) + barang masuk stok", icon: Coins },
  { value: "nego", label: "Nego (Diskon)", desc: "Nota Kredit diskon tanpa gerak stok", icon: Percent },
];

export default function ReturnSettleModal({ ret, open, onClose, onSettle }) {
  const [outcome, setOutcome] = useState("refund");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [warehouses, setWarehouses] = useState([]);
  const [returnWarehouseId, setReturnWarehouseId] = useState("");
  const [cashAccounts, setCashAccounts] = useState([]);
  const [refundAccount, setRefundAccount] = useState("");
  const [decisions, setDecisions] = useState(() =>
    (ret.items || []).map((it) => ({ include: true, settle_qty: it.quantity_returned ?? 0 })));

  // R3 — daftar gudang; R5.3 — daftar akun Kas/Bank untuk refund tunai
  useEffect(() => {
    if (!open) return;
    let active = true;
    (async () => {
      try {
        const res = await axios.get(`${API}/warehouses`);
        const list = Array.isArray(res.data) ? res.data : (res.data?.items || []);
        if (active) setWarehouses(list);
      } catch { if (active) setWarehouses([]); }
      try {
        const res2 = await axios.get(`${API}/gl/cash-accounts`);
        if (active) setCashAccounts(Array.isArray(res2.data) ? res2.data : []);
      } catch { if (active) setCashAccounts([]); }
    })();
    return () => { active = false; };
  }, [open]);

  if (!open) return null;
  const upd = (i, patch) => setDecisions((d) => d.map((x, idx) => (idx === i ? { ...x, ...patch } : x)));
  const movesStock = outcome === "refund" || outcome === "store_credit";

  async function confirm() {
    setBusy(true);
    try {
      const item_decisions = decisions.map((d, i) => ({
        index: i,
        outcome: d.include ? "" : "reject",
        settle_qty: d.include ? (parseFloat(d.settle_qty) || 0) : -1,
      }));
      await onSettle(ret, outcome, item_decisions, notes, movesStock ? returnWarehouseId : "",
                     outcome === "refund" ? refundAccount : "");
      onClose();
    } finally { setBusy(false); }
  }

  const anyIncluded = decisions.some((d) => d.include && (parseFloat(d.settle_qty) || 0) > 0);
  const ownerName = ret.entity_short_name || ret.entity_name || ret.entity_id || "entitas SO";

  return (
    <div className="modal-overlay" data-testid="settle-modal">
      <div className="modal-card" style={{ maxWidth: 640 }}>
        <div className="flex items-center justify-between mb-1">
          <h3 className="modal-title">Selesaikan Retur {ret.number}</h3>
          <button className="icon-button" onClick={onClose}><X size={15} /></button>
        </div>
        <p className="modal-subtitle">Pilih outcome & item yang diselesaikan (bisa sebagian / kecualikan item).</p>

        {/* Outcome selector */}
        <div className="grid grid-cols-3 gap-2 my-3">
          {OUTCOMES.map((o) => {
            const Icon = o.icon; const active = outcome === o.value;
            return (
              <button key={o.value} type="button" data-testid={`settle-outcome-${o.value}`}
                onClick={() => setOutcome(o.value)}
                className={`text-left rounded-md border p-2.5 transition ${active
                  ? "border-[#0058CC] bg-[#EAF2FF]" : "border-[#EFF0F2] bg-white hover:border-[#C9CDD4]"}`}>
                <div className="flex items-center gap-1.5 font-semibold text-[12px]">
                  <Icon size={13} className={active ? "text-[#0058CC]" : "text-[#6B6B73]"} /> {o.label}
                </div>
                <div className="text-[10px] text-[#6B6B73] mt-1 leading-snug">{o.desc}</div>
              </button>
            );
          })}
        </div>

        {/* R3 — Lokasi gudang penerimaan (owner tetap = entitas SO) */}
        {movesStock && (
          <div className="rounded-md border border-[#E4ECF7] bg-[#F6FAFF] p-2.5 mb-3" data-testid="settle-destination">
            <label className="flex items-center gap-1.5 text-[12px] font-semibold text-[#1B4F9C] mb-1.5">
              <Warehouse size={13} /> Lokasi Gudang Penerimaan Retur
            </label>
            <KNSelect className="field w-full" data-testid="settle-return-warehouse"
              value={returnWarehouseId} onValueChange={setReturnWarehouseId}
              aria-label="Gudang tujuan roll retur"
              placeholder="Default cerdas (gudang pengiriman SO)"
              options={[
                { value: "", label: "Default cerdas (gudang pengiriman SO)" },
                ...warehouses.map((w) => ({
                  value: w.id,
                  label: `${w.name || w.code || w.id}${w.city ? ` — ${w.city}` : ""}`,
                })),
              ]} />
            <div className="flex items-start gap-1 text-[10.5px] text-[#5B6472] mt-1.5 leading-snug">
              <Info size={12} className="mt-[1px] shrink-0" />
              <span>Roll retur masuk <b>karantina</b> di lokasi ini. Kepemilikan tetap pada <b>{ownerName}</b>;
                pindah kepemilikan lintas-PT dilakukan setelah release via aksi <b>Transfer Kepemilikan</b>.</span>
            </div>
          </div>
        )}

        {/* R5.3 — Akun Kas/Bank untuk refund TUNAI (hanya relevan bila order dibayar tunai) */}
        {outcome === "refund" && (
          <div className="rounded-md border border-[#E7E1F5] bg-[#F8F5FE] p-2.5 mb-3" data-testid="settle-refund-account-box">
            <label className="flex items-center gap-1.5 text-[12px] font-semibold text-[#6B219A] mb-1.5">
              <Coins size={13} /> Akun Kas/Bank Pengembalian Dana Tunai
            </label>
            <KNSelect className="field w-full" data-testid="settle-refund-account"
              value={refundAccount} onValueChange={setRefundAccount}
              aria-label="Akun kas/bank untuk pengembalian dana tunai"
              placeholder="Default — 1-1100 Kas Besar / Bank"
              options={[
                { value: "", label: "Default — 1-1100 Kas Besar / Bank" },
                ...cashAccounts.map((a) => ({ value: a.code, label: `${a.code} — ${a.name}` })),
              ]} />
            <div className="flex items-start gap-1 text-[10.5px] text-[#5B6472] mt-1.5 leading-snug">
              <Info size={12} className="mt-[1px] shrink-0" />
              <span>Berlaku bila retur berasal dari penjualan <b>tunai</b> → dana keluar dari akun ini &
                tercatat sebagai <b>kas keluar</b>. Penjualan kredit otomatis mengurangi piutang (tanpa kas).</span>
            </div>
          </div>
        )}

        {/* Per-item decisions */}
        <div className="section-card" style={{ margin: 0 }}>
          <table className="data-table">
            <thead>
              <tr><th>Sertakan</th><th>Produk</th><th>Qty Retur</th><th>Qty Diselesaikan</th></tr>
            </thead>
            <tbody>
              {(ret.items || []).map((it, i) => (
                <tr key={i} data-testid={`settle-item-${i}`}>
                  <td>
                    <input type="checkbox" data-testid={`settle-include-${i}`}
                      checked={decisions[i].include} onChange={(e) => upd(i, { include: e.target.checked })} />
                  </td>
                  <td>{it.product_name || it.product_id}</td>
                  <td className="font-mono">{fmtNum(it.quantity_returned)} {it.unit}</td>
                  <td style={{ maxWidth: 110 }}>
                    <input data-testid={`settle-qty-${i}`} type="number" min="0" max={it.quantity_returned}
                      className="field tabular-nums" disabled={!decisions[i].include}
                      value={decisions[i].settle_qty} onChange={(e) => upd(i, { settle_qty: e.target.value })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <textarea data-testid="settle-notes" className="textarea mt-3" rows={2}
          placeholder="Catatan penyelesaian (opsional)..." value={notes} onChange={(e) => setNotes(e.target.value)} />

        <p className="mt-2 text-[10.5px] text-[#5B6472]" data-testid="settle-cost-basis-note">
          Basis nilai barang kembali (pembalikan HPP ke stok) = <b>WAC</b> produk yang sudah
          <b> termasuk landed cost</b> (freight/duty/handling) untuk barang impor — bukan harga PO mentah.
        </p>

        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button data-testid="confirm-settle-btn" className="primary-button" disabled={busy || !anyIncluded}
            onClick={confirm}>
            {busy ? <Loader2 size={13} className="spin" /> : <CheckCircle2 size={13} />} Selesaikan ({outcome})
          </button>
        </div>
      </div>
    </div>
  );
}
