import React from 'react';
import { api, baseName, rulText } from '../../services/api.js';
import { useResourceDemand } from '../../services/hooks.js';
import { Badge, Empty, KpiCard, Loading, PageHeader, SectionTitle } from '../../components/ui.jsx';

// Commander / Base manager — Resources: demand versus supply.
//
// All arithmetic (demand counts, shortfalls, serviceable bases, totals) comes
// from GET /api/resources/demand. This view renders it and adds no business
// logic of its own (spec section 22).
export default function ResourcesView({ refreshKey, scopeBase, onOpenAircraft }) {
  const [data, error] = useResourceDemand(scopeBase, refreshKey);

  if (error) {
    return (
      <div>
        <PageHeader title="Resources" subtitle="Demand versus supply." />
        <div className="ops-card">
          <Empty>
            Resource demand is computed by the backend and is unavailable offline.
            Start the API to load it: <b>uvicorn app.main:app</b>
          </Empty>
        </div>
      </div>
    );
  }
  if (!data) return <Loading>Loading resources…</Loading>;

  const rows = data.parts || [];
  const totals = data.totals || {};
  const shortages = data.shortages || [];

  return (
    <div>
      <PageHeader
        title="Resources"
        subtitle={scopeBase
          ? `Demand from ${baseName(scopeBase)}'s aircraft versus the stock held at that base.`
          : 'What the fleet needs versus what the bases hold. Demand comes from the ML service via the maintenance knowledge layer; supply comes from logistics.'}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0' }}>
        <KpiCard label="Stock Lines" value={totals.stock_lines ?? '—'} />
        <KpiCard label="Units Free" value={totals.units_free ?? '—'} sub={`${totals.units_reserved ?? 0} reserved`} />
        <KpiCard label="Parts In Demand" value={(data.in_demand || []).length} accent="#d8a93d" />
        <KpiCard label="Shortages" value={shortages.length} accent="#e05c5c" sub="demand not covered" />
      </div>

      <SectionTitle>Demand vs stock</SectionTitle>
      <div className="ops-card" style={{ overflow: 'hidden' }}>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: '#8b94a3', fontSize: 11 }}>
              <th style={{ padding: 10 }}>Part</th>
              <th>Name</th>
              <th style={{ textAlign: 'right' }}>Demand</th>
              {rows[0]?.lines?.filter((_, i) => i === 0).length
                ? [...new Set(rows.flatMap(r => r.lines.map(l => l.base_name)))]
                    .map(name => <th key={name} style={{ textAlign: 'right' }}>{name.replace('Base ', '')}</th>)
                : null}
              <th style={{ textAlign: 'right' }}>Total</th>
              <th style={{ textAlign: 'right' }}>Gap</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const names = [...new Set(rows.flatMap(x => x.lines.map(l => l.base_name)))];
              return (
                <tr key={r.part_number} style={{ borderTop: '1px solid #2a3444', background: r.demand ? '#151b24' : 'transparent' }}>
                  <td style={{ padding: 10 }}><b>{r.part_number}</b></td>
                  <td style={{ color: '#8b94a3' }}>{r.name}</td>
                  <td style={{ textAlign: 'right', fontWeight: r.demand ? 800 : 400, color: r.demand ? '#d8a93d' : '#5d6675' }}>
                    {r.demand || '—'}
                  </td>
                  {names.map(name => {
                    const line = r.lines.find(l => l.base_name === name);
                    return (
                      <td key={name} style={{ textAlign: 'right', color: line?.available_for_transfer > 0 ? (line.serviceable ? '#3fb97f' : '#d8a93d') : '#5d6675' }}>
                        {line ? line.available_for_transfer : '—'}
                        {line && line.quantity > 0 && !line.serviceable ? (
                          <div style={{ fontSize: 10, color: '#e05c5c' }}>{line.condition_pct}% &lt; {r.min_condition_pct}%</div>
                        ) : null}
                      </td>
                    );
                  })}
                  <td style={{ textAlign: 'right' }}>{r.total_quantity}</td>
                  <td style={{ textAlign: 'right', fontWeight: 800, color: r.shortfall ? '#e05c5c' : '#3fb97f' }}>
                    {r.shortfall ? '-' + r.shortfall : '0'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <SectionTitle>Aircraft waiting on a component</SectionTitle>
      {(data.in_demand || []).filter(r => r.needing.length).length === 0 ? (
        <div className="ops-card"><Empty>No aircraft are currently blocked on a component.</Empty></div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(250px,1fr))', gap: 12 }}>
          {(data.in_demand || []).filter(r => r.needing.length).map(r => (
            <div key={r.part_number} className="ops-card" style={{ padding: 14, borderLeft: '4px solid ' + (r.shortfall ? '#e05c5c' : '#3fb97f') }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <b>{r.part_number}</b>
                <Badge color={r.shortfall ? '#e05c5c' : '#3fb97f'}>
                  {r.shortfall ? 'SHORT ' + r.shortfall : 'COVERED'}
                </Badge>
              </div>
              <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 4 }}>{r.name}</div>
              <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {r.needing.map(a => (
                  <button
                    key={a.id}
                    onClick={() => onOpenAircraft(a.id)}
                    style={{ textAlign: 'left', background: '#151b24', border: '1px solid #2a3444', borderRadius: 7, padding: '7px 9px', color: '#e6e9ee', cursor: 'pointer', fontSize: 12 }}
                  >
                    <b>{a.id}</b> · {baseName(a.base_id)}
                    {a.rul != null || a.remaining_useful_life != null ? <> · RUL <b style={{ color: '#d8a93d' }}>{rulText(a)}</b></> : null}
                    {a.risk_level ? <> · {a.risk_level}</> : null}
                  </button>
                ))}
              </div>
              {r.serviceable_bases.length > 0 ? (
                <div style={{ fontSize: 11, color: '#8b94a3', marginTop: 10 }}>
                  Serviceable at: {r.serviceable_bases.map(baseName).join(' · ')}
                </div>
              ) : (
                <div style={{ fontSize: 11, color: '#e05c5c', marginTop: 10 }}>
                  No base holds serviceable stock of {r.part_number}.
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
