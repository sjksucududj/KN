import { useState } from "react";
import { Layers3, ShieldCheck } from "lucide-react";

/**
 * LoginScreen — role-based auth entry. Extracted from CoreWidgets.jsx so the
 * shared layout primitives stay free of form/grid markup (KN_02 modularity).
 */
export function LoginScreen({ onLogin, notice }) {
  const [email, setEmail] = useState("admin@kainnusantara.id");
  const [password, setPassword] = useState("demo12345");
  // `key` dipakai untuk data-testid (STABIL, jangan diterjemahkan) sedangkan
  // `label` adalah yang DILIHAT pengguna. Sebelumnya keduanya satu nilai, jadi
  // menerjemahkan tombol otomatis mengubah data-testid dan mematikan skrip uji.
  const demoUsers = [
    { key: "admin", label: "Admin", mail: "admin@kainnusantara.id" },
    { key: "manager", label: "Manajer", mail: "manager@kainnusantara.id" },
    // FASE E-8 (E8.1) — dua peran baru: pemilik alur pesanan & sisi uang masuk.
    { key: "sales-admin", label: "Admin Sales", mail: "salesadmin@kainnusantara.id" },
    { key: "finance", label: "Finance", mail: "finance@kainnusantara.id" },
    { key: "sales", label: "Sales", mail: "sales@kainnusantara.id" },
    { key: "warehouse", label: "Gudang", mail: "warehouse@kainnusantara.id" },
  ];
  return (
    <main data-testid="login-screen" className="app-shell login-screen">
      <section className="login-card">
        <div className="login-left">
          <div className="login-brand-mark"><Layers3 size={20} /></div>
          <p className="mt-5 text-[10.5px] font-bold uppercase tracking-wider text-[#0058CC]">Akses sesuai peran</p>
          <h1 data-testid="login-title" className="login-title">Kain Nusantara Control Center</h1>
          <p data-testid="login-subtitle" className="login-sub">Masuk sesuai peran Anda — Admin, Manajer, Admin Sales, Finance, Sales, atau Gudang — untuk akses menu dan aksi sesuai izin.</p>
          <div className="mt-5 grid grid-cols-2 gap-2">
            {demoUsers.map(({ key, label, mail }) => (
              <button key={mail} data-testid={`demo-login-${key}-button`} className="secondary-button justify-start"
                onClick={() => { setEmail(mail); setPassword("demo12345"); onLogin(mail, "demo12345"); }}>
                <ShieldCheck size={14} /> {label}
              </button>
            ))}
          </div>
        </div>
        <div className="login-right">
          <h2 className="login-form-title">Masuk</h2>
          <p data-testid="login-notice" className="login-form-sub">{notice || "Password demo: demo12345"}</p>
          <div className="grid gap-3">
            <label className="grid gap-1">
              <span className="text-[11px] font-semibold text-[#3C3C43]">Email</span>
              <input data-testid="login-email-input" className="field" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email@perusahaan.id" autoComplete="email" />
            </label>
            <label className="grid gap-1">
              <span className="text-[11px] font-semibold text-[#3C3C43]">Password</span>
              <input data-testid="login-password-input" className="field" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />
            </label>
            <button data-testid="login-submit-button" className="primary-button w-full" onClick={() => onLogin(email, password)}><ShieldCheck size={16} /> Masuk</button>
          </div>
        </div>
      </section>
    </main>
  );
}
