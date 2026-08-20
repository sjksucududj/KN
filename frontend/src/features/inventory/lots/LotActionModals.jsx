/**
 * LotActionModals (FASE C · D-10) — aksi genealogi lot: split, merge, rework,
 * ubah status, buat lot manual, dan cetak label/QR.
 * Semua aksi memanggil endpoint tunggal `/api/lots/*` (SSOT `lot_service`).
 */
import { useEffect, useState } from "react";
import { Printer, X } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { formatQty } from "../../../utils/formatters";
import { errText, lotApi } from "./lotApi";

function Shell({ title, subtitle, onClose, children, actions, testId, error, onDismissError }) {
  return (
    <div className="modal-overlay" data-testid={testId}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 620, width: "95vw", maxHeight: "90vh", overflowY: "auto" }}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="modal-title">{title}</p>
            {subtitle && <p className="modal-subtitle">{subtitle}</p>}
          </div>
          <button data-testid={`${testId}-close`} className="icon-button" onClick={onClose} aria-label="Tutup">
            <X size={15} />
          </button>
        </div>
        {error && (
          <div className="notice-bar danger" data-testid={`${testId}-error`}>
            <span>{error}</span><button onClick={onDismissError}>×</button>
          </div>
        )}
        <div className="mt-2 grid gap-2">{children}</div>
        <div className="modal-actions">{actions}</div>
      </div>
    </div>
  );
}

