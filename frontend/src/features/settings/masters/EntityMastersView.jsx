/**
 * EntityMastersView (FASE E-4 · E4d) — MASTER PER BADAN USAHA.
 *
 * KENAPA SATU LAYAR UNTUK ENAM MASTER
 * Keputusan pemilik #6: semua master yang dulu "bersama" harus bisa berbeda per
 * badan usaha. Kalau tiap master dapat layarnya sendiri, aturan yang sama
 * (**global → badan usaha**, override menang, global tak boleh diubah dari konteks
 * satu badan usaha) akan ditulis ulang enam kali — dan pengguna harus menghafal enam
 * tempat untuk satu pertanyaan sederhana: *"nilai ini milik badan usaha saya atau
 * milik semua?"*
 *
 * Yang dijaga layar ini secara sadar:
 *   · Setiap baris SELALU berlencana asal — **Global** atau **Badan usaha ini**.
 *     Tanpa lencana, angka yang sama terbaca dua arti (cacat yang dicatat plan.md §6).
 *   · Baris global yang sudah ditimpa diredupkan + diberi keterangan "ditimpa" supaya
 *     tak ada yang bingung kenapa nilainya "tidak berlaku".
 *   · Tombol **Buat khusus <badan usaha>** = satu klik menyalin baris global.
 *     Tombol **Kembalikan ke global** = melepas override.
 *   · Baris global hanya bisa diubah di mode **Semua Entitas** — layar mengatakannya
 *     sebelum pengguna mencoba, dan server menolak 409 bila tetap dicoba.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Building2, CheckCircle2, ChevronRight, Copy, ExternalLink, Globe, Info, Layers3,
  Plus, RefreshCw, RotateCcw, Save, Search, Trash2, X,
} from "lucide-react";

import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import KNSelect from "../../../components/KNSelect";
import useUomConversions from "../../../hooks/useUomConversions";   // FASE U
import { uomSelectOptions } from "../../../utils/uomCatalog";        // FASE U
import { entityShort, entityShortById } from "../../../utils/entityLabel";
import { formatCurrency } from "../../../utils/formatters";
import { COLUMNS, CREATE_FIELDS, cellText, defaultsFor, fieldOf, parseFieldValue, toInputValue }
  from "./masterFieldsConfig";

/**
 * FASE L — definisi kolom & field per jenis master dipindah ke berkas data
 * `masterFieldsConfig.js`. Alasannya bukan estetika: jenis master BARU tanpa entri
 * kolom akan muncul di layar ini sebagai **tabel tanpa kolom** (§3.3 rencana MD ERP),
 * dan berkas ini sudah menyentuh batas panduan 500 baris. Sekarang menambah master
 * = menambah satu entri data, tanpa menyunting layar.
 */
const fmtCell = (col, row) => cellText(col, row, formatCurrency);

