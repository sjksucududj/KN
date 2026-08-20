/**
 * UomConvertHint (FASE B · D-07) — baris pratinjau konversi satuan yang RINGKAS.
 *
 * Dipakai form yang sudah punya input qty & satuan sendiri (mis. form PO) supaya
 * tidak perlu mengganti tata letak, tetapi angka konversinya tetap berasal dari
 * server (SSOT) — bukan rumus yang digandakan di frontend.
 */
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Scale } from "lucide-react";
import useUomConversions, { SOURCE_LABEL } from "../hooks/useUomConversions";
import { parseDecimal } from "../utils/decimalInput";

export default function UomConvertHint({
  productId = "", baseUnit = "", qty = "", unit = "", suffix = "",
  testId = "uom-hint", onResult,
}) {
  const { convert } = useUomConversions();
  const [trail, setTrail] = useState(null);
  const [err, setErr] = useState("");
  const timer = useRef(null);

  useEffect(() => {
    const q = parseDecimal(qty);
    if (timer.current) clearTimeout(timer.current);
    if (!productId || !unit || !Number.isFinite(q) || q <= 0) {
      setTrail(null); setErr("");
      return () => {};
    }
    timer.current = setTimeout(() => {
      convert({ product_id: productId, qty: String(qty), from_unit: unit,
                to_unit: baseUnit || "" })
        .then((res) => { setTrail(res); setErr(""); if (onResult) onResult(res); })
        .catch((e) => {
          setTrail(null);
          setErr(e.response?.data?.detail || "Konversi satuan belum tersedia.");
          if (onResult) onResult(null);
        });
    }, 350);
    return () => timer.current && clearTimeout(timer.current);
  }, [productId, baseUnit, qty, unit, convert, onResult]);

  if (err) {
    return (
      <p data-testid={`${testId}-error`}
        className="mt-1.5 flex items-start gap-1 text-[10.5px] font-semibold text-[#B4231F]">
        <AlertTriangle size={11} className="mt-0.5 shrink-0" /> {err}
      </p>
    );
  }
  if (!trail || trail.source === "same_unit") return null;
  return (
    <p data-testid={testId}
      className="mt-1.5 flex flex-wrap items-center gap-1 text-[10.5px] text-[#0058CC]">
      <Scale size={11} />
      <span className="tabular-nums font-semibold">
        {trail.doc_qty} {trail.doc_uom} = {trail.base_qty} {trail.base_uom}
      </span>
      <span className="text-[#6B6B73]">
        (faktor {Number(trail.factor).toLocaleString("id-ID", { maximumFractionDigits: 6 })} ·
        {" "}{SOURCE_LABEL[trail.source] || trail.source}){suffix}
      </span>
    </p>
  );
}
