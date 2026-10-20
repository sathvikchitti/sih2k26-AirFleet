import React from 'react';
import { baseName, healthScoreText, rulText, titleCase } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  Badge, DataError, Empty, HealthBar, KpiCard, Loading, PageHeader,
  SearchInput, SectionTitle, priorityColor, riskColor, statusColor,
} from '../../components/ui.jsx';
import { C } from '../../theme.js';

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

      <div className="ops-kpi-grid">
        <KpiCard label="Base Readiness" value={(f ? f.availability_pct : 0) + '%'} accent={f && f.availability_pct >= 85 ? C.ok : C.warn} />
        <KpiCard label="Aircraft" value={held.length} />
        <KpiCard label="Available" value={held.filter(a => a.status === 'AVAILABLE').length} accent={C.ok} />
        <KpiCard label="At Risk" value={held.filter(a => ['AT_RISK', 'DEGRADED'].includes(a.status)).length} accent={C.crit} />
        <KpiCard label="Blocked On Parts" value={blocked.length} accent={C.crit} />
      </div>

      {blocked.length > 0 && (
        <div className="ops-card ops-callout" style={{ '--callout': C.crit, padding: '14px 18px', marginBottom: 6 }}>
          <div className="ops-label">Attention required</div>
          <div style={{ fontSize: 14, marginTop: 6 }}>
            {blocked.length} aircraft at {baseName(homeBase)} {blocked.length === 1 ? 'needs' : 'need'} a component this base does not hold in stock:{' '}
            <b style={{ color: C.warn }}>{[...new Set(blocked.map(a => a.health?.required_component || a.required_component))].join(', ')}</b>.
            Raise a transfer request from Resources.
          </div>
        </div>
      )}

      <SectionTitle>Work orders at this base</SectionTitle>
      {wos.length === 0 ? (
        <div className="ops-card"><Empty>No maintenance work orders at this base.</Empty></div>
      ) : (
        <div className="ops-card ops-table-scroll">
          <table className="ops-table" style={{ minWidth: 600 }}>
            <thead>
              <tr>
                <th>WO</th><th>Aircraft</th><th>Component</th><th>Priority</th><th>Status</th><th style={{ textAlign: 'right' }}>Est. hours</th>
              </tr>
            </thead>
            <tbody>
              {wos.map(m => (
                <tr key={m.id} className="ops-table-row is-clickable" onClick={() => onOpenAircraft(m.aircraft_id)}>
                  <td className="ops-id">{m.id}</td>
                  <td><b className="ops-id">{m.aircraft_id}</b></td>
                  <td>{m.component}</td>
                  <td><Badge color={priorityColor(m.priority)}>{m.priority}</Badge></td>
                  <td><Badge color={statusColor(m.status)}>{titleCase(m.status)}</Badge></td>
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
            className="ops-tile"
          >
            <div className="ops-tile-head">
              <span className="ops-tile-title">{a.id}</span>
              <Badge color={statusColor(a.status)}>{String(a.status).replace(/_/g, ' ')}</Badge>
            </div>
            <div className="ops-tile-meta">{a.type}</div>
            {a.health && (
              <>
                <div style={{ marginTop: 10 }}><HealthBar score={a.health.health_score} /></div>
                <div style={{ fontSize: 12, marginTop: 6, color: riskColor(a.health.risk_level) }}>
                  {healthScoreText(a.health)} · {a.health.risk_level} · RUL {rulText(a.health)}
                </div>
                <div style={{ fontSize: 12, marginTop: 2 }}>
                  Needs: <b style={{ color: C.warn }}>{a.health.required_component || a.required_component || '—'}</b>
                </div>
              </>
            )}
          </button>
        ))}
        {!list.length && <div style={{ color: C.muted, fontSize: 13 }}>No aircraft at this base.</div>}
      </div>
    </div>
  );
}
