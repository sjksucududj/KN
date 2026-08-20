# KN_08 — UI/UX STANDARDS
## Kain Nusantara Platform — Design System & User Experience Guidelines

**Versi:** 1.0 | **Berlaku sejak:** 2026-05-23

---

## 🎨 DESIGN PHILOSOPHY

### Core Principles
1. **Function Over Form** — Beauty serves usability, not the reverse
2. **Progressive Disclosure** — Show what's needed now, hide complexity until required
3. **Consistent Mental Models** — Same patterns for same actions across the app
4. **Feedback Loop** — Every action gets immediate, clear feedback
5. **Error Prevention > Error Handling** — Design to prevent mistakes

### Target Persona UX Goals
| Persona | Primary Goal | UX Priority |
|---|---|---|
| **Warehouse Operator** | Complete tasks fast without errors | Speed + Clarity |
| **Sales** | Create orders quickly from visual catalog | Visuals + Search |
| **Manager** | Get insights at-a-glance | Data Density + Charts |
| **Admin** | Manage master data efficiently | Bulk Actions + Filters |

---

## 🎨 DESIGN SYSTEM

### Color Palette

#### Brand Colors
```css
--primary: hsl(222, 47%, 11%);        /* Dark Navy (Main Brand) */
--primary-foreground: hsl(210, 40%, 98%);
--secondary: hsl(210, 40%, 96.1%);    /* Light Gray */
--secondary-foreground: hsl(222, 47%, 11%);
```

#### Semantic Colors
```css
--success: hsl(142, 76%, 36%);        /* Green for positive actions */
--warning: hsl(38, 92%, 50%);         /* Amber for caution */
--destructive: hsl(0, 84%, 60%);      /* Red for destructive actions */
--info: hsl(199, 89%, 48%);           /* Blue for informational */
```

#### Contextual UI
```css
--background: hsl(0, 0%, 100%);       /* Page background */
--foreground: hsl(222, 47%, 11%);     /* Main text */
--card: hsl(0, 0%, 100%);             /* Card background */
--card-foreground: hsl(222, 47%, 11%);
--muted: hsl(210, 40%, 96.1%);        /* Subtle background */
--muted-foreground: hsl(215, 16%, 47%); /* Secondary text */
--border: hsl(214, 32%, 91%);         /* Border default */
--input: hsl(214, 32%, 91%);          /* Input border */
--ring: hsl(222, 47%, 11%);           /* Focus ring */
```

### Typography

#### Font Stack
```css
--font-sans: "Inter", system-ui, -apple-system, sans-serif;
--font-mono: "JetBrains Mono", "Fira Code", monospace;
```

#### Type Scale
```css
/* Headings */
h1: 2rem (32px), font-weight: 700, line-height: 1.2
h2: 1.5rem (24px), font-weight: 600, line-height: 1.3
h3: 1.25rem (20px), font-weight: 600, line-height: 1.4
h4: 1.125rem (18px), font-weight: 600, line-height: 1.4

/* Body */
p: 0.875rem (14px), font-weight: 400, line-height: 1.5
small: 0.75rem (12px), font-weight: 400, line-height: 1.4
```

### Spacing Scale
```css
--spacing-0: 0px
--spacing-1: 4px
--spacing-2: 8px
--spacing-3: 12px
--spacing-4: 16px
--spacing-5: 20px
--spacing-6: 24px
--spacing-8: 32px
--spacing-10: 40px
--spacing-12: 48px
--spacing-16: 64px
--spacing-20: 80px
```

### Border Radius
```css
--radius-none: 0px
--radius-sm: 0.125rem (2px)   /* Subtle elements */
--radius: 0.375rem (6px)       /* Default (buttons, inputs) */
--radius-md: 0.5rem (8px)      /* Cards */
--radius-lg: 0.75rem (12px)    /* Modals */
--radius-xl: 1rem (16px)       /* Large containers */
--radius-full: 9999px          /* Pills, avatars */
```

### Shadows
```css
--shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05)
--shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1)
--shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1)
--shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)
--shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)
```

