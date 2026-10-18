import React from 'react';

export function riskColor(risk) {
  if (risk === 'CRITICAL') return '#e05c5c';
  if (risk === 'HIGH') return '#e05c5c';
  if (risk === 'MEDIUM') return '#d8a93d';
  return '#3fb97f';
}

export function statusColor(status) {
  if (status === 'AVAILABLE') return '#3fb97f';
  if (status === 'AT_RISK') return '#e05c5c';
  if (status === 'DEGRADED') return '#d8a93d';
  if (status === 'MAINTENANCE') return '#4f9cf0';
  return '#8b94a3';
}

export function Badge({ children, color }) {
  return (
    <span className="ops-badge" style={{ background: color + '22', color, border: `1px solid ${color}55` }}>
      {children}
    </span>
  );
}

export function KpiCard({ label, value, sub, accent }) {
  return (
    <div className="ops-card ops-kpi-card">
      <div className="ops-label">{label}</div>
      <div style={{ fontSize: 30, fontWeight: 800, marginTop: 4, color: accent || '#e6e9ee' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export function HealthBar({ score }) {
  const c = score < 60 ? '#e05c5c' : score < 80 ? '#d8a93d' : '#3fb97f';
  return (
    <div style={{ background: '#0a0e13', borderRadius: 6, height: 8, overflow: 'hidden', border: '1px solid #2a3444' }}>
      <div style={{ width: score + '%', height: '100%', background: c }} />
    </div>
  );
}

// Simple illustrative degradation trend (POC) — not sensor data.
export function HealthChart({ trend, caption = 'illustrative trend' }) {
  if (!trend || !trend.length) return null;
  const w = 420, h = 110, pad = 12;
  const min = Math.min(...trend) - 5, max = Math.max(...trend) + 5;
  const pts = trend.map((v, i) => {
    const x = pad + (i / (trend.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / (max - min)) * (h - pad * 2);
    return [x, y, v];
  });
  const d = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const last = pts[pts.length - 1];
  const col = last[2] < 60 ? '#e05c5c' : last[2] < 80 ? '#d8a93d' : '#3fb97f';
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: 130, background: '#0a0e13', border: '1px solid #2a3444', borderRadius: 8 }}>
      <path d={d} fill="none" stroke={col} strokeWidth="2.5" />
      {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="3" fill={col} opacity={i === pts.length - 1 ? 1 : 0.45} />)}
      <text x={last[0] - 34} y={last[1] - 10} fill={col} fontSize="13" fontWeight="800">{last[2]}%</text>
      <text x={pad} y={h - 2} fill="#8b94a3" fontSize="9">Sample order · {caption}</text>
    </svg>
  );
}

export function SectionTitle({ children, right }) {
  return (
    <div className="ops-section-title">
      <div className="ops-label ops-section-label">{children}</div>
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
  return <div style={{ padding: 18, fontSize: 13, color: '#8b94a3', textAlign: 'center' }}>{children}</div>;
}

export function Loading({ children = 'Loading…' }) {
  return <div style={{ padding: 18, fontSize: 13, color: '#8b94a3' }}>{children}</div>;
}

export function DataError({ error, children = 'Data unavailable.' }) {
  return (
    <div role="alert" className="ops-card" style={{ padding: 16, color: '#e05c5c', fontSize: 13 }}>
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
          <tr style={{ textAlign: 'left', color: '#8b94a3', fontSize: 11 }}>
            {columns.map(c => (
              <th key={c.key} style={{ width: c.width, textAlign: c.align || 'left', whiteSpace: 'nowrap' }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={rowKey ? r[rowKey] : i}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={onRowClick ? 'ops-table-row is-clickable' : 'ops-table-row'}
              style={{ cursor: onRowClick ? 'pointer' : 'default' }}
            >
              {columns.map(c => (
                <td key={c.key} style={{ textAlign: c.align || 'left' }}>
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

// Text input / select styled to match the dark ops theme.
export const inputStyle = {
  background: '#151b24', color: '#e6e9ee', border: '1px solid #2a3444',
  borderRadius: 6, padding: '6px 9px', fontSize: 13,
};

export function SearchInput({ value, onChange, placeholder }) {
  return (
    <input
      className="ops-control ops-search-input"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
    />
  );
}

export function Select({ value, onChange, options, label, id, required }) {
  return (
    <select id={id} required={required} className="ops-control" value={value} onChange={e => onChange(e.target.value)}>
      {label && <option value="">{label}</option>}
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

// `type` defaults to "button" so a button placed inside a <form> never
// triggers an implicit submit alongside its own onClick.
export function ActionButton({ children, onClick, primary, disabled, small, type = 'button' }) {
  return (
    <button
      className={`ops-button${primary ? ' is-primary' : ''}${small ? ' is-small' : ''}`}
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={
        primary
          ? { background: disabled ? '#6b5a2a' : '#d8a93d', border: 'none', color: '#111', fontWeight: 800, borderRadius: 7, padding: small ? '4px 10px' : '8px 14px', cursor: disabled ? 'default' : 'pointer', fontSize: small ? 12 : 13 }
          : { background: '#1c2431', border: '1px solid #2a3444', color: '#e6e9ee', borderRadius: 7, padding: small ? '4px 10px' : '8px 14px', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.5 : 1, fontSize: small ? 12 : 13 }
      }
    >
      {children}
    </button>
  );
}

export function StatusMsg({ children }) {
  if (!children) return null;
  return <div style={{ marginTop: 10, fontSize: 13, color: '#d8a93d' }}>{children}</div>;
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
