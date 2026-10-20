import React from 'react';
import { C, CAT } from '../theme.js';

// Shared chart kit. Every chart here follows the same instrument-panel rules:
// hairline solid gridlines one step off the surface, 2px lines, end markers
// with a surface-coloured ring, text in text tokens (never the series colour),
// a legend whenever there are two or more series, and a hover readout.

export const AXIS_FONT = { fontFamily: 'var(--font-mono)', fontSize: 10 };

// Round, human tick values covering [min, max].
export function niceTicks(min, max, count = 4) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const span = max - min;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= count) || 10 * mag;
  const start = Math.ceil(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 1e-9; v += step) ticks.push(Number(v.toFixed(6)));
  return ticks;
}

export const fmt = (value, digits = 0) => (Number.isFinite(Number(value)) ? Number(value).toFixed(digits).replace(/\.0+$/, '') : '—');

// Charts draw in real pixels so axis text stays a fixed, legible size at any
// width. Server render (render-check) falls back to `fallback`.
export function useMeasuredWidth(fallback) {
  const ref = React.useRef(null);
  const [width, setWidth] = React.useState(fallback);
  React.useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(entries => {
      const w = Math.round(entries[0].contentRect.width);
      if (w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

// Pointer → nearest index. Works on the SVG's own viewBox so it scales.
export function useNearestIndex(xs, width) {
  const [index, setIndex] = React.useState(null);
  const onMove = React.useCallback(event => {
    const svg = event.currentTarget.ownerSVGElement || event.currentTarget;
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return;
    const vx = ((event.clientX - rect.left) / rect.width) * width;
    let best = 0;
    let bestDist = Infinity;
    xs.forEach((x, i) => { const d = Math.abs(x - vx); if (d < bestDist) { bestDist = d; best = i; } });
    setIndex(best);
  }, [xs, width]);
  return [index, onMove, () => setIndex(null)];
}

// Tooltip positioned in % of the chart frame so it tracks responsive SVGs.
export function ChartTooltip({ xPct, yPct = 8, children }) {
  if (xPct == null) return null;
  const flip = xPct > 62;
  return (
    <div
      className="ops-chart-tip"
      role="status"
      style={{
        left: `${xPct}%`,
        top: `${yPct}%`,
        transform: flip ? 'translateX(calc(-100% - 12px))' : 'translateX(12px)',
      }}
    >
      {children}
    </div>
  );
}

export function TipRow({ color, label, value }) {
  return (
    <div className="ops-chart-tip-row">
      {color ? <span className="ops-swatch" style={{ background: color }} /> : null}
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

export function Legend({ items }) {
  return (
    <div className="ops-legend">
      {items.map(item => (
        <span key={item.label} className="ops-legend-item">
          <span className={`ops-swatch${item.line ? ' is-line' : ''}`} style={{ background: item.color }} />
          {item.label}
          {item.note ? <span style={{ color: C.muted }}>({item.note})</span> : null}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fleet status mix — one stacked bar, status colours (state, always labelled).
// ---------------------------------------------------------------------------
const STATUS_ORDER = [
  ['AVAILABLE', 'Available', C.ok],
  ['DEGRADED', 'Degraded', C.warn],
  ['MAINTENANCE', 'Maintenance', C.info],
  ['AT_RISK', 'At risk', C.crit],
  ['WAITING_FOR_PART', 'Waiting for part', C.critDeep],
];

export function FleetStatusBar({ aircraft }) {
  const list = Array.isArray(aircraft) ? aircraft : [];
  if (!list.length) return null;
  const counts = {};
  list.forEach(a => { const s = String(a.status || 'OTHER').toUpperCase(); counts[s] = (counts[s] || 0) + 1; });
  const known = STATUS_ORDER.filter(([key]) => counts[key]);
  const other = Object.entries(counts).filter(([key]) => !STATUS_ORDER.some(([k]) => k === key)).reduce((s, [, n]) => s + n, 0);
  const segments = [...known.map(([key, label, color]) => ({ key, label, color, n: counts[key] })),
    ...(other ? [{ key: 'OTHER', label: 'Other', color: C.paint, n: other }] : [])];
  return (
    <div className="ops-statusbar">
      <div className="ops-statusbar-track" role="img" aria-label={`Fleet status: ${segments.map(s => `${s.n} ${s.label.toLowerCase()}`).join(', ')}`}>
        {segments.map(s => (
          <div key={s.key} title={`${s.label}: ${s.n}`} style={{ flexGrow: s.n, background: s.color }} />
        ))}
      </div>
      <div className="ops-legend" style={{ marginTop: 10 }}>
        {segments.map(s => (
          <span key={s.key} className="ops-legend-item">
            <span className="ops-swatch" style={{ background: s.color }} />
            {s.label} <b>{s.n}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Availability over the simulation horizon — step lines, one per policy.
// ---------------------------------------------------------------------------
export function AvailabilityCurveChart({ series, horizon, target }) {
  const valid = (series || []).filter(s => Array.isArray(s.points) && s.points.length);
  const [frameRef, measured] = useMeasuredWidth(640);
  const width = Math.max(320, measured), height = 230, left = 44, right = 20, top = 14, bottom = 28;
  const maxH = Math.max(Number(horizon) || 0, ...valid.flatMap(s => s.points.map(p => Number(p.hours) || 0)), 1);
  const x = h => left + (Number(h) / maxH) * (width - left - right);
  const y = v => top + (1 - Number(v) / 100) * (height - top - bottom);
  // Shared hour grid so the hover readout can show every policy at one time.
  const hours = [...new Set(valid.flatMap(s => s.points.map(p => Number(p.hours))).concat([maxH]))].sort((a, b) => a - b);
  const valueAt = (s, h) => {
    let v = null;
    s.points.forEach(p => { if (Number(p.hours) <= h + 1e-9) v = p; });
    return v;
  };
  const xs = hours.map(x);
  const [hover, onMove, onLeave] = useNearestIndex(xs, width);
  if (!valid.length) return null;
  const stepPath = s => {
    const pts = [...s.points].sort((a, b) => a.hours - b.hours);
    let d = `M${x(pts[0].hours)} ${y(pts[0].availability_pct)}`;
    for (let i = 1; i < pts.length; i++) d += ` H${x(pts[i].hours)} V${y(pts[i].availability_pct)}`;
    return d + ` H${x(maxH)}`;
  };
  const yTicks = [0, 25, 50, 75, 100];
  const xTicks = niceTicks(0, maxH, Math.max(3, Math.min(8, Math.floor(width / 110))));
  // A series whose curve matches a later one is drawn as a wider casing
  // underneath, so both stay visible instead of one hiding the other.
  const sig = s2 => JSON.stringify([...s2.points].sort((a, b) => a.hours - b.hours).map(p => [p.hours, p.availability_pct]));
  const overlaps = valid.map((s2, i) => valid.slice(i + 1).find(t => sig(t) === sig(s2)) || null);
  const hoverH = hover != null ? hours[hover] : null;
  return (
    <div>
      <Legend items={valid.map((s2, i) => ({ label: s2.label, color: s2.color, line: true, note: overlaps[i] ? `same curve as ${overlaps[i].label}` : null }))} />
      <div className="ops-chart-frame" ref={frameRef}>
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label="Fleet availability over the simulation horizon for each allocation policy" className="ops-chart-svg">
          {yTicks.map(t => (
            <g key={t}>
              <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke={C.line} />
              <text x={left - 8} y={y(t) + 3} textAnchor="end" fill={C.muted} {...AXIS_FONT}>{t}%</text>
            </g>
          ))}
          {xTicks.map(t => (
            <text key={t} x={x(t)} y={height - 8} textAnchor="middle" fill={C.muted} {...AXIS_FONT}>{fmt(t)}h</text>
          ))}
          {Number.isFinite(Number(target)) ? (
            <g>
              <line x1={left} x2={width - right} y1={y(target)} y2={y(target)} stroke={C.text2} strokeDasharray="1 3" />
              <text x={width - right} y={y(target) - 5} textAnchor="end" fill={C.text2} {...AXIS_FONT}>Target {fmt(target)}%</text>
            </g>
          ) : null}
          {/* Earlier series drawn wider underneath so identical curves stay visible. */}
          {valid.map((s2, i) => (
            <path key={s2.key} d={stepPath(s2)} fill="none" stroke={s2.color} strokeWidth={overlaps[i] ? 7 : 2} strokeOpacity={overlaps[i] ? 0.45 : 1} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {valid.map(s => {
            const last = valueAt(s, maxH);
            return last ? <circle key={`end-${s.key}`} cx={x(maxH)} cy={y(last.availability_pct)} r="4.5" fill={s.color} stroke={C.panel} strokeWidth="2" /> : null;
          })}
          {hoverH != null && (
            <g pointerEvents="none">
              <line x1={x(hoverH)} x2={x(hoverH)} y1={top} y2={height - bottom} stroke={C.text2} strokeWidth="1" />
              {valid.map(s => { const v = valueAt(s, hoverH); return v ? <circle key={s.key} cx={x(hoverH)} cy={y(v.availability_pct)} r="4.5" fill={s.color} stroke={C.panel} strokeWidth="2" /> : null; })}
            </g>
          )}
          <rect x={left} y={top} width={width - left - right} height={height - top - bottom} fill="transparent" onMouseMove={onMove} onMouseLeave={onLeave} />
        </svg>
        {hoverH != null && (
          <ChartTooltip xPct={(x(hoverH) / width) * 100}>
            <div className="ops-chart-tip-title">Hour {fmt(hoverH, 1)}</div>
            {valid.map(s => { const v = valueAt(s, hoverH); return <TipRow key={s.key} color={s.color} label={s.label} value={v ? `${fmt(v.availability_pct, 1)}% · ${v.available_aircraft}/${v.total_aircraft}` : '—'} />; })}
          </ChartTooltip>
        )}
      </div>
    </div>
  );
}

export { CAT };
