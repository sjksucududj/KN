/**
 * ScopeReadOnlyBanner (FASE E-3 · user story 7) — pita "sedang melihat gabungan".
 *
 * Kenapa ada: dulu admin bisa berada di mode "Semua Entitas" tanpa tanda apa pun,
 * menekan Simpan, lalu dokumennya masuk ke buku badan usaha HOME-nya tanpa
 * pemberitahuan. Pita ini membuat keadaan itu TERLIHAT dan sekaligus menyediakan
 * jalan keluar satu klik: pilih badan usaha langsung dari pita.
 */
import { Eye, Building2 } from "lucide-react";

import { entityShort, entityFull } from "../utils/entityLabel";

export default function ScopeReadOnlyBanner({ entities = [], onPick, flash = 0 }) {
  const list = (entities || []).filter((e) => e && e.status !== "archived");
  return (
    <div
      data-testid="scope-readonly-banner"
      key={flash}
      className={`scope-readonly-banner${flash ? " scope-readonly-flash" : ""}`}
    >
      <Eye size={14} className="shrink-0 text-[#8C4A00]" />
      <div className="min-w-0 flex-1">
        <p className="scope-readonly-title">
          Anda sedang melihat gabungan <strong>semua badan usaha</strong> — mode ini hanya untuk melihat.
        </p>
        <p className="scope-readonly-text">
          Untuk membuat pesanan, pelanggan, faktur, atau dokumen apa pun, pilih dulu satu
          badan usaha supaya dokumennya masuk ke buku yang benar.
        </p>
      </div>
      {list.length > 0 && (
        <div className="scope-readonly-actions" data-testid="scope-readonly-picks">
          <span className="scope-readonly-label">Kerja di:</span>
          {list.slice(0, 6).map((e) => (
            <button
              key={e.id}
              type="button"
              data-testid={`scope-pick-${e.id}`}
              className="scope-readonly-pick"
              title={`Pindah ke ${entityFull(e)}`}
              onClick={() => onPick?.(e.id)}
            >
              <Building2 size={11} /> {entityShort(e)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
