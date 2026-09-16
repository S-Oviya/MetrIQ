"""
MetrIQ Regulatory Engine - Comprehensive Rule Versioning & Audit Tests
======================================================================
Tests the complete regulatory profile system:
1. Regulatory profile lifecycle statuses (ACTIVE, DRAFT, SUPERSEDED, MANUAL_REVIEW).
2. Version selection by jurisdiction, effective date, and lifecycle state.
3. Data-driven overrides for MPE tables, statutory fees, GATC eligibility,
   test weight substitution ratios, state-specific rules, and re-verification periods.
4. G.S.R. 568(E) isolation (stored as MANUAL_REVIEW, non-authoritative, pending verification).
5. Audit trace verification answering: "Why did the system apply this rule?"
   with all 5 required components:
   - Rule ID
   - Source document
   - Clause
   - Regulatory version
   - Effective date
6. API endpoint integration with versioning filters.
"""

import unittest
from decimal import Decimal

from app.regulatory.models import AccuracyClass
from app.regulatory.mpe_engine import MPEEngine, MPEBandDefinition, VerificationType
from app.regulatory.profile import (
    ProfileStatus,
    RuleAuditTrace,
    RegulatoryProfile,
    RegulatoryProfileRegistry,
    PROFILE_REGISTRY,
    DEFAULT_INDIAN_LM_PROFILE,
    DRAFT_GSR_568E_PROFILE,
    SUPERSEDED_LM_2009_PROFILE,
    INTERNATIONAL_OIML_PROFILE,
    STATE_MAHARASHTRA_PROFILE,
)
from app.regulatory.test_plan_generator import RegulatoryTestPlanGenerator
from app.regulatory.api import (
    get_regulatory_profile_api,
    calculate_mpe_api,
    generate_test_plan_api,
    RegulatoryAPI,
)


class TestRegulatoryProfileModel(unittest.TestCase):
    """Verifies profile metadata, structure, and lifecycle enum support."""

    def test_lifecycle_statuses_supported(self):
        """Must support ACTIVE, DRAFT, SUPERSEDED, and MANUAL_REVIEW."""
        self.assertEqual(ProfileStatus.ACTIVE.value, "ACTIVE")
        self.assertEqual(ProfileStatus.DRAFT.value, "DRAFT")
        self.assertEqual(ProfileStatus.SUPERSEDED.value, "SUPERSEDED")
        self.assertEqual(ProfileStatus.MANUAL_REVIEW.value, "MANUAL_REVIEW")

    def test_profile_required_attributes(self):
        """Profile must contain all core required metadata fields."""
        prof = DEFAULT_INDIAN_LM_PROFILE
        self.assertEqual(prof.profile_id, "IN_LM_2011_ACTIVE")
        self.assertEqual(prof.jurisdiction, "INDIA")
        self.assertIn("Legal Metrology (General) Rules, 2011", prof.regulation_name)
        self.assertEqual(prof.version, "2011.1-CURRENT")
        self.assertEqual(prof.effective_from, "2011-04-01")
        self.assertIsNone(prof.effective_to)
        self.assertIn("Ministry of Consumer Affairs", prof.source)
        self.assertEqual(prof.verification_status, ProfileStatus.ACTIVE)
        self.assertTrue(prof.is_authoritative)
        self.assertIsInstance(prof.rules, dict)

    def test_profile_serialization(self):
        """to_dict produces complete JSON-compatible representation."""
        data = DEFAULT_INDIAN_LM_PROFILE.to_dict()
        self.assertEqual(data["profile_id"], "IN_LM_2011_ACTIVE")
        self.assertEqual(data["verification_status"], "ACTIVE")
        self.assertTrue(data["is_authoritative"])
        self.assertIn("fees", data)
        self.assertIn("gatc_applicability", data)
        self.assertIn("test_weight_substitution", data)


