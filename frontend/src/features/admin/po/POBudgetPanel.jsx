/**
 * POBudgetPanel (R6.3) — kontrol anggaran di form buat PO.
 * Memilih tag anggaran (akun COA / kategori beban) + pratinjau sisa anggaran
 * via POST /api/finance/budget-check (nilai dasar = DPP PO).
 * Props: formData, setFormData, dppAmount, entityId
 */
import { useCallback, useEffect, useState } from "react";
import { Target, AlertTriangle, CheckCircle2, ShieldOff } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import KNSelect from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";

export default function POBudgetPanel({ formData, setFormData, dppAmount = 0, entityId = "" }) {
  const [keys, setKeys] = useState({ accounts: [], categories: [], default_po_account: "1-1300" });
  const [check, setCheck] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    axios.get(`${API}/finance/budget-keys`, { params: entityId ? { entity_id: entityId } : {} })
      .then((r) => setKeys(r.data || {}))
      .catch(() => setErr("akses"));
  }, [entityId]);

  const dim = formData.budget_dimension || "account";
  const key = formData.budget_key || "";
  const effKey = key || (dim === "account" ? (keys.default_po_account || "1-1300") : "");

  const runCheck = useCallback(async () => {
    if (!effKey || dppAmount <= 0) { setCheck(null); return; }
    try {
      const r = await axios.post(`${API}/finance/budget-check`, {
        ...(entityId ? { entity_id: entityId } : {}),
        dimension: dim, key: effKey, amount: dppAmount,
        date: formData.expected_delivery_date || "",
      });
      setCheck(r.data); setErr("");
    } catch (e) {
      setCheck(null);
      setErr(e.response?.status === 403 ? "akses" : "");
    }
  }, [dim, effKey, dppAmount, entityId, formData.expected_delivery_date]);

  useEffect(() => { const t = setTimeout(runCheck, 450); return () => clearTimeout(t); }, [runCheck]);

  if (err === "akses") return null;   // role tanpa permission budget → panel disembunyikan

  const opts = dim === "account"
    ? [{ value: "", label: `— Default: ${keys.default_po_account || "1-1300"} (Persediaan) —` },
       ...(keys.accounts || []).map((a) => ({ value: a.code, label: `${a.code} · ${a.name}` }))]
    : [{ value: "", label: "— Pilih kategori beban —" },
       ...(keys.categories || []).map((c) => ({ value: c.code, label: `${c.label} (${c.account_code || "—"})` }))];

  const mode = check?.mode || "warn";
  const over = !!check?.over;
  const blocked = !!check?.blocked;
  const tone = mode === "off" ? "border-[#EFF0F2] bg-[#FAFBFC] text-[#6B6B73]"
    : blocked ? "border-[#F0B5AE] bg-[#FDECEC] text-[#A8221A]"
    : over ? "border-[#F5D9A8] bg-[#FFFBF3] text-[#8A5A00]"
    : "border-[#BFE3CC] bg-[#F4FBF6] text-[#1B7F4B]";
  const Icon = mode === "off" ? ShieldOff : (over ? AlertTriangle : CheckCircle2);

  return (
    <div className="rounded-md border border-[#EFF0F2] bg-[#FCFCFD] p-2.5" data-testid="po-budget-panel">
      <p className="text-[10.5px] font-bold uppercase text-[#6B6B73] mb-2 flex items-center gap-1.5">
        <Target size={12} /> Kontrol Anggaran (R6.3)
      </p>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-[10px] font-semibold text-[#8E8E93] mb-1">Dimensi</label>
          <KNSelect data-testid="po-budget-dimension" className="field py-1.5 text-[12px]" value={dim}
            onValueChange={(v) => setFormData({ ...formData, budget_dimension: v, budget_key: "" })}
            options={[{ value: "account", label: "Akun COA" }, { value: "category", label: "Kategori Beban" }]} />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-[#8E8E93] mb-1">Kunci Anggaran</label>
          <KNSelect data-testid="po-budget-key" className="field py-1.5 text-[12px]" value={key}
            onValueChange={(v) => setFormData({ ...formData, budget_dimension: dim, budget_key: v })}
            options={opts} placeholder="Pilih…" />
        </div>
      </div>
      {check && (
        <div className={`mt-2 rounded-md border px-2.5 py-2 text-[11px] ${tone}`} data-testid="po-budget-check">
          <div className="flex items-center gap-1.5 font-bold mb-0.5">
            <Icon size={13} />
            {mode === "off" ? "Kontrol anggaran OFF — pemantauan saja"
              : blocked ? "DITOLAK: melampaui anggaran (mode BLOCK)"
              : over ? "Melampaui anggaran — PO tetap bisa dibuat (mode WARN)"
              : "Dalam anggaran"}
          </div>
          {check.has_budget ? (
            <p className="tabular-nums">
              {check.label} ({check.key}) · pagu {formatCurrency(check.budget)} − realisasi {formatCurrency(check.actual)}
              {" − "}komitmen {formatCurrency(check.committed)} = <b>sisa {formatCurrency(check.available)}</b>
              {" · "}kebutuhan PO {formatCurrency(check.amount)} → sisa setelah <b>{formatCurrency(check.available_after)}</b>
              {check.used_pct_after != null ? ` (${check.used_pct_after}%)` : ""}
            </p>
          ) : (
            <p>Belum ada anggaran untuk {check.key} tahun {check.year}. {check.warning || ""}</p>
          )}
        </div>
      )}
    </div>
  );
}
