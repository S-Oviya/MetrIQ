"""
MetrIQ Regulatory Knowledge Base - Unit Test Suite
Verifies:
- Accurate loading and schemas of statutory data
- Accuracy class specifications (Class I, II, III, IIII)
- Distinction between Indian Legal, OIML Technical, and Practice Formats
- OIML R 76-2 is NOT treated as an Indian statutory requirement
- GATC routing rules:
    * Class III <= 150 kg -> GATC
    * Class III > 150 kg -> State LMO
    * Class IIII -> GATC
    * Class II -> State LMO (NOT routed to GATC)
- Fourth Amendment 2026 / G.S.R. 568(E):
    * Marked as NOT_OFFICIALLY_VERIFIED
    * ₹50,000 fee is NOT authoritative and is configurable
    * 20% substitution is NOT authoritative and is configurable
    * Requires regulatory confirmation
- Test weight accuracy requirements (<= 1/3 instrument MPE)
"""

import unittest
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.regulatory import (
    AccuracyClass,
    InstrumentProfile,
    JobType,
    MassUnit,
    KNOWLEDGE_BASE,
    RegulatoryKnowledgeBase,
    LegalOrigin,
    VerificationStatus,
    RuleCategory,
    evaluate_gatc_routing,
)
from app.regulatory.router import (
    api_get_knowledge_classes,
    api_get_knowledge_rules,
    api_evaluate_gatc_routing,
    api_get_unverified_amendments,
    api_get_test_weight_requirements,
)


class TestKnowledgeBaseLoading(unittest.TestCase):
    """Verifies that the knowledge base loads with versioning and sources."""

    def test_knowledge_base_initialization(self):
        self.assertIsNotNone(KNOWLEDGE_BASE)
        self.assertEqual(KNOWLEDGE_BASE.VERSION, "2026.1-IN-OIML")
        sources = KNOWLEDGE_BASE.list_sources()
        self.assertGreaterEqual(len(sources), 6)

        source_ids = {s["id"] for s in sources}
        self.assertIn("IN_ACT_2009", source_ids)
        self.assertIn("IN_GENERAL_RULES_2011", source_ids)
        self.assertIn("IN_GATC_RULES_2013", source_ids)
        self.assertIn("OIML_R76_1_2006", source_ids)
        self.assertIn("OIML_R76_2_2007", source_ids)


class TestAccuracyClassDefinitions(unittest.TestCase):
    """Verifies structured definitions for Classes I, II, III, IIII."""

    def test_all_four_classes_present(self):
        classes = KNOWLEDGE_BASE.list_accuracy_classes()
        self.assertEqual(len(classes), 4)
        acc_classes = {c.accuracy_class for c in classes}
        self.assertEqual(
            acc_classes,
            {AccuracyClass.CLASS_I, AccuracyClass.CLASS_II, AccuracyClass.CLASS_III, AccuracyClass.CLASS_IIII},
        )

    def test_class_i_specifications(self):
        class_i = KNOWLEDGE_BASE.get_accuracy_class_definition(AccuracyClass.CLASS_I)
        self.assertIsNotNone(class_i)
        self.assertEqual(class_i.e_ranges[0]["e_min_grams"], 0.001)
        self.assertEqual(class_i.e_ranges[0]["n_min"], 50000)
        self.assertIsNone(class_i.e_ranges[0]["n_max"])
        self.assertEqual(class_i.e_ranges[0]["min_capacity_factor"], 100)

        # MPE initial steps: 0.5e, 1.0e, 1.5e
        mpe_steps = class_i.mpe_thresholds_initial
        self.assertEqual(mpe_steps[0]["load_max_e"], 50000.0)
        self.assertEqual(mpe_steps[0]["mpe_e"], 0.5)
        self.assertEqual(mpe_steps[1]["load_max_e"], 200000.0)
        self.assertEqual(mpe_steps[1]["mpe_e"], 1.0)
        self.assertEqual(mpe_steps[2]["mpe_e"], 1.5)

    def test_class_ii_specifications(self):
        class_ii = KNOWLEDGE_BASE.get_accuracy_class_definition(AccuracyClass.CLASS_II)
        self.assertIsNotNone(class_ii)
        self.assertEqual(len(class_ii.e_ranges), 2)
        # Band A: 0.001 g <= e <= 0.05 g, n from 100 to 100,000, Min = 20e
        self.assertEqual(class_ii.e_ranges[0]["min_capacity_factor"], 20)
        self.assertEqual(class_ii.e_ranges[0]["n_min"], 100)
        # Band B: e >= 0.1 g, n from 5000 to 100,000, Min = 50e
        self.assertEqual(class_ii.e_ranges[1]["min_capacity_factor"], 50)
        self.assertEqual(class_ii.e_ranges[1]["n_min"], 5000)

    def test_class_iii_specifications(self):
        class_iii = KNOWLEDGE_BASE.get_accuracy_class_definition(AccuracyClass.CLASS_III)
        self.assertIsNotNone(class_iii)
        self.assertEqual(len(class_iii.e_ranges), 2)
        # Band B (e >= 5g): n_min = 500, n_max = 10000, Min = 20e
        band_b = [r for r in class_iii.e_ranges if r["e_min_grams"] == 5.0][0]
        self.assertEqual(band_b["n_min"], 500)
        self.assertEqual(band_b["n_max"], 10000)
        self.assertEqual(band_b["min_capacity_factor"], 20)

    def test_class_iiii_specifications(self):
        class_iiii = KNOWLEDGE_BASE.get_accuracy_class_definition(AccuracyClass.CLASS_IIII)
        self.assertIsNotNone(class_iiii)
        self.assertEqual(class_iiii.e_ranges[0]["e_min_grams"], 5.0)
        self.assertEqual(class_iiii.e_ranges[0]["n_min"], 100)
        self.assertEqual(class_iiii.e_ranges[0]["n_max"], 1000)
        self.assertEqual(class_iiii.e_ranges[0]["min_capacity_factor"], 10)


