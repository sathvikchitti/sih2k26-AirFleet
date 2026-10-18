import React from 'react';
import { baseName, healthScoreText, rulText, titleCase } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  Badge, DataError, Empty, HealthBar, KpiCard, Loading, PageHeader,
  SearchInput, SectionTitle, riskColor, statusColor,
} from '../../components/ui.jsx';

// Base manager — My Base: everything scoped to one base. The commander's Fleet
// view is fleet-wide; this is the single-base readiness picture a base
// commander owns end to end.
export default function MyBaseView({ homeBase, onOpenAircraft, refreshKey }) {
  const { fleet, aircraft, maintenance, inventory, loading, predictionError } = useFleetViews(refreshKey);
  const [q, setQ] = React.useState('');

  if (loading) return <Loading>Loading {baseName(homeBase)}…</Loading>;
  if (predictionError) return <DataError error={predictionError}>Base readiness predictions are unavailable from the selected ML provider.</DataError>;

  const held = (aircraft || []).filter(a => a.base_id === homeBase);
  const wos = (maintenance || []).filter(m => held.some(a => a.id === m.aircraft_id));
  const stock = (inventory || []).filter(i => i.base_id === homeBase);
  const f = (fleet?.bases || []).find(b => b.id === homeBase);

  const blocked = held.filter(a =>
    (a.health?.required_component || a.required_component) &&
    !stock.some(i => i.part_number === (a.health?.required_component || a.required_component) && i.quantity - (i.reserved || 0) > 0));

  let list = held;
  if (q) {
    const needle = q.toLowerCase();
    list = list.filter(a => String(a.id).toLowerCase().includes(needle) || String(a.type || '').toLowerCase().includes(needle));
  }

  return (
    <div>
      <PageHeader
        title={baseName(homeBase)}
        subtitle="Your base only. Base → aircraft → subsystem health → maintenance, scoped to the aircraft this base is responsible for."
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0' }}>
        <KpiCard label="Base Readiness" value={(f ? f.availability_pct : 0) + '%'} accent="#d8a93d" />
        <KpiCard label="Aircraft" value={held.length} />
        <KpiCard label="Available" value={held.filter(a => a.status === 'AVAILABLE').length} accent="#3fb97f" />
        <KpiCard label="At Risk" value={held.filter(a => ['AT_RISK', 'DEGRADED'].includes(a.status)).length} accent="#e05c5c" />
        <KpiCard label="Blocked On Parts" value={blocked.length} accent="#e05c5c" />
      </div>

      {blocked.length > 0 && (
        <div className="ops-card" style={{ padding: 14, borderLeft: '4px solid #e05c5c', marginBottom: 6 }}>
          <div className="ops-label">Attention required</div>
          <div style={{ fontSize: 14, marginTop: 6 }}>
            {blocked.length} aircraft at {baseName(homeBase)} {blocked.length === 1 ? 'needs' : 'need'} a component this base does not hold in stock:{' '}
            <b style={{ color: '#d8a93d' }}>{[...new Set(blocked.map(a => a.health?.required_component || a.required_component))].join(', ')}</b>.
            Raise a transfer request from Resources.
          </div>
        </div>
      )}

      <SectionTitle>Work orders at this base</SectionTitle>
      {wos.length === 0 ? (
        <div className="ops-card"><Empty>No maintenance work orders at this base.</Empty></div>
      ) : (
        <div className="ops-card" style={{ padding: 0, overflow: 'hidden' }}>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: '#8b94a3', fontSize: 11 }}>
                <th style={{ padding: 10 }}>WO</th><th>Aircraft</th><th>Component</th><th>Priority</th><th>Status</th><th style={{ textAlign: 'right' }}>Est. hours</th>
              </tr>
            </thead>
            <tbody>
              {wos.map(m => (
                <tr key={m.id} style={{ borderTop: '1px solid #2a3444', cursor: 'pointer' }} onClick={() => onOpenAircraft(m.aircraft_id)}>
                  <td style={{ padding: 10 }} className="font-mono">{m.id}</td>
                  <td><b>{m.aircraft_id}</b></td>
                  <td>{m.component}</td>
                  <td>{m.priority}</td>
                  <td>{titleCase(m.status)}</td>
                  <td style={{ textAlign: 'right' }}>{m.estimated_recovery_hours ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SectionTitle
        right={<SearchInput value={q} onChange={setQ} placeholder="Search aircraft…" />}
      >
        Aircraft at {baseName(homeBase)}
      </SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 12 }}>
        {list.map(a => (
          <button
            key={a.id}
            onClick={() => onOpenAircraft(a.id)}
            style={{ textAlign: 'left', cursor: 'pointer', background: '#151b24', border: '1px solid #2a3444', borderRadius: 10, padding: 14, color: '#e6e9ee' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <b style={{ fontSize: 16 }}>{a.id}</b>
              <Badge color={statusColor(a.status)}>{String(a.status).replace(/_/g, ' ')}</Badge>
            </div>
            <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 4 }}>{a.type}</div>
            {a.health && (
              <>
                <div style={{ marginTop: 10 }}><HealthBar score={a.health.health_score} /></div>
                <div style={{ fontSize: 12, marginTop: 6, color: riskColor(a.health.risk_level) }}>
                  {healthScoreText(a.health)} · {a.health.risk_level} · RUL {rulText(a.health)}
                </div>
                <div style={{ fontSize: 12, marginTop: 2 }}>
                  Needs: <b style={{ color: '#d8a93d' }}>{a.health.required_component || a.required_component || '—'}</b>
                </div>
              </>
            )}
          </button>
        ))}
        {!list.length && <div style={{ color: '#8b94a3', fontSize: 13 }}>No aircraft at this base.</div>}
      </div>
    </div>
  );
}
