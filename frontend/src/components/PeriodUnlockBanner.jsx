/**
 * PeriodUnlockBanner (FASE G-5) — Banner MERAH global saat ada periode tertutup
 * yang sedang DIBUKA (jendela unlock aktif). Muncul di semua layar bagi admin/manager
 * sebagai peringatan bahwa posting mundur sedang dimungkinkan sementara.
 * Sumber: GET /api/finance/period-unlocks/active (polling ringan tiap 45 dtk).
 */
import { useCallback, useEffect, useState } from "react";
import { ShieldAlert, Clock, ArrowRight } from "lucide-react";
import axios, { API } from "../services/apiClient";

function fmtTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("id-ID", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export default function PeriodUnlockBanner({ currentUser, onNavigate }) {
  const canSee = currentUser?.role === "admin" || currentUser?.role === "manager";
  const [active, setActive] = useState([]);

  const load = useCallback(async () => {
    if (!canSee) return;
    try {
      const res = await axios.get(`${API}/finance/period-unlocks/active`);
      setActive(Array.isArray(res.data) ? res.data : []);
    } catch {
      /* diam — banner bersifat informatif, jangan ganggu layar utama */
    }
  }, [canSee]);

  useEffect(() => {
    if (!canSee) return undefined;
    load();
    const t = setInterval(load, 45000);
    return () => clearInterval(t);
  }, [canSee, load]);

  if (!canSee || active.length === 0) return null;

  const first = active[0];
  const extra = active.length - 1;

  return (
    <div
      data-testid="period-unlock-banner"
      className="mb-3 rounded-md border border-[#F5C6C0] bg-[#FDEDE7] text-[#B02A1E] px-3 py-2 flex items-center gap-2 text-[12px]"
      role="alert"
    >
      <ShieldAlert size={16} className="shrink-0" />
      <div className="min-w-0 flex-1">
        <span className="font-bold">Periode dibuka sementara:</span>{" "}
        <span className="font-semibold">{first.period_label}</span>
        {" — jendela posting mundur aktif hingga "}
        <span className="inline-flex items-center gap-1 font-semibold"><Clock size={11} /> {fmtTime(first.window_until)}</span>
        {first.approved_by ? ` (disetujui ${first.approved_by})` : ""}
        {first.reason ? <span className="text-[#8a5049]"> · alasan: {first.reason}</span> : null}
        {extra > 0 ? <span className="font-semibold"> · +{extra} periode lain</span> : null}
      </div>
      {onNavigate && (
        <button
          data-testid="period-unlock-banner-link"
          onClick={() => onNavigate("period-unlock")}
          className="shrink-0 inline-flex items-center gap-1 font-bold underline decoration-dotted hover:text-[#8a1f14]"
        >
          Kelola <ArrowRight size={12} />
        </button>
      )}
    </div>
  );
}
