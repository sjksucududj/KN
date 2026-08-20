/**
 * FASE G-7 — **KONTRABON** (siklus tukar faktur supplier).
 *
 * Masalah nyata yang diselesaikan layar ini: supplier tekstil tidak ditagih per surat
 * jalan. Mereka datang sekali per siklus membawa setumpuk faktur, lalu terjadi ritual
 * *tukar faktur*. Sebelum fase ini sistem hanya bisa membayar PER faktur (12 faktur =
 * 12 transaksi kas), tidak bisa menjawab “GR mana yang belum ditagih?”, dan seluruh
 * potongan (retur beli, uang muka, denda, selisih 3-way) hidup di luar sistem.
 *
 * Tiga tab = tiga pertanyaan lapangan:
 *   1. Daftar Kontrabon      — “siklus mana yang sedang jalan & sudah sampai mana?”
 *   2. GR Belum Ditagih      — “barang mana yang sudah masuk tapi belum ditagih?”
 *   3. Jadwal Tukar Faktur   — “supplier mana yang datang hari apa, siap berapa?”
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  RefreshCw, Receipt, Plus, AlertTriangle, CheckCircle2, FilterX, Search,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";
import { apiErrorText } from "../../../utils/apiError";
import { entityShortById } from "../../../utils/entityLabel";
import ContraBonListTable from "./ContraBonListTable";
import ContraBonDetailPanel from "./ContraBonDetailPanel";
import ContraBonCreateWizard from "./ContraBonCreateWizard";
import UnbilledReceiptsTab from "./UnbilledReceiptsTab";
import ExchangeSchedulesTab from "./ExchangeSchedulesTab";
import ExchangeScheduleModal from "./ExchangeScheduleModal";
import { STATUS_FILTERS } from "./contraBonApi";

const TABS = [
  { id: "list", label: "Daftar Kontrabon" },
  { id: "unbilled", label: "GR Belum Ditagih" },
  { id: "schedules", label: "Jadwal Tukar Faktur" },
];

export default function ContraBonsView({ currentUser, selectedEntity, entities = [] }) {
  const [tab, setTab] = useState("list");
  const [meta, setMeta] = useState(null);
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({});
  const [unbilled, setUnbilled] = useState(null);
  const [schedules, setSchedules] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [active, setActive] = useState(null);
  const [wizard, setWizard] = useState(null);        // {presetSupplierId} | null
  const [exchangeRow, setExchangeRow] = useState(null);
  const [fStatus, setFStatus] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [msgKind, setMsgKind] = useState("success");

  const role = (currentUser?.role || "").toLowerCase();
  const canWrite = ["admin", "manager"].includes(role);

  /**
   * Bilah konfirmasi. Pengatur waktu DISIMPAN lalu dibatalkan sebelum pesan baru:
   * tanpa ini, pengatur waktu pesan LAMA ikut menghapus pesan BARU (terukur saat uji
   * layar ini: konfirmasi "Jadwal tukar faktur … disimpan" hanya tampil ±0,5 detik
   * karena timer pesan sebelumnya jatuh tempo). Akibatnya petugas menekan Simpan,
   * datanya benar-benar tersimpan, tetapi layar seperti tidak menjawab apa pun.
   */
  const msgTimer = useRef(null);
  const notify = useCallback((m, kind = "success") => {
    if (msgTimer.current) clearTimeout(msgTimer.current);
    setMsg(m); setMsgKind(kind);
    msgTimer.current = setTimeout(() => setMsg(""), kind === "warning" ? 14000 : 9000);
  }, []);
  useEffect(() => () => { if (msgTimer.current) clearTimeout(msgTimer.current); }, []);

  /** Semua penolakan backend dinormalkan jadi KALIMAT (INV-UI-03 / KN-G9-ERR-SILENT). */
  const fail = useCallback((e) => setErr(apiErrorText(e)), []);

  const loadRefs = useCallback(async () => {
    try {
      const m = await axios.get(`${API}/contra-bons/meta`);
      setMeta(m.data || null);
    } catch (e) { fail(e); }
    /**
     * Daftar supplier HANYA dipakai wizard "Kontrabon baru", jadi ia diambil terpisah
     * dan kegagalannya TIDAK boleh memerahkan layar. Peran Gudang sengaja tidak punya
     * izin `supplier.view` (mereka hanya memantau kontrabon & GR belum ditagih), dan
     * dulu panggilan ini membuat bilah merah "Permission ditolak: supplier.view"
     * menyambut mereka di layar yang justru memang boleh mereka buka.
     */
    if (!canWrite) return;
    try {
      const s = await axios.get(`${API}/suppliers`);
      setSuppliers(Array.isArray(s.data) ? s.data : (s.data?.items || []));
    } catch { /* wizard tidak tersedia bagi peran ini — bukan kegagalan layar */ }
  }, [fail, canWrite]);

  const loadList = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const [ls, sm, ct] = await Promise.all([
        axios.get(`${API}/contra-bons`, {
          params: { ...(fStatus ? { status: fStatus } : {}), ...(q ? { q } : {}) },
        }),
        axios.get(`${API}/contra-bons/summary`),
        axios.get(`${API}/contra-bons/status-counts`),
      ]);
      const list = Array.isArray(ls.data) ? ls.data : [];
      setRows(list);
      setSummary(sm.data || null);
      setCounts(ct.data || {});
      // Panel detail selalu mengikuti data terbaru dari server.
      setActive((cur) => (cur ? list.find((r) => r.id === cur.id) || cur : null));
    } catch (e) { fail(e); } finally { setLoading(false); }
  }, [fStatus, q, fail]);

  const loadUnbilled = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/contra-bons/unbilled-receipts`);
      setUnbilled(r.data || null);
    } catch (e) { fail(e); } finally { setLoading(false); }
  }, [fail]);

  const loadSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/contra-bons/exchange-schedules`);
      setSchedules(r.data || null);
    } catch (e) { fail(e); } finally { setLoading(false); }
  }, [fail]);

  useEffect(() => { loadRefs(); }, [loadRefs, selectedEntity]);
  useEffect(() => { loadList(); }, [loadList, selectedEntity]);
  useEffect(() => { if (tab === "unbilled") loadUnbilled(); }, [tab, loadUnbilled, selectedEntity]);
  useEffect(() => { if (tab === "schedules") loadSchedules(); }, [tab, loadSchedules, selectedEntity]);

  const refreshAll = useCallback(async () => {
    await loadList();
    if (tab === "unbilled") await loadUnbilled();
    if (tab === "schedules") await loadSchedules();
  }, [tab, loadList, loadUnbilled, loadSchedules]);

  async function runReminder() {
    setBusy("reminder"); setErr("");
    try {
      const r = await axios.post(`${API}/contra-bons/run-reminder`, {});
      const n = (r.data || {}).notifications || 0;
      notify(n
        ? `Pengingat dijalankan: ${n} notifikasi terbit (jadwal tukar faktur H-n & kontrabon `
          + "yang menunggu terlalu lama)."
        : "Pengingat dijalankan — tidak ada yang perlu diingatkan hari ini (atau sudah "
          + "diingatkan sebelumnya hari ini).");
      await loadSchedules();
    } catch (e) { fail(e); } finally { setBusy(""); }
  }

  const openCreate = (supplierId = "") => {
    if (!canWrite) {
      setErr("Peran Anda tidak berwenang membuat kontrabon — hubungi Keuangan atau Manajer.");
      return;
    }
    setWizard({ presetSupplierId: supplierId });
  };

  const statusOptions = useMemo(() => STATUS_FILTERS.map((s) => ({
    ...s,
    label: s.value && counts[s.value] ? `${s.label} (${counts[s.value]})` : s.label,
  })), [counts]);
  const filterOn = !!(fStatus || q);

  return (
    <div className="p-5" data-testid="contra-bons-view">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-[17px] font-bold text-[#1C1C1E]">
            <Receipt size={18} className="text-[#0058CC]" /> Kontrabon · Tukar Faktur Supplier
          </h2>
          <p className="text-[12px] text-[#6B6B73]">
            Banyak faktur satu supplier digabung jadi SATU tanda terima dan SATU pembayaran.
            Potongan retur beli, uang muka, denda, dan selisih 3-way ikut masuk sistem —
            tidak lagi dihitung di kertas.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className="secondary-button" data-testid="cb-refresh" onClick={refreshAll}>
            <RefreshCw size={14} className={loading ? "spin" : ""} /> Muat ulang
          </button>
          {canWrite && (
            <button className="primary-button" data-testid="cb-new" onClick={() => openCreate("")}>
              <Plus size={14} /> Kontrabon baru
            </button>
          )}
        </div>
      </div>

      {err && <ErrorNotice message={err} onRetry={refreshAll} onDismiss={() => setErr("")}
        testId="cb-error" />}
      {msg && (
        <div className={`notice-bar ${msgKind} mb-3`} data-testid="cb-notice">
          {msgKind === "warning" ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
          {" "}{msg}
        </div>
      )}

      {summary && (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6"
          data-testid="cb-summary">
          <div className="stat-card">
            <p className="stat-label">Menunggu tindakan</p>
            <p className="stat-value text-[#B26A00]" data-testid="cb-kpi-waiting">
              {summary.waiting_count}
            </p>
            <p className="text-[10px] text-[#8E8E93]">
              {formatCurrency(summary.waiting_value)} diajukan / terverifikasi
            </p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Dijadwalkan bayar</p>
            <p className="stat-value text-[#0F6B52]" data-testid="cb-kpi-scheduled">
              {summary.scheduled_count}
            </p>
            <p className="text-[10px] text-[#8E8E93] tabular-nums">{formatCurrency(summary.scheduled_value)}</p>
          </div>
          <div className={`stat-card ${summary.due_soon_count ? "ring-1 ring-[#FFE0B2]" : ""}`}>
            <p className="stat-label">Jatuh tempo ≤ 7 hari</p>
            <p className="stat-value text-[#0058CC]" data-testid="cb-kpi-duesoon">
              {summary.due_soon_count}
            </p>
            <p className="text-[10px] text-[#8E8E93] tabular-nums">{formatCurrency(summary.due_soon_value)}</p>
          </div>
          <div className={`stat-card ${summary.disputed_count ? "ring-1 ring-[#F3C9C7]" : ""}`}>
            <p className="stat-label">Sengketa</p>
            <p className={`stat-value ${summary.disputed_count ? "text-[#C0392B]" : "text-[#1B7F4B]"}`}
              data-testid="cb-kpi-disputed">{summary.disputed_count}</p>
            <p className="text-[10px] text-[#8E8E93] tabular-nums">{formatCurrency(summary.disputed_value)}</p>
          </div>
          <div className={`stat-card ${summary.overdue_count ? "ring-1 ring-[#F3C9C7]" : ""}`}>
            <p className="stat-label">Lewat batas waktu</p>
            <p className={`stat-value ${summary.overdue_count ? "text-[#C0392B]" : "text-[#1B7F4B]"}`}
              data-testid="cb-kpi-overdue">{summary.overdue_count}</p>
            <p className="text-[10px] text-[#8E8E93]">batas {summary.sla_days} hari</p>
          </div>
          <button className="stat-card text-left" data-testid="cb-kpi-unbilled"
            onClick={() => setTab("unbilled")}>
            <p className="stat-label">GR belum ditagih</p>
            <p className="stat-value text-[#8C4A00]">
              {formatCurrency(summary.unbilled_gr_value)}
            </p>
            <p className="text-[10px] text-[#8E8E93]">
              {summary.unbilled_gr_po_count} PO
              {summary.unbilled_gr_overdue ? ` · ${summary.unbilled_gr_overdue} tertunggak` : ""}
            </p>
          </button>
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-1.5" data-testid="cb-tabs">
        {TABS.map((t) => (
          <button key={t.id} data-testid={`cb-tab-${t.id}`} onClick={() => setTab(t.id)}
            className={`rounded-full border px-3 py-1.5 text-[12px] ${
              tab === t.id
                ? "border-[#0058CC] bg-[#EAF2FF] font-bold text-[#0058CC]"
                : "border-[#E5E5EA] bg-white text-[#6B6B73] hover:border-[#CBDCF7]"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "list" && (
        <>
          <div className="mb-3 flex flex-wrap items-end gap-3 rounded-lg border border-[#E5E5EA] bg-[#FAFBFC] px-3 py-2"
            data-testid="cb-filter-bar">
            <div className="min-w-[210px]">
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Status</label>
              <KNSelect data-testid="cb-filter-status" value={fStatus} onValueChange={setFStatus}
                options={statusOptions} className="field" />
            </div>
            <div className="min-w-[240px]">
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Cari nomor / supplier
              </label>
              <div className="relative">
                <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
                <input data-testid="cb-filter-q" className="input-field w-full pl-7" value={q}
                  onChange={(e) => setQ(e.target.value)} placeholder="KSC/CB-00001 atau Solo Weave" />
              </div>
            </div>
            {filterOn && (
              <button className="secondary-button" data-testid="cb-filter-clear"
                onClick={() => { setFStatus(""); setQ(""); }}>
                <FilterX size={14} /> Bersihkan filter
              </button>
            )}
            <span className="text-[11px] text-[#6B6B73]" data-testid="cb-filter-count">
              {loading ? "Memuat…" : `${rows.length} kontrabon ditampilkan`}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <ContraBonListTable rows={rows} loading={loading} activeId={active?.id}
              onOpen={setActive} />
            {active
              ? (
                <ContraBonDetailPanel cb={active} meta={meta} currentUser={currentUser}
                  entityLabel={entityShortById(entities, active.entity_id, "")}
                  onClose={() => setActive(null)}
                  onChanged={async (updated) => { setActive(updated); await loadList(); }}
                  onError={fail} onNotify={notify} />
              )
              : (
                <div className="rounded-lg border border-dashed border-[#E5E5EA] bg-white px-4 py-10 text-center"
                  data-testid="cb-detail-empty">
                  <p className="text-[13px] font-semibold text-[#1C1C1E]">
                    Pilih satu kontrabon untuk melihat detailnya.
                  </p>
                  <p className="mt-1 text-[12px] text-[#6B6B73]">
                    Panel ini menampilkan faktur yang ditukar, selisih 3-way beserta keputusannya,
                    potongan, pembayaran, tanda terima yang bisa ditandatangani, dan jejak waktu.
                  </p>
                </div>
              )}
          </div>
        </>
      )}

      {tab === "unbilled" && (
        <UnbilledReceiptsTab data={unbilled} loading={loading} canWrite={canWrite}
          onCreateFor={(sid) => openCreate(sid)} />
      )}

      {tab === "schedules" && (
        <ExchangeSchedulesTab data={schedules} loading={loading} busy={busy} canWrite={canWrite}
          onEdit={(row) => setExchangeRow(row)} onCreateFor={(sid) => openCreate(sid)}
          onRunReminder={runReminder} />
      )}

      <p className="mt-3 flex items-start gap-1 text-[11px] text-[#9A9BA3]">
        <AlertTriangle size={11} className="mt-[2px] shrink-0" />
        Satu faktur hanya boleh berada di satu kontrabon berjalan, dan satu nota debit / uang muka
        hanya boleh dipotong sekali — dijaga invarian INV-CB-01..04. Toleransi 3-way, ambang
        persetujuan, dan jadwal pengingat diatur di Pengaturan → Kontrabon.
      </p>

      {wizard && (
        <ContraBonCreateWizard suppliers={suppliers} presetSupplierId={wizard.presetSupplierId}
          selectedEntity={selectedEntity} onClose={() => setWizard(null)}
          onCreated={async (cb, failed = []) => {
            setWizard(null);
            setTab("list");
            setActive(cb);
            const ded = (cb.deductions || []).length;
            notify(`Kontrabon ${cb.number} terbit — ${(cb.bills || []).length} faktur digabung`
              + (ded ? `, ${ded} potongan langsung menempel` : "")
              + `, nilai bersih ${formatCurrency((cb.totals || {}).net_payable)}.`);
            // Potongan/pengajuan yang DITOLAK backend tidak boleh hilang tanpa jejak:
            // kontrabonnya sudah terbit, jadi pengguna harus tahu bagian mana yang gagal.
            if (failed.length) {
              setErr(`Kontrabon ${cb.number} sudah terbit, tetapi ${failed.length} langkah `
                + `lanjutan ditolak: ${failed.join(" · ")}`);
            }
            await loadList();
          }}
          onError={fail} />
      )}

      {exchangeRow && meta && (
        <ExchangeScheduleModal row={exchangeRow} meta={meta} onClose={() => setExchangeRow(null)}
          onSaved={async (res) => {
            setExchangeRow(null);
            notify(`Jadwal tukar faktur ${res.supplier_name} disimpan: ${res.schedule_label}`
              + (res.next_exchange_date ? ` · berikutnya ${res.next_exchange_date}.` : "."));
            await loadSchedules();
          }}
          onError={fail} />
      )}
    </div>
  );
}
