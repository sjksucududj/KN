/**
 * FASE G-8 — ReconHoldingPanel: antrean **Titipan Dana Belum Teridentifikasi**.
 *
 * Dana masuk yang belum ketahuan pemiliknya sudah diakui sebagai KEWAJIBAN
 * (Dr Bank / Cr 2-1950) saat dititipkan. Di sini dana itu dialokasikan ke pesanan
 * pelanggan begitu identitasnya ketemu — piutang berkurang, jurnal Dr Titipan /
 * Cr Piutang terbit, dan TIDAK ada kas dobel.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { PiggyBank, X, RefreshCw, AlertTriangle, Undo2, HandCoins, Briefcase } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { KNSelect } from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { apiErrorText } from "../../../utils/apiError";
import ErrorNotice from "../../../components/ErrorNotice";
import { openFinanceCase, caseNumberFromText } from "../cases/caseDeepLink";

const fmtDate = (s) => {
  if (!s) return "—";
  try {
    return new Date(String(s).length <= 10 ? `${s}T00:00:00` : s)
      .toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return s; }
};

// Label alasan keputusan atas uang — wajib dipilih (tidak boleh alokasi tanpa alasan).
const REASONS = [
  { value: "identified_customer", label: "Pengirim akhirnya teridentifikasi" },
  { value: "customer_confirmation", label: "Dikonfirmasi pelanggan lewat bukti transfer" },
  { value: "sales_confirmation", label: "Dikonfirmasi sales/penagih" },
  { value: "partial_identification", label: "Sebagian teridentifikasi (sisanya masih ditelusuri)" },
];

export default function ReconHoldingPanel({ holding, busy, onAction, onReload, onError,
  onNotify }) {
  const [target, setTarget] = useState(null);      // baris titipan yang sedang dialokasikan
  const [customers, setCustomers] = useState([]);
  const [customerId, setCustomerId] = useState("");
  const [orders, setOrders] = useState([]);
  const [alloc, setAlloc] = useState({});
  const [reason, setReason] = useState("identified_customer");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [opening, setOpening] = useState("");   // baris yang sedang dibuatkan kasus
  // INV-UI-03 — modal WAJIB menampilkan penolakannya sendiri: bilah error layar
  // induk berada di belakang lapisan modal ini, jadi tak terlihat pengguna.
  const [mErr, setMErr] = useState("");

  const loadCustomers = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/customers`);
      const list = Array.isArray(r.data) ? r.data : (r.data?.items || []);
      setCustomers(list);
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); }
  }, [onError]);

  useEffect(() => { if (target) loadCustomers(); }, [target, loadCustomers]);

  useEffect(() => {
    if (!customerId) { setOrders([]); return; }
    (async () => {
      try {
        const r = await axios.get(`${API}/ar-receipts/open-orders`,
          { params: { customer_id: customerId } });
        setOrders(Array.isArray(r.data) ? r.data : []);
      } catch (e) { setMErr(apiErrorText(e)); onError?.(e); }
    })();
  }, [customerId, onError]);

  const items = holding?.items || [];
  // KN-G8-ALLOC-CROSSPT: titipan pada rekening satu PT hanya boleh melunasi pesanan PT yang
  // sama (backend menolak 403). Daftar pelanggan disaring ke entitas baris titipannya supaya
  // pengguna tidak ditawari pilihan yang pasti gagal.
  const customerOptions = useMemo(() => customers
    .filter((c) => !target?.entity_id || !c.entity_id || c.entity_id === "all"
      || c.entity_id === target.entity_id)
    .map((c) => ({ value: c.id, label: c.name || c.id })), [customers, target]);
  const allocTotal = useMemo(
    () => Object.values(alloc).reduce((a, v) => a + (Number(v) || 0), 0), [alloc]);
  const remaining = (Number(target?.remaining || 0) - allocTotal);

  function close() {
    setTarget(null); setCustomerId(""); setOrders([]); setAlloc({}); setNote("");
  }

  /**
   * FASE G-9 — serahkan titipan ini ke **Pusat Kasus Keuangan**.
   *
   * Kasus dibuat dengan sumber = baris titipan ini, sehingga layar kasus tahu dana mana
   * yang sedang diurus (dan penyelesaiannya memakai jalur `alokasi_titipan` yang sama —
   * tidak ada mesin uang kedua). Sesudah kasus lahir, petugas LANGSUNG DIANTAR ke
   * kasusnya (US8: "tanpa mengetik ulang") lewat deep-link global `kn-open-finance-case`.
   *
   * Bila kasusnya SUDAH ada, backend menolak dengan kalimat yang menyebut nomor kasusnya.
   * Kalimat itu kita pakai untuk mengantar pengguna ke kasus yang sudah ada — jadi jalan
   * buntu ("kok tidak bisa?") berubah jadi jalan terusan.
   */
  async function openCase(h) {
    setOpening(h.id);
    try {
      const r = await axios.post(`${API}/finance-cases`, {
        case_type: "dana_tak_dikenal",
        title: `Dana masuk tak dikenal ${formatCurrency(h.remaining)}`,
        description: `Titipan dari mutasi "${h.description || ""}" (pihak: `
          + `${h.counterparty || "tidak diketahui"}) belum ketemu pemiliknya.`,
        amount: Number(h.remaining) || 0,
        customer_id: h.customer_id || "",
        source: { kind: "bank_holding", id: h.id,
          label: `Mutasi ${h.stmt_date || ""} · ${(h.description || "").slice(0, 50)}` },
      });
      openFinanceCase({ caseId: r.data.id, number: r.data.number,
        note: `Kasus ${r.data.number} dibuat dari mutasi titipan ini (batas waktu `
          + `${r.data.sla_hours} jam) — sumber, nominal, dan dugaan pelanggan sudah terisi.` });
    } catch (e) {
      const text = apiErrorText(e);
      const number = caseNumberFromText(text);
      if (number) {
        // Bukan jalan buntu: antar pengguna ke kasus yang sudah ada.
        openFinanceCase({ number, note: text, noteKind: "warning" });
      } else {
        onError(e);
      }
    } finally { setOpening(""); }
  }

  async function submit() {
    const allocations = Object.entries(alloc)
      .filter(([, v]) => Number(v) > 0)
      .map(([order_id, v]) => ({ order_id, amount: Number(v) }));
    if (!allocations.length) return;
    setSaving(true);
    try {
      const r = await axios.post(
        `${API}/bank-reconciliation/lines/${target.id}/holding/allocate`,
        { customer_id: customerId, reason_code: reason, note, allocations });
      onNotify(`Titipan dialokasikan ${formatCurrency(r.data.allocated_now)} · sisa titipan `
        + `${formatCurrency(r.data.holding_remaining)}.`);
      close();
      await onReload();
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); } finally { setSaving(false); }
  }

  return (
    <div data-testid="recon-holding-panel">
      <div className="mb-3 rounded-lg border border-[#CBDCF7] bg-[#F2F7FF] px-3 py-2 text-[12px] text-[#1C1C1E]">
        Dana masuk yang belum diketahui pemiliknya ditampung di akun{" "}
        <b>{holding?.account_code || "2-1950"} Titipan Dana Belum Teridentifikasi</b>. Saldo
        titipan <b>{formatCurrency(holding?.balance || 0)}</b> dari {holding?.count || 0} baris.
        Titipan yang menganggur lebih dari {holding?.max_age_days || 7} hari ditandai perlu
        tindakan.
      </div>

      <div className="rounded-lg border border-[#E5E5EA] overflow-hidden" data-testid="recon-holding-table">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
              <th className="px-3 py-2">Tanggal</th>
              <th className="px-3 py-2">Keterangan</th>
              <th className="px-3 py-2 text-right">Dana masuk</th>
              <th className="px-3 py-2 text-right">Sudah dialokasikan</th>
              <th className="px-3 py-2 text-right">Sisa titipan</th>
              <th className="px-3 py-2">Umur</th>
              <th className="px-3 py-2 text-right">Tindakan</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-[#8E8E93]">
                  Tidak ada dana titipan. Bila ada transfer masuk tanpa identitas, tekan
                  “Titipkan” pada baris mutasinya.
                </td>
              </tr>
            ) : items.map((h) => (
              <tr key={h.id} data-testid={`recon-holding-row-${h.id}`}
                className="border-b border-[#F5F5F7] last:border-0">
                <td className="px-3 py-2 whitespace-nowrap">{fmtDate(h.stmt_date)}</td>
                <td className="px-3 py-2 max-w-[280px]">
                  <p className="truncate" title={h.description}>{h.description || "—"}</p>
                  {h.counterparty && (
                    <p className="text-[10px] text-[#8E8E93]">Pihak: {h.counterparty}</p>
                  )}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(h.amount)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-[#1B7F4B]">
                  {formatCurrency(h.allocated)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums font-semibold text-[#0058CC]">
                  {formatCurrency(h.remaining)}
                </td>
                <td className="px-3 py-2">
                  <span className={h.needs_action ? "text-[#C0392B] font-semibold" : ""}>
                    {h.age_days} hari
                  </span>
                  {h.needs_action && (
                    <span className="ml-1 inline-flex items-center gap-0.5 text-[10px] text-[#C0392B]">
                      <AlertTriangle size={10} /> perlu tindakan
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  <div className="flex justify-end gap-2 flex-wrap">
                    <button data-testid={`recon-allocate-${h.id}`} className="link-button"
                      disabled={Number(h.remaining) <= 0}
                      onClick={() => { setTarget(h); setAlloc({}); }}>
                      <HandCoins size={12} /> Alokasikan
                    </button>
                    {/* FASE G-9 — titipan yang belum ketemu pemiliknya diserahkan ke Pusat
                        Kasus Keuangan supaya punya penanggung jawab & batas waktu, bukan
                        menganggur di layar ini. Kasusnya terisi otomatis dari mutasi bank
                        ini (sumber, nominal, dugaan pelanggan) — tanpa mengetik ulang. */}
                    {Number(h.remaining) > 0 && (
                      <button data-testid={`recon-open-case-${h.id}`} className="link-button"
                        disabled={opening === h.id}
                        onClick={() => openCase(h)}>
                        <Briefcase size={12} /> {opening === h.id ? "Membuka…" : "Buka kasus"}
                      </button>
                    )}
                    {Number(h.allocated) <= 0 && (
                      <button data-testid={`recon-holding-cancel-${h.id}`} className="link-button"
                        style={{ color: "#B4231F" }} disabled={busy === h.id + "holding/cancel"}
                        onClick={() => onAction(h.id, "holding/cancel", {},
                          "Titipan dibatalkan (kas & jurnalnya dibatalkan).")}>
                        <Undo2 size={12} /> Batalkan titipan
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {target && (
        <div className="modal-overlay" data-testid="recon-allocate-modal"
          {...overlayDismiss(close)}>
          <div className="modal-card max-w-[640px]">
            <div className="flex items-center justify-between mb-2">
              <h3 className="modal-title flex items-center gap-1.5">
                <PiggyBank size={15} /> Alokasikan dana titipan
              </h3>
              <button className="icon-button" data-testid="recon-allocate-close" onClick={close}>
                <X size={15} />
              </button>
            </div>
            {mErr && (
              <ErrorNotice message={mErr} onDismiss={() => setMErr("")}
                testId="recon-allocate-error" />
            )}
            <p className="modal-subtitle">
              {fmtDate(target.stmt_date)} · sisa titipan{" "}
              <b>{formatCurrency(target.remaining)}</b> — {target.description}
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Pelanggan <span className="font-normal text-[#8E8E93]">
                    (hanya pelanggan pada entitas rekening ini)</span>
                </label>
                <KNSelect data-testid="recon-allocate-customer" value={customerId}
                  onValueChange={setCustomerId} placeholder="Pilih pelanggan"
                  options={customerOptions} />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Alasan keputusan (wajib)
                </label>
                <KNSelect data-testid="recon-allocate-reason" value={reason}
                  onValueChange={setReason} options={REASONS} />
              </div>
            </div>

            <div className="mt-3">
              <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                Pesanan yang dilunasi
              </label>
              <div className="rounded border border-[#EFF0F2] max-h-[240px] overflow-auto">
                {!customerId ? (
                  <div className="p-4 text-center text-[12px] text-[#8E8E93]">
                    Pilih pelanggan dulu untuk melihat pesanan yang masih punya sisa tagihan.
                  </div>
                ) : orders.length === 0 ? (
                  <div className="p-4 text-center text-[12px] text-[#8E8E93]">
                    Pelanggan ini tidak punya pesanan bersisa tagihan.
                  </div>
                ) : orders.map((o) => (
                  <div key={o.id || o.order_id}
                    data-testid={`recon-allocate-order-${o.id || o.order_id}`}
                    className="flex items-center justify-between gap-3 px-3 py-2 border-b border-[#F5F5F7] last:border-0">
                    <div className="min-w-0">
                      <p className="text-[12px]">
                        <b>{o.number}</b> ·{" "}
                        {fmtDate(o.date || o.order_date || o.created_at)}
                      </p>
                      <p className="text-[10px] text-[#8E8E93]">
                        Sisa tagihan {formatCurrency(o.outstanding ?? o.outstanding_amount ?? 0)}
                      </p>
                    </div>
                    <input data-testid={`recon-allocate-amount-${o.id || o.order_id}`}
                      type="number" min={0} step={1000} className="input-field w-[150px]"
                      placeholder="Nominal"
                      value={alloc[o.id || o.order_id] ?? ""}
                      onChange={(e) => setAlloc((cur) => ({
                        ...cur, [o.id || o.order_id]: e.target.value,
                      }))} />
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-3">
              <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                Catatan (opsional)
              </label>
              <input data-testid="recon-allocate-note" className="input-field w-full" value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Contoh: bukti transfer dikirim via WhatsApp oleh pelanggan" />
            </div>

            <p className={`mt-2 text-[12px] ${remaining < -0.01 ? "text-[#C0392B]" : "text-[#6B6B73]"}`}>
              Total alokasi <b>{formatCurrency(allocTotal)}</b> · sisa titipan setelah ini{" "}
              <b>{formatCurrency(remaining)}</b>
            </p>

            <div className="flex justify-end gap-2 mt-3">
              <button className="secondary-button" onClick={close}>Batal</button>
              <button data-testid="recon-allocate-submit" className="primary-button"
                disabled={allocTotal <= 0 || remaining < -0.01 || saving} onClick={submit}>
                {saving ? <RefreshCw size={14} className="spin" /> : <HandCoins size={14} />}
                Alokasikan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
