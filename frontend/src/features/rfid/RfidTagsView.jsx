import { useEffect, useState } from "react";
import { Tag, RefreshCw, Trash2, Zap, Boxes, Radio, PackageSearch } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import axios, { API } from "../../services/apiClient";
import { nf, q, fmtTime, Stat, EmptyBox, TabBtn, SectionCard, RfidHeader, useWarehouses } from "./rfidShared";

export default function RfidTagsView({ currentUser, selectedEntity }) {
  const [tab, setTab] = useState("tags");
  const { whId, setWhId, whOpts } = useWarehouses();
  const [summary, setSummary] = useState(null);
  const [tags, setTags] = useState([]);
  const [untagged, setUntagged] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [msg, setMsg] = useState("");

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const params = whId ? { warehouse_id: whId } : {};
      const [s, t, u] = await Promise.all([
        axios.get(`${API}/rfid/summary`, { params }),
        axios.get(`${API}/rfid/tags`, { params: { ...params, status: "active" } }),
        axios.get(`${API}/rfid/untagged-rolls`, { params }),
      ]);
      setSummary(s.data); setTags(t.data.tags || []); setUntagged(u.data.rolls || []);
    } catch (e) { setError(e.response?.data?.detail || e.message || "Gagal memuat data RFID"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [whId, selectedEntity]); // eslint-disable-line

  const flash = (m) => { setMsg(m); setTimeout(() => setMsg(""), 2500); };
  const encode = async (rollId) => {
    setBusy(true); setError(null);
    try { await axios.post(`${API}/rfid/tags/encode`, { roll_id: rollId }); flash("Tag RFID ter-encode."); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal encode tag"); } finally { setBusy(false); }
  };
  const autoEncode = async () => {
    setBusy(true); setError(null);
    try { const r = await axios.post(`${API}/rfid/tags/auto-encode`, { warehouse_id: whId || null }); flash(`${r.data.encoded} roll ter-encode otomatis.`); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal auto-encode"); } finally { setBusy(false); }
  };
  const retire = async (tagId) => {
    setBusy(true); setError(null);
    try { await axios.delete(`${API}/rfid/tags/${tagId}`); flash("Tag di-retire (roll kembali tanpa tag)."); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal retire tag"); } finally { setBusy(false); }
  };

  return (
    <div data-testid="rfid-tags-view" className="space-y-4">
      <RfidHeader icon={Tag} title="Tags (tag ↔ item)" subtitle="Encode tag EPC ke roll fisik. Roll-as-SSOT: encode tak mengubah stok.">
        <KNSelect data-testid="rfid-tags-wh" value={whId} onValueChange={setWhId} options={whOpts}
          className="field !py-1 !px-2 text-[12px] w-auto" placeholder="Gudang" />
        <button data-testid="rfid-tags-refresh" onClick={load}
          className="flex items-center gap-1 rounded-lg border border-[#EFF0F2] bg-white px-3 py-1.5 text-[12px] font-semibold hover:bg-[#F5F5F7]">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </RfidHeader>

      {error && <ErrorNotice message={error} onRetry={load} />}
      {msg && <div className="rounded-lg bg-[#E7F7EC] text-[#1B7E3B] text-[12px] font-semibold px-3 py-2">{msg}</div>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat icon={Tag} label="Total Tag" value={summary?.tags_total ?? 0} color="#0058CC" loading={loading} testId="rfid-stat-total" />
        <Stat icon={Radio} label="Tag Aktif" value={summary?.tags_active ?? 0} color="#34C759" loading={loading} testId="rfid-stat-active" />
        <Stat icon={Boxes} label="Roll Belum Ber-tag" value={summary?.untagged_rolls ?? 0} color="#FF9500" loading={loading} testId="rfid-stat-untagged" />
        <Stat icon={PackageSearch} label="Reader Online" value={`${summary?.devices_online ?? 0}/${summary?.devices_total ?? 0}`} color="#5856D6" loading={loading} />
      </div>

      <div className="flex gap-1 border-b border-[#EFF0F2]">
        <TabBtn id="tags" tab={tab} setTab={setTab} label={`Tag Aktif${tags.length ? ` (${tags.length})` : ""}`} testId="rfid-tab-tags" />
        <TabBtn id="untagged" tab={tab} setTab={setTab} label={`Belum Ber-tag${untagged.length ? ` (${untagged.length})` : ""}`} testId="rfid-tab-untagged" />
      </div>

      {tab === "tags" ? (
        <SectionCard title="Daftar Tag RFID Aktif">
          {loading ? <div className="h-16 bg-[#F5F5F7] rounded animate-pulse" />
            : tags.length === 0 ? <EmptyBox icon={Tag} text="Belum ada tag aktif. Encode roll di tab 'Belum Ber-tag'." />
              : (
                <div className="overflow-x-auto">
                  <table className="w-full text-[12px]">
                    <thead><tr className="text-left text-[11px] text-[#8E8E93] border-b border-[#EFF0F2]">
                      <th className="py-2 pr-2">EPC</th><th className="pr-2">SKU</th><th className="pr-2">Produk</th>
                      <th className="pr-2">Roll / Lot</th><th className="pr-2">Last Seen</th><th className="pr-2 text-right">Aksi</th>
                    </tr></thead>
                    <tbody>
                      {tags.map((t) => (
                        <tr key={t.id} data-testid={`rfid-tag-row-${t.id}`} className="border-b border-[#F5F5F7] hover:bg-[#FAFAFB]">
                          <td className="py-2 pr-2 font-mono font-semibold text-[11px]">{t.epc}</td>
                          <td className="pr-2">{t.sku || "—"}</td>
                          <td className="pr-2">{t.product_name || "—"}</td>
                          <td className="pr-2">{t.roll_no} · {t.lot || "—"}</td>
                          <td className="pr-2 text-[#6B6B73]">{t.last_seen_at ? `${fmtTime(t.last_seen_at)} @ ${t.last_seen_location || "?"}` : "belum terbaca"}</td>
                          <td className="pr-2 text-right">
                            <button data-testid={`rfid-retire-${t.id}`} disabled={busy} onClick={() => retire(t.id)}
                              className="inline-flex items-center gap-1 text-[#C0341D] hover:bg-[#FBE9E7] rounded px-2 py-1 disabled:opacity-40">
                              <Trash2 size={13} /> Retire
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
        </SectionCard>
      ) : (
        <SectionCard title="Roll Fisik Belum Ber-tag" right={
          <button data-testid="rfid-auto-encode" disabled={busy || untagged.length === 0} onClick={autoEncode}
            className="flex items-center gap-1 rounded-lg bg-[#0058CC] text-white px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40">
            <Zap size={14} /> Auto-Encode Semua
          </button>}>
          {loading ? <div className="h-16 bg-[#F5F5F7] rounded animate-pulse" />
            : untagged.length === 0 ? <EmptyBox icon={Radio} text="Semua roll fisik sudah ber-tag RFID." />
              : (
                <div className="space-y-2">
                  {untagged.map((r) => (
                    <div key={r.id} data-testid={`rfid-untagged-${r.id}`} className="flex flex-wrap items-center gap-2 rounded-lg bg-[#FAFAFB] p-2">
                      <div className="flex-1 min-w-[200px]">
                        <p className="text-[12px] font-semibold">{r.roll_no} · {r.sku || "—"}</p>
                        <p className="text-[11px] text-[#6B6B73]">{r.product_name} — {q(r.length_remaining)} {r.unit} · Lot {r.lot || "—"} · {r.status}</p>
                      </div>
                      <button data-testid={`rfid-encode-${r.id}`} disabled={busy} onClick={() => encode(r.id)}
                        className="flex items-center gap-1 rounded-lg bg-[#0058CC] text-white px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40">
                        <Tag size={13} /> Encode
                      </button>
                    </div>
                  ))}
                </div>
              )}
        </SectionCard>
      )}
    </div>
  );
}
