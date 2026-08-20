/**
 * IssueMaterialModal (FASE F · PS-19) — ambil bahan dari ROLL untuk membuat sample.
 * Stok gudang benar-benar berkurang (mutasi `sample_issue`) — tidak ada stok sample kedua.
 */
import { useEffect, useState } from "react";
import { PackageMinus, X } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { listRolls } from "./rndApi";
import { errMsg } from "./rndMeta";

export default function IssueMaterialModal({ onClose, onConfirm, busy }) {
  const [rolls, setRolls] = useState([]);
  const [rollId, setRollId] = useState("");
  const [qty, setQty] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    listRolls({ status: "available", limit: 300 })
      .then((r) => {
        const list = Array.isArray(r) ? r : r?.items || [];
        setRolls(list.filter((x) => Number(x.length_remaining || 0) > 0));
      })
      .catch((e) => setErr(errMsg(e, "Gagal memuat daftar roll.")));
  }, []);

  const roll = rolls.find((r) => r.id === rollId);

  return (
    <div data-testid="issue-material-modal"
      className="fixed inset-0 z-[176] flex items-center justify-center bg-black/50 p-4"
      {...overlayDismiss(onClose)}>
      <div className="flex max-h-[92vh] w-full max-w-[560px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            <PackageMinus size={16} className="text-[#B26A00]" /> Ambil Bahan untuk Sample
          </h2>
          <button className="icon-button" onClick={onClose} data-testid="issue-close">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-2.5 overflow-y-auto p-4">
          {err && (
            <div className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]">{err}</div>
          )}
          <div className="rounded-lg bg-[#FFF6E5] px-3 py-2 text-[11.5px] text-[#8C4A00]">
            Pengambilan ini <b>mengurangi stok gudang</b> (tercatat sebagai mutasi
            <b> Ambil Bahan Sample (R&D)</b>) dan biayanya masuk ke biaya sample serta dibebankan di
            buku besar (<b>Dr 6-7000 Beban Sample & Pengembangan / Cr 1-1300 Persediaan</b>).
            Stok sample dan stok gudang selalu <b>satu angka</b>.
          </div>
          <Field label="Roll sumber bahan *">
            <KNSelect data-testid="issue-roll" className="field" value={rollId}
              options={rolls.map((r) => ({
                value: r.id,
                label: `${r.roll_no} · ${r.product_name || r.product_id} · sisa `
                  + `${formatQty(r.length_remaining)} ${r.unit || "meter"}`,
              }))} onValueChange={setRollId} />
          </Field>
          <div className="grid gap-2.5 md:grid-cols-2">
            <Field label="Jumlah diambil *">
              <input className="field" data-testid="issue-qty" value={qty}
                onChange={(e) => setQty(e.target.value)} placeholder="3" />
            </Field>
            <Field label="Catatan">
              <input className="field" data-testid="issue-note" value={note}
                onChange={(e) => setNote(e.target.value)} placeholder="mis. swatch labdip" />
            </Field>
          </div>
          {roll && qty && (
            <p className="text-[11.5px] text-[#6B6B73]" data-testid="issue-impact">
              Sisa roll {roll.roll_no}: <b>{formatQty(roll.length_remaining)}</b> →{" "}
              <b>{formatQty(Math.max(Number(roll.length_remaining) - Number(qty || 0), 0))}</b>
              {" "}{roll.unit || "meter"}
              {roll.unit_cost
                ? ` · perkiraan biaya ${formatCurrency(Number(roll.unit_cost) * Number(qty || 0))}`
                : ""}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" data-testid="issue-confirm"
            disabled={busy || !rollId || !qty}
            onClick={() => onConfirm({ roll_id: rollId, qty, note })}>
            <PackageMinus size={13} /> {busy ? "Memproses…" : "Ambil bahan"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">{label}</span>
      {children}
    </label>
  );
}
