import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { FolderTree, RefreshCw, Save, Info } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";

/**
 * ExpenseCategoriesView — Konfigurasi pemetaan kategori pengeluaran petty cash → akun COA.
 * Dipakai saat posting GL pertanggungjawaban (Dr beban per kategori / Cr Kas Kecil).
 * RBAC: view = cash_settlement.view; ubah = cash_settlement.manage (admin/manager).
 */
export default function ExpenseCategoriesView({ currentUser }) {
  const [cats, setCats] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [savingCode, setSavingCode] = useState("");

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => { loadAll(); }, []); // eslint-disable-line

  async function loadAll() {
    setLoading(true);
    try {
      const [c, a] = await Promise.all([
        axios.get(`${API}/expense-categories`),
        axios.get(`${API}/gl/accounts`).catch(() => ({ data: [] })),
      ]);
      setCats(Array.isArray(c.data) ? c.data : []);
      setAccounts(Array.isArray(a.data) ? a.data : (a.data?.items || []));
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat kategori beban.");
    } finally { setLoading(false); }
  }
  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  // Akun beban yang postable (kode 6-xxxx) untuk mapping.
  const accountOptions = useMemo(() => accounts
    .filter((a) => (a.is_postable ?? a.is_active ?? true) && String(a.code || "").startsWith("6"))
    .map((a) => ({ value: a.code, label: `${a.code} · ${a.name}` })), [accounts]);
  const accName = (code) => accounts.find((a) => a.code === code)?.name || "";

  async function patchCat(code, patch, okMsg) {
    setSavingCode(code); setError("");
    try {
      const res = await axios.patch(`${API}/expense-categories/${code}`, patch);
      setCats(cats.map((c) => (c.code === code ? { ...c, ...res.data } : c)));
      flash(okMsg || "Tersimpan.");
    } catch (e) { setError(e.response?.data?.detail || "Gagal menyimpan kategori."); }
    finally { setSavingCode(""); }
  }

  return (
    <div data-testid="expense-categories-view" className="grid gap-4">
      {toast && <div className="notice-bar success" data-testid="excat-toast"><span>{toast}</span><button onClick={() => setToast("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="excat-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <FolderTree size={15} className="text-[#0058CC]" />
            <span className="kicker">Kas & Petty Cash</span>
            <h2 data-testid="excat-title">Kategori Beban → Akun COA</h2>
          </div>
          <button data-testid="excat-refresh" className="icon-button" onClick={loadAll} aria-label="Muat ulang"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
        </div>
        <div className="section-body">
          <div className="flex items-start gap-2 rounded-md bg-[#F0F6FF] border border-[#D6E6FF] px-3 py-2 mb-3 text-[11.5px] text-[#004099]">
            <Info size={14} className="mt-0.5 shrink-0" />
            <span>Pemetaan ini menentukan akun beban yang di-debit saat pertanggungjawaban (LPJ) disetujui. Kredit selalu ke <b>Kas Kecil</b>. {canManage ? "" : "Hanya admin/manager yang dapat mengubah."}</span>
          </div>

          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[1.6fr_1.6fr_100px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
              <span>Kategori</span><span>Akun Beban (COA)</span><span className="text-right">Status</span>
            </div>
            {loading ? <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
              : cats.length === 0 ? <div data-testid="excat-empty" className="py-12 text-center text-[12px] text-[#6B6B73]">Belum ada kategori.</div>
              : (
                <div className="divide-y divide-[#EFF0F2]">
                  {cats.map((c) => (
                    <div key={c.code} data-testid={`excat-row-${c.code}`} className="grid grid-cols-[1.6fr_1.6fr_100px] items-center gap-2 px-3 py-2.5">
                      <div className="min-w-0">
                        <p className="text-[12px] font-semibold truncate">{c.label}</p>
                        <p className="text-[10.5px] text-[#9A9BA3]">{c.code}</p>
                      </div>
                      <div className="min-w-0">
                        {canManage ? (
                          <KNSelect data-testid={`excat-account-${c.code}`} className="form-input" value={c.account_code}
                            onValueChange={(v) => patchCat(c.code, { account_code: v }, `Akun ${c.label} → ${v}`)}
                            options={accountOptions} placeholder="Pilih akun" />
                        ) : (
                          <span className="text-[12px]">{c.account_code} · {accName(c.account_code)}</span>
                        )}
                      </div>
                      <div className="flex justify-end items-center gap-2">
                        {savingCode === c.code && <Save size={13} className="text-[#0058CC] animate-pulse" />}
                        {canManage ? (
                          <label className="flex items-center gap-1.5 text-[11px]">
                            <input type="checkbox" data-testid={`excat-active-${c.code}`} checked={c.active !== false} onChange={(e) => patchCat(c.code, { active: e.target.checked }, e.target.checked ? "Diaktifkan." : "Dinonaktifkan.")} />
                            Aktif
                          </label>
                        ) : (
                          <span className={`status-pill ${c.active ? "pill-success" : "pill-muted"}`}>{c.active ? "Aktif" : "Nonaktif"}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
          </div>
        </div>
      </section>
    </div>
  );
}
