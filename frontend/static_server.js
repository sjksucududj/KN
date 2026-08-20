/**
 * static_server.js — Stable preview server for the prebuilt CRA bundle.
 *
 * WHY: This container is capped at 1 CPU / 2GB RAM and the frontend has 500+
 * source files. Running the CRA/craco dev server (`craco start`) pins the CPU at
 * 100% for ~5 minutes while it compiles, which makes the platform health-probe
 * fail and the pod restarts in a loop (preview never loads).
 *
 * Instead, supervisor runs `yarn start` === `node static_server.js`, which serves
 * the already-built static bundle in `build/` instantly. Files are read from disk
 * on every request, so after a rebuild (`yarn build`) new assets are served with
 * no restart required.
 *
 * Dependency-free (pure Node http + fs) so it can never fail to boot.
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

const HOST = process.env.HOST || "0.0.0.0";
const PORT = parseInt(process.env.PORT || "3000", 10);
const BUILD_DIR = path.join(__dirname, "build");
const INDEX = path.join(BUILD_DIR, "index.html");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".eot": "application/vnd.ms-fontobject",
  ".txt": "text/plain; charset=utf-8",
  ".webmanifest": "application/manifest+json",
};

function safeJoin(root, reqPath) {
  const decoded = decodeURIComponent(reqPath.split("?")[0].split("#")[0]);
  const resolved = path.normalize(path.join(root, decoded));
  if (!resolved.startsWith(root)) return null; // path traversal guard
  return resolved;
}

function sendFile(res, filePath, statusCode = 200) {
  const ext = path.extname(filePath).toLowerCase();
  const type = MIME[ext] || "application/octet-stream";
  const stream = fs.createReadStream(filePath);
  stream.on("open", () => {
    const headers = { "Content-Type": type };
    // Long cache for hashed static assets; no-cache for html/service worker.
    if (filePath.includes(`${path.sep}static${path.sep}`)) {
      headers["Cache-Control"] = "public, max-age=31536000, immutable";
    } else {
      headers["Cache-Control"] = "no-cache";
    }
    res.writeHead(statusCode, headers);
  });
  stream.on("error", () => {
    res.writeHead(500, { "Content-Type": "text/plain" });
    res.end("Internal Server Error");
  });
  stream.pipe(res);
}

const server = http.createServer((req, res) => {
  // Lightweight health endpoint (platform probe hits `/` too, which is fine).
  if (req.url === "/healthz" || req.url === "/health") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("ok");
    return;
  }

  if (!fs.existsSync(INDEX)) {
    res.writeHead(503, { "Content-Type": "text/html; charset=utf-8" });
    res.end(
      "<h1>Build not ready</h1><p>The static bundle has not been built yet. " +
        "Run <code>bash /app/scripts/rebuild_frontend.sh</code>.</p>"
    );
    return;
  }

  const target = safeJoin(BUILD_DIR, req.url || "/");
  if (!target) {
    res.writeHead(400, { "Content-Type": "text/plain" });
    res.end("Bad Request");
    return;
  }

  fs.stat(target, (err, stat) => {
    if (!err && stat.isFile()) {
      sendFile(res, target);
      return;
    }
    // SPA fallback → index.html (client-side routing)
    sendFile(res, INDEX, 200);
  });
});

server.listen(PORT, HOST, () => {
  console.log(`[static_server] serving ${BUILD_DIR} at http://${HOST}:${PORT}`);
  if (!fs.existsSync(INDEX)) {
    console.warn("[static_server] WARNING: build/index.html missing — run rebuild_frontend.sh");
  }
});
