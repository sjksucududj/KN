export const formatCurrency = (value) => new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(value || 0);

export const formatQty = (value) => new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value || 0);