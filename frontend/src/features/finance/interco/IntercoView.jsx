/**
 * FASE G-6 / G-6b — **TRANSAKSI ANTAR ENTITAS** (jual-beli antar-PT dalam grup).
 *
 * Masalah nyata yang diselesaikan layar ini: PT KSC menjual kain ke CV Kanda
 * dengan HARGA KHUSUS dan margin — bukan sekadar pindah gudang. Sebelum fase ini
 * antar-PT hidup sebagai `warehouse_transfers` at-cost sehingga tidak ada harga,
 * tidak ada margin, dan **tidak ada saldo antar-PT**.
 *
 *   1. Daftar Transaksi — dokumen kembar (SO+SJ+Invoice / PO+Vendor Bill)
 *   2. Saldo Antar-PT   — "CV Kanda utang berapa ke KSC?" + pengingat (G-6b)
 *   3. Settlement       — pelunasan sekaligus banyak transaksi (US6)
 *   4. Retur Antar-PT   — jalan resmi sesudah barangnya berpindah (G-6b)
 *   5. Rapor Margin     — margin grup: sudah vs belum terealisasi (G-6b)
 */
import { useCallback, useEffect, useState } from "react";
import {
  RefreshCw, Plus, ArrowRightLeft, Layers, Wallet, CheckCircle2,
  Handshake, Undo2, TrendingUp,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency } from "../../../utils/formatters";
import { apiErrorText } from "../../../utils/apiError";
import { can } from "../../../config/roles";
import IntercoCreateModal from "./IntercoCreateModal";
import IntercoSettlementModal from "./IntercoSettlementModal";
import IntercoDetailPanel from "./IntercoDetailPanel";
import InternalContractWizardModal from "./InternalContractWizardModal";
import IntercoCancelModal from "./IntercoCancelModal";
import IntercoTaxModal from "./IntercoTaxModal";
import IntercoReturnModal from "./IntercoReturnModal";
import IntercoReturnsPanel from "./IntercoReturnsPanel";
import IntercoMarginPanel from "./IntercoMarginPanel";
// FASE E-7 (E7f) — pinjaman uang antar-PT (dokumen kembar + eliminasi non-dagang).
import IntercoLoansPanel from "./IntercoLoansPanel";
import { TransactionsPanel, BalancesPanel, SettlementsPanel } from "./IntercoPanels";
import DetailModal from "../../../components/DetailModal";

const TABS = [
  { id: "transactions", label: "Daftar Transaksi", icon: ArrowRightLeft },
  { id: "balances",     label: "Saldo Antar-PT",   icon: Wallet },
  { id: "settlements",  label: "Settlement",       icon: Layers },
  { id: "returns",      label: "Retur Antar-PT",   icon: Undo2 },
  { id: "loans",        label: "Pinjaman Antar-PT", icon: Wallet },
  { id: "margin",       label: "Rapor Margin",     icon: TrendingUp },
];

// Tab yang bicara UANG antar-PT — dipagari izin `interco_finance` (E-0/E0.8f).
const MONEY_TABS = ["balances", "settlements", "loans", "margin"];

