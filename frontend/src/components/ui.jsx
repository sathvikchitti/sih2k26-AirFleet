import React from 'react';
import { C } from '../theme.js';
import { AXIS_FONT, ChartTooltip, TipRow, useMeasuredWidth, useNearestIndex } from './charts.jsx';

export function riskColor(risk) {
  if (risk === 'CRITICAL') return C.crit;
  if (risk === 'HIGH') return C.crit;
  if (risk === 'MEDIUM') return C.warn;
  return C.ok;
}

// One colour language for every status the app shows: aircraft, inventory
// lines, transfers and work orders.
const STATUS_COLOR = {
  AVAILABLE: C.ok, RECEIVED: C.ok, COMPLETED: C.ok, SERVICEABLE: C.ok, COVERED: C.ok,
  AT_RISK: C.crit, WAITING_FOR_PART: C.crit, UNAVAILABLE: C.crit, STOCKOUT: C.crit,
  WAITING_FOR_COMPONENT: C.crit, REJECTED: C.crit, SHORTAGE: C.crit,
  DEGRADED: C.warn, LOW_STOCK: C.warn, PENDING_APPROVAL: C.warn, AWAITING_DELIVERY: C.warn, RESERVED: C.warn,
  MAINTENANCE: C.info, IN_TRANSIT: C.info, IN_PROGRESS: C.info, READY_TO_START: C.info, APPROVED: C.info,
  SCHEDULED: C.muted, NOT_STOCKED: C.dim, CANCELLED: C.dim, CANCELED: C.dim,
};

export function statusColor(status) {
  return STATUS_COLOR[String(status || '').toUpperCase()] || C.muted;
}

// Work-order priority: CRITICAL/HIGH are alarms, MEDIUM is caution, the rest neutral.
export function priorityColor(priority) {
  const p = String(priority || '').toUpperCase();
  if (p === 'CRITICAL' || p === 'HIGH' || p === 'URGENT') return C.crit;
  if (p === 'MEDIUM') return C.warn;
  return C.muted;
}

// Annunciator-style badge: square lamp + caption, tinted by `color`.
export function Badge({ children, color = C.muted }) {
  return (
    <span
      className="ops-badge"
      style={{
        color,
        background: `color-mix(in srgb, ${color} 10%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 38%, transparent)`,
      }}
    >
      {children}
    </span>
  );
}

export function KpiCard({ label, value, sub, accent }) {
  return (
    <div className="ops-kpi-card" style={accent ? { '--kpi-accent': accent } : undefined}>
      <div className="ops-label">{label}</div>
      <div className="ops-kpi-value" style={accent ? { color: accent } : undefined}>{value}</div>
      {sub && <div className="ops-kpi-sub">{sub}</div>}
    </div>
  );
}

// Segmented meter: the fill carries severity, the unfilled track is a faint
// step of the same colour, segments read like a HUD tape.
export function HealthBar({ score }) {
  const c = score < 60 ? C.crit : score < 80 ? C.warn : C.ok;
  const pct = Math.max(0, Math.min(100, Number(score) || 0));
  return (
    <div className="ops-health-bar" role="img" aria-label={`Health ${score}%`} style={{ background: `color-mix(in srgb, ${c} 14%, transparent)` }}>
      <div style={{ width: pct + '%', background: c }} />
    </div>
  );
}

// Inline readout for table cells: value plus a short segmented bar.
export function MiniMeter({ pct, color = C.ok }) {
  const v = Number.isFinite(Number(pct)) ? Math.max(0, Math.min(100, Number(pct))) : null;
  return (
    <span className="ops-mini-meter">
      <span className="ops-mini-meter-track" style={{ background: `color-mix(in srgb, ${color} 16%, transparent)` }}>
        {v != null && <span style={{ width: v + '%', background: color }} />}
      </span>
      <b style={{ color: v == null ? C.muted : C.text }}>{v == null ? '—' : `${pct}%`}</b>
    </span>
  );
}

