import io
import json
import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as st_html

# ---------------- Page / constants ----------------
st.set_page_config(page_title="Raffle Wheel", page_icon="🎟️", layout="centered")

REQUIRED_COLUMNS = {
    "ID1": "U",
    "Full Name": "I",
    "Email1": "L",
    "Phone Number": "O",
    "Tickets Purchased": "R",
}

def clean_cell(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

def build_entries(df: pd.DataFrame, id_value: str = "6610", separator: str = " - "):
    """
    Filter by ID1==id_value, compose "Full Name - Email1 - Phone Number",
    and repeat rows by Tickets Purchased.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return (
            pd.DataFrame(columns=["Entry"]),
            {
                "ok": False,
                "message": "Missing required column(s): "
                + ", ".join([f"{c} (expected in column {REQUIRED_COLUMNS[c]})" for c in missing]),
            },
        )

    # Filter by ID1
    id_series = df["ID1"].astype(str).str.strip()
    filtered = df[id_series == str(id_value).strip()].copy()

    if filtered.empty:
        return (
            pd.DataFrame(columns=["Entry"]),
            {
                "ok": True,
                "message": "No rows matched the ID filter.",
                "kept_rows": 0,
                "total_rows": len(df),
                "generated_entries": 0,
                "nonzero_ticket_rows": 0,
                "zero_ticket_rows": 0,
            },
        )

    # Build full entry text
    combined = filtered.apply(
        lambda r: f"{clean_cell(r['Full Name'])}{separator}"
                  f"{clean_cell(r['Email1'])}{separator}"
                  f"{clean_cell(r['Phone Number'])}",
        axis=1,
    ).astype(str)

    # Repeat by tickets
    tickets = pd.to_numeric(filtered["Tickets Purchased"], errors="coerce").fillna(0).astype(int).clip(lower=0)
    repeated = combined.repeat(tickets)
    out_df = pd.DataFrame({"Entry": repeated.values})

    info = {
        "ok": True,
        "message": "Success",
        "kept_rows": len(filtered),
        "total_rows": len(df),
        "generated_entries": len(out_df),
        "nonzero_ticket_rows": int((tickets > 0).sum()),
        "zero_ticket_rows": int((tickets == 0).sum()),
    }
    return out_df, info

def to_excel_bytes(df: pd.DataFrame, header: bool = True) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, header=header, sheet_name="Entries")
    buf.seek(0)
    return buf.read()

# ---------------- JS wheel renderer ----------------
def render_wheel(display_names, full_entries):
    """
    Canvas-based wheel with:
     - names clipped inside wedges (auto-fit),
     - pointer on the RIGHT (slice touching it wins),
     - eliminate-one and eliminate-all buttons,
     - winner text shows FULL entry.
    No f-strings in HTML; we inject JSON via .replace().
    """
    init = {
        "labels": [str(x) for x in display_names],
        "fulls":  [str(x) for x in full_entries],
        "durationMs": 5000,   # spin length
        "minSpins": 6,        # always long smooth spin
        "maxSpins": 6
    }

    html_template = """
<div id="app" style="display:flex;flex-direction:column;align-items:center;gap:14px;">
  <h1 style="margin:0 0 8px 0;font-weight:800;font-size:28px;">🎰 Spin the Wheel</h1>

  <div style="position:relative; width:560px; max-width:92vw;">
    <!-- RIGHT pointer (triangle points left into the wheel) -->
    <div style="position:absolute; right:-2px; top:50%; transform:translateY(-50%) rotate(180deg);
                width:0;height:0;border-top:14px solid transparent;border-bottom:14px solid transparent;
                border-left:26px solid #444; z-index:5; filter:drop-shadow(0 1px 2px rgba(0,0,0,.35));">
    </div>
    <canvas id="wheel" width="600" height="600"
      style="width:100%;height:auto;border-radius:12px;display:block;background:radial-gradient(circle at 50% 50%, #fff, #f3f3f3 70%, #e9e9e9 100%);">
    </canvas>
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

// --------- state ----------
let labels = [...INIT.labels];      // display names (1 per slice)
let fulls  = [...INIT.fulls];       // full entries (aligned 1:1)
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
  const h = (i / Math.max(1,n)) % 1;
  const s = 0.75, v = 0.95;
  const k = (a)=> (a % 6);
  const f = h*6, p=v*(1-s), q=v*(1-(f%1)*s), t=v*(1-(1-f%1)*s);
  const m = Math.floor(f) % 6;
  const r=[v,q,p,p,t,v][m], g=[t,v,v,q,p,p][m], b=[p,p,t,v,v,q][m];
  return `rgb(${Math.round(r*255)},${Math.round(g*255)},${Math.round(b*255)})`;
}

