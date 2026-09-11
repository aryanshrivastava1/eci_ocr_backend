"""Scoped constituency resolution — hermetic tests.

Run with the project venv, from the repository root:

    venv/Scripts/python.exe -m unittest discover -s tests -v

These tests build an in-memory SQLite database. They never open
DATABASE_URL, never touch the production database, and never create a voters
table, so no voter row can be read or written by them.

The fixture mirrors rows that really exist in the loaded reference data, so the
ambiguity being tested is the real ambiguity and not an invented one:

  Kalyanpur          UP(9)  AC 211  Kanpur Nagar (157)
  Kalyanpur          BR(10) AC  16  Purbi Champaran (213)
  Kalyanpur          BR(10) AC 131  Samastipur (217)
  Ramnagar           UK(5)  AC  61 / BR(10) AC 2 / TR(16) AC 7 / WB(19) AC 217
  Bakshi Kaa Talab   UP(9)  AC 169  Lucknow (162)        -- globally unique
  Bilaspur           a district name in both HP(2) and CG(22)
"""

import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core import constituency_resolver as cr
from app.models.constituency import Constituency
from app.models.districts import District
from app.models.states import State

STATES = [
    (2, "2", "Himachal Pradesh"),
    (5, "5", "Uttarakhand"),
    (9, "9", "Uttar Pradesh"),
    (10, "10", "Bihar"),
    (16, "16", "Tripura"),
    (19, "19", "West Bengal"),
    (22, "22", "Chhattisgarh"),
]

# (district_id, state_id, lgd_district_code, name_en, name_hi)
DISTRICTS = [
    (127, 9, "162", "Lucknow", "लखनऊ"),
    (121, 9, "157", "Kanpur Nagar", "कानपुर नगर"),
    (2400, 10, "213", "Purbi Champaran", None),
    (2404, 10, "217", "Samastipur", None),
    (2960, 5, "65", "Nainital", None),
    (2398, 10, "211", "Pashchim Champaran", None),
    (2953, 16, "292", "Gomati", None),
    (2986, 19, "320", "Purba Medinipur", None),
    (2519, 2, "15", "Bilaspur", None),
    (2419, 22, "375", "Bilaspur", None),
]

# (id, state_id, ac_number, name_en, name_hi, district_id, lgd_district_code)
CONSTITUENCIES = [
    # the 9 legacy Lucknow rows, with their legacy ids and genuine Hindi
    (20, 9, 168, "Malihabad", "मलिहाबाद", 127, "162"),
    (13, 9, 169, "Bakshi Kaa Talab", "बक्शी का तालाब", 127, "162"),
    (21, 9, 170, "Sarojini Nagar", "सरोजिनी नगर", 127, "162"),
    (17, 9, 171, "Lucknow West", "लखनऊ पश्चिम", 127, "162"),
    (14, 9, 172, "Lucknow North", "लखनऊ उत्तर", 127, "162"),
    (15, 9, 173, "Lucknow East", "लखनऊ पूर्व", 127, "162"),
    (16, 9, 174, "Lucknow Central", "लखनऊ मध्य", 127, "162"),
    (18, 9, 175, "Lucknow Cantonment", "लखनऊ छावनी", 127, "162"),
    (19, 9, 176, "Mohanlalganj", "मोहनलालगंज", 127, "162"),
    # Kalyanpur: once in UP, twice in Bihar in two different districts
    (10999, 9, 211, "Kalyanpur", None, 121, "157"),
    (11354, 10, 16, "Kalyanpur", None, 2400, "213"),
    (11382, 10, 131, "Kalyanpur", None, 2404, "217"),
    # Ramnagar: four states
    (20001, 5, 61, "Ramnagar", None, 2960, "65"),
    (20002, 10, 2, "Ramnagar", None, 2398, "211"),
    (20003, 16, 7, "RAMNAGAR", None, 2953, "292"),
    (20004, 19, 217, "RAMNAGAR", None, 2986, "320"),
    # a row with no district attribution, as Delhi's 70 rows have
    (20005, 22, 1, "Bharatpur-Sonhat", None, None, None),
]


class ResolverTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        for table in (State.__table__, District.__table__,
                      Constituency.__table__):
            table.create(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)
        db = cls.Session()
        db.add_all([State(state_id=i, state_code=c, state_name_en=n)
                    for i, c, n in STATES])
        db.add_all([District(district_id=i, state_id=s, lgd_district_code=c,
                             district_name_en=en, district_name_hi=hi)
                    for i, s, c, en, hi in DISTRICTS])
        db.add_all([Constituency(id=i, state_id=s, ac_number=ac,
                                 constituency=en, constituency_hindi=hi,
                                 district=None, district_id=d,
                                 lgd_district_code=c)
                    for i, s, ac, en, hi, d, c in CONSTITUENCIES])
        db.commit()
        db.close()

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    # -- A ---------------------------------------------------------------
    def test_A_existing_lucknow_ac_resolves(self):
        """The existing Lucknow workflow still resolves, by Hindi name."""
        r = cr.resolve(self.db, "लखनऊ मध्य",
                       state_name="उत्तर प्रदेश", district_name="लखनऊ")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.constituency_id, 16)
        self.assertEqual(r.match.ac_number, 174)
        self.assertEqual(r.match.state_code, "9")
        self.assertEqual(r.scope.lgd_district_code, "162")
        self.assertEqual(r.scope.level, "district")

    def test_A2_all_nine_legacy_lucknow_acs_resolve(self):
        """All 9 legacy rows resolve to their own id and ECI AC number."""
        for cid, _s, ac, en, hi, _d, _c in CONSTITUENCIES[:9]:
            for probe in (en, hi):
                r = cr.resolve(self.db, probe, state_code="9",
                               district_lgd_code="162")
                self.assertTrue(r.resolved, "%s: %s" % (probe, r.reason))
                self.assertEqual(r.match.constituency_id, cid, probe)
                self.assertEqual(r.match.ac_number, ac, probe)
        # and the legacy ids are exactly 13..21
        self.assertEqual(sorted(c[0] for c in CONSTITUENCIES[:9]),
                         list(range(13, 22)))

    def test_A3_legacy_cantonment_name_still_resolves(self):
        """The legacy spelling differs from ECI's; both must resolve to 175."""
        r = cr.resolve(self.db, "Lucknow Cantonment", state_code="9")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.constituency_id, 18)
        self.assertEqual(r.match.ac_number, 175)

    # -- B ---------------------------------------------------------------
    def test_B_same_name_two_states_state_selects_correctly(self):
        """Kalyanpur exists in UP and Bihar; the state decides."""
        r = cr.resolve(self.db, "Kalyanpur", state_code="9")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.state_code, "9")
        self.assertEqual(r.match.ac_number, 211)
        self.assertEqual(r.match.constituency_id, 10999)

    def test_B2_state_by_english_name(self):
        r = cr.resolve(self.db, "Kalyanpur", state_name="Uttar Pradesh")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.ac_number, 211)

    def test_B3_ramnagar_each_of_four_states(self):
        for code, ac in (("5", 61), ("10", 2), ("16", 7), ("19", 217)):
            r = cr.resolve(self.db, "Ramnagar", state_code=code)
            self.assertTrue(r.resolved, "%s: %s" % (code, r.reason))
            self.assertEqual(r.match.state_code, code)
            self.assertEqual(r.match.ac_number, ac)

    def test_B4_state_alone_insufficient_when_name_repeats_in_state(self):
        """Kalyanpur appears twice in Bihar — state alone is not enough."""
        r = cr.resolve(self.db, "Kalyanpur", state_code="10")
        self.assertFalse(r.resolved)
        self.assertEqual(r.status, cr.UNRESOLVED_AMBIGUOUS)
        self.assertIsNone(r.match)
        self.assertEqual(len(r.candidates), 2)
        self.assertIn("district_lgd_code", r.required)

    # -- C ---------------------------------------------------------------
    def test_C_same_name_two_districts_district_selects_correctly(self):
        r = cr.resolve(self.db, "Kalyanpur", state_code="10",
                       district_lgd_code="217")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.ac_number, 131)
        self.assertEqual(r.match.constituency_id, 11382)

        r = cr.resolve(self.db, "Kalyanpur", state_code="10",
                       district_lgd_code="213")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.ac_number, 16)
        self.assertEqual(r.match.constituency_id, 11354)

    def test_C2_district_name_alone_carries_the_state(self):
        """A district name resolves the state too, so no state is needed."""
        r = cr.resolve(self.db, "Kalyanpur", district_name="Samastipur")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.ac_number, 131)
        self.assertEqual(r.scope.state_code, "10")
        self.assertIn("state derived from the resolved district",
                      r.scope.notes)

    def test_C3_duplicate_district_name_without_state_is_not_guessed(self):
        """Bilaspur is a district in two states — do not pick one."""
        district, note = cr.resolve_district(self.db, district_name="Bilaspur")
        self.assertIsNone(district)
        self.assertIn("a state is required", note)

    def test_C4_state_district_conflict_is_refused(self):
        """state_code 9 with a Bihar district code is a contradiction."""
        r = cr.resolve(self.db, "Kalyanpur", state_code="9",
                       district_lgd_code="217")
        self.assertEqual(r.status, cr.UNRESOLVED_SCOPE_CONFLICT)
        self.assertIsNone(r.match)

    # -- D ---------------------------------------------------------------
    def test_D_duplicate_global_name_without_scope_is_ambiguous(self):
        """The core regression: never silently take .first()."""
        r = cr.resolve(self.db, "Kalyanpur")
        self.assertFalse(r.resolved)
        self.assertEqual(r.status, cr.UNRESOLVED_AMBIGUOUS)
        self.assertIsNone(r.match)
        self.assertEqual(len(r.candidates), 3)
        self.assertEqual({c.state_code for c in r.candidates}, {"9", "10"})
        self.assertIn("state_code", r.required)

    def test_D2_ramnagar_without_scope_is_ambiguous_across_four_states(self):
        r = cr.resolve(self.db, "Ramnagar")
        self.assertEqual(r.status, cr.UNRESOLVED_AMBIGUOUS)
        self.assertIsNone(r.match)
        self.assertEqual({c.state_code for c in r.candidates},
                         {"5", "10", "16", "19"})

    def test_D3_legacy_wrapper_returns_none_on_ambiguity(self):
        """The two-argument OCR signature must refuse, not guess."""
        self.assertEqual(cr.resolve_constituency(self.db, "Kalyanpur"),
                         (None, None))

    # -- E ---------------------------------------------------------------
    def test_E_globally_unique_name_resolves_without_scope(self):
        r = cr.resolve(self.db, "Bakshi Kaa Talab")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.constituency_id, 13)
        self.assertEqual(r.match.ac_number, 169)
        self.assertEqual(r.scope.level, "global")
        self.assertEqual(r.method, "exact")

    def test_E2_globally_unique_hindi_name_resolves_without_scope(self):
        r = cr.resolve(self.db, "बक्शी का तालाब")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.ac_number, 169)

    def test_E3_unknown_name_is_not_found(self):
        r = cr.resolve(self.db, "Nowhere Constituency", state_code="9")
        self.assertEqual(r.status, cr.UNRESOLVED_NOT_FOUND)
        self.assertIsNone(r.match)

    # -- F ---------------------------------------------------------------
    def test_F_fuzzy_candidates_are_state_scoped(self):
        """A misspelling must not cross a state boundary."""
        r = cr.resolve(self.db, "Kalyanpurr", state_code="9")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.method, "fuzzy")
        self.assertEqual(r.match.state_code, "9")
        self.assertEqual(r.match.ac_number, 211)

    def test_F2_fuzzy_candidates_are_district_scoped(self):
        r = cr.resolve(self.db, "Kalyanpurr", state_code="10",
                       district_lgd_code="217")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.method, "fuzzy")
        self.assertEqual(r.match.ac_number, 131)

    def test_F3_noisy_hindi_resolves_within_the_district(self):
        r = cr.resolve(self.db, "विधान सभा क्षेत्र लखनऊ मध्य",
                       district_name="जिला : लखनऊ")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.ac_number, 174)

    def test_F4_bare_lucknow_still_ties_and_stays_unresolved(self):
        """Preserved behaviour: 'लखनऊ' ties across every 'लखनऊ ...' AC."""
        r = cr.resolve(self.db, "लखनऊ", district_lgd_code="162")
        self.assertFalse(r.resolved)
        self.assertEqual(r.status, cr.UNRESOLVED_AMBIGUOUS)
        self.assertIsNone(r.match)
        self.assertGreater(len(r.candidates), 1)

    def test_F5_threshold_unchanged(self):
        self.assertEqual(cr._MATCH_THRESHOLD, 65)

    def test_F6_misspelling_without_scope_never_guesses(self):
        """Unscoped fuzzy must not pick a state for the caller.

        Unscoped, the candidate pool is narrowed in SQL by a token of the
        input, so a misspelling ("Kalyanpurr") matches nothing rather than
        being fuzzy-matched across four states. Safe, and the result tells the
        caller that a state would let the fuzzy search run.
        """
        r = cr.resolve(self.db, "Kalyanpurr")
        self.assertFalse(r.resolved)
        self.assertIsNone(r.match)
        self.assertEqual(r.candidates, [])
        self.assertIn("state_code", r.required)

    def test_F6b_unscoped_fuzzy_spanning_states_is_ambiguous(self):
        """When an unscoped fuzzy search does reach several states, refuse.

        "Ramnaga" is contained in no name, so use a token that is: the pool
        for "Ramnagar x" narrows to all four Ramnagar rows, and the plausible
        set then spans four States/UTs.
        """
        r = cr.resolve(self.db, "Ramnagar Purba")
        self.assertFalse(r.resolved)
        self.assertEqual(r.status, cr.UNRESOLVED_AMBIGUOUS)
        self.assertIsNone(r.match)
        self.assertGreater(len({c.state_code for c in r.candidates}), 1)
        self.assertIn("state_code", r.required)

    def test_F7_devanagari_is_preserved_not_transliterated(self):
        r = cr.resolve(self.db, "लखनऊ उत्तर", district_lgd_code="162")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.constituency_hindi, "लखनऊ उत्तर")

    def test_F8_nfc_normalisation_is_applied(self):
        import unicodedata
        decomposed = unicodedata.normalize("NFD", "लखनऊ मध्य")
        r = cr.resolve(self.db, decomposed, district_lgd_code="162")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.ac_number, 174)

    # -- G ---------------------------------------------------------------
    def test_G_voter_save_payload_shape_resolves(self):
        """Exactly what POST /voters/save passes, for the Lucknow flow."""
        r = cr.resolve(
            self.db,
            "लखनऊ मध्य",                # payload.assembly_constituency_name
            state_code=None,             # payload.state_code (new, optional)
            state_name="उत्तर प्रदेश",   # payload.state
            district_lgd_code=None,      # payload.district_lgd_code (new)
            district_name="लखनऊ",        # payload.district
        )
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.constituency_id, 16)
        # The voter would be attached to constituency.id 16, which is exactly
        # what the 5 existing Lucknow Central voters already reference.

    def test_G2_voter_save_english_name_only_still_works_for_unique_name(self):
        r = cr.resolve(self.db, "Mohanlalganj")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.constituency_id, 19)

    def test_G3_voter_save_ambiguous_payload_yields_actionable_error(self):
        r = cr.resolve(self.db, "Kalyanpur")
        self.assertFalse(r.resolved)
        payload = r.to_dict()
        self.assertEqual(payload["status"], cr.UNRESOLVED_AMBIGUOUS)
        self.assertIsNone(payload["match"])
        self.assertEqual(len(payload["candidates"]), 3)
        self.assertIn("state_code", payload["required"])
        for cand in payload["candidates"]:
            self.assertIn("state_code", cand)
            self.assertIn("ac_number", cand)

    def test_G4_missing_name_is_rejected(self):
        for probe in (None, "", "   "):
            r = cr.resolve(self.db, probe)
            self.assertFalse(r.resolved)
            self.assertIsNone(r.match)

    def test_G5_row_without_district_attribution_still_resolves(self):
        """104 loaded rows have a NULL district_id (Delhi and needs_review)."""
        r = cr.resolve(self.db, "Bharatpur-Sonhat", state_code="22")
        self.assertTrue(r.resolved, r.reason)
        self.assertIsNone(r.match.district_id)
        self.assertIsNone(r.match.district_name_en)

    # -- H ---------------------------------------------------------------
    def test_H_no_voters_table_exists_in_the_test_database(self):
        """Structural proof that no test can read or write a voter row."""
        names = [r[0] for r in self.db.execute(
            text("select name from sqlite_master where type='table'"))]
        self.assertNotIn("voters", names)
        self.assertEqual(sorted(names),
                         ["constituency", "districts", "states"])

    def test_H2_test_database_is_in_memory_not_production(self):
        self.assertEqual(str(self.engine.url), "sqlite://")

    def test_H3_reference_rows_unchanged_by_the_test_run(self):
        self.assertEqual(
            self.db.execute(text("select count(*) from constituency")).scalar(),
            len(CONSTITUENCIES))
        self.assertEqual(
            self.db.execute(text("select count(*) from districts")).scalar(),
            len(DISTRICTS))
        self.assertEqual(
            self.db.execute(text("select count(*) from states")).scalar(),
            len(STATES))


if __name__ == "__main__":
    unittest.main(verbosity=2)
