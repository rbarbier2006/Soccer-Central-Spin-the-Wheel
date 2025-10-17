# app.py
# Streamlit Fortune Wheel (Python + JS, no matplotlib)
# ---------------------------------------------------
# - Renders an animated wheel in HTML5 Canvas via embedded JS.
# - Labels stay inside slices; tangential text orientation with auto-shrink.
# - Weighted slices (optional).
# - Fixed pointer at the top; winner calculated precisely.
# - Client-side animation; optional "remove winner after spin".
# - Download PNG and spin history in the component UI.
#
# Run locally:
#   pip install streamlit
#   streamlit run app.py

import json
import streamlit as st

st.set_page_config(page_title="Fortune Wheel (JS Canvas)", page_icon="🎡", layout="centered")
st.title("🎡 Fortune Wheel — Python + JS (no matplotlib)")

with st.sidebar:
    st.header("Wheel Inputs")
    default_names = "Alice\nBob\nCarlos\nDina\nEvan\nFatima\nGianni\nHana"
    labels_text = st.text_area("Labels (one per line)", value=default_names, height=160)
    labels = [line.strip() for line in labels_text.splitlines() if line.strip()]

    csv = st.file_uploader("Or upload CSV with columns Name[,Weight]", type=["csv"])
    weights = None
    if csv is not None:
        import pandas as pd
        df = pd.read_csv(csv)
        # Pick name column
        name_col = None
        for c in ["Name", "name", "label", "Label", "names", "labels"]:
            if c in df.columns:
                name_col = c
                break
        if name_col is None:
            name_col = df.columns[0]
        labels = [str(x).strip() for x in df[name_col].tolist() if str(x).strip()]
        # Pick weight column if present
        for wc in ["Weight", "weight", "Weights", "weights"]:
            if wc in df.columns:
                try:
                    weights = [float(x) for x in df[wc].tolist()]
                except:
                    weights = None
                break

    if not weights:
        w_txt = st.text_input("Weights (comma-separated, optional)", value="")
        if w_txt.strip():
            try:
                weights = [float(x) for x in w_txt.split(",")]
            except:
                weights = None

    st.caption("Tip: If weights are omitted or invalid, slices are equal.")

    colA, colB = st.columns(2)
    with colA:
        min_spins = st.number_input("Min full spins", 1, 20, 4)
        duration_ms = int(st.number_input("Spin duration (ms)", 500, 10000, 2500, step=100))
    with colB:
        max_spins = st.number_input("Max full spins", 1, 30, 7)
        seed = st.number_input("Seed (0 = random)", 0, 2_147_483_647, 0, step=1)

    remove_after = st.checkbox("Remove winner after spin", value=False)

if len(labels) < 2:
    st.info("Add at least two labels to spin the wheel.")
    st.stop()

config = {
    "labels": labels,
    "weights": weights if weights and len(weights) == len(labels) else None,
    "minSpins": int(min(min_spins, max_spins)),
    "maxSpins": int(max(min_spins, max_spins)),
    "durationMs": int(duration_ms),
    "seed": int(seed),
    "removeAfterWin": bool(remove_after),
}

