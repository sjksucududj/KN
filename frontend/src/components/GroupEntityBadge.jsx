/**
 * GroupEntityBadge — FASE E-7 (E7.2/E7.7)
 *
 * Lencana **"Entitas grup"** untuk baris pemasok yang sebenarnya adalah badan usaha
 * lain di dalam grup (`partner_kind === "entity"`).
 *
 * Kenapa perlu terlihat di layar, bukan cuma dijaga di server: keputusan pemilik
 * memperlakukan badan usaha lain **seperti pemasok**, jadi "Kanda" memang MUNCUL di
 * daftar pemasok. Tanpa lencana, staf pembelian akan membuat PO ke sana, lalu ditolak
 * server — pengalaman yang menjengkelkan dan terlihat seperti kerusakan. Dengan lencana
 * + tombol pintas ke layar Antar Entitas, penolakan itu jadi arahan, bukan jalan buntu.
 */
import { Building2, ArrowRight } from "lucide-react";

/** Apakah satu baris pemasok/pelanggan sebenarnya badan usaha grup? */
export const isGroupEntityPartner = (p) =>
  !!p && (p.partner_kind === "entity" || !!p.group_entity_id || p.is_group_entity === true);

export const groupEntityShortName = (p) =>
  (p && (p.group_entity_short_name || p.group_entity_prefix)) || "badan usaha grup";

/**
 * Label opsi pemasok yang MENANDAI badan usaha grup sejak di daftar pilihan.
 * Dipakai semua pemilih pemasok (PO · PR · realisasi PR · RFQ · Blanket PO) supaya
 * tidak ada satu pun tempat yang membiarkan orang memilih dulu lalu ditolak server.
 */
export const supplierOptionLabel = (s, base) =>
  `${base ?? s?.name ?? ""}${isGroupEntityPartner(s) ? "  (Entitas grup)" : ""}`;

export default function GroupEntityBadge({ partner, className = "", size = "sm" }) {
  if (!isGroupEntityPartner(partner)) return null;
  const short = groupEntityShortName(partner);
  return (
    <span
      data-testid={`group-entity-badge-${partner.id || short}`}
      data-group-entity={short}
      title={`${partner.name || short} adalah badan usaha di dalam grup Anda. Pembelian dari ${short} dicatat lewat menu Antar Entitas supaya dokumennya kembar di kedua badan usaha dan margin grup ikut dieliminasi.`}
      className={`inline-flex items-center gap-1 rounded border border-violet-200 bg-violet-50 font-semibold text-violet-700 whitespace-nowrap ${
        size === "sm" ? "px-1.5 py-[1px] text-[9.5px]" : "px-2 py-0.5 text-[11px]"
      } ${className}`}
    >
      <Building2 size={size === "sm" ? 9 : 11} /> Entitas grup
    </span>
  );
}

/**
 * Pita penjelas + pintasan, dipakai saat pengguna sudah MEMILIH badan usaha grup di
 * formulir pembelian. Menjelaskan lebih dulu supaya tidak ada tombol yang "diam-diam
 * gagal", lalu memberi satu klik ke tempat yang benar.
 */
export function GroupEntityNotice({ partner, docLabel = "PO biasa", onOpenInterco, className = "" }) {
  if (!isGroupEntityPartner(partner)) return null;
  const short = groupEntityShortName(partner);
  return (
    <div
      data-testid="group-entity-notice"
      className={`rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 ${className}`}
    >
      <div className="flex items-start gap-2">
        <Building2 size={14} className="mt-0.5 flex-shrink-0 text-violet-600" />
        <div className="min-w-0 flex-1">
          <p className="text-[11.5px] font-bold text-violet-800">
            {partner.name} adalah badan usaha di dalam grup Anda
          </p>
          <p className="mt-0.5 text-[10.5px] leading-relaxed text-violet-900/80">
            Pembelian dari {short} <b>tidak dicatat sebagai {docLabel}</b>. Pakai menu{" "}
            <b>Antar Entitas</b> supaya satu transaksi melahirkan dokumen kembar di kedua
            badan usaha, harganya diambil dari kontrak internal, PPN &amp; faktur pajaknya
            berpasangan, dan margin antar-PT ikut dieliminasi di laporan konsolidasi.
          </p>
          <button
            type="button"
            data-testid="group-entity-open-interco"
            onClick={() => {
              if (onOpenInterco) return onOpenInterco();
              const url = new URL(window.location.href);
              url.searchParams.set("view", "interco-transactions");
              window.location.assign(url.toString());
            }}
            className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-violet-600 px-2 py-1 text-[10.5px] font-semibold text-white hover:bg-violet-700"
          >
            Buka Antar Entitas <ArrowRight size={11} />
          </button>
        </div>
      </div>
    </div>
  );
}
