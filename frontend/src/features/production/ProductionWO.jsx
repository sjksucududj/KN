/**
 * ProductionWO — komponen Work Order (R6.4): WOTable, WOCreateModal (live rencana bahan),
 * WODetailPanel (rencana, konsumsi, roll produksi, rincian HPP).
 */
import { useMemo, useState } from "react";
import { Eye, PlayCircle, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { StatusBadge } from "./ProductionParts";
import { formatCurrency, Badge } from "../finance/financeShared";

const inputCls = "w-full rounded-lg border border-[#E2E2E7] bg-white px-2.5 py-1.5 text-[12px] text-[#1C1C1E] focus:border-[#6B219A] focus:outline-none";
const labelCls = "block text-[11px] font-bold text-[#3A3A3C] mb-1";

// ── WO table ──────────────────────────────────────────────────────────────
export function WOTable({ wos, perms, busyId, onDetail, onAction }) {
  const [filter, setFilter] = useState("");
  const rows = useMemo(() => (filter ? wos.filter((w) => w.status === filter) : wos), [wos, filter]);
  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2">
        <KNSelect data-testid="wo-status-filter" value={filter} onValueChange={setFilter}
                  options={[{ value: "", label: "Semua status" }, { value: "draft", label: "Draf" },
                            { value: "released", label: "Dirilis" }, { value: "completed", label: "Selesai" },
                            { value: "cancelled", label: "Dibatalkan" }]}
                  className={`${inputCls} w-48`} />
        <span className="text-[11px] text-[#9A9BA3]">{rows.length} Perintah Kerja</span>
      </div>
      <div className="overflow-hidden rounded-xl border border-[#EFF0F2] bg-white" data-testid="wo-table">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="bg-[#FAFAFC] text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93]">
              <th className="px-3 py-2.5 font-bold">No. WO</th>
              <th className="px-3 py-2.5 font-bold">Barang Jadi</th>
              <th className="px-3 py-2.5 font-bold text-right">Qty</th>
              <th className="px-3 py-2.5 font-bold">Gudang</th>
              <th className="px-3 py-2.5 font-bold text-center">Status</th>
              <th className="px-3 py-2.5 font-bold text-right">Total HPP</th>
              <th className="px-3 py-2.5 font-bold text-right">Aksi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#F2F2F5]">
            {rows.map((w) => {
              const busy = busyId === w.id;
              const open = w.status === "draft" || w.status === "released";
              return (
                <tr key={w.id} data-testid={`wo-row-${w.id}`} className="hover:bg-[#FCFAFE]">
                  <td className="px-3 py-2.5 font-bold text-[#6B219A]">{w.wo_number}</td>
                  <td className="px-3 py-2.5">
                    <span className="font-medium text-[#3A3A3C]">{w.output_name || w.output_product_id}</span>
                    <span className="ml-1 block text-[10.5px] text-[#9A9BA3]">{w.bom_name}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{w.planned_qty} {w.output_unit}</td>
                  <td className="px-3 py-2.5 text-[#3A3A3C]">{w.warehouse_name || w.warehouse_id}</td>
                  <td className="px-3 py-2.5 text-center"><StatusBadge status={w.status} /></td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{w.status === "completed" ? formatCurrency(w.total_cost) : "—"}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-end gap-1.5">
                      <button data-testid={`wo-detail-${w.id}`} onClick={() => onDetail(w)}
                              className="rounded-md border border-[#E2E2E7] p-1.5 text-[#3A3A3C] hover:bg-[#F2F2F5]" title="Detail"><Eye size={13} /></button>
                      {open && perms.release && w.status === "draft" && (
                        <button data-testid={`wo-release-${w.id}`} disabled={busy} onClick={() => onAction(w, "release")}
                                className="rounded-md border border-[#D9CBEA] p-1.5 text-[#6B219A] hover:bg-[#F3EAFB] disabled:opacity-50" title="Rilis"><PlayCircle size={13} /></button>
                      )}
                      {open && perms.complete && (
                        <button data-testid={`wo-complete-${w.id}`} disabled={busy} onClick={() => onAction(w, "complete")}
                                className="rounded-md border border-[#CBE7D5] p-1.5 text-[#1B7F4B] hover:bg-[#EAF6EF] disabled:opacity-50" title="Selesaikan"><CheckCircle2 size={13} /></button>
                      )}
                      {open && perms.cancel && (
                        <button data-testid={`wo-cancel-${w.id}`} disabled={busy} onClick={() => onAction(w, "cancel")}
                                className="rounded-md border border-[#F3D6D6] p-1.5 text-[#C0392B] hover:bg-[#FDECEC] disabled:opacity-50" title="Batalkan"><XCircle size={13} /></button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── WO create modal (dengan rencana bahan live) ──────────────────────────────
export function WOCreateModal({ boms, warehouses, balances, onCancel, onCreate }) {
  const bomOptions = useMemo(() => boms.map((b) => ({ value: b.id, label: `${b.name} → ${b.output_name || b.output_product_id}` })), [boms]);
  const whOptions = useMemo(() => (warehouses || []).map((w) => ({ value: w.id, label: w.name || w.id })), [warehouses]);
  const [bomId, setBomId] = useState(boms[0]?.id || "");
  const [qty, setQty] = useState(1);
  const [warehouseId, setWarehouseId] = useState(warehouses[0]?.id || "");
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  const bom = useMemo(() => boms.find((b) => b.id === bomId), [boms, bomId]);

  const availOf = (pid) =>
    (balances || [])
      .filter((b) => b.product_id === pid && b.warehouse_id === warehouseId)
      .reduce((s, b) => s + Number(b.available_qty || 0), 0);

  const plan = useMemo(() => {
    if (!bom) return [];
    const q = Number(qty) || 0;
    return (bom.components || []).map((c) => {
      const required = +(c.qty_per_unit * q).toFixed(2);
      const available = +availOf(c.material_product_id).toFixed(2);
      return { ...c, required, available, sufficient: available + 0.005 >= required };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bom, qty, warehouseId, balances]);

  const allOk = plan.length > 0 && plan.every((p) => p.sufficient);

  const submit = async () => {
    setErr("");
    if (!bomId) return setErr("Pilih BOM.");
    if (!(Number(qty) > 0)) return setErr("Jumlah produksi harus > 0.");
    if (!warehouseId) return setErr("Pilih gudang produksi.");
    setSaving(true);
    try {
      await onCreate({ bom_id: bomId, planned_qty: Number(qty), warehouse_id: warehouseId, notes });
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal membuat Work Order.");
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="wo-form">
      {err && <div data-testid="wo-form-error" className="rounded-lg border border-[#F3D6D6] bg-[#FDECEC] px-3 py-2 text-[11.5px] font-semibold text-[#C0392B]">{err}</div>}
      {boms.length === 0 && <div className="rounded-lg border border-[#F5D9A8] bg-[#FFFBF3] px-3 py-2 text-[11.5px] text-[#8A5A00]">Belum ada BOM aktif. Buat BOM terlebih dahulu di tab BOM / Resep.</div>}
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className={labelCls}>BOM / Resep</label>
          <KNSelect data-testid="wo-bom-select" value={bomId} onValueChange={setBomId} options={bomOptions} searchable placeholder="Pilih BOM" className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Jumlah Produksi (unit output)</label>
          <input data-testid="wo-qty-input" type="number" min="0" step="0.01" className={inputCls} value={qty} onChange={(e) => setQty(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Gudang Produksi</label>
          <KNSelect data-testid="wo-warehouse-select" value={warehouseId} onValueChange={setWarehouseId} options={whOptions} searchable placeholder="Pilih gudang" className={inputCls} />
        </div>
        <div className="col-span-2">
          <label className={labelCls}>Catatan (opsional)</label>
          <input data-testid="wo-notes-input" className={inputCls} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
      </div>

      {bom && (
        <div data-testid="wo-plan-preview" className="rounded-xl border border-[#EFF0F2] bg-[#FCFCFD] p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[11px] font-bold text-[#3A3A3C]">Rencana Kebutuhan Bahan</span>
            {plan.length > 0 && (
              allOk ? <Badge tone="ok" testId="wo-plan-ok">Bahan mencukupi</Badge>
                    : <Badge tone="over" testId="wo-plan-short">Bahan kurang</Badge>
            )}
          </div>
          <table className="w-full text-[11.5px]">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wide text-[#9A9BA3]">
                <th className="py-1 font-bold">Bahan</th>
                <th className="py-1 font-bold text-right">Butuh</th>
                <th className="py-1 font-bold text-right">Tersedia</th>
                <th className="py-1 font-bold text-center">Cukup?</th>
              </tr>
            </thead>
            <tbody>
              {plan.map((p, i) => (
                <tr key={p.material_product_id} data-testid={`wo-plan-row-${i}`} className="border-t border-[#F2F2F5]">
                  <td className="py-1.5 text-[#3A3A3C]">{p.name || p.material_product_id}</td>
                  <td className="py-1.5 text-right tabular-nums">{p.required} {p.unit}</td>
                  <td className="py-1.5 text-right tabular-nums">{p.available} {p.unit}</td>
                  <td className="py-1.5 text-center">
                    {p.sufficient ? <span className="text-[#1B7F4B] font-bold">✓</span>
                                   : <span className="inline-flex items-center gap-1 text-[#C0392B] font-bold"><AlertTriangle size={11} /> ✗</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1.5 text-[10px] text-[#9A9BA3]">Ketersediaan dihitung dari saldo gudang terpilih. Validasi final saat WO diselesaikan.</p>
        </div>
      )}

      <div className="flex items-center justify-end gap-2 pt-1">
        <button data-testid="wo-cancel" onClick={onCancel} className="rounded-lg border border-[#E2E2E7] px-3 py-2 text-[12px] font-semibold text-[#3A3A3C] hover:bg-[#FAFAFA]">Batal</button>
        <button data-testid="wo-save" onClick={submit} disabled={saving || boms.length === 0}
                className="rounded-lg bg-[#6B219A] px-4 py-2 text-[12px] font-bold text-white hover:bg-[#581680] disabled:opacity-50">
          {saving ? "Membuat…" : "Buat Work Order"}
        </button>
      </div>
    </div>
  );
}

// ── WO detail panel ──────────────────────────────────────────────────────────
function CostRow({ label, value, strong }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className={`text-[11.5px] ${strong ? "font-bold text-[#1C1C1E]" : "text-[#6B6B73]"}`}>{label}</span>
      <span className={`tabular-nums text-[12px] ${strong ? "font-bold text-[#1C1C1E]" : "text-[#3A3A3C]"}`}>{formatCurrency(value || 0)}</span>
    </div>
  );
}

export function WODetailPanel({ wo, perms, busy, onAction }) {
  const open = wo.status === "draft" || wo.status === "released";
  const plan = wo.material_plan || [];
  const consumed = wo.consumed || [];
  return (
    <div className="space-y-3.5" data-testid="wo-detail">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={wo.status} />
        <span className="text-[12px] text-[#6B6B73]">Output: <b className="text-[#1C1C1E]">{wo.output_name || wo.output_product_id}</b> · {wo.planned_qty} {wo.output_unit} · Gudang {wo.warehouse_name || wo.warehouse_id}</span>
      </div>

      {/* Rencana / konsumsi bahan */}
      <div className="rounded-xl border border-[#EFF0F2] bg-white">
        <div className="border-b border-[#F2F2F5] px-3 py-2 text-[11px] font-bold text-[#3A3A3C]">
          {wo.status === "completed" ? "Bahan Terkonsumsi" : "Rencana Kebutuhan Bahan"}
        </div>
        <table className="w-full text-[11.5px]">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-[#9A9BA3]">
              <th className="px-3 py-1.5 font-bold">Bahan</th>
              <th className="px-3 py-1.5 font-bold text-right">{wo.status === "completed" ? "Qty" : "Butuh"}</th>
              {wo.status !== "completed" && <th className="px-3 py-1.5 font-bold text-right">Tersedia</th>}
              {wo.status === "completed" && <th className="px-3 py-1.5 font-bold text-right">Nilai</th>}
              {wo.status !== "completed" && <th className="px-3 py-1.5 font-bold text-center">Cukup?</th>}
            </tr>
          </thead>
          <tbody>
            {(wo.status === "completed" ? consumed : plan).map((r, i) => (
              <tr key={i} className="border-t border-[#F2F2F5]" data-testid={`wo-detail-mat-${i}`}>
                <td className="px-3 py-1.5 text-[#3A3A3C]">{r.name || r.material_product_id}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{(wo.status === "completed" ? r.qty : r.required_qty)} {r.unit}</td>
                {wo.status !== "completed" && <td className="px-3 py-1.5 text-right tabular-nums">{r.available_qty} {r.unit}</td>}
                {wo.status === "completed" && <td className="px-3 py-1.5 text-right tabular-nums">{formatCurrency(r.value || 0)}</td>}
                {wo.status !== "completed" && (
                  <td className="px-3 py-1.5 text-center">{r.sufficient ? <span className="text-[#1B7F4B] font-bold">✓</span> : <span className="text-[#C0392B] font-bold">✗</span>}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {wo.status === "completed" && (
        <div className="rounded-xl border border-[#EFF0F2] bg-white p-3">
          <p className="mb-1 text-[11px] font-bold text-[#3A3A3C]">Rincian HPP Produksi</p>
          <CostRow label="Biaya bahan" value={wo.material_cost} />
          <CostRow label="Overhead" value={wo.overhead_cost} />
          <div className="my-1 border-t border-[#F2F2F5]" />
          <CostRow label="Total HPP" value={wo.total_cost} strong />
          <div className="mt-1 flex items-center justify-between">
            <span className="text-[11.5px] text-[#6B6B73]">HPP / unit</span>
            <span className="tabular-nums text-[12px] font-bold text-[#6B219A]">{formatCurrency(wo.unit_cost || 0)}</span>
          </div>
          <p className="mt-2 text-[10.5px] text-[#9A9BA3]">
            {wo.produced_qty} {wo.output_unit} barang jadi diproduksi ({(wo.produced_roll_ids || []).length} roll).
            {wo.je_id ? " Overhead dikapitalisasi ke persediaan (jurnal terbit)." : " Tanpa overhead — transformasi persediaan (GL net-0)."}
          </p>
        </div>
      )}

      {open && (
        <div className="flex items-center justify-end gap-2">
          {perms.cancel && (
            <button data-testid="wo-detail-cancel" disabled={busy} onClick={() => onAction("cancel")}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#F3D6D6] px-3 py-2 text-[12px] font-semibold text-[#C0392B] hover:bg-[#FDECEC] disabled:opacity-50"><XCircle size={14} /> Batalkan</button>
          )}
          {perms.release && wo.status === "draft" && (
            <button data-testid="wo-detail-release" disabled={busy} onClick={() => onAction("release")}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#D9CBEA] px-3 py-2 text-[12px] font-semibold text-[#6B219A] hover:bg-[#F3EAFB] disabled:opacity-50"><PlayCircle size={14} /> Rilis</button>
          )}
          {perms.complete && (
            <button data-testid="wo-detail-complete" disabled={busy} onClick={() => onAction("complete")}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-[#1B7F4B] px-4 py-2 text-[12px] font-bold text-white hover:bg-[#166a3f] disabled:opacity-50"><CheckCircle2 size={14} /> Selesaikan Produksi</button>
          )}
        </div>
      )}
    </div>
  );
}
