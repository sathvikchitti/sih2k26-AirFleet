import React from 'react';
import { api } from '../services/api.js';

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
  ],
  base: [
    { key: 'dashboard', label: 'Dashboard' },
    { key: 'mybase', label: 'My Base' },
    { key: 'aircraft', label: 'Aircraft' },
    { key: 'maintenance', label: 'Maintenance' },
    { key: 'resources', label: 'Resources' },
  ],
  logistics: [
    { key: 'dashboard', label: 'Dashboard' },
    { key: 'inventory', label: 'Inventory' },
    { key: 'components', label: 'Components' },
    { key: 'transfers', label: 'Transfers' },
    { key: 'mxresources', label: 'Maintenance Resources' },
    { key: 'bases', label: 'Bases' },
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

export function Shell({ role, onRole, view, setView, onOpenAircraft, children, onReset, resetMsg }) {
  const items = navFor(role);
  const [connectionStatus, setConnectionStatus] = React.useState(() => api.getConnectionStatus());
  React.useEffect(() => {
    const timer = setInterval(() => setConnectionStatus(api.getConnectionStatus()), 500);
    return () => clearInterval(timer);
  }, []);
  const responseLabel = connectionStatus?.url
    ? connectionStatus.ok
      ? `Last API response HTTP ${connectionStatus.status} · ${String(connectionStatus.url).replace(/^https?:\/\/[^/]+/, '')}`
      : connectionStatus.status
        ? `API responded HTTP ${connectionStatus.status} · ${String(connectionStatus.url).replace(/^https?:\/\/[^/]+/, '')}`
        : `No API response · ${String(connectionStatus.url).replace(/^https?:\/\/[^/]+/, '')}`
    : 'No API response recorded';

  return (
    <div className="ops-shell">
      <aside className="ops-sidebar">
        <div className="ops-brand">FLEET READINESS</div>
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
          <div style={{ fontSize: 11, color: '#8b94a3' }}>
            Demo role: <b style={{ color: '#e6e9ee' }}>{ROLE_LABEL[role] || role}</b>
            <div title={connectionStatus?.url || ''} style={{ marginTop: 3 }}>{responseLabel}{connectionStatus?.at ? ` · ${new Date(connectionStatus.at).toLocaleTimeString()}` : ''}</div>
          </div>
          {role === 'commander' && <button onClick={onReset} style={{ fontSize: 12, background: 'transparent', border: '1px solid #2a3444', color: '#8b94a3', borderRadius: 6, padding: '6px 8px', cursor: 'pointer' }}>Reset demo</button>}
          {role === 'commander' && resetMsg && <div role="status" style={{ fontSize: 11, color: '#d8a93d' }}>{resetMsg}</div>}
          <button onClick={onRole} style={{ fontSize: 12, background: '#1c2431', border: '1px solid #2a3444', color: '#e6e9ee', borderRadius: 6, padding: '6px 8px', cursor: 'pointer' }}>Switch role</button>
        </div>
      </aside>
      <main className="ops-main">
        {children}
      </main>
    </div>
  );
}

export function FleetBanner({ fleet }) {
  if (!fleet) return null;
  return (
    <div className="ops-card" style={{ padding: 18, marginBottom: 16, borderLeft: '4px solid #d8a93d' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div className="ops-label">Fleet availability — north-star metric</div>
          <div style={{ fontSize: 40, fontWeight: 800 }}>{fleet.availability_pct}% <span style={{ fontSize: 13, color: '#8b94a3', fontWeight: 400 }}>{fleet.available}/{fleet.total} available · {fleet.maintenance} in maintenance · {fleet.high_risk} high-risk</span></div>
        </div>
        <div style={{ fontSize: 12, color: '#8b94a3', maxWidth: 300 }}>
          Objective: <b style={{ color: '#e6e9ee' }}>maximize aircraft availability</b> — convert predictive intelligence into operational decisions.
        </div>
      </div>
    </div>
  );
}
