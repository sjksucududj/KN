import { Building2 } from "lucide-react";

/**
 * EntityBadge (Multi-Entity F0-B+) — pill berwarna konsisten per entitas legal.
 * Membantu staf yang menangani >1 PT agar tak salah konteks dokumen.
 * Warna dipetakan deterministik dari entityId; label = short_name/code entitas.
 */
const PALETTE = [
  { bg: "#E8F0FE", fg: "#1A56DB", dot: "#1A56DB" }, // blue
  { bg: "#E6F6EC", fg: "#0E7C3A", dot: "#0E7C3A" }, // green
  { bg: "#FBEAEA", fg: "#B42318", dot: "#B42318" }, // red
  { bg: "#FDF1E3", fg: "#B25E09", dot: "#B25E09" }, // amber
  { bg: "#F0EAFB", fg: "#6B2FB3", dot: "#6B2FB3" }, // purple
  { bg: "#E6F4F6", fg: "#0C6E7A", dot: "#0C6E7A" }, // teal
];

function colorFor(id) {
  if (!id) return PALETTE[0];
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

function resolveEntities(entities) {
  if (entities && entities.length) return entities;
  try {
    return JSON.parse(localStorage.getItem("kn_entity_ctx") || "null")?.entities || [];
  } catch {
    return [];
  }
}

export default function EntityBadge({ entityId, entities, size = "sm" }) {
  if (!entityId) return null;
  if (entityId === "all") {
    return (
      <span className={`entity-badge entity-badge-${size} entity-badge-group`} data-testid="entity-badge-all">
        <Building2 size={10} /> Grup
      </span>
    );
  }
  const list = resolveEntities(entities);
  const e = list.find((x) => x.id === entityId);
  const label = e?.short_name || e?.code || e?.name || entityId;
  const c = colorFor(entityId);
  return (
    <span
      className={`entity-badge entity-badge-${size}`}
      data-testid={`entity-badge-${entityId}`}
      title={e?.name || label}
      style={{ background: c.bg, color: c.fg }}
    >
      <span className="entity-badge-dot" style={{ background: c.dot }} />
      {label}
    </span>
  );
}
