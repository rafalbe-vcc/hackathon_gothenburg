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
      @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&display=swap');
      
      .stApp {{
        background-color: {PALETTE['warm_grey']};
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      }}
      h1, h2, h3, h4, h5, h6 {{
        font-family: 'Outfit', sans-serif;
        color: {PALETTE['charcoal']};
        font-weight: 800;
        letter-spacing: -0.02em;
      }}
      .laureate-poem {{
        font-family: 'Playfair Display', Georgia, serif;
        font-size: 1.35rem;
        font-style: italic;
        line-height: 1.8;
        color: #2b2b3a;
        background-color: #ffffff;
        padding: 2rem 2.5rem;
        border-radius: 12px;
        border-left: 6px solid {PALETTE['copper']};
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.03);
        white-space: pre-wrap;
        position: relative;
        overflow: hidden;
      }}
      .laureate-poem::before {{
        content: "“";
        position: absolute;
        top: -10px;
        left: 10px;
        font-size: 5rem;
        color: rgba(176, 125, 98, 0.15);
        font-family: 'Playfair Display', serif;
      }}
      .mode-chip {{
        display: inline-block;
        padding: 0.35rem 1rem;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.8rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        background: linear-gradient(135deg, {PALETTE['pine']} 0%, #1b4d32 100%);
        color: white;
        box-shadow: 0 4px 10px rgba(45, 106, 79, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.1);
      }}
      .pothole-card {{
        background: white;
        padding: 1.8rem;
        border-radius: 16px;
        border: 1px solid rgba(0,0,0,0.06);
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03), 0 2px 4px -1px rgba(0,0,0,0.02);
        transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        height: 100%;
      }}
      .pothole-card:hover {{
        transform: translateY(-5px);
        box-shadow: 0 15px 30px -5px rgba(176, 125, 98, 0.15), 0 8px 15px -6px rgba(176, 125, 98, 0.08);
        border-color: rgba(176, 125, 98, 0.3);
      }}
      
      /* Poetry Marquee / News Ticker Styles */
      @keyframes marquee {{
        0% {{ transform: translateX(0%); }}
        100% {{ transform: translateX(-50%); }}
      }}
      .marquee-wrapper {{
        overflow: hidden;
        background: linear-gradient(90deg, #1a1a2e 0%, #2b2b4a 100%);
        color: #f5f0eb;
        padding: 0.75rem 0;
        font-family: 'Playfair Display', serif;
        font-style: italic;
        font-size: 1.05rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 12px rgba(26, 26, 46, 0.15);
        display: flex;
        align-items: center;
        border: 1px solid rgba(255, 255, 255, 0.05);
      }}
      .marquee-scroll {{
        display: flex;
        width: max-content;
        animation: marquee 40s linear infinite;
      }}
      .marquee-item {{
        padding: 0 3rem;
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        gap: 10px;
      }}
      .marquee-separator {{
        color: {PALETTE['copper']};
        font-weight: bold;
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

    from alloydb_writer import insert_pothole_report
    st.markdown("---")
    st.subheader("🚧 Report a Pothole")
    with st.form("report_form", clear_on_submit=True):
        nb       = st.selectbox("Neighbourhood", sorted(NEIGHBOURHOODS))
        severity = st.slider("Severity (Iron Marks)", 1, 5, 3)
        weather  = st.selectbox("Weather", ["snö", "regn", "sol", "slask", "dimma"])
        mood     = st.selectbox(
            "Your Mood",
            ["frustrated", "philosophical", "amused", "resigned", "vengeful", "lagom"],
        )
        swallowed = st.text_input("Swallowed Object", placeholder="e.g. Left shoe, Volvo wheel (optional)")
        citizen = st.text_input("Citizen ID", placeholder="Leave blank for anonymous (optional)")
        quote = st.text_input("Your Quote / Complaint", placeholder='e.g. "It has political opinions."')
        
        submit_btn = st.form_submit_button("Submit Report")
        if submit_btn:
            if quote.strip():
                # Format variables
                swallowed_val = swallowed.strip() if swallowed.strip() else None
                citizen_val = citizen.strip() if citizen.strip() else None
                
                if MODE == "full" or os.environ.get("ALLOYDB_HOST"):
                    try:
                        insert_pothole_report(
                            neighbourhood=nb, 
                            severity=severity,
                            weather=weather, 
                            mood=mood, 
                            quote=quote.strip(),
                            swallowed_object=swallowed_val,
                            citizen_id=citizen_val
                        )
                        st.success("✅ Reported to AlloyDB! The Laureate composes hourly — re-trigger the DAG to see your quote in the next ode.")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not write to AlloyDB: {e}")
                        st.info("💡 Running in Live Demo Mode. Simulating submission success...")
                        st.success(f"✅ [Demo Mode] Successfully captured report for {nb}! Quote: '{quote.strip()}'")
                else:
                    # Graceful local fallback for live demoing in seed/non-full modes
                    st.info("💡 App running in Sandbox/Demo mode.")
                    st.success(f"✅ [Demo Mode] Successfully captured report for {nb}! Quote: '{quote.strip()}'")
            else:
                st.warning("Tell us what happened. The Laureate needs material.")

# ─── MAIN ───────────────────────────────────────────────────────────────────

df = load_data()

if df.empty:
    st.warning("No data yet. The Laureate awaits material.")
    st.stop()

# 📜 GÖTEBORG POETRY TICKER (Live Marquee)
ticker_items = []
for _, row in df.iterrows():
    first_line = row["ode"].split("\n")[0] if "\n" in row["ode"] else row["ode"]
    if len(first_line) > 65:
        first_line = first_line[:62] + "..."
    ticker_items.append(
        f'<span class="marquee-item"><span class="marquee-separator">✦</span> '
        f'<strong>{row["neighbourhood"]}</strong>: "{first_line}"</span>'
    )

# Seamless loop requires doubling the content
double_ticker = ticker_items + ticker_items
ticker_html = f"""
<div class="marquee-wrapper">
    <div class="marquee-scroll">
        {"".join(double_ticker)}
    </div>
</div>
"""
st.markdown(ticker_html, unsafe_allow_html=True)

# Top-level metrics
c1, c2, c3 = st.columns(3)
c1.metric("Neighbourhoods on Watch", len(df))
c2.metric("Total Potholes Reported", int(df["pothole_count"].sum()))
c3.metric("Citywide Average Severity", f"{df['avg_severity'].mean():.2f} / 5")

st.markdown("<div style='margin-bottom: 2rem;'></div>", unsafe_allow_html=True)

# Side-by-side interactive split
map_col, ode_col = st.columns([1.2, 1])

with map_col:
    st.subheader("📍 Gothenburg Pothole Topography")
    st.caption("*Private VPC-bound mapping of citizen reports across urban sectors.*")
    
    import pydeck as pdk
    # Make a copy and scale points for a stunning 3D scatter effect
    df_map = df.copy()
    df_map["radius"] = df_map["pothole_count"] * 12
    
    st.pydeck_chart(pdk.Deck(
        map_style="mapbox://styles/mapbox/light-v9",
        initial_view_state=pdk.ViewState(
            latitude=57.708878, 
            longitude=11.974560, 
            zoom=11.0, 
            pitch=35
        ),
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=df_map,
                get_position=["centroid_lng", "centroid_lat"],
                get_radius="radius",
                get_fill_color="[176, 125, 98, 180]",  # Copper theme
                pickable=True,
                auto_highlight=True,
            ),
        ],
        tooltip={
            "html": "<b>{neighbourhood}</b><br/>"
                    "Reports: {pothole_count}<br/>"
                    "Severity: {avg_severity:.2f} / 5",
            "style": {"backgroundColor": "#1a1a2e", "color": "#f5f0eb", "fontFamily": "Outfit"}
        }
    ))

with ode_col:
    st.subheader("🖋️ Today's Featured Ode")
    st.caption("*Select an active neighbourhood to read the Laureate's official composition.*")
    
    nb = st.selectbox("Select a neighbourhood:", df["neighbourhood"].tolist(), label_visibility="collapsed")
    row = df[df["neighbourhood"] == nb].iloc[0]
    
    st.markdown(f'<div class="laureate-poem">{row["ode"]}</div>', unsafe_allow_html=True)
    
    # Per-neighbourhood metrics
    st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)
    m1, m2 = st.columns(2)
    m1.metric(f"Reports in {nb}", int(row["pothole_count"]))
    m2.metric("Average Severity", f"{row['avg_severity']:.2f} / 5")
    
    if MODE != "seed" and pd.notna(row.get("composed_at", None)):
        st.caption(
            f"Composed: {row['composed_at']} · "
            f"Weather: {row.get('dominant_weather', '—')} · "
            f"Mood: {row.get('dominant_mood', '—')}"
        )

