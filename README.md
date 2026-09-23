# MetrIQ

### Digital Test Report & Compliance Management Platform for Non-Automatic Weighing Instruments

MetrIQ is a software platform designed to support the **testing, validation, compliance checking, review, and report generation of Non-Automatic Weighing Instruments (NAWI)** in accordance with applicable **Legal Metrology requirements and OIML Recommendation R 76**.

Instead of treating a test report as simply a form that is filled in and exported to PDF, MetrIQ models the **complete test-report lifecycle** — from instrument registration and test planning to measurement execution, automated validation, review, report generation, and audit tracking.

---

## Why MetrIQ?

Testing a weighing instrument is not just about entering measurements and generating a document.

A proper test process may involve:

* Identifying the instrument and its characteristics
* Recording manufacturer, model and serial information
* Determining the applicable accuracy class
* Recording `Max`, `Min`, `e`, `d`, and `n`
* Identifying the applicable regulatory requirements
* Selecting the appropriate tests
* Recording raw measurements
* Calculating derived values
* Determining Maximum Permissible Errors (MPE)
* Checking whether measurements comply
* Recording equipment and traceability information
* Performing independent review
* Maintaining an audit trail
* Generating the final test report

When these activities are handled manually across spreadsheets, documents, and separate records, it becomes difficult to maintain consistency and traceability.

**MetrIQ brings these activities into one structured workflow.**

---

# What is a NAWI?

A **Non-Automatic Weighing Instrument (NAWI)** is a weighing instrument that requires the intervention of an operator during the weighing process.

Examples include weighing instruments where an operator:

* places an object on the weighing platform,
* observes the indication,
* determines when the measurement is stable,
* or performs another action before or during weighing.

MetrIQ is focused on managing the testing and reporting process associated with these instruments.

---

# Regulatory Foundation

MetrIQ is designed around the concepts and requirements relevant to Indian Legal Metrology and OIML-based testing.

The system considers the following regulatory framework:

### Legal Metrology Act, 2009

Provides the broader legal framework governing weights and measures in India.

### Legal Metrology (General) Rules, 2011

Defines requirements relating to weighing and measuring instruments and their verification.

### Legal Metrology (Approval of Models) Rules, 2011

Relevant to the approval and evaluation of instrument models.

### Government Approved Test Centre (GATC) Rules, 2013

Provides the framework for approved testing facilities and applicable testing workflows.

### OIML R 76

The **International Recommendation for Non-Automatic Weighing Instruments**, providing technical requirements and test procedures for NAWIs.

MetrIQ does not replace the governing regulations. Instead, it provides a structured software layer for applying, recording, validating, reviewing, and reporting the relevant requirements.

---

# The Problem MetrIQ Solves

Traditional test-report workflows can become fragmented.

An organization may have:

```text
Instrument details
       ↓
Spreadsheet
       ↓
Test measurements
       ↓
Manual calculations
       ↓
Manual compliance checking
       ↓
Word/PDF report
       ↓
Separate review records
       ↓
Separate audit records
```

This creates opportunities for:

* inconsistent data,
* calculation mistakes,
* missing test evidence,
* incorrect regulatory references,
* duplicated data entry,
* difficult report revisions,
* weak traceability,
* and difficulty determining who changed what.

MetrIQ transforms this into a structured digital workflow:

```text
Instrument Registration
        ↓
Regulatory Classification
        ↓
Test Planning
        ↓
Test Execution
        ↓
Measurement Capture
        ↓
Automatic Calculations
        ↓
Compliance Validation
        ↓
Independent Review
        ↓
Report Generation
        ↓
Audit & Record Retention
```

---

# Core Idea

MetrIQ treats a test report as the **result of a controlled testing process**, rather than as a document that is manually filled out.

The generated report is backed by structured information such as:

