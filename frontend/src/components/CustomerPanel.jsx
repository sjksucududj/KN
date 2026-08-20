import { useState, useEffect } from "react";
import { Users, UserPlus } from "lucide-react";
import KNSelect from "./KNSelect";

// P0-4 — kebijakan lot/dye-lot per customer (KN_15 / textile traceability)
const LOT_POLICY_OPTIONS = [
  { value: "", label: "Default (prefer single)" },
  { value: "prefer_single", label: "Prefer single lot" },
  { value: "strict_single", label: "Strict single lot" },
  { value: "allow_mixed", label: "Boleh mixed lot" },
];

export function CustomerPanel({ 
  customers, 
  selectedCustomer, 
  setSelectedCustomer, 
  selectedAddress, 
  setSelectedAddress, 
  onCreateCustomer, 
  onShowDetail 
}) {
  const [form, setForm] = useState({ 
    name: "", 
    pic_name: "", 
    phone: "", 
    city: "Jakarta", 
    address: "",
    enforce_single_dye_lot: false,
    lot_policy: "",
  });
  
  const addresses = selectedCustomer?.addresses || [];
  
  useEffect(() => {
    if (selectedCustomer && !selectedAddress) {
      setSelectedAddress(selectedCustomer.addresses?.[0]?.id || "");
    }
  }, [selectedCustomer, selectedAddress, setSelectedAddress]);
  
  return (
    <section data-testid="customer-panel" className="section-card">
      <div className="section-head">
        <div className="flex items-center gap-2 min-w-0">
          <Users data-testid="customer-panel-icon" size={14} className="text-[#0058CC]" />
          <span className="kicker">Master Pelanggan</span>
          <h2>Pelanggan aktif</h2>
        </div>
      </div>
      <div className="section-body">
        {/* Customer Dropdown */}
        <div data-testid="customer-select" className="mb-3">
          <label className="block text-[10px] font-bold uppercase tracking-wide text-[#6B6B73] mb-1.5">
            Pilih Pelanggan
          </label>
          <KNSelect
            className="field w-full"
            value={selectedCustomer?.id || ""}
            onValueChange={(id) => {
              const customer = customers.find(c => c.id === id);
              setSelectedCustomer(customer);
            }}
            placeholder="-- Pilih pelanggan dari master --"
            options={[
              { value: "", label: "-- Pilih pelanggan dari master --" },
              ...customers.map(c => ({ value: c.id, label: `${c.name} — ${c.city}` })),
            ]}
          />
        </div>
        
        {selectedCustomer && (
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
            <button 
              data-testid="selected-customer-info" 
              className="interactive-card w-full rounded-md bg-white p-2 text-left border border-[#EFF0F2]" 
              onClick={() => onShowDetail({ 
                title: selectedCustomer.name, 
                body: "Customer aktif untuk sales order ini. Pilih alamat pengiriman yang tepat agar Surat Jalan jelas.", 
                facts: [
                  { label: "PIC", value: selectedCustomer.pic_name }, 
                  { label: "Telepon", value: selectedCustomer.phone }, 
                  { label: "Alamat", value: addresses.length }
                ], 
                target: "sales", 
                cta: "Lanjut ke pesanan" 
              })}
            >
              <p data-testid="selected-customer-name" className="text-[12.5px] font-semibold">
                {selectedCustomer.name}
              </p>
              <p data-testid="selected-customer-contact" className="text-[11px] text-[#3C3C43]">
                {selectedCustomer.pic_name} • {selectedCustomer.phone}
              </p>
            </button>
            {addresses.length > 0 && (
              <div data-testid="shipping-address-select" className="mt-2">
                <label className="block text-[10px] font-bold uppercase tracking-wide text-[#6B6B73] mb-1">
                  Alamat Pengiriman
                </label>
                <KNSelect
                  className="field w-full"
                  value={selectedAddress || ""}
                  onValueChange={setSelectedAddress}
                  placeholder="-- Pilih alamat --"
                  options={[
                    { value: "", label: "-- Pilih alamat --" },
                    ...addresses.map(a => ({ value: a.id, label: `${a.label} — ${a.city}` })),
                  ]}
                />
              </div>
            )}
          </div>
        )}
        <div className="mt-3 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
          <p className="mb-2 text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
            Pelanggan baru langsung aktif
          </p>
          <div className="grid gap-2">
            <input 
              data-testid="new-customer-name-input" 
              className="field" 
              placeholder="Nama pelanggan" 
              value={form.name} 
              onChange={(e) => setForm({ ...form, name: e.target.value })} 
            />
            <input 
              data-testid="new-customer-pic-input" 
              className="field" 
              placeholder="Nama PIC" 
              value={form.pic_name} 
              onChange={(e) => setForm({ ...form, pic_name: e.target.value })} 
            />
            <input 
              data-testid="new-customer-phone-input" 
              className="field" 
              placeholder="No. WhatsApp" 
              value={form.phone} 
              onChange={(e) => setForm({ ...form, phone: e.target.value })} 
            />
            <div className="grid gap-2 sm:grid-cols-2">
              <input 
                data-testid="new-customer-city-input" 
                className="field" 
                placeholder="Kota" 
                value={form.city} 
                onChange={(e) => setForm({ ...form, city: e.target.value })} 
              />
              <input 
                data-testid="new-customer-address-input" 
                className="field" 
                placeholder="Alamat" 
                value={form.address} 
                onChange={(e) => setForm({ ...form, address: e.target.value })} 
              />
            </div>
            <div className="grid gap-2 rounded-md border border-[#E5C7F5] bg-[#FBF7FF] p-2">
              <label data-testid="new-customer-enforce-dyelot"
                className="flex items-start gap-2 text-[11px] text-[#3C3C43] cursor-pointer">
                <input type="checkbox" className="mt-0.5"
                  checked={form.enforce_single_dye_lot}
                  onChange={(e) => setForm({ ...form, enforce_single_dye_lot: e.target.checked })} />
                <span>Paksa <b>1 dye lot</b> saat alokasi (tekstil — hindari belang warna antar roll)</span>
              </label>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wide text-[#6B6B73] mb-1">
                  Kebijakan Lot
                </label>
                <KNSelect
                  data-testid="new-customer-lot-policy"
                  className="field w-full"
                  value={form.lot_policy}
                  onValueChange={(v) => setForm({ ...form, lot_policy: v })}
                  options={LOT_POLICY_OPTIONS}
                />
              </div>
            </div>
            <button 
              data-testid="create-customer-button" 
              className="secondary-button" 
              onClick={() => onCreateCustomer(form)}
            >
              <UserPlus size={14} /> Buat Pelanggan
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
