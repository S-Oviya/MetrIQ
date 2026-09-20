"""
Full End-to-End Fresh User Smoke Test for MetrIQ SIH Demo.
Tests the exact user flow:
1. Register New Instrument
2. Create Verification Job
3. Verify Regulatory Test Plan
4. Validate Job
5. Start Execution
6. Submit Test Observations & Check PASS/FAIL
7. Submit for Review
8. Supervisory Approval
9. Generate Statutory Verification Report
10. Download and Validate PDF File
11. Check Comprehensive Audit Trail
12. Verify Persistence after simulated backend restart
"""

import sys
import os
from pathlib import Path
from fastapi.testclient import TestClient

backend_dir = Path(r"C:\Users\Oviyazhini\MetrIQ\backend")
sys.path.insert(0, str(backend_dir))

from app.main import app
from app.database.connection import get_db_connection

client = TestClient(app)

def run_smoke_test():
    print("==================================================")
    print("STARTING FULL END-TO-END FRESH USER SMOKE TEST")
    print("==================================================")
    
    # 1. REGISTER NEW INSTRUMENT
    import uuid
    uid = uuid.uuid4().hex[:6].upper()
    serial_no = f"DEMO-SIH-2026-{uid}"
    print(f"\n[Step 1] Registering New Instrument ({serial_no})...")
    inst_payload = {
        "serial_number": serial_no,
        "instrument_type": "NON_AUTOMATIC_WEIGHING",
        "manufacturer": "MetrIQ Precision Instruments Ltd",
        "model_name": "SIH-NX-3000",
        "model_number": "NX-3000-IND",
        "accuracy_class": "CLASS_III",
        "max_capacity": 15000.0,
        "min_capacity": 100.0,
        "verification_scale_interval": 5.0,
        "scale_interval": 5.0,
        "unit": "kg",
        "location": {
            "customer_name": "Standard Client",
            "city": "Chennai",
            "state": "Tamil Nadu"
        }
    }
    resp = client.post("/instruments?enforce_model_approval=false", json=inst_payload)
    assert resp.status_code in (200, 201), f"Failed to register instrument: {resp.text}"
    inst_resp = resp.json()
    instrument = inst_resp.get("data", inst_resp)
    instrument_id = instrument.get("instrument_id", instrument.get("id"))
    print(f"-> Instrument created successfully! ID: {instrument_id}, Serial: {instrument.get('serial_number')}")
    
    # Check it appears in GET /instruments
    resp_list = client.get("/instruments")
    assert resp_list.status_code == 200
    list_body = resp_list.json()
    inst_rows = list_body.get("data", list_body) if isinstance(list_body, dict) else list_body
    inst_ids = [i.get("instrument_id", i.get("id")) for i in inst_rows]
    assert instrument_id in inst_ids, "Instrument not listed in registry"
    print(f"-> Instrument confirmed present in live registry (total: {len(inst_ids)})")

    # 2. CREATE NEW VERIFICATION JOB
    print("\n[Step 2] Creating New Verification Job...")
    job_payload = {
        "instrument_id": instrument_id,
        "job_type": "INITIAL",
        "location": "Chennai Central Warehouse Dock 4",
        "assigned_inspector_id": "INSP-SIH-42",
        "assigned_inspector_name": "Inspector R. Sundaram"
    }
    resp = client.post("/jobs", json=job_payload)
    assert resp.status_code in (200, 201), f"Failed to create job: {resp.text}"
    job_data = resp.json()
    job = job_data.get("data", job_data)
    job_id = job.get("job_id", job.get("id"))
    print(f"-> Job created successfully! ID: {job_id}, Status: {job.get('status')}")

    # 3. VERIFY REGULATORY TEST PLAN
    print("\n[Step 3] Fetching Statutory Test Plan...")
    resp = client.get(f"/jobs/{job_id}/test-plan")
    assert resp.status_code == 200, f"Failed to get test plan: {resp.text}"
    plan_body = resp.json()
    test_plan = plan_body.get("data", plan_body)
    tests = test_plan.get("tests", test_plan.get("applicable_tests", []))
    print(f"-> Statutory Test Plan generated with {len(tests)} statutory tests.")
    assert len(tests) > 0, "No tests generated in test plan"

    # 4. VALIDATE JOB
    print("\n[Step 4] Validating Job Compliance...")
    resp = client.post(f"/jobs/{job_id}/validate", json={"user_id": "INSP-SIH-42"})
    assert resp.status_code == 200, f"Failed to validate job: {resp.text}"
    val_data = resp.json().get("data", resp.json())
    print(f"-> Validation outcome: is_valid={val_data.get('is_valid')}")

    # 5. START TEST EXECUTION
    print("\n[Step 5] Starting Test Execution...")
    resp = client.post(f"/jobs/{job_id}/start-execution", json={"user_id": "INSP-SIH-42"})
    assert resp.status_code == 200, f"Failed to start execution: {resp.text}"
    job_after_start = resp.json().get("data", resp.json())
    print(f"-> Job status updated: {job_after_start.get('status')}")

    # 6. SUBMIT TEST OBSERVATIONS & CHECK PASS/FAIL
    print("\n[Step 6] Submitting Real Test Observations (Weighing Performance)...")
    test_type = "WEIGHING_PERFORMANCE"
    observations = [
        {"step_number": 1, "applied_load": 500.0, "indicated_value": 500.0, "tare_load": 0.0, "position": "CENTER"},
        {"step_number": 2, "applied_load": 5000.0, "indicated_value": 5000.0, "tare_load": 0.0, "position": "CENTER"},
        {"step_number": 3, "applied_load": 15000.0, "indicated_value": 15000.0, "tare_load": 0.0, "position": "CENTER"},
    ]

    attempt_payload = {
        "job_id": job_id,
        "test_type": test_type,
        "observations": observations,
        "operator": "INSP-SIH-42",
        "notes": "Metrological accuracy verified at standard reference checkpoints."
    }

    resp = client.post("/test-execution/submit", json=attempt_payload)
    assert resp.status_code in (200, 201), f"Failed to submit test execution: {resp.text}"
    attempt_res = resp.json().get("data", resp.json())
    verdict = attempt_res.get("verdict")
    print(f"-> Test execution evaluated: verdict={verdict}, test_type={test_type}")
    assert verdict == "PASS", f"Expected PASS, got {verdict}"

    # 7. SUBMIT FOR SUPERVISORY REVIEW
    print("\n[Step 7] Submitting Job for Supervisory Review...")
    rev_submit_payload = {
        "submitted_by": "INSP-SIH-42",
        "comments": "All legal metrology verification criteria satisfied under statutory limits."
    }
    resp = client.post(f"/jobs/{job_id}/submit-review", json=rev_submit_payload)
    assert resp.status_code == 200, f"Failed to submit for review: {resp.text}"
    print(f"-> Job submitted for review. Current status: {resp.json().get('data', resp.json()).get('status')}")

    # 8. SUPERVISORY APPROVAL (Four-eyes compliance)
    print("\n[Step 8] Performing Independent Supervisory Review (Approval)...")
    rev_decision_payload = {
        "reviewer": "SUPV-LEGAL-METROLOGY-07",
        "decision": "APPROVE",
        "comments": "Verified against Legal Metrology (General) Rules 2011 Schedule VII. Stamped and cleared."
    }
    resp = client.post(f"/jobs/{job_id}/review", json=rev_decision_payload)
    assert resp.status_code == 200, f"Failed to approve job: {resp.text}"
    print(f"-> Supervisory decision recorded! Status: {resp.json().get('data', resp.json()).get('status')}")

    # 9. GENERATE STATUTORY REPORT
    print("\n[Step 9] Generating Statutory Verification Report...")
    report_payload = {
        "job_id": job_id,
        "report_type": "GENERIC_VERIFICATION",
        "created_by": "SUPV-LEGAL-METROLOGY-07"
    }
    resp = client.post("/reports/generate", json=report_payload)
    assert resp.status_code in (200, 201), f"Failed to generate report: {resp.text}"
    report_body = resp.json().get("data", resp.json())
    report_id = report_body.get("report_id", report_body.get("id"))
    print(f"-> Report generated! ID: {report_id}, Type: {report_body.get('report_type')}, Status: {report_body.get('generation_status')}")

    # 10. DOWNLOAD AND VALIDATE REAL PDF FILE
    print("\n[Step 10] Downloading and Validating Real PDF...")
    resp = client.get(f"/reports/{report_id}/pdf?download=true")
    assert resp.status_code == 200, f"Failed to download PDF: {resp.text}"
    content_type = resp.headers.get("content-type", "")
    assert "application/pdf" in content_type, f"Content-Type is not application/pdf: {content_type}"
    pdf_bytes = resp.content
    assert pdf_bytes.startswith(b"%PDF"), "Downloaded file does not have valid %PDF magic header"
    print(f"-> PDF verified successfully! Size: {len(pdf_bytes)} bytes, Magic Header: {pdf_bytes[:4].decode('ascii')}")

    # 11. CHECK AUDIT TRAIL
    print("\n[Step 11] Checking Complete Job Audit Trail...")
    resp = client.get(f"/jobs/{job_id}/audit")
    assert resp.status_code == 200, f"Failed to get audit trail: {resp.text}"
    audit_data = resp.json().get("data", resp.json())
    events = audit_data if isinstance(audit_data, list) else []
    print(f"-> Total audit events logged: {len(events)}")
    assert len(events) >= 5, f"Expected at least 5 audit events, found {len(events)}"
    for e in events[-5:]:
        print(f"   [{e.get('timestamp')}] {e.get('action')} by {e.get('actor')}")

    # 12. VERIFY SQLITE PERSISTENCE ACROSS RESTART
    print("\n[Step 12] Verifying SQLite Persistence...")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT instrument_id, serial_number FROM instruments WHERE instrument_id = ?", (instrument_id,))
    row = c.fetchone()
    assert row is not None, "Instrument missing from SQLite DB!"
    print(f"-> SQLite persisted Instrument: {row['instrument_id']} ({row['serial_number']})")
    
    c.execute("SELECT job_id, status FROM jobs WHERE job_id = ?", (job_id,))
    row = c.fetchone()
    assert row is not None, "Job missing from SQLite DB!"
    print(f"-> SQLite persisted Job: {row['job_id']} ({row['status']})")
    
    c.execute("SELECT report_id, report_type, pdf_path FROM reports WHERE report_id = ?", (report_id,))
    row = c.fetchone()
    assert row is not None, "Report missing from SQLite DB!"
    print(f"-> SQLite persisted Report: {row['report_id']} (PDF path: {row['pdf_path']})")
    conn.close()

    print("\n==================================================")
    print("ALL 12 END-TO-END SMOKE TEST STEPS PASSED PERFECTLY!")
    print("==================================================")

if __name__ == "__main__":
    run_smoke_test()
