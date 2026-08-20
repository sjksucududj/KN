/**
 * LineFilter (FASE L) — CHIP PENYARING **LINI PRODUK** untuk 12 layar.
 *
 * KENAPA SATU KOMPONEN
 * Lini (woven · knit · printing · lini baru berikutnya) muncul di Pesanan,
 * Pesanan Pembelian, PR, Roll, Transfer, Retur ×2, Makloon, Sample, Spesifikasi,
 * Desain, dan Master Produk. Kalau tiap layar membuat bilah filternya sendiri,
 * lini ke-4 yang ditambah pemilik akan muncul di sebagian layar saja — persis
 * kelas "dua daftar untuk satu fakta" yang paling mahal di repo ini.
 *
 * TIGA KEPUTUSAN YANG DISENGAJA
 * 1. **Nilai chip datang dari MASTER**, bukan hardcode: `useDomainEnums()` →
 *    `product_line` yang isinya di-overlay `services/master_registry.py` dari
 *    koleksi `product_lines`. Menambah lini di Pengaturan → Master → Lini Produk
 *    langsung terasa di sini tanpa satu baris kode pun berubah (POC L1).
 * 2. **Pilihan diingat per pengguna & per layar** (`localStorage`), karena orang
 *    yang bekerja di satu lini membuka layar yang sama puluhan kali sehari; memaksa
 *    dia memilih ulang tiap kali adalah pajak yang tidak perlu.
 * 3. **Akun berpagar lini hanya melihat lininya.** Menampilkan chip "Woven"
 *    kepada staf printing berarti menawarkan tombol yang PASTI menghasilkan daftar
 *    kosong — server memang menolaknya (pagar `line_scope`), jadi menyembunyikan
 *    chipnya bukan menyembunyikan kebenaran, melainkan tidak memasang jebakan.
 *
 * Gaya visual MENIRU bilah filter yang sudah ada (`features/orders/OrdersView.jsx`
 * & `AccountList.jsx`): kotak putih, border #E5E5EA, chip rounded-md. Tidak ada
 * bahasa visual baru (kontrak UI/UX §4 RENCANA_EKSEKUSI_MD_ERP.md).
 *
 * Pemakaian:
 *   const [line, setLine] = useState("");            // "" = semua
 *   <LineFilter value={line} onChange={setLine} storageKey="orders"
 *               allowed={currentUser?.allowed_line_codes} />
 *   …lalu kirim `line` sebagai parameter `?line=` ke endpoint daftarnya.
 */
import { useCallback, useEffect, useMemo } from "react";
import { Layers3 } from "lucide-react";

import useDomainEnums from "../hooks/useDomainEnums";

const STORAGE_PREFIX = "kn.lineFilter.";

/** Baca pilihan tersimpan (aman bila localStorage diblokir peramban). */
function readSaved(storageKey) {
  if (!storageKey) return "";
  try {
    return window.localStorage.getItem(STORAGE_PREFIX + storageKey) || "";
  } catch {
    return "";
  }
}

function writeSaved(storageKey, value) {
  if (!storageKey) return;
  try {
    window.localStorage.setItem(STORAGE_PREFIX + storageKey, value || "");
  } catch {
    /* mode privat / storage penuh — penyaring tetap bekerja, hanya tidak diingat */
  }
}

export default function LineFilter({
  value = "",
  onChange,
  storageKey = "",
  allowed = [],
  label = "Lini",
  className = "",
  testId = "line-filter",
}) {
  const { options, loading } = useDomainEnums();

  const allOptions = useMemo(() => options("product_line"), [options]);
  const allowedSet = useMemo(
    () => new Set((allowed || []).map((c) => String(c || "").trim().toLowerCase())),
    [allowed]
  );
  const lines = useMemo(
    () => (allowedSet.size ? allOptions.filter((o) => allowedSet.has(o.value)) : allOptions),
    [allOptions, allowedSet]
  );

  const selected = useMemo(
    () => String(value || "").split(",").map((s) => s.trim()).filter(Boolean),
    [value]
  );

  // Pulihkan pilihan terakhir sekali saat layar dibuka (hanya bila belum dipilih).
  useEffect(() => {
    if (!storageKey || value) return;
    const saved = readSaved(storageKey);
    if (!saved) return;
    // Buang lini yang sudah tidak ada / tidak boleh diakses akun ini, supaya
    // pilihan lama tidak membuat layar kosong tanpa sebab setelah hak berubah.
    const known = new Set(lines.map((o) => o.value));
    const keep = saved.split(",").filter((c) => known.has(c));
    if (keep.length) onChange?.(keep.join(","));
    else if (saved) writeSaved(storageKey, "");
  }, [storageKey, lines]); // eslint-disable-line react-hooks/exhaustive-deps

  const setValue = useCallback((next) => {
    writeSaved(storageKey, next);
    onChange?.(next);
  }, [onChange, storageKey]);

  const toggle = (code) => {
    const next = selected.includes(code)
      ? selected.filter((c) => c !== code)
      : [...selected, code];
    setValue(next.join(","));
  };

  // Satu lini (atau nol) → tidak ada yang bisa disaring; sembunyikan bilahnya
  // daripada memasang kontrol yang tidak mengubah apa pun.
  if (loading || lines.length < 2) return null;

  const chip = (active) =>
    `rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors ${
      active
        ? "bg-[#1C1C1E] text-white"
        : "border border-[#E5E5EA] bg-white text-[#6B6B73] hover:border-[#1C1C1E]/40"
    }`;

  return (
    <div
      data-testid={testId}
      className={`flex flex-wrap items-center gap-1.5 rounded-lg border border-[#E5E5EA] bg-white px-3 py-2 ${className}`}
    >
      <Layers3 size={13} className="text-[#6B6B73]" />
      <span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
        {label}
      </span>
      <button
        type="button"
        data-testid={`${testId}-all`}
        onClick={() => setValue("")}
        className={chip(selected.length === 0)}
      >
        Semua
      </button>
      {lines.map((o) => (
        <button
          key={o.value}
          type="button"
          data-testid={`${testId}-${o.value}`}
          onClick={() => toggle(o.value)}
          className={chip(selected.includes(o.value))}
          title={o.label}
        >
          {o.label}
        </button>
      ))}
      {allowedSet.size > 0 && (
        <span
          data-testid={`${testId}-restricted`}
          className="ml-1 rounded bg-[#FFF4E5] px-1.5 py-0.5 text-[9.5px] font-bold text-[#B45309]"
          title="Akses akun Anda dibatasi pada lini ini oleh admin (Badan Usaha & Akses → Akun)."
        >
          akses lini terbatas
        </span>
      )}
    </div>
  );
}
