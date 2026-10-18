import React from 'react';
import { api, baseName, healthScoreText, rulText } from '../services/api.js';
import { Badge, DataError, KpiCard, SectionTitle, riskColor, statusColor } from '../components/ui.jsx';

export default function BaseManager({ homeBase, onOpenAircraft, refreshKey }) {
  const [aircraft, setAircraft] = React.useState([]);
  const [fleet, setFleet] = React.useState(null);
  const [loadError, setLoadError] = React.useState(null);

  React.useEffect(() => {
    (async () => {
      setLoadError(null);
      setAircraft([]);
      setFleet(null);
      try {
        const [allAircraft, nextFleet] = await Promise.all([api.getAircraft(), api.getFleet()]);
        setAircraft(allAircraft.filter(a => a.base_id === homeBase));
        setFleet(nextFleet);
      } catch (e) { setLoadError(e); }
    })();
  }, [homeBase, refreshKey]);

  const b = (fleet?.bases || []).find(x => x.id === homeBase);
  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 800 }}>{baseName(homeBase)} — Aircraft Readiness</h2>
      <p style={{ color: '#8b94a3', fontSize: 13 }}>Base → Aircraft → Subsystem health → maintenance. Health values arrive from the ML API, not manual entry.</p>
      {loadError && <DataError error={loadError}>Base aircraft predictions are unavailable from the selected ML provider.</DataError>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginTop: 12 }}>
        <KpiCard label="Base Readiness" value={(b ? b.availability_pct : '—') + '%'} accent="#d8a93d" />
        <KpiCard label="Aircraft" value={aircraft.length} />
        <KpiCard label="At Risk" value={aircraft.filter(a => ['AT_RISK', 'DEGRADED'].includes(a.status)).length} accent="#e05c5c" />
      </div>
      <SectionTitle>Aircraft at {baseName(homeBase)}</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 12 }}>
        {aircraft.map(a => (
          <button key={a.id} onClick={() => onOpenAircraft(a.id)} style={{ textAlign: 'left', cursor: 'pointer', background: '#151b24', border: '1px solid #2a3444', borderRadius: 10, padding: 14, color: '#e6e9ee' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <b style={{ fontSize: 17 }}>{a.id}</b>
              <Badge color={statusColor(a.status)}>{a.status.replace('_', ' ')}</Badge>
            </div>
            <div style={{ fontSize: 12, color: '#8b94a3' }}>{a.type}</div>
            {a.health && (
              <div style={{ fontSize: 13, marginTop: 8 }}>
                Health <b style={{ color: riskColor(a.health.risk_level) }}>{healthScoreText(a.health)}</b> · {a.health.risk_level} · RUL {rulText(a.health)}
                {(a.health.required_component || a.required_component) && <div style={{ marginTop: 4 }}>Needs: <b>{a.health.required_component || a.required_component}</b></div>}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
