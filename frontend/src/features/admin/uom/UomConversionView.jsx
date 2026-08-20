/**
 * UomConversionView (FASE B · D-06/D-07) — layar “Konversi Satuan”.
 *
 * Masalah yang dijawab (KN_18 §11 D-06/D-07): perusahaan memakai banyak satuan
 * (meter, yard, kg, roll, cone, bal, lbs…) dan tiap dokumen memakai satuan yang
 * berbeda. Tanpa registry + jejak, laporan pecah dan tagihan makloon sulit diaudit.
 *
 * Isi layar:
 *   1) Ringkasan aturan (kebijakan toleransi kini di Pusat Pengaturan — FASE G-0).
 *   2) Kalkulator konversi (memakai server → angka layar = angka tersimpan).
 *   3) Tabel aturan global + tambah/ubah/nonaktifkan (audit otomatis).
 *   4) Jejak konversi dokumen nyata (PO/PR/penerimaan) — bukti D-07.
 *
 * Nav: Produk & Harga → Konversi Satuan (admin & manager; ubah butuh izin uom:update).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Calculator, Plus, RefreshCw, Ruler, X } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import DecimalInput from "../../../components/DecimalInput";
import KNSelect from "../../../components/KNSelect";
import UomInputConvert from "../../../components/UomInputConvert";
import useUomConversions, { invalidateUomCache } from "../../../hooks/useUomConversions";
import { RuleTable, StatCards, UsageTable } from "./UomConversionParts";
import ConfigRedirectCard from "../../settings/config/ConfigRedirectCard";

const EMPTY_RULE = { from_unit: "", to_unit: "", kind: "fixed", factor: "", formula: "",
                     note: "", status: "active" };

export default function UomConversionView({ user, products = [] }) {
  const { units, dimensions, kinds, settings, unitOptions } = useUomConversions();
  const canEdit = user?.role === "admin" || (user?.permissions?.uom || []).includes("update");

  const [rules, setRules] = useState([]);
  const [usage, setUsage] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState({ dimension: "", kind: "", status: "" });
  const [modal, setModal] = useState(null);      // {mode:'create'|'edit', data}
  const [modalErr, setModalErr] = useState("");
  const [busyId, setBusyId] = useState("");
  // kalkulator
  const [calc, setCalc] = useState({ product_id: "", qty: "1", unit: "" });

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const [r, u] = await Promise.all([
        axios.get(`${API}/uom-conversions/rules`),
        axios.get(`${API}/uom-conversions/usage`, { params: { limit: 20 } }),
      ]);
      setRules(r.data?.rules || []);
      setUsage(u.data?.usage || []);
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal memuat aturan konversi.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const shown = useMemo(() => rules.filter((r) =>
    (!filter.dimension || r.dimension === filter.dimension)
    && (!filter.kind || r.kind === filter.kind)
    && (!filter.status || r.status === filter.status)), [rules, filter]);

  async function submitRule() {    setModalErr("");
    const d = modal?.data || {};
    try {
      const body = {
        from_unit: d.from_unit, to_unit: d.to_unit, kind: d.kind,
        factor: String(d.factor || "0"), formula: d.formula || "",
        note: d.note || "", status: d.status || "active",
      };
      if (modal.mode === "create") {
        await axios.post(`${API}/uom-conversions/rules`, body);
      } else {
        await axios.patch(`${API}/uom-conversions/rules/${d.id}`, body);
      }
      setModal(null);
      invalidateUomCache();
      await load();
    } catch (e) {
      setModalErr(e.response?.data?.detail || "Aturan gagal disimpan.");
    }
  }

  async function toggleRule(r) {
    setBusyId(r.id); setErr("");
    try {
      await axios.post(`${API}/uom-conversions/rules/${r.id}/status`, null,
        { params: { status: r.status === "active" ? "inactive" : "active" } });
      invalidateUomCache();
      await load();
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal mengubah status aturan.");
    } finally { setBusyId(""); }
  }

  const calcProduct = products.find((p) => p.id === calc.product_id);
  const productOptions = products.slice(0, 300).map((p) => ({
    value: p.id, label: `${p.sku} — ${p.name} (dasar: ${p.base_unit || "meter"})` }));

  return (
    <div data-testid="uom-conversion-view" className="space-y-3">
      <div className="section-card">
        <div className="section-head">
          <div className="min-w-0">
            <h2 className="flex items-center gap-1.5 text-[13px] font-bold">
              <Ruler size={14} className="text-[#0058CC]" /> Konversi Satuan (Global)
            </h2>
            <p className="text-[10.5px] text-[#6B6B73]">
              Satu registry untuk semua produk — dipakai PR, PO, penerimaan barang, dan
              perhitungan makloon. Setiap konversi menyimpan <b>jejak</b> (faktor + sumber)
              sesuai keputusan <b>D-07</b>.
            </p>
          </div>
          <button data-testid="uom-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
            <RefreshCw size={13} />
          </button>
        </div>
        <div className="section-body space-y-3">
          {err && (
            <div className="notice-bar danger" data-testid="uom-error">
              <span>{err}</span><button onClick={() => setErr("")}>×</button>
            </div>
          )}
          {loading && <p data-testid="uom-loading" className="text-[11px] text-[#6B6B73]">Memuat…</p>}
          {!loading && rules.length === 0 && (
            <p data-testid="uom-empty-state" className="notice-bar">
              <span>
                Belum ada aturan konversi. Jalankan <b>python backend/scripts/migrate_fase_b_uom.py</b>
                {" "}untuk memasang aturan standar (yard↔meter, lbs↔kg, GSM × lebar), atau tambah
                aturan sendiri lewat tombol “Tambah Aturan”.
              </span>
            </p>
          )}
          <StatCards rules={rules} settings={settings} />

          {/* FASE G-0 — form toleransi & kebijakan penerimaan DIHAPUS dari sini.
              Aturannya tetap sama, tetapi hanya boleh diubah dari satu tempat. */}
          <ConfigRedirectCard
            title="Toleransi konversi & kebijakan penerimaan"
            note="Di sana tersedia juga simulator untuk melihat kapan sebuah selisih hanya diperingatkan dan kapan diblokir."
            group="stok-satuan"
            testId="uom-config-redirect"
            settings={[
              { key: "uom.warn_pct", label: "Ambang peringatan selisih" },
              { key: "uom.block_pct", label: "Ambang blokir selisih" },
              { key: "uom.precision", label: "Pembulatan hasil konversi" },
              { key: "uom.allow_override", label: "Boleh menimpa hasil konversi" },
              { key: "receiving.supplier_uom_input_mode", label: "Input satuan supplier" },
              { key: "receiving.block_over_remaining", label: "Blokir terima melebihi sisa PO" },
            ]}
          />

          {/* Kalkulator konversi — memakai endpoint yang sama dengan dokumen */}
          <div data-testid="uom-calculator" className="rounded-md border border-[#EFF0F2] bg-white">
            <div className="flex items-center gap-1.5 border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
              <Calculator size={12} className="text-[#0058CC]" />
              <span className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
                Kalkulator Konversi (hasil dari server — sama dengan yang tersimpan)
              </span>
            </div>
            <div className="grid gap-2 px-2.5 py-2 md:grid-cols-[1fr_1fr]">
              <label className="grid gap-1">
                <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  Produk (opsional — untuk faktor per produk & GSM × lebar)
                </span>
                <KNSelect data-testid="uom-calc-product" className="field" searchable
                  value={calc.product_id} placeholder="Pilih produk"
                  options={productOptions}
                  onValueChange={(v) => {
                    const p = products.find((x) => x.id === v);
                    setCalc({ ...calc, product_id: v, unit: calc.unit || p?.base_unit || "meter" });
                  }} />
                <span className="text-[10px] text-[#8E8E93]">
                  {calc.product_id
                    ? `Satuan dasar produk: ${calcProduct?.base_unit || "meter"}`
                    : "Tanpa produk: hanya konversi antar satuan sedimensi (mis. yard → meter). "
                      + "Pilih produk untuk konversi panjang ↔ berat (GSM × lebar) atau faktor kemasan per produk."}
                </span>
              </label>
              <label className="grid gap-1">
                <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  Jumlah & satuan dokumen → satuan dasar produk
                </span>
                <UomInputConvert testId="uom-calc"
                  productId={calc.product_id}
                  baseUnit={calcProduct?.base_unit || "meter"}
                  qty={calc.qty} onQtyChange={(v) => setCalc({ ...calc, qty: v })}
                  unit={calc.unit} onUnitChange={(v) => setCalc({ ...calc, unit: v })} />
              </label>
            </div>
          </div>

          {/* Tabel aturan */}
          <div className="rounded-md border border-[#EFF0F2] bg-white">
            <div className="flex flex-wrap items-center gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
              <span className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
                Aturan Konversi
              </span>
              <div className="ml-auto flex flex-wrap items-center gap-1.5">
                <KNSelect data-testid="uom-filter-dimension" className="field !py-1 !text-[10.5px] w-[130px]"
                  value={filter.dimension} placeholder="Semua dimensi"
                  options={[{ value: "", label: "Semua dimensi" },
                            ...dimensions.map((d) => ({ value: d.value, label: d.label }))]}
                  onValueChange={(v) => setFilter({ ...filter, dimension: v })} />
                <KNSelect data-testid="uom-filter-kind" className="field !py-1 !text-[10.5px] w-[130px]"
                  value={filter.kind} placeholder="Semua jenis"
                  options={[{ value: "", label: "Semua jenis" },
                            ...kinds.map((k) => ({ value: k.value, label: k.label }))]}
                  onValueChange={(v) => setFilter({ ...filter, kind: v })} />
                <KNSelect data-testid="uom-filter-status" className="field !py-1 !text-[10.5px] w-[120px]"
                  value={filter.status} placeholder="Semua status"
                  options={[{ value: "", label: "Semua status" },
                            { value: "active", label: "Aktif" },
                            { value: "inactive", label: "Nonaktif" }]}
                  onValueChange={(v) => setFilter({ ...filter, status: v })} />
                {canEdit && (
                  <button data-testid="uom-rule-add" className="primary-button !px-2 !py-1 !text-[10.5px]"
                    onClick={() => { setModal({ mode: "create", data: { ...EMPTY_RULE } }); setModalErr(""); }}>
                    <span className="flex items-center gap-1"><Plus size={11} /> Tambah Aturan</span>
                  </button>
                )}
              </div>
            </div>
            <RuleTable rules={shown} canEdit={canEdit} busyId={busyId} loading={loading}
              onEdit={(r) => { setModal({ mode: "edit", data: { ...r, factor: String(r.factor ?? "") } }); setModalErr(""); }}
              onToggle={toggleRule} />
          </div>

          {/* Jejak konversi dokumen */}
          <div className="rounded-md border border-[#EFF0F2] bg-white">
            <div className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
              Jejak Konversi Dokumen Terakhir (bukti D-07)
            </div>
            <UsageTable usage={usage} loading={loading} />
          </div>
        </div>
      </div>

      {modal && (
        <div className="modal-overlay" data-testid="uom-rule-modal">
          <div className="modal-card">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="modal-title">
                  {modal.mode === "create" ? "Tambah Aturan Konversi" : "Ubah Aturan Konversi"}
                </p>
                <p className="modal-subtitle">
                  Aturan berlaku <b>global</b> untuk semua produk. Faktor per produk (mis. 1 roll
                  = 50 yard untuk produk tertentu) tetap diisi di master produk dan menang atas
                  aturan global.
                </p>
              </div>
              <button data-testid="uom-rule-modal-close" className="icon-button"
                onClick={() => setModal(null)} aria-label="Tutup"><X size={15} /></button>
            </div>
            {modalErr && (
              <div className="notice-bar danger" data-testid="uom-rule-modal-error">
                <span>{modalErr}</span><button onClick={() => setModalErr("")}>×</button>
              </div>
            )}
            <div className="mt-2 grid gap-2">
              <div className="grid grid-cols-2 gap-2">
                <label className="grid gap-1">
                  <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Satuan asal</span>
                  <KNSelect data-testid="uom-rule-from" className="field" searchable
                    value={modal.data.from_unit} placeholder="mis. yard"
                    options={unitOptions()}
                    onValueChange={(v) => setModal({ ...modal, data: { ...modal.data, from_unit: v } })} />
                </label>
                <label className="grid gap-1">
                  <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Satuan tujuan</span>
                  <KNSelect data-testid="uom-rule-to" className="field" searchable
                    value={modal.data.to_unit} placeholder="mis. meter"
                    options={unitOptions()}
                    onValueChange={(v) => setModal({ ...modal, data: { ...modal.data, to_unit: v } })} />
                </label>
              </div>
              <label className="grid gap-1">
                <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Jenis aturan</span>
                <KNSelect data-testid="uom-rule-kind" className="field" value={modal.data.kind}
                  options={kinds.map((k) => ({ value: k.value, label: k.label }))}
                  onValueChange={(v) => setModal({ ...modal, data: { ...modal.data, kind: v } })} />
                <span className="text-[10px] text-[#8E8E93]">
                  {(kinds.find((k) => k.value === modal.data.kind) || {}).note}
                </span>
              </label>
              {modal.data.kind === "formula" ? (
                <label className="grid gap-1">
                  <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Formula</span>
                  <KNSelect data-testid="uom-rule-formula" className="field"
                    value={modal.data.formula || "gsm_width"}
                    options={[{ value: "gsm_width", label: "GSM × lebar ÷ 1000 (kg per meter)" }]}
                    onValueChange={(v) => setModal({ ...modal, data: { ...modal.data, formula: v } })} />
                </label>
              ) : (
                <label className="grid gap-1">
                  <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
                    Faktor (1 {modal.data.from_unit || "asal"} = ? {modal.data.to_unit || "tujuan"})
                  </span>
                  <DecimalInput data-testid="uom-rule-factor" className="field" min={0}
                    placeholder="mis. 0,9144" value={modal.data.factor}
                    onChange={(v) => setModal({ ...modal, data: { ...modal.data, factor: v } })} />
                </label>
              )}
              <label className="grid gap-1">
                <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">Catatan</span>
                <input data-testid="uom-rule-note" className="field"
                  placeholder="mis. cone benang standar pabrik A"
                  value={modal.data.note || ""}
                  onChange={(e) => setModal({ ...modal, data: { ...modal.data, note: e.target.value } })} />
              </label>
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setModal(null)}>Batal</button>
              <button data-testid="uom-rule-submit" className="primary-button"
                disabled={!modal.data.from_unit || !modal.data.to_unit}
                onClick={submitRule}>Simpan Aturan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
