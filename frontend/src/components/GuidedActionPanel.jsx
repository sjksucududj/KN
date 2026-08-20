import { Sparkles } from "lucide-react";

export default function GuidedActionPanel({ activeView, user, onNavigate }) {
  const guidance = {
    admin: { title: "Langkah admin berikutnya", body: "Kelola master data, review permission, lalu cek Audit untuk memastikan setiap perubahan terekam.", action: "Buka Audit", target: "admin" },
    sales: { title: "Langkah sales berikutnya", body: "Pilih customer, inspect stok per gudang, tambahkan item ke draft, lalu reserve sales order.", action: "Cari Produk", target: "sales" },
    orders: { title: "Langkah pesanan berikutnya", body: "Klik order untuk melihat allocation plan, lalu approve/confirm sesuai status. Invoice dibuat saat confirmed.", action: "Review Orders", target: "orders" },
    operations: { title: "Langkah gudang berikutnya", body: "Pilih task WMS, scan SKU/batch/lot/roll/bin, review queue, lalu submit/advance stage.", action: "Buka Scanner", target: "operations" },
    documents: { title: "Langkah dokumen berikutnya", body: "Generate template, barcode label, invoice, atau surat jalan dari transaksi yang sudah valid.", action: "Print Center", target: "documents" },
  };
  const item = guidance[activeView] || guidance.sales;
  return (
    <div data-testid="guided-action-panel" className="mx-auto mt-4 max-w-[1600px] px-4 no-print">
      <div className="guided-panel flex flex-col gap-3 rounded-[22px] px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p data-testid="guided-action-title" className="text-sm font-black text-[#007AFF]">{item.title}</p>
          <p data-testid="guided-action-body" className="text-sm font-bold text-[#3C3C43]">{item.body} Role aktif: {user?.role}.</p>
        </div>
        <button data-testid="guided-action-button" className="secondary-button" onClick={() => onNavigate(item.target)}><Sparkles size={16} /> {item.action}</button>
      </div>
    </div>
  );
}
