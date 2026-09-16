# MetrIQ — Regulatory Engine Module (`backend/app/regulatory`)

**Role:** Person 2 — Regulatory Engineer  
**Project:** MetrIQ / METRA (SIH26035 — NAWI Test Report Generation Software)  
**Standard Compliance:**
- **OIML R 76-1:2006 (E)**: *Non-automatic weighing instruments — Part 1: Metrological and technical requirements — Tests*
- **Indian Legal Metrology (General) Rules, 2011**: *Seventh Schedule, Heading A: Non-Automatic Weighing Instruments*
- **Indian Legal Metrology (Amendment) Rules, 2022**: *Digital displays, weighbridge specifications*

---

## Table of Contents

1. [Module Overview](#1-module-overview)
2. [Architecture & Separation of Concerns](#2-architecture--separation-of-concerns)
3. [Public Interfaces (Functions, Classes, API Endpoints)](#3-public-interfaces)
4. [Data Models, Inputs, and Outputs](#4-data-models-inputs-and-outputs)
5. [Metrological Rules & Mathematical Formulations](#5-metrological-rules--mathematical-formulations)
   - [Accuracy Class Boundaries (Table 3 / Table 1)](#accuracy-class-boundaries)
   - [Scale Interval Form ($1, 2, 5 \times 10^k$)](#scale-interval-form)
   - [Auxiliary Indicating Devices ($d$ vs $e$)](#auxiliary-indicating-devices)
   - [Maximum Permissible Error (MPE) Tables](#maximum-permissible-error-mpe)
   - [Multi-Interval Instruments](#multi-interval-instruments)
6. [Test Applicability Matrix](#6-test-applicability-matrix)
7. [Automatic Test Plan Generation](#7-automatic-test-plan-generation)
8. [Configurable Rules & Laboratory Overrides](#8-configurable-rules--laboratory-overrides)
9. [Rules Requiring Manual Review (Inspector Checklist)](#9-rules-requiring-manual-review)
10. [Integration Guide for Team Members](#10-integration-guide-for-team-members)
    - [Person 1 (Core Integration / Lead)](#person-1-core-integration--lead)
    - [Person 3 (Instruments & Jobs)](#person-3-instruments--jobs)
    - [Person 4 (Test Engine & Calculations)](#person-4-test-engine--calculations)
11. [Running the Unit Tests](#11-running-the-unit-tests)

---

## 1. Module Overview

The **Regulatory Engine** is the authoritative metrological brain of MetrIQ. It enforces statutory compliance, validates instrument metrological parameters, computes statutory Maximum Permissible Errors (MPE), resolves test applicability across diverse verification jobs, and automatically generates comprehensive, sequenced test plans.

### Core Capabilities:
- **Statutory Source Registry:** Manages OIML R 76-1:2006, Indian Legal Metrology Rules 2011, amendments, and custom ISO/IEC 17025 accredited laboratory specifications.
- **Accuracy Class Verification:** Validates Class I, Class II, Class III, and Class IIII instruments against mandatory bounds for verification scale intervals ($e$), interval counts ($n = \text{Max}/e$), and minimum capacities ($\text{Min} \ge k \cdot e$).
- **Scale Parameter Validation:** Validates form of $e \in \{1, 2, 5\} \times 10^k$, auxiliary devices ($d < e \le 10d$), multi-interval partial ranges, tare limits, and temperature specifications.
- **Dynamic MPE Calculator:** Computes exact tolerance limits in both scale intervals ($e$) and engineering mass units ($g, kg, mg, t$) for gross and net loads across initial verification and in-service inspection.
- **Statutory Applicability Resolver:** Determines which of the 12 metrological tests apply to a given job type (`INITIAL_VERIFICATION`, `RE_VERIFICATION`, `MODEL_APPROVAL`, `POST_REPAIR`, `POST_RELOCATION`, `RETEST`).
- **Automated Test Plan Generator:** Generates discrete, numbered test points with loading/unloading sequences, eccentric corner positions, repeatability runs, and tare tests with pre-calculated tolerance bands.
- **Structured Diagnostic Reporting:** Provides rich, strongly-typed issue reports with error codes, normative clause citations, severity levels, and actionable suggestions.

---

## 2. Architecture & Separation of Concerns

The module is situated inside `backend/app/regulatory/` and requires zero heavy external dependencies (runs out of the box on Python 3.10+ standard library):

```text
backend/app/regulatory/
├── __init__.py            # Root package export of public interfaces
├── models.py              # Domain models (AccuracyClass, InstrumentProfile, TestPlan, MPEValue)
├── sources.py             # Statutory standards, jurisdictions, and version registry
├── accuracy_class.py      # Table 3/Table 1 classification boundaries and validation
├── scale_validation.py    # e, d, Max, Min, n, and multi-interval validation logic
├── mpe.py                 # Maximum Permissible Error calculation and tolerance checking
├── applicability.py       # Test applicability matrix for job types & instrument types
├── test_plan.py           # Automatic test plan generator with test point sequences
├── config.py              # Configurable overrides and manual review inspection checklists
├── errors.py              # RegulatoryErrorCode, RegulatoryIssue, ValidationResult
├── router.py              # REST API service functions and optional FastAPI router
└── README.md              # Complete metrological documentation
```

### Separation of Concerns:
- **Person 2 (Regulatory Engine)**: Owns the statutory rules, MPE definitions, test requirements, and test plan specifications.
- **Person 3 (Instruments & Jobs)**: Gathers instrument attributes and creates test jobs; queries Person 2 to validate instrument feasibility.
- **Person 4 (Test Engine & Calculations)**: Consumes the test plan and MPE tolerance limits from Person 2 to log raw readings and evaluate PASS/FAIL. **Person 4 does not duplicate MPE tables.**

---

## 3. Public Interfaces

All public classes and functions can be directly imported from `app.regulatory`:

```python
from app.regulatory import (
    # Domain Models
    AccuracyClass,
    InstrumentProfile,
    WeighingRange,
    JobType,
    MassUnit,
    MPEValue,
    TestPlan,
    TestPoint,
    TestType,
    ReceptorType,
    
    # Core Validation Functions
    validate_instrument_scales,
    validate_accuracy_class,
    is_valid_scale_interval_form,
    determine_eligible_classes,
    
    # MPE Engine
    calculate_mpe,
    calculate_mpe_in_e,
    is_error_within_mpe,
    get_mpe_breakpoints_for_instrument,
    
    # Applicability & Test Plans
    get_applicable_tests,
    is_test_applicable,
    generate_test_plan,
    
    # Errors & Configuration
    ValidationResult,
    RegulatoryIssue,
    RegulatoryErrorCode,
    RegulatoryConfig,
    REGULATORY_REGISTRY,
    get_manual_review_checklist,
)
```

### Summary of Primary Functions:

| Function | Signature | Responsibility |
| :--- | :--- | :--- |
| `validate_instrument_scales` | `(instrument, standard_id="OIML_R76_2006") -> ValidationResult` | Runs complete statutory check on $e, d, \text{Max}, \text{Min}, n$, auxiliary devices, and partial ranges. |
| `calculate_mpe` | `(load, instrument, job_type, tare_load=0.0, standard_id="OIML_R76_2006") -> MPEValue` | Computes statutory MPE in $e$ and engineering units, lower/upper error bounds, and clause references. |
| `is_error_within_mpe` | `(observed_error, load, instrument, job_type, tare_load=0.0) -> Tuple[bool, MPEValue]` | Evaluates whether an observed error passes or fails statutory tolerance. |
| `get_applicable_tests` | `(instrument, job_type, standard_id="OIML_R76_2006") -> List[ApplicableTest]` | Resolves which of the 12 metrological tests are mandatory, optional, or not applicable. |
| `generate_test_plan` | `(instrument, job_type, standard_id="OIML_R76_2006", config=None) -> TestPlan` | Generates a complete test plan with sequenced test points, eccentric positions, and MPE bands. |
| `determine_eligible_classes` | `(e, max_capacity, min_capacity, unit) -> List[Tuple[AccuracyClass, str]]` | Analyzes a scale's parameters and returns all statutory classes it qualifies for. |

### REST API Endpoints (in `backend/app/regulatory/router.py`):
- `POST /api/regulatory/validate-scales`: Accepts instrument profile JSON, returns `ValidationResult`.
- `POST /api/regulatory/calculate-mpe`: Accepts instrument, load, and job type, returns `MPEValue`.
- `POST /api/regulatory/evaluate-error`: Accepts instrument, load, and observed error, returns PASS/FAIL evaluation.
- `POST /api/regulatory/applicable-tests`: Accepts instrument and job type, returns list of applicable tests.
- `POST /api/regulatory/generate-test-plan`: Accepts instrument and job type, returns full `TestPlan`.
- `GET /api/regulatory/standards`: Returns all registered statutory standards.
- `GET /api/regulatory/manual-review-checklist`: Returns statutory physical inspection items.

---

## 4. Data Models, Inputs, and Outputs

### `InstrumentProfile` (Input Model)
```python
from app.regulatory import InstrumentProfile, AccuracyClass, MassUnit, ReceptorType

instrument = InstrumentProfile(
    manufacturer="Avery Weigh-Tronix",
    model="ZM301",
    serial_number="SN-2026-8812",
    accuracy_class=AccuracyClass.CLASS_III,  # CLASS_I, CLASS_II, CLASS_III, CLASS_IIII
    max_capacity=15.0,                      # 15 kg
    min_capacity=0.1,                       # 100 g (20e)
    e=0.005,                                # 5 g verification scale interval
    d=0.005,                                # 5 g actual scale interval
    unit=MassUnit.KG,                       # MG, G, KG, T, CT
    is_multi_interval=False,
    has_tare=True,
    is_electronic=True,
    has_software=True,
    software_version="v2.1.0",
    receptor_type=ReceptorType.STANDARD_PLATTER,
)
```

### `ValidationResult` (Output Model)
```python
result = validate_instrument_scales(instrument)
if not result.is_valid:
    for err in result.errors:
        print(f"[{err.code}] {err.field}: {err.message} (Ref: {err.reference_clause})")
```
- `is_valid: bool`: True if zero statutory errors exist.
- `errors: List[RegulatoryIssue]`: Blocking regulatory violations.
- `warnings: List[RegulatoryIssue]`: Non-blocking warnings (e.g. narrow temperature operating span).
- `manual_reviews: List[RegulatoryIssue]`: Items flagged for inspector physical verification.
- `metadata: Dict[str, Any]`: Calculated $n$, normalized units, and standard metadata.

### `MPEValue` (Output Model)
```python
mpe = calculate_mpe(load=2.5, instrument=instrument, job_type=JobType.INITIAL_VERIFICATION)
# Output attributes:
# mpe.load = 2.5 kg
# mpe.load_in_e = 500.0
# mpe.mpe_in_e = 0.5 e
# mpe.mpe_in_units = 0.0025 kg (+/- 2.5 g)
# mpe.lower_limit_error = -0.0025 kg
# mpe.upper_limit_error = 0.0025 kg
# mpe.verification_type = "INITIAL"
# mpe.reference_clause = "OIML R 76-1:2006 Clause 3.5.1 (Table 6 initial verification)"
```

---

## 5. Metrological Rules & Mathematical Formulations

### Accuracy Class Boundaries
*Source: OIML R 76-1:2006 Table 3 / Indian Legal Metrology Rules, 2011 Table 1*

$$\text{Scale Interval Count } n = \frac{\text{Max}}{e}$$

| Accuracy Class | Verification Scale Interval ($e$) | Minimum $n$ ($n_{\min}$) | Maximum $n$ ($n_{\max}$) | Minimum Capacity ($\text{Min}$) |
| :--- | :--- | :--- | :--- | :--- |
| **Class I** ($\text{Special}$) | $0.001\text{ g} \le e$ | $50,000$ | No limit | $100 \cdot e$ |
| **Class II** ($\text{High}$) | $0.001\text{ g} \le e \le 0.05\text{ g}$<br>$0.1\text{ g} \le e$ | $100$<br>$5,000$ | $100,000$<br>$100,000$ | $20 \cdot e$<br>$50 \cdot e$ |
| **Class III** ($\text{Medium}$) | $0.1\text{ g} \le e \le 2\text{ g}$<br>$5\text{ g} \le e$ | $100$<br>$500$ | $10,000$<br>$10,000$ | $20 \cdot e$<br>$20 \cdot e$ |
| **Class IIII** ($\text{Ordinary}$) | $5\text{ g} \le e$ | $100$ | $1,000$ | $10 \cdot e$ |

### Scale Interval Form
*Source: OIML R 76-1 Clause 3.2.1 / IN LM 2011 Part I Clause 3*

The verification scale interval $e$ must strictly satisfy:
$$e = 1 \times 10^k, \quad 2 \times 10^k, \quad \text{or} \quad 5 \times 10^k \quad \text{units of mass} \quad (k \in \mathbb{Z})$$
Any values such as $3\text{ g}, 4\text{ g}, 7\text{ g}, 2.5\text{ g}$ trigger `RegulatoryErrorCode.INVALID_SCALE_INTERVAL_FORM`.

### Auxiliary Indicating Devices
*Source: OIML R 76-1 Clause 3.4.1 & 3.4.2*
- Auxiliary indicating devices ($d < e$) are permitted **only for Class I and Class II**.
- Permitted ratio: $d < e \le 10d$.
- For **Class III and Class IIII**, auxiliary indicating devices with differentiated scale intervals are strictly prohibited under statutory verification ($d = e$).
- $d$ can never exceed $e$ ($d \le e$).

### Maximum Permissible Error (MPE)
*Source: OIML R 76-1 Clause 3.5 & Table 6 / IN LM 2011 Table 2*

#### Initial Verification (`INITIAL_VERIFICATION`, `MODEL_APPROVAL`):
For test load $m$ expressed in verification scale intervals ($m/e$):

| Load Range ($m$ in $e$) — Class I | Load Range ($m$ in $e$) — Class II | Load Range ($m$ in $e$) — Class III | Load Range ($m$ in $e$) — Class IIII | Initial Verification MPE |
| :--- | :--- | :--- | :--- | :--- |
| $0 \le m \le 50,000 e$ | $0 \le m \le 5,000 e$ | $0 \le m \le 500 e$ | $0 \le m \le 50 e$ | **$\pm 0.5 e$** |
| $50,000 e < m \le 200,000 e$ | $5,000 e < m \le 20,000 e$ | $500 e < m \le 2,000 e$ | $50 e < m \le 200 e$ | **$\pm 1.0 e$** |
| $m > 200,000 e$ | $20,000 e < m \le 100,000 e$ | $2,000 e < m \le 10,000 e$ | $200 e < m \le 1,000 e$ | **$\pm 1.5 e$** |

#### In-Service Inspection / Periodic Re-verification (`RE_VERIFICATION`, `POST_RELOCATION`):
Per Clause 3.5.2:
$$\text{MPE}_{\text{in-service}} = 2.0 \times \text{MPE}_{\text{initial}}$$
$$\pm 1.0 e \quad (\text{Band 1}), \quad \pm 2.0 e \quad (\text{Band 2}), \quad \pm 3.0 e \quad (\text{Band 3})$$

#### Net Loads with Tare Device:
Per Clause 3.5.3.3:
$$m_{\text{net}} = m_{\text{gross}} - \text{Tare}$$
The MPE applies to the net load for any tare value.

### Multi-Interval Instruments
*Source: OIML R 76-1 Clause 3.3*
- Partial weighing ranges $1 \dots r$: $e_1 < e_2 < \dots < e_r$.
- $\text{Min}_1 = \text{Min}$, $\text{Max}_r = \text{Max}$.
- Each partial range must independently satisfy accuracy class bounds $n_{\min}$ and $n_{\max}$.
- Auxiliary indicating devices ($d < e$) are not permitted on multi-interval instruments.

---

## 6. Test Applicability Matrix

The engine resolves statutory applicability across 12 standard tests:

| Test Identifier | Test Name | Model Approval | Initial Verification | Re-Verification | Post-Repair | Retest | Primary Statutory Reference |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `VISUAL_EXAMINATION` | Visual & Construction Examination | Yes | Yes | Yes | Yes | Yes | Clause 7.1 / IN LM Part I |
| `WEIGHING_PERFORMANCE`| Weighing Performance (Inc/Dec) | Yes | Yes | Yes | Yes | Yes | Clause A.4.4 |
| `ECCENTRICITY` | Eccentric / Corner Loading | Yes | Yes | Yes | Yes | Yes | Clause A.4.7 |
| `REPEATABILITY` | Repeatability (3 / 10 runs) | Yes | Yes | Yes | Yes | Yes | Clause A.4.10 |
| `DISCRIMINATION` | Digital Discrimination ($+1.4d$) | Yes | Yes | Optional | Yes | Yes | Clause A.4.8 |
| `TARE` | Tare Device & Net Weighing | Yes* | Yes* | Yes* | Yes* | Yes* | Clause A.4.6 (*if tare present) |
| `ZERO_SETTING_AND_TRACKING` | Zero Setting & Tracking Rate | Yes | Yes | No | Conditional| No | Clause A.4.1 - A.4.3 |
| `TILTING` | Tilting Sensitivity | Yes | Mobile only | Mobile only | Mobile only| No | Clause A.4.4 |
| `CREEP_AND_ZERO_RETURN` | Creep & Zero Return (30 min) | Yes | No | No | Major sensor| No | Clause A.4.11 |
| `TEMPERATURE_EFFECT`| Temperature Chamber Testing | Yes | No | No | No | No | Clause A.5.3 |
| `VOLTAGE_VARIATION` | Voltage Fluctuation Immunity | Yes | No | No | No | No | Clause A.5.4 |
| `SOFTWARE_EXAMINATION`| Software Checksum & Event Counter| Yes | Yes* | Yes (check) | Yes* | No | Clause 5.5 (*if software fitted) |

---

## 7. Automatic Test Plan Generation

When `generate_test_plan(instrument, job_type)` is invoked:
1. **Validation Pre-check:** Instrument parameters are validated.
2. **Applicable Test Filter:** Only applicable tests are scheduled.
3. **Weighing Performance Series:**
   - Prepares increasing series: Zero $\to$ Min $\to$ MPE Breakpoints (e.g. $500e, 2000e$) $\to$ $50\%\text{Max}$ $\to$ Max.
   - Prepares decreasing series: Max $\to$ Breakpoints $\to$ Min $\to$ Zero.
   - Attaches pre-calculated `expected_mpe` for each step.
4. **Eccentricity Series:**
   - Standard platter ($\le 4$ supports): Load $= \frac{1}{3}\text{Max}$, applied at Center, Front-Left, Back-Left, Back-Right, Front-Right.
   - Large platforms ($N > 4$ supports): Load $= \frac{1}{N-1}\text{Max}$, applied at each support point $1 \dots N$.
5. **Repeatability Series:**
   - Series A at $\approx 50\%\text{Max}$ (3 runs for verification, 10 for approval).
   - Series B at $\approx 100\%\text{Max}$ (3 runs for verification, 10 for approval).
   - Maximum allowed spread criteria $= |\text{MPE}|$.
6. **Discrimination Series:**
   - Test at Min, $50\%\text{Max}$, and Max with extra load $+1.4d$.
7. **Tare Series:**
   - Prepares tare at $\frac{1}{3}\text{Max}$, tests net weighing across net Min, $50\%$ net Max, and net Max.
8. **Statutory Review Checklist:** Attaches mandatory physical examination items.

---

## 8. Configurable Rules & Laboratory Overrides

Configurable via `RegulatoryConfig`:

```python
from app.regulatory import RegulatoryConfig, generate_test_plan

custom_cfg = RegulatoryConfig(
    in_service_mpe_multiplier=2.0,            # Default 2.0 per OIML 3.5.2
    post_repair_uses_initial_mpe=True,         # Can enforce tighter initial MPE after repair
    min_weighing_points_count=7,               # Increase test point density
    eccentricity_load_ratio=0.333333,          # 1/3 Max standard
    repeatability_cycles_verification=3,       # 3 cycles standard
    repeatability_cycles_approval=10,          # 10 cycles for pattern approval
    discrimination_load_factor=1.4,            # 1.4d standard
    strict_rounding=True,
    state_jurisdiction="Tamil Nadu",           # State-specific jurisdiction
)

plan = generate_test_plan(instrument, JobType.INITIAL_VERIFICATION, config=custom_cfg)
```

---

## 9. Rules Requiring Manual Review

Certain statutory requirements cannot be verified mathematically and require physical verification by a qualified Legal Metrology Officer (LMO) or testing technician. The engine surfaces these via `get_manual_review_checklist()`:

1. **Statutory Markings & Inscription Legibility (`REV_INSCRIPTION_LEGIBILITY`):**
   - Max, Min, e, d, Accuracy Class mark, Serial Number, and Manufacturer Name clearly, indelibly stamped or printed on the nameplate.
2. **Government Model Approval Sign (`REV_MODEL_APPROVAL_SIGN`):**
   - Valid Central Government Gazette notification number displayed on the instrument.
3. **Physical Sealing Provisions & Stamping Plugs (`REV_SEALING_PROVISION`):**
   - Security wire/lead seal intact; stamping plug prepared to accept verification punch.
4. **Level Indicator Alignment & Base Stability (`REV_LEVEL_INDICATOR`):**
   - Spirit level bubble centered in ring; no mechanical foot rocking or severe ambient vibration.
5. **Environmental Operating Limits (`REV_ENVIRONMENT_SUITABILITY`):**
   - Ambient temperature and draft conditions within rated specification.
6. **Software Event Counter Verification (`REV_SOFTWARE_AUDIT_TRAIL`):**
   - Firmware event counter matches value recorded on previous certificate.

---

## 10. Integration Guide for Team Members

### Person 1 (Core Integration / Team Lead):
Person 1 can expose the regulatory engine via FastAPI in `backend/app/api/router.py`:
```python
from app.regulatory.router import router as regulatory_router

# In main API router:
app.include_router(regulatory_router, prefix="/api")
```
If FastAPI is not yet installed, Person 1 can call the pure-Python API functions in `app.regulatory.router`:
- `api_validate_scales(payload)`
- `api_calculate_mpe(payload)`
- `api_evaluate_error(payload)`
- `api_applicable_tests(payload)`
- `api_generate_test_plan(payload)`

### Person 3 (Instruments & Jobs):
Person 3 validates an instrument before storing it or creating a test job:
```python
from app.regulatory import validate_instrument_scales, InstrumentProfile

instrument = InstrumentProfile.from_dict(instrument_data)
validation = validate_instrument_scales(instrument)

if not validation.is_valid:
    # Reject or notify user of invalid metrological combination
    errors = [e.message for e in validation.errors]
    raise ValueError(f"Instrument fails statutory metrology rules: {errors}")
```

### Person 4 (Test Engine & Calculations):
Person 4 requests a statutory test plan and retrieves MPE limits:
```python
from app.regulatory import generate_test_plan, calculate_mpe, is_error_within_mpe, JobType

# 1. Generate the test plan
plan = generate_test_plan(instrument, JobType.INITIAL_VERIFICATION)

# 2. Iterate through weighing performance test points
for point in plan.test_suites["WEIGHING_PERFORMANCE"]:
    target = point.target_load
    mpe_limit = point.expected_mpe.upper_limit_error
    print(f"Apply {target} {point.unit.value}, MPE is +/- {mpe_limit}")

# 3. Evaluate observed error
is_pass, mpe_spec = is_error_within_mpe(
    observed_error=0.002, 
    load=5.0, 
    instrument=instrument, 
    job_type=JobType.INITIAL_VERIFICATION
)
print("Result:", "PASS" if is_pass else "FAIL")
```

---

## 11. Running the Unit Tests

Execute the unit tests from the project root using Python's standard `unittest` test runner:

```bash
cd C:\Users\yogik\MetrIQ
py -m unittest discover backend/tests
```

All 48 comprehensive tests run and pass cleanly in under 0.01 seconds with zero external package dependencies.

---

## 12. MetrIQ Regulatory Knowledge Base (`app.regulatory.knowledge`)

The **MetrIQ Regulatory Knowledge Base** is the authoritative, structured repository of metrological statutory data. It replaces scattered constants with versioned, provenance-tracked rule definitions.

### Knowledge Base Architecture:
```text
backend/app/regulatory/knowledge/
├── __init__.py           # Export knowledge base singleton and models
├── schema.py             # Strongly-typed schemas, Provenance & LegalOrigin metadata
├── sources_data.py       # Primary Indian statutory sources & OIML technical standards
├── classes_data.py       # Complete structured definitions for Accuracy Classes I, II, III, IIII
├── rules_data.py         # Structured metrological rules (Test weights, eccentricity, creep, etc.)
├── gatc_rules_data.py    # Statutory GATC verification routing engine (GATC Rules 2013)
├── amendments_data.py    # Unverified / draft amendments (G.S.R. 568(E) Fourth Amendment 2026)
└── knowledge_base.py     # RegulatoryKnowledgeBase master query manager
```

### Critical Metrological Distinctions:
1. **Indian Statutory Requirements:** Legally binding mandates under the Legal Metrology Act, 2009, General Rules 2011, Model Approval Rules 2011, and GATC Rules 2013 (`LegalOrigin.INDIAN_STATUTORY`).
2. **OIML Technical Standards:** International technical recommendations (OIML R 76-1:2006) (`LegalOrigin.OIML_TECHNICAL`).
3. **Practice / Default Report Formats:** International test report templates (OIML R 76-2:2007) and test certificate layouts (`LegalOrigin.PRACTICE_REPORT_FORMAT`). **OIML R 76-2 is NOT an Indian statutory requirement.**
4. **Configurable Rules:** Rules containing parameters that state controllers or accredited laboratories can adjust (`is_configurable=True`).
5. **Rules Requiring Manual Review:** Physical inspections and non-computational criteria requiring inspector discretion (`requires_manual_review=True`).

### Statutory GATC Verification Routing Rules:
*Source: Legal Metrology (Government Approved Test Centre) Rules, 2013 (First Schedule)*
- **Class III with $\text{Max} \le 150\text{ kg}$:** **Eligible for GATC** verification and stamping.
- **Class III with $\text{Max} > 150\text{ kg}$:** **Not eligible for GATC**; routed to the State Legal Metrology Officer.
- **Class IIII:** **Eligible for GATC** across all standard commercial capacities.
- **Class II (High Accuracy):** **STRICTLY NOT ROUTED TO GATC.** Statutory verification must be performed directly by the State Legal Metrology Officer (correcting historical misconceptions).
- **Class I (Special Accuracy):** **NOT ROUTED TO GATC.**

### Handling of G.S.R. 568(E) / Fourth Amendment 2026:
- Marked strictly as **`VerificationStatus.NOT_OFFICIALLY_VERIFIED`**.
- The reported ₹50,000 fee is **NOT hard-coded as authoritative** (`is_authoritative = False`); it is a configurable parameter defaulting to ₹50,000 with a requirement for statutory confirmation.
- The reported 20% test weight substitution requirement is **NOT hard-coded as authoritative**; it is configurable and marked as requiring regulatory confirmation.
- Flagged with **`requires_regulatory_confirmation = True`**.

### How the Backend Can Query the Knowledge Base:

```python
from app.regulatory import (
    KNOWLEDGE_BASE, 
    AccuracyClass, 
    InstrumentProfile, 
    RuleCategory, 
    LegalOrigin, 
    evaluate_gatc_routing
)

# 1. Retrieve Accuracy Class Specifications
class_iii_def = KNOWLEDGE_BASE.get_accuracy_class_definition(AccuracyClass.CLASS_III)
print(class_iii_def.display_name)
print("Initial MPE steps:", class_iii_def.mpe_thresholds_initial)

# 2. Evaluate Statutory GATC Routing
inst = InstrumentProfile(accuracy_class=AccuracyClass.CLASS_III, max_capacity=50.0)
decision = evaluate_gatc_routing(inst)
print(f"Eligible for GATC: {decision.eligible_for_gatc}")  # True
print(f"Target Authority: {decision.target_authority}")    # GATC

inst_class_ii = InstrumentProfile(accuracy_class=AccuracyClass.CLASS_II, max_capacity=6.0)
decision_ii = evaluate_gatc_routing(inst_class_ii)
print(f"Eligible for GATC: {decision_ii.eligible_for_gatc}")  # False
print(f"Target Authority: {decision_ii.target_authority}")    # STATE_LEGAL_METROLOGY_OFFICER

# 3. Retrieve Rules by Category
test_weight_rules = KNOWLEDGE_BASE.get_rules_by_category(RuleCategory.TEST_WEIGHTS)
for rule in test_weight_rules:
    print(f"[{rule.rule_id}] {rule.title} (Source: {rule.citation.source_document})")

# 4. Check Unverified Amendments
unverified = KNOWLEDGE_BASE.get_unverified_rules()
for rule in unverified:
    print(f"Unverified Rule: {rule.title} - Status: {rule.citation.verification_status.value}")

# 5. Query Test Weight Accuracy Requirements for an Instrument
test_wt_req = KNOWLEDGE_BASE.get_test_weight_requirement(inst)
print("Recommended weights:", test_wt_req["recommended_test_weight_classes"])
print("Error ratio limit:", test_wt_req["max_weight_error_ratio"])
```

---

## 8. Regulatory Instrument Classification Validator

The module `app.regulatory.classification_validator` provides strict metrological validation of instrument specifications before test execution or model approval.

### Features
- **Statutory Accuracy Class Validation:** Validates against Table 1 of Indian Legal Metrology Rules, 2011 and Table 3 of OIML R 76-1:2006 for Classes I, II, III, IIII.
- **Verification Scale Interval ($e$):** Validates class ranges and strict $1, 2, 5 \times 10^k$ step sizes.
- **Discrete Scale Counts ($n$):** Enforces integer verification interval counts $n = \text{Max}/e$, $n_{\min}$, $n_{\max}$, and checks against user-supplied $n$ without silent rounding.
- **Capacity Boundaries:** Verifies $\text{Min} < \text{Max}$, strictly positive numeric values, and class minimum capacity factors ($100e, 50e, 20e, 10e$).
- **Auxiliary Indicating Devices ($d$ vs $e$):** Permitted only for Class I and II ($d < e \le 10d$); strictly prohibited on Class III, Class IIII, and multi-interval instruments.
- **Multi-Interval & Multi-Range:** Validates partial ranges, ascending $e_i$ and $\text{Max}_i$, and flags required manual physical changeover verification.
- **Zero Silent Rounding:** Preserves exact statutory values and detects precision discrepancies.

### Validator Output Model
```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "manual_review_required": false,
  "manual_review_reasons": [],
  "instrument_summary": {
    "accuracy_class": "III",
    "accuracy_class_name": "Medium Accuracy (Class III)",
    "unit": "kg",
    "is_electronic": true,
    "is_multi_interval": false,
    "is_multi_range": false,
    "instrument_type": "STANDARD_NAWI",
    "total_errors": 0,
    "total_warnings": 0,
    "manual_review_required": false
  },
  "ranges_evaluated": [
    {
      "range": "main",
      "Max": "15.0 kg",
      "Min": "0.1 kg",
      "e": "0.005 kg",
      "d": "0.005 kg",
      "n": 3000.0,
      "e_in_grams": 5.0
    }
  ]
}
```

### Usage Example:
```python
from app.regulatory import validate_classification

spec = {
    "accuracy_class": "III",
    "Max": 15.0,
    "Min": 0.1,
    "e": 0.005,
    "d": 0.005,
    "unit": "kg",
    "is_electronic": True,
    "multi_range_status": False,
    "multi_interval_status": False,
}

result = validate_classification(spec)
if result.valid:
    print("Instrument specification meets all statutory and OIML requirements!")
    if result.manual_review_required:
        print("Manual verification checklist:", result.manual_review_reasons)
else:
    for err in result.errors:
        print(f"[{err.rule_id}] {err.field}: {err.message} (Source: {err.source})")
```

---

## 9. Maximum Permissible Error (MPE) Calculation Engine

The module `app.regulatory.mpe_engine` implements high-precision, statutory MPE determinations per OIML R 76-1:2006 Table 6 and the Indian Legal Metrology (General) Rules, 2011 Seventh Schedule (Part I, Table 2).

### Statutory Lookup Table & Exact Boundaries

Calculations use structured lookup tables (`MPE_STATUTORY_TABLE`) and exact `Decimal` arithmetic to prevent binary floating-point rounding artifacts and eliminate arbitrary tolerance fudges:

| Accuracy Class | Band 1 ($m \le \text{Threshold}_1$) | Band 2 ($\text{Threshold}_1 < m \le \text{Threshold}_2$) | Band 3 ($m > \text{Threshold}_2$) |
| :--- | :--- | :--- | :--- |
| **Class I** | $0 \le m \le 50,000 e \implies \mathbf{\pm 0.5 e}$ | $50,000 e < m \le 200,000 e \implies \mathbf{\pm 1.0 e}$ | $200,000 e < m \le 1,000,000 e \implies \mathbf{\pm 1.5 e}$ |
| **Class II** | $0 \le m \le 5,000 e \implies \mathbf{\pm 0.5 e}$ | $5,000 e < m \le 20,000 e \implies \mathbf{\pm 1.0 e}$ | $20,000 e < m \le 100,000 e \implies \mathbf{\pm 1.5 e}$ |
| **Class III** | $0 \le m \le 500 e \implies \mathbf{\pm 0.5 e}$ | $500 e < m \le 2,000 e \implies \mathbf{\pm 1.0 e}$ | $2,000 e < m \le 10,000 e \implies \mathbf{\pm 1.5 e}$ |
| **Class IIII** | $0 \le m \le 50 e \implies \mathbf{\pm 0.5 e}$ | $50 e < m \le 200 e \implies \mathbf{\pm 1.0 e}$ | $200 e < m \le 1,000 e \implies \mathbf{\pm 1.5 e}$ |

**Subsequent / In-Service Verification:**
$$\text{MPE}_{\text{subsequent}} = 2.0 \times \text{MPE}_{\text{initial}} \implies \mathbf{\pm 1.0 e}, \quad \mathbf{\pm 2.0 e}, \quad \mathbf{\pm 3.0 e}$$

### Exact Boundary Discrimination:
- **Class II at $5,000 e$:** Band 1 ($\pm 0.5 e$).
- **Class II at $5,000.001 e$:** Band 2 ($\pm 1.0 e$).
- **Class II at $20,000 e$:** Band 2 ($\pm 1.0 e$).
- **Class II at $20,000.001 e$:** Band 3 ($\pm 1.5 e$).

### Observed Error Evaluation:
When `observed_error` (e.g. indication error $E = I - L$) is provided:
$$\text{Pass} \iff |E| \le \text{MPE}_{\text{absolute}}$$
$$\text{Margin} = \text{MPE}_{\text{absolute}} - |E|$$
- $\text{Margin} \ge 0 \implies \text{Pass}$ (remaining statutory tolerance budget).
- $\text{Margin} < 0 \implies \text{Fail}$ (amount by which error exceeded legal tolerance).

### Usage Example:
```python
from app.regulatory import MPEEngine, VerificationType

# 1. Stateless MPE Calculation
res = MPEEngine.calculate(
    accuracy_class="III",
    load=10.0,             # 10 kg
    e=0.005,               # 5 g (0.005 kg) -> load_in_e = 2000e
    verification_type=VerificationType.INITIAL,
    observed_error=0.004,  # +4 g error
)

print(f"Load in e: {res.load_in_e}")        # 2000.0 e (Band 2)
print(f"MPE in e: {res.mpe_in_e}")          # 1.0 e
print(f"MPE absolute: {res.mpe_absolute}")  # 0.005 kg
print(f"Pass: {res.passed}")                # True (0.004 <= 0.005)
print(f"Margin: {res.margin} kg")           # 0.001 kg

# 2. Subsequent Verification (2 x MPE)
res_sub = MPEEngine.calculate(
    accuracy_class="III",
    load=10.0,
    e=0.005,
    verification_type=VerificationType.SUBSEQUENT,
    observed_error=0.008,
)
print(f"MPE in e: {res_sub.mpe_in_e}")         # 2.0 e
print(f"MPE absolute: {res_sub.mpe_absolute}") # 0.010 kg
print(f"Pass: {res_sub.passed}")               # True (0.008 <= 0.010)
```

---

## 10. Regulatory Test Applicability Engine

The module `app.regulatory.test_applicability_engine` determines which metrological and technical tests apply to an instrument based on its design characteristics, peripherals, and verification stage.

### Supported Tests (OIML R 76-1 Annex A & B / Indian Legal Metrology Rules):
- **`A.1` Administrative Examination:** Mandatory legal baseline for all verification and model approval jobs.
- **`A.2` Comparison of Construction with Documentation:** Mandatory for Type Evaluation / Model Approval.
- **`A.3` Initial Examination (Markings & Sealing):** Verification of legal markings (Max, Min, e, class) and sealing.
- **`A.4.2` Zero-Setting Accuracy:** Conditional on presence of zero-setting/zero-tracking devices (<= 0.25e).
- **`A.4.3` Tare Accuracy:** Conditional on presence of tare devices (tare setting accuracy and net weighing MPE).
- **`A.4.4` Weighing Performance:** Core mandatory test across increasing and decreasing loads.
- **`A.4.7` Eccentricity (Off-Center Loading):** Mandatory for all standard platforms/receptors.
- **`A.4.7.1` Rolling-Load Eccentricity:** Conditional on rolling-load capability (vehicle/rail weighbridges, roll conveyors).
- **`A.4.8` Discrimination:** Applies to digital indication (1.4d test) or analog indication (0.7d test).
- **`A.4.9` Sensitivity:** Applies strictly to non-self-indicating or semi-self-indicating instruments (e.g. beam scales).
- **`A.4.10` Repeatability:** Mandatory evaluation of repeated weighing consistency.
- **`A.4.11` Zero Return:** Electronic scales unloaded from Max (drift <= 0.5e).
- **`A.4.11.1` Creep (30-Minute Full-Load Drift):** Strictly Type Evaluation / Model Approval for electronic load cells.
- **`A.4.12` Stability of Equilibrium:** Conditional on printing or automated data storage (printout lockout during motion).
- **`A.5.1` Tilting Susceptibility:** Mobile scales or scales without level indicator (Class II, III, IIII); Class I is strictly exempt.
- **`A.5.2` Warm-Up Time:** Electronic instruments powered by mains or battery.
- **`A.5.3` Temperature Effect on No-Load & Span:** Type Evaluation environmental chamber testing (-10°C to +40°C).
- **`A.5.4` Voltage Variation:** Electronic instruments during Type Evaluation (85% to 110% of nominal).
- **`B.1` Electronic Disturbance Immunity:** EMC testing (ESD, RF fields, Bursts, Surges) during Type Evaluation.
- **`B.2` Damp Heat:** 48-hour climatic exposure (85% RH at 40°C) during Type Evaluation.
- **`B.3` Span Stability:** 28-day span drift tracking during Type Evaluation.
- **`A.6` Endurance (100,000 Cycles):** Type Evaluation for instruments with $\text{Max} \le 100\text{ kg}$.

### Applicability Engine Output Model:
```json
{
  "applicable_tests": [
    {
      "test_id": "A.4.4",
      "test_name": "Weighing Performance Test (Increasing & Decreasing Load)",
      "source": "OIML R 76-1:2006 Clause A.4.4 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part II Table 1",
      "applicable": true,
      "applicable_when": "Always applicable for all weighing instruments across all verification jobs.",
      "not_applicable_when": "Never.",
      "required_inputs": ["Max", "Min", "verification_scale_interval_e", "breakpoint_test_loads"],
      "manual_review": false,
      "priority": 6,
      "reason": "Core metrological test evaluating indication errors across load range against statutory MPE breakpoints."
    }
  ],
  "not_applicable_tests": [
    {
      "test_id": "A.4.9",
      "test_name": "Sensitivity Test for Non-Self-Indicating Instruments",
      "source": "OIML R 76-1:2006 Clause A.4.9 & Clause 3.7",
      "applicable": false,
      "reason": "Sensitivity test applies strictly to non-self-indicating instruments. This instrument is self-indicating."
    }
  ],
  "manual_review_tests": [
    {
      "test_id": "A.1",
      "test_name": "Administrative Examination",
      "manual_review": true
    }
  ],
  "warnings": [
    "Printing/Data-storage enabled: mandatory manual examination of printout lockout during motion (A.4.12)."
  ]
}
```

### Usage Example:
```python
from app.regulatory import evaluate_test_applicability

spec = {
    "accuracy_class": "III",
    "instrument_type": "SELF_INDICATING",
    "digital_analog": "DIGITAL",
    "electronic_status": True,
    "has_zero_setting": True,
    "has_tare": True,
    "load_receptor": "STANDARD_PLATTER",
    "rolling_load_capability": False,
    "printing_data_storage": True,
    "type_evaluation_status": False,
}

report = evaluate_test_applicability(spec)

print(f"Applicable Tests: {len(report['applicable_tests'])}")
print(f"Not Applicable Tests: {len(report['not_applicable_tests'])}")
print(f"Manual Review Tests: {len(report['manual_review_tests'])}")
print(f"Warnings: {report['warnings']}")
```

---

## 11. Regulatory Test Plan Generator

The **Regulatory Test Plan Generator** automates the end-to-end statutory planning pipeline that takes an instrument specification, validates its parameters, checks test applicability, calculates exact test loads and tolerances, and generates an executable `GeneratedTestPlan` consumable by **Person 4 (Test Engine)**.

### Pipeline Architecture:
```
Instrument Specification
         ↓
Classification Validation (app.regulatory.classification_validator)
         ↓
Regulatory Applicability (app.regulatory.test_applicability_engine)
         ↓
Test Load Calculation (MPE, Eccentricity, Repeatability, Discrimination, Creep, Temperature)
         ↓
Generated Test Plan (app.regulatory.test_plan_generator)
```

### Established Automated Calculations:

1. **Weighing Performance Test (Clause A.4.4):**
   - Calculates discrete test points starting at `0.0 (Zero)`, `Min`, statutory MPE transition breakpoints (e.g. `500e`, `2000e`), `50% Max`, and `Max`.
   - Generates progressive increasing and decreasing load schedules.
   - Computes exact lower/upper error limits matching applicable statutory MPE bands.
   - Enforces residual zero return tolerance $\le 0.5e$.

2. **Eccentricity / Off-Center Loading Test (Clause A.4.7):**
   - Automatically computes eccentric test load: $\text{Test Load} = (\text{Max} + \text{Additive Tare}) / 3$ (or $1/(N-1)$ for $N > 4$ points of support).
   - Generates test points across 5 platform locations: Center, Front-Left, Back-Left, Back-Right, and Front-Right.
   - Pre-calculates position-specific MPE tolerances based on the applied eccentric load.

3. **Repeatability Test (Clause A.4.10):**
   - Generates 2 test series: ~50% Max and 100% Max.
   - Configures exact observation cycles: 3 cycles for routine/in-service verification; 10 cycles for Model Approval (Pattern Evaluation).
   - Establishes statutory acceptance criteria: difference between maximum and minimum indication $\le |\text{MPE}|$.

4. **Digital Discrimination Test (Clause A.4.8):**
   - Generates test loads at Min, 50% Max, and Max.
   - Automatically calculates fractional extra test weight: $+1.4d$.
   - Acceptance criteria: addition of $1.4d$ must unequivocally increase indication by $+1d$.

5. **Creep Test (Clause A.4.11.1):**
   - 30-minute full-load drift evaluation under continuous Max load.
   - Observation schedule at $T = 0, 5, 15, \text{ and } 30\text{ minutes}$.
   - **Early Termination Rule:** If $|I_{30\text{min}} - I_{15\text{min}}| \le 0.2e$, the test concludes early as compliant per OIML R 76-1 Clause 3.9.4.1. Total 30-minute drift must be $\le 0.5e$.

6. **Temperature Effect Test (Clause A.5.3):**
   - Climatic environmental chamber cycle: $+20^\circ\text{C} \to +40^\circ\text{C} \to -10^\circ\text{C} \to +20^\circ\text{C}$.
   - Thermal soak time: 2 hours per step; max rate of temperature change: $\le 5^\circ\text{C}/\text{h}$.
   - Zero drift limit: $\le 1e \text{ per } 5^\circ\text{C}$.

7. **Tare Device Accuracy (Clause A.4.3):**
   - Net weighing performance evaluated under subtractive/preset tare load with net MPE bounds.

### Handling Ambiguous / Complex Cases:
- **Multi-Interval Scales:** Scales with discontinuous verification scale intervals ($e_1 < e_2 < \dots$) require physical on-site verification of range crossover thresholds on increasing load and tare deduction across ranges per OIML R 76-1 Clause 3.3. The generator safely flags `is_partial_plan = True`, sets `manual_review = True`, and attaches detailed statutory explanations in `partial_plan_reasons` and `manual_review_items`.
- **Validation Failures:** If classification validation detects non-compliance, a partial plan is emitted documenting the failure reasons without interrupting downstream review.

### Output Data Model (Person 4 Interface):
```json
{
  "test_plan_id": "PLAN-ABCD1234",
  "job_id": "JOB-2026-001",
  "instrument_id": "INST-NAWI-882",
  "regulatory_profile": "OIML R 76-1:2006 / Indian Legal Metrology (General) Rules, 2011",
  "accuracy_class": "III",
  "max_capacity": 15.0,
  "min_capacity": 0.1,
  "e": 0.005,
  "d": 0.005,
  "n": 3000,
  "unit": "kg",
  "verification_type": "INITIAL",
  "is_partial_plan": false,
  "partial_plan_reasons": [],
  "applicable_tests": ["A.1", "A.3", "A.4.2", "A.4.3", "A.4.4", "A.4.7", "A.4.8", "A.4.10", "A.4.12"],
  "not_applicable_tests": ["A.2", "A.4.9", "A.4.11.1", "A.5.1", "A.5.3", ...],
  "manual_review_items": [...],
  "calculated_test_loads": [0.0, 0.1, 2.5, 5.0, 7.5, 10.0, 15.0],
  "required_equipment": [
    "Class M1 (or M2) Reference Standard Weights (Maximum permissible error <= 1/3 instrument MPE)",
    "Calibrated auxiliary fractional weights (0.0005 kg for turning-point determination)",
    "Precision digital thermo-hygrometer for ambient temperature and relative humidity logging",
    "Stop watch / calibrated digital timer (+/- 0.1s resolution)"
  ],
  "required_environmental_conditions": {
    "prescribed_temperature_range": "+10°C to +30°C for routine verification; -10°C to +40°C for model approval",
    "max_temperature_rate_of_change": "5°C per hour (1°C/h for Class I)",
    "relative_humidity_range": "20% to 85% RH (non-condensing)",
    "barometric_pressure_range": "86 kPa to 106 kPa (ambient atmospheric)"
  },
  "mpe_reference": "OIML R 76-1:2006 Table 6 / Seventh Schedule Table 2 (INITIAL verification)",
  "tests": [
    {
      "test_id": "A.4.4",
      "test_name": "Weighing Performance Test",
      "applicable": true,
      "manual_review": false,
      "test_loads": [
        {
          "step_number": 1,
          "load": 0.0,
          "direction": "INCREASING",
          "load_in_e": 0.0,
          "mpe_in_e": 0.5,
          "mpe_absolute": 0.0025,
          "lower_limit_error": -0.0025,
          "upper_limit_error": 0.0025,
          "tolerance_rule": "0 <= m <= 500e -> MPE: +/-0.5e",
          "position": "CENTER"
        },
        ...
      ],
      "acceptance_criteria": "Indication error at each load point must not exceed the statutory MPE (+/- INITIAL MPE)...",
      "required_equipment": ["Class M1 standard weights"],
      "source": "OIML R 76-1:2006 Clause A.4.4 & Table 6",
      "priority": 6
    }
  ]
}
```

### Python API Usage:
```python
from app.regulatory import RegulatoryTestPlanGenerator, generate_regulatory_test_plan

spec = {
    "job_id": "JOB-2026-001",
    "instrument_id": "INST-NAWI-882",
    "accuracy_class": "III",
    "Max": 15.0,
    "Min": 0.1,
    "e": 0.005,
    "d": 0.005,
    "unit": "kg",
    "verification_type": "INITIAL",
    "electronic_status": True,
    "digital_analog": "DIGITAL",
    "zero_setting_device": True,
    "tare_device": True,
    "is_type_evaluation": False,
}

# Object output
plan = RegulatoryTestPlanGenerator.generate(spec)
print(f"Generated Plan ID: {plan.test_plan_id}")
print(f"Total Applicable Tests: {len(plan.applicable_tests)}")
print(f"Calculated Test Loads: {plan.calculated_test_loads}")

# Dict output for API / serialization
plan_dict = generate_regulatory_test_plan(spec)
```

---

## 12. Backend API Architecture & Endpoints

This section defines the external API service layer for **Person 1 (Team Lead)** to integrate the Regulatory Engine into the MetrIQ backend architecture without importing internal submodules directly.

### Integration for Person 1:
```python
# Clean single import for Person 1:
from app.regulatory import (
    validate_instrument_api,
    calculate_mpe_api,
    determine_applicable_tests_api,
    generate_test_plan_api,
    get_regulatory_profile_api,
    get_rule_or_source_api,
    RegulatoryAPI,
)

# Or import through the master router (app/api/router.py):
from app.api.router import RegulatoryAPI
```

### Standard Response Envelope:
All endpoints return consistent JSON envelopes:
```json
// Success Response:
{
  "success": true,
  "status_code": 200,
  "data": { ... },
  "timestamp": "2026-09-17T01:05:00.000000+00:00"
}

// Error Response:
{
  "success": false,
  "status_code": 400,
  "error": {
    "code": "ERROR_IDENTIFIER",
    "message": "Human-readable explanation of error",
    "details": [...]
  },
  "timestamp": "2026-09-17T01:05:00.000000+00:00"
}
```

---

### Endpoint 1: Validate Instrument
`POST /regulatory/validate-instrument`

Validates instrument metrological parameters against statutory OIML R 76-1:2006 Table 3 and Indian Legal Metrology (General) Rules, 2011 Seventh Schedule Table 1.

#### Request Schema:
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `accuracy_class` | string | **Yes** | Allowed: `"I"`, `"II"`, `"III"`, `"IIII"` |
| `Max` | float | **Yes** | Maximum weighing capacity |
| `Min` | float | No | Minimum capacity (defaults to statutory $20e$ or $10e$) |
| `e` | float | **Yes** | Verification scale interval ($1, 2, 5 \times 10^k$) |
| `d` | float | No | Actual scale interval ($d \le e$) |
| `calculated_n` | int / float | No | Number of verification intervals ($n = \text{Max} / e$) |
| `unit` | string | No | Legal unit: `"mg"`, `"g"`, `"kg"`, `"t"`, `"ct"` (default `"kg"`) |
| `electronic_status`| bool | No | True for electronic, False for mechanical |
| `multi_range_status` | bool | No | Multi-range architecture flag |
| `multi_interval_status` | bool | No | Multi-interval architecture flag |

#### Example Request:
```json
{
  "accuracy_class": "III",
  "Max": 15.0,
  "Min": 0.1,
  "e": 0.005,
  "d": 0.005,
  "calculated_n": 3000,
  "unit": "kg"
}
```

#### Example Response (200 OK):
```json
{
  "success": true,
  "status_code": 200,
  "data": {
    "valid": true,
    "accuracy_class": "III",
    "max_capacity": 15.0,
    "min_capacity": 0.1,
    "e": 0.005,
    "d": 0.005,
    "n": 3000,
    "unit": "kg",
    "errors": [],
    "warnings": [],
    "manual_review_required": false,
    "manual_review_reasons": []
  },
  "timestamp": "2026-09-17T01:05:00.000000+00:00"
}
```

#### Error Cases:
- **400 Bad Request (`MISSING_REQUIRED_FIELD`):** Missing `accuracy_class`, `Max`, or `e`.
- **422 Unprocessable Entity (`INVALID_FIELD_FORMAT`):** Non-numeric characters for `Max` or `e`.
- **200 Evaluation Failure (`data.valid = false`):** Exceeds statutory limits (e.g. $n > 10,000$ for Class III or $Min > Max$). The errors array contains detailed `rule_id`, `actual_value`, and `expected_condition`.

---

### Endpoint 2: Calculate MPE
`POST /regulatory/mpe`

Calculates statutory Maximum Permissible Error (MPE) for any test load based on accuracy class and verification scale interval $e$. Supports observed error evaluation and subsequent verification ($2 \times \text{Initial}$).

#### Request Schema:
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `accuracy_class` | string | **Yes** | `"I"`, `"II"`, `"III"`, or `"IIII"` |
| `load` | float | **Yes** | Applied test load |
| `e` | float | **Yes** | Verification scale interval ($e > 0$) |
| `verification_type`| string | No | `"INITIAL"` (default) or `"SUBSEQUENT"` / `"IN_SERVICE"` |
| `observed_error` | float | No | Observed indication error $(I - L)$ to evaluate |
| `unit` | string | No | Mass unit (default `"kg"`) |

#### Example Request:
```json
{
  "accuracy_class": "III",
  "load": 2.5,
  "e": 0.005,
  "verification_type": "INITIAL",
  "observed_error": 0.002,
  "unit": "kg"
}
```

#### Example Response (200 OK):
```json
{
  "success": true,
  "status_code": 200,
  "data": {
    "accuracy_class": "III",
    "load": 2.5,
    "unit": "kg",
    "e": 0.005,
    "verification_type": "INITIAL",
    "load_in_e": 500.0,
    "mpe_in_e": 0.5,
    "mpe_absolute": 0.0025,
    "tolerance_band": "0 <= m <= 500 e",
    "lower_limit_error": -0.0025,
    "upper_limit_error": 0.0025,
    "applicable_rule": "0 <= m <= 500e -> MPE: +/-0.5e",
    "source": "OIML R 76-1:2006 Table 6 / Seventh Schedule Table 2",
    "observed_error": 0.002,
    "is_pass": true,
    "margin": 0.0005
  },
  "timestamp": "2026-09-17T01:05:00.000000+00:00"
}
```

#### Error Cases:
- **400 Bad Request (`MISSING_PARAMETER`):** Missing `accuracy_class`, `load`, or `e`.
- **422 Unprocessable Entity (`INVALID_SCALE_INTERVAL`):** $e \le 0$.
- **422 Unprocessable Entity (`MPE_CALCULATION_ERROR`):** Invalid accuracy class string.

---

### Endpoint 3: Determine Applicable Tests
`POST /regulatory/applicable-tests`

Determines which of the 22 statutory metrological tests apply to an instrument based on its physical and metrological characteristics.

#### Request Schema:
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `accuracy_class` | string | No | Class (`"I"`, `"II"`, `"III"`, `"IIII"`) |
| `instrument_type` | string | No | `"SELF_INDICATING"` or `"NON_SELF_INDICATING"` |
| `digital_analog` | string | No | `"DIGITAL"`, `"ANALOG"`, or `"BOTH"` |
| `electronic_status`| bool | No | True for electronic, False for mechanical |
| `zero_setting_device`| bool | No | Presence of zero-setting device |
| `tare_device` | bool | No | Presence of tare mechanism |
| `load_receptor` | string | No | `"STANDARD_PLATTER"`, `"ROLLING_LOAD"`, `"WEIGHBRIDGE"` |
| `printing_data_storage`| bool | No | Data printing or storage facility |
| `is_type_evaluation` | bool | No | True for Model Approval, False for verification |

#### Example Request:
```json
{
  "accuracy_class": "III",
  "instrument_type": "SELF_INDICATING",
  "digital_analog": "DIGITAL",
  "electronic_status": true,
  "zero_setting_device": true,
  "tare_device": true,
  "load_receptor": "STANDARD_PLATTER",
  "printing_data_storage": true,
  "is_type_evaluation": false
}
```

#### Example Response (200 OK):
```json
{
  "success": true,
  "status_code": 200,
  "data": {
    "total_tests_evaluated": 22,
    "applicable_count": 9,
    "not_applicable_count": 13,
    "manual_review_count": 4,
    "applicable_tests": [
      {
        "test_id": "A.1",
        "test_name": "Administrative Examination",
        "source": "OIML R 76-1:2006 Clause A.1",
        "applicable": true,
        "manual_review": true,
        "priority": 1
      },
      {
        "test_id": "A.4.4",
        "test_name": "Weighing Performance Test",
        "source": "OIML R 76-1:2006 Clause A.4.4",
        "applicable": true,
        "manual_review": false,
        "priority": 6
      }
    ],
    "not_applicable_tests": [...],
    "manual_review_tests": [...],
    "warnings": [
      "Printing/Data-storage enabled: mandatory manual examination of printout lockout during motion (A.4.12)."
    ]
  },
  "timestamp": "2026-09-17T01:05:00.000000+00:00"
}
```

#### Error Cases:
- **400 Bad Request (`INVALID_REQUEST_PAYLOAD`):** Non-dictionary payload.

---

### Endpoint 4: Generate Test Plan
`POST /regulatory/test-plan`

Executes the complete 5-stage regulatory pipeline and generates a fully sequenced test plan consumable by **Person 4 (Test Engine)**.

#### Request Schema:
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `accuracy_class` | string | **Yes** | Accuracy class (`"I"`, `"II"`, `"III"`, `"IIII"`) |
| `Max` | float | **Yes** | Maximum weighing capacity |
| `Min` | float | No | Minimum capacity |
| `e` | float | **Yes** | Verification scale interval |
| `d` | float | No | Actual scale interval |
| `unit` | string | No | Mass unit |
| `job_id` | string | No | External Job identifier |
| `instrument_id` | string | No | External Instrument / Serial identifier |
| `verification_type`| string | No | `"INITIAL"` or `"SUBSEQUENT"` |
| `is_type_evaluation`| bool | No | Set true for Model Approval (10 repeatability runs, creep, etc.) |

#### Example Request:
```json
{
  "job_id": "JOB-2026-001",
  "instrument_id": "INST-NAWI-882",
  "accuracy_class": "III",
  "Max": 15.0,
  "Min": 0.1,
  "e": 0.005,
  "d": 0.005,
  "unit": "kg",
  "verification_type": "INITIAL"
}
```

#### Example Response (200 OK):
```json
{
  "success": true,
  "status_code": 200,
  "data": {
    "test_plan_id": "PLAN-7E6D8A21",
    "job_id": "JOB-2026-001",
    "instrument_id": "INST-NAWI-882",
    "regulatory_profile": "OIML R 76-1:2006 / Indian Legal Metrology (General) Rules, 2011",
    "accuracy_class": "III",
    "max_capacity": 15.0,
    "min_capacity": 0.1,
    "e": 0.005,
    "d": 0.005,
    "n": 3000,
    "unit": "kg",
    "verification_type": "INITIAL",
    "is_partial_plan": false,
    "partial_plan_reasons": [],
    "applicable_tests": ["A.1", "A.3", "A.4.2", "A.4.3", "A.4.4", "A.4.7", "A.4.8", "A.4.10", "A.4.12"],
    "not_applicable_tests": ["A.2", "A.4.9", "A.4.11.1", "A.5.1", "A.5.3"],
    "calculated_test_loads": [0.0, 0.1, 2.5, 5.0, 7.5, 10.0, 15.0],
    "required_equipment": [
      "Class M1 (or M2) Reference Standard Weights (Maximum permissible error <= 1/3 instrument MPE)",
      "Calibrated auxiliary fractional weights (0.0005 kg for turning-point determination)",
      "Precision digital thermo-hygrometer for ambient temperature and relative humidity logging",
      "Stop watch / calibrated digital timer (+/- 0.1s resolution)"
    ],
    "required_environmental_conditions": {
      "prescribed_temperature_range": "+10°C to +30°C for routine verification; -10°C to +40°C for model approval",
      "max_temperature_rate_of_change": "5°C per hour (1°C/h for Class I)",
      "relative_humidity_range": "20% to 85% RH (non-condensing)",
      "barometric_pressure_range": "86 kPa to 106 kPa (ambient atmospheric)"
    },
    "mpe_reference": "OIML R 76-1:2006 Table 6 / Seventh Schedule Table 2 (INITIAL verification)",
    "tests": [...]
  },
  "timestamp": "2026-09-17T01:05:00.000000+00:00"
}
```

#### Error Cases:
- **400 Bad Request (`MISSING_PLAN_PARAMETERS`):** Missing `accuracy_class`, `Max`, or `e`.
- **422 Unprocessable Entity (`INVALID_PARAMETER_FORMAT`):** Non-numeric capacity or scale interval.

---

### Endpoint 5: Retrieve Regulatory Profile/Version
`GET /regulatory/profile`

Returns metadata regarding active statutory frameworks, legal jurisdictions, supported accuracy classes, and distinction rules.

#### Example Request:
```http
GET /regulatory/profile HTTP/1.1
Host: api.metriq.internal
```

#### Example Response (200 OK):
```json
{
  "success": true,
  "status_code": 200,
  "data": {
    "engine_name": "MetrIQ Regulatory Compliance Engine",
    "version": "1.0.0",
    "active_profile": "OIML R 76-1:2006 / Indian Legal Metrology (General) Rules, 2011",
    "supported_accuracy_classes": ["I", "II", "III", "IIII"],
    "supported_verification_types": ["INITIAL", "SUBSEQUENT", "IN_SERVICE"],
    "primary_indian_sources": [
      {
        "code": "LM_ACT_2009",
        "title": "Legal Metrology Act, 2009 (Act 1 of 2010)",
        "jurisdiction": "INDIA",
        "status": "STATUTORY_MANDATORY"
      },
      {
        "code": "IN_LM_2011",
        "title": "Legal Metrology (General) Rules, 2011",
        "jurisdiction": "INDIA",
        "status": "STATUTORY_MANDATORY"
      },
      {
        "code": "IN_AMR_2011",
        "title": "Legal Metrology (Approval of Models) Rules, 2011",
        "jurisdiction": "INDIA",
        "status": "STATUTORY_MANDATORY"
      },
      {
        "code": "IN_GATC_2013",
        "title": "Legal Metrology (Government Approved Test Centre) Rules, 2013",
        "jurisdiction": "INDIA",
        "status": "STATUTORY_MANDATORY"
      }
    ],
    "technical_sources": [
      {
        "code": "OIML_R76_2006",
        "title": "OIML R 76-1:2006 Non-automatic weighing instruments",
        "jurisdiction": "INTERNATIONAL",
        "status": "TECHNICAL_STANDARD"
      },
      {
        "code": "OIML_R76_2_2007",
        "title": "OIML R 76-2:2007 Non-automatic weighing instruments - Pattern evaluation report",
        "jurisdiction": "INTERNATIONAL",
        "status": "TECHNICAL_REPORT_FORMAT"
      }
    ],
    "statutory_distinctions": {
      "indian_legal": "Statutory requirements carrying legal force under Legal Metrology Act, 2009 and Central Rules.",
      "oiml_technical": "International technical standards and test protocols.",
      "report_formats": "Default evaluation templates (e.g. OIML R 76-2, non-statutory in India).",
      "configurable_rules": "Parameters that testing laboratories or State controllers can configure.",
      "manual_review": "Procedures requiring physical visual inspection or inspector discretion."
    },
    "gatc_routing_supported": true,
    "subsequent_mpe_multiplier": 2.0
  },
  "timestamp": "2026-09-17T01:05:00.000000+00:00"
}
```

---

### Endpoint 6: Retrieve Rule / Source Information
`GET /regulatory/rules/{rule_id}`

Retrieves statutory citations, formulas, test requirements, or standard source documentation for any rule, test ID, standard ID, or accuracy class identifier.

#### Path Parameter:
- `rule_id`: e.g. `A.4.4`, `A.4.7`, `OIML_R76_2006`, `IN_LM_2011`, `CLASS_III`, `RULE_GATC_CLASS_RESTRICTION`.

#### Example Request:
```http
GET /regulatory/rules/A.4.4 HTTP/1.1
Host: api.metriq.internal
```

#### Example Response (200 OK):
```json
{
  "success": true,
  "status_code": 200,
  "data": {
    "rule_id": "A.4.4",
    "rule_name": "Weighing Performance Test (Increasing & Decreasing Load)",
    "source": "OIML R 76-1:2006 Clause A.4.4 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part II Clause 2",
    "category": "STATUTORY_TEST_PROCEDURE",
    "applicable_when": "Always applicable across all accuracy classes and verification jobs.",
    "not_applicable_when": "Never.",
    "required_inputs": ["min_capacity", "mpe_breakpoints", "50_percent_max", "max_capacity"],
    "manual_review": false,
    "priority": 6,
    "type": "STATUTORY_TEST_DEFINITION"
  },
  "timestamp": "2026-09-17T01:05:00.000000+00:00"
}
```

#### Error Cases:
- **404 Not Found (`RULE_NOT_FOUND`):** Unknown identifier. Returns suggested IDs to assist client integration.
```json
{
  "success": false,
  "status_code": 404,
  "error": {
    "code": "RULE_NOT_FOUND",
    "message": "Regulatory rule, test, or standard 'UNKNOWN_RULE' was not found in knowledge base or registry.",
    "details": {
      "requested_id": "UNKNOWN_RULE",
      "suggested_ids": ["A.1", "A.4.4", "A.4.7", "A.4.8", "OIML_R76_2006", "IN_LM_2011"]
    }
  },
  "timestamp": "2026-09-17T01:05:00.000000+00:00"
}
```



