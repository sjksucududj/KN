import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  Car, Plus, RefreshCw, Trash2, Pencil, Route, Fuel, X,
} from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import { fmtDate } from "./pettyCashShared";

/**
 * VehicleLogsView — Aset & GA: Laporan Penggunaan & Biaya Kendaraan.
 * Tab: Log & Biaya · Master Kendaraan · Rekap per kendaraan.
 */
const JENIS = [
  { value: "mobil", label: "Mobil" }, { value: "motor", label: "Motor" },
  { value: "truk", label: "Truk" }, { value: "lainnya", label: "Lainnya" },
];
const emptyLog = () => ({
  vehicle_id: "", no_polisi: "", tanggal: new Date().toISOString().slice(0, 10),
  km_awal: "", km_akhir: "", bbm: "", tol: "", parkir: "", lain_lain: "",
  tujuan: "", driver: "", pemakai: "", mengetahui: "",
});

export default function VehicleLogsView({ currentUser, selectedEntity = "all", entities = [] }) {
  const [tab, setTab] = useState("logs");
  const [logs, setLogs] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [summary, setSummary] = useState({ grand_total: 0, count: 0, per_vehicle: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const [logForm, setLogForm] = useState(null);   // null | {} (create/edit)
  const [vehForm, setVehForm] = useState(null);
  const [delTarget, setDelTarget] = useState(null); // {kind, item}

  const role = currentUser?.role;
  const canCreate = ["admin", "manager", "warehouse", "sales"].includes(role);
  const canManageVeh = ["admin", "manager", "warehouse"].includes(role);
  const canDelete = ["admin", "manager"].includes(role);

  useEffect(() => { loadAll(); }, [selectedEntity]); // eslint-disable-line

  async function loadAll() {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const [l, v, s] = await Promise.all([
        axios.get(`${API}/vehicle-usage-logs`, { params }),
        axios.get(`${API}/vehicles`, { params }),
        axios.get(`${API}/vehicle-usage-logs/summary`, { params }).catch(() => ({ data: {} })),
      ]);
      setLogs(Array.isArray(l.data) ? l.data : []);
      setVehicles(Array.isArray(v.data) ? v.data : []);
      setSummary(s.data || { grand_total: 0, count: 0, per_vehicle: [] });
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data kendaraan.");
    } finally { setLoading(false); }
  }
  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 3500); }

  async function doDelete() {
    const { kind, item } = delTarget;
    try {
      if (kind === "log") await axios.delete(`${API}/vehicle-usage-logs/${item.id}`);
      else await axios.delete(`${API}/vehicles/${item.id}`);
      flash("Data dihapus.");
    } catch (e) { flash(e.response?.data?.detail || "Gagal menghapus."); }
    finally { setDelTarget(null); loadAll(); }
  }

  const entityName = (id) => entities.find((e) => e.id === id)?.short_name || entities.find((e) => e.id === id)?.legal_name || id || "—";

  return (
    <div data-testid="vehicle-logs-view" className="grid gap-4">
      {toast && <div className="notice-bar success" data-testid="veh-toast"><span>{toast}</span><button onClick={() => setToast("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="veh-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Car size={15} className="text-[#0058CC]" />
            <span className="kicker">Aset & GA</span>
            <h2 data-testid="veh-title">Penggunaan & Biaya Kendaraan</h2>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="veh-refresh" className="icon-button" onClick={loadAll} aria-label="Muat ulang"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
            {tab === "logs" && canCreate && <button data-testid="veh-log-create-btn" className="btn-primary" onClick={() => setLogForm(emptyLog())}><Plus size={14} /> Catat Perjalanan</button>}
            {tab === "vehicles" && canManageVeh && <button data-testid="veh-create-btn" className="btn-primary" onClick={() => setVehForm({ no_polisi: "", nama: "", jenis: "mobil", active: true })}><Plus size={14} /> Kendaraan Baru</button>}
          </div>
        </div>
        <section data-testid="veh-metrics" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 p-3">
          <Metric label="Total Kendaraan" value={vehicles.length} tone="rgba(0,122,255,.12)" testId="veh-metric-count" icon={Car} />
          <Metric label="Total Perjalanan" value={summary.count || 0} tone="rgba(175,82,222,.14)" testId="veh-metric-trips" icon={Route} />
          <Metric label="Total Jarak (km)" value={formatQty(summary.per_vehicle?.reduce((s, v) => s + (v.jarak || 0), 0))} tone="rgba(52,199,89,.15)" testId="veh-metric-km" icon={Route} />
          <Metric label="Total Biaya" value={formatCurrency(summary.grand_total)} tone="rgba(255,149,0,.16)" testId="veh-metric-cost" icon={Fuel} money />
        </section>
        <div className="flex flex-wrap gap-1.5 px-3 pb-3">
          {[{ k: "logs", l: "Log & Biaya" }, { k: "vehicles", l: "Master Kendaraan" }, { k: "recap", l: "Rekap" }].map((t) => (
            <button key={t.k} data-testid={`veh-tab-${t.k}`} className={`tab-button ${tab === t.k ? "active" : ""}`} onClick={() => setTab(t.k)}>{t.l}</button>
          ))}
        </div>
      </section>

      {tab === "logs" && (
        <section className="section-card">
          <div className="overflow-x-auto">
            <div className="grid grid-cols-[90px_90px_1.4fr_100px_130px_80px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Nomor</span><span>Tanggal</span><span>Tujuan / Kendaraan</span><span className="text-right">Jarak</span><span className="text-right">Biaya</span><span className="text-right">Aksi</span>
            </div>
            {loading ? <div data-testid="veh-log-loading" className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
              : logs.length === 0 ? <div data-testid="veh-log-empty" className="py-12 text-center text-[12px] text-[#6B6B73]"><Car className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada log. Klik <b>Catat Perjalanan</b>.</p></div>
              : (
                <div className="divide-y divide-[#EFF0F2]">
                  {logs.map((r) => (
                    <div key={r.id} data-testid={`veh-log-row-${r.id}`} className="grid grid-cols-[90px_90px_1.4fr_100px_130px_80px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                      <span className="text-[11px] font-bold text-[#0058CC]">{r.number}</span>
                      <span className="text-[10.5px] text-[#6B6B73]">{fmtDate(r.tanggal)}</span>
                      <div className="min-w-0"><p className="text-[12px] font-semibold truncate">{r.tujuan || "—"}</p><p className="text-[10.5px] text-[#9A9BA3] truncate">{r.no_polisi || "—"} · {r.driver || r.pemakai || "—"}</p></div>
                      <span className="text-[11.5px] tabular-nums text-right">{formatQty(r.jarak_tempuh)} km</span>
                      <span className="text-[12px] tabular-nums text-right font-semibold">{formatCurrency(r.total)}</span>
                      <div className="flex justify-end gap-1">
                        {canCreate && <button data-testid={`veh-log-edit-${r.id}`} className="icon-button" onClick={() => setLogForm({ ...r, tanggal: (r.tanggal || "").slice(0, 10) })} aria-label="Ubah"><Pencil size={13} /></button>}
                        {canDelete && <button data-testid={`veh-log-del-${r.id}`} className="icon-button text-red-400" onClick={() => setDelTarget({ kind: "log", item: r })} aria-label="Hapus"><Trash2 size={13} /></button>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
          </div>
        </section>
      )}

      {tab === "vehicles" && (
        <section className="section-card">
          <div className="overflow-x-auto">
            <div className="grid grid-cols-[130px_1.4fr_110px_110px_90px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>No. Polisi</span><span>Nama / Merk</span><span>Jenis</span><span>Status</span><span className="text-right">Aksi</span>
            </div>
            {loading ? <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
              : vehicles.length === 0 ? <div data-testid="veh-empty" className="py-12 text-center text-[12px] text-[#6B6B73]"><Car className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada kendaraan.</p></div>
              : (
                <div className="divide-y divide-[#EFF0F2]">
                  {vehicles.map((v) => (
                    <div key={v.id} data-testid={`veh-row-${v.id}`} className="grid grid-cols-[130px_1.4fr_110px_110px_90px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                      <span className="text-[12px] font-bold text-[#0058CC]">{v.no_polisi}</span>
                      <span className="text-[12px] truncate">{v.nama || "—"}</span>
                      <span className="text-[11.5px] capitalize">{v.jenis}</span>
                      <span className={`status-pill ${v.active ? "pill-success" : "pill-muted"}`}>{v.active ? "Aktif" : "Nonaktif"}</span>
                      <div className="flex justify-end gap-1">
                        {canManageVeh && <button data-testid={`veh-edit-${v.id}`} className="icon-button" onClick={() => setVehForm(v)} aria-label="Ubah"><Pencil size={13} /></button>}
                        {canDelete && <button data-testid={`veh-del-${v.id}`} className="icon-button text-red-400" onClick={() => setDelTarget({ kind: "vehicle", item: v })} aria-label="Hapus"><Trash2 size={13} /></button>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
          </div>
        </section>
      )}

      {tab === "recap" && (
        <section className="section-card">
          <div className="grid grid-cols-[1.4fr_120px_140px_100px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Kendaraan</span><span className="text-right">Total Jarak</span><span className="text-right">Total Biaya</span><span className="text-right">Perjalanan</span>
          </div>
          {(summary.per_vehicle || []).length === 0 ? (
            <div data-testid="veh-recap-empty" className="py-12 text-center text-[12px] text-[#6B6B73]">Belum ada rekap biaya.</div>
          ) : (
            <div className="divide-y divide-[#EFF0F2]">
              {summary.per_vehicle.map((p, i) => (
                <div key={i} data-testid={`veh-recap-${i}`} className="grid grid-cols-[1.4fr_120px_140px_100px] items-center px-3 py-2.5">
                  <span className="text-[12px] font-semibold">{p.no_polisi}</span>
                  <span className="text-[11.5px] tabular-nums text-right">{formatQty(p.jarak)} km</span>
                  <span className="text-[12px] tabular-nums text-right font-semibold">{formatCurrency(p.total)}</span>
                  <span className="text-[11.5px] tabular-nums text-right">{p.count}</span>
                </div>
              ))}
              <div className="grid grid-cols-[1.4fr_120px_140px_100px] items-center px-3 py-2.5 bg-[#FAFBFC]">
                <span className="text-[11px] font-bold uppercase text-[#6B6B73]">Grand Total</span><span></span>
                <span data-testid="veh-recap-grand" className="text-[13px] tabular-nums text-right font-bold text-[#0058CC]">{formatCurrency(summary.grand_total)}</span><span></span>
              </div>
            </div>
          )}
        </section>
      )}

      {logForm && <LogFormModal form={logForm} setForm={setLogForm} vehicles={vehicles} entities={entities} selectedEntity={selectedEntity} onClose={() => setLogForm(null)} onSaved={(msg) => { flash(msg); setLogForm(null); loadAll(); }} />}
      {vehForm && <VehicleFormModal form={vehForm} entities={entities} selectedEntity={selectedEntity} onClose={() => setVehForm(null)} onSaved={(msg) => { flash(msg); setVehForm(null); loadAll(); }} />}

      <ConfirmModal open={!!delTarget} title="Hapus Data" message={`Hapus ${delTarget?.kind === "log" ? "log perjalanan" : "kendaraan"} ini? Kendaraan yang sudah dipakai log akan dinonaktifkan.`} confirmLabel="Hapus" danger onConfirm={doDelete} onCancel={() => setDelTarget(null)} testId="veh-del-modal" />
    </div>
  );
}

// ─── Log form (modal) ────────────────────────────────────────────────────────
function LogFormModal({ form, vehicles, entities, selectedEntity, onClose, onSaved }) {
  const [f, setF] = useState(form);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const isEdit = !!f.id;
  const upd = (k, v) => setF({ ...f, [k]: v });
  const total = (Number(f.bbm) || 0) + (Number(f.tol) || 0) + (Number(f.parkir) || 0) + (Number(f.lain_lain) || 0);
  const jarak = Math.max(0, (Number(f.km_akhir) || 0) - (Number(f.km_awal) || 0));

  async function save() {
    setErr("");
    if (!f.vehicle_id && !f.no_polisi) { setErr("Pilih kendaraan atau isi No. Polisi."); return; }
    setBusy(true);
    try {
      const body = {
        vehicle_id: f.vehicle_id || "", no_polisi: f.no_polisi || "", tanggal: f.tanggal,
        km_awal: Number(f.km_awal) || 0, km_akhir: Number(f.km_akhir) || 0,
        bbm: Number(f.bbm) || 0, tol: Number(f.tol) || 0, parkir: Number(f.parkir) || 0, lain_lain: Number(f.lain_lain) || 0,
        tujuan: f.tujuan || "", driver: f.driver || "", pemakai: f.pemakai || "", mengetahui: f.mengetahui || "",
      };
      if (isEdit) await axios.patch(`${API}/vehicle-usage-logs/${f.id}`, body);
      else {
        body.entity_id = selectedEntity && selectedEntity !== "all" ? selectedEntity : (entities[0]?.id || "");
        await axios.post(`${API}/vehicle-usage-logs`, body);
      }
      onSaved(isEdit ? "Log diperbarui." : "Log perjalanan dicatat.");
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyimpan log."); } finally { setBusy(false); }
  }

  return (
    <div className="modal-overlay" data-testid="veh-log-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 640 }}>
        <div className="flex items-center justify-between mb-2"><p className="modal-title">{isEdit ? "Ubah Log Perjalanan" : "Catat Perjalanan Kendaraan"}</p><button className="icon-button" onClick={onClose}><X size={15} /></button></div>
        {err && <div className="notice-bar danger" data-testid="veh-log-form-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}
        <div className="grid gap-3 sm:grid-cols-2 mt-1">
          <F label="Kendaraan">
            <KNSelect data-testid="veh-log-vehicle" className="form-input" value={f.vehicle_id} onValueChange={(v) => { const veh = vehicles.find((x) => x.id === v); setF({ ...f, vehicle_id: v, no_polisi: veh?.no_polisi || f.no_polisi }); }}
              placeholder="Pilih dari master" options={vehicles.map((v) => ({ value: v.id, label: `${v.no_polisi} · ${v.nama || v.jenis}` }))} />
          </F>
          <F label="No. Polisi (manual)"><input data-testid="veh-log-nopol" className="form-input" value={f.no_polisi} onChange={(e) => upd("no_polisi", e.target.value)} placeholder="B 1234 XX" /></F>
          <F label="Tanggal"><input type="date" data-testid="veh-log-tanggal" className="form-input" value={f.tanggal} onChange={(e) => upd("tanggal", e.target.value)} /></F>
          <F label="Tujuan"><input data-testid="veh-log-tujuan" className="form-input" value={f.tujuan} onChange={(e) => upd("tujuan", e.target.value)} placeholder="mis. Kirim sampel ke pelanggan" /></F>
          <F label="KM Awal"><input type="number" data-testid="veh-log-kmawal" className="form-input text-right" value={f.km_awal} onChange={(e) => upd("km_awal", e.target.value)} /></F>
          <F label="KM Akhir"><input type="number" data-testid="veh-log-kmakhir" className="form-input text-right" value={f.km_akhir} onChange={(e) => upd("km_akhir", e.target.value)} /></F>
          <F label="BBM (Rp)"><input type="number" data-testid="veh-log-bbm" className="form-input text-right" value={f.bbm} onChange={(e) => upd("bbm", e.target.value)} /></F>
          <F label="Tol (Rp)"><input type="number" data-testid="veh-log-tol" className="form-input text-right" value={f.tol} onChange={(e) => upd("tol", e.target.value)} /></F>
          <F label="Parkir (Rp)"><input type="number" data-testid="veh-log-parkir" className="form-input text-right" value={f.parkir} onChange={(e) => upd("parkir", e.target.value)} /></F>
          <F label="Lain-lain (Rp)"><input type="number" data-testid="veh-log-lain" className="form-input text-right" value={f.lain_lain} onChange={(e) => upd("lain_lain", e.target.value)} /></F>
          <F label="Driver"><input data-testid="veh-log-driver" className="form-input" value={f.driver} onChange={(e) => upd("driver", e.target.value)} /></F>
          <F label="Pemakai"><input data-testid="veh-log-pemakai" className="form-input" value={f.pemakai} onChange={(e) => upd("pemakai", e.target.value)} /></F>
        </div>
        <div className="flex items-center justify-between mt-3 rounded-md bg-[#FAFBFC] px-3 py-2 border border-[#EFF0F2]">
          <span className="text-[11.5px] text-[#6B6B73]">Jarak: <b className="tabular-nums">{formatQty(jarak)} km</b></span>
          <span className="text-[12px] font-bold text-[#0058CC]">Total Biaya: <span data-testid="veh-log-total" className="tabular-nums">{formatCurrency(total)}</span></span>
        </div>
        <div className="modal-actions"><button className="btn-secondary" onClick={onClose}>Batal</button><button data-testid="veh-log-save" className="btn-primary" onClick={save} disabled={busy}>{busy ? "Menyimpan…" : "Simpan"}</button></div>
      </div>
    </div>
  );
}

// ─── Vehicle master form (modal) ─────────────────────────────────────────────
function VehicleFormModal({ form, entities, selectedEntity, onClose, onSaved }) {
  const [f, setF] = useState(form);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const isEdit = !!f.id;
  const upd = (k, v) => setF({ ...f, [k]: v });

  async function save() {
    setErr("");
    if (!f.no_polisi?.trim()) { setErr("No. Polisi wajib diisi."); return; }
    setBusy(true);
    try {
      const body = { no_polisi: f.no_polisi, nama: f.nama || "", jenis: f.jenis || "mobil", active: f.active !== false };
      if (isEdit) await axios.patch(`${API}/vehicles/${f.id}`, body);
      else { body.entity_id = selectedEntity && selectedEntity !== "all" ? selectedEntity : (entities[0]?.id || ""); await axios.post(`${API}/vehicles`, body); }
      onSaved(isEdit ? "Kendaraan diperbarui." : "Kendaraan ditambahkan.");
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyimpan kendaraan."); } finally { setBusy(false); }
  }

  return (
    <div className="modal-overlay" data-testid="veh-form-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 480 }}>
        <div className="flex items-center justify-between mb-2"><p className="modal-title">{isEdit ? "Ubah Kendaraan" : "Tambah Kendaraan"}</p><button className="icon-button" onClick={onClose}><X size={15} /></button></div>
        {err && <div className="notice-bar danger" data-testid="veh-form-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}
        <div className="grid gap-3 mt-1">
          <F label="No. Polisi" req><input data-testid="veh-form-nopol" className="form-input" value={f.no_polisi} onChange={(e) => upd("no_polisi", e.target.value)} placeholder="B 1234 XX" /></F>
          <F label="Nama / Merk"><input data-testid="veh-form-nama" className="form-input" value={f.nama} onChange={(e) => upd("nama", e.target.value)} placeholder="mis. Toyota Avanza" /></F>
          <F label="Jenis"><KNSelect data-testid="veh-form-jenis" className="form-input" value={f.jenis} onValueChange={(v) => upd("jenis", v)} options={JENIS} /></F>
          <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" data-testid="veh-form-active" checked={f.active !== false} onChange={(e) => upd("active", e.target.checked)} /> Aktif</label>
        </div>
        <div className="modal-actions"><button className="btn-secondary" onClick={onClose}>Batal</button><button data-testid="veh-form-save" className="btn-primary" onClick={save} disabled={busy}>{busy ? "Menyimpan…" : "Simpan"}</button></div>
      </div>
    </div>
  );
}

function Metric({ label, value, tone, testId, icon: Icon, money }) {
  return (<div data-testid={testId} className="metric-card"><div className="metric-icon" style={{ background: tone }}><Icon size={16} className="text-[#1C1C1E]" /></div><div className="min-w-0"><p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p><p className={`${money ? "text-[15px]" : "text-[17px]"} font-bold tabular-nums truncate`}>{value}</p></div></div>);
}
function F({ label, req, children }) {
  return (<div className="grid gap-1.5"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">{label}{req && <span className="req"> *</span>}</label>{children}</div>);
}
