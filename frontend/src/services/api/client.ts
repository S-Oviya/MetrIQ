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

// ── Report types ──────────────────────────────────────────────────────────────

export interface ReportSummary extends ApiRecord {
  report_id: string;
  report_number: string;
  report_type: ReportType;
  job_id: string;
  job_number?: string;
  instrument_id: string;
  instrument?: string;
  customer_name?: string;
  test_date?: string;
  report_status: ReportStatus;
  generation_status: GenerationStatus;
  created_at: string;
  generated_at?: string | null;
  contains_demo_data?: boolean;
  has_pdf?: boolean;
  pdf_filename?: string;
}

export type ReportType = 'OIML_R76_2_TYPE_EVALUATION' | 'GATC_THIRD_SCHEDULE_VERIFICATION' | 'GENERIC_VERIFICATION' | 'REJECTION_DOCUMENT' | 'TECHNICAL_EVIDENCE_ANNEX';

export type ReportStatus = 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'ISSUED' | 'REJECTED' | 'ARCHIVED';
export type GenerationStatus = 'NOT_GENERATED' | 'GENERATING' | 'GENERATED' | 'FAILED';

// ── Job types ─────────────────────────────────────────────────────────────────

/** All status values the backend can emit — P3 pipeline + P5 execution vocabulary */
export type JobStatus =
  // P3 pipeline
  | 'DRAFT' | 'CREATED' | 'VALIDATED' | 'TEST_PLAN_GENERATED' | 'PLAN_GENERATED'
  | 'READY_FOR_TEST' | 'ASSIGNED' | 'IN_TESTING' | 'TEST_COMPLETED' | 'TESTS_COMPLETED'
  // P5 execution vocabulary
  | 'READY' | 'IN_PROGRESS' | 'RETEST_REQUIRED'
  // Review stage
  | 'REVIEW' | 'UNDER_REVIEW' | 'SUBMITTED_FOR_REVIEW'
  // Post-review
  | 'APPROVED' | 'REJECTED'
  // Terminal / report
  | 'REPORT_GENERATED' | 'CLOSED' | 'CERTIFIED' | 'CANCELLED';

/**
 * Statuses for which the backend allows report creation/generation.
 * Must match GENERATABLE_JOB_STATUSES in backend/app/reports/service.py.
 */
export const REPORT_GENERATABLE_JOB_STATUSES: JobStatus[] = [
  'APPROVED', 'REJECTED', 'CLOSED', 'CERTIFIED', 'REPORT_GENERATED',
];

/** Statuses considered "active" for dashboard counting */
export const ACTIVE_JOB_STATUSES: JobStatus[] = [
  'CREATED', 'VALIDATED', 'TEST_PLAN_GENERATED', 'PLAN_GENERATED',
  'READY_FOR_TEST', 'ASSIGNED', 'IN_TESTING', 'READY',
  'IN_PROGRESS', 'RETEST_REQUIRED',
];

/** Statuses considered "pending review" for dashboard counting */
export const REVIEW_JOB_STATUSES: JobStatus[] = [
  'REVIEW', 'UNDER_REVIEW', 'SUBMITTED_FOR_REVIEW', 'TEST_COMPLETED', 'TESTS_COMPLETED',
];

export interface ReportDetail extends ReportSummary {
  created_by?: string;
  generated_by?: string | null;
  generation_error?: string | null;
  source_updated_at?: string;
  job_snapshot?: ApiRecord | null;
  instrument_snapshot?: ApiRecord | null;
  approval_snapshot?: ApiRecord | null;
  audit_snapshot?: ApiRecord[];
}

export interface ReportsQuery {
  search?: string;
  report_status?: ReportStatus;
  generation_status?: GenerationStatus;
  sort_by?: 'created_at' | 'generated_at' | 'report_number' | 'report_status' | 'generation_status';
  sort_direction?: 'asc' | 'desc';
}

export interface DashboardMetrics extends ApiRecord {
  active_jobs?: number;
  pending_reviews?: number;
  failed_tests?: number;
  retests?: number;
  completed_jobs?: number;
  verification_due?: number;
  reports_generated?: number;
  reports_pending_generation?: number;
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
  applicable_tests?: string[];
  test_plan?: ApiRecord | null;
  state_history?: ApiRecord[];
}

