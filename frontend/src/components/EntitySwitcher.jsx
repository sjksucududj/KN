import { Building2, ChevronDown, Check, Star, Eye, Search } from "lucide-react";
import { useState, useRef, useEffect, useMemo } from "react";

import { roleLabel } from "../config/roles";
import { entityShort, entityFull } from "../utils/entityLabel";

/**
 * EntitySwitcher — pemilih badan usaha aktif (FASE E-3).
 *
 * Yang dijamin layar ini (semuanya cacat nyata yang pernah terjadi):
 *  1. **Hanya badan usaha aktif & yang diizinkan** yang bisa dipilih. Dulu badan
 *     usaha terarsip ikut muncul, dipilih, lalu tulisnya gagal jauh di belakang.
 *  2. **Badan usaha utama (home) ditandai** bintang + label "Utama" supaya staf
 *     lintas-PT tahu mana tempat kerja bawaannya.
 *  3. **Pencarian muncul otomatis bila > 8 badan usaha** — daftar puluhan entitas
 *     tidak boleh memaksa mata menyapu satu-satu.
 *  4. **"Semua Entitas" diberi label jujur: "hanya lihat"**. Mode itu tidak bisa
 *     membuat dokumen (dijaga `entity_write_guard.py` di server), jadi labelnya
 *     harus mengatakannya SEBELUM pengguna mencoba menyimpan.
 */
const SEARCH_THRESHOLD = 8;

export default function EntitySwitcher({ entities = [], value = "all", onChange,
  canSwitch = true, role = "", homeEntityId = "" }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef(null);

  // FASE E-8 — label peran dari REGISTRY (`config/roles.js`), bukan peta lokal.
  // Peta lama hanya memuat 4 peran, jadi peran baru jatuh ke pembesaran huruf
  // pertama dan pengguna melihat id teknis setengah jadi: "Sales_admin".
  const roleTag = roleLabel(role);

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  useEffect(() => { if (!open) setQ(""); }, [open]);

  // E1.5 — badan usaha terarsip TIDAK boleh bisa dipilih (server pun menolaknya 403).
  const selectable = useMemo(
    () => (entities || []).filter((e) => e && e.status !== "archived" && !e.write_locked),
    [entities]
  );
  const active = selectable.find((e) => e.id === value) || entities.find((e) => e.id === value);

  // User terkunci 1 badan usaha (sales/gudang — silo): tampilkan badge statis.
  if (!canSwitch) {
    const only = active || selectable[0] || entities[0];
    const lockLabel = entityShort(only, "Badan usaha");
    return (
      <div className="entity-switcher" data-testid="entity-switcher-locked">
        <div className="entity-switcher-trigger" title={`Anda di ${lockLabel}${roleTag ? ` sebagai ${roleTag}` : ""} (terkunci)`} style={{ cursor: "default" }}>
          <Building2 size={14} />
          <span className="entity-switcher-label">{lockLabel}</span>
          {roleTag && <><span className="entity-switcher-sep" aria-hidden="true">·</span><span className="entity-switcher-role" data-testid="entity-role-tag">{roleTag}</span></>}
        </div>
      </div>
    );
  }

  const viewAll = value === "all";
  const label = viewAll ? "Semua Entitas" : entityShort(active, "Badan usaha");

  const term = q.trim().toLowerCase();
  const filtered = term
    ? selectable.filter((e) =>
      `${e.legal_name || ""} ${e.short_name || ""} ${e.doc_prefix || ""} ${e.city || ""}`
        .toLowerCase().includes(term))
    : selectable;
  const showSearch = selectable.length > SEARCH_THRESHOLD;

  return (
    <div className="entity-switcher" ref={ref}>
      <button
        type="button"
        data-testid="entity-switcher"
        className={`entity-switcher-trigger${viewAll ? " entity-switcher-readonly" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={viewAll
          ? "Mode gabungan: hanya untuk melihat. Pilih satu badan usaha untuk membuat data."
          : "Pilih badan usaha aktif"}
      >
        {viewAll ? <Eye size={14} /> : <Building2 size={14} />}
        <span className="entity-switcher-label">{label}</span>
        {viewAll && <span className="entity-switcher-ro-tag" data-testid="entity-switcher-readonly-tag">hanya lihat</span>}
        {roleTag && <><span className="entity-switcher-sep" aria-hidden="true">·</span><span className="entity-switcher-role" data-testid="entity-role-tag">{roleTag}</span></>}
        <ChevronDown size={13} className={open ? "rotate-180 transition-transform" : "transition-transform"} />
      </button>
      {open && (
        <div className="entity-switcher-menu" role="listbox" data-testid="entity-switcher-menu">
          {showSearch && (
            <div className="entity-switcher-search">
              <Search size={12} className="shrink-0 text-[#9A9BA3]" />
              <input
                data-testid="entity-switcher-search"
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={`Cari di ${selectable.length} badan usaha…`}
              />
            </div>
          )}

          <button
            type="button"
            role="option"
            aria-selected={viewAll}
            data-testid="entity-option-all"
            className={`entity-switcher-item ${viewAll ? "active" : ""}`}
            onClick={() => { onChange?.("all"); setOpen(false); }}
          >
            <span className="flex items-center gap-2 min-w-0">
              <Eye size={13} className="shrink-0" />
              <span className="truncate">
                Semua Entitas
                <span className="entity-tag entity-tag-ro">hanya lihat</span>
              </span>
            </span>
            {viewAll && <Check size={14} className="shrink-0 text-[#007AFF]" />}
          </button>

          {filtered.length === 0 && (
            <p className="entity-switcher-empty" data-testid="entity-switcher-empty">
              Tidak ada badan usaha yang cocok.
            </p>
          )}

          {filtered.map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="option"
              aria-selected={value === opt.id}
              data-testid={`entity-option-${opt.id}`}
              className={`entity-switcher-item ${value === opt.id ? "active" : ""}`}
              onClick={() => { onChange?.(opt.id); setOpen(false); }}
            >
              <span className="flex items-center gap-2 min-w-0">
                <Building2 size={13} className="shrink-0" />
                <span className="truncate">
                  {entityFull(opt)}
                  {opt.type ? <span className="entity-tag">{opt.type}</span> : null}
                  {(opt.is_home || opt.id === homeEntityId) && (
                    <span className="entity-tag entity-tag-home" data-testid={`entity-home-tag-${opt.id}`}>
                      <Star size={8} /> Utama
                    </span>
                  )}
                </span>
              </span>
              {value === opt.id && <Check size={14} className="shrink-0 text-[#007AFF]" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
