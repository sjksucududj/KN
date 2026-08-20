/**
 * SettingCard — kartu satu setting di Pusat Pengaturan.
 *
 * Menjawab kebingungan user dengan menampilkan 5 hal SEKALIGUS, bukan hanya field kosong:
 *   1. Label awam + nilai efektif  2. "Artinya:"  3. "Kalau diubah:"
 *   4. Contoh angka konkret        5. Badge lapisan asal + status wiring
 * Plus 4 aksi: Kenapa nilainya begini? · Coba dulu · Riwayat · Berlaku sejak.
 */
import { useState } from "react";
import {
  Layers, FlaskConical, History, Save, RotateCcw, Info, Zap,
  CalendarClock, ShieldAlert, Ban, ChevronDown, ChevronUp,
} from "lucide-react";
import SettingEditor from "./SettingEditor";
import {
  formatValue, LAYER_TONE, RISK_LABEL, SCOPE_LABEL, WIRING_LABEL, WIRING_TONE,
} from "./configApi";

export default function SettingCard({
  item, scopeType, scopeId, scopeLabel = "", wiring, canEdit, onSave, onReset,
  onClearEntity, onWhy, onSimulate, onHistory,
}) {
  const [draft, setDraft] = useState(undefined);
  const [reason, setReason] = useState("");
  const [effFrom, setEffFrom] = useState("");
  const [showSched, setShowSched] = useState(false);
  const [showMore, setShowMore] = useState(false);
  const [busy, setBusy] = useState(false);

  const notUsed = item.status === "not_used";
  const dirty = draft !== undefined && JSON.stringify(draft) !== JSON.stringify(item.value);
  const editable = canEdit && !notUsed;
  const wStatus = notUsed ? "NOT_USED" : (wiring?.wiring_status || "OK");
  const scopeSupported = (item.scopes || []).includes(scopeType);
  // FASE E-4 (E4.6) — apakah nilai yang tampil BENAR-BENAR milik badan usaha ini?
  // Kalau ya, ia bisa dicabut ("Kembalikan ke global"); kalau tidak, ia warisan grup
  // dan mengubahnya dari sini akan melahirkan nilai khusus badan usaha (bukan
  // mengubah nilai grup) — itu dijelaskan di kotak konfirmasi di bawah.
  const ownedByEntity = scopeType === "entity" && Boolean(scopeId)
    && ["entity", "legacy_entity"].includes(item.source_layer);
  const inheritedGlobal = scopeType === "entity" && Boolean(scopeId) && !ownedByEntity;
  const globalOnly = (item.scopes || []).length === 1 && (item.scopes || [])[0] === "global";

  const submit = async () => {
    setBusy(true);
    const ok = await onSave({
      key: item.key, value: draft, scope_type: scopeType, scope_id: scopeId,
      reason, effective_from: effFrom,
    });
    setBusy(false);
    if (ok) { setDraft(undefined); setReason(""); setEffFrom(""); setShowSched(false); }
  };

  return (
    <article className={`cfg-card ${notUsed ? "not-used" : ""} ${dirty ? "dirty" : ""}`}
      data-testid={`cfg-card-${item.key}`}>
      <header className="cfg-card-head">
        <div className="cfg-card-title">
          <h3 data-testid={`cfg-card-label-${item.key}`}>{item.label}</h3>
          <code className="cfg-key">{item.key}</code>
        </div>
        <div className="cfg-card-badges">
          <span className={`badge-${LAYER_TONE[item.source_layer] || "muted"}`}
            title="Lapisan yang menentukan nilai saat ini"
            data-testid={`cfg-layer-badge-${item.key}`}>
            {item.source_label}
          </span>
          <span className={`badge-${WIRING_TONE[wStatus]}`} title="Status wiring ke mesin"
            data-testid={`cfg-wiring-badge-${item.key}`}>
            {WIRING_LABEL[wStatus]}
          </span>
          {item.risk !== "low" ? (
            <span className={`badge-${item.risk === "high" ? "red" : "orange"}`}>
              <ShieldAlert size={11} /> {RISK_LABEL[item.risk]}
            </span>
          ) : null}
        </div>
      </header>

      <div className="cfg-value-row">
        <span className="cfg-value-label">Nilai berlaku sekarang</span>
        <span className="cfg-value" data-testid={`cfg-value-${item.key}`}>
          {formatValue(item, item.value)}
        </span>
        {item.is_default ? <span className="badge-muted">bawaan sistem</span> : null}
        {ownedByEntity ? (
          <span className="badge-purple" data-testid={`cfg-owned-${item.key}`}>
            nilai {scopeLabel || "badan usaha ini"}
          </span>
        ) : null}
        {inheritedGlobal ? (
          <span className="badge-muted" data-testid={`cfg-inherited-${item.key}`}>
            diwarisi dari Global
          </span>
        ) : null}
      </div>
      {globalOnly ? (
        <p className="cfg-hint-sm" data-testid={`cfg-global-only-${item.key}`}>
          Pengaturan ini <b>berlaku untuk seluruh sistem</b> — tidak bisa dibedakan per
          badan usaha (menyangkut tampilan aplikasi, bukan aturan bisnis).
        </p>
      ) : null}

      <p className="cfg-help"><Info size={13} /> <span><b>Artinya:</b> {item.help}</span></p>
      <p className="cfg-impact"><Zap size={13} /> <span><b>Kalau diubah:</b> {item.impact}</span></p>

      {notUsed ? (
        <div className="cfg-notused-box" data-testid={`cfg-notused-${item.key}`}>
          <Ban size={14} />
          <div>
            <b>Pengaturan ini TIDAK dipakai sistem saat ini.</b>
            <p>{item.not_used_reason}</p>
          </div>
        </div>
      ) : null}

      <button className="cfg-more-toggle" onClick={() => setShowMore((v) => !v)}
        data-testid={`cfg-more-${item.key}`}>
        {showMore ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        {showMore ? "Sembunyikan detail" : "Contoh & detail teknis"}
      </button>
      {showMore ? (
        <div className="cfg-more">
          {item.example ? (
            <p className="cfg-example"><b>Contoh:</b> {item.example}</p>
          ) : null}
          <p className="cfg-hint-sm">
            Bisa diatur pada level: {(item.scopes || []).map((s) => SCOPE_LABEL[s] || s).join(" · ")}
          </p>
          {(item.consumers || []).length ? (
            <p className="cfg-hint-sm">
              Dipakai oleh: {item.consumers.map((c) => <code key={c}>{c}</code>)}
            </p>
          ) : null}
          {(item.related || []).length ? (
            <p className="cfg-hint-sm">Terkait: {item.related.join(" · ")}</p>
          ) : null}
        </div>
      ) : null}

      {(item.scheduled || []).length > 0 ? (
        <div className="cfg-sched-box" data-testid={`cfg-scheduled-${item.key}`}>
          <CalendarClock size={13} />
          <span>
            Terjadwal:{" "}
            {item.scheduled.map((s, i) => (
              <b key={i}>
                {formatValue(item, s.value)} mulai {String(s.effective_from).slice(0, 10)}
                {i < item.scheduled.length - 1 ? " · " : ""}
              </b>
            ))}
          </span>
        </div>
      ) : null}

      {editable ? (
        <div className="cfg-edit-zone">
          {!scopeSupported ? (
            <p className="cfg-scope-warn" data-testid={`cfg-scope-warn-${item.key}`}>
              Pengaturan ini belum bisa dibedakan pada level “{SCOPE_LABEL[scopeType] || scopeType}”
              karena mesin pembacanya belum mendukung. Pilih cakupan lain di atas.
            </p>
          ) : (
            <>
              <div className="cfg-edit-row">
                <SettingEditor
                  entry={item}
                  value={draft !== undefined ? draft : item.value}
                  onChange={setDraft}
                  disabled={busy}
                />
                <div className="cfg-edit-actions">
                  <button className="btn-primary btn-sm" disabled={!dirty || busy}
                    onClick={submit} data-testid={`cfg-save-${item.key}`}>
                    <Save size={13} /> {busy ? "Menyimpan…" : "Simpan"}
                  </button>
                  {ownedByEntity ? (
                    <button className="btn-secondary btn-sm" disabled={busy}
                      onClick={() => onClearEntity && onClearEntity(item)}
                      data-testid={`cfg-clear-entity-${item.key}`}
                      title={`Cabut nilai khusus ${scopeLabel || "badan usaha ini"} — kembali memakai nilai Global`}>
                      <RotateCcw size={13} /> Kembalikan ke global
                    </button>
                  ) : (
                    <button className="btn-secondary btn-sm" disabled={busy || item.is_default}
                      onClick={() => onReset(item)} data-testid={`cfg-reset-${item.key}`}
                      title="Kembalikan ke nilai bawaan sistem">
                      <RotateCcw size={13} /> Default
                    </button>
                  )}
                </div>
              </div>
              {dirty ? (
                <div className="cfg-dirty-box" data-testid={`cfg-dirty-${item.key}`}>
                  <p className="cfg-dirty-line">
                    Akan berubah: <b>{formatValue(item, item.value)}</b> →{" "}
                    <b className="cfg-new">{formatValue(item, draft)}</b>
                    {" "}pada cakupan <b>{scopeType === "entity" ? (scopeLabel || SCOPE_LABEL.entity) : SCOPE_LABEL.global}</b>
                  </p>
                  <p className="cfg-hint-sm" data-testid={`cfg-dirty-scope-note-${item.key}`}>
                    {scopeType === "entity"
                      ? `Hanya ${scopeLabel || "badan usaha ini"} yang terpengaruh — badan usaha lain tetap memakai nilai Global.`
                      : "Berlaku untuk SEMUA badan usaha yang belum punya nilai sendiri."}
                  </p>
                  <input
                    className="form-input cfg-input-wide"
                    placeholder={item.requires_reason
                      ? "Alasan perubahan (WAJIB untuk setting berisiko tinggi)"
                      : "Alasan perubahan (opsional, sangat dianjurkan)"}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    data-testid={`cfg-reason-${item.key}`}
                  />
                  <button className="cfg-link-btn" onClick={() => setShowSched((v) => !v)}
                    data-testid={`cfg-sched-toggle-${item.key}`}>
                    <CalendarClock size={12} /> {showSched ? "Berlaku sekarang" : "Jadwalkan berlaku sejak…"}
                  </button>
                  {showSched ? (
                    <label className="cfg-sched-field">
                      <span>Berlaku sejak</span>
                      <input type="datetime-local" className="form-input"
                        value={effFrom} onChange={(e) => setEffFrom(e.target.value)}
                        data-testid={`cfg-efffrom-${item.key}`} />
                      <em>Sebelum tanggal ini, nilai lama tetap dipakai mesin.</em>
                    </label>
                  ) : null}
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : (
        <p className="cfg-readonly" data-testid={`cfg-readonly-${item.key}`}>
          {notUsed ? "Tidak bisa diubah karena tidak dipakai sistem." : "Hanya admin yang boleh mengubah setting ini."}
        </p>
      )}

      <footer className="cfg-card-foot">
        <button className="cfg-link-btn" onClick={() => onWhy(item)}
          data-testid={`cfg-why-${item.key}`}>
          <Layers size={13} /> Kenapa nilainya begini?
        </button>
        {item.simulate ? (
          <button className="cfg-link-btn" onClick={() => onSimulate(item, dirty ? draft : undefined)}
            data-testid={`cfg-sim-${item.key}`}>
            <FlaskConical size={13} /> Coba dulu
          </button>
        ) : null}
        <button className="cfg-link-btn" onClick={() => onHistory(item)}
          data-testid={`cfg-hist-${item.key}`}>
          <History size={13} /> Riwayat
        </button>
      </footer>
    </article>
  );
}
