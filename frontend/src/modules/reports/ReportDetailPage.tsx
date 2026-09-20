import { ArrowLeft, ChevronDown, ChevronRight, Download, Eye, FileCog } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiError, AuditLogEntry, ReportDetail, auditApi, reportsApi } from '../../services/api/client';
import { Badge } from './ReportsPage';
import { demoReportDetail } from './reportData';

const display = (v: unknown) =>
  v === undefined || v === null || v === '' ? 'Not recorded' : String(v);

const Details = ({ title, values }: { title: string; values: Array<[string, unknown]> }) => (
  <article className="detail-section">
    <h2>{title}</h2>
    <dl>
      {values.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{display(v)}</dd>
        </div>
      ))}
    </dl>
  </article>
);

function AuditTrailSection({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = () => {
    if (entries.length > 0 || loading) return;
    setLoading(true);
    auditApi
      .getJobTrail(jobId)
      .then((res) => setEntries(res.data || []))
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : 'Audit trail unavailable.'),
      )
      .finally(() => setLoading(false));
  };

  const toggle = () => {
    if (!open) load();
    setOpen((prev) => !prev);
  };

  const fmt = (ts: string) => {
    try {
      return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(
        new Date(ts),
      );
    } catch {
      return ts;
    }
  };

  return (
    <article className="detail-section" style={{ gridColumn: '1 / -1' }}>
      <h2
        onClick={toggle}
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', userSelect: 'none' }}
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        Audit trail{entries.length > 0 ? ` (${entries.length} events)` : ''}
      </h2>
      {open && (
        <>
          {loading && <p style={{ color: '#666', fontSize: '0.85rem' }}>Loading audit trail…</p>}
          {error && <p style={{ color: '#c0392b', fontSize: '0.85rem' }}>{error}</p>}
          {!loading && !error && entries.length === 0 && (
            <p style={{ color: '#666', fontSize: '0.85rem' }}>No audit events recorded for this job.</p>
          )}
          {entries.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                    <th style={{ padding: '4px 8px' }}>Timestamp</th>
                    <th style={{ padding: '4px 8px' }}>Action</th>
                    <th style={{ padding: '4px 8px' }}>Actor</th>
                    <th style={{ padding: '4px 8px' }}>Entity</th>
                    <th style={{ padding: '4px 8px' }}>New value</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <tr key={e.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                      <td style={{ padding: '4px 8px', whiteSpace: 'nowrap' }}>{fmt(e.timestamp)}</td>
                      <td style={{ padding: '4px 8px', fontWeight: 600 }}>
                        {String(e.action).replace(/_/g, ' ')}
                      </td>
                      <td style={{ padding: '4px 8px' }}>{e.actor || e.user_id}</td>
                      <td style={{ padding: '4px 8px' }}>
                        {e.entity_type} · {e.entity_id}
                      </td>
                      <td style={{ padding: '4px 8px', color: '#555', maxWidth: '260px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {e.new_value ? JSON.stringify(e.new_value) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </article>
  );
}

export function ReportDetailPage() {
  const { reportId = '' } = useParams();
  const [report, setReport] = useState<ReportDetail>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const load = () =>
    reportsApi
      .get(reportId)
      .then((r) => setReport(r.data))
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : 'Report details could not be loaded.');
      });

  useEffect(() => {
    void load();
  }, [reportId]);

  const generate = async () => {
    setBusy(true);
    setError('');
    try {
      setReport((await reportsApi.generate(reportId)).data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Report generation failed.');
    } finally {
      setBusy(false);
    }
  };

  const downloadPdf = async () => {
    if (!report) return;
    setDownloading(true);
    try {
      const filename = `${report.report_number.replace(/\//g, '_')}.pdf`;
      await reportsApi.downloadPdf(report.report_id, filename);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'PDF download failed.');
    } finally {
      setDownloading(false);
    }
  };

  if (error)
    return (
      <section className="page-section">
        <Link className="back-link" to="/reports">
          <ArrowLeft size={16} /> Reports register
        </Link>
        <div className="notice error">{error}</div>
      </section>
    );

  if (!report)
    return (
      <section className="page-section">
        <div className="table-state">Loading controlled report record…</div>
      </section>
    );

  const job = report.job_snapshot || {};
  const instrument = report.instrument_snapshot || {};
  const approval = report.approval_snapshot || {};

  return (
    <section className="page-section">
      <Link className="back-link" to="/reports">
        <ArrowLeft size={16} /> Reports register
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Controlled report record</p>
          <h1>{report.report_number}</h1>
          <p className="page-description">
            {report.report_type.replace(/_/g, ' ')} · linked to{' '}
            {report.job_number || report.job_id}
          </p>
        </div>
        {report.generation_status === 'GENERATED' ? (
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button
              className="primary-button"
              onClick={() => void downloadPdf()}
              disabled={downloading || report.report_id.startsWith('demo-')}
            >
              <Download size={17} />
              {downloading ? 'Downloading…' : 'Download PDF'}
            </button>
            <Link className="secondary-button" to={`/reports/${report.report_id}/preview`}>
              <Eye size={17} /> Preview report
            </Link>
          </div>
        ) : (
          <button
            className="primary-button"
            onClick={() => void generate()}
            disabled={busy || report.report_id.startsWith('demo-')}
          >
            <FileCog size={17} />
            {busy ? 'Generating…' : 'Generate report'}
          </button>
        )}
      </div>

      {Boolean(report.contains_demo_data && (report.report_id.startsWith('demo-') || report.report_id.startsWith('mock-'))) && (
        <div
          role="alert"
          style={{
            margin: '0 0 16px',
            padding: '14px 18px',
            border: '2px solid #9a6700',
            background: '#fff3cd',
            color: '#5c4300',
            display: 'grid',
            gap: '3px',
          }}
        >
          <strong>DEMO/MOCK DATA</strong>
          <span>NOT A MEASUREMENT RECORD</span>
        </div>
      )}

      {report.generation_error && (
        <div className="notice error">{report.generation_error}</div>
      )}

      <div className="detail-banner">
        <Badge value={report.report_status} />
        <span>
          Generation: <strong>{report.generation_status.replace(/_/g, ' ')}</strong>
        </span>
      </div>

      <div className="detail-grid">
        <Details
          title="Report metadata"
          values={[
            ['Report ID', report.report_id],
            ['Job/Test ID', report.job_id],
            ['Created by', report.created_by],
            ['Generated by', report.generated_by],
          ]}
        />
        <Details
          title="Instrument and customer"
          values={[
            ['Instrument', instrument.model_name || instrument.model_number],
            ['Serial number', instrument.serial_number],
            ['Manufacturer', instrument.manufacturer],
            [
              'Customer',
              (instrument.location as Record<string, unknown> | undefined)?.customer_name ||
                (instrument.customer_info as Record<string, unknown> | undefined)?.customer_name ||
                (report as unknown as Record<string, unknown>).customer_name,
            ],
          ]}
        />
        <Details
          title="Test information"
          values={[
            ['Job status', job.status],
            ['Job type', job.job_type],
            ['Test date', job.completed_at || job.scheduled_date],
            ['Test centre', job.testing_centre_name],
            ['Inspector', job.assigned_inspector_name],
          ]}
        />
        <Details
          title="Regulatory and approval references"
          values={[
            ['Approval number', approval.approval_number],
            ['Approval status', approval.approval_status],
            ['Regulatory profile', approval.regulatory_profile_id],
            ['GATC reference', approval.gatc_reference],
          ]}
        />

        {/* Live audit trail — expands on demand, loaded from /jobs/{id}/audit */}
        {report.job_id && !report.report_id.startsWith('demo-') && (
          <AuditTrailSection jobId={report.job_id} />
        )}
      </div>
    </section>
  );
}
