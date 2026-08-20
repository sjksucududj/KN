import { useEffect, useMemo, useState } from "react";
import {
  MapPin, Plus, Trash2, Save, Package, Layers, Boxes, RefreshCw, ArrowRight, PackageCheck,
} from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import axios, { API } from "../../services/apiClient";

const nf = new Intl.NumberFormat("id-ID");
const q = (v) => nf.format(Math.round((v || 0) * 100) / 100);
const uid = (p) => `${p}_${Math.random().toString(36).slice(2, 9)}`;

// Normalisasi rack lama (rack.bins langsung) → 1 Level default, agar editor seragam 4-level.
function normalizeZones(zones) {
  return (zones || []).map((z) => ({
    id: z.id || uid("zone"), name: z.name || "", code: z.code || "",
    racks: (z.racks || []).map((r) => {
      let levels = r.levels;
      if ((!levels || levels.length === 0) && (r.bins || []).length) {
        levels = [{ id: uid("level"), name: "Level 1", bins: r.bins }];
      }
      return {
        id: r.id || uid("rack"), name: r.name || "", code: r.code || "",
        levels: (levels || []).map((l) => ({
          id: l.id || uid("level"), name: l.name || "", code: l.code || "",
          bins: (l.bins || []).map((b) => ({
            id: b.id || uid("bin"), code: b.code || "", capacity: Number(b.capacity || 0),
          })),
        })),
      };
    }),
  }));
}

function UtilBar({ util }) {
  if (util == null) return <span className="text-[11px] text-[#8E8E93]">tanpa kapasitas</span>;
  const color = util >= 90 ? "#C0341D" : util >= 70 ? "#FF9500" : "#34C759";
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-1.5 rounded-full bg-[#EFF0F2] overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.min(util, 100)}%`, background: color }} />
      </div>
      <span className="text-[11px] tabular-nums" style={{ color }}>{util}%</span>
    </div>
  );
}

