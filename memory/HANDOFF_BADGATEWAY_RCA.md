# HANDOFF — RCA "Bad Gateway" (502) & Rencana Perbaikan

> **Status:** DIAGNOSA SELESAI · PERBAIKAN BELUM DITERAPKAN (sengaja diserahkan ke agent berikutnya sesuai permintaan owner).
> **Tanggal:** 2026-07-05 · **Konteks:** Kain Nusantara ERP (React CRACO dev server + FastAPI `uvicorn --reload` + MongoDB + MCP servers) dalam SATU container ber-limit **2 GiB**.
> **Kesimpulan singkat:** Ini **BUKAN bug logika aplikasi**. Ini **tekanan memori (OOM) terhadap limit cgroup 2 GiB** yang membuat container di-recycle → transport tool & preview URL sesaat mengembalikan **502 Bad Gateway**. Deploy produksi (build statis via nginx) **tidak** akan mengalami ini karena dev server 628 MB tidak berjalan.

---

## 1. GEJALA YANG TERAMATI
- Error berulang saat memanggil tool: `calling "initialize": rejected by transport: sending "initialize": Bad Gateway` (muncul di tool `execute_bash` **dan** `screenshot`).
- Setiap kali error muncul, **SEMUA service supervisor restart bersamaan** — `supervisorctl status` menunjukkan `uptime` reset ke ~6–15 detik (backend, frontend, mongodb, nginx semua uptime sama).
- Klaster error terjadi **di sekitar pemanggilan tool `screenshot`** (yang menjalankan headless Chromium) dan saat **edit file beruntun** (memicu recompile webpack berulang).
- Tidak ada stack trace aplikasi; service hanya restart.

## 2. BUKTI TERKUMPUL (angka nyata)
| Metrik | Nilai | Catatan |
|---|---|---|
| `cgroup memory.max` | **2 GiB** (2147483648) | Limit container (cgroup v2). |
| `memory.current` | ~1.65–1.78 GiB | **~80–88%** saat near-idle. |
| `memory.peak` | **1.80 GiB (1938104320)** | **90% limit** — sangat mepet. |
| `swap` | **0 B** | Tidak ada bantalan; spike langsung OOM. |
| `memory.events oom_kill` | 0 (SEKARANG) | Counter **reset** tiap cgroup dibuat ulang (pod restart), jadi 0 tidak menyanggah OOM sebelumnya. |
| Restart container hari ini | **5x** (dari log supervisor) | Semua service restart bareng = pod recycle. |

**Top proses berdasarkan RSS:**
| Proses | RSS | Peran |
|---|---|---|
| `craco/webpack start` (node pid 83) | **628 MB** | **Dev server frontend — konsumen terbesar** |
| `mongod` | 173 MB | Database |
| `mongodb-mcp-server` (node) | 103 MB | Tool MCP (dev only) |
| plugins agent `uvicorn` | 101 MB | Tool MCP (dev only) |
| python (backend worker) | 103 MB | Backend |
| `yarn start` (node) | 73 MB | Wrapper dev server |
| `craco` (node pid 75) | 42 MB | Dev server child |
| backend `uvicorn --reload` | 27 MB | + reload watcher |

**Konfigurasi relevan:**
- Frontend dijalankan `yarn start` (CRACO **dev server**, BUKAN build statis). `GENERATE_SOURCEMAP` tidak di-set → source map digenerate (boros memori). `node_modules` ~1.1 GB, ~5.055 file source-map.
- Backend `uvicorn server:app --workers 1 --reload` → watcher reload + memori ekstra saat file berubah.
- Backend `server.py` meng-import **76 router secara eager** saat startup (import graph besar).
- `bootstrap.py` memuat dataset besar ke memori saat seed: beberapa `.to_list(2000)` (products/PO) dan `.to_list(5000)` (AR receipts).
- Tidak ada `--max-old-space-size` pada proses Node; tidak ada memory monitor (memmon/superlance).

## 3. ROOT CAUSE (keyakinan tinggi)
Baseline memori container ~1.5–1.8 GiB (dev server 628 MB + Mongo + MCP + backend) menyisakan **< 0.4 GiB headroom** terhadap limit 2 GiB, **tanpa swap**. Spike sementara mendorong melewati 2 GiB → **cgroup OOM-kill / pod eviction**. Dua pemicu spike utama:
1. **Playwright/Chromium** yang dijalankan tool `screenshot` (spike 300–800 MB per pemanggilan).
2. **Recompile webpack** akibat edit file beruntun (generasi source-map + parsing AST melonjak).

