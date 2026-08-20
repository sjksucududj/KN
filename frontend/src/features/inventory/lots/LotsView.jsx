/**
 * LotsView (FASE C · D-10/D-26/D-27) — layar “Lot & Silsilah”.
 *
 * Masalah yang dijawab (KN_18 PS-10): lot sebelumnya hanya string di roll, tanpa
 * titik input jelas dan tanpa silsilah — sehingga traceability & recall tidak bisa
 * dipakai. Fase C menaikkan lot menjadi ENTITAS (`inventory_lots`) dengan:
 *   • penomoran per entitas `KSC/LOT-YYMM-####` (D-26, deletion-safe),
 *   • pembentukan otomatis saat penerimaan/makloon/produksi (granularitas batch, D-10),
 *   • aksi genealogi split / merge / rework (induk–anak dua arah, bebas siklus),
 *   • laporan recall (lot → roll → SO → pelanggan) & label/QR,
 *   • kebijakan penegakan yang bisa diubah tanpa deploy (D-27: peringatan / blokir).
 *
 * Nav: Gudang → Stok & ATP → Lot & Silsilah (admin/manager/warehouse/sales-view).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Layers3, Plus, RefreshCw } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import PaginationBar from "../../../components/PaginationBar";
import useDomainEnums from "../../../hooks/useDomainEnums";
import LotDetailPanel from "./LotDetailPanel";
import { CreateLotModal, LotLabelModal, LotStatusModal, MergeLotModal, ReworkLotModal,
         SplitLotModal } from "./LotActionModals";
import { LotFilters, LotStatCards, LotTable, UnassignedRollsCard } from "./LotParts";
import ConfigRedirectCard from "../../settings/config/ConfigRedirectCard";
import { errText, lotApi } from "./lotApi";

const EMPTY_FILTER = { q: "", source: "", lot_status: "", stage: "", warehouse_id: "" };

export default function LotsView({ user, products = [], warehouses = [], entityId }) {
  const { options, labelOf } = useDomainEnums();
  const canEdit = user?.role === "admin" || user?.role === "manager" || user?.role === "warehouse";
  const canConfig = user?.role === "admin" || user?.role === "manager";

  const [lots, setLots] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filter, setFilter] = useState(EMPTY_FILTER);
  const [applied, setApplied] = useState(EMPTY_FILTER);
  const [stats, setStats] = useState(null);
  const [unassigned, setUnassigned] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [flash, setFlash] = useState("");
  const [fixBusy, setFixBusy] = useState(false);

  // detail
  const [activeId, setActiveId] = useState("");
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [tab, setTab] = useState("ringkasan");
  const [genealogy, setGenealogy] = useState(null);
  const [genLoading, setGenLoading] = useState(false);
  const [recall, setRecall] = useState(null);
  const [recallLoading, setRecallLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [modal, setModal] = useState("");   // split | merge | rework | status | create | label
  const [makloons, setMakloons] = useState([]);

  const params = useMemo(() => {
    const p = { page, page_size: pageSize };
    Object.entries(applied).forEach(([k, v]) => { if (v) p[k] = v; });
    if (entityId && entityId !== "all") p.entity_id = entityId;
    return p;
  }, [applied, page, pageSize, entityId]);

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const scope = (entityId && entityId !== "all") ? { entity_id: entityId } : {};
      const [rows, st, un] = await Promise.all([
        lotApi.list(params),
        lotApi.stats(scope),
        lotApi.unassignedRolls({ ...scope, limit: 50 }).catch(() => ({ rolls: [], total: 0 })),
      ]);
      const items = Array.isArray(rows) ? rows : rows.items || [];
      setLots(items);
      setTotal(Array.isArray(rows) ? items.length : rows.total ?? items.length);
      setStats(st);
      setUnassigned(un);
    } catch (e) {
      setErr(errText(e, "Gagal memuat daftar lot."));
    } finally { setLoading(false); }
  }, [params, entityId]);

  useEffect(() => { load(); }, [load]);

  // ── FASE P6 — Unduh CSV ────────────────────────────────────────────────────
  // Layar ini memegang paginasinya SENDIRI (bukan `usePagedList`), jadi penyusur
  // halamannya ditulis di sini — tetapi tetap memakai `lotApi.list` dengan filter
  // `applied` + `entityId` YANG SAMA seperti daftar di layar, supaya jumlah baris di
  // berkas tidak pernah berbeda dari angka "… dari N" di bilah paginasi.
  const fetchAllLots = useCallback(async ({ onProgress, isCancelled } = {}) => {
    const base = {};
    Object.entries(applied).forEach(([k, v]) => { if (v) base[k] = v; });
    if (entityId && entityId !== "all") base.entity_id = entityId;
    const out = [];
    let p = 1;
    for (;;) {
      const rows = await lotApi.list({ ...base, page: p, page_size: 200 });
      const items = Array.isArray(rows) ? rows : rows.items || [];
      out.push(...items);
      const grand = Array.isArray(rows) ? out.length : (rows.total ?? out.length);
      if (typeof onProgress === "function") onProgress(out.length, grand);
      if (items.length === 0 || out.length >= grand || out.length >= 50000) break;
      if (typeof isCancelled === "function" && isCancelled()) break;
      p += 1;
    }
    return out;
  }, [applied, entityId]);

  // Kolom memakai `labelOf` supaya berkasnya memuat kata yang SAMA dengan yang terbaca
  // di tabel (mis. "Kain Greige"), bukan kode internalnya.
  const lotCsvColumns = useMemo(() => [
    { key: "lot_number", header: "Nomor Lot" },
    { key: "sku", header: "SKU" },
    { key: "product_name", header: "Produk" },
    { key: "supplier_lot", header: "Lot Supplier" },
    { key: "dye_lot", header: "Dye Lot" },
    { header: "Tahap", get: (l) => labelOf("stage", l.stage) },
    { header: "Status", get: (l) => labelOf("lot_status", l.lot_status) },
    { key: "roll_count", header: "Jumlah Roll", type: "int" },
    { key: "qty_remaining", header: "Sisa", type: "num" },
    { key: "unit", header: "Satuan" },
    { header: "Sumber", get: (l) => labelOf("lot_source", l.source) },
    { key: "created_at", header: "Dibuat", type: "date" },
  ], [labelOf]);
  useEffect(() => {
    axios.get(`${API}/makloons`).then((r) => setMakloons(Array.isArray(r.data) ? r.data : r.data?.items || []))
      .catch(() => setMakloons([]));
  }, []);

  const openLot = useCallback(async (id, nextTab) => {
    setActiveId(id); setDetailLoading(true); setSaveMsg("");
    if (nextTab) setTab(nextTab);
    try {
      setDetail(await lotApi.detail(id));
    } catch (e) {
      setErr(errText(e, "Gagal memuat detail lot."));
    } finally { setDetailLoading(false); }
  }, []);

  // muat silsilah / recall saat tab dibuka (hemat panggilan)
  useEffect(() => {
    if (!activeId) return;
    if (tab === "silsilah" && !genLoading) {
      setGenLoading(true);
      lotApi.genealogy(activeId).then(setGenealogy)
        .catch((e) => setErr(errText(e, "Gagal memuat silsilah.")))
        .finally(() => setGenLoading(false));
    }
    if (tab === "recall" && !recallLoading) {
      setRecallLoading(true);
      lotApi.recall(activeId).then(setRecall)
        .catch((e) => setErr(errText(e, "Gagal memuat recall.")))
        .finally(() => setRecallLoading(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, activeId]);

  async function saveIdentity(next) {
    setSaving(true); setSaveMsg(""); setErr("");
    try {
      const out = await lotApi.patch(activeId, next);
      setDetail({ ...out, rolls: detail?.rolls || [], parents: detail?.parents || [],
                  children: detail?.children || [] });
      setSaveMsg("Identitas lot tersimpan.");
      await load();
      await openLot(activeId);
    } catch (e) { setErr(errText(e, "Gagal menyimpan identitas lot.")); }
    finally { setSaving(false); }
  }

  async function fixUnassigned() {
    setFixBusy(true); setErr("");
    try {
      const rows = unassigned?.rolls || [];
      const byKey = {};
      rows.forEach((r) => {
        const key = `${r.product_id}|${r.owner_entity_id}|${r.lot || ""}`;
        (byKey[key] = byKey[key] || []).push(r);
      });
      let made = 0;
      for (const group of Object.values(byKey)) {
        const head = group[0];
        const lot = await lotApi.create({
          product_id: head.product_id, owner_entity_id: head.owner_entity_id,
          warehouse_id: head.warehouse_id, source: "migration",
          dye_lot: head.dye_lot || "", note: `Tambal data: lot lama ${head.lot || "(kosong)"}`,
        });
        await lotApi.attachRolls(lot.id, { roll_ids: group.map((r) => r.id), keep_lot_string: true });
        made += 1;
      }
      setFlash(`${made} lot dibentuk untuk menambal ${rows.length} roll tanpa lot.`);
      await load();
    } catch (e) { setErr(errText(e, "Gagal menambal roll tanpa lot.")); }
    finally { setFixBusy(false); }
  }

  function afterAction(msg, focusLotId) {
    setModal(""); setFlash(msg);
    setGenealogy(null); setRecall(null);
    load();
    if (focusLotId) openLot(focusLotId, "silsilah");
    else if (activeId) openLot(activeId);
  }

  const sourceOptions = options("lot_source");
  const statusOptions = options("lot_status");
  const stageOptions = options("stage");
  const processOptions = options("process_type");

  return (
    <div data-testid="lots-view" className="space-y-3">
      <div className="section-card">
        <div className="section-head">
          <div className="min-w-0">
            <h2 className="flex items-center gap-1.5 text-[13px] font-bold">
              <Layers3 size={14} className="text-[#0058CC]" /> Lot & Silsilah
            </h2>
            <p className="text-[10.5px] text-[#6B6B73]">
              Lot = identitas batch (satu lot menaungi banyak roll). Nomor dibuat otomatis per
              entitas <b>KSC/LOT-YYMM-####</b> saat penerimaan barang, hasil makloon, dan produksi
              (keputusan <b>D-10</b>/<b>D-26</b>). Dari sini Anda bisa menelusuri silsilah,
              menjalankan <b>recall</b>, dan mencetak label/QR.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {canEdit && (
              <button data-testid="lot-create-open" className="primary-button !px-2 !py-1 !text-[10.5px]"
                onClick={() => setModal("create")}>
                <span className="flex items-center gap-1"><Plus size={11} /> Buat Lot</span>
              </button>
            )}
            <button data-testid="lots-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={13} />
            </button>
          </div>
        </div>
        <div className="section-body space-y-3">
          {err && (
            <div className="notice-bar danger" data-testid="lots-error">
              <span>{err}</span><button onClick={() => setErr("")}>×</button>
            </div>
          )}
          {flash && (
            <div className="notice-bar" data-testid="lots-flash">
              <span>{flash}</span><button onClick={() => setFlash("")}>×</button>
            </div>
          )}

          <LotStatCards stats={stats} />
          {unassigned?.total > 0 && (
            <UnassignedRollsCard data={unassigned} onFix={fixUnassigned} busy={fixBusy} />
          )}
          {/* FASE G-0 — form "Penegakan Lot" DIHAPUS dari sini; aturannya tunggal
              di Pusat Pengaturan supaya tidak ada dua tempat yang bisa berbeda. */}
          <ConfigRedirectCard
            title="Penegakan lot & ketertelusuran"
            note="Mode peringatan hanya menandai data lot yang belum lengkap; mode blokir menolak penerimaan tanpa nomor lot."
            group="lot"
            testId="lot-config-redirect"
            settings={[
              { key: "lot.enforcement_mode", label: "Mode penegakan lot" },
              { key: "lot.require_supplier_lot", label: "Wajib nomor lot supplier" },
              { key: "lot.require_dye_lot", label: "Wajib dye lot / shade" },
              { key: "lot.status_on_receipt", label: "Status lot saat diterima" },
              { key: "lot.auto_create_on_receiving", label: "Buat lot otomatis saat penerimaan" },
              { key: "lot.number_format", label: "Format nomor lot" },
            ]}
          />

          <div className="rounded-md border border-[#EFF0F2] bg-white">
            <div className="flex flex-wrap items-center gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
              <span className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
                Daftar Lot
              </span>
              <div className="ml-auto">
                <LotFilters filter={filter} setFilter={setFilter} sourceOptions={sourceOptions}
                  statusOptions={statusOptions} stageOptions={stageOptions} warehouses={warehouses}
                  onSearch={() => { setPage(1); setApplied(filter); }} />
              </div>
            </div>
            <LotTable lots={lots} loading={loading} activeId={activeId} labelOf={labelOf}
              onOpen={(l) => openLot(l.id, "ringkasan")} />
            <PaginationBar page={page} pageSize={pageSize} total={total}
              hasMore={page * pageSize < total} loading={loading} label="lot" testId="lot-pager"
              onPrev={() => setPage((p) => Math.max(1, p - 1))}
              onNext={() => setPage((p) => p + 1)}
              onPageSize={(n) => { setPageSize(n); setPage(1); }}
              exportConfig={{ columns: lotCsvColumns, rows: lots,
                fetchAll: fetchAllLots, filename: "lot" }} />
          </div>

          {activeId && (
            <LotDetailPanel lot={detail} loading={detailLoading} genealogy={genealogy}
              genealogyLoading={genLoading} recall={recall} recallLoading={recallLoading}
              tab={tab} setTab={setTab} canEdit={canEdit} labelOf={labelOf}
              onClose={() => { setActiveId(""); setDetail(null); setGenealogy(null); setRecall(null); }}
              onRefresh={() => openLot(activeId)}
              onOpenLot={(id) => { setGenealogy(null); setRecall(null); openLot(id, tab); }}
              onSaveIdentity={saveIdentity} savingIdentity={saving} saveMsg={saveMsg}
              onSplit={() => setModal("split")} onMerge={() => setModal("merge")}
              onRework={() => setModal("rework")} onStatus={() => setModal("status")}
              onLabel={() => setModal("label")} />
          )}
        </div>
      </div>

      {modal === "create" && (
        <CreateLotModal products={products} warehouses={warehouses} sourceOptions={sourceOptions}
          statusOptions={statusOptions} onClose={() => setModal("")}
          onDone={(msg, id) => afterAction(msg, id)} />
      )}
      {modal === "split" && detail && (
        <SplitLotModal lot={detail} rolls={detail.rolls || []} onClose={() => setModal("")}
          onDone={afterAction} />
      )}
      {modal === "merge" && detail && (
        <MergeLotModal lot={detail} onClose={() => setModal("")} onDone={afterAction} />
      )}
      {modal === "rework" && detail && (
        <ReworkLotModal lot={detail} rolls={detail.rolls || []} processOptions={processOptions}
          stageOptions={stageOptions} makloons={makloons} onClose={() => setModal("")}
          onDone={afterAction} />
      )}
      {modal === "status" && detail && (
        <LotStatusModal lot={detail} statusOptions={statusOptions} onClose={() => setModal("")}
          onDone={afterAction} />
      )}
      {modal === "label" && detail && (
        <LotLabelModal lot={detail} rolls={detail.rolls || []} onClose={() => setModal("")} />
      )}
    </div>
  );
}
