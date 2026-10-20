import React from 'react';
import { api, baseName } from '../services/api.js';
import { ActionButton, Badge, KpiCard, PageHeader, SectionTitle, StatusMsg, statusColor } from '../components/ui.jsx';
import ResourceForecastPanel from '../components/ResourceForecastPanel.jsx';
import { C } from '../theme.js';

export default function Logistics({ refreshKey, refresh }) {
  const [inv, setInv] = React.useState([]);
  const [transfers, setTransfers] = React.useState([]);
  const [msg, setMsg] = React.useState('');

  const load = async () => {
    setInv(await api.getInventory());
    setTransfers(await api.getTransfers());
  };
  React.useEffect(() => { load(); }, [refreshKey]);

  const act = async (fn, label) => {
    try { await fn(); setMsg(label + ' — done'); load(); refresh(); }
    catch (e) { setMsg(e?.message || 'Action failed. Check the backend connection and try again.'); }
  };

  const low = inv.filter(i => i.quantity <= 1);
  return (
    <div>
      <PageHeader
        title="Inventory & resources"
        subtitle="Manages physical resources only. Aircraft health comes from the ML layer — logistics never edits predictions."
      />
      <div className="ops-kpi-grid">
        <KpiCard label="Inventory lines" value={inv.length} />
        <KpiCard label="Low / stockout" value={low.length} accent={C.crit} />
        <KpiCard label="Pending transfers" value={transfers.filter(t => t.status === 'PENDING_APPROVAL').length} accent={C.warn} />
        <KpiCard label="In transit" value={transfers.filter(t => t.status === 'IN_TRANSIT').length} accent={C.info} />
      </div>
      <ResourceForecastPanel canRequestMove refreshKey={refreshKey} onRefresh={refresh} />
      <StatusMsg>{msg}</StatusMsg>
      <SectionTitle>Component inventory</SectionTitle>
      <div className="ops-card ops-table-scroll">
        <table className="ops-table" style={{ minWidth: 620 }}>
          <thead><tr>
            <th>Part</th><th>Base</th><th style={{ textAlign: 'right' }}>Qty</th><th style={{ textAlign: 'right' }}>Reserved</th><th style={{ textAlign: 'right' }}>Condition</th><th>Status</th>
          </tr></thead>
          <tbody>
            {inv.map(i => (
              <tr key={i.id} className="ops-table-row">
                <td><b className="ops-id">{i.part_number}</b></td>
                <td>{baseName(i.base_id)}</td>
                <td className="ops-number" style={{ textAlign: 'right' }}>{i.quantity}</td>
                <td className="ops-number" style={{ textAlign: 'right' }}>{i.reserved || 0}</td>
                <td className="ops-number" style={{ textAlign: 'right' }}>{i.condition_pct}%</td>
                <td><Badge color={statusColor(i.status)}>{String(i.status || '—').replace(/_/g, ' ')}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SectionTitle>Transfers — incoming / outgoing / pending</SectionTitle>
      <div className="ops-card ops-table-scroll">
        <table className="ops-table" style={{ minWidth: 640 }}>
          <thead><tr>
            <th>ID</th><th>Part</th><th>Route</th><th>Status</th><th style={{ textAlign: 'right' }}>ETA</th><th style={{ textAlign: 'right' }}>Action</th>
          </tr></thead>
          <tbody>
            {transfers.map(t => (
              <tr key={t.id} className="ops-table-row">
                <td className="ops-id">{t.id}</td><td>{t.part_number}</td>
                <td>{baseName(t.source_base)} → {baseName(t.dest_base)}</td>
                <td><Badge color={statusColor(t.status)}>{String(t.status || '—').replace(/_/g, ' ')}</Badge></td>
                <td className="ops-number" style={{ textAlign: 'right' }}>{t.eta_hours}h</td>
                <td>
                  <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                    {t.status === 'PENDING_APPROVAL' && <ActionButton small primary onClick={() => act(() => api.approveTransfer(t.id), 'Transfer approved → IN TRANSIT')}>Approve</ActionButton>}
                    {t.status === 'IN_TRANSIT' && <ActionButton small onClick={() => act(() => api.receiveTransfer(t.id), 'Component received')}>Simulate arrival</ActionButton>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
