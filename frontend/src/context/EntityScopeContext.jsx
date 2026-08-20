/**
 * EntityScopeContext (FASE E-3 · user story 7) — konteks badan usaha aktif untuk
 * SELURUH layar, tanpa harus menurunkan prop lewat 50 komponen.
 *
 * Dipakai untuk satu pertanyaan yang muncul di mana-mana:
 *   "Boleh saya menyimpan sesuatu sekarang?"
 *
 * Jawabannya TIDAK bila pengguna sedang di mode "Semua Entitas" (gabungan),
 * karena sistem tidak tahu buku badan usaha mana yang harus menerima dokumennya.
 * Server menegakkan aturan yang sama di `entity_write_guard.py` — layar hanya
 * membuatnya terlihat lebih awal (tombol mati + alasannya di tooltip).
 */
import { createContext, useContext, useMemo } from "react";

import { canWriteInScope, WRITE_BLOCK_HINT } from "../utils/writeScope";

const EntityScopeContext = createContext({
  selectedEntity: "all",
  entities: [],
  canWrite: true,
  writeBlockHint: "",
  pickEntity: () => {},
});

export function EntityScopeProvider({ selectedEntity, entities, canSwitch, pickEntity, children }) {
  const value = useMemo(() => {
    // Pengguna yang terkunci di satu badan usaha tidak pernah berada di mode
    // gabungan — jangan pernah mematikan tombolnya karena alasan ini.
    const canWrite = canSwitch === false ? true : canWriteInScope(selectedEntity);
    return {
      selectedEntity: selectedEntity || "all",
      entities: entities || [],
      canWrite,
      writeBlockHint: canWrite ? "" : WRITE_BLOCK_HINT,
      pickEntity: pickEntity || (() => {}),
    };
  }, [selectedEntity, entities, canSwitch, pickEntity]);

  return (
    <EntityScopeContext.Provider value={value}>{children}</EntityScopeContext.Provider>
  );
}

export const useEntityScope = () => useContext(EntityScopeContext);

export default EntityScopeContext;