export interface TestObservation {
  step_number?: number;
  applied_load?: number;
  indicated_value?: number;
  position?: string;
  time_seconds?: number;
  temperature_c?: number;
  extra_load?: number;
  tare_load?: number;
  checklist_item?: {
    item_id: string;
    title: string;
    clause: string;
    status: 'COMPLIANT' | 'NON_COMPLIANT' | 'NOT_APPLICABLE';
    is_mandatory?: boolean;
  };
  [key: string]: unknown;
}

export interface SubmitObservationsPayload {
  job_id: string;
  test_type: string;
  observations: TestObservation[];
  operator: string;
  notes?: string;
  metadata?: ApiRecord;
}

export interface InstrumentRecord extends ApiRecord {
  instrument_id: string;
  serial_number: string;
  manufacturer: string;
  model_name: string;
  model_number?: string;
  instrument_name?: string;
  description?: string;
  accuracy_class: 'I' | 'II' | 'III' | 'IIII' | 'CLASS_I' | 'CLASS_II' | 'CLASS_III' | 'CLASS_IIII' | string;
  max_capacity: number;
  min_capacity: number;
  e: number;
  d: number;
  n?: number;
  unit: string;
  instrument_type?: string;
  usage_type?: string;
  status: string;
  verification_status?: string;
  model_approval_number?: string;
  model_approval_date?: string;
  is_electronic?: boolean;
  next_re_verification_due?: string | null;
  last_verification_date?: string | null;
  location?: {
    customer_name?: string;
    site_name?: string;
    city?: string;
    state?: string;
    address?: string;
  };
  created_at?: string;
  updated_at?: string;
}

export interface CreateInstrumentPayload {
  instrument_id?: string;
  serial_number: string;
  manufacturer: string;
  model_name: string;
  model_number?: string;
  instrument_name?: string;
  description?: string;
  accuracy_class: string;
  max_capacity: number;
  min_capacity?: number;
  e: number;
  d?: number;
  unit?: string;
  instrument_type?: string;
  usage_type?: string;
  model_approval_number?: string;
  is_electronic?: boolean;
  location?: {
    customer_name?: string;
    site_name?: string;
    city?: string;
    state?: string;
    address?: string;
  };
}

export interface CreateJobPayload {
  instrument_id: string;
  job_type?: string;
  priority?: string;
  reason?: string;
  verification_reason?: string;
  assigned_inspector_id?: string;
  assigned_inspector_name?: string;
  scheduled_date?: string;
  testing_centre_name?: string;
  verification_location_type?: string;
  strict_gatc_validation?: boolean;
  notes?: string;
  created_by?: string;
}

export interface AuditLogEntry extends ApiRecord {
  id: string;
  timestamp: string;
  user_id: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string;
  old_value?: ApiRecord | null;
  new_value?: ApiRecord | null;
  metadata: ApiRecord;
  created_at: string;
}

// ── API clients ───────────────────────────────────────────────────────────────

