/**
 * ProductionParts — komponen bersama modul Produksi (R6.4):
 * Modal, StatusBadge, prodPerms (RBAC UI), BOMTable, BOMFormModal (editor resep multi-komponen).
 */
import { useMemo, useState } from "react";
import { X, Plus, Trash2, Pencil, Layers3 } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { Badge, formatCurrency } from "../finance/financeShared";

// ── RBAC UI (selaras permissions_config: resource "production") ───────────────
export function prodPerms(role) {
  const R = (arr) => arr.includes(role);
  return {
    manageBom: R(["admin", "manager"]),
    createWo: R(["admin", "manager", "warehouse"]),
    release: R(["admin", "manager", "warehouse"]),
    complete: R(["admin", "manager", "warehouse"]),
    cancel: R(["admin", "manager"]),
  };
}

// ── Modal generik (background solid, aksesibel) ──────────────────────────────
export function Modal({ title, children, onClose, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
         data-testid="prod-modal" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`mt-10 w-full ${wide ? "max-w-3xl" : "max-w-xl"} rounded-2xl border border-[#E7E7EC] bg-white shadow-xl`}>
        <div className="flex items-center gap-2 border-b border-[#F0F0F3] px-4 py-3">
          <h3 className="text-[13px] font-bold text-[#1C1C1E]">{title}</h3>
          <button data-testid="prod-modal-close" onClick={onClose}
                  className="ml-auto rounded-lg p-1 text-[#8E8E93] hover:bg-[#F2F2F5]"><X size={16} /></button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

// ── Status badge WO ──────────────────────────────────────────────────────────
export function StatusBadge({ status }) {
  const map = {
    draft: { tone: "neutral", label: "Draf" },
    released: { tone: "purple", label: "Dirilis" },
    completed: { tone: "ok", label: "Selesai" },
    cancelled: { tone: "over", label: "Dibatalkan" },
  };
  const s = map[status] || map.draft;
  return <Badge tone={s.tone} testId={`wo-status-${status}`}>{s.label}</Badge>;
}

const inputCls = "w-full rounded-lg border border-[#E2E2E7] bg-white px-2.5 py-1.5 text-[12px] text-[#1C1C1E] focus:border-[#6B219A] focus:outline-none";
const labelCls = "block text-[11px] font-bold text-[#3A3A3C] mb-1";

// ── BOM table ──────────────────────────────────────────────────────────────
export function BOMTable({ boms, perms, onEdit, onDelete }) {
  return (
    <div className="overflow-hidden rounded-xl border border-[#EFF0F2] bg-white" data-testid="bom-table">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="bg-[#FAFAFC] text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93]">
            <th className="px-3 py-2.5 font-bold">Nama BOM</th>
            <th className="px-3 py-2.5 font-bold">Barang Jadi (Output)</th>
            <th className="px-3 py-2.5 font-bold text-center">Komponen</th>
            <th className="px-3 py-2.5 font-bold text-right">Overhead/unit</th>
            <th className="px-3 py-2.5 font-bold text-center">Status</th>
            <th className="px-3 py-2.5 font-bold text-right">Aksi</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#F2F2F5]">
          {boms.map((b) => (
            <tr key={b.id} data-testid={`bom-row-${b.id}`} className="hover:bg-[#FCFAFE]">
              <td className="px-3 py-2.5 font-semibold text-[#1C1C1E]">{b.name}</td>
              <td className="px-3 py-2.5">
                <span className="font-medium text-[#3A3A3C]">{b.output_name || b.output_product_id}</span>
                <span className="ml-1 text-[10.5px] text-[#9A9BA3]">{b.output_sku}</span>
              </td>
              <td className="px-3 py-2.5 text-center tabular-nums">{(b.components || []).length}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{b.overhead_per_unit ? formatCurrency(b.overhead_per_unit) : "—"}</td>
              <td className="px-3 py-2.5 text-center">
                <Badge tone={b.status === "active" ? "ok" : "neutral"}>{b.status === "active" ? "Aktif" : "Non-aktif"}</Badge>
              </td>
              <td className="px-3 py-2.5">
                <div className="flex items-center justify-end gap-1.5">
                  {perms.manageBom && (
                    <>
                      <button data-testid={`bom-edit-${b.id}`} onClick={() => onEdit(b)}
                              className="rounded-md border border-[#E2E2E7] p-1.5 text-[#3A3A3C] hover:bg-[#F2F2F5]" title="Ubah"><Pencil size={13} /></button>
                      <button data-testid={`bom-delete-${b.id}`} onClick={() => onDelete(b)}
                              className="rounded-md border border-[#F3D6D6] p-1.5 text-[#C0392B] hover:bg-[#FDECEC]" title="Hapus"><Trash2 size={13} /></button>
                    </>
                  )}
                  {!perms.manageBom && <span className="text-[10.5px] text-[#B0B0B8]">—</span>}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── BOM form (create/edit) ───────────────────────────────────────────────────
export function BOMFormModal({ bom, products, onCancel, onSave }) {
  const prodOptions = useMemo(
    () => (products || []).map((p) => ({ value: p.id, label: `${p.name}${p.sku ? ` · ${p.sku}` : ""}` })),
    [products]
  );
  const [name, setName] = useState(bom?.name || "");
  const [outputId, setOutputId] = useState(bom?.output_product_id || "");
  const [overhead, setOverhead] = useState(bom?.overhead_per_unit ?? 0);
  const [status, setStatus] = useState(bom?.status || "active");
  const [notes, setNotes] = useState(bom?.notes || "");
  const [rows, setRows] = useState(
    (bom?.components || []).map((c) => ({ material_product_id: c.material_product_id, qty_per_unit: c.qty_per_unit }))
  );
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  const addRow = () => setRows((r) => [...r, { material_product_id: "", qty_per_unit: 1 }]);
  const rmRow = (i) => setRows((r) => r.filter((_, idx) => idx !== i));
  const setRow = (i, patch) => setRows((r) => r.map((x, idx) => (idx === i ? { ...x, ...patch } : x)));

  const submit = async () => {
    setErr("");
    if (!name.trim()) return setErr("Nama BOM wajib diisi.");
    if (!outputId) return setErr("Pilih produk output.");
    const comps = rows.filter((r) => r.material_product_id);
    if (comps.length === 0) return setErr("Tambahkan minimal satu komponen bahan.");
    if (comps.some((r) => !(Number(r.qty_per_unit) > 0))) return setErr("qty per unit tiap komponen harus > 0.");
    if (comps.some((r) => r.material_product_id === outputId)) return setErr("Bahan tidak boleh sama dengan output.");
    const ids = comps.map((r) => r.material_product_id);
    if (new Set(ids).size !== ids.length) return setErr("Komponen bahan duplikat.");
    const payload = {
      name: name.trim(), output_product_id: outputId, overhead_per_unit: Number(overhead) || 0,
      notes, components: comps.map((r) => ({ material_product_id: r.material_product_id, qty_per_unit: Number(r.qty_per_unit) })),
    };
    if (bom?.id) payload.status = status;
    setSaving(true);
    try {
      await onSave(payload, bom?.id);
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal menyimpan BOM.");
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="bom-form">
      {err && <div data-testid="bom-form-error" className="rounded-lg border border-[#F3D6D6] bg-[#FDECEC] px-3 py-2 text-[11.5px] font-semibold text-[#C0392B]">{err}</div>}
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className={labelCls}>Nama BOM</label>
          <input data-testid="bom-name-input" className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="mis. Batik Cap Mega Mendung" />
        </div>
        <div className="col-span-2">
          <label className={labelCls}>Produk Output (Barang Jadi)</label>
          <KNSelect data-testid="bom-output-select" value={outputId} onValueChange={setOutputId} options={prodOptions} searchable placeholder="Pilih produk output" className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Overhead / unit (Rp)</label>
          <input data-testid="bom-overhead-input" type="number" min="0" className={inputCls} value={overhead} onChange={(e) => setOverhead(e.target.value)} />
        </div>
        {bom?.id && (
          <div>
            <label className={labelCls}>Status</label>
            <KNSelect data-testid="bom-status-select" value={status} onValueChange={setStatus}
                      options={[{ value: "active", label: "Aktif" }, { value: "inactive", label: "Non-aktif" }]} className={inputCls} />
          </div>
        )}
      </div>

      <div>
        <div className="mb-1.5 flex items-center gap-2">
          <Layers3 size={13} className="text-[#6B219A]" />
          <span className="text-[11px] font-bold text-[#3A3A3C]">Komponen Bahan</span>
          <button data-testid="bom-add-component" onClick={addRow}
                  className="ml-auto inline-flex items-center gap-1 rounded-md border border-[#E2E2E7] px-2 py-1 text-[10.5px] font-bold text-[#6B219A] hover:bg-[#F3EAFB]"><Plus size={12} /> Tambah</button>
        </div>
        <div className="space-y-2">
          {rows.length === 0 && <p className="text-[11px] text-[#9A9BA3]">Belum ada komponen.</p>}
          {rows.map((r, i) => (
            <div key={i} className="flex items-center gap-2" data-testid={`bom-component-row-${i}`}>
              <div className="flex-1">
                <KNSelect data-testid={`bom-component-select-${i}`} value={r.material_product_id}
                          onValueChange={(v) => setRow(i, { material_product_id: v })}
                          options={prodOptions} searchable placeholder="Pilih bahan" className={inputCls} />
              </div>
              <input data-testid={`bom-component-qty-${i}`} type="number" min="0" step="0.01"
                     className={`${inputCls} w-28`} value={r.qty_per_unit}
                     onChange={(e) => setRow(i, { qty_per_unit: e.target.value })} placeholder="qty/unit" />
              <button data-testid={`bom-component-remove-${i}`} onClick={() => rmRow(i)}
                      className="rounded-md border border-[#F3D6D6] p-1.5 text-[#C0392B] hover:bg-[#FDECEC]"><Trash2 size={13} /></button>
            </div>
          ))}
        </div>
        <p className="mt-1.5 text-[10.5px] text-[#9A9BA3]">qty/unit = kebutuhan bahan untuk memproduksi 1 unit output.</p>
      </div>

      <div className="flex items-center justify-end gap-2 pt-1">
        <button data-testid="bom-cancel" onClick={onCancel} className="rounded-lg border border-[#E2E2E7] px-3 py-2 text-[12px] font-semibold text-[#3A3A3C] hover:bg-[#FAFAFA]">Batal</button>
        <button data-testid="bom-save" onClick={submit} disabled={saving}
                className="rounded-lg bg-[#6B219A] px-4 py-2 text-[12px] font-bold text-white hover:bg-[#581680] disabled:opacity-50">
          {saving ? "Menyimpan…" : bom?.id ? "Simpan Perubahan" : "Simpan BOM"}
        </button>
      </div>
    </div>
  );
}