* instrument identity,
* instrument characteristics,
* applicable rules,
* selected tests,
* raw measurements,
* calculated values,
* MPE limits,
* compliance results,
* equipment information,
* reviewer information,
* timestamps,
* and audit history.

This makes the report traceable back to the underlying test data.

---

# MetrIQ Workflow

## 1. Instrument Registration

The first step is creating a record for the instrument being examined.

The system can maintain information such as:

* Manufacturer
* Model
* Serial number
* Instrument type
* Accuracy class
* Maximum capacity (`Max`)
* Minimum capacity (`Min`)
* Verification scale interval (`e`)
* Actual scale interval (`d`)
* Number of verification intervals (`n`)
* Applicable jurisdiction
* Applicable regulatory/rule version
* Date of receipt
* Verification-related dates
* Identification and supporting documents

This creates a persistent **instrument record** rather than treating each report as an isolated document.

---

## 2. Regulatory Classification

Not every weighing instrument follows exactly the same testing path.

MetrIQ uses instrument characteristics and applicable regulatory information to determine the relevant testing and compliance context.

The system can consider factors such as:

* Accuracy class
* Capacity
* Verification interval
* Instrument type
* Applicable rule version
* Jurisdiction
* Testing context

This helps prevent the workflow from becoming a generic one-size-fits-all form.

---

# 3. Test Planning

Once the instrument is registered, the applicable test plan can be prepared.

Depending on the instrument and testing context, the workflow can include tests such as:

* Weighing performance
* Repeatability
* Eccentricity
* Discrimination
* Creep
* Zero return
* Tare
* Temperature-related testing
* Stability
* Construction and marking examination
* Software-related examination where applicable

The objective is to establish **what needs to be tested before measurements are entered**.

---

# 4. Test Execution

The test execution module records the actual evidence produced during testing.

Instead of only storing a final PASS/FAIL value, MetrIQ can preserve the underlying measurement information.

For example:

```text
Test
 ├── Test conditions
 ├── Reference/equipment information
 ├── Raw measurements
 ├── Calculated values
 ├── Applicable MPE
 ├── Result
 └── Supporting notes/evidence
```

This creates a connection between the final compliance decision and the measurements that produced it.

---

# 5. Measurement & Calculation Engine

MetrIQ contains a calculation layer for processing test measurements.

Depending on the test, the system can calculate and evaluate values such as:

* Errors of indication
* Maximum Permissible Errors
* Repeatability characteristics
* Eccentricity errors
* Discrimination-related values
* Creep-related values
* Zero-return behavior
* Tare-related results
* Temperature test results
* Other derived test values

The calculation engine separates **raw measurement data** from **derived results**.

For example:

```text
Raw Measurement
       ↓
Calculation Engine
       ↓
Derived Value
       ↓
MPE / Requirement
       ↓
Compliance Result
```

This reduces the need to manually perform the same calculations every time.

---

# 6. Compliance Validation

After calculations are performed, MetrIQ evaluates the results against the applicable requirements.

A result is therefore represented as more than:

```text
PASS
```

The system can maintain the relationship between:

```text
Measurement
     ↓
Calculated Error
     ↓
Applicable Limit
     ↓
Compliance Decision
```

This makes the result easier to understand and review.

---

# 7. Independent Review

Testing and review are treated as separate stages of the workflow.

A reviewer can examine:

* Instrument information
* Test configuration
* Measurements
* Calculations
* Compliance results
* Supporting information
* Report contents

The goal is to provide a controlled review step before a report is finalized.

---

# 8. Report Generation

After the testing and validation workflow is completed, MetrIQ generates the formal test report.

The report can bring together:

* Instrument identity
* Customer/organization information
* Instrument characteristics
* Applicable standards/rules
* Test conditions
* Test results
* Measurements
* Calculated values
* Compliance status
* Equipment/traceability information
* Reviewer information
* Dates and references

The PDF is therefore an **output of the workflow**, rather than the place where the entire workflow happens.

---

