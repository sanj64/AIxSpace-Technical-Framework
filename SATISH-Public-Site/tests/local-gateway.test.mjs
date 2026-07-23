import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "node:http";
import { spawn } from "node:child_process";

const TOKEN = "test-internal-token-abcdef0123456789"; // >= 24 chars, required by the gateway

function listen(handler) {
  const server = createServer(handler);
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

async function freePort() {
  const server = await listen(() => {});
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function startGateway(env) {
  const child = spawn(process.execPath, ["scripts/local-gateway.mjs"], {
    env: { ...process.env, ...env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stderr = "";
  child.stderr.on("data", (chunk) => (stderr += String(chunk)));
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`gateway did not start: ${stderr}`)), 8000);
    child.stdout.on("data", (chunk) => {
      if (String(chunk).includes("gateway running")) {
        clearTimeout(timer);
        resolve();
      }
    });
    child.on("exit", (code) => reject(new Error(`gateway exited early (${code}): ${stderr}`)));
  });
  return child;
}

test("local gateway enforces the browser-facing security boundary", async () => {
  let sawAuth = "";
  const live = await listen((request, response) => {
    sawAuth = request.headers.authorization ?? "";
    response.setHeader("access-control-allow-origin", "*"); // upstream ACAO the gateway must strip
    if (request.headers.authorization !== `Bearer ${TOKEN}`) {
      response.writeHead(401);
      response.end(JSON.stringify({ error: "unauthorized" }));
      return;
    }
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ ok: true, path: request.url }));
  });
  const renderer = await listen((request, response) => {
    response.writeHead(200, { "content-type": "text/html" });
    response.end("RENDERER");
  });

  const gatewayPort = await freePort();
  const base = `http://127.0.0.1:${gatewayPort}`;
  const child = await startGateway({
    SATISH_GATEWAY_HOST: "127.0.0.1",
    SATISH_GATEWAY_PORT: String(gatewayPort),
    SATISH_RENDERER_PORT: String(renderer.address().port),
    SATISH_LIVE_PORT: String(live.address().port),
    SATISH_INTERNAL_TOKEN: TOKEN,
  });

  try {
    // Cross-origin control POST is rejected even with a valid token.
    const badOrigin = await fetch(`${base}/api/v1/live/control`, {
      method: "POST",
      headers: { origin: "http://evil.example", "x-satish-csrf": TOKEN },
    });
    assert.equal(badOrigin.status, 403);

    // Same-origin control POST with the wrong CSRF token is rejected.
    const badToken = await fetch(`${base}/api/v1/live/control`, {
      method: "POST",
      headers: { origin: "http://127.0.0.1:3000", "x-satish-csrf": "wrong" },
    });
    assert.equal(badToken.status, 403);

    // Same-origin control POST with the correct token is proxied to the live engine.
    const okControl = await fetch(`${base}/api/v1/live/control`, {
      method: "POST",
      headers: { origin: "http://127.0.0.1:3000", "x-satish-csrf": TOKEN },
    });
    assert.equal(okControl.status, 200);
    assert.equal(okControl.headers.get("access-control-allow-origin"), null); // ACAO stripped

    // The shutdown endpoint is blocked by the gateway regardless of credentials.
    const shutdown = await fetch(`${base}/api/v1/live/shutdown`, { method: "POST" });
    assert.equal(shutdown.status, 404);

    // The control token is vended to local callers.
    const tokenResponse = await fetch(`${base}/api/v1/live/control-token`);
    assert.equal(tokenResponse.status, 200);
    assert.deepEqual(await tokenResponse.json(), { token: TOKEN });

    // GET reads are proxied with the injected bearer and ACAO stripped.
    const snapshot = await fetch(`${base}/api/v1/live/snapshot`);
    assert.equal(snapshot.status, 200);
    assert.equal(snapshot.headers.get("access-control-allow-origin"), null);
    assert.equal(sawAuth, `Bearer ${TOKEN}`);

    // Non-API GETs fall through to the renderer.
    const page = await fetch(`${base}/`);
    assert.equal(await page.text(), "RENDERER");
  } finally {
    child.kill();
    await Promise.all([
      new Promise((resolve) => live.close(resolve)),
      new Promise((resolve) => renderer.close(resolve)),
    ]);
  }
});
