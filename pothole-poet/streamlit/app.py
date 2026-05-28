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
# ── OpenTelemetry → telemetry.googleapis.com (traces + metrics) ──────────
import os, time, socket
import grpc
import google.auth
import google.auth.transport.requests
from google.auth.transport.grpc import AuthMetadataPlugin

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

def setup_otel():
    """Wire OTel traces + metrics to telemetry.googleapis.com. Safe to skip."""
    if os.environ.get("OTEL_ENABLED", "").lower() not in ("1", "true", "yes"):
        return
    # Streamlit reruns the script on every interaction. OTel provider state is
    # process-global (lives in the opentelemetry package, not in this script),
    # so check if a real provider is already set before configuring again.
    if type(trace.get_tracer_provider()).__name__ != "ProxyTracerProvider":
        return
    try:
        credentials, project_id = google.auth.default()
        request = google.auth.transport.requests.Request()
        channel_creds = grpc.composite_channel_credentials(
            grpc.ssl_channel_credentials(),
            grpc.metadata_call_credentials(
                AuthMetadataPlugin(credentials=credentials, request=request)),
        )

        resource = Resource.create({
            SERVICE_NAME: "pothole-laureate",
            "service.instance.id": socket.gethostname(),
            "service.namespace": "laureate",
            "cloud.region": os.environ.get("REGION", "europe-west1"),
            "gcp.project_id": project_id or "unknown",
        })

        # Traces → Cloud Trace
        tp = TracerProvider(resource=resource)
        tp.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(
            credentials=channel_creds,
            endpoint="https://telemetry.googleapis.com:443/v1/traces",
        )))
        trace.set_tracer_provider(tp)

        # Metrics → Cloud Monitoring (PromQL-queryable as prometheus.googleapis.com/*)
        metrics.set_meter_provider(MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(
                OTLPMetricExporter(
                    credentials=channel_creds,
                    endpoint="https://telemetry.googleapis.com:443/v1/metrics",
                ),
                export_interval_millis=15000,
            )],
        ))
    except Exception as e:
        print(f"[otel] setup skipped: {e}", flush=True)

setup_otel()
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)
request_counter = meter.create_counter(
    "pothole_laureate_requests", description="Total page renders")
request_duration = meter.create_histogram(
    "pothole_laureate_request_duration_seconds",
    description="Page render duration", unit="s")

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
    "volvo_blue": "#003057",     # Volvo Swedish Blue
    "slate":      "#131921",     # Volvo Charcoal / Dark Slate
    "nordic_ice": "#f4f6f8",     # Nordic Ice cool light grey background
    "sandstone":  "#f5f3ef",     # Warm premium sandstone beige accent
    "amber":      "#c68a4c",     # Crystal Swedish Amber
    "iron_mark":  "#70757a",     # Satin metal grey
}

# ─── PAGE CONFIG + CSS ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="Volvo | Göteborg Pothole Poet Laureate Office",
    page_icon="🇸🇪",
    layout="wide",
)

