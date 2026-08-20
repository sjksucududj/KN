// ESignModal — tanda tangan elektronik: gambar TTD (canvas) → kirim OTP (simulasi)
// → verifikasi → tersimpan + kode verifikasi publik + QR link.
import { useCallback, useEffect, useRef, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { X, PenLine, Eraser, ShieldCheck, Loader2, KeyRound, CheckCircle2, ExternalLink, Copy } from "lucide-react";

function SignaturePad({ onChange }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const last = useRef({ x: 0, y: 0 });

  const ctxOf = () => {
    const c = canvasRef.current;
    const ctx = c.getContext("2d");
    ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.lineWidth = 2.4; ctx.strokeStyle = "#0B1B3B";
    return ctx;
  };
  const pos = (e) => {
    const c = canvasRef.current;
    const rect = c.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return { x: (t.clientX - rect.left) * (c.width / rect.width), y: (t.clientY - rect.top) * (c.height / rect.height) };
  };
  const start = (e) => { e.preventDefault(); drawing.current = true; last.current = pos(e); };
  const move = (e) => {
    if (!drawing.current) return;
    e.preventDefault();
    const ctx = ctxOf(); const p = pos(e);
    ctx.beginPath(); ctx.moveTo(last.current.x, last.current.y); ctx.lineTo(p.x, p.y); ctx.stroke();
    last.current = p;
  };
  const end = () => {
    if (!drawing.current) return;
    drawing.current = false;
    onChange(canvasRef.current.toDataURL("image/png"));
  };
  const clear = () => {
    const c = canvasRef.current; c.getContext("2d").clearRect(0, 0, c.width, c.height); onChange("");
  };

  useEffect(() => {
    const c = canvasRef.current;
    c.addEventListener("touchstart", start, { passive: false });
    c.addEventListener("touchmove", move, { passive: false });
    c.addEventListener("touchend", end);
    return () => {
      c.removeEventListener("touchstart", start);
      c.removeEventListener("touchmove", move);
      c.removeEventListener("touchend", end);
    };
  }); // eslint-disable-line

  return (
    <div className="grid gap-1">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Bubuhkan Tanda Tangan</span>
        <button type="button" onClick={clear} className="flex items-center gap-1 text-[11px] text-[#6B6B73] hover:text-[#C0392B]" data-testid="esign-clear"><Eraser size={12} /> Bersihkan</button>
      </div>
      <canvas
        ref={canvasRef} width={460} height={170}
        onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
        className="w-full touch-none rounded-lg border border-dashed border-[#B9C0CC] bg-[#FBFCFE] cursor-crosshair"
        data-testid="esign-canvas"
      />
      <p className="text-[10.5px] text-[#9A9BA3]">Gambar tanda tangan menggunakan mouse / sentuhan.</p>
    </div>
  );
}

export default function ESignModal({ open, onClose, doc, currentUser, onSigned }) {
  const [step, setStep] = useState("form"); // form | otp | done
  const [signerName, setSignerName] = useState("");
  const [signerRole, setSignerRole] = useState("");
  const [signerContact, setSignerContact] = useState("");
  const [signature, setSignature] = useState("");
  const [otp, setOtp] = useState("");
  const [reqInfo, setReqInfo] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open) {
      setStep("form"); setSignerName(currentUser?.name || ""); setSignerRole("");
      setSignerContact(""); setSignature(""); setOtp(""); setReqInfo(null); setResult(null);
      setErr(""); setCopied(false);
    }
  }, [open, currentUser]);

  const sendOtp = useCallback(async () => {
    setErr("");
    if (!signerName.trim()) { setErr("Nama penandatangan wajib diisi."); return; }
    if (!signature) { setErr("Bubuhkan tanda tangan terlebih dahulu."); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/esign/request`, {
        doc_type: doc.doc_type, source_id: doc.source_id, entity_id: doc.entity_id,
        signer_name: signerName.trim(), signer_role: signerRole.trim(), signer_contact: signerContact.trim(),
      });
      setReqInfo(r.data);
      if (r.data.reveal_code) setOtp(r.data.reveal_code); // auto-isi di mode simulasi
      setStep("otp");
    } catch (e) { setErr(e.response?.data?.detail || "Gagal mengirim OTP."); }
    finally { setBusy(false); }
  }, [signerName, signerRole, signerContact, signature, doc]);

  const doVerify = useCallback(async () => {
    setErr("");
    if (!otp.trim()) { setErr("Masukkan kode OTP."); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/esign/verify`, {
        request_id: reqInfo.request_id, otp: otp.trim(), signature_b64: signature,
      });
      setResult(r.data); setStep("done");
      onSigned && onSigned();
    } catch (e) { setErr(e.response?.data?.detail || "Verifikasi gagal."); }
    finally { setBusy(false); }
  }, [otp, reqInfo, signature, onSigned]);

  const copyLink = () => {
    if (result?.verify_url) {
      navigator.clipboard?.writeText(result.verify_url);
      setCopied(true); setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4" data-testid="esign-modal">
      <div className="w-full max-w-[520px] overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#EDEEF1] px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#EAF2FF] text-[#0058CC]"><PenLine size={16} /></span>
            <div>
              <h3 className="text-[14px] font-bold leading-tight">Tanda Tangan Elektronik</h3>
              <p className="text-[11px] text-[#6B6B73]">{doc?.label} · {doc?.number || doc?.source_id}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-[#9A9BA3] hover:text-[#1a1a1a]" data-testid="esign-close"><X size={18} /></button>
        </div>

        <div className="px-5 py-4">
          {err && <div className="notice-bar danger mb-3 !py-1.5"><span className="text-[11.5px]">{err}</span></div>}

          {step === "form" && (
            <div className="grid gap-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="grid gap-1">
                  <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Nama Penandatangan</label>
                  <input className="form-input" value={signerName} onChange={(e) => setSignerName(e.target.value)} data-testid="esign-signer-name" />
                </div>
                <div className="grid gap-1">
                  <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Jabatan / Peran</label>
                  <input className="form-input" value={signerRole} onChange={(e) => setSignerRole(e.target.value)} placeholder="mis. Manager" data-testid="esign-signer-role" />
                </div>
              </div>
              <div className="grid gap-1">
                <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Kontak (opsional)</label>
                <input className="form-input" value={signerContact} onChange={(e) => setSignerContact(e.target.value)} placeholder="No. HP / email penandatangan" data-testid="esign-signer-contact" />
              </div>
              <SignaturePad onChange={setSignature} />
              <button className="btn-primary flex items-center justify-center gap-2" onClick={sendOtp} disabled={busy} data-testid="esign-send-otp">
                {busy ? <Loader2 size={15} className="animate-spin" /> : <KeyRound size={15} />} Kirim OTP
              </button>
            </div>
          )}

          {step === "otp" && (
            <div className="grid gap-3">
              <div className="rounded-lg bg-[#EFF4FF] px-3 py-2 text-[11.5px] text-[#0058CC]">
                {reqInfo?.message || "Kode OTP telah dikirim."}
                {reqInfo?.reveal_code && (
                  <span className="ml-1 font-semibold"> Kode simulasi: <b data-testid="esign-otp-hint">{reqInfo.reveal_code}</b></span>
                )}
              </div>
              <div className="grid gap-1">
                <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Kode OTP</label>
                <input className="form-input text-center text-[18px] font-mono tracking-[0.4em]" maxLength={6}
                  value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} data-testid="esign-otp-input" />
              </div>
              <div className="flex gap-2">
                <button className="btn-secondary flex-1" onClick={() => setStep("form")} disabled={busy}>Kembali</button>
                <button className="btn-primary flex-1 flex items-center justify-center gap-2" onClick={doVerify} disabled={busy} data-testid="esign-verify">
                  {busy ? <Loader2 size={15} className="animate-spin" /> : <ShieldCheck size={15} />} Verifikasi & Tandatangani
                </button>
              </div>
            </div>
          )}

          {step === "done" && result && (
            <div className="grid gap-3 text-center">
              <div className="flex flex-col items-center gap-1 pt-1">
                <CheckCircle2 size={44} className="text-[#1F7A45]" />
                <h4 className="text-[15px] font-bold">Dokumen Ditandatangani</h4>
                <p className="text-[12px] text-[#6B6B73]">Oleh {result.signer_name} · {String(result.signed_at).slice(0, 19).replace("T", " ")}</p>
              </div>
              <div className="rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] px-3 py-2 text-left">
                <p className="text-[10.5px] uppercase tracking-wide text-[#9A9BA3]">Kode Verifikasi</p>
                <p className="text-[20px] font-bold font-mono text-[#0058CC]" data-testid="esign-result-code">{result.verification_code}</p>
                <div className="mt-1 flex items-center gap-2">
                  <a href={result.verify_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[11.5px] text-[#0058CC] hover:underline" data-testid="esign-verify-link"><ExternalLink size={12} /> Buka halaman verifikasi</a>
                  <button onClick={copyLink} className="flex items-center gap-1 text-[11.5px] text-[#6B6B73] hover:text-[#0058CC]"><Copy size={12} /> {copied ? "Tersalin" : "Salin tautan"}</button>
                </div>
              </div>
              <button className="btn-primary" onClick={onClose} data-testid="esign-done">Selesai</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
