/**
 * KNSelect — Select universal (wrapper shadcn).
 * UX W2: Semua select harus pakai komponen ini.
 *
 * API (tidak berubah — backward compatible):
 *   <KNSelect value={v} onValueChange={setV} options={[{value, label}]}
 *             className="field" placeholder="..." disabled searchable data-testid="..." />
 *
 * Dua mode render (otomatis, transparan ke pemanggil):
 *  1) Radix Select (default) untuk daftar pendek.
 *  2) Combobox (Popover + cmdk Command) dengan pencarian inline untuk daftar panjang
 *     (>= SEARCH_THRESHOLD opsi) atau saat prop `searchable` di-set true.
 *
 * Empty-value handling: Radix <Select.Item> melarang value="" — komponen ini
 * memetakan "" <-> sentinel "__empty__" untuk jalur Select, DAN menyisipkan satu
 * item sentinel berlabel `placeholder` bila daftar opsi belum punya opsi bernilai
 * kosong. Tanpa item itu, Radix menampilkan kotak KOSONG tanpa petunjuk saat value
 * masih "". Jalur combobox tidak butuh sentinel (kontrol penuh), tapi tetap
 * mengirim "" ke parent seperti biasa.
 */
import React, { useState } from "react";
import { Check, ChevronDown, ChevronsUpDown } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

// Aktifkan pencarian otomatis bila opsi >= ambang ini.
const SEARCH_THRESHOLD = 6;
// Sentinel internal untuk menggantikan empty string yang dilarang Radix Select.
const EMPTY_SENTINEL = "__empty__";

const toSafe = (v) =>
  v === "" || v === null || v === undefined ? EMPTY_SENTINEL : String(v);

/** Combobox dengan pencarian inline. Kontrak prop sama dengan KNSelect. */
function KNCombobox({ value, onValueChange, options, className, placeholder, disabled, testId, ariaLabel }) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => String(o.value) === String(value ?? ""));

  const handleSelect = (val) => {
    if (typeof onValueChange === "function") onValueChange(val);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={className}
          data-testid={testId}
          aria-label={ariaLabel}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            textAlign: "left",
            cursor: disabled ? "not-allowed" : "pointer",
          }}
        >
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              color: selected ? "inherit" : "#9A9BA3",
            }}
          >
            {selected ? selected.label : placeholder}
          </span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="p-0 w-[var(--radix-popover-trigger-width)]"
        data-testid={testId ? `${testId}-popover` : undefined}
      >
        <Command>
          <CommandInput placeholder="Cari..." data-testid={testId ? `${testId}-search` : undefined} />
          <CommandList>
            <CommandEmpty>Tidak ada hasil.</CommandEmpty>
            <CommandGroup>
              {options.map((opt) => (
                <CommandItem
                  key={String(opt.value)}
                  value={`${opt.label} ${String(opt.value)}`}
                  onSelect={() => handleSelect(opt.value)}
                  data-testid={testId ? `${testId}-option-${String(opt.value) || "empty"}` : undefined}
                >
                  <Check
                    className={`mr-2 h-4 w-4 ${
                      String(opt.value) === String(value ?? "") ? "opacity-100" : "opacity-0"
                    }`}
                  />
                  {opt.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

/**
 * KNSelect — komponen Select reusable.
 * @param {string|number} value - nilai terpilih ("" untuk kosong)
 * @param {(val: string) => void} onValueChange - callback ("" untuk kosong)
 * @param {Array<{value: string|number, label: string}>} options
 * @param {string} [className]
 * @param {string} [placeholder]
 * @param {boolean} [disabled]
 * @param {boolean} [searchable] - paksa aktif/nonaktif pencarian (override ambang)
 * @param {string} [aria-label] - nama yang terbacakan pembaca layar. WAJIB diteruskan:
 *   `<select>` bawaan bisa diberi `aria-label` langsung, jadi tanpa pass-through ini
 *   setiap konversi native → KNSelect akan **menghapus** nama kontrolnya secara senyap
 *   (terukur pada `NotificationCenter`, filter "Filter jenis notifikasi").
 */
export function KNSelect({
  value,
  onValueChange,
  options = [],
  className = "field",
  placeholder = "Pilih...",
  disabled = false,
  searchable,
  "data-testid": testId,
  "aria-label": ariaLabel,
}) {
  const useSearch =
    searchable === true || (searchable !== false && options.length >= SEARCH_THRESHOLD);

  if (useSearch) {
    return (
      <KNCombobox
        value={value}
        onValueChange={onValueChange}
        options={options}
        className={className}
        placeholder={placeholder}
        disabled={disabled}
        testId={testId}
        ariaLabel={ariaLabel}
      />
    );
  }

  // ── Jalur Radix Select (daftar pendek) ──
  // CATATAN PENTING: Radix hanya menampilkan `placeholder` bila value-nya `undefined`,
  // sedangkan komponen ini SELALU controlled (memakai "" untuk kondisi kosong). Bila
  // "" dipetakan ke sentinel tanpa item pendamping, Radix menganggap "sudah ada nilai"
  // tetapi tidak menemukan item yang cocok → kotak tampil BENAR-BENAR KOSONG tanpa
  // petunjuk apa pun (mis. "Gudang Tujuan *" terlihat kosong).
  // Solusi: sediakan satu item sentinel berlabel placeholder — kotak selalu punya
  // petunjuk, pengguna juga bisa mengosongkan kembali pilihannya, dan komponen tetap
  // controlled (tanpa peringatan uncontrolled→controlled dari React).
  const safeValue = toSafe(value);
  const handleValueChange = (val) => {
    if (typeof onValueChange === "function") {
      onValueChange(val === EMPTY_SENTINEL ? "" : val);
    }
  };
  const mapped = options.map((opt) => ({ ...opt, safeValue: toSafe(opt.value) }));
  const hasEmptyOption = mapped.some((opt) => opt.safeValue === EMPTY_SENTINEL);
  const isEmpty = safeValue === EMPTY_SENTINEL;
  // Sentinel HANYA disisipkan selama nilainya masih kosong: cukup untuk memunculkan
  // teks petunjuk di trigger, tanpa menambah kemampuan baru "mengosongkan kembali"
  // pada field wajib setelah pengguna memilih (perilaku lama tetap terjaga).
  const safeOptions = hasEmptyOption || !isEmpty
    ? mapped
    : [{ value: "", label: placeholder, safeValue: EMPTY_SENTINEL }, ...mapped];

  return (
    <Select value={safeValue} onValueChange={handleValueChange} disabled={disabled}>
      <SelectTrigger className={className} data-testid={testId} aria-label={ariaLabel} data-kn-empty={isEmpty ? "true" : undefined}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {safeOptions.map((opt) => (
          <SelectItem key={opt.safeValue} value={opt.safeValue}
            data-testid={testId ? `${testId}-option-${String(opt.value) || "empty"}` : undefined}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export default KNSelect;