// Health trend with the backend risk bands shaded behind the line.
export function HealthChart({ trend, caption = 'illustrative trend' }) {
  const values = (trend || []).map(Number).filter(Number.isFinite);
  const [frameRef, measured] = useMeasuredWidth(520);
  const width = Math.max(280, measured), height = 200, left = 36, right = 52, top = 12, bottom = 26;
  const x = i => left + (values.length > 1 ? i / (values.length - 1) : 0.5) * (width - left - right);
  const y = v => top + (1 - Math.max(0, Math.min(100, v)) / 100) * (height - top - bottom);
  const xs = values.map((_, i) => x(i));
  const [hover, onMove, onLeave] = useNearestIndex(xs, width);
  const gradId = React.useId().replace(/:/g, '');
  if (!values.length) return null;
  const last = values[values.length - 1];
  const col = last < 60 ? C.crit : last < 80 ? C.warn : C.ok;
  const line = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const area = `${line} L${x(values.length - 1).toFixed(1)} ${y(0)} L${x(0).toFixed(1)} ${y(0)} Z`;
  return (
    <div className="ops-chart-frame" ref={frameRef}>
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} className="ops-chart-svg ops-chart-well" role="img" aria-label={`Health trend over ${values.length} samples, latest ${last}%`}>
        <defs>
          <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor={col} stopOpacity="0.12" />
            <stop offset="1" stopColor={col} stopOpacity="0" />
          </linearGradient>
        </defs>
        <rect x={left} y={y(60)} width={width - left - right} height={y(0) - y(60)} fill={C.crit} opacity="0.06" />
        <rect x={left} y={y(80)} width={width - left - right} height={y(60) - y(80)} fill={C.warn} opacity="0.05" />
        {[0, 20, 40, 60, 80, 100].map(t => (
          <g key={t}>
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke={C.line} />
            <text x={left - 8} y={y(t) + 3} textAnchor="end" fill={t === 60 || t === 80 ? C.text2 : C.muted} {...AXIS_FONT}>{t}</text>
          </g>
        ))}
        <path d={area} fill={`url(#${gradId})`} />
        <path d={line} fill="none" stroke={col} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(values.length - 1)} cy={y(last)} r="4.5" fill={col} stroke={C.deck} strokeWidth="2" />
        <text x={x(values.length - 1) + 10} y={y(last) + 4} fill={C.text} fontFamily="var(--font-mono)" fontSize="12" fontWeight="700">{last}%</text>
        <text x={left} y={height - 8} fill={C.muted} {...AXIS_FONT}>Sample 1</text>
        <text x={width - right} y={height - 8} textAnchor="end" fill={C.muted} {...AXIS_FONT}>Sample {values.length} · {caption}</text>
        {hover != null && (
          <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1={top} y2={y(0)} stroke={C.text2} />
            <circle cx={x(hover)} cy={y(values[hover])} r="4.5" fill={col} stroke={C.deck} strokeWidth="2" />
          </g>
        )}
        <rect x={left} y={top} width={width - left - right} height={y(0) - top} fill="transparent" onMouseMove={onMove} onMouseLeave={onLeave} />
      </svg>
      {hover != null && (
        <ChartTooltip xPct={(x(hover) / width) * 100}>
          <div className="ops-chart-tip-title">Sample {hover + 1}</div>
          <TipRow color={col} label="Health" value={`${values[hover]}%`} />
        </ChartTooltip>
      )}
      <div className="ops-legend" style={{ marginTop: 8 }}>
        <span className="ops-legend-item"><span className="ops-swatch" style={{ background: C.crit, opacity: 0.5 }} />Below 60 · high risk (default bands)</span>
        <span className="ops-legend-item"><span className="ops-swatch" style={{ background: C.warn, opacity: 0.5 }} />60–80 · medium risk</span>
      </div>
    </div>
  );
}

export function SectionTitle({ children, right }) {
  return (
    <div className="ops-section-title">
      <h3 className="ops-section-label">{children}</h3>
      {right}
    </div>
  );
}