class TestProfileVersionSelection(unittest.TestCase):
    """Tests version selection by effective date, status, and jurisdiction."""

    def setUp(self):
        self.registry = RegulatoryProfileRegistry()

    def test_effective_date_evaluation(self):
        """Profiles evaluate correctly against past, present, and future dates."""
        # 2009 profile effective 1987-01-01 to 2011-03-31
        hist = SUPERSEDED_LM_2009_PROFILE
        self.assertTrue(hist.is_effective("2000-01-01"))
        self.assertTrue(hist.is_effective("2011-03-30"))
        # Beyond 2011-03-31 it is not effective
        self.assertFalse(hist.is_effective("2011-04-01"))
        self.assertFalse(hist.is_effective("2026-01-01"))

        # 2011 profile effective from 2011-04-01 onward
        active = DEFAULT_INDIAN_LM_PROFILE
        self.assertFalse(active.is_effective("2010-01-01"))
        self.assertTrue(active.is_effective("2011-04-01"))
        self.assertTrue(active.is_effective("2026-09-01"))

    def test_select_profile_historical_date(self):
        """Historical date 2010-05-01 selects the 2009 superseded baseline."""
        selected = self.registry.select_profile(jurisdiction="INDIA", at_date="2010-05-01")
        self.assertEqual(selected.profile_id, "IN_LM_HISTORIC_2009_SUPERSEDED")

    def test_select_profile_current_date(self):
        """Current date selects the verified ACTIVE Indian 2011 profile."""
        selected = self.registry.select_profile(jurisdiction="INDIA", at_date="2026-03-15")
        self.assertEqual(selected.profile_id, "IN_LM_2011_ACTIVE")
        self.assertEqual(selected.verification_status, ProfileStatus.ACTIVE)

    def test_select_profile_future_draft_isolated_by_default(self):
        """Draft/Manual review profile is NOT returned unless explicitly authorized."""
        # Date after reported July 2026
        selected_default = self.registry.select_profile(
            jurisdiction="INDIA",
            at_date="2026-08-01",
            allow_manual_review=False,
        )
        self.assertEqual(selected_default.profile_id, "IN_LM_2011_ACTIVE")

        # With allow_manual_review=True, it selects the draft profile
        selected_draft = self.registry.select_profile(
            jurisdiction="INDIA",
            at_date="2026-08-01",
            allow_manual_review=True,
        )
        self.assertEqual(selected_draft.profile_id, "IN_LM_2026_GSR568E_DRAFT")

    def test_list_profiles_by_status(self):
        """Listing profiles filters correctly by lifecycle status."""
        superseded = self.registry.list_profiles(status=ProfileStatus.SUPERSEDED)
        self.assertTrue(any(p.profile_id == "IN_LM_HISTORIC_2009_SUPERSEDED" for p in superseded))

        manual_review = self.registry.list_profiles(status=ProfileStatus.MANUAL_REVIEW)
        self.assertTrue(any(p.profile_id == "IN_LM_2026_GSR568E_DRAFT" for p in manual_review))

        active = self.registry.list_profiles(status=ProfileStatus.ACTIVE)
        self.assertTrue(any(p.profile_id == "IN_LM_2011_ACTIVE" for p in active))
        self.assertTrue(any(p.profile_id == "OIML_R76_2006_ACTIVE" for p in active))

    def test_jurisdiction_selection(self):
        """State of Maharashtra profile is isolated to Maharashtra jurisdiction."""
        mh = self.registry.select_profile(jurisdiction="INDIA_MAHARASHTRA", at_date="2026-02-01")
        self.assertEqual(mh.profile_id, "STATE_MAHARASHTRA_2026")


