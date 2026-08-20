/**
 * Approval Rules Settings
 * Configure approval rules untuk berbagai entity types
 */
import { useState, useEffect } from "react";
import axios, { API } from "../../services/apiClient";
import {
  AlertCircle, CheckCircle2, Edit2, Loader2, Plus, Settings, Trash2, X
} from "lucide-react";
import ApprovalRuleForm from "./ApprovalRuleForm";
import FormModal from "../../components/FormModal";
import { fmtNum, ENTITY_TYPES, OPERATORS, ROLES } from "./approvalRulesConstants";
import { askConfirm } from "@/services/confirmService";

export default function ApprovalRulesSettings({ currentUser }) {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingRule, setEditingRule] = useState(null);

  // Form state
  const [formData, setFormData] = useState({
    name: "",
    entity_type: "special_order",
    threshold_field: "total_amount",
    threshold_operator: "gt",
    threshold_value: "",
    approver_role: "manager",
    description: "",
    priority: 100,
    is_active: true,
  });

  const token = localStorage.getItem("kn_token");
  const isAdmin = currentUser?.role === "admin";

  useEffect(() => {
    loadRules();
  }, []);

  async function loadRules() {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/approval-rules`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setRules(res.data || []);
      setError(null);
    } catch (e) {
      setError("Gagal memuat rules: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  function resetForm() {
    setFormData({
      name: "",
      entity_type: "special_order",
      threshold_field: "total_amount",
      threshold_operator: "gt",
      threshold_value: "",
      approver_role: "manager",
      description: "",
      priority: 100,
      is_active: true,
    });
    setEditingRule(null);
    setShowCreateForm(false);
  }

  function handleEdit(rule) {
    setFormData({
      name: rule.name,
      entity_type: rule.entity_type,
      threshold_field: rule.threshold_field,
      threshold_operator: rule.threshold_operator,
      threshold_value: rule.threshold_value,
      approver_role: rule.approver_role,
      description: rule.description || "",
      priority: rule.priority,
      is_active: rule.is_active,
    });
    setEditingRule(rule);
    setShowCreateForm(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!formData.threshold_value || parseFloat(formData.threshold_value) < 0) {
      return setError("Threshold value harus >= 0");
    }

    try {
      if (editingRule) {
        // Update
        await axios.patch(
          `${API}/approval-rules/${editingRule.id}`,
          { ...formData, threshold_value: parseFloat(formData.threshold_value) },
          { headers: { Authorization: `Bearer ${token}` } }
        );
        setNotice(`Rule "${formData.name}" berhasil diupdate!`);
      } else {
        // Create
        await axios.post(
          `${API}/approval-rules`,
          { ...formData, threshold_value: parseFloat(formData.threshold_value) },
          { headers: { Authorization: `Bearer ${token}` } }
        );
        setNotice(`Rule "${formData.name}" berhasil dibuat!`);
      }
      resetForm();
      loadRules();
    } catch (e) {
      setError("Gagal menyimpan: " + (e.response?.data?.detail || e.message));
    }
  }

  async function handleDelete(rule) {
    const ok = await askConfirm({
      title: `Hapus aturan persetujuan "${rule.name}"?`,
      message: "Dokumen yang memenuhi syarat aturan ini tidak lagi otomatis meminta persetujuan.",
      confirmLabel: "Hapus Aturan",
      danger: true,
      testId: "approval-rule-delete-confirm",
    });
    if (!ok) return;
    try {
      await axios.delete(`${API}/approval-rules/${rule.id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setNotice(`Rule "${rule.name}" berhasil dihapus!`);
      loadRules();
    } catch (e) {
      setError("Gagal menghapus: " + (e.response?.data?.detail || e.message));
    }
  }

  async function toggleActive(rule) {
    try {
      await axios.patch(
        `${API}/approval-rules/${rule.id}`,
        { is_active: !rule.is_active },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      loadRules();
    } catch (e) {
      setError("Gagal toggle status: " + (e.response?.data?.detail || e.message));
    }
  }

  if (!isAdmin) {
    return (
      <div className="view-container">
        <div className="notice-bar danger">
          <AlertCircle size={14} /> Hanya admin yang dapat mengelola aturan persetujuan.
        </div>
      </div>
    );
  }

  return (
    <div data-testid="approval-rules-settings" className="view-container">
      {/* Notice */}
      {notice && (
        <div className="notice-bar success">
          <CheckCircle2 size={14} /> {notice}
          <button onClick={() => setNotice(null)}><X size={12} /></button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="notice-bar danger">
          <AlertCircle size={14} /> {error}
          <button onClick={() => setError(null)}><X size={12} /></button>
        </div>
      )}

      {/* Header */}
      <div className="view-header">
        <div>
          <h1 className="view-title">
            <Settings size={20} /> Aturan Persetujuan
          </h1>
          <p className="view-subtitle">
            Konfigurasi aturan persetujuan untuk berbagai jenis dokumen
          </p>
        </div>
        {!showCreateForm && (
          <button
            data-testid="create-rule-btn"
            className="primary-button"
            onClick={() => setShowCreateForm(true)}
          >
            <Plus size={14} /> Buat Aturan Baru
          </button>
        )}
      </div>

      {/* FASE P4 — aturan persetujuan dibuat/diubah lewat POP-UP (dulu formnya
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
      </FormModal>

      {/* Rules List */}
      {loading ? (
        <div className="loading-state">
          <Loader2 size={24} className="spin" />
          <p>Memuat aturan persetujuan…</p>
        </div>
      ) : rules.length === 0 ? (
        <div className="empty-state">
          <Settings size={32} style={{ opacity: 0.3 }} />
          <p>Belum ada aturan persetujuan.</p>
          {!showCreateForm && (
            <button className="primary-button" onClick={() => setShowCreateForm(true)}>
              <Plus size={14} /> Buat Aturan Pertama
            </button>
          )}
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Nama Aturan</th>
                <th>Entity Type</th>
                <th>Condition</th>
                <th>Approver</th>
                <th>Priority</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rules.map(rule => (
                <tr key={rule.id} data-testid={`rule-row-${rule.id}`}>
                  <td>
                    <div className="font-medium">{rule.name}</div>
                    {rule.description && (
                      <div className="text-xs text-muted">{rule.description}</div>
                    )}
                  </td>
                  <td>
                    <span className="feature-badge badge-blue">
                      {ENTITY_TYPES.find(t => t.value === rule.entity_type)?.label || rule.entity_type}
                    </span>
                  </td>
                  <td className="font-mono text-sm">
                    {rule.threshold_field} {OPERATORS.find(o => o.value === rule.threshold_operator)?.label} <span className="tabular-nums">{fmtNum(rule.threshold_value)}</span>
                  </td>
                  <td>
                    <span className="feature-badge badge-purple">
                      {ROLES.find(r => r.value === rule.approver_role)?.label || rule.approver_role}
                    </span>
                  </td>
                  <td className="text-center">{rule.priority}</td>
                  <td>
                    <button
                      data-testid={`toggle-rule-${rule.id}`}
                      className={`status-pill ${rule.is_active ? "pill-success" : "pill-muted"}`}
                      onClick={() => toggleActive(rule)}
                    >
                      {rule.is_active ? "Active" : "Inactive"}
                    </button>
                  </td>
                  <td>
                    <div className="flex gap-2">
                      <button
                        data-testid={`edit-rule-${rule.id}`}
                        className="icon-button"
                        onClick={() => handleEdit(rule)}
                      >
                        <Edit2 size={14} />
                      </button>
                      <button
                        data-testid={`delete-rule-${rule.id}`}
                        className="icon-button danger"
                        onClick={() => handleDelete(rule)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
