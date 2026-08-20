/** R2/R3/R4 — Panel karantina roll retur.
 *  R2: roll retur masuk karantina; manager release ke stok (available) atau scrap (damaged).
 *  R3: tampilkan KEPEMILIKAN (owner entity) vs LOKASI (warehouse) terpisah (SSOT);
 *      REGRADE grade final A/B/C saat release; dan aksi TRANSFER KEPEMILIKAN lintas-PT
 *      (GL-safe inter-entity) untuk roll yang sudah 'available'.
 *  R4: teruskan barang cacat ke SUPPLIER (buat Retur Beli tertaut) — hormati kebijakan impor. */
import { useState, useEffect, useCallback } from "react";
import axios, { API } from "../../services/apiClient";
import {
  ShieldAlert, Loader2, PackageCheck, Building2, MapPin, ArrowLeftRight, X, CheckCircle2, Store, Link2, FileMinus, RotateCcw,
} from "lucide-react";
import { fmtNum } from "./ReturnShared";
import KNSelect from "../../components/KNSelect";
import useDomainEnums from "../../hooks/useDomainEnums";

const STATUS_PILL = {
  quarantine: { cls: "pill-warning", label: "Karantina" },
  available: { cls: "pill-success", label: "Tersedia" },
  damaged: { cls: "pill-danger", label: "Scrap/Rusak" },
  reserved: { cls: "pill-muted", label: "Direservasi" },
  returned_supplier: { cls: "pill-muted", label: "Diretur ke Supplier" },
};
// Fase A · PS-09/R7 — daftar grade DIAMBIL dari registry (`/api/enums`), bukan
// konstanta lokal; A/B/C lama sudah tidak sah (enum resmi: A|A1|A2|B|BS).

