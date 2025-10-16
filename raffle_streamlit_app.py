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

# ---------- Pretty wheel (JS) ----------
def render_pretty_wheel(labels):
    """
    Returns an HTML string that renders a polished wheel using GSAP + Winwheel.
    'labels' should include duplicates so ticket counts map to probability.
    """
    labels_json = json.dumps(labels)  # safe for JS consumption

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; }}
  .wrap {{ display:flex; flex-direction:column; align-items:center; gap:14px; padding:8px; }}
  #wheel {{ position:relative; width:520px; height:520px; }}
  #wheel canvas {{ width:520px; height:520px; }}
  .pointer {{
    position:absolute; left:50%; top:-6px; transform:translateX(-50%);
    width:0; height:0; border-left:14px solid transparent; border-right:14px solid transparent;
    border-bottom:24px solid #444; filter:drop-shadow(0 1px 2px rgba(0,0,0,.3));
  }}
  .btn {{
    background:#4F46E5; color:#fff; border:none; padding:10px 16px; border-radius:10px;
    font-weight:600; cursor:pointer;
  }}
  .btn:disabled {{ background:#9AA0A6; cursor:not-allowed; }}
  .winner {{ font-weight:700; }}
</style>
</head>
<body>
<div class="wrap">
  <div id="wheel">
    <div class="pointer"></div>
    <canvas id="wheelCanvas" width="520" height="520"></canvas>
  </div>
  <div>
    <button id="spinBtn" class="btn">Spin 🎯</button>
    <button id="resetBtn" class="btn" style="background:#6B7280;margin-left:8px;">Reset</button>
  </div>
  <div id="winner" class="winner"></div>
</div>

<!-- GSAP TweenMax + Winwheel from CDNs -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/1.20.3/TweenMax.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/winwheel@2.7.0/Winwheel.min.js"></script>
<script>
  const labels = {labels_json};

  function pastel(i) {{
    const hue = (i * 137.508) % 360; // golden angle spacing
    return "hsl(" + hue + ", 70%, 60%)";
  }}

  const segments = labels.map((t, i) => ({{ fillStyle: pastel(i), text: t }}));

  let theWheel = new Winwheel({{
    'numSegments': segments.length,
    'outerRadius': 240,
    'textFontSize': 14,
    'textMargin': 6,
    'segments': segments,
    'animation':
    {{
      'type': 'spinToStop',
      'duration': 6,
      'spins': 8,
      'easing': 'Power4.easeOut',
      'callbackFinished': 'showWinner()',
      'callbackAfter': 'drawPointer()'
    }}
  }});

  const canvas = document.getElementById('wheelCanvas');
  const winnerEl = document.getElementById('winner');
  const spinBtn = document.getElementById('spinBtn');
  const resetBtn = document.getElementById('resetBtn');

  function drawPointer() {{
    const ctx = canvas.getContext('2d');
    ctx.save();
    ctx.translate(canvas.width/2, canvas.height/2);
    ctx.restore();
  }}

  function showWinner() {{
    const seg = theWheel.getIndicatedSegment();
    winnerEl.textContent = '🏆 Winner: ' + (seg && seg.text ? seg.text : '—');
  }}

  spinBtn.addEventListener('click', () => {{
    if (theWheel.numSegments === 0) return;
    winnerEl.textContent = '';
    spinBtn.disabled = true;
    const stopAt = Math.floor(Math.random() * 360); // random end angle
    theWheel.stopAnimation(false);
    theWheel.animation.stopAngle = stopAt;
    theWheel.startAnimation();
    setTimeout(() => spinBtn.disabled = false, (theWheel.animation.duration + 0.5) * 1000);
  }});

  resetBtn.addEventListener('click', () => {{
    winnerEl.textContent = '';
    theWheel.stopAnimation(false);
    theWheel.rotationAngle = 0;
    theWheel.draw();
  }});

  theWheel.draw();
  drawPointer();
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
        # Allow the user to choose the sheet
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
    st.header("🎰 Spin the Wheel (pretty animation)")

    # Use duplicates so probability matches ticket counts
    labels_for_wheel = out_df["Entry"].dropna().astype(str).tolist()
    st_html(render_pretty_wheel(labels_for_wheel), height=650)

st.caption("Required headers: ID1, Full Name, Email1, Phone Number, Tickets Purchased.")
