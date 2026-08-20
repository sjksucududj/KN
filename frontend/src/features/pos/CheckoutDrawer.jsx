import { useEffect, useMemo, useState } from "react";
import {
  X, ChevronRight, ChevronLeft, Users, UserPlus, PackageCheck, Receipt,
  AlertTriangle, Layers, ShieldAlert, ShieldCheck, MapPin, CreditCard, CheckCircle2, Truck,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { computeOrderPreview } from "../../utils/pricing";
import { convFactor } from "../../utils/uom";
import { MixedLotConfirmModal } from "../../components/MixedLotConfirmModal";
import KNSelect from "../../components/KNSelect";
import StoreCreditBadge from "../../components/StoreCreditBadge";
import CreateCustomerModal from "./CreateCustomerModal";
import RequestSpecialPriceModal from "./RequestSpecialPriceModal";
import { CheckoutItemCard, Row } from "./CheckoutItemCard";
import CheckoutStep3 from "./CheckoutStep3";
import { SalesTeamEditor, salesTeamError, customerDefaultTeam } from "./SalesTeamEditor";
import { useEffectivePrices, pickPrice, sourceMeta } from "../../hooks/useEffectivePrices";
import { useEntityScope } from "../../context/EntityScopeContext";

const STEPS = [
  { n: 1, label: "Pelanggan & Alamat", icon: Users },
  { n: 2, label: "Termin & Lot", icon: Layers },
  { n: 3, label: "Review", icon: CheckCircle2 },
];

/** EPIC5 — Checkout stepper 3 langkah. Memakai ulang preview ATP/lot/harga-khusus + gate kredit. */
export default function CheckoutDrawer({
  open, onClose, cart, setCart, customers = [],
  selectedCustomer, setSelectedCustomer, selectedAddress, setSelectedAddress,
  onCreateCustomer, onSubmitOrder, settings = {}, paymentTerms = [], selectedEntity = "all", onShowDetail, user = null,
}) {
  const [step, setStep] = useState(1);
  // FASE E-3 (user story 7) — pesanan WAJIB lahir di satu badan usaha.
  const { canWrite, writeBlockHint } = useEntityScope();
  const [orderDiscount, setOrderDiscount] = useState(0);
  const [paymentTerm, setPaymentTerm] = useState("");
  const [allowBackorder, setAllowBackorder] = useState(false);
  const [showMixedConfirm, setShowMixedConfirm] = useState(false);
  const [showCreateCustomer, setShowCreateCustomer] = useState(false);
  const [allocation, setAllocation] = useState({ map: {}, loading: false, entityId: "" });
  const [transferRequests, setTransferRequests] = useState({});
  const [lotPlan, setLotPlan] = useState({ requires_confirmation: false, lines: [], policy: {}, loading: false });
  const [credit, setCredit] = useState(null);
  const [needsTaxInvoice, setNeedsTaxInvoice] = useState(false);  // F6 — minta Faktur Pajak
  const [fulfillmentMethod, setFulfillmentMethod] = useState("kirim");  // kirim | ambil (Order Pengambilan)
  const [pickupDate, setPickupDate] = useState("");
  const [deliveryDate, setDeliveryDate] = useState("");   // F-SHIP — request tgl pengiriman (opsional, metode kirim)
  const [salesTeam, setSalesTeam] = useState([]);         // F-4c REVISI — tim sales PER ORDER (prefill dari customer)
  const [spModalItem, setSpModalItem] = useState(null);  // item yg sedang diajukan harga khusus
  const [spNotice, setSpNotice] = useState({});          // {productId: {message, applied}}
  const [spRefresh, setSpRefresh] = useState(0);         // trigger re-load harga khusus efektif
  const canApprovePrice = ["admin", "manager"].includes(user?.role);

  const defaultTerm = settings?.finance?.default_payment_term_code || "";
  useEffect(() => { if (!paymentTerm && defaultTerm) setPaymentTerm(defaultTerm); }, [defaultTerm]); // eslint-disable-line
  useEffect(() => { if (open) { setStep(1); setSpNotice({}); } }, [open]);
  // F-4c REVISI — prefill tim sales dari default customer saat customer dipilih (boleh di-override per order).
  useEffect(() => { setSalesTeam(customerDefaultTeam(selectedCustomer)); }, [selectedCustomer?.id]); // eslint-disable-line

  // Diskon manual DIHAPUS untuk semua role — potongan harga hanya via Harga Khusus
  // (special-price) yang diajukan di detail SO & disetujui manager/admin.
  const allowItemDiscount = false;
  const allowOrderDiscount = false;
  const addresses = selectedCustomer?.addresses || [];
  const entityFor = selectedEntity && selectedEntity !== "all" ? selectedEntity : (selectedCustomer?.entity_id || "");

  // F1b — harga EFEKTIF per pelanggan dalam SATU panggilan (harga khusus → pelanggan →
  // PT → umum). `pickPrice` per baris menghormati qty minimum aturan harga khusus,
  // sehingga angka di review checkout SAMA dengan yang disimpan server.
  const cartIds = useMemo(() => cart.map((i) => i.product.id), [cart]);
  const { priceMap: specialMap } = useEffectivePrices({
    customerId: selectedCustomer?.id || "",
    entityId: entityFor,
    productIds: cartIds,
    enabled: open && cart.length > 0,
    delay: 400,
    refreshKey: spRefresh,
  });

  // ATP / alokasi preview — debounced.
  useEffect(() => {
    if (!open || !cart.length) { setAllocation({ map: {}, loading: false, entityId: "" }); return undefined; }
    let cancelled = false;
    setAllocation((a) => ({ ...a, loading: true }));
    const timer = setTimeout(async () => {
      try {
        const res = await axios.post(`${API}/sales-orders/preview-allocation`, {
          entity_id: entityFor, customer_id: selectedCustomer?.id || "",
          items: cart.map((i) => ({ product_id: i.product.id, quantity: i.quantity, unit: i.unit })),
        });
        if (cancelled) return;
        const map = {};
        (res.data.lines || []).forEach((l) => { map[l.product_id] = l; });
        setAllocation({ map, loading: false, entityId: res.data.entity_id || entityFor });
      } catch { if (!cancelled) setAllocation({ map: {}, loading: false, entityId: "" }); }
    }, 350);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [open, cart, entityFor, selectedCustomer]); // eslint-disable-line

  // Lot plan (mixed-lot confirmation) — debounced.
  useEffect(() => {
    if (!open || !cart.length || !selectedCustomer?.id) { setLotPlan({ requires_confirmation: false, lines: [], policy: {}, loading: false }); return undefined; }
    let cancelled = false;
    setLotPlan((lp) => ({ ...lp, loading: true }));
    const timer = setTimeout(async () => {
      try {
        const res = await axios.post(`${API}/sales-orders/preview-lots`, {
          entity_id: entityFor, customer_id: selectedCustomer?.id || "",
          items: cart.map((i) => ({ product_id: i.product.id, quantity: i.quantity, unit: i.unit })),
        });
        if (cancelled) return;
        setLotPlan({ requires_confirmation: !!res.data.requires_confirmation, lines: res.data.lines || [], policy: res.data.policy || {}, loading: false });
      } catch { if (!cancelled) setLotPlan({ requires_confirmation: false, lines: [], policy: {}, loading: false }); }
    }, 400);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [open, cart, entityFor, selectedCustomer]); // eslint-disable-line

  // Harga per baris SETELAH menghormati qty minimum aturan harga khusus.
  const linePrices = useMemo(() => {
    const out = {};
    cart.forEach((i) => { out[i.product.id] = pickPrice(specialMap[i.product.id], i.quantity); });
    return out;
  }, [cart, specialMap]);

  const cartPriced = cart.map((item) => {
    const sp = linePrices[item.product.id];
    const factor = convFactor(item.product, item.unit || item.product.base_unit) ?? 1;
    // Harga dasar = harga EFEKTIF pelanggan (pelanggan → PT → umum), bukan harga umum saja.
    const basePrice = sp ? Number(sp.price) : (item.product.price || 0);
    const scaled = Math.round(basePrice * factor * 100) / 100;
    const price = sp && sp.has_special ? Number(sp.price) : scaled;
    return { ...item, product: { ...item.product, price } };
  });
  const p = useMemo(() => computeOrderPreview(cartPriced, orderDiscount, settings), [cartPriced, orderDiscount, settings]);

  // Gate kredit live.
  useEffect(() => {
    const cid = selectedCustomer?.id;
    if (!open || !cid || cart.length === 0) { setCredit(null); return undefined; }
    let active = true;
    const t = setTimeout(() => {
      axios.get(`${API}/customers/${cid}/credit-status`, { params: { amount: p.grand } })
        .then((r) => { if (active) setCredit(r.data); }).catch(() => { if (active) setCredit(null); });
    }, 350);
    return () => { active = false; clearTimeout(t); };
  }, [open, selectedCustomer, p.grand, cart.length]); // eslint-disable-line

  const backorderQtyTotal = Object.values(allocation.map || {}).reduce((s, l) => s + (Number(l?.breakdown?.backorder) || 0), 0);
  const hasBackorderLine = backorderQtyTotal > 0;
  const mixedLotLines = (lotPlan?.lines || []).filter((l) => l.requires_confirmation);
  const requiresLotConfirmation = !!lotPlan?.requires_confirmation && mixedLotLines.length > 0;
  const creditBlocked = !!credit && credit.blocked && !credit.has_approved_override;

  const updateQty = (id, q) => setCart(cart.map((it) => it.product.id === id ? { ...it, quantity: Number(q) || 0 } : it));
  const updateDiscount = (id, d) => setCart(cart.map((it) => it.product.id === id ? { ...it, discount_percent: Math.max(0, Math.min(100, Number(d) || 0)) } : it));
  const remove = (id) => setCart(cart.filter((it) => it.product.id !== id));

  const doSubmit = (confirmMixed) => {
    onSubmitOrder({
      order_discount_percent: 0, payment_term_code: paymentTerm,
      allow_backorder: allowBackorder, special_prices: linePrices, confirm_mixed_lot: !!confirmMixed,
      needs_tax_invoice: p.isPkp !== false ? needsTaxInvoice : false,
      fulfillment_method: fulfillmentMethod,
      pickup_date: fulfillmentMethod === "ambil" ? pickupDate : "",
      delivery_date: fulfillmentMethod === "kirim" ? deliveryDate : "",
      sales_team: salesTeam,
    });
    onClose();
  };
  const handleSubmitClick = () => { if (requiresLotConfirmation) setShowMixedConfirm(true); else doSubmit(false); };

  const handleRequestTransfer = async (line) => {
    const source = (line.cross_entity || [])[0];
    const destEntity = allocation.entityId || entityFor;
    const qty = line.breakdown?.inter_company || 0;
    if (!source || !destEntity || qty <= 0) return;
    setTransferRequests((t) => ({ ...t, [line.product_id]: "requesting" }));
    try {
      await axios.post(`${API}/transfers/inter-company`, {
        source_entity_id: source.entity_id, dest_entity_id: destEntity,
        items: [{ product_id: line.product_id, quantity: qty, unit: line.unit }],
        notes: "Permintaan dari POS checkout (Fulfillment Assistant)",
      });
      setTransferRequests((t) => ({ ...t, [line.product_id]: "requested" }));
    } catch { setTransferRequests((t) => ({ ...t, [line.product_id]: "error" })); }
  };

  if (!open) return null;
  const canNext1 = !!selectedCustomer && !!selectedAddress;
  const canNext2 = cart.length > 0 && !lotPlan.loading;
  const pickupInvalid = fulfillmentMethod === "ambil" && !pickupDate;
  const teamInvalid = !!salesTeamError(salesTeam);
  const deliveryInvalid = fulfillmentMethod === "kirim" && !!deliveryDate && deliveryDate < new Date().toISOString().slice(0, 10);

  return (
    <div className="fixed inset-0 z-[110] flex justify-end bg-black/40" data-testid="checkout-drawer">
      <div className="flex h-full w-full max-w-[520px] flex-col bg-[#F7F8FA] shadow-2xl">
        {/* Header + stepper */}
        <div className="border-b border-[#EFF0F2] bg-white px-4 py-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[15px] font-bold">Checkout</h2>
            <button data-testid="checkout-close" className="icon-button" onClick={onClose} aria-label="Tutup"><X size={18} /></button>
          </div>
          <div className="mt-3 flex items-center">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              const active = step === s.n, done = step > s.n;
              return (
                <div key={s.n} className="flex flex-1 items-center">
                  <div data-testid={`checkout-step-indicator-${s.n}`} className={`flex items-center gap-1.5 ${active ? "text-[#0058CC]" : done ? "text-[#126E2C]" : "text-[#9A9BA3]"}`}>
                    <span className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold ${active ? "bg-[#0058CC] text-white" : done ? "bg-[#126E2C] text-white" : "bg-[#E5E5EA] text-[#6B6B73]"}`}>
                      {done ? <CheckCircle2 size={14} /> : s.n}
                    </span>
                    <span className="hidden text-[11px] font-semibold sm:inline">{s.label}</span>
                  </div>
                  {i < STEPS.length - 1 && <div className={`mx-1.5 h-0.5 flex-1 ${done ? "bg-[#126E2C]" : "bg-[#E5E5EA]"}`} />}
                </div>
              );
            })}
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {step === 1 && (
            <div data-testid="checkout-step-1" className="space-y-3">
              <div className="section-card">
                <div className="section-head"><div className="flex items-center gap-2"><Users size={14} className="text-[#0058CC]" /><h2 className="text-[13px]">Pilih Pelanggan</h2></div></div>
                <div className="section-body space-y-3">
                  <KNSelect data-testid="checkout-customer-select" className="field w-full" value={selectedCustomer?.id || ""}
                    onValueChange={(id) => { setSelectedCustomer(customers.find((c) => c.id === id)); setSelectedAddress(""); }}
                    placeholder="-- Pilih pelanggan --"
                    options={[{ value: "", label: "-- Pilih pelanggan --" }, ...customers.map((c) => ({ value: c.id, label: `${c.name} — ${c.city}` }))]} />
                  <button data-testid="checkout-new-customer-button" className="secondary-button w-full" onClick={() => setShowCreateCustomer(true)}><UserPlus size={14} /> Pelanggan Baru</button>
                  {selectedCustomer && (
                    <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
                      <p data-testid="checkout-selected-customer" className="text-[12.5px] font-semibold">{selectedCustomer.name}</p>
                      <p className="text-[11px] text-[#3C3C43]">{selectedCustomer.pic_name} • {selectedCustomer.phone}</p>
                      <div className="mt-1.5"><StoreCreditBadge customerId={selectedCustomer.id} testId="checkout-store-credit" /></div>
                    </div>
                  )}
                  {selectedCustomer && (
                    <div data-testid="checkout-address-select">
                      <label className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]"><MapPin size={11} /> Alamat Pengiriman</label>
                      <KNSelect className="field w-full" value={selectedAddress || ""} onValueChange={setSelectedAddress}
                        placeholder="-- Pilih alamat --"
                        options={[{ value: "", label: "-- Pilih alamat --" }, ...addresses.map((a) => ({ value: a.id, label: `${a.label} — ${a.city}` }))]} />
                    </div>
                  )}
                </div>
              </div>

              {cart.length > 0 && (
                <div className="section-card" data-testid="checkout-step1-items">
                  <div className="section-head"><div className="flex items-center gap-2"><PackageCheck size={14} className="text-[#0058CC]" /><h2 className="text-[13px]">Item Pesanan ({cart.length})</h2></div></div>
                  <div className="section-body space-y-1.5">
                    {cart.map((it) => (
                      <div key={it.product.id} data-testid={`step1-item-${it.product.id}`} className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-[12px] font-semibold truncate">{it.product.name}</p>
                            <p className="text-[10.5px] text-[#6B6B73]">
                              {it.product.sku} · {formatQty(it.quantity)} {it.product.base_unit || "meter"}
                              {it.purchase_mode === "roll" && (
                                <span data-testid={`step1-item-rollmode-${it.product.id}`} className="ml-1 inline-flex items-center gap-0.5 rounded-full bg-[#EAF2FF] px-1.5 py-0.5 text-[9px] font-bold text-[#0058CC]"><Layers size={9} /> per roll · qty terkunci</span>
                              )}
                            </p>
                          </div>
                          {/* F1b — ringkasan langkah-1 WAJIB memakai harga efektif pelanggan.
                              Dulu memakai `it.product.price` (harga umum) sehingga satu layar
                              menampilkan dua total berbeda dengan tombol keranjang. */}
                          <p className="shrink-0 text-right text-[12px] font-semibold tabular-nums">
                            {formatCurrency(Number(linePrices[it.product.id]?.price ?? it.product.price ?? 0) * (it.quantity || 0))}
                            {linePrices[it.product.id]
                              && ["customer", "special_approval"].includes(linePrices[it.product.id].source) && (
                              <span data-testid={`step1-item-source-${it.product.id}`} className="block text-[9.5px] font-bold"
                                style={{ color: sourceMeta(linePrices[it.product.id].source).fg }}>
                                {sourceMeta(linePrices[it.product.id].source).label}
                              </span>
                            )}
                          </p>
                        </div>
                        {it.purchase_mode === "roll" && (it.rolls_snapshot || []).length > 0 && (
                          <div data-testid={`cart-item-rolls-${it.product.id}`} className="mt-1.5 rounded-md border border-[#E0E7FF] bg-[#F5F8FF] p-2">
                            <p className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[#0058CC]">
                              <Layers size={11} /> {(it.rolls_snapshot || []).length} roll dipilih
                            </p>
                            <div className="space-y-0.5">
                              {(it.rolls_snapshot || []).map((r) => (
                                <div key={r.roll_id} className="flex items-center gap-1.5 text-[10.5px]">
                                  <span className="font-semibold text-[#1C1C1E]">{r.roll_no}</span>
                                  <span className="text-[#8E8E93]">· {formatQty(r.length)} {it.product.base_unit || "meter"}</span>
                                  <span className={`ml-auto inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${r.is_cross_entity ? "bg-[#FFF3E0] text-[#9A5B00]" : "bg-[#EEF1F4] text-[#3C3C43]"}`}>
                                    {r.owner_entity_name}{r.is_cross_entity ? " · transfer" : ""}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 2 && (
            <div data-testid="checkout-step-2" className="space-y-2">
              {cart.length === 0 && <p data-testid="checkout-empty" className="rounded-md border border-dashed border-[#E5E5EA] bg-white p-3 text-[12px] text-[#6B6B73]">Keranjang kosong.</p>}
              {cart.map((item) => (
                <CheckoutItemCard
                  key={item.product.id}
                  item={item}
                  sp={linePrices[item.product.id]}
                  notice={spNotice[item.product.id]}
                  allowItemDiscount={allowItemDiscount}
                  selectedCustomer={selectedCustomer}
                  onRemove={remove}
                  onUpdateQty={updateQty}
                  onUpdateDiscount={updateDiscount}
                  onRequestSpecial={() => setSpModalItem(item)}
                  allocationLine={allocation.map[item.product.id]}
                  allocationLoading={allocation.loading}
                  reqStatus={transferRequests[item.product.id]}
                  onRequestTransfer={handleRequestTransfer}
                />
              ))}

              {cart.length > 0 && (
                <div className="grid gap-2 rounded-md border border-[#EFF0F2] bg-white p-2.5">
                  <div>
                    <label className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Termin Pembayaran</label>
                    <KNSelect data-testid="payment-term-select" className="field" value={paymentTerm} onValueChange={setPaymentTerm}
                      options={paymentTerms.length === 0 ? [{ value: "", label: "Default" }] : paymentTerms.map((t) => ({ value: t.code, label: t.name }))} />
                  </div>
                  {allowOrderDiscount && (
                    <div>
                      <label className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Diskon Pesanan (%)</label>
                      <input data-testid="order-discount-input" className="field" type="number" min="0" max="100" value={orderDiscount} onChange={(e) => setOrderDiscount(Math.max(0, Math.min(100, Number(e.target.value) || 0)))} />
                    </div>
                  )}
                  <p data-testid="sales-discount-note" className="rounded-md bg-[#FFF7EC] px-2 py-1.5 text-[10px] text-[#9A5B00]">
                    Potongan harga hanya via <b>Harga Khusus</b>. Klik <b>"Minta Harga Khusus"</b> di tiap item untuk mengajukan langsung dari sini (disetujui manager/admin).
                  </p>
                </div>
              )}

              {cart.length > 0 && selectedCustomer && (
                <div data-testid="checkout-sales-team" className="rounded-md border border-[#EFF0F2] bg-white p-2.5">
                  <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">
                    <Users size={13} className="text-[#0058CC]" /> Tim Sales & Bagi Insentif (pesanan ini)
                  </div>
                  <p className="mb-2 text-[10.5px] text-[#8E8E93]">Terisi otomatis dari bawaan pelanggan — bisa diubah khusus untuk pesanan ini (PIC + pendamping sales, total bagi 100%).</p>
                  <SalesTeamEditor value={salesTeam} onChange={setSalesTeam} />
                </div>
              )}

              {hasBackorderLine && (
                <div data-testid="backorder-option-card" className="rounded-md border border-[#F5C9A6] bg-[#FFF7EF] p-2.5">
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[#A8221A]" />
                    <div>
                      <p className="text-[11.5px] font-semibold text-[#8C4A00]">Stok entitas tidak cukup untuk {formatQty(backorderQtyTotal)} unit.</p>
                      <label className="mt-1.5 flex cursor-pointer items-center gap-2">
                        <input data-testid="allow-backorder-checkbox" type="checkbox" className="h-3.5 w-3.5 accent-[#0058CC]" checked={allowBackorder} onChange={(e) => setAllowBackorder(e.target.checked)} />
                        <span className="text-[11.5px] font-medium text-[#1C1C1E]">Izinkan backorder (reservasi stok tersedia, sisanya menunggu barang masuk)</span>
                      </label>
                    </div>
                  </div>
                </div>
              )}
              {requiresLotConfirmation && (
                <div data-testid="mixed-lot-warning-card" className="rounded-md border border-[#D9C2EE] bg-[#F7F2FE] p-2.5">
                  <div className="flex items-start gap-2">
                    <Layers size={14} className="mt-0.5 shrink-0 text-[#6B219A]" />
                    <div>
                      <p className="text-[11.5px] font-semibold text-[#5B1A86]">{mixedLotLines.length} item akan dipenuhi dari beberapa lot (mixed lot).</p>
                      <p className="mt-0.5 text-[10.5px] text-[#6B219A]">Konfirmasi diperlukan saat membuat pesanan — warna/dye-lot bisa berbeda antar lot.</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 3 && (
            <CheckoutStep3
              fulfillmentMethod={fulfillmentMethod} setFulfillmentMethod={setFulfillmentMethod}
              pickupDate={pickupDate} setPickupDate={setPickupDate}
              selectedCustomer={selectedCustomer} addresses={addresses} selectedAddress={selectedAddress}
              p={p} cart={cart} paymentTerm={paymentTerm}
              needsTaxInvoice={needsTaxInvoice} setNeedsTaxInvoice={setNeedsTaxInvoice}
              credit={credit} creditBlocked={creditBlocked}
              hasBackorderLine={hasBackorderLine} allowBackorder={allowBackorder}
              requiresLotConfirmation={requiresLotConfirmation} mixedLotLines={mixedLotLines}
            />
          )}
        </div>

        {/* Footer nav */}
        <div className="border-t border-[#EFF0F2] bg-white px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            {step > 1 ? (
              <button data-testid="checkout-back" className="secondary-button" onClick={() => setStep(step - 1)}><ChevronLeft size={14} /> Kembali</button>
            ) : <span />}
            {step < 3 ? (
              <button data-testid="checkout-next" className="primary-button" disabled={step === 1 ? !canNext1 : !canNext2} onClick={() => setStep(step + 1)}>
                Lanjut <ChevronRight size={14} />
              </button>
            ) : (
              <button data-testid="checkout-submit" className="primary-button" disabled={!canWrite || !selectedCustomer || !selectedAddress || cart.length === 0 || lotPlan.loading || creditBlocked || pickupInvalid || deliveryInvalid || teamInvalid} title={writeBlockHint} onClick={handleSubmitClick}>
                <PackageCheck size={14} /> {!canWrite ? "Pilih Badan Usaha Dulu" : creditBlocked ? "Terblokir Kredit" : pickupInvalid ? "Pilih Tanggal Ambil" : teamInvalid ? "Perbaiki Tim Sales" : deliveryInvalid ? "Tanggal Kirim Tak Valid" : requiresLotConfirmation ? "Tinjau Lot & Buat" : "Buat Sales Order"}
              </button>
            )}
          </div>
        </div>
      </div>

      <CreateCustomerModal open={showCreateCustomer} onClose={() => setShowCreateCustomer(false)} onCreateCustomer={onCreateCustomer} />
      <RequestSpecialPriceModal
        open={!!spModalItem}
        onClose={() => setSpModalItem(null)}
        product={spModalItem?.product}
        customer={selectedCustomer}
        entityId={entityFor}
        defaultQty={spModalItem?.quantity || 0}
        canApprove={canApprovePrice}
        onSubmitted={({ productId, applied, message }) => {
          setSpNotice((prev) => ({ ...prev, [productId]: { applied, message } }));
          if (applied) setSpRefresh((x) => x + 1);  // muat ulang harga khusus efektif → badge terpasang
        }}
      />
      <MixedLotConfirmModal open={showMixedConfirm} lines={mixedLotLines} policy={lotPlan?.policy || {}} onCancel={() => setShowMixedConfirm(false)} onConfirm={() => { setShowMixedConfirm(false); doSubmit(true); }} />
    </div>
  );
}
