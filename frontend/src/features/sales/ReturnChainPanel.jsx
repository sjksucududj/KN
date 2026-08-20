/**
 * ReturnChainPanel (FASE E-9 · E9.6 · user story 29)
 * ---------------------------------------------------
 * Menjawab satu pertanyaan yang dulu tidak bisa dijawab layar mana pun:
 * **"kain yang diretur pelanggan itu akhirnya ke mana?"**
 *
 * Rantainya bisa tiga tingkat — retur pelanggan → retur antar-PT → retur ke supplier
 * (atau disimpan sendiri oleh badan usaha penerima). Panel ini sengaja diletakkan DI
 * DALAM dokumen retur (bukan layar terpisah) supaya tidak ada jalan buntu: dari
 * dokumen mana pun dalam rantai, pengguna melihat rantai yang sama.
 *
 * Sumber: GET /api/returns/chain/{docId} — read-only.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertCircle, ArrowRight, Boxes, Building2, EyeOff, Loader2, Route } from "lucide-react";
import axios, { API } from "../../services/apiClient";

const STAGE_TONE = {
  sales_return: "border-[#F5C9A6] bg-[#FFF7EF] text-[#8C4A00]",
  interco_return: "border-[#BDE5CC] bg-[#F2FBF6] text-[#0F6B52]",
  purchase_return: "border-[#CBD9F5] bg-[#F3F7FF] text-[#123E8C]",
  kept: "border-[#E5E5EA] bg-[#F7F7F9] text-[#3C3C43]",
};

function fmtQty(n) {
  const v = Number(n || 0);
  return Number.isFinite(v) ? v.toLocaleString("id-ID", { maximumFractionDigits: 2 }) : "0";
}

export default function ReturnChainPanel({ docId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    if (!docId) return;
    setLoading(true);
    setErr("");
    try {
      const res = await axios.get(`${API}/returns/chain/${docId}`);
      setData(res.data);
    } catch (e) {
      setErr(e.response?.data?.detail || e.message || "Gagal memuat jejak retur");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="section-card" data-testid="return-chain-loading">
        <div className="section-header inline-flex items-center gap-1.5">
          <Route size={14} /> Jejak Retur
        </div>
        <div className="flex items-center gap-2 text-[11.5px] text-[#6E6E73] px-1 py-2">
          <Loader2 size={13} className="spin" /> Menyusun rantai retur…
        </div>
      </div>
    );
  }

  if (err) {
    return (
      <div className="section-card" data-testid="return-chain-error">
        <div className="section-header inline-flex items-center gap-1.5">
          <Route size={14} /> Jejak Retur
        </div>
        <div className="flex items-start gap-1.5 text-[11.5px] text-[#B4231F] px-1 py-2">
          <AlertCircle size={13} className="mt-0.5 shrink-0" /> {err}
        </div>
      </div>
    );
  }

  const steps = data?.steps || [];
  const rolls = data?.rolls || [];

  return (
    <div className="section-card" data-testid="return-chain-panel">
      <div className="section-header flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5"><Route size={14} /> Jejak Retur</span>
        <span data-testid="return-chain-complete"
              className={`text-[10px] rounded px-2 py-0.5 border ${
                data?.complete
                  ? "border-[#BDE5CC] bg-[#F2FBF6] text-[#0F6B52]"
                  : "border-[#EFD9A8] bg-[#FFF3DC] text-[#9A6700]"}`}>
          {data?.complete ? "Rantai lengkap" : "Rantai belum tuntas"}
        </span>
      </div>

      <p className="text-[11px] text-[#6E6E73] px-1 mb-2" data-testid="return-chain-summary">
        {data?.summary || "Belum ada jejak."}
      </p>

      {steps.length === 0 && (
        <div className="px-1 py-3 text-[11.5px] text-[#8E8E93]" data-testid="return-chain-empty">
          Belum ada dokumen lanjutan. Kalau barangnya berasal dari pembelian internal,
          kembalikan lewat <b>Retur Antar-PT</b>; kalau dari supplier, lewat <b>Retur Beli</b>.
        </div>
      )}

      <ol className="space-y-1.5">
        {steps.map((s, i) => (
          <li key={`${s.stage}-${s.doc_id || i}`}
              data-testid={`return-chain-step-${s.stage}-${s.doc_id || i}`}
              className={`rounded-md border px-2.5 py-2 ${STAGE_TONE[s.stage] || STAGE_TONE.kept}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide">
                {i + 1}. {s.stage_label}
                {s.number ? <b className="font-mono normal-case">{s.number}</b> : null}
              </span>
              <span className="text-[10px] shrink-0 inline-flex items-center gap-1">
                {s.redacted && (
                  <span data-testid={`return-chain-redacted-${s.doc_id || i}`}
                        className="inline-flex items-center gap-1 rounded border border-[#E5E5EA] bg-white px-1.5 py-0.5 text-[9.5px] text-[#6E6E73]"
                        title="Dokumen milik badan usaha lain — hanya ringkasannya yang boleh tampil">
                    <EyeOff size={9} /> ringkasan
                  </span>
                )}
                {s.status ? s.status : ""}{s.date ? ` · ${String(s.date).slice(0, 10)}` : ""}
              </span>
            </div>
            <div className="mt-0.5 text-[11px] leading-snug">
              {s.entity_name && (
                <span className="inline-flex items-center gap-1 mr-1">
                  <Building2 size={10} /> {s.entity_name}
                </span>
              )}
              {s.party && (
                <span className="inline-flex items-center gap-1 mr-1">
                  <ArrowRight size={10} /> {s.party}
                </span>
              )}
              {s.note}
              {s.counterpart_number ? ` · dokumen kembar ${s.counterpart_number}` : ""}
              {s.warehouse_transfer_code
                ? ` · tugas gudang ${s.warehouse_transfer_code}`
                  + (s.warehouse_transfer_status ? ` (${s.warehouse_transfer_status})` : "")
                : ""}
            </div>
          </li>
        ))}
      </ol>

      {rolls.length > 0 && (
        <div className="mt-2.5">
          <div className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93] mb-1 inline-flex items-center gap-1">
            <Boxes size={11} /> Barangnya sekarang
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]" data-testid="return-chain-rolls">
              <thead className="bg-[#FAFBFC] text-[10px] uppercase text-[#8E8E93]">
                <tr>
                  <th className="text-left px-2 py-1.5">Roll / Lot</th>
                  <th className="text-left px-2 py-1.5">Grade</th>
                  <th className="text-right px-2 py-1.5">Jumlah</th>
                  <th className="text-left px-2 py-1.5">Status</th>
                  <th className="text-left px-2 py-1.5">Pemilik</th>
                  <th className="text-left px-2 py-1.5">Asal</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#F2F2F5]">
                {rolls.map((r) => (
                  <tr key={r.roll_id} data-testid={`return-chain-roll-${r.roll_id}`}>
                    <td className="px-2 py-1.5">
                      <span className="font-medium">
                        {r.roll_no || (r.redacted ? "—" : r.roll_id)}
                      </span>
                      <span className="block text-[10px] font-mono text-[#9A9BA3]">
                        {r.lot || (r.redacted ? "detail milik badan usaha lain" : "")}
                      </span>
                    </td>
                    <td className="px-2 py-1.5">{r.grade || "—"}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">
                      {fmtQty(r.qty)} {r.unit}
                    </td>
                    <td className="px-2 py-1.5">{r.status}</td>
                    <td className="px-2 py-1.5">{r.owner_entity_name || "—"}</td>
                    <td className="px-2 py-1.5 text-[10px] text-[#6E6E73]">
                      {r.supplier_name ? `${r.supplier_name}` : ""}
                      {r.po_number ? ` · ${r.po_number}` : ""}
                      {r.origin_interco_number ? ` · internal ${r.origin_interco_number}` : ""}
                      {!r.supplier_name && !r.po_number && !r.origin_interco_number ? "—" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
