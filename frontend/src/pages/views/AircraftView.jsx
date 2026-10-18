import React from 'react';
import { baseName, healthScoreText, rulText } from '../../services/api.js';
import { useFleetViews } from '../../services/hooks.js';
import {
  Badge, DataError, Empty, HealthBar, KpiCard, Loading, PageHeader, RiskBadge,
  SearchInput, SectionTitle, Select, riskColor, statusColor,
} from '../../components/ui.jsx';

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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0' }}>
        <KpiCard label="In Register" value={(aircraft || []).length} />
        <KpiCard label="Flyable Now" value={(aircraft || []).filter(a => a.status === 'AVAILABLE').length} accent="#3fb97f" />
        <KpiCard label="High / Critical" value={(aircraft || []).filter(a => ['HIGH', 'CRITICAL'].includes(a.health?.risk_level)).length} accent="#e05c5c" />
        <KpiCard label="In Maintenance" value={(aircraft || []).filter(a => a.status === 'MAINTENANCE').length} accent="#4f9cf0" />
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
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
                style={{ textAlign: 'left', cursor: 'pointer', background: '#151b24', border: '1px solid #e05c5c55', borderRadius: 10, padding: 14, color: '#e6e9ee' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <b style={{ fontSize: 16 }}>{a.id}</b>
                  <RiskBadge risk={a.health.risk_level} />
                </div>
                <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 4 }}>{baseName(a.base_id)} · {a.type}</div>
                <div style={{ marginTop: 10 }}><HealthBar score={a.health.health_score} /></div>
                <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 6 }}>
                  RUL {rulText(a.health)} · needs <b style={{ color: '#d8a93d' }}>{a.health.required_component || a.required_component || '—'}</b>
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
              style={{ textAlign: 'left', cursor: 'pointer', background: '#151b24', border: '1px solid #2a3444', borderRadius: 10, padding: 14, color: '#e6e9ee' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <b style={{ fontSize: 16 }}>{a.id}</b>
                <Badge color={statusColor(a.status)}>{String(a.status).replace(/_/g, ' ')}</Badge>
              </div>
              <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 4 }}>{baseName(a.base_id)} · {a.type}</div>
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
