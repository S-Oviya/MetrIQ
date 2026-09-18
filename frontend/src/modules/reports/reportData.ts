import { ApiError, JobSummary, ReportDetail, ReportSummary, ReportType, jobsApi, reportsApi } from '../../services/api/client';

export const reportTypeLabels: Record<ReportType, string> = {
  OIML_R76_2_TYPE_EVALUATION: 'OIML R76-2:2007 Type Evaluation Report',
  GATC_THIRD_SCHEDULE_VERIFICATION: 'GATC Third Schedule Verification Certificate',
  GENERIC_VERIFICATION: 'Configurable Verification Record',
  REJECTION_DOCUMENT: 'Rejection Document / Notice of Non-Compliance',
  TECHNICAL_EVIDENCE_ANNEX: 'Technical Evidence Annex',
};

export const supportedReportTypes = Object.entries(reportTypeLabels) as Array<[ReportType, string]>;

export const demoReports: ReportSummary[] = [
  { report_id: 'demo-rpt-001', report_number: 'METRIQ/2026/00841', report_type: 'GATC_THIRD_SCHEDULE_VERIFICATION', job_id: 'JOB-8421', job_number: 'JOB/2026/8421', instrument_id: 'NAWI-0147', instrument: 'Bench Scale · BX-30', customer_name: 'Aster Foods Pvt. Ltd.', test_date: '2026-09-16', report_status: 'ISSUED', generation_status: 'GENERATED', created_at: '2026-09-16T08:20:00Z', generated_at: '2026-09-16T11:42:00Z', contains_demo_data: true },
  { report_id: 'demo-rpt-002', report_number: 'METRIQ/2026/00839', report_type: 'REJECTION_DOCUMENT', job_id: 'JOB-8413', job_number: 'JOB/2026/8413', instrument_id: 'NAWI-0098', instrument: 'Platform Scale · PS-300', customer_name: 'Kaveri Logistics', test_date: '2026-09-15', report_status: 'REJECTED', generation_status: 'GENERATED', created_at: '2026-09-15T06:40:00Z', generated_at: '2026-09-15T15:06:00Z', contains_demo_data: true },
  { report_id: 'demo-rpt-003', report_number: 'METRIQ/2026/00837', report_type: 'TECHNICAL_EVIDENCE_ANNEX', job_id: 'JOB-8406', job_number: 'JOB/2026/8406', instrument_id: 'NAWI-0211', instrument: 'Weighbridge · WB-60', customer_name: 'Harbor Aggregates', test_date: '2026-09-14', report_status: 'DRAFT', generation_status: 'NOT_GENERATED', created_at: '2026-09-14T09:00:00Z', contains_demo_data: true },
];

export const demoJobs: JobSummary[] = [
  { job_id: 'JOB-8450', job_number: 'JOB/2026/8450', instrument_id: 'NAWI-0234', instrument_snapshot: { model_name: 'Retail Scale · RS-15' }, job_type: 'RE_VERIFICATION', status: 'IN_TESTING', assigned_inspector_name: 'S. Iyer', scheduled_date: '2026-09-18' },
  { job_id: 'JOB-8448', job_number: 'JOB/2026/8448', instrument_id: 'NAWI-0188', instrument_snapshot: { model_name: 'Platform Scale · PS-300' }, job_type: 'POST_REPAIR', status: 'UNDER_REVIEW', assigned_inspector_name: 'R. Mehta', scheduled_date: '2026-09-18' },
  { job_id: 'JOB-8442', job_number: 'JOB/2026/8442', instrument_id: 'NAWI-0062', instrument_snapshot: { model_name: 'Bench Scale · BX-30' }, job_type: 'RETEST', status: 'READY_FOR_TEST', assigned_inspector_name: 'A. Thomas', scheduled_date: '2026-09-19' },
];

export function demoReportDetail(id: string): ReportDetail | undefined {
  const summary = demoReports.find((report) => report.report_id === id);
  if (!summary) return undefined;
  return { ...summary, generated_by: 'Demo workflow', job_snapshot: { status: summary.report_status === 'ISSUED' ? 'CLOSED' : 'UNDER_REVIEW', job_type: 'RE_VERIFICATION', completed_at: summary.test_date, testing_centre_name: 'Demo Technical Centre', assigned_inspector_name: 'Demo Inspector', applicable_tests: ['Recorded backend test evidence'] }, instrument_snapshot: { model_name: summary.instrument, serial_number: 'DEMO-SERIAL-001', manufacturer: 'Demo manufacturer' }, approval_snapshot: { approval_number: 'Demo approval reference', regulatory_profile_id: 'Backend-supplied profile', regulatory_rule_references: ['Backend-supplied reference'] }, audit_snapshot: [] };
}

export interface DataSource<T> { data: T; isDemo: boolean; error?: string }

export async function loadReports(): Promise<DataSource<ReportSummary[]>> {
  try { return { data: (await reportsApi.list()).data, isDemo: false }; }
  catch (error) { return { data: demoReports, isDemo: true, error: error instanceof ApiError ? error.message : 'Report service unavailable.' }; }
}

export async function loadJobs(): Promise<DataSource<JobSummary[]>> {
  try { return { data: (await jobsApi.list()).data, isDemo: false }; }
  catch (error) { return { data: demoJobs, isDemo: true, error: error instanceof ApiError ? error.message : 'Job service unavailable.' }; }
}
