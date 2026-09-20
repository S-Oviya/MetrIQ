import { ArrowLeft, Download, Printer } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiError, ReportDetail, reportsApi } from '../../services/api/client';
import { demoReportDetail, reportTypeLabels } from './reportData';

const value = (v: unknown) => v === undefined || v === null || v === '' ? 'Not recorded' : String(v);
const Block = ({ title, rows }: { title: string; rows: Array<[string, unknown]> }) => <section className="preview-section"><h2>{title}</h2>{rows.map(([k, v]) => <div className="preview-row" key={k}><span>{k}</span><strong>{value(v)}</strong></div>)}</section>;

export function ReportPreviewPage() {
  const { reportId = '' } = useParams();
  const frame = useRef<HTMLIFrameElement>(null);
  const [report, setReport] = useState<ReportDetail>();
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    reportsApi.preview(reportId).then(async (response) => {
      setReport(response.data);
      try {
        setHtml(await reportsApi.html(reportId));
      } catch {
        // Keep the existing snapshot preview available if the HTML document is unavailable.
        setHtml(null);
      }
    }).catch((cause: unknown) => {
      setError(cause instanceof ApiError ? cause.message : 'Preview unavailable.');
    });
  }, [reportId]);

  if (error) return <section className="page-section"><Link className="back-link" to="/reports"><ArrowLeft size={16}/> Reports register</Link><div className="notice error">{error}</div></section>;
  if (!report) return <section className="page-section"><div className="table-state">Preparing print preview…</div></section>;

  const handleDownloadPdf = async () => {
    if (!report) return;
    setDownloading(true);
    try {
      const filename = `${report.report_number.replace(/\//g, '_')}.pdf`;
      await reportsApi.downloadPdf(report.report_id, filename);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'PDF download failed.');
    } finally {
      setDownloading(false);
    }
  };

  const actions = (
    <div className="preview-actions">
      <Link className="secondary-button" to={`/reports/${report.report_id}`}>
        <ArrowLeft size={16}/> Report record
      </Link>
      <button className="primary-button" onClick={() => void handleDownloadPdf()} disabled={downloading || report.report_id.startsWith('demo-')}>
        <Download size={16}/> {downloading ? 'Downloading PDF…' : 'Download PDF'}
      </button>
      <button className="secondary-button" onClick={() => frame.current?.contentWindow?.print() || window.print()}>
        <Printer size={16}/> Print HTML
      </button>
    </div>
  );
  const isDemoFallback = report.report_id.startsWith('demo-') || report.report_id.startsWith('mock-');
  const containsDemoData = Boolean(report.contains_demo_data && isDemoFallback);

  if (html) return <section className="preview-wrap">{actions}<iframe ref={frame} title={`Printable report ${report.report_number}`} srcDoc={html} style={{ width: '100%', minHeight: '1120px', border: 0, background: '#fff' }} /></section>;

  const job = report.job_snapshot || {}, inst = report.instrument_snapshot || {}, approval = report.approval_snapshot || {};
  const customerName = (inst.customer_info as Record<string, unknown> | undefined)?.customer_name || (inst.location as Record<string, unknown> | undefined)?.customer_name || (report as unknown as Record<string, unknown>).customer_name;
  const refs = Array.isArray(approval.regulatory_rule_references) ? approval.regulatory_rule_references.join(', ') : approval.regulatory_rule_references;
  return <section className="preview-wrap">{actions}{containsDemoData && <aside role="alert" style={{ margin: '0 0 16px', padding: '14px 18px', border: '2px solid #9a6700', background: '#fff3cd', color: '#5c4300', display: 'grid', gap: '3px' }}><strong>DEMO/MOCK DATA</strong><span>NOT A MEASUREMENT RECORD</span></aside>}<aside className="notice info" role="status">Fallback preview — authoritative generated HTML is unavailable. Displayed content is not a measurement record.</aside><article className="report-paper"><header><div><p>METRIQ · NAWI TEST &amp; VERIFICATION MANAGEMENT</p><h1>{reportTypeLabels[report.report_type] || report.report_type?.replace(/_/g, ' ')}</h1><small>Application report output — not a frontend-issued certificate.</small></div><div>{report.report_number}<small>Generated {new Date(report.generated_at || report.created_at).toLocaleString('en-IN')}</small></div></header><Block title="Report metadata" rows={[["Report ID", report.report_id], ["Linked job/test", report.job_number || report.job_id], ["Status", report.report_status]]}/><Block title="Customer and instrument" rows={[["Customer", customerName], ["Instrument", inst.model_name || inst.model_number], ["Serial number", inst.serial_number], ["Manufacturer", inst.manufacturer], ["Accuracy class", inst.accuracy_class]]}/><Block title="Test and supplied references" rows={[["Recorded job outcome", job.status], ["Test date", job.completed_at || job.scheduled_date], ["Test centre", job.testing_centre_name], ["Approval number", approval.approval_number || report.approval_number || '—'], ["Regulatory profile", approval.regulatory_profile_id], ["Legal references supplied", refs], ["GATC reference", approval.gatc_reference]]}/><Block title="Results, evidence and conclusion" rows={[["Applicable tests", Array.isArray(job.applicable_tests) ? job.applicable_tests.join(', ') : undefined], ["Evidence entries", report.audit_snapshot?.length ? `${report.audit_snapshot.length} recorded workflow entries` : 'No evidence entries supplied'], ["Conclusion", 'This document displays the backend-recorded report snapshot and makes no independent compliance decision.']]}/><footer><span>Prepared by: {value(report.generated_by)}</span><span>Technical review / approval signature: ________________________</span></footer></article></section>;
}