export default function EntityMastersView({ entities = [], selectedEntity = "all", currentUser }) {
  const activeList = useMemo(
    () => (entities || []).filter((e) => e.status !== "inactive" && e.status !== "archived"),
    [entities]);
  const groupMode = !selectedEntity || selectedEntity === "all";
  const entityLabel = groupMode ? "Semua Badan Usaha" : entityShortById(activeList, selectedEntity);

  const [groups, setGroups] = useState([]);
  const [kind, setKind] = useState("payment-terms");
  const [data, setData] = useState(null);
  const [loadingGroups, setLoadingGroups] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState("");
  const [editRow, setEditRow] = useState(null);     // { id, values }
  const [creating, setCreating] = useState(false);
  const [createValues, setCreateValues] = useState({});
  const [createGlobal, setCreateGlobal] = useState(false);

  const canManage = ["admin", "manager"].includes(currentUser?.role);
  const spec = groups.find((g) => g.kind === kind) || {};

  const loadGroups = useCallback(async () => {
    setLoadingGroups(true);
    try {
      const res = await axios.get(`${API}/entity-masters`);
      setGroups(Array.isArray(res.data) ? res.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat daftar master.");
    } finally { setLoadingGroups(false); }
  }, []);

  const loadRows = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/entity-masters/${kind}`, {
        params: { include_inactive: false },
      });
      setData(res.data || null);
      setError("");
    } catch (e) {
      setData(null);
      setError(e.response?.data?.detail || "Gagal memuat baris master.");
    } finally { setLoading(false); }
  }, [kind]);

  useEffect(() => { loadGroups(); }, [loadGroups, selectedEntity]);
  useEffect(() => { loadRows(); }, [loadRows, selectedEntity]);

  const flash = (msg) => { setNotice(msg); setTimeout(() => setNotice(""), 4000); };

  const rows = useMemo(() => {
    const all = data?.rows || [];
    const q = search.trim().toLowerCase();
    if (!q) return all;
    return all.filter((r) => JSON.stringify(r).toLowerCase().includes(q));
  }, [data, search]);

  const columns = COLUMNS[kind] || [{ key: data?.name_field || "name", label: "Nama" }];
  const createFields = CREATE_FIELDS[kind] || [];
  // FASE U — field ber-`optionsFrom: "uom"` mengambil pilihannya dari MASTER SATUAN
  // (katalog server = benih + baris master aktif). Ini yang membuat "menambah satuan
  // di master" benar-benar mengubah pemilih di layar master lain — tanpa perlu satu
  // baris kode diubah untuk setiap satuan baru.
  useUomConversions();
  const selectOptionsOf = (f) => (f.optionsFrom === "uom"
    ? uomSelectOptions({ dimensions: ["length", "weight", "count"] })
    : (f.options || []));

  // ─── aksi ──────────────────────────────────────────────────────────────────
  async function doOverride(row) {
    setBusyId(row.id); setError("");
    try {
      await axios.post(`${API}/entity-masters/${kind}/${row.id}/override`);
      flash(`Salinan khusus ${entityLabel} dibuat — sekarang bisa diubah tanpa memengaruhi badan usaha lain.`);
      await Promise.all([loadRows(), loadGroups()]);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal membuat salinan khusus badan usaha.");
    } finally { setBusyId(""); }
  }

  async function doRevert(row) {
    setBusyId(row.id); setError("");
    try {
      const res = await axios.delete(`${API}/entity-masters/${kind}/${row.id}`);
      flash(res.data?.fell_back_to_global
        ? "Override dilepas — nilainya kembali mengikuti baris Global."
        : "Override dilepas. Tidak ada baris Global untuk kunci ini, jadi nilainya kini tidak diatur.");
      await Promise.all([loadRows(), loadGroups()]);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal melepas override.");
    } finally { setBusyId(""); }
  }

  async function saveEdit() {
    if (!editRow) return;
    setBusyId(editRow.id); setError("");
    try {
      await axios.patch(`${API}/entity-masters/${kind}/${editRow.id}`, { data: editRow.values });
      flash("Perubahan tersimpan.");
      setEditRow(null);
      await loadRows();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyimpan perubahan.");
    } finally { setBusyId(""); }
  }

  async function saveCreate() {
    setError("");
    const missing = createFields.filter((f) => f.required && !String(createValues[f.key] || "").trim());
    if (missing.length) {
      setError(`Lengkapi dulu: ${missing.map((m) => m.label).join(", ")}.`);
      return;
    }
    setBusyId("create");
    try {
      const body = { ...createValues };
      if (createGlobal || groupMode) body.entity_id = "all";
      await axios.post(`${API}/entity-masters/${kind}`, body);
      flash(createGlobal || groupMode
        ? "Baris baru dibuat sebagai Global — berlaku untuk semua badan usaha."
        : `Baris baru dibuat khusus ${entityLabel}.`);
      setCreating(false); setCreateValues({}); setCreateGlobal(false);
      await Promise.all([loadRows(), loadGroups()]);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menambah baris master.");
    } finally { setBusyId(""); }
  }

  // ─── render ────────────────────────────────────────────────────────────────
  return (
    <div data-testid="entity-masters-view" className="grid gap-4">
      {notice && (
        <div data-testid="em-notice"
          className="flex items-center gap-2 rounded-md border border-[#BDE5CC] bg-[#E6F6EC] px-3 py-2 text-[12px] text-[#1B7F4B]">
          <CheckCircle2 size={14} /><span>{notice}</span>
          <button className="ml-auto" onClick={() => setNotice("")} aria-label="Tutup"><X size={13} /></button>
        </div>
      )}
      <ErrorNotice message={error} onRetry={loadRows} onDismiss={() => setError("")} testId="em-error" />

      {/* Pita konteks — pengguna harus tahu ia sedang mengubah milik siapa */}
      <div data-testid="em-scope-ribbon"
        className={`flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-[12px] ${
          groupMode
            ? "border-[#F5C97B] bg-[#FFF7E6] text-[#8C4A00]"
            : "border-[#D6E6FF] bg-[#F0F6FF] text-[#004099]"}`}>
        {groupMode ? <Globe size={14} /> : <Building2 size={14} />}
        <span>
          {groupMode ? (
            <>Anda berada di mode <b>Semua Badan Usaha</b>. Di sini Anda mengubah nilai{" "}
              <b>Global</b> — perubahannya berlaku untuk <b>semua</b> badan usaha.</>
          ) : (
            <>Anda sedang mengatur <b>{entityLabel}</b>. Baris berlencana <b>Global</b> milik
              semua badan usaha dan tidak bisa diubah dari sini — pakai{" "}
              <b>Buat khusus {entityLabel}</b> untuk membuat salinannya.</>
          )}
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        {/* Kolom kiri — kelompok master */}
        <section className="section-card">
          <div className="section-head">
            <div className="flex min-w-0 items-center gap-2">
              <Layers3 size={15} className="text-[#0058CC]" />
              <span className="kicker">Master</span>
              <h2 data-testid="em-groups-title">Kelompok</h2>
            </div>
            <button data-testid="em-refresh-groups" className="icon-button" onClick={loadGroups}
              aria-label="Muat ulang kelompok">
              <RefreshCw size={14} className={loadingGroups ? "animate-spin" : ""} />
            </button>
          </div>
          <div className="section-body">
            {loadingGroups ? (
              <div className="grid gap-2" data-testid="em-groups-loading">
                {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="h-12 animate-pulse rounded bg-[#F5F5F7]" />)}
              </div>
            ) : groups.length === 0 ? (
              <p data-testid="em-groups-empty" className="py-6 text-center text-[12px] text-[#8E8E93]">
                Belum ada master berlapis yang terdaftar.
              </p>
            ) : (
              <div className="grid gap-1.5">
                {groups.map((g) => {
                  const on = g.kind === kind;
                  return (
                    <button key={g.kind} type="button" data-testid={`em-group-${g.kind}`}
                      onClick={() => { setKind(g.kind); setEditRow(null); setCreating(false); }}
                      className={`flex items-start gap-2 rounded-md border px-2.5 py-2 text-left transition-colors ${
                        on ? "border-[#0058CC] bg-[#EAF2FF]" : "border-[#E5E5EA] bg-white hover:border-[#0058CC]"}`}>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12.5px] font-bold text-[#1C1C1E]">{g.label}</span>
                        <span className="block text-[10.5px] text-[#6B6B73]">
                          <span data-testid={`em-count-global-${g.kind}`}>{g.global} global</span>
                          {" · "}
                          <span data-testid={`em-count-entity-${g.kind}`}>{g.entity} khusus</span>
                          {!g.manage && " · dikelola di layar sendiri"}
                        </span>
                      </span>
                      <ChevronRight size={14} className={on ? "text-[#0058CC]" : "text-[#C7C7CC]"} />
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        {/* Kolom kanan — baris master */}
        <section className="section-card">
          <div className="section-head">
            <div className="flex min-w-0 items-center gap-2">
              <Building2 size={15} className="text-[#6B219A]" />
              <span className="kicker">{entityLabel}</span>
              <h2 data-testid="em-rows-title">{spec.label || data?.label || "Master"}</h2>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <div className="relative">
                <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-[#8E8E93]" />
                <input data-testid="em-search" value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Cari baris…"
                  className="h-8 w-[180px] rounded-md border border-[#E5E5EA] bg-white pl-7 pr-2 text-[12px] text-[#1C1C1E] placeholder:text-[#B0B0B8] focus:border-[#0058CC] focus:outline-none" />
              </div>
              {canManage && (data?.manage ?? spec.manage) !== false && (
                <button data-testid="em-toggle-create" className="secondary-button text-[11.5px]"
                  onClick={() => {
                    // Bawaan diisi saat form DIBUKA (bukan disimpan di state awal),
                    // supaya berganti jenis master tidak membawa bawaan master lain.
                    setCreating((v) => {
                      if (!v) setCreateValues(defaultsFor(kind));
                      return !v;
                    });
                    setEditRow(null);
                  }}>
                  <Plus size={13} /> Baris baru
                </button>
              )}
              <button data-testid="em-refresh-rows" className="icon-button" onClick={loadRows} aria-label="Muat ulang">
                <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
              </button>
            </div>
          </div>

          <div className="section-body">
            {(spec.hint || data?.hint) && (
              <div className="mb-3 flex items-start gap-2 rounded-md border border-[#D6E6FF] bg-[#F0F6FF] px-3 py-2 text-[11.5px] text-[#004099]">
                <Info size={14} className="mt-0.5 shrink-0" />
                <span data-testid="em-hint">{spec.hint || data?.hint}</span>
              </div>
            )}

            {(data?.manage ?? spec.manage) === false && (
              <div data-testid="em-readonly-hint"
                className="mb-3 flex items-center gap-2 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2 text-[11.5px] text-[#6B6B73]">
                <ExternalLink size={13} />
                <span>Master ini hanya <b>ditampilkan</b> di sini supaya asal nilainya terlihat.
                  Perubahannya dilakukan di layar khususnya.</span>
              </div>
            )}

            {/* Form tambah baris */}
            {creating && (
              <div data-testid="em-create-form"
                className="mb-3 rounded-md border border-[#0058CC]/30 bg-[#F7FAFF] p-3">
                <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-[#004099]">
                  Baris baru · {groupMode ? "Global" : (createGlobal ? "Global" : `khusus ${entityLabel}`)}
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {createFields.map((f) => (
                    <label key={f.key} className="grid gap-1 text-[11px] text-[#6B6B73]">
                      <span>{f.label}{f.required && <span className="text-[#C0392B]"> *</span>}</span>
                      {f.type === "select" ? (
                        <KNSelect testId={`em-form-${f.key}`} value={createValues[f.key] ?? ""}
                          onValueChange={(v) => setCreateValues({ ...createValues, [f.key]: v })}
                          options={selectOptionsOf(f)} placeholder="Pilih…" />
                      ) : f.type === "checkbox" ? (
                        <input data-testid={`em-form-${f.key}`} type="checkbox"
                          checked={Boolean(createValues[f.key])}
                          onChange={(e) => setCreateValues({ ...createValues, [f.key]: e.target.checked })}
                          className="h-4 w-4" />
                      ) : (
                        <input data-testid={`em-form-${f.key}`} type={f.type === "number" ? "number" : "text"}
                          value={toInputValue(f, createValues[f.key]) ?? ""} placeholder={f.placeholder || ""}
                          onChange={(e) => setCreateValues({
                            ...createValues,
                            [f.key]: parseFieldValue(f, e.target.value),
                          })}
                          className="h-8 rounded-md border border-[#E5E5EA] bg-white px-2 text-[12px] text-[#1C1C1E] focus:border-[#0058CC] focus:outline-none" />
                      )}
                      {f.hint && (
                        <span className="text-[10px] text-[#8E8E93]" data-testid={`em-form-hint-${f.key}`}>
                          {f.hint}
                        </span>
                      )}
                    </label>
                  ))}
                </div>
                {!groupMode && (
                  <label data-testid="em-form-global-toggle"
                    className="mt-2 flex cursor-pointer items-center gap-2 text-[11.5px] text-[#3A3A3C]">
                    <input type="checkbox" checked={createGlobal}
                      onChange={(e) => setCreateGlobal(e.target.checked)} />
                    <span>Jadikan <b>Global</b> — berlaku untuk semua badan usaha, bukan hanya {entityLabel}</span>
                  </label>
                )}
                <div className="mt-3 flex justify-end gap-2">
                  <button className="secondary-button text-[11.5px]"
                    onClick={() => { setCreating(false); setCreateValues({}); setCreateGlobal(false); }}>
                    Batal
                  </button>
                  <button data-testid="em-form-save" className="primary-button text-[11.5px]"
                    disabled={busyId === "create"} onClick={saveCreate}>
                    <Save size={13} /> {busyId === "create" ? "Menyimpan…" : "Simpan baris"}
                  </button>
                </div>
              </div>
            )}

            {/* Ringkasan lapisan */}
            {data?.summary && !loading && (
              <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px]">
                <span data-testid="em-summary-global"
                  className="rounded bg-[#F5F5F7] px-2 py-1 font-semibold text-[#6B6B73]">
                  {data.summary.global} baris Global
                </span>
                <span data-testid="em-summary-entity"
                  className="rounded bg-[#F3E9FA] px-2 py-1 font-semibold text-[#6B219A]">
                  {data.summary.entity} khusus badan usaha
                </span>
                {data.summary.overridden > 0 && (
                  <span data-testid="em-summary-overridden"
                    className="rounded bg-[#FFF7E6] px-2 py-1 font-semibold text-[#8C4A00]">
                    {data.summary.overridden} baris Global sedang ditimpa
                  </span>
                )}
              </div>
            )}

            {loading ? (
              <div className="grid gap-2" data-testid="em-loading">
                {[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-[#F5F5F7]" />)}
              </div>
            ) : rows.length === 0 ? (
              <div data-testid="em-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">
                <Layers3 size={26} className="mx-auto mb-2 text-gray-300" />
                {search
                  ? `Tidak ada baris yang cocok dengan "${search}".`
                  : `Belum ada baris ${spec.label || "master"} untuk ${entityLabel}.`}
              </div>
            ) : (
              <div className="overflow-auto rounded-md border border-[#EFF0F2]">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
                      {columns.map((c) => (
                        <th key={c.key} className={`px-3 py-2 ${c.align === "right" ? "text-right" : ""}`}>
                          {c.label}
                        </th>
                      ))}
                      <th className="px-3 py-2 text-center">Asal</th>
                      <th className="px-3 py-2 text-right">Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => {
                      const isGlobal = r.entity_scope === "global";
                      const editing = editRow?.id === r.id;
                      return (
                        <tr key={r.id} data-testid={`em-row-${r.id}`}
                          className={`border-b border-[#F5F5F7] last:border-0 hover:bg-[#FBF8FE] ${
                            r.is_overridden ? "opacity-55" : ""}`}>
                          {columns.map((c) => (
                            <td key={c.key}
                              className={`px-3 py-2 ${c.align === "right" ? "text-right tabular-nums" : ""} ${
                                c.mono ? "font-mono text-[11px] text-[#6B6B73]" : "text-[#1C1C1E]"}`}>
                              {editing && (createFields.some((f) => f.key === c.key)) ? (
                                <input data-testid={`em-edit-${c.key}`}
                                  value={toInputValue(fieldOf(kind, c.key), editRow.values[c.key]) ?? ""}
                                  onChange={(e) => setEditRow({
                                    ...editRow,
                                    values: {
                                      ...editRow.values,
                                      // Bentuk nilai mengikuti DEFINISI field (list → array,
                                      // angka → number). Sebelum FASE L bentuknya ditebak dari
                                      // nilai lama di baris (`typeof r[c.key]`), yang salah untuk
                                      // baris yang fieldnya masih kosong.
                                      [c.key]: parseFieldValue(fieldOf(kind, c.key), e.target.value),
                                    },
                                  })}
                                  className="h-7 w-full rounded border border-[#0058CC]/40 bg-white px-1.5 text-[12px] focus:border-[#0058CC] focus:outline-none" />
                              ) : (
                                <span className="line-clamp-2">{fmtCell(c, r)}</span>
                              )}
                            </td>
                          ))}
                          <td className="px-3 py-2 text-center">
                            <span data-testid={`em-source-${r.id}`}
                              className={`whitespace-nowrap rounded px-1.5 py-0.5 text-[9px] font-bold ${
                                isGlobal ? "bg-[#F5F5F7] text-[#6B6B73]" : "bg-[#F3E9FA] text-[#6B219A]"}`}>
                              {r.source_label}
                            </span>
                            {r.is_overridden && (
                              <span data-testid={`em-overridden-${r.id}`}
                                className="mt-0.5 block text-[9px] font-semibold text-[#8C4A00]">
                                ditimpa {entityLabel}
                              </span>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-right">
                            {editing ? (
                              <>
                                <button data-testid={`em-edit-cancel-${r.id}`} className="secondary-button text-[11px]"
                                  onClick={() => setEditRow(null)}>Batal</button>
                                <button data-testid={`em-edit-save-${r.id}`} className="primary-button ml-1 text-[11px]"
                                  disabled={busyId === r.id} onClick={saveEdit}>
                                  <Save size={12} /> Simpan
                                </button>
                              </>
                            ) : (
                              <>
                                {canManage && isGlobal && !groupMode && !r.is_overridden
                                  && (data?.manage ?? spec.manage) !== false && (
                                  <button data-testid={`em-override-${r.id}`}
                                    className="secondary-button text-[11px]" disabled={busyId === r.id}
                                    title={`Salin baris ini menjadi milik ${entityLabel}`}
                                    onClick={() => doOverride(r)}>
                                    <Copy size={12} /> Buat khusus {entityLabel}
                                  </button>
                                )}
                                {canManage && !isGlobal && (data?.manage ?? spec.manage) !== false && (
                                  <button data-testid={`em-revert-${r.id}`}
                                    className="secondary-button ml-1 text-[11px]" disabled={busyId === r.id}
                                    title="Lepas override — kembali mengikuti nilai Global"
                                    onClick={() => doRevert(r)}>
                                    <RotateCcw size={12} /> Kembalikan ke global
                                  </button>
                                )}
                                {canManage && r.can_edit_here && (data?.manage ?? spec.manage) !== false && (
                                  <button data-testid={`em-edit-${r.id}`}
                                    className="primary-button ml-1 text-[11px]"
                                    onClick={() => setEditRow({ id: r.id, values: { ...r } })}>
                                    Ubah
                                  </button>
                                )}
                              </>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
