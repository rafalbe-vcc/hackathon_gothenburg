"""The Göteborg Pothole Poet Laureate Office — public-facing web app.

Three modes via the MODE environment variable (default seed):
  - seed : reads ../seed/pothole_reports.csv. No GCP services. Always demoable.
  - live : reads BigQuery pothole_laureate.neighbourhood_odes (DAG must have run).
  - full : live + a sidebar form that writes back to AlloyDB.

TEAM: the bottom of this file is your canvas. The starter app gives you a
header, metrics, the poem display, and the dataframe. Everything else —
maps, charts, animations, news ticker, opera libretto — is yours.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

# ─── CONFIG ──────────────────────────────────────────────────────────────────

MODE             = os.environ.get("MODE", "live")             # seed | live | full
PROJECT_ID       = os.environ.get("PROJECT_ID", "")
BROADCAST_BUCKET = os.environ.get("BROADCAST_BUCKET", "")    # Guardian banner; empty = disabled
BQ_DATASET       = "pothole_laureate"
BQ_TABLE         = "neighbourhood_odes"
CSV_PATH         = Path(__file__).parent.parent / "seed" / "pothole_reports.csv"

NEIGHBOURHOODS = [
    "Hisingen", "Frölunda", "Kortedala", "Haga", "Centrum", "Annedal",
    "Gamlestaden", "Linné", "Majorna", "Örgryte", "Vasastan", "Lorensberg",
]

PALETTE = {
    "charcoal":  "#1a1a2e",
    "warm_grey": "#f5f0eb",
    "pine":      "#2d6a4f",
    "copper":    "#b07d62",
}

# ─── PAGE CONFIG + CSS ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="Göteborg Pothole Poet Laureate Office",
    page_icon="🕳",
    layout="wide",
)

st.markdown(
    f"""
    <style>
      .stApp {{ background-color: {PALETTE['warm_grey']}; }}
      h1, h2, h3 {{ color: {PALETTE['charcoal']}; }}
      .laureate-poem {{
        font-family: Georgia, serif;
        font-size: 1.4rem;
        line-height: 1.7;
        color: {PALETTE['charcoal']};
        background-color: white;
        padding: 1.5rem 2rem;
        border-left: 4px solid {PALETTE['copper']};
        white-space: pre-wrap;
      }}
      .mode-chip {{
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.85rem;
        background: {PALETTE['pine']};
        color: white;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── BROADCAST BANNER (Guardian channel) ────────────────────────────────────
# Reads gs://<BROADCAST_BUCKET>/broadcast.txt on every page render (cached 30s).
# Guardian writes via `gcloud storage cp - gs://...broadcast.txt` (Q2E-3).
# Returns "" on any failure so the page never breaks because the banner can't load.

@st.cache_data(ttl=30)
def read_broadcast() -> str:
    if not BROADCAST_BUCKET:
        return ""
    try:
        from google.cloud import storage
        blob = storage.Client().bucket(BROADCAST_BUCKET).blob("broadcast.txt")
        if not blob.exists():
            return ""
        return blob.download_as_text().strip()
    except Exception:
        return ""


# ─── DATA ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_seed() -> pd.DataFrame:
    """Seed mode: aggregate the bundled CSV locally; placeholder poems."""
    raw = pd.read_csv(CSV_PATH)
    g = raw.groupby("neighbourhood").agg(
        pothole_count=("id", "count"),
        avg_severity=("severity_iron_marks", "mean"),
        centroid_lat=("latitude", "mean"),
        centroid_lng=("longitude", "mean"),
    ).reset_index()
    g["ode"] = g["neighbourhood"].apply(
        lambda n: f"(Placeholder)\nCitizens of {n} await composition.\nThe Laureate composes once the pipeline is live."
    )
    g["dominant_weather"] = "—"
    g["dominant_mood"]    = "—"
    g["composed_at"]      = pd.NaT
    return g.sort_values("pothole_count", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=60)
def load_live() -> pd.DataFrame:
    """Live/full mode: read enriched table from BigQuery."""
    from google.cloud import bigquery
    client = bigquery.Client(project=PROJECT_ID)
    sql = f"""
      SELECT neighbourhood, pothole_count, avg_severity,
             dominant_weather, dominant_mood,
             centroid_lat, centroid_lng,
             ode, composed_at
      FROM `{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}`
      ORDER BY pothole_count DESC
    """
    return client.query(sql).to_dataframe()


def load_data() -> pd.DataFrame:
    return load_seed() if MODE == "seed" else load_live()


# ─── HEADER ─────────────────────────────────────────────────────────────────

# Guardian's broadcast banner — appears at the top of every page if set.
_broadcast = read_broadcast()
if _broadcast:
    st.warning(f"🛡 **Guardian broadcast** · {_broadcast}")

st.title("🕳 Göteborg Pothole Poet Laureate Office")
st.caption("*Official commissioned verse on the state of the city's roads, est. 2026.*")

# ─── SIDEBAR ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        f'**Mode:** <span class="mode-chip">{MODE}</span>',
        unsafe_allow_html=True,
    )

    if MODE == "full":
        from alloydb_writer import insert_pothole_report
        st.markdown("---")
        st.subheader("🚧 Report a pothole")
        with st.form("report_form", clear_on_submit=True):
            nb       = st.selectbox("Neighbourhood", sorted(NEIGHBOURHOODS))
            severity = st.slider("Severity (Iron Marks)", 1, 5, 3)
            weather  = st.selectbox("Weather", ["snö", "regn", "sol", "slask", "dimma"])
            mood     = st.selectbox(
                "Your mood",
                ["frustrated", "philosophical", "amused", "resigned", "vengeful", "lagom"],
            )
            quote = st.text_input("Your quote", placeholder='e.g. "It contains weather."')
            if st.form_submit_button("Report it"):
                if quote.strip():
                    try:
                        insert_pothole_report(
                            neighbourhood=nb, severity=severity,
                            weather=weather, mood=mood, quote=quote.strip(),
                        )
                        st.success("Reported. The Laureate composes hourly — re-trigger the DAG to see your quote in the next ode.")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not write to AlloyDB: {e}")
                else:
                    st.warning("Tell us what happened. The Laureate needs material.")

# ─── MAIN ───────────────────────────────────────────────────────────────────

df = load_data()

if df.empty:
    st.warning("No data yet. The Laureate awaits material.")
    st.stop()

# Top-level metrics
c1, c2, c3 = st.columns(3)
c1.metric("Neighbourhoods on watch", len(df))
c2.metric("Total potholes reported", int(df["pothole_count"].sum()))
c3.metric("Citywide average severity", f"{df['avg_severity'].mean():.2f} / 5")

st.markdown("---")

# Neighbourhood selector
nb = st.selectbox("Select a neighbourhood:", df["neighbourhood"].tolist())
row = df[df["neighbourhood"] == nb].iloc[0]

# Poem display
st.markdown("### Today's Ode")
st.markdown(f'<div class="laureate-poem">{row["ode"]}</div>', unsafe_allow_html=True)

# Per-neighbourhood stats
st.markdown("---")
st.markdown("### Office Records")
m1, m2 = st.columns(2)
m1.metric(f"Reports in {nb}", int(row["pothole_count"]))
m2.metric("Average severity", f"{row['avg_severity']:.2f} / 5")

if MODE != "seed" and pd.notna(row.get("composed_at", None)):
    st.caption(
        f"Composed at: {row['composed_at']} · "
        f"Dominant weather: {row.get('dominant_weather', '—')} · "
        f"Dominant mood: {row.get('dominant_mood', '—')}"
    )

# ─── TEAM CANVAS ────────────────────────────────────────────────────────────
#
# TEAM: render however you want, this is your space.
# `df` has every neighbourhood with: pothole_count, avg_severity, dominant_weather,
# dominant_mood, centroid_lat, centroid_lng, ode (poem), composed_at.
# Inspiration cards in codelab/quest-4-render.md — but you can ignore them all
# and design something nobody else thought of.
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown("### Office Bulletin Board")
st.dataframe(
    df[["neighbourhood", "pothole_count", "avg_severity", "dominant_mood", "ode"]],
    use_container_width=True,
    hide_index=True,
)
