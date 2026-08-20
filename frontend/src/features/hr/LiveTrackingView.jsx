import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import axios, { API } from "../../services/apiClient";
import { Navigation, RefreshCw, Radio, Battery, Crosshair, Users, MapPin } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import EntityBadge from "../../components/EntityBadge";
import { timeAgo, fmtTime, todayStr, wsTrackUrl, upsertPosition, isFreshTs } from "./trackingUtils";

const BANDUNG = [-6.91747, 107.61912];
const ONLINE_COLOR = "#1F9D55";
const OFFLINE_COLOR = "#9A9BA3";

export default function LiveTrackingView({ currentUser, selectedEntity }) {
  const params = useMemo(
    () => (selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}),
    [selectedEntity]
  );
  const token = typeof window !== "undefined" ? localStorage.getItem("kn_token") || "" : "";

  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedEmp, setSelectedEmp] = useState("");
  const [wsLive, setWsLive] = useState(false);
  const [trailEmp, setTrailEmp] = useState("");

  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const markersRef = useRef({});
  const trailRef = useRef(null);
  const didFitRef = useRef(false);
  const wsRef = useRef(null);

  // ─── Init Leaflet map (sekali) ───
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return undefined;
    const map = L.map(containerRef.current, { zoomControl: true, attributionControl: true }).setView(BANDUNG, 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "\u00a9 OpenStreetMap",
    }).addTo(map);
    mapRef.current = map;
    setTimeout(() => map.invalidateSize(), 200);
    return () => {
      try { map.remove(); } catch (_) { /* noop */ }
      mapRef.current = null;
      markersRef.current = {};
      trailRef.current = null;
      didFitRef.current = false;
    };
  }, []);

  // ─── Polling backbone (selalu jalan; WS hanya pempercepat realtime) ───
  async function loadLatest(showSpin = false) {
    if (showSpin) setLoading(true);
    try {
      const r = await axios.get(`${API}/hr/field-tracks/latest`, { params });
      const list = (Array.isArray(r.data) ? r.data : []).map((p) => ({ ...p, online: isFreshTs(p.ts) }));
      setPositions(list);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat posisi lapangan.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { loadLatest(true); }, [selectedEntity]); // eslint-disable-line
  useEffect(() => {
    const id = setInterval(() => loadLatest(false), 12000);
    return () => clearInterval(id);
  }, [selectedEntity]); // eslint-disable-line

  // ─── WebSocket realtime (subscribe) — merge ke state; fallback polling tetap aktif ───
  useEffect(() => {
    if (!token) return undefined;
    let ws;
    try {
      ws = new WebSocket(wsTrackUrl(token, "subscribe"));
    } catch (_) { return undefined; }
    wsRef.current = ws;
    ws.onopen = () => setWsLive(true);
    ws.onclose = () => setWsLive(false);
    ws.onerror = () => setWsLive(false);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "snapshot" && Array.isArray(msg.data)) {
          setPositions((prev) => {
            let next = prev;
            msg.data.forEach((p) => { next = upsertPosition(next, p); });
            return next;
          });
        } else if (msg.type === "position" && msg.data) {
          setPositions((prev) => upsertPosition(prev, msg.data));
        }
      } catch (_) { /* noop */ }
    };
    return () => { try { ws.close(); } catch (_) { /* noop */ } wsRef.current = null; };
  }, [token]);

  // ─── Sync marker peta saat positions berubah ───
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const seen = new Set();
    positions.forEach((p) => {
      if (p.lat == null || p.lon == null) return;
      seen.add(p.employee_id);
      const color = p.online ? ONLINE_COLOR : OFFLINE_COLOR;
      const ll = [p.lat, p.lon];
      let mk = markersRef.current[p.employee_id];
      if (mk) {
        mk.setLatLng(ll);
        mk.setStyle({ color, fillColor: color });
      } else {
        mk = L.circleMarker(ll, { radius: 8, color, fillColor: color, fillOpacity: 0.85, weight: 3 });
        mk.addTo(map);
        mk.on("click", () => { setSelectedEmp(p.employee_id); loadTrail(p.employee_id); });
        markersRef.current[p.employee_id] = mk;
      }
      mk.bindTooltip(`${p.employee_name}\u00b7${p.online ? "online" : "offline"}`, { direction: "top", offset: [0, -6] });
    });
    // hapus marker karyawan yang hilang
    Object.keys(markersRef.current).forEach((eid) => {
      if (!seen.has(eid)) { try { map.removeLayer(markersRef.current[eid]); } catch (_) { /* noop */ } delete markersRef.current[eid]; }
    });
    if (!didFitRef.current && positions.length) {
      const pts = positions.filter((p) => p.lat != null).map((p) => [p.lat, p.lon]);
      if (pts.length) { try { map.fitBounds(pts, { padding: [40, 40], maxZoom: 15 }); didFitRef.current = true; } catch (_) { /* noop */ } }
    }
  }, [positions]);

  // ─── Breadcrumb (jejak) seorang karyawan hari ini ───
  async function loadTrail(empId) {
    setTrailEmp(empId);
    try {
      const r = await axios.get(`${API}/hr/field-tracks`, { params: { ...params, employee_id: empId, date: todayStr() } });
      const rows = Array.isArray(r.data) ? r.data : [];
      const map = mapRef.current;
      if (!map) return;
      if (trailRef.current) { try { map.removeLayer(trailRef.current); } catch (_) { /* noop */ } trailRef.current = null; }
      const pts = rows.filter((x) => x.lat != null).map((x) => [x.lat, x.lon]);
      if (pts.length >= 2) {
        trailRef.current = L.polyline(pts, { color: "#0058CC", weight: 3, opacity: 0.7, dashArray: "4 4" }).addTo(map);
        try { map.fitBounds(pts, { padding: [50, 50], maxZoom: 16 }); } catch (_) { /* noop */ }
      }
    } catch (_) { /* noop */ }
  }
  function focusEmp(p) {
    setSelectedEmp(p.employee_id);
    loadTrail(p.employee_id);
    if (mapRef.current && p.lat != null) mapRef.current.setView([p.lat, p.lon], 16);
  }

  const onlineCount = positions.filter((p) => p.online).length;

  return (
    <div data-testid="live-tracking-view">
      <ErrorNotice message={error} onRetry={() => loadLatest(true)} onDismiss={() => setError("")} testId="live-tracking-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Navigation size={16} className="text-[#0058CC]" />
            <h2 data-testid="live-tracking-title">Lacak Lapangan — Posisi Sales Realtime</h2>
          </div>
          <div className="flex items-center gap-2">
            <span data-testid="live-ws-status" className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-full ${wsLive ? "bg-[#E7F6EE] text-[#1F7A45]" : "bg-[#F2F4F7] text-[#6B6B73]"}`}>
              <Radio size={12} /> {wsLive ? "Realtime" : "Polling"}
            </span>
            <button data-testid="live-tracking-refresh" onClick={() => loadLatest(true)} className="icon-button" title="Muat ulang"><RefreshCw size={15} /></button>
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[320px_1fr]">
        {/* Daftar karyawan lapangan */}
        <div className="section-card">
          <div className="flex items-center justify-between px-3 py-2 border-b border-[#EFF0F2]">
            <span className="text-[11px] font-bold uppercase text-[#6B6B73] flex items-center gap-1"><Users size={13} /> Karyawan Lapangan</span>
            <span data-testid="live-online-count" className="text-[11px] font-semibold text-[#1F9D55] tabular-nums">{onlineCount} online</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="live-tracking-loading">Memuat posisi...</div>
          ) : positions.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="live-tracking-empty">
              <MapPin className="mx-auto mb-2 text-gray-300" size={28} />
              <p>Belum ada posisi lapangan terkirim.</p>
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[520px] overflow-y-auto">
              {positions.map((p) => (
                <button key={p.employee_id} data-testid={`live-emp-${p.employee_id}`} onClick={() => focusEmp(p)}
                  className={`w-full text-left px-3 py-2.5 hover:bg-[#FAFBFC] transition ${selectedEmp === p.employee_id ? "bg-[#EEF4FF]" : ""}`}>
                  <div className="flex items-center gap-2">
                    <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: p.online ? ONLINE_COLOR : OFFLINE_COLOR }} />
                    <EntityBadge entityId={p.entity_id} />
                    <span className="text-[12.5px] font-semibold truncate flex-1">{p.employee_name}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 pl-[18px] text-[11px] text-[#6B6B73]">
                    <span>{timeAgo(p.ts)}</span>
                    <span className="inline-flex items-center gap-0.5"><Battery size={12} /> {p.battery != null ? `${Math.round(p.battery)}%` : "\u2014"}</span>
                    <span className="inline-flex items-center gap-0.5"><Crosshair size={11} /> {p.accuracy != null ? `${Math.round(p.accuracy)}m` : "\u2014"}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
          {trailEmp && (
            <div className="px-3 py-2 border-t border-[#EFF0F2] text-[11px] text-[#0058CC] flex items-center justify-between">
              <span>Jejak hari ini ditampilkan</span>
              <button data-testid="live-clear-trail" className="underline" onClick={() => {
                setTrailEmp("");
                if (trailRef.current && mapRef.current) { try { mapRef.current.removeLayer(trailRef.current); } catch (_) { /* noop */ } trailRef.current = null; }
              }}>Bersihkan</button>
            </div>
          )}
        </div>

        {/* Peta */}
        <div className="section-card overflow-hidden">
          <div ref={containerRef} data-testid="live-tracking-map" style={{ height: "560px", width: "100%", borderRadius: "10px" }} />
          <div className="px-3 py-2 text-[11px] text-[#6B6B73] flex items-center gap-3">
            <span className="inline-flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: ONLINE_COLOR }} /> Online (&lt;10 mnt)</span>
            <span className="inline-flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: OFFLINE_COLOR }} /> Offline</span>
            <span className="ml-auto">Klik karyawan untuk lihat jejak GPS · update {fmtTime(positions[0]?.ts)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