function mod(a, n){ return ((a % n) + n) % n; }
function clamp(x,min,max){ return Math.max(min, Math.min(max, x)); }
function easeOutCubic(t){ return 1 - Math.pow(1 - t, 3); }

function drawWheel(rot=0) {
  const rect = canvas.getBoundingClientRect();
  const size = rect.width;
  const cx = size/2, cy = size/2;
  const R = size*0.46;
  const hubR = R * 0.12;
  const labelR = R * 0.62;

  ctx.clearRect(0,0,size,size);

  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(1, -1); // y up

  // ring border
  ctx.save();
  ctx.beginPath();
  ctx.arc(0,0,R+1,0,TAU);
  ctx.lineWidth = 3;
  ctx.strokeStyle = "#333";
  ctx.stroke();
  ctx.restore();

  // equal slices
  const n = labels.length || 1;
  const sliceDeg = 360 / n;

  for (let i=0;i<n;i++){
    const start = (i*sliceDeg) + rot;
    const end   = ((i+1)*sliceDeg) + rot;
    const t1 = start * Math.PI/180;
    const t2 = end   * Math.PI/180;

    // Wedge
    ctx.beginPath();
    ctx.moveTo(0,0);
    ctx.arc(0,0,R,t1,t2,false);
    ctx.closePath();
    ctx.fillStyle = hsv(i,n);
    ctx.fill();

    // Separator
    ctx.beginPath();
    ctx.arc(0,0,R,t1,t1+0.006,false);
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#fff";
    ctx.stroke();
  }

  // Labels (clipped to each wedge so they never spill)
  for (let i=0;i<n;i++){
    const start = (i*sliceDeg) + rot;
    const end   = ((i+1)*sliceDeg) + rot;
    const mid   = (start + end) / 2;
    const t1 = start * Math.PI/180;
    const t2 = end   * Math.PI/180;
    const name = labels[i];

    // Clip to wedge
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(0,0);
    ctx.arc(0,0,R,t1,t2,false);
    ctx.closePath();
    ctx.clip();

    // Choose layout: tangent if arc wide enough; otherwise radial
    const arcLen = labelR * ((t2 - t1));
    const tangentOK = arcLen >= 26;

    if (tangentOK) {
      // Tangent orientation
      ctx.save();
      const midRad = mid * Math.PI/180;
      ctx.rotate(midRad + Math.PI/2);
      ctx.translate(labelR, 0);

      // Auto-fit
      let fontSize = 18;
      ctx.font = `700 ${fontSize}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
      let w = ctx.measureText(name).width;
      while (w > arcLen * 0.92 and fontSize > 9){
        fontSize -= 1;
        ctx.font = `700 ${fontSize}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
        w = ctx.measureText(name).width;
      }

      // Keep upright
      const absA = mod(mid, 360);
      if (absA > 90 && absA < 270){
        ctx.rotate(Math.PI);
        ctx.textAlign = "right";
      } else {
        ctx.textAlign = "left";
      }
      ctx.textBaseline = "middle";
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = Math.max(2, Math.floor(fontSize/6));
      ctx.fillStyle = "#111";
      ctx.strokeText(name, 0, 0);
      ctx.fillText(name, 0, 0);
      ctx.restore();
    } else {
      // Radial fallback
      ctx.save();
      const midRad = mid * Math.PI/180;
      ctx.rotate(midRad);
      const startR = (R*0.30) + 10;
      const endR   = R * 0.90;
      const maxW   = (endR - startR) * 0.95;

      let fontSize = 18;
      ctx.font = `700 ${fontSize}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
      let w = ctx.measureText(name).width;
      while (w > maxW and fontSize > 9){
        fontSize -= 1;
        ctx.font = `700 ${fontSize}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
        w = ctx.measureText(name).width;
      }

      // Keep upright
      if (Math.cos(mid * Math.PI/180) < 0){
        ctx.rotate(Math.PI);
        ctx.textAlign = "right";
      } else {
        ctx.textAlign = "left";
      }
      ctx.textBaseline = "middle";
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = Math.max(2, Math.floor(fontSize/6));
      ctx.fillStyle = "#111";
      ctx.strokeText(name, startR, 0);
      ctx.fillText(name, startR, 0);
      ctx.restore();
    }

    ctx.restore(); // end clip
  }

  // hub
  ctx.beginPath();
  ctx.arc(0,0,hubR,0,TAU);
  ctx.fillStyle = "#fff";
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#333";
  ctx.stroke();

  ctx.restore();
}

