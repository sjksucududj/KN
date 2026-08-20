#!/usr/bin/env python3
"""Transformer FASE P4 (gelombang 2) — 4 layar sisa: form yang berupa KOMPONEN sendiri.

Pola di sini berbeda dari gelombang 1: formnya sudah komponen terpisah
(`CreateReturnForm`, `TransferCreateForm`, `ApprovalRuleForm`) atau kartu besar
(`AdminView`). Karena itu komponen anak diberi prop `variant="modal"` untuk melepas
"chrome"-nya sendiri (kartu + judul + tombol kembali) supaya tidak ada kartu di dalam
kartu maupun dua judul, lalu `FormModal` yang menyediakan kepala & tombolnya.
"""
import re
import sys
from pathlib import Path

SRC = Path("/app/frontend/src")
laporan = []


def sunting(rel: str, pasangan, tambah_import=None):
    p = SRC / rel
    s = p.read_text(encoding="utf-8")
    for lama, baru in pasangan:
        if lama not in s:
            laporan.append(f"GAGAL (jangkar tak ketemu) {rel}: {lama.strip()[:70]}")
            return
        s = s.replace(lama, baru, 1)
    if tambah_import and "import FormModal" not in s:
        s = s.replace(tambah_import[0], tambah_import[0] + "\n" + tambah_import[1], 1)
    p.write_text(s, encoding="utf-8")
    laporan.append(f"OK {rel}")


# ── A. CreateReturnForm — bisa dipakai sebagai isi pop-up ────────────────────────
sunting("features/sales/CreateReturnForm.jsx", [
    ("export default function CreateReturnForm({ orders, token, onCreated, onCancel, onLoadOrders }) {",
     "export default function CreateReturnForm({ orders, token, onCreated, onCancel,\n"
     "                                           onLoadOrders, variant = \"page\" }) {\n"
     "  // FASE P4 — `variant=\"modal\"`: lepas chrome halaman (tombol kembali + judul besar)\n"
     "  // karena FormModal sudah menyediakannya; tanpa ini pengguna melihat DUA judul.\n"
     "  const isModal = variant === \"modal\";"),
    ('''    <div data-testid="create-return-form" className="view-container">
      <button className="back-button" onClick={onCancel}><ArrowLeft size={14} /> Batal</button>

      <div className="view-header">
        <div>
          <h1 className="view-title">Buat Return Baru</h1>
          <p className="view-subtitle">Retur barang, Barang Sisa (BS), penggantian, komplain & garansi (purna jual) dari pelanggan</p>
        </div>
      </div>
''',
     '''    <div data-testid="create-return-form" className={isModal ? "" : "view-container"}>
      {!isModal && (
        <button className="back-button" onClick={onCancel}><ArrowLeft size={14} /> Batal</button>
      )}

      {!isModal && (
        <div className="view-header">
          <div>
            <h1 className="view-title">Buat Return Baru</h1>
            <p className="view-subtitle">Retur barang, Barang Sisa (BS), penggantian, komplain & garansi (purna jual) dari pelanggan</p>
          </div>
        </div>
      )}
'''),
    ('      <form onSubmit={handleSubmit} className="form-card">',
     '      <form onSubmit={handleSubmit} className={isModal ? "" : "form-card"}>'),
])

