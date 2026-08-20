import { useEffect, useMemo, useRef, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { BadgePercent, RefreshCw, Search, Plus } from "lucide-react";
import { PriceApprovalForm } from "./priceApprovals/PriceApprovalForm";
import { PriceApprovalCard } from "./priceApprovals/PriceApprovalCard";
import ErrorNotice from "../../components/ErrorNotice";
import FormModal from "../../components/FormModal";

const FILTERS = [
  { id: "all", label: "Semua" },
  { id: "pending", label: "Menunggu" },
  { id: "approved", label: "Disetujui" },
  { id: "rejected", label: "Ditolak" },
  { id: "draft", label: "Draf" },
  // F1b — pengajuan dari Daftar Harga per Pelanggan bisa berakhir digantikan aturan
  // baru atau dibatalkan pengajunya; keduanya harus bisa dilihat, bukan hilang.
  { id: "superseded", label: "Digantikan" },
  { id: "revoked", label: "Diakhiri" },
  { id: "cancelled", label: "Dibatalkan" },
];

const EMPTY_FORM = {
  customer_id: "",
  product_id: "",
  requested_price: "",
  min_quantity: "",
  valid_until: "",
  reason: "",
};

/**
 * Approval Harga Khusus (Sub-fase 1.7 — Special Price / Approval Harga).
 * Sales mengajukan harga nego per customer+product → upload bukti → manager/admin
 * approve/reject. Harga disetujui dipakai otomatis di POS (override harga normal).
 * Koleksi: price_approvals (pra_). Respons BE = bare object/array.
 * Sub-komponen di ./priceApprovals/ (Form + Card) agar file < 500 baris (compliance).
 */
export default function PriceApprovals({ currentUser = {} }) {
  const role = (currentUser.role || "").toLowerCase();
  const canApprove = ["manager", "admin"].includes(role);

  const [rows, setRows] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState("");

  // form (create / edit)
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [formErr, setFormErr] = useState("");

  // decision (approve/reject)
  const [decideFor, setDecideFor] = useState(""); // `${id}:${mode}`
  const [decisionNotes, setDecisionNotes] = useState("");

  const fileInputs = useRef({});

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [pa, cu, pr] = await Promise.all([
        axios.get(`${API}/price-approvals`),
        axios.get(`${API}/customers`),
        axios.get(`${API}/products`),
      ]);
      setRows(Array.isArray(pa.data) ? pa.data : []);
      setCustomers(Array.isArray(cu.data) ? cu.data : []);
      setProducts(Array.isArray(pr.data) ? pr.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data approval harga.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const resetForm = () => { setForm(EMPTY_FORM); setEditId(""); setShowForm(false); setFormErr(""); };

  const openCreate = () => { setForm(EMPTY_FORM); setEditId(""); setFormErr(""); setShowForm(true); };

  const openEdit = (r) => {
    setEditId(r.id);
    setForm({
      customer_id: r.customer_id, product_id: r.product_id,
      requested_price: String(r.requested_price ?? ""),
      min_quantity: String(r.min_quantity ?? ""),
      valid_until: (r.valid_until || "").slice(0, 10),
      reason: r.reason || "",
    });
    setFormErr("");
    setShowForm(true);
  };

  const submitForm = async (submitNow) => {
    setFormErr("");
    const price = parseFloat(form.requested_price);
    if (!form.customer_id || !form.product_id) { setFormErr("Pilih customer dan produk."); return; }
    if (!price || price <= 0) { setFormErr("Harga khusus harus lebih dari 0."); return; }
    setBusyId("form");
    try {
      if (editId) {
        await axios.patch(`${API}/price-approvals/${editId}`, {
          data: {
            requested_price: price,
            min_quantity: parseFloat(form.min_quantity) || 0,
            valid_until: form.valid_until || "",
            reason: form.reason || "",
          },
        });
      } else {
        await axios.post(`${API}/price-approvals`, {
          customer_id: form.customer_id,
          product_id: form.product_id,
          requested_price: price,
          min_quantity: parseFloat(form.min_quantity) || 0,
          valid_until: form.valid_until || "",
          reason: form.reason || "",
          submit_now: !!submitNow,
        });
      }
      resetForm();
      await load();
    } catch (e) {
      setFormErr(e.response?.data?.detail || "Gagal menyimpan pengajuan.");
    } finally {
      setBusyId("");
    }
  };

  const runAction = async (id, fn) => {
    setBusyId(id);
    setError("");
    try {
      await fn();
      setDecideFor(""); setDecisionNotes("");
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Aksi gagal diproses.");
    } finally {
      setBusyId("");
    }
  };

  const submitApproval = (id) => runAction(id, () => axios.post(`${API}/price-approvals/${id}/submit`, {}));
  const approveApproval = (id, notes) => runAction(id, () => axios.post(`${API}/price-approvals/${id}/approve`, { decision_notes: notes }));
  const rejectApproval = (id, notes) => runAction(id, () => axios.post(`${API}/price-approvals/${id}/reject`, { decision_notes: notes }));
  // F1b — akhiri aturan STANDING yang sudah disetujui (promo selesai / kesepakatan batal).
  // Dulu tidak ada jalan menghentikannya: hapus ditolak (409) dan ubah hanya untuk draf.
  const revokeApproval = (id, notes) => runAction(id, () => axios.post(`${API}/price-approvals/${id}/revoke`, { decision_notes: notes }));

  const removeApproval = async (id) => {
    setBusyId(id);
    try {
      await axios.delete(`${API}/price-approvals/${id}`);
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menghapus pengajuan.");
    } finally {
      setBusyId("");
    }
  };

  const uploadFile = async (id, file) => {
    if (!file) return;
    setBusyId(id);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      await axios.post(`${API}/price-approvals/${id}/attachments`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal mengunggah bukti.");
    } finally {
      setBusyId("");
    }
  };

  const viewAttachment = async (id, att) => {
    try {
      const res = await axios.get(`${API}/price-approvals/${id}/attachments/${att.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      setError("Gagal membuka lampiran.");
    }
  };

  const deleteAttachment = async (id, attId) => {
    setBusyId(id);
    try {
      await axios.delete(`${API}/price-approvals/${id}/attachments/${attId}`);
      await load();
    } catch (e) {
      setError("Gagal menghapus lampiran.");
    } finally {
      setBusyId("");
    }
  };

  const filtered = useMemo(() => rows.filter((r) => {
    if (filter !== "all" && r.status !== filter) return false;
    const hay = `${r.customer_name} ${r.product_name} ${r.sku}`.toLowerCase();
    return hay.includes(search.toLowerCase());
  }), [rows, filter, search]);

  const counts = useMemo(() => ({
    pending: rows.filter((r) => r.status === "pending").length,
  }), [rows]);

  return (
    <div data-testid="price-approvals-view" className="grid gap-4">
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <BadgePercent size={15} className="text-[#6B219A]" />
            <span className="kicker">Sales</span>
            <h2 data-testid="price-approvals-title">Persetujuan Harga Khusus</h2>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 rounded-md border border-[#E5E5EA] bg-white px-2 py-1.5 min-w-[180px]">
              <Search size={14} className="text-[#6B6B73]" />
              <input
                data-testid="price-approvals-search"
                className="w-full bg-transparent text-[13px] outline-none"
                placeholder="Cari pelanggan / produk…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button
              data-testid="price-approvals-new"
              className="flex items-center gap-1.5 rounded-md bg-[#6B219A] px-3 py-1.5 text-[12px] font-bold text-white transition hover:bg-[#581580]"
              onClick={openCreate}
            >
              <Plus size={14} /> Ajukan
            </button>
            <button data-testid="price-approvals-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 px-4 py-2">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              data-testid={`price-approvals-filter-${f.id}`}
              onClick={() => setFilter(f.id)}
              className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
                filter === f.id ? "bg-[#1C1C1E] text-white" : "bg-[#F2F2F7] text-[#3C3C43] hover:bg-[#E5E5EA]"
              }`}
            >
              {f.label}
              {f.id === "pending" && counts.pending > 0 && (
                <span className="ml-1 rounded-full bg-[#FF9500] px-1.5 text-[9px] text-white">{counts.pending}</span>
              )}
            </button>
          ))}
        </div>
      </section>

      {/* FASE P5 — form pengajuan harga khusus menjadi POP-UP: daftar pengajuan &
          ringkasan di belakang tetap terlihat sebagai pembanding. */}
      <FormModal
        open={showForm}
        onClose={resetForm}
        title={editId ? "Ubah Pengajuan Harga" : "Ajukan Harga Khusus"}
        subtitle="Harga di luar daftar harga standar — perlu persetujuan manajer"
        icon={BadgePercent}
        size="lg"
        testId="price-approval-modal"
      >
        <PriceApprovalForm
          variant="modal"
          editId={editId}
          form={form}
          setForm={setForm}
          formErr={formErr}
          busyId={busyId}
          customers={customers}
          products={products}
          onClose={resetForm}
          onSubmit={submitForm}
        />
      </FormModal>

      {error && (
        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="price-approvals-error" />
      )}

      <section className="grid gap-3">
        {loading && (
          <div data-testid="price-approvals-loading" className="section-card animate-pulse p-8 text-center text-[13px] text-[#6B6B73]">
            Memuat pengajuan…
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div data-testid="price-approvals-empty" className="section-card p-10 text-center text-[13px] text-[#6B6B73]">
            Belum ada pengajuan harga khusus.
          </div>
        )}
        {!loading && filtered.map((r) => (
          <PriceApprovalCard
            key={r.id}
            r={r}
            canApprove={canApprove}
            busyId={busyId}
            decideFor={decideFor}
            setDecideFor={setDecideFor}
            decisionNotes={decisionNotes}
            setDecisionNotes={setDecisionNotes}
            fileInputs={fileInputs}
            onUpload={uploadFile}
            onSubmit={submitApproval}
            onApprove={approveApproval}
            onReject={rejectApproval}
            onRevoke={revokeApproval}
            onEdit={openEdit}
            onRemove={removeApproval}
            onViewAttachment={viewAttachment}
            onDeleteAttachment={deleteAttachment}
          />
        ))}
      </section>
    </div>
  );
}