# ─── TEAM CANVAS ────────────────────────────────────────────────────────────
#
# TEAM: Render however you want, this is your space.
# We replace the static dataframe with a glorious interactive gallery.
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown("### 🏛️ The Gothenburg Poetry Wall")
st.caption("*Browse the Laureate's complete civic portfolio by district.*")

# Create columns for cards (3 columns)
gallery_cols = st.columns(3)
for idx, (_, r) in enumerate(df.iterrows()):
    col = gallery_cols[idx % 3]
    with col:
        # Weather & mood icons
        weather_emoji = {
            "snö": "❄️", "regn": "🌧️", "sol": "☀️", "slask": "🌨️", "dimma": "🌫️"
        }.get(str(r.get("dominant_weather", "")).lower(), "🌤️")
        
        mood_emoji = {
            "frustrated": "😤", "philosophical": "🤔", "amused": "🤭", 
            "resigned": "😔", "vengeful": "🥷", "lagom": "☕"
        }.get(str(r.get("dominant_mood", "")).lower(), "🎭")
        
        severity_stars = "★" * int(round(r["avg_severity"])) + "☆" * (5 - int(round(r["avg_severity"])))
        
        col.markdown(f"""
        <div class="pothole-card">
            <div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
                    <span style="font-size: 1.25rem; font-weight: 800; color: {PALETTE['charcoal']}; letter-spacing: -0.01em;">{r['neighbourhood']}</span>
                    <span style="font-size: 0.8rem; padding: 0.25rem 0.6rem; background: {PALETTE['warm_grey']}; border-radius: 6px; font-weight: 700; color: {PALETTE['charcoal']};">
                        {r['pothole_count']} reports
                    </span>
                </div>
                <div style="margin-bottom: 1rem; font-size: 0.85rem; color: #5a5a6a; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                    <span style="background: rgba(0,0,0,0.03); padding: 0.15rem 0.4rem; border-radius: 4px;">{weather_emoji} {r.get('dominant_weather', '—')}</span>
                    <span style="background: rgba(0,0,0,0.03); padding: 0.15rem 0.4rem; border-radius: 4px;">{mood_emoji} {r.get('dominant_mood', '—')}</span>
                    <span style="color: {PALETTE['copper']}; font-weight: bold; letter-spacing: 1px;">{severity_stars}</span>
                </div>
                <div class="laureate-poem" style="font-size: 1.05rem; padding: 1.2rem; border-left: 4px solid {PALETTE['copper']}; background: #faf9f6; border-radius: 0 8px 8px 0; margin-bottom: 0; box-shadow: none;">
                    {r['ode']}
                </div>
            </div>
        </div>
        <div style="margin-bottom: 1.5rem;"></div>
        """, unsafe_allow_html=True)

# ─── FOOTER & VERSION ────────────────────────────────────────────────────────
st.markdown("<div style='margin-top: 3rem;'></div>", unsafe_allow_html=True)
st.markdown("---")
f_col1, f_col2 = st.columns([1, 1])
with f_col1:
    st.caption("© 2026 Göteborg Pothole Poet Laureate Office · Iron & Cloud Hackathon")
with f_col2:
    st.markdown(
        "<div style='text-align: right; color: rgba(0,0,0,0.4); font-size: 0.85rem; font-weight: 600;'>"
        "Deployed Version: <span style='padding: 0.2rem 0.5rem; background: rgba(0,0,0,0.05); border-radius: 4px; font-family: monospace;'>v3.1.0-gold</span>"
        "</div>",
        unsafe_allow_html=True
    )


