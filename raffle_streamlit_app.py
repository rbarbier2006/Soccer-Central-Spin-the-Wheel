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
import json

def render_wheel(display_names, full_entries):
    init = {
        "labels": [str(x) for x in display_names],
        "fulls":  [str(x) for x in full_entries],
        "durationMs": 5000,
        "minSpins": 6,
        "maxSpins": 6
    }

    html = """
<div style="display:flex;flex-direction:column;align-items:center;gap:14px;">
  <h1 style="margin:0 0 8px 0;font-weight:800;font-size:28px;">🎰 Spin the Wheel</h1>

  <div style="position:relative;width:560px;max-width:92vw;">
    <div style="position:absolute;right:-2px;top:50%;transform:translateY(-50%) rotate(180deg);
                width:0;height:0;border-top:14px solid transparent;border-bottom:14px solid transparent;
                border-left:26px solid #444;filter:drop-shadow(0 1px 2px rgba(0,0,0,.35));"></div>
    <canvas id="wheel" width="600" height="600"
            style="width:100%;height:auto;border-radius:12px;display:block;
                   background:radial-gradient(circle at 50% 50%, #fff, #f3f3f3 70%, #e9e9e9 100%);"></canvas>
  </div>

  <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
    <button id="spinBtn"  style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#1f7ae0;color:#fff;font-weight:700;cursor:pointer;">🎯 Spin</button>
    <button id="resetBtn" style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#fafafa;cursor:pointer;">🔄 Reset</button>
    <button id="rm1"     disabled style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#ef4444;color:#fff;cursor:pointer;">🗑️ Eliminate Winner</button>
    <button id="rmAll"   disabled style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#b91c1c;color:#fff;cursor:pointer;">🗑️ Eliminate All (same name)</button>
    <button id="pngBtn"  style="padding:10px 16px;border-radius:10px;border:1px solid #ddd;background:#fafafa;cursor:pointer;">⬇️ PNG</button>
  </div>

  <div id="winner" style="font-size:18px;font-weight:800;color:#0f5132;min-height:1.5em;"></div>
  <div id="count"  style="color:#6B7280;"></div>
</div>

<script>
const INIT = __INIT_JSON__;

let labels = [...INIT.labels];
let fulls  = [...INIT.fulls];
let rotation = 0;
let spinning = false;
let lastIdx = null;

const canvas = document.getElementById('wheel');
const ctx = canvas.getContext('2d');

function setupCanvas(){
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const size = Math.min(rect.width, 560);
  canvas.style.width = size + "px";
  canvas.style.height = size + "px";
  canvas.width = Math.floor(size * dpr);
  canvas.height = Math.floor(size * dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
}
setupCanvas();
window.addEventListener('resize', ()=>{ setupCanvas(); draw(rotation); });

function hsv(i,n){
  const h=(i/Math.max(1,n))%1,s=.75,v=.95;
  const f=h*6,p=v*(1-s),q=v*(1-(f%1)*s),t=v*(1-(1-f%1)*s),m=Math.floor(f)%6;
  const r=[v,q,p,p,t,v][m],g=[t,v,v,q,p,p][m],b=[p,p,t,v,v,q][m];
  return `rgb(${Math.round(r*255)},${Math.round(g*255)},${Math.round(b*255)})`;
}
function mod(a,n){return ((a%n)+n)%n}
function easeOutCubic(t){return 1-Math.pow(1-t,3)}

function draw(rot=0){
  const rect = canvas.getBoundingClientRect(), S = rect.width;
  const CX=S/2, CY=S/2, R=S*0.46, innerR=R*0.18, labelStart=innerR+10, labelEnd=R*0.90;

  ctx.clearRect(0,0,S,S);

  const n = Math.max(1, labels.length), slice = 2*Math.PI/n;

  // wedges
  for(let i=0;i<n;i++){
    const a1 = rot + i*slice, a2 = rot + (i+1)*slice;
    ctx.beginPath(); ctx.moveTo(CX,CY); ctx.arc(CX,CY,R,a1,a2,false); ctx.closePath();
    ctx.fillStyle = hsv(i,n); ctx.fill();
    ctx.beginPath(); ctx.arc(CX,CY,R,a1,a1+0.006,false);
    ctx.lineWidth = 2; ctx.strokeStyle = "#fff"; ctx.stroke();
  }

  // labels anchored at the rim, flowing inward
  for(let i=0;i<n;i++){
    const a1 = rot + i*slice, a2 = rot + (i+1)*slice, mid = (a1+a2)/2;
    const name = labels[i];

    // clip to the wedge
    ctx.save();
    ctx.beginPath(); ctx.moveTo(CX,CY); ctx.arc(CX,CY,R,a1,a2,false); ctx.closePath(); ctx.clip();

    ctx.save();
    ctx.translate(CX,CY);
    ctx.rotate(mid);

    // keep text upright on the left side
    const flipped = Math.cos(mid) < 0;
    if (flipped) ctx.rotate(Math.PI);

    const maxW = (labelEnd - labelStart) * 0.95; // don't intrude past inner margin

    // auto-fit
    let font = 18;
    ctx.font = `700 ${font}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
    let w = ctx.measureText(name).width;
    while (w > maxW && font > 9){
      font -= 1;
      ctx.font = `700 ${font}px system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif`;
      w = ctx.measureText(name).width;
    }

    // --- anchor at rim ---
    const x = flipped ? -labelEnd : labelEnd;            // rim position
    ctx.textAlign = flipped ? "left" : "right";          // flow inward
    ctx.textBaseline = "middle";

    ctx.strokeStyle = "rgba(255,255,255,0.9)";
    ctx.lineWidth = Math.max(2, Math.floor(font/6));
    ctx.fillStyle = "#111";
    ctx.strokeText(name, x, 0);
    ctx.fillText(name, x, 0);

    ctx.restore();
    ctx.restore();
  }

  // hub on top
  ctx.beginPath(); ctx.arc(CX,CY,innerR,0,2*Math.PI);
  ctx.fillStyle="#fff"; ctx.fill();
  ctx.lineWidth = 2; ctx.strokeStyle="#333"; ctx.stroke();
}

function winnerIndex(rot){
  const n = Math.max(1, labels.length), slice = 2*Math.PI/n;
  const p = mod(0 - rot, 2*Math.PI); // pointer at angle 0 (right)
  return Math.min(n-1, Math.floor(p / slice));
}

function spin(){
  if (spinning || labels.length < 2) return;
  spinning = true; setElims(true);
  document.getElementById('winner').textContent = "";

  const total = (INIT.maxSpins||6)*2*Math.PI + Math.random()*2*Math.PI;
  const dur = Math.max(400, Math.min(10000, INIT.durationMs||5000));
  const t0 = performance.now(), start = rotation;

  const frame = (t)=>{
    const p = Math.min(1,(t-t0)/dur), k = easeOutCubic(p);
    rotation = mod(start + total*k, 2*Math.PI);
    draw(rotation);
    if (p<1) requestAnimationFrame(frame);
    else {
      lastIdx = winnerIndex(rotation);
      const full = fulls[lastIdx] || labels[lastIdx] || "";
      document.getElementById('winner').textContent = "🏆 Winner: " + full;
      setElims(false); spinning = false;
    }
  };
  requestAnimationFrame(frame);
}

function setElims(dis){
  document.getElementById('rm1').disabled = dis;
  document.getElementById('rmAll').disabled = dis;
}
function updateCount(){
  document.getElementById('count').textContent =
    labels.length + " slice" + (labels.length===1?"":"s") + " on wheel";
}

document.getElementById('spinBtn').onclick = spin;
document.getElementById('resetBtn').onclick = ()=>{
  labels=[...INIT.labels]; fulls=[...INIT.fulls]; rotation=0; lastIdx=null;
  setElims(true); document.getElementById('winner').textContent="";
  draw(rotation); updateCount();
};
document.getElementById('pngBtn').onclick = ()=>{
  const a=document.createElement('a'); a.download="wheel.png"; a.href=canvas.toDataURL("image/png"); a.click();
};
document.getElementById('rm1').onclick = ()=>{
  if(lastIdx==null)return;
  labels.splice(lastIdx,1); fulls.splice(lastIdx,1);
  lastIdx=null; setElims(true); draw(rotation); updateCount();
};
document.getElementById('rmAll').onclick = ()=>{
  if(lastIdx==null)return;
  const n=labels[lastIdx]; const L=[],F=[];
  for(let i=0;i<labels.length;i++){ if(labels[i]!==n){L.push(labels[i]);F.push(fulls[i]);} }
  labels=L; fulls=F; lastIdx=null; setElims(true); draw(rotation); updateCount();
};

draw(rotation); updateCount();
</script>
"""
    return html.replace("__INIT_JSON__", json.dumps(init))

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

    # Wheel inputs
    full_entries = out_df["Entry"].fillna("").astype(str).tolist()
    display_names = [s.split(" - ")[0] for s in full_entries]

    if len(display_names) == 0:
        st.warning("No entries to spin. Check the ID filter and that Tickets Purchased > 0.")
    else:
        st_html(render_wheel(display_names, full_entries), height=820, scrolling=False)

st.caption("Required headers: ID1, Full Name, Email1, Phone Number, Tickets Purchased.")
