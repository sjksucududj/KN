/**
 * ImpactPicker — "DAFTAR DAMPAK" (blast-radius picker).
 *
 * Jawaban langsung untuk kekhawatiran pemilik:
 *   "kalau harga master saya koreksi, saya takut SEMUA invoice terpengaruh —
 *    padahal saya hanya ingin mengubah 1 dokumen itu."
 *
 * Alur di layar ini:
 *   1. pilih produk + harga baru → sistem menghitung dokumen terbuka yang terdampak
 *   2. DEFAULT: tidak ada yang tercentang (kecuali dokumen yang sedang dibuka)
 *   3. user mencentang sendiri mana yang ikut dikoreksi
 *   4. dokumen yang invoice-nya sudah terbit TIDAK PERNAH diubah → daftar terpisah
 *   5. setelah dijalankan, sistem MEMBUKTIKAN dokumen tak tercentang tidak berubah
 */
import { useEffect, useMemo, useState } from "react";
import {
  Search, ListChecks, AlertTriangle, ShieldCheck, FileWarning, Check, RefreshCw,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import KNSelect from "../../../components/KNSelect";
import { configApi, errMsg, idNum } from "./configApi";

const rp = (v) => `Rp ${idNum(v, 0)}`;

export default function ImpactPicker({ selectedEntity, canApply }) {
  const [products, setProducts] = useState([]);
  const [productId, setProductId] = useState("");
  const [newPrice, setNewPrice] = useState("");
  const [plan, setPlan] = useState(null);
  const [picked, setPicked] = useState([]);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/products`)
      .then((r) => {
        const arr = Array.isArray(r.data) ? r.data : (r.data?.items || []);
        if (alive) setProducts(arr);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const product = useMemo(
    () => products.find((p) => p.id === productId) || null, [products, productId]);

  const loadPlan = async () => {
    setErr(""); setResult(null); setBusy(true);
    try {
      const d = await configApi.impactPreview({
        product_id: productId, new_price: Number(newPrice),
        entity_id: selectedEntity && selectedEntity !== "all" ? selectedEntity : "",
      });
      setPlan(d);
      setPicked(d.default_selected || []);
    } catch (e) {
      setPlan(null);
      setErr(errMsg(e, "Gagal menghitung daftar dampak."));
    } finally { setBusy(false); }
  };

  const apply = async () => {
    setErr(""); setBusy(true);
    try {
      const d = await configApi.impactApply({
        product_id: productId, new_price: Number(newPrice), doc_ids: picked, reason,
        entity_id: selectedEntity && selectedEntity !== "all" ? selectedEntity : "",
      });
      setResult(d);
      await loadPlan();
    } catch (e) {
      setErr(errMsg(e, "Gagal menerapkan koreksi harga."));
    } finally { setBusy(false); }
  };

  const editable = plan?.editable_documents || [];
  const locked = plan?.locked_documents || [];
  const pickedRows = editable.filter((d) => picked.includes(d.doc_id));
  const pickedDelta = pickedRows.reduce((s, d) => s + Number(d.delta || 0), 0);
  const toggle = (id) =>
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <div className="cfg-impact" data-testid="cfg-impact-tool">
      <div className="cfg-impact-intro">
        <ListChecks size={18} />
        <div>
          <h3>Koreksi Harga Master — dengan Daftar Dampak</h3>
          <p>
            Harga master diperbaiki <b>tanpa</b> menyeret semua dokumen. Sistem menunjukkan
            dokumen mana saja yang bisa terpengaruh, lalu <b>Anda yang mencentang</b> mana yang
            ikut dikoreksi. Dokumen yang tidak dicentang dijamin tidak berubah.
          </p>
        </div>
      </div>

      <ErrorNotice message={err} onRetry={plan ? loadPlan : undefined} onDismiss={() => setErr("")} />

      <div className="cfg-impact-form">
        <label className="cfg-impact-field">
          <span>Produk</span>
          <KNSelect
            value={productId}
            onValueChange={(v) => { setProductId(v); setPlan(null); setResult(null); }}
            options={products.map((p) => ({ value: p.id, label: `${p.sku} — ${p.name}` }))}
            className="field"
            placeholder="Pilih produk…"
            searchable
            data-testid="cfg-impact-product"
          />
        </label>
        <label className="cfg-impact-field">
          <span>Harga sekarang</span>
          <input className="form-input" readOnly value={product ? rp(product.price) : "—"}
            data-testid="cfg-impact-current-price" />
        </label>
        <label className="cfg-impact-field">
          <span>Harga yang benar</span>
          <input className="form-input" type="number" min="1" value={newPrice}
            onChange={(e) => { setNewPrice(e.target.value); setPlan(null); setResult(null); }}
            placeholder="mis. 120000" data-testid="cfg-impact-new-price" />
        </label>
        <button className="btn-primary" disabled={!productId || !Number(newPrice) || busy}
          onClick={loadPlan} data-testid="cfg-impact-check">
          <Search size={14} /> {busy ? "Menghitung…" : "Lihat Daftar Dampak"}
        </button>
      </div>

      {plan ? (
        <>
          <div className="cfg-impact-summary" data-testid="cfg-impact-summary">
            <div>
              <span>Perubahan harga</span>
              <b>{rp(plan.price_now)} → {rp(plan.price_new)}</b>
              <em className={plan.price_delta >= 0 ? "up" : "down"}>
                {plan.price_delta >= 0 ? "+" : ""}{rp(plan.price_delta)} ({idNum(plan.price_delta_pct)}%)
              </em>
            </div>
            <div>
              <span>Dokumen bisa dikoreksi</span>
              <b>{plan.summary.editable_count}</b>
              <em>total dampak {rp(plan.summary.editable_delta_total)}</em>
            </div>
            <div>
              <span>Perlu Nota Kredit/Debit</span>
              <b>{plan.summary.locked_count}</b>
              <em>faktur sudah terbit</em>
            </div>
            <div className="cfg-impact-picked">
              <span>Anda centang</span>
              <b data-testid="cfg-impact-picked-count">{picked.length}</b>
              <em>dampak {rp(pickedDelta)}</em>
            </div>
          </div>

          <p className="cfg-policy-note" data-testid="cfg-impact-policy">
            <ShieldCheck size={13} /> {plan.policy}
          </p>

          <div className="cfg-impact-toolbar">
            <button className="btn-secondary btn-sm" onClick={() => setPicked(editable.map((d) => d.doc_id))}
              data-testid="cfg-impact-select-all">Centang semua</button>
            <button className="btn-secondary btn-sm" onClick={() => setPicked([])}
              data-testid="cfg-impact-clear">Kosongkan</button>
            <button className="btn-secondary btn-sm" onClick={() => setPicked(plan.default_selected || [])}
              data-testid="cfg-impact-default">Kembali ke default</button>
          </div>

          {editable.length === 0 ? (
            <p className="cfg-empty" data-testid="cfg-impact-empty">
              Tidak ada dokumen terbuka yang memakai harga produk ini. Koreksi harga master
              aman dilakukan tanpa efek samping.
            </p>
          ) : (
            <table className="data-table cfg-impact-table" data-testid="cfg-impact-table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>Ikut?</th>
                  <th>Dokumen</th><th>Pelanggan</th><th>Status</th>
                  <th className="cfg-right">Total sekarang</th>
                  <th className="cfg-right">Total setelah</th>
                  <th className="cfg-right">Selisih</th>
                </tr>
              </thead>
              <tbody>
                {editable.map((d) => (
                  <tr key={d.doc_id} className={picked.includes(d.doc_id) ? "cfg-row-picked" : ""}
                    data-testid={`cfg-impact-row-${d.doc_id}`}>
                    <td>
                      <input type="checkbox" checked={picked.includes(d.doc_id)}
                        onChange={() => toggle(d.doc_id)}
                        data-testid={`cfg-impact-check-${d.doc_id}`}
                        aria-label={`Ikut koreksi ${d.doc_number}`} />
                    </td>
                    <td>
                      <b>{d.doc_number}</b>
                      <div className="cfg-impact-lines">
                        {d.lines.map((l, i) => (
                          <span key={i}>
                            {idNum(l.quantity)} {l.unit} · {rp(l.price_now)} → {rp(l.price_new)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>{d.customer_name || "—"}</td>
                    <td><span className="badge-muted">{d.status}</span></td>
                    <td className="tabular-nums cfg-right">{rp(d.total_now)}</td>
                    <td className="tabular-nums cfg-right">{rp(d.total_new)}</td>
                    <td className={`tabular-nums cfg-right ${d.delta >= 0 ? "up" : "down"}`}>
                      {d.delta >= 0 ? "+" : ""}{rp(d.delta)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {locked.length > 0 ? (
            <div className="cfg-locked-box" data-testid="cfg-impact-locked">
              <h4><FileWarning size={14} /> Tidak bisa dikoreksi otomatis ({locked.length})</h4>
              <p className="cfg-hint-sm">
                Angka pada dokumen yang sudah terbit tidak pernah diubah. Koreksinya lewat
                Nota Kredit/Debit agar jejak akuntansi tetap utuh.
              </p>
              <ul>
                {locked.map((d) => (
                  <li key={d.doc_id} data-testid={`cfg-impact-locked-${d.doc_id}`}>
                    <b>{d.doc_number}</b> — {d.lock_reason} (dampak {rp(d.delta)})
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {canApply ? (
            <div className="cfg-impact-apply">
              <input className="form-input cfg-input-wide" value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Alasan koreksi (WAJIB) — mis. salah input harga produk"
                data-testid="cfg-impact-reason" />
              <button className="btn-primary" disabled={busy || !reason.trim()}
                onClick={apply} data-testid="cfg-impact-apply">
                <Check size={14} />
                {busy ? "Menerapkan…" : `Terapkan ke ${picked.length} dokumen tercentang`}
              </button>
              {!reason.trim() ? (
                <p className="cfg-hint-sm">
                  <AlertTriangle size={12} /> Alasan wajib diisi supaya perubahan bisa dipertanggungjawabkan.
                </p>
              ) : null}
            </div>
          ) : (
            <p className="cfg-readonly">Hanya admin/manager yang boleh menerapkan koreksi harga.</p>
          )}
        </>
      ) : null}

      {result ? (
        <div className={`cfg-impact-result ${result.untouched_verified ? "ok" : "bad"}`}
          data-testid="cfg-impact-result">
          <h4>
            {result.untouched_verified ? <ShieldCheck size={15} /> : <AlertTriangle size={15} />}
            Hasil koreksi harga
          </h4>
          <ul>
            <li>Harga master: <b>{rp(result.price_before)} → {rp(result.price_after)}</b></li>
            <li>
              Dokumen diubah: <b>{result.changed_documents.length}</b>
              {result.changed_documents.map((c) => (
                <span key={c.doc_id} className="cfg-chip">
                  {c.doc_number}: {rp(c.total_before)} → {rp(c.total_after)}
                </span>
              ))}
            </li>
            <li data-testid="cfg-impact-verified">
              Dokumen lain: <b>{result.untouched_documents.length}</b> —{" "}
              {result.untouched_verified
                ? "terbukti TIDAK berubah sama sekali (sidik jari dokumen identik)."
                : `PERINGATAN: ${result.violations.join(", ")} ternyata berubah.`}
            </li>
            {result.needs_credit_note.length ? (
              <li>
                Perlu Nota Kredit/Debit: <b>{result.needs_credit_note.length}</b> dokumen
              </li>
            ) : null}
          </ul>
          <button className="cfg-link-btn" onClick={loadPlan} data-testid="cfg-impact-refresh">
            <RefreshCw size={12} /> Muat ulang daftar dampak
          </button>
        </div>
      ) : null}
    </div>
  );
}
