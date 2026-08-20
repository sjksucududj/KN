/**
 * UomInputConvert (FASE B · D-06/D-07) — komponen “Input & Konversi” lintas modul
 * (PO, PR, penerimaan, makloon).
 *
 * Kenapa ada: sebelumnya tiap form menghitung sendiri “≈ x kg” dengan rumus yang
 * digandakan di FE. Itu rawan salah (mis. produk berbasis **yard** dihitung seolah
 * meter) dan melanggar SSOT. Komponen ini SELALU menanyakan hasil + JEJAK konversi
 * ke server (`POST /api/uom-conversions/convert`) sehingga angka di layar = angka
 * yang tersimpan di dokumen.
 *
 * Props:
 *   productId, baseUnit, gramasi, lebar   → konteks produk (boleh belum tersimpan)
 *   qty, onQtyChange(text)                → nilai input (string, koma-desimal)
 *   unit, onUnitChange(code)              → satuan dokumen
 *   unitOptions                           → opsi satuan (default: katalog server)
 *   actual, actualLabel                   → ukur/timbang aktual (opsional) → cek toleransi
 *   onResult(trail)                       → callback jejak konversi terakhir
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Info } from "lucide-react";
import DecimalInput from "./DecimalInput";
import KNSelect from "./KNSelect";
import useUomConversions, { SOURCE_LABEL } from "../hooks/useUomConversions";
import { parseDecimal } from "../utils/decimalInput";

export default function UomInputConvert({
  productId = "", baseUnit = "", gramasi = null, lebar = null,
  qty = "", onQtyChange, unit = "", onUnitChange,
  unitOptions = null, actual = null, actualLabel = "timbangan aktual",
  onResult, testId = "uom-input", disabled = false, compact = false, placeholder = "Qty",
}) {
  const { unitOptions: catalogUnits, convert, checkVariance, settings } = useUomConversions();
  const [trail, setTrail] = useState(null);
  const [warn, setWarn] = useState("");
  const [variance, setVariance] = useState(null);
  const timer = useRef(null);

  const options = unitOptions && unitOptions.length ? unitOptions : catalogUnits();

  const run = useCallback(async () => {
    const q = parseDecimal(qty);
    if (!unit || !Number.isFinite(q) || q <= 0) { setTrail(null); setWarn(""); return; }
    try {
      const body = { qty: String(qty), from_unit: unit, to_unit: baseUnit || "" };
      if (productId) body.product_id = productId;
      if (!productId && baseUnit) body.base_unit = baseUnit;
      if (gramasi !== null && gramasi !== "") body.gramasi = String(gramasi);
      if (lebar !== null && lebar !== "") body.lebar = String(lebar);
      const res = await convert(body);
      setTrail(res); setWarn("");
      if (onResult) onResult(res);
      if (actual !== null && actual !== "" && parseDecimal(actual) > 0) {
        setVariance(await checkVariance(res.base_qty, actual, actualLabel));
      } else {
        setVariance(null);
      }
    } catch (e) {
      setTrail(null);
      setVariance(null);
      setWarn(e.response?.data?.detail || "Konversi satuan gagal.");
      if (onResult) onResult(null);
    }
  }, [qty, unit, baseUnit, productId, gramasi, lebar, actual, actualLabel,
      convert, checkVariance, onResult]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(run, 350);      // debounce ketikan
    return () => timer.current && clearTimeout(timer.current);
  }, [run]);

  const danger = variance?.level === "block";

  return (
    <div data-testid={testId} className="grid gap-1">
      <div className={`grid gap-1.5 ${compact ? "grid-cols-[1fr_110px]" : "grid-cols-[1fr_130px]"}`}>
        <DecimalInput data-testid={`${testId}-qty`} className="field" min={0}
          placeholder={placeholder} value={qty} disabled={disabled}
          onChange={(v) => onQtyChange && onQtyChange(v)} />
        <KNSelect data-testid={`${testId}-unit`} className="field" value={unit || ""}
          placeholder="Satuan" disabled={disabled} options={options}
          onValueChange={(v) => onUnitChange && onUnitChange(v)} />
      </div>

      {warn && (
        <p data-testid={`${testId}-error`}
          className="flex items-start gap-1 text-[10.5px] font-semibold text-[#B4231F]">
          <AlertTriangle size={11} className="mt-0.5 shrink-0" /> {warn}
        </p>
      )}

      {trail && !warn && (
        <p data-testid={`${testId}-preview`}
          className="flex flex-wrap items-center gap-1 text-[10.5px] text-[#3C3C43]">
          <span className="tabular-nums font-semibold">{trail.doc_qty} {trail.doc_uom}</span>
          <ArrowRight size={10} className="text-[#8E8E93]" />
          <span data-testid={`${testId}-base`} className="tabular-nums font-bold text-[#0058CC]">
            {trail.base_qty} {trail.base_uom}
          </span>
          <span className="text-[#8E8E93]">
            (faktor {Number(trail.factor).toLocaleString("id-ID", { maximumFractionDigits: 6 })}
            {" · "}{SOURCE_LABEL[trail.source] || trail.source})
          </span>
        </p>
      )}

      {variance && variance.level !== "ok" && (
        <p data-testid={`${testId}-variance`}
          className={`flex items-start gap-1 text-[10.5px] font-semibold ${
            danger ? "text-[#B4231F]" : "text-[#8C4A00]"}`}>
          <AlertTriangle size={11} className="mt-0.5 shrink-0" />
          {variance.message}
        </p>
      )}
      {variance && variance.level === "ok" && variance.variance_pct !== null && (
        <p data-testid={`${testId}-variance-ok`}
          className="flex items-center gap-1 text-[10.5px] text-[#126E2C]">
          <CheckCircle2 size={11} /> Selisih {Math.abs(variance.variance_pct).toFixed(2)}% —
          masih dalam toleransi {Number(settings?.warn_pct ?? variance.warn_pct)}%.
        </p>
      )}
      {!trail && !warn && parseDecimal(qty) > 0 && (
        <p className="flex items-center gap-1 text-[10.5px] text-[#8E8E93]">
          <Info size={11} /> Menghitung konversi…
        </p>
      )}
    </div>
  );
}
