import { Activity, ArrowRight, Briefcase, FilePlus2, Plus, Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ACTIVE_JOB_STATUSES,
  ApiError,
  JobSummary,
  REPORT_GENERATABLE_JOB_STATUSES,
  REVIEW_JOB_STATUSES,
  jobsApi,
} from '../../services/api/client';
import { CreateJobModal } from './CreateJobModal';
import { RegisterInstrumentModal } from '../instruments/RegisterInstrumentModal';

const pretty = (v?: string) => v?.replace(/_/g, ' ') ?? '—';
const date = (v?: string | null) =>
  v
    ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(v))
    : '—';

function statusGroup(status?: string): 'active' | 'review' | 'done' | 'other' {
  const s = (status ?? '') as (typeof ACTIVE_JOB_STATUSES)[number];
  if (ACTIVE_JOB_STATUSES.includes(s)) return 'active';
  if (REVIEW_JOB_STATUSES.includes(s as (typeof REVIEW_JOB_STATUSES)[number])) return 'review';
  if (REPORT_GENERATABLE_JOB_STATUSES.includes(s as (typeof REPORT_GENERATABLE_JOB_STATUSES)[number]))
    return 'done';
  return 'other';
}

export function JobsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState(searchParams.get('search') ?? '');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') ?? '');

  const [isCreateOpen, setIsCreateOpen] = useState(searchParams.get('new') === 'true');
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const initialInstrumentId = searchParams.get('instrument_id') ?? undefined;

  const load = () => {
    setLoading(true);
    jobsApi
      .list({ status: statusFilter || undefined, search: search || undefined })
      .then((res) => {
        setRows(res.data ?? []);
        setError('');
      })
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : 'Could not load jobs.'),
      )
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [statusFilter]);

  const filtered = rows.filter((j) => {
    if (!search) return true;
    const hay = `${j.job_id} ${j.job_number ?? ''} ${j.instrument_id} ${
      String(j.instrument_snapshot?.model_name ?? '')
    } ${j.assigned_inspector_name ?? ''}`.toLowerCase();
    return hay.includes(search.toLowerCase());
  });

  return (
    <section className="page-section">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Verification workflow</p>
          <h1>Jobs</h1>
          <p className="page-description">
            Active and historical NAWI verification test jobs. Open a job to run tests, review
            results, and generate reports.
          </p>
        </div>
        <button
          className="primary-button"
          onClick={() => setIsCreateOpen(true)}
          style={{ whiteSpace: 'nowrap' }}
        >
          <Plus size={16} /> New Verification Job
        </button>
      </div>

      {error && <div className="notice error">{error}</div>}

      <div className="register-toolbar">
        <label className="search-control" style={{ flex: '1 1 260px' }}>
          <Search size={16} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load()}
            placeholder="Search job ID, instrument, inspector…"
          />
        </label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{ minHeight: 38, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
        >
          <option value="">All statuses</option>
          <option value="IN_PROGRESS">In Progress</option>
          <option value="RETEST_REQUIRED">Retest Required</option>
          <option value="REVIEW">Under Review</option>
          <option value="UNDER_REVIEW">Under Review (P3)</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="ASSIGNED">Assigned</option>
          <option value="TEST_PLAN_GENERATED">Test Plan Generated</option>
        </select>
        <button className="secondary-button" onClick={() => { setSearch(''); setStatusFilter(''); }}>
          Clear
        </button>
      </div>

      <p className="result-count">
        {loading
          ? 'Loading jobs…'
          : `${filtered.length} job${filtered.length === 1 ? '' : 's'}`}
      </p>

      <div className="table-frame">
        {loading ? (
          <div className="table-state">Loading jobs…</div>
        ) : filtered.length === 0 ? (
          <div className="table-state" style={{ padding: '32px 16px', textAlign: 'center' }}>
            <Activity size={26} style={{ margin: '0 auto 10px', color: '#64748b' }} />
            <p style={{ margin: 0, fontWeight: 600, color: '#334155' }}>No verification jobs found.</p>
            <p style={{ margin: '6px 0 16px', fontSize: 13, color: '#64748b' }}>
              Create a new test job to generate a regulatory test plan and initiate testing.
            </p>
            <button
              className="primary-button"
              style={{ display: 'inline-flex' }}
              onClick={() => setIsCreateOpen(true)}
            >
              <Plus size={15} /> Create Verification Job
            </button>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Job ID / Number</th>
                <th>Instrument</th>
                <th>Type</th>
                <th>Status</th>
                <th>Inspector</th>
                <th>Scheduled</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((job) => {
                const group = statusGroup(job.status);
                return (
                  <tr key={job.job_id}>
                    <td>
                      <strong>{job.job_number || job.job_id}</strong>
                      <small>{job.job_id}</small>
                    </td>
                    <td>
                      {String(job.instrument_snapshot?.model_name ?? job.instrument_id)}
                      <small>{job.instrument_id}</small>
                    </td>
                    <td>{pretty(job.job_type)}</td>
                    <td>
                      <span className={`status-badge ${String(job.status ?? '').toLowerCase()}`}>
                        {pretty(job.status)}
                      </span>
                    </td>
                    <td>{job.assigned_inspector_name || '—'}</td>
                    <td>{date(job.scheduled_date)}</td>
                    <td>
                      <Link className="table-link" to={`/jobs/${job.job_id}`}>
                        {group === 'active' ? 'Run tests' : group === 'review' ? 'Review' : 'Open'}
                        {' '}
                        <ArrowRight size={13} style={{ verticalAlign: 'middle' }} />
                      </Link>
                      {REPORT_GENERATABLE_JOB_STATUSES.includes(
                        job.status as (typeof REPORT_GENERATABLE_JOB_STATUSES)[number],
                      ) && (
                        <>
                          <br />
                          <Link className="table-link" to={`/reports?job_id=${job.job_id}`}>
                            <FilePlus2 size={13} style={{ verticalAlign: 'middle' }} /> Report
                          </Link>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      <CreateJobModal
        isOpen={isCreateOpen}
        initialInstrumentId={initialInstrumentId}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={() => load()}
        onRequestRegisterInstrument={() => setIsRegisterOpen(true)}
      />

      <RegisterInstrumentModal
        isOpen={isRegisterOpen}
        onClose={() => setIsRegisterOpen(false)}
        onSuccess={(newInst) => {
          setIsRegisterOpen(false);
          setIsCreateOpen(true);
        }}
      />
    </section>
  );
}