---

## 📐 LAYOUT PATTERNS

### Page Structure
```
┌─────────────────────────────────────────────────────────┐
│ Header (fixed, 64px)                                    │
│ [Logo] [Warehouse Selector] [Search]  [User Menu] [Help]│
├──────┬──────────────────────────────────────────────────┤
│      │                                                  │
│  S   │  Main Content Area                               │
│  i   │  (Scrollable, max-width: 1440px, centered)      │
│  d   │                                                  │
│  e   │  [Page Header: Title + Actions]                 │
│  b   │  [Content Panels / Cards]                       │
│  a   │  [Data Tables / Lists]                          │
│  r   │  [Forms / Details]                              │
│      │                                                  │
│ 240px│                                                  │
│      │                                                  │
└──────┴──────────────────────────────────────────────────┘
```

### Card Anatomy
```
┌─────────────────────────────────────────┐
│ Card Header (optional)                  │
│ [Title]                      [Actions]  │
├─────────────────────────────────────────┤
│                                         │
│ Card Content                            │
│ (padding: 24px)                         │
│                                         │
│ [Content Body]                          │
│                                         │
├─────────────────────────────────────────┤
│ Card Footer (optional)                  │
│ [Secondary Actions]                     │
└─────────────────────────────────────────┘
```

### 2-Panel Layout (WMS Tasks)
```
┌────────────────┬─────────────────────────┐
│                │                         │
│  Task List     │  Action Panel           │
│  (Left 40%)    │  (Right 60%)            │
│                │                         │
│  [Filters]     │  [Active Task Info]     │
│  [Tasks...]    │  [Scanner/Input]        │
│  [Tasks...]    │  [Scanned Items]        │
│                │  [Complete Button]      │
│                │                         │
└────────────────┴─────────────────────────┘
```

---

## 🧩 COMPONENT STANDARDS

### Shadcn/UI Component Library
**WAJIB:** Use Shadcn/UI components dari `/app/frontend/src/components/ui/` untuk consistency.

#### Available Components
```
accordion, alert, alert-dialog, aspect-ratio, avatar, badge, 
breadcrumb, button, calendar, card, carousel, checkbox, 
collapsible, command, context-menu, dialog, drawer, 
dropdown-menu, form, hover-card, input, input-otp, label, 
menubar, navigation-menu, pagination, popover, progress, 
radio-group, resizable, scroll-area, select, separator, 
sheet, skeleton, slider, sonner (toast), switch, table, 
tabs, textarea, toaster, toggle, toggle-group, tooltip
```

### Button Variants
```jsx
<Button variant="default">Primary Action</Button>
<Button variant="secondary">Secondary Action</Button>
<Button variant="outline">Tertiary Action</Button>
<Button variant="ghost">Subtle Action</Button>
<Button variant="destructive">Delete / Cancel</Button>
<Button variant="link">Text Link</Button>

// Sizes
<Button size="sm">Small</Button>
<Button size="default">Default</Button>
<Button size="lg">Large</Button>
<Button size="icon">Icon Only</Button>
```

### Status Badge Semantics
```jsx
<Badge variant="default">Neutral</Badge>
<Badge variant="secondary">Informational</Badge>
<Badge variant="success">Success / Active</Badge>
<Badge variant="warning">Warning / Pending</Badge>
<Badge variant="destructive">Error / Cancelled</Badge>
```

### Form Input Pattern
```jsx
<div className="space-y-2">
  <Label htmlFor="sku">SKU</Label>
  <Input 
    id="sku" 
    data-testid="product-sku-input"
    placeholder="Contoh: BTK-MEGA-001"
    required
  />
  <p className="text-sm text-muted-foreground">
    Kode unik produk (3-20 karakter)
  </p>
</div>
```

---

## 🎯 INTERACTION PATTERNS

### Loading States