class TestDataDrivenMPECustomization(unittest.TestCase):
    """
    Verifies that MPE tables can be modified via data configuration
    without rewriting the MPE engine code.
    """

    def test_custom_mpe_bands_without_code_rewrite(self):
        """Custom tight aerospace profile with 0.25e / 0.75e / 1.0e tolerances."""
        custom_profile = RegulatoryProfile(
            profile_id="AEROSPACE_CALIBRATION_2026",
            jurisdiction="AEROSPACE_PRECISION",
            regulation_name="Aerospace High-Precision Weighing Standard",
            version="2026.1",
            effective_from="2026-01-01",
            effective_to=None,
            source="Aerospace Metrology Directive 2026",
            verification_status=ProfileStatus.ACTIVE,
            mpe_tables={
                "III": [
                    {
                        "band_index": 1,
                        "min_load_e": 0,
                        "max_load_e": 500,
                        "mpe_initial_e": 0.25,
                        "mpe_subsequent_e": 0.50,
                        "inclusive_lower": True,
                        "inclusive_upper": True,
                        "description": "0 <= m <= 500 e (Aerospace Tight)",
                    },
                    {
                        "band_index": 2,
                        "min_load_e": 500,
                        "max_load_e": 2000,
                        "mpe_initial_e": 0.75,
                        "mpe_subsequent_e": 1.50,
                        "inclusive_lower": False,
                        "inclusive_upper": True,
                        "description": "500 < m <= 2000 e (Aerospace Tight)",
                    },
                ]
            },
        )

        # Statutory default MPE for Class III at 250e is +/- 0.5e
        std_res = MPEEngine.calculate(
            accuracy_class="III",
            load=250.0,
            e=1.0,
            verification_type=VerificationType.INITIAL,
        )
        self.assertEqual(std_res.mpe_in_e, 0.5)

        # With aerospace custom profile, MPE at 250e is overridden to +/- 0.25e
        aero_res = MPEEngine.calculate(
            accuracy_class="III",
            load=250.0,
            e=1.0,
            verification_type=VerificationType.INITIAL,
            profile=custom_profile,
        )
        self.assertEqual(aero_res.mpe_in_e, 0.25)
        self.assertIn("Custom Profile MPE Table", aero_res.applicable_rule)
        self.assertIn("Aerospace Metrology Directive 2026", aero_res.source)


class TestDataDrivenFeesAndReVerification(unittest.TestCase):
    """Tests configurable fee schedules and re-verification periods."""

    def test_statutory_fee_schedule_tiers(self):
        """Active 2011 fee tiers based on capacity."""
        prof = DEFAULT_INDIAN_LM_PROFILE
        self.assertEqual(prof.get_fee("VERIFICATION", capacity_kg=25.0), 200.0)
        self.assertEqual(prof.get_fee("VERIFICATION", capacity_kg=150.0), 500.0)
        self.assertEqual(prof.get_fee("VERIFICATION", capacity_kg=3000.0), 2000.0)
        self.assertEqual(prof.get_fee("VERIFICATION", capacity_kg=20000.0), 5000.0)

    def test_model_approval_fee_comparison(self):
        """Verified statutory ₹25,000 vs reported G.S.R. 568(E) ₹50,000."""
        active = DEFAULT_INDIAN_LM_PROFILE
        draft = DRAFT_GSR_568E_PROFILE

        self.assertEqual(active.fees.get("model_approval_inr"), 25000.0)
        self.assertEqual(draft.fees.get("model_approval_inr"), 50000.0)

    def test_re_verification_periods(self):
        """Configurable inspection intervals."""
        prof = DEFAULT_INDIAN_LM_PROFILE
        self.assertEqual(prof.get_re_verification_period_months("COMMERCIAL_NAWI"), 12)
        self.assertEqual(prof.get_re_verification_period_months("PRECISION_LAB"), 24)

        # Draft GSR 568(E) reported semi-annual (6 months) for industrial weighbridges
        draft = DRAFT_GSR_568E_PROFILE
        self.assertEqual(draft.get_re_verification_period_months("INDUSTRIAL_WEIGHBRIDGE"), 6)


