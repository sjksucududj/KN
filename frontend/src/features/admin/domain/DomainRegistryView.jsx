/**
 * DomainRegistryView (Fase A · PS-01/02/03/09 · R7) — “Registry Domain”.
 *
 * Layar rujukan tunggal untuk aturan domain tekstil yang DIKUNCI server:
 *   1. Rantai stage (yarn → grey → PFD|PFP → finished) + matriks transisi
 *   2. Simulator transisi (uji kombinasi stage × proses × tujuan × jenis kain)
 *   3. Aturan kelengkapan field per stage (woven vs knit — D-22)
 *   4. Daftar enum resmi + keputusan pemilik (D-01…D-23)
 *
 * Sumber data: `GET /api/enums` (satu pintu) & `POST /api/enums/stage-transitions/validate`.
 */
import { useMemo, useState } from "react";
import {
  AlertTriangle, CheckCircle2, GitBranch, Layers3, RefreshCw, ShieldCheck, Workflow,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import KNSelect from "../../../components/KNSelect";
import useDomainEnums from "../../../hooks/useDomainEnums";
import {
  EnumCard, FieldRuleTable, Kpi, StageChain, TransitionMatrix,
} from "./DomainRegistryParts";

export default function DomainRegistryView() {
  const {
    loading, error, reload, enums, items, options, fieldRules, fieldLabels,
    transitions, matrix, decisions,
  } = useDomainEnums();

  const [sim, setSim] = useState({
    from_stage: "grey", process_type: "pre_treatment", target_use: "dye", fabric_type: "",
  });
  const [simResult, setSimResult] = useState(null);
  const [simBusy, setSimBusy] = useState(false);

  const stages = items("stage");
  const enumNames = useMemo(() => Object.keys(enums || {}), [enums]);
  const activeEnums = enumNames.filter((n) => enums[n]?.in_use);

  async function runSim() {
    setSimBusy(true); setSimResult(null);
    try {
      const body = {
        from_stage: sim.from_stage,
        process_type: sim.process_type,
        target_use: sim.target_use || null,
        fabric_type: sim.fabric_type || null,
      };
      const res = await axios.post(`${API}/enums/stage-transitions/validate`, body);
      setSimResult({ ok: true, ...res.data });
    } catch (e) {
      setSimResult({ ok: false, message: e.response?.data?.detail || "Transisi tidak sah." });
    } finally { setSimBusy(false); }
  }

  if (loading) {
    return (
      <div data-testid="domain-registry-loading" className="section-card">
        <div className="section-body py-10 text-center text-[12px] text-[#6B6B73]">
          Memuat registry enum domain…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="domain-registry-error" className="grid gap-2">
        <ErrorNotice message={error} onRetry={reload} />
      </div>
    );
  }

  if (!enumNames.length) {
    return (
      <div data-testid="domain-registry-empty" className="section-card">
        <div className="section-body py-10 text-center text-[12px] text-[#6B6B73]">
          Registry belum berisi enum. Jalankan ulang backend atau muat ulang.
          <div className="mt-2">
            <button data-testid="domain-registry-empty-reload" className="secondary-button" onClick={reload}>
              <RefreshCw size={13} /> Muat ulang
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="domain-registry-view" className="grid gap-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi testId="domain-kpi-enums" label="Enum Terdaftar" value={enumNames.length}
          hint={`${activeEnums.length} sudah dipakai sistem`} icon={Layers3} />
        <Kpi testId="domain-kpi-stages" label="Tahap Bahan (stage)" value={stages.length}
          hint="yarn → grey → pfd/pfp → finished" icon={Workflow} tone="#6B219A" />
        <Kpi testId="domain-kpi-transitions" label="Transisi Sah" value={transitions.length}
          hint="kombinasi lain ditolak server" icon={GitBranch} tone="#1E7B34" />
        <Kpi testId="domain-kpi-decisions" label="Keputusan Pemilik" value={Object.keys(decisions).length}
          hint="D-01 … D-23 (mengikat)" icon={ShieldCheck} tone="#8C4A00" />
      </div>

      <section className="section-card">
        <div className="section-head">
          <div className="min-w-0">
            <span className="kicker">KN_18 Fase A · PS-01</span>
            <h2>Rantai Tahap Bahan & Matriks Transisi</h2>
          </div>
          <button data-testid="domain-registry-reload" className="secondary-button ml-auto" onClick={reload}>
            <RefreshCw size={13} /> Muat Ulang Registry
          </button>
        </div>
        <div className="section-body grid gap-3">
          <StageChain stages={stages} transitions={transitions} />
          <TransitionMatrix matrix={matrix} />
        </div>
      </section>

      <section className="section-card">
        <div className="section-head">
          <div className="min-w-0">
            <span className="kicker">Uji Aturan</span>
            <h2>Simulator Transisi Stage</h2>
          </div>
        </div>
        <div className="section-body grid gap-2">
          <p className="text-[11px] text-[#6B6B73]">
            Pilih kombinasi lalu uji — hasilnya berasal dari validasi server yang sama dipakai
            saat membuat produk & order makloon (bukan simulasi di browser).
          </p>
          <div className="grid gap-2 md:grid-cols-[1fr_1fr_1fr_1fr_auto]">
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Stage asal</label>
              <KNSelect data-testid="sim-from-stage" className="field" value={sim.from_stage}
                onValueChange={(v) => setSim({ ...sim, from_stage: v })} options={options("stage")} />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Proses</label>
              <KNSelect data-testid="sim-process" className="field" value={sim.process_type}
                onValueChange={(v) => setSim({ ...sim, process_type: v })} options={options("process_type")} />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Tujuan (D-03)</label>
              <KNSelect data-testid="sim-target-use" className="field" value={sim.target_use}
                onValueChange={(v) => setSim({ ...sim, target_use: v })}
                options={options("target_use", [{ value: "", label: "— tidak diisi —" }])} />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Jenis kain</label>
              <KNSelect data-testid="sim-fabric" className="field" value={sim.fabric_type}
                onValueChange={(v) => setSim({ ...sim, fabric_type: v })}
                options={options("fabric_type", [{ value: "", label: "— tidak diisi —" }])} />
            </div>
            <div className="flex items-end">
              <button data-testid="sim-run-button" className="primary-button" disabled={simBusy} onClick={runSim}>
                {simBusy ? "Menguji…" : "Uji Transisi"}
              </button>
            </div>
          </div>
          {simResult && (
            simResult.ok ? (
              <p data-testid="sim-result-ok"
                className="flex items-start gap-1.5 rounded-md border border-[#BBE9C8] bg-[#F0FCF3] p-2 text-[11.5px] font-semibold text-[#1E7B34]">
                <CheckCircle2 size={13} className="mt-0.5 shrink-0" />
                {simResult.message} — stage tujuan: <b className="font-mono">{simResult.to_stage}</b>
              </p>
            ) : (
              <p data-testid="sim-result-error"
                className="flex items-start gap-1.5 rounded-md border border-[#F5C2C0] bg-[#FEF3F2] p-2 text-[11.5px] font-semibold text-[#B3261E]">
                <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                {simResult.message}
              </p>
            )
          )}
        </div>
      </section>

      <section className="section-card">
        <div className="section-head">
          <div className="min-w-0">
            <span className="kicker">PS-02 · PS-03 · D-22</span>
            <h2>Kelengkapan Field Wajib per Tahap</h2>
          </div>
        </div>
        <div className="section-body grid gap-2">
          <FieldRuleTable stages={stages} fieldRules={fieldRules} fieldLabels={fieldLabels} />
          <p className="text-[10.5px] text-[#6B6B73]">
            <b>Woven</b> dikendalikan panjang → GSM & lebar wajib sejak <i>grey</i> agar konversi
            kg↔meter dapat diaudit. <b>Knit</b> dikendalikan berat (kg) → field terukur hanya
            disarankan (peringatan, tidak memblokir).
          </p>
        </div>
      </section>

      <section className="section-card">
        <div className="section-head">
          <div className="min-w-0">
            <span className="kicker">R7 · satu registry</span>
            <h2>Daftar Enum Domain</h2>
          </div>
        </div>
        <div className="section-body grid gap-2">
          {enumNames.map((name) => <EnumCard key={name} name={name} meta={enums[name]} />)}
        </div>
      </section>

      <section className="section-card">
        <div className="section-head">
          <div className="min-w-0">
            <span className="kicker">KN_18 §11</span>
            <h2>Keputusan Pemilik yang Mengikat</h2>
          </div>
        </div>
        <div className="section-body grid gap-1.5">
          {Object.entries(decisions).map(([id, text]) => (
            <p key={id} data-testid={`decision-${id}`} className="text-[11.5px]">
              <b className="font-mono text-[#0058CC]">{id}</b> — {text}
            </p>
          ))}
        </div>
      </section>
    </div>
  );
}
