// Render an HTML file in the CDP browser and save a PNG screenshot of it.
// usage: node shot.mjs <in.html> <out.png> [width] [height]
const DEBUG="http://127.0.0.1:9222";
const [inch, outpng, wArg, hArg] = process.argv.slice(2);
const W=Number(wArg||1100), H=Number(hArg||700);
const list=await (await fetch(`${DEBUG}/json/list`)).json();
let page=list.find(t=>t.type==="page");
let target;
if(!page){ const r=await fetch(`${DEBUG}/json/new?about:blank`,{method:"PUT"}); target=await r.json(); page=target; }
const ws=new WebSocket(page.webSocketDebuggerUrl);
await new Promise((ok,err)=>{ws.onopen=ok;ws.onerror=()=>err(new Error("ws"))});
let id=0;const pend=new Map();
ws.onmessage=m=>{const g=JSON.parse(m.data);if(g.id&&pend.has(g.id)){pend.get(g.id)(g);pend.delete(g.id)}};
const send=(me,p={})=>new Promise(ok=>{const n=++id;pend.set(n,ok);ws.send(JSON.stringify({id:n,method:me,params:p}))});
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride",{width:W,height:H,deviceScaleFactor:2,mobile:false});
await send("Page.navigate",{url:"file://"+inch});
await new Promise(r=>setTimeout(r,1200));
const r=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});
const fs=await import("node:fs");
fs.writeFileSync(outpng, Buffer.from(r.result.data,"base64"));
console.log("saved",outpng);
ws.close();
