#!/usr/bin/env python3
"""Transformer FASE P4 — ubah form "Buat" INLINE menjadi <FormModal> (pop-up).

Dipakai sekali untuk 4 layar berpola sama (kepala `section-head` + badan `section-body` +
kaki tombol). Logika form TIDAK diubah: hanya wadahnya yang berpindah ke pop-up.
Skrip ini sengaja disimpan di `.logs/` (bukan `scripts/`) karena sifatnya sekali-jalan;
penjaga tetapnya adalah `scripts/audit_create_modal.py` (INV-UI-05).
"""
import re
import sys
from pathlib import Path

ROOT = Path("/app/frontend/src/features")

KONFIG = [
    {
        "file": "hr/OrgUnitsView.jsx",
        "open": '      {showForm && canManage && (',
        "body_open": '<div className="section-body grid grid-cols-2 gap-3">\n',
        "footer_open": '            <div className="col-span-2 flex gap-2">',
        "import_after": 'import EntityBadge from "../../components/EntityBadge";',
        "modal_open": '''      {/* FASE P4 — form unit organisasi menjadi POP-UP (dulu menyelip di atas pohon
          struktur sehingga hierarkinya terdorong ke bawah). Logika form tidak diubah. */}
      <FormModal
        open={showForm && canManage}
        onClose={() => { setShowForm(false); setEditId(null); }}
        title={editId ? "Ubah Unit Organisasi" : form.unit_type === "department" ? "Tambah Departemen" : "Tambah Jabatan"}
        subtitle="Perusahaan (Entitas) › Departemen › Jabatan"
        icon={Network}
        size="md"
        testId="org-form"
        onSubmit={submit}
        submitLabel={editId ? "Simpan Perubahan" : "Simpan"}
        submitTestId="submit-org-button"
        cancelTestId="cancel-org-button"
        error={error}
      >
        <div className="grid grid-cols-2 gap-3">
''',
        "modal_close": '''        </div>
      </FormModal>
''',
    },
    {
        "file": "sales/ReturnPoliciesView.jsx",
        "open": '      {showForm && canManage && (',
        "body_open": '<div className="section-body space-y-3">\n',
        "footer_open": '            <div className="flex gap-2">',
        "import_after": 'import ErrorNotice from "../../components/ErrorNotice";',
        "modal_open": '''      {/* FASE P4 — form kebijakan retur menjadi POP-UP (dulu form panjang ini menyelip
          di atas daftar kebijakan). Logika form tidak diubah. */}
      <FormModal
        open={showForm && canManage}
        onClose={() => { setShowForm(false); setEditId(null); }}
        title={editId ? "Ubah Kebijakan Retur" : "Kebijakan Retur Baru"}
        subtitle="Jendela retur, biaya restocking, jenis & outcome yang diizinkan"
        icon={ShieldCheck}
        size="lg"
        testId="policy-form"
        onSubmit={submit}
        submitLabel={editId ? "Simpan Perubahan" : "Buat Kebijakan"}
        submitTestId="submit-policy-button"
        cancelTestId="cancel-policy-button"
        error={error}
      >
        <div className="space-y-3">
''',
        "modal_close": '''        </div>
      </FormModal>
''',
    },
    {
        "file": "purchasing/CashManagementView.jsx",
        "open": '      {showForm && canManage && (',
        "body_open": '<div className="section-body space-y-3">\n',
        "footer_open": '            <div className="flex gap-2">',
        "import_after": 'import ErrorNotice from "../../components/ErrorNotice";',
        "modal_open": '''      {/* FASE P4 — pencatatan kas menjadi POP-UP (dulu menyelip di antara ringkasan
          saldo dan daftar transaksi). Logika form tidak diubah. */}
      <FormModal
        open={showForm && canManage}
        onClose={() => setShowForm(false)}
        title="Catat Transaksi Kas"
        subtitle="Kas kecil (tunai) atau kas besar/bank — masuk & keluar"
        icon={Wallet}
        size="md"
        testId="cash-form"
        onSubmit={handleSubmit}
        submitLabel="Catat Transaksi"
        submitTestId="submit-cash-button"
        cancelTestId="cancel-cash-button"
        error={error}
      >
        <div className="space-y-3">
''',
        "modal_close": '''        </div>
      </FormModal>
''',
    },
    {
        "file": "purchasing/PurchaseReturns.jsx",
        "open": '      {showForm && (',
        "body_open": '<div className="section-body space-y-3">\n',
        "footer_open": '            <div className="flex gap-2">',
        "import_after": 'import ErrorNotice from "../../components/ErrorNotice";',
        "modal_open": '''      {/* FASE P4 — form retur beli menjadi POP-UP (dulu menyelip di atas daftar retur;
          pada layar 13" tabelnya terdorong keluar layar). Logika form tidak diubah. */}
      <FormModal
        open={showForm}
        onClose={() => setShowForm(false)}
        title="Buat Retur Beli"
        subtitle="Pilih PO & roll yang dikembalikan ke supplier"
        icon={RotateCcw}
        size="lg"
        testId="purchase-return-form"
        onSubmit={handleSubmit}
        submitLabel="Buat Retur"
        submitTestId="submit-return-button"
        error={error}
      >
        <div className="space-y-3">
''',
        "modal_close": '''        </div>
      </FormModal>
''',
    },
]

TUTUP_BLOK = re.compile(r"\n\s{6}\)\}\n")


def ubah(cfg) -> str:
    p = ROOT / cfg["file"]
    s = p.read_text(encoding="utf-8")
    i = s.find(cfg["open"])
    if i < 0:
        return f"LEWAT (jangkar buka tak ketemu): {cfg['file']}"
    bo = s.find(cfg["body_open"], i)
    if bo < 0:
        return f"LEWAT (jangkar badan tak ketemu): {cfg['file']}"
    body_start = bo + len(cfg["body_open"])
    fo = s.find(cfg["footer_open"], body_start)
    if fo < 0:
        return f"LEWAT (jangkar kaki tak ketemu): {cfg['file']}"
    m = TUTUP_BLOK.search(s, fo)
    if not m:
        return f"LEWAT (penutup blok tak ketemu): {cfg['file']}"
    badan = s[body_start:fo].rstrip("\n") + "\n"
    baru = cfg["modal_open"] + badan + cfg["modal_close"]
    s = s[:i] + baru + s[m.end():]
    if "import FormModal" not in s:
        s = s.replace(cfg["import_after"],
                      cfg["import_after"] + '\nimport FormModal from "'
                      + ("../../components/FormModal" if cfg["file"].count("/") == 1
                         else "../../../components/FormModal") + '";', 1)
    p.write_text(s, encoding="utf-8")
    return f"OK: {cfg['file']} ({len(badan.splitlines())} baris isian dipindah ke pop-up)"


if __name__ == "__main__":
    for c in KONFIG:
        print(ubah(c))
    sys.exit(0)
