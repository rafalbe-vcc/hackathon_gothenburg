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
    page = st.radio("Go to page:", ["🖋️ Poet Laureate Office", "📋 Citizen Reports Ledger"], label_visibility="collapsed")

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