/** SPLIT — pecah sebagian roll menjadi lot anak. */
export function SplitLotModal({ lot, rolls, onClose, onDone }) {
  const [picked, setPicked] = useState([]);
  const [reason, setReason] = useState("");
  const [dyeLot, setDyeLot] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  async function submit() {
    setBusy(true); setErr("");
    try {
      const out = await lotApi.split(lot.id, { roll_ids: picked, reason, dye_lot: dyeLot });
      onDone(`Lot ${out.child.lot_number} terbentuk dari ${out.moved_rolls} roll.`, out.child.id);
    } catch (e) { setErr(errText(e, "Split lot gagal.")); } finally { setBusy(false); }
  }

  return (
    <Shell testId="lot-split-modal" title={`Split Lot ${lot.lot_number}`} onClose={onClose}
      error={err} onDismissError={() => setErr("")}
      subtitle="Pilih roll yang dipisahkan (mis. beda shade setelah inspeksi). Lot asal wajib menyisakan minimal 1 roll; riwayat induk–anak tersimpan otomatis."
      actions={(
        <>
          <button className="btn-secondary" onClick={onClose}>Batal</button>
          <button data-testid="lot-split-submit" className="primary-button"
            disabled={busy || picked.length === 0 || picked.length >= rolls.length} onClick={submit}>
            {busy ? "Memproses…" : `Split ${picked.length} roll`}
          </button>
        </>
      )}>
      <div className="rounded-md border border-[#EFF0F2]">
        <div className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          Roll dalam lot ({rolls.length})
        </div>
        <div className="max-h-[240px] divide-y divide-[#F5F5F7] overflow-y-auto">
          {rolls.map((r) => (
            <label key={r.id} data-testid={`lot-split-roll-${r.id}`}
              className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-[10.5px] hover:bg-[#FAFBFC]">
              <input type="checkbox" checked={picked.includes(r.id)} onChange={() => toggle(r.id)} />
              <span className="font-semibold">{r.roll_no}</span>
              <span className="text-[#6B6B73]">{formatQty(r.length_remaining)} {r.unit}</span>
              <span className="status-pill pill-muted">{r.status}</span>
              {r.dye_lot && <span className="text-[#8E8E93]">dye {r.dye_lot}</span>}
              <span className="ml-auto text-[#8E8E93]">grade {r.grade || "—"}</span>
            </label>
          ))}
        </div>
      </div>
      <label className="grid gap-1">
        <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Dye lot baru (opsional)</span>
        <input data-testid="lot-split-dyelot" className="field" value={dyeLot}
          placeholder="mis. DL-RED-B" onChange={(e) => setDyeLot(e.target.value)} />
      </label>
      <label className="grid gap-1">
        <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Alasan split</span>
        <input data-testid="lot-split-reason" className="field" value={reason}
          placeholder="mis. shade berbeda hasil inspeksi" onChange={(e) => setReason(e.target.value)} />
      </label>
    </Shell>
  );
}

/** MERGE — gabungkan lot lain (produk & pemilik sama) ke lot baru. */
export function MergeLotModal({ lot, onClose, onDone }) {
  const [candidates, setCandidates] = useState([]);
  const [picked, setPicked] = useState([lot.id]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    lotApi.list({ product_id: lot.product_id, limit: 200 })
      .then((rows) => setCandidates((Array.isArray(rows) ? rows : rows.items || [])
        .filter((l) => l.owner_entity_id === lot.owner_entity_id && !l.merged_into)))
      .catch((e) => setErr(errText(e, "Gagal memuat kandidat lot.")));
  }, [lot.id, lot.product_id, lot.owner_entity_id]);

  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  async function submit() {
    setBusy(true); setErr("");
    try {
      const out = await lotApi.merge({ lot_ids: picked, reason });
      onDone(`Lot gabungan ${out.lot.lot_number} dibuat dari ${out.sources.length} lot (${out.moved_rolls} roll).`,
             out.lot.id);
    } catch (e) { setErr(errText(e, "Merge lot gagal.")); } finally { setBusy(false); }
  }

  return (
    <Shell testId="lot-merge-modal" title="Merge Lot" onClose={onClose}
      error={err} onDismissError={() => setErr("")}
      subtitle="Pilih minimal 2 lot dengan produk & pemilik sama. Seluruh roll dipindahkan ke lot baru dan lot sumber tetap tersimpan sebagai induk (jejak audit)."
      actions={(
        <>
          <button className="btn-secondary" onClick={onClose}>Batal</button>
          <button data-testid="lot-merge-submit" className="primary-button"
            disabled={busy || picked.length < 2} onClick={submit}>
            {busy ? "Memproses…" : `Gabung ${picked.length} lot`}
          </button>
        </>
      )}>
      <div className="rounded-md border border-[#EFF0F2]">
        <div className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          Lot produk {lot.sku} ({candidates.length})
        </div>
        <div className="max-h-[280px] divide-y divide-[#F5F5F7] overflow-y-auto">
          {candidates.length === 0 && (
            <p className="px-2.5 py-2 text-[10.5px] text-[#8E8E93]">Tidak ada lot lain untuk produk ini.</p>
          )}
          {candidates.map((c) => (
            <label key={c.id} data-testid={`lot-merge-pick-${c.id}`}
              className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-[10.5px] hover:bg-[#FAFBFC]">
              <input type="checkbox" checked={picked.includes(c.id)} onChange={() => toggle(c.id)} />
              <span className="font-semibold">{c.lot_number}</span>
              <span className="text-[#6B6B73]">{c.roll_count} roll · {formatQty(c.qty_remaining)} {c.unit}</span>
              {c.dye_lot && <span className="text-[#8E8E93]">dye {c.dye_lot}</span>}
              <span className="ml-auto status-pill pill-muted">{c.lot_status}</span>
            </label>
          ))}
        </div>
      </div>
      <label className="grid gap-1">
        <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Alasan merge</span>
        <input data-testid="lot-merge-reason" className="field" value={reason}
          placeholder="mis. sisa beberapa batch disatukan untuk 1 pesanan besar"
          onChange={(e) => setReason(e.target.value)} />
      </label>
    </Shell>
  );
}

/** REWORK — bentuk lot anak hasil proses ulang/lanjutan. */
export function ReworkLotModal({ lot, rolls, processOptions, stageOptions, makloons = [],
                                 onClose, onDone }) {
  const [processType, setProcessType] = useState("");
  const [partnerId, setPartnerId] = useState("");
  const [toStage, setToStage] = useState("");
  const [reason, setReason] = useState("");
  const [picked, setPicked] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const partner = makloons.find((m) => m.id === partnerId);

  async function submit() {
    setBusy(true); setErr("");
    try {
      const out = await lotApi.rework(lot.id, {
        process_type: processType, roll_ids: picked, partner_id: partnerId,
        partner_name: partner?.name || "", to_stage: toStage, reason,
      });
      onDone(`Lot rework ${out.child.lot_number} dibuat (${out.moved_rolls} roll).`, out.child.id);
    } catch (e) { setErr(errText(e, "Rework gagal.")); } finally { setBusy(false); }
  }

  return (
    <Shell testId="lot-rework-modal" title={`Rework Lot ${lot.lot_number}`} onClose={onClose}
      error={err} onDismissError={() => setErr("")}
      subtitle="Proses ulang / proses lanjutan. Roll berpindah ke lot anak; bila tahap tujuan diisi, transisi divalidasi mesin tahap (tidak boleh melompat)."
      actions={(
        <>
          <button className="btn-secondary" onClick={onClose}>Batal</button>
          <button data-testid="lot-rework-submit" className="primary-button"
            disabled={busy || !processType} onClick={submit}>
            {busy ? "Memproses…" : "Buat Lot Rework"}
          </button>
        </>
      )}>
      <div className="grid gap-2 md:grid-cols-2">
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Jenis proses *</span>
          <KNSelect data-testid="lot-rework-process" className="field" value={processType}
            placeholder="Pilih proses" options={processOptions}
            onValueChange={setProcessType} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Tahap tujuan (opsional)</span>
          <KNSelect data-testid="lot-rework-stage" className="field" value={toStage}
            placeholder="Tetap di tahap sekarang"
            options={[{ value: "", label: "Tetap di tahap sekarang" }, ...stageOptions]}
            onValueChange={setToStage} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Mitra pelaksana (opsional)</span>
          <KNSelect data-testid="lot-rework-partner" className="field" value={partnerId} searchable
            placeholder="Internal / pilih mitra makloon"
            options={[{ value: "", label: "Internal (tanpa mitra)" },
                      ...makloons.map((m) => ({ value: m.id, label: m.name }))]}
            onValueChange={setPartnerId} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Alasan / catatan</span>
          <input data-testid="lot-rework-reason" className="field" value={reason}
            placeholder="mis. celup ulang karena shade tidak lolos"
            onChange={(e) => setReason(e.target.value)} />
        </label>
      </div>
      <div className="rounded-md border border-[#EFF0F2]">
        <div className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          Roll yang di-rework — kosongkan pilihan = seluruh {rolls.length} roll
        </div>
        <div className="max-h-[200px] divide-y divide-[#F5F5F7] overflow-y-auto">
          {rolls.map((r) => (
            <label key={r.id} data-testid={`lot-rework-roll-${r.id}`}
              className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-[10.5px] hover:bg-[#FAFBFC]">
              <input type="checkbox" checked={picked.includes(r.id)} onChange={() => toggle(r.id)} />
              <span className="font-semibold">{r.roll_no}</span>
              <span className="text-[#6B6B73]">{formatQty(r.length_remaining)} {r.unit}</span>
              <span className="ml-auto status-pill pill-muted">{r.status}</span>
            </label>
          ))}
        </div>
      </div>
    </Shell>
  );
}

/** UBAH STATUS MUTU LOT (informasional — tidak memblokir penjualan). */
export function LotStatusModal({ lot, statusOptions, onClose, onDone }) {
  const [status, setStatus] = useState(lot.lot_status || "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    setBusy(true); setErr("");
    try {
      const out = await lotApi.setStatus(lot.id, { status, reason });
      onDone(`Status lot ${out.lot_number} → ${out.lot_status}.`, out.id);
    } catch (e) { setErr(errText(e, "Gagal mengubah status lot.")); } finally { setBusy(false); }
  }

  return (
    <Shell testId="lot-status-modal" title={`Status Mutu Lot ${lot.lot_number}`} onClose={onClose}
      error={err} onDismissError={() => setErr("")}
      subtitle="Status mutu lot bersifat informasional pada Fase C (tidak memblokir penjualan) dan seluruh perubahan tercatat dengan alasan + pelaku."
      actions={(
        <>
          <button className="btn-secondary" onClick={onClose}>Batal</button>
          <button data-testid="lot-status-submit" className="primary-button"
            disabled={busy || !status} onClick={submit}>{busy ? "Menyimpan…" : "Simpan Status"}</button>
        </>
      )}>
      <label className="grid gap-1">
        <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Status baru</span>
        <KNSelect data-testid="lot-status-select" className="field" value={status}
          options={statusOptions} onValueChange={setStatus} />
      </label>
      <label className="grid gap-1">
        <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Alasan</span>
        <input data-testid="lot-status-reason" className="field" value={reason}
          placeholder="mis. lolos inspeksi 4-point" onChange={(e) => setReason(e.target.value)} />
      </label>
    </Shell>
  );
}

/** BUAT LOT MANUAL (stok awal / koreksi data lapangan). */
export function CreateLotModal({ products = [], warehouses = [], sourceOptions, statusOptions,
                                 onClose, onDone }) {
  const [form, setForm] = useState({ product_id: "", warehouse_id: "", supplier_lot: "",
                                     dye_lot: "", shade_ref: "", source: "manual",
                                     lot_status: "released", note: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function submit() {
    setBusy(true); setErr("");
    try {
      const out = await lotApi.create(form);
      onDone(`Lot ${out.lot_number} dibuat.`, out.id);
    } catch (e) { setErr(errText(e, "Gagal membuat lot.")); } finally { setBusy(false); }
  }

  return (
    <Shell testId="lot-create-modal" title="Buat Lot Manual" onClose={onClose}
      error={err} onDismissError={() => setErr("")}
      subtitle="Untuk stok awal atau koreksi data lapangan. Nomor lot dibuat otomatis per entitas (KSC/LOT-YYMM-####) dan tidak bisa diketik manual agar tidak bentrok."
      actions={(
        <>
          <button className="btn-secondary" onClick={onClose}>Batal</button>
          <button data-testid="lot-create-submit" className="primary-button"
            disabled={busy || !form.product_id} onClick={submit}>
            {busy ? "Menyimpan…" : "Buat Lot"}
          </button>
        </>
      )}>
      <div className="grid gap-2 md:grid-cols-2">
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Produk *</span>
          <KNSelect data-testid="lot-create-product" className="field" searchable
            value={form.product_id} placeholder="Pilih produk"
            options={products.slice(0, 400).map((p) => ({ value: p.id, label: `${p.sku} — ${p.name}` }))}
            onValueChange={(v) => set("product_id", v)} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Gudang</span>
          <KNSelect data-testid="lot-create-warehouse" className="field" value={form.warehouse_id}
            placeholder="Pilih gudang"
            options={warehouses.map((w) => ({ value: w.id, label: w.name || w.id }))}
            onValueChange={(v) => set("warehouse_id", v)} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Nomor lot supplier</span>
          <input data-testid="lot-create-supplier-lot" className="field" value={form.supplier_lot}
            placeholder="mis. SUP-2024-118" onChange={(e) => set("supplier_lot", e.target.value)} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Dye lot / shade</span>
          <input data-testid="lot-create-dye-lot" className="field" value={form.dye_lot}
            placeholder="mis. DL-RED-01" onChange={(e) => set("dye_lot", e.target.value)} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Sumber</span>
          <KNSelect data-testid="lot-create-source" className="field" value={form.source}
            options={sourceOptions} onValueChange={(v) => set("source", v)} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Status mutu</span>
          <KNSelect data-testid="lot-create-status" className="field" value={form.lot_status}
            options={statusOptions} onValueChange={(v) => set("lot_status", v)} />
        </label>
      </div>
      <label className="grid gap-1">
        <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Catatan</span>
        <input data-testid="lot-create-note" className="field" value={form.note}
          placeholder="mis. stok awal opname gudang Bandung"
          onChange={(e) => set("note", e.target.value)} />
      </label>
    </Shell>
  );
}

/** LABEL / QR — memakai mesin label yang sudah ada (ZPL / ESC-POS). */
export function LotLabelModal({ lot, rolls = [], onClose }) {
  const [format, setFormat] = useState("zpl");
  const [qty, setQty] = useState(1);
  const [rollId, setRollId] = useState("");
  const [out, setOut] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);

  async function generate() {
    setBusy(true); setErr(""); setCopied(false);
    try {
      setOut(await lotApi.label(lot.id, { format, qty: Number(qty) || 1, roll_id: rollId }));
    } catch (e) { setErr(errText(e, "Gagal membuat label.")); } finally { setBusy(false); }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(out?.content || "");
      setCopied(true);
    } catch { setErr("Perangkat tidak mengizinkan salin otomatis — salin manual dari kotak di bawah."); }
  }

  return (
    <Shell testId="lot-label-modal" title={`Label Lot ${lot.lot_number}`} onClose={onClose}
      error={err} onDismissError={() => setErr("")}
      subtitle="Perintah cetak dibuat server memakai mesin label yang sudah dipakai produk (ZPL untuk printer label, ESC-POS untuk printer struk). Nilai barcode/QR = nomor lot (atau nomor roll bila dipilih)."
      actions={(
        <>
          <button className="btn-secondary" onClick={onClose}>Tutup</button>
          <button data-testid="lot-label-generate" className="primary-button" disabled={busy}
            onClick={generate}>
            <span className="flex items-center gap-1"><Printer size={12} /> {busy ? "Membuat…" : "Buat Perintah Cetak"}</span>
          </button>
        </>
      )}>
      <div className="grid gap-2 md:grid-cols-3">
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Format printer</span>
          <KNSelect data-testid="lot-label-format" className="field" value={format}
            options={[{ value: "zpl", label: "ZPL (Zebra label)" },
                      { value: "escpos", label: "ESC-POS (printer struk)" }]}
            onValueChange={setFormat} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Jumlah label</span>
          <input data-testid="lot-label-qty" className="field" type="number" min={1} max={50}
            value={qty} onChange={(e) => setQty(e.target.value)} />
        </label>
        <label className="grid gap-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Untuk roll (opsional)</span>
          <KNSelect data-testid="lot-label-roll" className="field" value={rollId}
            placeholder="Label lot (semua roll)"
            options={[{ value: "", label: "Label lot (semua roll)" },
                      ...rolls.map((r) => ({ value: r.id, label: `${r.roll_no} · ${formatQty(r.length_remaining)} ${r.unit}` }))]}
            onValueChange={setRollId} />
        </label>
      </div>
      {out && (
        <div data-testid="lot-label-output" className="grid gap-1.5">
          <div className="grid grid-cols-2 gap-1.5 md:grid-cols-4">
            {[["Nomor lot", out.lot.lot_number], ["SKU", out.lot.sku],
              ["Dye lot", out.lot.dye_lot || "—"], ["Nilai QR", out.lot.qr_value]].map(([k, v]) => (
              <div key={k} className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-2 py-1.5">
                <p className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">{k}</p>
                <p className="truncate text-[11px] font-semibold">{v}</p>
              </div>
            ))}
          </div>
          <pre data-testid="lot-label-content"
            className="max-h-[180px] overflow-auto rounded-md border border-[#EFF0F2] bg-[#1C1C1E] p-2 text-[10px] leading-tight text-[#E5E5EA]">
            {out.content}
          </pre>
          <button data-testid="lot-label-copy" className="btn-secondary !px-2 !py-1 !text-[10.5px] w-fit"
            onClick={copy}>{copied ? "Tersalin ✓" : "Salin perintah cetak"}</button>
        </div>
      )}
    </Shell>
  );
}