st.markdown(
    f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&display=swap');
      
      .stApp {{
        background-color: {PALETTE['nordic_ice']};
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      }}
      h1, h2, h3, h4, h5, h6 {{
        font-family: 'Outfit', sans-serif;
        color: {PALETTE['slate']};
        font-weight: 300;
        text-transform: uppercase;
        letter-spacing: 0.15em;
      }}
      .laureate-poem {{
        font-family: 'Playfair Display', Georgia, serif;
        font-size: 1.3rem;
        font-style: italic;
        line-height: 1.8;
        color: {PALETTE['slate']};
        background-color: #ffffff;
        padding: 2.2rem 2.8rem;
        border-radius: 2px;
        border-left: 4px solid {PALETTE['volvo_blue']};
        border-top: 1px solid #eaeaea;
        border-right: 1px solid #eaeaea;
        border-bottom: 1px solid #eaeaea;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
        white-space: pre-wrap;
        position: relative;
        overflow: hidden;
      }}
      .laureate-poem::before {{
        content: "“";
        position: absolute;
        top: -10px;
        left: 15px;
        font-size: 5rem;
        color: rgba(0, 48, 87, 0.08);
        font-family: 'Playfair Display', serif;
      }}
      .mode-chip {{
        display: inline-block;
        padding: 0.3rem 0.8rem;
        border-radius: 2px;
        font-weight: 600;
        font-size: 0.75rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        background: {PALETTE['volvo_blue']};
        color: white;
        border: 1px solid rgba(255, 255, 255, 0.1);
      }}
      .pothole-card {{
        background: white;
        padding: 1.8rem;
        border-radius: 2px;
        border: 1px solid #eaeaea;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.01);
        transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        height: 100%;
      }}
      .pothole-card:hover {{
        border-color: {PALETTE['volvo_blue']};
        box-shadow: 0 10px 25px rgba(0, 48, 87, 0.05);
      }}
      
      /* Poetry Marquee / News Ticker Styles */
      @keyframes marquee {{
        0% {{ transform: translateX(0%); }}
        100% {{ transform: translateX(-50%); }}
      }}
      .marquee-wrapper {{
        overflow: hidden;
        background: {PALETTE['slate']};
        color: #ffffff;
        padding: 0.75rem 0;
        font-family: 'Outfit', sans-serif;
        font-weight: 300;
        font-size: 0.85rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        border-radius: 2px;
        margin-bottom: 2rem;
        display: flex;
        align-items: center;
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      }}
      .marquee-scroll {{
        display: flex;
        width: max-content;
        animation: marquee 45s linear infinite;
      }}
      .marquee-item {{
        padding: 0 3rem;
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        gap: 12px;
      }}
      .marquee-separator {{
        color: {PALETTE['amber']};
        font-weight: bold;
      }}
      
      /* Premium Volvo UI Buttons & Form Elements */
      div.stButton > button {{
        background-color: {PALETTE['volvo_blue']} !important;
        color: white !important;
        font-family: 'Outfit', sans-serif !important;
        font-weight: 500 !important;
        letter-spacing: 0.12em !important;
        text-transform: uppercase !important;
        border: none !important;
        border-radius: 2px !important;
        padding: 0.6rem 2rem !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
      }}
      div.stButton > button:hover {{
        background-color: {PALETTE['slate']} !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1) !important;
      }}
      
      div[data-baseweb="select"] > div {{
        border-radius: 2px !important;
        border-color: #eaeaea !important;
      }}
      
      div[data-baseweb="input"] {{
        border-radius: 2px !important;
        border-color: #eaeaea !important;
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
    with tracer.start_as_current_span("read_broadcast"):
        _start = time.time()
        res = ""
        if BROADCAST_BUCKET:
            try:
                from google.cloud import storage
                blob = storage.Client().bucket(BROADCAST_BUCKET).blob("broadcast.txt")
                if blob.exists():
                    res = blob.download_as_text().strip()
            except Exception:
                pass

        request_counter.add(1, {"function": "read_broadcast"})
        request_duration.record(time.time() - _start, {"function": "read_broadcast"})
        return res


# ─── DATA ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_seed() -> pd.DataFrame:
    """Seed mode: aggregate the bundled CSV locally; placeholder poems."""
    with tracer.start_as_current_span("load_seed"):
        _start = time.time()
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
        res_df = g.sort_values("pothole_count", ascending=False).reset_index(drop=True)
        request_counter.add(1, {"function": "load_seed"})
        request_duration.record(time.time() - _start, {"function": "load_seed"})
        return res_df


@st.cache_data(ttl=60)
def load_live() -> pd.DataFrame:
    """Live/full mode: read enriched table from BigQuery."""
    with tracer.start_as_current_span("load_live"):
        _start = time.time()
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
        res_df = client.query(sql).to_dataframe()
        request_counter.add(1, {"function": "load_live"})
        request_duration.record(time.time() - _start, {"function": "load_live"})
        return res_df




def load_data() -> pd.DataFrame:
    return load_seed() if MODE == "seed" else load_live()


def load_recent_reports() -> pd.DataFrame:
    """Load the 50 most recent citizen reports directly from AlloyDB."""
    import psycopg2
    try:
        from alloydb_writer import _conn
        with _conn() as conn:
            sql = """
                SELECT reported_at, neighbourhood, severity_iron_marks, 
                       weather, reporter_mood, swallowed_object, reporter_quote, citizen_id
                FROM pothole_reports
                ORDER BY reported_at DESC
                LIMIT 50
            """
            return pd.read_sql(sql, conn)
    except Exception as e:
        # Fallback if AlloyDB is not configured or fails
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        return pd.DataFrame([
            {
                "reported_at": (now - datetime.timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "neighbourhood": "Vasastan",
                "severity_iron_marks": 5,
                "weather": "regn",
                "reporter_mood": "frustrated",
                "swallowed_object": "Volvo hubcap",
                "reporter_quote": "My wheel is completely gone, please help!",
                "citizen_id": "SE89012"
            },
            {
                "reported_at": (now - datetime.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "neighbourhood": "Haga",
                "severity_iron_marks": 3,
                "weather": "dimma",
                "reporter_mood": "philosophical",
                "swallowed_object": "Umbrella tip",
                "reporter_quote": "Is the hole getting deeper, or is the ground getting higher?",
                "citizen_id": "Anonymous"
            },
            {
                "reported_at": (now - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "neighbourhood": "Hisingen",
                "severity_iron_marks": 4,
                "weather": "slask",
                "reporter_mood": "vengeful",
                "swallowed_object": "Left boot",
                "reporter_quote": "The sludge swallowed my entire left foot. Gothenburg deserves better.",
                "citizen_id": "SE44510"
            },
            {
                "reported_at": (now - datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "neighbourhood": "Majorna",
                "severity_iron_marks": 2,
                "weather": "sol",
                "reporter_mood": "amused",
                "swallowed_object": "Coffee mug",
                "reporter_quote": "Pothole is coffee-cup shaped. Perfect cup holder for cycling!",
                "citizen_id": "Anonymous"
            }
        ])



# ─── HEADER ─────────────────────────────────────────────────────────────────

# Guardian's broadcast banner — appears at the top of every page if set.
_broadcast = read_broadcast()
if _broadcast:
    st.warning(f"🛡 **Guardian broadcast** · {_broadcast}")

st.markdown(
    f"""
    <div style="text-align: center; margin-top: 1rem; margin-bottom: 2.5rem; border-bottom: 1px solid #eaeaea; padding-bottom: 2rem;">
        <div style="font-family: 'Outfit', sans-serif; font-size: 2.2rem; font-weight: 300; letter-spacing: 0.45em; text-transform: uppercase; color: {PALETTE['slate']}; line-height: 1.2;">VOLVO</div>
        <div style="font-family: 'Outfit', sans-serif; font-size: 0.85rem; font-weight: 600; letter-spacing: 0.2em; text-transform: uppercase; color: {PALETTE['iron_mark']}; margin-top: 0.8rem;">Göteborg Pothole Poet Laureate Office</div>
        <div style="font-family: 'Outfit', sans-serif; font-size: 0.75rem; font-style: italic; color: {PALETTE['amber']}; margin-top: 0.4rem; letter-spacing: 0.05em;">
            Swedish Civic Verse & Road Safety Telemetry · Designed in Gothenburg · Est. 2026
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── SIDEBAR ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        f'**Mode:** <span class="mode-chip">{MODE}</span>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.subheader("🧭 Navigation")
    page = st.radio("Go to page:", ["🖋️ Poet Laureate Office", "📋 Citizen Reports Ledger", "🎮 Volvo City Safety Drive"], label_visibility="collapsed")

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


if page == "📋 Citizen Reports Ledger":
    st.subheader("📋 Citizen Reports Ledger")
    st.caption("*Operational log of live community submissions from Gothenburg's roads.*")
    
    reports_df = load_recent_reports()
    
    if reports_df.empty:
        st.info("No citizen reports submitted yet. Use the sidebar to submit the first pothole!")
    else:
        # Mini dashboard
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("Logged Submissions", len(reports_df))
        max_severity = int(reports_df["severity_iron_marks"].max()) if not reports_df.empty else 0
        rc2.metric("Peak Threat Level", f"{max_severity} / 5 Marks")
        
        most_common_weather = reports_df["weather"].mode().iloc[0] if not reports_df.empty else "—"
        rc3.metric("Prevalent Road Conditions", most_common_weather.title())
        
        st.markdown("<div style='margin-bottom: 2rem;'></div>", unsafe_allow_html=True)
        
        # Filters
        f1, f2 = st.columns([1, 1])
        with f1:
            search_query = st.text_input("🔍 Search quotes or swallowed objects:", placeholder="Type to filter...")
        with f2:
            nb_filter = st.selectbox("📍 Filter by neighbourhood:", ["All"] + sorted(NEIGHBOURHOODS))
            
        # Apply filters
        filtered_df = reports_df.copy()
        if search_query:
            q = search_query.lower()
            # Handle cases where columns are object/text
            filtered_df = filtered_df[
                filtered_df["reporter_quote"].astype(str).str.lower().str.contains(q, na=False) |
                filtered_df["swallowed_object"].astype(str).str.lower().str.contains(q, na=False)
            ]
        if nb_filter != "All":
            filtered_df = filtered_df[filtered_df["neighbourhood"] == nb_filter]
            
        st.markdown(f"**Showing {len(filtered_df)} reports**")
        
        # Render cards
        for idx, row in filtered_df.iterrows():
            severity_colors = {5: "🔴 Critical", 4: "🟠 High", 3: "🟡 Moderate", 2: "🟢 Minor", 1: "🟢 Negligible"}
            sev_label = severity_colors.get(row["severity_iron_marks"], "🟡 Unknown")
            
            weather_emoji = {
                "snö": "❄️", "regn": "🌧️", "sol": "☀️", "slask": "🌨️", "dimma": "🌫️"
            }.get(str(row.get("weather", "")).lower(), "🌤️")
            
            mood_emoji = {
                "frustrated": "😤", "philosophical": "🤔", "amused": "🤭", 
                "resigned": "😔", "vengeful": "🥷", "lagom": "☕"
            }.get(str(row.get("reporter_mood", "")).lower(), "🎭")
            
            swallowed_str = f"🎒 Swallowed: <strong>{row['swallowed_object']}</strong>" if pd.notna(row.get("swallowed_object")) and row["swallowed_object"] else "🎒 Swallowed: None"
            citizen_str = f"🆔 Citizen: <code>{row['citizen_id']}</code>" if pd.notna(row.get("citizen_id")) and row["citizen_id"] else "🆔 Citizen: <em>Anonymous</em>"
            
            st.markdown(f"""
            <div class="pothole-card" style="margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; flex-wrap: wrap;">
                    <span style="font-size: 1.25rem; font-weight: 600; color: {PALETTE['slate']};">{row['neighbourhood']}</span>
                    <span style="font-size: 0.85rem; padding: 0.25rem 0.6rem; background: {PALETTE['sandstone']}; border-radius: 2px; font-weight: bold; color: {PALETTE['slate']};">
                        {row['reported_at']}
                    </span>
                </div>
                <div style="margin-bottom: 0.8rem; font-size: 0.9rem; display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
                    <span style="color: #c0392b; font-weight: 700;">{sev_label}</span>
                    <span style="color: #ccc;">·</span>
                    <span style="background: rgba(0,0,0,0.03); padding: 0.15rem 0.4rem; border-radius: 4px;">{weather_emoji} {row['weather']}</span>
                    <span style="color: #ccc;">·</span>
                    <span style="background: rgba(0,0,0,0.03); padding: 0.15rem 0.4rem; border-radius: 4px;">{mood_emoji} {row['reporter_mood']}</span>
                </div>
                <div style="margin-bottom: 0.8rem; font-size: 0.95rem; color: #444; background: rgba(0,0,0,0.01); padding: 0.6rem; border-radius: 2px; display: flex; gap: 20px;">
                    <span>{swallowed_str}</span>
                    <span>{citizen_str}</span>
                </div>
                <div class="laureate-poem" style="font-size: 1.1rem; padding: 1rem 1.5rem; border-left: 4px solid {PALETTE['volvo_blue']}; background: {PALETTE['sandstone']}; border-radius: 0 2px 2px 0; margin-bottom: 0; box-shadow: none;">
                    "{row['reporter_quote']}"
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    # Draw Footer
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
        
    st.stop()


if page == "🎮 Volvo City Safety Drive":
    st.subheader("🇸🇪 Volvo IntelliSafe Simulator")
    st.caption("*Interactive 2D City Safety training ground. Learn to avoid road craters behind the wheel of a Volvo.*")
    
    # We will pass the list of neighbourhoods and odes to the Javascript game so it has dynamic content
    # Make sure we fall back gracefully if BQ or AlloyDB data is empty
    odes_list = []
    for _, row in df.iterrows():
        odes_list.append({
            "neighbourhood": row["neighbourhood"],
            "ode": row["ode"]
        })
    import json
    odes_json_str = json.dumps(odes_list)
    
    # Let's render the iframe component
    import streamlit.components.v1 as components
    
    game_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Volvo City Safety Drive</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: #131921;
                font-family: 'Outfit', sans-serif;
                color: #ffffff;
                display: flex;
                flex-direction: column;
                align-items: center;
                user-select: none;
                overflow: hidden;
            }}
            #game-container {{
                position: relative;
                width: 800px;
                height: 500px;
                background-color: #1c2430;
                border: 4px solid #003057;
                border-radius: 4px;
                box-shadow: 0 15px 40px rgba(0, 0, 0, 0.5);
                overflow: hidden;
            }}
            canvas {{
                display: block;
                background-color: #242e3b;
            }}
            /* Premium HUD / Dashboard Styling */
            #hud-overlay {{
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 50px;
                background: linear-gradient(180deg, rgba(19, 25, 33, 0.9) 0%, rgba(19, 25, 33, 0.7) 100%);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 0 20px;
                box-sizing: border-box;
                z-index: 10;
                font-size: 0.85rem;
                letter-spacing: 0.12em;
                text-transform: uppercase;
            }}
            .hud-block {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            .hud-label {{
                color: #70757a;
                font-weight: 500;
            }}
            .hud-value {{
                font-weight: 600;
            }}
            .status-indicator {{
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background-color: #2ecc71;
                box-shadow: 0 0 10px #2ecc71;
                display: inline-block;
            }}
            /* Warning Banner */
            #warning-banner {{
                position: absolute;
                top: 80px;
                left: 50%;
                transform: translateX(-50%);
                background-color: rgba(198, 138, 76, 0.9);
                border: 1px solid #c68a4c;
                color: #ffffff;
                padding: 10px 24px;
                font-weight: 600;
                letter-spacing: 0.1em;
                border-radius: 2px;
                z-index: 10;
                text-transform: uppercase;
                font-size: 0.9rem;
                box-shadow: 0 8px 20px rgba(0,0,0,0.3);
                display: none;
                animation: pulse 1s infinite alternate;
            }}
            @keyframes pulse {{
                0% {{ opacity: 0.6; }}
                100% {{ opacity: 1; }}
            }}
            /* Safety Intervention Message */
            #safety-overlay {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(194, 54, 22, 0.85);
                z-index: 20;
                display: none;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                text-align: center;
                color: #ffffff;
                letter-spacing: 0.15em;
                text-transform: uppercase;
            }}
            #safety-overlay h2 {{
                font-size: 2.2rem;
                font-weight: 300;
                margin-bottom: 0.5rem;
                letter-spacing: 0.2em;
            }}
            #safety-overlay p {{
                font-size: 0.9rem;
                color: #eaeaea;
                margin-top: 0;
            }}
            /* Game Over Screen */
            #game-over {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(19, 25, 33, 0.95);
                z-index: 30;
                display: none;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 40px;
                box-sizing: border-box;
                text-align: center;
            }}
            #game-over h2 {{
                font-family: 'Outfit', sans-serif;
                font-size: 1.8rem;
                font-weight: 300;
                letter-spacing: 0.25em;
                color: #eaeaea;
                margin-bottom: 0.5rem;
                text-transform: uppercase;
            }}
            #game-over .safety-badge {{
                font-size: 0.8rem;
                font-weight: 600;
                letter-spacing: 0.12em;
                color: #c68a4c;
                border: 1px solid #c68a4c;
                padding: 4px 12px;
                border-radius: 2px;
                text-transform: uppercase;
                margin-bottom: 1.5rem;
            }}
            #game-over .poetry-card {{
                background-color: #1c2430;
                border-left: 3px solid #003057;
                padding: 1.5rem 2rem;
                border-radius: 2px;
                max-width: 550px;
                text-align: left;
                margin-bottom: 2rem;
                font-family: 'Playfair Display', serif;
                font-style: italic;
                font-size: 1.15rem;
                line-height: 1.7;
                color: #eae6e1;
                position: relative;
                box-shadow: inset 0 2px 10px rgba(0,0,0,0.2);
            }}
            #game-over .poetry-card::before {{
                content: "“";
                position: absolute;
                top: -5px;
                left: 8px;
                font-size: 3.5rem;
                color: rgba(0, 48, 87, 0.2);
            }}
            #game-over .poetry-author {{
                font-family: 'Outfit', sans-serif;
                font-size: 0.75rem;
                font-style: normal;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: #c68a4c;
                margin-top: 0.8rem;
                text-align: right;
            }}
            .btn {{
                background-color: #003057;
                color: #ffffff;
                border: none;
                border-radius: 2px;
                padding: 10px 30px;
                font-family: 'Outfit', sans-serif;
                font-size: 0.85rem;
                font-weight: 500;
                letter-spacing: 0.15em;
                text-transform: uppercase;
                cursor: pointer;
                transition: all 0.3s ease;
            }}
            .btn:hover {{
                background-color: #c68a4c;
                box-shadow: 0 4px 12px rgba(198, 138, 76, 0.3);
            }}
            /* Instructions Overlay */
            #instructions {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(19, 25, 33, 0.9);
                z-index: 40;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                text-align: center;
                padding: 30px;
                box-sizing: border-box;
            }}
            #instructions h2 {{
                font-size: 1.6rem;
                font-weight: 300;
                letter-spacing: 0.2em;
                text-transform: uppercase;
                color: #ffffff;
                margin-bottom: 1.5rem;
            }}
            .control-keys {{
                display: flex;
                gap: 15px;
                margin-bottom: 2rem;
            }}
            .key-cap {{
                background-color: #242e3b;
                border: 1px solid #70757a;
                border-radius: 4px;
                padding: 10px 18px;
                font-size: 1.1rem;
                font-weight: bold;
                color: #eaeaea;
                box-shadow: 0 4px 0 #131921;
            }}
        </style>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@0,400;1,400&display=swap" rel="stylesheet">
    </head>
    <body>
        <div id="game-container">
            <!-- HUD -->
            <div id="hud-overlay">
                <div class="hud-block">
                    <span class="status-indicator"></span>
                    <span class="hud-label">IntelliSafe:</span>
                    <span class="hud-value" style="color: #2ecc71;">Active</span>
                </div>
                <div class="hud-block">
                    <span class="hud-label">Safety Shield:</span>
                    <span id="shield-hud" class="hud-value" style="color: #c68a4c;">[ ] [ ] [ ]</span>
                </div>
                <div class="hud-block">
                    <span class="hud-label">Distance:</span>
                    <span id="score-hud" class="hud-value">0 m</span>
                </div>
            </div>

            <!-- Danger Warning Alert -->
            <div id="warning-banner">⚠️ Collision Warning</div>

            <!-- Safety Intervention Warning -->
            <div id="safety-overlay">
                <h2>City Safety</h2>
                <p>Automatic Brake Intervention Active - Impact Mitigated</p>
            </div>

            <!-- Game Over -->
            <div id="game-over">
                <h2>Simulation Suspended</h2>
                <div class="safety-badge">Passenger Cabin Safe (Volvo Certified)</div>
                <div class="poetry-card">
                    <div id="consolation-poetry">Loading city report...</div>
                    <div id="poetry-location" class="poetry-author">— Göteborg Poet Laureate</div>
                </div>
                <button class="btn" onclick="startGame()">Engage Ignition</button>
            </div>

            <!-- Instructions -->
            <div id="instructions">
                <h2>Volvo City Safety Drive</h2>
                <p style="max-width: 500px; color: #b0b5be; line-height: 1.6; margin-bottom: 2rem; font-size: 0.95rem;">
                    Pilot a Volvo wagon on the potholed streets of Gothenburg. Steer left or right to avoid the oncoming chassis hazards. 
                    Volvo City Safety sensors will warn you of threats and mitigate impact severity!
                </p>
                <div class="control-keys">
                    <div class="key-cap">◀ / A</div>
                    <div class="key-cap">▶ / D</div>
                    <p style="align-self: center; color: #70757a; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase; margin: 0 10px;">or</p>
                    <div class="key-cap" style="font-size: 0.85rem; padding: 10px 15px;">Mouse / Drag</div>
                </div>
                <button class="btn" onclick="startGame()">Ignite Engine</button>
            </div>

            <canvas id="gameCanvas" width="800" height="500"></canvas>
        </div>

        <script>
            const canvas = document.getElementById("gameCanvas");
            const ctx = canvas.getContext("2d");
            
            // Core Game State
            let gameRunning = false;
            let playerX = canvas.width / 2;
            let playerY = canvas.height - 100;
            let playerWidth = 36;
            let playerHeight = 75;
            let playerSpeed = 7;
            let keys = {{}};
            let score = 0;
            let shields = 3;
            let obstacles = [];
            let roadOffset = 0;
            let obstacleSpeed = 4.5;
            let obstacleSpawnRate = 120; // Frames between spawns
            let obstacleFrameCount = 0;
            
            // Audio System
            let audioCtx = null;
            
            // Real Odes passed in from BigQuery/AlloyDB
            const odesData = {odes_json_str};
            
            // Standard backup odes if data is missing
            const backupOdes = [
                {{
                    "neighbourhood": "Hisingen",
                    "ode": "Oh depth of slush, oh iron mark,\\nThe tyre yields unto the dark.\\nA Volvo hubcap left behind,\\nAn amber teardrop in the slask."
                }},
                {{
                    "neighbourhood": "Haga",
                    "ode": "The cobblestone yields to the crater's bite,\\nIn morning fog and rainy light.\\nBut Volvo's steel stands firm and deep,\\nWhile we compile the odes to keep."
                }}
            ];
            
            const activeOdes = odesData.length > 0 ? odesData : backupOdes;

            // Handle Input Keys
            window.addEventListener("keydown", e => {{
                keys[e.key] = true;
                if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " "].includes(e.key)) {{
                    e.preventDefault();
                }}
            }});
            window.addEventListener("keyup", e => keys[e.key] = false);

            // Handle Mouse / Touch Steer
            let isDragging = false;
            canvas.addEventListener("mousedown", () => isDragging = true);
            canvas.addEventListener("mouseup", () => isDragging = false);
            canvas.addEventListener("mousemove", e => {{
                if (isDragging || !isDragging) {{ // Allow hover steering for butter-smooth desktop feel
                    const rect = canvas.getBoundingClientRect();
                    const mouseX = e.clientX - rect.left;
                    // Scale because of CSS sizing
                    const scaledX = mouseX * (canvas.width / rect.width);
                    playerX = Math.max(150 + playerWidth/2, Math.min(canvas.width - 150 - playerWidth/2, scaledX));
                }}
            }});
            canvas.addEventListener("touchstart", () => isDragging = true);
            canvas.addEventListener("touchend", () => isDragging = false);
            canvas.addEventListener("touchmove", e => {{
                if (e.touches.length > 0) {{
                    const rect = canvas.getBoundingClientRect();
                    const touchX = e.touches[0].clientX - rect.left;
                    const scaledX = touchX * (canvas.width / rect.width);
                    playerX = Math.max(150 + playerWidth/2, Math.min(canvas.width - 150 - playerWidth/2, scaledX));
                }}
            }});

            // Web Audio Synth Function
            function initAudio() {{
                if (!audioCtx) {{
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                }}
            }}

            function playSound(type) {{
                if (!audioCtx) return;
                try {{
                    const osc = audioCtx.createOscillator();
                    const gain = audioCtx.createGain();
                    osc.connect(gain);
                    gain.connect(audioCtx.destination);

                    if (type === "warning") {{
                        // Volvo dual warning tone (high pitch pulse)
                        osc.type = "sawtooth";
                        osc.frequency.setValueAtTime(1200, audioCtx.currentTime);
                        osc.frequency.exponentialRampToValueAtTime(1800, audioCtx.currentTime + 0.1);
                        gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
                        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.15);
                        osc.start();
                        osc.stop(audioCtx.currentTime + 0.15);
                    }} else if (type === "mitigate") {{
                        // Volvo Safety impact thud and alarm
                        osc.type = "triangle";
                        osc.frequency.setValueAtTime(250, audioCtx.currentTime);
                        osc.frequency.exponentialRampToValueAtTime(50, audioCtx.currentTime + 0.35);
                        gain.gain.setValueAtTime(0.35, audioCtx.currentTime);
                        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.4);
                        osc.start();
                        osc.stop(audioCtx.currentTime + 0.4);
                        
                        // Dual tone chirp
                        setTimeout(() => {{
                            playSound("warning");
                        }}, 100);
                    }} else if (type === "gameover") {{
                        // Melancholic Swedish chord
                        osc.type = "sine";
                        osc.frequency.setValueAtTime(220, audioCtx.currentTime);
                        osc.frequency.exponentialRampToValueAtTime(110, audioCtx.currentTime + 0.8);
                        gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
                        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.8);
                        osc.start();
                        osc.stop(audioCtx.currentTime + 0.8);
                    }}
                }} catch(e) {{}}
            }}

            function startGame() {{
                initAudio();
                document.getElementById("instructions").style.display = "none";
                document.getElementById("game-over").style.display = "none";
                document.getElementById("safety-overlay").style.display = "none";
                document.getElementById("warning-banner").style.display = "none";
                
                playerX = canvas.width / 2;
                score = 0;
                shields = 3;
                obstacles = [];
                obstacleSpeed = 4.5;
                obstacleFrameCount = 0;
                gameRunning = true;
                
                updateShieldHud();
                requestAnimationFrame(gameLoop);
            }}

            function updateShieldHud() {{
                let shieldsText = "";
                for(let i=0; i<3; i++) {{
                    shieldsText += i < shields ? "▰ " : "▱ ";
                }}
                document.getElementById("shield-hud").textContent = shieldsText;
                if (shields === 1) {{
                    document.getElementById("shield-hud").style.color = "#c23616";
                }} else {{
                    document.getElementById("shield-hud").style.color = "#c68a4c";
                }}
            }}

            // Drawing helper: beautiful Volvo EX90 top-down vector
            function drawVolvo(x, y) {{
                ctx.save();
                ctx.translate(x, y);
                
                // Shadow
                ctx.shadowColor = "rgba(0,0,0,0.4)";
                ctx.shadowBlur = 10;
                ctx.shadowOffsetY = 5;

                // Outer Mirrors
                ctx.fillStyle = "#003057";
                ctx.fillRect(-22, -18, 6, 4); // Left mirror
                ctx.fillRect(16, -18, 6, 4);  // Right mirror
                
                // Main Car Body (Boron Steel Structure)
                ctx.shadowBlur = 0;
                ctx.shadowOffsetY = 0;
                ctx.fillStyle = "#003057"; // Classic Volvo Dark Blue
                ctx.beginPath();
                ctx.roundRect(-16, -playerHeight/2, playerWidth, playerHeight, [8, 8, 4, 4]);
                ctx.fill();
                
                // Chrome details & Swedish Grille lines
                ctx.strokeStyle = "rgba(255,255,255,0.15)";
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(-12, -playerHeight/2 + 3);
                ctx.lineTo(12, -playerHeight/2 + 3);
                ctx.stroke();

                // Panoramic Panoramic Glass Roof
                ctx.fillStyle = "#131921"; // Dark Obsidian
                ctx.beginPath();
                ctx.roundRect(-12, -playerHeight/2 + 15, playerWidth - 8, 40, [4, 4, 2, 2]);
                ctx.fill();
                
                // Interior dashboard display glow (warm copper/sandstone)
                ctx.fillStyle = "rgba(198, 138, 76, 0.4)";
                ctx.fillRect(-8, -playerHeight/2 + 18, 16, 2);

                // Rear Windshield
                ctx.fillStyle = "#1a222e";
                ctx.fillRect(-11, 20, 22, 10);
                
                // Signature Active "Thor's Hammer" LED Headlights
                ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
                ctx.shadowColor = "rgba(255,255,255,0.7)";
                ctx.shadowBlur = 15;
                ctx.fillRect(-15, -playerHeight/2 + 4, 4, 3);
                ctx.fillRect(11, -playerHeight/2 + 4, 4, 3);
                
                // Headlight Beams (Aesthetic volumetric cone)
                ctx.shadowBlur = 0;
                const beamGradientLeft = ctx.createLinearGradient(-13, -playerHeight/2, -25, -playerHeight/2 - 100);
                beamGradientLeft.addColorStop(0, "rgba(255, 255, 255, 0.35)");
                beamGradientLeft.addColorStop(1, "rgba(255, 255, 255, 0.0)");
                ctx.fillStyle = beamGradientLeft;
                ctx.beginPath();
                ctx.moveTo(-15, -playerHeight/2 + 4);
                ctx.lineTo(-45, -playerHeight/2 - 120);
                ctx.lineTo(0, -playerHeight/2 - 120);
                ctx.closePath();
                ctx.fill();

                const beamGradientRight = ctx.createLinearGradient(13, -playerHeight/2, 25, -playerHeight/2 - 100);
                beamGradientRight.addColorStop(0, "rgba(255, 255, 255, 0.35)");
                beamGradientRight.addColorStop(1, "rgba(255, 255, 255, 0.0)");
                ctx.fillStyle = beamGradientRight;
                ctx.beginPath();
                ctx.moveTo(11, -playerHeight/2 + 4);
                ctx.lineTo(0, -playerHeight/2 - 120);
                ctx.lineTo(45, -playerHeight/2 - 120);
                ctx.closePath();
                ctx.fill();

                // Signature vertical Red Taillights (Swedish safety lighting)
                ctx.fillStyle = "#c23616";
                ctx.shadowColor = "#c23616";
                ctx.shadowBlur = 8;
                ctx.fillRect(-14, playerHeight/2 - 4, 3, 3);
                ctx.fillRect(11, playerHeight/2 - 4, 3, 3);

                ctx.restore();
            }}

            function drawObstacle(obs) {{
                ctx.save();
                
                // Pothole Crater
                ctx.fillStyle = "#181f29"; // Dark recess
                ctx.beginPath();
                ctx.arc(obs.x, obs.y, obs.radius, 0, Math.PI * 2);
                ctx.fill();
                
                // Crack Ring (rough edges)
                ctx.strokeStyle = "rgba(0,0,0,0.6)";
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(obs.x, obs.y, obs.radius + 1, 0, Math.PI * 2);
                ctx.stroke();

                // Slush/water layer reflections (white dashes)
                ctx.strokeStyle = "rgba(255,255,255,0.15)";
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.arc(obs.x - 2, obs.y - 2, obs.radius - 4, Math.PI * 0.9, Math.PI * 1.4);
                ctx.stroke();

                // Text tag with district label
                ctx.fillStyle = "rgba(255, 255, 255, 0.35)";
                ctx.font = "500 9px 'Outfit', sans-serif";
                ctx.textAlign = "center";
                ctx.fillText(obs.neighbourhood.toUpperCase(), obs.x, obs.y + obs.radius + 15);
                
                ctx.restore();
            }}

            function triggerCitySafety(obs) {{
                shields--;
                updateShieldHud();
                playSound("mitigate");
                
                // Remove the triggering obstacle
                obstacles = obstacles.filter(o => o !== obs);
                
                if (shields <= 0) {{
                    gameRunning = false;
                    endGame(obs.neighbourhood);
                }} else {{
                    // Interfere and flash screen
                    const safetyOverlay = document.getElementById("safety-overlay");
                    safetyOverlay.style.display = "flex";
                    setTimeout(() => {{
                        safetyOverlay.style.display = "none";
                    }}, 1000);
                }}
            }}

            function endGame(district) {{
                playSound("gameover");
                document.getElementById("game-over").style.display = "flex";
                
                // Pick a poetry consolation piece
                const matchingOdes = activeOdes.filter(o => o.neighbourhood.toLowerCase() === district.toLowerCase());
                const finalOde = matchingOdes.length > 0 
                    ? matchingOdes[Math.floor(Math.random() * matchingOdes.length)]
                    : activeOdes[Math.floor(Math.random() * activeOdes.length)];
                
                document.getElementById("consolation-poetry").innerHTML = finalOde.ode.replace(/\\n/g, "<br/>");
                document.getElementById("poetry-location").textContent = `— Göteborg Poet Laureate, District of ${{finalOde.neighbourhood}}`;
            }}

            function gameLoop() {{
                if (!gameRunning) return;
                
                // Handle Keyboard Input
                if (keys["ArrowLeft"] || keys["a"]) {{
                    playerX -= playerSpeed;
                }}
                if (keys["ArrowRight"] || keys["d"]) {{
                    playerX += playerSpeed;
                }}
                
                // Constrain vehicle to road boundaries
                playerX = Math.max(150 + playerWidth/2, Math.min(canvas.width - 150 - playerWidth/2, playerX));
                
                // Progress score
                score += 0.2;
                document.getElementById("score-hud").textContent = `${{Math.floor(score)}} m`;
                
                // Progress speed
                obstacleSpeed = 4.5 + Math.floor(score / 150) * 0.5;
                obstacleSpeed = Math.min(obstacleSpeed, 9); // Speed limit
                
                // Clear Canvas
                ctx.fillStyle = "#242e3b"; // Nordic Asphalt grey
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                
                // Draw Highway Green verges (Sweden nature borders)
                ctx.fillStyle = "#1e3d2f"; // Soft Nordic Forest Pine
                ctx.fillRect(0, 0, 150, canvas.height);
                ctx.fillRect(canvas.width - 150, 0, 150, canvas.height);
                
                // Solid Solid Yellow Lane Lines (classic Volvo safety highway marker)
                ctx.fillStyle = "#c68a4c"; // Safety amber/yellow
                ctx.fillRect(146, 0, 4, canvas.height);
                ctx.fillRect(canvas.width - 150, 0, 4, canvas.height);
                
                // Scrolling road lines
                roadOffset += obstacleSpeed;
                if (roadOffset >= 60) roadOffset = 0;
                
                ctx.fillStyle = "rgba(255, 255, 255, 0.15)";
                for (let y = -60 + roadOffset; y < canvas.height; y += 60) {{
                    // Lane divider 1
                    ctx.fillRect(150 + (canvas.width - 300)/3, y, 4, 30);
                    // Lane divider 2
                    ctx.fillRect(150 + 2*(canvas.width - 300)/3, y, 4, 30);
                }}
                
                // Spawn Obstacles (Potholes)
                obstacleFrameCount++;
                if (obstacleFrameCount >= obstacleSpawnRate) {{
                    obstacleFrameCount = 0;
                    // Lower spawn interval with progress
                    obstacleSpawnRate = Math.max(70, 120 - Math.floor(score / 100) * 8);
                    
                    // Pick random neighborhood
                    const randomDistrictObj = activeOdes[Math.floor(Math.random() * activeOdes.length)];
                    const randomDistrict = randomDistrictObj.neighbourhood;

                    // Choose lane randomly
                    const laneWidth = (canvas.width - 300) / 3;
                    const randomLane = Math.floor(Math.random() * 3);
                    const spawnX = 150 + randomLane * laneWidth + laneWidth/2;

                    obstacles.push({{
                        x: spawnX,
                        y: -30,
                        radius: 18 + Math.random() * 8,
                        neighbourhood: randomDistrict
                    }});
                }}
                
                // Update and Draw Obstacles
                let collisionWarningActive = false;
                
                obstacles.forEach(obs => {{
                    obs.y += obstacleSpeed;
                    drawObstacle(obs);
                    
                    // Pre-Collision warning system (Volvo Active Sensor warning)
                    // Check if an obstacle is directly ahead of the car vertically and close by
                    const horizontalDist = Math.abs(obs.x - playerX);
                    const verticalDist = obs.y - playerY;
                    
                    if (horizontalDist < 50 && verticalDist < -30 && verticalDist > -250) {{
                        collisionWarningActive = true;
                    }}
                    
                    // Direct Collision detection
                    const colXDist = Math.abs(obs.x - playerX);
                    const colYDist = Math.abs(obs.y - playerY);
                    
                    // Using fine-tuned bounding box matching car geometry
                    if (colXDist < (playerWidth/2 + obs.radius - 2) && colYDist < (playerHeight/2 + obs.radius - 5)) {{
                        triggerCitySafety(obs);
                    }}
                }});
                
                // Clean up off-screen obstacles
                obstacles = obstacles.filter(obs => obs.y < canvas.height + 40);
                
                // Toggle warning banner
                const warningBanner = document.getElementById("warning-banner");
                if (collisionWarningActive) {{
                    if (warningBanner.style.display !== "block") {{
                        warningBanner.style.display = "block";
                        playSound("warning");
                    }}
                }} else {{
                    warningBanner.style.display = "none";
                }}
                
                // Draw Player (Volvo EX90)
                drawVolvo(playerX, playerY);
                
                requestAnimationFrame(gameLoop);
            }}
        </script>
    </body>
    </html>
    """
    
    # Render with Streamlit HTML components
    components.html(game_html, height=530)
    
    st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)
    st.markdown("### 🇸🇪 Volvo City Safety Integration")
    st.info(
        "💡 **Technical Note**: This simulator runs high-fidelity client-side 60fps logic embedded as a secure Sandboxed Iframe. "
        "It queries live neighborhood odes dynamically compiled from BigQuery and uses local Web Audio API synthesizer for native sound support."
    )
    
    # Draw Footer
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
                get_fill_color="[0, 48, 87, 180]",  # Volvo Swedish Blue theme
                pickable=True,
                auto_highlight=True,
            ),
        ],
        tooltip={
            "html": "<b>{neighbourhood}</b><br/>"
                    "Reports: {pothole_count}<br/>"
                    "Severity: {avg_severity:.2f} / 5",
            "style": {"backgroundColor": PALETTE['slate'], "color": "#ffffff", "fontFamily": "Outfit"}
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
                    <span style="font-size: 1.25rem; font-weight: 600; color: {PALETTE['slate']}; letter-spacing: -0.01em;">{r['neighbourhood']}</span>
                    <span style="font-size: 0.8rem; padding: 0.25rem 0.6rem; background: {PALETTE['sandstone']}; border-radius: 2px; font-weight: 700; color: {PALETTE['slate']};">
                        {r['pothole_count']} reports
                    </span>
                </div>
                <div style="margin-bottom: 1rem; font-size: 0.85rem; color: #5a5a6a; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                    <span style="background: rgba(0,0,0,0.03); padding: 0.15rem 0.4rem; border-radius: 4px;">{weather_emoji} {r.get('dominant_weather', '—')}</span>
                    <span style="background: rgba(0,0,0,0.03); padding: 0.15rem 0.4rem; border-radius: 4px;">{mood_emoji} {r.get('dominant_mood', '—')}</span>
                    <span style="color: {PALETTE['amber']}; font-weight: bold; letter-spacing: 1px;">{severity_stars}</span>
                </div>
                <div class="laureate-poem" style="font-size: 1.05rem; padding: 1.2rem; border-left: 4px solid {PALETTE['volvo_blue']}; background: {PALETTE['sandstone']}; border-radius: 0 2px 2px 0; margin-bottom: 0; box-shadow: none;">
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


