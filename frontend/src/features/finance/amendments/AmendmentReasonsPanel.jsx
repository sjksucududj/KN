/**
 * AmendmentReasonsPanel — FASE G-1 · pengelolaan LABEL ALASAN koreksi (admin).
 *
 * Daftar alasan sengaja TIDAK di-hardcode: setiap perusahaan punya taksonomi
 * koreksinya sendiri. Admin bisa menambah, mengubah penjelasan, menandai alasan
 * yang menyangkut data master, atau menonaktifkan alasan yang tak dipakai lagi —
 * tanpa deploy. Alasan yang dinonaktifkan tidak hilang dari amandemen lama
 * (jejak audit tetap utuh), ia hanya tidak bisa dipilih lagi.
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, RefreshCw, Save, Tag } from "lucide-react";
import ErrorNotice from "../../../components/ErrorNotice";
import { errText, listReasons, upsertReason } from "./amendmentApi";
import KNSelect from "../../../components/KNSelect";

const BLANK = { code: "", label: "", help: "", affects_master: false, status: "active" };

export default function AmendmentReasonsPanel({ currentUser }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState("");
  const [draft, setDraft] = useState(BLANK);
  const [ok, setOk] = useState("");

  const isAdmin = currentUser?.role === "admin";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listReasons("", true));
      setError("");
    } catch (e) {
      setError(errText(e, "Gagal memuat label alasan."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function save(payload, key) {
    setSaving(key);
    setOk("");
    try {
      await upsertReason({
        code: payload.code,
        label: payload.label,
        help: payload.help || "",
        applies_to: payload.applies_to && payload.applies_to.length ? payload.applies_to : ["sales_order"],
        affects_master: !!payload.affects_master,
        status: payload.status || "active",
      });
      setOk(`Label “${payload.label}” tersimpan.`);
      setError("");
      await load();
      return true;
    } catch (e) {
      setError(errText(e, "Gagal menyimpan label alasan."));
      return false;
    } finally {
      setSaving("");
    }
  }

  async function addNew() {
    if (!draft.code.trim() || !draft.label.trim()) {
      setError("Kode dan nama label wajib diisi.");
      return;
    }
    const done = await save({ ...draft, code: draft.code.trim().toLowerCase().replace(/\s+/g, "_") }, "new");
    if (done) setDraft(BLANK);
  }

  return (
    <div className="section-card" data-testid="amd-reasons-panel">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <Tag size={15} className="text-[#0058CC]" />
          <div>
            <h3 className="text-[12.5px] font-bold">Label Alasan Koreksi</h3>
            <p className="text-[10.5px] text-[#6B6B73]">
              Taksonomi alasan yang boleh dipilih pengusul. Bisa diubah tanpa deploy.
            </p>
          </div>
        </div>
        <button className="secondary-button" data-testid="amd-reasons-refresh" onClick={load}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
        </button>
      </div>

      <div className="section-body space-y-2.5">
        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="amd-reasons-error" />
        {ok && (
          <p data-testid="amd-reasons-ok" className="rounded border border-[#CDEBD8] bg-[#EAF7EF] px-2.5 py-1.5 text-[11px] text-[#1B7A43]">
            {ok}
          </p>
        )}

        {loading ? (
          <p className="py-6 text-center text-[12px] text-[#6B6B73]">
            <Loader2 size={14} className="inline animate-spin" /> Memuat label…
          </p>
        ) : (
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[150px_1fr_110px_96px] gap-2 bg-[#FAFBFC] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Kode</span><span>Nama & penjelasan</span><span>Data master</span><span>Status</span>
            </div>
            {rows.map((r) => (
              <ReasonRow key={r.code} row={r} isAdmin={isAdmin} saving={saving === r.code}
                onSave={(payload) => save(payload, r.code)} />
            ))}
            {rows.length === 0 && (
              <p data-testid="amd-reasons-empty" className="px-2.5 py-6 text-center text-[11.5px] text-[#6B6B73]">
                Belum ada label alasan.
              </p>
            )}
          </div>
        )}

        {isAdmin && (
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5" data-testid="amd-reason-new">
            <p className="mb-2 text-[10px] font-bold uppercase text-[#6B6B73]">Tambah label alasan</p>
            <div className="grid gap-2 md:grid-cols-[150px_1fr_auto]">
              <input data-testid="amd-reason-new-code" className="field" placeholder="kode_alasan"
                value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} />
              <input data-testid="amd-reason-new-label" className="field" placeholder="Nama yang dilihat pengguna"
                value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} />
              <button data-testid="amd-reason-new-save" className="primary-button" onClick={addNew} disabled={saving === "new"}>
                <Plus size={13} /> {saving === "new" ? "Menyimpan…" : "Tambah"}
              </button>
            </div>
            <input data-testid="amd-reason-new-help" className="field mt-2" placeholder="Penjelasan singkat kapan alasan ini dipakai"
              value={draft.help} onChange={(e) => setDraft({ ...draft, help: e.target.value })} />
            <label className="mt-2 flex items-center gap-1.5 text-[11px] text-[#3C3C43]">
              <input data-testid="amd-reason-new-master" type="checkbox" checked={draft.affects_master}
                onChange={(e) => setDraft({ ...draft, affects_master: e.target.checked })} />
              Koreksi dengan alasan ini menyangkut data master
            </label>
          </div>
        )}

        {!isAdmin && (
          <p data-testid="amd-reasons-readonly" className="text-[10.5px] text-[#6B6B73]">
            Hanya admin yang dapat mengubah daftar label alasan.
          </p>
        )}
      </div>
    </div>
  );
}

function ReasonRow({ row, isAdmin, saving, onSave }) {
  const [label, setLabel] = useState(row.label || "");
  const [help, setHelp] = useState(row.help || "");
  const [master, setMaster] = useState(!!row.affects_master);
  const [status, setStatus] = useState(row.status || "active");

  const dirty = label !== (row.label || "") || help !== (row.help || "")
    || master !== !!row.affects_master || status !== (row.status || "active");

  return (
    <div data-testid={`amd-reason-row-${row.code}`}
      className="grid grid-cols-[150px_1fr_110px_96px] items-start gap-2 px-2.5 py-2 border-b border-[#EFF0F2] last:border-0">
      <span className="text-[10.5px] font-mono text-[#6B6B73] break-all">{row.code}</span>
      <div className="space-y-1">
        <input data-testid={`amd-reason-label-${row.code}`} className="field !py-1 text-[11.5px]" value={label}
          disabled={!isAdmin} onChange={(e) => setLabel(e.target.value)} />
        <input data-testid={`amd-reason-help-${row.code}`} className="field !py-1 text-[10.5px]" value={help}
          disabled={!isAdmin} onChange={(e) => setHelp(e.target.value)} placeholder="Penjelasan singkat" />
        {isAdmin && dirty && (
          <button data-testid={`amd-reason-save-${row.code}`} className="primary-button !py-1 !px-2 !text-[10.5px]"
            disabled={saving}
            onClick={() => onSave({ code: row.code, label, help, affects_master: master, status, applies_to: row.applies_to })}>
            <Save size={11} /> {saving ? "Menyimpan…" : "Simpan"}
          </button>
        )}
      </div>
      <label className="flex items-center gap-1.5 text-[10.5px] text-[#3C3C43]">
        <input data-testid={`amd-reason-master-${row.code}`} type="checkbox" checked={master} disabled={!isAdmin}
          onChange={(e) => setMaster(e.target.checked)} />
        Master
      </label>
      <KNSelect data-testid={`amd-reason-status-${row.code}`} className="field !py-1 !text-[10.5px]"
        value={status} disabled={!isAdmin} onValueChange={setStatus}
        aria-label={`Status alasan ${row.code}`}
        options={[{ value: "active", label: "Aktif" }, { value: "inactive", label: "Nonaktif" }]} />
    </div>
  );
}
