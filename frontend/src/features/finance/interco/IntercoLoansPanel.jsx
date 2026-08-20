/**
 * IntercoLoansPanel — FASE E-7 (E7f) · **PINJAMAN UANG ANTAR-PT**.
 *
 * Jalur yang pemilik nyatakan memang terjadi: PT A menalangi PT B. Sebelum ini caranya
 * “transfer saja dari rekening”, lalu uangnya tercatat sebagai entah apa — utang-piutang
 * antar-PT tidak pernah cocok. Di sini satu peristiwa uang menghasilkan dokumen kembar,
 * mutasi kas di kedua buku, jurnal IC-AR ↔ IC-AP, dan eliminasi otomatis di konsolidasi.
 *
 * Bunga TIDAK diakru sistem (pemilik tidak memintanya) — kolom catatan bunga ada supaya
 * kesepakatannya terbaca, bukan supaya angkanya dikarang.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Banknote, Plus, RefreshCw, HandCoins, Ban, CheckCircle2 } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import KNSelect from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";

const STATUS_CLASS = {
  draft: "bg-[#F2F2F5] text-[#6E6E73] border-[#E2E2E7]",
  disbursed: "bg-[#E7F0FF] text-[#0058CC] border-[#C9DBF7]",
  partially_repaid: "bg-[#FFF4E5] text-[#8A5300] border-[#F5D9A8]",
  repaid: "bg-[#E6F6EC] text-[#1B7F4B] border-[#BFE6CE]",
  cancelled: "bg-[#FDEDE7] text-[#C0392B] border-[#F5C9BC]",
};

const apiText = (e, f = "Terjadi kesalahan.") => e?.response?.data?.detail || e?.message || f;

export default function IntercoLoansPanel({ entities = [], entityId = "", canWrite = false }) {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState({});
  const [meta, setMeta] = useState({ statuses: [] });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [repayFor, setRepayFor] = useState(null);
  const [repayAmt, setRepayAmt] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = entityId && entityId !== "all" ? { entity_id: entityId } : {};
      const res = await axios.get(`${API}/interco/loans`, { params });
      setItems(res.data?.items || []);
      setSummary(res.data?.summary || {});
      setErr("");
    } catch (e) { setErr(apiText(e, "Gagal memuat pinjaman antar-PT.")); }
    finally { setLoading(false); }
  }, [entityId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    axios.get(`${API}/interco/loans/meta`).then((r) => setMeta(r.data)).catch(() => {});
  }, []);

  const label = (s) => (meta.statuses || []).find((x) => x.id === s)?.label || s;

  async function act(loan, path, body, okMsg) {
    setBusy(loan.id); setErr("");
    try {
      await axios.post(`${API}/interco/loans/${loan.id}/${path}`, body || {});
      setMsg(okMsg); setTimeout(() => setMsg(""), 5000);
      setRepayFor(null); setRepayAmt("");
      await load();
    } catch (e) { setErr(apiText(e)); }
    finally { setBusy(""); }
  }

  return (
    <div className="space-y-3" data-testid="interco-loans-panel">
      <p className="text-[12px] leading-relaxed text-[#6E6E73]">
        Pinjaman uang antar badan usaha dalam grup. Saat dicairkan, uang benar-benar
        berpindah: <b>kas keluar di PT pemberi</b> & <b>kas masuk di PT penerima</b>, dengan
        jurnal <b>Piutang/Utang Antar-Perusahaan</b> di masing-masing buku. Saldonya
        tampil sebagai <b>saldo non-dagang</b> (diangsur, bukan di-netting) dan otomatis
        dieliminasi di Konsolidasi Grup. Bunga tidak dihitung sistem — tulis
        kesepakatannya di catatan bunga.
      </p>

      {err && <div className="notice-bar danger" data-testid="loan-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}
      {msg && <div className="notice-bar success" data-testid="loan-notice"><span>{msg}</span><button onClick={() => setMsg("")}>×</button></div>}

      <div className="grid gap-3 sm:grid-cols-3">
        <Kpi label="Dipinjamkan (belum kembali)" value={formatCurrency(summary.outstanding_lent || 0)} testid="loan-kpi-lent" />
        <Kpi label="Dipinjam (belum dibayar)" value={formatCurrency(summary.outstanding_borrowed || 0)} testid="loan-kpi-borrowed" />
        <Kpi label="Jumlah Dokumen" value={summary.total || 0} testid="loan-kpi-count" />
      </div>

      <div className="flex items-center justify-end gap-2">
        <button className="icon-button" onClick={load} aria-label="Muat ulang" data-testid="loan-refresh">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
        {canWrite && (
          <button className="btn-primary" data-testid="loan-create-btn" onClick={() => setShowCreate(true)}>
            <Plus size={14} /> Pinjaman Baru
          </button>
        )}
      </div>

      <div className="rounded-xl border border-[#E5E5EA] bg-white overflow-x-auto">
        <table className="w-full text-[12px]" data-testid="loan-table">
          <thead className="bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73]">
            <tr>
              <th className="px-3 py-2 text-left">Nomor</th>
              <th className="px-3 py-2 text-left">Arah</th>
              <th className="px-3 py-2 text-left">Tujuan</th>
              <th className="px-3 py-2 text-right">Pokok</th>
              <th className="px-3 py-2 text-right">Sisa</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-right">Aksi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#F2F2F5]">
            {loading && <tr><td colSpan={7} className="px-3 py-8 text-center text-[#8E8E93]">Memuat…</td></tr>}
            {!loading && items.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-10 text-center text-[#8E8E93]" data-testid="loan-empty">
                Belum ada pinjaman antar-PT.
              </td></tr>
            )}
            {!loading && items.map((l) => (
              <tr key={l.id} data-testid={`loan-row-${l.id}`} className="hover:bg-[#FAFAFB]">
                <td className="px-3 py-2 font-bold text-[#0058CC]">{l.number}</td>
                <td className="px-3 py-2">
                  {l.role === "lender" ? "memberi →" : "menerima ←"}{" "}
                  <b>{l.role === "lender" ? l.borrower_entity_name : l.lender_entity_name}</b>
                </td>
                <td className="px-3 py-2 max-w-[240px] truncate" title={l.purpose}>{l.purpose}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(l.principal)}</td>
                <td className="px-3 py-2 text-right tabular-nums font-semibold">{formatCurrency(l.outstanding)}</td>
                <td className="px-3 py-2">
                  <span data-testid={`loan-status-${l.id}`}
                    className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold ${STATUS_CLASS[l.status] || ""}`}>
                    {label(l.status)}
                  </span>
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  {canWrite && l.status === "draft" && l.role === "lender" && (
                    <>
                      <button data-testid={`loan-disburse-${l.id}`} className="btn-primary btn-xs mr-1"
                        disabled={busy === l.id}
                        onClick={() => act(l, "disburse", {}, `${l.number} dicairkan — kas berpindah & jurnal terbit di kedua buku.`)}>
                        <HandCoins size={11} /> Cairkan
                      </button>
                      <button data-testid={`loan-cancel-${l.id}`} className="btn-secondary btn-xs"
                        disabled={busy === l.id}
                        onClick={() => act(l, "cancel", { reason: "dibatalkan sebelum dicairkan" }, `${l.number} dibatalkan.`)}>
                        <Ban size={11} /> Batal
                      </button>
                    </>
                  )}
                  {canWrite && ["disbursed", "partially_repaid"].includes(l.status) && (
                    <button data-testid={`loan-repay-${l.id}`} className="btn-secondary btn-xs"
                      onClick={() => { setRepayFor(l); setRepayAmt(String(l.outstanding || "")); }}>
                      Angsur
                    </button>
                  )}
                  {l.status === "repaid" && (
                    <span className="inline-flex items-center gap-1 text-[10.5px] text-[#1B7F4B]">
                      <CheckCircle2 size={11} /> lunas
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateLoanModal entities={entities} defaultEntity={entityId}
          onClose={() => setShowCreate(false)}
          onCreated={(res) => {
            setShowCreate(false);
            setMsg(`Pinjaman ${res.lender.number} ⇄ ${res.borrower.number} dibuat (draf) — tekan Cairkan bila uangnya sudah siap dipindah.`);
            setTimeout(() => setMsg(""), 7000);
            load();
          }} />
      )}

      {repayFor && (
        <div className="modal-overlay" data-testid="loan-repay-modal"
          onClick={(e) => { if (e.target === e.currentTarget) setRepayFor(null); }}>
          <div className="modal-card small" onClick={(e) => e.stopPropagation()}>
            <p className="modal-title">Angsuran {repayFor.number}</p>
            <p className="modal-subtitle">
              Sisa pinjaman {formatCurrency(repayFor.outstanding)}. Uang akan berpindah
              dari {repayFor.borrower_entity_name} ke {repayFor.lender_entity_name}, dan
              jurnalnya terbit di kedua buku.
            </p>
            <input data-testid="loan-repay-amount" type="number" className="field mt-2"
              value={repayAmt} onChange={(e) => setRepayAmt(e.target.value)} />
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setRepayFor(null)}>Batal</button>
              <button data-testid="loan-repay-confirm" className="btn-primary"
                disabled={busy === repayFor.id || !(Number(repayAmt) > 0)}
                onClick={() => act(repayFor, "repay", { amount: Number(repayAmt), note: "" },
                  `Angsuran ${formatCurrency(Number(repayAmt))} untuk ${repayFor.number} dicatat.`)}>
                Catat Angsuran
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Kpi({ label, value, testid }) {
  return (
    <div className="rounded-xl border border-[#E5E5EA] bg-white p-3" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-wide text-[#6E6E73]">{label}</div>
      <div className="mt-1 text-[18px] font-bold tabular-nums text-[#1D1D1F]">{value}</div>
    </div>
  );
}

function CreateLoanModal({ entities, defaultEntity, onClose, onCreated }) {
  const [lender, setLender] = useState(defaultEntity && defaultEntity !== "all" ? defaultEntity : "");
  const [borrower, setBorrower] = useState("");
  const [principal, setPrincipal] = useState("");
  const [purpose, setPurpose] = useState("");
  const [interestNote, setInterestNote] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const opts = useMemo(() => (entities || [])
    .filter((e) => (e.status || "active") === "active")
    .map((e) => ({ value: e.id, label: e.short_name || e.legal_name || e.id })), [entities]);

  async function submit() {
    if (!lender || !borrower) { setErr("Pilih badan usaha pemberi & penerima."); return; }
    if (lender === borrower) { setErr("Pemberi & penerima harus berbeda."); return; }
    if (!(Number(principal) > 0)) { setErr("Jumlah pinjaman harus lebih dari 0."); return; }
    if (purpose.trim().length < 5) { setErr("Tujuan pinjaman wajib diisi (minimal 5 huruf)."); return; }
    setBusy(true); setErr("");
    try {
      const res = await axios.post(`${API}/interco/loans`, {
        lender_entity_id: lender, borrower_entity_id: borrower,
        principal: Number(principal), purpose: purpose.trim(),
        interest_note: interestNote, agreed_return_date: returnDate,
      });
      onCreated(res.data);
    } catch (e) { setErr(apiText(e, "Gagal membuat pinjaman.")); }
    finally { setBusy(false); }
  }

  return (
    <div className="modal-overlay" data-testid="loan-create-modal"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 560, width: "95vw" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <Banknote size={16} className="text-[#0058CC]" />
          <h2 className="text-[14px] font-bold">Pinjaman Uang Antar-PT</h2>
        </div>
        <div className="space-y-3 p-4">
          {err && <div className="notice-bar danger" data-testid="loan-create-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#4A4B53]">PT Pemberi (piutang) *</label>
              <KNSelect data-testid="loan-lender" className="field" value={lender}
                onValueChange={setLender} options={opts} placeholder="Pilih badan usaha…" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#4A4B53]">PT Penerima (utang) *</label>
              <KNSelect data-testid="loan-borrower" className="field" value={borrower}
                onValueChange={setBorrower} options={opts} placeholder="Pilih badan usaha…" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#4A4B53]">Jumlah Pinjaman *</label>
              <input data-testid="loan-principal" type="number" className="field"
                value={principal} onChange={(e) => setPrincipal(e.target.value)} placeholder="0" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#4A4B53]">Rencana Kembali</label>
              <input data-testid="loan-return-date" type="date" className="field"
                value={returnDate} onChange={(e) => setReturnDate(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#4A4B53]">Tujuan Pinjaman *</label>
            <input data-testid="loan-purpose" className="field" value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="mis. menutup kebutuhan modal kerja bulan ini" />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#4A4B53]">
              Catatan Bunga / Biaya <span className="font-normal text-[#9A9BA3]">(tidak dihitung sistem)</span>
            </label>
            <input data-testid="loan-interest-note" className="field" value={interestNote}
              onChange={(e) => setInterestNote(e.target.value)}
              placeholder="mis. tanpa bunga · atau 1%/bulan dibayar saat pelunasan" />
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="btn-secondary" onClick={onClose}>Batal</button>
          <button data-testid="loan-create-submit" className="btn-primary" disabled={busy} onClick={submit}>
            {busy ? "Menyimpan…" : "Simpan sebagai Draf"}
          </button>
        </div>
      </div>
    </div>
  );
}
