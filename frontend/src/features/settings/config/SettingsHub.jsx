/**
 * SettingsHub — **PUSAT PENGATURAN** (FASE G-0, frontend).
 *
 * Menyelesaikan 5 masalah nyata yang dikonfirmasi audit 2026-07-26:
 *   1. Konfigurasi tersebar di **13 permukaan editor** dengan 13 bentuk API →
 *      user tidak tahu di mana mengubah apa. Sekarang: satu pintu.
 *   2. **31 aturan tersembunyi** (dipakai mesin, tanpa UI) → sekarang SEMUA
 *      setting di registry dirender otomatis, jadi UI tidak mungkin ketinggalan.
 *   3. **6 tombol palsu** (UI tanpa pembaca kode) → tab Kesehatan Konfigurasi.
 *   4. Tak ada penjelasan/jejak/riwayat → tiap kartu punya "Artinya", "Kalau
 *      diubah", contoh angka, "Kenapa nilainya begini?", "Coba dulu", "Riwayat".
 *   5. Tak ada berlaku-sejak → setiap perubahan bisa dijadwalkan.
 *
 * IA: kelompok disusun berdasarkan **PERTANYAAN BISNIS** (bukan nama modul),
 * mis. "Kapan pelanggan harus bayar, dan apa akibatnya kalau telat?".
 *
 * Sumber data: /api/config/registry · /effective · /explain · /simulate ·
 * /values · /values/reset · /history · /health · /impact-preview · /impact-apply
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Search, SlidersHorizontal, ShieldCheck, History, Wand2, Loader2, RefreshCw,
  CheckCircle2, AlertTriangle, X, Building2, ChevronRight, Globe2,
} from "lucide-react";
import ErrorNotice from "../../../components/ErrorNotice";
import KNSelect from "../../../components/KNSelect";
import SettingCard from "./SettingCard";
import ImpactPicker from "./ImpactPicker";
import ConfigHealthPanel from "./ConfigHealthPanel";
import {
  WhyThisValueDrawer, SimulatorPanel, ChangeHistoryDrawer, ChangeHistoryInline,
} from "./ConfigDrawers";
import { configApi, errMsg, SCOPE_LABEL } from "./configApi";
import { LEGACY_DEEPLINK, groupForKey } from "./configDeepLink";
import { entityOptions, entityShortById } from "../../../utils/entityLabel";

const TABS = [
  { k: "settings", label: "Pengaturan", icon: SlidersHorizontal },
  { k: "health", label: "Kesehatan Konfigurasi", icon: ShieldCheck },
  { k: "history", label: "Riwayat Perubahan", icon: History },
  { k: "impact", label: "Koreksi Harga & Daftar Dampak", icon: Wand2 },
];

/**
 * Kelompok mana yang dituju oleh editor lama (deep-link satu sumber kebenaran).
 * Definisi pindah ke `configDeepLink.js` (modul tanpa dependensi) agar layar lain
 * bisa menautkan tanpa ikut menarik bundel Pusat Pengaturan yang di-lazy-load.
 * Re-export dipertahankan supaya impor lama tidak patah.
 */
export { LEGACY_DEEPLINK };