# 9. Audit & Traceability

A major part of MetrIQ is maintaining traceability throughout the testing lifecycle.

Important actions can be associated with:

* User
* Role
* Timestamp
* Action
* Related instrument/report
* Workflow state

This helps answer questions such as:

> Who created this test?

> Which measurements were recorded?

> Who reviewed the results?

> When was the report generated?

> What stage is this instrument currently in?

The objective is to make the system suitable for a controlled professional workflow rather than a simple form-filling application.

---

# Application Modules

MetrIQ is organized around a modular workflow.

## 1. Authentication & Role Management

Provides controlled access to the application.

Different users can have different responsibilities within the testing lifecycle.

Example roles can include:

* Administrator
* Test Engineer / Inspector
* Reviewer
* Other authorized personnel

Role-based access helps prevent every user from having unrestricted control over the entire workflow.

---

## 2. Dashboard

The dashboard provides an overview of the organization's testing activity.

It can surface information such as:

* Active instruments
* Pending tests
* Tests awaiting review
* Completed reports
* Compliance status
* Recent activity
* Workflow status

This provides a high-level operational view without requiring users to search through individual records.

---

## 3. Instrument Registry

The instrument registry acts as the central record for NAWIs.

Instead of creating an entirely new identity every time a report is generated, the system can maintain the instrument's historical information.

This creates a foundation for:

```text
Instrument
    ↓
Testing History
    ↓
Reports
    ↓
Reviews
    ↓
Audit Trail
```

---

## 4. Rules & Compliance Engine

The rules engine connects instrument characteristics with the applicable requirements.

It provides the foundation for:

* Regulatory classification
* Test applicability
* MPE evaluation
* Compliance checks
* Rule-version tracking

This is important because regulations and applicable requirements need to remain identifiable rather than being hidden inside hard-coded report templates.

---

## 5. Test Planning

Creates the test plan for a specific instrument.

It determines the tests and conditions that need to be executed based on the instrument and testing context.

---

## 6. Test Execution

Provides the workspace where actual test measurements and observations are recorded.

The module connects the physical testing process with the digital record.

---

## 7. Validation

The validation layer evaluates the recorded measurements and calculations against applicable requirements.

It acts as the bridge between:

```text
Test Data
    ↓
Calculations
    ↓
Regulatory Requirements
    ↓
Compliance Result
```

---

## 8. Reports

Converts the completed and reviewed test record into a formal report.

Reports are generated from structured data instead of requiring users to manually recreate the same information in a document.

---

## 9. Audit & Administration

Provides administrative control and traceability across the platform.

This includes areas such as:

* User management
* Roles
* Activity history
* Workflow tracking
* Report history
* System records

---

# Supported Testing Concepts

MetrIQ's calculation and validation architecture is designed to accommodate multiple NAWI test categories.

### Weighing Performance

Evaluates the instrument's indication against the relevant reference/load conditions.

### Repeatability

Checks the consistency of repeated weighing results under defined conditions.

### Eccentricity

Examines whether the position of a load on different sections of the load receptor affects the indication.

### Discrimination

Evaluates the instrument's ability to detect a relevant change in load.

### Creep

Evaluates changes in indication while a load remains applied over a specified period.

### Zero Return

Checks the behavior of the instrument when returning toward zero after a weighing operation.

### Tare

Handles testing associated with tare functionality where applicable.

### Temperature

Provides a structure for recording and evaluating temperature-related test conditions and results.

### Construction & Marking Examination

Allows non-measurement requirements such as construction, markings, identification, and related characteristics to be examined.

---

# Data Flow

A simplified representation of MetrIQ is:

```text
                 ┌─────────────────────┐
                 │ Instrument Registry │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Regulatory Rules    │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Test Planning       │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Test Execution      │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Raw Measurements    │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Calculation Engine  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Compliance Engine   │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Independent Review  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Test Report         │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Audit & History     │
                 └─────────────────────┘
```

