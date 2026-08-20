import { useEffect, useState } from "react";
import { Users, Plus, Trash2, Crown } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";

/** F-4c — Validasi sales_team di FE (mirror aturan backend). "" = valid (tidak dipakai). */
export function salesTeamError(team) {
  const t = team || [];
  if (t.length === 0) return "";
  if (t.some((m) => !m.sales_id)) return "Pilih sales untuk setiap baris tim.";
  if (new Set(t.map((m) => m.sales_id)).size !== t.length) return "Sales tim tidak boleh duplikat.";
  if (t.some((m) => Number(m.split_pct) <= 0)) return "Setiap anggota harus punya split > 0%.";
  if (t.filter((m) => m.role === "pic").length !== 1) return "Harus ada tepat 1 PIC.";
  const total = Math.round(t.reduce((s, m) => s + Number(m.split_pct || 0), 0) * 100) / 100;
  if (Math.abs(total - 100) > 0.01) return `Total split harus 100% (saat ini ${total}%).`;
  return "";
}

/** Prefill tim sales di checkout dari default CUSTOMER (mirror resolve_customer_sales_team BE).
 *  Urutan: customer.sales_team → PIC tunggal dari assigned_sales_id → []. */
export function customerDefaultTeam(customer) {
  if (!customer) return [];
  const team = Array.isArray(customer.sales_team) ? customer.sales_team : [];
  if (team.length) {
    return team.map((m) => ({
      sales_id: m.sales_id || "", name: m.name || "",
      role: m.role === "pic" ? "pic" : "co", split_pct: Number(m.split_pct || 0),
    }));
  }
  if (customer.assigned_sales_id) {
    return [{ sales_id: customer.assigned_sales_id, name: customer.assigned_sales_name || "", role: "pic", split_pct: 100 }];
  }
  return [];
}

/** F-4c — Editor join/group sales: PIC + co-sales dengan split insentif custom. */
export function SalesTeamEditor({ value = [], onChange }) {
  const [enabled, setEnabled] = useState((value?.length || 0) > 0);
  const [reps, setReps] = useState([]);

  useEffect(() => {
    let on = true;
    axios.get(`${API}/sales-users`).then(({ data }) => { if (on) setReps(Array.isArray(data) ? data : []); }).catch(() => {});
    return () => { on = false; };
  }, []);

  const members = value || [];
  const err = salesTeamError(members);

  const emit = (next) => {
    if (next.length && !next.some((m) => m.role === "pic")) next[0].role = "pic";
    onChange(next);
  };

  const toggle = (on) => {
    setEnabled(on);
    onChange(on ? (members.length ? members : [{ sales_id: "", name: "", role: "pic", split_pct: 100 }]) : []);
  };
  const update = (i, patch) => {
    const next = members.map((m, idx) => (idx === i ? { ...m, ...patch } : { ...m }));
    if (patch.role === "pic") next.forEach((m, idx) => { if (idx !== i) m.role = "co"; });
    emit(next);
  };
  const setRep = (i, sid) => { const r = reps.find((x) => x.id === sid); update(i, { sales_id: sid, name: r?.name || "" }); };
  const addMember = () => emit([...members, { sales_id: "", name: "", role: "co", split_pct: 0 }]);
  const removeMember = (i) => emit(members.filter((_, idx) => idx !== i));

  const repOptions = reps.map((r) => ({ value: r.id, label: r.name }));

  return (
    <div data-testid="sales-team-editor" className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
      <label className="flex items-center gap-2 text-[12px] font-semibold">
        <input type="checkbox" data-testid="sales-team-toggle" checked={enabled} onChange={(e) => toggle(e.target.checked)} />
        <Users size={14} className="text-[#0058CC]" /> Join / Group Sales (split insentif)
      </label>

      {enabled && (
        <div className="mt-2.5 space-y-2">
          {members.map((m, i) => (
            <div key={i} data-testid={`sales-team-row-${i}`} className="flex items-center gap-1.5">
              <div className="flex-1">
                <KNSelect
                  data-testid={`sales-team-rep-${i}`}
                  className="field py-1.5 text-[12px]"
                  value={m.sales_id || ""}
                  onValueChange={(sid) => setRep(i, sid)}
                  placeholder="Pilih sales"
                  options={[{ value: "", label: "Pilih sales" }, ...repOptions]}
                />
              </div>
              <button
                type="button"
                data-testid={`sales-team-pic-${i}`}
                onClick={() => update(i, { role: "pic" })}
                className={`flex items-center gap-1 rounded-md border px-2 py-1.5 text-[11px] font-semibold ${m.role === "pic" ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] text-[#6B6B73]"}`}
                title="Jadikan PIC"
              >
                <Crown size={11} /> {m.role === "pic" ? "PIC" : "co"}
              </button>
              <div className="flex items-center rounded-md border border-[#E5E5EA] px-1">
                <input
                  type="number" min="0" max="100"
                  data-testid={`sales-team-split-${i}`}
                  value={m.split_pct}
                  onChange={(e) => update(i, { split_pct: Number(e.target.value) })}
                  className="w-12 bg-transparent py-1 text-right text-[12px] tabular-nums outline-none"
                />
                <span className="pr-1 text-[11px] text-[#8E8E93]">%</span>
              </div>
              <button type="button" data-testid={`sales-team-remove-${i}`} onClick={() => removeMember(i)} className="icon-button px-1.5 text-[#C0392B]" aria-label="Hapus anggota"><Trash2 size={13} /></button>
            </div>
          ))}
          <button type="button" data-testid="sales-team-add" onClick={addMember} className="secondary-button w-full justify-center py-1.5 text-[11.5px]">
            <Plus size={12} /> Tambah Co-Sales
          </button>
          <div className="flex items-center justify-between text-[11.5px]">
            <span className="text-[#6B6B73]">Total split</span>
            <span data-testid="sales-team-total" className={`font-bold tabular-nums ${err ? "text-[#C0392B]" : "text-[#126E2C]"}`}>
              {Math.round(members.reduce((s, m) => s + Number(m.split_pct || 0), 0) * 100) / 100}%
            </span>
          </div>
          {err && <p data-testid="sales-team-error" className="text-[11px] text-[#C0392B]">{err}</p>}
        </div>
      )}
    </div>
  );
}
