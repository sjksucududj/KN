/**
 * TraceBackfill — FASE G-4 · **Susun Ulang Relasi** untuk dokumen lama (admin).
 *
 * Data yang lahir sebelum fase ini tidak menyimpan `refs[]`. Alat ini membentuk
 * relasi dari kolom penghubung yang MEMANG sudah ada (mis. `shipments.order_id`) —
 * tidak mengarang relasi.
 *
 * UX yang disengaja: tombol pertama adalah **Periksa dulu (dry-run)** yang tidak
 * mengubah satu pun dokumen. Tombol terapkan baru muncul setelah user melihat
 * berapa relasi yang akan ditambahkan — supaya tidak ada aksi tulis "tak terlihat".
 */
import { useState } from "react";
import { CheckCircle2, Database, Loader2, PlayCircle, SearchCheck } from "lucide-react";
import { errText, runBackfill } from "./traceApi";

export default function TraceBackfill({ onDone }) {
  const [busy, setBusy] = useState("");
  const [dry, setDry] = useState(null);
  const [applied, setApplied] = useState(null);
  const [err, setErr] = useState("");

  const check = async () => {
    setBusy("dry"); setErr(""); setApplied(null);
    try { setDry(await runBackfill(true)); }
    catch (e) { setErr(errText(e, "Gagal memeriksa relasi.")); }
    finally { setBusy(""); }
  };

  const apply = async () => {
    setBusy("apply"); setErr("");
    try {
      const res = await runBackfill(false);
      setApplied(res);
      setDry(await runBackfill(true));
      if (onDone) onDone(res);
    } catch (e) { setErr(errText(e, "Gagal menyusun relasi.")); }
    finally { setBusy(""); }
  };

  return (
    <section className="section-card" data-testid="trace-backfill">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <Database size={14} className="text-[#0058CC]" />
          <h3 className="text-[12.5px] font-bold">Susun Ulang Relasi Dokumen Lama</h3>
        </div>
      </div>
      <div className="section-body space-y-2">
        <p className="text-[11px] text-[#6B6B73]">
          Membentuk referensi dua arah untuk dokumen yang lahir sebelum fitur ini ada.
          Aman diulang (tidak menduplikasi). <b>Periksa dulu</b> tidak mengubah data.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="secondary-button" onClick={check}
            disabled={busy !== ""} data-testid="trace-backfill-dry">
            {busy === "dry" ? <Loader2 size={13} className="animate-spin" /> : <SearchCheck size={13} />}
            Periksa dulu (tanpa mengubah)
          </button>
          {dry && Number(dry.would_add) > 0 && (
            <button type="button" className="primary-button" onClick={apply}
              disabled={busy !== ""} data-testid="trace-backfill-apply">
              {busy === "apply" ? <Loader2 size={13} className="animate-spin" /> : <PlayCircle size={13} />}
              Terapkan {dry.would_add} tautan
            </button>
          )}
        </div>

        {err && (
          <div className="notice-bar danger !py-1.5" data-testid="trace-backfill-error">
            <span className="text-[11.5px]">{err}</span>
          </div>
        )}

        {dry && (
          <div data-testid="trace-backfill-result"
            className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2 text-[11px]">
            <p className="font-semibold text-[#1C1C1E]">
              {Number(dry.would_add) === 0
                ? "Semua relasi sudah lengkap — tidak ada yang perlu ditambahkan."
                : `${dry.would_add} tautan belum tercatat dari ${dry.candidates} kandidat.`}
            </p>
            <p className="text-[10.5px] text-[#6B6B73]">
              Kandidat diperiksa: {dry.candidates} · dilewati (dokumen sudah hilang/duplikat): {dry.skipped}
            </p>
          </div>
        )}

        {applied && (
          <div data-testid="trace-backfill-applied"
            className="flex items-center gap-1.5 rounded-lg border border-[#BFE6CE] bg-[#E7F8EE] p-2 text-[11px] text-[#146c38]">
            <CheckCircle2 size={13} />
            <span><b>{applied.written}</b> tautan ditulis. Jalankan lagi kapan pun — hasilnya tetap sama.</span>
          </div>
        )}
      </div>
    </section>
  );
}
