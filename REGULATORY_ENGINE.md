# MetrIQ Regulatory Engine Technical Reference & Specification
**Project:** MetrIQ (METRA SIH26035) — Automated NAWI Compliance & Test Report Generation System  
**Author / Role:** Person 2 — Regulatory Engineer  
**Branch:** `feature/regulatory`  
**Target Consumer:** Person 1 (Team Lead & Integration), Person 4 (Test Execution Engine), Person 3 (Frontend/Mobile)  
**Standard Status:** Production-Ready, Fully Tested (209/209 Tests Passing)

---

## Table of Contents
1. [Architecture](#1-architecture)
2. [Rule Catalogue](#2-rule-catalogue)
3. [Maximum Permissible Error (MPE) Logic](#3-maximum-permissible-error-mpe-logic)
4. [Instrument Classification Logic](#4-instrument-classification-logic)
5. [Test Applicability Engine](#5-test-applicability-engine)
6. [Regulatory Test Plan Generator](#6-regulatory-test-plan-generator)
7. [API Endpoints & Calling Conventions](#7-api-endpoints--calling-conventions)
8. [Statutory & Regulatory Sources](#8-statutory--regulatory-sources)
9. [Configurable Rules & Lifecycle Versioning](#9-configurable-rules--lifecycle-versioning)
10. [Manual-Review Scenarios & Safeguards](#10-manual-review-scenarios--safeguards)
11. [Known Limitations](#11-known-limitations)
12. [Integration Instructions for Person 1](#12-integration-instructions-for-person-1)

---

## 1. Architecture

The MetrIQ Regulatory Engine provides a deterministic, data-driven, mathematically exact compliance engine for Non-Automatic Weighing Instruments (NAWI). It bridges international technical harmonisation (**OIML R 76-1:2006**) with Indian statutory law (**Legal Metrology Act, 2009** and subordinate rules).

```
                             [ INCOMING REQUEST ]
                                      │
                   ┌──────────────────┴──────────────────┐
                   ▼                                     ▼
        POST /regulatory/...                     Direct Python Call
       (FastAPI Router / Facade)             (app.regulatory Modules)
                   │                                     │
                   └──────────────────┬──────────────────┘
                                      ▼
                        [ 0. REGULATORY PROFILE ]
                      (app.regulatory.profile)
                      - Profile Registry & Status
                      - Dynamic Overrides (MPE, Fees, GATC)
                      - Audit Trail Generation
                                      │
                                      ▼
                   [ 1. CLASSIFICATION VALIDATION ]
                (app.regulatory.classification_validator)
                 - e, d, Max, Min, n = Max / e
                 - Strict class boundary evaluation
                 - Non-rounding Decimal arithmetic
                                      │
                                      ▼
                   [ 2. TEST APPLICABILITY ENGINE ]
                (app.regulatory.test_applicability_engine)
                 - Evaluates 22 statutory procedures
                 - Eliminates non-applicable tests
                 - Isolates mechanical vs electronic
                                      │
                                      ▼
                        [ 3. MPE CALCULATION ]
                     (app.regulatory.mpe_engine)
                 - Exact 3-band boundary transitions
                 - Dual-unit (e and kg/g) calculation
                 - Initial vs Subsequent (2x) limits
                                      │
                                      ▼
                    [ 4. TEST LOAD CALCULATION ]
                 - Weighing breakpoints (0, Min, 500e, 2000e, Max)
                 - Eccentricity (Max/3 per receptor type)
                 - Repeatability (0.5 Max & Max / 0.8 Max)
                 - Discrimination (1.4d digital / 0.7d analog)
                 - Tare accuracy & Creep (30-min drift)
                                      │
                                      ▼
                 [ 5. GENERATED TEST PLAN / AUDIT ]
                  (Consumable by Person 4 Engine)
```

### Module Structure
All code resides under `backend/app/regulatory/`:
* `models.py`: Core metrological domain models (`AccuracyClass`, `JobType`, `MassUnit`, `VerificationType`, etc.).
* `knowledge/`: Structured statutory database (OIML R 76-1, Indian Legal Metrology 2011/2013, GATC, fees).
* `classification_validator.py`: Strict non-rounding classification validator (`e`, `d`, `Max`, `Min`, `n`).
* `mpe_engine.py`: High-precision Decimal MPE lookup and calculation engine with boundary transition guarantees.
* `test_applicability_engine.py`: 22-procedure statutory applicability evaluator.
* `test_plan_generator.py`: Complete 5-stage automated test plan generator.
* `profile.py`: Data-driven regulatory profile versioning, lifecycle status, fee schedules, GATC, and audit traces.
* `api.py` & `router.py`: REST API schemas, FastAPI router endpoints, and standalone fallback dispatch.
* `__init__.py`: Clean public API re-export for external team members.

---

## 2. Rule Catalogue

Every regulatory decision in the engine maps to a unique, traceable `rule_id`.

| Rule ID | Module | Statutory / Technical Basis | Rule Description | Severity |
| :--- | :--- | :--- | :--- | :--- |
| `RULE_ACCURACY_CLASS_VALID` | Classification | OIML R 76 Table 3 / IN LM Table 1 | Verifies accuracy class is I, II, III, or IIII | ERROR |
| `RULE_SCALE_INTERVAL_FORM` | Classification | OIML R 76 Clause 3.2 / IN LM Sch VII | Verifies verification scale interval $e = 1, 2, 5 \times 10^k$ | ERROR |
| `RULE_CLASS_I_E_MIN` | Classification | OIML R 76 Table 3 | For Class I, $e \ge 0.001\text{ g}$ (1 mg) | ERROR |
| `RULE_CLASS_I_N_MIN` | Classification | OIML R 76 Table 3 | For Class I, $n \ge 50,000$ | ERROR |
| `RULE_CLASS_I_MIN_CAPACITY` | Classification | OIML R 76 Table 3 | For Class I, $Min \ge 100e$ | ERROR |
| `RULE_CLASS_II_E_RANGE` | Classification | OIML R 76 Table 3 | For Class II, $0.001\text{ g} \le e \le 0.05\text{ g}$ or $e \ge 0.1\text{ g}$ | ERROR |
| `RULE_CLASS_II_N_BOUNDS` | Classification | OIML R 76 Table 3 | For Class II, $100 \le n \le 100,000$ (Band A: $\ge 100$, Band B: $\ge 5,000$) | ERROR |
| `RULE_CLASS_II_MIN_CAPACITY` | Classification | OIML R 76 Table 3 | For Class II, $Min \ge 20e$ (Band A) or $Min \ge 50e$ (Band B) | ERROR |
| `RULE_CLASS_III_N_BOUNDS` | Classification | OIML R 76 Table 3 | For Class III, $500 \le n \le 10,000$ | ERROR |
| `RULE_CLASS_III_MIN_CAPACITY` | Classification | OIML R 76 Table 3 | For Class III, $Min \ge 20e$ | ERROR |
| `RULE_CLASS_IIII_N_BOUNDS` | Classification | OIML R 76 Table 3 | For Class IIII, $100 \le n \le 1,000$ | ERROR |
| `RULE_CLASS_IIII_MIN_CAPACITY` | Classification | OIML R 76 Table 3 | For Class IIII, $Min \ge 10e$ | ERROR |
| `RULE_D_EXCEEDS_E` | Classification | OIML R 76 Clause 3.4.1 | Actual scale interval $d$ cannot exceed verification interval $e$ | ERROR |
| `RULE_MIN_EXCEEDS_MAX` | Classification | OIML R 76 Clause 3.4.3 | Minimum capacity $Min$ cannot exceed maximum capacity $Max$ | ERROR |
| `RULE_MAX_NON_POSITIVE` | Classification | OIML R 76 Clause 3.1 | Maximum capacity $Max$ must be strictly positive ($> 0$) | ERROR |
| `RULE_N_CALCULATION_MISMATCH`| Classification | OIML R 76 Table 3 | User provided $n$ must exactly equal $\text{round}(Max / e)$ | ERROR |
| `RULE_N_NON_INTEGER` | Classification | OIML R 76 Clause 3.2 | $Max / e$ must resolve to a clean integer without fractional steps | ERROR |
| `RULE_MULTI_INTERVAL_E_ORDER` | Classification | OIML R 76 Clause 3.3 | Scale intervals must strictly increase across ranges ($e_1 < e_2 < e_3$) | ERROR |
| `RULE_MULTI_RANGE_MIN_RANGES` | Classification | OIML R 76 Clause 3.2.2 | Multi-range instruments must declare at least 2 independent ranges | ERROR |
| `RULE_MPE_BAND_LOOKUP` | MPE Engine | OIML R 76 Table 6 / IN LM Table 2 | Allocates load $m$ to Band 1 ($0.5e$), Band 2 ($1.0e$), or Band 3 ($1.5e$) | PASS/FAIL |
| `RULE_MPE_SUBSEQUENT_DOUBLING`| MPE Engine | IN LM Rules 2011 Sch VII Clause 4 | Multiplies initial verification MPE by exactly $2.0$ for subsequent checks | PASS/FAIL |
| `RULE_GATC_ELIGIBILITY` | Profile / Routing | GATC Rules 2013 Rule 4(1) | Permits Class II, III, IIII up to $5000\text{ kg}$; excludes Class I | ROUTING |
| `RULE_TEST_WEIGHT_SUBSTITUTION`| Test Plan | OIML R 76 Clause 3.7.3 / Profile | Evaluates substitution limit ($50\%$ standard vs $20\%$ reported draft) | AUDIT |

---

## 3. Maximum Permissible Error (MPE) Logic

### 3.1 Mathematical Formulation
MPE calculation is handled strictly in `decimal.Decimal` to avoid binary floating-point drift (e.g. `500 * 0.005 = 2.5000000000000004` which would prematurely trigger Band 2).

The statutory bands per OIML R 76-1:2006 Table 6 and Indian Legal Metrology (General) Rules, 2011 (Seventh Schedule, Part I, Table 2) are:

$$\text{MPE}_{\text{initial}}(m) = \begin{cases} \pm 0.5e & \text{if } 0 \le m \le B_1 \\ \pm 1.0e & \text{if } B_1 < m \le B_2 \\ \pm 1.5e & \text{if } B_2 < m \le B_3 \end{cases}$$

$$\text{MPE}_{\text{subsequent}}(m) = 2.0 \times \text{MPE}_{\text{initial}}(m)$$

### 3.2 Threshold Breakpoints ($m$ in $e$ units)
* **Class I:** $0 \le m \le 50,000e \to \pm 0.5e$; $50,000e < m \le 200,000e \to \pm 1.0e$; $200,000e < m \le 1,000,000e \to \pm 1.5e$.
* **Class II:** $0 \le m \le 5,000e \to \pm 0.5e$; $5,000e < m \le 20,000e \to \pm 1.0e$; $20,000e < m \le 100,000e \to \pm 1.5e$.
* **Class III:** $0 \le m \le 500e \to \pm 0.5e$; $500e < m \le 2,000e \to \pm 1.0e$; $2,000e < m \le 10,000e \to \pm 1.5e$.
* **Class IIII:** $0 \le m \le 50e \to \pm 0.5e$; $50e < m \le 200e \to \pm 1.0e$; $200e < m \le 1,000e \to \pm 1.5e$.

### 3.3 Boundary Evaluation Guarantees
* Exactly at $500e$: Evaluates as **Band 1** ($\pm 0.5e$).
* At $500.001e$: Evaluates strictly as **Band 2** ($\pm 1.0e$).
* Absolute MPE in instrument units is computed as:
  $$\text{MPE}_{\text{absolute}} = \text{MPE}_{\text{in\_e}} \times e$$
* Observed error assessment:
  $$\text{passed} = |\text{observed\_error}| \le \text{MPE}_{\text{absolute}}$$
  $$\text{margin} = \text{MPE}_{\text{absolute}} - |\text{observed\_error}|$$

---

## 4. Instrument Classification Logic

### 4.1 Verification Sequence
Validation executes through `RegulatoryClassificationValidator.validate(spec)`:
1. **Class Extraction & Normalisation:** Maps Roman/Arabic inputs (`"III"`, `"3"`, `"CLASS_III"`) to `AccuracyClass`.
2. **Numeric Safety:** All numeric fields (`Max`, `Min`, `e`, `d`, `n`) are strictly validated against non-positive and non-numeric values. No silent rounding is performed.
3. **Step Sequence:** Verifies that $e = 1 \times 10^k$, $2 \times 10^k$, or $5 \times 10^k$ (rejecting $3\text{ g}$, $7\text{ g}$, etc.).
4. **Resolution Check ($n$):** Computes $n = \text{round}(Max / e)$ using Decimal arithmetic. Fails if $Max / e$ is non-integer or deviates from user-supplied $n$.
5. **Class Boundary Limits:**
   - Validates $n_{\min} \le n \le n_{\max}$.
   - Validates $e_{\min} \le e \le e_{\max}$.
   - Validates $Min \ge \text{statutory minimum}$ ($100e$ for Class I; $20e$ or $50e$ for Class II; $20e$ for Class III; $10e$ for Class IIII).
6. **Multi-Range & Multi-Interval Handling:**
   - Multi-range scales validate each independent range $i$.
   - Multi-interval scales validate interval progression ($e_1 < e_2$) and automatically flag manual review for on-site automatic changeover checks.

---

## 5. Test Applicability Engine

The `RegulatoryTestApplicabilityEngine` evaluates 22 statutory procedures and classifies each as:
* `applicable: True/False`
* `manual_review: True/False`
* `priority: int` (1 to 22)
* `reason`: Clear statutory justification citing OIML R 76 / Indian Rules 2011.

### Procedure Overview
1. **A.1 Administrative Examination:** Always applicable; legal markings and model approval verification.
2. **A.2 Construction & Documentation Comparison:** Applicable during initial verification and type evaluation.
3. **A.3 Initial Visual & Metrological Examination:** Always applicable.
4. **A.4.2 Zero-Setting Accuracy:** Applicable only when `has_zero_setting=True` ($\pm 0.25e$ limit).
5. **A.4.3 Tare Accuracy & Net Weighing:** Applicable only when `has_tare=True`.
6. **A.4.4 Weighing Performance:** Always applicable (increasing and decreasing load at breakpoints).
7. **A.4.7 Eccentricity Test:** Applicable to platforms, pans, and tanks. Excluded for single-point hanging scales.
8. **A.4.7.1 Rolling Load Eccentricity:** Applicable conditionally when `has_rolling_load=True` (rail/road weighbridges).
9. **A.4.8 Discrimination Test:**
   - Digital indication: $1.4d$ test load.
   - Analog indication: $0.7d$ pointer displacement.
   - Excluded for non-self-indicating instruments.
10. **A.4.9 Sensitivity Test:** Applicable strictly to non-self-indicating instruments (beam/counter scales). Excluded for digital/self-indicating instruments.
11. **A.4.10 Repeatability Test:** Always applicable ($3$ or $10$ repetitions at $0.5 Max$ and $Max$).
12. **A.4.11 Zero Return Test:** Applicable to electronic instruments during type evaluation and Class I/II verification. Excluded for mechanical scales.
13. **A.4.11.1 Creep Test (30-min drift):** Applicable to electronic scales during type evaluation / major load cell repair. Excluded for routine field checks and mechanical scales.
14. **A.4.12 Stability of Equilibrium:** Applicable to printing, tare setting, or zero-setting devices.
15. **A.5.1 Static Tilt Test:** Applicable to portable/mobile scales or instruments without level indicators.
16. **A.5.2 Warm-Up Time Test:** Applicable strictly to electronic mains/battery instruments. Excluded for mechanical instruments.
17. **A.5.3 Temperature Effect on Span:** Applicable during type evaluation in climatic chambers ($-10^\circ\text{C}$ to $+40^\circ\text{C}$).
18. **A.5.4 Voltage Variation Test:** Applicable to electronic instruments during type evaluation ($85\%$ to $110\%$ nominal voltage).
19. **B.1 Disturbance Immunity (ESD, Burst, Surge, RF):** Type evaluation EMC laboratory tests.
20. **B.2 Damp Heat Test:** Type evaluation 48-hour climatic chamber exposure ($85\%$ RH at $40^\circ\text{C}$).
21. **B.3 Span Stability Test:** Type evaluation 28-day drift evaluation.
22. **A.6 Endurance Test:** 100,000-cycle test for instruments with $Max \le 100\text{ kg}$ during type evaluation.

---

## 6. Regulatory Test Plan Generator

The `RegulatoryTestPlanGenerator` coordinates the entire pipeline to generate an executable test plan.

### 6.1 Automatic Load Point Derivations
* **Weighing Performance (A.4.4):**
  Generates load points in both increasing and decreasing order:
  $$\{0, Min, 500e, 2000e, Max\}$$
  Includes MPE breakpoint transition checks ($499e, 500e, 501e$) where appropriate.
* **Eccentricity (A.4.7):**
  - Standard platter / 4 support points: Test load = $(Max + \text{additive tare}) / 3$. Applied to center and 4 quadrants.
  - Multi-support tank / hopper (e.g. 3 or 4 points): Test load = $(Max + \text{additive tare}) / (N - 1)$.
  - Rolling load: Prescribes standard test vehicle axle loads.
* **Repeatability (A.4.10):**
  - Point 1: $0.5 \times Max$ (or $0.5 \times \text{range max}$).
  - Point 2: $Max$ (or $0.8 \times Max$ for heavy weighbridges per practical guidelines).
  - Executed for 3 series of 3 weighings (or 10 weighings during type evaluation).
* **Discrimination (A.4.8):**
  Calculates auxiliary turning-point load: $1.4d$ for digital; $0.7d$ for analog.
* **Tare Accuracy (A.4.3):**
  Prescribes tare load at $1/3 Max$ and evaluates net load points $\{Min, 500e, Max - Tare\}$.
* **Creep Test (A.4.11.1):**
  Calculates static readings at $T = 0, 5, 15, 30$ minutes under $Max$, enforcing total drift $\le 0.5e$ and early termination check ($\le 0.2e$ between 15m and 30m).

### 6.2 Partial Plan Fallback
If an instrument has validation errors or complex multi-interval features, the generator produces a **safe partial plan**:
* `is_partial_plan: True`
* `partial_plan_reasons: List[str]` detailing non-compliances.
* Standard safety tests generated, while flagging ambiguous checks for on-site inspector sign-off.

---

## 7. API Endpoints & Calling Conventions

The Regulatory Engine is exposed via FastAPI router at `/regulatory` and through the standalone facade `RegulatoryAPI.dispatch(method, path, body)`.

### 7.1 POST `/regulatory/validate-instrument`
Validates an instrument specification.
* **Request:**
  ```json
  {
    "accuracy_class": "III",
    "Max": 15.0,
    "Min": 0.1,
    "e": 0.005,
    "d": 0.005,
    "unit": "kg",
    "is_electronic": true,
    "is_multi_interval": false
  }
  ```
* **Response (200 OK):**
  ```json
  {
    "success": true,
    "valid": true,
    "errors": [],
    "warnings": [],
    "manual_review_required": false,
    "instrument_summary": {
      "accuracy_class": "III",
      "calculated_n": 3000
    }
  }
  ```

### 7.2 POST `/regulatory/mpe`
Calculates statutory MPE for an applied load.
* **Request:**
  ```json
  {
    "accuracy_class": "III",
    "load": 2.5,
    "e": 0.005,
    "verification_type": "INITIAL",
    "observed_error": 0.002
  }
  ```
* **Response (200 OK):**
  ```json
  {
    "success": true,
    "load": 2.5,
    "e": 0.005,
    "load_in_e": 500.0,
    "mpe_in_e": 0.5,
    "mpe_absolute": 0.0025,
    "verification_type": "INITIAL",
    "observed_error": 0.002,
    "passed": true,
    "fail": false,
    "margin": 0.0005,
    "margin_in_e": 0.1,
    "applicable_rule": "Band 1: 0 <= m <= 500 e (MPE: +/-0.5 e)",
    "source": "OIML R 76-1:2006 Clause 3.5.1 (Table 6)"
  }
  ```

### 7.3 POST `/regulatory/applicable-tests`
Determines which statutory tests apply to an instrument.
* **Request:**
  ```json
  {
    "accuracy_class": "III",
    "max_capacity": 15.0,
    "verification_scale_interval": 0.005,
    "is_electronic": true,
    "has_zero_setting": true,
    "has_tare": true,
    "indication_type": "DIGITAL"
  }
  ```
* **Response (200 OK):**
  ```json
  {
    "success": true,
    "applicable_test_ids": ["A.1", "A.3", "A.4.2", "A.4.3", "A.4.4", "A.4.7", "A.4.8", "A.4.10", "A.5.2"],
    "not_applicable_test_ids": ["A.2", "A.4.7.1", "A.4.9", "A.4.11", "A.4.11.1", ...],
    "manual_review_tests": ["A.1", "A.3"]
  }
  ```

### 7.4 POST `/regulatory/test-plan`
Generates a complete executable test plan.
* **Request:**
  ```json
  {
    "job_id": "JOB-2026-001",
    "instrument_id": "SCALE-774",
    "accuracy_class": "III",
    "Max": 15.0,
    "Min": 0.1,
    "e": 0.005,
    "d": 0.005,
    "unit": "kg",
    "is_electronic": true,
    "has_zero_setting": true,
    "has_tare": true,
    "verification_type": "INITIAL"
  }
  ```
* **Response (200 OK):**
  Returns `GeneratedTestPlan` structure with `test_plan_id`, `tests`, `calculated_test_loads`, `statutory_fee_inr`, `gatc_eligible`, and `required_equipment`.

### 7.5 GET `/regulatory/profile`
Retrieves regulatory profiles with optional filtering by `profile_id`, `status`, `date`, or `jurisdiction`.

### 7.6 GET `/regulatory/rules/{rule_id}`
Returns rule details, statutory citations, and audit explanations.

---

## 8. Statutory & Regulatory Sources

The Regulatory Engine explicitly distinguishes between binding Indian statutory law, international technical recommendations, and administrative guidance:

1. **Indian Statutory Law (Primary Mandate):**
   - *Legal Metrology Act, 2009 (No. 1 of 2010)*: Sections 15, 24, and 53.
   - *Legal Metrology (General) Rules, 2011*:
     - Seventh Schedule, Part I: Specifications for Non-Automatic Weighing Instruments.
     - Seventh Schedule, Part II: Testing Procedures.
     - Schedule XII: Statutory Verification Fee Schedules.
   - *Legal Metrology (Approval of Models) Rules, 2011*: Pattern evaluation standards.
   - *Legal Metrology (Government Approved Test Centre) Rules, 2013*: GATC delegation limits (Rule 4(1)).
2. **International Technical Source (Harmonised Methodology):**
   - *OIML R 76-1:2006 (E)*: Technical and metrological requirements, test procedures (Annex A and B).
   - *OIML R 76-2:2007 (E)*: Test report formats (used as reporting template convention, NOT an Indian statutory requirement).
3. **Draft / Reported Amendments (Isolated):**
   - *Reported G.S.R. 568(E)*: Industry-circulated draft rules regarding $20\%$ weight substitution and fee revisions. Held strictly in `MANUAL_REVIEW` status (`is_authoritative: False`).

---

## 9. Configurable Rules & Lifecycle Versioning

The Regulatory Engine avoids hardcoded constants through data-driven profiles (`app.regulatory.profile`):

```python
from app.regulatory.profile import RegulatoryProfile, ProfileStatus, PROFILE_REGISTRY

profile = RegulatoryProfile(
    profile_id="IN_CUSTOM_2026",
    jurisdiction="INDIA",
    regulation_name="Custom State Legal Metrology Schedule",
    version="1.0",
    verification_status=ProfileStatus.ACTIVE,
    fees={"capacity_tiers": [...]},
    gatc_applicability={"enabled": True, "allowed_classes": ["III"], "max_capacity_kg": 2000.0},
    test_weight_substitution={"max_substitution_ratio": 0.40},
    re_verification_periods={"COMMERCIAL_NAWI": 12, "WEIGHBRIDGE": 6},
)
PROFILE_REGISTRY.register(profile)
```

### Supported Profile Lifecycle Statuses
1. `ACTIVE`: Officially gazetted, verified law currently in force.
2. `DRAFT`: Proposed amendment or secondary-source claim. Triggers `manual_review_required: True`.
3. `SUPERSEDED`: Historical regulation replaced by an amendment.
4. `MANUAL_REVIEW`: Unconfirmed secondary-source draft requiring legal officer sign-off.

### Audit Trail ("Why did the engine apply this rule?")
Every rule application attaches an audit trace:
```json
{
  "rule_id": "RULE_MPE_BAND_LOOKUP",
  "statutory_source": "OIML R 76-1:2006 Clause 3.5.1 (Table 6) / IN LM 2011 Seventh Schedule",
  "applied_profile_id": "IN_LM_2011_ACTIVE",
  "evaluation_context": {"load": 2.5, "e": 0.005, "load_in_e": 500.0},
  "rationale": "Load 500.0 e falls into Band 1 (0 <= m <= 500 e), yielding MPE +/-0.5 e."
}
```

---

## 10. Manual-Review Scenarios & Safeguards

The engine enforces strict fail-safe mechanisms when statutory ambiguity exists:

1. **Unverified Regulatory Profiles (G.S.R. 568(E)):**
   Whenever `IN_LM_2026_GSR568E_DRAFT` is invoked, the test plan is generated with `is_authoritative: False` and injects `PROFILE_MANUAL_REVIEW_REQUIRED`.
2. **Multi-Interval Scales:**
   Discontinuous scale intervals ($e_1, e_2$) have physical changeover thresholds that must be inspected visually. The engine generates a partial plan and flags `PARTIAL_PLAN_ALERT`.
3. **Tilting Susceptibility Without Level Indicator:**
   If an instrument is mobile or tilt-susceptible without a verified level bubble, manual review is flagged for field tilt testing.
4. **Missing Software Identification:**
   If an electronic instrument declares legally relevant software but lacks a declared software version/checksum, a warning is emitted and flagged for visual verification.
5. **Direct State Inspection Routing (GATC Rule 4(1)):**
   Class I instruments or instruments with $Max > 5,000\text{ kg}$ are denied GATC eligibility and routed to State Legal Metrology Officers.

---

## 11. Known Limitations

1. **Continuous Dynamic Scales:**
   The engine implements non-automatic weighing instruments (NAWI per OIML R 76). Automatic weighing instruments (catchweighers, checkweighers per OIML R 51) are outside this module's scope.
2. **Multi-Interval Mid-Range Tare:**
   While multi-interval load points are calculated, tare tare deductions that bridge across interval changeover points require physical verification on the physical instrument.
3. **State-Specific Fee Amendments:**
   While the engine provides Schedule XII Central fees and dynamic override capability, state-specific local court fees must be configured via profile overrides.

---

## 12. Integration Instructions for Person 1

Person 1 (Team Lead & Orchestration) can consume the Regulatory Engine directly with zero friction:

### Option A: Python Module Imports (Fastest & In-Process)
```python
from app.regulatory import (
    RegulatoryClassificationValidator,
    RegulatoryTestApplicabilityEngine,
    RegulatoryTestPlanGenerator,
    MPEEngine,
    generate_regulatory_test_plan,
)

# 1. Validate an incoming instrument spec
result = RegulatoryClassificationValidator.validate(instrument_dict)
if not result.valid:
    print("Errors:", [e.message for e in result.errors])

# 2. Generate a complete test plan for Person 4
plan = RegulatoryTestPlanGenerator.generate(instrument_dict)
# Or as a dictionary:
plan_dict = generate_regulatory_test_plan(instrument_dict)
```

### Option B: FastAPI Router Integration
Mount the router in your main FastAPI application (`backend/app/main.py`):
```python
from fastapi import FastAPI
from app.regulatory.router import router as regulatory_router

app = FastAPI(title="MetrIQ API")
app.include_router(regulatory_router, prefix="/regulatory", tags=["Regulatory Engine"])
```

### Calling Conventions
* **Units:** All calculations support `mg`, `g`, `kg`, `t`, and `ct`. The generator automatically normalizes capacities for fee and GATC calculations.
* **Accuracy Classes:** Pass either string (`"I"`, `"II"`, `"III"`, `"IIII"`) or enum (`AccuracyClass.CLASS_III`).
* **Verification Types:** Pass `"INITIAL"` or `"SUBSEQUENT"` (or aliases `"in_service"`, `"re_verification"`).

---
*Verified compliant with OIML R 76-1:2006 and Indian Legal Metrology Rules, 2011.*
