import React from 'react';
import RoleSelect from './components/RoleSelect.jsx';
import { Shell, navFor } from './components/Shell.jsx';
import { api } from './services/api.js';
import Commander from './pages/Commander.jsx';
import BaseManager from './pages/BaseManager.jsx';
import Logistics from './pages/Logistics.jsx';
import AircraftDetail from './pages/AircraftDetail.jsx';

import FleetView from './pages/views/FleetView.jsx';
import BasesView from './pages/views/BasesView.jsx';
import AircraftView from './pages/views/AircraftView.jsx';
import MaintenanceView from './pages/views/MaintenanceView.jsx';
import ResourcesView from './pages/views/ResourcesView.jsx';
import RecommendationsView from './pages/views/RecommendationsView.jsx';

import MyBaseView from './pages/views/MyBaseView.jsx';
import BaseAircraftView from './pages/views/BaseAircraftView.jsx';
import BaseMaintenanceView from './pages/views/BaseMaintenanceView.jsx';
import BaseResourcesView from './pages/views/BaseResourcesView.jsx';

import InventoryView from './pages/views/InventoryView.jsx';
import ComponentsView from './pages/views/ComponentsView.jsx';
import TransfersView from './pages/views/TransfersView.jsx';
import MaintenanceResourcesView from './pages/views/MaintenanceResourcesView.jsx';
import LogisticsBasesView from './pages/views/LogisticsBasesView.jsx';

// Each sidebar item maps to its own component. Keys match `NAV` in Shell.jsx.
const VIEWS = {
  commander: {
    dashboard: Commander,
    fleet: FleetView,
    bases: BasesView,
    aircraft: AircraftView,
    maintenance: MaintenanceView,
    resources: ResourcesView,
    recommendations: RecommendationsView,
  },
  base: {
    dashboard: BaseManager,
    mybase: MyBaseView,
    aircraft: BaseAircraftView,
    maintenance: BaseMaintenanceView,
    resources: BaseResourcesView,
  },
  logistics: {
    dashboard: Logistics,
    inventory: InventoryView,
    components: ComponentsView,
    transfers: TransfersView,
    mxresources: MaintenanceResourcesView,
    bases: LogisticsBasesView,
  },
};

export default function App() {
  const [role, setRole] = React.useState(null);
  const [homeBase, setHomeBase] = React.useState('alpha');
  const [view, setView] = React.useState('dashboard');
  const [openAircraft, setOpenAircraft] = React.useState(null);
  const [focusBase, setFocusBase] = React.useState('');
  const [refreshKey, setRefreshKey] = React.useState(0);
  const [resetMsg, setResetMsg] = React.useState('');
  const refresh = React.useCallback(() => setRefreshKey(k => k + 1), []);

  api.setDemoContext(role, homeBase);

  if (!role) {
    return (
      <RoleSelect onSelect={(r, b) => { setRole(r); setHomeBase(b || 'alpha'); setView('dashboard'); }} />
    );
  }

  const goAircraft = (id) => setOpenAircraft(id);

  // Guard: if the current view isn't valid for this role, fall back to dashboard.
  const map = VIEWS[role] || VIEWS.commander;
  const valid = navFor(role).some(i => i.key === view);
  const active = valid ? view : 'dashboard';
  const View = map[active] || map.dashboard;

  const common = { onOpenAircraft: goAircraft, refreshKey, refresh };

  // Role-specific props. Bases → drill down into that base's aircraft.
  const extra = {};
  if (role === 'base') extra.homeBase = homeBase;
  if (role === 'commander') {
    extra.focusBase = focusBase;
    extra.onOpenBaseAircraft = (id) => { setFocusBase(id); setView('aircraft'); };
  }

  let content;
  if (openAircraft) {
    content = <AircraftDetail id={openAircraft} role={role} homeBase={homeBase} onBack={() => setOpenAircraft(null)} refresh={refresh} refreshKey={refreshKey} />;
  } else {
    content = <View {...common} {...extra} />;
  }

  const activeLabel = (navFor(role).find(i => i.key === active) || {}).label || '';

  return (
    <Shell
      role={role}
      view={active}
      setView={(v) => { setView(v); setOpenAircraft(null); }}
      onRole={() => { setRole(null); setOpenAircraft(null); }}
      onOpenAircraft={goAircraft}
      resetMsg={resetMsg}
      onReset={async () => {
        setResetMsg('Resetting demo data…');
        try { await api.resetDemo(); setResetMsg('Demo data reset.'); refresh(); }
        catch (e) { setResetMsg(e?.message || 'Demo reset failed.'); }
      }}
    >
      {role === 'base' && !openAircraft && (
        <div style={{ marginBottom: 12, fontSize: 12, color: '#8b94a3' }}>
          Home base:{' '}
          <select
            value={homeBase}
            onChange={e => { setHomeBase(e.target.value); setOpenAircraft(null); }}
            style={{ background: '#151b24', color: '#e6e9ee', border: '1px solid #2a3444', borderRadius: 6, padding: '4px 8px' }}
          >
            <option value="alpha">Base Alpha</option>
            <option value="bravo">Base Bravo</option>
            <option value="charlie">Base Charlie</option>
          </select>
          <span style={{ marginLeft: 10 }}>— {activeLabel} view</span>
        </div>
      )}
      {content}
    </Shell>
  );
}
