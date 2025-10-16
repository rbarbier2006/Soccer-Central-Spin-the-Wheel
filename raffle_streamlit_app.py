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
def render_pure_wheel(display_labels):
    """
    Returns an HTML string that renders a spinning wheel using plain Canvas + requestAnimationFrame.
    - display_labels: array of text to show on slices (duplicates allowed for ticket weighting)
    - Eliminate Winner button removes all slices matching the winner's displayed name
    - Reset restores original labels
    - Pointer points DOWN; slice under the pointer wins
    - Every spin does a full smooth spin (no 'short' spins after the first)
    """
    labels_json = json.dumps([str(x) for x in display_labels if str(x).strip() != ""])
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
  /* Pointer pointing DOWN to the wheel */
  .pointer {{
    position:absolute; left:50%; top:-2px; transform:translateX(-50%);
    width:0; height:0; border-left:14px solid transparent; border-right:14px solid transparent;
    border-bottom:26px solid #444; filter:drop-shadow(0 1px 2px rgba(0,0,0,.35));
  }}
  .btn {{
    background:#4F46E5; color:#fff; border:none; padding:10px 16px; border-radius:10px;
    font-weight:600; cursor:pointer; margin-right:8px;
  }}
  .btn.secondary {{ background:#6B7280; }}
  .btn.warn {{ background:#DC2626; }}
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
    <button id="remove" class="btn warn" disabled>Eliminate Winner</button>
  </div>
  <div id="winner" class="winner"></div>
  <div class="muted" id="count"></div>
</div>

<script>
const original = {labels_json};   // original pool for Reset
let pool = original.slice();      // current pool
let lastWinner = null;

const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const W = canvas.width, H = canvas.height;
const CX = W/2, CY = H/2, R = Math.min(W, H)*0.46;
const innerR = R*0.3;
const twoPi = Math.PI * 2;

const spinBtn = document.getElementById('spin');
const resetBtn = document.getElementById('reset');
const removeBtn = document.getElementById('remove');
const winnerEl = document.getElementById('winner');
const countEl = document.getElementById('count');

let angle = 0;           // current rotation (radians)
let spinning = false;

function updateCount() {{
  countEl.textContent = pool.length + " slice" + (pool.length===1?"":"s") + " on wheel";
}}
updateCount();

function pastel(i) {{
  const hue = (i * 137.508) % 360;
  return 'hsl(' + hue + ',70%,60%)';
}}

function drawWheel(a) {{
  ctx.clearRect(0,0,W,H);
  const n = pool.length;
  if (n === 0) {{
    ctx.fillStyle = '#666';
    ctx.font = '16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No entries loaded', CX, CY);
    return;
  }}
  const slice = twoPi / n;

  // draw slices
  for (let i=0; i<n; i++) {{
    const start = a + i*slice;
    const end   = a + (i+1)*slice;
    ctx.beginPath();
    ctx.moveTo(CX, CY);
    ctx.arc(CX, CY, R, start, end);
    ctx.closePath();
    ctx.fillStyle = pastel(i);
    ctx.fill();

    // label (only the name is already provided by Python)
    const mid = (start + end) / 2;
    const rx = CX + Math.cos(mid) * (R*0.72);
    const ry = CY + Math.sin(mid) * (R*0.72);
    ctx.save();
    ctx.translate(rx, ry);
    ctx.rotate(mid + Math.PI/2); // radial orientation
    ctx.fillStyle = '#111';
    ctx.font = '14px sans-serif';
    const text = (pool[i].length <= 26) ? pool[i] : pool[i].slice(0,23) + '...';
    ctx.textAlign = 'center';
    ctx.fillText(text, 0, 5);
    ctx.restore();
  }}

  // inner circle
  ctx.beginPath();
  ctx.arc(CX, CY, innerR, 0, twoPi);
  ctx.fillStyle = '#fff';
  ctx.fill();
}}

function easeOutCubic(t) {{ return 1 - Math.pow(1 - t, 3); }}
function modTau(x) {{ const t = twoPi; x = x % t; return x < 0 ? x + t : x; }}

function targetAngleForIndex(idx) {{
  // Align center of slice idx to top (pointer) with zero added spins
  const n = pool.length;
  const slice = twoPi / n;
  const center = (idx + 0.5) * slice;
  return -Math.PI/2 - center;  // base alignment
}}

function spin() {{
  if (spinning || pool.length === 0) return;
  spinning = true; lastWinner = null; removeBtn.disabled = true;
  winnerEl.textContent = '';

  // pick random winner index in current pool
  const n = pool.length;
  const idx = Math.floor(Math.random() * n);

  // compute a long spin from current angle to the target index
  const baseTarget = targetAngleForIndex(idx);
  const start = angle;
  // smallest positive rotation to baseTarget from current angle
  const deltaBase = modTau(baseTarget - modTau(start));
  const fullSpins = 6 * twoPi;               // always do 6 full spins
  const end = start + deltaBase + fullSpins; // guaranteed long, smooth spin

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
      const winner = pool[idx] || '';
      lastWinner = winner;
      winnerEl.textContent = '🏆 Winner: ' + winner;
      removeBtn.disabled = false; // enable removal option
    }}
  }}
  requestAnimationFrame(frame);
}}

function resetWheel() {{
  pool = original.slice();
  angle = 0; lastWinner = null; removeBtn.disabled = true;
  winnerEl.textContent = '';
  drawWheel(angle);
  updateCount();
}}

function removeWinner() {{
  if (!lastWinner) return;
  // remove ALL slices with that name
  pool = pool.filter(x => x !== lastWinner);
  lastWinner = null;
  removeBtn.disabled = true;
  drawWheel(angle);
  updateCount();
  if (pool.length === 0) {{
    spinBtn.disabled = true;
  }}
}}

spinBtn.addEventListener('click', spin);
resetBtn.addEventListener('click', resetWheel);
removeBtn.addEventListener('click', removeWinner);

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

    # Downloads (use the full 'Entry' text)
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

    # Show only the name on the wheel (text before the first " - ")
    display_names = out_df["Entry"].fillna("").astype(str).str.split(" - ").str[0].tolist()
    if len(display_names) == 0:
        st.warning("No entries to spin. Check the ID filter and that Tickets Purchased > 0.")
    st_html(render_pure_wheel(display_names), height=760)

st.caption("Required headers: ID1, Full Name, Email1, Phone Number, Tickets Purchased.")
