import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const templateRoot = new URL("../", import.meta.url);

async function render(pathname = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${pathname}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the SATISH public synthetic replay", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /SATISH/);
  assert.match(html, /See every recommendation/);
  assert.match(html, /ESA-ADB Mission1 replay/);
  assert.match(html, /ESA Anomaly Detection Benchmark/i);
  assert.match(html, /not affiliated with or endorsed by ESA/i);
  assert.match(html, /Advisory only/i);
  assert.match(html, /No actuation/i);
  assert.match(html, /TRL 4 partial/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Starter Project/i);
});

test("server-renders the separate local live monitor", async () => {
  const response = await render("/live");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /STREAM DISCONNECTED/);
  assert.match(html, /GUIDED DEMO CONTROLS/);
  assert.match(html, /not operational validation/i);
  assert.match(html, /Not probability/);
  assert.match(html, /No command/);
});

test("every rendered stylesheet reference exists in the compiled client", async () => {
  const response = await render();
  const html = await response.text();
  const stylesheets = [...html.matchAll(/href="(\/assets\/[^"?]+\.css)"/g)].map((match) => match[1]);
  assert.ok(stylesheets.length > 0, "expected at least one compiled stylesheet");
  for (const href of stylesheets) {
    const file = new URL(`../dist/client${href}`, import.meta.url);
    const css = await readFile(file, "utf8");
    assert.match(css, /\.live-status|\.hero/);
  }
});

test("removes the disposable starter and keeps public claims bounded", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /no command transmission/i);
  assert.match(page, /ESA Anomaly Detection Benchmark/i);
  assert.match(page, /not affiliated with or endorsed by ESA/i);
  assert.match(page, /not\s+operational validation/i);
  assert.match(layout, /Explainable Space Operations/);
  assert.match(layout, /not affiliated with or endorsed by ESA/i);
  assert.doesNotMatch(page, /_sites-preview|SkeletonPreview/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  await assert.rejects(access(new URL("../app/_sites-preview", templateRoot)));
});
