/**
 * PeriodUnlockCard (FASE G-5 · Dashboard) — kartu RINGKAS periode yang sedang DIBUKA
 * (jendela unlock aktif) + sisa waktunya, dengan tautan cepat ke layar kelola.
 * Sumber: GET /api/finance/period-unlocks/active. Tampil di Beranda Admin.
 */
import { useCallback, useEffect, useState } from "react";
import { ShieldCheck, Unlock, Clock, ArrowRight, Lock } from "lucide-react";
import axios, { API } from "../services/apiClient";

function fmtLeft(secs) {
  if (!secs || secs <= 0) return "berakhir";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (h >= 1) return `${h}j ${m}m lagi`;
  return `${m}m ${secs % 60}d lagi`;
}
function fmtWhen(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

export default function PeriodUnlockCard({ onNavigate }) {
  const [active, setActive] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/finance/period-unlocks/active`);
      setActive(Array.isArray(res.data) ? res.data : []);
    } catch {
      setActive([]);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 45000); return () => clearInterval(t); }, [load]);
  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), 1000); return () => clearInterval(t); }, []);

  if (!loaded) {
    // FASE P5 — dulu `return null`: kartu ini MELOMPAT MASUK begitu data tiba sehingga
    // isi Beranda bergeser di bawah kursor pengguna (tata letak "melompat"). Kerangka
    // seukuran kartunya membuat ruangnya sudah dipesan sejak awal.
    return (
      <div data-testid="dashboard-unlock-card-loading"
        className="mt-4 rounded-xl border border-[#EFF0F2] bg-white p-4">
        <div className="h-4 w-48 rounded bg-[#F0F0F3] animate-pulse" />
        <div className="mt-2 h-3 w-72 rounded bg-[#F5F5F7] animate-pulse" />
      </div>
    );
  }
  const hasActive = active.length > 0;

  return (
    <div
      data-testid="dashboard-unlock-card"
      className={`mt-4 rounded-xl border p-4 ${hasActive ? "border-[#F5C6C0] bg-[#FDF6F5]" : "border-[#EFF0F2] bg-white"}`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {hasActive ? <Unlock size={15} className="text-[#B02A1E]" /> : <ShieldCheck size={15} className="text-[#1B7F4B]" />}
          <h3 className="text-[14px] font-bold text-[#1C1C1E]">Buka Periode (Unlock)</h3>
          {hasActive && (
            <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-[#FDEDE7] text-[#B02A1E]">
              {active.length} AKTIF
            </span>
          )}
        </div>
        {onNavigate && (
          <button
            data-testid="dashboard-unlock-card-link"
            onClick={() => onNavigate("period-unlock")}
            className="text-[11px] font-semibold text-[#6B219A] inline-flex items-center gap-1 hover:underline"
          >
            Kelola <ArrowRight size={12} />
          </button>
        )}
      </div>

      {!hasActive ? (
        <div className="flex items-center gap-2 text-[12px] text-[#8E8E93]" data-testid="dashboard-unlock-none">
          <Lock size={13} className="text-[#1B7F4B]" />
          Semua periode terkunci normal — tidak ada jendela posting mundur yang terbuka.
        </div>
      ) : (
        <div className="grid gap-1.5" data-testid="dashboard-unlock-list">
          {active.map((u) => (
            <div key={u.id} data-testid={`dashboard-unlock-item-${u.id}`}
              className="flex items-center gap-2 py-1.5 border-b border-[#F3E4E1] last:border-0">
              <span className="text-[12px] font-semibold text-[#1C1C1E] min-w-[120px]">{u.period_label}</span>
              <span className="text-[11px] text-[#B02A1E] font-semibold inline-flex items-center gap-1">
                <Clock size={11} /> {fmtLeft(u.window_seconds_left)}
              </span>
              <span className="text-[11px] text-[#8E8E93] ml-auto truncate">
                s.d. {fmtWhen(u.window_until)}{u.approved_by ? ` · oleh ${u.approved_by}` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