function computeWinner(rot){
  // Pointer is on the RIGHT => angle = 0° in our wheel frame
  const pointer = 0;
  const n = labels.length || 1;
  const sliceDeg = 360 / n;
  // position of pointer in wheel coordinates:
  const p = mod(pointer - rot, 360);
  // slice index whose span covers p
  const idx = Math.floor(p / sliceDeg);
  return clamp(idx, 0, n-1);
}

function drawCount(){
  const el = document.getElementById("count");
  el.textContent = labels.length + " slice" + (labels.length===1 ? "" : "s") + " on wheel";
}

// ---------- controls ----------
const spinBtn = document.getElementById("spinBtn");
const resetBtn = document.getElementById("resetBtn");
const dlBtn = document.getElementById("dlBtn");
const btnRemove1 = document.getElementById("remove1");
const btnRemoveAll = document.getElementById("removeAll");

function setElimDisabled(v){
  btnRemove1.disabled = v;
  btnRemoveAll.disabled = v;
}

function spinOnce(){
  if (spinning || labels.length < 2) return;
  spinning = true;
  setElimDisabled(true);
  document.getElementById("winner").textContent = "";

  const minS = Math.max(1, INIT.minSpins);
  const maxS = Math.max(minS, INIT.maxSpins);
  const fullSpins = maxS; // fixed
  const finalOffset = Math.random() * 360;
  const totalDelta = fullSpins * 360 + finalOffset;

  const duration = clamp(INIT.durationMs, 400, 10000);
  const start = performance.now();
  const startRot = rotationDeg;

  function frame(t){
    const p = clamp((t - start)/duration, 0, 1);
    const k = easeOutCubic(p);
    rotationDeg = mod(startRot + totalDelta * k, 360);
    drawWheel(rotationDeg);
    if (p < 1){
      requestAnimationFrame(frame);
    } else {
      const idx = computeWinner(rotationDeg);
      lastWinIdx = idx;
      const winnerFull = fulls[idx] || labels[idx] || "";
      document.getElementById("winner").textContent = "🏆 Winner: " + winnerFull;
      setElimDisabled(false);
      spinning = false;
    }
  }
  requestAnimationFrame(frame);
}

spinBtn.addEventListener("click", spinOnce);

resetBtn.addEventListener("click", ()=>{
  labels = [...INIT.labels];
  fulls  = [...INIT.fulls];
  rotationDeg = 0;
  lastWinIdx = null;
  setElimDisabled(true);
  document.getElementById("winner").textContent = "";
  drawWheel(rotationDeg);
  drawCount();
});

dlBtn.addEventListener("click", ()=>{
  const a = document.createElement("a");
  a.download = "wheel.png";
  a.href = canvas.toDataURL("image/png");
  a.click();
});

