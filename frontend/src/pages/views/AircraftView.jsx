import React from 'react';
import { baseName, healthScoreText, rulText } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  Badge, DataError, Empty, HealthBar, KpiCard, Loading, PageHeader, RiskBadge,
  SearchInput, SectionTitle, Select, riskColor, statusColor,
} from '../../components/ui.jsx';
import { C } from '../../theme.js';

// Commander — Aircraft: register / inspection view. Card-per-aircraft layout
// showing health trend-style bars so a commander can eyeball the fleet's
// condition without opening each record.
export default function AircraftView({ onOpenAircraft, refreshKey }) {
  const { aircraft, loading, predictionError } = useFleetViews(refreshKey);
  const [q, setQ] = React.useState('');
  const [status, setStatus] = React.useState('');

  if (loading) return <Loading>Loading aircraft register…</Loading>;
  if (predictionError) return <DataError error={predictionError}>Aircraft predictions are unavailable from the selected ML provider.</DataError>;

  let list = aircraft || [];
  if (q) {
    const needle = q.toLowerCase();
    list = list.filter(a => String(a.id).toLowerCase().includes(needle) || String(a.type || '').toLowerCase().includes(needle));
  }
  if (status) list = list.filter(a => a.status === status);

  const risky = list.filter(a => ['HIGH', 'CRITICAL'].includes(a.health?.risk_level));

  return (
    <div>
      <PageHeader
        title="Aircraft"
        subtitle="Fleet register. Each card shows the aircraft's live health from the ML service, its failure risk and the part it needs next."
      />

      <div className="ops-kpi-grid">
        <KpiCard label="In Register" value={(aircraft || []).length} />
        <KpiCard label="Flyable Now" value={(aircraft || []).filter(a => a.status === 'AVAILABLE').length} accent={C.ok} />
        <KpiCard label="High / Critical" value={(aircraft || []).filter(a => ['HIGH', 'CRITICAL'].includes(a.health?.risk_level)).length} accent={C.crit} />
        <KpiCard label="In Maintenance" value={(aircraft || []).filter(a => a.status === 'MAINTENANCE').length} accent={C.info} />
      </div>

      <div className="ops-toolbar">
        <SearchInput value={q} onChange={setQ} placeholder="Search tail or type…" />
        <Select
          value={status}
          onChange={setStatus}
          label="All statuses"
          options={['AVAILABLE', 'AT_RISK', 'DEGRADED', 'MAINTENANCE'].map(s => ({ value: s, label: s.replace(/_/g, ' ') }))}
        />
      </div>

      {risky.length > 0 && (
        <>
          <SectionTitle>Priority attention — {risky.length} aircraft</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 12, marginBottom: 6 }}>
            {risky.map(a => (
              <button
                key={a.id}
                onClick={() => onOpenAircraft(a.id)}
                className="ops-tile is-alert"
              >
                <div className="ops-tile-head">
                  <span className="ops-tile-title">{a.id}</span>
                  <RiskBadge risk={a.health.risk_level} />
                </div>
                <div className="ops-tile-meta">{baseName(a.base_id)} · {a.type}</div>
                <div style={{ marginTop: 10 }}><HealthBar score={a.health.health_score} /></div>
                <div style={{ fontSize: 12, color: C.muted, marginTop: 6 }}>
                  RUL {rulText(a.health)} · needs <b style={{ color: C.warn }}>{a.health.required_component || a.required_component || '—'}</b>
                </div>
              </button>
            ))}
          </div>
        </>
      )}

      <SectionTitle>All aircraft</SectionTitle>
      {list.length === 0 ? (
        <div className="ops-card"><Empty>No aircraft match your filters.</Empty></div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(250px,1fr))', gap: 12 }}>
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
              <div className="ops-tile-meta">{baseName(a.base_id)} · {a.type}</div>
              {a.health && (
                <>
                  <div style={{ marginTop: 10 }}><HealthBar score={a.health.health_score} /></div>
                  <div style={{ fontSize: 12, marginTop: 6, color: riskColor(a.health.risk_level) }}>
                    {healthScoreText(a.health)} · {a.health.risk_level} · RUL {rulText(a.health)}
                  </div>
                </>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
