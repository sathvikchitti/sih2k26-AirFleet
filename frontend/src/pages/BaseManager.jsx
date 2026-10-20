import React from 'react';
import { api, baseName, healthScoreText, rulText } from '../services/api.js';
import { Badge, DataError, HealthBar, KpiCard, PageHeader, SectionTitle, riskColor, statusColor } from '../components/ui.jsx';
import { C } from '../theme.js';

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
      <PageHeader
        title={`${baseName(homeBase)} readiness`}
        subtitle="Base → aircraft → subsystem health → maintenance. Health values arrive from the ML API, not manual entry."
      />
      {loadError && <div style={{ marginTop: 16 }}><DataError error={loadError}>Base aircraft predictions are unavailable from the selected ML provider.</DataError></div>}
      <div className="ops-kpi-grid">
        <KpiCard label="Base readiness" value={(b ? b.availability_pct : '—') + '%'} accent={b && b.availability_pct >= 85 ? C.ok : C.warn} />
        <KpiCard label="Aircraft" value={aircraft.length} />
        <KpiCard label="At risk" value={aircraft.filter(a => ['AT_RISK', 'DEGRADED'].includes(a.status)).length} accent={C.crit} />
      </div>
      <SectionTitle>Aircraft at {baseName(homeBase)}</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 12 }}>
        {aircraft.map(a => (
          <button key={a.id} onClick={() => onOpenAircraft(a.id)} className={`ops-tile${['HIGH', 'CRITICAL'].includes(a.health?.risk_level) ? ' is-alert' : ''}`}>
            <div className="ops-tile-head">
              <span className="ops-tile-title">{a.id}</span>
              <Badge color={statusColor(a.status)}>{String(a.status).replace(/_/g, ' ')}</Badge>
            </div>
            <div className="ops-tile-meta">{a.type}</div>
            {a.health && (
              <>
                {a.health.health_score != null && <div style={{ marginTop: 12 }}><HealthBar score={a.health.health_score} /></div>}
                <div style={{ fontSize: 12.5, marginTop: 8, color: C.text2 }}>
                  Health <b style={{ color: riskColor(a.health.risk_level) }}>{healthScoreText(a.health)}</b> · {a.health.risk_level} · RUL {rulText(a.health)}
                  {(a.health.required_component || a.required_component) && <div style={{ marginTop: 4 }}>Needs <b style={{ color: C.text }}>{a.health.required_component || a.required_component}</b></div>}
                </div>
              </>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
