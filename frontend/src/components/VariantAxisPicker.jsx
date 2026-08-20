/**
 * VariantAxisPicker (M0) — POS: pisahkan pemilihan varian jadi DUA sumbu:
 *   (1) Warna  → baris swatch warna
 *   (2) Grade  → chip grade
 * Kombinasi terpilih di-resolve ke 1 SKU konkret via resolveVariant().
 * Dipakai desktop (ProductQuickView) & mobile (MobileQuickView).
 */
import { useMemo } from "react";
import { Palette, Award } from "lucide-react";
import { formatQty } from "../utils/formatters";
import { deriveAxisOptions, resolveVariant, colorKeyOf, gradesForColor } from "../utils/variants";

export default function VariantAxisPicker({ variants = [], selectedId, onSelect, testIdPrefix = "axis" }) {
  const { colors, grades, hasColor, hasGrade } = useMemo(() => deriveAxisOptions(variants), [variants]);
  const selected = useMemo(
    () => variants.find((v) => v.id === selectedId) || variants[0] || null, [variants, selectedId]);

  if (!selected || (!hasColor && !hasGrade)) return null;

  const selColorKey = colorKeyOf(selected);
  const selGradeKey = (selected.grade || "").toString();
  const availGrades = gradesForColor(variants, selColorKey);

  const availForColor = (ck) =>
    variants.filter((v) => colorKeyOf(v) === ck).reduce((s, v) => s + Number(v.available_qty || 0), 0);

  const pick = (v) => v && onSelect?.(v);

  return (
    <div className="space-y-2.5" data-testid={`${testIdPrefix}-picker`}>
      {hasColor && (
        <div>
          <label className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
            <Palette size={11} /> Warna
          </label>
          <div className="flex flex-wrap gap-2" data-testid={`${testIdPrefix}-color-list`}>
            {colors.map((c) => {
              const active = c.key === selColorKey;
              const stock = availForColor(c.key);
              return (
                <button key={c.key} type="button" data-testid={`${testIdPrefix}-color-${c.key}`}
                  onClick={() => pick(resolveVariant(variants, c.key, selGradeKey))}
                  title={`${c.label}${stock <= 0 ? " · habis" : ""}`}
                  className={`flex items-center gap-1.5 rounded-full border py-1 pl-1 pr-2.5 transition ${active ? "border-[#0058CC] bg-[#EAF2FF] ring-1 ring-[#0058CC]" : "border-[#E5E5EA] bg-white hover:border-[#9A9BA3]"}`}>
                  <span className="h-5 w-5 shrink-0 rounded-full border border-[#E5E5EA]"
                    style={{ backgroundColor: c.hex || "#F5F5F7" }} />
                  <span className={`text-[11.5px] font-semibold ${stock <= 0 ? "text-[#A8221A]" : "text-[#1C1C1E]"}`}>{c.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {hasGrade && (
        <div>
          <label className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
            <Award size={11} /> Grade
          </label>
          <div className="flex flex-wrap gap-2" data-testid={`${testIdPrefix}-grade-list`}>
            {grades.map((g) => {
              const active = g.key === selGradeKey;
              const disabled = !availGrades.has(g.key);
              return (
                <button key={g.key} type="button" data-testid={`${testIdPrefix}-grade-${g.key}`} disabled={disabled}
                  onClick={() => pick(resolveVariant(variants, selColorKey, g.key))}
                  className={`rounded-md border px-3 py-1.5 text-[12px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-35 ${active ? "border-[#0058CC] bg-[#EAF2FF] text-[#0058CC]" : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#9A9BA3]"}`}>
                  Grade {g.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <p className="text-[10.5px] text-[#8E8E93]" data-testid={`${testIdPrefix}-resolved`}>
        Terpilih: <span className="font-semibold text-[#0058CC]">{selected.sku}</span> · Stok {formatQty(selected.available_qty || 0)} {selected.base_unit || "meter"}
      </p>
    </div>
  );
}
