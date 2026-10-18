import React from 'react';
import { baseName } from '../../services/api.js';
import { useResourceDemand } from '../../services/hooks.js';
import { Badge, Empty, KpiCard, Loading, PageHeader, SectionTitle } from '../../components/ui.jsx';

// Logistics — Components: the parts catalogue crossed with stock position and
// fleet demand.
//
// Everything quantitative comes from GET /api/resources/demand; this view only
// renders it (spec section 22).
export default function ComponentsView({ onOpenAircraft, refreshKey }) {
  const [data, error] = useResourceDemand(undefined, refreshKey);

  if (error) {
    return (
      <div>
        <PageHeader title="Components" subtitle="Catalogue, stock position and demand." />
        <div className="ops-card">
          <Empty>Component demand is computed by the backend and is unavailable offline. Start the API to load it.</Empty>
        </div>
      </div>
    );
  }
  if (!data) return <Loading>Loading components…</Loading>;

  const rows = data.parts || [];
  const totals = data.totals || {};
  const shortages = data.shortages || [];
  const idle = rows.filter(r => r.demand === 0 && r.total_quantity > 0);

  return (
    <div>
      <PageHeader
        title="Components"
        subtitle="Catalogue of parts, where each is stocked, and which aircraft need it next. Demand is derived from the ML service through the maintenance knowledge layer; supply from logistics."
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0' }}>
        <KpiCard label="Part Types" value={totals.part_types ?? '—'} />
        <KpiCard label="Units Free" value={totals.units_free ?? '—'} accent="#3fb97f" sub="free and above min condition" />
        <KpiCard label="Shortfalls" value={shortages.length} accent="#e05c5c" sub="demand exceeds supply" />
        <KpiCard label="Stockouts" value={totals.stockouts ?? '—'} accent="#d8a93d" />
        <KpiCard label="Below Min Condition" value={totals.unserviceable ?? '—'} accent="#e05c5c" sub="unusable for fit" />
      </div>

      <SectionTitle>Stock by component and base</SectionTitle>
      <div className="ops-card" style={{ overflow: 'hidden' }}>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: '#8b94a3', fontSize: 11 }}>
              <th style={{ padding: 10 }}>Part</th>
              <th>Name</th>
              <th>Category</th>
              {[...new Set(rows.flatMap(r => r.lines.map(l => l.base_name)))]
                .map(name => <th key={name} style={{ textAlign: 'right' }}>{name.replace('Base ', '')}</th>)}
              <th style={{ textAlign: 'right' }}>Free</th>
              <th style={{ textAlign: 'right' }}>Demand</th>
              <th style={{ textAlign: 'right' }}>Gap</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const names = [...new Set(rows.flatMap(x => x.lines.map(l => l.base_name)))];
              return (
                <tr key={r.part_number} style={{ borderTop: '1px solid #2a3444', background: r.shortfall ? '#1a1414' : 'transparent' }}>
                  <td style={{ padding: 10 }}><b>{r.part_number}</b></td>
                  <td style={{ color: '#8b94a3' }}>{r.name}</td>
                  <td style={{ color: '#8b94a3' }}>{r.category}</td>
                  {names.map(name => {
                    const line = r.lines.find(l => l.base_name === name);
                    return (
                      <td key={name} style={{ textAlign: 'right' }}>
                        <span style={{ color: line?.available_for_transfer > 0 ? (line.serviceable ? '#3fb97f' : '#d8a93d') : '#5d6675', fontWeight: line?.available_for_transfer > 0 ? 700 : 400 }}>
                          {line ? line.available_for_transfer : '—'}
                        </span>
                        {line && line.quantity > 0 && !line.serviceable ? (
                          <div style={{ fontSize: 10, color: '#e05c5c' }}>{line.condition_pct}% cond</div>
                        ) : null}
                      </td>
                    );
                  })}
                  <td style={{ textAlign: 'right', fontWeight: 700 }}>{r.total_free}</td>
                  <td style={{ textAlign: 'right', color: r.demand ? '#d8a93d' : '#5d6675' }}>{r.demand || '—'}</td>
                  <td style={{ textAlign: 'right', fontWeight: 800, color: r.shortfall ? '#e05c5c' : '#3fb97f' }}>
                    {r.shortfall ? '-' + r.shortfall : '0'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <SectionTitle>Part detail</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 12 }}>
        {rows.map(r => (
          <div key={r.part_number} className="ops-card" style={{ padding: 14, borderLeft: '4px solid ' + (r.shortfall ? '#e05c5c' : r.demand ? '#d8a93d' : '#3fb97f') }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <b>{r.part_number}</b>
              <Badge color={r.shortfall ? '#e05c5c' : r.demand ? '#d8a93d' : '#3fb97f'}>
                {r.shortfall ? 'SHORT ' + r.shortfall : r.demand ? 'IN DEMAND' : 'SURPLUS'}
              </Badge>
            </div>
            <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 4 }}>{r.name} · {r.category}</div>
            <div style={{ fontSize: 12, marginTop: 8 }}>
              Min serviceable condition: <b>{r.min_condition_pct}%</b>
            </div>
            <div style={{ fontSize: 12 }}>
              Serviceable at <b>{r.serviceable_bases.length}</b> of {r.lines.length} base{r.lines.length === 1 ? '' : 's'}
            </div>
            {r.needing.length > 0 && (
              <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {r.needing.map(a => (
                  <button
                    key={a.id}
                    onClick={() => onOpenAircraft(a.id)}
                    style={{ background: '#151b24', border: '1px solid #2a3444', borderRadius: 6, padding: '4px 8px', color: '#e6e9ee', cursor: 'pointer', fontSize: 12 }}
                  >
                    {a.id} <span style={{ color: '#8b94a3' }}>· {baseName(a.base_id)}</span>
                  </button>
                ))}
              </div>
            )}
            {r.open_work_orders.length > 0 && (
              <div style={{ fontSize: 11, color: '#8b94a3', marginTop: 8 }}>
                Open work orders: {r.open_work_orders.map(w => w.id).join(', ')}
              </div>
            )}
            {r.demand === 0 && (
              <div style={{ fontSize: 11, color: '#5d6675', marginTop: 8 }}>
                No aircraft currently require this part.
              </div>
            )}
          </div>
        ))}
        {!rows.length && <div className="ops-card"><Empty>No components in the catalogue.</Empty></div>}
      </div>

      {idle.length > 0 && (
        <>
          <SectionTitle>Held but not currently required</SectionTitle>
          <div style={{ fontSize: 13, color: '#8b94a3' }}>
            {idle.map(r => r.part_number + ' (' + r.total_quantity + ' units)').join(' · ')} — cover stock, no open demand.
          </div>
        </>
      )}
    </div>
  );
}