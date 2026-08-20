/**
 * ConfigHealthPanel — layar "Kesehatan Konfigurasi" (user story G-0 #8).
 *
 * Menjawab pertanyaan auditor: *"apakah setiap tombol pengaturan benar-benar
 * mengubah perilaku sistem?"* — masalah nyata yang ditemukan audit 2026-07-26:
 * dulu ada **6 tombol palsu** (ORPHAN_UI: ada UI tapi nol pembaca di kode) dan
 * **31 aturan tersembunyi** (dipakai mesin tapi tak ada UI sama sekali).
 *
 * Sumber: GET /api/config/health (registry × pemindaian kode nyata).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ShieldCheck, RefreshCw, AlertTriangle, Ban, CheckCircle2, Search, Loader2,
} from "lucide-react";
import ErrorNotice from "../../../components/ErrorNotice";
import { configApi, errMsg, WIRING_LABEL, WIRING_TONE } from "./configApi";

const STATUS_HELP = {
  OK: "Setting ini dibaca oleh kode yang benar-benar ada. Mengubahnya PASTI mengubah perilaku sistem.",
  STALE: "Referensi kode tercatat, tetapi berkas/fungsinya sudah berpindah. Perlu diperbarui.",
  MISSING: "Registry menunjuk kode yang TIDAK ADA — inilah 'tombol palsu': diubah tapi tak berefek.",
  NOT_USED: "Sengaja tidak dipakai. Alasannya ditampilkan agar tidak dihidupkan tanpa sadar.",
};
export default function ConfigHealthPanel({ onOpenSetting }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(true);
  const [q, setQ] = useState("");
  const [only, setOnly] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      setData(await configApi.health());
    } catch (e) {
      setErr(errMsg(e, "Gagal memuat kesehatan konfigurasi."));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => {
    const all = data?.rows || [];
    const term = q.trim().toLowerCase();
    return all.filter((r) => {
      if (only && r.wiring_status !== only) return false;
      if (!term) return true;
      return `${r.key} ${r.label} ${r.group}`.toLowerCase().includes(term);
    });
  }, [data, q, only]);

  const summary = data?.summary || {};
  // BENTUK DATA NYATA dari GET /api/config/health (diverifikasi via curl):
  //   healthy: bool · broken: ARRAY berisi key yang bermasalah (bukan angka)
  //   scheduled_applied: OBJEK {applied, pending} (bukan angka)
  //   legend: {STATUS: penjelasan} — dipakai sebagai sumber kebenaran teks status
  // Merender objek/array langsung ke JSX memicu React error #31, jadi selalu
  // diturunkan dulu ke primitif di sini.
  const brokenList = Array.isArray(data?.broken) ? data.broken : [];
  const broken = brokenList.length;
  const sched = data?.scheduled_applied || {};
  const schedApplied = Number(sched.applied || 0);
  const schedPending = Number(sched.pending || 0);
  const legend = data?.legend || {};
  const orderedStatuses = ["OK", "STALE", "MISSING", "NOT_USED"];
  const helpFor = (s) => legend[s] || STATUS_HELP[s] || "";

  return (
    <section className="cfg-health" data-testid="cfg-health-panel">
      <ErrorNotice message={err} onRetry={load} />

      <div className={`cfg-health-verdict ${broken ? "bad" : "good"}`}
        data-testid="cfg-health-verdict">
        {broken ? <AlertTriangle size={20} /> : <ShieldCheck size={20} />}
        <div>
          <h3>
            {broken
              ? `${broken} setting BELUM tersambung ke mesin`
              : "Semua setting aktif benar-benar tersambung ke mesin"}
          </h3>
          <p>
            {broken
              ? `Setting berikut bisa diubah dari layar ini tetapi TIDAK akan mengubah perilaku sistem (tombol palsu): ${brokenList.slice(0, 6).join(", ")}${brokenList.length > 6 ? ` … +${brokenList.length - 6} lagi` : ""}.`
              : `Diperiksa ${data?.total || 0} setting: setiap setting yang berstatus aktif punya kode pembaca yang nyata, sehingga mengubahnya pasti berefek. Tidak ada tombol palsu.`}
          </p>
        </div>
        <button className="btn-secondary btn-sm" onClick={load} disabled={busy}
          data-testid="cfg-health-refresh">
          {busy ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />} Periksa ulang
        </button>
      </div>

      <div className="cfg-health-cards">
        {orderedStatuses.map((s) => {
          const n = Number(summary[s] || 0);
          // Nol masalah TIDAK boleh tampil merah/oranye — itu justru kabar baik.
          const tone = n === 0 && (s === "STALE" || s === "MISSING") ? "muted" : WIRING_TONE[s];
          return (
            <button
              key={s}
              className={`cfg-health-kpi tone-${tone} ${only === s ? "active" : ""}`}
              onClick={() => setOnly(only === s ? "" : s)}
              data-testid={`cfg-health-kpi-${s}`}
              title={helpFor(s)}
            >
              <span className="cfg-health-kpi-num">{n}</span>
              <span className="cfg-health-kpi-label">{WIRING_LABEL[s]}</span>
            </button>
          );
        })}
      </div>

      <div className="cfg-health-legend" data-testid="cfg-health-legend">
        <h4>Arti setiap status</h4>
        <ul>
          {orderedStatuses.map((s) => (
            <li key={s}>
              <span className={`badge-${WIRING_TONE[s]}`}>{WIRING_LABEL[s]}</span>
              <span>{helpFor(s)}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="cfg-health-toolbar">
        <label className="cfg-search-wrap cfg-search-sm">
          <Search size={14} />
          <input
            className="form-input"
            placeholder="Cari pengaturan… (mis. denda, PPN, toleransi)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid="cfg-health-search"
          />
        </label>
        {only ? (
          <button className="btn-secondary btn-sm" onClick={() => setOnly("")}
            data-testid="cfg-health-clear-filter">
            Tampilkan semua status
          </button>
        ) : null}
        <span className="cfg-hint-sm">
          Menampilkan <b>{rows.length}</b> dari {data?.total || 0} pengaturan
        </span>
      </div>

      {busy && !data ? <p className="cfg-hint">Memuat…</p> : null}

      {data ? (
        <table className="data-table cfg-health-table" data-testid="cfg-health-table">
          <thead>
            <tr>
              <th>Pengaturan</th>
              <th>Kelompok</th>
              <th>Status wiring</th>
              <th>Dibaca oleh kode</th>
              <th> </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} data-testid={`cfg-health-row-${r.key}`}>
                <td>
                  <b>{r.label}</b>
                  <br />
                  <code className="cfg-key">{r.key}</code>
                </td>
                <td>{r.group}</td>
                <td>
                  <span className={`badge-${WIRING_TONE[r.wiring_status]}`}>
                    {WIRING_LABEL[r.wiring_status]}
                  </span>
                  {r.wiring_status === "NOT_USED" && r.not_used_reason ? (
                    <p className="cfg-hint-sm">{r.not_used_reason}</p>
                  ) : null}
                  {r.consumers_missing?.length ? (
                    <p className="cfg-inline-err">
                      <Ban size={11} /> tak ditemukan: {r.consumers_missing.join(", ")}
                    </p>
                  ) : null}
                  {r.consumers_stale?.length ? (
                    <p className="cfg-inline-warn">
                      <AlertTriangle size={11} /> basi: {r.consumers_stale.join(", ")}
                    </p>
                  ) : null}
                </td>
                <td>
                  {r.consumer_count > 0 ? (
                    <span className="cfg-consumer-list">
                      <CheckCircle2 size={12} /> {r.consumer_count} tempat
                      <br />
                      {(r.consumers_ok || []).slice(0, 2).map((c) => (
                        <code key={c}>{c}</code>
                      ))}
                    </span>
                  ) : (
                    <span className="cfg-hint-sm">—</span>
                  )}
                </td>
                <td>
                  <button className="cfg-link-btn" onClick={() => onOpenSetting?.(r)}
                    data-testid={`cfg-health-open-${r.key}`}>
                    Buka pengaturan
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && !busy ? (
              <tr>
                <td colSpan={5} className="cfg-empty">Tidak ada pengaturan yang cocok.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      ) : null}

      {schedApplied || schedPending ? (
        <p className="cfg-hint-sm" data-testid="cfg-health-scheduled">
          {schedApplied
            ? `${schedApplied} perubahan terjadwal baru saja jatuh tempo dan sudah diaktifkan. `
            : ""}
          {schedPending
            ? `${schedPending} perubahan masih menunggu tanggal berlakunya.`
            : ""}
        </p>
      ) : null}
    </section>
  );
}