export default function SettingsHub({
  currentUser,
  selectedEntity,
  entities = [],
  focusKey = "",
  focusGroup = "",
  focusNonce = 0,
  onFocusConsumed,
}) {
  const isAdmin = currentUser?.role === "admin";

  const [tab, setTab] = useState("settings");
  const [groups, setGroups] = useState([]);
  const [group, setGroup] = useState("");
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");           // q yang sudah di-debounce
  // FASE E-4 (E4.6) — scope BAWAAN = badan usaha aktif, bukan global.
  // Alasannya nyata: pengguna membuka Pusat Pengaturan sambil bekerja "di CV Kanda
  // Suka", lalu mengubah nilai yang ternyata GLOBAL dan diam-diam mengubah aturan
  // seluruh grup. Sekarang default-nya aman, dan pita di atas kartu menyebutkan
  // dengan jelas nilai siapa yang sedang diubah.
  const singleEntity = selectedEntity && selectedEntity !== "all" ? selectedEntity : "";
  const [scopeType, setScopeType] = useState(singleEntity ? "entity" : "global");
  const [scopeId, setScopeId] = useState(singleEntity);
  const [health, setHealth] = useState({});       // key -> row wiring
  // Kemampuan NYATA user menurut server (bukan tebakan dari role di klien).
  // Sumber: GET /api/config/registry → caps. Membuat UI tidak pernah menampilkan
  // tombol yang pasti ditolak server (akar masalah lama "tombol palsu").
  const [caps, setCaps] = useState({ settings_manage: false, impact_apply: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null);     // {msg, tone}
  const [why, setWhy] = useState(null);
  const [sim, setSim] = useState(null);           // {entry, draft}
  const [hist, setHist] = useState(null);         // {entry} | {} = semua
  const cardRefs = useRef({});

  const flash = useCallback((msg, tone = "ok") => {
    setNotice({ msg, tone });
    window.clearTimeout(flash._t);
    flash._t = window.setTimeout(() => setNotice(null), tone === "err" ? 7000 : 4500);
  }, []);

  const ctx = useMemo(
    () => ({ entity_id: scopeType === "entity" ? scopeId : (selectedEntity || "") }),
    [scopeType, scopeId, selectedEntity]
  );

  /* debounce pencarian supaya tidak memukul API setiap ketikan */
  useEffect(() => {
    const t = window.setTimeout(() => setTerm(q.trim()), 280);
    return () => window.clearTimeout(t);
  }, [q]);

  /* muat katalog grup + peta kesehatan sekali */
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [reg, hp] = await Promise.all([configApi.registry(), configApi.health()]);
        if (!alive) return;
        setGroups(reg.groups || []);
        setCaps(reg.caps || { settings_manage: false, impact_apply: false });
        const map = {};
        (hp.rows || []).forEach((r) => { map[r.key] = r; });
        setHealth(map);
        // Fungsional: `group` di closure ini adalah nilai saat efek DIPASANG.
        // Bila deep-link (`kn-open-config`) sudah menetapkan kelompok tujuan
        // sebelum permintaan registry selesai, pembacaan closure yang basi akan
        // menimpanya dengan kelompok pertama — pengguna mendarat di tempat yang
        // salah. Bentuk fungsional selalu membaca nilai TERBARU.
        if ((reg.groups || []).length) setGroup((cur) => cur || reg.groups[0].id);
      } catch (e) {
        if (alive) setError(errMsg(e, "Gagal memuat katalog pengaturan."));
      }
    })();
    return () => { alive = false; };
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, []);

  /* ── Deep-link dari layar lain (event global `kn-open-config`) ───────────
   * `focusNonce` berubah tiap permintaan sehingga menautkan ke kunci yang SAMA
   * dua kali tetap memicu fokus ulang. Setelah diserap, parent langsung
   * membersihkan state-nya (onFocusConsumed) supaya navigasi biasa ke Pusat
   * Pengaturan tidak "nyangkut" pada kunci lama. */
  const [highlight, setHighlight] = useState("");
  const [pendingScroll, setPendingScroll] = useState("");

  useEffect(() => {
    if (!focusNonce) return;
    const key = focusKey || "";
    const g = focusGroup || groupForKey(key);
    setTab("settings");
    if (g) setGroup(g);
    if (key) {
      setQ(key);
      setTerm(key);            // lewati debounce: hasil harus langsung muncul
      setPendingScroll(key);
      setHighlight(key);
    } else {
      setQ("");
      setTerm("");
      setPendingScroll("");
      setHighlight("");
    }
    if (typeof onFocusConsumed === "function") onFocusConsumed();
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [focusNonce]);

  /* Sorotan visual hanya sementara — supaya tidak mengganggu setelah dibaca. */
  useEffect(() => {
    if (!highlight) return undefined;
    const t = window.setTimeout(() => setHighlight(""), 8000);
    return () => window.clearTimeout(t);
  }, [highlight]);

  const load = useCallback(async () => {
    if (!group && !term) return;
    setLoading(true);
    setError("");
    try {
      const d = await configApi.effective({
        ...(term ? { q: term } : { group }),
        entity_id: ctx.entity_id || "",
      });
      setItems(d.items || []);
      if (d.groups?.length) setGroups(d.groups);
    } catch (e) {
      setError(errMsg(e, "Gagal memuat nilai pengaturan."));
    } finally {
      setLoading(false);
    }
  }, [group, term, ctx.entity_id]);

  useEffect(() => { load(); }, [load]);

  /* scroll ke kartu yang dituju deep-link setelah data siap */
  useEffect(() => {
    if (!pendingScroll || loading) return;
    const el = cardRefs.current[pendingScroll];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setPendingScroll("");
    }
  }, [pendingScroll, loading, items]);

  const onSave = async (payload) => {
    try {
      await configApi.save([payload]);
      flash(
        payload.effective_from
          ? `Tersimpan. Perubahan akan berlaku mulai ${String(payload.effective_from).slice(0, 10)}.`
          : "Tersimpan dan langsung berlaku di mesin."
      );
      await load();
      return true;
    } catch (e) {
      flash(errMsg(e, "Gagal menyimpan."), "err");
      return false;
    }
  };

  const onReset = async (item) => {
    try {
      await configApi.reset({ key: item.key, scope_type: scopeType, scope_id: scopeId });
      flash(`“${item.label}” dikembalikan ke bawaan sistem.`);
      await load();
    } catch (e) {
      flash(errMsg(e, "Gagal mengembalikan ke default."), "err");
    }
  };

  // FASE E-4 (E4.6) — cabut nilai khusus badan usaha → kembali mewarisi nilai global.
  // Sengaja BUKAN `onReset`: reset menulis angka bawaan kode, sedangkan pengguna
  // yang menekan "kembalikan ke global" ingin memakai nilai grup yang berlaku.
  const onClearEntity = async (item) => {
    if (!scopeId) return;
    try {
      const res = await configApi.clear({ key: item.key, scope_type: "entity", scope_id: scopeId });
      flash(`“${item.label}” kembali mengikuti nilai ${res?.source_label_now || "Global"}.`);
      await load();
    } catch (e) {
      flash(errMsg(e, "Gagal mengembalikan ke nilai global."), "err");
    }
  };

  const activeGroup = groups.find((g) => g.id === group);
  // `/api/entities` tak punya `name`/`code` — pakai resolver bersama supaya
  // pemilih entitas tidak menampilkan id teknis (`ent_ksc`).
  const entityOpts = useMemo(() => entityOptions(entities), [entities]);
  // Nama badan usaha untuk pita & kartu (jangan pernah menampilkan id teknis).
  const scopeName = useMemo(
    () => (scopeType === "entity" && scopeId ? entityShortById(entities, scopeId) : "Global"),
    [scopeType, scopeId, entities]);

  const notUsedCount = items.filter((i) => i.status === "not_used").length;
  // Berapa setting yang benar-benar boleh diubah user ini di daftar yang tampil.
  const editableShown = items.filter((i) => i.can_edit !== false).length;

  return (
    <div className="cfg-hub" data-testid="settings-hub">
      <header className="cfg-hub-head">
        <div>
          <p className="cfg-kicker">PENGATURAN & MASTER DATA › PUSAT PENGATURAN</p>
          <h2>Pusat Pengaturan</h2>
          <p className="cfg-sub-lead">
            Semua aturan yang dipakai sistem ada di sini — bisa dicari, dijelaskan, dicoba
            dulu, dijadwalkan, dan dilihat riwayatnya. Tidak perlu developer.
          </p>
        </div>
        <button className="btn-secondary btn-sm" onClick={load} disabled={loading}
          data-testid="cfg-refresh">
          {loading ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />} Muat ulang
        </button>
      </header>

      <nav className="tab-pills cfg-tabs" role="tablist">
        {TABS.filter((t) => t.k !== "impact" || caps.impact_apply).map((t) => (
          <button
            key={t.k}
            role="tab"
            aria-selected={tab === t.k}
            className={`tab-pill ${tab === t.k ? "active" : ""}`}
            onClick={() => setTab(t.k)}
            data-testid={`cfg-tab-${t.k}`}
          >
            <t.icon size={14} /> {t.label}
          </button>
        ))}
      </nav>

      {notice ? (
        <div className={`cfg-notice ${notice.tone}`} data-testid="cfg-notice">
          {notice.tone === "err" ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}
          <span>{notice.msg}</span>
          <button className="icon-button" onClick={() => setNotice(null)} aria-label="Tutup">
            <X size={14} />
          </button>
        </div>
      ) : null}

      {!isAdmin && !caps.settings_manage ? (
        <div className="cfg-notice info" data-testid="cfg-limited-rights">
          <ShieldCheck size={15} />
          <span>
            Anda dapat <b>melihat semua aturan</b> beserta penjelasannya. Yang bisa Anda{" "}
            <b>ubah</b> hanya aturan yang menjadi wewenang peran Anda
            {tab === "settings" && items.length > 0
              ? ` — di daftar ini ${editableShown} dari ${items.length} pengaturan`
              : ""}
            . Sisanya tampil terkunci, bukan disembunyikan, supaya Anda tetap tahu
            aturan apa yang sedang dipakai sistem.
          </span>
        </div>
      ) : null}

      {tab === "settings" ? (
        <>
          <div className="cfg-toolbar">
            <label className="cfg-search-wrap">
              <Search size={15} />
              <input
                className="form-input"
                placeholder="Cari pengaturan… coba “denda”, “toleransi”, “PPN”, “persetujuan”"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                data-testid="cfg-search"
              />
              {q ? (
                <button className="icon-button" onClick={() => setQ("")}
                  aria-label="Kosongkan pencarian" data-testid="cfg-search-clear">
                  <X size={13} />
                </button>
              ) : null}
            </label>

            <div className="cfg-scope-box" data-testid="cfg-scope-box">
              <span className="cfg-scope-caption"><Building2 size={13} /> Berlaku untuk</span>
              <KNSelect
                value={scopeType}
                onValueChange={(v) => { setScopeType(v); if (v === "global") setScopeId(""); }}
                options={[
                  { value: "global", label: SCOPE_LABEL.global },
                  { value: "entity", label: SCOPE_LABEL.entity },
                ]}
                className="field cfg-select-sm"
                data-testid="cfg-scope-type"
              />
              {scopeType === "entity" ? (
                <KNSelect
                  value={scopeId}
                  onValueChange={setScopeId}
                  options={entityOpts}
                  className="field cfg-select-sm"
                  placeholder="Pilih entitas…"
                  data-testid="cfg-scope-entity"
                />
              ) : null}
            </div>
          </div>

          {/* FASE E-4 (E4.6) — pita konteks: nilai SIAPA yang sedang diubah */}
          <div data-testid="cfg-scope-ribbon"
            className={`cfg-scope-ribbon ${scopeType === "entity" ? "is-entity" : "is-global"}`}>
            {scopeType === "entity" ? <Building2 size={13} /> : <Globe2 size={13} />}
            <span>
              {scopeType === "entity" && scopeId ? (
                <>Anda sedang mengubah <b>{scopeName}</b>. Perubahan hanya berlaku untuk badan
                  usaha ini; nilai berlencana <b>Global</b> masih diwarisi dari grup.</>
              ) : scopeType === "entity" ? (
                <>Pilih badan usaha dulu supaya perubahan tersimpan pada badan usaha yang benar.</>
              ) : (
                <>Anda sedang mengubah nilai <b>Global</b> — berlaku untuk <b>semua</b> badan
                  usaha yang belum punya nilai sendiri.</>
              )}
            </span>
          </div>

          {scopeType === "entity" && !scopeId ? (
            <p className="cfg-scope-warn" data-testid="cfg-scope-need-entity">
              Pilih entitas dulu supaya perubahan tersimpan pada entitas yang benar.
              Nilai di bawah masih menampilkan nilai global.
            </p>
          ) : null}

          <div className="cfg-body">
            <aside className="cfg-groupnav" data-testid="cfg-group-nav">
              <h4>Kelompok</h4>
              {groups.map((g) => (
                <button
                  key={g.id}
                  className={`cfg-group-btn ${group === g.id && !term ? "active" : ""}`}
                  onClick={() => { setGroup(g.id); setQ(""); }}
                  data-testid={`cfg-group-${g.id}`}
                  title={g.question}
                >
                  <span className="cfg-group-label">{g.label}</span>
                  <span className="cfg-group-count">{g.count}</span>
                  <ChevronRight size={13} />
                </button>
              ))}
            </aside>

            <section className="cfg-list">
              <ErrorNotice message={error} onRetry={load} />

              {term ? (
                <div className="cfg-result-head" data-testid="cfg-search-result-head">
                  <h3>Hasil pencarian “{term}”</h3>
                  <p>
                    {items.length} pengaturan cocok — dari seluruh kelompok.{" "}
                    <button className="cfg-link-btn" onClick={() => setQ("")}
                      data-testid="cfg-back-to-group">
                      Kembali ke kelompok
                    </button>
                  </p>
                </div>
              ) : activeGroup ? (
                <div className="cfg-result-head" data-testid="cfg-group-head">
                  <h3>{activeGroup.label}</h3>
                  <p className="cfg-question">
                    Kelompok ini menjawab: <b>{activeGroup.question}</b>
                  </p>
                  <p className="cfg-hint-sm">
                    {activeGroup.count} pengaturan
                    {notUsedCount ? ` · ${notUsedCount} ditandai tidak dipakai` : ""}
                  </p>
                </div>
              ) : null}

              {loading ? <p className="cfg-hint">Memuat pengaturan…</p> : null}

              {!loading && items.length === 0 ? (
                <p className="cfg-empty" data-testid="cfg-empty">
                  {term
                    ? `Tidak ada pengaturan yang cocok dengan “${term}”. Coba kata lain, mis. “denda”, “PPN”, “lot”.`
                    : "Belum ada pengaturan di kelompok ini."}
                </p>
              ) : null}

              <div className="cfg-cards">
                {items.map((item) => (
                  // Pembungkus fokus deep-link. `data-testid` SENGAJA berbeda dari
                  // kartunya (`cfg-card-<key>` ada di <article> SettingCard): dua
                  // elemen ber-testid identik membuat automasi gagal ("resolved to
                  // 2 elements") sehingga kartunya seolah tidak ada saat diuji.
                  <div
                    key={item.key}
                    ref={(el) => { cardRefs.current[item.key] = el; }}
                    className={highlight === item.key ? "cfg-card-focus" : ""}
                    data-testid={`cfg-card-wrap-${item.key}`}
                    data-focused={highlight === item.key ? "1" : "0"}
                  >
                    <SettingCard
                      item={item}
                      scopeType={scopeType}
                      scopeId={scopeId}
                      scopeLabel={scopeName}
                      wiring={health[item.key]}
                      canEdit={item.can_edit !== false}
                      onSave={onSave}
                      onReset={onReset}
                      onClearEntity={onClearEntity}
                      onWhy={(it) => setWhy(it)}
                      onSimulate={(it, draft) => setSim({ entry: it, draft })}
                      onHistory={(it) => setHist({ entry: it })}
                    />
                  </div>
                ))}
              </div>
            </section>
          </div>
        </>
      ) : null}

      {tab === "health" ? (
        <ConfigHealthPanel
          onOpenSetting={(row) => {
            setTab("settings");
            setGroup(row.group);
            setQ(row.key);
          }}
        />
      ) : null}

      {tab === "history" ? (
        <section className="cfg-history-tab" data-testid="cfg-history-tab">
          <p className="cfg-hint">
            Seluruh perubahan konfigurasi, terbaru dulu. Data bersifat <b>append-only</b>:
            nilai lama tidak pernah ditimpa sehingga selalu bisa ditelusuri dan dipulihkan.
          </p>
          <button className="btn-primary btn-sm" onClick={() => setHist({})}
            data-testid="cfg-open-all-history">
            <History size={14} /> Buka riwayat lengkap
          </button>
          <ChangeHistoryInline />
        </section>
      ) : null}

      {tab === "impact" ? (
        <ImpactPicker selectedEntity={selectedEntity} canApply={!!caps.impact_apply} />
      ) : null}

      {why ? <WhyThisValueDrawer entry={why} ctx={ctx} onClose={() => setWhy(null)} /> : null}
      {sim ? (
        <SimulatorPanel entry={sim.entry} ctx={ctx} draftValue={sim.draft}
          onClose={() => setSim(null)} />
      ) : null}
      {hist ? (
        <ChangeHistoryDrawer entry={hist.entry} onClose={() => setHist(null)} />
      ) : null}
    </div>
  );
}

