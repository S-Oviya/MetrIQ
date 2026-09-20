import {
  ArrowRight,
  Briefcase,
  CheckCircle2,
  Plus,
  Scale,
  Search,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ApiError,
  InstrumentRecord,
  instrumentsApi,
} from '../../services/api/client';
import { RegisterInstrumentModal } from './RegisterInstrumentModal';

const pretty = (v?: string) => v?.replace(/_/g, ' ') ?? '—';
const date = (v?: string | null) =>
  v
    ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(v))
    : '—';

export function InstrumentsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState<InstrumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState(searchParams.get('search') ?? '');
  const [classFilter, setClassFilter] = useState(searchParams.get('class') ?? '');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') ?? '');

  const [isRegisterOpen, setIsRegisterOpen] = useState(searchParams.get('register') === 'true');
  const [recentlyCreated, setRecentlyCreated] = useState<InstrumentRecord | null>(null);

  const load = () => {
    setLoading(true);
    instrumentsApi
      .list({
        search: search || undefined,
        accuracy_class: classFilter || undefined,
        status: statusFilter || undefined,
      })
      .then((res) => {
        setRows(res.data ?? []);
        setError('');
      })
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : 'Could not load instruments.'),
      )
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [classFilter, statusFilter]);

  const handleRegisterSuccess = (newInst: InstrumentRecord) => {
    setRecentlyCreated(newInst);
    load();
  };

  const filtered = rows.filter((inst) => {
    if (!search) return true;
    const hay = `${inst.instrument_id} ${inst.serial_number} ${inst.manufacturer} ${
      inst.model_name
    } ${inst.location?.customer_name ?? ''} ${inst.location?.city ?? ''}`.toLowerCase();
    return hay.includes(search.toLowerCase());
  });

  return (
    <section className="page-section">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Registry operations</p>
          <h1>Instruments</h1>
          <p className="page-description">
            Inventory of registered weighing instruments under statutory Legal Metrology
            oversight. Select or register an instrument to initiate verification test jobs.
          </p>
        </div>
        <button
          className="primary-button"
          onClick={() => setIsRegisterOpen(true)}
          style={{ whiteSpace: 'nowrap' }}
        >
          <Plus size={16} /> Register Instrument
        </button>
      </div>

      {recentlyCreated && (
        <div className="notice info" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <CheckCircle2 size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            Instrument <strong>{recentlyCreated.instrument_id}</strong> ({recentlyCreated.model_name}, SN: {recentlyCreated.serial_number}) successfully registered!
          </div>
          <button
            className="primary-button"
            style={{ minHeight: 32, padding: '0 12px', fontSize: 12 }}
            onClick={() => navigate(`/jobs?new=true&instrument_id=${encodeURIComponent(recentlyCreated.instrument_id)}`)}
          >
            <Briefcase size={14} /> Create Verification Job <ArrowRight size={13} />
          </button>
        </div>
      )}

      {error && <div className="notice error">{error}</div>}

      <div className="register-toolbar">
        <label className="search-control" style={{ flex: '1 1 260px' }}>
          <Search size={16} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load()}
            placeholder="Search instrument ID, serial number, model, customer…"
          />
        </label>
        <select
          value={classFilter}
          onChange={(e) => setClassFilter(e.target.value)}
          style={{ minHeight: 38, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
        >
          <option value="">All Accuracy Classes</option>
          <option value="CLASS_I">Class I (Special)</option>
          <option value="CLASS_II">Class II (High)</option>
          <option value="CLASS_III">Class III (Medium)</option>
          <option value="CLASS_IIII">Class IIII (Ordinary)</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{ minHeight: 38, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="IN_VERIFICATION">In Verification</option>
          <option value="RE_VERIFICATION_DUE">Re-verification Due</option>
          <option value="REPAIR_REQUIRED">Repair Required</option>
          <option value="RETIRED">Retired</option>
        </select>
        <button
          className="secondary-button"
          onClick={() => {
            setSearch('');
            setClassFilter('');
            setStatusFilter('');
          }}
        >
          Clear
        </button>
      </div>

      <p className="result-count">
        {loading
          ? 'Loading instruments…'
          : `${filtered.length} instrument${filtered.length === 1 ? '' : 's'}`}
      </p>

      <div className="table-frame">
        {loading ? (
          <div className="table-state">Loading registered instruments…</div>
        ) : filtered.length === 0 ? (
          <div className="table-state">
            <Scale size={24} style={{ margin: '0 auto 10px' }} />
            <p>No instruments found.</p>
            <button
              className="primary-button"
              style={{ marginTop: 12 }}
              onClick={() => setIsRegisterOpen(true)}
            >
              <Plus size={15} /> Register First Instrument
            </button>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Instrument / Serial</th>
                <th>Manufacturer &amp; Model</th>
                <th>Accuracy Class</th>
                <th>Capacity / Resolution</th>
                <th>Customer / Location</th>
                <th>Status</th>
                <th>Verification Due</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((inst) => (
                <tr key={inst.instrument_id}>
                  <td>
                    <strong>{inst.instrument_id}</strong>
                    <small>SN: {inst.serial_number}</small>
                  </td>
                  <td>
                    {inst.model_name}
                    <small>{inst.manufacturer}</small>
                  </td>
                  <td>
                    <span className="status-badge" style={{ fontWeight: 700 }}>
                      Class {String(inst.accuracy_class).replace('CLASS_', '')}
                    </span>
                  </td>
                  <td>
                    <strong>
                      Max {inst.max_capacity} {inst.unit}
                    </strong>
                    <small>
                      Min: {inst.min_capacity} {inst.unit} · e={inst.e} {inst.unit}
                    </small>
                  </td>
                  <td>
                    {inst.location?.customer_name || 'Standard Client'}
                    <small>
                      {[inst.location?.city, inst.location?.state].filter(Boolean).join(', ') || '—'}
                    </small>
                  </td>
                  <td>
                    <span className={`status-badge ${String(inst.status).toLowerCase()}`}>
                      {pretty(inst.status)}
                    </span>
                  </td>
                  <td>{date(inst.next_re_verification_due)}</td>
                  <td>
                    <button
                      className="primary-button"
                      style={{ minHeight: 30, padding: '0 10px', fontSize: 12 }}
                      onClick={() =>
                        navigate(`/jobs?new=true&instrument_id=${encodeURIComponent(inst.instrument_id)}`)
                      }
                    >
                      <Briefcase size={12} /> New Job
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <RegisterInstrumentModal
        isOpen={isRegisterOpen}
        onClose={() => setIsRegisterOpen(false)}
        onSuccess={handleRegisterSuccess}
      />
    </section>
  );
}
