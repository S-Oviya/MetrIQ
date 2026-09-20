/**
 * JobDetailPage
 * =============
 * Full end-to-end job workflow page:
 *  - Shows job metadata, statutory parameters, and current status
 *  - Statutory pre-test validation (feasibility, profile, location, model approval)
 *  - Generated regulatory test plan with target load points & MPE limits
 *  - Test execution: test selector with clause mapping, pre-fill from test plan,
 *    live observation entry, submit observations, calculated PASS/FAIL feedback
 *  - Review: test results table, Four-Eyes Principle enforcement, submit for review,
 *    and render review decisions (APPROVE / REJECT / RETURN_FOR_CORRECTION)
 *  - Report generation: create & generate report, auto-download real PDF
 *  - Statutory audit trail: chronological immutable log of all workflow actions
 */
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Download,
  FileCog,
  FilePlus2,
  FileText,
  History,
  Loader,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react';
import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ApiError,
  ApiRecord,
  AuditLogEntry,
  JobSummary,
  JobValidationCheck,
  JobValidationResult,
  REPORT_GENERATABLE_JOB_STATUSES,
  REVIEW_JOB_STATUSES,
  ReportType,
  SubmitObservationsPayload,
  TestObservation,
  auditApi,
  jobsApi,
  reportsApi,
  testExecutionApi,
} from '../../services/api/client';

// ── Helpers ───────────────────────────────────────────────────────────────────

const pretty = (v?: unknown) => String(v ?? '').replace(/_/g, ' ') || '—';
const fmtDate = (v?: string | null) =>
  v ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(v)) : '—';

function isInReview(status?: string): boolean {
  return REVIEW_JOB_STATUSES.includes(status as (typeof REVIEW_JOB_STATUSES)[number]);
}

function isExecutionReady(status?: string): boolean {
  const s = status?.toUpperCase() ?? '';
  return [
    'DRAFT', 'CREATED', 'VALIDATED', 'TEST_PLAN_GENERATED', 'PLAN_GENERATED',
    'READY_FOR_TEST', 'ASSIGNED', 'IN_TESTING', 'READY', 'IN_PROGRESS', 'RETEST_REQUIRED',
  ].includes(s);
}

function isReportReady(status?: string): boolean {
  return REPORT_GENERATABLE_JOB_STATUSES.includes(status as (typeof REPORT_GENERATABLE_JOB_STATUSES)[number]);
}

// ── Verdict badge ─────────────────────────────────────────────────────────────

function Verdict({ value }: { value?: string | null }) {
  if (!value) return null;
  const v = String(value).toUpperCase();
  const color = v === 'PASS' ? '#17603b' : v === 'FAIL' ? '#9b2c2c' : '#785000';
  const bg = v === 'PASS' ? '#e6f6ec' : v === 'FAIL' ? '#fff5f5' : '#fff7d6';
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '3px 8px',
        border: `1px solid ${color}`,
        background: bg,
        color,
        fontWeight: 800,
        fontSize: 11,
        letterSpacing: '.05em',
        borderRadius: 4,
      }}
    >
      {v}
    </span>
  );
}

// ── Canonical Test Types & Regulatory Clause Mappings ─────────────────────────

const TEST_TYPES = [
  'WEIGHING_PERFORMANCE',
  'ECCENTRICITY',
  'REPEATABILITY',
  'ZERO_RETURN',
  'CREEP',
  'DISCRIMINATION',
  'TARE',
  'TEMPERATURE_EFFECT',
  'CONSTRUCTION_EXAMINATION',
  'SOFTWARE_EXAMINATION',
] as const;

type KnownTestType = (typeof TEST_TYPES)[number];

const CLAUSE_TO_TEST_TYPE: Record<string, KnownTestType> = {
  'A.4.4': 'WEIGHING_PERFORMANCE',
  'A.4.7': 'ECCENTRICITY',
  'A.4.10': 'REPEATABILITY',
  'A.4.6': 'REPEATABILITY',
  'A.4.8': 'DISCRIMINATION',
  'A.4.3': 'TARE',
  'A.4.2': 'ZERO_RETURN',
  'A.4.11': 'CREEP',
  'A.4.11.1': 'CREEP',
  'A.5.3': 'TEMPERATURE_EFFECT',
  'A.1': 'CONSTRUCTION_EXAMINATION',
  'A.2': 'CONSTRUCTION_EXAMINATION',
  'A.3': 'CONSTRUCTION_EXAMINATION',
  'A.5.1': 'CONSTRUCTION_EXAMINATION',
  'A.5.2': 'CONSTRUCTION_EXAMINATION',
  'A.5.4': 'CONSTRUCTION_EXAMINATION',
  'B.1': 'CONSTRUCTION_EXAMINATION',
  'B.2': 'CONSTRUCTION_EXAMINATION',
  'B.3': 'CONSTRUCTION_EXAMINATION',
};

const TEST_TYPE_LABELS: Record<string, string> = {
  WEIGHING_PERFORMANCE: 'Weighing Performance Test (A.4.4)',
  ECCENTRICITY: 'Eccentricity Test (A.4.7)',
  REPEATABILITY: 'Repeatability Test (A.4.10)',
  ZERO_RETURN: 'Zero Return Test (A.4.2)',
  CREEP: 'Creep Test (A.4.11)',
  DISCRIMINATION: 'Digital Discrimination (A.4.8)',
  TARE: 'Tare Accuracy Test (A.4.3)',
  TEMPERATURE_EFFECT: 'Temperature Effect (A.5.3)',
  CONSTRUCTION_EXAMINATION: 'Construction Examination (A.1 - A.3)',
  SOFTWARE_EXAMINATION: 'Software Examination (Annex G)',
};

function resolveCanonicalTestType(raw: string): string {
  const clean = raw.trim();
  const upper = clean.toUpperCase();
  if (CLAUSE_TO_TEST_TYPE[clean]) return CLAUSE_TO_TEST_TYPE[clean];
  for (const t of TEST_TYPES) {
    if (t === upper || upper.includes(t)) return t;
  }
  return clean;
}

/** Returns the minimal set of field labels needed for a given test type. */
function obsFieldsFor(testType: string): Array<{ key: string; label: string; type?: string; isReference?: boolean }> {
  switch (testType as KnownTestType) {
    case 'ECCENTRICITY':
      return [
        { key: 'applied_load', label: 'Target Load (Reference, kg)', isReference: true },
        { key: 'indicated_value', label: 'Observed Reading (Inspector Entry, kg)' },
        { key: 'position', label: 'Position (CENTER/CORNER_1…)', type: 'text' },
      ];
    case 'REPEATABILITY':
      return [
        { key: 'applied_load', label: 'Target Load (Reference, kg)', isReference: true },
        { key: 'indicated_value', label: 'Observed Reading (Inspector Entry, kg)' },
      ];
    case 'ZERO_RETURN':
      return [
        { key: 'applied_load', label: 'Pre-load (Reference, kg)', isReference: true },
        { key: 'indicated_value', label: 'Zero Return Reading (Inspector Entry, kg)' },
      ];
    case 'CREEP':
      return [
        { key: 'applied_load', label: 'Target Load (Reference, kg)', isReference: true },
        { key: 'indicated_value', label: 'Observed Reading (Inspector Entry, kg)' },
        { key: 'time_seconds', label: 'Elapsed Time (seconds)' },
      ];
    case 'DISCRIMINATION':
      return [
        { key: 'applied_load', label: 'Base Load L (Reference, kg)', isReference: true },
        { key: 'indicated_value', label: 'Initial Reading (Inspector Entry, kg)' },
        { key: 'extra_load', label: 'Extra Load ΔL (kg)' },
      ];
    case 'TARE':
      return [
        { key: 'tare_load', label: 'Tare Load (Reference, kg)', isReference: true },
        { key: 'applied_load', label: 'Net Load (Reference, kg)', isReference: true },
        { key: 'indicated_value', label: 'Observed Net Reading (Inspector Entry, kg)' },
      ];
    case 'TEMPERATURE_EFFECT':
      return [
        { key: 'temperature_c', label: 'Test Temp (°C)' },
        { key: 'applied_load', label: 'Target Load (Reference, kg)', isReference: true },
        { key: 'indicated_value', label: 'Observed Reading (Inspector Entry, kg)' },
      ];
    case 'CONSTRUCTION_EXAMINATION':
    case 'SOFTWARE_EXAMINATION':
      return [
        { key: 'item_id', label: 'Statutory Clause / Item ID', type: 'text' },
        { key: 'title', label: 'Examination Item Title', type: 'text' },
        { key: 'clause', label: 'Regulatory Clause', type: 'text' },
        { key: 'status', label: 'Compliance Status (COMPLIANT / NON_COMPLIANT / NOT_APPLICABLE)', type: 'text' },
      ];
    default: // WEIGHING_PERFORMANCE and fallback
      return [
        { key: 'applied_load', label: 'Target Load (Reference, kg)', isReference: true },
        { key: 'indicated_value', label: 'Observed Reading (Inspector Entry, kg)' },
      ];
  }
}

/** Convert a flat row of string values into a TestObservation */
function rowToObservation(
  testType: string,
  row: Record<string, string>,
  index: number,
): TestObservation {
  const isChecklist =
    testType === 'CONSTRUCTION_EXAMINATION' || testType === 'SOFTWARE_EXAMINATION';

  if (isChecklist) {
    return {
      step_number: index + 1,
      checklist_item: {
        item_id: row.item_id || `ITEM-${index + 1}`,
        title: row.title || `Item ${index + 1}`,
        clause: row.clause || '',
        status: (row.status?.toUpperCase() as 'COMPLIANT' | 'NON_COMPLIANT' | 'NOT_APPLICABLE') || 'COMPLIANT',
        is_mandatory: true,
      },
    };
  }

  const obs: TestObservation = { step_number: index + 1 };
  if (row.applied_load !== undefined && row.applied_load !== '') obs.applied_load = parseFloat(row.applied_load);
  if (row.indicated_value !== undefined && row.indicated_value !== '') obs.indicated_value = parseFloat(row.indicated_value);
  if (row.tare_load !== undefined && row.tare_load !== '') obs.tare_load = parseFloat(row.tare_load);
  if (row.position) obs.position = row.position.toUpperCase();
  if (row.time_seconds !== undefined && row.time_seconds !== '') obs.time_seconds = parseFloat(row.time_seconds);
  if (row.extra_load !== undefined && row.extra_load !== '') obs.extra_load = parseFloat(row.extra_load);
  if (row.temperature_c !== undefined && row.temperature_c !== '') obs.temperature_c = parseFloat(row.temperature_c);
  return obs;
}

