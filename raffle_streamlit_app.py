# app.py
# Streamlit Fortune Wheel — single-file app
# ----------------------------------------
# Features:
# - Enter labels (one per line) or upload CSV.
# - Optional weights for non-equal slice sizes.
# - Smooth decelerating spin animation.
# - Labels stay inside slices and rotate with the wheel.
# - Fixed pointer at the top; winner computed precisely.
# - Option to remove winners from the wheel.
# - Seed control for reproducible spins.
#
# CSV formats supported:
#   labels only:              Name
#   labels + weights:         Name,Weight
#
# Tip: Narrow slices use smaller font automatically.

import io
import math
import time
import random
from typing import List, Tuple, Optional

import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Circle, Polygon


# ------------- Helpers --------------------------------------------------------

def _normalize_weights(labels: List[str], weights: Optional[List[float]]) -> np.ndarray:
    n = len(labels)
    if not weights or len(weights) != n:
        w = np.ones(n, dtype=float)
    else:
        w = np.array([max(0.0, float(x)) for x in weights], dtype=float)
        if np.allclose(w.sum(), 0.0):
            w = np.ones(n, dtype=float)
    return w / w.sum()


def _angles_from_weights(weights: np.ndarray) -> np.ndarray:
    """Return slice angles (degrees) summing to 360."""
    return 360.0 * weights


def _pick_winner(labels: List[str], angles: np.ndarray, angle_offset_deg: float, pointer_deg: float = 90.0) -> int:
    """
    Determine which slice is under the fixed pointer.
    - angles: slice angles in degrees (sum to 360).
    - angle_offset_deg: current rotation (added to each slice start).
    - pointer_deg: fixed pointer direction in plot coords (default 90° = up).
    """
    # Convert the pointer angle into the "unrotated wheel" frame
    # by subtracting the current rotation, then wrap into [0, 360)
    pointer_in_wheel = (pointer_deg - angle_offset_deg) % 360.0

    cum = 0.0
    for i, a in enumerate(angles):
        if cum <= pointer_in_wheel < cum + a:
            return i
        cum += a
    # Edge case if pointer_in_wheel == 360 exactly
    return len(labels) - 1


def _wheel_colors(n: int) -> List[tuple]:
    """Distinct colors (no style settings)."""
    # Use HSV for even spread
    return [plt.cm.hsv(i / max(n, 1)) for i in range(n)]


