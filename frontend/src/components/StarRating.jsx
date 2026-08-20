import { useState } from "react";
import { Star } from "lucide-react";

/**
 * StarRating — komponen rating bintang 1–5 dipakai lintas layar desain.
 *
 * Dua mode:
 *  - Tampilan (editable=false): menampilkan RATA-RATA (`value`) sebagai bintang terisi
 *    + label "x.x (n)". Untuk kartu/daftar.
 *  - Interaktif (editable=true): penilai (admin/manager) mengeklik bintang untuk
 *    memberi/mengubah nilainya sendiri (`my`). Menampilkan tombol "hapus nilai" bila
 *    penilai sudah pernah memberi nilai.
 *
 * Kontrak data (dari backend design-gallery): value=rating_avg, count=rating_count,
 * my=my_rating. Perubahan dipanggil balik lewat onRate(stars) / onClear().
 */
export default function StarRating({
  value = 0,
  count = 0,
  my = null,
  editable = false,
  size = 14,
  busy = false,
  onRate,
  onClear,
  testId = "rating",
  showCount = true,
}) {
  const [hover, setHover] = useState(0);
  const avg = Number(value) || 0;
  // Mode interaktif menyoroti nilai penilai (hover > nilai sendiri > 0);
  // mode tampilan menyoroti pembulatan rata-rata.
  const active = editable ? hover || Number(my) || 0 : Math.round(avg);

  return (
    <div className="flex items-center gap-1.5" data-testid={testId}>
      <div className="flex items-center" role={editable ? "radiogroup" : undefined}
        aria-label={editable ? "Beri rating desain" : `Rata-rata rating ${avg.toFixed(1)}`}>
        {[1, 2, 3, 4, 5].map((n) => {
          const filled = n <= active;
          const star = (
            <Star
              size={size}
              className={filled ? "fill-[#F5A623] text-[#F5A623]" : "text-[#C7C9CF]"}
              strokeWidth={filled ? 1.5 : 1.75}
            />
          );
          if (!editable) {
            return <span key={n} className="leading-none">{star}</span>;
          }
          return (
            <button
              key={n}
              type="button"
              disabled={busy}
              data-testid={`${testId}-star-${n}`}
              title={`${n} bintang`}
              className={`leading-none px-0.5 transition-transform ${busy ? "opacity-50" : "hover:scale-110"}`}
              onMouseEnter={() => setHover(n)}
              onMouseLeave={() => setHover(0)}
              onClick={() => onRate && onRate(n)}
            >
              {star}
            </button>
          );
        })}
      </div>
      {showCount && (
        <span className="text-[10.5px] font-semibold tabular-nums text-[#6B6B73]"
          data-testid={`${testId}-avg`}>
          {count > 0 ? `${avg.toFixed(1)} (${count})` : "Belum dinilai"}
        </span>
      )}
      {editable && Number(my) > 0 && (
        <button
          type="button"
          disabled={busy}
          data-testid={`${testId}-clear`}
          className="text-[10px] font-medium text-[#9A9BA3] underline hover:text-[#C0341D]"
          onClick={() => onClear && onClear()}
          title="Hapus nilai saya"
        >
          hapus
        </button>
      )}
    </div>
  );
}
