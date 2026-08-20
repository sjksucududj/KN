/**
 * SchedulerWa (R6.5) — tab WhatsApp: pengaturan provider/kredensial + Outbox pesan.
 *
 * Mode default = SIMULASI: pesan TIDAK dikirim ke jaringan tetapi tetap tercatat di
 * Outbox (tujuan + isi lengkap) sehingga user bisa memverifikasi sebelum mengisi
 * kredensial provider nyata (Meta Cloud API / Fonnte).
 */
import { useState } from "react";
import { Send, RotateCcw, ShieldCheck, Info, Loader2, Trash2, Eye } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { Badge } from "../../finance/financeShared";
import { inputCls, labelCls, fmtWaktu } from "./SchedulerParts";

const PROVIDER_OPTS = [
  { value: "simulated", label: "Simulasi (tercatat di Outbox, tidak dikirim)" },
  { value: "fonnte", label: "Fonnte (gateway lokal · 1 token, teks bebas)" },
  { value: "meta_cloud", label: "Meta WhatsApp Cloud API (resmi · wajib template)" },
];
const SEVERITY_OPTS = [
  { value: "info", label: "Semua (info, perhatian, penting)" },
  { value: "warning", label: "Perhatian & Penting saja (disarankan)" },
  { value: "critical", label: "Hanya Penting (paling hemat)" },
];
// R6.6 — mode pengiriman: cegah staf kebanjiran pesan per-alert.
const MODE_OPTS = [
  { value: "instant", label: "Instan — 1 pesan per alert (real-time)" },
  { value: "digest", label: "Ringkasan Harian — semua alert digabung jadi 1 pesan" },
];

function OutboxStatus({ status }) {
  if (status === "sent") return <Badge tone="ok" testId="wa-status-sent">Terkirim</Badge>;
  if (status === "simulated") return <Badge tone="purple" testId="wa-status-simulated">Simulasi</Badge>;
  if (status === "failed") return <Badge tone="over" testId="wa-status-failed">Gagal</Badge>;
  return <Badge tone="neutral">{status || "—"}</Badge>;
}