def _draw_wheel(
    labels: List[str],
    angles: np.ndarray,
    angle_offset_deg: float,
    *,
    radius: float = 1.0,
    show_center_text: str = "SPIN",
) -> plt.Figure:
    """
    Draw the wheel, its labels (rotating with the wheel), and a fixed pointer.
    Returns a Matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=(6.8, 6.8), dpi=200)
    ax.set_aspect('equal')
    ax.axis('off')

    # Draw slices
    colors = _wheel_colors(len(labels))
    start = 0.0
    for i, (label, ang) in enumerate(zip(labels, angles)):
        theta1 = start + angle_offset_deg
        theta2 = theta1 + ang

        wedge = Wedge((0, 0), radius, theta1, theta2,
                      facecolor=colors[i], edgecolor='white', linewidth=2)
        ax.add_patch(wedge)

        # Label: place at 0.62*radius and align tangentially
        mid = (theta1 + theta2) / 2.0
        r_text = radius * 0.62
        rad = math.radians(mid)
        x = r_text * math.cos(rad)
        y = r_text * math.sin(rad)

        # Tangential orientation (parallel to arc)
        rot = mid
        # Avoid upside-down: if text angle points left-ish, flip
        if 90 < (rot % 360) < 270:
            rot = (rot + 180) % 360
            ha = 'right'
        else:
            ha = 'left'

        # Auto font size depending on slice width and label length
        # Wider slices -> larger font; longer labels -> smaller font
        size = max(8, min(18, 12 + 6 * math.sqrt(ang / 60)))
        size = max(8, min(size, 220 / max(8, len(label))))

        ax.text(x, y, label,
                rotation=rot, rotation_mode='anchor',
                ha=ha, va='center', fontsize=size, weight='bold')

        start += ang

    # Center hub
    hub_r = radius * 0.12
    ax.add_patch(Circle((0, 0), hub_r, color='white', zorder=5))
    if show_center_text:
        ax.text(0, 0, show_center_text, ha='center', va='center', fontsize=12, weight='bold')

    # Fixed pointer (top)
    # Triangle centered above the rim (points to 90° direction)
    tip = (0.0, radius * 1.16)
    left = (-radius * 0.05, radius * 1.02)
    right = (radius * 0.05, radius * 1.02)
    ptr = Polygon([left, right, tip], closed=True, facecolor=(0.9, 0.1, 0.1), edgecolor='black', linewidth=1.0, zorder=10)
    ax.add_patch(ptr)

    # Decorative outer ring
    ax.add_patch(Circle((0, 0), radius, fill=False, edgecolor='black', linewidth=1.5))

    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-1.25, 1.25)
    return fig


def _figure_to_bytes(fig: plt.Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    return buf.getvalue()


def _ease_out_cubic(t: float) -> float:
    """Cubic ease-out for smooth deceleration (t in [0,1])."""
    return 1 - (1 - t) ** 3


# ------------- Streamlit App --------------------------------------------------

st.set_page_config(page_title="Fortune Wheel", page_icon="🎡", layout="centered")

st.title("🎡 Fortune Wheel")

with st.sidebar:
    st.header("Wheel Inputs")
    default_names = "Alice\nBob\nCarlos\nDina\nEvan\nFatima\nGianni\nHana"
    txt = st.text_area("Labels (one per line)", value=default_names, height=160)

    csv = st.file_uploader("Or upload CSV (Name[,Weight])", type=["csv"])

    with st.expander("Optional weights"):
        st.write("If you didn’t upload weights, you can paste a comma-separated list here (same order as labels).")
        weights_raw = st.text_input("Weights (comma-separated)", value="")

    remove_after_win = st.checkbox("Remove winner after spin", value=False)
    seed_val = st.number_input("Seed (optional for reproducibility)", value=0, min_value=0, step=1, help="0 = random")
    spin_min = st.slider("Min full spins", 3, 10, 4)
    spin_max = st.slider("Max full spins", 5, 15, 7)
    frames = st.slider("Animation frames", 35, 180, 70)

# Parse labels
labels: List[str] = []
weights: Optional[List[float]] = None

if csv is not None:
    import pandas as pd
    df = pd.read_csv(csv)
    # Accept common column names
    label_col = None
    for cand in ["label", "labels", "name", "names", "Label", "Name"]:
        if cand in df.columns:
            label_col = cand
            break
    if label_col is None:
        # fallback to first column
        label_col = df.columns[0]
    labels = [str(x).strip() for x in df[label_col].tolist() if str(x).strip()]

    # weights if present
    wcol = None
    for cand in ["weight", "Weight", "weights", "Weights"]:
        if cand in df.columns:
            wcol = cand
            break
    if wcol is not None:
        w = []
        for x in df[wcol].tolist():
            try:
                w.append(float(x))
            except:
                w.append(0.0)
        weights = w
else:
    labels = [line.strip() for line in txt.splitlines() if line.strip()]

    if weights_raw.strip():
        try:
            weights = [float(x) for x in weights_raw.split(",")]
        except:
            weights = None

# Guard: need at least 2 labels
if len(labels) < 2:
    st.info("Add at least two labels to spin the wheel.")
    st.stop()

# Session state
if "angle" not in st.session_state:
    st.session_state.angle = 0.0
if "history" not in st.session_state:
    st.session_state.history = []
if "active_labels" not in st.session_state:
    st.session_state.active_labels = labels.copy()
if "active_weights" not in st.session_state:
    st.session_state.active_weights = weights.copy() if weights else None

# If inputs changed (count or names), reset active lists
if set(st.session_state.get("active_labels", [])) != set(labels) or \
   (weights is not None and st.session_state.get("active_weights") is None) or \
   (weights is None and st.session_state.get("active_weights") is not None) or \
   (weights is not None and len(st.session_state.get("active_weights", [])) != len(labels)):
    st.session_state.active_labels = labels.copy()
    st.session_state.active_weights = weights.copy() if weights else None
    st.session_state.angle = 0.0

active_labels = st.session_state.active_labels
active_weights = st.session_state.active_weights

# If removal emptied the list, reset
if len(active_labels) < 2:
    st.warning("Less than two items remain. Resetting the wheel to your latest inputs.")
    st.session_state.active_labels = labels.copy()
    st.session_state.active_weights = weights.copy() if weights else None
    st.session_state.angle = 0.0
    active_labels = st.session_state.active_labels
    active_weights = st.session_state.active_weights

# Compute geometry
norm_w = _normalize_weights(active_labels, active_weights)
angles = _angles_from_weights(norm_w)

# Wheel preview (static) / Placeholder for animation
canvas = st.empty()

# Draw initial/static wheel
fig = _draw_wheel(active_labels, angles, st.session_state.angle)
png = _figure_to_bytes(fig)
canvas.image(png)

col1, col2, col3 = st.columns([1, 1, 1])

# Spin button
with col2:
    spin = st.button("🎯 SPIN", use_container_width=True)

with col1:
    reset = st.button("🔄 Reset Wheel", use_container_width=True)

with col3:
    download = st.download_button("⬇️ Download PNG", data=png, file_name="fortune_wheel.png", mime="image/png", use_container_width=True)

if reset:
    st.session_state.angle = 0.0
    st.session_state.history = []
    st.session_state.active_labels = labels.copy()
    st.session_state.active_weights = weights.copy() if weights else None
    active_labels = st.session_state.active_labels
    active_weights = st.session_state.active_weights
    norm_w = _normalize_weights(active_labels, active_weights)
    angles = _angles_from_weights(norm_w)
    fig = _draw_wheel(active_labels, angles, st.session_state.angle)
    canvas.image(_figure_to_bytes(fig))
    st.stop()

if spin:
    # Seed
    if seed_val > 0:
        random.seed(seed_val)
        np.random.seed(seed_val)

    min_spins = min(spin_min, spin_max)
    max_spins = max(spin_min, spin_max)

    full_spins = random.randint(min_spins, max_spins)
    final_offset = random.random() * 360.0  # random landing within a slice
    total_delta = full_spins * 360.0 + final_offset

    start_angle = st.session_state.angle

    # Animate
    for i in range(frames):
        t = i / (frames - 1) if frames > 1 else 1.0
        delta = _ease_out_cubic(t) * total_delta
        st.session_state.angle = (start_angle + delta) % 360.0

        fig = _draw_wheel(active_labels, angles, st.session_state.angle)
        canvas.image(_figure_to_bytes(fig))
        time.sleep(0.012)  # ~80 FPS -> we slow to ~60-80ms per frame for smoothness

    # Determine winner
    winner_idx = _pick_winner(active_labels, angles, st.session_state.angle, pointer_deg=90.0)
    winner = active_labels[winner_idx]
    st.session_state.history.insert(0, winner)

    st.balloons()
    st.success(f"🎉 Winner: **{winner}**")

    # Optionally remove winner
    if remove_after_win:
        removed_label = active_labels.pop(winner_idx)
        if active_weights is not None and len(active_weights) > winner_idx:
            active_weights.pop(winner_idx)
        st.session_state.active_labels = active_labels
        st.session_state.active_weights = active_weights
        # Keep the current angle; next draw uses fewer slices
        norm_w = _normalize_weights(active_labels, active_weights)
        angles = _angles_from_weights(norm_w)
        fig = _draw_wheel(active_labels, angles, st.session_state.angle)
        canvas.image(_figure_to_bytes(fig))

# History
if st.session_state.history:
    st.subheader("Recent Winners")
    st.write(", ".join(st.session_state.history[:12]))
