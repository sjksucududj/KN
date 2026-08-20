/**
 * AccountList (FASE E-3 / E-2) — daftar akun dengan LENCANA badan usaha.
 *
 * Pertanyaan yang harus bisa dijawab dalam sekali lihat: siapa bekerja di badan
 * usaha mana, apakah akunnya tertaut data karyawan (HR), dan apakah dia masih
 * dipakai (login terakhir). Kolom “Taut HR” sengaja menampilkan PERINGATAN, karena
 * akun tanpa tautan HR adalah sumber utama badan usaha akun ≠ badan usaha payroll.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Search, UserPlus, KeyRound, Power, RotateCcw, LogOut, AlertTriangle,
  Loader2, Pencil } from "lucide-react";

import EntityBadge from "../../../components/EntityBadge";
import PaginationBar from "../../../components/PaginationBar";
import AccountFormDrawer from "./AccountFormDrawer";
import { listUsers, deactivateUser, reactivateUser, resetUserPassword,
  revokeUserSessions, ROLE_OPTIONS, errText } from "./entityApi";
import { askText } from "@/services/confirmService";

const STATUSES = [
  { key: "", label: "Semua status" },
  { key: "active", label: "Aktif" },
  { key: "inactive", label: "Nonaktif" },
];

function fmtDate(iso) {
  if (!iso) return "belum pernah";
  try {
    return new Date(iso).toLocaleDateString("id-ID",
      { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return "—"; }
}

export default function AccountList({ entities = [], currentUser, selectedEntity,
  onChanged, onError }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  // FASE P6 — 15 diganti 20 + bisa diubah pengguna, supaya layar ini memakai kontrol
  // halaman yang SAMA dengan 11 daftar berhalaman lain (dulu pagernya buatan sendiri,
  // dan karena itu satu-satunya yang tak akan pernah kebagian tombol Unduh).
  const [pageSize, setPageSize] = useState(20);
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState(null);   // {} = akun baru

  const isAdmin = currentUser?.role === "admin";
  const activeEntities = useMemo(
    () => entities.filter((e) => e.status === "active"), [entities]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listUsers({
        page, page_size: pageSize,
        ...(q ? { q } : {}),
        ...(role ? { role } : {}),
        ...(status ? { status } : {}),
        ...(entityFilter ? { entity_id: entityFilter } : {}),
      });
      setRows(res?.items || []);
      setTotal(res?.total || 0);
    } catch (e) {
      onError?.(errText(e, "Gagal memuat daftar akun."));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, q, role, status, entityFilter, onError]);

  useEffect(() => { load(); }, [load]);

  // ── FASE P6 — Unduh CSV ────────────────────────────────────────────────────
  const entityName = useCallback((id) => {
    if (!id) return "";
    const e = entities.find((x) => x.id === id);
    return e?.short_name || e?.legal_name || "";
  }, [entities]);

  // Penyusur halaman memakai `listUsers` dengan filter yang SAMA seperti daftar di layar
  // (q/role/status/entity), hanya halamannya yang berjalan.
  const fetchAllAccounts = useCallback(async ({ onProgress, isCancelled } = {}) => {
    const base = {
      ...(q ? { q } : {}),
      ...(role ? { role } : {}),
      ...(status ? { status } : {}),
      ...(entityFilter ? { entity_id: entityFilter } : {}),
    };
    const out = [];
    let p = 1;
    for (;;) {
      const res = await listUsers({ ...base, page: p, page_size: 200 });
      const items = res?.items || [];
      out.push(...items);
      const grand = res?.total ?? out.length;
      if (typeof onProgress === "function") onProgress(out.length, grand);
      if (items.length === 0 || out.length >= grand || out.length >= 50000) break;
      if (typeof isCancelled === "function" && isCancelled()) break;
      p += 1;
    }
    return out;
  }, [q, role, status, entityFilter]);

  // Nama badan usaha, BUKAN id-nya (INV-UI-02): kolom berisi `ent_ksc` tidak berarti
  // apa pun bagi yang membuka berkasnya di Excel.
  const accountCsvColumns = useMemo(() => [
    { key: "name", header: "Nama" },
    { key: "email", header: "Email" },
    { header: "Peran",
      get: (u) => ROLE_OPTIONS.find((r) => r.value === u.role)?.label || u.role },
    { header: "Badan Usaha Utama", get: (u) => entityName(u.home_entity_id) },
    { header: "Badan Usaha Diizinkan",
      get: (u) => (u.allowed_entity_ids || []).map(entityName).filter(Boolean).join(", ") },
    { header: "Lini Produk",     // FASE L — kosong = semua lini, jangan kirim sel kosong
      get: (u) => ((u.allowed_line_codes || []).length
        ? (u.allowed_line_codes || []).join(", ") : "Semua lini") },
    { header: "Taut HR",
      get: (u) => (u.hr_link_warning
        ? u.hr_link_warning
        : [u.employee?.code, u.employee?.name].filter(Boolean).join(" ")) },
    { key: "last_login_at", header: "Terakhir Masuk", type: "date" },
    { header: "Sesi Aktif", get: (u) => Boolean(u.has_active_session) },
    { header: "Status", get: (u) => (u.status === "active" ? "Aktif" : "Nonaktif") },
  ], [entityName]);

  const act = async (fn, id, okMsg) => {
    setBusy(id);
    try {
      const res = await fn(id);
      onChanged?.(typeof okMsg === "function" ? okMsg(res) : okMsg);
      await load();
    } catch (e) {
      onError?.(errText(e, "Aksi akun gagal."));
    } finally {
      setBusy("");
    }
  };

  const doReset = async (u) => {
    // FASE P5 — dulu `window.prompt`: kata sandi baru diketik sebagai TEKS TERBUKA di kotak
    // bawaan peramban (terlihat siapa pun di dekat layar, bisa tersimpan di riwayat sesi
    // peramban). `askText` dengan `inputType: "password"` menyamarkan karakternya.
    const pwd = await askText({
      title: `Setel ulang kata sandi ${u.name}?`,
      message: "Semua sesi lama akun ini dicabut dan dia harus masuk lagi dengan kata sandi baru.",
      reasonLabel: "Kata sandi baru (minimal 8 karakter)",
      inputType: "password",
      confirmLabel: "Setel Ulang",
      danger: true,
      testId: "account-reset-pwd",
    });
    if (pwd === null) return;
    if (pwd.length < 8) {
      onError?.("Kata sandi baru minimal 8 karakter.");
      return;
    }
    setBusy(u.id);
    try {
      const res = await resetUserPassword(u.id, pwd);
      onChanged?.(`${res.message} (${res.sessions_revoked} sesi dicabut)`);
    } catch (e) {
      onError?.(errText(e, "Gagal reset password."));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="section-card" data-testid="account-list-card">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <h2 data-testid="account-list-title">Akun & Akses</h2>
          <span className="text-[10.5px] text-[#9A9BA3] tabular-nums"
                data-testid="account-list-count">{total} akun</span>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1" data-testid="account-entity-filter">
            <button type="button" data-testid="account-entity-all"
                    onClick={() => { setEntityFilter(""); setPage(1); }}
                    className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                      !entityFilter ? "bg-[#007AFF] text-white"
                        : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
              Semua badan usaha
            </button>
            {activeEntities.map((e) => (
              <button key={e.id} type="button" data-testid={`account-entity-${e.id}`}
                      onClick={() => { setEntityFilter(e.id); setPage(1); }}
                      className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                        entityFilter === e.id ? "bg-[#007AFF] text-white"
                          : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
                {e.short_name || e.legal_name}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1" data-testid="account-status-filter">
            {STATUSES.map((s) => (
              <button key={s.key || "all"} type="button"
                      data-testid={`account-status-${s.key || "all"}`}
                      onClick={() => { setStatus(s.key); setPage(1); }}
                      className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                        status === s.key ? "bg-[#6B219A] text-white"
                          : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
                {s.label}
              </button>
            ))}
          </div>
          <div className="relative">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="account-search-input" className="field pl-7 py-1 text-[12px]"
                   placeholder="Cari nama / email…" value={q}
                   onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          </div>
          {isAdmin && (
            <button type="button" className="primary-button" data-testid="account-add-button"
                    onClick={() => setEditing({})}>
              <UserPlus size={14} /> Buat Akun
            </button>
          )}
        </div>
      </div>

      <div className="section-body">
        <div className="mb-2 flex flex-wrap items-center gap-1" data-testid="account-role-filter">
          <span className="text-[10px] font-bold uppercase text-[#8E8E93]">Peran</span>
          <button type="button" data-testid="account-role-all"
                  onClick={() => { setRole(""); setPage(1); }}
                  className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                    !role ? "bg-[#1C1C1E] text-white"
                      : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
            Semua
          </button>
          {ROLE_OPTIONS.map((r) => (
            <button key={r.value} type="button" data-testid={`account-role-${r.value}`}
                    onClick={() => { setRole(r.value); setPage(1); }}
                    className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                      role === r.value ? "bg-[#1C1C1E] text-white"
                        : "border border-[#E5E5EA] bg-white text-[#6B6B73]"}`}>
              {r.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="grid gap-2" data-testid="account-list-loading">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-11 animate-pulse rounded bg-[#F5F5F7]" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-[#8E8E93]"
               data-testid="account-list-empty">
            Tidak ada akun yang cocok dengan filter ini.
          </div>
        ) : (
          <div className="overflow-auto rounded-md border border-[#EFF0F2]">
            <table className="w-full text-[12px]" data-testid="account-list-table">
              <thead>
                <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
                  <th className="px-3 py-2">Nama & email</th>
                  <th className="px-3 py-2">Peran</th>
                  <th className="px-3 py-2">Badan usaha utama</th>
                  <th className="px-3 py-2">Badan usaha diizinkan</th>
                  <th className="px-3 py-2">Lini produk</th>
                  <th className="px-3 py-2">Taut HR</th>
                  <th className="px-3 py-2">Terakhir masuk</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.id} data-testid={`account-row-${u.id}`}
                      className="border-b border-[#F5F5F7] last:border-0 hover:bg-[#FAFBFF]">
                    <td className="px-3 py-2">
                      <p className="font-semibold text-[#1C1C1E]">{u.name}</p>
                      <p className="text-[10px] text-[#9A9BA3]">{u.email}</p>
                    </td>
                    <td className="px-3 py-2 text-[#3C3C43]" data-testid={`account-role-cell-${u.id}`}>
                      {ROLE_OPTIONS.find((r) => r.value === u.role)?.label || u.role}
                    </td>
                    <td className="px-3 py-2" data-testid={`account-home-${u.id}`}>
                      <EntityBadge entityId={u.home_entity_id} entities={entities} />
                    </td>
                    <td className="px-3 py-2" data-testid={`account-allowed-${u.id}`}>
                      <div className="flex flex-wrap gap-1">
                        {(u.allowed_entity_ids || []).map((id) => (
                          <EntityBadge key={id} entityId={id} entities={entities} />
                        ))}
                      </div>
                    </td>
                    {/* FASE L — kolom lini: "Semua lini" bukan sel kosong. Sel kosong
                        terbaca "belum diatur / tidak boleh apa-apa"; kenyataannya
                        kosong = boleh SEMUA, dan itu harus terbaca sekali lihat. */}
                    <td className="px-3 py-2" data-testid={`account-lines-${u.id}`}>
                      {(u.allowed_line_codes || []).length === 0 ? (
                        <span className="text-[10.5px] text-[#8E8E93]">Semua lini</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {(u.allowed_line_codes || []).map((c) => (
                            <span key={c}
                                  className="rounded bg-[#F3E9FA] px-1.5 py-0.5 text-[9.5px] font-bold text-[#6B219A]">
                              {c}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2" data-testid={`account-hr-${u.id}`}>
                      {u.hr_link_warning ? (
                        <span className="inline-flex items-center gap-1 text-[10.5px] font-semibold text-[#B45309]"
                              title={u.hr_link_warning}>
                          <AlertTriangle size={11} /> {u.hr_link_warning}
                        </span>
                      ) : (
                        <span className="text-[10.5px] text-[#1B7F4B]">
                          {u.employee?.code} {u.employee?.name}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-[10.5px] text-[#6B6B73] tabular-nums">
                      {fmtDate(u.last_login_at)}
                      {u.has_active_session && (
                        <span className="ml-1 rounded bg-[#E6F6EC] px-1 text-[9px] font-bold text-[#1B7F4B]">
                          sesi aktif
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span className="status-pill" data-testid={`account-status-pill-${u.id}`}
                            style={u.status === "active"
                              ? { background: "#E6F6EC", color: "#1B7F4B" }
                              : { background: "#F2F2F7", color: "#6B6B73" }}>
                        {u.status === "active" ? "Aktif" : "Nonaktif"}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap items-center justify-end gap-1">
                        {isAdmin && (
                          <button type="button" className="secondary-button !py-1 !px-2 !text-[10.5px]"
                                  data-testid={`account-edit-${u.id}`}
                                  onClick={() => setEditing(u)}>
                            <Pencil size={11} /> Ubah
                          </button>
                        )}
                        {isAdmin && (
                          <button type="button" className="secondary-button !py-1 !px-2 !text-[10.5px]"
                                  data-testid={`account-reset-${u.id}`}
                                  disabled={busy === u.id} onClick={() => doReset(u)}>
                            <KeyRound size={11} /> Reset
                          </button>
                        )}
                        {isAdmin && u.has_active_session && (
                          <button type="button" className="secondary-button !py-1 !px-2 !text-[10.5px]"
                                  data-testid={`account-revoke-${u.id}`}
                                  disabled={busy === u.id}
                                  onClick={() => act(revokeUserSessions, u.id,
                                    (r) => `${r.sessions_revoked} sesi ${u.name} dicabut.`)}>
                            <LogOut size={11} /> Cabut sesi
                          </button>
                        )}
                        {isAdmin && u.status === "active" && (
                          <button type="button" className="secondary-button !py-1 !px-2 !text-[10.5px]"
                                  data-testid={`account-deactivate-${u.id}`}
                                  disabled={busy === u.id}
                                  onClick={() => act(deactivateUser, u.id,
                                    `Akun ${u.name} dinonaktifkan — datanya tetap tersimpan.`)}>
                            {busy === u.id ? <Loader2 size={11} className="animate-spin" />
                                           : <Power size={11} />} Nonaktifkan
                          </button>
                        )}
                        {isAdmin && u.status !== "active" && (
                          <button type="button" className="secondary-button !py-1 !px-2 !text-[10.5px]"
                                  data-testid={`account-reactivate-${u.id}`}
                                  disabled={busy === u.id}
                                  onClick={() => act(reactivateUser, u.id,
                                    `Akun ${u.name} aktif kembali.`)}>
                            <RotateCcw size={11} /> Aktifkan
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {rows.length > 0 && (
          <div className="mt-2" data-testid="account-list-pager">
            <PaginationBar
              testId="account-pager" label="akun"
              page={page} pageSize={pageSize} total={total}
              hasMore={page * pageSize < total} loading={loading}
              onPrev={() => setPage((p) => Math.max(1, p - 1))}
              onNext={() => setPage((p) => p + 1)}
              onPageSize={(n) => { setPageSize(n); setPage(1); }}
              exportConfig={{ columns: accountCsvColumns, rows,
                fetchAll: fetchAllAccounts, filename: "akun-pengguna" }}
            />
          </div>
        )}
      </div>

      {editing && (
        <AccountFormDrawer
          user={editing.id ? editing : null}
          entities={activeEntities}
          selectedEntity={selectedEntity}
          onClose={() => setEditing(null)}
          onSaved={(msg) => { setEditing(null); onChanged?.(msg); load(); }}
          onError={onError}
        />
      )}
    </div>
  );
}
