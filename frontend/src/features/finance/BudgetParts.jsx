/**
 * BudgetParts (R6.3) — komponen pendukung BudgetView (dipisah agar file < 500 baris).
 * Berisi: DIM_TABS, BudgetFormRow, BudgetTable, BudgetRulesPanel, AlertsStrip, UnbudgetedPanel.
 */
import { useState } from "react";
import {
  Save, Trash2, X, AlertTriangle, ShieldAlert, ShieldCheck, ShieldOff, ClipboardList, Pencil,
} from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { FC, Panel, Progress, Badge, fmtPct, formatCurrency } from "./financeShared";

export const DIM_TABS = [
  { value: "account", label: "Per Akun COA" },
  { value: "category", label: "Per Kategori Beban" },
];

export const MONTH_OPTS = [
  { value: "0", label: "Tahunan" }, { value: "1", label: "Januari" }, { value: "2", label: "Februari" },
  { value: "3", label: "Maret" }, { value: "4", label: "April" }, { value: "5", label: "Mei" },
  { value: "6", label: "Juni" }, { value: "7", label: "Juli" }, { value: "8", label: "Agustus" },
  { value: "9", label: "September" }, { value: "10", label: "Oktober" }, { value: "11", label: "November" },
  { value: "12", label: "Desember" },
];

const STATUS_TONE = { ok: "ok", warning: "warning", over: "over" };
const STATUS_LABEL = { ok: "Aman", warning: "Waspada", over: "Over Budget" };

const MODE_META = {
  off: { icon: ShieldOff, label: "OFF — tanpa kontrol", tone: "text-[#6B6B73]", bg: "bg-[#F2F2F5]",
         hint: "Anggaran hanya dipantau; PO tidak diperiksa." },
  warn: { icon: ShieldCheck, label: "WARN — peringatan", tone: "text-[#C77700]", bg: "bg-[#FBF3E5]",
          hint: "PO over-budget tetap dibuat, tapi diberi peringatan & jejak audit." },
  block: { icon: ShieldAlert, label: "BLOCK — tolak PO", tone: "text-[#C0392B]", bg: "bg-[#FDECEC]",
           hint: "PO yang melampaui anggaran DITOLAK saat dibuat maupun disetujui." },
};

/* ── Form tambah anggaran ────────────────────────────────────────────────── */
export function BudgetFormRow({ dimension, keys, onSubmit, onCancel }) {
  const [form, setForm] = useState({ key: "", month: "0", amount: "", note: "" });
  const opts = dimension === "account"
    ? (keys.accounts || []).map((a) => ({ value: a.code, label: `${a.code} · ${a.name}` }))
    : (keys.categories || []).map((c) => ({ value: c.code, label: `${c.label} (${c.account_code || "—"})` }));
  return (
    <div className="rounded-lg border border-[#D9C4EC] bg-[#FCF9FF] p-3 mb-3" data-testid="budget-form">
      <p className="text-[10.5px] font-bold uppercase text-[#6B219A] mb-2">
        Anggaran baru · {DIM_TABS.find((t) => t.value === dimension)?.label}
      </p>
      <div className="grid md:grid-cols-5 gap-3 items-end">
        <div className="md:col-span-2">
          <label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">
            {dimension === "account" ? "Akun COA" : "Kategori Beban"}
          </label>
          <KNSelect data-testid="budget-form-key" className="field py-1.5 text-[12px]" value={form.key}
            onValueChange={(v) => setForm((f) => ({ ...f, key: v }))} options={opts}
            placeholder={dimension === "account" ? "Pilih akun…" : "Pilih kategori…"} />
        </div>
        <div>
          <label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Periode</label>
          <KNSelect data-testid="budget-form-month" className="field py-1.5 text-[12px]" value={form.month}
            onValueChange={(v) => setForm((f) => ({ ...f, month: v }))} options={MONTH_OPTS} />
        </div>
        <div>
          <label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Nominal (Rp)</label>
          <input type="number" data-testid="budget-form-amount" className="field py-1.5 text-[12px]"
            value={form.amount} placeholder="0"
            onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} />
        </div>
        <div className="flex items-center gap-2">
          <button data-testid="budget-form-submit" onClick={() => onSubmit(form)}
            className="btn-primary text-[12px] py-1.5 px-3 inline-flex items-center gap-1">
            <Save size={13} /> Simpan
          </button>
          <button data-testid="budget-form-cancel" onClick={onCancel}
            className="btn-secondary text-[12px] py-1.5 px-3"><X size={13} /></button>
        </div>
      </div>
      <input data-testid="budget-form-note" className="field py-1.5 text-[12px] mt-2" value={form.note}
        placeholder="Catatan (opsional)" onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} />
    </div>
  );
}

