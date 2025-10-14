import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Raffle Entries Builder", page_icon="🎟️", layout="centered")

# ---- Constants ----
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
    """Return (entries_df, diagnostics_dict)."""
    # Normalize headers
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # Check columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return (
            pd.DataFrame(columns=["Entry"]),
            {
                "ok": False,
                "message": "Missing required column(s): " + ", ".join([f"{c} (expected in column {REQUIRED_COLUMNS[c]})" for c in missing]),
            },
        )

    # Filter
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
            },
        )

    combined = filtered.apply(
        lambda r: f"{clean_cell(r['Full Name'])}{separator}{clean_cell(r['Email1'])}{separator}{clean_cell(r['Phone Number'])}",
        axis=1,
    ).astype(str)

    tickets = pd.to_numeric(filtered["Tickets Purchased"], errors="coerce").fillna(0).astype(int).clip(lower=0)

    repeated = combined.repeat(tickets)
    out_df = pd.DataFrame({"Entry": repeated.values})

    return (
        out_df,
        {
            "ok": True,
            "message": "Success",
            "kept_rows": len(filtered),
            "total_rows": len(df),
            "generated_entries": len(out_df),
            "nonzero_ticket_rows": int((tickets > 0).sum()),
            "zero_ticket_rows": int((tickets == 0).sum()),
        },
    )

def to_excel_bytes(df: pd.DataFrame, header: bool = True) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, header=header, sheet_name="Entries")
    buffer.seek(0)
    return buffer.read()

# ---- UI ----
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

sheet_name = None
df = None

if uploaded is not None:
    try:
        xls = pd.ExcelFile(uploaded, engine="openpyxl")
        sheet_name = st.selectbox("Select worksheet", options=xls.sheet_names, index=0)
        df = pd.read_excel(xls, sheet_name=sheet_name, dtype=str, engine="openpyxl")
        st.success(f"Loaded **{sheet_name}** with {len(df):,} rows and {len(df.columns)} columns.")
        st.dataframe(df.head(10), use_container_width=True)
    except Exception as e:
        st.error(f"Could not read the Excel file: {e}")

if df is not None:
    out_df, info = build_entries(df, id_value=id_value, separator=separator)

    if not info.get("ok", False):
        st.error(info.get("message", "Unknown error"))
    else:
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

        # Download buttons
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

st.caption("Tip: column headers must be exactly: ID1, Full Name, Email1, Phone Number, Tickets Purchased.")
