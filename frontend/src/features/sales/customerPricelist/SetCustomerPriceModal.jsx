/**
 * SetCustomerPriceModal (F1b) — tetapkan harga langganan satu pelanggan × satu produk.
 *
 * Yang penting di layar ini: pengguna melihat **batas bawah** (harga PT / biaya pokok)
 * dan diberi tahu SEBELUM menyimpan bahwa harganya akan masuk antrean persetujuan.
 * Angka & alasannya diambil dari `/customer-prices/floor` — sumber yang SAMA dengan
 * keputusan server, jadi peringatan di layar tidak mungkin berbeda.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Save, ShieldAlert, Tag, TrendingUp, X } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { formatCurrency, formatQty } from "../../../utils/formatters";

export default function SetCustomerPriceModal({
  row, customer, entityId, onClose, onSaved, onError,
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [price, setPrice] = useState(row.customer_price != null ? String(row.customer_price) : "");
  const [validFrom, setValidFrom] = useState(today);
  const [validUntil, setValidUntil] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [floor, setFloor] = useState(null);
  const [checking, setChecking] = useState(false);

  const numPrice = Number(String(price).replace(/[^\d.,-]/g, "").replace(",", "."));

  const checkFloor = useCallback(async (value) => {
    setChecking(true);
    try {
      const params = { product_id: row.product_id, entity_id: entityId };
      if (value > 0) params.price = value;
      const res = await axios.get(`${API}/customer-prices/floor`, { params });
      setFloor(res.data || null);
    } catch {
      setFloor(null);
    } finally {
      setChecking(false);
    }
  }, [row.product_id, entityId]);

  useEffect(() => { checkFloor(0); }, [checkFloor]);
  useEffect(() => {
    if (!(numPrice > 0)) return undefined;
    const t = setTimeout(() => checkFloor(numPrice), 400);
    return () => clearTimeout(t);
  }, [numPrice, checkFloor]);

  const willNeedApproval = !!(floor && numPrice > 0 && floor.needs_approval);
  const belowNoGuard = !!(floor && numPrice > 0 && floor.below_floor && !floor.needs_approval);

  const save = async () => {
    if (!(numPrice > 0)) { onError("Harga jual harus lebih dari 0."); return; }
    setSaving(true);
    try {
      const res = await axios.post(`${API}/customer-prices`, {
        customer_id: customer.id, product_id: row.product_id, sell_price: numPrice,
        entity_id: entityId, valid_from: validFrom, valid_until: validUntil, note,
      });
      onSaved(res.data);
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal menyimpan harga pelanggan.");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4"
      data-testid="cpl-setprice-modal">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-xl">
        <div className="flex items-center gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <Tag size={16} className="text-[#0058CC]" />
          <h3 className="truncate text-[14px] font-bold">Harga Langganan · {customer.name}</h3>
          <button data-testid="cpl-setprice-close" className="icon-button ml-auto" onClick={onClose}
            aria-label="Tutup"><X size={15} /></button>
        </div>

        <div className="space-y-3 p-4 text-[12px]">
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2">
            <p className="font-semibold text-[#1C1C1E]">{row.product_name}</p>
            <p className="text-[11px] text-[#9A9BA3]">
              {row.sku} · harga umum {formatCurrency(row.global_price)}/{row.base_unit}
              {row.entity_price != null && <> · harga PT {formatCurrency(row.entity_price)}</>}
            </p>
          </div>

          {floor && (
            <div data-testid="cpl-floor-info"
              className="grid grid-cols-3 gap-2 rounded-md border border-[#E5E5EA] px-3 py-2">
              <Fact label="Batas bawah" value={floor.floor > 0 ? formatCurrency(floor.floor) : "—"}
                tone="#0058CC" testId="cpl-floor-value" />
              <Fact label="Biaya pokok (HPP)"
                value={floor.hpp > 0 ? formatCurrency(floor.hpp) : "belum ada"} />
              <Fact label="Dasar batas" value={floor.basis_label} small />
            </div>
          )}

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Harga Langganan (per {row.base_unit})
            </label>
            <input data-testid="cpl-input-price" type="number" className="field py-2 text-[13px]"
              placeholder="Mis. 165000" value={price} onChange={(e) => setPrice(e.target.value)}
              autoFocus />
            {checking && <p className="mt-1 text-[10.5px] text-[#8E8E93]">Memeriksa batas bawah…</p>}
          </div>

          {willNeedApproval && (
            <div data-testid="cpl-approval-warning"
              className="rounded-md border border-[#F3D7A0] bg-[#FFF6E5] px-3 py-2 text-[11.5px] text-[#8C4A00]">
              <p className="flex items-center gap-1.5 font-bold">
                <ShieldAlert size={13} /> Harga ini butuh persetujuan manajer
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {(floor.reasons || []).map((rs, i) => <li key={i}>{rs}</li>)}
              </ul>
              <p className="mt-1">
                Setelah disimpan, harga <b>belum berlaku</b>. Pengajuan otomatis muncul di
                {" "}<b>Pusat Persetujuan › Persetujuan Harga</b> memakai alur Harga Khusus
                yang sudah ada. Yang boleh memutuskan: <b>manajer atau admin selain Anda</b>
                {" "}(pemisahan tugas).
              </p>
            </div>
          )}
          {belowNoGuard && (
            <div data-testid="cpl-below-noguard"
              className="rounded-md border border-[#F3D7A0] bg-[#FFFBF0] px-3 py-2 text-[11.5px] text-[#8C4A00]">
              <p className="flex items-center gap-1.5 font-bold">
                <AlertTriangle size={13} /> Di bawah batas, tetapi penjagaan sedang dimatikan
              </p>
              <p className="mt-0.5">Harga akan langsung berlaku. {floor.summary}</p>
            </div>
          )}
          {floor && numPrice > 0 && !floor.below_floor && (
            <p data-testid="cpl-price-ok"
              className="flex items-center gap-1.5 text-[11.5px] text-[#1B7F4B]">
              <TrendingUp size={13} /> Aman — langsung berlaku.
              {floor.margin_pct != null && <> Margin terhadap HPP {formatQty(floor.margin_pct)}%.</>}
            </p>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Berlaku Mulai</label>
              <input data-testid="cpl-input-from" type="date" className="field py-2 text-[13px]"
                value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Berlaku Sampai <span className="font-normal text-[#9A9BA3]">(opsional)</span>
              </label>
              <input data-testid="cpl-input-until" type="date" className="field py-2 text-[13px]"
                value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Catatan <span className="font-normal text-[#9A9BA3]">(opsional)</span>
            </label>
            <input data-testid="cpl-input-note" className="field py-2 text-[13px]"
              placeholder="Mis. kesepakatan kontrak 2026" value={note}
              onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="btn-secondary px-4 py-1.5 text-[12px]" onClick={onClose}>Batal</button>
          <button data-testid="cpl-setprice-save" onClick={save} disabled={saving}
            className="btn-primary inline-flex items-center gap-1 px-4 py-1.5 text-[12px] disabled:opacity-50">
            <Save size={14} />
            {saving ? "Menyimpan…" : willNeedApproval ? "Simpan & Ajukan" : "Simpan Harga"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Fact({ label, value, tone = "#1C1C1E", small = false, testId }) {
  return (
    <div data-testid={testId}>
      <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
      <p className={`${small ? "text-[11px]" : "text-[13px]"} font-bold tabular-nums`}
        style={{ color: tone }}>{value}</p>
    </div>
  );
}