/* ── Tabel rincian ─────────────────────────────────────────────────────── */
export function BudgetTable({ rows, editId, editAmount, setEditAmount, onEdit, onCancelEdit, onSave, onDelete }) {
  return (
    <div className="overflow-auto rounded-md border border-[#EFF0F2]">
      <table className="w-full text-[12px]" data-testid="budget-table">
        <thead>
          <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
            <th className="px-3 py-2">Kunci Anggaran</th>
            <th className="px-3 py-2 text-right">Anggaran</th>
            <th className="px-3 py-2 text-right">Komitmen</th>
            <th className="px-3 py-2 text-right">Realisasi</th>
            <th className="px-3 py-2 text-right">Sisa</th>
            <th className="px-3 py-2 w-[150px]">Terpakai (real+komit)</th>
            <th className="px-3 py-2 text-center">Status</th>
            <th className="px-3 py-2 text-right">Aksi</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} data-testid={`budget-row-${r.key}`} className="border-b border-[#F5F5F7] last:border-0">
              <td className="px-3 py-2">
                <span className="text-[10px] text-[#9A9BA3] mr-1.5">{r.key}</span>
                <span className="font-semibold text-[#1C1C1E]">{r.label}</span>
                {r.month > 0 && <span className="ml-1.5 text-[10px] text-[#6B219A]">bln {r.month}</span>}
                {(r.commitment_docs || []).length > 0 && (
                  <span className="block text-[10px] text-[#C77700] truncate"
                    title={(r.commitment_docs || []).map((d) => `${d.ref} ${formatCurrency(d.amount)}`).join(" · ")}>
                    terikat: {(r.commitment_docs || []).slice(0, 3).map((d) => d.ref).join(", ")}
                    {(r.commitment_docs || []).length > 3 ? "…" : ""}
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-[#6B219A] font-semibold">
                {editId === r.id ? (
                  <input type="number" data-testid={`budget-edit-input-${r.key}`}
                    className="field py-1 text-[11px] w-28 text-right" value={editAmount}
                    onChange={(e) => setEditAmount(e.target.value)} />
                ) : formatCurrency(r.budget)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-[#C77700]"
                data-testid={`budget-committed-${r.key}`}>
                {r.committed > 0 ? formatCurrency(r.committed) : "—"}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-[#0058CC]">{formatCurrency(r.actual)}</td>
              <td className={`px-3 py-2 text-right tabular-nums font-semibold ${r.remaining >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}
                data-testid={`budget-remaining-${r.key}`}>{formatCurrency(r.remaining)}</td>
              <td className="px-3 py-2">
                <Progress pct={r.spent_pct}
                  color={r.status === "over" ? FC.expense : r.status === "warning" ? FC.amber : FC.revenue} />
                <span className="text-[10px] text-[#9A9BA3]">
                  {fmtPct(r.spent_pct)} <span className="text-[#C7C7CC]">(real {fmtPct(r.used_pct)})</span>
                </span>
              </td>
              <td className="px-3 py-2 text-center">
                <Badge tone={STATUS_TONE[r.status]} testId={`budget-status-${r.key}`}>
                  {STATUS_LABEL[r.status]}
                </Badge>
              </td>
              <td className="px-3 py-2 text-right whitespace-nowrap">
                {editId === r.id ? (
                  <>
                    <button data-testid={`budget-save-${r.key}`} onClick={() => onSave(r.id)}
                      className="icon-button text-[#1B7F4B]" aria-label="Simpan"><Save size={13} /></button>
                    <button onClick={onCancelEdit} className="icon-button" aria-label="Batal"><X size={13} /></button>
                  </>
                ) : (
                  <>
                    <button data-testid={`budget-edit-${r.key}`} onClick={() => onEdit(r)}
                      className="icon-button" aria-label="Ubah"><Pencil size={13} /></button>
                    <button data-testid={`budget-delete-${r.key}`} onClick={() => onDelete(r.id)}
                      className="icon-button text-[#C0392B]" aria-label="Hapus"><Trash2 size={13} /></button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Panel kebijakan (rules) ───────────────────────────────────────────── */
export function BudgetRulesPanel({ rules, isAdmin, onSave, defaultAccount }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(null);
  const cur = rules || {};
  const meta = MODE_META[cur.mode] || MODE_META.warn;
  const Icon = meta.icon;
  const d = draft || {
    mode: cur.mode || "warn",
    warn_threshold_pct: String(cur.warn_threshold_pct ?? 85),
    unbudgeted_action: cur.unbudgeted_action || "allow",
    enforce_po_create: cur.enforce_po_create !== false,
    enforce_po_approve: cur.enforce_po_approve !== false,
  };
  const set = (k, v) => setDraft({ ...d, [k]: v });

  return (
    <div className="rounded-xl border border-[#EFF0F2] bg-white mb-3" data-testid="budget-rules-panel">
      <div className="flex flex-wrap items-center gap-2 px-3.5 py-2.5">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ${meta.bg} ${meta.tone}`}
          data-testid="budget-rules-mode">
          <Icon size={13} /> Kontrol Anggaran: {meta.label}
        </span>
        <span className="text-[11px] text-[#8E8E93]">{meta.hint}</span>
        <span className="text-[11px] text-[#8E8E93] ml-auto">
          Ambang waspada {cur.warn_threshold_pct ?? 85}% · tanpa anggaran: {cur.unbudgeted_action || "allow"}
          {cur.is_default ? " · (default)" : ""}
        </span>
        {isAdmin && (
          <button data-testid="budget-rules-toggle" className="btn-secondary text-[11.5px] py-1 px-2.5"
            onClick={() => { setOpen((v) => !v); setDraft(null); }}>
            {open ? "Tutup" : "Atur Kebijakan"}
          </button>
        )}
      </div>
      {open && isAdmin && (
        <div className="border-t border-[#F2F2F5] p-3.5 grid md:grid-cols-4 gap-3 items-end"
          data-testid="budget-rules-form">
          <div>
            <label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Mode Kontrol</label>
            <KNSelect data-testid="budget-rules-mode-select" className="field py-1.5 text-[12px]" value={d.mode}
              onValueChange={(v) => set("mode", v)} options={[
                { value: "off", label: "OFF — pantau saja" },
                { value: "warn", label: "WARN — beri peringatan" },
                { value: "block", label: "BLOCK — tolak PO over-budget" },
              ]} />
          </div>
          <div>
            <label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Ambang Waspada (%)</label>
            <input type="number" min="0" max="100" data-testid="budget-rules-threshold"
              className="field py-1.5 text-[12px]" value={d.warn_threshold_pct}
              onChange={(e) => set("warn_threshold_pct", e.target.value)} />
          </div>
          <div>
            <label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Belum Ada Anggaran</label>
            <KNSelect data-testid="budget-rules-unbudgeted" className="field py-1.5 text-[12px]"
              value={d.unbudgeted_action} onValueChange={(v) => set("unbudgeted_action", v)} options={[
                { value: "allow", label: "Izinkan" },
                { value: "warn", label: "Peringatkan" },
                { value: "block", label: "Tolak" },
              ]} />
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="budget-rules-save" className="btn-primary text-[12px] py-1.5 px-3 inline-flex items-center gap-1"
              onClick={async () => {
                const okSave = await onSave({
                  mode: d.mode, warn_threshold_pct: Number(d.warn_threshold_pct),
                  unbudgeted_action: d.unbudgeted_action,
                  enforce_po_create: d.enforce_po_create, enforce_po_approve: d.enforce_po_approve,
                });
                if (okSave) { setOpen(false); setDraft(null); }
              }}>
              <Save size={13} /> Simpan Kebijakan
            </button>
          </div>
          <label className="flex items-center gap-2 text-[11.5px] text-[#3C3C43]">
            <input type="checkbox" data-testid="budget-rules-po-create" checked={d.enforce_po_create}
              onChange={(e) => set("enforce_po_create", e.target.checked)} />
            Terapkan saat PO dibuat
          </label>
          <label className="flex items-center gap-2 text-[11.5px] text-[#3C3C43]">
            <input type="checkbox" data-testid="budget-rules-po-approve" checked={d.enforce_po_approve}
              onChange={(e) => set("enforce_po_approve", e.target.checked)} />
            Terapkan saat PO disetujui
          </label>
          <p className="md:col-span-2 text-[10.5px] text-[#9A9BA3]">
            PO tanpa tag anggaran otomatis dibebankan ke akun {defaultAccount || "1-1300"} (Persediaan).
          </p>
        </div>
      )}
    </div>
  );
}

/* ── Strip alert & komitmen tanpa anggaran ─────────────────────────────────── */
export function AlertsStrip({ alerts }) {
  const over = (alerts || []).filter((a) => a.status === "over");
  const warn = (alerts || []).filter((a) => a.status === "warning");
  if (over.length === 0 && warn.length === 0) return null;
  return (
    <div className="rounded-lg border border-[#F5D9A8] bg-[#FFFBF3] px-3 py-2.5 mb-3" data-testid="budget-alerts">
      <p className="flex items-center gap-1.5 text-[11.5px] font-bold text-[#8A5A00] mb-1.5">
        <AlertTriangle size={13} /> {over.length} pos over-budget · {warn.length} pos mendekati batas
      </p>
      <div className="grid md:grid-cols-2 gap-1">
        {[...over, ...warn].slice(0, 6).map((a) => (
          <div key={`${a.dimension}-${a.key}-${a.month}`} data-testid={`budget-alert-${a.key}`}
            className="flex items-center justify-between gap-2 text-[11px]">
            <span className="truncate">
              <b className={a.status === "over" ? "text-[#C0392B]" : "text-[#C77700]"}>{a.label}</b>
              <span className="text-[#9A9BA3]"> ({a.key}{a.month > 0 ? ` · bln ${a.month}` : ""})</span>
            </span>
            <span className="tabular-nums whitespace-nowrap">
              sisa <b className={a.remaining >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"}>{formatCurrency(a.remaining)}</b>
              {" · "}{fmtPct(a.spent_pct)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function UnbudgetedPanel({ items, dimension }) {
  if (!items || items.length === 0) return null;
  return (
    <Panel title="Komitmen Tanpa Anggaran (perlu ditetapkan pagu)" icon={ClipboardList}
      testId="budget-unbudgeted" className="mt-3">
      <div className="grid md:grid-cols-2 gap-2">
        {items.map((u) => (
          <div key={`${u.dimension}-${u.key}`} data-testid={`budget-unbudgeted-${u.key}`}
            className="flex items-center justify-between gap-2 rounded-md border border-[#EFF0F2] px-2.5 py-2 text-[11.5px]">
            <span className="truncate">
              <b>{u.key}</b>
              <span className="text-[#9A9BA3]"> · {dimension === "account" ? "akun" : "kategori"}</span>
              {(u.docs || []).length > 0 && (
                <span className="block text-[10px] text-[#9A9BA3] truncate">
                  {(u.docs || []).map((x) => x.ref).slice(0, 4).join(", ")}
                </span>
              )}
            </span>
            <span className="tabular-nums font-semibold text-[#C77700] whitespace-nowrap">
              {formatCurrency(u.committed)}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
