export type ApiRecord = Record<string, unknown>;

export interface ApiEnvelope<T> {
  success?: boolean;
  data: T;
  message?: string;
  meta?: ApiRecord;
  timestamp?: string;
}

export interface ApiErrorPayload {
  code?: string;
  message?: string;
  details?: unknown;
  detail?: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details?: unknown;

  constructor(message: string, status: number, payload?: ApiErrorPayload) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = payload?.code;
    this.details = payload?.details;
  }
}

function apiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
}

function toQueryString(params?: Record<string, string | number | boolean | undefined>): string {
  if (!params) return '';

  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value));
  });
  const value = query.toString();
  return value ? `?${value}` : '';
}

async function parseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json();
  return response.text();
}

function errorMessage(payload: unknown, fallback: string): string {
  if (typeof payload === 'string' && payload) return payload;
  if (!payload || typeof payload !== 'object') return fallback;

  const body = payload as ApiErrorPayload;
  if (typeof body.message === 'string' && body.message) return body.message;
  if (typeof body.detail === 'string' && body.detail) return body.detail;
  if (Array.isArray(body.detail)) {
    const messages = body.detail
      .map((item) => item && typeof item === 'object' && typeof (item as { msg?: unknown }).msg === 'string'
        ? (item as { msg: string }).msg
        : '')
      .filter(Boolean);
    if (messages.length) return messages.join('; ');
  }
  if (body.detail && typeof body.detail === 'object') return errorMessage(body.detail, fallback);
  return fallback;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init.headers },
    });
  } catch {
    throw new ApiError('Unable to reach the MetrIQ service. Confirm that the backend is available.', 0);
  }

  const body = await parseBody(response);
  if (!response.ok) {
    const payload = typeof body === 'object' && body !== null ? body as ApiErrorPayload : undefined;
    const message = errorMessage(body, `Request failed (${response.status}).`);
    throw new ApiError(message, response.status, payload);
  }
  return body as T;
}

export interface ReportSummary extends ApiRecord {
  report_id: string; report_number: string; report_type: ReportType; job_id: string; job_number?: string; instrument_id: string; instrument?: string; customer_name?: string; test_date?: string; report_status: ReportStatus; generation_status: GenerationStatus; created_at: string; generated_at?: string | null; contains_demo_data?: boolean;
}
export type ReportType = 'OIML_R76_2_TYPE_EVALUATION' | 'GATC_THIRD_SCHEDULE_VERIFICATION' | 'GENERIC_VERIFICATION' | 'REJECTION_DOCUMENT' | 'TECHNICAL_EVIDENCE_ANNEX';
export type ReportStatus = 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'ISSUED' | 'REJECTED' | 'ARCHIVED';
export type GenerationStatus = 'NOT_GENERATED' | 'GENERATING' | 'GENERATED' | 'FAILED';
export type JobStatus = 'DRAFT' | 'CREATED' | 'VALIDATED' | 'TEST_PLAN_GENERATED' | 'READY_FOR_TEST' | 'IN_TESTING' | 'TEST_COMPLETED' | 'UNDER_REVIEW' | 'APPROVED' | 'REJECTED' | 'CLOSED' | 'CANCELLED' | 'PLAN_GENERATED' | 'ASSIGNED' | 'IN_PROGRESS' | 'TESTS_COMPLETED' | 'CERTIFIED';
export const REPORT_GENERATABLE_JOB_STATUSES: JobStatus[] = ['APPROVED', 'REJECTED', 'CLOSED', 'CERTIFIED'];
export interface ReportDetail extends ReportSummary { created_by?: string; generated_by?: string | null; generation_error?: string | null; source_updated_at?: string; job_snapshot?: ApiRecord | null; instrument_snapshot?: ApiRecord | null; approval_snapshot?: ApiRecord | null; audit_snapshot?: ApiRecord[]; }
export interface ReportsQuery { search?: string; report_status?: ReportStatus; generation_status?: GenerationStatus; sort_by?: 'created_at' | 'generated_at' | 'report_number' | 'report_status' | 'generation_status'; sort_direction?: 'asc' | 'desc'; }

export interface DashboardMetrics extends ApiRecord {
  active_jobs?: number;
  pending_reviews?: number;
  failed_tests?: number;
  retests?: number;
  completed_jobs?: number;
  verification_due?: number;
}

export interface ArchiveSearchParams {
  search?: string;
  serial_number?: string;
  instrument_id?: string;
  job_id?: string;
  report_number?: string;
  approval_number?: string;
  date_from?: string;
  date_to?: string;
  report_type?: ReportType;
  report_status?: ReportStatus;
}

export interface JobSummary extends ApiRecord {
  job_id: string;
  job_number?: string;
  instrument_id: string;
  instrument_snapshot?: ApiRecord;
  job_type?: string;
  status?: JobStatus;
  assigned_inspector_name?: string;
  scheduled_date?: string;
  completed_at?: string | null;
  updated_at?: string;
}

export const reportsApi = {
  list: (query: ReportsQuery = {}) => apiRequest<ApiEnvelope<ReportSummary[]>>(`/reports${toQueryString({ ...query })}`),
  create: (payload: { job_id: string; report_type: ReportType }) => apiRequest<ApiEnvelope<ReportDetail>>('/reports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  get: (id: string) => apiRequest<ApiEnvelope<ReportDetail>>(`/reports/${encodeURIComponent(id)}`),
  generate: (id: string) => apiRequest<ApiEnvelope<ReportDetail>>(`/reports/${encodeURIComponent(id)}/generate`, { method: 'POST' }),
  preview: (id: string) => apiRequest<ApiEnvelope<ReportDetail>>(`/reports/${encodeURIComponent(id)}/preview`),
  html: (id: string) => apiRequest<string>(`/reports/${encodeURIComponent(id)}/html`, { headers: { Accept: 'text/html' } }),
};

export const dashboardApi = {
  metrics: () => apiRequest<ApiEnvelope<DashboardMetrics>>('/dashboard/metrics'),
};

export const jobsApi = {
  list: (query: { status?: string; search?: string } = {}) =>
    apiRequest<{ success?: boolean; data: JobSummary[] }>('/jobs' + toQueryString(query)),
};

export const archiveApi = {
  search: (params: ArchiveSearchParams = {}) =>
    apiRequest<ApiEnvelope<ReportSummary[]>>(`/archive/search${toQueryString({ ...params })}`),
};
