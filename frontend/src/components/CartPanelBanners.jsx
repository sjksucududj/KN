// Banner peringatan CartPanel (backorder / mixed-lot / status kredit) dipisah agar
// file utama di bawah batas guardrail. Pure — render dari props.
import { AlertTriangle, Layers, ShieldAlert, ShieldCheck } from "lucide-react";
import { formatCurrency, formatQty } from "../utils/formatters";

export default function CartPanelBanners({
  cartLength, hasBackorderLine, backorderQtyTotal, allowBackorder, setAllowBackorder,
  requiresLotConfirmation, mixedLotLines, credit, creditBlocked,
}) {
  if (!cartLength) return null;
  return (
    <>
      {/* Sub-fase 1.6 — opsi backorder bila stok entitas tak cukup */}
      {hasBackorderLine && (
        <div data-testid="backorder-option-card" className="mt-2 rounded-md border border-[#F5C9A6] bg-[#FFF7EF] p-2.5">
          <div className="flex items-start gap-2">
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[#A8221A]" />
            <div className="min-w-0">
              <p className="text-[11.5px] font-semibold text-[#8C4A00]">
                Stok entitas tidak cukup untuk {formatQty(backorderQtyTotal)} unit.
              </p>
              <label className="mt-1.5 flex cursor-pointer items-center gap-2">
                <input data-testid="allow-backorder-checkbox" type="checkbox" className="h-3.5 w-3.5 accent-[#0058CC]"
                  checked={allowBackorder} onChange={(e) => setAllowBackorder(e.target.checked)} />
                <span className="text-[11.5px] font-medium text-[#1C1C1E]">
                  Izinkan backorder (reservasi stok tersedia sekarang, sisanya menunggu barang masuk)
                </span>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Sub-fase 1.7 — peringatan pemenuhan lintas-lot (mixed lot) */}
      {requiresLotConfirmation && (
        <div data-testid="mixed-lot-warning-card" className="mt-2 rounded-md border border-[#D9C2EE] bg-[#F7F2FE] p-2.5">
          <div className="flex items-start gap-2">
            <Layers size={14} className="mt-0.5 shrink-0 text-[#6B219A]" />
            <div className="min-w-0">
              <p className="text-[11.5px] font-semibold text-[#5B1A86]">
                {mixedLotLines.length} item akan dipenuhi dari beberapa lot (mixed lot).
              </p>
              <p className="mt-0.5 text-[10.5px] text-[#6B219A]">
                Konfirmasi diperlukan saat membuat pesanan — warna/dye-lot bisa berbeda antar lot.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* KN_17 — banner status kredit customer (gate SO/POS) */}
      {credit && credit.level !== "ok" && (
        <div data-testid="credit-status-banner"
          className={`mt-2 rounded-md border p-2.5 ${creditBlocked
            ? "border-[#F1B0AB] bg-[#FDECEA]"
            : credit.has_approved_override
              ? "border-[#A7D8B0] bg-[#EAF7EE]"
              : "border-[#F5C9A6] bg-[#FFF7EF]"}`}>
          <div className="flex items-start gap-2">
            {creditBlocked ? <ShieldAlert size={14} className="mt-0.5 shrink-0 text-[#C0392B]" />
              : <ShieldCheck size={14} className="mt-0.5 shrink-0 text-[#9A5B00]" />}
            <div className="min-w-0 text-[11px]">
              <p className={`font-semibold ${creditBlocked ? "text-[#9B1C13]" : "text-[#8C4A00]"}`}>
                {creditBlocked ? "Kredit terblokir — order tidak bisa dibuat"
                  : credit.has_approved_override ? "Kredit terblokir, tapi ada Override yang disetujui"
                  : "Peringatan kredit (mendekati limit / ada tunggakan)"}
              </p>
              {(credit.reasons || []).map((r, i) => (
                <p key={i} className="text-[10.5px] text-[#6B6B73]">• {r}</p>
              ))}
              <p className="text-[10px] text-[#9A9BA3] mt-0.5 tabular-nums">
                AR {formatCurrency(credit.credit?.ar_outstanding)} / limit {credit.credit?.credit_limit > 0 ? formatCurrency(credit.credit.credit_limit) : "∞"} · proyeksi {formatCurrency(credit.projected_ar)}
              </p>
              {creditBlocked && (
                <p className="text-[10.5px] text-[#9B1C13] mt-1">Ajukan <b>Override Kredit</b> di menu Pelanggan / CRM dan minta persetujuan manager.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
