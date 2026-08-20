/**
 * WarehouseModeDrawer (FASE E-4 · E4.1) — mengatur SIAPA yang boleh memakai gudang.
 *
 * Keputusan pemilik #3: gudang boleh **Bersama** (semua badan usaha) atau
 * **Khusus** (hanya badan usaha yang dipilih).
 *
 * Layar ini sengaja menampilkan **isi gudang per badan usaha** SEBELUM pengguna
 * menekan simpan. Alasannya nyata: menjadikan gudang “khusus” sementara di dalamnya
 * masih ada 18 roll milik badan usaha lain akan MENGURUNG barang itu — server
 * menolak (409) dan drawer ini menjelaskan sebabnya dengan angka, bukan sekadar
 * “gagal menyimpan”. Tombol pintas “Sertakan pemilik stok” menyelesaikannya
 * dalam satu klik.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  X, Save, Users, Building2, AlertTriangle, Boxes, Loader2, Check,
} from "lucide-react";

import ErrorNotice from "../../../components/ErrorNotice";
import { entityFull, entityShort } from "../../../utils/entityLabel";
import { formatQty } from "../../../utils/formatters";
import { errText, patchWarehouse, warehouseOccupancy } from "./warehouseApi";

export default function WarehouseModeDrawer({ warehouse, entities = [], onClose, onSaved }) {
  const [mode, setMode] = useState(warehouse.sharing_mode === "dedicated" ? "dedicated" : "shared");
  const [picked, setPicked] = useState(warehouse.entity_ids || []);
  const [occupancy, setOccupancy] = useState(null);
  const [loadingOcc, setLoadingOcc] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const activeEntities = useMemo(
    () => (entities || []).filter((e) => e && e.status !== "archived" && e.status !== "inactive"),
    [entities]
  );

  const loadOccupancy = useCallback(async () => {
    setLoadingOcc(true);
    try {
      setOccupancy(await warehouseOccupancy(warehouse.id));
    } catch (e) {
      setError(errText(e, "Gagal membaca isi gudang."));
    } finally {
      setLoadingOcc(false);
    }
  }, [warehouse.id]);

  useEffect(() => { loadOccupancy(); }, [loadOccupancy]);

  const owners = occupancy?.owners || [];
  // Pemilik stok yang AKAN terkurung bila mode disimpan seperti sekarang.
  const stranded = mode === "dedicated"
    ? owners.filter((o) => o.entity_id && !picked.includes(o.entity_id))
    : [];

  const toggle = (id) =>
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const includeStranded = () =>
    setPicked((prev) => Array.from(new Set([...prev, ...stranded.map((o) => o.entity_id)])));

  const save = async () => {
    setError("");
    if (mode === "dedicated" && picked.length === 0) {
      setError("Gudang khusus wajib memilih minimal satu badan usaha.");
      return;
    }
    setSaving(true);
    try {
      const updated = await patchWarehouse(warehouse.id, {
        sharing_mode: mode,
        entity_ids: mode === "dedicated" ? picked : [],
      });
      onSaved(updated, mode === "shared"
        ? `${warehouse.name} sekarang bisa dipakai semua badan usaha.`
        : `${warehouse.name} sekarang khusus ${picked.map((id) => entityShort(activeEntities.find((e) => e.id === id))).join(", ")}.`);
    } catch (e) {
      setError(errText(e, "Gagal menyimpan mode gudang."));
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" data-testid="wh-mode-drawer">
      <div className="h-full w-full max-w-[520px] overflow-auto bg-white shadow-xl">
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-[#EFF0F2] bg-white px-4 py-3">
          <Building2 size={16} className="text-[#0058CC]" />
          <div className="min-w-0">
            <h3 className="truncate text-[14px] font-bold">Mode pemakaian · {warehouse.name}</h3>
            <p className="text-[11px] text-[#8E8E93]">{warehouse.code} · {warehouse.city}</p>
          </div>
          <button data-testid="wh-mode-close" className="icon-button ml-auto" onClick={onClose} aria-label="Tutup">
            <X size={15} />
          </button>
        </div>

        <div className="space-y-3 p-4">
          <ErrorNotice message={error} onDismiss={() => setError("")} testId="wh-mode-error" />

          {/* Pilihan mode */}
          <div className="grid gap-2">
            <ModeOption
              testId="wh-mode-shared"
              active={mode === "shared"}
              icon={Users}
              title="Bersama semua badan usaha"
              desc="Semua badan usaha boleh menerima, menyimpan, dan mengirim barang dari gudang ini."
              onClick={() => setMode("shared")}
            />
            <ModeOption
              testId="wh-mode-dedicated"
              active={mode === "dedicated"}
              icon={Building2}
              title="Khusus badan usaha tertentu"
              desc="Hanya badan usaha yang dipilih di bawah yang melihat & memakai gudang ini."
              onClick={() => setMode("dedicated")}
            />
          </div>

          {mode === "dedicated" && (
            <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5" data-testid="wh-mode-entity-picker">
              <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">
                Badan usaha yang boleh memakai
              </p>
              <div className="grid gap-1.5">
                {activeEntities.map((e) => {
                  const on = picked.includes(e.id);
                  const holder = owners.find((o) => o.entity_id === e.id);
                  return (
                    <button
                      key={e.id}
                      type="button"
                      data-testid={`wh-mode-entity-${e.id}`}
                      onClick={() => toggle(e.id)}
                      className={`flex items-center gap-2 rounded-md border px-2.5 py-2 text-left text-[12px] transition-colors ${
                        on ? "border-[#0058CC] bg-[#EAF2FF]" : "border-[#E5E5EA] bg-white hover:border-[#0058CC]"
                      }`}
                    >
                      <span className={`flex h-4 w-4 items-center justify-center rounded border ${
                        on ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#C7C7CC]"}`}>
                        {on && <Check size={11} />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-semibold text-[#1C1C1E]">{entityFull(e)}</span>
                        {holder && (
                          <span className="text-[10px] text-[#8E8E93]">
                            punya {holder.rolls} roll di gudang ini
                          </span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Isi gudang — fakta sebelum memutuskan */}
          <div className="rounded-md border border-[#EFF0F2] p-2.5" data-testid="wh-occupancy-panel">
            <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">
              <Boxes size={12} /> Isi gudang sekarang
            </p>
            {loadingOcc ? (
              <p className="flex items-center gap-1.5 text-[11.5px] text-[#8E8E93]">
                <Loader2 size={12} className="animate-spin" /> Menghitung…
              </p>
            ) : owners.length === 0 ? (
              <p data-testid="wh-occupancy-empty" className="text-[11.5px] text-[#8E8E93]">
                Gudang ini kosong — mode pemakaiannya bisa diubah tanpa risiko.
              </p>
            ) : (
              <div className="grid gap-1">
                {owners.map((o) => (
                  <div key={o.entity_id || "none"} data-testid={`wh-occupancy-${o.entity_id}`}
                    className="flex items-center justify-between rounded bg-[#FAFBFC] px-2 py-1.5 text-[11.5px]">
                    <span className="font-semibold text-[#1C1C1E]">{o.entity_name}</span>
                    <span className="tabular-nums text-[#6B6B73]">
                      {o.rolls} roll · {formatQty(o.qty)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {stranded.length > 0 && (
            <div data-testid="wh-mode-warning"
              className="rounded-md border border-[#F5C97B] bg-[#FFF7E6] p-2.5 text-[11.5px] text-[#8C4A00]">
              <p className="flex items-center gap-1.5 font-bold">
                <AlertTriangle size={13} /> Barang ini akan terkurung
              </p>
              <p className="mt-1">
                {stranded.map((o) => `${o.rolls} roll milik ${o.entity_name}`).join(" dan ")}{" "}
                ada di gudang ini. Kalau disimpan sebagai khusus, pemiliknya tidak bisa lagi
                kirim atau terima dari sini — server akan menolak.
              </p>
              <button data-testid="wh-mode-include-owners" className="secondary-button mt-2 text-[11px]"
                onClick={includeStranded}>
                Sertakan pemilik stok tersebut
              </button>
            </div>
          )}
        </div>

        <div className="sticky bottom-0 flex justify-end gap-2 border-t border-[#EFF0F2] bg-white px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button data-testid="wh-mode-save" className="primary-button" onClick={save} disabled={saving}>
            <Save size={14} /> {saving ? "Menyimpan…" : "Simpan mode"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ModeOption({ active, icon: Icon, title, desc, onClick, testId }) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className={`flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-left transition-colors ${
        active ? "border-[#0058CC] bg-[#EAF2FF]" : "border-[#E5E5EA] bg-white hover:border-[#0058CC]"
      }`}
    >
      <span className={`mt-0.5 flex h-7 w-7 items-center justify-center rounded-lg ${
        active ? "bg-[#0058CC] text-white" : "bg-[#F5F5F7] text-[#6B6B73]"}`}>
        <Icon size={15} />
      </span>
      <span className="min-w-0">
        <span className="block text-[12.5px] font-bold text-[#1C1C1E]">{title}</span>
        <span className="block text-[11px] leading-snug text-[#6B6B73]">{desc}</span>
      </span>
    </button>
  );
}
