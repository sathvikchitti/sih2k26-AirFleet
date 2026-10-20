import React from 'react';
import { api, baseName, rulText } from '../../services/api.js';
import { useResourceDemand } from '../../services/hooks.js';
import { Badge, Empty, KpiCard, Loading, PageHeader, SectionTitle } from '../../components/ui.jsx';
import { C } from '../../theme.js';

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

      <div className="ops-kpi-grid">
        <KpiCard label="Stock Lines" value={totals.stock_lines ?? '—'} />
        <KpiCard label="Units Free" value={totals.units_free ?? '—'} sub={`${totals.units_reserved ?? 0} reserved`} />
        <KpiCard label="Parts In Demand" value={(data.in_demand || []).length} accent={C.warn} />
        <KpiCard label="Shortages" value={shortages.length} accent={C.crit} sub="demand not covered" />
      </div>

      <SectionTitle>Demand vs stock</SectionTitle>
      <div className="ops-card ops-table-scroll">
        <table className="ops-table" style={{ minWidth: 640 }}>
          <thead>
            <tr>
              <th>Part</th>
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
                <tr key={r.part_number} className={`ops-table-row${r.demand ? ' is-highlight' : ''}`}>
                  <td><b className="ops-id">{r.part_number}</b></td>
                  <td style={{ color: C.muted }}>{r.name}</td>
                  <td style={{ textAlign: 'right', fontWeight: r.demand ? 800 : 400, color: r.demand ? C.warn : C.dim }}>
                    {r.demand || '—'}
                  </td>
                  {names.map(name => {
                    const line = r.lines.find(l => l.base_name === name);
                    return (
                      <td key={name} style={{ textAlign: 'right', color: line?.available_for_transfer > 0 ? (line.serviceable ? C.ok : C.warn) : C.dim }}>
                        {line ? line.available_for_transfer : '—'}
                        {line && line.quantity > 0 && !line.serviceable ? (
                          <div style={{ fontSize: 10, color: C.crit }}>{line.condition_pct}% &lt; {r.min_condition_pct}%</div>
                        ) : null}
                      </td>
                    );
                  })}
                  <td style={{ textAlign: 'right' }}>{r.total_quantity}</td>
                  <td style={{ textAlign: 'right', fontWeight: 800, color: r.shortfall ? C.crit : C.ok }}>
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
            <div key={r.part_number} className="ops-card ops-callout" style={{ '--callout': r.shortfall ? C.crit : C.ok, padding: '16px 18px' }}>
              <div className="ops-tile-head">
                <span className="ops-tile-title">{r.part_number}</span>
                <Badge color={r.shortfall ? C.crit : C.ok}>
                  {r.shortfall ? 'SHORT ' + r.shortfall : 'COVERED'}
                </Badge>
              </div>
              <div style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>{r.name}</div>
              <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {r.needing.map(a => (
                  <button
                    key={a.id}
                    onClick={() => onOpenAircraft(a.id)}
                    className="ops-tile" style={{ padding: '8px 10px', fontSize: 12.5, background: C.deck }}
                  >
                    <b>{a.id}</b> · {baseName(a.base_id)}
                    {a.rul != null || a.remaining_useful_life != null ? <> · RUL <b style={{ color: C.warn }}>{rulText(a)}</b></> : null}
                    {a.risk_level ? <> · {a.risk_level}</> : null}
                  </button>
                ))}
              </div>
              {r.serviceable_bases.length > 0 ? (
                <div style={{ fontSize: 11, color: C.muted, marginTop: 10 }}>
                  Serviceable at: {r.serviceable_bases.map(baseName).join(' · ')}
                </div>
              ) : (
                <div style={{ fontSize: 11, color: C.crit, marginTop: 10 }}>
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
