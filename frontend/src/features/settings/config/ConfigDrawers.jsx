/**
 * ConfigDrawers — panel penjelas yang menjawab 3 pertanyaan user:
 *
 *  1. WhyThisValueDrawer  — "Kenapa nilainya begini?"  (jejak lapisan, mana yang menang)
 *  2. SimulatorPanel      — "Coba dulu"                (lihat akibat sebelum menyimpan)
 *  3. ChangeHistoryDrawer — "Riwayat"                  (siapa, kapan, dari→ke, alasan)
 *
 * Ketiganya sengaja memakai bahasa awam, bukan istilah teknis.
 */
import { useEffect, useState } from "react";
import { X, Layers, FlaskConical, History, Play, Check, AlertTriangle, Ban, Clock } from "lucide-react";
import ErrorNotice from "../../../components/ErrorNotice";
import { configApi, errMsg, formatValue, idNum, shortVal, LAYER_TONE, VERDICT_TONE } from "./configApi";

function Shell({ title, subtitle, icon, onClose, children, testId }) {
  return (
    <div className="cfg-drawer-backdrop" data-testid={`${testId}-backdrop`}>
      <div className="cfg-drawer" data-testid={testId} role="dialog" aria-label={title}>
        <div className="cfg-drawer-head">
          <div className="cfg-drawer-title">
            {icon}
            <div>
              <h3>{title}</h3>
              {subtitle ? <p>{subtitle}</p> : null}
            </div>
          </div>
          <button className="icon-button" onClick={onClose} data-testid={`${testId}-close`}
            aria-label="Tutup">
            <X size={16} />
          </button>
        </div>
        <div className="cfg-drawer-body">{children}</div>
      </div>
    </div>
  );
}

