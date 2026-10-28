"""
Dashboard API (FastAPI) - read-only access to the vehicle_events table.

The React dashboard polls these endpoints every second. The API also serves
the built React app (frontend/dist) so everything is on one port (8000).

Endpoints
  GET /api/health                      DB connectivity check
  GET /api/summary?minutes=0           totals, colour + direction breakdown (0 = all time)
  GET /api/events?limit=25             most recent crossing events
  GET /api/timeseries?minutes=30       vehicles per minute (gaps filled with 0)
  GET /hls/...                         MediaMTX HLS video, passed through this port
"""
import os
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL",
                         "postgresql://vehicle:vehicle@127.0.0.1:5432/vehicle_analytics")
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
HLS_UPSTREAM = os.getenv("HLS_UPSTREAM", "http://127.0.0.1:8888")  # MediaMTX HLS server

app = FastAPI(title="Vehicle Analytics API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

_pool = None


def pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 10, DATABASE_URL)
    return _pool


@contextmanager
def cursor():
    try:
        conn = pool().getconn()
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool().putconn(conn)


def window(minutes):
    """SQL filter for the selected time range (0 = all time)."""
    if minutes > 0:
        return "event_time >= now() - make_interval(mins => %(minutes)s)", {"minutes": minutes}
    return "TRUE", {}


@app.get("/api/health")
def health():
    with cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        return {"status": "ok", "db": cur.fetchone()["ok"] == 1}


@app.get("/api/summary")
def summary(minutes: int = Query(0, ge=0, le=10080)):
    where, params = window(minutes)
    with cursor() as cur:
        cur.execute(f"""
            SELECT count(*)                                         AS total,
                   count(*) FILTER (WHERE direction = 'in')         AS total_in,
                   count(*) FILTER (WHERE direction = 'out')        AS total_out,
                   max(event_time)                                  AS last_event,
                   (SELECT count(*) FROM vehicle_events
                     WHERE event_time >= now() - interval '1 minute') AS last_minute
            FROM vehicle_events WHERE {where}""", params)
        totals = cur.fetchone()

        cur.execute(f"""
            SELECT color, count(*) AS count FROM vehicle_events
            WHERE {where} GROUP BY color ORDER BY count DESC""", params)
        by_color = cur.fetchall()

    return {"minutes": minutes, **totals, "by_color": by_color}


@app.get("/api/events")
def events(limit: int = Query(25, ge=1, le=500)):
    with cursor() as cur:
        cur.execute("""
            SELECT id, vehicle_id, vehicle_class, color, color_confidence, direction,
                   source_id, frame_number, event_time
            FROM vehicle_events ORDER BY id DESC LIMIT %s""", (limit,))
        return cur.fetchall()


@app.get("/api/timeseries")
def timeseries(minutes: int = Query(30, ge=5, le=1440)):
    with cursor() as cur:
        cur.execute("""
            WITH buckets AS (
                SELECT generate_series(date_trunc('minute', now()) - make_interval(mins => %(m)s - 1),
                                       date_trunc('minute', now()),
                                       interval '1 minute') AS bucket
            ),
            counts AS (
                SELECT date_trunc('minute', event_time) AS bucket,
                       count(*) FILTER (WHERE direction = 'in')  AS total_in,
                       count(*) FILTER (WHERE direction = 'out') AS total_out
                FROM vehicle_events
                WHERE event_time >= date_trunc('minute', now()) - make_interval(mins => %(m)s - 1)
                GROUP BY 1
            )
            SELECT b.bucket,
                   COALESCE(c.total_in, 0)  AS total_in,
                   COALESCE(c.total_out, 0) AS total_out
            FROM buckets b LEFT JOIN counts c USING (bucket)
            ORDER BY b.bucket""", {"m": minutes})
        return cur.fetchall()


@app.get("/hls/{path:path}")
def hls(path: str, request: Request):
    """
    Pass MediaMTX's HLS output (:8888) through this port, so the browser loads
    the video from the same origin as the dashboard. This is needed behind
    port-per-hostname proxies (e.g. Colab) and means only port 8000 must be reachable.
    """
    url = f"{HLS_UPSTREAM}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    try:
        with urllib.request.urlopen(url, timeout=10) as res:
            return Response(res.read(), media_type=res.headers.get("Content-Type"))
    except urllib.error.HTTPError as exc:
        raise HTTPException(exc.code, "HLS stream not available")
    except OSError:
        raise HTTPException(502, "MediaMTX not reachable")


# Serve the built React dashboard (npm run build) at "/"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="dashboard")
