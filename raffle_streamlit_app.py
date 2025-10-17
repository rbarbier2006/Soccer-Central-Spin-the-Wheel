def render_wheel(display_names, full_entries):
    init = {
        "labels": [str(x) for x in display_names],
        "fulls":  [str(x) for x in full_entries],
        "durationMs": 5000,
        "minSpins": 6,
        "maxSpins": 6
    }
    html_template = """
<div id="app" style="display:flex;flex-direction:column;align-items:center;gap:14px;">
  <h1 style="margin:0 0 8px 0;font-weight:800;font-size:28px;">🎰 Spin the Wheel</h1>
  <div style="position:relative; width:560px; max-width:92vw;">
    <div style="position:absolute; right:-2px; top:50%; transform:translateY(-50%) rotate(180deg);
                width:0;height:0;border-top:14px solid transparent;border-bottom:14px solid transparent;
                border-left:26px solid #444; z-index:5; filter:drop-shadow(0 1px 2px rgba(0,0,0,.35));"></div>
    <canvas id="wheel" width="600" height="600"
      style="width:100%;height:auto;border-radius:12px;display:block;background:radial-gradient(circle at 50% 50%, #fff, #f3f3f3 70%, #e9e9e9 100%);"></canvas>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
    <button id="spinBtn" style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#1f7ae0;color:white;font-weight:700;cursor:pointer;">🎯 Spin</button>
    <button id="resetBtn" style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#fafafa;cursor:pointer;">🔄 Reset</button>
    <button id="remove1"  disabled style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#ef4444;color:#fff;cursor:pointer;">🗑️ Eliminate Winner</button>
    <button id="removeAll" disabled style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#b91c1c;color:#fff;cursor:pointer;">🗑️ Eliminate All (same name)</button>
    <button id="dlBtn" style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#fafafa;cursor:pointer;">⬇️ PNG</button>
  </div>
  <div id="winner" style="font-size:18px;font-weight:800;color:#0f5132;min-height:1.5em;"></div>
  <div id="count" class="muted" style="color:#6B7280;"></div>
</div>

<script>
const INIT = __INIT_JSON__;

let labels = [...INIT.labels];
let fulls  = [...INIT.fulls];
let rotationDeg = 0;
let spinning = false;
let lastWinIdx = null;

const TAU = Math.PI * 2;
const canvas = document.getElementById('wheel');
const ctx = canvas.getContext('2d');

function setupCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const displaySize = canvas.getBoundingClientRect();
  const size = Math.min(displaySize.width, 560);
  canvas.style.width = size + "px";
  canvas.style.height = size + "px";
  canvas.width = Math.floor(size * dpr);
  canvas.height = Math.floor(size * dpr);
  ctx.setTransform(1,0,0,1,0,0);
  ctx.scale(dpr, dpr);
}
setupCanvas();
window.addEventListener('resize', ()=>{ setupCanvas(); drawWheel(rotationDeg); });

function hsv(i, n) {
  const h = (i / Math.max(1,n)) % 1, s = 0.75, v = 0.95;
  const f = h*6, p=v*(1-s), q=v*(1-(f%1)*s), t=v*(1-(1-f%1)*s), m = Math.floor(f) % 6;
  const r=[v,q,p,p,t,v][m], g=[t,v,v,q,p,p][m], b=[p,p,t,v,v,q][m];
  return `rgb(${Math.round(r*255)},${Math.round(g*255)},${Math.round(b*255)})`;
}
function mod(a, n){ return ((a % n) + n) % n; }
function clamp(x,min,max){ return Math.max(min, Math.min(max, x)); }
function easeOutCubic(t){ return 1 - Math.pow(1 - t, 3); }

function drawWheel(rot=0) {
  const rect = canvas.getBoundingClientRect();
  const size = rect.width, cx = size/2, cy = size/2;
  const R = size*0.46, hubR = R*0.12, labelR = R*0.62;

  ctx.clearRect(0,0,size,size);
  ctx.save(); ctx.translate(cx, cy); ctx.scale(1, -1);

  const n = Math.max(1, labels.length);
  const sliceDeg = 360 / n;

  // wedges
  for (let i=0;i<n;i++){
    const start = (i*sliceDeg) + rot;
    const end   = ((i+1)*sliceDeg) + rot;
    const t1 = start*Math.PI/180, t2 = end*Math.PI/180;

    ctx.beginPath(); ctx.moveTo(0,0); ctx.arc(0,0,R,t1,t2,false); ctx.closePath();
    ctx.fillStyle = hsv(i,n); ctx.fill();
    ctx.beginPath(); ctx.arc(0,0,R,t1,t1+0.006,false);
    ctx.lineWidth = 2; ctx.strokeStyle = "#fff"; ctx.stroke();
  }

  // labels (clipped)
  for (let i=0;i<n;i++){
    const start = (i*sliceDeg) + rot;
    const end   = ((i+1)*sliceDeg) + rot;
    const mid   = (start + end) / 2;
    const t1 = start*Math.PI/180, t2 = end*Math.PI/180;
    const name = labels[i];

    ctx.save();
    ctx.beginPath(); ctx.moveTo(0,0); ctx.arc(0,0,R,t1,t2,false); ctx.closePath(); ctx.clip();

    const arcLen = labelR * (t2 - t1);
    const tangentOK = arcLen >= 26;

    if (tangentOK) {
      ctx.save();
      const midRad = mid*Math.PI/180;
      ctx.rotate(midRad + Math.PI/2);
      ctx.translate(labelR, 0);

      let fontSize = 18;
      ctx.font = `700 ${fontSize}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
      let w = ctx.measureText(name).width;
      while (w > arcLen * 0.92 && fontSize > 9){
        fontSize -= 1;
        ctx.font = `700 ${fontSize}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
        w = ctx.measureText(name).width;
      }

      const absA = mod(mid, 360);
      if (absA > 90 && absA < 270){ ctx.rotate(Math.PI); ctx.textAlign = "right"; }
      else { ctx.textAlign = "left"; }
      ctx.textBaseline = "middle";
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = Math.max(2, Math.floor(fontSize/6));
      ctx.fillStyle = "#111";
      ctx.strokeText(name, 0, 0);
      ctx.fillText(name, 0, 0);
      ctx.restore();
    } else {
      ctx.save();
      const midRad = mid*Math.PI/180;
      ctx.rotate(midRad);
      const startR = (R*0.30) + 10, endR = R*0.90, maxW = (endR - startR) * 0.95;

      let fontSize = 18;
      ctx.font = `700 ${fontSize}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
      let w = ctx.measureText(name).width;
      while (w > maxW && fontSize > 9){
        fontSize -= 1;
        ctx.font = `700 ${fontSize}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
        w = ctx.measureText(name).width;
      }

      if (Math.cos(mid*Math.PI/180) < 0){ ctx.rotate(Math.PI); ctx.textAlign = "right"; }
      else { ctx.textAlign = "left"; }
      ctx.textBaseline = "middle";
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = Math.max(2, Math.floor(fontSize/6));
      ctx.fillStyle = "#111";
      ctx.strokeText(name, startR, 0);
      ctx.fillText(name, startR, 0);
      ctx.restore();
    }
    ctx.restore();
  }

  // hub
  ctx.beginPath(); ctx.arc(0,0,hubR,0,TAU); ctx.fillStyle = "#fff"; ctx.fill();
  ctx.lineWidth = 2; ctx.strokeStyle = "#333"; ctx.stroke();
  ctx.restore();
}

function computeWinner(rot){
  const n = Math.max(1, labels.length);
  const sliceDeg = 360 / n;
  const p = mod(0 - rot, 360); // pointer is at 0° (right)
  return Math.min(n-1, Math.floor(p / sliceDeg));
}

function drawCount(){
  document.getElementById("count").textContent =
    labels.length + " slice" + (labels.length===1?"":"s") + " on wheel";
}

const spinBtn = document.getElementById("spinBtn");
const resetBtn = document.getElementById("resetBtn");
const dlBtn = document.getElementById("dlBtn");
const btnRemove1 = document.getElementById("remove1");
const btnRemoveAll = document.getElementById("removeAll");
function setElimDisabled(v){ btnRemove1.disabled = v; btnRemoveAll.disabled = v; }

function spinOnce(){
  if (spinning || labels.length < 2) return;
  spinning = true; setElimDisabled(true);
  document.getElementById("winner").textContent = "";

  const fullSpins = Math.max(1, INIT.maxSpins);
  const totalDelta = fullSpins*360 + Math.random()*360;
  const duration = Math.max(400, Math.min(10000, INIT.durationMs));
  const start = performance.now(), startRot = rotationDeg;

  function frame(t){
    const p = Math.min(1, (t - start)/duration);
    rotationDeg = mod(startRot + totalDelta * (1 - Math.pow(1-p,3)), 360);
    drawWheel(rotationDeg);
    if (p < 1) requestAnimationFrame(frame);
    else {
      lastWinIdx = computeWinner(rotationDeg);
      const winnerFull = fulls[lastWinIdx] || labels[lastWinIdx] || "";
      document.getElementById("winner").textContent = "🏆 Winner: " + winnerFull;
      setElimDisabled(false);
      spinning = false;
    }
  }
  requestAnimationFrame(frame);
}

spinBtn.addEventListener("click", spinOnce);

resetBtn.addEventListener("click", ()=>{
  labels = [...INIT.labels]; fulls = [...INIT.fulls];
  rotationDeg = 0; lastWinIdx = null; setElimDisabled(true);
  document.getElementById("winner").textContent = "";
  drawWheel(rotationDeg); drawCount();
});

dlBtn.addEventListener("click", ()=>{
  const a = document.createElement("a");
  a.download = "wheel.png"; a.href = canvas.toDataURL("image/png"); a.click();
});

btnRemove1.addEventListener("click", ()=>{
  if (lastWinIdx==null) return;
  labels.splice(lastWinIdx,1); fulls.splice(lastWinIdx,1);
  lastWinIdx = null; setElimDisabled(true); drawWheel(rotationDeg); drawCount();
});

btnRemoveAll.addEventListener("click", ()=>{
  if (lastWinIdx==null) return;
  const name = labels[lastWinIdx];
  const newL=[], newF=[]; for (let i=0;i<labels.length;i++){ if (labels[i]!==name){ newL.push(labels[i]); newF.push(fulls[i]); } }
  labels=newL; fulls=newF; lastWinIdx=null; setElimDisabled(true); drawWheel(rotationDeg); drawCount();
});

drawWheel(rotationDeg); drawCount();
</script>
"""
    return html_template.replace("__INIT_JSON__", json.dumps(init))
