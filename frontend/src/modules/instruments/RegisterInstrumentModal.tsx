import { CheckCircle2, Loader, Scale, ShieldCheck, TriangleAlert, X } from 'lucide-react';
import React, { FormEvent, useState } from 'react';
import {
  ApiError,
  CreateInstrumentPayload,
  InstrumentRecord,
  instrumentsApi,
} from '../../services/api/client';

interface RegisterInstrumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (newInstrument: InstrumentRecord) => void;
}

export function RegisterInstrumentModal({
  isOpen,
  onClose,
  onSuccess,
}: RegisterInstrumentModalProps) {
  const [manufacturer, setManufacturer] = useState('Avery India');
  const [modelName, setModelName] = useState('DS-215 Electronic Scale');
  const [modelNumber, setModelNumber] = useState('DS-215');
  const [serialNumber, setSerialNumber] = useState(() => `SN-${Date.now().toString().slice(-6)}`);
  const [instrumentType, setInstrumentType] = useState('ELECTRONIC_COUNTER_SCALE');
  const [usageType, setUsageType] = useState('COMMERCIAL_TRADE');
  const [accuracyClass, setAccuracyClass] = useState('CLASS_III');
  const [maxCapacity, setMaxCapacity] = useState('15');
  const [minCapacity, setMinCapacity] = useState('0.1');
  const [eVal, setEVal] = useState('0.005');
  const [dVal, setDVal] = useState('0.005');
  const [unit, setUnit] = useState('kg');
  const [modelApprovalNumber, setModelApprovalNumber] = useState('IND/09/2023/452');
  const [customerName, setCustomerName] = useState('Metro Retail Mart');
  const [city, setCity] = useState('Mumbai');
  const [state, setState] = useState('Maharashtra');

  const [validationResult, setValidationResult] = useState<{
    valid?: boolean;
    message?: string;
    errors?: string[];
    warnings?: string[];
  } | null>(null);
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const buildPayload = (): CreateInstrumentPayload => {
    const max = parseFloat(maxCapacity) || 0;
    const e = parseFloat(eVal) || 0;
    const min = minCapacity ? parseFloat(minCapacity) : e * 20;
    const d = dVal ? parseFloat(dVal) : e;

    return {
      manufacturer: manufacturer.trim(),
      model_name: modelName.trim(),
      model_number: modelNumber.trim() || modelName.trim(),
      serial_number: serialNumber.trim(),
      instrument_type: instrumentType,
      usage_type: usageType,
      accuracy_class: accuracyClass,
      max_capacity: max,
      min_capacity: min,
      e,
      d,
      unit,
      model_approval_number: modelApprovalNumber.trim() || undefined,
      location: {
        customer_name: customerName.trim() || undefined,
        city: city.trim() || undefined,
        state: state.trim() || undefined,
      },
    };
  };

  const handlePreValidate = async () => {
    setValidating(true);
    setError('');
    setValidationResult(null);
    try {
      const payload = buildPayload();
      const res = await instrumentsApi.validateMetrology(payload as unknown as Record<string, unknown>);
      const data = res.data as { valid?: boolean; errors?: Array<{ message: string }>; warnings?: Array<{ message: string }> } | undefined;
      const isValid = res.valid ?? data?.valid ?? true;
      const errors = data?.errors?.map((err) => err.message) ?? [];
      const warnings = data?.warnings?.map((w) => w.message) ?? [];

      setValidationResult({
        valid: isValid,
        message: isValid ? 'Statutory metrological parameters are valid.' : 'Metrological parameters failed validation.',
        errors,
        warnings,
      });
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : 'Metrology pre-validation failed.');
    } finally {
      setValidating(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!manufacturer.trim() || !modelName.trim() || !serialNumber.trim()) {
      setError('Manufacturer, Model Name, and Serial Number are required.');
      return;
    }

    setSaving(true);
    setError('');
    try {
      const payload = buildPayload();
      const res = await instrumentsApi.create(payload, false);
      if (res.data) {
        onSuccess(res.data);
        onClose();
      }
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : 'Failed to register instrument.');
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
      aria-labelledby="register-instrument-title"
    >
      <div
        style={{
          background: '#fff',
          border: '1px solid #d9e2ec',
          boxShadow: '0 10px 25px rgba(0, 0, 0, 0.2)',
          width: '100%',
          maxWidth: '740px',
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
            <Scale size={22} color="#245d85" />
            <div>
              <h2 id="register-instrument-title" style={{ margin: 0, fontSize: 18, color: '#102a43' }}>
                Register New Weighing Instrument
              </h2>
              <p style={{ margin: '2px 0 0', fontSize: 12, color: '#627d98' }}>
                Registers an instrument into the statutory MetrIQ inventory.
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

        {/* Scrollable Body */}
        <form onSubmit={handleSubmit} style={{ overflowY: 'auto', padding: '24px', flex: 1 }}>
          {error && (
            <div className="notice error" style={{ marginBottom: 16 }}>
              <TriangleAlert size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              {error}
            </div>
          )}

          {validationResult && (
            <div
              className={`notice ${validationResult.valid ? 'info' : 'error'}`}
              style={{ marginBottom: 16 }}
            >
              {validationResult.valid ? (
                <CheckCircle2 size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              ) : (
                <TriangleAlert size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              )}
              <strong>{validationResult.message}</strong>
              {validationResult.errors && validationResult.errors.length > 0 && (
                <ul style={{ margin: '6px 0 0', paddingLeft: 20 }}>
                  {validationResult.errors.map((err, idx) => (
                    <li key={idx}>{err}</li>
                  ))}
                </ul>
              )}
              {validationResult.warnings && validationResult.warnings.length > 0 && (
                <ul style={{ margin: '6px 0 0', paddingLeft: 20, color: '#785000' }}>
                  {validationResult.warnings.map((w, idx) => (
                    <li key={idx}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Section 1: Identification */}
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: 13, color: '#3c78a5', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>
              1. Instrument Identification
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Manufacturer *
                </label>
                <input
                  required
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={manufacturer}
                  onChange={(e) => setManufacturer(e.target.value)}
                  placeholder="e.g. Avery India"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Model Name *
                </label>
                <input
                  required
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  placeholder="e.g. DS-215 Counter Scale"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Serial Number *
                </label>
                <input
                  required
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={serialNumber}
                  onChange={(e) => setSerialNumber(e.target.value)}
                  placeholder="e.g. SN-99824"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Instrument Type
                </label>
                <select
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
                  value={instrumentType}
                  onChange={(e) => setInstrumentType(e.target.value)}
                >
                  <option value="ELECTRONIC_COUNTER_SCALE">Electronic Counter Scale (Table Top)</option>
                  <option value="BENCH_SCALE">Bench Scale</option>
                  <option value="PLATFORM_SCALE">Platform Scale</option>
                  <option value="WEIGHBRIDGE">Weighbridge (Truck Scale)</option>
                  <option value="PRECISION_BALANCE">Precision Laboratory Balance</option>
                  <option value="CRANE_SCALE">Crane Suspended Scale</option>
                </select>
              </div>
            </div>
          </div>

          {/* Section 2: Metrological Parameters */}
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: 13, color: '#3c78a5', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>
              2. Metrological Characteristics (OIML R 76-1)
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Accuracy Class *
                </label>
                <select
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
                  value={accuracyClass}
                  onChange={(e) => setAccuracyClass(e.target.value)}
                >
                  <option value="CLASS_I">Class I (Special Accuracy)</option>
                  <option value="CLASS_II">Class II (High Accuracy)</option>
                  <option value="CLASS_III">Class III (Medium Accuracy - Trade)</option>
                  <option value="CLASS_IIII">Class IIII (Ordinary Accuracy)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Max Capacity (Max) *
                </label>
                <input
                  type="number"
                  step="any"
                  required
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={maxCapacity}
                  onChange={(e) => setMaxCapacity(e.target.value)}
                  placeholder="15"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Unit of Measure *
                </label>
                <select
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
                  value={unit}
                  onChange={(e) => setUnit(e.target.value)}
                >
                  <option value="kg">kg (Kilogram)</option>
                  <option value="g">g (Gram)</option>
                  <option value="t">t (Tonne)</option>
                  <option value="mg">mg (Milligram)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Verification Scale Interval (e) *
                </label>
                <input
                  type="number"
                  step="any"
                  required
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={eVal}
                  onChange={(e) => {
                    setEVal(e.target.value);
                    if (!dVal || dVal === eVal) setDVal(e.target.value);
                  }}
                  placeholder="0.005"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Actual Scale Interval (d)
                </label>
                <input
                  type="number"
                  step="any"
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={dVal}
                  onChange={(e) => setDVal(e.target.value)}
                  placeholder="0.005"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Min Capacity (Min)
                </label>
                <input
                  type="number"
                  step="any"
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={minCapacity}
                  onChange={(e) => setMinCapacity(e.target.value)}
                  placeholder="0.1"
                />
              </div>
            </div>
          </div>

          {/* Section 3: Legal & Deployment */}
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: 13, color: '#3c78a5', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>
              3. Regulatory Compliance & Deployment
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Model Approval Number
                </label>
                <input
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={modelApprovalNumber}
                  onChange={(e) => setModelApprovalNumber(e.target.value)}
                  placeholder="IND/09/2023/452"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Usage Type
                </label>
                <select
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc', background: '#fff' }}
                  value={usageType}
                  onChange={(e) => setUsageType(e.target.value)}
                >
                  <option value="COMMERCIAL_TRADE">Commercial Trade (Direct Retail)</option>
                  <option value="INDUSTRIAL">Industrial / Factory</option>
                  <option value="LABORATORY_RESEARCH">Laboratory & Scientific</option>
                  <option value="HEALTHCARE_MEDICAL">Healthcare / Pharmaceutical</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                  Customer / Establishment Name
                </label>
                <input
                  style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  placeholder="Metro Retail Mart"
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                    City
                  </label>
                  <input
                    style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="Mumbai"
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#334e68', marginBottom: 4 }}>
                    State
                  </label>
                  <input
                    style={{ width: '100%', minHeight: 36, padding: '0 10px', border: '1px solid #bcccdc' }}
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    placeholder="Maharashtra"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Footer controls */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginTop: 24,
              paddingTop: 16,
              borderTop: '1px solid #e6edf3',
            }}
          >
            <button
              type="button"
              className="secondary-button"
              onClick={() => void handlePreValidate()}
              disabled={validating}
            >
              {validating ? <Loader size={14} /> : <ShieldCheck size={14} />}
              {validating ? 'Validating…' : 'Pre-validate Metrology'}
            </button>

            <div style={{ display: 'flex', gap: 10 }}>
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
                disabled={saving}
              >
                {saving ? <Loader size={14} /> : <CheckCircle2 size={14} />}
                {saving ? 'Registering…' : 'Save & Register Instrument'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
