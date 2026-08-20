/**
 * RoleRealityPanel — **CEK PERAN** (utang migrasi (ii) FASE E-8).
 *
 * Menjawab pertanyaan pemilik: *"akun mana yang berperan Manajer padahal
 * pekerjaannya Admin Sales atau Finance?"* — dengan BUKTI, bukan tebakan.
 *
 * Kenapa layarnya begini:
 *  · **Kesimpulan dulu, bukti menyusul.** Baris ringkas menyebut kesimpulan +
 *    usulan; buktinya dibuka saat diminta. Daftar 40 kegiatan langsung terbuka
 *    membuat temuan yang penting tenggelam.
 *  · **Konfirmasi INLINE, bukan modal.** Mengubah wewenang orang adalah keputusan;
 *    tetapi memindahkannya ke jendela terpisah memutus bukti dari keputusannya.
 *    Di sini tombol "Yakin" muncul TEPAT di bawah buktinya.
 *  · **Label peran selalu dari registry** (`config/roles.js`) — id teknis seperti
 *    `sales_admin` tidak pernah sampai ke mata pengguna (INV-ROLE-01).
 *  · Nama badan usaha datang dari server sebagai NAMA SINGKAT saja (INV-UI-02).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { ShieldAlert, ShieldCheck, SplitSquareHorizontal, UserCog, ChevronDown,
  ChevronRight, Loader2, Info, ArrowDownRight, CircleSlash } from "lucide-react";

import ErrorNotice from "../../../components/ErrorNotice";
import { roleLabel, ROLE_OPTIONS } from "../../../config/roles";
import { roleReality, applyRoleReality, errText } from "./entityApi";

const VERDICTS = {
  kuasa_berlebih: {
    label: "Kuasa berlebih", icon: ShieldAlert,
    fg: "#B45309", bg: "#FEF3C7",
    hint: "Peran sekarang lebih tinggi daripada yang dibutuhkan pekerjaannya.",
  },
  pisah_tugas: {
    label: "Perlu pisah tugas", icon: SplitSquareHorizontal,
    fg: "#9A2222", bg: "#FDE8E8",
    hint: "Mengerjakan dua wilayah yang sengaja dipisah — sebaiknya dua akun.",
  },
  di_luar_peran: {
    label: "Di luar peran", icon: CircleSlash,
    fg: "#6B219A", bg: "#F3E8FF",
    hint: "Ada kegiatan yang peran sekarang tidak boleh lakukan.",
  },
  sesuai: {
    label: "Sesuai", icon: ShieldCheck,
    fg: "#1B7F4B", bg: "#E6F6EC",
    hint: "Peran sudah pas dengan kegiatannya.",
  },
  tanpa_jejak: {
    label: "Tanpa jejak", icon: Info,
    fg: "#6B6B73", bg: "#F2F2F7",
    hint: "Belum ada kegiatan tercatat — sengaja tidak dinilai.",
  },
};

const FILTERS = [
  { key: "temuan", label: "Perlu ditinjau" },
  { key: "", label: "Semua akun" },
  { key: "sesuai", label: "Sesuai" },
  { key: "tanpa_jejak", label: "Tanpa jejak" },
];

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("id-ID",
      { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return "—"; }
}

function VerdictPill({ verdict, testId }) {
  const v = VERDICTS[verdict] || VERDICTS.tanpa_jejak;
  const Icon = v.icon;
  return (
    <span className="status-pill inline-flex items-center gap-1" data-testid={testId}
          style={{ background: v.bg, color: v.fg }} title={v.hint}>
      <Icon size={11} /> {v.label}
    </span>
  );
}

function SummaryChip({ label, value, tone, testId }) {
  return (
    <div className="rounded-md border px-2.5 py-1.5" data-testid={testId}
         style={{ borderColor: tone.bg, background: tone.bg }}>
      <p className="text-[9.5px] font-bold uppercase tracking-wide" style={{ color: tone.fg }}>
        {label}
      </p>
      <p className="text-[15px] font-extrabold tabular-nums" style={{ color: tone.fg }}>
        {value}
      </p>
    </div>
  );
}

export default function RoleRealityPanel({ canManage = false, onChanged, onError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("temuan");
  const [roleFilter, setRoleFilter] = useState("");
  const [open, setOpen] = useState("");        // user_id yang buktinya dibuka
  const [confirming, setConfirming] = useState("");  // `${userId}:${role}`
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await roleReality(roleFilter ? { role: roleFilter } : {});
      setData(res);
      setError("");
    } catch (e) {
      setError(errText(e, "Gagal memuat hasil cek peran."));
    } finally {
      setLoading(false);
    }
  }, [roleFilter]);

  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => {
    const all = Array.isArray(data?.rows) ? data.rows : [];
    if (filter === "temuan") {
      return all.filter((r) => ["kuasa_berlebih", "pisah_tugas", "di_luar_peran"]
        .includes(r.verdict));
    }
    if (!filter) return all;
    return all.filter((r) => r.verdict === filter);
  }, [data, filter]);

  const summary = data?.summary || {};

  const apply = async (row, targetRole) => {
    setBusy(row.user_id);
    try {
      const res = await applyRoleReality(row.user_id, targetRole);
      setConfirming("");
      setOpen("");
      onChanged?.(res.message);
      await load();
    } catch (e) {
      setError(errText(e, "Gagal menerapkan peran usulan."));
      onError?.(errText(e, "Gagal menerapkan peran usulan."));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="section-card" data-testid="role-reality-card">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <h2 data-testid="role-reality-title">Cek Peran</h2>
          <span className="text-[10.5px] text-[#9A9BA3] tabular-nums"
                data-testid="role-reality-count">
            {summary.accounts || 0} akun diperiksa
          </span>
        </div>
      </div>

      <div className="section-body">
        {/* Penjelas metode — supaya angka di layar tidak terasa turun dari langit. */}
        <div className="mb-3 flex flex-wrap items-start gap-2 rounded-md border border-[#C9DBF7] bg-[#F2F7FF] px-3 py-2"
             data-testid="role-reality-method">
          <UserCog size={14} className="mt-0.5 text-[#0058CC]" />
          <div className="min-w-0">
            <p className="text-[11.5px] font-bold text-[#1C1C1E]">
              Peran diperiksa dari pekerjaan yang benar-benar tercatat, bukan dari jabatan.
            </p>
            <p className="text-[10.5px] text-[#6B6B73]">
              {data?.method
                || "Jejak diambil dari catatan audit dan pembuat dokumen, lalu diterjemahkan "
                   + "ke izin yang dibutuhkan."}{" "}
              Akun tanpa jejak <strong>tidak</strong> dinilai — sistem tidak menebak.
            </p>
          </div>
        </div>

        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6"
             data-testid="role-reality-summary">
          <SummaryChip label="Perlu ditinjau" value={summary.perlu_ditinjau || 0}
                       tone={{ fg: "#9A2222", bg: "#FDE8E8" }}
                       testId="role-reality-stat-review" />
          <SummaryChip label="Kuasa berlebih" value={summary.kuasa_berlebih || 0}
                       tone={VERDICTS.kuasa_berlebih}
                       testId="role-reality-stat-over" />
          <SummaryChip label="Pisah tugas" value={summary.pisah_tugas || 0}
                       tone={VERDICTS.pisah_tugas}
                       testId="role-reality-stat-split" />
          <SummaryChip label="Di luar peran" value={summary.di_luar_peran || 0}
                       tone={VERDICTS.di_luar_peran}
                       testId="role-reality-stat-beyond" />
          <SummaryChip label="Sesuai" value={summary.sesuai || 0}
                       tone={VERDICTS.sesuai} testId="role-reality-stat-ok" />
          <SummaryChip label="Tanpa jejak" value={summary.tanpa_jejak || 0}
                       tone={VERDICTS.tanpa_jejak} testId="role-reality-stat-none" />
        </div>

        <div className="mb-2 flex flex-wrap items-center gap-1.5"
             data-testid="role-reality-filters">
          {FILTERS.map((f) => (
            <button key={f.key || "all"} type="button"
                    data-testid={`role-reality-filter-${f.key || "all"}`}
                    onClick={() => setFilter(f.key)}
                    className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${
                      filter === f.key ? "bg-[#1C1C1E] text-white"
                        : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
              {f.label}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-[#E5E5EA]" />
          <button type="button" data-testid="role-reality-role-all"
                  onClick={() => setRoleFilter("")}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${
                    !roleFilter ? "bg-[#0058CC] text-white"
                      : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
            Semua peran
          </button>
          {ROLE_OPTIONS.map((r) => (
            <button key={r.value} type="button"
                    data-testid={`role-reality-role-${r.value}`}
                    onClick={() => setRoleFilter(r.value)}
                    className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${
                      roleFilter === r.value ? "bg-[#0058CC] text-white"
                        : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
              {roleLabel(r.value)}
            </button>
          ))}
        </div>

        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
                     testId="role-reality-error" />

        {loading ? (
          <div className="grid gap-2" data-testid="role-reality-loading">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded bg-[#F5F5F7]" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="py-10 text-center" data-testid="role-reality-empty">
            <ShieldCheck size={22} className="mx-auto mb-2 text-[#1B7F4B]" />
            <p className="text-[12.5px] font-semibold text-[#1C1C1E]">
              {filter === "temuan"
                ? "Tidak ada akun yang perlu ditinjau."
                : "Tidak ada akun pada saringan ini."}
            </p>
            <p className="mt-0.5 text-[11px] text-[#8E8E93]">
              {filter === "temuan"
                ? "Semua peran sudah sepadan dengan pekerjaan yang tercatat."
                : "Ubah saringan di atas untuk melihat akun lain."}
            </p>
            {filter === "temuan" && (
              <button type="button" className="secondary-button mt-3 !text-[11px]"
                      data-testid="role-reality-empty-showall"
                      onClick={() => setFilter("")}>
                Lihat semua akun
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-auto rounded-md border border-[#EFF0F2]">
            <table className="w-full text-[12px]" data-testid="role-reality-table">
              <thead>
                <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
                  <th className="px-3 py-2">Akun</th>
                  <th className="px-3 py-2">Peran sekarang</th>
                  <th className="px-3 py-2">Yang ia kerjakan</th>
                  <th className="px-3 py-2">Kesimpulan</th>
                  <th className="px-3 py-2">Usulan</th>
                  <th className="px-3 py-2 text-right">Bukti</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const expanded = open === r.user_id;
                  const confirmKey = `${r.user_id}:${r.suggested_role}`;
                  return (
                    <>
                      <tr key={r.user_id} data-testid={`role-reality-row-${r.user_id}`}
                          className="border-b border-[#F5F5F7] hover:bg-[#FAFBFF]">
                        <td className="px-3 py-2">
                          <p className="font-semibold text-[#1C1C1E]">{r.name}</p>
                          <p className="text-[10px] text-[#9A9BA3]">{r.email}</p>
                          <p className="text-[9.5px] text-[#9A9BA3]"
                             data-testid={`role-reality-entity-${r.user_id}`}>
                            {r.home_entity_name}
                            {(r.entity_names || []).length > 1
                              && ` · ditugaskan: ${r.entity_names.join(", ")}`}
                          </p>
                        </td>
                        <td className="px-3 py-2 font-semibold text-[#3C3C43]"
                            data-testid={`role-reality-current-${r.user_id}`}>
                          {roleLabel(r.role)}
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex flex-wrap gap-1"
                               data-testid={`role-reality-domains-${r.user_id}`}>
                            {(r.domains || []).length === 0 ? (
                              <span className="text-[10.5px] text-[#9A9BA3]">
                                belum ada kegiatan
                              </span>
                            ) : r.domains.map((d) => (
                              <span key={d.key}
                                    className="rounded bg-[#F2F2F7] px-1.5 py-0.5 text-[9.5px] font-semibold text-[#3C3C43]">
                                {d.label}
                              </span>
                            ))}
                          </div>
                          <p className="mt-0.5 text-[9.5px] text-[#9A9BA3] tabular-nums">
                            {r.activity_total} kegiatan tercatat
                          </p>
                        </td>
                        <td className="px-3 py-2">
                          <VerdictPill verdict={r.verdict}
                                       testId={`role-reality-verdict-${r.user_id}`} />
                        </td>
                        <td className="px-3 py-2" data-testid={`role-reality-suggest-${r.user_id}`}>
                          {r.suggested_role ? (
                            <span className="inline-flex items-center gap-1 font-semibold text-[#0058CC]">
                              <ArrowDownRight size={12} /> {roleLabel(r.suggested_role)}
                            </span>
                          ) : r.verdict === "pisah_tugas" ? (
                            <span className="text-[10.5px] font-semibold text-[#9A2222]">
                              dua akun
                            </span>
                          ) : (
                            <span className="text-[10.5px] text-[#9A9BA3]">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button type="button"
                                  className="secondary-button !py-1 !px-2 !text-[10.5px]"
                                  data-testid={`role-reality-toggle-${r.user_id}`}
                                  onClick={() => setOpen(expanded ? "" : r.user_id)}>
                            {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                            {expanded ? "Tutup" : "Lihat bukti"}
                          </button>
                        </td>
                      </tr>

                      {expanded && (
                        <tr key={`${r.user_id}-ev`} className="border-b border-[#F5F5F7] bg-[#FCFCFD]">
                          <td colSpan={6} className="px-3 py-3">
                            <p className="mb-2 text-[11.5px] font-semibold text-[#1C1C1E]"
                               data-testid={`role-reality-headline-${r.user_id}`}>
                              {r.headline}
                            </p>

                            {(r.evidence || []).length === 0 ? (
                              <p className="text-[11px] text-[#8E8E93]"
                                 data-testid={`role-reality-evidence-empty-${r.user_id}`}>
                                Tidak ada jejak kegiatan untuk akun ini, jadi tidak ada
                                usulan perubahan peran.
                              </p>
                            ) : (
                              <div className="overflow-hidden rounded border border-[#EFF0F2]">
                                <table className="w-full text-[11px]"
                                       data-testid={`role-reality-evidence-${r.user_id}`}>
                                  <thead>
                                    <tr className="bg-[#F7F8FA] text-left text-[9.5px] font-bold uppercase text-[#8E8E93]">
                                      <th className="px-2 py-1.5">Kegiatan</th>
                                      <th className="px-2 py-1.5">Wilayah kerja</th>
                                      <th className="px-2 py-1.5">Izin yang dipakai</th>
                                      <th className="px-2 py-1.5 text-right">Kali</th>
                                      <th className="px-2 py-1.5">Terakhir</th>
                                      <th className="px-2 py-1.5">Contoh dokumen</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {r.evidence.map((e) => (
                                      <tr key={e.key}
                                          className="border-t border-[#F5F5F7]"
                                          data-testid={`role-reality-ev-${r.user_id}-${e.key}`}>
                                        <td className="px-2 py-1.5 font-semibold text-[#1C1C1E]">
                                          {e.label}
                                          {e.beyond_current_role && (
                                            <span className="ml-1 rounded bg-[#F3E8FF] px-1 text-[9px] font-bold text-[#6B219A]">
                                              di luar peran sekarang
                                            </span>
                                          )}
                                        </td>
                                        <td className="px-2 py-1.5 text-[#6B6B73]">
                                          {e.domain_label}
                                        </td>
                                        <td className="px-2 py-1.5 text-[#8E8E93]">
                                          {e.permission}
                                        </td>
                                        <td className="px-2 py-1.5 text-right tabular-nums text-[#3C3C43]">
                                          {e.count}
                                        </td>
                                        <td className="px-2 py-1.5 tabular-nums text-[#6B6B73]">
                                          {fmtDate(e.last_at)}
                                        </td>
                                        <td className="px-2 py-1.5 text-[#6B6B73]">
                                          {(e.samples || []).join(" · ") || "—"}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}

                            {(r.split || []).length > 0 && (
                              <div className="mt-2 rounded border border-[#F5D6D6] bg-[#FFF8F8] px-2.5 py-2"
                                   data-testid={`role-reality-split-${r.user_id}`}>
                                <p className="text-[11px] font-bold text-[#9A2222]">
                                  Usulan pemisahan tugas
                                </p>
                                {r.split.map((s) => (
                                  <p key={s.domain} className="text-[10.5px] text-[#6B6B73]">
                                    <strong>{s.domain_label}</strong> →{" "}
                                    {s.suggested_role
                                      ? roleLabel(s.suggested_role)
                                      : "perlu peran khusus"}{" "}
                                    <span className="text-[#9A9BA3]">
                                      ({(s.activities || []).join(", ")})
                                    </span>
                                  </p>
                                ))}
                              </div>
                            )}

                            {canManage && r.suggested_role && (
                              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                                {confirming === confirmKey ? (
                                  <>
                                    <span className="text-[11px] font-semibold text-[#9A2222]"
                                          data-testid={`role-reality-confirm-text-${r.user_id}`}>
                                      Ubah peran {r.name} menjadi{" "}
                                      {roleLabel(r.suggested_role)}? Semua sesinya
                                      dicabut dan ia harus masuk lagi.
                                    </span>
                                    <button type="button" className="primary-button !py-1 !text-[11px]"
                                            disabled={busy === r.user_id}
                                            data-testid={`role-reality-confirm-${r.user_id}`}
                                            onClick={() => apply(r, r.suggested_role)}>
                                      {busy === r.user_id
                                        ? <Loader2 size={12} className="animate-spin" />
                                        : null}
                                      Ya, ubah peran
                                    </button>
                                    <button type="button" className="secondary-button !py-1 !text-[11px]"
                                            data-testid={`role-reality-cancel-${r.user_id}`}
                                            onClick={() => setConfirming("")}>
                                      Batal
                                    </button>
                                  </>
                                ) : (
                                  <button type="button" className="primary-button !py-1 !text-[11px]"
                                          data-testid={`role-reality-apply-${r.user_id}`}
                                          onClick={() => setConfirming(confirmKey)}>
                                    Terapkan usulan: {roleLabel(r.suggested_role)}
                                  </button>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {(data?.unmapped_actions || []).length > 0 && (
          <p className="mt-2 text-[10px] text-[#9A9BA3]"
             data-testid="role-reality-unmapped">
            Catatan kejujuran cakupan: {data.unmapped_actions.length} jenis kegiatan
            belum dipetakan ke izin ({data.unmapped_actions.map((u) => u.action).join(", ")}),
            jadi tidak ikut menilai peran. {data.activities_mapped} jenis kegiatan sudah dipetakan.
          </p>
        )}
      </div>
    </div>
  );
}
