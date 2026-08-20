// Shared sub-components + AssignModal untuk ProductTemplatesView (dipisah agar file
// utama di bawah batas guardrail). Modal/Field/Kpi dipakai TemplateModal & GenerateModal.
import { useEffect, useState } from "react";
import { X, Link2 } from "lucide-react";
import axios, { API } from "../../services/apiClient";

export function Modal({ title, icon: Icon, onClose, children, testId, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid={testId}>
      <div className={`bg-white rounded-xl shadow-xl w-full ${wide ? "max-w-2xl" : "max-w-lg"} max-h-[90vh] overflow-auto`}>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[#EFF0F2] sticky top-0 bg-white">
          <Icon size={16} className="text-[#6B219A]" /><h3 className="font-bold text-[14px]">{title}</h3>
          <button className="icon-button ml-auto" onClick={onClose} aria-label="Tutup" data-testid={`${testId}-close`}><X size={15} /></button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children }) {
  return (<div><label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">{label}</label>{children}</div>);
}

export function Kpi({ label, value, icon: Icon, tone = "", testId }) {
  return (
    <div className="section-card" data-testid={testId}>
      <div className="section-body flex items-center gap-3 py-3">
        <div className="w-9 h-9 rounded-lg bg-[#F3EAFB] flex items-center justify-center"><Icon size={17} className="text-[#6B219A]" /></div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`text-[17px] font-bold tabular-nums truncate ${tone || "text-[#1C1C1E]"}`} data-testid={`${testId}-value`}>{value}</p>
        </div>
      </div>
    </div>
  );
}

// ─── Assign Produk Modal ─────────────────────────────────────────────────────
export function AssignModal({ template, onClose, onDone, onError }) {
  const [products, setProducts] = useState([]);
  const [picked, setPicked] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/products`);
        setProducts((res.data || []).filter((p) => !p.template_id));
      } catch (e) {
        onError("Gagal memuat produk.");
      } finally { setLoading(false); }
    })();
  }, [onError]);

  const toggle = (id) => setPicked((prev) => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });

  const save = async () => {
    if (!picked.size) { onError("Pilih minimal satu produk."); return; }
    setSaving(true);
    try {
      const res = await axios.post(`${API}/product-templates/${template.id}/assign`, { product_ids: [...picked] });
      onDone(res.data.assigned);
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal menautkan produk.");
      setSaving(false);
    }
  };

  return (
    <Modal title={`Assign Produk → ${template.name}`} icon={Link2} onClose={onClose} testId="tpl-assign-modal">
      <div className="text-[12px]">
        {loading ? (
          <div className="grid gap-2">{[0, 1, 2].map((i) => <div key={i} className="h-9 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
        ) : products.length === 0 ? (
          <p data-testid="assign-empty" className="py-6 text-center text-[#8E8E93]">Semua produk sudah tertaut ke template.</p>
        ) : (
          <div className="max-h-[320px] overflow-auto rounded-md border border-[#EFF0F2] divide-y divide-[#F5F5F7]">
            {products.map((p) => (
              <label key={p.id} data-testid={`assign-prod-${p.id}`} className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-[#FBF8FE]">
                <input type="checkbox" checked={picked.has(p.id)} onChange={() => toggle(p.id)} className="accent-[#6B219A]" />
                <span className="font-mono text-[11px] text-[#6B6B73] w-28 shrink-0">{p.sku}</span>
                <span className="text-[#1C1C1E] truncate">{p.name}</span>
              </label>
            ))}
          </div>
        )}
      </div>
      <div className="flex justify-end gap-2 pt-4 mt-2 border-t border-[#EFF0F2]">
        <button className="btn-secondary text-[12px] py-1.5 px-4" onClick={onClose}>Batal</button>
        <button data-testid="assign-save" className="btn-primary text-[12px] py-1.5 px-4" onClick={save} disabled={saving || !picked.size}>{saving ? "Menyimpan…" : `Tautkan (${picked.size})`}</button>
      </div>
    </Modal>
  );
}
