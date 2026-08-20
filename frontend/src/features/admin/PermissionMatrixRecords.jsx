// Editor matriks permission (records) untuk AdminView, dipisah agar file utama di
// bawah batas guardrail. Menerima matrix + handler simpan dari parent.

const ALL_ACTIONS = {
  product: ["view", "create", "update", "delete", "import", "export"],
  customer: ["view", "create", "update", "delete", "import", "export"],
  warehouse: ["view", "create", "update", "delete", "import", "export"],
  uom: ["view", "create", "update", "delete", "import", "export"],
  template: ["view", "create", "update", "delete", "print", "import", "export"],
  order: ["view", "create", "update", "delete", "approve", "confirm", "print"],
  wms: ["view", "create", "update", "scan", "dispatch", "print"],
  document: ["view", "create", "print"],
  user: ["view", "create", "update", "delete"],
  permission: ["view", "update"],
  inventory: ["view", "create", "update", "cycle_count", "approve_count"],
  reports: ["view", "export"],
};

export default function PermissionMatrixRecords({ matrix, onUpdatePermissions }) {
  const roles = Object.entries(matrix || {});
  // FASE P5 — matriks kosong dulu dirender sebagai AREA KOSONG tanpa satu kata pun
  // (mis. saat `/permissions` ditolak 403 untuk peran ini, atau matriks belum pernah
  // disimpan). Pengguna hanya melihat tab yang "tidak menampilkan apa-apa".
  if (roles.length === 0) {
    return (
      <div data-testid="permission-matrix-empty"
        className="rounded-xl border border-dashed border-[#E5E5EA] bg-[#FAFBFC] py-10 text-center">
        <p className="text-[12px] font-semibold text-[#1C1C1E]">Belum ada matriks izin yang bisa ditampilkan</p>
        <p className="mt-1 text-[11px] text-[#8E8E93]">
          Matriks tersimpan di basis data dan hanya bisa dibuka oleh akun yang punya izin
          <b> permission.view</b>. Muat ulang halaman, atau minta admin membuka aksesnya.
        </p>
      </div>
    );
  }
  return (
    <div data-testid="permission-matrix-records" className="grid gap-4 overflow-auto">
      {roles.map(([role, modules]) => (
        <div key={role} className="rounded-xl border border-[#EFF0F2] bg-[#FAFBFC] p-3">
          <h4 className="text-[13px] font-bold capitalize mb-2">{role}</h4>
          <div className="grid gap-2">
            {Object.entries(modules).map(([module, actions]) => {
              const availableActions = ALL_ACTIONS[module] || Array.from(new Set([...Object.values(ALL_ACTIONS).flat()]));
              return (
                <div key={module} data-testid={`permission-row-${role}-${module}`} className="rounded-md border border-[#EFF0F2] bg-white p-2">
                  <p className="text-[11.5px] font-bold capitalize">{module}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {availableActions.map((action) => (
                      <label key={action} data-testid={`permission-cell-${role}-${module}-${action}`}
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold border cursor-pointer transition-colors ${
                          (actions || []).includes(action) ? "bg-[#007AFF] text-white border-[#007AFF]" : "bg-white text-[#6B6B73] border-[#EFF0F2] hover:border-[#007AFF]"
                        }`}>
                        <input type="checkbox" className="sr-only" checked={(actions || []).includes(action)}
                          onChange={(e) => {
                            const next = JSON.parse(JSON.stringify(matrix));
                            const current = new Set(next[role]?.[module] || []);
                            if (e.target.checked) current.add(action); else current.delete(action);
                            next[role] = next[role] || {};
                            next[role][module] = Array.from(current);
                            onUpdatePermissions(next, false);
                          }} />
                        {action}
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
