/**
 * ReturnPolicyEditor (R0) — editor kebijakan retur SUPPLIER (embedded di form supplier).
 * Controlled: `value` = objek return_policy, `onChange(next)` dipanggil tiap perubahan.
 * Mendukung custom_fields extensible (user tambah aturan sendiri — keputusan owner #6).
 */
import { useState, useEffect } from "react";
import { Plus, Trash2, ShieldCheck } from "lucide-react";

const REFUND_MODES = [
  { value: "ap_credit", label: "Potong Bon (Kredit AP)" },
  { value: "cash", label: "Pengembalian Dana Tunai" },
  { value: "none", label: "Tanpa Pengembalian Dana" },
];

const DEFAULTS = {
  window_days: 30,
  refund_modes: ["ap_credit"],
  returnable_to_supplier: true,
  rma_required: false,
  restocking_fee_pct: 0,
  condition_requirements: "",
  custom_fields: {},
  notes: "",
};

export function ReturnPolicyEditor({ value, onChange, isImport = false }) {
  const p = { ...DEFAULTS, ...(value || {}) };
  // Baris custom_fields lokal (key/value) — disinkron ke objek saat berubah.
  const [rows, setRows] = useState(() =>
    Object.entries(p.custom_fields || {}).map(([k, v]) => ({ k, v: String(v) })));

  // Sinkron ulang bila value.custom_fields berubah dari luar (mis. buka edit).
  useEffect(() => {
    setRows(Object.entries((value || {}).custom_fields || {}).map(([k, v]) => ({ k, v: String(v) })));
  }, [value?.custom_fields]); // eslint-disable-line

  const set = (patch) => onChange({ ...p, ...patch });

  const toggleMode = (m) => {
    const cur = Array.isArray(p.refund_modes) ? p.refund_modes : [];
    const next = cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m];
    set({ refund_modes: next });
  };

  const syncRows = (nextRows) => {
    setRows(nextRows);
    const obj = {};
    nextRows.forEach(({ k, v }) => { if (k.trim()) obj[k.trim()] = v; });
    set({ custom_fields: obj });
  };

  return (
    <div data-testid="return-policy-editor" className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3 space-y-3">
      <div className="flex items-center gap-2">
        <ShieldCheck size={14} className="text-[#0058CC]" />
        <span className="text-[12px] font-bold text-[#1A1A1F]">Kebijakan Retur ke Supplier</span>
      </div>

      {isImport && (
        <div className="text-[10.5px] text-[#6B219A] bg-[#F5EDFB] rounded px-2 py-1">
          Barang <b>impor</b>: bila "Bisa diretur ke supplier" dimatikan, sistem akan
          mengarahkan barang cacat ke <b>regrade + jual lokal</b> (bukan retur ke luar negeri).
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Jendela Retur (hari)</label>
          <input data-testid="rp-window-days" type="number" min="0" className="field"
            value={p.window_days}
            onChange={(e) => set({ window_days: parseInt(e.target.value, 10) || 0 })} placeholder="mis. 30" />
        </div>
        <div>
          <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Biaya Restocking (%)</label>
          <input data-testid="rp-restocking-fee" type="number" min="0" max="100" step="0.1" className="field tabular-nums"
            value={p.restocking_fee_pct}
            onChange={(e) => set({ restocking_fee_pct: Math.max(0, Math.min(100, parseFloat(e.target.value) || 0)) })} placeholder="0" />
        </div>
      </div>

      <div>
        <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1.5">Mode Pengembalian Dana yang Diizinkan</label>
        <div className="flex flex-wrap gap-3">
          {REFUND_MODES.map((m) => (
            <label key={m.value} className="flex items-center gap-1.5 text-[11px] cursor-pointer" data-testid={`rp-mode-${m.value}-label`}>
              <input type="checkbox" data-testid={`rp-mode-${m.value}`}
                checked={(p.refund_modes || []).includes(m.value)}
                onChange={() => toggleMode(m.value)} />
              {m.label}
            </label>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-1.5 text-[11px] cursor-pointer">
          <input type="checkbox" data-testid="rp-returnable"
            checked={!!p.returnable_to_supplier}
            onChange={(e) => set({ returnable_to_supplier: e.target.checked })} />
          Bisa diretur ke supplier
        </label>
        <label className="flex items-center gap-1.5 text-[11px] cursor-pointer">
          <input type="checkbox" data-testid="rp-rma-required"
            checked={!!p.rma_required}
            onChange={(e) => set({ rma_required: e.target.checked })} />
          Wajib nomor RMA
        </label>
      </div>

      <div>
        <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Syarat Kondisi Barang</label>
        <input data-testid="rp-condition" className="field" value={p.condition_requirements}
          onChange={(e) => set({ condition_requirements: e.target.value })}
          placeholder="mis. Kemasan asli, belum dipotong" />
      </div>

      {/* Custom fields extensible */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-[10.5px] font-semibold text-[#6B6B73]">Field Tambahan (custom)</label>
          <button type="button" data-testid="rp-add-custom" className="link-button text-[11px]"
            onClick={() => syncRows([...rows, { k: "", v: "" }])}>
            <Plus size={12} /> Tambah Field
          </button>
        </div>
        {rows.length === 0 ? (
          <p className="text-[10.5px] text-[#9A9BA3]">Belum ada field tambahan. Klik "Tambah Field" untuk menambah aturan sendiri.</p>
        ) : (
          <div className="space-y-1.5">
            {rows.map((row, i) => (
              <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2" data-testid={`rp-custom-row-${i}`}>
                <input data-testid={`rp-custom-key-${i}`} className="field" placeholder="Nama aturan"
                  value={row.k} onChange={(e) => syncRows(rows.map((r, idx) => idx === i ? { ...r, k: e.target.value } : r))} />
                <input data-testid={`rp-custom-val-${i}`} className="field" placeholder="Nilai"
                  value={row.v} onChange={(e) => syncRows(rows.map((r, idx) => idx === i ? { ...r, v: e.target.value } : r))} />
                <button type="button" className="icon-button danger" data-testid={`rp-custom-remove-${i}`}
                  onClick={() => syncRows(rows.filter((_, idx) => idx !== i))}>
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
