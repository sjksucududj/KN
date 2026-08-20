// Konstanta + helper untuk Approval Rules (dipisah agar file view di bawah batas guardrail).
export function fmtNum(n) {
  return new Intl.NumberFormat("id-ID").format(n || 0);
}

export const ENTITY_TYPES = [
  { value: "special_order", label: "Pesanan Khusus (OD)" },
  { value: "purchase_order", label: "Pesanan Pembelian (PO)" },
  { value: "transfer", label: "Transfer Antar-Entitas" },
  { value: "price_approval", label: "Persetujuan Harga" },
  { value: "invoice", label: "Faktur" },
];

export const OPERATORS = [
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
  { value: "eq", label: "=" },
];

export const ROLES = [
  { value: "manager", label: "Manager" },
  { value: "admin", label: "Admin" },
  { value: "owner", label: "Owner" },
];