btnRemove1.addEventListener("click", ()=>{
  if (lastWinIdx==null) return;
  labels.splice(lastWinIdx,1);
  fulls.splice(lastWinIdx,1);
  lastWinIdx = null;
  setElimDisabled(true);
  drawWheel(rotationDeg);
  drawCount();
});

btnRemoveAll.addEventListener("click", ()=>{
  if (lastWinIdx==null) return;
  const name = labels[lastWinIdx];
  const newLabels = [], newFulls = [];
  for (let i=0;i<labels.length;i++){
    if (labels[i] !== name){
      newLabels.push(labels[i]);
      newFulls.push(fulls[i]);
    }
  }
  labels = newLabels;
  fulls = newFulls;
  lastWinIdx = null;
  setElimDisabled(true);
  drawWheel(rotationDeg);
  drawCount();
});

// first paint
drawWheel(rotationDeg);
drawCount();
</script>
"""
    return html_template.replace("__INIT_JSON__", json.dumps(init))

# ---------------- UI ----------------
st.title("🎟️ Raffle Entries Builder")
st.write(
    "Upload your Excel (.xlsx). We’ll keep only rows where **ID1 = 6610**, "
    "compose `Full Name - Email1 - Phone Number`, and repeat by **Tickets Purchased**."
)

with st.expander("Advanced options", expanded=False):
    id_value = st.text_input("ID filter (ID1 must equal)", value="6610")
    separator = st.text_input("Separator between fields", value=" - ")
    include_header = st.checkbox("Include header row in export", value=True)

uploaded = st.file_uploader("Upload Excel file (.xlsx)", type=["xlsx"])
df = None

if uploaded is not None:
    try:
        xls = pd.ExcelFile(uploaded, engine="openpyxl")
        sheet_name = st.selectbox("Select worksheet", options=xls.sheet_names, index=0)
        df = pd.read_excel(xls, sheet_name=sheet_name, dtype=str, engine="openpyxl")
        st.success(f"Loaded **{sheet_name}** with {len(df):,} rows and {len(df.columns)} columns.")
        st.dataframe(df.head(10), use_container_width=True)
    except Exception as e:
        st.exception(e)

if df is not None:
    out_df, info = build_entries(df, id_value=id_value, separator=separator)

    if not info.get("ok", False):
        st.error(info.get("message", "Unknown error"))
        st.stop()

    if info.get("kept_rows", 0) == 0:
        st.warning("No rows matched the ID filter. You can still download an empty file below.")
    else:
        st.info(
            f"Filtered rows kept: **{info.get('kept_rows', 0):,}/{info.get('total_rows', 0):,}** · "
            f"Rows with tickets > 0: **{info.get('nonzero_ticket_rows', 0):,}** · "
            f"Generated entries: **{info.get('generated_entries', 0):,}**"
        )

    st.subheader("Preview of generated entries")
    st.dataframe(out_df.head(30), use_container_width=True)

    # Downloads
    excel_bytes = to_excel_bytes(out_df, header=include_header)
    st.download_button(
        label="⬇️ Download Excel (.xlsx)",
        data=excel_bytes,
        file_name="raffle_entries.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    csv_bytes = out_df.to_csv(index=False, header=include_header).encode("utf-8")
    st.download_button(
        label="⬇️ Download CSV (.csv)",
        data=csv_bytes,
        file_name="raffle_entries.csv",
        mime="text/csv",
    )

    st.divider()

    # Build wheel inputs
    full_entries = out_df["Entry"].fillna("").astype(str).tolist()
    display_names = [s.split(" - ")[0] for s in full_entries]

    if len(display_names) == 0:
        st.warning("No entries to spin. Check the ID filter and that Tickets Purchased > 0.")
    else:
        st_html(render_wheel(display_names, full_entries), height=820, scrolling=False)

st.caption("Required headers: ID1, Full Name, Email1, Phone Number, Tickets Purchased.")
