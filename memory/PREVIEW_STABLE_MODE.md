# PREVIEW STABLE MODE — READ FIRST (infra constraint)

> This container is capped at **1 CPU core / 2 GB RAM** and the frontend has 500+
> source files. Running the CRA/craco **dev server** (`craco start` / `yarn start:dev`)
> compiles for ~5 minutes at 100% CPU, which makes the platform health-probe fail and
> restarts the pod in a loop (preview never loads). **Do NOT run the dev server.**

## How the preview is served
The frontend is served as a **PREBUILT STATIC BUNDLE**:

- `supervisor` runs `yarn start` → **`node static_server.js`** (serves `frontend/build/`, instant, dependency-free).
- After **ANY** change under `frontend/src`, run:
  ```bash
  bash /app/scripts/rebuild_frontend.sh
  ```
  This runs `yarn build` at low priority (nice/ionice), then reloads the static server.
  **There is NO hot reload for the frontend.**
- `static_server.js` reads files from disk on every request, so once the build finishes
  the new assets are served immediately.

## Backend
- Backend hot-reloads normally (`uvicorn --reload`); **no rebuild needed** for backend changes.
- Auth uses **session tokens + bcrypt** (256-bit token + TTL + HttpOnly cookie, Bearer fallback).
  There is **no JWT_SECRET** in this codebase — do not add one expecting it to be required.

## Env / rules
- Never edit `frontend/.env:REACT_APP_BACKEND_URL` or `backend/.env:MONGO_URL`.
- `backend/.env` also carries `REACT_APP_BACKEND_URL` (used to build public PDF/verify links).
- Use `yarn` (never `npm`). Manage services with `supervisorctl` (never run servers manually).

## Quick commands
```bash
supervisorctl status
bash /app/scripts/rebuild_frontend.sh                 # rebuild FE bundle after src changes
tail -n 60 /var/log/supervisor/frontend.*.log         # static_server logs
tail -n 80 /var/log/supervisor/backend.*.log          # backend logs
tail -f /tmp/frontend_build.log                        # live build progress
cd /app/backend && esbuild ../frontend/src --loader:.js=jsx --bundle --outfile=/dev/null  # FE compile sanity
```

## Credentials (seeded, idempotent — verify with `/api/auth/login`)
The committed repo seeds **Kain Nusantara** demo users:
| Role | Email | Password |
|---|---|---|
| admin | admin@kainnusantara.id | demo12345 |
| sales | sales@kainnusantara.id | demo12345 |
| manager | manager@kainnusantara.id | demo12345 |
| warehouse | warehouse@kainnusantara.id | demo12345 |

> NOTE: an earlier (uncommitted) container mentioned `admin@garment.com / Admin@123`
> and `{hr,finance,spv,gudang,maklon}@dewiaditya.id / Dewi@123`. Those are **not** in the
> committed bootstrap; the working credentials are the kainnusantara.id set above.
