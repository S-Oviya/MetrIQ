import {
  Activity,
  ArrowRight,
  Briefcase,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  FilePlus2,
  FileText,
  Plus,
  RotateCcw,
  Scale,
  TriangleAlert,
  WifiOff,
} from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ACTIVE_JOB_STATUSES,
  DashboardMetrics,
  JobSummary,
  REVIEW_JOB_STATUSES,
  ReportSummary,
  dashboardApi,
} from '../../services/api/client';
import { loadJobs, loadReports } from '../reports/reportData';

const pretty = (value?: string) => value?.replace(/_/g, ' ') || 'Not recorded';
const date = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(
        new Date(value),
      )
    : '—';
const instrumentName = (job: JobSummary) =>
  String(job.instrument_snapshot?.model_name || job.instrument_snapshot?.model_number || job.instrument_id);

export function DashboardPage() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState('');

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    Promise.all([
      dashboardApi.metrics()
        .then((res) => res.data)
        .catch((err) => {
          console.warn('Dashboard metrics failed:', err);
          return null;
        }),
      loadJobs(),
      loadReports(),
    ])
      .then(([metricData, jobData, reportData]) => {
        if (!isMounted) return;

        if (jobData.error && reportData.error && !metricData) {
          setConnectionError(
            'Unable to connect to the MetrIQ backend service. Please ensure the backend is running.',
          );
        } else {
          setConnectionError('');
        }

        setMetrics(metricData);
        setJobs(jobData.data || []);
        setReports(reportData.data || []);
      })
      .catch(() => {
        if (!isMounted) return;
        setConnectionError('Unable to load operational data. Backend connection failure.');
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const count = (states: string[]) =>
    jobs.filter((job) => states.includes(String(job.status).toUpperCase())).length;

  const derivedMetrics: DashboardMetrics = {
    active_jobs: count(ACTIVE_JOB_STATUSES),
    pending_reviews: count(REVIEW_JOB_STATUSES),
    failed_tests: count(['REJECTED']),
    retests: jobs.filter((job) => job.job_type === 'RETEST').length,
    completed_jobs: count(['APPROVED', 'CLOSED', 'CERTIFIED', 'REPORT_GENERATED']),
  };

  const values = metrics || derivedMetrics;

  const metricCards = [
    {
      label: 'Active Jobs',
      value: values.active_jobs ?? 0,
      context: 'Work currently in progress',
      Icon: Activity,
      to: '/jobs',
    },
    {
      label: 'Pending Reviews',
      value: values.pending_reviews ?? 0,
      context: 'Awaiting supervisory decision',
      Icon: ClipboardCheck,
      to: '/jobs?status=REVIEW',
    },
    {
      label: 'Failed Tests',
      value: values.failed_tests ?? 0,
      context: 'Outcomes requiring action',
      Icon: TriangleAlert,
      to: '/jobs?status=REJECTED',
    },
    {
      label: 'Retests',
      value: values.retests ?? 0,
      context: 'Follow-up verification work',
      Icon: RotateCcw,
      to: '/jobs?status=RETEST_REQUIRED',
    },
    {
      label: 'Completed Jobs',
      value: values.completed_jobs ?? 0,
      context: 'Approved or closed records',
      Icon: CheckCircle2,
      to: '/jobs?status=APPROVED',
    },
    {
      label: 'Verification Due',
      value: values.verification_due ?? '—',
      context: 'Due within next 30 days',
      Icon: CalendarClock,
      to: '/instruments',
    },
  ];

  return (
    <section className="page-section" aria-labelledby="dashboard-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Operational overview</p>
          <h1 id="dashboard-title">Verification dashboard</h1>
          <p className="page-description">
            Statutory Legal Metrology dashboard for Non-Automatic Weighing Instruments (NAWI).
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span
            className="page-status"
            style={{
              background: connectionError ? '#fef2f2' : '#f0fdf4',
              color: connectionError ? '#991b1b' : '#166534',
              borderColor: connectionError ? '#fca5a5' : '#86efac',
            }}
          >
            {loading ? 'Connecting…' : connectionError ? 'Backend Disconnected' : 'Live Operational Data'}
          </span>
          <Link className="primary-button" to="/jobs?new=true" style={{ whiteSpace: 'nowrap' }}>
            <Plus size={15} /> New Verification Job
          </Link>
        </div>
      </div>

      {connectionError && (
        <div
          className="notice error"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '14px 18px',
            marginBottom: 20,
            borderRadius: 8,
          }}
        >
          <WifiOff size={20} color="#b91c1c" />
          <div>
            <strong>Backend Connection Unavailable:</strong> {connectionError}
          </div>
        </div>
      )}

      {/* Metric summary cards */}
      <div className="metric-grid">
        {metricCards.map(({ label, value, context, Icon, to }) => (
          <Link className="metric-card metric-link" to={to} key={label}>
            <div className="metric-icon">
              <Icon size={20} />
            </div>
            <div>
              <h2>{label}</h2>
              <p>{context}</p>
              <strong className="metric-value">{loading ? '—' : value}</strong>
            </div>
            <ArrowRight size={17} className="metric-arrow" />
          </Link>
        ))}
      </div>

      <div className="dashboard-grid">
        {/* Recent reports */}
        <section className="content-panel">
          <div className="panel-heading panel-heading-split">
            <div>
              <p className="eyebrow">Document output</p>
              <h2>Recent reports &amp; certificates</h2>
              <p>Generated statutory certificates and rejection notices.</p>
            </div>
            <Link className="table-link" to="/reports">
              View all reports <ArrowRight size={14} />
            </Link>
          </div>
          <DashboardTable reports={reports.slice(0, 5)} loading={loading} />
        </section>

        {/* Quick actions panel */}
        <aside className="content-panel quick-actions">
          <div className="panel-heading">
            <Briefcase size={20} />
            <div>
              <h2>Quick actions</h2>
              <p>Statutory metrology and record tasks.</p>
            </div>
          </div>
          {[
            {
              Icon: Scale,
              title: 'Register instrument',
              description: 'Add a weighing instrument to registry',
              to: '/instruments?register=true',
            },
            {
              Icon: Briefcase,
              title: 'New verification job',
              description: 'Provision test job and generate test plan',
              to: '/jobs?new=true',
            },
            {
              Icon: Activity,
              title: 'All verification jobs',
              description: 'View active queues, executions, and reviews',
              to: '/jobs',
            },
            {
              Icon: Scale,
              title: 'Instrument registry',
              description: 'View and manage registered instruments',
              to: '/instruments',
            },
            {
              Icon: FilePlus2,
              title: 'Generated certificates',
              description: 'View and download official report PDFs',
              to: '/reports',
            },
          ].map(({ Icon, title, description, to }) => (
            <Link className="quick-action" to={to} key={title}>
              <Icon size={18} />
              <span>
                <strong>{title}</strong>
                <small>{description}</small>
              </span>
              <ArrowRight size={16} />
            </Link>
          ))}
        </aside>

        {/* Recent jobs */}
        <section className="content-panel dashboard-jobs">
          <div className="panel-heading panel-heading-split">
            <div>
              <p className="eyebrow">Workflow queue</p>
              <h2>Recent verification jobs</h2>
              <p>Current test job assignments and verification progress.</p>
            </div>
            <Link className="table-link" to="/jobs">
              View all jobs <ArrowRight size={14} />
            </Link>
          </div>
          <div className="job-list">
            {loading ? (
              <div className="table-state">Loading verification jobs…</div>
            ) : jobs.length === 0 ? (
              <div className="table-state" style={{ padding: '24px 16px', textAlign: 'center' }}>
                <Briefcase size={24} style={{ margin: '0 auto 8px', color: '#64748b' }} />
                <p style={{ margin: 0, color: '#475569', fontSize: 13 }}>
                  No verification jobs found in repository.
                </p>
                <Link
                  className="primary-button"
                  to="/jobs?new=true"
                  style={{ display: 'inline-flex', marginTop: 12, minHeight: 32, fontSize: 12 }}
                >
                  <Plus size={14} /> Create First Verification Job
                </Link>
              </div>
            ) : (
              jobs.slice(0, 5).map((job) => (
                <div className="job-row" key={job.job_id}>
                  <div>
                    <strong>{job.job_number || job.job_id}</strong>
                    <small>
                      {instrumentName(job)} · {pretty(job.job_type)}
                    </small>
                  </div>
                  <div>
                    <span className={`status-badge ${String(job.status).toLowerCase()}`}>
                      {pretty(job.status)}
                    </span>
                    <small>{job.assigned_inspector_name || 'Inspector unassigned'}</small>
                  </div>
                  <Link
                    className="table-link"
                    to={`/jobs/${encodeURIComponent(job.job_id)}`}
                    style={{ whiteSpace: 'nowrap' }}
                  >
                    Open Job <ArrowRight size={12} style={{ verticalAlign: 'middle' }} />
                  </Link>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

function DashboardTable({
  reports,
  loading,
}: {
  reports: ReportSummary[];
  loading: boolean;
}) {
  if (loading) return <div className="table-state">Loading report records…</div>;
  if (reports.length === 0) {
    return (
      <div className="table-state" style={{ padding: '24px 16px', textAlign: 'center' }}>
        <FileText size={24} style={{ margin: '0 auto 8px', color: '#64748b' }} />
        <p style={{ margin: 0, color: '#475569', fontSize: 13 }}>
          No statutory report records generated yet.
        </p>
        <p style={{ margin: '4px 0 0', color: '#94a3b8', fontSize: 12 }}>
          Reports become available once a verification job is approved or rejected by supervisory review.
        </p>
      </div>
    );
  }

  return (
    <div className="compact-table">
      {reports.map((report) => (
        <div className="compact-row" key={report.report_id}>
          <FileText size={17} />
          <div>
            <Link className="table-link" to={`/reports/${encodeURIComponent(report.report_id)}`}>
              {report.report_number}
            </Link>
            <small>
              {pretty(report.report_type)} · {report.job_number || report.job_id}
            </small>
          </div>
          <div>
            <span className={`status-badge ${String(report.report_status).toLowerCase()}`}>
              {pretty(report.report_status)}
            </span>
            <small>{date(report.generated_at || report.created_at)}</small>
          </div>
        </div>
      ))}
    </div>
  );
}