#### Skeleton Loader (Preferred untuk data fetch)
```jsx
import { Skeleton } from '@/components/ui/skeleton';

{isLoading && (
  <div className="space-y-3">
    <Skeleton className="h-12 w-full" />
    <Skeleton className="h-12 w-full" />
    <Skeleton className="h-12 w-full" />
  </div>
)}
```

#### Spinner (For button actions only)
```jsx
<Button disabled={isPending}>
  {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
  {isPending ? 'Processing...' : 'Submit'}
</Button>
```

### Empty States

**WAJIB:** Setiap list/table harus punya empty state dengan:
1. Icon (relevant)
2. Title (deskriptif)
3. Description (helpful)
4. Primary action (jika applicable)

```jsx
{data.length === 0 && (
  <div className="flex flex-col items-center justify-center h-96 text-center">
    <Package className="h-16 w-16 text-muted-foreground mb-4" />
    <h3 className="text-lg font-semibold">Belum ada produk</h3>
    <p className="text-sm text-muted-foreground mt-1 mb-4">
      Mulai dengan menambahkan produk pertama Anda
    </p>
    <Button onClick={openCreateForm}>
      <Plus className="mr-2 h-4 w-4" />
      Tambah Produk
    </Button>
  </div>
)}
```

### Error States
```jsx
{error && (
  <Alert variant="destructive">
    <AlertCircle className="h-4 w-4" />
    <AlertTitle>Gagal memuat data</AlertTitle>
    <AlertDescription>
      {error.message || 'Terjadi kesalahan. Silakan coba lagi.'}
      <Button 
        variant="outline" 
        size="sm" 
        onClick={retry}
        className="ml-4"
      >
        Coba Lagi
      </Button>
    </AlertDescription>
  </Alert>
)}
```

### Toast Notifications (Sonner)
```jsx
import { toast } from 'sonner';

// Success
toast.success('Data berhasil disimpan');

// Error
toast.error('Gagal menyimpan data', {
  description: error.message,
});

// Loading → Success pattern
const promise = saveData();
toast.promise(promise, {
  loading: 'Menyimpan...',
  success: 'Berhasil disimpan',
  error: 'Gagal menyimpan',
});
```

---

## ♿ ACCESSIBILITY (A11Y)

### WCAG 2.1 Level AA Compliance

#### Contrast Ratios
- **Normal text (14px-18px):** Minimum 4.5:1
- **Large text (18px+ or 14px+ bold):** Minimum 3:1
- **Interactive elements:** Minimum 3:1 against background

#### Keyboard Navigation
**WAJIB:** Setiap interactive element harus keyboard-accessible:
```jsx
<button
  onClick={handleClick}
  onKeyDown={(e) => e.key === 'Enter' && handleClick()}
  tabIndex={0}
  aria-label="Close dialog"
>
  <X className="h-4 w-4" />
</button>
```

#### Focus Indicators
**NEVER** remove focus outline dengan `outline: none` tanpa alternative.
```css
/* ❌ BAD */
button:focus {
  outline: none;
}

/* ✅ GOOD */
button:focus-visible {
  outline: 2px solid hsl(var(--ring));
  outline-offset: 2px;
}
```

#### ARIA Labels
```jsx
// For icon-only buttons
<Button variant="ghost" size="icon" aria-label="Settings">
  <Settings className="h-4 w-4" />
</Button>

// For form inputs
<Input 
  id="email" 
  type="email"
  aria-required="true"
  aria-invalid={hasError}
  aria-describedby="email-error"
/>
{hasError && (
  <p id="email-error" className="text-sm text-destructive">
    Email tidak valid
  </p>
)}
```

---

## 📱 RESPONSIVE DESIGN

### Breakpoints (TailwindCSS)
```css
/* Mobile-first approach */
sm: 640px   /* Tablet portrait */
md: 768px   /* Tablet landscape */
lg: 1024px  /* Desktop */
xl: 1280px  /* Large desktop */
2xl: 1536px /* Extra large */
```

### Mobile Adaptations
**Warehouse Operators** often use tablets/handhelds:
- Touch target minimum: 44x44px
- Larger font sizes for scanning UI (16px+)
- Simplified navigation (bottom tab bar on mobile)
- Camera-first scanner (default to camera, not input)