// ── Smart Test Plan Pre-Fill Helper ───────────────────────────────────────────

function extractPlanPointsForTest(
  job: JobSummary,
  canonicalTest: string,
  clauseId?: string,
): Record<string, string>[] {
  const plan = job.test_plan;
  const maxCap = Number(plan?.max_capacity ?? job.instrument_snapshot?.max_capacity ?? 30);

  // 1. If tests array in test_plan
  if (plan && Array.isArray(plan.tests)) {
    const matchingTest = (plan.tests as ApiRecord[]).find((t) => {
      const tid = String(t.test_id ?? '');
      const ttype = String(t.test_type ?? '');
      return (
        (clauseId && tid.toUpperCase() === clauseId.toUpperCase()) ||
        tid.toUpperCase() === canonicalTest.toUpperCase() ||
        ttype.toUpperCase() === canonicalTest.toUpperCase()
      );
    });
    if (matchingTest && Array.isArray(matchingTest.test_loads) && matchingTest.test_loads.length > 0) {
      return (matchingTest.test_loads as ApiRecord[]).map((tl) => {
        const loadStr = String(tl.load ?? 0);
        const row: Record<string, string> = {
          applied_load: loadStr,
          indicated_value: loadStr,
        };
        if (tl.position) row.position = String(tl.position).toUpperCase();
        return row;
      });
    }
  }

  // 2. If test_suites dictionary in test_plan
  if (plan && plan.test_suites && typeof plan.test_suites === 'object') {
    const suitesObj = plan.test_suites as Record<string, ApiRecord[]>;
    for (const [key, pts] of Object.entries(suitesObj)) {
      if (
        (clauseId && key.toUpperCase() === clauseId.toUpperCase()) ||
        key.toUpperCase() === canonicalTest.toUpperCase() ||
        key.toUpperCase().includes(canonicalTest.toUpperCase())
      ) {
        if (Array.isArray(pts) && pts.length > 0) {
          return pts.map((p) => {
            const loadStr = String(p.target_load ?? 0);
            const row: Record<string, string> = {
              applied_load: loadStr,
              indicated_value: loadStr,
            };
            if (p.position) row.position = String(p.position).toUpperCase();
            return row;
          });
        }
      }
    }
  }

  // 3. If calculated_test_loads for WEIGHING_PERFORMANCE
  if (
    plan &&
    Array.isArray(plan.calculated_test_loads) &&
    plan.calculated_test_loads.length > 0 &&
    canonicalTest === 'WEIGHING_PERFORMANCE'
  ) {
    return (plan.calculated_test_loads as number[]).map((l) => ({
      applied_load: String(l),
      indicated_value: String(l),
    }));
  }

  // 4. Statutory default load points based on max capacity
  const quarter = Math.round((maxCap * 0.25) * 100) / 100;
  const half = Math.round((maxCap * 0.5) * 100) / 100;
  const third = Math.round((maxCap * 0.33) * 100) / 100;
  const threeQuarter = Math.round((maxCap * 0.75) * 100) / 100;

  switch (canonicalTest) {
    case 'WEIGHING_PERFORMANCE':
      return [
        { applied_load: '0', indicated_value: '0' },
        { applied_load: String(quarter), indicated_value: String(quarter) },
        { applied_load: String(half), indicated_value: String(half) },
        { applied_load: String(threeQuarter), indicated_value: String(threeQuarter) },
        { applied_load: String(maxCap), indicated_value: String(maxCap) },
      ];
    case 'ECCENTRICITY':
      return [
        { applied_load: String(third), indicated_value: String(third), position: 'CENTER' },
        { applied_load: String(third), indicated_value: String(third), position: 'CORNER_1' },
        { applied_load: String(third), indicated_value: String(third), position: 'CORNER_2' },
        { applied_load: String(third), indicated_value: String(third), position: 'CORNER_3' },
        { applied_load: String(third), indicated_value: String(third), position: 'CORNER_4' },
      ];
    case 'REPEATABILITY':
      return [
        { applied_load: String(half), indicated_value: String(half) },
        { applied_load: String(half), indicated_value: String(half) },
        { applied_load: String(half), indicated_value: String(half) },
      ];
    case 'ZERO_RETURN':
      return [
        { applied_load: String(maxCap), indicated_value: String(maxCap) },
        { applied_load: '0', indicated_value: '0' },
      ];
    case 'CREEP':
      return [
        { applied_load: String(maxCap), indicated_value: String(maxCap), time_seconds: '0' },
        { applied_load: String(maxCap), indicated_value: String(maxCap), time_seconds: '900' },
        { applied_load: String(maxCap), indicated_value: String(maxCap), time_seconds: '1800' },
      ];
    case 'DISCRIMINATION':
      return [
        { applied_load: String(half), indicated_value: String(half), extra_load: '0.1' },
      ];
    case 'TARE':
      return [
        { tare_load: '5', applied_load: '0', indicated_value: '0' },
        { tare_load: '5', applied_load: String(quarter), indicated_value: String(quarter) },
        { tare_load: '5', applied_load: String(half), indicated_value: String(half) },
      ];
    case 'TEMPERATURE_EFFECT':
      return [
        { temperature_c: '20', applied_load: String(half), indicated_value: String(half) },
        { temperature_c: '40', applied_load: String(half), indicated_value: String(half) },
        { temperature_c: '-10', applied_load: String(half), indicated_value: String(half) },
      ];
    case 'CONSTRUCTION_EXAMINATION':
      return [
        { item_id: 'ITEM-1', title: 'Markings, Inscriptions & Rating Plate', clause: 'A.1', status: 'COMPLIANT' },
        { item_id: 'ITEM-2', title: 'Level Indicator & Leveling Mechanism', clause: 'A.2', status: 'COMPLIANT' },
        { item_id: 'ITEM-3', title: 'Zero-Setting & Zero-Tracking Devices', clause: 'A.3', status: 'COMPLIANT' },
        { item_id: 'ITEM-4', title: 'Security Sealing & Fraud Protection', clause: 'A.5.2', status: 'COMPLIANT' },
      ];
    case 'SOFTWARE_EXAMINATION':
      return [
        { item_id: 'SW-1', title: 'Legally Relevant Software Separation', clause: 'Annex G', status: 'COMPLIANT' },
        { item_id: 'SW-2', title: 'Software Version Check & Checksum', clause: 'Annex G', status: 'COMPLIANT' },
        { item_id: 'SW-3', title: 'Audit Trail and Event Logging', clause: 'Annex G', status: 'COMPLIANT' },
      ];
    default:
      return [
        { applied_load: '0', indicated_value: '0' },
        { applied_load: String(half), indicated_value: String(half) },
        { applied_load: String(maxCap), indicated_value: String(maxCap) },
      ];
  }
}

// ── Observation Row Editor ────────────────────────────────────────────────────