export function PageHeader({ title, subtitle, right }) {
  return (
    <div className="ops-page-header">
      <div>
        <h2 className="ops-page-title">{title}</h2>
        {subtitle && <p className="ops-page-subtitle">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function Empty({ children = 'Nothing to show.' }) {
  return <div className="ops-empty">{children}</div>;
}

export function Loading({ children = 'Loading…' }) {
  return <div className="ops-loading" role="status">{children}</div>;
}

export function DataError({ error, children = 'Data unavailable.' }) {
  return (
    <div role="alert" className="ops-card ops-callout" style={{ '--callout': C.crit, padding: '14px 18px', color: C.crit, fontSize: 13 }}>
      {children}{error?.message ? <> {error.message}</> : null}
    </div>
  );
}

// Generic data table. `columns` = [{ key, label, render?, width?, align? }]
export function Table({ columns, rows, rowKey, empty, onRowClick, minWidth }) {
  if (!rows || !rows.length) return <div className="ops-card"><Empty>{empty}</Empty></div>;
  return (
    <div className="ops-card ops-table-scroll">
      <table className="ops-table" style={minWidth ? { minWidth } : undefined}>
        <thead className="ops-table-head">
          <tr>
            {columns.map(c => (
              <th key={c.key} style={{ width: c.width, textAlign: c.align || 'left' }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={rowKey ? r[rowKey] : i}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={onRowClick ? 'ops-table-row is-clickable' : 'ops-table-row'}
            >
              {columns.map(c => (
                <td key={c.key} className={c.mono ? 'ops-id' : undefined} style={{ textAlign: c.align || 'left', whiteSpace: c.nowrap ? 'nowrap' : undefined }}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Text input / select styled to match the theme (for controls that can't use
// the .ops-control class).
export const inputStyle = {
  background: C.deck, color: C.text, border: `1px solid ${C.line2}`,
  borderRadius: 2, padding: '6px 9px', fontSize: 13,
};

export function SearchInput({ value, onChange, placeholder }) {
  return (
    <input
      className="ops-control ops-search-input"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      aria-label={placeholder}
    />
  );
}

export function Select({ value, onChange, options, label, id, required }) {
  return (
    <select id={id} required={required} className="ops-control" value={value} onChange={e => onChange(e.target.value)} aria-label={label}>
      {label && <option value="">{label}</option>}
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

// `type` defaults to "button" so a button placed inside a <form> never
// triggers an implicit submit alongside its own onClick.
export function ActionButton({ children, onClick, primary, quiet, disabled, small, type = 'button' }) {
  return (
    <button
      className={`ops-button${primary ? ' is-primary' : ''}${quiet ? ' is-quiet' : ''}${small ? ' is-small' : ''}`}
      type={type}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export function StatusMsg({ children }) {
  if (!children) return null;
  return <div className="ops-status-msg" role="status">{children}</div>;
}

export function RiskBadge({ risk }) {
  return <Badge color={riskColor(risk)}>{risk} RISK</Badge>;
}

export function StatusBadge({ status, color }) {
  return <Badge color={color || statusColor(status)}>{String(status || '—').replace(/_/g, ' ')}</Badge>;
}

// Group inventory rows by part number for cross-base availability matrices.
export function stockMatrix(inventory, bases, partNumbers) {
  return partNumbers.map(pn => {
    const rows = bases.map(b => {
      const inv = inventory.find(i => i.base_id === b.id && i.part_number === pn);
      return {
        base_id: b.id,
        quantity: inv ? inv.quantity : 0,
        reserved: inv ? (inv.reserved || 0) : 0,
        condition_pct: inv ? inv.condition_pct : 0,
        status: inv ? inv.status : 'NOT_STOCKED',
      };
    });
    return {
      part_number: pn,
      rows,
      total: rows.reduce((s, r) => s + r.quantity, 0),
      availableBases: rows.filter(r => r.quantity - r.reserved > 0).length,
    };
  });
}
