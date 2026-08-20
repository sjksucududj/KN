// PublicVerify — halaman verifikasi dokumen PUBLIK (tanpa login).
// Route: /verify-document/:code (di-handle App.js sebelum gate login).
import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { ShieldCheck, ShieldX, Loader2, FileText, Building2, CalendarClock, Fingerprint } from "lucide-react";

export default function PublicVerify({ code }) {
  const [state, setState] = useState({ loading: true, data: null, error: "" });

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/esign/verify/${encodeURIComponent(code)}`);
        setState({ loading: false, data: r.data, error: "" });
      } catch (e) {
        setState({ loading: false, data: null, error: "Tidak dapat memuat status verifikasi." });
      }
    })();
  }, [code]);

  const { loading, data, error } = state;
  const valid = data?.valid;

  return (
    <div className="min-h-screen w-full bg-gradient-to-b from-[#EEF3FB] to-[#F7F8FA] px-4 py-10">
      <div className="mx-auto w-full max-w-[560px]">
        <div className="mb-5 flex items-center justify-center gap-2 text-[#0058CC]">
          <FileText size={20} />
          <span className="text-[15px] font-extrabold tracking-tight">Kain Nusantara · Verifikasi Dokumen</span>
        </div>

        <div className="overflow-hidden rounded-2xl bg-white shadow-xl">
          {loading ? (
            <div className="flex flex-col items-center gap-2 py-16 text-[#6B6B73]">
              <Loader2 size={26} className="animate-spin text-[#0058CC]" /><span className="text-[13px]">Memuat…</span>
            </div>
          ) : valid ? (
            <>
              <div className="flex flex-col items-center gap-2 bg-[#ECFAF1] px-6 py-7 text-center">
                <ShieldCheck size={48} className="text-[#1F7A45]" />
                <h1 className="text-[19px] font-extrabold text-[#146c38]">Dokumen Terverifikasi</h1>
                <p className="text-[12.5px] text-[#3f8a5e]">Tanda tangan elektronik sah & tercatat di sistem.</p>
              </div>
              <div className="grid gap-3 px-6 py-5">
                <Field icon={FileText} label="Dokumen" value={`${data.doc_label}${data.number ? " · " + data.number : ""}`} testId="pv-doc" />
                <Field icon={Building2} label="Entitas" value={data.entity_name || "-"} />
                <Field icon={CalendarClock} label="Ditandatangani" value={String(data.signed_at || "").slice(0, 19).replace("T", " ")} />
                <div className="grid gap-1">
                  <span className="text-[10.5px] font-bold uppercase tracking-wide text-[#9A9BA3]">Penandatangan</span>
                  <div className="grid gap-1">
                    {(data.signers || []).map((s, i) => (
                      <div key={i} className="flex items-center justify-between rounded-lg border border-[#EDEEF1] px-3 py-1.5" data-testid={`pv-signer-${i}`}>
                        <span className="text-[12.5px] font-semibold">{s.name}{s.role ? ` · ${s.role}` : ""}</span>
                        <span className="text-[11px] text-[#9A9BA3]">{String(s.signed_at || "").slice(0, 10)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex items-start gap-2 rounded-lg bg-[#F7F8FA] px-3 py-2">
                  <Fingerprint size={14} className="mt-0.5 shrink-0 text-[#9A9BA3]" />
                  <div className="min-w-0">
                    <span className="text-[10.5px] font-bold uppercase tracking-wide text-[#9A9BA3]">Hash Dokumen (SHA-256)</span>
                    <p className="break-all font-mono text-[10.5px] text-[#6B6B73]">{data.doc_hash}</p>
                  </div>
                </div>
                <div className="text-center text-[11px] text-[#9A9BA3]">Kode verifikasi: <b className="font-mono text-[#0058CC]">{data.code}</b></div>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
              <ShieldX size={48} className="text-[#C0392B]" />
              <h1 className="text-[18px] font-extrabold text-[#a3271b]">Kode Tidak Valid</h1>
              <p className="text-[12.5px] text-[#6B6B73]">{error || `Tidak ada dokumen dengan kode “${code}”.`}</p>
            </div>
          )}
        </div>
        <p className="mt-4 text-center text-[11px] text-[#9A9BA3]">Halaman ini dapat diakses publik untuk memverifikasi keaslian dokumen.</p>
      </div>
    </div>
  );
}

function Field({ icon: Icon, label, value, testId }) {
  return (
    <div className="flex items-center gap-2" data-testid={testId}>
      <Icon size={14} className="shrink-0 text-[#9A9BA3]" />
      <span className="text-[11px] font-bold uppercase tracking-wide text-[#9A9BA3] w-[110px] shrink-0">{label}</span>
      <span className="text-[12.5px] font-semibold text-[#1a1a1a]">{value}</span>
    </div>
  );
}
