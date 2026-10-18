import React from 'react';
import { api, baseName } from '../services/api.js';
import { SectionTitle, KpiCard } from '../components/ui.jsx';
import ResourceForecastPanel from '../components/ResourceForecastPanel.jsx';

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
      <h2 style={{ fontSize: 22, fontWeight: 800 }}>Logistics — Inventory & Resource Management</h2>
      <p style={{ color: '#8b94a3', fontSize: 13 }}>Manages physical resources only. Aircraft health comes from the ML layer — logistics never edits predictions.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginTop: 12 }}>
        <KpiCard label="Inventory Lines" value={inv.length} />
        <KpiCard label="Low / Stockout" value={low.length} accent="#e05c5c" />
        <KpiCard label="Pending Transfers" value={transfers.filter(t => t.status === 'PENDING_APPROVAL').length} accent="#d8a93d" />
        <KpiCard label="In Transit" value={transfers.filter(t => t.status === 'IN_TRANSIT').length} accent="#4f9cf0" />
      </div>
      <ResourceForecastPanel canRequestMove refreshKey={refreshKey} onRefresh={refresh} />
      {msg && <div style={{ marginTop: 10, fontSize: 13, color: '#d8a93d' }}>{msg}</div>}
      <SectionTitle>Component inventory</SectionTitle>
      <div className="ops-card" style={{ overflow: 'hidden' }}>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead><tr style={{ textAlign: 'left', color: '#8b94a3', fontSize: 11 }}>
            <th style={{ padding: 10 }}>Part</th><th>Base</th><th>Qty</th><th>Reserved</th><th>Condition</th><th>Status</th>
          </tr></thead>
          <tbody>
            {inv.map(i => (
              <tr key={i.id} style={{ borderTop: '1px solid #2a3444' }}>
                <td style={{ padding: 10 }}><b>{i.part_number}</b></td>
                <td>{baseName(i.base_id)}</td><td>{i.quantity}</td><td>{i.reserved || 0}</td>
                <td>{i.condition_pct}%</td><td>{i.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SectionTitle>Transfers — incoming / outgoing / pending</SectionTitle>
      <div className="ops-card" style={{ overflow: 'hidden' }}>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead><tr style={{ textAlign: 'left', color: '#8b94a3', fontSize: 11 }}>
            <th style={{ padding: 10 }}>ID</th><th>Part</th><th>Route</th><th>Status</th><th>ETA</th><th>Action</th>
          </tr></thead>
          <tbody>
            {transfers.map(t => (
              <tr key={t.id} style={{ borderTop: '1px solid #2a3444' }}>
                <td style={{ padding: 10 }}>{t.id}</td><td>{t.part_number}</td>
                <td>{baseName(t.source_base)} → {baseName(t.dest_base)}</td>
                <td>{t.status}</td><td>{t.eta_hours}h</td>
                <td style={{ display: 'flex', gap: 6, padding: 10 }}>
                  {t.status === 'PENDING_APPROVAL' && <button onClick={() => act(() => api.approveTransfer(t.id), 'Transfer approved → IN TRANSIT')} style={btn}>Approve</button>}
                  {t.status === 'IN_TRANSIT' && <button onClick={() => act(() => api.receiveTransfer(t.id), 'Component received')} style={btn}>Simulate arrival</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const btn = { background: '#1c2431', border: '1px solid #2a3444', color: '#e6e9ee', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 12 };
