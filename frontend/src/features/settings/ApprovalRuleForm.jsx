// Form buat/edit Approval Rule (dipisah dari ApprovalRulesSettings agar file view
// di bawah batas guardrail). State dikelola parent lewat props.
import { CheckCircle2, X } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { ENTITY_TYPES, OPERATORS, ROLES } from "./approvalRulesConstants";

export default function ApprovalRuleForm({ formData, setFormData, onSubmit, onCancel,
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

      <form onSubmit={onSubmit}>
        <div className="form-row-2col">
          <div className="form-group">
            <label className="form-label">Nama Aturan <span className="req">*</span></label>
            <input
              data-testid="rule-name"
              className="form-input"
              value={formData.name}
              onChange={e => setFormData({ ...formData, name: e.target.value })}
              placeholder="Contoh: Pesanan Khusus Bernilai Besar"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Entity Type <span className="req">*</span></label>
            <KNSelect
              data-testid="rule-entity-type"
              className="form-select"
              value={formData.entity_type}
              onValueChange={v => setFormData({ ...formData, entity_type: v })}
              options={ENTITY_TYPES.map(t => ({ value: t.value, label: t.label }))}
            />
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Keterangan</label>
          <input
            data-testid="rule-description"
            className="form-input"
            value={formData.description}
            onChange={e => setFormData({ ...formData, description: e.target.value })}
            placeholder="Keterangan aturan…"
          />
        </div>

        <div className="form-row-3col">
          <div className="form-group">
            <label className="form-label">Kolom Ambang <span className="req">*</span></label>
            <input
              data-testid="rule-threshold-field"
              className="form-input"
              value={formData.threshold_field}
              onChange={e => setFormData({ ...formData, threshold_field: e.target.value })}
              placeholder="total_amount"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Operator <span className="req">*</span></label>
            <KNSelect
              data-testid="rule-operator"
              className="form-select"
              value={formData.threshold_operator}
              onValueChange={v => setFormData({ ...formData, threshold_operator: v })}
              options={OPERATORS.map(op => ({ value: op.value, label: `${op.label} (${op.value})` }))}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Nilai Ambang <span className="req">*</span></label>
            <input
              data-testid="rule-threshold-value"
              className="form-input"
              type="number"
              min="0"
              step="0.01"
              value={formData.threshold_value}
              onChange={e => setFormData({ ...formData, threshold_value: e.target.value })}
              placeholder="10000000"
              required
            />
          </div>
        </div>

        <div className="form-row-3col">
          <div className="form-group">
            <label className="form-label">Peran Penyetuju <span className="req">*</span></label>
            <KNSelect
              data-testid="rule-approver-role"
              className="form-select"
              value={formData.approver_role}
              onValueChange={v => setFormData({ ...formData, approver_role: v })}
              options={ROLES.map(r => ({ value: r.value, label: r.label }))}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Priority</label>
            <input
              data-testid="rule-priority"
              className="form-input"
              type="number"
              min="1"
              value={formData.priority}
              onChange={e => setFormData({ ...formData, priority: parseInt(e.target.value) })}
            />
            <p className="form-help text-xs">Lower = higher priority</p>
          </div>

          <div className="form-group">
            <label className="form-check-label mt-6">
              <input
                type="checkbox"
                data-testid="rule-is-active"
                checked={formData.is_active}
                onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
              />
              {" "}Aktif
            </label>
          </div>
        </div>

        <div className="form-actions">
          <button type="button" className="secondary-button" onClick={onCancel}>
            Batal
          </button>
          <button type="submit" data-testid="save-rule-btn" className="primary-button">
            <CheckCircle2 size={14} /> {editingRule ? "Update" : "Buat"} Aturan
          </button>
        </div>
      </form>
    </div>
  );
}