---

# Architecture

MetrIQ follows a modular application architecture separating the user interface, API layer, domain logic, calculations, validation, and reporting.

```text
Frontend
   │
   ▼
Backend API
   │
   ├── Authentication & Roles
   ├── Instrument Registry
   ├── Test Planning
   ├── Test Execution
   ├── Validation
   ├── Reporting
   └── Audit
          │
          ▼
   Domain / Calculation Layer
          │
          ├── MPE
          ├── Repeatability
          ├── Eccentricity
          ├── Discrimination
          ├── Creep
          ├── Tare
          ├── Temperature
          └── Examination
```

The backend calculation layer is intentionally separated into individual test-specific components so that domain calculations are not tightly coupled to the user interface.

---

# Technology Stack

### Frontend

* React
* TypeScript
* Modern component-based UI
* Responsive web interface

### Backend

* Python
* FastAPI
* REST API architecture

### Data & Processing

* Structured database-backed records
* Domain-specific calculation modules
* Validation and compliance processing

### Reporting

* PDF report generation
* Template-based structured reporting
* Report data sourced from completed test records

### Deployment

The application can be deployed as a web-based system with separately hosted frontend and backend services.

---

# Project Structure

A simplified view of the backend architecture:

```text
backend/
├── app/
│   ├── api/
│   │   └── router.py
│   │
│   ├── calculations/
│   │   ├── engine.py
│   │   ├── models.py
│   │   ├── mpe.py
│   │   ├── eccentricity.py
│   │   ├── repeatability.py
│   │   ├── discrimination.py
│   │   ├── creep.py
│   │   ├── tare.py
│   │   ├── temperature.py
│   │   ├── examination.py
│   │   ├── router.py
│   │   └── service.py
│   │
│   └── ...
│
└── requirements.txt
```

The calculation modules are separated by test type so that each calculation can be developed, tested, and maintained independently.

---

# Key Design Principles

## 1. Report-first is not enough

MetrIQ does not treat PDF generation as the core functionality.

The report is the final representation of a much larger testing process.

---

## 2. Raw data should remain traceable

Where possible, calculated values should be derived from recorded measurements instead of requiring users to manually enter the final answer.

---

## 3. Regulatory context matters

The same generic form should not be blindly applied to every weighing instrument.

Instrument characteristics and applicable requirements influence the testing workflow.

---

## 4. Testing and review are different activities

The person performing a test and the person reviewing the result may have different responsibilities.

MetrIQ therefore separates these workflow stages.

---

## 5. Every report should have context

A useful test report should allow someone reviewing it to understand:

```text
What was tested?
        ↓
Under which requirements?
        ↓
How was it tested?
        ↓
What measurements were obtained?
        ↓
How were the results calculated?
        ↓
Did they comply?
        ↓
Who reviewed the result?
```

---

# What Makes MetrIQ Different?

MetrIQ is not intended to be:

> "Enter some values → click Generate PDF."

Instead, it models the actual lifecycle around a regulated weighing-instrument test.

### Traditional document-oriented approach

```text
Form
 ↓
Manual values
 ↓
Manual calculations
 ↓
PDF
```

### MetrIQ approach

```text
Instrument
 ↓
Regulatory Context
 ↓
Test Plan
 ↓
Controlled Execution
 ↓
Raw Measurements
 ↓
Calculation Engine
 ↓
Compliance Validation
 ↓
Review
 ↓
Traceable Report
 ↓
Audit History
```

This distinction is central to the project.

---

# Example Workflow

Consider a weighing instrument submitted for testing.

### Step 1 — Register

The instrument is registered with its:

* manufacturer,
* model,
* serial number,
* class,
* capacity,
* verification scale interval,
* and other relevant characteristics.

### Step 2 — Determine requirements

MetrIQ identifies the applicable regulatory and testing context.

### Step 3 — Create test plan