class TestStatutoryVsTechnicalDistinction(unittest.TestCase):
    """Verifies that the engine strictly separates Indian Law, OIML Standards, and Practice formats."""

    def test_oiml_r76_2_is_not_indian_statutory(self):
        rule = KNOWLEDGE_BASE.get_rule("RULE_OIML_R76_2_REPORT_FORMAT")
        self.assertIsNotNone(rule)
        # Must be classified as PRACTICE_REPORT_FORMAT
        self.assertEqual(rule.citation.legal_origin, LegalOrigin.PRACTICE_REPORT_FORMAT)
        # Must NOT be marked as an Indian statutory requirement
        self.assertFalse(rule.citation.is_indian_statutory)
        self.assertFalse(rule.parameters["is_indian_statutory"])

    def test_indian_statutory_rules_query(self):
        indian_rules = KNOWLEDGE_BASE.get_indian_statutory_rules()
        self.assertGreater(len(indian_rules), 5)
        for r in indian_rules:
            self.assertEqual(r.citation.legal_origin, LegalOrigin.INDIAN_STATUTORY)
            self.assertTrue(r.citation.is_indian_statutory)

    def test_oiml_technical_rules_query(self):
        oiml_rules = KNOWLEDGE_BASE.get_oiml_technical_rules()
        self.assertGreater(len(oiml_rules), 2)
        for r in oiml_rules:
            self.assertEqual(r.citation.legal_origin, LegalOrigin.OIML_TECHNICAL)
            self.assertFalse(r.citation.is_indian_statutory)


class TestGATCRoutingRules(unittest.TestCase):
    """Verifies GATC routing under Legal Metrology (GATC) Rules, 2013."""

    def test_class_iii_under_150kg_eligible(self):
        # Class III retail scale Max = 30 kg <= 150 kg -> GATC Eligible
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=30.0,
            unit=MassUnit.KG,
        )
        decision = evaluate_gatc_routing(inst)
        self.assertTrue(decision.eligible_for_gatc)
        self.assertEqual(decision.target_authority, "GATC")

    def test_class_iii_exactly_150kg_eligible(self):
        # Class III scale Max = 150 kg -> GATC Eligible
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=150.0,
            unit=MassUnit.KG,
        )
        decision = evaluate_gatc_routing(inst)
        self.assertTrue(decision.eligible_for_gatc)
        self.assertEqual(decision.target_authority, "GATC")

    def test_class_iii_over_150kg_routed_to_state_lmo(self):
        # Class III platform scale Max = 300 kg > 150 kg -> NOT GATC Eligible -> Routed to State LMO
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=300.0,
            unit=MassUnit.KG,
        )
        decision = evaluate_gatc_routing(inst)
        self.assertFalse(decision.eligible_for_gatc)
        self.assertEqual(decision.target_authority, "STATE_LEGAL_METROLOGY_OFFICER")
        self.assertIn("exceeds the 150 kg statutory threshold", decision.reason)

    def test_class_iiii_eligible(self):
        # Class IIII scale of any commercial capacity -> GATC Eligible
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_IIII,
            max_capacity=1000.0,
            unit=MassUnit.KG,
        )
        decision = evaluate_gatc_routing(inst)
        self.assertTrue(decision.eligible_for_gatc)
        self.assertEqual(decision.target_authority, "GATC")

    def test_class_ii_strictly_not_routed_to_gatc(self):
        # Class II jewelers / gold scale -> MUST NOT be routed to GATC!
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=6000.0,
            unit=MassUnit.G,  # 6 kg
        )
        decision = evaluate_gatc_routing(inst)
        self.assertFalse(decision.eligible_for_gatc)
        self.assertEqual(decision.target_authority, "STATE_LEGAL_METROLOGY_OFFICER")
        self.assertIn("Class II (High Accuracy) instruments", decision.reason)
        self.assertIn("NOT authorized for GATC verification", decision.reason)

    def test_class_i_not_routed_to_gatc(self):
        # Class I analytical balance -> NOT GATC Eligible
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=220.0,
            unit=MassUnit.G,
        )
        decision = evaluate_gatc_routing(inst)
        self.assertFalse(decision.eligible_for_gatc)
        self.assertEqual(decision.target_authority, "STATE_LEGAL_METROLOGY_OFFICER")


