/**
 * LotParts (FASE C) — bagian tampilan layar “Lot & Silsilah”.
 * Dipisah dari view utama agar tiap file di bawah batas guardrail (<500 baris).
 */
import { AlertTriangle, Boxes, Layers3, Search } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { formatQty } from "../../../utils/formatters";
import { LOT_STATUS_TONE, SOURCE_TONE, shortDate } from "./lotApi";

export function LotStatCards({ stats }) {
  const s = stats || {};
  const cards = [
    { k: "Lot terdaftar", v: s.total ?? 0, s: "identitas batch aktif", t: "total" },
    { k: "Roll dalam lot", v: s.rolls_in_lots ?? 0, s: "seluruh roll tertaut", t: "rolls" },
    { k: "Sisa dalam lot", v: formatQty(s.qty_remaining ?? 0), s: "satuan dasar produk", t: "qty" },
    { k: "Data belum lengkap", v: s.incomplete_capture ?? 0, s: "tanpa lot supplier/dye lot",
      t: "incomplete" },
    { k: "Roll tanpa lot", v: s.rolls_without_lot ?? 0,
      s: (s.rolls_without_lot ?? 0) > 0 ? "perlu ditambal (mode peringatan)" : "bersih ✓",
      t: "orphan" },
  ];
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
      {cards.map((c) => (
        <div key={c.t} data-testid={`lot-stat-${c.t}`}
          className="rounded-md border border-[#EFF0F2] bg-white px-2.5 py-2">
          <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">{c.k}</p>
          <p className="text-[16px] font-bold tabular-nums text-[#1C1C1E]">{c.v}</p>
          <p className="text-[10px] text-[#8E8E93]">{c.s}</p>
        </div>
      ))}
    </div>
  );
}


export function LotFilters({ filter, setFilter, sourceOptions, statusOptions, stageOptions,
                             warehouses = [], onSearch }) {
  return (
    <div data-testid="lot-filters" className="flex flex-wrap items-center gap-1.5">
      <div className="relative">
        <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#8E8E93]" />
        <input data-testid="lot-search" className="field !py-1 !pl-6 !text-[10.5px] w-[220px]"
          placeholder="Cari nomor lot / lot supplier / dye lot / SKU"
          value={filter.q}
          onChange={(e) => setFilter({ ...filter, q: e.target.value })}
          onKeyDown={(e) => { if (e.key === "Enter") onSearch?.(); }} />
      </div>
      <KNSelect data-testid="lot-filter-source" className="field !py-1 !text-[10.5px] w-[150px]"
        value={filter.source} placeholder="Semua sumber"
        options={[{ value: "", label: "Semua sumber" }, ...sourceOptions]}
        onValueChange={(v) => setFilter({ ...filter, source: v })} />
      <KNSelect data-testid="lot-filter-status" className="field !py-1 !text-[10.5px] w-[150px]"
        value={filter.lot_status} placeholder="Semua status"
        options={[{ value: "", label: "Semua status" }, ...statusOptions]}
        onValueChange={(v) => setFilter({ ...filter, lot_status: v })} />
      <KNSelect data-testid="lot-filter-stage" className="field !py-1 !text-[10.5px] w-[140px]"
        value={filter.stage} placeholder="Semua tahap"
        options={[{ value: "", label: "Semua tahap" }, ...stageOptions]}
        onValueChange={(v) => setFilter({ ...filter, stage: v })} />
      <KNSelect data-testid="lot-filter-warehouse" className="field !py-1 !text-[10.5px] w-[160px]"
        value={filter.warehouse_id} placeholder="Semua gudang"
        options={[{ value: "", label: "Semua gudang" },
                  ...warehouses.map((w) => ({ value: w.id, label: w.name || w.id }))]}
        onValueChange={(v) => setFilter({ ...filter, warehouse_id: v })} />
      <button data-testid="lot-filter-apply" className="btn-secondary !px-2 !py-1 !text-[10.5px]"
        onClick={onSearch}>Terapkan</button>
    </div>
  );
}

export function LotStatusPill({ value, label, testId }) {
  return (
    <span data-testid={testId} className={`status-pill ${LOT_STATUS_TONE[value] || "pill-muted"}`}>
      {label || value || "—"}
    </span>
  );
}

export function LotSourcePill({ value, label }) {
  return (
    <span className={`status-pill ${SOURCE_TONE[value] || "pill-muted"}`}>{label || value}</span>
  );
}