The relevant tests are selected.

### Step 4 — Perform tests

The inspector performs the physical tests and records the measurements.

### Step 5 — Calculate

MetrIQ processes the recorded measurements and derives the relevant values.

### Step 6 — Validate

The calculated results are compared with the applicable requirements.

### Step 7 — Review

A reviewer checks the test record and results.

### Step 8 — Generate report

MetrIQ produces the formal test report.

### Step 9 — Preserve history

The instrument, test, report, review, and audit information remain connected for future reference.

---

# Important Terminology

| Term                | Meaning                                                                                        |
| ------------------- | ---------------------------------------------------------------------------------------------- |
| **NAWI**            | Non-Automatic Weighing Instrument                                                              |
| **Max**             | Maximum capacity of the instrument                                                             |
| **Min**             | Minimum capacity relevant to the instrument                                                    |
| **e**               | Verification scale interval                                                                    |
| **d**               | Actual scale interval / resolution                                                             |
| **n**               | Number of verification intervals                                                               |
| **MPE**             | Maximum Permissible Error                                                                      |
| **OIML**            | International Organization of Legal Metrology                                                  |
| **GATC**            | Government Approved Test Centre                                                                |
| **Type Evaluation** | Evaluation of an instrument model against applicable requirements                              |
| **Verification**    | Examination/testing of an instrument for legal use                                             |
| **Calibration**     | Determination of measurement performance against a reference; distinct from legal verification |
| **Audit Trail**     | Record of relevant actions and changes throughout the workflow                                 |

---

# Scope

MetrIQ focuses on the **digital management of NAWI testing and reporting**.

It is intended to support:

* instrument registration,
* test planning,
* test execution,
* calculations,
* compliance validation,
* review,
* report generation,
* and traceability.

It does **not** replace:

* physical laboratory testing,
* authorized legal-metrology personnel,
* regulatory authorities,
* applicable legislation,
* OIML documents,
* or official approval/verification decisions.

The software assists with the workflow and documentation; the applicable authority and regulations remain the governing source.

---

# Future Scope

Potential future extensions include:

* Expanded regulatory rule libraries
* Additional OIML test coverage
* Digital evidence and attachment management
* Advanced audit trails
* Instrument history and recurring verification tracking
* Equipment calibration/traceability management
* Electronic signatures
* Multi-organization support
* Advanced analytics and compliance dashboards
* Offline testing support
* Integration with laboratory equipment
* Automated regulatory updates
* Enhanced report versioning

---

# Getting Started

## Prerequisites

Make sure the following are installed:

* Node.js
* npm
* Python 3.x
* Git

---

## Clone the Repository

```bash
git clone https://github.com/S-Oviya/MetrIQ.git
cd MetrIQ
```

---

## Backend Setup

Navigate to the backend:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the FastAPI server:

```bash
uvicorn app.main:app --reload
```

The API will then be available locally through the configured backend port.

---

## Frontend Setup

Navigate to the frontend directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Open the local development URL shown by Vite.

---

# Development Philosophy

MetrIQ is built around the idea that **domain software should model the real workflow it is supporting**.

For legal-metrology applications, that means understanding that a test report is not merely a document.

It is the final result of:

```text
Instrument Identity
        +
Regulatory Requirements
        +
Test Procedure
        +
Measurements
        +
Calculations
        +
Validation
        +
Review
        +
Traceability
```

MetrIQ brings these pieces together into one digital workflow.

---

# Project Status

MetrIQ is an actively developed prototype focused on demonstrating an industry-oriented workflow for **NAWI test-report generation and compliance management**.

The project is being developed with emphasis on:

* regulatory traceability,
* domain-specific calculations,
* structured testing workflows,
* automated validation,
* report generation,
* role-based processes,
* and auditability.

---


**MetrIQ**

From:

> **Instrument → Test → Measurement → Validation → Report**

to a complete, traceable digital workflow.

---