Saat pod di-recycle: (a) **proxy transport MCP → 502 Bad Gateway**, dan (b) **semua service supervisor restart** (uptime reset). Kontributor tingkat aplikasi (bukan penyebab utama, tapi menaikkan baseline): bootstrap memuat dataset besar ke memori + 76 router di-import eager.

## 4. MENGAPA INI BUKAN BUG APLIKASI
- Tidak ada error logika/endpoint; semua 12 guardrail gate HIJAU; data-integrity 124/0/0.
- Penyebabnya murni **resource management dev/preview**. Di **produksi** frontend disajikan sebagai **build statis oleh nginx** (bukan dev server 628 MB), sehingga baseline turun drastis dan masalah ini hilang.
- Tool platform (screenshot/Chromium, MCP servers) tidak berjalan di produksi.

## 5. RENCANA AKSI UNTUK AGENT BERIKUTNYA (prioritas)

### A. Quick Win Dev-Time (hemat ~200–300 MB, risiko rendah)
1. Tambah ke `/app/frontend/.env` (JANGAN ubah/rewrite baris `REACT_APP_BACKEND_URL`, hanya **append**):
   ```
   GENERATE_SOURCEMAP=false
   ```
   Lalu `sudo supervisorctl restart frontend` dan pantau `memory.current`.
2. Batasi heap Node dev server via supervisor `[program:frontend]` environment:
   ```
   NODE_OPTIONS="--max-old-space-size=512"
   ```
   (Hati-hati: bila terlalu kecil, dev server bisa OOM sendiri; 512 aman untuk app ini.)
3. Hindari memanggil tool `screenshot` (Playwright) berkali-kali beruntun; jalankan sekali, alur pendek. Ini pemicu spike terbesar.

### B. Optimasi Aplikasi (medium)
4. `bootstrap.py`: ganti `.to_list(N besar)` dengan iterasi cursor `async for ...` + proyeksi field minimal, agar tidak menahan ribuan dokumen di memori saat startup/seed.
5. Pertimbangkan lazy-load / pengelompokan router di `server.py` (core vs opsional) untuk memangkas import graph startup.
6. (Opsional) Tambah log memori di lifespan startup (`psutil` RSS) untuk observabilitas.

### C. Deploy-Time / Platform (paling menentukan)
7. **Produksi WAJIB pakai build statis**: `cd /app/frontend && yarn build` lalu serve via nginx (≈5–10 MB vs 628 MB). Ini menghilangkan penyebab utama.
8. Nonaktifkan `--reload` uvicorn di lingkungan mirip-produksi (hemat watcher + memori):
   `command=/root/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1`
9. Bila tetap butuh dev tooling berat (hot-reload + source-map + MCP), minta **naikkan limit memori preview ke 3–4 GiB**.

## 6. VERIFIKASI (setelah perbaikan diterapkan)
```bash
# Pantau baseline & puncak
watch -n 5 'cat /sys/fs/cgroup/memory.current; cat /sys/fs/cgroup/memory.peak'
# Target: baseline < 1.5 GiB, di bawah beban < 1.8 GiB, tidak ada restart bersamaan.
```
- Konfirmasi `supervisorctl status` menunjukkan uptime **stabil** (tidak reset) selama sesi kerja normal + 1x pemanggilan screenshot.
- **WAJIB:** setelah menerapkan perbaikan apa pun (mis. flag .env / config supervisor / optimasi bootstrap), panggil **testing_agent** untuk regresi guardrail + alur inti (login/POS/checkout/inventory) memastikan tidak ada yang rusak. Jangan tandai "fixed" hanya dari inspeksi manual.

## 7. RAMBU-RAMBU (JANGAN dilanggar)
- **JANGAN** ubah `REACT_APP_BACKEND_URL` (frontend/.env) atau `MONGO_URL`/`DB_NAME` (backend/.env). Hanya **append** flag baru bila perlu.
- Setelah ubah `.env` atau config supervisor → **restart via supervisor** (`sudo supervisorctl restart <svc>`), jangan jalankan uvicorn/yarn manual.
- Perubahan config supervisor (`/etc/supervisor/conf.d/*.conf`) perlu `supervisorctl reread && supervisorctl update`.
- Semua 12 guardrail gate saat ini HIJAU; jangan sampai optimasi memori menurunkan gate. Jalankan `bash scripts/gate.sh` sesudahnya.

## 8. LAMPIRAN — perintah diagnosa cepat
```bash
cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events            # oom_kill counter (reset tiap restart)
ps -eo rss,pid,args --sort=-rss | head -15  # proses paling boros memori
sudo supervisorctl status                   # cek uptime (reset = restart)
```
