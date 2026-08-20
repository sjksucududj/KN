/**
 * SettingTableEditor — FASE G-0 · editor untuk setting bertipe `table`.
 *
 * KENAPA ADA:
 *   Editor konfigurasi lama (mis. `TaxConfigPanel`) DIHAPUS supaya hanya ada satu
 *   sumber kebenaran. Tetapi panel lama punya satu keunggulan nyata: butir PPh bisa
 *   diubah lewat baris-baris rapi, bukan JSON mentah. Kalau Pusat Pengaturan hanya
 *   menyediakan textarea JSON, penggabungan ini justru menurunkan kualitas.
 *
 *   Maka bentuk tabel kini dideskripsikan di registry backend
 *   (`row_shape` + `columns`), dan komponen ini merendernya:
 *     row_shape "list" → daftar objek  ⇒ baris bisa ditambah/dihapus, kolom bertipe
 *     row_shape "map"  → objek datar   ⇒ pasangan kunci–nilai
 *     row_shape "json" → struktur bersarang ⇒ JSON (tetap ada, untuk kasus kompleks)
 *
 *   Hasilnya: satu pintu DAN lebih ramah daripada form yang dihapus.
 */
import { useState } from "react";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import KNSelect from "../../../components/KNSelect";

const num = (v) => (v === "" || v === null || v === undefined ? "" : Number(v));

/** Nilai awal sebuah baris baru, diturunkan dari `default` tiap kolom. */
function blankRow(columns) {
  const row = {};
  columns.forEach((c) => {
    row[c.name] = c.default !== undefined ? c.default : c.type === "bool" ? false : "";
  });
  return row;
}

function CellInput({ col, value, disabled, onChange, testId }) {
  if (col.type === "bool") {
    return (
      <input
        type="checkbox"
        checked={!!value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        data-testid={testId}
        aria-label={col.label}
      />
    );
  }
  if (col.type === "enum") {
    return (
      <KNSelect
        value={value ?? ""}
        onValueChange={onChange}
        options={col.options || []}
        className="field cfg-tbl-select"
        disabled={disabled}
        placeholder="Pilih…"
        data-testid={testId}
      />
    );
  }
  if (col.type === "pct" || col.type === "money" || col.type === "int" || col.type === "decimal") {
    return (
      <input
        type="number"
        step={col.type === "int" ? 1 : 0.01}
        className="form-input cfg-tbl-input"
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value === "" ? "" : num(e.target.value))}
        data-testid={testId}
        aria-label={col.label}
      />
    );
  }
  return (
    <input
      className="form-input cfg-tbl-input"
      value={value ?? ""}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      data-testid={testId}
      aria-label={col.label}
    />
  );
}

/** Baris objek (array of objects). */
function ListTable({ entry, rows, columns, disabled, onChange, tid }) {
  const setCell = (i, name, v) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, [name]: v } : r)));
  const addRow = () => onChange([...rows, blankRow(columns)]);
  const removeRow = (i) => onChange(rows.filter((_, idx) => idx !== i));

  return (
    <div className="cfg-tbl" data-testid={tid}>
      <div className="cfg-tbl-head" style={{ gridTemplateColumns: gridCols(columns, !disabled) }}>
        {columns.map((c) => (
          <span key={c.name}>{c.label}{c.unit ? ` (${c.unit})` : ""}</span>
        ))}
        {!disabled ? <span aria-hidden="true" /> : null}
      </div>

      {rows.length === 0 ? (
        <p className="cfg-empty-sm" data-testid={`${tid}-empty`}>
          Belum ada baris. Tekan “Tambah baris” untuk mulai.
        </p>
      ) : null}

      {rows.map((r, i) => (
        <div
          key={i}
          className="cfg-tbl-row"
          style={{ gridTemplateColumns: gridCols(columns, !disabled) }}
          data-testid={`${tid}-row-${i}`}
        >
          {columns.map((c) => {
            const off = c.disabled_when && r[c.disabled_when.field] === c.disabled_when.equals;
            return (
              <CellInput
                key={c.name}
                col={c}
                value={r[c.name]}
                disabled={disabled || !!off}
                onChange={(v) => setCell(i, c.name, v)}
                testId={`${tid}-${i}-${c.name}`}
              />
            );
          })}
          {!disabled ? (
            <button
              type="button"
              className="icon-button cfg-tbl-del"
              onClick={() => removeRow(i)}
              aria-label={`Hapus baris ${i + 1}`}
              data-testid={`${tid}-del-${i}`}
            >
              <Trash2 size={13} />
            </button>
          ) : null}
        </div>
      ))}

      {!disabled ? (
        <button type="button" className="cfg-link-btn cfg-tbl-add" onClick={addRow}
          data-testid={`${tid}-add`}>
          <Plus size={13} /> Tambah baris
        </button>
      ) : null}

      {columns.filter((c) => c.hint).map((c) => (
        <p className="cfg-hint-sm" key={c.name}>{c.hint}</p>
      ))}
      {entry.status === "not_used" ? null : null}
    </div>
  );
}