export default function IntercoView({ currentUser, selectedEntity, entities = [] }) {
  const [tab, setTab] = useState("transactions");
  const [rows, setRows] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [settlements, setSettlements] = useState([]);
  const [returns, setReturns] = useState([]);
  const [margin, setMargin] = useState(null);
  const [summary, setSummary] = useState(null);
  const [fStatus, setFStatus] = useState("");
  const [fRole, setFRole] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showSettle, setShowSettle] = useState(null);
  const [showContract, setShowContract] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [cancelDoc, setCancelDoc] = useState(null);
  const [taxDoc, setTaxDoc] = useState(null);
  const [returnDoc, setReturnDoc] = useState(null);

  const role = (currentUser?.role || "").toLowerCase();
  // FASE E-8 (E8.1) — wewenang dibaca dari IZIN EFEKTIF pengguna (dikirim server saat
  // login), bukan dari daftar nama peran. Dulu `["admin","manager"].includes(role)`:
  // begitu peran `sales_admin` lahir dengan izin `interco.create`, tombolnya tetap mati
  // padahal server mengizinkan — pengguna menyangka dirinya tidak berwenang.
  const perms = currentUser?.permissions || {};
  const canWrite = can(perms, "interco", "create");
  // Sisi UANG antar-PT (saldo pasangan PT, settlement/netting, pinjaman, rapor margin)
  // dipagari izin TERSENDIRI `interco_finance` sejak E-0/E0.8f. Tanpa penyaringan tab
  // di bawah, peran yang hanya mengurus BARANG (Admin Sales, gudang) akan membuka tab
  // yang pasti 403 — layar penuh galat merah yang bukan salah penggunanya.
  const canMoney = can(perms, "interco_finance", "view");
  const tabs = TABS.filter((t) => canMoney || !MONEY_TABS.includes(t.id));
  const entityId = selectedEntity?.id || "";

  useEffect(() => {
    // Kalau tab aktif ternyata tidak boleh dilihat peran ini, pindahkan ke tab pertama
    // yang sah (mis. deep-link `&tab=margin` dibuka Admin Sales).
    if (!tabs.some((t) => t.id === tab)) setTab(tabs[0]?.id || "transactions");
  }, [tabs, tab]);

  const refresh = useCallback(async () => {
    setBusy(true); setErr("");
    try {
      const params = { entity_id: entityId, status: fStatus, role: fRole };
      const money = (url, cfg) => (canMoney
        ? axios.get(url, cfg)
        : Promise.resolve({ data: null }));
      const [s, t, a, st, rt, mg] = await Promise.all([
        axios.get(`${API}/interco/summary`, { params: { entity_id: entityId } }),
        axios.get(`${API}/interco/transactions`, { params }),
        money(`${API}/interco/accounts`),
        money(`${API}/interco/settlements`, { params: { entity_id: entityId } }),
        axios.get(`${API}/interco/returns`, { params: { entity_id: entityId } }),
        money(`${API}/interco/margin-report`, { params: { entity_id: entityId } }),
      ]);
      setSummary(s.data);
      setRows(t.data || []);
      setAccounts(a.data || []);
      setSettlements(st.data || []);
      setReturns(rt.data || []);
      setMargin(mg.data || null);
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  }, [entityId, fStatus, fRole, canMoney]);

  useEffect(() => { refresh(); }, [refresh]);

  const showMsg = (t) => { setMsg(t); setTimeout(() => setMsg(""), 4000); };

  const LANGKAH_PESAN = {
    confirm: "dikonfirmasi — jurnal terbit di kedua buku PT",
    ship: "ditandai terkirim",
    invoice: "difakturkan (faktur internal terbit)",
    "warehouse-task": "punya tugas gudang — minta gudang menyetujui perpindahannya",
  };

  const advance = async (doc, action) => {
    if (!action) return;
    setBusy(true); setErr("");
    try {
      const r = await axios.post(
        `${API}/interco/transactions/${doc.id}/${action}`, { note: "" });
      if (action === "warehouse-task") {
        showMsg(`Tugas gudang ${r.data?.code || ""} terbit untuk ${doc.number} — `
                + "gudang yang menyetujui perpindahan barangnya");
      } else {
        showMsg(`Transaksi ${doc.number} ${LANGKAH_PESAN[action] || action}`);
      }
      refresh();
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  };

  const retAct = async (ret, action, body = { note: "" }, okMsg = "") => {
    setBusy(true); setErr("");
    try {
      const r = await axios.post(`${API}/interco/returns/${ret.id}/${action}`, body);
      showMsg(okMsg || `Retur ${ret.number} diperbarui`);
      if (action === "warehouse-task") {
        showMsg(`Tugas gudang balik ${r.data?.code || ""} terbit untuk ${ret.number} — `
                + "gudang yang menyetujui pengembalian barangnya");
      }
      refresh();
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  };

  const remind = async (acc) => {
    setBusy(true); setErr("");
    try {
      const r = await axios.post(
        `${API}/interco/accounts/${acc.from_entity_id}/${acc.to_entity_id}/remind`,
        { note: "" });
      const d = r.data || {};
      showMsg(d.deduped
        ? `Pengingat untuk ${d.payer_entity_name} → ${d.payee_entity_name} sudah ada `
          + "dan belum dibaca — tidak dikirim dua kali"
        : `Pengingat terkirim: saldo ${formatCurrency(d.outstanding)} menganggur `
          + `${d.idle_days} hari (batas ${d.limit_days} hari)`);
      refresh();
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-6" data-testid="interco-view">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-[#1D1D1F]">Transaksi Antar Entitas</h1>
          <p className="text-sm text-[#6E6E73] mt-1 max-w-3xl">
            Jual-beli antar-PT dengan harga internal &amp; margin. Dokumen kembar (PO
            internal ↔ SO+Surat Jalan+Invoice) + faktur pajak internal + saldo pasangan
            PT + settlement (netting) + retur — barang fisik tetap lewat jalur gudang.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={refresh} disabled={busy} data-testid="interco-refresh-btn"
                  className="inline-flex items-center gap-2 px-3.5 py-2 text-sm rounded-lg border border-[#E5E5EA] bg-white hover:bg-[#F2F2F5] transition text-[#3C3C43]">
            <RefreshCw size={15} className={busy ? "animate-spin" : ""} />
            Muat ulang
          </button>
          {canWrite && (
            <>
              <button onClick={() => setShowContract({ open: true })}
                      data-testid="interco-open-contract-btn"
                      className="inline-flex items-center gap-2 px-3.5 py-2 text-sm rounded-lg border border-[#E5E5EA] bg-white hover:bg-[#F2F2F5] transition text-[#3C3C43]">
                <Handshake size={15} /> Kontrak Internal
              </button>
              <button onClick={() => setShowSettle({ open: true })}
                      data-testid="interco-open-settle-btn"
                      className="inline-flex items-center gap-2 px-3.5 py-2 text-sm rounded-lg border border-[#0058CC] text-[#0058CC] bg-white hover:bg-[#EAF2FF] transition">
                <Layers size={15} /> Buat Settlement
              </button>
              <button onClick={() => setShowCreate(true)} data-testid="interco-create-btn"
                      className="inline-flex items-center gap-2 px-3.5 py-2 text-sm rounded-lg bg-[#0F172A] text-white hover:bg-black transition">
                <Plus size={15} /> Transaksi Baru
              </button>
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Kpi label="Total Piutang Antar-PT" value={formatCurrency(summary?.total_receivable || 0)}
             hint="jumlah yang wajib ditagih ke PT lain" testid="interco-kpi-receivable" />
        <Kpi label="Total Utang Antar-PT" value={formatCurrency(summary?.total_payable || 0)}
             hint="jumlah yang wajib dibayar ke PT lain" testid="interco-kpi-payable" />
        <Kpi label="Dokumen Terbuka" value={String(summary?.open_documents || 0)}
             hint="transaksi belum lunas" testid="interco-kpi-open" />
        <Kpi label="Margin Belum Terealisasi"
             value={formatCurrency(margin?.totals?.unrealized_margin || 0)}
             hint="dieliminasi di laporan konsolidasi grup" testid="interco-kpi-unrealized" />
      </div>

      {err && <ErrorNotice message={err} onDismiss={() => setErr("")} />}
      {msg && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#E8F6EE] text-[#1B7F4B] text-sm"
             data-testid="interco-msg">
          <CheckCircle2 size={15} /> {msg}
        </div>
      )}

      <div className="border-b border-[#E5E5EA] flex gap-1 flex-wrap">
        {tabs.map((t) => {
          const I = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)} data-testid={`interco-tab-${t.id}`}
                    className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
                      active ? "border-[#0F172A] text-[#0F172A]"
                             : "border-transparent text-[#6E6E73] hover:text-[#1D1D1F]"}`}>
              <I size={15} /> {t.label}
              {t.id === "returns" && returns.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded text-[10px] bg-[#F2F2F5] text-[#5A5A60]">
                  {returns.length}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {tab === "transactions" && (
        <TransactionsPanel
          rows={rows} fStatus={fStatus} fRole={fRole}
          setFStatus={setFStatus} setFRole={setFRole}
          onAdvance={advance} onView={(r) => setDetailId(r.id)}
          onCancel={(r) => setCancelDoc(r)}
          onTax={(r) => setTaxDoc(r)} onReturn={(r) => setReturnDoc(r)}
          canWrite={canWrite}
        />
      )}
      {tab === "balances" && (
        <BalancesPanel
          accounts={accounts} canWrite={canWrite} onRemind={remind}
          onNetting={(a) => setShowSettle({ open: true, from: a.from_entity_id,
                                            to: a.to_entity_id })}
        />
      )}
      {tab === "settlements" && <SettlementsPanel rows={settlements} />}
      {tab === "returns" && (
        <IntercoReturnsPanel
          rows={returns} canWrite={canWrite}
          onApprove={(r) => retAct(r, "approve", { note: "" },
            `Retur ${r.number} disetujui — jurnal pembalik terbit di kedua buku PT`)}
          onTask={(r) => retAct(r, "warehouse-task", { note: "" })}
          onCancel={(r, reason) => retAct(r, "cancel", { reason },
            `Draf retur ${r.number} dibatalkan`)}
        />
      )}
      {tab === "loans" && (
        <IntercoLoansPanel entities={entities} entityId={entityId} canWrite={canWrite} />
      )}
      {tab === "margin" && <IntercoMarginPanel report={margin} entityId={entityId} />}

      {showCreate && (
        <IntercoCreateModal
          entities={entities} currentEntityId={entityId}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); showMsg("Transaksi antar-PT diterbitkan"); refresh(); }}
        />
      )}
      {showSettle?.open && (
        <IntercoSettlementModal
          entities={entities} transactions={rows}
          presetPayerEntityId={showSettle.from || entityId}
          presetPayeeEntityId={showSettle.to || ""}
          onClose={() => setShowSettle(null)}
          onCreated={() => { setShowSettle(null); showMsg("Settlement antar-PT terbit"); refresh(); }}
        />
      )}
      {showContract?.open && (
        <InternalContractWizardModal
          entities={entities} sellerEntityId={showContract.seller || entityId}
          buyerEntityId={showContract.buyer || ""}
          onClose={() => setShowContract(null)}
          onCreated={() => { setShowContract(null); showMsg("Kontrak internal diterbitkan"); refresh(); }}
        />
      )}
      {detailId && (
        <DetailModal onClose={() => setDetailId(null)}
          label="Rincian transaksi antar-PT" testId="interco-detail-modal">
          <IntercoDetailPanel intercoId={detailId} currentUser={currentUser} onClose={() => setDetailId(null)} />
        </DetailModal>
      )}
      {cancelDoc && (
        <IntercoCancelModal
          doc={cancelDoc} onClose={() => setCancelDoc(null)}
          onCancelled={(res) => {
            setCancelDoc(null);
            const n = res?.reversed_journals || 0;
            showMsg(n > 0
              ? `Transaksi dibatalkan — ${n} jurnal dibalik di kedua buku PT`
              : "Draf transaksi dibatalkan");
            refresh();
          }}
        />
      )}
      {taxDoc && (
        <IntercoTaxModal
          doc={taxDoc} onClose={() => setTaxDoc(null)}
          onDone={() => { showMsg("Faktur pajak internal diperbarui"); refresh(); }}
        />
      )}
      {returnDoc && (
        <IntercoReturnModal
          doc={returnDoc} onClose={() => setReturnDoc(null)}
          onCreated={(res) => {
            setReturnDoc(null);
            showMsg(`Retur ${res?.returner?.number || ""} dibuat sebagai draf — minta rekan `
                    + "lain menyetujuinya (pembuat ≠ penyetuju)");
            setTab("returns");
            refresh();
          }}
        />
      )}
    </div>
  );
}

function Kpi({ label, value, hint, testid }) {
  return (
    <div className="rounded-xl border border-[#E5E5EA] bg-white p-4" data-testid={testid}>
      <div className="text-xs uppercase tracking-wide text-[#6E6E73]">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold text-[#1D1D1F]">{value}</div>
      <div className="mt-1 text-xs text-[#8E8E93]">{hint}</div>
    </div>
  );
}