/* ─── 1. Kenapa nilainya begini? ─────────────────────────────────────────── */
export function WhyThisValueDrawer({ entry, ctx, onClose }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    setErr("");
    configApi
      .explain({ key: entry.key, ...ctx })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setErr(errMsg(e, "Gagal memuat jejak nilai.")));
    return () => { alive = false; };
  }, [entry.key, ctx]);

  const layers = data?.explain || [];
  return (
    <Shell
      testId="cfg-why-drawer"
      icon={<Layers size={18} />}
      title="Kenapa nilainya begini?"
      subtitle={entry.label}
      onClose={onClose}
    >
      <ErrorNotice message={err} />
      {!data && !err ? <p className="cfg-hint">Memuat…</p> : null}
      {data ? (
        <>
          <div className="cfg-why-answer" data-testid="cfg-why-answer">
            <span className="cfg-why-value">{formatValue(entry, data.value)}</span>
            <span className={`badge-${LAYER_TONE[data.source_layer] || "muted"}`}>
              ditentukan oleh: {data.source_label}
            </span>
          </div>
          <p className="cfg-hint">
            Sistem membaca nilai dari lapisan paling umum ke paling khusus. Lapisan paling
            khusus yang berisi nilai adalah yang dipakai.
          </p>
          <ol className="cfg-layer-list" data-testid="cfg-layer-list">
            {layers.map((l, i) => (
              <li
                key={`${l.layer}-${i}`}
                className={`cfg-layer ${l.winner ? "winner" : ""} ${l.present ? "" : "empty"}`}
                data-testid={`cfg-layer-${l.layer}`}
              >
                <div className="cfg-layer-head">
                  <span className={`badge-${LAYER_TONE[l.layer] || "muted"}`}>{l.label}</span>
                  {l.scope_id ? <code className="cfg-scope-id">{l.scope_id}</code> : null}
                  {l.winner ? (
                    <span className="cfg-layer-win">
                      <Check size={12} /> DIPAKAI
                    </span>
                  ) : l.present ? (
                    <span className="cfg-layer-lose">tertimpa lapisan lebih khusus</span>
                  ) : (
                    <span className="cfg-layer-lose">belum diatur</span>
                  )}
                </div>
                <div className="cfg-layer-val">
                  {l.present ? formatValue(entry, l.value) : "—"}
                </div>
                <p className="cfg-layer-note">{l.note}</p>
                {l.changed_by ? (
                  <p className="cfg-layer-meta">
                    diubah oleh <b>{l.changed_by}</b>
                    {l.changed_at ? ` · ${String(l.changed_at).slice(0, 19).replace("T", " ")}` : ""}
                    {l.reason ? ` · alasan: “${l.reason}”` : ""}
                  </p>
                ) : null}
                {(l.scheduled || []).length > 0 ? (
                  <p className="cfg-layer-sched">
                    <Clock size={12} /> {l.scheduled.length} perubahan terjadwal:
                    {l.scheduled.map((s, k) => (
                      <span key={k}>
                        {" "}
                        {formatValue(entry, s.value)} mulai{" "}
                        {String(s.effective_from).slice(0, 10)}
                        {k < l.scheduled.length - 1 ? " ·" : ""}
                      </span>
                    ))}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
          <div className="cfg-wiring-box" data-testid="cfg-why-wiring">
            <h4>Bagian sistem yang memakai pengaturan ini</h4>
            <ul>
              {(entry.consumers || []).map((c) => (
                <li key={c}><code>{c}</code></li>
              ))}
              {(entry.consumers || []).length === 0 ? <li>—</li> : null}
            </ul>
            {data.wiring ? (
              <p className="cfg-hint-sm">
                Status wiring: <b>{data.wiring.wiring_status}</b>
                {data.wiring.consumers_stale?.length
                  ? ` · referensi basi: ${data.wiring.consumers_stale.join(", ")}`
                  : ""}
              </p>
            ) : null}
          </div>
        </>
      ) : null}
    </Shell>
  );
}

/* ─── 2. Coba dulu (Simulator) ───────────────────────────────────────────── */
export function SimulatorPanel({ entry, ctx, draftValue, onClose }) {
  const [sample, setSample] = useState({});
  const [useDraft, setUseDraft] = useState(draftValue !== undefined);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async (nextSample = sample, withDraft = useDraft) => {
    setBusy(true); setErr("");
    try {
      const overrides = withDraft && draftValue !== undefined ? { [entry.key]: draftValue } : {};
      const d = await configApi.simulate({
        simulator: entry.simulate || "", key: entry.key,
        sample: nextSample, overrides, ctx,
      });
      setRes(d);
      setSample(d.sample || nextSample);
    } catch (e) {
      setErr(errMsg(e, "Simulasi gagal."));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { run({}, useDraft); /* eslint-disable-line */ }, []);

  const Icon = { ok: Check, warn: AlertTriangle, block: Ban }[res?.verdict] || Check;
  return (
    <Shell
      testId="cfg-simulator"
      icon={<FlaskConical size={18} />}
      title="Coba dulu — lihat akibatnya"
      subtitle={entry.label}
      onClose={onClose}
    >
      <ErrorNotice message={err} onRetry={() => run()} />
      <p className="cfg-hint">
        Masukkan contoh angka, lalu lihat aturan mana yang menang dan hasil hitungnya.
        Tidak ada yang disimpan di langkah ini.
      </p>

      {draftValue !== undefined ? (
        <label className="cfg-check-row" data-testid="cfg-sim-use-draft">
          <input type="checkbox" checked={useDraft}
            onChange={(e) => { setUseDraft(e.target.checked); run(sample, e.target.checked); }} />
          <span>Pakai nilai yang sedang saya isi ({formatValue(entry, draftValue)}) — belum tersimpan</span>
        </label>
      ) : null}

      {(res?.inputs || []).length > 0 ? (
        <div className="cfg-sim-inputs" data-testid="cfg-sim-inputs">
          {res.inputs.map((inp) => (
            <label key={inp.name} className="cfg-sim-field">
              <span>{inp.label}{inp.unit ? ` (${inp.unit})` : ""}</span>
              {inp.type === "bool" ? (
                <input type="checkbox" checked={!!sample[inp.name]}
                  onChange={(e) => setSample({ ...sample, [inp.name]: e.target.checked })}
                  data-testid={`cfg-sim-in-${inp.name}`} />
              ) : (
                <input
                  className="form-input cfg-input"
                  type={inp.type === "text" ? "text" : "number"}
                  value={sample[inp.name] ?? inp.default ?? ""}
                  onChange={(e) => setSample({
                    ...sample,
                    [inp.name]: inp.type === "text" ? e.target.value : Number(e.target.value),
                  })}
                  data-testid={`cfg-sim-in-${inp.name}`}
                />
              )}
            </label>
          ))}
        </div>
      ) : null}

      <button className="btn-primary cfg-sim-run" onClick={() => run()} disabled={busy}
        data-testid="cfg-sim-run">
        <Play size={14} /> {busy ? "Menghitung…" : "Hitung ulang"}
      </button>

      {res ? (
        <>
          <div className={`cfg-sim-result tone-${VERDICT_TONE[res.verdict] || "muted"}`}
            data-testid="cfg-sim-result">
            <Icon size={16} />
            <span>{res.result}</span>
          </div>
          <h4 className="cfg-sub">Langkah hitung</h4>
          <table className="data-table cfg-sim-steps" data-testid="cfg-sim-steps">
            <tbody>
              {(res.steps || []).map((s, i) => (
                <tr key={i}>
                  <td>{s.label}</td>
                  <td className="tabular-nums cfg-right"><b>{s.value}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
          <h4 className="cfg-sub">Aturan yang dipakai</h4>
          <table className="data-table" data-testid="cfg-sim-resolved">
            <thead>
              <tr><th>Pengaturan</th><th>Nilai</th><th>Asal</th></tr>
            </thead>
            <tbody>
              {(res.resolved || []).map((r) => (
                <tr key={r.key} className={r.hypothetical ? "cfg-row-hyp" : ""}>
                  <td>{r.label}</td>
                  <td className="tabular-nums">{String(r.value)}</td>
                  <td>
                    <span className={`badge-${LAYER_TONE[r.source_layer] || "muted"}`}>
                      {r.hypothetical ? "sedang dicoba" : r.source_label}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </Shell>
  );
}

/* ─── 3. Riwayat perubahan ───────────────────────────────────────────────── */
export function ChangeHistoryDrawer({ entry, onClose }) {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    configApi
      .history({ key: entry?.key || "", limit: 200 })
      .then((d) => alive && setRows(d.rows || []))
      .catch((e) => alive && setErr(errMsg(e, "Gagal memuat riwayat.")));
    return () => { alive = false; };
  }, [entry?.key]);

  return (
    <Shell
      testId="cfg-history"
      icon={<History size={18} />}
      title="Riwayat perubahan"
      subtitle={entry?.label || "Semua setting"}
      onClose={onClose}
    >
      <ErrorNotice message={err} />
      <p className="cfg-hint">
        Setiap perubahan disimpan sebagai catatan baru (tidak menimpa), sehingga selalu bisa
        ditelusuri siapa mengubah apa dan mengapa.
      </p>
      {rows && rows.length === 0 ? (
        <p className="cfg-empty" data-testid="cfg-history-empty">
          Belum ada perubahan pada pengaturan ini — nilainya masih sesuai bawaan sistem.
        </p>
      ) : null}
      {rows && rows.length > 0 ? (
        <table className="data-table" data-testid="cfg-history-table">
          <thead>
            <tr>
              <th>Waktu</th><th>Pengaturan</th><th>Cakupan</th>
              <th>Dari → Ke</th><th>Oleh</th><th>Alasan</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} data-testid={`cfg-history-row-${r.id}`}>
                <td className="cfg-nowrap">
                  {String(r.changed_at || "").slice(0, 16).replace("T", " ")}
                  {r.scheduled ? (
                    <span className="badge-orange cfg-ml">terjadwal</span>
                  ) : null}
                </td>
                <td>{r.label}</td>
                <td>
                  <span className="badge-muted">
                    {r.scope_type}{r.scope_id ? `: ${r.scope_id}` : ""}
                  </span>
                </td>
                <td className="tabular-nums">
                  <span className="cfg-from">{shortVal(r.prev_value)}</span>
                  {" → "}
                  <b>{shortVal(r.value)}</b>
                  {r.unit ? ` ${r.unit}` : ""}
                </td>
                <td>{r.changed_by || "—"}</td>
                <td>{r.reason || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {rows === null && !err ? <p className="cfg-hint">Memuat…</p> : null}
      <p className="cfg-hint-sm">
        Catatan: <b>{idNum((rows || []).length, 0)}</b> perubahan tercatat.
      </p>
    </Shell>
  );
}

/* Riwayat ringkas yang langsung terlihat di tab (tanpa harus buka drawer). */
export function ChangeHistoryInline() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let alive = true;
    configApi
      .history({ limit: 50 })
      .then((d) => alive && setRows(d.rows || []))
      .catch((e) => alive && setErr(errMsg(e, "Gagal memuat riwayat.")));
    return () => { alive = false; };
  }, []);
  return (
    <>
      <ErrorNotice message={err} />
      {rows === null && !err ? <p className="cfg-hint">Memuat…</p> : null}
      {rows && rows.length === 0 ? (
        <p className="cfg-empty" data-testid="cfg-history-inline-empty">
          Belum ada perubahan konfigurasi — semua nilai masih bawaan sistem.
        </p>
      ) : null}
      {rows && rows.length > 0 ? (
        <table className="data-table" data-testid="cfg-history-inline">
          <thead>
            <tr>
              <th>Waktu</th><th>Pengaturan</th><th>Cakupan</th>
              <th>Dari → Ke</th><th>Oleh</th><th>Alasan</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="cfg-nowrap">
                  {String(r.changed_at || "").slice(0, 16).replace("T", " ")}
                </td>
                <td>{r.label}</td>
                <td>
                  <span className="badge-muted">
                    {r.scope_type}{r.scope_id ? `: ${r.scope_id}` : ""}
                  </span>
                </td>
                <td className="tabular-nums">
                  <span className="cfg-from">{shortVal(r.prev_value)}</span> → <b>{shortVal(r.value)}</b>
                </td>
                <td>{r.changed_by || "—"}</td>
                <td>{r.reason || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </>
  );
}
