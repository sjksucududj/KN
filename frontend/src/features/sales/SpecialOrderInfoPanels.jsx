/**
 * Special Order Detail — body panels.
 * Left: custom item details. Right: customer info + status timeline.
 */
import { Clock, Package } from "lucide-react";
import { STATUS_STYLE, fmtNum, fmtDate } from "./SpecialOrderShared";

export function SpecialOrderInfoPanels({ order }) {
  return (
    <div className="detail-grid-2col" data-testid="special-order-info-panels">
      {/* Left: Custom Item Details */}
      <div className="section-card">
        <div className="section-header">
          <Package size={14} /> Custom Item Details
        </div>

        <div className="space-y-4">
          <div>
            <div className="font-semibold mb-1">Deskripsi:</div>
            <div className="text-lg">{order.custom_item?.description || "-"}</div>
          </div>

          {order.custom_item?.specifications && Object.keys(order.custom_item.specifications).length > 0 ? (
            <div>
              <div className="font-semibold mb-2">Spesifikasi Custom:</div>
              <table className="data-table">
                <tbody>
                  {Object.entries(order.custom_item.specifications).map(([key, value]) => (
                    <tr key={key}>
                      <td className="font-medium">{key}</td>
                      <td>{value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-sm text-muted italic">Belum ada spesifikasi custom.</div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-muted">Jumlah</div>
              <div className="font-semibold text-lg">
                {fmtNum(order.custom_item?.quantity, 2)} {order.custom_item?.unit}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted">Harga Target</div>
              <div className="font-semibold text-lg tabular-nums">
                Rp {fmtNum(order.custom_item?.target_price, 0)}
              </div>
            </div>
          </div>

          <div>
            <div className="text-sm text-muted">Total Amount</div>
            <div className="font-bold text-2xl text-primary tabular-nums">
              Rp {fmtNum(order.total_amount, 0)}
            </div>
          </div>

          <div>
            <div className="text-sm text-muted">Perkiraan Pengiriman</div>
            <div className="font-medium">
              <Clock size={12} className="inline mr-1" />
              {fmtDate(order.expected_delivery)}
            </div>
          </div>

          {order.notes && (
            <div>
              <div className="text-sm text-muted">Catatan</div>
              <div className="section-notes">{order.notes}</div>
            </div>
          )}
        </div>
      </div>

      {/* Right: Customer & Status History */}
      <div className="space-y-4">
        {/* Customer Info */}
        <div className="section-card">
          <div className="section-header">Info Pelanggan</div>
          <div className="space-y-2">
            <div>
              <div className="text-sm text-muted">Name</div>
              <div className="font-semibold">{order.customer_name}</div>
            </div>
            {order.customer_email && (
              <div>
                <div className="text-sm text-muted">Email</div>
                <div>{order.customer_email}</div>
              </div>
            )}
            {order.customer_phone && (
              <div>
                <div className="text-sm text-muted">Telepon</div>
                <div>{order.customer_phone}</div>
              </div>
            )}
            {order.shipping_address && (
              <div>
                <div className="text-sm text-muted">Shipping Address</div>
                <div className="text-sm">
                  {order.shipping_address.street && <div>{order.shipping_address.street}</div>}
                  <div>
                    {order.shipping_address.city && `${order.shipping_address.city}, `}
                    {order.shipping_address.province}
                    {order.shipping_address.postal_code && ` ${order.shipping_address.postal_code}`}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Status History */}
        {order.status_history && order.status_history.length > 0 && (
          <div className="section-card">
            <div className="section-header">Status Timeline</div>
            <div className="space-y-2">
              {order.status_history.slice().reverse().map((hist, i) => {
                const s = STATUS_STYLE[hist.status] || {};
                const Icon = s.icon || Clock;
                return (
                  <div key={i} className="flex items-start gap-3 text-sm">
                    <Icon size={14} className="text-muted mt-0.5" />
                    <div className="flex-1">
                      <div className="font-medium">{s.label || hist.status}</div>
                      {hist.note && (
                        <div className="text-xs" style={{ color: "#4A4B52" }}>{hist.note}</div>
                      )}
                      <div className="text-xs text-muted">
                        {fmtDate(hist.timestamp)} • {hist.user}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