export function WaSettingsPanel({ wa, perms, saving, onSave, onTest, testing, onPreviewDigest }) {
  const [form, setForm] = useState({
    enabled: !!wa.enabled,
    provider: wa.provider || "simulated",
    pic_number: wa.pic_number || "",
    send_to_roles: wa.send_to_roles !== false,
    min_severity: wa.min_severity || "warning",
    delivery_mode: wa.delivery_mode || "instant",
    critical_bypass: wa.critical_bypass !== false,
    phone_number_id: wa.phone_number_id || "",
    template_name: wa.template_name || "",
    template_lang: wa.template_lang || "id",
    access_token: "",
    fonnte_token: "",
  });
  const [testPhone, setTestPhone] = useState(wa.pic_number || "");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = () => {
    const payload = {
      enabled: form.enabled, provider: form.provider,
      pic_number: form.pic_number, send_to_roles: form.send_to_roles,
      min_severity: form.min_severity,
      delivery_mode: form.delivery_mode, critical_bypass: form.critical_bypass,
    };
    if (form.provider === "meta_cloud") {
      payload.phone_number_id = form.phone_number_id;
      payload.template_name = form.template_name;
      payload.template_lang = form.template_lang;
    }
    // Kirim token HANYA bila diisi (kosong = jangan ubah yang tersimpan).
    if (form.access_token) payload.access_token = form.access_token;
    if (form.fonnte_token) payload.fonnte_token = form.fonnte_token;
    onSave(payload);
  };

  return (
    <div className="space-y-3" data-testid="wa-settings">
      <div className="flex items-start gap-2 rounded-xl border border-[#CFE3FF] bg-[#F2F7FF] px-3 py-2.5 text-[11.5px] text-[#0B4A9B]">
        <Info size={14} className="mt-0.5 shrink-0" />
        <div>
          <b>Mode Simulasi aktif secara default.</b> Semua pesan alert tercatat lengkap di
          Outbox (nomor tujuan + isi pesan) tanpa dikirim ke jaringan — aman untuk verifikasi.
          Isi kredensial provider bila sudah siap mengirim nyata.
          <div className="mt-1 text-[11px] text-[#3A6EA5]">
            Catatan: <b>Meta Cloud API</b> mewajibkan <b>template UTILITY yang disetujui</b> untuk
            pesan keluar ke nomor yang tidak membalas dalam 24 jam. <b>Fonnte</b> hanya butuh 1 token
            dan boleh teks bebas.
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-[#EFF0F2] bg-white p-3.5">
          <div className="mb-2.5 text-[11px] font-bold uppercase tracking-wide text-[#8E8E93]">Kanal & Penerima</div>
          <label className="mb-3 flex items-center gap-2 text-[12px] font-semibold text-[#1C1C1E]">
            <input data-testid="wa-enabled-toggle" type="checkbox" checked={form.enabled}
                   disabled={!perms.configure}
                   onChange={(e) => set("enabled", e.target.checked)}
                   className="h-4 w-4 accent-[#6B219A]" />
            Aktifkan kanal WhatsApp untuk alert
          </label>
          <div className="mb-3">
            <label className={labelCls}>Provider</label>
            <KNSelect data-testid="wa-provider-select" value={form.provider}
                      onValueChange={(v) => set("provider", v)} options={PROVIDER_OPTS}
                      className={inputCls} disabled={!perms.configure} />
          </div>
          <div className="mb-3">
            <label className={labelCls}>Kirim untuk tingkat kepentingan</label>
            <KNSelect data-testid="wa-severity-select" value={form.min_severity}
                      onValueChange={(v) => set("min_severity", v)} options={SEVERITY_OPTS}
                      className={inputCls} disabled={!perms.configure} />
          </div>
          {/* R6.6 — mode pengiriman: instan vs ringkasan harian */}
          <div className="mb-3 rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] p-2.5">
            <label className={labelCls}>Mode pengiriman</label>
            <KNSelect data-testid="wa-mode-select" value={form.delivery_mode}
                      onValueChange={(v) => set("delivery_mode", v)} options={MODE_OPTS}
                      className={inputCls} disabled={!perms.configure} />
            {form.delivery_mode === "digest" ? (
              <>
                <label className="mt-2 flex items-center gap-2 text-[11.5px] text-[#1C1C1E]">
                  <input data-testid="wa-critical-bypass-toggle" type="checkbox"
                         checked={form.critical_bypass} disabled={!perms.configure}
                         onChange={(e) => set("critical_bypass", e.target.checked)}
                         className="h-4 w-4 accent-[#6B219A]" />
                  Alert <b>PENTING</b> tetap dikirim seketika (tidak menunggu ringkasan)
                </label>
                <p className="mt-1 text-[10px] leading-snug text-[#9A9BA3]">
                  Ringkasan dikirim oleh job <b>Ringkasan Harian</b> (default 08:30 WIB) — satu
                  pesan per penerima berisi semua alert hari itu, dikelompokkan per jenis.
                </p>
              </>
            ) : (
              <p className="mt-1 text-[10px] leading-snug text-[#9A9BA3]">
                Setiap alert dikirim sebagai pesan terpisah. Bila terasa terlalu banyak,
                pilih <b>Ringkasan Harian</b>.
              </p>
            )}
            <button data-testid="wa-digest-preview" type="button"
                    onClick={() => onPreviewDigest?.()}
                    className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-[#E2E2E7] bg-white px-2.5 py-1.5 text-[11.5px] font-semibold text-[#6B219A] hover:bg-[#F7F2FB]">
              <Eye size={12} /> Pratinjau ringkasan hari ini
            </button>
          </div>
          <label className="mb-3 flex items-center gap-2 text-[12px] text-[#1C1C1E]">
            <input data-testid="wa-roles-toggle" type="checkbox" checked={form.send_to_roles}
                   disabled={!perms.configure}
                   onChange={(e) => set("send_to_roles", e.target.checked)}
                   className="h-4 w-4 accent-[#6B219A]" />
            Kirim ke nomor pengguna sesuai peran penerima
          </label>
          <div>
            <label className={labelCls}>Nomor PIC tambahan (opsional)</label>
            <input data-testid="wa-pic-input" className={inputCls} value={form.pic_number}
                   disabled={!perms.configure} placeholder="0812xxxxxxx"
                   onChange={(e) => set("pic_number", e.target.value)} />
            <p className="mt-1 text-[10px] text-[#9A9BA3]">Semua alert juga dikirim ke nomor ini (mis. grup/PIC operasional).</p>
          </div>
        </div>

        <div className="rounded-xl border border-[#EFF0F2] bg-white p-3.5">
          <div className="mb-2.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-[#8E8E93]">
            <ShieldCheck size={13} /> Kredensial
          </div>
          {form.provider === "simulated" && (
            <p className="text-[11.5px] text-[#8E8E93]">
              Mode simulasi tidak memerlukan kredensial. Pilih provider lain untuk mengirim nyata.
            </p>
          )}
          {form.provider === "fonnte" && (
            <div>
              <label className={labelCls}>Fonnte API Token {wa.has_fonnte_token && <span className="text-[#1B7F4B]">· tersimpan</span>}</label>
              <input data-testid="wa-fonnte-token-input" type="password" className={inputCls}
                     disabled={!perms.configure} value={form.fonnte_token}
                     placeholder={wa.has_fonnte_token ? "•••••• (biarkan kosong = tidak diubah)" : "Tempel token Fonnte"}
                     onChange={(e) => set("fonnte_token", e.target.value)} />
              <p className="mt-1 text-[10px] text-[#9A9BA3]">Dapatkan di dasbor Fonnte → menu Device → Token.</p>
            </div>
          )}
          {form.provider === "meta_cloud" && (
            <div className="space-y-2.5">
              <div>
                <label className={labelCls}>Phone Number ID</label>
                <input data-testid="wa-phone-number-id-input" className={inputCls}
                       disabled={!perms.configure} value={form.phone_number_id}
                       placeholder="mis. 104561239581234"
                       onChange={(e) => set("phone_number_id", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>System User Access Token (permanen) {wa.has_access_token && <span className="text-[#1B7F4B]">· tersimpan</span>}</label>
                <input data-testid="wa-access-token-input" type="password" className={inputCls}
                       disabled={!perms.configure} value={form.access_token}
                       placeholder={wa.has_access_token ? "•••••• (biarkan kosong = tidak diubah)" : "EAAI..."}
                       onChange={(e) => set("access_token", e.target.value)} />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="col-span-2">
                  <label className={labelCls}>Nama Template (UTILITY, disetujui)</label>
                  <input data-testid="wa-template-input" className={inputCls}
                         disabled={!perms.configure} value={form.template_name}
                         placeholder="mis. erp_alert_internal"
                         onChange={(e) => set("template_name", e.target.value)} />
                </div>
                <div>
                  <label className={labelCls}>Bahasa</label>
                  <input data-testid="wa-template-lang-input" className={inputCls}
                         disabled={!perms.configure} value={form.template_lang}
                         onChange={(e) => set("template_lang", e.target.value)} />
                </div>
              </div>
              <p className="text-[10px] text-[#9A9BA3]">
                Template harus punya 2 variabel body: {"{{1}}"} judul, {"{{2}}"} isi alert.
              </p>
            </div>
          )}
          <div className="mt-3 flex items-center gap-2 border-t border-[#F2F2F5] pt-3">
            <input data-testid="wa-test-phone-input" className={`${inputCls} flex-1`}
                   value={testPhone} placeholder="Nomor tujuan tes (0812xxxx)"
                   onChange={(e) => setTestPhone(e.target.value)} />
            <button data-testid="wa-test-button" disabled={!perms.configure || testing}
                    onClick={() => onTest(testPhone)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#E2E2E7] px-3 py-2 text-[12px] font-semibold text-[#6B219A] hover:bg-[#F7F2FB] disabled:opacity-40">
              {testing ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Tes Kirim
            </button>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2">
        {perms.configure && (wa.has_access_token || wa.has_fonnte_token) && (
          <button data-testid="wa-clear-tokens" disabled={saving}
                  onClick={() => onSave({ clear_tokens: true, provider: "simulated", enabled: form.enabled })}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[#F3D6D6] px-3 py-2 text-[12px] font-semibold text-[#C0392B] hover:bg-[#FDECEC] disabled:opacity-40">
            <Trash2 size={13} /> Hapus Kredensial
          </button>
        )}
        <button data-testid="wa-save-button" disabled={!perms.configure || saving} onClick={submit}
                className="rounded-lg bg-[#6B219A] px-4 py-2 text-[12px] font-bold text-white hover:bg-[#581680] disabled:opacity-50">
          {saving ? "Menyimpan…" : "Simpan Pengaturan WhatsApp"}
        </button>
      </div>
    </div>
  );
}

export function WaOutboxTable({ items, stats, perms, busyId, onRetry, filter, onFilter }) {
  return (
    <div className="space-y-2.5" data-testid="wa-outbox">
      <div className="flex flex-wrap items-center gap-2">
        <KNSelect data-testid="wa-outbox-filter" value={filter} onValueChange={onFilter}
                  options={[{ value: "", label: "Semua status" },
                            { value: "simulated", label: "Simulasi" },
                            { value: "sent", label: "Terkirim" },
                            { value: "failed", label: "Gagal" }]}
                  className={`${inputCls} w-44`} />
        <span className="text-[11px] text-[#9A9BA3]">
          {items.length} pesan ditampilkan · total {stats?.total ?? 0} · hari ini {stats?.today ?? 0}
        </span>
      </div>
      {items.length === 0 ? (
        <div className="rounded-xl border border-[#EFF0F2] bg-white px-4 py-8 text-center" data-testid="wa-outbox-empty">
          <p className="text-[12.5px] font-semibold text-[#1C1C1E]">Outbox masih kosong</p>
          <p className="mt-1 text-[11.5px] text-[#8E8E93]">
            Aktifkan kanal WhatsApp lalu jalankan job — pesan yang akan dikirim muncul di sini.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[#EFF0F2] bg-white">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="bg-[#FAFAFC] text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93]">
                <th className="px-3 py-2.5 font-bold">Waktu</th>
                <th className="px-3 py-2.5 font-bold">Tujuan</th>
                <th className="px-3 py-2.5 font-bold">Isi Pesan</th>
                <th className="px-3 py-2.5 font-bold">Provider</th>
                <th className="px-3 py-2.5 font-bold text-center">Status</th>
                <th className="px-3 py-2.5 font-bold text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F2F2F5]">
              {items.map((o) => (
                <tr key={o.id} data-testid={`wa-row-${o.id}`} className="hover:bg-[#FCFAFE]">
                  <td className="px-3 py-2 whitespace-nowrap text-[#3A3A3C]">{fmtWaktu(o.created_at)}</td>
                  <td className="px-3 py-2">
                    <div className="font-semibold text-[#1C1C1E]">{o.to}</div>
                    <div className="text-[10.5px] text-[#8E8E93]">{o.to_name} · {o.to_role}</div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-semibold text-[#1C1C1E]">{o.title}</div>
                    <div className="max-w-[420px] whitespace-pre-wrap text-[10.5px] leading-snug text-[#8E8E93]">
                      {(o.text || "").slice(0, 220)}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-[#3A3A3C]">{o.provider}</td>
                  <td className="px-3 py-2 text-center">
                    <OutboxStatus status={o.status} />
                    {o.error && <div className="mt-0.5 max-w-[180px] text-[10px] text-[#C0392B]">{o.error}</div>}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button data-testid={`wa-retry-${o.id}`} disabled={!perms.run || busyId === o.id}
                            onClick={() => onRetry(o.id)} title="Kirim ulang"
                            className="inline-flex items-center gap-1 rounded-lg border border-[#E2E2E7] px-2 py-1 text-[11.5px] font-semibold text-[#6B219A] hover:bg-[#F7F2FB] disabled:opacity-40">
                      {busyId === o.id ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
                      Ulangi
                    </button>
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
