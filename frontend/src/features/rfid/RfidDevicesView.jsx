import { useEffect, useState } from "react";
import { Wifi, RefreshCw, Trash2, Plus, Cpu, Router, Power, RadioTower } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import axios, { API } from "../../services/apiClient";
import { Stat, EmptyBox, Pill, SectionCard, RfidHeader, fmtTime, useWarehouses } from "./rfidShared";

const TYPE_LABEL = { gate: "Gate", fixed_reader: "Fixed Reader", handheld: "Handheld" };
const TYPE_OPTS = [
  { value: "gate", label: "Gate (pintu masuk/keluar)" },
  { value: "fixed_reader", label: "Fixed Reader (zona)" },
  { value: "handheld", label: "Handheld" },
];
const DIR_OPTS = [{ value: "in", label: "Masuk (in)" }, { value: "out", label: "Keluar (out)" }];

export default function RfidDevicesView({ currentUser, selectedEntity }) {
  const { warehouses, whId, setWhId, whOpts } = useWarehouses();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [msg, setMsg] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", type: "gate", direction: "out", warehouse_id: "", location: "" });
  const isAdmin = currentUser?.role === "admin";

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const params = whId ? { warehouse_id: whId } : {};
      const r = await axios.get(`${API}/rfid/devices`, { params });
      setDevices(r.data.devices || []);
    } catch (e) { setError(e.response?.data?.detail || e.message || "Gagal memuat devices"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [whId]); // eslint-disable-line

  const flash = (m) => { setMsg(m); setTimeout(() => setMsg(""), 2500); };
  const seedDefaults = async () => {
    setBusy(true); setError(null);
    try { const r = await axios.post(`${API}/rfid/devices/seed-defaults`); flash(`${r.data.created} device default dibuat.`); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal seed devices"); } finally { setBusy(false); }
  };
  const toggleStatus = async (d) => {
    setBusy(true); setError(null);
    try { await axios.patch(`${API}/rfid/devices/${d.id}`, { status: d.status === "online" ? "offline" : "online" }); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal ubah status"); } finally { setBusy(false); }
  };
  const remove = async (id) => {
    setBusy(true); setError(null);
    try { await axios.delete(`${API}/rfid/devices/${id}`); flash("Device dihapus."); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal hapus device"); } finally { setBusy(false); }
  };
  const submit = async () => {
    if (!form.name || !form.warehouse_id) { setError("Nama & gudang wajib diisi"); return; }
    setBusy(true); setError(null);
    try {
      await axios.post(`${API}/rfid/devices`, { ...form, direction: form.type === "gate" ? form.direction : undefined });
      flash("Device dibuat."); setShowForm(false);
      setForm({ code: "", name: "", type: "gate", direction: "out", warehouse_id: "", location: "" });
      await load();
    } catch (e) { setError(e.response?.data?.detail || "Gagal buat device"); } finally { setBusy(false); }
  };

  const online = devices.filter((d) => d.status === "online").length;
  const gates = devices.filter((d) => d.type === "gate").length;
  const readers = devices.filter((d) => d.type !== "gate").length;
  const whFormOpts = warehouses.map((w) => ({ value: w.id, label: w.name }));

  return (
    <div data-testid="rfid-devices-view" className="space-y-4">
      <RfidHeader icon={Wifi} title="Devices (Reader / Gate)" subtitle="Infrastruktur RFID per gudang. Nyalakan/matikan, tambah gate & reader.">
        <KNSelect data-testid="rfid-dev-wh" value={whId} onValueChange={setWhId} options={whOpts}
          className="field !py-1 !px-2 text-[12px] w-auto" placeholder="Gudang" />
        <button data-testid="rfid-dev-refresh" onClick={load}
          className="flex items-center gap-1 rounded-lg border border-[#EFF0F2] bg-white px-3 py-1.5 text-[12px] font-semibold hover:bg-[#F5F5F7]">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </RfidHeader>

      {error && <ErrorNotice message={error} onRetry={load} />}
      {msg && <div className="rounded-lg bg-[#E7F7EC] text-[#1B7E3B] text-[12px] font-semibold px-3 py-2">{msg}</div>}
      {!isAdmin && <div className="rounded-lg bg-[#FFF6E5] text-[#8A5A00] text-[11px] px-3 py-2">Mode baca-saja. Perubahan device memerlukan role admin.</div>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat icon={Cpu} label="Total Device" value={devices.length} color="#0058CC" loading={loading} />
        <Stat icon={Power} label="Online" value={online} color="#34C759" loading={loading} testId="rfid-dev-online" />
        <Stat icon={RadioTower} label="Gate" value={gates} color="#5856D6" loading={loading} />
        <Stat icon={Router} label="Reader" value={readers} color="#FF9500" loading={loading} />
      </div>

      {isAdmin && (
        <div className="flex flex-wrap gap-2">
          <button data-testid="rfid-seed-devices" disabled={busy} onClick={seedDefaults}
            className="flex items-center gap-1 rounded-lg border border-[#0058CC] text-[#0058CC] px-3 py-1.5 text-[12px] font-semibold hover:bg-[#EAF2FF] disabled:opacity-40">
            <RadioTower size={14} /> Buat Device Default (per gudang)
          </button>
          <button data-testid="rfid-add-device" onClick={() => setShowForm((v) => !v)}
            className="flex items-center gap-1 rounded-lg bg-[#0058CC] text-white px-3 py-1.5 text-[12px] font-semibold">
            <Plus size={14} /> Tambah Device
          </button>
        </div>
      )}

      {showForm && isAdmin && (
        <SectionCard title="Device Baru">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div><label className="text-[11px] text-[#6B6B73]">Kode (opsional)</label>
              <input data-testid="rfid-form-code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })}
                className="w-full mt-1 rounded-lg border border-[#E5E5EA] px-2 py-1.5 text-[12px] outline-none focus:border-[#0058CC]" placeholder="GATE-JKT-OUT" /></div>
            <div><label className="text-[11px] text-[#6B6B73]">Nama</label>
              <input data-testid="rfid-form-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full mt-1 rounded-lg border border-[#E5E5EA] px-2 py-1.5 text-[12px] outline-none focus:border-[#0058CC]" placeholder="Gate Keluar" /></div>
            <div><label className="text-[11px] text-[#6B6B73]">Tipe</label>
              <KNSelect data-testid="rfid-form-type" value={form.type} onValueChange={(v) => setForm({ ...form, type: v })} options={TYPE_OPTS} className="field mt-1 text-[12px]" /></div>
            {form.type === "gate" && (
              <div><label className="text-[11px] text-[#6B6B73]">Arah</label>
                <KNSelect data-testid="rfid-form-dir" value={form.direction} onValueChange={(v) => setForm({ ...form, direction: v })} options={DIR_OPTS} className="field mt-1 text-[12px]" /></div>
            )}
            <div><label className="text-[11px] text-[#6B6B73]">Gudang</label>
              <KNSelect data-testid="rfid-form-wh" value={form.warehouse_id} onValueChange={(v) => setForm({ ...form, warehouse_id: v })} options={whFormOpts} className="field mt-1 text-[12px]" placeholder="Pilih gudang" /></div>
            <div><label className="text-[11px] text-[#6B6B73]">Lokasi</label>
              <input data-testid="rfid-form-loc" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })}
                className="w-full mt-1 rounded-lg border border-[#E5E5EA] px-2 py-1.5 text-[12px] outline-none focus:border-[#0058CC]" placeholder="Dock Kirim" /></div>
          </div>
          <div className="flex gap-2 mt-3">
            <button data-testid="rfid-form-submit" disabled={busy} onClick={submit}
              className="rounded-lg bg-[#0058CC] text-white px-4 py-1.5 text-[12px] font-semibold disabled:opacity-40">Simpan</button>
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-[#EFF0F2] px-4 py-1.5 text-[12px] font-semibold">Batal</button>
          </div>
        </SectionCard>
      )}

      <SectionCard title="Daftar Device">
        {loading ? <div className="h-16 bg-[#F5F5F7] rounded animate-pulse" />
          : devices.length === 0 ? <EmptyBox icon={Wifi} text="Belum ada device. Klik 'Buat Device Default' untuk mulai." />
            : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {devices.map((d) => (
                  <div key={d.id} data-testid={`rfid-device-${d.id}`} className="rounded-lg border border-[#EFF0F2] p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-mono font-semibold">{d.code}</span>
                      <Pill color={d.status === "online" ? "green" : "gray"} testId={`rfid-device-status-${d.id}`}>{d.status}</Pill>
                    </div>
                    <p className="text-[12px] font-semibold mt-1">{d.name}</p>
                    <p className="text-[11px] text-[#6B6B73]">{TYPE_LABEL[d.type] || d.type}{d.type === "gate" ? ` · ${d.direction}` : ""} · {d.warehouse_name || d.warehouse_id}</p>
                    <p className="text-[10px] text-[#8E8E93]">{d.location || "—"} · heartbeat {fmtTime(d.last_heartbeat)}</p>
                    {isAdmin && (
                      <div className="flex gap-2 mt-2">
                        <button data-testid={`rfid-toggle-${d.id}`} disabled={busy} onClick={() => toggleStatus(d)}
                          className="flex-1 flex items-center justify-center gap-1 rounded-lg border border-[#EFF0F2] px-2 py-1 text-[11px] font-semibold hover:bg-[#F5F5F7] disabled:opacity-40">
                          <Power size={12} /> {d.status === "online" ? "Matikan" : "Nyalakan"}
                        </button>
                        <button data-testid={`rfid-del-device-${d.id}`} disabled={busy} onClick={() => remove(d.id)}
                          className="rounded-lg border border-[#EFF0F2] px-2 py-1 text-[#C0341D] hover:bg-[#FBE9E7] disabled:opacity-40"><Trash2 size={12} /></button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
      </SectionCard>
    </div>
  );
}
