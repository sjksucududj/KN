import { useMemo } from "react";
import { SlidersHorizontal, RotateCcw, Building2 } from "lucide-react";
import KNSelect from "../../components/KNSelect";

export const DEFAULT_FACETS = {
  categories: [], grades: [], colors: [],
  priceMin: "", priceMax: "", availability: "all", sort: "relevance",
};

const SORT_OPTIONS = [
  { value: "relevance", label: "Relevansi" },
  { value: "price_asc", label: "Harga ↑" },
  { value: "price_desc", label: "Harga ↓" },
  { value: "avail_desc", label: "Ketersediaan ↓" },
  { value: "name_asc", label: "Nama A-Z" },
];

const AVAIL_OPTIONS = [
  { value: "all", label: "Semua" },
  { value: "available", label: "Tersedia (ATP > 0)" },
  { value: "low", label: "Stok rendah" },
];

function uniq(arr) { return [...new Set(arr.filter(Boolean))].sort(); }

/** EPIC5 — facet rail Discover: Kategori/Grade/Warna/Harga/Ketersediaan/Entitas + sort. */
export function FacetRail({ products = [], facets, setFacets, selectedEntity = "all", entityName, loading = false }) {
  const opts = useMemo(() => ({
    categories: uniq(products.map((p) => p.category)),
    grades: uniq(products.map((p) => p.grade)),
    colors: uniq(products.map((p) => p.color)),
    colorHex: products.reduce((m, p) => { if (p.color && p.color_hex && !m[p.color]) m[p.color] = p.color_hex; return m; }, {}),
  }), [products]);

  const toggle = (key, val) => setFacets((f) => {
    const set = new Set(f[key]);
    set.has(val) ? set.delete(val) : set.add(val);
    return { ...f, [key]: [...set] };
  });

  const activeCount = facets.categories.length + facets.grades.length + facets.colors.length
    + (facets.priceMin ? 1 : 0) + (facets.priceMax ? 1 : 0) + (facets.availability !== "all" ? 1 : 0);

  return (
    <aside data-testid="facet-rail" className="section-card self-start lg:sticky lg:top-4 lg:max-h-[calc(100vh-5.5rem)] lg:!overflow-y-auto">
      <div className="section-head">
        <div className="flex items-center gap-2"><SlidersHorizontal size={14} className="text-[#0058CC]" /><h2 className="text-[13px]">Filter</h2></div>
        {activeCount > 0 && (
          <button data-testid="facet-reset" className="ml-auto inline-flex items-center gap-1 text-[11px] font-semibold text-[#0058CC]" onClick={() => setFacets(DEFAULT_FACETS)}>
            <RotateCcw size={12} /> Reset ({activeCount})
          </button>
        )}
      </div>
      <div className="section-body space-y-3">
        {loading && <p data-testid="facet-loading" className="animate-pulse text-[11px] text-[#6B6B73]">Memuat opsi filter…</p>}
        <div>
          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Urutkan</label>
          <KNSelect data-testid="facet-sort" className="field" value={facets.sort} onValueChange={(v) => setFacets((f) => ({ ...f, sort: v }))} options={SORT_OPTIONS} />
        </div>

        <FacetGroup label="Kategori" testid="facet-categories">
          <Chips options={opts.categories} selected={facets.categories} onToggle={(v) => toggle("categories", v)} group="category" />
        </FacetGroup>

        <FacetGroup label="Grade" testid="facet-grades">
          <Chips options={opts.grades} selected={facets.grades} onToggle={(v) => toggle("grades", v)} group="grade" />
        </FacetGroup>

        <FacetGroup label="Warna" testid="facet-colors">
          <Chips options={opts.colors} selected={facets.colors} onToggle={(v) => toggle("colors", v)} group="color" hexMap={opts.colorHex} />
        </FacetGroup>

        <div>
          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Rentang Harga (Rp)</label>
          <div className="grid grid-cols-2 gap-2">
            <input data-testid="facet-price-min" type="number" min="0" className="field" placeholder="Min" value={facets.priceMin} onChange={(e) => setFacets((f) => ({ ...f, priceMin: e.target.value }))} />
            <input data-testid="facet-price-max" type="number" min="0" className="field" placeholder="Max" value={facets.priceMax} onChange={(e) => setFacets((f) => ({ ...f, priceMax: e.target.value }))} />
          </div>
        </div>

        <div>
          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Ketersediaan</label>
          <KNSelect data-testid="facet-availability" className="field" value={facets.availability} onValueChange={(v) => setFacets((f) => ({ ...f, availability: v }))} options={AVAIL_OPTIONS} />
        </div>

        <div data-testid="facet-entity" className="rounded-md border border-[#E5E5EA] bg-[#FAFBFC] p-2">
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]"><Building2 size={12} /> Entitas</div>
          <p className="mt-1 text-[12px] font-semibold text-[#1C1C1E]" data-testid="facet-entity-name">
            {selectedEntity === "all" ? "Semua entitas" : (entityName || "Entitas aktif")}
          </p>
          <p className="text-[10px] text-[#9A9BA3]">Ketersediaan dihitung per entitas aktif (ubah via pemilih entitas di header).</p>
        </div>
      </div>
    </aside>
  );
}

function FacetGroup({ label, testid, children }) {
  return (
    <div data-testid={testid}>
      <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">{label}</label>
      {children}
    </div>
  );
}

function Chips({ options, selected, onToggle, group, hexMap = {} }) {
  // FASE P5 — dulu hanya "—": pengguna tidak tahu apakah penyaring ini memang kosong
  // untuk katalog saat ini, atau datanya gagal dimuat.
  if (!options.length) {
    return (
      <p className="text-[11px] text-[#9A9BA3]" data-testid={`facet-empty-${group}`}>
        Tidak ada pilihan untuk katalog ini.
      </p>
    );
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = selected.includes(o);
        const hex = group === "color" ? hexMap[o] : null;
        return (
          <button key={o} data-testid={`facet-${group}-${o}`} onClick={() => onToggle(o)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${on ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>
            {hex && <span className="h-3 w-3 rounded-full border border-black/10" style={{ backgroundColor: hex }} />}
            {o}
          </button>
        );
      })}
    </div>
  );
}
