/**
 * DivisionsView (PS-17) — layar **Desainer › Divisi & Persetujuan**.
 *
 * Menjawab keputusan pemilik D-13 dengan cakupan R&D-only (3a):
 *   1. Divisi apa saja yang ada & berapa anggotanya. (kartu divisi)
 *   2. Siapa menyetujui tiap tahap R&D. (matriks persetujuan — sumber rujukan)
 *   3. Menempatkan tiap orang R&D ke SATU divisi. (tabel anggota + dropdown)
 *
 * Penting: layar ini TIDAK mengubah hak akses/menu global — hanya menata organisasi
 * R&D dan mendokumentasikan approver. admin & manager tetap super-role.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Layers, RefreshCw, ShieldCheck, Users2 } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { errMsg } from "../rnd/rndMeta";
import { approvalMatrix } from "../approvals/approvalsMatrixApi";
import { listDivisionMembers, listDivisions, setMemberDivision } from "./designerApi";

const ROLE_LABEL = { admin: "Admin", manager: "Manager", sales: "Sales",
  warehouse: "Gudang", designer: "Desainer" };

const MODE_TONE = {
  enforce: "bg-[#E9F7EF] text-[#1B7F4B]",
  warn: "bg-[#FEF3C7] text-[#B45309]",
  off: "bg-[#F5F5F7] text-[#8E8E93]",
};

export default function DivisionsView({ currentUser, selectedEntity }) {
  const [data, setData] = useState(null);      // {divisions, approver_matrix, assigned}
  const [matrixInfo, setMatrixInfo] = useState(null);  // PS-20 — tingkat + kebijakan penegakan
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingName, setSavingName] = useState("");
  const [msg, setMsg] = useState(null);
  const [filterDiv, setFilterDiv] = useState("");   // klik kartu untuk menyaring anggota

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  const params = useMemo(() => {
    const p = {};
    if (selectedEntity && selectedEntity !== "all") p.entity_id = selectedEntity;
    return p;
  }, [selectedEntity]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, m, mx] = await Promise.all([
        listDivisions(params),
        listDivisionMembers(params),
        approvalMatrix(params).catch(() => null),
      ]);
      setData(d || null);
      setMembers(m || []);
      setMatrixInfo(mx || null);
      setError("");
    } catch (e) {
      setError(errMsg(e, "Gagal memuat data divisi R&D."));
    } finally {
      setLoading(false);
    }
  }, [params]);

  useEffect(() => { load(); }, [load]);

  async function assign(name, division) {
    setSavingName(name);
    setMsg(null);
    try {
      await setMemberDivision({ name, division }, params);
      await load();
      const label = division
        ? (data?.divisions.find((x) => x.id === division)?.name || division)
        : "tanpa divisi";
      setMsg({ ok: true, text: `${name} → ${label}.` });
    } catch (e) {
      setMsg({ ok: false, text: errMsg(e, `Gagal menempatkan ${name}.`) });
    } finally {
      setSavingName("");
    }
  }

  const divisions = data?.divisions || [];
  const matrix = data?.approver_matrix || [];
  const cfg = matrixInfo?.config || {};
  const stageLevels = Object.fromEntries(
    (matrixInfo?.stages || []).map((s) => [s.stage, s.levels || []]));
  const divOptions = [{ value: "", label: "Belum ditempatkan" },
    ...divisions.map((d) => ({ value: d.id, label: d.name }))];
  const shownMembers = filterDiv
    ? members.filter((m) => m.division === filterDiv)
    : members;

  return (
    <div className="grid gap-3" data-testid="rnd-divisions-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
        testId="rnd-divisions-error" />

      {/* ── Kepala ──────────────────────────────────────────────────────── */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-[#6B219A]" />
            <h2 data-testid="rnd-divisions-title">Divisi &amp; Persetujuan R&amp;D</h2>
          </div>
          <button className="secondary-button" onClick={load} data-testid="rnd-divisions-refresh">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
          </button>
        </div>
        <div className="section-body">
          <p className="text-[11.5px] text-[#6B6B73]">
            Menata orang R&amp;D ke dalam divisi dan mendokumentasikan siapa menyetujui tiap
            tahap. Pengaturan ini khusus R&amp;D — tidak mengubah menu atau hak akses aplikasi.
          </p>
          {msg && (
            <p data-testid="rnd-divisions-msg"
              className={`mt-2 rounded-md px-2.5 py-1.5 text-[11.5px] font-medium ${
                msg.ok ? "bg-[#E9F7EF] text-[#1B7F4B]" : "bg-[#FDECEA] text-[#C0392B]"}`}>
              {msg.text}
            </p>
          )}
        </div>
      </section>

      {/* ── Kartu divisi ────────────────────────────────────────────────── */}
      <section className="section-card">
        <div className="section-head"><h2>Divisi ({divisions.length})</h2></div>
        <div className="section-body">
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            data-testid="rnd-divisions-cards">
            {divisions.map((d) => {
              const activeCard = filterDiv === d.id;
              return (
                <button key={d.id} type="button"
                  data-testid={`rnd-division-card-${d.id}`}
                  onClick={() => setFilterDiv(activeCard ? "" : d.id)}
                  className={`rounded-xl border p-3 text-left transition-colors ${
                    activeCard ? "border-[#6B219A] bg-[#F6EEFB]"
                      : "border-[#E5E5EA] bg-white hover:border-[#6B219A]"}`}>
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-bold text-[#1C1C1E]">{d.name}</span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-[#EDE7F6] px-2 py-0.5 text-[10.5px] font-semibold text-[#5E35B1]">
                      <Users2 size={11} /> {d.member_count}
                    </span>
                  </div>
                  <p className="mt-1 text-[10.5px] leading-snug text-[#6B6B73]">{d.desc}</p>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Matriks persetujuan (D-13) + penegakan (PS-20/D-14) ─────────── */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <ShieldCheck size={15} className="text-[#1B7F4B]" />
            <h2>Matriks Persetujuan</h2>
          </div>
        </div>
        <div className="section-body">
          <div className="mb-2.5 flex flex-wrap items-center gap-1.5"
            data-testid="rnd-matrix-enforcement">
            <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ${
              MODE_TONE[cfg.mode] || MODE_TONE.off}`}>
              Penegakan: {cfg.mode_label || "—"}
            </span>
            <span className="rounded-full bg-[#EFF4FF] px-2 py-0.5 text-[10.5px] font-semibold text-[#0058CC]">
              Cakupan: {cfg.scope_label || "—"}
            </span>
            <span className="rounded-full bg-[#F3E9FA] px-2 py-0.5 text-[10.5px] font-semibold text-[#6B219A]">
              Pengaju tidak boleh menyetujui sendiri: {cfg.sod ? "aktif" : "nonaktif"}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-[12px]"
              data-testid="rnd-approver-matrix">
              <thead>
                <tr className="text-[10px] uppercase text-[#8E8E93]">
                  <th className="py-1.5 pr-3 font-bold">Tahap</th>
                  <th className="py-1.5 pr-3 font-bold">Approver</th>
                  <th className="py-1.5 pr-3 font-bold">Tingkat &amp; peran yang mengikat</th>
                  <th className="py-1.5 font-bold">Keterangan</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#F4F5F7]">
                {matrix.map((row) => {
                  const lv = (stageLevels[row.stage] || []);
                  return (
                    <tr key={row.stage} data-testid={`rnd-approver-${row.stage}`}>
                      <td className="py-2 pr-3 font-semibold text-[#1C1C1E]">{row.label}</td>
                      <td className="py-2 pr-3">
                        <span className="flex flex-wrap gap-1">
                          {row.approvers.map((a) => (
                            <span key={a}
                              className="inline-block rounded-full bg-[#E9F7EF] px-2 py-0.5 text-[10.5px] font-semibold text-[#1B7F4B]">
                              {a}
                            </span>
                          ))}
                        </span>
                      </td>
                      <td className="py-2 pr-3" data-testid={`rnd-approver-levels-${row.stage}`}>
                        {lv.length === 0 ? (
                          <span className="text-[11px] text-[#9A9BA3]">—</span>
                        ) : (
                          <span className="flex flex-wrap gap-1">
                            {lv.map((l) => (
                              <span key={l.level}
                                className="inline-block rounded-full bg-[#EEF1F5] px-2 py-0.5 text-[10.5px] font-semibold text-[#4A4B52]">
                                {l.level}. {l.label} → {l.roles_label}
                              </span>
                            ))}
                          </span>
                        )}
                      </td>
                      <td className="py-2 text-[11px] text-[#6B6B73]">{row.note}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[10.5px] text-[#9A9BA3]">
            Matriks ini <strong>mengikat</strong>: percobaan menyetujui oleh peran yang tidak
            berhak (atau oleh pengaju dokumen sendiri) ditolak sistem dan tercatat di jejak
            persetujuan. Antrean keputusan ada di <strong>Pusat Persetujuan › Persetujuan
            Saya</strong>; ketegasannya diatur di Pusat Pengaturan → Persetujuan &amp; Ambang.
          </p>
        </div>
      </section>

      {/* ── Anggota + penempatan divisi ─────────────────────────────────── */}
      <section className="section-card">
        <div className="section-head">
          <h2>Anggota R&amp;D ({shownMembers.length})</h2>
          {filterDiv && (
            <button className="secondary-button" data-testid="rnd-divisions-clear-filter"
              onClick={() => setFilterDiv("")}>Tampilkan semua</button>
          )}
        </div>
        <div className="section-body">
          {loading && !data ? (
            <p className="py-8 text-center text-[12px] text-[#6B6B73]">Memuat anggota…</p>
          ) : shownMembers.length === 0 ? (
            <p className="py-8 text-center text-[12px] text-[#9A9BA3]"
              data-testid="rnd-divisions-members-empty">
              Tidak ada anggota untuk saringan ini.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-[12px]"
                data-testid="rnd-divisions-members">
                <thead>
                  <tr className="text-[10px] uppercase text-[#8E8E93]">
                    <th className="py-1.5 pr-3 font-bold">Nama</th>
                    <th className="py-1.5 pr-3 font-bold">Peran</th>
                    <th className="py-1.5 font-bold">Divisi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#F4F5F7]">
                  {shownMembers.map((m) => (
                    <tr key={m.name} data-testid={`rnd-member-row-${m.name}`}>
                      <td className="py-2 pr-3 font-semibold text-[#1C1C1E]">
                        {m.name}
                        {m.source === "designer" && (
                          <span className="ml-1.5 rounded bg-[#EEF1F5] px-1.5 py-0.5 text-[9.5px] text-[#6B6B73]">
                            non-akun
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3 text-[11.5px] text-[#4A4B52]">
                        {ROLE_LABEL[m.role] || m.role || "—"}
                      </td>
                      <td className="py-2">
                        {canManage ? (
                          <KNSelect
                            data-testid={`rnd-member-division-${m.name}`}
                            value={m.division || ""}
                            onValueChange={(v) => assign(m.name, v)}
                            options={divOptions}
                            disabled={savingName === m.name}
                            className="field !h-8 !w-[190px] !text-[11.5px]" />
                        ) : (
                          <span className="text-[11.5px]">{m.division_name || "—"}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
