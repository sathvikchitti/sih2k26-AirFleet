import React from 'react';
import { baseName, healthScoreText, rulText } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  Badge, DataError, KpiCard, Loading, PageHeader, SectionTitle, Table, riskColor, statusColor,
} from '../../components/ui.jsx';

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
        return <span style={{ color: '#3fb97f', fontWeight: 700 }}>{f ? f.available : '—'}</span>;
      },
    },
    {
      key: 'availability_pct', label: 'Readiness', align: 'right',
      render: b => {
        const f = fleet.bases.find(x => x.id === b.id);
        const pct = f ? f.availability_pct : null;
        return (
          <span style={{ color: pct >= 85 ? '#3fb97f' : pct >= 50 ? '#d8a93d' : '#e05c5c', fontWeight: 800 }}>
            {pct != null ? pct + '%' : '—'}
          </span>
        );
      },
    },
    {
      key: 'at_risk', label: 'At Risk', align: 'right',
      render: b => {
        const f = fleet.bases.find(x => x.id === b.id);
        return <span style={{ color: '#e05c5c' }}>{f ? f.at_risk : '—'}</span>;
      },
    },
    {
      key: 'maintenance', label: 'In Mx', align: 'right',
      render: b => {
        const f = fleet.bases.find(x => x.id === b.id);
        return <span style={{ color: '#4f9cf0' }}>{f ? f.maintenance : '—'}</span>;
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="Bases"
        subtitle="Force-level readiness. Availability percentage is the share of the base's aircraft currently flyable — the metric the whole system is trying to maximize."
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0' }}>
        <KpiCard label="Bases" value={bases.length} />
        <KpiCard label="Fleet Readiness" value={fleet.availability_pct + '%'} accent="#d8a93d" />
        <KpiCard label="Available" value={fleet.available + ' / ' + fleet.total} accent="#3fb97f" />
        <KpiCard label="At Risk" value={fleet.at_risk} accent="#e05c5c" />
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
                    style={{ background: 'transparent', border: '1px solid #2a3444', color: '#c6ccd6', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 12 }}
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
                  style={{ textAlign: 'left', cursor: 'pointer', background: '#151b24', border: '1px solid #2a3444', borderRadius: 10, padding: 14, color: '#e6e9ee' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <b style={{ fontSize: 15 }}>{a.id}</b>
                    <Badge color={statusColor(a.status)}>{String(a.status).replace(/_/g, ' ')}</Badge>
                  </div>
                  <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 4 }}>{a.type}</div>
                  {a.health && (
                    <div style={{ fontSize: 12, marginTop: 6, color: riskColor(a.health.risk_level) }}>
                      Health <b>{healthScoreText(a.health)}</b> · {a.health.risk_level} · RUL {rulText(a.health)}
                    </div>
                  )}
                </button>
              ))}
              {!held.length && <div style={{ color: '#8b94a3', fontSize: 13 }}>No aircraft based here.</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
