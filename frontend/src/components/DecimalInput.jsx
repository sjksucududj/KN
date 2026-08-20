/**
 * DecimalInput (Fase A · PS-15/R5) — input angka yang menerima koma-desimal.
 *
 * `<input type="number">` menolak "10,5" di banyak browser sehingga pengguna
 * kehilangan angka saat mengetik. Komponen ini memakai input teks + `inputMode=
 * "decimal"`, menyimpan teks mentah, dan mengirim STRING ke backend (backend
 * memakai `core_utils.parse_decimal` untuk mengonversi "10,5" → 10.5).
 *
 * Props: value, onChange(text), placeholder, className, disabled, data-testid,
 *        min (validasi visual), suffix (label satuan), invalid (paksa state error).
 */
import { isDecimalDraft, parseDecimal } from "../utils/decimalInput";

export default function DecimalInput({
  value, onChange, placeholder = "", className = "field", disabled = false,
  suffix = "", min = null, invalid = false, ...rest
}) {
  const text = value === null || value === undefined ? "" : String(value);
  const numeric = parseDecimal(text);
  const belowMin = min !== null && text !== "" && !Number.isNaN(numeric) && numeric < min;
  const bad = invalid || belowMin || (text !== "" && !isDecimalDraft(text));

  return (
    <div className="relative">
      <input
        {...rest}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        disabled={disabled}
        placeholder={placeholder}
        value={text}
        onChange={(e) => {
          const next = e.target.value;
          // Izinkan draft ("10," / "-") supaya pengguna bisa mengetik bebas;
          // tolak karakter non-angka agar tidak ada sampah masuk ke payload.
          if (isDecimalDraft(next)) onChange(next);
        }}
        className={`${className} tabular-nums ${bad ? "!border-[#D14343]" : ""} ${suffix ? "pr-12" : ""}`}
      />
      {suffix && (
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[10.5px] font-semibold text-[#8E8E93]">
          {suffix}
        </span>
      )}
    </div>
  );
}
