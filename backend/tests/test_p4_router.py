"""
MetrIQ Unit Tests — Person 4 FastAPI REST API Router
====================================================
Tests all HTTP endpoints under the '/calculations' prefix using FastAPI TestClient:
- POST /calculations/mpe
- POST /calculations/execute
- POST /calculations/weighing
- POST /calculations/eccentricity
- POST /calculations/repeatability
- POST /calculations/zero-return
- POST /calculations/creep
- POST /calculations/discrimination
- POST /calculations/tare
- POST /calculations/temperature
- POST /calculations/examination
- Error handling on invalid input
"""

import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.calculations.router import router


class TestP4Router(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = FastAPI(title="MetrIQ Test Engine Test App")
        cls.app.include_router(router)
        cls.client = TestClient(cls.app)

    def test_post_mpe(self):
        """POST /calculations/mpe returns accurate statutory MPE."""
        payload = {
            "load": 5.0,
            "accuracy_class": "CLASS_III",
            "e": 0.005,
            "verification_type": "INITIAL",
            "unit": "kg",
        }
        resp = self.client.post("/calculations/mpe", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["mpe_in_e"], 1.0)
        self.assertEqual(data["data"]["mpe_absolute"], 0.005)

    def test_post_execute_weighing_run(self):
        """POST /calculations/execute dispatches complete test run."""
        payload = {
            "test_run": {
                "test_type": "WEIGHING_PERFORMANCE",
                "observations": [
                    {"step_number": 1, "applied_load": 0.0, "indicated_value": 0.0},
                    {"step_number": 2, "applied_load": 5.0, "indicated_value": 5.001},
                ],
            },
            "instrument": {
                "accuracy_class": "CLASS_III",
                "e": 0.005,
                "d": 0.005,
                "unit": "kg",
            },
            "verification_type": "INITIAL",
        }
        resp = self.client.post("/calculations/execute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["verdict"], "PASS")
        self.assertEqual(data["data"]["test_type"], "WEIGHING_PERFORMANCE")

    def test_post_weighing_endpoint(self):
        """POST /calculations/weighing calculates weighing performance."""
        payload = {
            "observations": [
                {"applied_load": 0.0, "indicated_value": 0.0},
                {"applied_load": 5.0, "indicated_value": 5.001},
            ],
            "accuracy_class": "CLASS_III",
            "e": 0.005,
            "unit": "kg",
        }
        resp = self.client.post("/calculations/weighing", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["verdict"], "PASS")

    def test_post_eccentricity_endpoint(self):
        """POST /calculations/eccentricity calculates eccentricity."""
        payload = {
            "observations": [
                {"applied_load": 5.0, "indicated_value": 5.000, "position": "CENTER"},
                {"applied_load": 5.0, "indicated_value": 5.001, "position": "CORNER_1"},
            ],
            "accuracy_class": "CLASS_III",
            "e": 0.005,
            "unit": "kg",
        }
        resp = self.client.post("/calculations/eccentricity", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["verdict"], "PASS")

    def test_post_repeatability_endpoint(self):
        """POST /calculations/repeatability calculates repeatability."""
        payload = {
            "observations": [
                {"applied_load": 10.0, "indicated_value": 10.000},
                {"applied_load": 10.0, "indicated_value": 10.001},
                {"applied_load": 10.0, "indicated_value": 10.001},
            ],
            "accuracy_class": "CLASS_III",
            "e": 0.005,
            "unit": "kg",
        }
        resp = self.client.post("/calculations/repeatability", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["verdict"], "PASS")

    def test_post_zero_return_endpoint(self):
        """POST /calculations/zero-return calculates zero drift."""
        payload = {
            "initial_zero": 0.000,
            "returned_zero": 0.001,
            "e": 0.005,
            "unit": "kg",
        }
        resp = self.client.post("/calculations/zero-return", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["verdict"], "PASS")

    def test_post_creep_endpoint(self):
        """POST /calculations/creep calculates creep."""
        payload = {
            "load": 15.0,
            "time_observations": [
                {"time_seconds": 5, "indicated_value": 15.000},
                {"time_seconds": 1800, "indicated_value": 15.001},
            ],
            "accuracy_class": "CLASS_III",
            "e": 0.005,
            "unit": "kg",
        }
        resp = self.client.post("/calculations/creep", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["verdict"], "PASS")

    def test_post_discrimination_endpoint(self):
        """POST /calculations/discrimination calculates discrimination."""
        payload = {
            "observations": [
                {"applied_load": 10.0, "indicated_value": 10.000, "extra_load": 0.007, "new_indication": 10.005},
            ],
            "d": 0.005,
            "unit": "kg",
        }
        resp = self.client.post("/calculations/discrimination", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["verdict"], "PASS")

    def test_post_tare_endpoint(self):
        """POST /calculations/tare calculates tare setting and net points."""
        payload = {
            "tare_load": 2.0,
            "tare_setting_observation": {"indicated_value": 0.000},
            "net_observations": [
                {"applied_load": 5.0, "indicated_value": 5.001},
            ],
            "accuracy_class": "CLASS_III",
            "e": 0.005,
            "unit": "kg",
        }
        resp = self.client.post("/calculations/tare", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["verdict"], "PASS")

    def test_post_temperature_endpoint(self):
        """POST /calculations/temperature calculates temperature effect."""
        payload = {
            "observations": [
                {"temperature_c": 20.0, "applied_load": 0.0, "indicated_value": 0.000},
                {"temperature_c": 20.0, "applied_load": 5.0, "indicated_value": 5.001},
                {"temperature_c": 40.0, "applied_load": 0.0, "indicated_value": 0.0005},
                {"temperature_c": 40.0, "applied_load": 5.0, "indicated_value": 5.0012},
            ],
            "accuracy_class": "CLASS_III",
            "e": 0.005,
            "unit": "kg",
        }
        resp = self.client.post("/calculations/temperature", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["verdict"], "PASS")

    def test_post_examination_endpoint(self):
        """POST /calculations/examination evaluates checklists."""
        payload = {
            "test_type": "CONSTRUCTION_EXAMINATION",
            "checklist_items": [
                {"item_id": "C1", "title": "Plate", "clause": "7.1", "status": "COMPLIANT"},
            ],
        }
        resp = self.client.post("/calculations/examination", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["verdict"], "PASS")

    def test_invalid_payload_returns_400(self):
        """Missing required parameters returns HTTP 400."""
        resp = self.client.post("/calculations/mpe", json={})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
