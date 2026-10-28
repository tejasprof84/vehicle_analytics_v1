import { swatch } from "../colors.js";

const fmt = (n) => (n ?? 0).toLocaleString();

export default function StatCards({ summary, rangeLabel }) {
  const top = summary?.by_color?.find((c) => c.color !== "unknown");
  const last = summary?.last_event ? new Date(summary.last_event).toLocaleTimeString() : "—";

  return (
    <section className="stats">
      <div className="stat primary">
        <span className="label">Total vehicles · {rangeLabel}</span>
        <span className="value">{fmt(summary?.total)}</span>
      </div>
      <div className="stat">
        <span className="label">Direction in</span>
        <span className="value in">{fmt(summary?.total_in)}</span>
      </div>
      <div className="stat">
        <span className="label">Direction out</span>
        <span className="value out">{fmt(summary?.total_out)}</span>
      </div>
      <div className="stat">
        <span className="label">Last 60 s</span>
        <span className="value">{fmt(summary?.last_minute)}</span>
      </div>
      <div className="stat">
        <span className="label">Most common colour</span>
        <span className="value small">
          {top ? (
            <>
              <i className="dot" style={{ background: swatch(top.color) }} />
              {top.color}
            </>
          ) : (
            "—"
          )}
        </span>
      </div>
      <div className="stat">
        <span className="label">Last crossing</span>
        <span className="value small mono">{last}</span>
      </div>
    </section>
  );
}