html = f"""
<div id="app" style="display:flex;flex-direction:column;align-items:center;gap:14px;">
  <div style="position:relative; width:560px; max-width:90vw;">
    <div id="pointer" style="position:absolute;left:50%;top:6px;transform:translateX(-50%);width:0;height:0;
      border-left: 16px solid transparent; border-right:16px solid transparent; border-bottom:28px solid #e53935; z-index:5; filter:drop-shadow(0 1px 0 rgba(0,0,0,.4));">
    </div>
    <canvas id="wheel" width="600" height="600" style="width:100%;height:auto;border-radius:12px;display:block;background:radial-gradient(circle at 50% 50%, #fff, #f3f3f3 70%, #e9e9e9 100%);"></canvas>
  </div>

  <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
    <button id="spinBtn" style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#1f7ae0;color:white;font-weight:600;cursor:pointer;">🎯 Spin</button>
    <button id="resetBtn" style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#fafafa;cursor:pointer;">🔄 Reset</button>
    <button id="downloadBtn" style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#fafafa;cursor:pointer;">⬇️ Download PNG</button>
    <label style="display:flex;align-items:center;gap:6px;padding:8px 10px;border:1px solid #eee;border-radius:10px;background:#fff;">
      <input type="checkbox" id="removeToggle"> Remove winner after spin
    </label>
  </div>

  <div id="winner" style="font-size:18px;font-weight:700;color:#1b5e20;"></div>
  <div id="history" style="font-size:14px;color:#444;max-width:560px;text-align:center;"></div>
</div>

<script>
  // ---------- Utilities ----------
  const INIT = {json.dumps(config)};

  function mulberry32(a) { // seeded RNG
    return function() {
      let t = a += 0x6D2B79F5;
      t = Math.imul(t ^ t >>> 15, t | 1);
      t ^= t + Math.imul(t ^ t >>> 7, t | 61);
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    }
  }

  let rand = Math.random;
  if (INIT.seed && INIT.seed > 0) rand = mulberry32(INIT.seed >>> 0);

  function clamp(x,min,max){ return Math.max(min, Math.min(max, x)); }
  const TAU = Math.PI * 2;

  function hsvToRgb(h, s, v) { // h in [0,1]
    let i = Math.floor(h*6), f = h*6 - i;
    let p = v*(1-s), q = v*(1-f*s), t = v*(1-(1-f)*s);
    let m = i % 6;
    let r = [v,q,p,p,t,v][m], g = [t,v,v,q,p,p][m], b = [p,p,t,v,v,q][m];
    return `rgb(${Math.round(r*255)}, ${Math.round(g*255)}, ${Math.round(b*255)})`;
  }

  function easeOutCubic(t){ return 1 - Math.pow(1 - t, 3); }

  function toRadians(deg){ return deg * Math.PI / 180; }
  function mod(a, n){ return ((a % n) + n) % n; } // positive modulo

  // ---------- Wheel State ----------
  let labels = [...INIT.labels];
  let weights = (Array.isArray(INIT.weights) && INIT.weights.length === labels.length)
    ? INIT.weights.map(x => Math.max(0, Number(x) || 0))
    : Array(labels.length).fill(1);

  function normalize(ws){
    const s = ws.reduce((a,b)=>a+b,0) || 1;
    return ws.map(x => x / s);
  }

  let weightsNorm = normalize(weights);
  let angles = weightsNorm.map(w => 360*w);

  function recompute(){
    weightsNorm = normalize(weights);
    angles = weightsNorm.map(w => 360*w);
  }

  // ---------- Canvas Setup (HiDPI) ----------
  const canvas = document.getElementById('wheel');
  const ctx = canvas.getContext('2d');
  function setupCanvas(){
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
  window.addEventListener('resize', setupCanvas);

  // ---------- Draw ----------
  function drawWheel(rotationDeg=0){
    const rect = canvas.getBoundingClientRect();
    const size = rect.width;
    const cx = size/2, cy = size/2;
    const R = size*0.46;
    const hubR = R*0.12;
    const rText = R*0.62;

    // backdrop
    ctx.clearRect(0,0,size,size);
    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(1, -1); // make y-axis point up (math coords)

    // Outer ring
    ctx.save();
    ctx.beginPath();
    ctx.arc(0,0,R+1,0,TAU);
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#333";
    ctx.stroke();
    ctx.restore();

    // Slices
    let start = 0;
    for (let i=0;i<labels.length;i++){
      const ang = angles[i];
      const theta1 = toRadians(start + rotationDeg);
      const theta2 = toRadians(start + ang + rotationDeg);

      // slice color
      const color = hsvToRgb((i/labels.length) % 1, 0.75, 0.95);

      ctx.beginPath();
      ctx.moveTo(0,0);
      ctx.arc(0,0,R, theta1, theta2, false);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();

      // slice separator
      ctx.beginPath();
      ctx.arc(0,0,R, theta1, theta1+0.005, false);
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#fff";
      ctx.stroke();

      // Label text
      const mid = start + ang/2;
      const midRad = toRadians(mid + rotationDeg);

      ctx.save();
      // Position at mid angle, tangential orientation
      ctx.rotate(midRad);
      ctx.translate(rText, 0);

      // Auto font size to fit arc length
      const arcLen = rText * toRadians(ang) * 0.9;
      let fontSize = Math.max(10, Math.min(20, 12 + Math.sqrt(ang)));

      ctx.font = `700 ${fontSize}px system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif`;
      let w = ctx.measureText(labels[i]).width;
      while (w > arcLen && fontSize > 9){
        fontSize -= 1;
        ctx.font = `700 ${fontSize}px system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif`;
        w = ctx.measureText(labels[i]).width;
      }

      // Avoid upside-down text
      const absA = mod(mid + rotationDeg, 360);
      if (absA > 90 && absA < 270){
        ctx.rotate(Math.PI);
        ctx.textAlign = "right";
      } else {
        ctx.textAlign = "left";
      }
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#000";
      ctx.fillText(labels[i], 0, 0);
      ctx.restore();

      start += ang;
    }

    // Center hub
    ctx.beginPath();
    ctx.arc(0,0,hubR,0,TAU);
    ctx.fillStyle = "#fff";
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#333";
    ctx.stroke();

    // Center text
    ctx.save();
    ctx.scale(1, -1);
    ctx.fillStyle = "#111";
    ctx.font = "700 14px system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("SPIN", 0, 0);
    ctx.restore();

    ctx.restore();
  }

  // ---------- Winner calculation ----------
  function computeWinner(rotationDeg){
    // pointer at +90° (up)
    const pointerAngle = 90;
    const pointerInWheel = mod(pointerAngle - rotationDeg, 360);
    let cum = 0;
    for (let i=0;i<labels.length;i++){
      const a = angles[i];
      if (pointerInWheel >= cum && pointerInWheel < cum + a) return i;
      cum += a;
    }
    return labels.length - 1; // fallback
  }

  // ---------- Animation ----------
  let rotationDeg = 0;
  let spinning = false;
  let history = [];

  function spinOnce(){
    if (spinning || labels.length < 2) return;
    spinning = true;
    document.getElementById('winner').textContent = "";

    const minS = Math.max(1, Math.min(INIT.minSpins, INIT.maxSpins));
    const maxS = Math.max(minS, INIT.maxSpins);
    const fullSpins = Math.floor(minS + rand() * (maxS - minS + 1));
    const finalOffset = rand() * 360;
    const totalDelta = fullSpins * 360 + finalOffset;

    const duration = clamp(INIT.durationMs, 400, 10000);
    const start = performance.now();
    const startRot = rotationDeg;

    function frame(t){
      const elapsed = t - start;
      const p = clamp(elapsed / duration, 0, 1);
      const eased = easeOutCubic(p);
      rotationDeg = mod(startRot + eased * totalDelta, 360);
      drawWheel(rotationDeg);
      if (p < 1){
        requestAnimationFrame(frame);
      } else {
        // settle
        const idx = computeWinner(rotationDeg);
        const win = labels[idx];
        history.unshift(win);
        document.getElementById('winner').textContent = "🎉 Winner: " + win;
        updateHistory();

        const remove = document.getElementById('removeToggle').checked || INIT.removeAfterWin;
        if (remove){
          labels.splice(idx,1);
          weights.splice(idx,1);
          if (labels.length < 2){
            history.unshift("(reset needed — fewer than 2 items)");
          }
          recompute();
        }
        spinning = false;
      }
    }
    requestAnimationFrame(frame);
  }

  function updateHistory(){
    const el = document.getElementById('history');
    if (!history.length){
      el.textContent = "";
      return;
    }
    el.innerHTML = "<b>Recent winners:</b> " + history.slice(0, 12).join(", ");
  }

  // ---------- Buttons ----------
  document.getElementById('spinBtn').addEventListener('click', spinOnce);
  document.getElementById('resetBtn').addEventListener('click', () => {
    labels = [...INIT.labels];
    weights = (Array.isArray(INIT.weights) && INIT.weights.length === labels.length)
      ? INIT.weights.map(x => Math.max(0, Number(x) || 0))
      : Array(labels.length).fill(1);
    recompute();
    rotationDeg = 0;
    history = [];
    updateHistory();
    drawWheel(rotationDeg);
  });
  document.getElementById('removeToggle').checked = !!INIT.removeAfterWin;

  document.getElementById('downloadBtn').addEventListener('click', () => {
    const link = document.createElement('a');
    link.download = 'fortune_wheel.png';
    link.href = canvas.toDataURL('image/png');
    link.click();
  });

  // ---------- Initial draw ----------
  drawWheel(rotationDeg);
</script>
"""

st.components.v1.html(html, height=760, scrolling=False)