export default function ReturnQuarantinePanel({ ret, canApprove, onReleased, onNavigate }) {
  const { options: enumOptions } = useDomainEnums();
  const gradeOptions = enumOptions("grade");
  const [rolls, setRolls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [decisionMap, setDecisionMap] = useState({});   // roll_id -> {scrap, grade}
  const [entities, setEntities] = useState([]);
  const [xferRoll, setXferRoll] = useState(null);        // roll object being transferred
  const [xferDest, setXferDest] = useState("");
  const [xferBusy, setXferBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  // R4 — teruskan ke supplier (retur beli)
  const [suppliers, setSuppliers] = useState([]);
  const [linkedPR, setLinkedPR] = useState(ret.linked_purchase_return_number || "");
  const [showSupRet, setShowSupRet] = useState(false);
  const [supRetSupplier, setSupRetSupplier] = useState("");
  const [supRetBusy, setSupRetBusy] = useState(false);
  // R5.4b — reversal write-off (un-scrap): kembalikan roll damaged ke stok
  const [unscrapRoll, setUnscrapRoll] = useState(null);
  const [unscrapReason, setUnscrapReason] = useState("");
  const [unscrapBusy, setUnscrapBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/sales-returns/${ret.id}/quarantine`);
      const list = Array.isArray(res.data) ? res.data : [];
      setRolls(list);
      // inisialisasi keputusan release: grade = grade roll saat ini, scrap=false
      setDecisionMap((prev) => {
        const next = { ...prev };
        list.forEach((r) => {
          if (r.status === "quarantine" && !next[r.id]) next[r.id] = { scrap: false, grade: r.grade || "A" };
        });
        return next;
      });
    } catch { setRolls([]); } finally { setLoading(false); }
  }, [ret.id]);

  useEffect(() => { load(); }, [load]);

  // R3 — daftar entitas untuk transfer kepemilikan; R4 — daftar supplier untuk retur beli
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [eRes, sRes] = await Promise.all([
          axios.get(`${API}/entities`).catch(() => ({ data: [] })),
          axios.get(`${API}/suppliers`).catch(() => ({ data: [] })),
        ]);
        if (!active) return;
        setEntities(Array.isArray(eRes.data) ? eRes.data : (eRes.data?.items || []));
        setSuppliers(Array.isArray(sRes.data) ? sRes.data : (sRes.data?.items || []));
      } catch { /* noop */ }
    })();
    return () => { active = false; };
  }, []);

  const pending = rolls.filter((r) => r.status === "quarantine");
  // R4 — roll kandidat untuk diteruskan ke supplier (masih dimiliki KN & belum diretur)
  const supplierCandidates = rolls.filter((r) => ["quarantine", "available"].includes(r.status));
  const setDec = (id, patch) => setDecisionMap((m) => ({ ...m, [id]: { ...m[id], ...patch } }));

  async function submitSupplierReturn() {
    setSupRetBusy(true); setErr(null);
    try {
      const body = { notes: "Barang cacat dari retur jual" };
      if (supRetSupplier) body.supplier_id = supRetSupplier;
      const res = await axios.post(`${API}/sales-returns/${ret.id}/create-purchase-return`, body);
      setLinkedPR(res.data?.number || "");
      setMsg(`Retur beli ${res.data?.number || ""} dibuat & ditautkan (ke supplier ${res.data?.supplier_name || ""}). Lanjutkan RMA di modul Retur Beli.`);
      setShowSupRet(false);
      await load();
      onReleased && onReleased();
    } catch (e) {
      setErr("Gagal buat retur beli: " + (e.response?.data?.detail || e.message));
    } finally { setSupRetBusy(false); }
  }

  async function release() {
    setBusy(true); setErr(null);
    try {
      const decisions = pending.map((r) => {
        const d = decisionMap[r.id] || {};
        return { roll_id: r.id, action: d.scrap ? "scrap" : "release", grade: d.grade || r.grade || "A" };
      });
      const res = await axios.post(`${API}/sales-returns/${ret.id}/quarantine/release`, { decisions, notes: "" });
      const sum = res.data?._release_summary || {};
      const woTxt = sum.writeoff_total ? `, write-off GL Rp${Number(sum.writeoff_total).toLocaleString("id-ID")}` : "";
      setMsg(`Release selesai — ${sum.released || 0} ke stok, ${sum.scrapped || 0} scrap, ${sum.regraded || 0} regrade${woTxt}.`);
      await load();
      onReleased && onReleased();
    } catch (e) {
      setErr("Gagal release: " + (e.response?.data?.detail || e.message));
    } finally { setBusy(false); }
  }

  function openTransfer(roll) {
    setXferRoll(roll);
    const other = entities.find((e) => e.id !== roll.owner_entity_id);
    setXferDest(other ? other.id : "");
    setErr(null);
  }

  async function submitTransfer() {
    if (!xferRoll || !xferDest) return;
    setXferBusy(true); setErr(null);
    try {
      const res = await axios.post(
        `${API}/sales-returns/${ret.id}/rolls/${xferRoll.id}/transfer-ownership`,
        { dest_entity_id: xferDest, notes: "Transfer kepemilikan roll retur" });
      const je = res.data?.je || {};
      const destName = entities.find((e) => e.id === xferDest)?.short_name || xferDest;
      setMsg(`Kepemilikan roll dipindah ke ${destName}. Jurnal inter-company ${je.posted ? "terposting" : "—"}${je.pair_id ? ` (pair ${String(je.pair_id).slice(-6)})` : ""}.`);
      setXferRoll(null); setXferDest("");
      await load();
      onReleased && onReleased();
    } catch (e) {
      setErr("Gagal transfer kepemilikan: " + (e.response?.data?.detail || e.message));
    } finally { setXferBusy(false); }
  }

  // R5.4b — batalkan write-off (un-scrap): roll damaged → available + balik jurnal write-off.
  async function submitUnscrap() {
    if (!unscrapRoll || !unscrapReason.trim()) return;
    setUnscrapBusy(true); setErr(null);
    try {
      const res = await axios.post(`${API}/sales-returns/${ret.id}/reverse-writeoff`,
        { roll_ids: [unscrapRoll.id], reason: unscrapReason.trim() });
      const sum = res.data?._writeoff_reversal_summary || {};
      setMsg(`Write-off dibatalkan — ${sum.rolls || 1} roll dikembalikan ke stok (jurnal write-off dibalik, GL persediaan pulih).`);
      setUnscrapRoll(null); setUnscrapReason("");
      await load();
      onReleased && onReleased();
    } catch (e) {
      setErr("Gagal batalkan write-off: " + (e.response?.data?.detail || e.message));
    } finally { setUnscrapBusy(false); }
  }

  if (!loading && rolls.length === 0) return null;

  // E9.3 — barang yang berasal dari PEMBELIAN INTERNAL tidak boleh dikembalikan lewat
  // pindah kepemilikan harga pokok: jalur itu tidak memperbarui jumlah yang sudah
  // diretur pada transaksi asal, tidak membalik PPN, dan tidak memperbarui eliminasi
  // margin. Tombolnya diganti tuntunan ke Retur Antar-PT (satu jalan untuk satu peristiwa).
  const canTransfer = (r) => canApprove && r.status === "available"
    && entities.length > 1 && !r.ownership_transfer_blocked;

  return (
    <div className="section-card" data-testid="quarantine-panel">
      <div className="section-header flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5"><ShieldAlert size={14} /> Karantina Roll Retur (Ownership vs Lokasi)</span>
        <span className="flex items-center gap-2">
          {linkedPR ? (
            <span data-testid="linked-purchase-return" className="inline-flex items-center gap-1 rounded border border-[#E4D4F0] bg-[#FBF5FF] px-2 py-0.5 text-[10.5px] font-semibold text-[#6B219A]">
              <Link2 size={11} /> Retur Beli: {linkedPR}
            </span>
          ) : (canApprove && supplierCandidates.length > 0 && (
            <button data-testid="create-supplier-return-btn" className="secondary-button !py-1 !px-2 text-[11px]"
              onClick={() => setShowSupRet(true)} title="Teruskan barang cacat ke supplier (buat Retur Beli tertaut)">
              <Store size={12} /> Teruskan ke Supplier
            </button>
          ))}
        </span>
      </div>

      {msg && (
        <div className="notice-bar success" data-testid="quarantine-msg" style={{ marginBottom: 8 }}>
          <CheckCircle2 size={13} /> {msg}<button onClick={() => setMsg(null)}><X size={11} /></button>
        </div>
      )}
      {err && (
        <div className="notice-bar danger" data-testid="quarantine-err" style={{ marginBottom: 8 }}>
          <X size={13} /> {err}<button onClick={() => setErr(null)}><X size={11} /></button>
        </div>
      )}

      {loading ? (
        <div className="py-6 text-center text-[12px] text-[#6B6B73]">Memuat roll karantina...</div>
      ) : (
        <>
          <div className="mb-1.5 text-[10.5px] text-[#5B6472] flex items-center gap-1" data-testid="quarantine-cost-basis-note">
            <FileMinus size={11} className="text-[#1B4F9C]" />
            Basis nilai roll = <b className="mx-0.5">WAC</b> (termasuk <b className="mx-0.5">landed cost</b> bila ada — freight/duty/handling). Roll impor ber-landed ditandai <span className="mx-0.5 rounded border border-[#CBD9F2] bg-[#F0F5FF] px-1 text-[9px] font-semibold text-[#1B4F9C]">incl. landed</span>.
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Roll</th><th>Produk</th><th>Panjang</th>
                <th>Owner (Pemilik)</th><th>Lokasi (Gudang)</th>
                <th>Grade</th><th>Status</th>
                {canApprove && <th>Aksi</th>}
              </tr>
            </thead>
            <tbody>
              {rolls.map((r) => {
                const sp = STATUS_PILL[r.status] || { cls: "pill-muted", label: r.status };
                const d = decisionMap[r.id] || {};
                const isQ = r.status === "quarantine";
                return (
                  <tr key={r.id} data-testid={`quarantine-roll-${r.id}`}>
                    <td className="font-mono text-[10.5px]">{r.roll_no}</td>
                    <td className="max-w-[150px] truncate" title={r.product_name || r.product_id}>
                      {r.product_name || r.product_id}
                      {r.landed_included && (
                        <span data-testid={`roll-cost-basis-${r.id}`}
                          className="ml-1 inline-flex items-center gap-0.5 rounded border border-[#CBD9F2] bg-[#F0F5FF] px-1 py-0 text-[9px] font-semibold text-[#1B4F9C] align-middle"
                          title={`Basis nilai (R5.5): WAC Rp${Number(r.unit_cost || 0).toLocaleString("id-ID")}/unit = dasar Rp${Number(r.base_unit_cost || 0).toLocaleString("id-ID")} + landed Rp${Number(r.landed_per_unit || 0).toLocaleString("id-ID")} (freight/duty/handling).`}>
                          incl. landed
                        </span>
                      )}
                    </td>
                    <td className="font-mono">{fmtNum(r.length_remaining ?? r.length)} m</td>
                    <td>
                      <span className="inline-flex items-center gap-1 text-[11px]" data-testid={`roll-owner-${r.id}`}>
                        <Building2 size={11} className="text-[#0058CC]" />
                        {r.owner_entity_name || r.owner_entity_id || "-"}
                      </span>
                    </td>
                    <td>
                      <span className="inline-flex items-center gap-1 text-[11px]" data-testid={`roll-location-${r.id}`}>
                        <MapPin size={11} className="text-[#6B6B73]" />
                        {r.warehouse_name || r.warehouse_id || "-"}
                      </span>
                    </td>
                    <td>
                      {isQ && canApprove ? (
                        <KNSelect data-testid={`regrade-${r.id}`} className="field" style={{ minWidth: 96 }}
                          value={d.grade || r.grade || "A"}
                          onValueChange={(v) => setDec(r.id, { grade: v })}
                          options={gradeOptions} />
                      ) : (
                        <span className="status-pill pill-muted" data-testid={`roll-grade-${r.id}`}>
                          {r.grade || "A"}{r.regraded_from ? ` (dari ${r.regraded_from})` : ""}
                        </span>
                      )}
                    </td>
                    <td><span className={`status-pill ${sp.cls}`}>{sp.label}</span>
                      {r.writeoff_je_number && (
                        <div className="mt-1 leading-tight">
                          <span data-testid={`writeoff-badge-${r.id}`}
                            className="inline-flex items-center gap-1 rounded border border-[#F3C9C7] bg-[#FDF2F2] px-1.5 py-0.5 text-[10px] font-semibold text-[#B4231F]"
                            title={`Jurnal write-off persediaan ${r.writeoff_je_number} (Dr 5-9500 / Cr 1-1300)`}>
                            <FileMinus size={10} /> Write-off {r.writeoff_je_number}
                          </span>
                          {r.writeoff_amount != null && (
                            <span className="ml-1 text-[10px] text-[#8A2A27]" data-testid={`writeoff-amt-${r.id}`}>
                              Rp{Number(r.writeoff_amount).toLocaleString("id-ID")}
                            </span>
                          )}
                        </div>
                      )}
                      {r.writeoff_reversed && (
                        <div className="mt-1 leading-tight">
                          <span data-testid={`unscrap-badge-${r.id}`}
                            className="inline-flex items-center gap-1 rounded border border-[#BFE3C8] bg-[#EFF9F1] px-1.5 py-0.5 text-[10px] font-semibold text-[#1F7A38]"
                            title={`Write-off dibatalkan${r.writeoff_reversal_je_number ? ` (jurnal balik ${r.writeoff_reversal_je_number})` : ""} — roll dikembalikan ke stok`}>
                            <RotateCcw size={10} /> Write-off dibatalkan
                          </span>
                        </div>
                      )}
                    </td>
                    {canApprove && (
                      <td>
                        {isQ && (
                          <label className="inline-flex items-center gap-1 text-[10.5px] text-[#B4231F]">
                            <input type="checkbox" data-testid={`quarantine-scrap-${r.id}`}
                              checked={!!d.scrap} onChange={(e) => setDec(r.id, { scrap: e.target.checked })} />
                            Scrap
                          </label>
                        )}
                        {canTransfer(r) && (
                          <button data-testid={`transfer-ownership-${r.id}`} className="link-button"
                            onClick={() => openTransfer(r)} title="Pindah kepemilikan ke PT lain (GL-safe)">
                            <ArrowLeftRight size={12} /> Transfer Kepemilikan
                          </button>
                        )}
                        {r.ownership_transfer_blocked && r.status === "available" && (
                          <div data-testid={`interco-return-hint-${r.id}`}
                               className="mt-1 rounded border border-[#BDE5CC] bg-[#F2FBF6] px-1.5 py-1 text-[10px] leading-snug text-[#0F6B52]">
                            <b>Asal pembelian internal {r.interco_origin?.number || ""}</b>
                            {r.interco_origin?.seller_entity_name
                              ? ` dari ${r.interco_origin.seller_entity_name}` : ""}.
                            Kembalikan lewat <b>Retur Antar-PT</b> — jalur pindah kepemilikan
                            harga pokok tidak membalik PPN, tidak mengurangi utang antar-PT,
                            dan tidak memperbarui eliminasi margin.
                            <button data-testid={`goto-interco-return-${r.id}`}
                                    className="link-button mt-0.5"
                                    onClick={() => onNavigate?.("interco-transactions")}>
                              <ArrowLeftRight size={11} /> Buka Retur Antar-PT
                            </button>
                          </div>
                        )}
                        {r.status === "damaged" && r.writeoff_je_number && !r.writeoff_reversed && (
                          <button data-testid={`unscrap-btn-${r.id}`} className="link-button" style={{ color: "#B4231F" }}
                            onClick={() => { setUnscrapReason(""); setErr(null); setUnscrapRoll(r); }}
                            title="Batalkan write-off & kembalikan roll ke stok (balik jurnal)">
                            <RotateCcw size={12} /> Batalkan Write-off
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>

          {canApprove && pending.length > 0 && (
            <button data-testid="release-quarantine-btn" className="primary-button mt-2" onClick={release} disabled={busy}>
              {busy ? <Loader2 size={13} className="spin" /> : <PackageCheck size={13} />}
              Release {pending.length} Roll (grade final / scrap)
            </button>
          )}
          {pending.length === 0 && rolls.length > 0 && (
            <div className="text-[11px] text-[#3B8C4D] mt-1 flex items-center gap-1">
              <PackageCheck size={12} /> Semua roll karantina sudah diproses.
            </div>
          )}
        </>
      )}

      {/* R3 — modal transfer kepemilikan lintas-PT */}
      {xferRoll && (
        <div className="modal-overlay" data-testid="transfer-ownership-modal">
          <div className="modal-card small">
            <div className="flex items-center justify-between mb-1">
              <h3 className="modal-title">Transfer Kepemilikan Roll</h3>
              <button className="icon-button" onClick={() => setXferRoll(null)}><X size={15} /></button>
            </div>
            <p className="modal-subtitle">
              Roll <b>{xferRoll.roll_no}</b> ({fmtNum(xferRoll.length_remaining ?? xferRoll.length)} m) —
              lokasi fisik <b>{xferRoll.warehouse_name || xferRoll.warehouse_id}</b> tetap. Pindah kepemilikan
              dari <b>{xferRoll.owner_entity_name || xferRoll.owner_entity_id}</b> ke PT tujuan (jurnal inter-company GL-safe).
            </p>
            <label className="form-label mt-2">Entitas Tujuan</label>
            <KNSelect className="field w-full" data-testid="transfer-dest-entity"
              value={xferDest} placeholder="— Pilih PT tujuan —" onValueChange={setXferDest}
              options={entities.filter((e) => e.id !== xferRoll.owner_entity_id)
                .map((e) => ({ value: e.id, label: e.short_name || e.legal_name || e.id }))} />
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => setXferRoll(null)}>Batal</button>
              <button data-testid="confirm-transfer-ownership-btn" className="primary-button"
                disabled={xferBusy || !xferDest} onClick={submitTransfer}>
                {xferBusy ? <Loader2 size={13} className="spin" /> : <ArrowLeftRight size={13} />} Pindahkan
              </button>
            </div>
          </div>
        </div>
      )}

      {/* R4 — modal buat Retur Beli (teruskan barang cacat ke supplier) */}
      {showSupRet && (
        <div className="modal-overlay" data-testid="supplier-return-modal">
          <div className="modal-card small">
            <div className="flex items-center justify-between mb-1">
              <h3 className="modal-title">Teruskan ke Supplier (Retur Beli)</h3>
              <button className="icon-button" onClick={() => setShowSupRet(false)}><X size={15} /></button>
            </div>
            <p className="modal-subtitle">
              Membuat <b>Retur Beli</b> tertaut dari {supplierCandidates.length} roll retur (karantina/tersedia).
              Alur RMA supplier (kirim → terima/tolak → barang kembali) dikelola di modul <b>Retur Beli</b>.
              Barang <b>impor tak-returnable</b> akan ditolak (rekomendasi regrade + jual lokal).
            </p>
            <label className="form-label mt-2">Supplier Tujuan</label>
            <KNSelect className="field w-full" data-testid="supplier-return-supplier"
              value={supRetSupplier} placeholder="Otomatis (dari PO terakhir produk)"
              onValueChange={setSupRetSupplier}
              options={[{ value: "", label: "Otomatis (dari PO terakhir produk)" },
                ...suppliers.map((s) => ({ value: s.id,
                  label: `${s.name}${s.origin_type === "import" ? " · Impor" : ""}` }))]} />
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => setShowSupRet(false)}>Batal</button>
              <button data-testid="confirm-supplier-return-btn" className="primary-button"
                disabled={supRetBusy} onClick={submitSupplierReturn}>
                {supRetBusy ? <Loader2 size={13} className="spin" /> : <Store size={13} />} Buat Retur Beli
              </button>
            </div>
          </div>
        </div>
      )}

      {/* R5.4b — modal batalkan write-off (un-scrap) roll */}
      {unscrapRoll && (
        <div className="modal-overlay" data-testid="unscrap-modal"
          onClick={(e) => { if (e.target === e.currentTarget) setUnscrapRoll(null); }}>
          <div className="modal-card small">
            <div className="flex items-center justify-between mb-1">
              <h3 className="modal-title flex items-center gap-1.5"><RotateCcw size={15} /> Batalkan Write-off Roll</h3>
              <button className="icon-button" onClick={() => setUnscrapRoll(null)}><X size={15} /></button>
            </div>
            <p className="modal-subtitle">
              Roll <b>{unscrapRoll.roll_no}</b> ({fmtNum(unscrapRoll.length_remaining ?? unscrapRoll.length)} m) akan
              <b> dikembalikan ke stok (tersedia)</b> dan jurnal write-off
              {unscrapRoll.writeoff_je_number ? <> <b>{unscrapRoll.writeoff_je_number}</b></> : null} dibalik
              (<b>Dr 1-1300 / Cr 5-9500</b>). Nilai persediaan GL dipulihkan.
            </p>
            <label className="form-label mt-2">Alasan pembatalan</label>
            <textarea data-testid="unscrap-reason" className="textarea" rows={3}
              placeholder="mis. salah scrap / roll masih layak jual..."
              value={unscrapReason} onChange={(e) => setUnscrapReason(e.target.value)} />
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => { setUnscrapRoll(null); setUnscrapReason(""); }}>Batal</button>
              <button data-testid="unscrap-submit" className="danger-button"
                disabled={!unscrapReason.trim() || unscrapBusy} onClick={submitUnscrap}>
                {unscrapBusy ? <Loader2 size={13} className="spin" /> : <RotateCcw size={13} />} Kembalikan ke Stok
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
