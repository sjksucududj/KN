/**
 * SpecDetailPanel (FASE F · PS-12) — detail spesifikasi + aksi alur:
 * ajukan → ACC (produk lahir) → rilis ke produksi (barang boleh dijual) — atau tolak.
 * Menampilkan permintaan sample turunannya supaya rantai R&D terlihat utuh.
 */
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, FlaskConical, Rocket, Send, X, XCircle } from "lucide-react";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { approveSpec, getSpec, rejectSpec, releaseProduct, submitSpec } from "./rndApi";
import { errMsg, lifecycleMeta, SAMPLE_STATUS_META, SAMPLE_TYPE_LABEL, SPEC_STATUS_META } from "./rndMeta";

export default function SpecDetailPanel({ specId, currentUser, onClose, onChanged }) {
  const [spec, setSpec] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [reason, setReason] = useState("");

  const role = currentUser?.role;
  const canApprove = ["admin", "manager"].includes(role);

  const load = useCallback(async () => {
    try {
      const d = await getSpec(specId);
      setSpec(d);
      setSku(d.sku_hint || "");
      setName(d.title || "");
      setPrice(String(d.target_price || ""));
      setErr("");
    } catch (e) { setErr(errMsg(e, "Gagal memuat spesifikasi.")); }
  }, [specId]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, okMsg) => {
    setBusy(true); setErr("");
    try {
      await fn();
      await load();
      onChanged?.();
      if (okMsg) setErr("");
    } catch (e) { setErr(errMsg(e, "Aksi gagal dijalankan.")); } finally { setBusy(false); }
  };

  const meta = SPEC_STATUS_META[spec?.status] || SPEC_STATUS_META.draft;
  const life = lifecycleMeta(spec?.lifecycle);

  return (
    <div data-testid="spec-detail-panel"
      className="fixed inset-0 z-[168] flex items-center justify-center bg-black/50 p-4"
      {...overlayDismiss(onClose)}>
      <div className="flex max-h-[94vh] w-full max-w-[880px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-[15px] font-bold">
              <FlaskConical size={16} className="text-[#0058CC]" />
              <span data-testid="spec-detail-number">{spec?.number || "…"}</span>
              <span className={`status-pill ${meta.cls}`}
                data-testid="spec-detail-status">{meta.label}</span>
            </h2>
            <p className="truncate text-[11.5px] text-[#6B6B73]">{spec?.title}</p>
          </div>
          <button className="icon-button" onClick={onClose} data-testid="spec-detail-close">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {err && (
            <div className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]"
              data-testid="spec-detail-error">{err}</div>
          )}

          <div className="grid gap-2 md:grid-cols-4">
            <Box label="Tahap produk" value={life.label} tone={life.tone}
              testId="spec-detail-lifecycle" />
            <Box label="Jenis kain / tahap bahan"
              value={`${spec?.target?.fabric_type || "—"} · ${spec?.target?.stage || "—"}`} />
            <Box label="Gramasi / lebar"
              value={`${formatQty(spec?.target?.gramasi || 0)} gsm · ${formatQty(spec?.target?.lebar || 0)} cm`} />
            <Box label="Target harga" value={formatCurrency(spec?.target_price || 0)} />
          </div>

          <div className="grid gap-2 md:grid-cols-3">
            <Box label="Warna target"
              value={`${spec?.color_target?.name || "—"}${spec?.color_target?.code ? ` (${spec.color_target.code})` : ""}`}
              swatch={spec?.color_target?.hex} />
            <Box label="Desain / pattern"
              value={spec?.design_code ? `${spec.design_code} v${spec.design_version || 1}` : "—"} />
            <Box label="Rencana sample"
              value={SAMPLE_TYPE_LABEL[spec?.sample_type_hint] || "—"} />
          </div>

          {spec?.product && (
            <div className="rounded-lg border border-[#EFF0F2] p-3" data-testid="spec-detail-product">
              <p className="mb-1 text-[10.5px] font-bold uppercase text-[#8E8E93]">
                Produk hasil persetujuan
              </p>
              <p className="text-[12.5px] font-semibold">
                {spec.product.sku} — {spec.product.name}
              </p>
              <p className="text-[11px]" style={{ color: lifecycleMeta(spec.product.lifecycle).tone }}>
                Tahap: <b>{lifecycleMeta(spec.product.lifecycle).label}</b>
                {lifecycleMeta(spec.product.lifecycle).sellable
                  ? " — sudah boleh dipesan & dijual"
                  : " — BELUM boleh dipesan/dijual"}
              </p>
            </div>
          )}

          {(spec?.samples || []).length > 0 && (
            <div className="rounded-lg border border-[#EFF0F2]" data-testid="spec-detail-samples">
              <p className="border-b border-[#EFF0F2] px-3 py-1.5 text-[10.5px] font-bold uppercase text-[#8E8E93]">
                Permintaan sample dari spesifikasi ini
              </p>
              <div className="divide-y divide-[#F4F5F7]">
                {spec.samples.map((s) => {
                  const sm = SAMPLE_STATUS_META[s.status] || SAMPLE_STATUS_META.draft;
                  return (
                    <div key={s.id} className="flex items-center justify-between px-3 py-2">
                      <span className="text-[11.5px] font-semibold">{s.number}</span>
                      <span className="text-[11px] text-[#6B6B73]">
                        {SAMPLE_TYPE_LABEL[s.sample_type] || s.sample_type} ·
                        {" "}{(s.participants || []).length} supplier ·
                        {" "}{(s.rounds || []).length} round
                      </span>
                      <span className={`status-pill ${sm.cls}`}>{sm.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {spec?.status === "review" && canApprove && (
            <div className="rounded-lg border border-[#D9E8FF] bg-[#F7FBFF] p-3"
              data-testid="spec-approve-form">
              <p className="mb-2 text-[11.5px] font-semibold text-[#004099]">
                Setujui spesifikasi → produk baru akan lahir (belum boleh dijual)
              </p>
              <div className="grid gap-2 md:grid-cols-3">
                <label className="block">
                  <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">Kode SKU</span>
                  <input className="field" data-testid="spec-approve-sku" value={sku}
                    onChange={(e) => setSku(e.target.value)} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">Nama produk</span>
                  <input className="field" data-testid="spec-approve-name" value={name}
                    onChange={(e) => setName(e.target.value)} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">Harga jual (Rp)</span>
                  <input className="field" data-testid="spec-approve-price" value={price}
                    onChange={(e) => setPrice(e.target.value)} />
                </label>
              </div>
            </div>
          )}

          {(spec?.timeline || []).length > 0 && (
            <div className="rounded-lg border border-[#EFF0F2] p-3" data-testid="spec-detail-timeline">
              <p className="mb-1.5 text-[10.5px] font-bold uppercase text-[#8E8E93]">Riwayat</p>
              <ul className="space-y-1">
                {spec.timeline.slice().reverse().map((t, i) => (
                  <li key={i} className="text-[11px] text-[#3C3C43]">
                    <b>{t.label}</b>
                    {t.actor ? ` · ${t.actor}` : ""}
                    {t.note ? ` — ${t.note}` : ""}
                    <span className="text-[#9A9BA3]"> · {String(t.at || "").slice(0, 16).replace("T", " ")}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          {spec?.status === "draft" && (
            <button className="primary-button" disabled={busy} data-testid="spec-submit-button"
              onClick={() => act(() => submitSpec(spec.id))}>
              <Send size={13} /> Ajukan untuk ACC
            </button>
          )}
          {spec?.status === "review" && canApprove && (
            <>
              <input className="field max-w-[220px]" placeholder="Alasan penolakan…"
                data-testid="spec-reject-reason" value={reason}
                onChange={(e) => setReason(e.target.value)} />
              <button className="secondary-button" disabled={busy || reason.trim().length < 3}
                data-testid="spec-reject-button"
                onClick={() => act(() => rejectSpec(spec.id, reason))}>
                <XCircle size={13} /> Tolak
              </button>
              <button className="primary-button" disabled={busy} data-testid="spec-approve-button"
                onClick={() => act(() => approveSpec(spec.id, {
                  sku, name, price: price || 0, note: "",
                }))}>
                <CheckCircle2 size={13} /> Setujui & buat produk
              </button>
            </>
          )}
          {spec?.status === "approved" && spec?.lifecycle !== "produksi" && canApprove && (
            <button className="primary-button" disabled={busy} data-testid="spec-release-button"
              onClick={() => act(() => releaseProduct(spec.id,
                "Sample sudah ACC & kontrak harga siap"))}>
              <Rocket size={13} /> Rilis ke produksi (boleh dijual)
            </button>
          )}
          <button className="secondary-button" onClick={onClose}>Tutup</button>
        </div>
      </div>
    </div>
  );
}

function Box({ label, value, tone = "#1C1C1E", swatch, testId }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2" data-testid={testId}>
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="flex items-center gap-1.5 text-[12px] font-bold leading-tight"
        style={{ color: tone }}>
        {swatch && (
          <span className="inline-block h-3.5 w-3.5 rounded-full border border-[#E5E5EA]"
            style={{ background: swatch }} />
        )}
        {value}
      </p>
    </div>
  );
}
