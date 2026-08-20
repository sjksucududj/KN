/**
 * EntityList (FASE E-3) — tabel badan usaha yang tetap terbaca saat jumlahnya puluhan.
 *
 * Kolom sengaja menjawab pertanyaan pemilik: “ini badan usaha apa, kode dokumennya
 * apa, PKP atau bukan, siapa yang kerja di sana, dan apakah sudah siap dipakai?”
 * Pencarian & filter dilakukan di sisi layar (daftar badan usaha selalu kecil
 * relatif terhadap transaksi) sehingga tidak ada jeda saat mengetik.
 */
import { useMemo, useState } from "react";
import { Search, Archive, RotateCcw, ChevronRight, ShieldCheck, Lock } from "lucide-react";

import { reactivateEntity, errText } from "./entityApi";
import ArchiveEntityDialog from "./ArchiveEntityDialog";

const STATUS_FILTERS = [
  { key: "active", label: "Aktif" },
  { key: "archived", label: "Terarsip" },
  { key: "all", label: "Semua" },
];

function ReadinessBar({ readiness, testId }) {
  const pct = readiness?.percent ?? 0;
  const tone = pct === 100 ? "#1B7F4B" : pct >= 60 ? "#B45309" : "#C0392B";
  return (
    <div className="min-w-[110px]" data-testid={testId}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#F2F2F7]">
        <div style={{ width: `${pct}%`, background: tone }} className="h-full" />
      </div>
      <span className="text-[10px] font-semibold tabular-nums" style={{ color: tone }}>
        {pct}% siap
        {readiness?.missing?.length ? ` · kurang: ${readiness.missing.join(", ")}` : ""}
      </span>
    </div>
  );
}