class TestUnverifiedFourthAmendment2026(unittest.TestCase):
    """Verifies strict handling of G.S.R. 568(E) Fourth Amendment 2026."""

    def test_fourth_amendment_is_unverified(self):
        unverified = KNOWLEDGE_BASE.get_unverified_rules()
        self.assertGreaterEqual(len(unverified), 2)
        rule_ids = {r.rule_id for r in unverified}
        self.assertIn("RULE_UNVERIFIED_2026_FEE", rule_ids)
        self.assertIn("RULE_UNVERIFIED_2026_SUBSTITUTION", rule_ids)

        for r in unverified:
            self.assertEqual(r.citation.verification_status, VerificationStatus.NOT_OFFICIALLY_VERIFIED)
            self.assertTrue(r.requires_regulatory_confirmation)

    def test_fee_is_not_authoritative_and_configurable(self):
        fee_rule = KNOWLEDGE_BASE.get_rule("RULE_UNVERIFIED_2026_FEE")
        self.assertIsNotNone(fee_rule)
        # Not hard-coded as authoritative
        self.assertFalse(fee_rule.parameters["is_authoritative"])
        self.assertTrue(fee_rule.is_configurable)
        self.assertEqual(fee_rule.parameters["reported_fee_inr"], 50000.0)

    def test_substitution_is_not_authoritative_and_configurable(self):
        sub_rule = KNOWLEDGE_BASE.get_rule("RULE_UNVERIFIED_2026_SUBSTITUTION")
        self.assertIsNotNone(sub_rule)
        # Not hard-coded as authoritative
        self.assertFalse(sub_rule.parameters["is_authoritative"])
        self.assertTrue(sub_rule.is_configurable)
        self.assertEqual(sub_rule.parameters["reported_substitution_ratio"], 0.20)
        self.assertEqual(sub_rule.parameters["verified_standard_substitution_ratio"], 0.50)


class TestMetrologicalRuleSpecifications(unittest.TestCase):
    """Verifies test weight accuracy, eccentricity, repeatability, and discrimination rules."""

    def test_test_weight_accuracy_ratio(self):
        weight_rule = KNOWLEDGE_BASE.get_rule("RULE_TEST_WEIGHT_ACCURACY")
        self.assertIsNotNone(weight_rule)
        self.assertAlmostEqual(weight_rule.parameters["max_test_weight_mpe_ratio"], 1.0 / 3.0)

        inst_class_iii = InstrumentProfile(accuracy_class=AccuracyClass.CLASS_III)
        req = KNOWLEDGE_BASE.get_test_weight_requirement(inst_class_iii)
        self.assertIn("M1", req["recommended_test_weight_classes"])
        self.assertIn("1/3 of instrument MPE", req["max_weight_error_ratio"])

    def test_eccentricity_rule(self):
        ecc_rule = KNOWLEDGE_BASE.get_rule("RULE_ECCENTRICITY_LOAD")
        self.assertIsNotNone(ecc_rule)
        self.assertAlmostEqual(ecc_rule.parameters["standard_platter_ratio"], 1.0 / 3.0)

    def test_discrimination_rule(self):
        disc_rule = KNOWLEDGE_BASE.get_rule("RULE_DIGITAL_DISCRIMINATION")
        self.assertIsNotNone(disc_rule)
        self.assertEqual(disc_rule.parameters["extra_load_factor"], 1.4)


class TestKnowledgeBaseAPIFunctions(unittest.TestCase):
    """Verifies router integration functions for Person 1."""

    def test_api_get_knowledge_classes(self):
        res = api_get_knowledge_classes()
        self.assertEqual(len(res), 4)

    def test_api_get_knowledge_rules(self):
        res = api_get_knowledge_rules(category="TEST_WEIGHTS")
        self.assertGreater(len(res), 0)

    def test_api_evaluate_gatc_routing(self):
        payload = {
            "instrument": {
                "accuracy_class": "CLASS_III",
                "max_capacity": 60.0,
                "unit": "kg",
            }
        }
        res = api_evaluate_gatc_routing(payload)
        self.assertTrue(res["eligible_for_gatc"])
        self.assertEqual(res["target_authority"], "GATC")

    def test_api_get_unverified_amendments(self):
        res = api_get_unverified_amendments()
        self.assertGreaterEqual(len(res), 2)
        for item in res:
            self.assertEqual(item["citation"]["verification_status"], "NOT_OFFICIALLY_VERIFIED")


if __name__ == "__main__":
    unittest.main()