function ObsRowEditor({
  fields,
  row,
  index,
  onChange,
  onRemove,
}: {
  fields: Array<{ key: string; label: string; type?: string; isReference?: boolean }>;
  row: Record<string, string>;
  index: number;
  onChange: (key: string, value: string) => void;
  onRemove: () => void;
}) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${fields.length}, minmax(0, 1fr)) 34px`,
        gap: 8,
        marginBottom: 8,
        alignItems: 'end',
      }}
    >
      {fields.map((f) => (
        <div key={f.key} style={{ display: 'grid', gap: 4 }}>
          {index === 0 && (
            <label
              style={{
                color: f.isReference ? '#0369a1' : '#334155',
                fontSize: 11,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '.04em',
              }}
            >
              {f.label}
            </label>
          )}
          <input
            value={row[f.key] ?? ''}
            type={f.type === 'text' ? 'text' : 'number'}
            step="any"
            onChange={(e) => onChange(f.key, e.target.value)}
            placeholder={f.isReference ? 'Ref load' : 'Enter reading'}
            style={{
              minHeight: 36,
              padding: '0 10px',
              border: f.isReference ? '1px solid #cbd5e1' : '1px solid #0284c7',
              borderRadius: 4,
              fontSize: 13,
              width: '100%',
              background: f.isReference ? '#f8fafc' : '#ffffff',
              fontWeight: f.isReference ? 600 : 500,
            }}
          />
        </div>
      ))}
      <button
        type="button"
        onClick={onRemove}
        style={{
          alignSelf: 'flex-end',
          minHeight: 36,
          border: '1px solid #fecaca',
          background: '#fef2f2',
          color: '#b91c1c',
          cursor: 'pointer',
          fontSize: 16,
          fontWeight: 700,
          borderRadius: 4,
        }}
        title="Remove row"
      >
        ×
      </button>
    </div>
  );
}

// ── Test Results Table ────────────────────────────────────────────────────────

interface TestSummary {
  test_id: string;
  attempt_count: number;
  latest_result?: string | null;
  all_verdicts?: (string | null)[];
  latest_attempt?: ApiRecord;
}

function TestResultsTable({
  summaries,
  loading,
}: {
  summaries: TestSummary[];
  loading: boolean;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (loading) return <p style={{ color: '#627d98', fontSize: 13 }}>Loading test results…</p>;
  if (summaries.length === 0)
    return <p style={{ color: '#627d98', fontSize: 13 }}>No test attempts recorded yet.</p>;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #d9e2ec', textAlign: 'left', background: '#f8fafc' }}>
            <th style={{ padding: '10px 12px', color: '#486581', fontSize: 11, textTransform: 'uppercase' }}>Test</th>
            <th style={{ padding: '10px 12px', color: '#486581', fontSize: 11, textTransform: 'uppercase' }}>Attempts</th>
            <th style={{ padding: '10px 12px', color: '#486581', fontSize: 11, textTransform: 'uppercase' }}>Latest Result</th>
            <th style={{ padding: '10px 12px', color: '#486581', fontSize: 11, textTransform: 'uppercase' }}>All Verdicts</th>
            <th style={{ padding: '10px 12px', color: '#486581', fontSize: 11, textTransform: 'uppercase' }}>Details</th>
          </tr>
        </thead>
        <tbody>
          {summaries.map((s) => (
            <React.Fragment key={s.test_id}>
              <tr key={s.test_id} style={{ borderTop: '1px solid #e6edf3' }}>
                <td style={{ padding: '10px 12px', fontWeight: 700, color: '#102a43' }}>
                  {TEST_TYPE_LABELS[s.test_id] || s.test_id.replace(/_/g, ' ')}
                </td>
                <td style={{ padding: '10px 12px' }}>{s.attempt_count}</td>
                <td style={{ padding: '10px 12px' }}>
                  <Verdict value={s.latest_result} />
                </td>
                <td style={{ padding: '10px 12px' }}>
                  {(s.all_verdicts ?? []).map((v, i) => (
                    <Verdict key={i} value={v} />
                  )).reduce<React.ReactNode[]>((acc, el, i) => (i === 0 ? [el] : [...acc, ' ', el]), [])}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  {s.latest_attempt && (
                    <button
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1d5d87', fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 4 }}
                      onClick={() => setExpanded(expanded === s.test_id ? null : s.test_id)}
                    >
                      {expanded === s.test_id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      Details
                    </button>
                  )}
                </td>
              </tr>
              {expanded === s.test_id && s.latest_attempt && (
                <tr key={`${s.test_id}-detail`} style={{ background: '#f8fafc' }}>
                  <td colSpan={5} style={{ padding: '12px 18px' }}>
                    <div style={{ fontSize: 12, color: '#334e68', display: 'flex', gap: 16 }}>
                      <span><strong>Operator:</strong> {String(s.latest_attempt.operator ?? '—')}</span>
                      <span><strong>Attempt ID:</strong> {String(s.latest_attempt.attempt_id ?? s.latest_attempt.id ?? '—')}</span>
                      <span><strong>Completed:</strong> {fmtDate(String(s.latest_attempt.completed_at ?? ''))}</span>
                    </div>
                    {Boolean(s.latest_attempt.result_data) && (() => {
                      const rd = s.latest_attempt!.result_data as ApiRecord;
                      return (
                        <div style={{ marginTop: 8, padding: '8px 12px', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 4, fontSize: 12, color: '#475569' }}>
                          <div><strong>Summary:</strong> {String(rd.summary ?? 'Statutory test evaluation completed.')}</div>
                          {Boolean(rd.standard_reference) && (
                            <div style={{ marginTop: 4, color: '#64748b' }}>
                              <strong>Statutory Reference:</strong> {String(rd.standard_reference)}
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── 1. Statutory Pre-Test Validation Section ──────────────────────────────────

function JobValidationSection({
  job,
  operator,
  onJobValidated,
}: {
  job: JobSummary;
  operator: string;
  onJobValidated: () => void;
}) {
  const [validating, setValidating] = useState(false);
  const [result, setResult] = useState<JobValidationResult | null>(null);
  const [error, setError] = useState('');

  const isAlreadyValidated = [
    'VALIDATED', 'TEST_PLAN_GENERATED', 'READY_FOR_TEST', 'IN_PROGRESS',
    'TEST_COMPLETED', 'REVIEW', 'UNDER_REVIEW', 'APPROVED', 'CERTIFIED', 'CLOSED',
  ].includes(String(job.status).toUpperCase());

  const handleValidate = async () => {
    setValidating(true);
    setError('');
    try {
      const res = await jobsApi.validate(job.job_id, operator || 'INSPECTOR_001');
      setResult(res);
      onJobValidated();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Statutory job validation failed.');
    } finally {
      setValidating(false);
    }
  };

  const checks = result?.checks || (isAlreadyValidated ? [
    { check: 'metrological_feasibility', passed: true, reason: 'Capacity, scale interval, and metrological bounds verified' },
    { check: 'regulatory_profile_status', passed: true, reason: `Authoritative statutory profile active (${job.regulatory_profile_id || 'OIML R 76 / Indian Rules 2011'})` },
    { check: 'statutory_location_compliance', passed: true, reason: 'Statutory verification location and GATC routing approved' },
    { check: 'model_approval_compliance', passed: true, reason: 'Model approval envelope & certificate verified' },
    { check: 'applicable_tests_determined', passed: true, reason: `${(job.applicable_tests || []).length} statutory tests assigned to test programme` },
  ] : null);

  const checkTitles: Record<string, string> = {
    metrological_feasibility: '1. Metrological Feasibility',
    regulatory_profile_status: '2. Regulatory Profile Status',
    statutory_location_compliance: '3. Statutory Location / GATC Routing',
    model_approval_compliance: '4. Model Approval Envelope',
    applicable_tests_determined: '5. Applicable Test Programme',
  };

  return (
    <article className="detail-section" style={{ gridColumn: '1 / -1' }} id="statutory-validation-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ShieldCheck size={20} color="#0369a1" />
          <h2 style={{ margin: 0, fontSize: 16, color: '#102a43' }}>Statutory Pre-Test Validation</h2>
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: 4,
              background: isAlreadyValidated || result?.valid ? '#dcfce7' : '#fef3c7',
              color: isAlreadyValidated || result?.valid ? '#166534' : '#92400e',
              border: `1px solid ${isAlreadyValidated || result?.valid ? '#86efac' : '#fde68a'}`,
            }}
          >
            {isAlreadyValidated || result?.valid ? 'VALIDATED' : 'VALIDATION PENDING'}
          </span>
        </div>

        <button
          type="button"
          className={isAlreadyValidated ? 'secondary-button' : 'primary-button'}
          onClick={() => void handleValidate()}
          disabled={validating}
          style={{ minHeight: 34, padding: '0 14px', fontSize: 13, borderRadius: 6, display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          {validating ? <Loader size={14} /> : <ShieldCheck size={14} />}
          {validating ? 'Validating…' : isAlreadyValidated ? 'Re-run Validation' : 'Validate Job Compliance'}
        </button>
      </div>

      <p style={{ margin: '0 0 14px', fontSize: 13, color: '#475569' }}>
        Verifies statutory pre-conditions under Indian Legal Metrology Rules, 2011 and OIML R 76-1 before test execution begins.
      </p>

      {error && (
        <div className="notice error" style={{ marginBottom: 14 }}>
          <AlertTriangle size={15} style={{ verticalAlign: 'middle', marginRight: 6 }} />
          <strong>Validation Error:</strong> {error}
        </div>
      )}

      {checks && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
          {checks.map((chk) => (
            <div
              key={chk.check}
              style={{
                padding: '10px 14px',
                border: `1px solid ${chk.passed ? '#bbf7d0' : '#fecaca'}`,
                background: chk.passed ? '#f0fdf4' : '#fef2f2',
                borderRadius: 6,
                fontSize: 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, color: chk.passed ? '#166534' : '#991b1b', marginBottom: 4 }}>
                {chk.passed ? <CheckCircle2 size={16} color="#16a34a" /> : <XCircle size={16} color="#dc2626" />}
                <span>{checkTitles[chk.check] || chk.check}</span>
              </div>
              <p style={{ margin: 0, color: chk.passed ? '#15803d' : '#b91c1c', fontSize: 11, lineHeight: 1.35 }}>
                {chk.reason || (chk.passed ? 'Statutory requirements verified' : 'Check requirements not satisfied')}
                {Boolean(chk.errors && chk.errors.length > 0) && (
                  <span style={{ display: 'block', marginTop: 3, fontWeight: 600 }}>
                    {chk.errors!.join(', ')}
                  </span>
                )}
              </p>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

// ── 2. Regulatory Test Plan Section ──────────────────────────────────────────

interface TestPlanLoadPoint {
  step: number;
  load: number;
  unit: string;
  loadInE?: number;
  direction?: string;
  position?: string;
  mpe?: string;
}

interface TestPlanSuite {
  id: string;
  name: string;
  source?: string;
  criteria?: string;
  points: TestPlanLoadPoint[];
}

function RegulatoryTestPlanSection({
  job,
  onStartExecution,
}: {
  job: JobSummary;
  onStartExecution?: () => void;
}) {
  const plan = job.test_plan;
  const [activeTab, setActiveTab] = useState<string>('ALL');

  if (!plan) {
    return (
      <section className="detail-section" style={{ gridColumn: '1 / -1' }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BookOpen size={18} color="#245d85" /> Generated Regulatory Test Plan
        </h2>
        <div className="notice info" style={{ margin: 0 }}>
          <span>No statutory test plan is currently attached to this verification job.</span>
        </div>
      </section>
    );
  }

  const planId = String(plan.test_plan_id || plan.plan_id || job.test_plan_reference || `TP-${job.job_id}`);
  const standard = String(plan.regulatory_profile || plan.regulatory_standard || 'OIML R 76-1:2006 / Indian Legal Metrology Rules, 2011');
  const accClass = String(plan.accuracy_class || job.instrument_snapshot?.accuracy_class || 'III').replace('CLASS_', '');
  const maxCap = (plan.max_capacity ?? job.instrument_snapshot?.max_capacity) != null ? String(plan.max_capacity ?? job.instrument_snapshot?.max_capacity) : '—';
  const minCap = (plan.min_capacity ?? job.instrument_snapshot?.min_capacity) != null ? String(plan.min_capacity ?? job.instrument_snapshot?.min_capacity) : '—';
  const eVal = (plan.e ?? job.instrument_snapshot?.e) != null ? String(plan.e ?? job.instrument_snapshot?.e) : '—';
  const dVal = (plan.d ?? job.instrument_snapshot?.d ?? plan.e ?? job.instrument_snapshot?.e) != null ? String(plan.d ?? job.instrument_snapshot?.d ?? plan.e ?? job.instrument_snapshot?.e) : eVal;
  const unit = String(plan.unit || job.instrument_snapshot?.unit || 'kg');
  const mpeRef = String(plan.mpe_reference || 'OIML R 76-1:2006 Table 6 / Seventh Schedule Table 2');

  const rawEquipment = (plan.required_equipment as string[] | undefined) ?? [];
  const equipment = Array.isArray(rawEquipment) ? rawEquipment : [];

  // Parse test suites
  const suites: TestPlanSuite[] = [];

  if (Array.isArray(plan.tests)) {
    for (const t of plan.tests as ApiRecord[]) {
      const tid = String(t.test_id ?? '');
      const tname = String(t.test_name ?? tid.replace(/_/g, ' '));
      const source = String(t.source ?? '');
      const criteria = String(t.acceptance_criteria ?? '');
      const loads = Array.isArray(t.test_loads) ? (t.test_loads as ApiRecord[]) : [];

      const points: TestPlanLoadPoint[] = loads.map((tl, i) => {
        const mpeAbs = tl.mpe_abs !== undefined ? Number(tl.mpe_abs) : undefined;
        const mpeE = tl.mpe_in_e !== undefined ? Number(tl.mpe_in_e) : undefined;
        let mpeText = '—';
        if (mpeAbs !== undefined) {
          mpeText = `± ${mpeAbs} ${tl.unit || unit}${mpeE !== undefined ? ` (± ${mpeE} e)` : ''}`;
        }
        return {
          step: i + 1,
          load: Number(tl.load ?? 0),
          unit: String(tl.unit || unit),
          loadInE: tl.load_in_e !== undefined ? Number(tl.load_in_e) : undefined,
          direction: String(tl.step_direction ?? 'STATIC'),
          position: String(tl.position ?? 'CENTER'),
          mpe: mpeText,
        };
      });

      suites.push({ id: tid, name: tname, source, criteria, points });
    }
  } else if (plan.test_suites && typeof plan.test_suites === 'object') {
    const obj = plan.test_suites as Record<string, ApiRecord[]>;
    for (const [key, pts] of Object.entries(obj)) {
      const points: TestPlanLoadPoint[] = (pts || []).map((tp, i) => {
        const expMpe = tp.expected_mpe as ApiRecord | undefined;
        let mpeText = '—';
        if (expMpe?.mpe_abs !== undefined) {
          mpeText = `± ${expMpe.mpe_abs} ${tp.unit || unit} (± ${expMpe.mpe_in_e ?? ''} e)`;
        }
        return {
          step: Number(tp.step_number ?? i + 1),
          load: Number(tp.target_load ?? 0),
          unit: String(tp.unit || unit),
          loadInE: tp.load_in_e !== undefined ? Number(tp.load_in_e) : undefined,
          direction: String(tp.direction ?? 'STATIC'),
          position: String(tp.position ?? 'CENTER'),
          mpe: mpeText,
        };
      });
      suites.push({ id: key, name: key.replace(/_/g, ' '), points });
    }
  } else if (Array.isArray(plan.calculated_test_loads)) {
    const loads = plan.calculated_test_loads as number[];
    const points: TestPlanLoadPoint[] = loads.map((l, i) => ({
      step: i + 1,
      load: Number(l),
      unit,
      direction: 'INCREASING',
      position: 'CENTER',
      mpe: `Statutory MPE (Class ${accClass})`,
    }));
    suites.push({
      id: 'A.4.4',
      name: 'Weighing Performance Test',
      source: 'OIML R 76-1:2006 Clause A.4.4',
      criteria: 'Error must not exceed maximum permissible error (MPE)',
      points,
    });
  }

  const totalPoints = suites.reduce((acc, s) => acc + s.points.length, 0);
  const displayedSuites = activeTab === 'ALL' ? suites : suites.filter((s) => s.id === activeTab);

  return (
    <section className="detail-section" style={{ gridColumn: '1 / -1' }} id="regulatory-test-plan-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 14, marginBottom: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <BookOpen size={18} color="#245d85" />
            <h2 style={{ margin: 0, fontSize: 16, color: '#102a43' }}>
              Generated Regulatory Test Plan
            </h2>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                background: '#eaf2f8',
                color: '#1d5d87',
                padding: '2px 8px',
                border: '1px solid #b9d9ee',
                borderRadius: 4,
              }}
            >
              {planId}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: '#627d98' }}>
            Statutory test sequence generated per <strong>{standard}</strong>
          </p>
        </div>

        {onStartExecution && isExecutionReady(job.status) && (
          <button
            type="button"
            className="primary-button"
            onClick={onStartExecution}
            style={{ minHeight: 34, padding: '0 14px', fontSize: 12, borderRadius: 6, display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <Play size={13} /> Start Test Execution
          </button>
        )}
      </div>

      {/* Statutory Parameters Bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
          gap: 12,
          padding: '14px',
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: 6,
          marginBottom: 18,
          fontSize: 12,
        }}
      >
        <div>
          <span style={{ color: '#627d98', display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
            Accuracy Class
          </span>
          <strong style={{ color: '#102a43', fontSize: 14 }}>Class {accClass}</strong>
        </div>
        <div>
          <span style={{ color: '#627d98', display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
            Capacity (Min → Max)
          </span>
          <strong style={{ color: '#102a43', fontSize: 14 }}>
            {minCap} {unit} → {maxCap} {unit}
          </strong>
        </div>
        <div>
          <span style={{ color: '#627d98', display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
            Interval (e / d)
          </span>
          <strong style={{ color: '#102a43', fontSize: 14 }}>
            e={eVal} {unit} (d={dVal} {unit})
          </strong>
        </div>
        <div>
          <span style={{ color: '#627d98', display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
            Total Test Points
          </span>
          <strong style={{ color: '#245d85', fontSize: 14 }}>
            {totalPoints} Target Points
          </strong>
        </div>
      </div>

      {/* Regulatory Reference & Equipment */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 14, marginBottom: 18 }}>
        <div style={{ padding: '12px 14px', background: '#fff', border: '1px solid #e6edf3', borderRadius: 6, fontSize: 12 }}>
          <strong style={{ color: '#334e68', display: 'block', marginBottom: 4 }}>
            Statutory Tolerance (MPE) Reference:
          </strong>
          <span style={{ color: '#627d98', lineHeight: 1.4 }}>{mpeRef}</span>
        </div>
        {equipment.length > 0 && (
          <div style={{ padding: '12px 14px', background: '#fff', border: '1px solid #e6edf3', borderRadius: 6, fontSize: 12 }}>
            <strong style={{ color: '#334e68', display: 'block', marginBottom: 4 }}>
              Required Test Standards:
            </strong>
            <ul style={{ margin: 0, paddingLeft: 16, color: '#627d98', lineHeight: 1.35 }}>
              {equipment.slice(0, 3).map((eq, i) => (
                <li key={i}>{eq}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Test Suite Tabs */}
      {suites.length > 1 && (
        <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid #d9e2ec', marginBottom: 14, overflowX: 'auto' }}>
          <button
            type="button"
            onClick={() => setActiveTab('ALL')}
            style={{
              border: 'none',
              background: 'none',
              padding: '8px 12px',
              fontSize: 13,
              fontWeight: 700,
              cursor: 'pointer',
              color: activeTab === 'ALL' ? '#245d85' : '#627d98',
              borderBottom: activeTab === 'ALL' ? '2px solid #245d85' : '2px solid transparent',
              whiteSpace: 'nowrap',
            }}
          >
            All Suites ({suites.length})
          </button>
          {suites.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setActiveTab(s.id)}
              style={{
                border: 'none',
                background: 'none',
                padding: '8px 12px',
                fontSize: 13,
                fontWeight: 700,
                cursor: 'pointer',
                color: activeTab === s.id ? '#245d85' : '#627d98',
                borderBottom: activeTab === s.id ? '2px solid #245d85' : '2px solid transparent',
                whiteSpace: 'nowrap',
              }}
            >
              {s.name} ({s.points.length})
            </button>
          ))}
        </div>
      )}

      {/* Test Suites & Target Load Points */}
      <div style={{ display: 'grid', gap: 16 }}>
        {displayedSuites.map((suite) => (
          <div
            key={suite.id}
            style={{
              border: '1px solid #d9e2ec',
              borderRadius: 6,
              background: '#fff',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 14px',
                background: '#f8fafc',
                borderBottom: '1px solid #e6edf3',
              }}
            >
              <div>
                <strong style={{ color: '#102a43', fontSize: 13 }}>{suite.name}</strong>
                {suite.source && (
                  <small style={{ display: 'block', color: '#627d98', fontSize: 11 }}>
                    Reference: {suite.source}
                  </small>
                )}
              </div>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  color: '#486581',
                  background: '#edf2f7',
                  padding: '2px 8px',
                  borderRadius: 4,
                }}
              >
                {suite.points.length} points
              </span>
            </div>

            {suite.criteria && (
              <div style={{ padding: '8px 14px', background: '#eff7fc', borderBottom: '1px solid #e6edf3', fontSize: 12, color: '#1e5479' }}>
                <strong>Acceptance Criteria:</strong> {suite.criteria}
              </div>
            )}

            {suite.points.length === 0 ? (
              <p style={{ padding: 14, margin: 0, color: '#829ab1', fontSize: 13 }}>
                Inspection / visual examination test. No discrete numerical load sequence.
              </p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: '#fafbfc', borderBottom: '1px solid #e6edf3', textAlign: 'left' }}>
                      <th style={{ padding: '8px 12px', color: '#486581', fontSize: 10, textTransform: 'uppercase' }}>Step</th>
                      <th style={{ padding: '8px 12px', color: '#486581', fontSize: 10, textTransform: 'uppercase' }}>Target Load</th>
                      <th style={{ padding: '8px 12px', color: '#486581', fontSize: 10, textTransform: 'uppercase' }}>Load in (e)</th>
                      <th style={{ padding: '8px 12px', color: '#486581', fontSize: 10, textTransform: 'uppercase' }}>Direction / Position</th>
                      <th style={{ padding: '8px 12px', color: '#486581', fontSize: 10, textTransform: 'uppercase' }}>Permissible Error (MPE)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {suite.points.map((pt) => (
                      <tr key={pt.step} style={{ borderTop: '1px solid #edf2f7' }}>
                        <td style={{ padding: '8px 12px', fontWeight: 700, color: '#334e68' }}>
                          #{pt.step}
                        </td>
                        <td style={{ padding: '8px 12px', fontWeight: 700, color: '#102a43' }}>
                          {pt.load} {pt.unit}
                        </td>
                        <td style={{ padding: '8px 12px', color: '#486581' }}>
                          {pt.loadInE !== undefined ? `${pt.loadInE} e` : '—'}
                        </td>
                        <td style={{ padding: '8px 12px', color: '#486581' }}>
                          <span style={{ fontWeight: 600 }}>{pt.direction}</span> · {pt.position}
                        </td>
                        <td style={{ padding: '8px 12px', color: '#17603b', fontWeight: 700 }}>
                          {pt.mpe}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

// ── 3. Test Execution Section ─────────────────────────────────────────────────

interface ExecResult {
  verdict: string;
  summary: string;
  test_type: string;
  job_status: string;
  auto_review_triggered: boolean;
  calculation_result?: ApiRecord;
  attempt?: ApiRecord;
}

interface TestOption {
  canonical: string;
  clauseId?: string;
  label: string;
  passed: boolean;
  attemptsCount: number;
}

function TestExecutionSection({
  job,
  applicableTests,
  testSummaries,
  onJobStatusChange,
  defaultOperator,
}: {
  job: JobSummary;
  applicableTests: string[];
  testSummaries: TestSummary[];
  onJobStatusChange: (status: string) => void;
  defaultOperator: string;
}) {
  // Build test options list mapping clause codes to canonical test types
  const testOptions = useMemo<TestOption[]>(() => {
    const list: TestOption[] = [];
    const seen = new Set<string>();

    // 1. From applicable_tests
    for (const raw of applicableTests) {
      const rawTrim = raw.trim();
      const canonical = resolveCanonicalTestType(rawTrim);
      if (!seen.has(canonical)) {
        seen.add(canonical);
        const isPassed = testSummaries.some(
          (s) =>
            (s.test_id.toUpperCase() === canonical ||
              s.test_id.toUpperCase() === rawTrim.toUpperCase()) &&
            s.latest_result === 'PASS',
        );
        const attempts = testSummaries.find(
          (s) =>
            s.test_id.toUpperCase() === canonical ||
            s.test_id.toUpperCase() === rawTrim.toUpperCase(),
        )?.attempt_count ?? 0;

        const label =
          TEST_TYPE_LABELS[canonical] ||
          `${canonical.replace(/_/g, ' ')}${rawTrim !== canonical ? ` (${rawTrim})` : ''}`;

        list.push({
          canonical,
          clauseId: rawTrim.startsWith('A.') || rawTrim.startsWith('B.') ? rawTrim : undefined,
          label,
          passed: isPassed,
          attemptsCount: attempts,
        });
      }
    }

    // 2. From test_plan.tests if any
    if (job.test_plan && Array.isArray(job.test_plan.tests)) {
      for (const t of job.test_plan.tests as ApiRecord[]) {
        const tid = String(t.test_id || '');
        const ttype = String(t.test_type || '');
        const canonical = resolveCanonicalTestType(ttype || tid);
        if (!seen.has(canonical)) {
          seen.add(canonical);
          const isPassed = testSummaries.some(
            (s) => s.test_id.toUpperCase() === canonical && s.latest_result === 'PASS',
          );
          const attempts = testSummaries.find((s) => s.test_id.toUpperCase() === canonical)?.attempt_count ?? 0;
          const label = TEST_TYPE_LABELS[canonical] || String(t.test_name || canonical.replace(/_/g, ' '));
          list.push({
            canonical,
            clauseId: tid.startsWith('A.') || tid.startsWith('B.') ? tid : undefined,
            label,
            passed: isPassed,
            attemptsCount: attempts,
          });
        }
      }
    }

    // 3. Fallback to TEST_TYPES if list is empty
    if (list.length === 0) {
      for (const t of TEST_TYPES) {
        const isPassed = testSummaries.some(
          (s) => s.test_id.toUpperCase() === t && s.latest_result === 'PASS',
        );
        const attempts = testSummaries.find((s) => s.test_id.toUpperCase() === t)?.attempt_count ?? 0;
        list.push({
          canonical: t,
          label: TEST_TYPE_LABELS[t] || t.replace(/_/g, ' '),
          passed: isPassed,
          attemptsCount: attempts,
        });
      }
    }

    return list;
  }, [applicableTests, job.test_plan, testSummaries]);

  // Active selected test
  const [selectedCanonical, setSelectedCanonical] = useState<string>(
    testOptions[0]?.canonical ?? TEST_TYPES[0],
  );
  const [operator, setOperator] = useState(defaultOperator || 'INSPECTOR_001');
  const [notes, setNotes] = useState('');
  const [rows, setRows] = useState<Record<string, string>[]>([{}]);
  const [busy, setBusy] = useState(false);
  const [startBusy, setStartBusy] = useState(false);
  const [result, setResult] = useState<ExecResult | null>(null);
  const [error, setError] = useState('');

  const currentOption = testOptions.find((o) => o.canonical === selectedCanonical) || testOptions[0];
  const fields = obsFieldsFor(selectedCanonical);

  const addRow = () => setRows((r) => [...r, {}]);
  const removeRow = (i: number) => setRows((r) => r.filter((_, idx) => idx !== i));
  const updateRow = (i: number, key: string, value: string) =>
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, [key]: value } : row)));

  const handleTestChange = (canonical: string) => {
    setSelectedCanonical(canonical);
    const opt = testOptions.find((o) => o.canonical === canonical);
    const prefill = extractPlanPointsForTest(job, canonical, opt?.clauseId);
    setRows(prefill.length > 0 ? prefill : [{}]);
    setResult(null);
    setError('');
  };

  // Pre-fill on initial selection if empty
  useEffect(() => {
    if (rows.length === 1 && Object.keys(rows[0]).length === 0) {
      const initialPoints = extractPlanPointsForTest(job, selectedCanonical, currentOption?.clauseId);
      if (initialPoints.length > 0) {
        setRows(initialPoints);
      }
    }
  }, [job, selectedCanonical, currentOption?.clauseId, rows]);

  const startExecution = async () => {
    setStartBusy(true);
    setError('');
    try {
      const res = await jobsApi.startExecution(job.job_id, operator || 'INSPECTOR_001');
      const newStatus = res.status ?? (res.data as { status?: string } | undefined)?.status;
      if (newStatus) onJobStatusChange(newStatus);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start execution.');
    } finally {
      setStartBusy(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!operator.trim()) { setError('Operator name is required.'); return; }
    if (rows.length === 0) { setError('At least one observation row is required.'); return; }

    const observations: TestObservation[] = rows.map((row, i) =>
      rowToObservation(selectedCanonical, row, i),
    );

    setBusy(true);
    setError('');
    setResult(null);
    try {
      const payload: SubmitObservationsPayload = {
        job_id: job.job_id,
        test_type: selectedCanonical,
        observations,
        operator: operator.trim(),
        notes: notes.trim(),
      };
      const res = await testExecutionApi.submit(payload);
      const data = res.data as unknown as ExecResult;
      setResult(data);
      if (data.job_status) onJobStatusChange(data.job_status);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Observation submission failed.');
    } finally {
      setBusy(false);
    }
  };

  const needsStart = job.status !== 'IN_PROGRESS' && job.status !== 'RETEST_REQUIRED';
  const passedCount = testOptions.filter((t) => t.passed).length;
  const nextPendingTest = testOptions.find((opt) => !opt.passed && opt.canonical !== selectedCanonical);

  return (
    <section className="detail-section" style={{ gridColumn: '1 / -1' }} id="test-execution-form-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 14 }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
          <Play size={18} color="#0369a1" /> Statutory Test Execution
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: passedCount === testOptions.length ? '#166534' : '#0369a1', background: passedCount === testOptions.length ? '#dcfce7' : '#e0f2fe', padding: '4px 10px', borderRadius: 4 }}>
            {passedCount} of {testOptions.length} Tests Passed
          </span>
        </div>
      </div>

      {needsStart && (
        <div style={{ marginBottom: 16, padding: '12px 16px', background: '#eff7fc', border: '1px solid #b9d9ee', borderRadius: 6, fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
          <span>
            Job is in <strong>{pretty(job.status)}</strong> state. You may start test execution to advance to <strong>IN PROGRESS</strong>.
          </span>
          <button
            className="primary-button"
            style={{ minHeight: 32, padding: '0 14px', fontSize: 12, borderRadius: 4, display: 'inline-flex', alignItems: 'center', gap: 6 }}
            onClick={() => void startExecution()}
            disabled={startBusy}
          >
            {startBusy ? <Loader size={13} /> : <Play size={13} />}
            {startBusy ? 'Starting…' : 'Start Test Execution'}
          </button>
        </div>
      )}

      <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, borderBottom: '1px solid #cbd5e1', paddingBottom: 10 }}>
          <h3 style={{ margin: 0, fontSize: 16, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Play size={16} color="#0369a1" />
            Active Test: <strong style={{ color: '#0369a1' }}>{currentOption?.label || selectedCanonical}</strong>
          </h3>
          {currentOption?.passed && (
            <span style={{ fontSize: 12, fontWeight: 700, color: '#166534', background: '#dcfce7', padding: '3px 8px', borderRadius: 4 }}>
              ✓ Passed
            </span>
          )}
        </div>

        <form onSubmit={(e) => void submit(e)}>
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 16, marginBottom: 18 }}>
            <div style={{ display: 'grid', gap: 4 }}>
              <label style={{ color: '#475569', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                Select Applicable Test *
              </label>
              <select
                value={selectedCanonical}
                onChange={(e) => handleTestChange(e.target.value)}
                style={{ minHeight: 40, padding: '0 12px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: 6, fontSize: 13, fontWeight: 600 }}
              >
                {testOptions.map((opt) => (
                  <option key={opt.canonical} value={opt.canonical}>
                    {opt.passed ? '✓ [PASS] ' : opt.attemptsCount > 0 ? '⚠ [ATTEMPTED] ' : '○ [PENDING] '}
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ display: 'grid', gap: 4 }}>
              <label style={{ color: '#475569', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                Operator / Inspector ID *
              </label>
              <input
                required
                value={operator}
                onChange={(e) => setOperator(e.target.value)}
                placeholder="Operator ID / Name"
                style={{ minHeight: 40, padding: '0 12px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 13, background: '#fff' }}
              />
            </div>
          </div>

          <div style={{ marginBottom: 20, background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8, padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
              <span style={{ color: '#0f172a', fontSize: 13, fontWeight: 700 }}>
                Test Observations ({rows.length} {rows.length === 1 ? 'row' : 'rows'})
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  className="secondary-button"
                  style={{ minHeight: 32, padding: '0 10px', fontSize: 12, borderRadius: 4, display: 'inline-flex', alignItems: 'center', gap: 5 }}
                  onClick={() => {
                    const targetPoints = extractPlanPointsForTest(job, selectedCanonical, currentOption?.clauseId);
                    if (targetPoints.length > 0) setRows(targetPoints);
                  }}
                  title="Load statutory nominal target load points from the regulatory test plan"
                >
                  <Sparkles size={13} color="#0369a1" /> Load Reference Loads from Plan
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  style={{ minHeight: 32, padding: '0 10px', fontSize: 12, borderRadius: 4 }}
                  onClick={addRow}
                >
                  + Add Row
                </button>
              </div>
            </div>

            <div style={{ margin: '0 0 12px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 4, fontSize: 12, color: '#475569' }}>
              <strong>Measurement Guidance:</strong> <em>Target Load</em> values are nominal test loads from the statutory test plan. Record the physical scale's <em>Observed Reading</em> for each applied test load.
            </div>

            {rows.map((row, i) => (
              <ObsRowEditor
                key={i}
                fields={fields}
                row={row}
                index={i}
                onChange={(key, value) => updateRow(i, key, value)}
                onRemove={() => removeRow(i)}
              />
            ))}
          </div>

          <div style={{ display: 'grid', gap: 4, marginBottom: 18 }}>
            <label style={{ color: '#475569', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em' }}>
              Execution Notes (optional)
            </label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Ambient temperature, test weights ID, or observations…"
              style={{ minHeight: 38, padding: '0 12px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 13, background: '#fff' }}
            />
          </div>

          <button
            className="primary-button"
            type="submit"
            disabled={busy}
            style={{ width: '100%', justifyContent: 'center', minHeight: 44, fontSize: 14, borderRadius: 6, display: 'flex', alignItems: 'center', gap: 8 }}
          >
            {busy ? <Loader size={18} /> : <Play size={18} />}
            {busy ? 'Submitting & Evaluating Observations…' : `Submit Observations for ${currentOption?.canonical.replace(/_/g, ' ')}`}
          </button>
        </form>

        {error && (
          <div className="notice error" style={{ marginTop: 16, borderRadius: 6, padding: '12px 16px', fontSize: 13 }}>
            <strong>Execution Error:</strong> {error}
          </div>
        )}

        {result && (
          <div
            style={{
              marginTop: 18,
              padding: '16px 20px',
              border: `2px solid ${result.verdict === 'PASS' ? '#22c55e' : '#ef4444'}`,
              background: result.verdict === 'PASS' ? '#f0fdf4' : '#fef2f2',
              borderRadius: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              {result.verdict === 'PASS' ? <CheckCircle2 size={24} color="#16a34a" /> : <XCircle size={24} color="#dc2626" />}
              <strong style={{ fontSize: 16, color: result.verdict === 'PASS' ? '#166534' : '#991b1b' }}>
                Test Verdict: {result.test_type?.replace(/_/g, ' ')}
              </strong>
              <Verdict value={result.verdict} />
              {result.auto_review_triggered && (
                <span style={{ marginLeft: 'auto', color: '#0369a1', fontSize: 12, fontWeight: 700, background: '#e0f2fe', padding: '4px 10px', borderRadius: 16, border: '1px solid #b9d9ee' }}>
                  ✓ All tests passed — auto-submitted for review
                </span>
              )}
            </div>

            {result.summary && (
              <p style={{ margin: '10px 0 0', color: result.verdict === 'PASS' ? '#14532d' : '#7f1d1d', fontSize: 13, lineHeight: 1.4 }}>
                {result.summary}
              </p>
            )}

            {result.calculation_result && (
              <div style={{ marginTop: 10, fontSize: 12, color: '#475569', borderTop: `1px solid ${result.verdict === 'PASS' ? '#bbf7d0' : '#fecaca'}`, paddingTop: 8 }}>
                <strong>Statutory Standard Reference:</strong> {String((result.calculation_result as ApiRecord).standard_reference ?? 'OIML R 76-1:2006')}
              </div>
            )}

            {nextPendingTest && (
              <button
                type="button"
                className="primary-button"
                style={{ marginTop: 14, minHeight: 34, padding: '0 14px', fontSize: 12, borderRadius: 6, display: 'inline-flex', alignItems: 'center', gap: 6 }}
                onClick={() => {
                  setSelectedCanonical(nextPendingTest.canonical);
                  const pts = extractPlanPointsForTest(job, nextPendingTest.canonical, nextPendingTest.clauseId);
                  setRows(pts.length > 0 ? pts : [{}]);
                  setResult(null);
                  setError('');
                }}
              >
                <Play size={13} /> Proceed to Next Test: {nextPendingTest.label} →
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

// ── 4. Review & Approval Section ──────────────────────────────────────────────

function ReviewSection({
  job,
  testSummaries,
  onJobStatusChange,
  inspectorName,
}: {
  job: JobSummary;
  testSummaries: TestSummary[];
  onJobStatusChange: (status: string) => void;
  inspectorName: string;
}) {
  const [reviewer, setReviewer] = useState('Superintendent P. Verma');
  const [decision, setDecision] = useState<'APPROVE' | 'REJECT' | 'RETURN_FOR_CORRECTION'>('APPROVE');
  const [comments, setComments] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const inReview = isInReview(job.status);
  const canSubmitForReview =
    job.status === 'IN_PROGRESS' || job.status === 'RETEST_REQUIRED' ||
    job.status === 'TEST_COMPLETED' || job.status === 'TESTS_COMPLETED';

  const submitForReview = async () => {
    setSubmitBusy(true);
    setError('');
    try {
      const res = await jobsApi.submitForReview(job.job_id, {
        submitted_by: inspectorName || 'INSPECTOR_001',
        comments: comments || 'All statutory tests completed and submitted for supervisory review.',
      });
      const data = res.data as ApiRecord;
      const newStatus = String(data.current_state ?? data.status ?? 'REVIEW');
      if (newStatus) onJobStatusChange(newStatus);
      setSuccess('Job successfully submitted for supervisory review.');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not submit for review.');
    } finally {
      setSubmitBusy(false);
    }
  };

  const executeReview = async (e: FormEvent) => {
    e.preventDefault();
    if (!reviewer.trim()) { setError('Reviewer name is required.'); return; }
    if ((decision === 'REJECT' || decision === 'RETURN_FOR_CORRECTION') && !comments.trim()) {
      setError('Comments are mandatory for rejection or return-for-correction.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const res = await jobsApi.review(job.job_id, {
        decision,
        reviewer: reviewer.trim(),
        comments: comments.trim(),
      });
      const data = res.data as ApiRecord;
      const newStatus = String(data.current_state ?? data.status ?? '');
      if (newStatus) onJobStatusChange(newStatus);
      setSuccess(`Review decision recorded successfully: ${decision.replace(/_/g, ' ')}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Review action failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="detail-section" style={{ gridColumn: '1 / -1' }} id="review-approval-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', gap: 10 }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
          <ClipboardCheck size={18} color="#0369a1" /> Supervisory Review & Approval
        </h2>
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            padding: '3px 8px',
            borderRadius: 4,
            background: inReview ? '#fef3c7' : job.status === 'APPROVED' ? '#dcfce7' : '#f1f5f9',
            color: inReview ? '#92400e' : job.status === 'APPROVED' ? '#166534' : '#475569',
          }}
        >
          {pretty(job.status)}
        </span>
      </div>

      <TestResultsTable summaries={testSummaries} loading={false} />

      {/* Four-Eyes Principle Statutory Notice */}
      <div
        style={{
          marginTop: 16,
          padding: '12px 16px',
          background: '#f8fafc',
          border: '1px solid #cbd5e1',
          borderRadius: 6,
          fontSize: 12,
          color: '#334e68',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, marginBottom: 4, color: '#0f172a' }}>
          <ShieldCheck size={16} color="#0369a1" />
          Statutory Four-Eyes Principle Enforced
        </div>
        <p style={{ margin: 0, lineHeight: 1.4 }}>
          Under Indian Legal Metrology Rules and OIML guidelines, self-review is strictly prohibited. The supervisory reviewer must be independent from the testing operator ({inspectorName || 'Inspector'}).
        </p>
      </div>

      <div style={{ marginTop: 18, borderTop: '1px solid #e6edf3', paddingTop: 18 }}>
        {canSubmitForReview && !inReview && (
          <div>
            <p style={{ margin: '0 0 10px', fontSize: 13, color: '#334e68', fontWeight: 600 }}>
              All tests executed. Submit this job to the Supervisory Controller for review:
            </p>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="Submission notes or inspection remarks…"
                style={{ minHeight: 38, padding: '0 12px', border: '1px solid #cbd5e1', borderRadius: 6, flex: '1 1 300px', fontSize: 13 }}
              />
              <button
                type="button"
                className="primary-button"
                onClick={() => void submitForReview()}
                disabled={submitBusy}
                style={{ minHeight: 38, padding: '0 16px', fontSize: 13, borderRadius: 6, display: 'inline-flex', alignItems: 'center', gap: 6 }}
              >
                {submitBusy ? <Loader size={14} /> : <ClipboardCheck size={14} />}
                {submitBusy ? 'Submitting…' : 'Submit for Supervisory Review'}
              </button>
            </div>
          </div>
        )}

        {inReview && (
          <form onSubmit={(e) => void executeReview(e)} style={{ display: 'grid', gap: 14 }}>
            <div style={{ padding: '10px 14px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 6, fontSize: 13, color: '#92400e', fontWeight: 600 }}>
              Job is currently under supervisory review. Render a formal statutory decision below:
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div style={{ display: 'grid', gap: 4 }}>
                <label style={{ color: '#475569', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
                  Independent Reviewer Name *
                </label>
                <input
                  required
                  value={reviewer}
                  onChange={(e) => setReviewer(e.target.value)}
                  placeholder="Supervisor / Superintendent Name"
                  style={{ minHeight: 38, padding: '0 12px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 13, background: '#fff' }}
                />
              </div>

              <div style={{ display: 'grid', gap: 4 }}>
                <label style={{ color: '#475569', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
                  Statutory Decision *
                </label>
                <select
                  value={decision}
                  onChange={(e) => setDecision(e.target.value as typeof decision)}
                  style={{ minHeight: 38, padding: '0 12px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: 6, fontSize: 13, fontWeight: 600 }}
                >
                  <option value="APPROVE">APPROVE (Issue Verification Certificate)</option>
                  <option value="REJECT">REJECT (Issue Rejection Notice)</option>
                  <option value="RETURN_FOR_CORRECTION">RETURN FOR CORRECTION (Retest Required)</option>
                </select>
              </div>
            </div>

            <div style={{ display: 'grid', gap: 4 }}>
              <label style={{ color: '#475569', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
                Review Comments {decision !== 'APPROVE' && '*'}
              </label>
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="Statutory findings, certificate endorsement notes, or grounds for rejection/re-test…"
                rows={3}
                style={{ padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' }}
              />
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                type="submit"
                className={decision === 'APPROVE' ? 'primary-button' : 'secondary-button'}
                disabled={submitting}
                style={{
                  minHeight: 40,
                  padding: '0 20px',
                  borderRadius: 6,
                  fontSize: 14,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  background: decision === 'APPROVE' ? '#16a34a' : decision === 'REJECT' ? '#dc2626' : '#d97706',
                  color: '#fff',
                  borderColor: 'transparent',
                }}
              >
                {submitting ? <Loader size={15} /> : decision === 'APPROVE' ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                {submitting ? 'Rendering Decision…' : `Record Decision: ${decision.replace(/_/g, ' ')}`}
              </button>
            </div>
          </form>
        )}

        {error && <div className="notice error" style={{ marginTop: 12 }}>{error}</div>}
        {success && (
          <div className="notice info" style={{ marginTop: 12 }}>
            <CheckCircle2 size={15} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            {success}
          </div>
        )}
      </div>
    </section>
  );
}

// ── 5. Report Generation & Real PDF Download Section ──────────────────────────

function ReportGenSection({
  job,
  onJobRefresh,
}: {
  job: JobSummary;
  onJobRefresh: () => void;
}) {
  const navigate = useNavigate();
  const [reportType, setReportType] = useState<ReportType>(
    String(job.status).toUpperCase() === 'REJECTED'
      ? 'REJECTION_DOCUMENT'
      : 'GENERIC_VERIFICATION',
  );
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [lastGeneratedReportId, setLastGeneratedReportId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const createAndGenerate = async () => {
    setBusy(true);
    setError('');
    try {
      const created = await reportsApi.create({ job_id: job.job_id, report_type: reportType });
      const reportId = created.data.report_id;
      const generated = await reportsApi.generate(reportId, 'Superintendent P. Verma');
      setLastGeneratedReportId(reportId);
      onJobRefresh();

      // Trigger immediate PDF download
      try {
        const reportNumber = generated.data.report_number || reportId;
        const filename = `${reportNumber.replace(/\//g, '_')}.pdf`;
        await reportsApi.downloadPdf(reportId, filename);
      } catch (dlErr) {
        console.warn('Auto PDF download fallback:', dlErr);
      }

      navigate(`/reports/${generated.data.report_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Report generation failed.');
    } finally {
      setBusy(false);
    }
  };

  const handleDownloadExisting = async (reportId: string) => {
    setDownloading(true);
    try {
      const filename = `Verification_Certificate_${job.job_number || job.job_id}.pdf`;
      await reportsApi.downloadPdf(reportId, filename);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'PDF download failed.');
    } finally {
      setDownloading(false);
    }
  };

  const availableTypes: Array<[ReportType, string]> = [
    ['GENERIC_VERIFICATION', 'Configurable Verification Record (Legal Metrology Rules, 2011)'],
    ['GATC_THIRD_SCHEDULE_VERIFICATION', 'GATC Third Schedule Verification Certificate'],
    ['OIML_R76_2_TYPE_EVALUATION', 'OIML R76-2:2007 Type Evaluation Report'],
    ['TECHNICAL_EVIDENCE_ANNEX', 'Technical Evidence Annex'],
  ];

  if (String(job.status).toUpperCase() === 'REJECTED') {
    availableTypes.unshift(['REJECTION_DOCUMENT', 'Rejection Document / Notice of Non-Compliance']);
  }

  return (
    <section className="detail-section" style={{ gridColumn: '1 / -1' }} id="report-generation-section">
      <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <FilePlus2 size={18} color="#0369a1" /> Generate Verification Certificate / Report
      </h2>
      <p style={{ margin: '0 0 16px', color: '#627d98', fontSize: 13 }}>
        Job has been reviewed and rendered as <strong>{pretty(job.status)}</strong>. Select a statutory report format to generate and download the official PDF.
      </p>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div style={{ display: 'grid', gap: 4, flex: '1 1 320px' }}>
          <label style={{ color: '#486581', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em' }}>
            Statutory Report Template
          </label>
          <select
            value={reportType}
            onChange={(e) => setReportType(e.target.value as ReportType)}
            style={{ minHeight: 40, padding: '0 12px', border: '1px solid #cbd5e1', borderRadius: 6, background: '#fff', fontSize: 13 }}
          >
            {availableTypes.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>

        <button
          className="primary-button"
          onClick={() => void createAndGenerate()}
          disabled={busy}
          style={{ minHeight: 40, padding: '0 18px', borderRadius: 6, fontSize: 14, display: 'inline-flex', alignItems: 'center', gap: 8 }}
        >
          {busy ? <Loader size={16} /> : <FileCog size={16} />}
          {busy ? 'Generating & Downloading PDF…' : 'Generate & Download PDF'}
        </button>

        {lastGeneratedReportId && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => void handleDownloadExisting(lastGeneratedReportId)}
            disabled={downloading}
            style={{ minHeight: 40, padding: '0 14px', borderRadius: 6, fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            {downloading ? <Loader size={14} /> : <Download size={14} />}
            Download PDF Again
          </button>
        )}

        <Link
          className="secondary-button"
          to="/reports"
          style={{ minHeight: 40, padding: '0 14px', borderRadius: 6, fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <FileText size={14} /> View All Reports
        </Link>
      </div>

      {error && <div className="notice error" style={{ marginTop: 14 }}>{error}</div>}
    </section>
  );
}

function formatAuditDetails(e: AuditLogEntry): string {
  const parts: string[] = [];
  if (e.new_value && typeof e.new_value === 'object') {
    const nv = e.new_value as Record<string, unknown>;
    if (nv.status) parts.push(`Status: ${String(nv.status).replace(/_/g, ' ')}`);
    if (nv.verdict) parts.push(`Verdict: ${nv.verdict}`);
    if (nv.decision) parts.push(`Decision: ${nv.decision}`);
    if (nv.report_number) parts.push(`Report: ${nv.report_number}`);
    if (nv.report_type) parts.push(`Type: ${String(nv.report_type).replace(/_/g, ' ')}`);
    if (nv.test_type) parts.push(`Test: ${String(nv.test_type).replace(/_/g, ' ')}`);
    if (nv.reason) parts.push(`Reason: ${nv.reason}`);
    if (nv.result) parts.push(`Result: ${nv.result}`);
    if (parts.length > 0) return parts.join(' · ');
    return Object.entries(nv)
      .slice(0, 3)
      .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'object' ? '...' : String(v)}`)
      .join(', ');
  }
  if (e.metadata && typeof e.metadata === 'object') {
    const md = e.metadata as Record<string, unknown>;
    if (md.result) parts.push(`Result: ${md.result}`);
    if (md.comments) parts.push(`Comments: ${md.comments}`);
    if (md.decision) parts.push(`Decision: ${md.decision}`);
    if (md.inspector) parts.push(`Inspector: ${md.inspector}`);
    if (parts.length > 0) return parts.join(' · ');
    return Object.entries(md)
      .slice(0, 3)
      .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'object' ? '...' : String(v)}`)
      .join(', ');
  }
  return e.action ? String(e.action).replace(/_/g, ' ') : 'Statutory event logged';
}

function JobAuditTrailSection({ jobId }: { jobId: string }) {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadTrail = useCallback(() => {
    setLoading(true);
    setError('');
    auditApi
      .getJobTrail(jobId)
      .then((res) => setEntries(res.data || []))
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : 'Audit trail unavailable.'),
      )
      .finally(() => setLoading(false));
  }, [jobId]);

  useEffect(() => {
    loadTrail();
  }, [loadTrail]);

  const actionColors: Record<string, { bg: string; color: string }> = {
    JOB_CREATED: { bg: '#e0f2fe', color: '#0369a1' },
    JOB_VALIDATED: { bg: '#dcfce7', color: '#166534' },
    JOB_STATUS_CHANGED: { bg: '#fef3c7', color: '#92400e' },
    TEST_ATTEMPT_RECORDED: { bg: '#ede9fe', color: '#6d28d9' },
    REVIEW_SUBMITTED: { bg: '#ffedd5', color: '#c2410c' },
    REVIEW_DECISION_RENDERED: { bg: '#d1fae5', color: '#065f46' },
    REPORT_GENERATED: { bg: '#ccfbf1', color: '#0f766e' },
  };

  return (
    <article className="detail-section" style={{ gridColumn: '1 / -1' }} id="audit-trail-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
          <History size={18} color="#0369a1" /> Statutory Audit Trail
          <span style={{ fontSize: 12, color: '#64748b', fontWeight: 600 }}>
            ({entries.length} immutable events)
          </span>
        </h2>
        <button
          type="button"
          className="secondary-button"
          onClick={loadTrail}
          disabled={loading}
          style={{ minHeight: 32, padding: '0 10px', fontSize: 12, borderRadius: 4, display: 'inline-flex', alignItems: 'center', gap: 5 }}
        >
          {loading ? <Loader size={12} /> : <RotateCcw size={12} />}
          Refresh Log
        </button>
      </div>

      <p style={{ margin: '0 0 14px', fontSize: 13, color: '#64748b' }}>
        Append-only regulatory log preserving all statutory verification events per Seventh Schedule requirements.
      </p>

      {loading && <p style={{ color: '#64748b', fontSize: 13 }}>Loading audit records…</p>}
      {error && <div className="notice error">{error}</div>}

      {!loading && !error && entries.length === 0 && (
        <p style={{ color: '#94a3b8', fontSize: 13 }}>No statutory audit events recorded for this job yet.</p>
      )}

      {entries.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e2e8f0', textAlign: 'left', background: '#f8fafc' }}>
                <th style={{ padding: '8px 10px', color: '#475569', textTransform: 'uppercase', fontSize: 10 }}>Timestamp</th>
                <th style={{ padding: '8px 10px', color: '#475569', textTransform: 'uppercase', fontSize: 10 }}>Action</th>
                <th style={{ padding: '8px 10px', color: '#475569', textTransform: 'uppercase', fontSize: 10 }}>Actor</th>
                <th style={{ padding: '8px 10px', color: '#475569', textTransform: 'uppercase', fontSize: 10 }}>Entity</th>
                <th style={{ padding: '8px 10px', color: '#475569', textTransform: 'uppercase', fontSize: 10 }}>Details / Recorded Value</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const actionStyle = actionColors[String(e.action)] || { bg: '#f1f5f9', color: '#475569' };
                return (
                  <tr key={e.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 10px', whiteSpace: 'nowrap', color: '#334e68' }}>
                      {fmtDate(e.timestamp)}
                    </td>
                    <td style={{ padding: '8px 10px' }}>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: 4,
                          background: actionStyle.bg,
                          color: actionStyle.color,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {String(e.action).replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td style={{ padding: '8px 10px', fontWeight: 600, color: '#1e293b' }}>
                      {e.actor || e.user_id}
                    </td>
                    <td style={{ padding: '8px 10px', color: '#64748b' }}>
                      {e.entity_type} · {e.entity_id}
                    </td>
                    <td style={{ padding: '8px 10px', color: '#334155', maxWidth: 360, fontSize: 12 }}>
                      {formatAuditDetails(e)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}

// ── Workflow Stepper Component ───────────────────────────────────────────────

function WorkflowStepper({ status }: { status: string }) {
  const s = status.toUpperCase();

  const getStepState = (stepIndex: number): 'completed' | 'current' | 'upcoming' => {
    switch (stepIndex) {
      case 0: // Test Plan
        return 'completed';
      case 1: // Validation
        if (['DRAFT', 'CREATED', 'PLAN_GENERATED', 'TEST_PLAN_GENERATED'].includes(s)) return 'current';
        return 'completed';
      case 2: // Execution
        if (['DRAFT', 'CREATED', 'PLAN_GENERATED', 'TEST_PLAN_GENERATED'].includes(s)) return 'upcoming';
        if (['VALIDATED', 'ASSIGNED', 'READY_FOR_TEST', 'READY', 'IN_TESTING', 'IN_PROGRESS', 'RETEST_REQUIRED'].includes(s)) return 'current';
        return 'completed';
      case 3: // Review
        if (['REVIEW', 'UNDER_REVIEW', 'SUBMITTED_FOR_REVIEW', 'TEST_COMPLETED', 'TESTS_COMPLETED'].includes(s)) return 'current';
        if (['APPROVED', 'REJECTED', 'CLOSED', 'CERTIFIED', 'REPORT_GENERATED'].includes(s)) return 'completed';
        return 'upcoming';
      case 4: // Decision
        if (['APPROVED', 'REJECTED'].includes(s)) return 'completed';
        if (['CLOSED', 'CERTIFIED', 'REPORT_GENERATED'].includes(s)) return 'completed';
        return 'upcoming';
      case 5: // Certificate / Report
        if (['REPORT_GENERATED', 'CLOSED', 'CERTIFIED'].includes(s)) return 'completed';
        if (['APPROVED', 'REJECTED'].includes(s)) return 'current';
        return 'upcoming';
      default:
        return 'upcoming';
    }
  };

  const steps = [
    { num: '1', label: 'Test Plan', desc: 'OIML / Sched VII' },
    { num: '2', label: 'Validation', desc: 'Pre-Test Check' },
    { num: '3', label: 'Execution', desc: 'Observations & MPE' },
    { num: '4', label: 'Review', desc: 'Four-Eyes Principle' },
    { num: '5', label: 'Decision', desc: s === 'REJECTED' ? 'Rejected' : 'Approved' },
    { num: '6', label: 'Certificate', desc: 'Download PDF' },
  ];

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        padding: '12px 16px',
        marginBottom: 20,
        overflowX: 'auto',
        gap: 8,
      }}
      aria-label="Verification Workflow Progress"
    >
      {steps.map((step, idx) => {
        const state = getStepState(idx);
        const isLast = idx === steps.length - 1;
        const color =
          state === 'completed' ? '#166534' : state === 'current' ? '#0369a1' : '#94a3b8';
        const bg =
          state === 'completed' ? '#dcfce7' : state === 'current' ? '#e0f2fe' : '#f1f5f9';
        const borderColor =
          state === 'completed' ? '#86efac' : state === 'current' ? '#7dd3fc' : '#e2e8f0';

        return (
          <React.Fragment key={step.num}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '4px 8px',
                borderRadius: 6,
                background: state === 'current' ? '#f0f9ff' : 'transparent',
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: bg,
                  border: `1.5px solid ${borderColor}`,
                  color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 11,
                  fontWeight: 700,
                }}
              >
                {state === 'completed' ? '✓' : step.num}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: 12, fontWeight: state === 'current' ? 700 : 600, color: state === 'current' ? '#0f172a' : color }}>
                  {step.label}
                </span>
                <span style={{ fontSize: 10, color: '#64748b' }}>{step.desc}</span>
              </div>
            </div>
            {!isLast && (
              <span style={{ color: '#cbd5e1', fontSize: 14, userSelect: 'none', margin: '0 2px' }}>
                →
              </span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── Main Page Component ───────────────────────────────────────────────────────

export function JobDetailPage() {
  const { jobId = '' } = useParams();
  const [job, setJob] = useState<JobSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [testSummaries, setTestSummaries] = useState<TestSummary[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [resultsLoading, setResultsLoading] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const loadJob = useCallback((background = false) => {
    if (background) setRefreshing(true);
    else setLoading(true);
    jobsApi
      .get(jobId)
      .then((res) => {
        if (!mounted.current) return;
        setJob(res.data ?? null);
        setError('');
      })
      .catch((e: unknown) => {
        if (!mounted.current) return;
        setError(e instanceof ApiError ? e.message : 'Could not load job.');
      })
      .finally(() => {
        if (!mounted.current) return;
        if (background) setRefreshing(false);
        else setLoading(false);
      });
  }, [jobId]);

  const loadResults = useCallback(() => {
    setResultsLoading(true);
    testExecutionApi
      .getResults(jobId)
      .then((res) => {
        if (!mounted.current) return;
        const data = res.data as ApiRecord;
        setTestSummaries((data.test_summaries as TestSummary[]) ?? []);
      })
      .catch(() => { /* results may be absent for new jobs */ })
      .finally(() => { if (mounted.current) setResultsLoading(false); });
  }, [jobId]);

  useEffect(() => {
    loadJob();
    loadResults();
  }, [loadJob, loadResults]);

  const handleStatusChange = (_newStatus: string) => {
    loadJob(true);
    loadResults();
  };

  if (loading)
    return <section className="page-section"><div className="table-state">Loading job…</div></section>;

  if (error || !job)
    return (
      <section className="page-section">
        <Link className="back-link" to="/jobs"><ArrowLeft size={16} /> Jobs</Link>
        <div className="notice error">{error || 'Job not found.'}</div>
      </section>
    );

  const applicableTests: string[] = (job.applicable_tests ?? []);
  const status = job.status ?? '';
  const showExecution = isExecutionReady(status);
  const showReview =
    isInReview(status) ||
    status === 'APPROVED' ||
    status === 'REJECTED' ||
    ((status === 'IN_PROGRESS' || status === 'RETEST_REQUIRED' || status === 'TEST_COMPLETED' || status === 'TESTS_COMPLETED') && testSummaries.length > 0);
  const showReport = isReportReady(status);
  const operatorName = job.assigned_inspector_name || 'Inspector S. Sharma';

  return (
    <section className="page-section">
      <Link className="back-link" to="/jobs"><ArrowLeft size={16} /> Jobs</Link>

      <div className="page-heading">
        <div>
          <p className="eyebrow">Verification job</p>
          <h1>{job.job_number || job.job_id}</h1>
          <p className="page-description">
            {pretty(job.job_type)} ·{' '}
            {String(job.instrument_snapshot?.model_name ?? job.instrument_id)}
          </p>
        </div>
        <span className={`status-badge ${status.toLowerCase()}`} style={{ fontSize: 13, padding: '6px 10px' }}>
          {pretty(status)}
          {refreshing && <Loader size={12} style={{ marginLeft: 6, verticalAlign: 'middle', opacity: 0.6 }} />}
        </span>
      </div>

      {/* Visual Workflow Stepper */}
      <WorkflowStepper status={status} />

      <div className="detail-grid">
        {/* 1. Job details */}
        <article className="detail-section">
          <h2>Job details</h2>
          <dl>
            {[
              ['Job ID', job.job_id],
              ['Job number', job.job_number],
              ['Type', pretty(job.job_type)],
              ['Status', pretty(status)],
              ['Instrument', String(job.instrument_snapshot?.model_name ?? job.instrument_id)],
              ['Inspector', job.assigned_inspector_name],
              ['Scheduled', job.scheduled_date],
            ].map(([k, v]) => (
              <div key={k as string}>
                <dt>{k as string}</dt>
                <dd>{v ?? '—'}</dd>
              </div>
            ))}
          </dl>
        </article>

        {/* 2. Statutory test programme */}
        <article className="detail-section">
          <h2>Statutory test programme ({applicableTests.length})</h2>
          {applicableTests.length === 0 ? (
            <p style={{ color: '#829ab1', fontSize: 13 }}>No applicable tests listed.</p>
          ) : (
            <ul style={{ margin: 0, padding: '0 0 0 18px', fontSize: 13, color: '#334e68' }}>
              {applicableTests.map((t) => {
                const canonical = resolveCanonicalTestType(t);
                const label = TEST_TYPE_LABELS[canonical] || t.replace(/_/g, ' ');
                return <li key={t} style={{ paddingBottom: 4 }}>{label}</li>;
              })}
            </ul>
          )}
        </article>

        {/* 3. Generated Regulatory Test Plan */}
        <RegulatoryTestPlanSection
          job={job}
          onStartExecution={() => {
            const el = document.getElementById('test-execution-form-section');
            if (el) el.scrollIntoView({ behavior: 'smooth' });
          }}
        />

        {/* 4. Statutory Pre-Test Validation */}
        <JobValidationSection
          job={job}
          operator={operatorName}
          onJobValidated={() => loadJob(true)}
        />

        {/* 5. Test execution — shown when job is in any execution-ready state */}
        {showExecution && (
          <TestExecutionSection
            job={job}
            applicableTests={applicableTests}
            testSummaries={testSummaries}
            onJobStatusChange={handleStatusChange}
            defaultOperator={operatorName}
          />
        )}

        {/* 6. Supervisory Review & Approval Section */}
        {showReview && (
          <ReviewSection
            job={job}
            testSummaries={testSummaries}
            onJobStatusChange={handleStatusChange}
            inspectorName={operatorName}
          />
        )}

        {/* Standalone results when job is completed and review is closed */}
        {!showReview && testSummaries.length > 0 && (
          <section className="detail-section" style={{ gridColumn: '1 / -1' }}>
            <h2>Test Results Summary</h2>
            <TestResultsTable summaries={testSummaries} loading={resultsLoading} />
          </section>
        )}

        {/* 7. Report Generation & PDF Download */}
        {showReport && <ReportGenSection job={job} onJobRefresh={() => loadJob(true)} />}

        {/* 8. Statutory Audit Trail */}
        <JobAuditTrailSection jobId={job.job_id} />
      </div>
    </section>
  );
}