/** Objek datar: pasangan kunci → nilai. */
function MapTable({ value, columns, disabled, onChange, tid }) {
  const keyCol = columns.find((c) => c.name === "__key") || { label: "Kunci", type: "text" };
  const valCol = columns.find((c) => c.name === "__value") || { label: "Nilai", type: "text" };
  const pairs = Object.entries(value || {});

  const rename = (oldK, newK) => {
    const next = {};
    pairs.forEach(([k, v]) => { next[k === oldK ? newK : k] = v; });
    onChange(next);
  };
  const setVal = (k, v) => onChange({ ...(value || {}), [k]: v });
  const removeKey = (k) => {
    const next = { ...(value || {}) };
    delete next[k];
    onChange(next);
  };
  const addPair = () => {
    let name = "BARU";
    let n = 1;
    while (Object.prototype.hasOwnProperty.call(value || {}, name)) { name = `BARU_${n++}`; }
    onChange({ ...(value || {}), [name]: valCol.type === "money" ? 0 : "" });
  };

  return (
    <div className="cfg-tbl" data-testid={tid}>
      <div className="cfg-tbl-head" style={{ gridTemplateColumns: disabled ? "1fr 1fr" : "1fr 1fr 34px" }}>
        <span>{keyCol.label}</span>
        <span>{valCol.label}</span>
        {!disabled ? <span aria-hidden="true" /> : null}
      </div>

      {pairs.length === 0 ? (
        <p className="cfg-empty-sm" data-testid={`${tid}-empty`}>Belum ada entri.</p>
      ) : null}

      {pairs.map(([k, v], i) => (
        <div key={k} className="cfg-tbl-row"
          style={{ gridTemplateColumns: disabled ? "1fr 1fr" : "1fr 1fr 34px" }}
          data-testid={`${tid}-row-${i}`}>
          <input className="form-input cfg-tbl-input" value={k} disabled={disabled}
            onChange={(e) => rename(k, e.target.value)} aria-label={keyCol.label}
            data-testid={`${tid}-${i}-key`} />
          <CellInput col={valCol} value={v} disabled={disabled}
            onChange={(nv) => setVal(k, nv)} testId={`${tid}-${i}-value`} />
          {!disabled ? (
            <button type="button" className="icon-button cfg-tbl-del" onClick={() => removeKey(k)}
              aria-label={`Hapus ${k}`} data-testid={`${tid}-del-${i}`}>
              <Trash2 size={13} />
            </button>
          ) : null}
        </div>
      ))}

      {!disabled ? (
        <button type="button" className="cfg-link-btn cfg-tbl-add" onClick={addPair}
          data-testid={`${tid}-add`}>
          <Plus size={13} /> Tambah entri
        </button>
      ) : null}
    </div>
  );
}

/** Struktur bersarang — tetap JSON, tapi dengan validasi & pesan yang jelas. */
function JsonTable({ value, disabled, onChange, tid }) {
  const [raw, setRaw] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [err, setErr] = useState("");
  return (
    <div className="cfg-table-field">
      <textarea
        className="textarea cfg-json"
        rows={8}
        value={raw}
        disabled={disabled}
        onChange={(e) => {
          setRaw(e.target.value);
          try {
            onChange(JSON.parse(e.target.value));
            setErr("");
          } catch (_) {
            setErr("Format belum benar — periksa tanda kurung, kutip, dan koma.");
          }
        }}
        data-testid={tid}
      />
      {err ? (
        <p className="cfg-inline-err"><AlertTriangle size={12} /> {err}</p>
      ) : (
        <p className="cfg-hint-sm">
          Struktur bertingkat — ubah dengan hati-hati. Perubahan hanya tersimpan bila format benar.
        </p>
      )}
    </div>
  );
}

function gridCols(columns, withDelete) {
  const cols = columns.map((c) => c.width || "1fr").join(" ");
  return withDelete ? `${cols} 34px` : cols;
}

export default function SettingTableEditor({ entry, value, onChange, disabled, testId }) {
  const tid = testId || `cfg-input-${entry.key}`;
  const shape = entry.row_shape || "json";
  const columns = entry.columns || [];

  if (shape === "list" && columns.length) {
    const rows = Array.isArray(value) ? value : [];
    return (
      <ListTable entry={entry} rows={rows} columns={columns} disabled={disabled}
        onChange={onChange} tid={tid} />
    );
  }
  if (shape === "map") {
    const obj = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return (
      <MapTable value={obj} columns={columns} disabled={disabled} onChange={onChange} tid={tid} />
    );
  }
  return <JsonTable value={value} disabled={disabled} onChange={onChange} tid={tid} />;
}
