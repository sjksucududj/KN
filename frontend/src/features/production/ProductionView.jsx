/**
 * ProductionView (R6.4 — Produksi In-House) — BOM (Resep) + Work Order board.
 * Sumber: /api/production/boms, /api/production/work-orders (+ release/complete/cancel),
 * /api/production/summary. Complete WO = konsumsi roll bahan (FEFO) → produksi roll barang jadi
 * (Roll-as-SSOT), dinilai HPP produksi (bahan + overhead). GL-safe (akun Persediaan 1-1300).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Factory, Layers3, ClipboardList, CheckCircle2, Wallet, Plus } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { KpiCard, EmptyState, compactIDR, entityParam } from "../finance/financeShared";
import { Modal, StatusBadge, BOMTable, BOMFormModal, prodPerms } from "./ProductionParts";
import { WOTable, WOCreateModal, WODetailPanel } from "./ProductionWO";
import { askConfirm } from "@/services/confirmService";

export default function ProductionView({ selectedEntity, entities, currentUser }) {
  const perms = useMemo(() => prodPerms(currentUser?.role), [currentUser]);
  const [tab, setTab] = useState("wo");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null); // {msg, tone:'ok'|'err'}

  const [boms, setBoms] = useState([]);
  const [wos, setWos] = useState([]);
  const [summary, setSummary] = useState(null);
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [balances, setBalances] = useState([]);

  // modals
  const [bomModal, setBomModal] = useState(null); // {mode:'create'|'edit', bom}
  const [woModal, setWoModal] = useState(false);
  const [detailWo, setDetailWo] = useState(null);
  const [busyId, setBusyId] = useState("");

  const eParam = useMemo(() => entityParam(selectedEntity), [selectedEntity]);

  // Notifikasi ringan. tone='err' untuk kegagalan (mis. hapus BOM yang masih dipakai WO)
  // agar warna TIDAK menyesatkan (hijau = sukses, merah = gagal).
  const flash = useCallback((msg, tone = "ok") => {
    setNotice({ msg, tone });
    window.clearTimeout(flash._t);
    flash._t = window.setTimeout(() => setNotice(null), tone === "err" ? 6000 : 4000);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [b, w, s] = await Promise.all([
        axios.get(`${API}/production/boms`, { params: eParam }),
        axios.get(`${API}/production/work-orders`, { params: eParam }),
        axios.get(`${API}/production/summary`, { params: eParam }),
      ]);
      setBoms(b.data || []);
      setWos(w.data || []);
      setSummary(s.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data produksi.");
    } finally {
      setLoading(false);
    }
  }, [eParam]);

  const loadRefs = useCallback(async () => {
    try {
      const [p, wh, bal] = await Promise.all([
        axios.get(`${API}/products`),
        axios.get(`${API}/warehouses`),
        axios.get(`${API}/inventory/balances`, { params: eParam }),
      ]);
      setProducts(Array.isArray(p.data) ? p.data : p.data?.items || []);
      setWarehouses(Array.isArray(wh.data) ? wh.data : wh.data?.items || []);
      const bd = bal.data;
      setBalances(Array.isArray(bd) ? bd : bd?.items || bd?.balances || []);
    } catch {
      /* referensi opsional; abaikan */
    }
  }, [eParam]);

  useEffect(() => { load(); loadRefs(); }, [load, loadRefs]);

  // ── actions ───────────────────────────────────────────────────────────────
  const saveBom = async (payload, id) => {
    if (id) await axios.patch(`${API}/production/boms/${id}`, payload);
    else await axios.post(`${API}/production/boms`, { ...payload, entity_id: selectedEntity !== "all" ? selectedEntity : undefined });
    setBomModal(null);
    flash(id ? "BOM diperbarui." : "BOM baru dibuat.");
    load();
  };
  const deleteBom = async (bom) => {
    const ok = await askConfirm({
      title: `Hapus BOM "${bom.name}"?`,
      message: "Resep ini tidak bisa dipakai lagi untuk pesanan produksi baru. Pesanan "
        + "produksi yang sudah berjalan tetap memakai resep yang tersimpan padanya.",
      confirmLabel: "Hapus BOM",
      danger: true,
      testId: "bom-delete-confirm",
    });
    if (!ok) return;
    try {
      await axios.delete(`${API}/production/boms/${bom.id}`);
      flash("BOM dihapus.");
      load();
    } catch (e) { flash(e.response?.data?.detail || "Gagal menghapus BOM.", "err"); }
  };
  const createWo = async (payload) => {
    await axios.post(`${API}/production/work-orders`, { ...payload, entity_id: selectedEntity !== "all" ? selectedEntity : undefined });
    setWoModal(false);
    flash("Work Order dibuat (draft).");
    load();
  };
  const woAction = async (wo, action) => {
    setBusyId(wo.id);
    try {
      const body = action === "cancel" ? { reason: "" } : {};
      const { data } = await axios.post(`${API}/production/work-orders/${wo.id}/${action}`, body);
      const labels = { release: "dirilis", complete: "diselesaikan", cancel: "dibatalkan" };
      flash(`Work Order ${data.wo_number} ${labels[action]}.`);
      if (detailWo && detailWo.id === wo.id) setDetailWo(data);
      load();
    } catch (e) {
      flash(e.response?.data?.detail || `Gagal ${action} Work Order.`, "err");
    } finally { setBusyId(""); }
  };
  const openDetail = async (wo) => {
    try {
      const { data } = await axios.get(`${API}/production/work-orders/${wo.id}`);
      setDetailWo(data);
    } catch { setDetailWo(wo); }
  };

  const activeBoms = useMemo(() => boms.filter((b) => b.status === "active"), [boms]);

  return (
    <div className="space-y-4" data-testid="production-view">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-[#F3EAFB] flex items-center justify-center">
          <Factory size={19} className="text-[#6B219A]" />
        </div>
        <div className="mr-auto">
          <h2 className="text-[16px] font-bold text-[#1C1C1E]">Produksi In-House</h2>
          <p className="text-[11px] text-[#8E8E93]">BOM (resep) & Perintah Kerja · konsumsi bahan → barang jadi (Roll-as-SSOT)</p>
        </div>
        {tab === "wo" && perms.createWo && (
          <button data-testid="wo-add-button" onClick={() => setWoModal(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[#6B219A] px-3 py-2 text-[12px] font-bold text-white hover:bg-[#581680]">
            <Plus size={14} /> Buat Perintah Kerja
          </button>
        )}
        {tab === "bom" && perms.manageBom && (
          <button data-testid="bom-add-button" onClick={() => setBomModal({ mode: "create" })}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[#6B219A] px-3 py-2 text-[12px] font-bold text-white hover:bg-[#581680]">
            <Plus size={14} /> Tambah BOM
          </button>
        )}
        <button data-testid="production-refresh" onClick={() => { load(); loadRefs(); }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#E2E2E7] bg-white px-3 py-2 text-[12px] font-semibold text-[#3A3A3C] hover:bg-[#FAFAFA]">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Muat ulang
        </button>
      </div>

      {notice && (
        <div data-testid="production-notice"
             className={`rounded-lg border px-3 py-2 text-[12px] font-semibold ${
               notice.tone === "err"
                 ? "border-[#F3D6D6] bg-[#FDECEC] text-[#C0392B]"
                 : "border-[#D6EBDD] bg-[#EAF6EF] text-[#1B7F4B]"}`}>
          {notice.msg}
        </div>
      )}
      {error && <ErrorNotice message={error} onRetry={load} />}

      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard testId="prod-kpi-boms" label="Total BOM" value={summary?.boms ?? boms.length} icon={Layers3} accent="#6B219A" sub={`${activeBoms.length} aktif`} />
        <KpiCard testId="prod-kpi-open" label="WO Terbuka" value={summary?.open ?? 0} icon={ClipboardList} accent="#C77700" sub="draf + dirilis" />
        <KpiCard testId="prod-kpi-done" label="WO Selesai" value={summary?.completed ?? 0} icon={CheckCircle2} accent="#1B7F4B" />
        <KpiCard testId="prod-kpi-value" label="Nilai Produksi" value={`Rp ${compactIDR(summary?.produced_value || 0)}`} icon={Wallet} accent="#0058CC" sub={`${summary?.produced_qty ?? 0} unit`} />
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-[#EFEFF4]">
        {[{ k: "wo", label: "Perintah Kerja", icon: ClipboardList }, { k: "bom", label: "BOM / Resep", icon: Layers3 }].map((t) => (
          <button key={t.k} data-testid={`prod-tab-${t.k}`} onClick={() => setTab(t.k)}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-2 text-[12px] font-bold border-b-2 -mb-px transition ${tab === t.k ? "border-[#6B219A] text-[#6B219A]" : "border-transparent text-[#8E8E93] hover:text-[#3A3A3C]"}`}>
            <t.icon size={14} /> {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === "wo" ? (
        wos.length === 0 && !loading ? (
          <EmptyState icon={ClipboardList} title="Belum ada Perintah Kerja" hint="Buat Perintah Kerja dari BOM aktif untuk memproduksi barang jadi." testId="wo-empty" />
        ) : (
          <WOTable wos={wos} perms={perms} busyId={busyId} onDetail={openDetail} onAction={woAction} />
        )
      ) : (
        boms.length === 0 && !loading ? (
          <EmptyState icon={Layers3} title="Belum ada BOM" hint="Tambahkan resep produksi (output + komponen bahan) untuk mulai." testId="bom-empty" />
        ) : (
          <BOMTable boms={boms} perms={perms} onEdit={(b) => setBomModal({ mode: "edit", bom: b })} onDelete={deleteBom} />
        )
      )}

      {/* Modals */}
      {bomModal && (
        <Modal title={bomModal.mode === "edit" ? "Ubah BOM" : "BOM Baru"} onClose={() => setBomModal(null)}>
          <BOMFormModal bom={bomModal.bom} products={products} onCancel={() => setBomModal(null)} onSave={saveBom} />
        </Modal>
      )}
      {woModal && (
        <Modal title="Perintah Kerja Baru" onClose={() => setWoModal(false)}>
          <WOCreateModal boms={activeBoms} warehouses={warehouses} balances={balances}
                         onCancel={() => setWoModal(false)} onCreate={createWo} />
        </Modal>
      )}
      {detailWo && (
        <Modal title={`Perintah Kerja ${detailWo.wo_number}`} onClose={() => setDetailWo(null)} wide>
          <WODetailPanel wo={detailWo} perms={perms} busy={busyId === detailWo.id}
                         onAction={(a) => woAction(detailWo, a)} onClose={() => setDetailWo(null)} />
        </Modal>
      )}
    </div>
  );
}
