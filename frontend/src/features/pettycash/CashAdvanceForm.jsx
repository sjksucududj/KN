import { useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import { SATUAN_OPTIONS } from "./pettyCashShared";

/**
 * CashAdvanceForm — Buat / ubah Form Pengajuan Dana (PD).
 * FIX BUG EXCEL: satu kuantitas AKTIF per baris; amount = qty × harga (dihitung BE juga).
 */
const emptyLine = () => ({ description: "", qty: "", satuan: "unit", unit_price: "", catatan: "" });

export default function CashAdvanceForm({ record, entities, selectedEntity, onCancel, onSaved }) {
  const isEdit = !!record;
  const [entityId, setEntityId] = useState(
    record?.entity_id || (selectedEntity && selectedEntity !== "all" ? selectedEntity : (entities[0]?.id || ""))
  );
  const [divisi, setDivisi] = useState(record?.divisi || "");
  const [kegiatan, setKegiatan] = useState(record?.kegiatan || "");
  const [tanggal, setTanggal] = useState((record?.tanggal_pengajuan || "").slice(0, 10) || new Date().toISOString().slice(0, 10));
  const [periodFrom, setPeriodFrom] = useState((record?.period_from || "").slice(0, 10));
  const [periodTo, setPeriodTo] = useState((record?.period_to || "").slice(0, 10));
  const [accountLabel, setAccountLabel] = useState(record?.account_label || "");
  const [paymentMethod, setPaymentMethod] = useState(record?.payment_method || "tunai");
  const [bank, setBank] = useState({
    bank: record?.bank_detail?.bank || "", no_account: record?.bank_detail?.no_account || "",
    nama: record?.bank_detail?.nama || "", cabang: record?.bank_detail?.cabang || "",
  });
  const [catatan, setCatatan] = useState(record?.catatan || "");
  const [lines, setLines] = useState(record?.lines?.length ? record.lines.map((l) => ({ ...l })) : [emptyLine()]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const total = useMemo(
    () => lines.reduce((s, l) => s + (Number(l.qty) || 0) * (Number(l.unit_price) || 0), 0),
    [lines]
  );

  function updLine(i, k, v) { setLines(lines.map((l, idx) => (idx === i ? { ...l, [k]: v } : l))); }
  function addLine() { setLines([...lines, emptyLine()]); }
  function rmLine(i) { setLines(lines.length > 1 ? lines.filter((_, idx) => idx !== i) : lines); }

  async function submit() {
    setErr("");
    if (!entityId) { setErr("Pilih entitas."); return; }
    const clean = lines
      .filter((l) => (Number(l.qty) || 0) > 0 && (Number(l.unit_price) || 0) > 0)
      .map((l) => ({
        description: l.description || "", qty: Number(l.qty) || 0, satuan: l.satuan || "unit",
        unit_price: Number(l.unit_price) || 0, catatan: l.catatan || "",
      }));
    if (clean.length === 0) { setErr("Minimal 1 baris dengan qty & harga > 0."); return; }
    setBusy(true);
    try {
      const payload = {
        entity_id: entityId, divisi, kegiatan, tanggal_pengajuan: tanggal,
        period_from: periodFrom, period_to: periodTo, account_label: accountLabel,
        payment_method: paymentMethod,
        bank_detail: paymentMethod === "transfer" ? bank : null,
        lines: clean, catatan,
      };
      const res = isEdit
        ? await axios.patch(`${API}/cash-advances/${record.id}`, payload)
        : await axios.post(`${API}/cash-advances`, payload);
      onSaved(res.data, isEdit);
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal menyimpan Pengajuan Dana.");
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="ca-form" className="grid gap-4">
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <button className="icon-button" onClick={onCancel} aria-label="Kembali"><ArrowLeft size={15} /></button>
            <h2 data-testid="ca-form-title">{isEdit ? `Ubah ${record.number}` : "Buat Pengajuan Dana (PD)"}</h2>
          </div>
        </div>
        <div className="section-body grid gap-3">
          {err && <div className="notice-bar danger" data-testid="ca-form-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Entitas" req>
              <KNSelect data-testid="ca-entity" className="form-input" value={entityId} onValueChange={setEntityId}
                placeholder="Pilih entitas"
                options={entities.map((e) => ({ value: e.id, label: e.short_name || e.legal_name }))} />
            </Field>
            <Field label="Divisi">
              <input data-testid="ca-divisi" className="form-input" value={divisi} onChange={(e) => setDivisi(e.target.value)} placeholder="mis. Marketing" />
            </Field>
            <Field label="Kegiatan / Keperluan">
              <input data-testid="ca-kegiatan" className="form-input" value={kegiatan} onChange={(e) => setKegiatan(e.target.value)} placeholder="mis. Operasional pameran" />
            </Field>
            <Field label="Tanggal Pengajuan">
              <input type="date" data-testid="ca-tanggal" className="form-input" value={tanggal} onChange={(e) => setTanggal(e.target.value)} />
            </Field>
            <Field label="Periode Dari">
              <input type="date" data-testid="ca-period-from" className="form-input" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
            </Field>
            <Field label="Periode Sampai">
              <input type="date" data-testid="ca-period-to" className="form-input" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
            </Field>
          </div>

          {/* Lines */}
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[1.6fr_90px_110px_130px_120px_36px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
              <span>Uraian</span><span className="text-right">Qty</span><span>Satuan</span><span className="text-right">Harga</span><span className="text-right">Jumlah</span><span></span>
            </div>
            {lines.map((l, i) => (
              <div key={i} data-testid={`ca-line-${i}`} className="grid grid-cols-[1.6fr_90px_110px_130px_120px_36px] items-center gap-1 px-3 py-2 border-t border-[#F4F5F7]">
                <input data-testid={`ca-line-desc-${i}`} className="form-input" value={l.description} onChange={(e) => updLine(i, "description", e.target.value)} placeholder="Uraian item / biaya" />
                <input type="number" data-testid={`ca-line-qty-${i}`} className="form-input text-right" value={l.qty} onChange={(e) => updLine(i, "qty", e.target.value)} placeholder="0" />
                <KNSelect data-testid={`ca-line-satuan-${i}`} className="form-input" value={l.satuan} onValueChange={(v) => updLine(i, "satuan", v)} options={SATUAN_OPTIONS} />
                <input type="number" data-testid={`ca-line-price-${i}`} className="form-input text-right" value={l.unit_price} onChange={(e) => updLine(i, "unit_price", e.target.value)} placeholder="0" />
                <span className="text-[12px] tabular-nums text-right font-semibold">{formatCurrency((Number(l.qty) || 0) * (Number(l.unit_price) || 0))}</span>
                <button className="icon-button text-red-500" onClick={() => rmLine(i)} aria-label="Hapus baris"><Trash2 size={14} /></button>
              </div>
            ))}
            <div className="flex items-center justify-between px-3 py-2 border-t border-[#EFF0F2] bg-[#FAFBFC]">
              <button data-testid="ca-add-line" className="btn-secondary btn-xs" onClick={addLine}><Plus size={13} /> Tambah Baris</button>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold uppercase text-[#6B6B73]">Total</span>
                <span data-testid="ca-form-total" className="text-[16px] font-bold tabular-nums text-[#0058CC]">{formatCurrency(total)}</span>
              </div>
            </div>
          </div>

          {/* Payment */}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Metode Pembayaran">
              <KNSelect data-testid="ca-payment-method" className="form-input" value={paymentMethod} onValueChange={setPaymentMethod}
                options={[{ value: "tunai", label: "Tunai (Kas)" }, { value: "transfer", label: "Transfer Bank" }]} />
            </Field>
            <Field label="Rekening Sumber / Label">
              <input data-testid="ca-account-label" className="form-input" value={accountLabel} onChange={(e) => setAccountLabel(e.target.value)} placeholder="mis. BCA 3999-988-858" />
            </Field>
          </div>

          {paymentMethod === "transfer" && (
            <div data-testid="ca-bank-detail" className="grid gap-3 sm:grid-cols-2 rounded-md border border-[#EFF0F2] p-3 bg-[#FAFBFC]">
              <Field label="Bank Tujuan"><input data-testid="ca-bank-name" className="form-input" value={bank.bank} onChange={(e) => setBank({ ...bank, bank: e.target.value })} placeholder="mis. BCA" /></Field>
              <Field label="No. Rekening"><input data-testid="ca-bank-no" className="form-input" value={bank.no_account} onChange={(e) => setBank({ ...bank, no_account: e.target.value })} placeholder="1234567890" /></Field>
              <Field label="Atas Nama"><input data-testid="ca-bank-nama" className="form-input" value={bank.nama} onChange={(e) => setBank({ ...bank, nama: e.target.value })} placeholder="Nama penerima" /></Field>
              <Field label="Cabang"><input data-testid="ca-bank-cabang" className="form-input" value={bank.cabang} onChange={(e) => setBank({ ...bank, cabang: e.target.value })} placeholder="Cabang" /></Field>
            </div>
          )}

          <Field label="Catatan">
            <textarea data-testid="ca-catatan" className="form-input" rows="2" value={catatan} onChange={(e) => setCatatan(e.target.value)} placeholder="Keterangan tambahan..." />
          </Field>

          <div className="flex justify-end gap-2 pt-1">
            <button className="btn-secondary" onClick={onCancel}>Batal</button>
            <button data-testid="ca-submit" className="btn-primary" onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : (isEdit ? "Simpan Perubahan" : "Simpan PD")}</button>
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({ label, req, children }) {
  return (
    <div className="grid gap-1.5">
      <label className="text-[11px] font-bold uppercase text-[#6B6B73]">{label}{req && <span className="req"> *</span>}</label>
      {children}
    </div>
  );
}
