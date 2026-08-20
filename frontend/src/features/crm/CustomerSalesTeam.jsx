import { Crown, Plus, Trash2, Users } from "lucide-react";
import KNSelect from "../../components/KNSelect";

/** Validasi tim sales customer (mirror aturan backend). "" = valid. */
export function customerTeamError(team) {
  const t = team || [];
  if (t.length === 0) return "";
  if (t.some((m) => !m.sales_id)) return "Pilih sales untuk setiap baris co-sales.";
  if (new Set(t.map((m) => m.sales_id)).size !== t.length) return "Sales tidak boleh duplikat.";
  if (t.some((m) => Number(m.split_pct) <= 0)) return "Setiap anggota harus punya split > 0%.";
  if (t.filter((m) => m.role === "pic").length !== 1) return "Harus ada tepat 1 PIC.";
  const total = Math.round(t.reduce((s, m) => s + Number(m.split_pct || 0), 0) * 100) / 100;
  if (Math.abs(total - 100) > 0.01) return `Total split harus 100% (kini ${total}%).`;
  return "";
}

/**
 * CustomerSalesTeam — editor tim sales di level CUSTOMER (SALES REVAMP V2).
 * PIC = salesperson penanggung jawab (assigned_sales_id) — TERKUNCI sebagai PIC.
 * value = tim lengkap (PIC + co-sales) saat aktif; [] saat hanya PIC 100% (default).
 */
export function CustomerSalesTeam({ salesUsers = [], assignedSalesId = "", assignedSalesName = "", value = [], onChange }) {
  const enabled = (value || []).length > 0;
  const picName = assignedSalesName || (salesUsers.find((s) => s.id === assignedSalesId)?.name) || "—";
  const members = value || [];
  const cos = members.filter((m) => m.role !== "pic");
  const pic = members.find((m) => m.role === "pic");
  const err = customerTeamError(members);
  const total = Math.round(members.reduce((s, m) => s + Number(m.split_pct || 0), 0) * 100) / 100;

  const build = (picPct, coList) => [
    { sales_id: assignedSalesId, name: picName, role: "pic", split_pct: Number(picPct) || 0 },
    ...coList.map((c) => ({ sales_id: c.sales_id || "", name: c.name || "", role: "co", split_pct: Number(c.split_pct) || 0 })),
  ];

  const toggle = (on) => {
    if (!assignedSalesId) return;
    onChange(on ? [{ sales_id: assignedSalesId, name: picName, role: "pic", split_pct: 100 }] : []);
  };
  const setPicSplit = (v) => onChange(build(Math.max(0, Math.min(100, Number(v) || 0)), cos));
  const addCo = () => {
    const used = (pic ? Number(pic.split_pct) : 100) + cos.reduce((s, c) => s + Number(c.split_pct || 0), 0);
    const remaining = Math.max(0, 100 - used);
    onChange(build(pic ? pic.split_pct : 100, [...cos, { sales_id: "", name: "", split_pct: remaining }]));
  };
  const updateCo = (i, patch) => {
    const next = cos.map((c, idx) => (idx === i ? { ...c, ...patch } : c));
    onChange(build(pic ? pic.split_pct : 100, next));
  };
  const setCoRep = (i, sid) => {
    const r = salesUsers.find((x) => x.id === sid);
    updateCo(i, { sales_id: sid, name: r?.name || "" });
  };
  const removeCo = (i) => onChange(build(pic ? pic.split_pct : 100, cos.filter((_, idx) => idx !== i)));

  const usedIds = new Set([assignedSalesId, ...cos.map((c) => c.sales_id)].filter(Boolean));
  const repOptions = (curId) => [
    { value: "", label: "Pilih co-sales" },
    ...salesUsers.filter((s) => s.id === curId || !usedIds.has(s.id)).map((s) => ({ value: s.id, label: s.name })),
  ];

  return (
    <div data-testid="customer-sales-team" className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3">
      <label className="flex items-center gap-2 text-[11.5px] font-semibold text-[#1C1C1E]">
        <input
          type="checkbox" data-testid="customer-team-toggle"
          disabled={!assignedSalesId}
          checked={enabled}
          onChange={(e) => toggle(e.target.checked)}
        />
        <Users size={14} className="text-[#0058CC]" /> Join / Group Sales — bagi insentif dengan co-sales
      </label>
      {!assignedSalesId && <p className="mt-1 text-[10px] text-[#9A5B00]">Pilih Salesperson (PIC) dulu untuk mengatur tim.</p>}

      {enabled && (
        <div className="mt-2.5 space-y-2">
          {/* PIC row (locked) */}
          <div data-testid="customer-team-pic-row" className="flex items-center gap-1.5">
            <div className="flex flex-1 items-center gap-1.5 rounded-md border border-[#0058CC] bg-[#EAF2FF] px-2 py-1.5 text-[12px] font-semibold text-[#0058CC]">
              <Crown size={12} /> {picName} <span className="text-[10px] font-normal text-[#6B6B73]">(PIC)</span>
            </div>
            <div className="flex items-center rounded-md border border-[#E5E5EA] px-1">
              <input
                type="number" min="0" max="100" data-testid="customer-team-pic-split"
                value={pic ? pic.split_pct : 100}
                onChange={(e) => setPicSplit(e.target.value)}
                className="w-12 bg-transparent py-1 text-right text-[12px] tabular-nums outline-none"
              />
              <span className="pr-1 text-[11px] text-[#8E8E93]">%</span>
            </div>
            <span className="w-[30px]" />
          </div>

          {/* Co-sales rows */}
          {cos.map((c, i) => (
            <div key={i} data-testid={`customer-team-co-row-${i}`} className="flex items-center gap-1.5">
              <div className="flex-1">
                <KNSelect
                  data-testid={`customer-team-co-rep-${i}`}
                  className="field py-1.5 text-[12px]"
                  value={c.sales_id || ""}
                  onValueChange={(sid) => setCoRep(i, sid)}
                  placeholder="Pilih co-sales"
                  options={repOptions(c.sales_id)}
                />
              </div>
              <div className="flex items-center rounded-md border border-[#E5E5EA] px-1">
                <input
                  type="number" min="0" max="100" data-testid={`customer-team-co-split-${i}`}
                  value={c.split_pct}
                  onChange={(e) => updateCo(i, { split_pct: Math.max(0, Math.min(100, Number(e.target.value) || 0)) })}
                  className="w-12 bg-transparent py-1 text-right text-[12px] tabular-nums outline-none"
                />
                <span className="pr-1 text-[11px] text-[#8E8E93]">%</span>
              </div>
              <button type="button" data-testid={`customer-team-co-remove-${i}`} onClick={() => removeCo(i)} className="icon-button px-1.5 text-[#C0392B]" aria-label="Hapus co-sales"><Trash2 size={13} /></button>
            </div>
          ))}

          <button type="button" data-testid="customer-team-add-co" onClick={addCo} className="secondary-button w-full justify-center py-1.5 text-[11.5px]">
            <Plus size={12} /> Tambah Co-Sales
          </button>

          <div className="flex items-center justify-between text-[11.5px]">
            <span className="text-[#6B6B73]">Total split</span>
            <span data-testid="customer-team-total" className={`font-bold tabular-nums ${err ? "text-[#C0392B]" : "text-[#126E2C]"}`}>{total}%</span>
          </div>
          {err && <p data-testid="customer-team-error" className="text-[11px] text-[#C0392B]">{err}</p>}
        </div>
      )}
    </div>
  );
}
