import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer, request as httpRequest } from "node:http";
import path from "node:path";

const host = process.env.SATISH_GATEWAY_HOST ?? "127.0.0.1";
const port = Number(process.env.SATISH_GATEWAY_PORT ?? "3000");
const rendererPort = Number(process.env.SATISH_RENDERER_PORT ?? "3001");
const livePort = Number(process.env.SATISH_LIVE_PORT ?? "8765");
const token = process.env.SATISH_INTERNAL_TOKEN ?? "";
const clientRoot = path.resolve(process.cwd(), "dist", "client");

if (host !== "127.0.0.1") throw new Error("SATISH local gateway may bind only to 127.0.0.1");
if (token.length < 24) throw new Error("SATISH internal token is missing or too short");
if (!existsSync(clientRoot)) throw new Error(`Compiled client assets were not found at ${clientRoot}`);

const types = new Map([
  [".css", "text/css; charset=utf-8"],
  [".js", "application/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".webp", "image/webp"],
  [".svg", "image/svg+xml"],
  [".ico", "image/x-icon"],
  [".woff2", "font/woff2"],
]);

function sendJson(response, status, payload) {
  const body = Buffer.from(JSON.stringify(payload));
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": String(body.length),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  response.end(body);
}

function serveAsset(request, response, pathname) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return false;
  }
  const target = path.resolve(clientRoot, `.${decoded}`);
  if (!target.startsWith(`${clientRoot}${path.sep}`)) return false;
  if (!existsSync(target) || !statSync(target).isFile()) return false;
  const stat = statSync(target);
  response.writeHead(200, {
    "Content-Type": types.get(path.extname(target).toLowerCase()) ?? "application/octet-stream",
    "Content-Length": String(stat.size),
    "Cache-Control": pathname.startsWith("/assets/")
      ? "public, max-age=31536000, immutable"
      : "public, max-age=3600",
    "X-Content-Type-Options": "nosniff",
  });
  if (request.method === "HEAD") response.end();
  else createReadStream(target).pipe(response);
  return true;
}

function proxy(request, response, targetPort, extraHeaders = {}) {
  const headers = { ...request.headers, ...extraHeaders, host: `127.0.0.1:${targetPort}` };
  const upstream = httpRequest(
    {
      hostname: "127.0.0.1",
      port: targetPort,
      method: request.method,
      path: request.url,
      headers,
    },
    (upstreamResponse) => {
      const responseHeaders = { ...upstreamResponse.headers };
      delete responseHeaders["access-control-allow-origin"];
      response.writeHead(upstreamResponse.statusCode ?? 502, responseHeaders);
      upstreamResponse.pipe(response);
    },
  );
  upstream.on("error", () => {
    if (!response.headersSent) sendJson(response, 502, { error: "local_service_unavailable" });
    else response.destroy();
  });
  request.pipe(upstream);
}

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "127.0.0.1"}`);
  if ((request.method === "GET" || request.method === "HEAD") && serveAsset(request, response, url.pathname)) return;

  if (url.pathname === "/api/v1/live/control-token" && request.method === "GET") {
    sendJson(response, 200, { token });
    return;
  }

  if (url.pathname.startsWith("/api/v1/live/")) {
    if (url.pathname === "/api/v1/live/shutdown") {
      sendJson(response, 404, { error: "not_found" });
      return;
    }
    if (request.method === "POST") {
      const origin = request.headers.origin;
      const localOrigins = new Set(["http://127.0.0.1:3000", "http://localhost:3000"]);
      if (!origin || !localOrigins.has(origin) || request.headers["x-satish-csrf"] !== token) {
        sendJson(response, 403, { error: "control_origin_or_token_rejected" });
        return;
      }
    }
    proxy(request, response, livePort, { authorization: `Bearer ${token}` });
    return;
  }

  proxy(request, response, rendererPort, {
    "x-forwarded-host": request.headers.host ?? "127.0.0.1:3000",
    "x-forwarded-proto": "http",
  });
});

server.listen(port, host, () => {
  process.stdout.write(`SATISH local gateway running at http://${host}:${port}\n`);
});
