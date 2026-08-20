/**
 * WarehouseMasterView (FASE E-4 · E4.1) — layar MASTER GUDANG.
 *
 * Dulu gudang dikelola dari tab generik "Warehouse" di Master Data: formulir
 * tanpa aturan pemakaian, dan tombol "Update" yang hanya menyimpan kota. Setelah
 * keputusan pemilik #3 (ada gudang bersama & ada gudang khusus badan usaha),
 * gudang punya aturan yang berdampak pada stok dan uang — jadi ia butuh layarnya
 * sendiri, bukan satu baris di daftar serba-ada.
 *
 * Yang dijawab layar ini, dalam urutan pertanyaan pemilik:
 *   1. "Gudang apa saja yang ada, dan mana yang boleh dipakai badan usaha ini?"
 *      → kolom MODE + penyaring "Boleh dipakai / Semua".
 *   2. "Isi gudang ini punya siapa?" → kolom pemilik stok (roll per badan usaha).
 *   3. "Bagaimana mengubahnya tanpa mengurung barang orang?"
 *      → drawer mode dengan pagar & pintasan (WarehouseModeDrawer).
 *
 * Pemilih gudang di seluruh aplikasi TIDAK perlu diubah: `GET /api/warehouses`
 * sudah tersaring per badan usaha di server, jadi gudang khusus milik badan usaha
 * lain tidak pernah muncul sebagai pilihan.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Warehouse, Search, RefreshCw, Plus, Save, X, Building2, Users, MapPin,
  CheckCircle2, Boxes, Settings2, Ban, RotateCcw,
} from "lucide-react";

import ErrorNotice from "../../../components/ErrorNotice";
import WarehouseModeBadge from "../../../components/WarehouseModeBadge";
import WarehouseStructure from "../inventory/WarehouseStructure";
import { useEntityScope } from "../../../context/EntityScopeContext";
import { entityFullById, entityShort } from "../../../utils/entityLabel";
import { formatQty } from "../../../utils/formatters";
import {
  createWarehouse, deactivateWarehouse, errText, listAllWarehouses, patchWarehouse,
  warehouseOccupancy,
} from "./warehouseApi";
import WarehouseModeDrawer from "./WarehouseModeDrawer";

const EMPTY_FORM = {
  code: "", name: "", city: "", bin_code: "A1-01", bin_capacity: 1000,
  lat: "", lng: "", sharing_mode: "dedicated",
};

const SCOPE_FILTERS = [
  { key: "usable", label: "Boleh dipakai" },
  { key: "all", label: "Semua gudang" },
];

export default function WarehouseMasterView({ entities = [], selectedEntity, currentUser }) {
  const { canWrite, writeBlockHint } = useEntityScope();
  const canManage = ["admin", "manager", "warehouse"].includes(currentUser?.role);
  const [rows, setRows] = useState([]);
  const [occupancy, setOccupancy] = useState({});     // { [warehouseId]: owners[] }
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [q, setQ] = useState("");
  const [scope, setScope] = useState("usable");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [modeFor, setModeFor] = useState(null);

  const activeEntityLabel = entityFullById(entities, selectedEntity);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const list = await listAllWarehouses();
      setRows(list);
      // Isi gudang dimuat paralel — dipakai kolom "pemilik stok" supaya keputusan
      // mode gudang tidak diambil buta.
      const pairs = await Promise.all(list.map(async (w) => {
        try { return [w.id, (await warehouseOccupancy(w.id)).owners || []]; }
        catch { return [w.id, []]; }
      }));
      setOccupancy(Object.fromEntries(pairs));
    } catch (e) {
      setError(errText(e, "Gagal memuat daftar gudang."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load, selectedEntity]);

  const shown = useMemo(() => {
    const term = q.trim().toLowerCase();
    return rows.filter((w) => {
      if (scope === "usable" && w.usable_by_active === false) return false;
      if (!term) return true;
      return `${w.code} ${w.name} ${w.city} ${w.sharing_label}`.toLowerCase().includes(term);
    });
  }, [rows, q, scope]);

  const stats = useMemo(() => ({
    total: rows.length,
    shared: rows.filter((w) => w.sharing_mode !== "dedicated").length,
    dedicated: rows.filter((w) => w.sharing_mode === "dedicated").length,
    usable: rows.filter((w) => w.usable_by_active !== false).length,
  }), [rows]);

  const submit = async () => {
    setError(""); setNotice("");
    if (!form.code.trim() || !form.name.trim()) {
      setError("Kode dan nama gudang wajib diisi."); return;
    }
    setSaving(true);
    try {
      const payload = {
        code: form.code.trim(), name: form.name.trim(), city: form.city.trim(),
        bin_code: form.bin_code || "A1-01",
        bin_capacity: Number(form.bin_capacity) || 0,
        lat: form.lat === "" ? null : Number(form.lat),
        lng: form.lng === "" ? null : Number(form.lng),
        sharing_mode: form.sharing_mode,
        entity_ids: form.sharing_mode === "dedicated" && selectedEntity && selectedEntity !== "all"
          ? [selectedEntity] : [],
      };
      const created = await createWarehouse(payload);
      setNotice(form.sharing_mode === "dedicated"
        ? `${created.name} dibuat sebagai gudang khusus ${entityShort(entities.find((e) => e.id === selectedEntity))}.`
        : `${created.name} dibuat sebagai gudang bersama.`);
      setForm(EMPTY_FORM); setShowCreate(false);
      load();
    } catch (e) {
      setError(errText(e, "Gagal menyimpan gudang."));
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (w) => {
    setError(""); setNotice("");
    try {
      if (w.active === false) {
        await patchWarehouse(w.id, { active: true });
        setNotice(`${w.name} diaktifkan kembali.`);
      } else {
        await deactivateWarehouse(w.id);
        setNotice(`${w.name} dinonaktifkan — tidak lagi muncul di pemilih gudang.`);
      }
      load();
    } catch (e) {
      setError(errText(e, "Gagal mengubah status gudang."));
    }
  };

  return (
    <div data-testid="warehouse-master-view">
      <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi testId="wh-kpi-total" label="Total gudang" value={stats.total} icon={Warehouse} />
        <Kpi testId="wh-kpi-shared" label="Bersama" value={stats.shared} icon={Users} tone="text-[#0058CC]" />
        <Kpi testId="wh-kpi-dedicated" label="Khusus badan usaha" value={stats.dedicated} icon={Building2} tone="text-[#6B219A]" />
        <Kpi testId="wh-kpi-usable" label={`Boleh dipakai ${activeEntityLabel}`} value={stats.usable} icon={CheckCircle2} tone="text-[#1B7F4B]" />
      </div>

      <section className="section-card">
        <div className="section-head flex-wrap gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="kicker">Master Gudang</span>
            <h2 data-testid="wh-master-title">Gudang bersama &amp; gudang khusus badan usaha</h2>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1" data-testid="wh-scope-filter">
              {SCOPE_FILTERS.map((s) => (
                <button key={s.key} type="button" data-testid={`wh-scope-${s.key}`}
                  onClick={() => setScope(s.key)}
                  className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                    scope === s.key ? "bg-[#007AFF] text-white"
                      : "border border-[#E5E5EA] bg-white text-[#6B6B73] hover:border-[#007AFF]"}`}>
                  {s.label}
                </button>
              ))}
            </div>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="wh-search" className="field w-[220px] py-1.5 pl-8 text-[12px]"
                placeholder="Cari kode / nama / kota" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            {canManage && (
              <button data-testid="wh-toggle-create" className="secondary-button"
                onClick={() => setShowCreate((v) => !v)}>
                {showCreate ? <X size={14} /> : <Plus size={14} />} {showCreate ? "Tutup form" : "Gudang baru"}
              </button>
            )}
            <button data-testid="wh-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="wh-error" />
          {notice && (
            <div data-testid="wh-notice"
              className="mb-3 flex items-center gap-2 rounded-md border border-[#BDE5CC] bg-[#E6F6EC] px-3 py-2 text-[12px] text-[#1B7F4B]">
              <CheckCircle2 size={14} />{notice}
              <button className="ml-auto" onClick={() => setNotice("")} aria-label="Tutup"><X size={13} /></button>
            </div>
          )}

          {showCreate && canManage && (
            <div className="mb-3 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3" data-testid="wh-create-form">
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Gudang baru</p>
              <div className="grid gap-2 md:grid-cols-2">
                {[["code", "Kode gudang (mis. WH-SMG)"], ["name", "Nama gudang"], ["city", "Kota"],
                  ["bin_code", "Kode bin pertama"]].map(([key, ph]) => (
                  <input key={key} data-testid={`wh-form-${key}`} className="field" placeholder={ph}
                    value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
                ))}
                <input data-testid="wh-form-bin_capacity" className="field" type="number"
                  placeholder="Kapasitas bin" value={form.bin_capacity}
                  onChange={(e) => setForm({ ...form, bin_capacity: e.target.value })} />
                <div className="grid grid-cols-2 gap-2">
                  <input data-testid="wh-form-lat" className="field" type="number" step="0.0001"
                    placeholder="Latitude (opsional)" value={form.lat}
                    onChange={(e) => setForm({ ...form, lat: e.target.value })} />
                  <input data-testid="wh-form-lng" className="field" type="number" step="0.0001"
                    placeholder="Longitude (opsional)" value={form.lng}
                    onChange={(e) => setForm({ ...form, lng: e.target.value })} />
                </div>
              </div>

              <div className="mt-2 grid gap-1.5">
                <p className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Siapa yang boleh memakai?</p>
                <div className="grid gap-1.5 md:grid-cols-2">
                  <button type="button" data-testid="wh-form-mode-dedicated"
                    onClick={() => setForm({ ...form, sharing_mode: "dedicated" })}
                    className={`rounded-md border px-2.5 py-2 text-left text-[12px] ${
                      form.sharing_mode === "dedicated" ? "border-[#6B219A] bg-[#F3E9FA]" : "border-[#E5E5EA] bg-white"}`}>
                    <span className="block font-bold">Khusus {entityFullById(entities, selectedEntity)}</span>
                    <span className="block text-[10.5px] text-[#6B6B73]">Bawaan — badan usaha lain tidak melihat gudang ini.</span>
                  </button>
                  <button type="button" data-testid="wh-form-mode-shared"
                    onClick={() => setForm({ ...form, sharing_mode: "shared" })}
                    className={`rounded-md border px-2.5 py-2 text-left text-[12px] ${
                      form.sharing_mode === "shared" ? "border-[#0058CC] bg-[#EAF2FF]" : "border-[#E5E5EA] bg-white"}`}>
                    <span className="block font-bold">Bersama semua badan usaha</span>
                    <span className="block text-[10.5px] text-[#6B6B73]">Dipakai bergantian oleh semua badan usaha.</span>
                  </button>
                </div>
              </div>

              <button data-testid="wh-form-save" className="primary-button mt-2.5" onClick={submit}
                disabled={saving || (!canWrite && form.sharing_mode === "dedicated")}
                title={!canWrite ? writeBlockHint : ""}>
                <Save size={14} /> {saving ? "Menyimpan…" : "Simpan gudang"}
              </button>
              {!canWrite && (
                <p data-testid="wh-form-scope-note" className="mt-1 text-[10.5px] text-[#8C4A00]">{writeBlockHint}</p>
              )}
            </div>
          )}

          {loading ? (
            <div className="grid gap-2" data-testid="wh-loading">
              {[0, 1, 2, 3].map((i) => <div key={i} className="h-12 animate-pulse rounded bg-[#F5F5F7]" />)}
            </div>
          ) : shown.length === 0 ? (
            <div data-testid="wh-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">
              <Warehouse size={26} className="mx-auto mb-2 text-gray-300" />
              {scope === "usable"
                ? `Belum ada gudang yang boleh dipakai ${activeEntityLabel}.`
                : "Belum ada gudang."}
            </div>
          ) : (
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
                    <th className="px-3 py-2">Gudang</th>
                    <th className="px-3 py-2">Mode pemakaian</th>
                    <th className="px-3 py-2">Isi gudang (pemilik stok)</th>
                    <th className="px-3 py-2 text-center">Status</th>
                    <th className="px-3 py-2 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((w) => {
                    const owners = occupancy[w.id] || [];
                    return (
                      <tr key={w.id} data-testid={`wh-row-${w.id}`}
                        className="border-b border-[#F5F5F7] last:border-0 hover:bg-[#FBFCFE]">
                        <td className="px-3 py-2">
                          <span className="font-semibold text-[#1C1C1E]">{w.name}</span>
                          <span className="block text-[10.5px] text-[#9A9BA3]">
                            <MapPin size={9} className="inline" /> {w.code} · {w.city || "—"}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <WarehouseModeBadge warehouse={w} testId={`wh-mode-badge-${w.id}`} />
                          {w.usable_by_active === false && (
                            <span data-testid={`wh-not-usable-${w.id}`}
                              className="mt-1 block text-[10px] font-semibold text-[#8C4A00]">
                              tidak bisa dipakai {activeEntityLabel}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {owners.length === 0 ? (
                            <span className="text-[11px] text-[#9A9BA3]">kosong</span>
                          ) : (
                            <span className="flex flex-wrap gap-1" data-testid={`wh-owners-${w.id}`}>
                              {owners.map((o) => (
                                <span key={o.entity_id || "none"}
                                  className="inline-flex items-center gap-1 rounded bg-[#F5F5F7] px-1.5 py-0.5 text-[10px] font-semibold text-[#3C3C43]">
                                  <Boxes size={9} /> {o.entity_name}: {o.rolls} roll · {formatQty(o.qty)}
                                </span>
                              ))}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-center">
                          <span className={`status-pill ${w.active === false ? "pill-muted" : "pill-success"}`}>
                            {w.active === false ? "Nonaktif" : "Aktif"}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          {canManage && (
                            <>
                              <button data-testid={`wh-edit-mode-${w.id}`} className="secondary-button text-[11px]"
                                onClick={() => setModeFor(w)}>
                                <Settings2 size={12} /> Atur mode
                              </button>
                              <button data-testid={`wh-toggle-active-${w.id}`}
                                className={`${w.active === false ? "secondary-button" : "danger-button"} ml-1.5 text-[11px]`}
                                onClick={() => toggleActive(w)}>
                                {w.active === false ? <><RotateCcw size={12} /> Aktifkan</> : <><Ban size={12} /> Nonaktifkan</>}
                              </button>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <div className="mt-3">
        <WarehouseStructure warehouses={shown} loading={loading} />
      </div>

      {modeFor && (
        <WarehouseModeDrawer
          warehouse={modeFor}
          entities={entities}
          onClose={() => setModeFor(null)}
          onSaved={(_updated, msg) => { setModeFor(null); setNotice(msg); load(); }}
        />
      )}
    </div>
  );
}

function Kpi({ label, value, icon: Icon, tone = "", testId }) {
  return (
    <div className="section-card" data-testid={testId}>
      <div className="section-body flex items-center gap-3 py-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#EAF2FF]">
          <Icon size={17} className="text-[#0058CC]" />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`truncate text-[17px] font-bold tabular-nums ${tone || "text-[#1C1C1E]"}`}
            data-testid={`${testId}-value`}>{value}</p>
        </div>
      </div>
    </div>
  );
}
