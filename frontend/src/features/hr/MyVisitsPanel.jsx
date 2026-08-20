import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Play, Square, LocateFixed, Building2, Clock, RefreshCw, MapPin } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import { OUTCOME_OPTS, OUTCOME_PILL, VISIT_STATUS_PILL, fmtTime, fmtMin, elapsedMin } from "./trackingUtils";

// ESS Sales — Kunjungan Saya: mulai (check-in) / selesai (check-out) + daftar hari ini.
export function MyVisitsPanel({ currentUser }) {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [customers, setCustomers] = useState([]);
  const [ci, setCi] = useState({ customer_id: "", customer_name: "", lat: "", lon: "", photo_url: "", notes: "" });
  const [locating, setLocating] = useState(false);
  const [savingIn, setSavingIn] = useState(false);
  const [co, setCo] = useState({ outcome: "order", linked_so_id: "", notes: "", lat: "", lon: "" });
  const [savingOut, setSavingOut] = useState(false);
  const [, setTick] = useState(0);

  useEffect(() => { loadMe(); loadCustomers(); }, []); // eslint-disable-line
  useEffect(() => { const id = setInterval(() => setTick((t) => t + 1), 30000); return () => clearInterval(id); }, []);

  async function loadMe() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/visits/me`); setMe(r.data || null); setError(""); }
    catch (e) { setError(e.response?.data?.detail || "Gagal memuat kunjungan Anda."); }
    finally { setLoading(false); }
  }
  async function loadCustomers() {
    try { const r = await axios.get(`${API}/customers`); setCustomers(Array.isArray(r.data) ? r.data : []); }
    catch (_) { /* customer opsional; bisa isi nama manual */ }
  }
  function getMyLocation(apply) {
    if (!navigator.geolocation) { setError("Browser tidak mendukung geolokasi. Isi lokasi manual bila perlu."); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => { apply(pos.coords.latitude.toFixed(6), pos.coords.longitude.toFixed(6)); setLocating(false); },
      () => { setError("Tidak bisa ambil lokasi (izin ditolak). Kunjungan tetap bisa dimulai."); setLocating(false); },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }
  async function checkIn() {
    if (!ci.customer_id && !ci.customer_name.trim()) { setError("Pilih customer atau isi nama customer."); return; }
    setSavingIn(true);
    try {
      const body = { customer_id: ci.customer_id, customer_name: ci.customer_name, photo_url: ci.photo_url, notes: ci.notes };
      if (ci.lat !== "") body.lat = parseFloat(ci.lat);
      if (ci.lon !== "") body.lon = parseFloat(ci.lon);
      await axios.post(`${API}/hr/visits/check-in`, body);
      // Cohesion H2: publikasikan posisi sekarang agar muncul di Live Map manajer (best-effort).
      if (ci.lat !== "" && ci.lon !== "") {
        try { await axios.post(`${API}/hr/field-tracks`, { lat: parseFloat(ci.lat), lon: parseFloat(ci.lon), accuracy: 0 }); } catch (_) { /* noop */ }
      }
      setNotice("Kunjungan dimulai."); setError("");
      setCi({ customer_id: "", customer_name: "", lat: "", lon: "", photo_url: "", notes: "" });
      loadMe();
    } catch (e) { setError(e.response?.data?.detail || "Gagal memulai kunjungan."); }
    finally { setSavingIn(false); }
  }
  async function checkOut(visitId) {
    setSavingOut(true);
    try {
      const body = { outcome: co.outcome, linked_so_id: co.linked_so_id, notes: co.notes };
      if (co.lat !== "") body.lat = parseFloat(co.lat);
      if (co.lon !== "") body.lon = parseFloat(co.lon);
      await axios.post(`${API}/hr/visits/${visitId}/check-out`, body);
      setNotice("Kunjungan selesai dicatat."); setError("");
      setCo({ outcome: "order", linked_so_id: "", notes: "", lat: "", lon: "" });
      loadMe();
    } catch (e) { setError(e.response?.data?.detail || "Gagal menyelesaikan kunjungan."); }
    finally { setSavingOut(false); }
  }

  const custOpts = [{ value: "", label: "— pilih pelanggan —" }, ...customers.map((c) => ({ value: c.id, label: c.name }))];
  const ongoing = me?.ongoing;
  const today = Array.isArray(me?.today) ? me.today : [];
  const doneToday = today.filter((v) => v.status === "done").length;

  return (
    <div data-testid="my-visits-panel">
      {notice && (<div className="notice-bar success" data-testid="my-visits-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>)}
      <ErrorNotice message={error} onRetry={loadMe} onDismiss={() => setError("")} testId="my-visits-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2"><MapPin size={16} className="text-[#0058CC]" /><h2 data-testid="my-visits-title">Kunjungan Saya</h2></div>
          <div className="flex items-center gap-3 text-[12px]">
            <span className="text-[#6B6B73]">Hari ini: <b className="tabular-nums" data-testid="my-visits-count">{today.length}</b> ({doneToday} selesai)</span>
            <button data-testid="my-visits-refresh" onClick={loadMe} className="icon-button" title="Muat ulang"><RefreshCw size={15} /></button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="section-card py-12 text-center text-[12px] text-[#6B6B73]" data-testid="my-visits-loading">Memuat kunjungan...</div>
      ) : (
        <>
          {ongoing ? (
            <div className="section-card mb-3 border-l-4" style={{ borderLeftColor: "#B7791F" }} data-testid="ongoing-visit-card">
              <div className="section-body">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`status-pill ${VISIT_STATUS_PILL.ongoing.cls}`}>{VISIT_STATUS_PILL.ongoing.label}</span>
                    <span className="text-[13px] font-semibold flex items-center gap-1"><Building2 size={14} className="text-[#6B6B73]" /> {ongoing.customer_name}</span>
                  </div>
                  <span className="text-[12px] text-[#6B6B73] flex items-center gap-1"><Clock size={13} /> Mulai {fmtTime(ongoing.check_in?.ts)} · <b className="tabular-nums">{fmtMin(elapsedMin(ongoing.check_in?.ts))}</b></span>
                </div>
                {ongoing.notes && <p className="text-[12px] text-[#6B6B73] mb-2">Catatan: {ongoing.notes}</p>}
                <div className="border-t border-[#EFF0F2] pt-3 grid gap-2 md:grid-cols-[150px_1fr_auto]">
                  <KNSelect data-testid="checkout-outcome" value={co.outcome} onValueChange={(v) => setCo((s) => ({ ...s, outcome: v }))} className="field" options={OUTCOME_OPTS} />
                  <input data-testid="checkout-linked-so" value={co.linked_so_id} onChange={(e) => setCo((s) => ({ ...s, linked_so_id: e.target.value }))} className="field" placeholder="No. SO terkait (opsional)" />
                  <button data-testid="checkout-submit" disabled={savingOut} onClick={() => checkOut(ongoing.id)} className="primary-button justify-center"><Square size={13} /> {savingOut ? "..." : "Selesai Kunjungan"}</button>
                </div>
                <input data-testid="checkout-notes" value={co.notes} onChange={(e) => setCo((s) => ({ ...s, notes: e.target.value }))} className="field mt-2" placeholder="Catatan hasil kunjungan (opsional)" />
              </div>
            </div>
          ) : (
            <div className="section-card mb-3" data-testid="checkin-card">
              <div className="section-head"><div className="flex items-center gap-2"><Play size={15} className="text-[#1F9D55]" /><h2>Mulai Kunjungan Baru</h2></div></div>
              <div className="section-body grid gap-2 md:grid-cols-2">
                <div>
                  <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Pelanggan</label>
                  <KNSelect data-testid="checkin-customer" value={ci.customer_id} onValueChange={(v) => setCi((s) => ({ ...s, customer_id: v, customer_name: "" }))} className="field" placeholder="— pilih pelanggan —" searchable options={custOpts} />
                </div>
                <div>
                  <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">atau nama pelanggan (tanpa master)</label>
                  <input data-testid="checkin-customer-name" value={ci.customer_name} onChange={(e) => setCi((s) => ({ ...s, customer_name: e.target.value, customer_id: "" }))} className="field" placeholder="Nama pelanggan baru" />
                </div>
                <div className="md:col-span-2 grid gap-2 grid-cols-[1fr_1fr_auto] items-end">
                  <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Latitude</label>
                    <input data-testid="checkin-lat" value={ci.lat} onChange={(e) => setCi((s) => ({ ...s, lat: e.target.value }))} className="field tabular-nums" placeholder="-6.917" /></div>
                  <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Longitude</label>
                    <input data-testid="checkin-lon" value={ci.lon} onChange={(e) => setCi((s) => ({ ...s, lon: e.target.value }))} className="field tabular-nums" placeholder="107.619" /></div>
                  <button data-testid="checkin-geo" onClick={() => getMyLocation((la, lo) => setCi((s) => ({ ...s, lat: la, lon: lo })))} className="secondary-button justify-center" type="button"><LocateFixed size={13} /> {locating ? "..." : "Lokasi Saya"}</button>
                </div>
                <input data-testid="checkin-photo" value={ci.photo_url} onChange={(e) => setCi((s) => ({ ...s, photo_url: e.target.value }))} className="field md:col-span-2" placeholder="URL foto bukti (opsional)" />
                <input data-testid="checkin-notes" value={ci.notes} onChange={(e) => setCi((s) => ({ ...s, notes: e.target.value }))} className="field md:col-span-2" placeholder="Catatan (opsional)" />
                <div className="md:col-span-2 flex justify-end">
                  <button data-testid="checkin-submit" disabled={savingIn} onClick={checkIn} className="primary-button justify-center"><Play size={13} /> {savingIn ? "Memulai..." : "Mulai Kunjungan"}</button>
                </div>
              </div>
            </div>
          )}

          <div className="section-card">
            <div className="px-3 py-2 border-b border-[#EFF0F2] text-[11px] font-bold uppercase text-[#6B6B73]">Kunjungan Hari Ini</div>
            {today.length === 0 ? (
              <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="my-visits-empty"><MapPin className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada kunjungan hari ini. Mulai kunjungan pertama Anda.</p></div>
            ) : (
              <div className="divide-y divide-[#EFF0F2]">
                {today.map((v) => {
                  const oc = OUTCOME_PILL[v.outcome] || OUTCOME_PILL[""];
                  const st = VISIT_STATUS_PILL[v.status] || VISIT_STATUS_PILL.done;
                  return (
                    <div key={v.id} data-testid={`my-visit-row-${v.id}`} className="flex items-center gap-3 px-3 py-2.5 hover:bg-[#FAFBFC]">
                      <span className="text-[12.5px] font-semibold truncate flex-1 flex items-center gap-1"><Building2 size={13} className="text-[#6B6B73]" /> {v.customer_name}</span>
                      <span className="text-[11.5px] tabular-nums text-[#6B6B73]">{fmtTime(v.check_in?.ts)}–{fmtTime(v.check_out?.ts)}</span>
                      <span className="text-[11.5px] tabular-nums w-12 text-right">{fmtMin(v.duration_min)}</span>
                      <span className={`status-pill ${oc.cls}`}>{oc.label}</span>
                      <span className={`status-pill ${st.cls}`}>{st.label}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
