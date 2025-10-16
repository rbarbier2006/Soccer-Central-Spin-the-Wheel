import io
import json
import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as st_html

# ---------- Page config ----------
st.set_page_config(page_title="Raffle Entries Builder", page_icon="🎟️", layout="centered")

# ---------- Constants ----------
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
    Returns (entries_df, diagnostics_dict).
    entries_df has one column 'Entry' with repeated rows by Tickets Purchased.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]  # normalize headers

    # Validate required columns
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

    # Build "Full Name - Email1 - Phone Number"
    combined = filtered.apply(
        lambda r: f"{clean_cell(r['Full Name'])}{separator}"
                  f"{clean_cell(r['Email1'])}{separator}"
                  f"{clean_cell(r['Phone Number'])}",
        axis=1,
    ).astype(str)

    # Repeat per Tickets Purchased
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

# ---------- Pure-JS wheel (no external libraries) ----------
def render_pure_wheel(display_labels, full_labels):
    """
    HTML wheel (Canvas + requestAnimationFrame) with label clipping.
    - display_labels: names shown on slices (duplicates allowed).
    - full_labels: full entries aligned 1:1 with display_labels.
    - Pointer on RIGHT (triangle flipped); slice under the pointer wins.
    - Labels are clipped to their wedge so they never spill outside the slice.
      Font size auto-fits to the slice arc length.
    - Buttons:
        * Eliminate Winner (1 slice) -> removes that exact slice
        * Eliminate All (same name)  -> removes all slices with that name
        * Reset -> restores original pool
    """
    display_json = json.dumps([str(x) for x in display_labels])
    full_json    = json.dumps([str(x) for x in full_labels])
    disabled_attr = "disabled" if len(display_labels) == 0 else ""

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; }}
  .wrap {{ display:flex; flex-direction:column; align-items:center; gap:16px; padding:8px; }}
  #wheel {{ position:relative; width:560px; height:560px; }}
  #wheel canvas {{ width:560px; height:560px; background:#fff; border-radius:50%; }}
  /* RIGHT-side pointer; flipped 180° (pointing into wheel) */
  .pointer {{
    position:absolute; right:-2px; top:50%; transform:translateY(-50%) rotate(180deg);
    width:0; height:0; border-top:14px solid transparent; border-bottom:14px solid transparent;
    border-left:26px solid #444; filter:drop-shadow(0 1px 2px rgba(0,0,0,.35));
  }}
  .btn {{ background:#4F46E5; color:#fff; border:none; padding:10px 16px; border-radius:10px;
         font-weight:600; cursor:pointer; margin-right:8px; }}
  .btn.secondary {{ background:#6B7280; }}
  .btn.warn {{ background:#DC2626; }}
  .btn.altwarn {{ background:#EF4444; }}
  .btn:disabled {{ background:#9AA0A6; cursor:not-allowed; }}
  .winner {{ font-weight:700; min-height:1.5em; }}
  .row {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; justify-content:center; }}
  .muted {{ color:#6B7280; font-size:0.9rem; }}
</style>
</head>
<body>
<div class="wrap">
  <div id="wheel">
    <div class="pointer"></div>
    <canvas id="c" width="560" height="560"></canvas>
  </div>

  <div class="row">
    <button id="spin" class="btn" {disabled_attr}>Spin 🎯</button>
    <button id="reset" class="btn secondary">Reset</button>
    <button id="remove1" class="btn warn" disabled>Eliminate Winner (1 slice)</button>
    <button id="removeAll" class="btn altwarn" disabled>Eliminate All (same name)</button>
  </div>
  <div id="winner" class="winner"></div>
  <div class="muted" id="count"></div>
</div>

<script>
const origDisplay = {display_json};
const origFull    = {full_json};

let displayPool = origDisplay.slice();
let fullPool    = origFull.slice();

let lastWinnerIndex = null;

const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const W = canvas.width, H = canvas.height;
const CX = W/2, CY = H/2, R = Math.min(W, H)*0.46;
const innerR = R*0.30;   // inner hole radius
const twoPi = Math.PI * 2;

// label radius (mid band of the slice)
const labelR = innerR + (R - innerR) * 0.60;

const spinBtn = document.getElementById('spin');
const resetBtn = document.getElementById('reset');
const remove1Btn = document.getElementById('remove1');
const removeAllBtn = document.getElementById('removeAll');
const winnerEl = document.getElementById('winner');
const countEl = document.getElementById('count');

let angle = 0;
let spinning = false;

function updateCount() {{
  countEl.textContent = displayPool.length + " slice" + (displayPool.length===1?"":"s") + " on wheel";
}}
updateCount();

function pastel(i) {{
  const hue = (i * 137.508) % 360;
  return 'hsl(' + hue + ',70%,60%)';
}}

// Draw one label, clipped to its wedge, auto-fitting font size to the available arc.
function drawLabelClipped(text, start, end) {{
  const mid = (start + end) / 2;
  const sliceAngle = end - start;
  const maxArc = sliceAngle * labelR * 0.90; // 90% of arc length as width budget

  // Create wedge clip
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(CX, CY);
  ctx.arc(CX, CY, R, start, end);
  ctx.closePath();
  ctx.clip();

  // Rotate to tangent orientation at the slice centerline
  ctx.translate(CX, CY);
  let rot = mid + Math.PI/2;
  // Keep text upright for readability (optional)
  if (Math.sin(mid) < 0) rot += Math.PI;
  ctx.rotate(rot);

  // Find font size that fits within available arc
  let fontSize = 18;
  ctx.font = fontSize + 'px sans-serif';
  let width = ctx.measureText(text).width;
  if (width > maxArc) {{
    fontSize = Math.max(10, Math.floor(fontSize * (maxArc / width)));
    ctx.font = fontSize + 'px sans-serif';
  }}

  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  // High-contrast outline + fill
  ctx.strokeStyle = 'rgba(255,255,255,0.9)';
  ctx.lineWidth = Math.max(2, Math.floor(fontSize/6));
  ctx.fillStyle = '#111';

  ctx.strokeText(text, labelR, 0);
  ctx.fillText(text, labelR, 0);

  ctx.restore();
}}

function drawWheel(a) {{
  ctx.clearRect(0,0,W,H);
  const n = displayPool.length;
  if (n === 0) {{
    ctx.fillStyle = '#666';
    ctx.font = '16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No entries loaded', CX, CY);
    return;
  }}
  const slice = twoPi / n;

  // 1) Draw all wedges first
  for (let i=0; i<n; i++) {{
    const start = a + i*slice;
    const end   = a + (i+1)*slice;
    ctx.beginPath();
    ctx.moveTo(CX, CY);
    ctx.arc(CX, CY, R, start, end);
    ctx.closePath();
    ctx.fillStyle = pastel(i);
    ctx.fill();
  }}

  // 2) Draw all labels on top, each clipped to its wedge
  for (let i=0; i<n; i++) {{
    const start = a + i*slice;
    const end   = a + (i+1)*slice;
    drawLabelClipped(displayPool[i], start, end);
  }}

  // 3) Draw inner circle last
  ctx.beginPath();
  ctx.arc(CX, CY, innerR, 0, twoPi);
  ctx.fillStyle = '#fff';
  ctx.fill();
}}

function easeOutCubic(t) {{ return 1 - Math.pow(1 - t, 3); }}
function modTau(x) {{ const t = twoPi; x = x % t; return x < 0 ? x + t : x; }}

// Pointer is at angle 0 (right). Align center of slice to angle 0.
function targetAngleForIndex(idx) {{
  const n = displayPool.length;
  const slice = twoPi / n;
  const center = (idx + 0.5) * slice;
  return 0 - center;
}}

function spin() {{
  if (spinning || displayPool.length === 0) return;
  spinning = true;
  lastWinnerIndex = null;
  remove1Btn.disabled = true;
  removeAllBtn.disabled = true;
  winnerEl.textContent = '';

  const n = displayPool.length;
  const idx = Math.floor(Math.random() * n);

  // Always a long, smooth spin
  const baseTarget = targetAngleForIndex(idx);
  const start = angle;
  const deltaBase = modTau(baseTarget - modTau(start));
  const fullSpins = 6 * twoPi;              // 6 spins every time
  const end = start + deltaBase + fullSpins;

  const duration = 5000; // ms
  const t0 = performance.now();

  function frame(t) {{
    const p = Math.min(1, (t - t0) / duration);
    const k = easeOutCubic(p);
    angle = start + (end - start) * k;
    drawWheel(angle);
    if (p < 1) {{
      requestAnimationFrame(frame);
    }} else {{
      spinning = false;
      lastWinnerIndex = idx;
      const full = fullPool[idx] || '';
      winnerEl.textContent = '🏆 Winner: ' + full;  // full entry
      remove1Btn.disabled = false;
      removeAllBtn.disabled = false;
    }}
  }}
  requestAnimationFrame(frame);
}}

function resetWheel() {{
  displayPool = origDisplay.slice();
  fullPool    = origFull.slice();
  angle = 0; lastWinnerIndex = null;
  remove1Btn.disabled = true;
  removeAllBtn.disabled = true;
  winnerEl.textContent = '';
  drawWheel(angle);
  updateCount();
  spinBtn.disabled = (displayPool.length === 0);
}}

function removeWinnerOne() {{
  if (lastWinnerIndex == null) return;
  if (lastWinnerIndex >= 0 && lastWinnerIndex < displayPool.length) {{
    displayPool.splice(lastWinnerIndex, 1);  // exact slice only
    fullPool.splice(lastWinnerIndex, 1);
  }}
  lastWinnerIndex = null;
  remove1Btn.disabled = true;
  removeAllBtn.disabled = true;
  drawWheel(angle);
  updateCount();
  if (displayPool.length === 0) spinBtn.disabled = true;
}}

function removeWinnerAll() {{
  if (lastWinnerIndex == null) return;
  const name = displayPool[lastWinnerIndex];
  const newDisplay = [], newFull = [];
  for (let i=0; i<displayPool.length; i++) {{
    if (displayPool[i] !== name) {{
      newDisplay.push(displayPool[i]);
      newFull.push(fullPool[i]);
    }}
  }}
  displayPool = newDisplay;
  fullPool = newFull;
  lastWinnerIndex = null;
  remove1Btn.disabled = true;
  removeAllBtn.disabled = true;
  drawWheel(angle);
  updateCount();
  if (displayPool.length === 0) spinBtn.disabled = true;
}}

spinBtn.addEventListener('click', spin);
resetBtn.addEventListener('click', resetWheel);
remove1Btn.addEventListener('click', removeWinnerOne);
removeAllBtn.addEventListener('click', removeWinnerAll);

// initial draw
drawWheel(angle);
</script>
</body>
</html>
"""

# ---------- UI ----------
st.title("🎟️ Raffle Entries Builder")
st.write(
    "Upload your Excel (.xlsx). The app will keep only rows where **ID1 = 6610**, "
    "then build `Full Name - Email1 - Phone Number`, and repeat it according to **Tickets Purchased**."
)

with st.expander("Advanced options", expanded=False):
    id_value = st.text_input("ID filter (ID1 must equal)", value="6610")
    separator = st.text_input("Separator between fields", value=" - ")
    include_header = st.checkbox("Include header row in output", value=True)

uploaded = st.file_uploader("Upload Excel file (.xlsx)", type=["xlsx"])
df = None

if uploaded is not None:
    try:
        xls = pd.ExcelFile(uploaded, engine="openpyxl")
        sheet_name = st.selectbox("Select worksheet", options=xls.sheet_names, index=0)
        df = pd.read_excel(xls, sheet_name=sheet_name, dtype=str, engine="openpyxl")
        st.success(f"Loaded **{sheet_name}** with {len(df):,} rows and {len[df.columns)} columns.")
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

    # Downloads (full 'Entry' text)
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
    st.header("🎰 Spin the Wheel")

    # Prepare aligned lists:
    #   full_entries -> "Name - Email - Phone"
    #   display_names -> Name only (before first " - ")
    full_entries = out_df["Entry"].fillna("").astype(str).tolist()
    display_names = [s.split(" - ")[0] for s in full_entries]

    if len(display_names) == 0:
        st.warning("No entries to spin. Check the ID filter and that Tickets Purchased > 0.")
    st_html(render_pure_wheel(display_names, full_entries), height=820)

st.caption("Required headers: ID1, Full Name, Email1, Phone Number, Tickets Purchased.")