export default function EntityList({ entities = [], loading, canManage, onOpen,
  onChanged, onError }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("active");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [archiving, setArchiving] = useState(null);
  const [busy, setBusy] = useState("");
  const pageSize = 12;

  const types = useMemo(
    () => Array.from(new Set(entities.map((e) => e.type).filter(Boolean))).sort(),
    [entities]
  );

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    return entities.filter((e) => {
      if (status === "active" && e.status !== "active") return false;
      if (status === "archived" && e.status === "active") return false;
      if (type && e.type !== type) return false;
      if (!term) return true;
      return `${e.legal_name} ${e.short_name} ${e.doc_prefix} ${e.city}`
        .toLowerCase().includes(term);
    });
  }, [entities, q, status, type]);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, totalPages);
  const shown = rows.slice((current - 1) * pageSize, current * pageSize);

  const doReactivate = async (id, name) => {
    setBusy(id);
    try {
      await reactivateEntity(id);
      onChanged?.(`“${name}” aktif kembali dan bisa menerima transaksi lagi.`);
    } catch (e) {
      onError?.(errText(e, "Gagal mengaktifkan kembali badan usaha."));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="section-card" data-testid="entity-list-card">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <h2 data-testid="entity-list-title">Daftar Badan Usaha</h2>
          <span className="text-[10.5px] text-[#9A9BA3]" data-testid="entity-list-count">
            {rows.length} badan usaha
          </span>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1" data-testid="entity-status-filter">
            {STATUS_FILTERS.map((s) => (
              <button
                key={s.key}
                type="button"
                data-testid={`entity-status-${s.key}`}
                onClick={() => { setStatus(s.key); setPage(1); }}
                className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                  status === s.key
                    ? "bg-[#007AFF] text-white"
                    : "border border-[#E5E5EA] bg-white text-[#6B6B73] hover:border-[#007AFF]"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
          {types.length > 1 && (
            <div className="flex items-center gap-1" data-testid="entity-type-filter">
              <button
                type="button"
                data-testid="entity-type-all"
                onClick={() => { setType(""); setPage(1); }}
                className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                  !type ? "bg-[#6B219A] text-white"
                       : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}
              >
                Semua jenis
              </button>
              {types.map((t) => (
                <button
                  key={t}
                  type="button"
                  data-testid={`entity-type-${t}`}
                  onClick={() => { setType(t); setPage(1); }}
                  className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                    type === t ? "bg-[#6B219A] text-white"
                              : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}
                >
                  {t}
                </button>
              ))}
            </div>
          )}
          <div className="relative">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input
              data-testid="entity-search-input"
              className="field pl-7 py-1 text-[12px]"
              placeholder="Cari nama / kode / kota…"
              value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1); }}
            />
          </div>
        </div>
      </div>

      <div className="section-body">
        {loading ? (
          <div className="grid gap-2" data-testid="entity-list-loading">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-11 animate-pulse rounded bg-[#F5F5F7]" />
            ))}
          </div>
        ) : shown.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-[#8E8E93]"
               data-testid="entity-list-empty">
            Tidak ada badan usaha yang cocok dengan pencarian/filter ini.
          </div>
        ) : (
          <div className="overflow-auto rounded-md border border-[#EFF0F2]">
            <table className="w-full text-[12px]" data-testid="entity-list-table">
              <thead>
                <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
                  <th className="px-3 py-2">Nama legal</th>
                  <th className="px-3 py-2">Jenis</th>
                  <th className="px-3 py-2">Kode dokumen</th>
                  <th className="px-3 py-2">Pajak</th>
                  <th className="px-3 py-2">Mata uang</th>
                  <th className="px-3 py-2 text-right">Pengguna</th>
                  <th className="px-3 py-2 text-right">Gudang</th>
                  <th className="px-3 py-2">Kesiapan</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((e) => (
                  <tr
                    key={e.id}
                    data-testid={`entity-row-${e.id}`}
                    className="cursor-pointer border-b border-[#F5F5F7] last:border-0 hover:bg-[#FAFBFF]"
                    onClick={() => onOpen?.(e.id)}
                  >
                    <td className="px-3 py-2">
                      <p className="font-semibold text-[#1C1C1E]">{e.legal_name || e.name}</p>
                      <p className="text-[10px] text-[#9A9BA3]">
                        {e.short_name}{e.city ? ` · ${e.city}` : ""}
                      </p>
                    </td>
                    <td className="px-3 py-2 text-[#3C3C43]">{e.type || "—"}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1 rounded bg-[#F2F2F7] px-1.5 py-0.5 font-mono text-[11px] font-bold text-[#3C3C43]">
                        {e.doc_prefix || "—"}
                      </span>
                      <span className="ml-1 text-[10px] text-[#9A9BA3]">
                        {e.doc_prefix ? `${e.doc_prefix}/SO-00001` : ""}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      {e.is_pkp ? (
                        <span className="inline-flex items-center gap-1 rounded bg-[#E6F6EC] px-1.5 py-0.5 text-[10px] font-bold text-[#1B7F4B]"
                              data-testid={`entity-pkp-${e.id}`}>
                          <ShieldCheck size={10} /> PKP
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded bg-[#F2F2F7] px-1.5 py-0.5 text-[10px] font-bold text-[#6B6B73]"
                              data-testid={`entity-pkp-${e.id}`}>
                          non-PKP
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-[#3C3C43]" data-testid={`entity-currency-${e.id}`}>
                      {e.currency || "IDR"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{e.user_count ?? 0}</td>
                    <td className="px-3 py-2 text-right tabular-nums"
                        data-testid={`entity-warehouses-${e.id}`}>
                      {e.readiness?.warehouse_count ?? "—"}
                    </td>
                    <td className="px-3 py-2">
                      <ReadinessBar readiness={e.readiness} testId={`entity-readiness-${e.id}`} />
                    </td>
                    <td className="px-3 py-2">
                      {e.status === "active" ? (
                        <span className="status-pill" data-testid={`entity-status-pill-${e.id}`}
                              style={{ background: "#E6F6EC", color: "#1B7F4B" }}>Aktif</span>
                      ) : (
                        <span className="status-pill inline-flex items-center gap-1"
                              data-testid={`entity-status-pill-${e.id}`}
                              style={{ background: "#FDF3E7", color: "#8C4A00" }}>
                          <Lock size={9} /> Terarsip
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center justify-end gap-1.5">
                        {canManage && e.status === "active" && (
                          <button
                            type="button"
                            className="secondary-button !py-1 !px-2 !text-[10.5px]"
                            data-testid={`entity-archive-${e.id}`}
                            onClick={(ev) => { ev.stopPropagation(); setArchiving(e); }}
                          >
                            <Archive size={11} /> Arsipkan
                          </button>
                        )}
                        {canManage && e.status !== "active" && (
                          <button
                            type="button"
                            className="secondary-button !py-1 !px-2 !text-[10.5px]"
                            data-testid={`entity-reactivate-${e.id}`}
                            disabled={busy === e.id}
                            onClick={(ev) => {
                              ev.stopPropagation();
                              doReactivate(e.id, e.legal_name || e.short_name);
                            }}
                          >
                            <RotateCcw size={11} /> Aktifkan
                          </button>
                        )}
                        <ChevronRight size={14} className="text-[#C7C7CC]" />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && (
          <div className="mt-2 flex items-center justify-between" data-testid="entity-list-pager">
            <span className="text-[11px] text-[#6B6B73] tabular-nums">
              Halaman {current} dari {totalPages}
            </span>
            <div className="flex gap-1.5">
              <button type="button" className="secondary-button !py-1"
                      data-testid="entity-page-prev"
                      disabled={current <= 1} onClick={() => setPage(current - 1)}>
                Sebelumnya
              </button>
              <button type="button" className="secondary-button !py-1"
                      data-testid="entity-page-next"
                      disabled={current >= totalPages} onClick={() => setPage(current + 1)}>
                Berikutnya
              </button>
            </div>
          </div>
        )}
      </div>

      {archiving && (
        <ArchiveEntityDialog
          entity={archiving}
          onClose={() => setArchiving(null)}
          onDone={(msg) => { setArchiving(null); onChanged?.(msg); }}
        />
      )}
    </div>
  );
}
