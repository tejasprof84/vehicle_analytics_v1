import { swatch } from "../colors.js";

export default function EventsTable({ rows, highlight }) {
  if (!rows.length) return <p className="empty">Waiting for the first line crossing…</p>;

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Time</th>
            <th>Vehicle ID</th>
            <th>Colour</th>
            <th>Conf.</th>
            <th>Direction</th>
            <th>Frame</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={highlight.has(r.id) ? "new" : ""}>
              <td className="mono dim">{r.id}</td>
              <td className="mono">
                {new Date(r.event_time).toLocaleTimeString([], { hour12: false })}
                <span className="dim">
                  .{String(new Date(r.event_time).getMilliseconds()).padStart(3, "0")}
                </span>
              </td>
              <td className="mono">{r.vehicle_id}</td>
              <td>
                <i className="dot" style={{ background: swatch(r.color) }} />
                {r.color}
              </td>
              <td className="mono dim">
                {r.color_confidence != null ? `${Math.round(r.color_confidence * 100)}%` : "—"}
              </td>
              <td>
                <span className={`pill ${r.direction}`}>{r.direction}</span>
              </td>
              <td className="mono dim">{r.frame_number ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
