import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Wallet, Plus, ArrowDownCircle, ArrowUpCircle, Ban, X, Building2 } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import FormModal from "../../components/FormModal";
import ConfirmModal from "../../components/ConfirmModal";

/**
 * CashManagementView (Fase 3 — Pengelolaan Kas).
 * Kas kecil (per entitas) + kas besar (gabungan). Catat kas masuk/keluar + saldo.
 * Koleksi kanonik: cash_transactions (prefix cash_).
 */
const EMPTY_FORM = {
  cash_type: "kas_kecil", direction: "out", amount: "",
  category: "operasional", description: "", entity_id: "",
};
const CATEGORIES = [
  { value: "operasional", label: "Operasional" },
  { value: "pembelian", label: "Pembelian" },
  { value: "gaji", label: "Gaji / Upah" },
  { value: "transfer", label: "Transfer / Top-up" },
  { value: "modal", label: "Setoran Modal" },
  { value: "lain", label: "Lain-lain" },
];

export default function CashManagementView({ currentUser, selectedEntity }) {
  const [txns, setTxns] = useState([]);
  const [summary, setSummary] = useState({ kas_kecil: {}, kas_besar: {}, kas_kecil_per_entity: {} });
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [voidTarget, setVoidTarget] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filter, setFilter] = useState("all"); // all | kas_kecil | kas_besar
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => { loadAll(); }, [selectedEntity]); // eslint-disable-line

  async function loadAll() {
    setLoading(true);
    try {
      const params = (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
      const [tRes, sRes, eRes] = await Promise.all([
        axios.get(`${API}/cash-transactions`, { params }),
        axios.get(`${API}/cash-transactions/summary`, { params }),
        axios.get(`${API}/entities`).catch(() => ({ data: [] })),
      ]);
      setTxns(Array.isArray(tRes.data) ? tRes.data : []);
      setSummary(sRes.data || { kas_kecil: {}, kas_besar: {}, kas_kecil_per_entity: {} });
      setEntities(Array.isArray(eRes.data) ? eRes.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data kas.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit() {
    if (!form.amount || Number(form.amount) <= 0) { setError("Nominal harus lebih dari 0."); return; }
    try {
      const payload = { ...form, amount: Number(form.amount) };
      const res = await axios.post(`${API}/cash-transactions`, payload);
      setNotice(`Transaksi ${res.data.number} (${res.data.direction === "in" ? "masuk" : "keluar"}) dicatat.`);
      setShowForm(false);
      setForm(EMPTY_FORM);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal mencatat transaksi kas.");
    }
  }

  async function handleVoid(t) {
    setVoidTarget(t);
  }

  async function doVoid(t) {
    try {
      await axios.post(`${API}/cash-transactions/${t.id}/void`);
      setNotice(`Transaksi ${t.number} di-void.`);
      setVoidTarget(null);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal void transaksi.");
      setVoidTarget(null);
    }
  }

  const entityName = (id) => {
    if (id === "all") return "Gabungan";
    return entities.find((e) => e.id === id)?.short_name || entities.find((e) => e.id === id)?.legal_name || id || "—";
  };
  const filtered = txns.filter((t) => filter === "all" || t.cash_type === filter);
  const fmtDate = (s) => s ? new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }) : "—";

  return (
    <div data-testid="cash-management-view">
      {notice && <div className="notice-bar success" data-testid="cash-notice"><span>{notice}</span><button onClick={() => setNotice("")}><X size={13} /></button></div>}
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="cash-error" />

      {/* FASE E-7 (E7.4) — kas tingkat grup DIHAPUS (setiap uang wajib milik satu badan
          usaha). Sisa data lama tidak disembunyikan: ia ditegur di sini, dengan perintah
          migrasinya, supaya tidak ada saldo yatim yang diam-diam hilang dari laporan. */}
      {(summary.group_cash_pending?.transactions > 0 || summary.group_cash_pending?.accounts > 0) && (
        <div className="notice-bar warning mb-3" data-testid="cash-group-pending">
          <span>
            <b>Masih ada kas tingkat grup</b>: {summary.group_cash_pending.transactions} transaksi
            {summary.group_cash_pending.accounts > 0
              ? ` dan ${summary.group_cash_pending.accounts} rekening`
              : ""} belum punya pemilik badan usaha
            (nilai bersih {formatCurrency(summary.group_cash_pending.net_amount || 0)}).
            Selama belum dipetakan, laporan keuangan tiap badan usaha belum utuh.
            Minta admin menjalankan{" "}
            <code className="rounded bg-white/60 px-1">python scripts/migrate_e7_group_cash.py --report</code>{" "}
            lalu <code className="rounded bg-white/60 px-1">--apply</code>. Baris yang tidak
            bisa dibuktikan pemiliknya otomatis menjadi kasus di <b>Pusat Kasus Keuangan</b>.
          </span>
        </div>
      )}

      {/* Summary cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 mb-3">
        <SummaryCard testId="cash-besar-card" title="Kas Besar / Bank"
          sub={selectedEntity && selectedEntity !== "all" ? entityName(selectedEntity) : "Semua entitas"}
          balance={summary.kas_besar?.balance} inAmt={summary.kas_besar?.in} outAmt={summary.kas_besar?.out} tone="rgba(0,88,204,.10)" />
        <SummaryCard testId="cash-kecil-card" title="Kas Kecil" sub={selectedEntity && selectedEntity !== "all" ? entityName(selectedEntity) : "Semua entitas"} balance={summary.kas_kecil?.balance} inAmt={summary.kas_kecil?.in} outAmt={summary.kas_kecil?.out} tone="rgba(107,33,154,.10)" />
        <div data-testid="cash-per-entity-card" className="section-card">
          <div className="section-body">
            <p className="text-[10px] font-bold uppercase text-[#6B6B73] mb-1.5">Kas Kecil per Entitas</p>
            {Object.keys(summary.kas_kecil_per_entity || {}).length === 0 ? (
              <p className="text-[11.5px] text-[#9A9BA3]">Belum ada data.</p>
            ) : (
              <div className="space-y-1.5">
                {Object.entries(summary.kas_kecil_per_entity).map(([eid, v]) => (
                  <div key={eid} className="flex items-center justify-between text-[11.5px]">
                    <span className="flex items-center gap-1 text-[#3C3C43]"><Building2 size={11} />{entityName(eid)}</span>
                    <span className="font-bold tabular-nums">{formatCurrency(v.balance)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Header + filter */}
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Wallet size={16} className="text-[#0058CC]" />
            <h2 data-testid="cash-title">Pengelolaan Kas</h2>
          </div>
          {canManage && (
            <button data-testid="create-cash-button" onClick={() => { setShowForm(!showForm); setForm({ ...EMPTY_FORM, entity_id: (selectedEntity && selectedEntity !== "all") ? selectedEntity : "" }); }} className="primary-button">
              <Plus size={13} /> Catat Transaksi
            </button>
          )}
        </div>
        <div className="section-body">
          <div className="tab-bar">
            {[{ k: "all", l: "Semua" }, { k: "kas_kecil", l: "Kas Kecil" }, { k: "kas_besar", l: "Kas Besar" }].map((t) => (
              <button key={t.k} data-testid={`cash-filter-${t.k}`} className={`tab-button ${filter === t.k ? "active" : ""}`} onClick={() => setFilter(t.k)}>{t.l}</button>
            ))}
          </div>
        </div>
      </div>

      {/* Create form */}
      {/* FASE P4 — pencatatan kas menjadi POP-UP (dulu menyelip di antara ringkasan
          saldo dan daftar transaksi). Logika form tidak diubah. */}
      <FormModal
        open={showForm && canManage}
        onClose={() => setShowForm(false)}
        title="Catat Transaksi Kas"
        subtitle="Kas kecil (tunai) atau kas besar/bank — masuk & keluar"
        icon={Wallet}
        size="md"
        testId="cash-form"
        onSubmit={handleSubmit}
        submitLabel="Catat Transaksi"
        submitTestId="submit-cash-button"
        cancelTestId="cancel-cash-button"
        error={error}
      >
        <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Jenis Kas">
                <KNSelect data-testid="cash-type-select" value={form.cash_type} onValueChange={(v) => setForm({ ...form, cash_type: v })} className="field"
                  options={[{ value: "kas_kecil", label: "Kas Kecil (tunai)" }, { value: "kas_besar", label: "Kas Besar / Bank (transfer)" }]} />
              </Field>
              <Field label="Arah">
                <KNSelect data-testid="cash-direction-select" value={form.direction} onValueChange={(v) => setForm({ ...form, direction: v })} className="field"
                  options={[{ value: "out", label: "Keluar (pengeluaran)" }, { value: "in", label: "Masuk (penerimaan)" }]} />
              </Field>
              <Field label="Nominal (Rp)" req>
                <input data-testid="cash-amount-input" type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="field" placeholder="0" />
              </Field>
              <Field label="Kategori">
                <KNSelect data-testid="cash-category-select" value={form.category} onValueChange={(v) => setForm({ ...form, category: v })} className="field" options={CATEGORIES} />
              </Field>
              {form.cash_type === "kas_kecil" && (
                <Field label="Entitas">
                  <KNSelect data-testid="cash-entity-select" value={form.entity_id} onValueChange={(v) => setForm({ ...form, entity_id: v })} className="field" placeholder="Pilih Entitas"
                    options={[{ value: "", label: "— Default (PT Kain Suka Cita) —" }, ...entities.map((e) => ({ value: e.id, label: e.short_name || e.legal_name }))]} />
                </Field>
              )}
            </div>
            <Field label="Deskripsi">
              <input data-testid="cash-description-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="field" placeholder="Keterangan transaksi..." />
            </Field>
        </div>
      </FormModal>

      {/* Transactions table */}
      <div className="section-card">
        <div className="overflow-hidden">
          <div className="grid grid-cols-[90px_90px_1.4fr_110px_120px_60px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Nomor</span><span>Tanggal</span><span>Deskripsi / Kategori</span><span>Jenis / Entitas</span><span className="text-right">Nominal</span><span></span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat transaksi kas...</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]">
              <Wallet className="mx-auto mb-2 text-gray-300" size={28} />
              <p>Belum ada transaksi kas.</p>
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[520px] overflow-y-auto">
              {filtered.map((t) => (
                <div key={t.id} data-testid={`cash-row-${t.id}`} className="grid grid-cols-[90px_90px_1.4fr_110px_120px_60px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="text-[11px] font-bold text-[#0058CC]">{t.number}</span>
                  <span className="text-[10.5px] text-[#6B6B73]">{fmtDate(t.txn_date)}</span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{t.description || "—"}</p>
                    <p className="text-[10.5px] text-[#6B6B73] capitalize">{t.category || "—"}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11px] truncate">{t.cash_type === "kas_besar" ? "Kas Besar" : "Kas Kecil"}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate">{entityName(t.entity_id)}</p>
                  </div>
                  <div className="flex items-center justify-end gap-1">
                    {t.direction === "in"
                      ? <ArrowDownCircle size={13} className="text-green-600" />
                      : <ArrowUpCircle size={13} className="text-red-500" />}
                    <span className={`text-[12px] font-bold tabular-nums ${t.direction === "in" ? "text-green-700" : "text-red-600"}`}>
                      {t.direction === "in" ? "+" : "−"}{formatCurrency(t.amount)}
                    </span>
                  </div>
                  <div className="flex justify-end">
                    {canManage && (
                      <button data-testid={`void-cash-${t.id}`} onClick={() => handleVoid(t)} className="icon-button text-red-400 hover:text-red-600" title="Anulir"><Ban size={13} /></button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <ConfirmModal
        open={!!voidTarget}
        title={`Anulir ${voidTarget?.number || "Transaksi"}`}
        message="Anulir transaksi kas ini? Saldo akan disesuaikan otomatis. Tindakan tidak dapat dibatalkan."
        confirmLabel="Anulir Transaksi"
        danger
        onConfirm={() => doVoid(voidTarget)}
        onCancel={() => setVoidTarget(null)}
        testId="cash-void-modal"
      />
    </div>
  );
}

function SummaryCard({ testId, title, sub, balance, inAmt, outAmt, tone }) {
  return (
    <div data-testid={testId} className="section-card">
      <div className="section-body">
        <div className="flex items-center justify-between mb-1">
          <p className="text-[10px] font-bold uppercase text-[#6B6B73]">{title}</p>
          <span className="text-[9.5px] text-[#9A9BA3]">{sub}</span>
        </div>
        <p className="text-[20px] font-bold tabular-nums" style={{ color: "#0F1115" }}>{formatCurrency(balance)}</p>
        <div className="mt-1.5 flex items-center gap-3 text-[10.5px]">
          <span className="text-green-700 tabular-nums">Masuk {formatCurrency(inAmt)}</span>
          <span className="text-red-600 tabular-nums">Keluar {formatCurrency(outAmt)}</span>
        </div>
        <div className="mt-2 h-1 rounded-full" style={{ background: tone }} />
      </div>
    </div>
  );
}

function Field({ label, req, children }) {
  return (
    <div>
      <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">
        {label} {req && <span className="req">*</span>}
      </label>
      {children}
    </div>
  );
}
