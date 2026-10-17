// Render an HTML file to PDF via the CDP browser, honouring the dark theme.
// usage: node print.mjs <input.html> <output.pdf>
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const DEBUG = "http://127.0.0.1:9222";
const [input, output] = process.argv.slice(2);
if (!input || !output) { console.error("usage: node print.mjs in.html out.pdf"); process.exit(2); }

const url = pathToFileURL(input).href;

// open a fresh target
const created = await (await fetch(`${DEBUG}/json/new?${encodeURIComponent(url)}`, { method: "PUT" })).json();
const target = created.webSocketDebuggerUrl || created.targetId;
if (!target) { console.error("could not create target", created); process.exit(1); }

const ws = new WebSocket(target);
await new Promise((ok, err) => { ws.onopen = ok; ws.onerror = () => err(new Error("ws connect failed")); });

let id = 0; const pending = new Map();
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
};
const send = (method, params = {}) => new Promise((ok) => {
  const n = ++id; pending.set(n, ok); ws.send(JSON.stringify({ id: n, method, params }));
});

await send("Page.enable");
// give fonts and layout a moment to settle
await new Promise(r => setTimeout(r, 1200));

const res = await send("Page.printToPDF", {
  printBackground: true,          // required, or the black theme is dropped
  preferCSSPageSize: true,
  marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0,
  displayHeaderFooter: false,
});
const b64 = res?.result?.data;
if (!b64) { console.error("printToPDF failed:", JSON.stringify(res).slice(0, 400)); process.exit(1); }
writeFileSync(output, Buffer.from(b64, "base64"));
console.log("wrote", output, Buffer.from(b64, "base64").length, "bytes");
ws.close();
process.exit(0);