### Desktop Optimizations
**Managers & Admins** primarily use desktop:
- Data-dense tables (more columns visible)
- Hover states untuk tooltips
- Keyboard shortcuts visible hints
- Multi-panel layouts (side-by-side)

---

## 🎬 ANIMATION & MOTION

### Motion Principles
1. **Purposeful** — Animate to guide attention, not for decoration
2. **Fast** — Durations 150-250ms for UI feedback
3. **Natural** — Ease-in-out untuk smooth transitions
4. **Consistent** — Same duration/easing for same type of animation

### Animation Guidelines
```css
/* ✅ GOOD: Specific properties */
transition: transform 200ms ease-in-out, opacity 200ms ease-in-out;

/* ❌ BAD: Transition all (performance issue) */
transition: all 200ms;
```

### Common Animations
```jsx
// Fade in
<div className="animate-in fade-in duration-200">...</div>

// Slide in from bottom
<div className="animate-in slide-in-from-bottom-4 duration-300">...</div>

// Scale up (for modals)
<Dialog>
  <DialogContent className="animate-in zoom-in-95 duration-200">
    ...
  </DialogContent>
</Dialog>
```

---

## 🚨 ANTI-PATTERNS (NEVER DO THIS)

### ❌ 1. Centered Text for Body Content
```jsx
/* ❌ BAD */
<div className="text-center">
  <p>Long paragraph of body text that is hard to read...</p>
</div>

/* ✅ GOOD */
<div className="text-left max-w-prose">
  <p>Readable paragraph aligned left...</p>
</div>
```

### ❌ 2. Generic Empty States
```jsx
/* ❌ BAD */
{data.length === 0 && <p>No data</p>}

/* ✅ GOOD */
{data.length === 0 && (
  <EmptyState 
    icon={Package}
    title="Belum ada produk"
    description="Tambahkan produk pertama untuk mulai"
    action={<Button>Tambah Produk</Button>}
  />
)}
```

### ❌ 3. Invisible Buttons (No Visual Affordance)
```jsx
/* ❌ BAD */
<div onClick={handleClick} className="cursor-pointer">
  Click me (looks like text)
</div>

/* ✅ GOOD */
<Button onClick={handleClick}>
  Click me
</Button>
```

### ❌ 4. Modal on Modal
```jsx
/* ❌ BAD */
<Dialog open={modal1}>
  <Dialog open={modal2}>  {/* Nested modal */}
    ...
  </Dialog>
</Dialog>

/* ✅ GOOD */
<Dialog open={modal1} onOpenChange={closeModal1}>
  ...
  <Button onClick={() => { closeModal1(); openModal2(); }}>
    Next Step
  </Button>
</Dialog>
```

### ❌ 5. Excessive Animations
```jsx
/* ❌ BAD: Every element animates */
<div className="animate-bounce">
  <div className="animate-pulse">
    <div className="animate-spin">...</div>
  </div>
</div>

/* ✅ GOOD: Subtle, purposeful */
<Card className="hover:shadow-md transition-shadow">
  ...
</Card>
```

---

## ✅ QUALITY CHECKLIST (Per Component)

Before marking component as "DONE":

- [ ] Uses Shadcn/UI components (no custom reinvention)
- [ ] Has loading state (skeleton/spinner)
- [ ] Has empty state (icon + title + description + action)
- [ ] Has error state (with retry action)
- [ ] All interactive elements have `data-testid`
- [ ] All buttons have clear labels (not just icons without aria-label)
- [ ] Forms have proper validation feedback
- [ ] Color contrast meets WCAG AA (4.5:1 for text)
- [ ] Keyboard navigable (tab order makes sense)
- [ ] Focus indicators visible
- [ ] Responsive (tested on mobile + desktop)
- [ ] No console.log left in code

---

**Last Updated:** 23 Mei 2026  
**Maintained by:** Design + Development Team  
**Review Cycle:** Quarterly
