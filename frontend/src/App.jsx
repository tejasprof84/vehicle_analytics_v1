import { useCallback, useEffect, useRef, useState } from "react";
import { fetchEvents, fetchSummary, fetchTimeseries } from "./api.js";
import StatCards from "./components/StatCards.jsx";
import ColorBreakdown from "./components/ColorBreakdown.jsx";
import TrafficChart from "./components/TrafficChart.jsx";
import EventsTable from "./components/EventsTable.jsx";
import LivePlayer from "./components/LivePlayer.jsx";

const RANGES = [
  { label: "15 min", minutes: 15 },
  { label: "1 hour", minutes: 60 },
  { label: "24 hours", minutes: 1440 },
  { label: "All time", minutes: 0 },
];
const LIVE_POLL_MS = 1000; // metrics + table
const CHART_POLL_MS = 5000; // per-minute history

// Poll an async function every `ms` while the component is mounted.
function usePolling(fn, ms, deps) {
  useEffect(() => {
    let alive = true;
    const tick = () =>
      fn()
        .catch(() => {})
        .finally(() => alive && (timer = setTimeout(tick, ms)));
    let timer = setTimeout(tick, 0);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export default function App() {
  const [range, setRange] = useState(RANGES[3]);
  const [summary, setSummary] = useState(null);
  const [events, setEvents] = useState([]);
  const [series, setSeries] = useState([]);
  const [online, setOnline] = useState(true);
  const [newIds, setNewIds] = useState(new Set());
  const lastTopId = useRef(null);

  const loadLive = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([fetchSummary(range.minutes), fetchEvents(25)]);
      setSummary(s);
      // highlight rows that arrived since the previous poll
      if (lastTopId.current !== null) {
        setNewIds(new Set(e.filter((r) => r.id > lastTopId.current).map((r) => r.id)));
      }
      lastTopId.current = e.length ? e[0].id : (lastTopId.current ?? 0);
      setEvents(e);
      setOnline(true);
    } catch (err) {
      setOnline(false);
      throw err;
    }
  }, [range.minutes]);

  const loadChart = useCallback(async () => {
    const minutes = range.minutes === 0 || range.minutes > 120 ? 60 : Math.max(range.minutes, 15);
    setSeries(await fetchTimeseries(minutes));
  }, [range.minutes]);

  usePolling(loadLive, LIVE_POLL_MS, [loadLive]);
  usePolling(loadChart, CHART_POLL_MS, [loadChart]);

  const live =
    online && summary?.last_event && Date.now() - new Date(summary.last_event).getTime() < 60_000;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            ▚
          </span>
          <div>
            <h1>Vehicle Analytics</h1>
            <p className="sub">MediaMTX · DeepStream · PostgreSQL</p>
          </div>
        </div>
        <div className="topbar-right">
          <div className="range" role="tablist" aria-label="Time range">
            {RANGES.map((r) => (
              <button
                key={r.label}
                role="tab"
                aria-selected={r.label === range.label}
                className={r.label === range.label ? "active" : ""}
                onClick={() => setRange(r)}
              >
                {r.label}
              </button>
            ))}
          </div>
          <span className={`status ${!online ? "down" : live ? "live" : "idle"}`}>
            <i />
            {!online ? "API offline" : live ? "Live" : "Waiting for traffic"}
          </span>
        </div>
      </header>

      <StatCards summary={summary} rangeLabel={range.label} />

      <main className="grid">
        <section className="panel video">
          <div className="panel-head">
            <h2>Live feed</h2>
            <span className="hint">annotated by DeepStream · HLS</span>
          </div>
          <LivePlayer />
        </section>

        <section className="panel colors">
          <div className="panel-head">
            <h2>By colour</h2>
            <span className="hint">{range.label}</span>
          </div>
          <ColorBreakdown data={summary?.by_color || []} total={summary?.total || 0} />
        </section>

        <section className="panel chart">
          <div className="panel-head">
            <h2>Vehicles per minute</h2>
            <span className="legend">
              <i className="in" /> in <i className="out" /> out
            </span>
          </div>
          <TrafficChart data={series} />
        </section>

        <section className="panel table">
          <div className="panel-head">
            <h2>Latest crossings</h2>
            <span className="hint">newest first · updates every second</span>
          </div>
          <EventsTable rows={events} highlight={newIds} />
        </section>
      </main>
    </div>
  );
}
