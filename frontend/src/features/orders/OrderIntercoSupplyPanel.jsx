import { useCallback, useEffect, useState } from "react";
import { Building2 } from "lucide-react";
import { formatQty } from "../../utils/formatters";
import axios, { API } from "../../services/apiClient";

/**
 * OrderIntercoSupplyPanel — FASE E-9 (E9.2 · US23/US24) · "kekurangannya diambil dari PT mana".
 *
 * MENGAPA PANEL INI MENGAMBIL DATANYA SENDIRI
 * ===========================================
 * `interco_supply` adalah field TURUNAN: ia dihitung saat `GET /sales-orders/{id}`
 * dipanggil (menelusuri `interco_transactions.source_order_id` + status tugas gudang),
 * dan sengaja TIDAK disertakan pada respons DAFTAR supaya daftar pesanan tidak
 * menembak N+1 query tiap kali dibuka.
 *
 * Bug yang ditutup berkas ini (ditemukan uji layar sesi 2026-08-15): panel detail
 * membaca `sel.interco_supply`, padahal `sel` berasal dari respons DAFTAR
 * (`GET /dashboard` → `orders[]`). Field itu tidak pernah ada di sana, jadi pita
 * "Dipenuhi dari Badan Usaha Lain" TIDAK PERNAH tampil — walau backend sudah benar
 * (POC E-9 hijau karena ia memeriksa endpoint DETAIL, bukan sumber data layar).
 * Akibatnya user story US24 tidak bisa dibuktikan di layar, dan risiko nyatanya:
 * ada yang menerbitkan permintaan beli KEDUA untuk barang yang sudah di jalan.
 *
 * Karena itu panel ini memanggil endpoint detail sendiri (pola yang sudah dipakai
 * `OrderJourneyPanel`), memakai data daftar sebagai nilai awal bila ada.
 */
export default function OrderIntercoSupplyPanel({ orderId, fallback }) {
  const [rows, setRows] = useState(Array.isArray(fallback) ? fallback : []);

  const load = useCallback(async (id) => {
    if (!id) return [];
    try {
      const res = await axios.get(`${API}/sales-orders/${id}`);
      return Array.isArray(res.data?.interco_supply) ? res.data.interco_supply : [];
    } catch {
      // Panel pelengkap tidak boleh menjatuhkan layar detail pesanan.
      return [];
    }
  }, []);

  useEffect(() => {
    let active = true;
    setRows(Array.isArray(fallback) ? fallback : []);
    load(orderId).then((r) => { if (active && r.length) setRows(r); });
    return () => { active = false; };
  }, [orderId, load]);

  if (!rows.length) return null;

  return (
    <div data-testid="order-interco-supply-panel"
         className="rounded-md border border-[#BDE5CC] bg-[#F2FBF6] p-2.5">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Building2 size={13} className="text-[#0F6B52]" />
        <p className="text-[10px] font-bold uppercase tracking-wide text-[#0F6B52]">
          Dipenuhi dari Badan Usaha Lain
        </p>
      </div>
      <div className="space-y-1">
        {rows.map((ic) => (
          <div key={ic.interco_id}
               data-testid={`order-interco-supply-${ic.interco_id}`}
               className="rounded bg-white/80 px-2 py-1.5 text-[10.5px]">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-[#1C1C1E] truncate">
                {(ic.items || []).map((x) => `${formatQty(x.quantity)} ${x.unit || ""} ${x.product_name || x.sku}`).join(" · ")}
              </span>
              <span className={`shrink-0 text-[9.5px] rounded px-1.5 py-0.5 border ${
                ic.goods_arrived
                  ? "bg-[#E6F6EC] text-[#1B7F4B] border-[#BDE5CC]"
                  : "bg-[#FFF3DC] text-[#9A6700] border-[#EFD9A8]"}`}>
                {ic.goods_arrived ? "Barang sudah masuk" : ic.status_label || ic.status}
              </span>
            </div>
            <p className="text-[10px] text-[#3C6B57] mt-0.5">
              diambil dari <b>{ic.from_entity_name || "badan usaha lain"}</b> lewat{" "}
              <b>{ic.number}</b>
              {ic.eta ? ` · janji ${ic.eta}` : ""}
              {ic.warehouse_transfer_code ? ` · tugas gudang ${ic.warehouse_transfer_code}` : ""}
              {ic.source_request_number ? ` · dari permintaan ${ic.source_request_number}` : ""}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
