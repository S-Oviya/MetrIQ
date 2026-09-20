import {
  ArrowRight,
  Briefcase,
  CheckCircle2,
  Loader,
  Plus,
  Scale,
  TriangleAlert,
  X,
} from 'lucide-react';
import React, { FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ApiError,
  CreateJobPayload,
  InstrumentRecord,
  instrumentsApi,
  jobsApi,
} from '../../services/api/client';

interface CreateJobModalProps {
  isOpen: boolean;
  initialInstrumentId?: string;
  onClose: () => void;
  onSuccess?: (jobId: string) => void;
  onRequestRegisterInstrument?: () => void;
}

export function CreateJobModal({
  isOpen,
  initialInstrumentId,
  onClose,
  onSuccess,
  onRequestRegisterInstrument,
}: CreateJobModalProps) {
  const navigate = useNavigate();
  const [instruments, setInstruments] = useState<InstrumentRecord[]>([]);
  const [loadingInstruments, setLoadingInstruments] = useState(true);
  const [selectedInstrumentId, setSelectedInstrumentId] = useState(initialInstrumentId ?? '');

  const [jobType, setJobType] = useState('RE_VERIFICATION');
  const [priority, setPriority] = useState('NORMAL');
  const [inspectorName, setInspectorName] = useState('R. K. Sharma (Legal Metrology Officer)');
  const [inspectorId, setInspectorId] = useState('INS-042');
  const [scheduledDate, setScheduledDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [testingCentre, setTestingCentre] = useState('Central Legal Metrology Lab');
  const [locationType, setLocationType] = useState('ON_SITE');
  const [notes, setNotes] = useState('');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    setLoadingInstruments(true);
    instrumentsApi
      .list()
      .then((res) => {
        const list = res.data ?? [];
        setInstruments(list);
        if (initialInstrumentId && list.some((i) => i.instrument_id === initialInstrumentId)) {
          setSelectedInstrumentId(initialInstrumentId);
        } else if (list.length > 0 && !selectedInstrumentId) {
          setSelectedInstrumentId(list[0].instrument_id);
        }
      })
      .catch(() => {
        setError('Failed to fetch instruments from registry.');
      })
      .finally(() => setLoadingInstruments(false));
  }, [isOpen, initialInstrumentId]);

  if (!isOpen) return null;

  const selectedInst = instruments.find((i) => i.instrument_id === selectedInstrumentId);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedInstrumentId) {
      setError('Please select an instrument to verify.');
      return;
    }

    setSaving(true);
    setError('');

    try {
      const payload: CreateJobPayload = {
        instrument_id: selectedInstrumentId,
        job_type: jobType,
        priority,
        scheduled_date: scheduledDate,
        assigned_inspector_name: inspectorName.trim() || undefined,
        assigned_inspector_id: inspectorId.trim() || undefined,
        testing_centre_name: testingCentre.trim() || undefined,
        verification_location_type: locationType,
        notes: notes.trim() || undefined,
        created_by: 'OFFICER',
      };

      const res = await jobsApi.create(payload);
      const newJobId = res.job_id ?? (res.data as { job_id?: string })?.job_id;

      if (newJobId) {
        onClose();
        if (onSuccess) onSuccess(newJobId);
        navigate(`/jobs/${encodeURIComponent(newJobId)}`);
      } else {
        throw new Error('Backend did not return a job ID.');
      }
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : 'Failed to create verification job.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(16, 42, 67, 0.65)',
        zIndex: 1000,
        display: 'grid',
        placeItems: 'center',
        padding: '24px',
        overflowY: 'auto',
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-job-title"
    >
      <div
        style={{
          background: '#fff',
          border: '1px solid #d9e2ec',
          boxShadow: '0 10px 25px rgba(0, 0, 0, 0.2)',
          width: '100%',
          maxWidth: '680px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: 2,
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '20px 24px',
            borderBottom: '1px solid #e6edf3',
            background: '#f8fafc',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Briefcase size={22} color="#245d85" />
            <div>
              <h2 id="create-job-title" style={{ margin: 0, fontSize: 18, color: '#102a43' }}>
                Create Verification Job
              </h2>
              <p style={{ margin: '2px 0 0', fontSize: 12, color: '#627d98' }}>
                Provisions a statutory verification job and generates the regulatory test plan.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              color: '#627d98',
              padding: 4,
            }}
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>

        {/* Scrollable Form */}
        <form onSubmit={handleSubmit} style={{ overflowY: 'auto', padding: '24px', flex: 1 }}>
          {error && (
            <div className="notice error" style={{ marginBottom: 16 }}>
              <TriangleAlert size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              {error}
            </div>
          )}

          {/* Section 1: Instrument Selection */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <label style={{ fontSize: 12, fontWeight: 700, color: '#334e68' }}>
                Select Weighing Instrument *
              </label>
              {onRequestRegisterInstrument && (
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onRequestRegisterInstrument();
                  }}
                  style={{
                    border: 'none',
                    background: 'none',
                    color: '#1d5d87',
                    fontWeight: 700,
                    fontSize: 12,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                  }}
                >
                  <Plus size={13} /> Register New Instrument
                </button>
              )}
            </div>

            {loadingInstruments ? (
              <p style={{ color: '#627d98', fontSize: 13 }}>Loading registered instruments…</p>
            ) : instruments.length === 0 ? (
              <div className="notice error" style={{ margin: 0 }}>
                No registered instruments found in inventory.{' '}
                {onRequestRegisterInstrument && (
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      onRequestRegisterInstrument();
                    }}
                    className="primary-button"
                    style={{ minHeight: 28, padding: '0 10px', fontSize: 11, marginLeft: 8 }}
                  >
                    <Plus size={12} /> Register an instrument now
                  </button>
                )}
              </div>
            ) : (
              <>
                <select
                  required
                  style={{
                    width: '100%',
                    minHeight: 40,
                    padding: '0 12px',
                    border: '1px solid #bcccdc',
                    background: '#fff',
                    fontSize: 13,
                    color: '#102a43',
                  }}
                  value={selectedInstrumentId}
                  onChange={(e) => setSelectedInstrumentId(e.target.value)}
                >
                  {instruments.map((inst) => (
                    <option key={inst.instrument_id} value={inst.instrument_id}>
                      {inst.instrument_id} — {inst.model_name} (SN: {inst.serial_number}) · Max {inst.max_capacity} {inst.unit} [Class {String(inst.accuracy_class).replace('CLASS_', '')}]
                    </option>
                  ))}
                </select>

                {selectedInst && (
                  <div
                    style={{
                      marginTop: 10,
                      padding: '12px 14px',
                      background: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      fontSize: 12,
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 1fr)',
                      gap: 8,
                    }}
                  >
                    <div>
                      <span style={{ color: '#627d98', display: 'block' }}>Manufacturer:</span>
                      <strong>{selectedInst.manufacturer}</strong>
                    </div>
                    <div>
                      <span style={{ color: '#627d98', display: 'block' }}>Capacity / e:</span>
                      <strong>
                        {selectedInst.max_capacity} {selectedInst.unit} (e={selectedInst.e} {selectedInst.unit})
                      </strong>
                    </div>
                    <div>
                      <span style={{ color: '#627d98', display: 'block' }}>Customer / Site:</span>
                      <strong>{selectedInst.location?.customer_name || 'Standard Client'}</strong>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Section 2: Verification Context */}
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: 13, color: '#3c78a5', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>
              Verification Context &amp; Routing
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Job Type *
                </label>
                <select
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
                  value={jobType}
                  onChange={(e) => setJobType(e.target.value)}
                >
                  <option value="INITIAL_VERIFICATION">Initial Verification (Rule 14)</option>
                  <option value="RE_VERIFICATION">Periodic Re-Verification (Annual/Bi-annual)</option>
                  <option value="POST_REPAIR">Post-Repair Re-Verification</option>
                  <option value="POST_RELOCATION">Post-Relocation / Reinstallation</option>
                  <option value="MODEL_APPROVAL">Model / Pattern Evaluation</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Priority
                </label>
                <select
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                >
                  <option value="NORMAL">Normal (Standard Schedule)</option>
                  <option value="HIGH">High (Within 48 hours)</option>
                  <option value="URGENT">Urgent (Immediate)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Assigned Inspector
                </label>
                <input
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={inspectorName}
                  onChange={(e) => setInspectorName(e.target.value)}
                  placeholder="Inspector name"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Scheduled Date
                </label>
                <input
                  type="date"
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={scheduledDate}
                  onChange={(e) => setScheduledDate(e.target.value)}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Verification Location
                </label>
                <select
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
                  value={locationType}
                  onChange={(e) => setLocationType(e.target.value)}
                >
                  <option value="ON_SITE">On-Site (At Trader / Customer Premise)</option>
                  <option value="TESTING_CENTRE">Testing Centre (GATC / Lab)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Assigned Laboratory / GATC
                </label>
                <input
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={testingCentre}
                  onChange={(e) => setTestingCentre(e.target.value)}
                  placeholder="Testing Centre Name"
                />
              </div>
            </div>

            <div style={{ marginTop: 14 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                Operational Notes
              </label>
              <textarea
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  border: '1px solid #bcccdc',
                  fontSize: 13,
                  fontFamily: 'inherit',
                  resize: 'vertical',
                }}
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Optional verification instructions or statutory remarks…"
              />
            </div>
          </div>

          {/* Footer */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 10,
              marginTop: 20,
              paddingTop: 16,
              borderTop: '1px solid #e6edf3',
            }}
          >
            <button
              type="button"
              className="secondary-button"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="primary-button"
              disabled={saving || instruments.length === 0}
            >
              {saving ? <Loader size={14} /> : <CheckCircle2 size={14} />}
              {saving ? 'Creating Job…' : 'Create Job & Generate Plan'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