class TestDataDrivenGATCAndSubstitution(unittest.TestCase):
    """Tests GATC routing rules and standard test weight substitution limits."""

    def test_gatc_eligibility(self):
        """Class II up to 5000kg eligible; Class I or > 5000kg ineligible."""
        prof = DEFAULT_INDIAN_LM_PROFILE

        # Class II at 500 kg is eligible
        ok, msg = prof.is_gatc_eligible(AccuracyClass.CLASS_II, max_capacity_kg=500.0)
        self.assertTrue(ok)

        # Class I is NOT eligible (must be tested directly by State LM Officers)
        ok_cls1, msg_cls1 = prof.is_gatc_eligible(AccuracyClass.CLASS_I, max_capacity_kg=1.0)
        self.assertFalse(ok_cls1)
        self.assertIn("State Legal Metrology Officers", msg_cls1)

        # Capacity > 5000 kg exceeds ceiling
        ok_heavy, msg_heavy = prof.is_gatc_eligible(AccuracyClass.CLASS_III, max_capacity_kg=10000.0)
        self.assertFalse(ok_heavy)
        self.assertIn("exceeds maximum GATC", msg_heavy)

    def test_test_weight_substitution_ratio(self):
        """Statutory baseline 50% vs reported G.S.R. 568(E) 20% limit."""
        active = DEFAULT_INDIAN_LM_PROFILE
        draft = DRAFT_GSR_568E_PROFILE

        self.assertEqual(active.get_max_substitution_ratio(), 0.50)
        self.assertEqual(draft.get_max_substitution_ratio(), 0.20)


class TestGSR568EUncertaintyIsolation(unittest.TestCase):
    """
    CRITICAL STATUTORY SAFETY:
    G.S.R. 568(E) claims must NEVER be treated as verified law.
    Stored as MANUAL_REVIEW, non-authoritative, and flagged in test plans.
    """

    def test_gsr_568e_profile_attributes(self):
        """Verifies clear unverified flag and manual review status."""
        prof = DRAFT_GSR_568E_PROFILE
        self.assertEqual(prof.verification_status, ProfileStatus.MANUAL_REVIEW)
        self.assertFalse(prof.is_authoritative)
        self.assertIn("UNVERIFIED", prof.notes)
        self.assertIn("Verification Pending", prof.source)

    def test_gsr_568e_test_plan_flagged_for_manual_review(self):
        """When G.S.R. 568(E) profile is specified, test plan triggers manual review."""
        spec = {
            "accuracy_class": "III",
            "Max": 30.0,
            "e": 0.01,
            "unit": "kg",
            "profile_id": "IN_LM_2026_GSR568E_DRAFT",
        }
        plan = RegulatoryTestPlanGenerator.generate(spec)

        self.assertEqual(plan.profile_id, "IN_LM_2026_GSR568E_DRAFT")
        self.assertEqual(plan.profile_status, "MANUAL_REVIEW")
        self.assertFalse(plan.is_authoritative)
        self.assertTrue(plan.is_partial_plan)
        self.assertEqual(plan.test_weight_substitution_limit, 0.20)

        # Check manual review items contains notice
        mr_test_ids = [item["test_id"] for item in plan.manual_review_items]
        self.assertIn("PROFILE_MANUAL_REVIEW_REQUIRED", mr_test_ids)


class TestRuleAuditTrace(unittest.TestCase):
    """
    Answers: 'Why did the system apply this rule?'
    Must include:
    1. Rule ID
    2. Source document
    3. Clause
    4. Regulatory version
    5. Effective date
    """

    def test_audit_trace_answers_why_all_five_elements(self):
        """Audit trace contains all 5 required statutory elements."""
        prof = DEFAULT_INDIAN_LM_PROFILE
        trace = prof.create_audit_trace(
            rule_id="RULE_STATUTORY_MPE_BAND_1",
            applied_to="Load 10.0 kg (ratio 2000e) on Class III NAWI",
            rule_name="Class III MPE Band 2 Tolerance",
            clause="Seventh Schedule Table 2",
            rationale="Initial verification error shall not exceed +/- 1.0e.",
            parameters={"load_kg": 10.0, "e_kg": 0.005, "load_in_e": 2000.0},
        )

        self.assertIsInstance(trace, RuleAuditTrace)
        why_text = trace.answer_why()

        # 1. Rule ID
        self.assertIn("RULE_STATUTORY_MPE_BAND_1", why_text)
        self.assertEqual(trace.rule_id, "RULE_STATUTORY_MPE_BAND_1")

        # 2. Source Document
        self.assertIn(prof.source, why_text)
        self.assertEqual(trace.source_document, prof.source)

        # 3. Clause
        self.assertIn("Seventh Schedule Table 2", why_text)
        self.assertEqual(trace.clause, "Seventh Schedule Table 2")

        # 4. Regulatory Version
        self.assertIn(prof.version, why_text)
        self.assertEqual(trace.regulatory_version, prof.version)

        # 5. Effective Date
        self.assertIn(prof.effective_from, why_text)
        self.assertEqual(trace.effective_date, prof.effective_from)

    def test_mpe_engine_generates_audit_trace_when_profile_passed(self):
        """MPEEngine calculation embeds the complete audit trace."""
        res = MPEEngine.calculate(
            accuracy_class="II",
            load=500.0,
            e=0.1,
            profile=DEFAULT_INDIAN_LM_PROFILE,
        )
        self.assertIsNotNone(res.audit_trace)
        trace = res.audit_trace
        self.assertEqual(trace.rule_id, "RULE_STATUTORY_MPE")
        self.assertIn("2011", trace.regulatory_version)
        self.assertIn("2011-04-01", trace.effective_date)

        # Dictionary export includes audit explanation
        res_dict = res.to_dict()
        self.assertIn("audit_trace", res_dict)
        self.assertIn("audit_explanation", res_dict["audit_trace"])


