/**
 * EntitiesAccessView (FASE E-3) — SATU PINTU untuk badan usaha & hak akses.
 *
 * Mengganti tab "Entities" dan "Users" lama di Master Data. Tab lama DIHAPUS
 * (bukan dibiarkan hidup berdampingan) supaya tidak ada dua pintu yang bisa
 * saling bertentangan — dulu formulir lama bisa mengetik `home_entity_id` bebas
 * sehingga bertentangan dengan data HR.
 *
 * Tiga tab:
 *   Badan Usaha · Akun & Akses · Kesiapan
 */
import { useCallback, useEffect, useState } from "react";
import { Building2, Users, ClipboardCheck, Plus, RefreshCw, UserCheck } from "lucide-react";

import ErrorNotice from "../../../components/ErrorNotice";
import EntityList from "./EntityList";
import EntityWizard from "./EntityWizard";
import EntityDetailDrawer from "./EntityDetailDrawer";
import AccountList from "./AccountList";
import RoleRealityPanel from "./RoleRealityPanel";
import EntityReadinessPanel from "./EntityReadinessPanel";
import { listEntities, errText } from "./entityApi";

const TABS = [
  { key: "entities", label: "Badan Usaha", icon: Building2 },
  { key: "accounts", label: "Akun & Akses", icon: Users },
  // Utang migrasi (ii) E-8 — tab ini menjawab "peran siapa yang tidak cocok dengan
  // pekerjaannya", dihitung dari jejak nyata. Letaknya SETELAH "Akun & Akses"
  // karena ia menilai isi tab itu.
  { key: "role-reality", label: "Cek Peran", icon: UserCheck },
  { key: "readiness", label: "Kesiapan", icon: ClipboardCheck },
];

export default function EntitiesAccessView({ currentUser, selectedEntity, onNavigate }) {
  const [tab, setTab] = useState("entities");
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [detailId, setDetailId] = useState("");
  const [flash, setFlash] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const isAdmin = currentUser?.role === "admin";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // status=all: layar pengelolaan HARUS bisa melihat yang terarsip juga,
      // berbeda dari pemilih entitas yang hanya menampilkan yang aktif.
      const rows = await listEntities({ status: "all", with_readiness: true });
      setEntities(rows);
      setError("");
    } catch (e) {
      setError(errText(e, "Gagal memuat daftar badan usaha."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load, reloadKey]);

  const refreshAll = () => setReloadKey((k) => k + 1);

  return (
    <div data-testid="entities-access-view">
      {/* Pita penjelas: layar ini mengatur SIAPA boleh melihat APA. */}
      <div
        data-testid="entities-access-intro"
        className="mb-3 flex flex-wrap items-start gap-2 rounded-md border border-[#C9DBF7] bg-[#F2F7FF] px-3 py-2"
      >
        <Building2 size={14} className="mt-0.5 text-[#0058CC]" />
        <div className="min-w-0">
          <p className="text-[11.5px] font-bold text-[#1C1C1E]">
            Satu perusahaan, beberapa badan usaha — buku keuangan, pajak, harga, dan
            pelanggannya terpisah.
          </p>
          <p className="text-[10.5px] text-[#6B6B73]">
            Karyawan hanya melihat data badan usaha tempat dia ditugaskan. Badan usaha
            utama akun diambil dari data karyawan (HR) supaya penggajian dan hak akses
            tidak pernah bertentangan.
          </p>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              type="button"
              data-testid={`entities-access-tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[12.5px] font-semibold transition-colors ${
                active
                  ? "border-[#1C1C1E] bg-[#1C1C1E] text-white"
                  : "border-[#E5E5EA] bg-white text-[#3A3A3C] hover:border-[#1C1C1E]/40"
              }`}
            >
              <Icon size={13} /> {t.label}
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-2">
          {tab === "entities" && isAdmin && (
            <button
              type="button"
              className="primary-button"
              data-testid="entity-add-button"
              onClick={() => setWizardOpen(true)}
            >
              <Plus size={14} /> Tambah Badan Usaha
            </button>
          )}
          <button
            type="button"
            className="icon-button"
            data-testid="entities-access-refresh"
            aria-label="Muat ulang"
            onClick={refreshAll}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {flash && (
        <div className="notice-bar success !py-1.5 mb-2" data-testid="entities-access-flash">
          <span className="text-[11.5px]">{flash}</span>
        </div>
      )}
      <ErrorNotice
        message={error}
        onRetry={refreshAll}
        onDismiss={() => setError("")}
        testId="entities-access-error"
      />

      {tab === "entities" && (
        <EntityList
          entities={entities}
          loading={loading}
          canManage={isAdmin}
          onOpen={(id) => setDetailId(id)}
          onChanged={(msg) => { setFlash(msg); refreshAll(); }}
          onError={setError}
        />
      )}

      {tab === "accounts" && (
        <AccountList
          entities={entities}
          currentUser={currentUser}
          selectedEntity={selectedEntity}
          onChanged={(msg) => { setFlash(msg); refreshAll(); }}
          onError={setError}
        />
      )}

      {tab === "role-reality" && (
        <RoleRealityPanel
          canManage={isAdmin}
          onChanged={(msg) => { setFlash(msg); refreshAll(); }}
          onError={setError}
        />
      )}

      {tab === "readiness" && (
        <EntityReadinessPanel
          entities={entities}
          onNavigate={onNavigate}
          onError={setError}
        />
      )}

      {wizardOpen && (
        <EntityWizard
          entities={entities}
          onClose={() => setWizardOpen(false)}
          onCreated={(ent) => {
            setWizardOpen(false);
            setFlash(
              `Badan usaha “${ent.legal_name || ent.name}” dibuat. Nomor dokumennya akan ` +
              `berawalan ${ent.provisioning?.number_preview || ent.doc_prefix}.`
            );
            refreshAll();
            setDetailId(ent.id);
          }}
        />
      )}

      {detailId && (
        <EntityDetailDrawer
          entityId={detailId}
          canManage={isAdmin}
          onClose={() => setDetailId("")}
          onChanged={(msg) => { setFlash(msg); refreshAll(); }}
          onNavigate={onNavigate}
        />
      )}
    </div>
  );
}