# ── B. SalesReturns — form retur jual jadi pop-up (dulu MENUKAR seluruh halaman) ──
sunting("features/sales/SalesReturns.jsx", [
    ('''  if (showCreate) {
    return (
      <CreateReturnForm
        orders={orders}
        token={token}
        onCreated={(doc) => {
          setShowCreate(false);
          setNotice(`${doc.number} berhasil dibuat.`);
          load();
          setSelected(doc);
        }}
        onCancel={() => setShowCreate(false)}
        onLoadOrders={loadOrders}
      />
    );
  }

''', ""),
    ('''  return (
    <div data-testid="sales-returns-view" className="view-container">''',
     '''  return (
    <div data-testid="sales-returns-view" className="view-container">
      {/* FASE P4 — form retur jual menjadi POP-UP. Sebelumnya tombol "Buat Return"
          MENUKAR seluruh halaman (daftar retur & ringkasan hilang), jadi pengguna
          kehilangan konteks dan harus menekan "kembali" untuk melihat datanya lagi. */}
      <FormModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Buat Retur / Barang Sisa"
        subtitle="Retur, BS, penggantian, komplain & garansi dari pesanan yang sudah dikirim"
        icon={RotateCcw}
        size="lg"
        testId="sales-return-form"
      >
        <CreateReturnForm
          variant="modal"
          orders={orders}
          token={token}
          onCreated={(doc) => {
            setShowCreate(false);
            setNotice(`${doc.number} berhasil dibuat.`);
            load();
            setSelected(doc);
          }}
          onCancel={() => setShowCreate(false)}
          onLoadOrders={loadOrders}
        />
      </FormModal>'''),
], tambah_import=('import CreateReturnForm from "./CreateReturnForm";',
                  'import FormModal from "../../components/FormModal";'))

# ── C. TransferCreateForm — lepas kartu & judulnya sendiri saat dipakai di pop-up ─
sunting("features/wms/transfer/TransferCreateForm.jsx", [
    ("""  products = [], warehouses = [], onAddItem, onRemoveItem, onSubmit, onClose,
}) {
  return (
    <div data-testid="create-transfer-form" className="bg-white border border-[#E5E5EA] rounded-2xl p-6 shadow-sm">
      <h3 className="text-md font-semibold mb-4">Buat Transfer Baru</h3>
""",
     """  products = [], warehouses = [], onAddItem, onRemoveItem, onSubmit, onClose,
  variant = "card",
}) {
  // FASE P4 — `variant="modal"`: kartu & judul sendiri dilepas (FormModal yang
  // menyediakannya) supaya tidak ada kartu di dalam kartu dan dua judul bertumpuk.
  const isModal = variant === "modal";
  return (
    <div data-testid="create-transfer-form"
      className={isModal ? "" : "bg-white border border-[#E5E5EA] rounded-2xl p-6 shadow-sm"}>
      {!isModal && <h3 className="text-md font-semibold mb-4">Buat Transfer Baru</h3>}
"""),
    ("""      <div className="flex gap-2">
        <button
          data-testid="submit-transfer-button"
          onClick={onSubmit}
          className="flex-1 bg-[#007AFF] hover:bg-[#0056B3] text-white rounded-full px-6 py-2.5 font-medium"
        >
          Buat Transfer
        </button>
        <button
          data-testid="cancel-form-button"
          onClick={onClose}
          className="flex-1 bg-white border border-[#E5E5EA] hover:border-[#007AFF] text-[#3C3C43] rounded-full px-6 py-2.5 font-medium"
        >
          Batal
        </button>
      </div>""",
     """      {/* Tombol aksi hanya dipakai pada mode halaman; di pop-up, FormModal yang
          menyediakan tombol Simpan/Batal yang menempel di bawah. */}
      {!isModal && (
        <div className="flex gap-2">
          <button
            data-testid="submit-transfer-button"
            onClick={onSubmit}
            className="flex-1 bg-[#007AFF] hover:bg-[#0056B3] text-white rounded-full px-6 py-2.5 font-medium"
          >
            Buat Transfer
          </button>
          <button
            data-testid="cancel-form-button"
            onClick={onClose}
            className="flex-1 bg-white border border-[#E5E5EA] hover:border-[#007AFF] text-[#3C3C43] rounded-full px-6 py-2.5 font-medium"
          >
            Batal
          </button>
        </div>
      )}"""),
])

