/**
 * LotDetailPanel (FASE C · D-10) — panel detail lot dengan 4 tab:
 * Ringkasan (identitas + status + aksi) · Roll · Silsilah · Recall.
 * Dipisah dari view utama agar tiap file di bawah batas guardrail (<500 baris).
 */
import { useEffect, useState } from "react";
import { AlertTriangle, GitBranch, Layers3, Printer, RefreshCw, Save, Scissors,
         Merge, Repeat, ShieldCheck, X } from "lucide-react";
import { formatQty } from "../../../utils/formatters";
import LotGenealogyTree from "./LotGenealogyTree";
import LotRecallPanel from "./LotRecallPanel";
import { LotSourcePill, LotStatusPill } from "./LotParts";
import { shortDateTime } from "./lotApi";

const TABS = [
  { id: "ringkasan", label: "Ringkasan" },
  { id: "rolls", label: "Roll" },
  { id: "silsilah", label: "Silsilah" },
  { id: "recall", label: "Recall" },
];

export default function LotDetailPanel({
  lot, loading, genealogy, genealogyLoading, recall, recallLoading,
  tab, setTab, onClose, onRefresh, onOpenLot, canEdit, labelOf,
  onSaveIdentity, onSplit, onMerge, onRework, onStatus, onLabel, savingIdentity, saveMsg,
}) {
  const [draft, setDraft] = useState({ supplier_lot: "", dye_lot: "", shade_ref: "", note: "" });

  useEffect(() => {
    setDraft({
      supplier_lot: lot?.supplier_lot || "", dye_lot: lot?.dye_lot || "",
      shade_ref: lot?.shade_ref || "", note: lot?.note || "",
    });
  }, [lot?.id, lot?.supplier_lot, lot?.dye_lot, lot?.shade_ref, lot?.note]);

  if (!lot) return null;
  const rolls = lot.rolls || [];
  const warnings = lot.warnings || [];

  return (
    <div data-testid="lot-detail-panel" className="rounded-md border border-[#0058CC]/25 bg-white shadow-[0_6px_20px_rgba(20,28,45,0.08)]">
      {/* Kepala */}
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[#EFF0F2] bg-[#F7FAFF] px-2.5 py-2">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[13px] font-bold text-[#1C1C1E]">
            <Layers3 size={14} className="text-[#0058CC]" /> {lot.lot_number}
            <LotStatusPill value={lot.lot_status} label={labelOf("lot_status", lot.lot_status)}
              testId="lot-detail-status" />
            <LotSourcePill value={lot.source} label={labelOf("lot_source", lot.source)} />
          </p>
          <p className="text-[10.5px] text-[#6B6B73]">
            {lot.sku} · {lot.product_name} · {labelOf("stage", lot.stage)} ·{" "}
            {labelOf("fabric_type", lot.fabric_type)} · {lot.roll_count} roll ·{" "}
            sisa <b>{formatQty(lot.qty_remaining)} {lot.unit}</b>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button data-testid="lot-detail-refresh" className="icon-button" onClick={onRefresh}
            aria-label="Muat ulang lot"><RefreshCw size={13} /></button>
          <button data-testid="lot-detail-close" className="icon-button" onClick={onClose}
            aria-label="Tutup detail"><X size={14} /></button>
        </div>
      </div>

      {/* Aksi */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-[#EFF0F2] px-2.5 py-1.5">
        {canEdit && (
          <>
            <button data-testid="lot-action-split" className="btn-secondary !px-2 !py-1 !text-[10.5px]"
              disabled={rolls.length < 2} onClick={onSplit}
              title={rolls.length < 2 ? "Butuh minimal 2 roll untuk split" : "Pecah sebagian roll ke lot anak"}>
              <span className="flex items-center gap-1"><Scissors size={11} /> Split</span>
            </button>
            <button data-testid="lot-action-merge" className="btn-secondary !px-2 !py-1 !text-[10.5px]"
              onClick={onMerge} title="Gabungkan dengan lot lain (produk & pemilik sama)">
              <span className="flex items-center gap-1"><Merge size={11} /> Merge</span>
            </button>
            <button data-testid="lot-action-rework" className="btn-secondary !px-2 !py-1 !text-[10.5px]"
              onClick={onRework} title="Bentuk lot anak hasil proses ulang">
              <span className="flex items-center gap-1"><Repeat size={11} /> Rework</span>
            </button>
            <button data-testid="lot-action-status" className="btn-secondary !px-2 !py-1 !text-[10.5px]"
              onClick={onStatus} title="Ubah status mutu lot">
              <span className="flex items-center gap-1"><ShieldCheck size={11} /> Status</span>
            </button>
          </>
        )}
        <button data-testid="lot-action-label" className="btn-secondary !px-2 !py-1 !text-[10.5px]"
          onClick={onLabel} title="Cetak label / QR lot">
          <span className="flex items-center gap-1"><Printer size={11} /> Label / QR</span>
        </button>
        <div className="ml-auto flex items-center gap-1">
          {TABS.map((t) => (
            <button key={t.id} data-testid={`lot-tab-${t.id}`}
              className={`rounded-full px-2.5 py-1 text-[10.5px] font-semibold transition-colors ${tab === t.id
                ? "bg-[#0058CC] text-white" : "border border-[#E5E5EA] bg-white text-[#6B6B73] hover:border-[#0058CC]"}`}
              onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </div>
      </div>

      <div className="px-2.5 py-2">
        {loading && <p data-testid="lot-detail-loading" className="py-4 text-center text-[11px] text-[#6B6B73]">Memuat detail lot…</p>}

        {!loading && tab === "ringkasan" && (
          <div className="space-y-2" data-testid="lot-tabpanel-ringkasan">
            {warnings.length > 0 && (
              <div data-testid="lot-detail-warnings" className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5">
                {warnings.map((w) => (
                  <p key={w} className="flex items-start gap-1.5 text-[10.5px] text-amber-800">
                    <AlertTriangle size={11} className="mt-[2px] shrink-0" /> {w}
                  </p>
                ))}
              </div>
            )}
            <div className="grid grid-cols-2 gap-1.5 md:grid-cols-4">
              {[["Pemilik (entitas)", lot.owner_entity_id],
                ["Gudang", lot.warehouse_id || "—"],
                ["Supplier", lot.supplier_name || "—"],
                ["Dokumen sumber", (lot.source_ref || {}).number || (lot.source_ref || {}).type || "—"],
                ["Qty awal", `${formatQty(lot.qty_initial)} ${lot.unit}`],
                ["Sisa tersedia", `${formatQty(lot.qty_available)} ${lot.unit}`],
                ["Roll aktif", `${lot.active_roll_count ?? 0} / ${lot.roll_count ?? 0}`],
                ["Dibuat", `${shortDateTime(lot.created_at)} · ${lot.created_by_name || lot.created_by || "—"}`],
              ].map(([k, v]) => (
                <div key={k} className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-2 py-1.5">
                  <p className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">{k}</p>
                  <p className="truncate text-[11px] font-semibold">{v}</p>
                </div>
              ))}
            </div>

            {(lot.legacy_lot_codes || []).length > 0 && (
              <p data-testid="lot-detail-legacy" className="text-[10.5px] text-[#6B6B73]">
                Kode lot lama (jejak migrasi): <b>{(lot.legacy_lot_codes || []).join(", ")}</b>
              </p>
            )}

            <div className="rounded-md border border-[#EFF0F2]">
              <div className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
                Identitas lot (dipakai label, silsilah, dan recall)
              </div>
              <div className="grid gap-2 px-2.5 py-2 md:grid-cols-2">
                {[["supplier_lot", "Nomor lot supplier", "mis. SUP-2024-118"],
                  ["dye_lot", "Dye lot / batch warna", "mis. DL-RED-01"],
                  ["shade_ref", "Referensi shade", "mis. SHADE-A / Pantone 18-1663"],
                  ["note", "Catatan", "mis. hasil kiriman kedua supplier A"]].map(([k, label, ph]) => (
                  <label key={k} className="grid gap-1">
                    <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</span>
                    <input data-testid={`lot-edit-${k}`} className="field" disabled={!canEdit}
                      value={draft[k]} placeholder={ph}
                      onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
                  </label>
                ))}
              </div>
              {canEdit && (
                <div className="flex items-center gap-2 border-t border-[#EFF0F2] px-2.5 py-1.5">
                  <button data-testid="lot-edit-save" className="primary-button !px-2.5 !py-1 !text-[10.5px]"
                    disabled={savingIdentity} onClick={() => onSaveIdentity(draft)}>
                    <span className="flex items-center gap-1">
                      <Save size={11} /> {savingIdentity ? "Menyimpan…" : "Simpan Identitas Lot"}
                    </span>
                  </button>
                  {saveMsg && <span data-testid="lot-edit-msg" className="text-[10.5px] font-semibold text-emerald-600">{saveMsg}</span>}
                </div>
              )}
            </div>

            <div className="grid gap-2 md:grid-cols-2">
              <div className="rounded-md border border-[#EFF0F2]">
                <div className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
                  Riwayat status mutu
                </div>
                <div className="max-h-[160px] divide-y divide-[#F5F5F7] overflow-y-auto" data-testid="lot-status-history">
                  {(lot.status_history || []).slice().reverse().map((h, i) => (
                    <div key={i} className="px-2.5 py-1.5 text-[10.5px]">
                      <span className="font-semibold">{labelOf("lot_status", h.status)}</span>
                      {h.status_before && <span className="text-[#8E8E93]"> ← {labelOf("lot_status", h.status_before)}</span>}
                      <span className="block text-[9.5px] text-[#8E8E93]">
                        {shortDateTime(h.at)} · {h.actor || "—"}{h.reason ? ` · ${h.reason}` : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-md border border-[#EFF0F2]">
                <div className="flex items-center gap-1.5 border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
                  <GitBranch size={11} className="text-[#0058CC]" />
                  <span className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Relasi langsung</span>
                </div>
                <div className="space-y-1.5 px-2.5 py-2 text-[10.5px]" data-testid="lot-direct-relations">
                  <p><b>Induk:</b>{" "}
                    {(lot.parents || []).length === 0 ? <span className="text-[#8E8E93]">tidak ada</span>
                      : (lot.parents || []).map((p) => (
                        <button key={p.id} data-testid={`lot-parent-${p.id}`}
                          className="mr-1 rounded-full border border-[#E5E5EA] px-1.5 py-0.5 text-[10px] hover:border-[#0058CC]"
                          onClick={() => onOpenLot(p.id)}>{p.lot_number}</button>))}
                  </p>
                  <p><b>Turunan:</b>{" "}
                    {(lot.children || []).length === 0 ? <span className="text-[#8E8E93]">tidak ada</span>
                      : (lot.children || []).map((c) => (
                        <button key={c.id} data-testid={`lot-child-${c.id}`}
                          className="mr-1 rounded-full border border-[#E5E5EA] px-1.5 py-0.5 text-[10px] hover:border-[#0058CC]"
                          onClick={() => onOpenLot(c.id)}>{c.lot_number}</button>))}
                  </p>
                  {(lot.process || {}).process_type && (
                    <p><b>Proses pembentuk:</b> {labelOf("process_type", lot.process.process_type)}
                      {lot.process.partner_name ? ` · ${lot.process.partner_name}` : ""}</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {!loading && tab === "rolls" && (
          <div data-testid="lot-tabpanel-rolls" className="overflow-x-auto">
            {rolls.length === 0 ? (
              <p data-testid="lot-rolls-empty" className="py-6 text-center text-[11px] text-[#6B6B73]">
                Lot ini tidak lagi memiliki roll (mis. seluruh roll sudah pindah ke lot turunan
                setelah split/merge/rework). Lihat tab <b>Silsilah</b> untuk menelusuri.
              </p>
            ) : (
              <table className="w-full min-w-[620px] text-[11px]">
                <thead>
                  <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[9.5px] uppercase tracking-wide text-[#8E8E93]">
                    <th className="px-2 py-1.5 font-bold">Roll</th>
                    <th className="px-2 py-1.5 font-bold">Status</th>
                    <th className="px-2 py-1.5 font-bold">Grade</th>
                    <th className="px-2 py-1.5 text-right font-bold">Awal</th>
                    <th className="px-2 py-1.5 text-right font-bold">Sisa</th>
                    <th className="px-2 py-1.5 font-bold">Gudang / Bin</th>
                    <th className="px-2 py-1.5 font-bold">Dye lot</th>
                    <th className="px-2 py-1.5 font-bold">Terikat</th>
                  </tr>
                </thead>
                <tbody>
                  {rolls.map((r) => (
                    <tr key={r.id} data-testid={`lot-roll-${r.id}`} className="border-b border-[#F5F5F7] last:border-0">
                      <td className="px-2 py-1.5 font-semibold">{r.roll_no}</td>
                      <td className="px-2 py-1.5"><span className="status-pill pill-muted">{r.status}</span></td>
                      <td className="px-2 py-1.5">{r.grade || "—"}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{formatQty(r.length_initial)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{formatQty(r.length_remaining)} {r.unit}</td>
                      <td className="px-2 py-1.5">{r.warehouse_id}{r.bin_id ? ` / ${r.bin_id}` : ""}</td>
                      <td className="px-2 py-1.5">{r.dye_lot || "—"}</td>
                      <td className="px-2 py-1.5 text-[10px] text-[#6B6B73]">
                        {(r.reserved_ref || {}).id || (r.earmarked_for || {}).id || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {!loading && tab === "silsilah" && (
          <div data-testid="lot-tabpanel-silsilah">
            <LotGenealogyTree data={genealogy} loading={genealogyLoading}
              onOpenLot={onOpenLot} labelOf={labelOf} />
          </div>
        )}

        {!loading && tab === "recall" && (
          <div data-testid="lot-tabpanel-recall">
            <LotRecallPanel data={recall} loading={recallLoading} />
          </div>
        )}
      </div>
    </div>
  );
}
