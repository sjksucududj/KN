/**
 * SettingEditor — kontrol input yang menyesuaikan TIPE setting.
 *
 * Satu komponen untuk semua tipe (bool/int/pct/money/decimal/duration/enum/text/list/table)
 * sehingga UI Pusat Pengaturan bisa di-generate dari registry backend — UI dan mesin
 * tidak mungkin lagi berbeda (akar masalah "tombol palsu").
 */
import KNSelect from "../../../components/KNSelect";
import SettingTableEditor from "./SettingTableEditor";

function NumberField({ entry, value, onChange, disabled, testId }) {
  const step = entry.step ?? (entry.type === "int" || entry.type === "duration" ? 1 : 0.1);
  return (
    <div className="cfg-num-wrap">
      <input
        type="number"
        className="form-input cfg-input"
        value={value ?? ""}
        min={entry.min ?? undefined}
        max={entry.max ?? undefined}
        step={step}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        data-testid={testId}
      />
      {entry.unit ? <span className="cfg-unit">{entry.unit}</span> : null}
      {(entry.min !== null || entry.max !== null) && (
        <span className="cfg-bounds">
          batas {entry.min ?? "−∞"} … {entry.max ?? "∞"}
        </span>
      )}
    </div>
  );
}

function ListField({ value, onChange, disabled, testId }) {
  const text = Array.isArray(value) ? value.join(", ") : String(value ?? "");
  return (
    <div className="cfg-num-wrap">
      <input
        className="form-input cfg-input cfg-input-wide"
        value={text}
        disabled={disabled}
        placeholder="pisahkan dengan koma, mis. 30, 60, 90"
        onChange={(e) =>
          onChange(
            e.target.value
              .split(",")
              .map((x) => x.trim())
              .filter((x) => x !== "")
              .map((x) => (Number.isNaN(Number(x)) ? x : Number(x)))
          )
        }
        data-testid={testId}
      />
      <span className="cfg-bounds">urutan berpengaruh</span>
    </div>
  );
}

function TableField({ entry, value, onChange, disabled, testId }) {
  return (
    <SettingTableEditor entry={entry} value={value} onChange={onChange}
      disabled={disabled} testId={testId} />
  );
}

export default function SettingEditor({ entry, value, onChange, disabled, testId }) {
  const tid = testId || `cfg-input-${entry.key}`;
  switch (entry.type) {
    case "bool":
      return (
        <div className="cfg-switch-row">
          <button
            type="button"
            role="switch"
            aria-checked={!!value}
            aria-label={entry.label}
            className={`cfg-switch ${value ? "on" : "off"}`}
            disabled={disabled}
            onClick={() => onChange(!value)}
            data-testid={tid}
          >
            <span className="cfg-switch-knob" />
          </button>
          <span className={`cfg-switch-label ${value ? "on" : ""}`}>
            {value ? "Ya / Aktif" : "Tidak / Mati"}
          </span>
        </div>
      );
    case "enum":
      return (
        <KNSelect
          value={value ?? ""}
          onValueChange={onChange}
          options={entry.options || []}
          className="field cfg-select"
          placeholder="Pilih…"
          disabled={disabled}
          data-testid={tid}
        />
      );
    case "int":
    case "duration":
    case "pct":
    case "money":
    case "decimal":
      return (
        <NumberField entry={entry} value={value} onChange={onChange}
          disabled={disabled} testId={tid} />
      );
    case "list":
      return <ListField value={value} onChange={onChange} disabled={disabled} testId={tid} />;
    case "table":
      return <TableField entry={entry} value={value} onChange={onChange} disabled={disabled} testId={tid} />;
    default:
      return (
        <input
          className="form-input cfg-input cfg-input-wide"
          value={value ?? ""}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          data-testid={tid}
        />
      );
  }
}