export const reportsApi = {
  list: (query: ReportsQuery = {}) =>
    apiRequest<ApiEnvelope<ReportSummary[]>>(`/reports${toQueryString({ ...query })}`),

  create: (payload: { job_id: string; report_type: ReportType; created_by?: string }) =>
    apiRequest<ApiEnvelope<ReportDetail>>('/reports', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  createAndGenerate: (payload: { job_id: string; report_type: ReportType; generated_by?: string }) =>
    apiRequest<ApiEnvelope<ReportDetail>>('/reports/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  get: (id: string) =>
    apiRequest<ApiEnvelope<ReportDetail>>(`/reports/${encodeURIComponent(id)}`),

  generate: (id: string, generatedBy = 'SYSTEM') =>
    apiRequest<ApiEnvelope<ReportDetail>>(`/reports/${encodeURIComponent(id)}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ generated_by: generatedBy }),
    }),

  /** Returns report detail regardless of generation status (no 409). */
  preview: (id: string) =>
    apiRequest<ApiEnvelope<ReportDetail>>(`/reports/${encodeURIComponent(id)}/preview`).catch(
      async (err: unknown) => {
        if (err instanceof ApiError && err.status === 409) {
          // Report not yet generated — fall back to the plain get endpoint
          return apiRequest<ApiEnvelope<ReportDetail>>(`/reports/${encodeURIComponent(id)}`);
        }
        throw err;
      },
    ),

  html: (id: string) =>
    apiRequest<string>(`/reports/${encodeURIComponent(id)}/html`, {
      headers: { Accept: 'text/html' },
    }),

  pdfUrl: (id: string, download = false) =>
    `${apiBaseUrl()}/reports/${encodeURIComponent(id)}/pdf${download ? '?download=true' : ''}`,

  downloadPdf: async (id: string, filename?: string) => {
    const url = `${apiBaseUrl()}/reports/${encodeURIComponent(id)}/pdf?download=true`;
    const res = await fetch(url, {
      headers: { Accept: 'application/pdf' },
    });
    if (!res.ok) {
      let errorMsg = 'Failed to download report PDF.';
      try {
        const json = await res.json();
        errorMsg = json.message || json.detail?.message || json.detail || errorMsg;
      } catch {
        // Fall back to default error message
      }
      throw new ApiError(errorMsg, res.status);
    }
    const blob = await res.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = filename || `report-${id}.pdf`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(downloadUrl);
    document.body.removeChild(a);
  },
};

export const dashboardApi = {
  metrics: () => apiRequest<ApiEnvelope<DashboardMetrics>>('/dashboard/metrics'),
};

export interface JobValidationCheck {
  check: string;
  passed: boolean;
  errors?: string[];
  warnings?: string[];
  reason?: string;
  profile_id?: string;
  profile_status?: string;
  requires_manual_review?: boolean;
  location_type?: string;
  test_count?: number;
  test_ids?: string[];
  details?: ApiRecord;
}

export interface JobValidationResult {
  success: boolean;
  status_code?: number;
  job_id?: string;
  valid?: boolean;
  checks?: JobValidationCheck[];
  job?: JobSummary | ApiRecord;
  message?: string;
}

export const jobsApi = {
  list: (query: { status?: string; search?: string } = {}) =>
    apiRequest<{ success?: boolean; data: JobSummary[] }>('/jobs' + toQueryString(query)),

  get: (jobId: string) =>
    apiRequest<{ success?: boolean; data: JobSummary }>(`/jobs/${encodeURIComponent(jobId)}`),

  create: (payload: CreateJobPayload | ApiRecord) =>
    apiRequest<{ success?: boolean; job_id?: string; data: JobSummary; message?: string }>('/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  validate: (jobId: string, userId = 'SYSTEM') =>
    apiRequest<JobValidationResult>(`/jobs/${encodeURIComponent(jobId)}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    }),

  generatePlan: (jobId: string, userId = 'SYSTEM', forceRegenerate = false) =>
    apiRequest<{ success?: boolean; data: ApiRecord }>(`/jobs/${encodeURIComponent(jobId)}/generate-plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, force_regenerate: forceRegenerate }),
    }),

  assign: (jobId: string, payload: {
    inspector_id: string;
    inspector_name: string;
    testing_centre_name?: string;
    scheduled_date?: string;
    assigned_by?: string;
  }) =>
    apiRequest<{ success?: boolean; data: ApiRecord }>(`/jobs/${encodeURIComponent(jobId)}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  startExecution: (jobId: string, userId = 'SYSTEM') =>
    apiRequest<{ success?: boolean; status?: string; data?: ApiRecord }>(
      `/jobs/${encodeURIComponent(jobId)}/start-execution`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      },
    ),

  submitForReview: (jobId: string, payload: {
    reviewer?: string;
    comments?: string;
    submitted_by?: string;
  }) =>
    apiRequest<{ success?: boolean; data: ApiRecord }>(`/jobs/${encodeURIComponent(jobId)}/submit-review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  review: (jobId: string, payload: {
    decision: 'APPROVE' | 'REJECT' | 'RETURN_FOR_CORRECTION';
    reviewer: string;
    comments?: string;
    role?: string;
  }) =>
    apiRequest<{ success?: boolean; data: ApiRecord }>(`/jobs/${encodeURIComponent(jobId)}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  getAuditTrail: (jobId: string) =>
    apiRequest<{ success?: boolean; count: number; data: AuditLogEntry[] }>(
      `/jobs/${encodeURIComponent(jobId)}/audit`,
    ),

  testResults: (jobId: string) =>
    apiRequest<ApiEnvelope<ApiRecord>>(`/test-execution/${encodeURIComponent(jobId)}/results`),
};

export const testExecutionApi = {
  submit: (payload: SubmitObservationsPayload) =>
    apiRequest<ApiEnvelope<ApiRecord>>('/test-execution/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  getResults: (jobId: string) =>
    apiRequest<ApiEnvelope<ApiRecord>>(`/test-execution/${encodeURIComponent(jobId)}/results`),

  getAttempt: (attemptId: string) =>
    apiRequest<ApiEnvelope<ApiRecord>>(`/test-execution/attempts/${encodeURIComponent(attemptId)}`),
};

export const auditApi = {
  /** Full audit trail for a specific job */
  getJobTrail: (jobId: string) =>
    apiRequest<{ success?: boolean; count: number; data: AuditLogEntry[] }>(
      `/jobs/${encodeURIComponent(jobId)}/audit`,
    ),

  /** Audit trail for any entity type + id */
  getEntityTrail: (entityType: string, entityId: string) =>
    apiRequest<{ success?: boolean; count: number; data: AuditLogEntry[] }>(
      `/audit/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
    ),

  /** Filtered query across all audit logs */
  query: (params: {
    action?: string;
    actor?: string;
    entity_type?: string;
    from_date?: string;
    to_date?: string;
  } = {}) =>
    apiRequest<{ success?: boolean; count: number; data: AuditLogEntry[] }>(
      `/audit${toQueryString(params)}`,
    ),
};

export const archiveApi = {
  search: (params: ArchiveSearchParams = {}) =>
    apiRequest<ApiEnvelope<ReportSummary[]>>(`/archive/search${toQueryString({ ...params })}`),
};

export const instrumentsApi = {
  list: (params: {
    status?: string;
    accuracy_class?: string;
    instrument_type?: string;
    usage_type?: string;
    manufacturer?: string;
    customer?: string;
    search?: string;
  } = {}) =>
    apiRequest<{ success?: boolean; count: number; data: InstrumentRecord[] }>(
      `/instruments${toQueryString(params)}`,
    ),

  get: (id: string) =>
    apiRequest<{ success?: boolean; data: InstrumentRecord }>(
      `/instruments/${encodeURIComponent(id)}`,
    ),

  getBySerial: (serial: string) =>
    apiRequest<{ success?: boolean; data: InstrumentRecord }>(
      `/instruments/by-serial/${encodeURIComponent(serial)}`,
    ),

  create: (payload: CreateInstrumentPayload, enforceModelApproval = false) =>
    apiRequest<{ success?: boolean; data: InstrumentRecord; message?: string }>(
      `/instruments${toQueryString({ enforce_model_approval: enforceModelApproval })}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    ),

  update: (id: string, payload: Partial<CreateInstrumentPayload>) =>
    apiRequest<{ success?: boolean; data: InstrumentRecord; message?: string }>(
      `/instruments/${encodeURIComponent(id)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    ),

  delete: (id: string) =>
    apiRequest<{ success?: boolean; message: string }>(
      `/instruments/${encodeURIComponent(id)}`,
      { method: 'DELETE' },
    ),

  validateMetrology: (idOrPayload: string | Record<string, unknown>) => {
    if (typeof idOrPayload === 'string') {
      return apiRequest<{ success?: boolean; data?: ApiRecord; valid?: boolean; message?: string }>(
        `/instruments/${encodeURIComponent(idOrPayload)}/validate-metrology`,
      );
    }
    return apiRequest<{ success?: boolean; data?: ApiRecord; valid?: boolean; message?: string }>(
      '/instruments/validate-feasibility',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(idOrPayload),
      },
    );
  },
};
