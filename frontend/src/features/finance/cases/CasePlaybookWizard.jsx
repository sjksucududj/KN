/**
 * FASE G-9 — CasePlaybookWizard: menyelesaikan kasus lewat **playbook**.
 *
 * Kolom masukan dirakit dari `action.needs` yang DIKIRIM BACKEND, jadi layar tidak
 * pernah meminta data yang tidak dipakai mesin — dan tidak pernah lupa data yang wajib.
 * Setiap aksi menampilkan kalimat "apa yang akan terjadi" + dokumen turunan yang lahir,
 * supaya petugas tahu akibatnya SEBELUM menekan tombol.
 */
import { useEffect, useMemo, useState } from "react";
import { X, Wand2, FileCheck2, AlertTriangle } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { entityFull } from "../../../utils/entityLabel";
import { apiErrorText } from "../../../utils/apiError";

export default function CasePlaybookWizard({ caseData, reasons, entities, customers,
  suppliers, accounts, policy, onClose, onDone, onError }) {
  const actions = caseData.actions || [];
  const [actionCode, setActionCode] = useState(
    (caseData.resolution || {}).next_action || actions[0]?.code || "");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [amount, setAmount] = useState(String(caseData.amount || ""));
  const [customerId, setCustomerId] = useState(caseData.customer_id || "");
  const [supplierId, setSupplierId] = useState(caseData.supplier_id || "");
  const [orderId, setOrderId] = useState((caseData.order_ids || [])[0] || "");
  const [fromOrderId, setFromOrderId] = useState("");
  const [toOrderId, setToOrderId] = useState("");
  const [toAccountId, setToAccountId] = useState("");
  const [ownerEntityId, setOwnerEntityId] = useState("");
  const [employeeName, setEmployeeName] = useState("");
  const [withPenalty, setWithPenalty] = useState(false);
  const [alloc, setAlloc] = useState({});
  const [orders, setOrders] = useState([]);
  const [saving, setSaving] = useState(false);
  // KN-G9-ERR-SILENT — wizard ini MODAL. Bilah error milik layar induk berada di
  // BELAKANG modal, jadi penolakan backend (alasan wajib, bukti wajib, di atas ambang
  // persetujuan, entitas lain) HARUS tampil di dalam modal ini juga. Tanpa ini, tombol
  // "Jalankan & selesaikan" terasa mati tanpa penjelasan.
  const [err, setErr] = useState("");

  const action = useMemo(
    () => actions.find((a) => a.code === actionCode) || null, [actions, actionCode]);
  const needs = action?.needs || [];
  const need = (k) => needs.includes(k);

  // Pesanan terbuka pelanggan — dipakai alokasi/realokasi/pelunasan.
  useEffect(() => {
    const cid = customerId || caseData.customer_id;
    if (!cid) { setOrders([]); return; }
    (async () => {
      try {
        const r = await axios.get(`${API}/ar-receipts/open-orders`,
          { params: { customer_id: cid } });
        setOrders(Array.isArray(r.data) ? r.data : []);
      } catch (e) { setErr(apiErrorText(e)); onError?.(e); }
    })();
  }, [customerId, caseData.customer_id, onError]);

  // US3 — label alasan HARUS nyambung dengan jenis kasusnya. Daftar sahnya datang dari
  // backend (`caseData.reason_codes`, SSOT di services/finance_case_playbooks.py), bukan
  // tebakan layar. Sebelum ini wizard menawarkan seluruh 12 label untuk semua jenis kasus
  // sehingga "Dana masuk tak dikenal" bisa ditutup dengan alasan "Cek / giro ditolak bank"
  // — jejaknya menyesatkan auditor padahal invarian tetap hijau.
  const reasonOptions = useMemo(() => {
    const allow = caseData.reason_codes || [];
    const fit = allow.length ? reasons.filter((r) => allow.includes(r.code)) : reasons;
    return (fit.length ? fit : reasons).map((r) => ({ value: r.code, label: r.label }));
  }, [reasons, caseData.reason_codes]);
  const custOptions = useMemo(
    () => customers.map((c) => ({ value: c.id, label: c.name || c.id })), [customers]);
  const supOptions = useMemo(
    () => suppliers.map((s) => ({ value: s.id, label: s.name || s.id })), [suppliers]);
  const orderOptions = useMemo(() => orders.map((o) => ({
    value: o.order_id,
    label: `${o.number} · sisa ${formatCurrency(o.outstanding)}`,
  })), [orders]);
  const accountOptions = useMemo(() => accounts
    .filter((a) => !caseData.entity_id || !a.entity_id || a.entity_id === "all"
      || a.entity_id === caseData.entity_id)
    .map((a) => ({ value: a.id, label: a.name || a.bank_name || a.id })),
  [accounts, caseData.entity_id]);
  const entityOptions = useMemo(() => (entities || [])
    .filter((e) => e.id !== caseData.entity_id)
    .map((e) => ({ value: e.id, label: entityFull(e) })), [entities, caseData.entity_id]);

  const allocTotal = useMemo(
    () => Object.values(alloc).reduce((a, v) => a + (Number(v) || 0), 0), [alloc]);
  const effAmount = need("allocations") ? allocTotal : Number(amount) || 0;
  const needsApproval = Number(policy?.approval_above || 0) > 0
    && effAmount >= Number(policy.approval_above);

  const missing = [];
  if (!reason) missing.push("alasan");
  if (need("allocations") && allocTotal <= 0) missing.push("alokasi pesanan");
  if (need("amount") && !(Number(amount) > 0)) missing.push("nominal");
  if (need("customer_id") && !(customerId || caseData.customer_id)) missing.push("pelanggan");
  if (need("supplier_id") && !(supplierId || caseData.supplier_id)) missing.push("supplier");
  if (need("order_id") && !orderId) missing.push("pesanan");
  if (need("from_order_id") && !fromOrderId) missing.push("pesanan asal");
  if (need("to_order_id") && !toOrderId) missing.push("pesanan tujuan");
  if (need("to_account_id") && !toAccountId) missing.push("rekening tujuan");
  if (need("owner_entity_id") && !ownerEntityId) missing.push("PT pemilik tagihan");
  if (need("employee_name") && !employeeName.trim()) missing.push("nama karyawan");
  const needEvidence = caseData.needs_evidence && !(caseData.attachments || []).length;
  // US3 — jenis kasus ber-klaim (pembayar pihak ketiga, rekening pribadi karyawan) WAJIB
  // berlampiran bukti. Backend menolaknya dengan 400, jadi tombolnya JANGAN dibiarkan
  // aktif: petugas tidak boleh dibiarkan menabrak dinding lalu menebak sendiri sebabnya.
  // Arahannya ada di `case-evidence-warning` di bawah (tempat menambah buktinya).
  if (needEvidence) missing.push("lampiran bukti");

  async function submit() {
    setSaving(true); setErr("");
    try {
      const body = {
        action: actionCode, reason_code: reason, note,
        amount: Number(amount) || 0,
        customer_id: customerId || caseData.customer_id || "",
        supplier_id: supplierId || caseData.supplier_id || "",
        order_id: orderId, from_order_id: fromOrderId, to_order_id: toOrderId,
        to_account_id: toAccountId, owner_entity_id: ownerEntityId,
        employee_name: employeeName, with_penalty: withPenalty,
        receipt_id: caseData.source?.kind === "ar_receipt" ? caseData.source.id : "",
        allocations: Object.entries(alloc)
          .filter(([, v]) => Number(v) > 0)
          .map(([order_id, v]) => ({ order_id, amount: Number(v) })),
      };
      const r = await axios.post(`${API}/finance-cases/${caseData.id}/resolve`, body);
      onDone(r.data);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-overlay" data-testid="case-wizard" {...overlayDismiss(onClose)}>
      <div className="modal-panel max-h-[92vh] w-[680px] max-w-[96vw] overflow-y-auto">
        <div className="sticky top-0 flex items-center justify-between border-b border-[#EFF0F2] bg-white px-4 py-3">
          <div>
            <h3 className="flex items-center gap-2 text-[14px] font-bold text-[#1C1C1E]">
              <Wand2 size={15} className="text-[#0058CC]" /> Selesaikan {caseData.number}
            </h3>
            <p className="text-[11px] text-[#6B6B73]">{caseData.case_type_label}</p>
          </div>
          <button className="icon-button" data-testid="case-wizard-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>

        <div className="space-y-3 px-4 py-4">
          {/* Langkah playbook — kalimat manusia */}
          {!!(caseData.playbook || []).length && (
            <ol className="space-y-1 rounded-lg border border-[#CBDCF7] bg-[#F2F7FF] px-3 py-2 text-[11px] text-[#1C1C1E]"
              data-testid="case-wizard-steps">
              {caseData.playbook.map((s, i) => (
                <li key={i}><b>{i + 1}.</b> {s}</li>
              ))}
            </ol>
          )}

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Cara menyelesaikan
            </label>
            <div className="space-y-2">
              {actions.map((a) => (
                <button key={a.code} type="button" data-testid={`case-action-${a.code}`}
                  onClick={() => setActionCode(a.code)}
                  className={`w-full rounded-lg border px-3 py-2 text-left ${
                    actionCode === a.code
                      ? "border-[#0058CC] bg-[#F2F7FF]"
                      : "border-[#E5E5EA] bg-white hover:border-[#CBDCF7]"}`}>
                  <p className="text-[12px] font-semibold text-[#1C1C1E]">
                    {a.label}
                    {a.sensitive && (
                      <span className="ml-1.5 rounded bg-[#FDECEA] px-1.5 py-0.5 text-[9px] font-bold text-[#C0392B]">
                        UANG KELUAR
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 text-[11px] text-[#6B6B73]">{a.effect}</p>
                  <p className="mt-1 flex items-start gap-1 text-[10px] text-[#1B7F4B]">
                    <FileCheck2 size={11} className="mt-[1px] shrink-0" />
                    <span>Yang lahir: {a.produces}</span>
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* Masukan dinamis sesuai `needs` aksi */}
          <div className="grid grid-cols-2 gap-3">
            {need("customer_id") && (
              <div className="col-span-2">
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Pelanggan</label>
                <KNSelect data-testid="case-field-customer" value={customerId}
                  onValueChange={setCustomerId} options={custOptions}
                  placeholder="Pilih pelanggan" />
              </div>
            )}
            {need("supplier_id") && (
              <div className="col-span-2">
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Supplier</label>
                <KNSelect data-testid="case-field-supplier" value={supplierId}
                  onValueChange={setSupplierId} options={supOptions}
                  placeholder="Pilih supplier" />
              </div>
            )}
            {need("employee_name") && (
              <div className="col-span-2">
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                  Nama karyawan yang memegang uang
                </label>
                <input data-testid="case-field-employee" className="input-field w-full"
                  value={employeeName} onChange={(e) => setEmployeeName(e.target.value)} />
              </div>
            )}
            {need("owner_entity_id") && (
              <div className="col-span-2">
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                  PT pemilik tagihan
                </label>
                <KNSelect data-testid="case-field-owner-entity" value={ownerEntityId}
                  onValueChange={setOwnerEntityId} options={entityOptions}
                  placeholder="Pilih PT" />
              </div>
            )}
            {need("to_account_id") && (
              <div className="col-span-2">
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                  Rekening tujuan pindah-buku
                </label>
                <KNSelect data-testid="case-field-to-account" value={toAccountId}
                  onValueChange={setToAccountId} options={accountOptions}
                  placeholder="Pilih rekening" />
              </div>
            )}
            {need("order_id") && (
              <div className="col-span-2">
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Pesanan</label>
                <KNSelect data-testid="case-field-order" value={orderId}
                  onValueChange={setOrderId} options={orderOptions}
                  placeholder="Pilih pesanan" />
              </div>
            )}
            {need("from_order_id") && (
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                  Pesanan asal (salah tempel)
                </label>
                <KNSelect data-testid="case-field-from-order" value={fromOrderId}
                  onValueChange={setFromOrderId} options={orderOptions}
                  placeholder="Pilih pesanan asal" />
              </div>
            )}
            {need("to_order_id") && (
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                  Pesanan tujuan (yang benar)
                </label>
                <KNSelect data-testid="case-field-to-order" value={toOrderId}
                  onValueChange={setToOrderId} options={orderOptions}
                  placeholder="Pilih pesanan tujuan" />
              </div>
            )}
            {need("amount") && (
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                  Nominal (Rp)
                </label>
                <input data-testid="case-field-amount" type="number" min={0}
                  className="input-field w-full" value={amount}
                  onChange={(e) => setAmount(e.target.value)} />
              </div>
            )}
          </div>

          {need("allocations") && (
            <div className="rounded-lg border border-[#E5E5EA] p-3" data-testid="case-field-allocations">
              <p className="mb-2 text-[11px] font-semibold text-[#6B6B73]">
                Pesanan yang dilunasi
              </p>
              {!orders.length && (
                <p className="text-[11px] text-[#8E8E93]">
                  Pilih pelanggan dulu, atau pelanggan ini tidak punya pesanan terbuka.
                </p>
              )}
              {orders.map((o) => (
                <div key={o.order_id} className="mb-1.5 flex items-center gap-2"
                  data-testid={`case-alloc-row-${o.order_id}`}>
                  <span className="flex-1 text-[12px] text-[#1C1C1E]">
                    {o.number}
                    <span className="ml-1 text-[11px] text-[#8E8E93]">
                      sisa {formatCurrency(o.outstanding)}
                    </span>
                  </span>
                  <input type="number" min={0} max={o.outstanding} placeholder="0"
                    data-testid={`case-alloc-${o.order_id}`}
                    className="input-field w-[150px] text-right"
                    value={alloc[o.order_id] || ""}
                    onChange={(e) => setAlloc({ ...alloc, [o.order_id]: e.target.value })} />
                </div>
              ))}
              <p className="mt-1 text-right text-[11px] text-[#6B6B73]">
                Total alokasi <b>{formatCurrency(allocTotal)}</b> dari nominal kasus{" "}
                {formatCurrency(caseData.amount)}
              </p>
            </div>
          )}

          {caseData.case_type === "giro_ditolak" && (
            <label className="flex items-center gap-2 text-[12px] text-[#1C1C1E]">
              <input type="checkbox" data-testid="case-field-penalty" checked={withPenalty}
                onChange={(e) => setWithPenalty(e.target.checked)} />
              Terbitkan sekaligus nota denda keterlambatan (sesuai kebijakan denda)
            </label>
          )}

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Alasan penyelesaian (wajib)
            </label>
            <KNSelect data-testid="case-field-reason" value={reason} onValueChange={setReason}
              options={reasonOptions} placeholder="Pilih label alasan" />
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Catatan (dibaca auditor)
            </label>
            <textarea data-testid="case-field-note" className="textarea w-full" rows={2}
              value={note} onChange={(e) => setNote(e.target.value)} />
          </div>

          {needsApproval && (
            <div className="flex items-start gap-2 rounded-lg border border-[#F3C9C7] bg-[#FDECEA] px-3 py-2 text-[11px] text-[#8A2A20]"
              data-testid="case-approval-warning">
              <AlertTriangle size={13} className="mt-[1px] shrink-0" />
              <span>
                Nominal {formatCurrency(effAmount)} melebihi ambang persetujuan{" "}
                {formatCurrency(policy.approval_above)} — hanya{" "}
                <b>{policy.approver_role === "admin" ? "admin" : "manager"}</b> atau admin
                yang boleh menutup kasus ini.
              </span>
            </div>
          )}
          {needEvidence && (
            <div className="flex items-start gap-2 rounded-lg border border-[#F3C9C7] bg-[#FDECEA] px-3 py-2 text-[11px] text-[#8A2A20]"
              data-testid="case-evidence-warning">
              <AlertTriangle size={13} className="mt-[1px] shrink-0" />
              <span>
                Jenis kasus ini wajib disertai <b>lampiran bukti</b>. Tambahkan bukti di
                panel detail (tombol “Tambah catatan / bukti”) sebelum menyelesaikan.
              </span>
            </div>
          )}
        </div>

        {err && (
          <div className="px-4">
            <ErrorNotice message={err} onDismiss={() => setErr("")} testId="case-wizard-error" />
          </div>
        )}

        <div className="sticky bottom-0 flex items-center justify-between gap-2 border-t border-[#EFF0F2] bg-white px-4 py-3">
          <span className="text-[11px] text-[#8E8E93]" data-testid="case-wizard-missing">
            {missing.length ? `Belum lengkap: ${missing.join(", ")}` : "Siap diselesaikan"}
          </span>
          <div className="flex items-center gap-2">
            <button className="secondary-button" onClick={onClose}>Batal</button>
            <button className="primary-button" data-testid="case-wizard-submit"
              disabled={saving || missing.length > 0} onClick={submit}>
              {saving ? "Menjalankan…" : "Jalankan & selesaikan"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
