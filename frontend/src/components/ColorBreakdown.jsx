import { swatch } from "../colors.js";

// Horizontal bar per colour, sorted by count (API already sorts).
export default function ColorBreakdown({ data, total }) {
  if (!data.length) return <p className="empty">No vehicles counted yet.</p>;
  const max = Math.max(...data.map((d) => d.count));

  return (
    <ul className="bars">
      {data.map((d) => (
        <li key={d.color}>
          <span className="bar-name">
            <i className="dot" style={{ background: swatch(d.color) }} />
            {d.color}
          </span>
          <span className="bar-track">
            <span
              className="bar-fill"
              style={{ width: `${(d.count / max) * 100}%`, background: swatch(d.color) }}
            />
          </span>
          <span className="bar-num mono">
            {d.count}
            <small>{total ? Math.round((d.count / total) * 100) : 0}%</small>
          </span>
        </li>
      ))}
    </ul>
  );
}
