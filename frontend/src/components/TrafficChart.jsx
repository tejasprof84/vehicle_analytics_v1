import { useState } from "react";

// Stacked bar chart (in + out) per minute, plain SVG - no chart library needed.
export default function TrafficChart({ data }) {
  const [hover, setHover] = useState(null);
  if (!data.length) return <p className="empty">Loading…</p>;

  const W = 640,
    H = 200,
    padL = 28,
    padB = 22,
    padT = 8;
  const max = Math.max(1, ...data.map((d) => d.total_in + d.total_out));
  const step = (W - padL) / data.length;
  const barW = Math.max(2, step - 2);
  const y = (v) => padT + (H - padT - padB) * (1 - v / max);
  const ticks = [0, Math.ceil(max / 2), max];
  const label = (t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Vehicles per minute">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W} y1={y(t)} y2={y(t)} className="gridline" />
            <text x={padL - 6} y={y(t) + 4} className="axis" textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = padL + i * step + 1;
          const inTop = y(d.total_in);
          const outTop = y(d.total_in + d.total_out);
          return (
            <g key={d.bucket} onMouseEnter={() => setHover(d)} onMouseLeave={() => setHover(null)}>
              <rect x={x} y={padT} width={barW} height={H - padT - padB} className="hit" />
              <rect x={x} y={inTop} width={barW} height={y(0) - inTop} className="bar-in" rx="1" />
              <rect
                x={x}
                y={outTop}
                width={barW}
                height={inTop - outTop}
                className="bar-out"
                rx="1"
              />
            </g>
          );
        })}
        {[0, Math.floor(data.length / 2), data.length - 1].map((i) => (
          <text
            key={i}
            x={padL + i * step + barW / 2}
            y={H - 6}
            className="axis"
            textAnchor="middle"
          >
            {label(data[i].bucket)}
          </text>
        ))}
      </svg>
      <div className="chart-tip mono">
        {hover
          ? `${label(hover.bucket)} — in ${hover.total_in}, out ${hover.total_out}`
          : "Hover a bar for details"}
      </div>
    </div>
  );
}
