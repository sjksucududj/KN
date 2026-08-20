"""FASE G-6 — Skema `interco_transactions`, `interco_accounts`, `interco_settlements`.

Antar entitas = **jual-beli** (bukan pindah gudang). Setiap transaksi lahir sebagai
**dokumen kembar**: satu baris di PT penjual (`role="seller"`), satu di PT pembeli
(`role="buyer"`), saling menunjuk lewat `pair_id`.

Semua nominal memakai `MoneyDecimal` (PS-15): menerima "1.000,50" maupun "1000.5".
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from core_utils import MoneyDecimal, QtyDecimal


class IntercoLineIn(BaseModel):
    product_id: str
    quantity: QtyDecimal = Field(..., gt=0)
    unit_price: Optional[MoneyDecimal] = Field(None, ge=0)  # None = ambil dari kontrak internal
    notes: str = ""
    # FASE U — DUA SATUAN: jumlah gulungan (roll) di samping ukuran (`quantity`+`unit`).
    # `None` = dokumen/baris ini tidak menyebut jumlah roll (dokumen LAMA tampil "—",
    # BUKAN "0 roll" yang menyesatkan). Diisi manual saat memesan (rencana), atau
    # DIHITUNG dari roll nyata saat penerimaan/pengiriman/retur (lihat §U.D rencana).
    qty_rolls: Optional[int] = Field(None, ge=0)


class IntercoCreate(BaseModel):
    seller_entity_id: str
    buyer_entity_id: str
    items: List[IntercoLineIn] = Field(default_factory=list)
    contract_id: str = ""            # kontrak internal (partner_kind="entity") — opsional (auto-resolve bila kosong)
    pricing_mode: str = ""           # kosong = pakai config `antar_entitas.pricing_mode`
    ppn_mode: str = ""               # kosong = pakai config per-PT `antar_entitas.ppn_mode`
    doc_date: str = ""               # default: hari ini
    due_date: str = ""
    notes: str = ""
    submit_now: bool = False         # bila True → langsung confirmed
    # FASE E-7 (E7d) / E8.12 — asal permintaan (permintaan internal & pesanan pelanggan)
    # supaya "IC ini untuk SO mana" tidak lagi hanya tertulis di catatan bebas.
    source_request_id: str = ""
    source_request_number: str = ""
    source_order_id: str = ""
    source_order_number: str = ""


class IntercoActionIn(BaseModel):
    note: str = ""


class IntercoSettlementBillPick(BaseModel):
    """Satu transaksi antar-PT yang ditarik ke settlement (netting)."""
    interco_id: str
    applied_amount: Optional[MoneyDecimal] = Field(None, ge=0)  # None = seluruh sisa


class IntercoSettlementCreate(BaseModel):
    """FASE G-6 US6 — Pelunasan sekaligus (netting) satu pasangan PT."""
    payer_entity_id: str             # PT yang membayar
    payee_entity_id: str             # PT yang menerima
    transactions: List[IntercoSettlementBillPick] = Field(default_factory=list)
    settle_date: str = ""            # default: hari ini
    method: str = "netting"          # netting | transfer | cash
    bank_account_id: str = ""
    notes: str = ""


# ═════════════════════════════════════════════════════════════════════════════
#  FASE G-6b — faktur pajak internal · retur antar-PT · alasan
# ═════════════════════════════════════════════════════════════════════════════
class IntercoReasonIn(BaseModel):
    """Aksi yang WAJIB ber-alasan (batal / ganti faktur pajak / batal retur)."""
    reason: str = ""


class IntercoTaxIssueIn(BaseModel):
    """Terbitkan faktur pajak internal. NSFP DJP boleh diisi menyusul."""
    nsfp: str = ""
    kode_transaksi: str = "01"
    faktur_date: str = ""


class IntercoReturnLineIn(BaseModel):
    product_id: str
    quantity: QtyDecimal = Field(..., gt=0)
    # FASE E-9 (E9.4) — roll yang DIPILIH untuk dikirim balik. Kosong = mesin
    # mengutamakan roll hasil retur pelanggan (lot `RTN-…`) sebelum FEFO biasa,
    # supaya roll bagus tidak terkirim balik sementara roll cacat tinggal.
    roll_ids: List[str] = Field(default_factory=list)
    notes: str = ""


class IntercoReturnCreate(BaseModel):
    """Retur antar-PT atas transaksi yang barangnya SUDAH berpindah."""
    interco_id: str
    items: List[IntercoReturnLineIn] = Field(default_factory=list)
    reason: str = ""
    notes: str = ""
    doc_date: str = ""
    # FASE E-9 (E9.6) — retur pelanggan yang MEMICU retur antar-PT ini, supaya
    # rantai retur (pelanggan → antar-PT → beli/simpan) bisa ditelusuri satu layar.
    source_sales_return_id: str = ""
