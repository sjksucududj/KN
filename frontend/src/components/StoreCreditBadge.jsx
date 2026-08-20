/**
 * StoreCreditBadge (R5.2) — chip saldo store credit pelanggan (read-only awareness).
 * Dipakai di POS checkout, detail order/invoice, dsb. Tidak tampil bila saldo 0.
 */
import { useEffect, useState } from "react";
import { Wallet } from "lucide-react";
import axios, { API } from "../services/apiClient";
import { formatCurrency } from "../utils/formatters";

export default function StoreCreditBadge({ customerId, entityId, testId = "store-credit-badge" }) {
  const [bal, setBal] = useState(null);

  useEffect(() => {
    let alive = true;
    if (!customerId) { setBal(null); return; }
    (async () => {
      try {
        const res = await axios.get(`${API}/store-credit/balance`, {
          params: { customer_id: customerId, entity_id: entityId || undefined },
        });
        if (alive) setBal(Number(res.data?.balance || 0));
      } catch { if (alive) setBal(null); }
    })();
    return () => { alive = false; };
  }, [customerId, entityId]);

  if (!bal || bal <= 0) return null;
  return (
    <span
      data-testid={testId}
      className="inline-flex items-center gap-1 rounded-md border border-[#D9C7EC] bg-[#F3EAFB] px-2 py-0.5 text-[11px] font-semibold text-[#6B219A]"
      title="Saldo store credit pelanggan (dapat dipakai melunasi piutang pesanan)"
    >
      <Wallet size={11} /> Store Credit: {formatCurrency(bal)}
    </span>
  );
}
