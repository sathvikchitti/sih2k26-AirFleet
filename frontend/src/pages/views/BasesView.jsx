import React from 'react';
import { baseName, healthScoreText, rulText } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  Badge, DataError, KpiCard, Loading, MiniMeter, PageHeader, SectionTitle, Table, riskColor, statusColor,
} from '../../components/ui.jsx';
import { C } from '../../theme.js';

// Commander — Bases: force-level view of the three bases, their readiness and
// the aircraft they hold. Clicking a base filters down to its aircraft.
export default function BasesView({ onOpenAircraft, refreshKey, onOpenBaseAircraft }) {
  const { fleet, bases, aircraft, loading, predictionError } = useFleetViews(refreshKey);

  if (predictionError) return <DataError error={predictionError}>Base readiness predictions are unavailable from the selected ML provider.</DataError>;
  if (loading || !fleet || !bases) return <Loading>Loading bases…</Loading>;

  const cols = [
    { key: 'name', label: 'Base', render: b => <b>{b.name}</b> },
    { key: 'location', label: 'Location' },
    {
      key: 'aircraft_count', label: 'Aircraft', align: 'right',
      render: b => (fleet.bases.find(f => f.id === b.id)?.aircraft_count ?? (b.aircraft || []).length),
    },
    {
      key: 'available', label: 'Available', align: 'right',
      render: b => {
        const f = fleet.bases.find(x => x.id === b.id);
        return <span style={{ color: C.ok, fontWeight: 700 }}>{f ? f.available : '—'}</span>;
      },
    },
    {
      key: 'availability_pct', label: 'Readiness', align: 'right',
      render: b => {
        const f = fleet.bases.find(x => x.id === b.id);
        const pct = f ? f.availability_pct : null;
        return (
          <MiniMeter pct={pct} color={pct >= 85 ? C.ok : pct >= 50 ? C.warn : C.crit} />
        );
      },
    },
    {
      key: 'at_risk', label: 'At Risk', align: 'right',
      render: b => {
        const f = fleet.bases.find(x => x.id === b.id);
        return <span style={{ color: C.crit }}>{f ? f.at_risk : '—'}</span>;
      },
    },
    {
      key: 'maintenance', label: 'In Mx', align: 'right',
      render: b => {
        const f = fleet.bases.find(x => x.id === b.id);
        return <span style={{ color: C.info }}>{f ? f.maintenance : '—'}</span>;
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="Bases"
        subtitle="Force-level readiness. Availability percentage is the share of the base's aircraft currently flyable — the metric the whole system is trying to maximize."
      />

      <div className="ops-kpi-grid">
        <KpiCard label="Bases" value={bases.length} />
        <KpiCard label="Fleet Readiness" value={fleet.availability_pct + '%'} accent={fleet.availability_pct >= 85 ? C.ok : C.warn} />
        <KpiCard label="Available" value={fleet.available + ' / ' + fleet.total} accent={C.ok} />
        <KpiCard label="At Risk" value={fleet.at_risk} accent={C.crit} />
      </div>

      <SectionTitle>Readiness by base</SectionTitle>
      <Table columns={cols} rows={bases} rowKey="id" empty="No bases configured." />

      {bases.map(b => {
        const held = (aircraft || []).filter(a => a.base_id === b.id);
        const f = fleet.bases.find(x => x.id === b.id);
        return (
          <div key={b.id}>
            <SectionTitle
              right={
                onOpenBaseAircraft && (
                  <button
                    onClick={() => onOpenBaseAircraft(b.id)}
                    className="ops-button is-small"
                  >
                    Open {baseName(b.id)} aircraft
                  </button>
                )
              }
            >
              {b.name} — {held.length} aircraft · {f ? f.available : 0} available
            </SectionTitle>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 12 }}>
              {held.map(a => (
                <button
                  key={a.id}
                  onClick={() => onOpenAircraft(a.id)}
                  className="ops-tile"
                >
                  <div className="ops-tile-head">
                    <span className="ops-tile-title">{a.id}</span>
                    <Badge color={statusColor(a.status)}>{String(a.status).replace(/_/g, ' ')}</Badge>
                  </div>
                  <div className="ops-tile-meta">{a.type}</div>
                  {a.health && (
                    <div style={{ fontSize: 12, marginTop: 6, color: riskColor(a.health.risk_level) }}>
                      Health <b>{healthScoreText(a.health)}</b> · {a.health.risk_level} · RUL {rulText(a.health)}
                    </div>
                  )}
                </button>
              ))}
              {!held.length && <div style={{ color: C.muted, fontSize: 13 }}>No aircraft based here.</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