# ── D. TransferManagement — bungkus form transfer dengan FormModal ───────────────
sunting("features/wms/TransferManagement.jsx", [
    ("""      {showCreateForm && (
        <TransferCreateForm
          formData={formData}
          setFormData={setFormData}
          newItem={newItem}
          setNewItem={setNewItem}
          products={products}
          warehouses={warehouses}
          onAddItem={handleAddItem}
          onRemoveItem={handleRemoveItem}
          onSubmit={handleCreateTransfer}
          onClose={() => { setShowCreateForm(false); resetForm(); }}
        />
      )}""",
     """      {/* FASE P4 — form transfer menjadi POP-UP: daftar transfer di belakang tetap
          terlihat, jadi pengguna bisa membandingkan sambil mengisi. */}
      <FormModal
        open={showCreateForm}
        onClose={() => { setShowCreateForm(false); resetForm(); }}
        title="Transfer Gudang Baru"
        subtitle="Pilih gudang asal & tujuan, lalu tambahkan barang yang dipindah"
        icon={ArrowRight}
        size="lg"
        testId="transfer-form"
        onSubmit={handleCreateTransfer}
        submitLabel="Buat Transfer"
        submitTestId="submit-transfer-button"
        cancelTestId="cancel-form-button"
      >
        <TransferCreateForm
          variant="modal"
          formData={formData}
          setFormData={setFormData}
          newItem={newItem}
          setNewItem={setNewItem}
          products={products}
          warehouses={warehouses}
          onAddItem={handleAddItem}
          onRemoveItem={handleRemoveItem}
          onSubmit={handleCreateTransfer}
          onClose={() => { setShowCreateForm(false); resetForm(); }}
        />
      </FormModal>"""),
], tambah_import=('import TransferCreateForm from "./transfer/TransferCreateForm";',
                  'import FormModal from "../../components/FormModal";'))

# ── E. ApprovalRuleForm — lepas kartu & judul sendiri saat di pop-up ─────────────
sunting("features/settings/ApprovalRuleForm.jsx", [
    ("""export default function ApprovalRuleForm({ formData, setFormData, onSubmit, onCancel, editingRule }) {
  return (
    <div className="form-card" data-testid="rule-form">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">
          {editingRule ? "Edit Rule" : "Buat Rule Baru"}
        </h3>
        <button className="icon-button" onClick={onCancel}>
          <X size={14} />
        </button>
      </div>
""",
     """export default function ApprovalRuleForm({ formData, setFormData, onSubmit, onCancel,
                                          editingRule, variant = "card" }) {
  // FASE P4 — `variant="modal"`: kartu & judul sendiri dilepas karena FormModal sudah
  // menyediakan kepala + tombol tutup (kalau tidak, muncul dua judul & dua tombol X).
  const isModal = variant === "modal";
  return (
    <div className={isModal ? "" : "form-card"} data-testid="rule-form">
      {!isModal && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">
            {editingRule ? "Ubah Aturan" : "Buat Aturan Baru"}
          </h3>
          <button className="icon-button" onClick={onCancel}>
            <X size={14} />
          </button>
        </div>
      )}
"""),
])

# ── F. ApprovalRulesSettings — bungkus dengan FormModal ─────────────────────────
sunting("features/settings/ApprovalRulesSettings.jsx", [
    ("""      {/* Create/Edit Form */}
      {showCreateForm && (
        <ApprovalRuleForm
          formData={formData}
          setFormData={setFormData}
          onSubmit={handleSubmit}
          onCancel={resetForm}
          editingRule={editingRule}
        />
      )}""",
     """      {/* FASE P4 — aturan persetujuan dibuat/diubah lewat POP-UP (dulu formnya
          menyelip di atas daftar aturan sehingga daftarnya terdorong ke bawah). */}
      <FormModal
        open={showCreateForm}
        onClose={resetForm}
        title={editingRule ? "Ubah Aturan Persetujuan" : "Aturan Persetujuan Baru"}
        subtitle="Ambang nilai dokumen & peran yang berwenang memutuskan"
        icon={Settings}
        size="lg"
        testId="rule-form-modal"
      >
        <ApprovalRuleForm
          variant="modal"
          formData={formData}
          setFormData={setFormData}
          onSubmit={handleSubmit}
          onCancel={resetForm}
          editingRule={editingRule}
        />
      </FormModal>"""),
], tambah_import=('import ApprovalRuleForm from "./ApprovalRuleForm";',
                  'import FormModal from "../../components/FormModal";'))

if __name__ == "__main__":
    for r in laporan:
        print(r)
    sys.exit(0 if all(r.startswith("OK") for r in laporan) else 1)
