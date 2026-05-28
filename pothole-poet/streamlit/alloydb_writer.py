"""Write a new pothole report to AlloyDB. Used by Streamlit's interactive form (MODE=full).

Connects via psycopg2 over the AlloyDB private IP. The Streamlit Pod runs on
GKE Autopilot in the same VPC as the AlloyDB cluster, so the private IP is
reachable directly — no proxy, no Serverless VPC connector.

Required environment variables (set on the Deployment in Q6A):
  ALLOYDB_HOST     — private IP of the AlloyDB primary instance
  ALLOYDB_USER     — typically 'postgres'
  ALLOYDB_PASSWORD — typically 'buildwithgemini2026' (workshop default)
  ALLOYDB_DBNAME   — typically 'postgres'

Authentication is password-based (postgres user). The Pod's WIF principal
binding in Q2D-3 is only for BigQuery; AlloyDB access doesn't use IAM auth here.
"""

from __future__ import annotations

import os

import psycopg2

# Approximate Gothenburg-centre coordinates. The form doesn't ask the
# reporter for lat/lng — pothole location is implied by neighbourhood.
DEFAULT_LAT = 57.7
DEFAULT_LNG = 11.97


def _conn():
    return psycopg2.connect(
        host=os.environ["ALLOYDB_HOST"],
        user=os.environ.get("ALLOYDB_USER", "postgres"),
        password=os.environ["ALLOYDB_PASSWORD"],
        dbname=os.environ.get("ALLOYDB_DBNAME", "postgres"),
        sslmode="require",
        connect_timeout=10,
    )


def insert_pothole_report(
    *,
    neighbourhood: str,
    severity: int,
    weather: str,
    mood: str,
    quote: str,
    swallowed_object: str | None = None,
    citizen_id: str | None = None,
) -> None:
    """Insert one citizen-submitted pothole report. Raises on failure."""
    sql = """
      INSERT INTO pothole_reports (
        neighbourhood, latitude, longitude, severity_iron_marks,
        weather, reporter_mood, swallowed_object, reporter_quote, citizen_id
      ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s
      )
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    neighbourhood,
                    DEFAULT_LAT,
                    DEFAULT_LNG,
                    severity,
                    weather,
                    mood,
                    swallowed_object,
                    quote,
                    citizen_id,
                ),
            )
        conn.commit()