class TestRegulatoryProfileAPI(unittest.TestCase):
    """Tests the /regulatory/profile endpoint and version queries."""

    def test_get_profile_default(self):
        """Default call returns active profile, registered profiles, and source list."""
        resp = get_regulatory_profile_api()
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertIn("active_profile", data)
        self.assertIn("registered_profiles", data)
        self.assertGreaterEqual(len(data["registered_profiles"]), 4)

    def test_get_profile_by_id(self):
        """Query specific profile by ID."""
        resp = get_regulatory_profile_api(profile_id="STATE_MAHARASHTRA_2026")
        self.assertEqual(resp["status_code"], 200)
        self.assertEqual(resp["data"]["profile_id"], "STATE_MAHARASHTRA_2026")
        self.assertEqual(resp["data"]["jurisdiction"], "INDIA_MAHARASHTRA")

    def test_get_profile_by_id_not_found(self):
        """Non-existent profile ID returns 404."""
        resp = get_regulatory_profile_api(profile_id="UNKNOWN_PROFILE_999")
        self.assertEqual(resp["status_code"], 404)
        self.assertEqual(resp["error"]["code"], "PROFILE_NOT_FOUND")

    def test_get_profile_by_status(self):
        """Filter profiles by lifecycle status."""
        resp = get_regulatory_profile_api(status="MANUAL_REVIEW")
        self.assertEqual(resp["status_code"], 200)
        profiles = resp["data"]["profiles"]
        self.assertTrue(all(p["verification_status"] == "MANUAL_REVIEW" for p in profiles))
        self.assertTrue(any(p["profile_id"] == "IN_LM_2026_GSR568E_DRAFT" for p in profiles))

    def test_get_profile_by_date(self):
        """Selects profile effective on historical date."""
        resp = get_regulatory_profile_api(date="2010-01-01")
        self.assertEqual(resp["status_code"], 200)
        self.assertEqual(resp["data"]["profile_id"], "IN_LM_HISTORIC_2009_SUPERSEDED")

    def test_calculate_mpe_api_with_profile(self):
        """POST /regulatory/mpe with profile_id returns audit trace."""
        payload = {
            "accuracy_class": "III",
            "load": 10.0,
            "e": 0.005,
            "profile_id": "IN_LM_2011_ACTIVE",
        }
        resp = calculate_mpe_api(payload)
        self.assertEqual(resp["status_code"], 200)
        self.assertIn("audit_trace", resp["data"])
        self.assertEqual(resp["data"]["audit_trace"]["rule_id"], "RULE_STATUTORY_MPE")

    def test_dispatch_get_profile_with_params(self):
        """RegulatoryAPI.dispatch routes GET /regulatory/profile with query params."""
        resp = RegulatoryAPI.dispatch(
            method="GET",
            path="/regulatory/profile",
            params={"profile_id": "OIML_R76_2006_ACTIVE"},
        )
        self.assertEqual(resp["status_code"], 200)
        self.assertEqual(resp["data"]["profile_id"], "OIML_R76_2006_ACTIVE")


if __name__ == "__main__":
    unittest.main()
