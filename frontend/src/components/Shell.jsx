import React from 'react';
import { api } from '../services/api.js';
import { C } from '../theme.js';

// Sidebar menu per role. `key` is the stable view id used for routing;
// `label` is what the user sees. Keys are unique per role.
export const NAV = {
  commander: [
    { key: 'dashboard', label: 'Dashboard' },
    { key: 'fleet', label: 'Fleet' },
    { key: 'bases', label: 'Bases' },
    { key: 'aircraft', label: 'Aircraft' },
    { key: 'maintenance', label: 'Maintenance' },
    { key: 'resources', label: 'Resources' },
    { key: 'recommendations', label: 'Recommendations' },
    { key: 'docs', label: 'Documentation' },
  ],
  base: [
    { key: 'dashboard', label: 'Dashboard' },
    { key: 'mybase', label: 'My Base' },
    { key: 'aircraft', label: 'Aircraft' },
    { key: 'maintenance', label: 'Maintenance' },
    { key: 'resources', label: 'Resources' },
    { key: 'docs', label: 'Documentation' },
  ],
  logistics: [
    { key: 'dashboard', label: 'Dashboard' },
    { key: 'inventory', label: 'Inventory' },
    { key: 'components', label: 'Components' },
    { key: 'transfers', label: 'Transfers' },
    { key: 'mxresources', label: 'Maintenance Resources' },
    { key: 'bases', label: 'Bases' },
    { key: 'docs', label: 'Documentation' },
  ],
};

export function navFor(role) {
  return NAV[role] || NAV.commander;
}

const ROLE_LABEL = {
  commander: 'Fleet Commander',
  base: 'Base Manager',
  logistics: 'Logistics Officer',
};

function zuluTime(d) {
  return d.toISOString().slice(11, 16).replace(':', '') + 'Z';
}

export function Shell({ role, onRole, view, setView, onOpenAircraft, children, onReset, resetMsg }) {
  const items = navFor(role);
  const [connectionStatus, setConnectionStatus] = React.useState(() => api.getConnectionStatus());
  const [now, setNow] = React.useState(() => new Date());
  React.useEffect(() => {
    const timer = setInterval(() => { setConnectionStatus(api.getConnectionStatus()); setNow(new Date()); }, 500);
    return () => clearInterval(timer);
  }, []);
  const path = connectionStatus?.url ? String(connectionStatus.url).replace(/^https?:\/\/[^/]+/, '') : '';
  const responseLabel = connectionStatus?.url
    ? connectionStatus.ok
      ? `Last API response HTTP ${connectionStatus.status} · ${path}`
      : connectionStatus.status
        ? `API responded HTTP ${connectionStatus.status} · ${path}`
        : `No API response · ${path}`
    : 'No API response recorded';
  const linkState = !connectionStatus?.url ? '' : connectionStatus.ok ? ' is-ok' : ' is-bad';
  const activeLabel = (items.find(i => i.key === view) || {}).label || '';

  return (
    <div className="ops-shell">
      <aside className="ops-sidebar">
        <div className="ops-brand">
          <div className="ops-brand-name">Fleet<br />Readiness</div>
          <div className="ops-brand-sub">Aircraft sustainment platform</div>
        </div>
        <div className="ops-label ops-role-label">{ROLE_LABEL[role] || role}</div>
        <nav className="ops-nav-list" aria-label="Primary navigation">
          {items.map(i => (
            <button key={i.key} onClick={() => setView(i.key)}
              className={`ops-nav-item${view === i.key ? ' is-active' : ''}`}
              aria-current={view === i.key ? 'page' : undefined}>
              {i.label}
            </button>
          ))}
        </nav>
        <div className="ops-sidebar-footer">
          <div className="ops-sidebar-note">
            Demo role: <b>{ROLE_LABEL[role] || role}</b>
          </div>
          {role === 'commander' && <button className="ops-button is-small is-quiet" onClick={onReset} style={{ justifyContent: 'flex-start' }}>Reset demo</button>}
          {role === 'commander' && resetMsg && <div role="status" style={{ fontSize: 11.5, color: C.warn, padding: '0 2px' }}>{resetMsg}</div>}
          <button className="ops-button is-small" onClick={onRole}>Switch role</button>
        </div>
      </aside>
      <div className="ops-main-wrap">
        <header className="ops-topbar">
          <div className="ops-crumbs">
            <span>{ROLE_LABEL[role] || role}</span>
            <span aria-hidden="true">/</span>
            <b>{activeLabel}</b>
          </div>
          <div className="ops-topbar-status">
            <span className="ops-link-status" title={connectionStatus?.url || ''}>
              <span className={`ops-link-dot${linkState}`} aria-hidden="true" />
              {responseLabel}{connectionStatus?.at ? ` · ${new Date(connectionStatus.at).toLocaleTimeString()}` : ''}
            </span>
            <span className="ops-zulu" title="Coordinated Universal Time">{zuluTime(now)}</span>
          </div>
        </header>
        <main className="ops-main">
          {children}
        </main>
      </div>
    </div>
  );
}

export function FleetBanner({ fleet }) {
  if (!fleet) return null;
  return (
    <div className="ops-card ops-callout" style={{ '--callout': C.hud, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div className="ops-label">Fleet availability — north-star metric</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginTop: 6 }}>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 52, fontWeight: 700, lineHeight: 0.9, color: C.hud }}>{fleet.availability_pct}%</span>
            <span style={{ fontSize: 13, color: C.muted }}>{fleet.available}/{fleet.total} available · {fleet.maintenance} in maintenance · {fleet.high_risk} high-risk</span>
          </div>
        </div>
        <div style={{ fontSize: 12.5, color: C.muted, maxWidth: 300 }}>
          Objective: <b style={{ color: C.text }}>maximize aircraft availability</b>. Turn predictive intelligence into operational decisions.
        </div>
      </div>
    </div>
  );
}