export default function LocationPutawayView({ currentUser, selectedEntity }) {
  const [tab, setTab] = useState("structure");
  const [warehouses, setWarehouses] = useState([]);
  const [whId, setWhId] = useState("");
  const [loc, setLoc] = useState(null);
  const [zones, setZones] = useState([]);
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    axios.get(`${API}/warehouses`).then((r) => {
      setWarehouses(r.data || []);
      if ((r.data || []).length && !whId) setWhId(r.data[0].id);
    }).catch((e) => setError(e.message));
  }, []); // eslint-disable-line

  const loadAll = async () => {
    if (!whId) return;
    setLoading(true); setError(null);
    try {
      const ent = selectedEntity && selectedEntity !== "all" ? selectedEntity : "all";
      const [l, qd] = await Promise.all([
        axios.get(`${API}/warehouses/${whId}/locations`, { params: { entity_id: ent } }),
        axios.get(`${API}/inventory/putaway/queue`, { params: { warehouse_id: whId, entity_id: ent } }),
      ]);
      setLoc(l.data);
      setZones(normalizeZones(l.data.zones));
      setQueue(qd.data.rolls || []);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || "Gagal memuat data lokasi");
    } finally { setLoading(false); }
  };
  useEffect(() => { loadAll(); }, [whId, selectedEntity]); // eslint-disable-line

  const occByBin = useMemo(() => {
    const m = {};
    (loc?.bins || []).forEach((b) => { m[b.bin_id] = b; });
    return m;
  }, [loc]);

  const binOptions = useMemo(
    () => (loc?.bins || []).map((b) => ({ value: b.bin_id, label: `${b.code} — ${b.path}` })),
    [loc]
  );

  // ── mutators struktur ──
  const update = (fn) => setZones((prev) => { const n = JSON.parse(JSON.stringify(prev)); fn(n); return n; });
  const addZone = () => update((n) => n.push({ id: uid("zone"), name: `Zone ${String.fromCharCode(65 + n.length)}`, code: "", racks: [] }));
  const delZone = (zi) => update((n) => n.splice(zi, 1));
  const addRack = (zi) => update((n) => n[zi].racks.push({ id: uid("rack"), name: `Rack ${n[zi].racks.length + 1}`, code: "", levels: [] }));
  const delRack = (zi, ri) => update((n) => n[zi].racks.splice(ri, 1));
  const addLevel = (zi, ri) => update((n) => n[zi].racks[ri].levels.push({ id: uid("level"), name: `Level ${n[zi].racks[ri].levels.length + 1}`, code: "", bins: [] }));
  const delLevel = (zi, ri, li) => update((n) => n[zi].racks[ri].levels.splice(li, 1));
  const addBin = (zi, ri, li) => update((n) => {
    const lvl = n[zi].racks[ri].levels[li];
    lvl.bins.push({ id: uid("bin"), code: `BIN-${uid("").slice(-4).toUpperCase()}`, capacity: 500 });
  });
  const delBin = (zi, ri, li, bi) => update((n) => n[zi].racks[ri].levels[li].bins.splice(bi, 1));

  const saveStructure = async () => {
    setSaving(true); setError(null); setMsg("");
    try {
      await axios.put(`${API}/warehouses/${whId}/structure`, { zones });
      setMsg("Struktur lokasi tersimpan.");
      await loadAll();
      setTimeout(() => setMsg(""), 2500);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyimpan struktur");
    } finally { setSaving(false); }
  };

  const doPutaway = async (rollId, binId) => {
    if (!binId) return;
    setError(null);
    try {
      await axios.post(`${API}/inventory/putaway`, { roll_id: rollId, bin_id: binId });
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal putaway");
    }
  };

  const whOpts = warehouses.map((w) => ({ value: w.id, label: w.name }));

  return (
    <div data-testid="location-putaway-view" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[12px] font-semibold text-[#0058CC] tracking-wide">GUDANG</p>
          <h1 className="text-[20px] font-bold text-[#1C1C1E] flex items-center gap-2">
            <MapPin size={20} className="text-[#0058CC]" /> Lokasi Gudang & Penempatan Rak
          </h1>
          <p className="text-[12px] text-[#6B6B73] mt-0.5">Zona → Rak → Tingkat → Bin. Penempatan rak menaruh roll ke bin (tidak mengubah stok/saldo).</p>
        </div>
        <div className="flex items-center gap-2">
          <KNSelect data-testid="lp-warehouse" value={whId} onValueChange={setWhId} options={whOpts}
            className="field !py-1 !px-2 text-[12px] w-auto" placeholder="Gudang" />
          <button data-testid="lp-refresh" onClick={loadAll}
            className="flex items-center gap-1 rounded-lg border border-[#EFF0F2] bg-white px-3 py-1.5 text-[12px] font-semibold hover:bg-[#F5F5F7]">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {error && <ErrorNotice message={error} onRetry={loadAll} />}
      {msg && <div className="rounded-lg bg-[#E7F7EC] text-[#1B7E3B] text-[12px] font-semibold px-3 py-2">{msg}</div>}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat icon={Boxes} label="Total Bin" value={loc?.bin_count ?? 0} color="#0058CC" loading={loading} />
        <Stat icon={Package} label="Kapasitas" value={`${q(loc?.total_capacity)} m`} color="#5856D6" loading={loading} />
        <Stat icon={PackageCheck} label="Terisi" value={`${q(loc?.total_occupied)} m`} color="#34C759" loading={loading} />
        <Stat icon={Layers} label="Belum Ditempatkan" value={`${loc?.unassigned?.rolls ?? 0} roll`} sub={`${q(loc?.unassigned?.qty)} m`} color="#FF9500" loading={loading} testId="lp-unassigned" />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-[#EFF0F2]">
        <TabBtn id="structure" tab={tab} setTab={setTab} label="Struktur Lokasi" testId="lp-tab-structure" />
        <TabBtn id="putaway" tab={tab} setTab={setTab} label={`Putaway${loc?.unassigned?.rolls ? ` (${loc.unassigned.rolls})` : ""}`} testId="lp-tab-putaway" />
      </div>

      {tab === "structure" ? (
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <button data-testid="lp-add-zone" onClick={addZone}
              className="flex items-center gap-1 text-[12px] font-semibold text-[#0058CC] hover:underline"><Plus size={14} /> Tambah Zone</button>
            <button data-testid="lp-save-structure" onClick={saveStructure} disabled={saving}
              className="flex items-center gap-1 rounded-lg bg-[#0058CC] text-white px-4 py-1.5 text-[12px] font-semibold disabled:opacity-50">
              <Save size={14} /> {saving ? "Menyimpan…" : "Simpan Struktur"}
            </button>
          </div>
          {zones.length === 0 ? (
            <EmptyBox icon={MapPin} text="Belum ada zona. Klik 'Tambah Zone' untuk mulai menata lokasi." />
          ) : zones.map((z, zi) => (
            <div key={z.id} className="rounded-xl border border-[#EFF0F2] bg-white p-3">
              <div className="flex items-center gap-2 mb-2">
                <input value={z.name || ''} onChange={(e) => update((n) => { n[zi].name = e.target.value; })}
                  data-testid={`lp-zone-name-${zi}`} placeholder="Nama Zone"
                  className="font-bold text-[14px] border-b border-transparent focus:border-[#0058CC] outline-none bg-transparent" />
                <button onClick={() => addRack(zi)} className="text-[11px] text-[#0058CC] font-semibold hover:underline flex items-center gap-0.5"><Plus size={12} /> Rack</button>
                <button onClick={() => delZone(zi)} className="ml-auto text-[#C0341D] hover:bg-[#FBE9E7] rounded p-1"><Trash2 size={13} /></button>
              </div>
              <div className="pl-3 space-y-2 border-l-2 border-[#F0F0F2]">
                {(z.racks || []).length === 0 && <p className="text-[11px] text-[#8E8E93]">Belum ada rack.</p>}
                {(z.racks || []).map((r, ri) => (
                  <div key={r.id} className="rounded-lg bg-[#FAFAFB] p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <input value={r.name || ''} onChange={(e) => update((n) => { n[zi].racks[ri].name = e.target.value; })}
                        placeholder="Rack" className="font-semibold text-[12px] bg-transparent outline-none border-b border-transparent focus:border-[#0058CC]" />
                      <button onClick={() => addLevel(zi, ri)} className="text-[11px] text-[#0058CC] font-semibold hover:underline flex items-center gap-0.5"><Plus size={11} /> Level</button>
                      <button onClick={() => delRack(zi, ri)} className="ml-auto text-[#C0341D] hover:bg-[#FBE9E7] rounded p-1"><Trash2 size={12} /></button>
                    </div>
                    <div className="pl-3 space-y-1.5">
                      {(r.levels || []).map((l, li) => (
                        <div key={l.id} className="rounded bg-white border border-[#EFF0F2] p-2">
                          <div className="flex items-center gap-2 mb-1">
                            <Layers size={12} className="text-[#8E8E93]" />
                            <input value={l.name || ''} onChange={(e) => update((n) => { n[zi].racks[ri].levels[li].name = e.target.value; })}
                              placeholder="Level" className="text-[12px] font-medium bg-transparent outline-none border-b border-transparent focus:border-[#0058CC]" />
                            <button onClick={() => addBin(zi, ri, li)} className="text-[11px] text-[#0058CC] font-semibold hover:underline flex items-center gap-0.5"><Plus size={11} /> Bin</button>
                            <button onClick={() => delLevel(zi, ri, li)} className="ml-auto text-[#C0341D] hover:bg-[#FBE9E7] rounded p-1"><Trash2 size={11} /></button>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 pl-3">
                            {(l.bins || []).map((b, bi) => {
                              const occ = occByBin[b.id];
                              return (
                                <div key={b.id} className="flex items-center gap-2 rounded bg-[#F5F5F7] px-2 py-1">
                                  <input value={b.code || ''} onChange={(e) => update((n) => { n[zi].racks[ri].levels[li].bins[bi].code = e.target.value; })}
                                    placeholder="Kode Bin" className="text-[11px] font-mono font-semibold bg-transparent outline-none w-24 border-b border-transparent focus:border-[#0058CC]" />
                                  <span className="text-[10px] text-[#8E8E93]">cap</span>
                                  <input type="number" value={b.capacity || 0} onChange={(e) => update((n) => { n[zi].racks[ri].levels[li].bins[bi].capacity = Number(e.target.value || 0); })}
                                    className="text-[11px] tabular-nums bg-white rounded w-16 px-1 border border-[#E5E5EA] outline-none" />
                                  {occ && <span className="text-[10px] text-[#6B6B73]">terisi {q(occ.occupied)}</span>}
                                  <button onClick={() => delBin(zi, ri, li, bi)} className="ml-auto text-[#C0341D] hover:bg-[#FBE9E7] rounded p-0.5"><Trash2 size={11} /></button>
                                </div>
                              );
                            })}
                            {(l.bins || []).length === 0 && <p className="text-[10px] text-[#8E8E93]">Belum ada bin.</p>}
                          </div>
                        </div>
                      ))}
                      {(r.levels || []).length === 0 && <p className="text-[10px] text-[#8E8E93]">Belum ada level.</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {/* Bin occupancy grid */}
          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4">
            <h3 className="text-[13px] font-bold mb-3">Okupansi Bin</h3>
            {(loc?.bins || []).length === 0 ? (
              <EmptyBox icon={Boxes} text="Belum ada bin. Tata struktur lokasi lebih dulu." />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {loc.bins.map((b) => (
                  <div key={b.bin_id} className="rounded-lg border border-[#EFF0F2] p-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-mono font-semibold">{b.code || b.bin_id || '-'}</span>
                      <span className="text-[10px] text-[#8E8E93]">{b.roll_count || 0} roll</span>
                    </div>
                    <p className="text-[10px] text-[#8E8E93] mb-1">{b.path || '-'}</p>
                    <UtilBar util={b.utilization} />
                    <p className="text-[10px] text-[#6B6B73] mt-1">{q(b.occupied || 0)} / {q(b.capacity || 0)} m</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Putaway queue */}
          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4">
            <h3 className="text-[13px] font-bold mb-3">Antrean Penempatan Rak — roll belum ditempatkan</h3>
            {loading ? (
              <div className="h-16 bg-[#F5F5F7] rounded animate-pulse" />
            ) : queue.length === 0 ? (
              <EmptyBox icon={PackageCheck} text="Semua roll sudah ditempatkan ke bin. 🎉" />
            ) : (
              <div className="space-y-2">
                {queue.map((r) => (
                  <PutawayRow key={r.id} roll={r} binOptions={binOptions} onPutaway={doPutaway} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function PutawayRow({ roll, binOptions, onPutaway }) {
  const [bin, setBin] = useState("");
  return (
    <div data-testid={`lp-queue-${roll.id}`} className="flex flex-wrap items-center gap-2 rounded-lg bg-[#FAFAFB] p-2">
      <div className="flex-1 min-w-[180px]">
        <p className="text-[12px] font-semibold">{roll.roll_no} · {roll.sku}</p>
        <p className="text-[11px] text-[#6B6B73]">{roll.product_name} — {q(roll.length_remaining)} {roll.unit} · Lot {roll.lot || "-"}</p>
      </div>
      <KNSelect data-testid={`lp-bin-select-${roll.id}`} value={bin} onValueChange={setBin} options={binOptions}
        className="field !py-1 !px-2 text-[12px] w-56" placeholder="Pilih bin…" />
      <button data-testid={`lp-assign-${roll.id}`} disabled={!bin} onClick={() => onPutaway(roll.id, bin)}
        className="flex items-center gap-1 rounded-lg bg-[#0058CC] text-white px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40">
        Tempatkan <ArrowRight size={13} />
      </button>
    </div>
  );
}

function Stat({ icon: Icon, label, value, sub, color, loading, testId }) {
  return (
    <div data-testid={testId} className="rounded-xl border border-[#EFF0F2] bg-white p-4 flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <div className="rounded-lg p-1.5" style={{ background: `${color}18` }}><Icon size={15} style={{ color }} /></div>
        <span className="text-[12px] font-semibold text-[#6B6B73]">{label}</span>
      </div>
      {loading ? <div className="h-6 bg-[#F5F5F7] rounded animate-pulse" />
        : <p className="text-[19px] font-bold text-[#1C1C1E] tabular-nums leading-tight">{value}</p>}
      {sub && <p className="text-[11px] text-[#6B6B73]">{sub}</p>}
    </div>
  );
}

function TabBtn({ id, tab, setTab, label, testId }) {
  const active = tab === id;
  return (
    <button data-testid={testId} onClick={() => setTab(id)}
      className={`px-4 py-2 text-[13px] font-semibold border-b-2 -mb-px ${active ? "border-[#0058CC] text-[#0058CC]" : "border-transparent text-[#6B6B73] hover:text-[#1C1C1E]"}`}>
      {label}
    </button>
  );
}

function EmptyBox({ icon: Icon, text }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="rounded-full bg-[#F5F5F7] p-3"><Icon size={22} className="text-[#8E8E93]" /></div>
      <p className="text-[12px] text-[#6B6B73] max-w-xs">{text}</p>
    </div>
  );
}
