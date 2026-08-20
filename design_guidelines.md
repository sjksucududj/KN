{
  "meta": {
    "product": "Kain Nusantara (KN) ERP",
    "scope": "Blueprint UI/UX untuk komponen & halaman BARU (Makloon + Product/Color master upgrade) TANPA mengubah tema/palette existing.",
    "language": "id-ID",
    "tech": {
      "frontend": "React (JS), Tailwind, shadcn/ui (components/ui), lucide-react",
      "patterns": "Dense ERP, desktop-first dengan fallback mobile",
      "testing": "Semua elemen interaktif & info penting wajib data-testid (kebab-case)"
    },
    "non_goals": [
      "Jangan memperkenalkan tema baru, font baru, atau palette baru.",
      "Jangan restyle halaman existing; hanya extend sistem yang ada.",
      "Jangan pakai emoji untuk ikon; hanya lucide-react.",
      "Jangan pakai gradient baru untuk komponen baru (ikuti existing)."
    ]
  },

  "design_tokens_reference": {
    "source_files": [
      "/app/frontend/src/styles/tokens.css",
      "/app/frontend/src/styles/components.css",
      "/app/frontend/src/styles/layout.css",
      "/app/frontend/src/index.css"
    ],
    "do_not_change": {
      "primary": "#0058CC (ios-blue-strong) / #007AFF (ios-blue)",
      "accent_blue_bg": "#EAF2FF / #EFF4FF",
      "purple_accent": "#6B219A (bg #F3E9FA)",
      "success": "#126E2C / #3A7D44",
      "danger": "#A8221A / #D14343",
      "neutrals": "#1C1C1E, #3C3C43, #6B6B73, #8E8E93, #9A9BA3",
      "borders": "#E5E5EA / #EFF0F2",
      "subtle_bg": "#FAFBFC / #F5F5F7"
    },
    "typography": {
      "existing": {
        "body": "Manrope",
        "headings": "Outfit",
        "base_font_size": "13px typical (lihat .field, .button)"
      },
      "rules": [
        "Jangan ganti font-family global.",
        "Angka uang/qty: gunakan class `tabular-nums` + formatter existing (formatCurrency/formatQty)."
      ]
    },
    "spacing_and_radius": {
      "spacing_scale": "--sp-1..--sp-8 (4pt scale)",
      "radii": "--r-sm 8px, --r-md 10px, --r-lg 14px, --r-xl 18px",
      "shadows": "--shadow-1..--shadow-3"
    },
    "existing_utility_classes_to_reuse": {
      "surfaces": ["section-card", "section-head", "section-body", "solid-card", "glass-panel"],
      "inputs": ["field", "search-wrap", "search-box"],
      "buttons": ["primary-button", "secondary-button", "danger-button", "icon-button", "nav-button"],
      "status": ["status-pill", "status-<status>"]
    }
  },

  "component_path": {
    "shadcn_ui": {
      "popover": "/app/frontend/src/components/ui/popover.jsx",
      "dialog": "/app/frontend/src/components/ui/dialog.jsx",
      "sheet": "/app/frontend/src/components/ui/sheet.jsx",
      "drawer": "/app/frontend/src/components/ui/drawer.jsx",
      "command": "/app/frontend/src/components/ui/command.jsx",
      "input": "/app/frontend/src/components/ui/input.jsx",
      "label": "/app/frontend/src/components/ui/label.jsx",
      "button": "/app/frontend/src/components/ui/button.jsx",
      "badge": "/app/frontend/src/components/ui/badge.jsx",
      "tabs": "/app/frontend/src/components/ui/tabs.jsx",
      "table": "/app/frontend/src/components/ui/table.jsx",
      "scroll_area": "/app/frontend/src/components/ui/scroll-area.jsx",
      "separator": "/app/frontend/src/components/ui/separator.jsx",
      "skeleton": "/app/frontend/src/components/ui/skeleton.jsx",
      "tooltip": "/app/frontend/src/components/ui/tooltip.jsx",
      "toggle_group": "/app/frontend/src/components/ui/toggle-group.jsx",
      "select": "/app/frontend/src/components/ui/select.jsx",
      "calendar": "/app/frontend/src/components/ui/calendar.jsx",
      "sonner": "/app/frontend/src/components/ui/sonner.jsx"
    },
    "existing_custom": {
      "KNSelect": "Custom wrapper (existing) — gunakan untuk Select agar konsisten",
      "styles": "/app/frontend/src/styles/*.css"
    }
  },

  "instructions_to_main_agent": {
    "global_rules": [
      "Extend existing CSS classes; jangan bikin theme baru.",
      "Komponen baru harus terasa seperti bagian dari KN: dense, border halus, radius medium, hover translateY(-1px) mengikuti button/card existing.",
      "Gunakan shadcn primitives untuk popover/dialog/sheet/command/tabs/table.",
      "JSX per file <= 500 lines: pecah jadi komponen kecil (SwatchGrid, SwatchCard, FilterChips, CreateColorInlineForm, dll).",
      "Semua state wajib: loading (Skeleton), empty (pesan + CTA), error (Alert + retry).",
      "Semua elemen interaktif & info penting wajib `data-testid` kebab-case."
    ],
    "data_density": [
      "Desktop: gunakan grid/table dengan kolom ringkas; hindari whitespace berlebihan.",
      "Mobile: gunakan Sheet/Drawer bottom untuk picker; grid swatch 6–8 kolom tergantung lebar."
    ]
  },

  "new_components_blueprint": {
    "PantoneFinder": {
      "purpose": "Reusable color picker (Pantone-style swatches) untuk memilih/menambah warna master.",
      "entry_points": [
        "Trigger dari field label (ikon pipet / palet) membuka Popover/Dialog",
        "Inline embed (mis. di halaman Color Library atau form)"
      ],
      "recommended_container": {
        "desktop": "Popover untuk quick pick; Dialog untuk mode 'browse' (lebih besar)",
        "mobile": "Sheet (bottom) untuk browse + search"
      },
      "layout": {
        "header_row": {
          "left": "Judul: 'Pilih Warna' + sublabel kecil (kicker) 'PANTONE/KN'",
          "right": "Button ghost kecil: '+ Buat Warna Baru'"
        },
        "search_and_tools": [
          "Search input (kode/nama) memakai pattern .search-wrap atau Input shadcn dengan icon Search",
          "Family filter chips (horizontal scroll) + System filter (TPX/TCX/KN) sebagai chips atau KNSelect",
          "Cari terdekat by hex: input kecil '#RRGGBB' + tombol 'Cari' + hasil highlight"
        ],
        "body": {
          "swatch_grid": {
            "grid": "CSS grid; gap 8px (var(--sp-2));",
            "columns": {
              "mobile": "grid-cols-6",
              "sm": "grid-cols-8",
              "md": "grid-cols-10",
              "lg": "grid-cols-12"
            },
            "scroll": "Gunakan ScrollArea untuk tinggi tetap (mis. 320–420px) agar header tetap terlihat"
          },
          "footer": "Area ringkas untuk info warna terpilih + tombol 'Pilih' (opsional jika picker butuh confirm)"
        }
      },
      "swatch_card_spec": {
        "size": {
          "chip": "20x20 (preview kecil di field)",
          "grid_item": "min 44x44 tap target; visual chip 28x28 di tengah"
        },
        "content": [
          "Color chip (background = hex)",
          "Kode (mis. 'TCX 19-4052') font 11px semibold",
          "Nama (truncate 1 line) font 11px muted",
          "Tag system kecil (Badge) mis. 'TPX' / 'TCX' / 'KN'",
          "Family (opsional di tooltip/secondary line)"
        ],
        "states": {
          "default": "border 1px var(--solid-line), bg #fff",
          "hover": "border-color rgba(0,122,255,0.35) + shadow ringan (ikuti .interactive-card)",
          "selected": "ring 2px rgba(0,122,255,0.35) + check icon kecil (lucide Check) di pojok",
          "disabled": "opacity 0.45 + cursor not-allowed",
          "nearest_match": "outline dashed 2px rgba(0,122,255,0.35) + label 'Terdekat'"
        },
        "accessibility": [
          "Swatch item = button dengan aria-label 'Pilih warna <kode> <nama>'",
          "Kontras teks: jangan taruh teks di atas chip; teks di bawah chip pada background putih"
        ]
      },
      "quick_create_inline_form": {
        "trigger": "Link/button kecil '+ Buat Warna Baru'",
        "container": "Collapsible di dalam picker (bukan halaman baru) agar cepat",
        "fields": [
          "Kode (required)",
          "Nama (required)",
          "Hex (required) — input '#RRGGBB' + preview chip",
          "Sistem (TPX/TCX/KN) — KNSelect",
          "Family — chips atau KNSelect"
        ],
        "actions": [
          "Simpan (primary-button)",
          "Batal (secondary-button)"
        ],
        "validation": [
          "Hex harus valid 6 digit; tampilkan error text kecil di bawah field",
          "Kode unik: jika conflict, tampilkan Alert (danger)"
        ]
      },
      "loading_empty_error": {
        "loading": "Skeleton grid 24–36 item (kotak 44x44) + skeleton text 2 baris",
        "empty": "Pesan: 'Tidak ada warna yang cocok.' + tombol 'Buat Warna Baru'",
        "error": "Alert (destructive) 'Gagal memuat warna.' + tombol 'Coba lagi'"
      },
      "data_testids": {
        "trigger_button": "pantone-finder-trigger",
        "search_input": "pantone-finder-search-input",
        "family_chip": "pantone-finder-family-chip-<family>",
        "system_filter": "pantone-finder-system-filter",
        "hex_input": "pantone-finder-hex-input",
        "hex_search_button": "pantone-finder-hex-search-button",
        "swatch_item": "pantone-finder-swatch-<color-id>",
        "create_toggle": "pantone-finder-create-toggle",
        "create_submit": "pantone-finder-create-submit",
        "create_cancel": "pantone-finder-create-cancel",
        "state_empty": "pantone-finder-empty-state",
        "state_error": "pantone-finder-error-state"
      }
    },

    "ColorLibraryPage_Tab": {
      "location": "Tab di hub existing: 'Produk & Harga' → tab 'Library Warna'",
      "primary_tasks": ["Cari warna", "Filter family/system/status", "Tambah/Edit/Hapus"],
      "layout": {
        "top": "Gunakan .view-header pattern: judul 'Library Warna' + subtitle ringkas",
        "toolbar": "FilterSortBar (reusable) + tombol 'Tambah Warna' (primary-button)",
        "content": {
          "default": "Swatch grid responsif (lebih visual) + opsi toggle ke Table untuk power users",
          "grid": "Card kecil (solid-card) berisi chip besar + meta",
          "table": "shadcn Table untuk kolom: Chip | Kode | Nama | Hex | Sistem | Family | Status | Aksi"
        }
      },
      "grid_item_spec": {
        "card": "solid-card p-3 flex gap-3 items-start",
        "chip": "w-10 h-10 rounded-md border border-[var(--solid-line)]",
        "meta": "Kode (font 12.5 semibold), Nama (12 muted), row badges untuk system/family, status-pill",
        "actions": "icon-button edit/trash (lucide Pencil/Trash2)"
      },
      "crud_patterns": {
        "create_edit": "Dialog (desktop) / Sheet (mobile) dengan form fields sama seperti quick-create",
        "delete": "AlertDialog konfirmasi: 'Hapus warna ini?' + detail kode/nama",
        "optimistic": "Boleh optimistic update untuk edit; delete harus confirm"
      },
      "states": {
        "loading": "Skeleton grid/table",
        "empty": "Empty state di dalam section-card: 'Belum ada warna.' + CTA 'Tambah Warna'",
        "error": "Alert + retry"
      },
      "data_testids": {
        "tab_trigger": "produk-harga-tab-library-warna",
        "create_button": "color-library-create-button",
        "search_input": "color-library-search-input",
        "view_toggle_grid": "color-library-view-toggle-grid",
        "view_toggle_table": "color-library-view-toggle-table",
        "row_edit": "color-library-edit-<color-id>",
        "row_delete": "color-library-delete-<color-id>",
        "dialog_form": "color-library-form",
        "dialog_submit": "color-library-form-submit"
      }
    },

    "ProductMaster_ColorField_and_StageSelector": {
      "replace_field": "Input free-text 'Warna' diganti PantoneFinder trigger + preview",
      "field_layout": {
        "container": "Form row existing (gunakan .form-row-2col jika cocok)",
        "warna_field": {
          "label": "Warna",
          "control": "Button/trigger bergaya field: border 1px #D6D7DC, radius var(--r-md), bg #fff",
          "content": "Kiri: chip 16–18px + kode; bawah/kanan: nama (muted). Kanan: chevron-down icon",
          "empty": "Placeholder 'Pilih warna…'"
        },
        "tahap_bahan": {
          "label": "Tahap Bahan",
          "options": ["Benang", "Grey", "Finished"],
          "recommended": "ToggleGroup (segmented) untuk desktop; fallback Select untuk mobile sempit",
          "style": "Gunakan ToggleGroup shadcn dengan variant outline; tinggi 32px; font 12.5"
        }
      },
      "interaction": [
        "Klik field Warna membuka PantoneFinder (Popover di desktop, Sheet di mobile)",
        "Setelah pilih: field menampilkan chip + kode + nama; ada icon-button kecil 'X' untuk clear"
      ],
      "data_testids": {
        "warna_trigger": "product-form-warna-trigger",
        "warna_clear": "product-form-warna-clear",
        "tahap_toggle": "product-form-tahap-bahan-toggle",
        "tahap_select": "product-form-tahap-bahan-select"
      }
    },

    "POS_VariantAxisPicker": {
      "purpose": "Pisahkan pemilihan varian menjadi 2 axis: Warna (swatches) + Grade (chips).",
      "containers": {
        "desktop": "Dialog/Popover panel max-w-[560px]",
        "mobile": "Sheet bottom (gunakan /ui/sheet.jsx) dengan header sticky"
      },
      "layout": {
        "header": "Nama produk + ProductAttrChips ringkas (SKU base, motif, gramasi×lebar)",
        "axis_warna": {
          "label": "Warna",
          "control": "Row horizontal scroll swatches (tap target 44px) + nama singkat di tooltip",
          "selected": "ring biru + check"
        },
        "axis_grade": {
          "label": "Grade",
          "control": "Chips (Badge/ToggleGroup) mis. 'A', 'B', 'C'",
          "selected": "bg var(--ios-blue) text white (atau outline + ring)"
        },
        "resolution_panel": {
          "shows": [
            "SKU terpilih",
            "Harga (money-cell/tabular-nums)",
            "Stok tersedia (qty) + status-pill jika low stock"
          ],
          "actions": [
            "Tambah ke Keranjang (primary-button)",
            "Batal (secondary-button)"
          ]
        }
      },
      "logic_notes": [
        "Jika warna dipilih tapi grade belum: tampilkan hint 'Pilih grade untuk melihat SKU'.",
        "Jika kombinasi tidak ada: disable chip/warna yang invalid (atau tampilkan 'Tidak tersedia').",
        "Saat kombinasi valid: fetch stock/price; tampilkan skeleton kecil saat loading."
      ],
      "data_testids": {
        "warna_swatch": "pos-variant-warna-swatch-<color-id>",
        "grade_chip": "pos-variant-grade-chip-<grade>",
        "sku_text": "pos-variant-selected-sku",
        "price_text": "pos-variant-selected-price",
        "stock_text": "pos-variant-selected-stock",
        "add_button": "pos-variant-add-to-cart-button"
      }
    },

    "FilterSortBar": {
      "purpose": "Reusable bar untuk list pages: status/date/entity filters + sort.",
      "base_pattern": "Extend .filter-bar + .field auto-width (lihat layout.css).",
      "layout": {
        "left": [
          "Search (search-wrap)",
          "Status filter (Tabs atau ToggleGroup) jika 3–6 status",
          "Entity filter (KNSelect)"
        ],
        "right": [
          "Date range (Calendar popover) jika diperlukan",
          "Sort (KNSelect) + tombol reset"
        ]
      },
      "responsive": [
        "Mobile: wrap ke 2–3 baris; search full width; filter lain scroll horizontal jika perlu.",
        "Jangan paksa semua field full width; ikuti .filter-bar .field width:auto."
      ],
      "data_testids": {
        "search": "filter-sort-bar-search",
        "status": "filter-sort-bar-status",
        "entity": "filter-sort-bar-entity",
        "date": "filter-sort-bar-date",
        "sort": "filter-sort-bar-sort",
        "reset": "filter-sort-bar-reset"
      }
    },

    "ProductAttrChips": {
      "purpose": "Read-only chips untuk atribut produk pada PO/PR line items & POS header.",
      "visual": "Gunakan Badge shadcn atau .status-pill style kecil; jangan terlalu tinggi.",
      "chips": [
        "SKU (mono/tabular-nums jika numeric)",
        "Grade",
        "Warna (chip kecil + kode)",
        "Motif",
        "Gramasi×Lebar (contoh: '120gsm × 150cm')"
      ],
      "layout": {
        "container": "flex flex-wrap gap-2",
        "warna_chip": "inline-flex items-center gap-2; chip 10–12px rounded-sm border"
      },
      "data_testids": {
        "container": "product-attr-chips",
        "chip": "product-attr-chip-<key>"
      }
    },

    "Partner360_TabbedPanel": {
      "purpose": "Pattern panel detail partner Makloon/Supplier: Profil / Riwayat / Scorecard.",
      "container": "section-card",
      "tabs": {
        "component": "shadcn Tabs",
        "labels": ["Profil", "Riwayat", "Scorecard"],
        "style": "Gunakan tab style existing (tab-bar/tab-button) jika sudah dipakai; jika tidak, Tabs shadcn dengan kelas yang meniru tab-button"
      },
      "content_patterns": {
        "profil": "2-col detail grid (lihat .detail-grid-2col) + status-pill",
        "riwayat": "Table + FilterSortBar mini",
        "scorecard": "Metric cards (reuse .metric-card) + Recharts kecil"
      },
      "states": {
        "loading": "Skeleton untuk header + 2 kolom",
        "empty": "Riwayat kosong: 'Belum ada transaksi.'",
        "error": "Alert + retry"
      },
      "data_testids": {
        "tabs": "partner-360-tabs",
        "tab_profil": "partner-360-tab-profil",
        "tab_riwayat": "partner-360-tab-riwayat",
        "tab_scorecard": "partner-360-tab-scorecard"
      }
    }
  },

  "implementation_notes_tailwind": {
    "swatch_grid_classes": {
      "container": "grid gap-2",
      "responsive": "grid-cols-6 sm:grid-cols-8 md:grid-cols-10 lg:grid-cols-12"
    },
    "swatch_button_classes": {
      "base": "group relative flex flex-col items-center justify-center rounded-[10px] border border-[var(--solid-line)] bg-white p-2 text-left",
      "hover": "hover:border-[rgba(0,122,255,0.35)] hover:shadow-[0_6px_16px_rgba(0,122,255,0.10)]",
      "focus": "focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_rgba(0,122,255,0.35),0_1px_2px_rgba(20,28,45,.05)]",
      "selected": "data-[selected=true]:ring-2 data-[selected=true]:ring-[rgba(0,122,255,0.35)]"
    },
    "color_chip_classes": {
      "chip": "h-7 w-7 rounded-md border border-[var(--solid-line)]",
      "chip_small": "h-4 w-4 rounded-[6px] border border-[var(--solid-line)]"
    },
    "muted_text": "text-[12px] text-[#6B6B73]",
    "kicker": "text-[10.5px] font-bold uppercase tracking-[0.04em] text-[#0058CC]"
  },

  "image_urls": {
    "note": "Tidak perlu gambar eksternal untuk ERP internal; swatch berasal dari data hex. Jika butuh ilustrasi empty-state, gunakan icon lucide-react saja.",
    "categories": []
  },

  "accessibility": {
    "keyboard": [
      "Swatch grid harus bisa dinavigasi via keyboard (tab ke item; enter/space select).",
      "Popover/Dialog/Sheet: fokus masuk ke search input; ESC menutup; fokus kembali ke trigger."
    ],
    "contrast": [
      "Teks tidak boleh diletakkan di atas chip warna (hindari kontras buruk).",
      "Gunakan ring/focus shadow existing (rgba(0,122,255,...))."
    ],
    "touch_targets": [
      "Minimum 44px untuk swatch/grade chip di POS mobile.",
      "Jarak antar chip minimal 8px."
    ]
  },

  "motion_microinteractions": {
    "rules": [
      "Ikuti existing: hover translateY(-1px), active scale(0.97) untuk button.",
      "Untuk swatch: hover border + shadow ringan; selected ring.",
      "Jangan pakai transition: all."
    ],
    "recommended": {
      "swatch_select": "Animate ring/outline via transition-shadow 160ms ease, transition-colors 160ms ease",
      "filter_chips": "Hover background rgba(0,0,0,0.04) atau accent blue soft"
    }
  },

  "General UI UX Design Guidelines": "    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals."
}