export function LotTable({ lots, loading, activeId, onOpen, labelOf }) {
  if (loading) {
    return <p data-testid="lot-table-loading" className="px-2.5 py-6 text-center text-[11px] text-[#6B6B73]">Memuat lot…</p>;
  }
  if (!lots.length) {
    return (
      <p data-testid="lot-table-empty" className="px-2.5 py-6 text-center text-[11px] text-[#6B6B73]">
        Belum ada lot yang cocok dengan filter. Lot terbentuk otomatis saat penerimaan barang
        (GR), hasil makloon, dan produksi — atau buat manual lewat tombol “Buat Lot”.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table data-testid="lot-table" className="w-full min-w-[880px] text-[11px]">
        <thead>
          <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[9.5px] uppercase tracking-wide text-[#8E8E93]">
            <th className="px-2.5 py-1.5 font-bold">Nomor Lot</th>
            <th className="px-2.5 py-1.5 font-bold">Produk</th>
            <th className="px-2.5 py-1.5 font-bold">Lot Supplier / Dye Lot</th>
            <th className="px-2.5 py-1.5 font-bold">Tahap</th>
            <th className="px-2.5 py-1.5 font-bold">Status</th>
            <th className="px-2.5 py-1.5 text-right font-bold">Roll</th>
            <th className="px-2.5 py-1.5 text-right font-bold">Sisa</th>
            <th className="px-2.5 py-1.5 font-bold">Sumber</th>
            <th className="px-2.5 py-1.5 font-bold">Dibuat</th>
            <th className="px-2.5 py-1.5"></th>
          </tr>
        </thead>
        <tbody>
          {lots.map((l) => {
            const incomplete = !l.supplier_lot || !l.dye_lot;
            return (
              <tr key={l.id} data-testid={`lot-row-${l.id}`}
                className={`border-b border-[#F5F5F7] last:border-0 hover:bg-[#FAFBFC] ${activeId === l.id ? "bg-[#F0F6FF]" : ""}`}>
                <td className="px-2.5 py-1.5 font-semibold text-[#1C1C1E]">
                  <span className="flex items-center gap-1">
                    <Layers3 size={11} className="text-[#0058CC]" />
                    {l.lot_number}
                    {(l.parent_lot_ids || []).length > 0 && (
                      <span title="punya lot induk" className="text-[9.5px] text-[#8E8E93]">↑</span>
                    )}
                    {(l.child_lot_ids || []).length > 0 && (
                      <span title="punya lot turunan" className="text-[9.5px] text-[#8E8E93]">↓</span>
                    )}
                  </span>
                  {(l.legacy_lot_codes || []).length > 0 && (
                    <span className="block text-[9.5px] text-[#8E8E93]">
                      lot lama: {(l.legacy_lot_codes || []).join(", ")}
                    </span>
                  )}
                </td>
                <td className="px-2.5 py-1.5">
                  <span className="font-semibold">{l.sku || "—"}</span>
                  <span className="block text-[10px] text-[#8E8E93]">{l.product_name}</span>
                </td>
                <td className="px-2.5 py-1.5">
                  {incomplete ? (
                    <span className="flex items-center gap-1 text-[10.5px] text-amber-600">
                      <AlertTriangle size={11} /> {l.supplier_lot || "lot supplier kosong"} ·{" "}
                      {l.dye_lot || "dye lot kosong"}
                    </span>
                  ) : (
                    <span className="text-[10.5px]">{l.supplier_lot} · {l.dye_lot}</span>
                  )}
                </td>
                <td className="px-2.5 py-1.5">{labelOf("stage", l.stage)}</td>
                <td className="px-2.5 py-1.5">
                  <LotStatusPill value={l.lot_status} label={labelOf("lot_status", l.lot_status)}
                    testId={`lot-status-${l.id}`} />
                </td>
                <td className="px-2.5 py-1.5 text-right tabular-nums">{l.roll_count ?? 0}</td>
                <td className="px-2.5 py-1.5 text-right tabular-nums">
                  {formatQty(l.qty_remaining)} <span className="text-[9.5px] text-[#8E8E93]">{l.unit}</span>
                </td>
                <td className="px-2.5 py-1.5">
                  <LotSourcePill value={l.source} label={labelOf("lot_source", l.source)} />
                </td>
                <td className="px-2.5 py-1.5 text-[10.5px] text-[#6B6B73]">{shortDate(l.created_at)}</td>
                <td className="px-2.5 py-1.5 text-right">
                  <button data-testid={`lot-open-${l.id}`} className="btn-secondary !px-2 !py-0.5 !text-[10px]"
                    onClick={() => onOpen(l)}>Detail</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function UnassignedRollsCard({ data, onFix, busy }) {
  const rows = data?.rolls || [];
  if (!rows.length) return null;
  return (
    <div data-testid="lot-unassigned-card" className="rounded-md border border-amber-200 bg-amber-50">
      <div className="flex items-center gap-1.5 border-b border-amber-200 px-2.5 py-1.5">
        <Boxes size={12} className="text-amber-600" />
        <span className="text-[10px] font-bold uppercase tracking-wide text-amber-700">
          {data.total} roll belum bertaut lot (mode peringatan)
        </span>
        <button data-testid="lot-fix-unassigned" className="primary-button ml-auto !px-2 !py-0.5 !text-[10px]"
          disabled={busy} onClick={onFix}>
          {busy ? "Menambal…" : "Tambal otomatis"}
        </button>
      </div>
      <div className="px-2.5 py-1.5 text-[10.5px] text-amber-800">
        Contoh: {rows.slice(0, 6).map((r) => r.roll_no || r.id).join(", ")}
        {rows.length > 6 ? ", …" : ""}
      </div>
    </div>
  );
}
