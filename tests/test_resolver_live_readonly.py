"""Scoped resolution against the real production reference data — READ ONLY.

Skipped unless explicitly enabled, so the default test run stays hermetic:

    PRAMAAN_LIVE_DB_TESTS=1 venv/Scripts/python.exe -m unittest \
        tests.test_resolver_live_readonly -v

Every connection sets `SET TRANSACTION READ ONLY` and asserts it is `on`
before running a single query, and the session is rolled back in teardown.
No INSERT, UPDATE or DELETE appears anywhere in this file, and the voters
table is only ever counted and read.
"""

import os
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core import constituency_resolver as cr

LIVE = os.getenv("PRAMAAN_LIVE_DB_TESTS") == "1"

EXPECTED_VOTER_PKS = [
    ("2e3beab9-917d-42f8-a044-643bffcfd693", 14),
    ("35c7f119-854c-4afd-a8d8-193266d71b12", 14),
    ("49a4f922-3b20-4ae7-a5bc-c9751ad4d92b", 14),
    ("199253c6-49cd-438c-bc0b-6898a83abef7", 16),
    ("54472274-ce21-4090-bdef-e3382a3ec07c", 16),
    ("803df057-8d8e-4998-ac34-ab6d01423a7d", 16),
    ("8496774b-e627-4ece-9e7a-b916cfdb810b", 16),
    ("b2b6caa5-e41f-4081-b635-350a4a8a222d", 16),
]


@unittest.skipUnless(LIVE, "set PRAMAAN_LIVE_DB_TESTS=1 to run read-only "
                           "checks against the production database")
class LiveReadOnlyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
        cls.engine = create_engine(os.environ["DATABASE_URL"])
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        self.db.execute(text("SET TRANSACTION READ ONLY"))
        self.assertEqual(
            self.db.execute(text("SHOW transaction_read_only")).scalar(), "on",
            "refusing to run: the session is not read-only")

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    # -- production state verification -----------------------------------
    def test_counts(self):
        one = lambda s: self.db.execute(text(s)).scalar()  # noqa: E731
        self.assertEqual(one("select count(*) from states"), 36)
        self.assertEqual(one("select count(*) from districts"), 784)
        self.assertEqual(one("select count(*) from constituency"), 3551)
        self.assertEqual(one("select count(*) from voters"), 8)

    def test_voter_pks_unchanged(self):
        rows = [(str(r[0]), r[1]) for r in self.db.execute(text(
            "select id, assembly_constituency_id from voters "
            "order by assembly_constituency_id, id"))]
        self.assertEqual(rows, EXPECTED_VOTER_PKS)

    def test_voter_reference_distribution_unchanged(self):
        rows = dict(self.db.execute(text(
            "select assembly_constituency_id, count(*) from voters "
            "group by 1")).all())
        self.assertEqual(rows, {14: 3, 16: 5})

    def test_legacy_constituency_ids_unchanged(self):
        rows = [r[0] for r in self.db.execute(text(
            "select id from constituency where id <= 21 order by id"))]
        self.assertEqual(rows, list(range(13, 22)))

    def test_legacy_district_ids_unchanged(self):
        n = self.db.execute(text(
            "select count(*) from districts "
            "where district_id between 79 and 153")).scalar()
        self.assertEqual(n, 75)

    # -- resolution against real data ------------------------------------
    def test_lucknow_voter_flow_resolves_to_the_live_rows(self):
        """The two constituencies the 8 existing voters reference."""
        for hindi, cid, ac in (("लखनऊ उत्तर", 14, 172),
                               ("लखनऊ मध्य", 16, 174)):
            r = cr.resolve(self.db, hindi,
                           state_name="उत्तर प्रदेश", district_name="लखनऊ")
            self.assertTrue(r.resolved, "%s: %s" % (hindi, r.reason))
            self.assertEqual(r.match.constituency_id, cid)
            self.assertEqual(r.match.ac_number, ac)
            self.assertEqual(r.match.state_code, "9")

    def test_all_nine_legacy_lucknow_acs_resolve(self):
        rows = self.db.execute(text(
            'select id, "Constituency", ac_number from constituency '
            "where id <= 21 order by ac_number")).all()
        self.assertEqual(len(rows), 9)
        for cid, name, ac in rows:
            r = cr.resolve(self.db, name, state_code="9",
                           district_lgd_code="162")
            self.assertTrue(r.resolved, "%s: %s" % (name, r.reason))
            self.assertEqual(r.match.constituency_id, cid, name)
            self.assertEqual(r.match.ac_number, ac, name)

    def test_duplicate_name_across_states_needs_a_state(self):
        r = cr.resolve(self.db, "Ramnagar")
        self.assertFalse(r.resolved)
        self.assertEqual(r.status, cr.UNRESOLVED_AMBIGUOUS)
        self.assertIsNone(r.match)
        self.assertGreater(len({c.state_code for c in r.candidates}), 1)

    def test_duplicate_name_resolves_per_state(self):
        for code, ac in (("5", 61), ("10", 2), ("16", 7), ("19", 217)):
            r = cr.resolve(self.db, "Ramnagar", state_code=code)
            self.assertTrue(r.resolved, "%s: %s" % (code, r.reason))
            self.assertEqual(r.match.state_code, code)
            self.assertEqual(r.match.ac_number, ac)

    def test_intra_state_duplicate_needs_a_district(self):
        """Kalyanpur appears twice in Bihar, in two districts."""
        r = cr.resolve(self.db, "Kalyanpur", state_code="10")
        self.assertEqual(r.status, cr.UNRESOLVED_AMBIGUOUS)
        self.assertIsNone(r.match)
        r = cr.resolve(self.db, "Kalyanpur", state_code="10",
                       district_lgd_code="217")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.ac_number, 131)

    def test_globally_unique_name_resolves_unscoped(self):
        r = cr.resolve(self.db, "Bakshi Kaa Talab")
        self.assertTrue(r.resolved, r.reason)
        self.assertEqual(r.match.constituency_id, 13)
        self.assertEqual(r.match.ac_number, 169)

    def test_withheld_states_have_no_rows_to_resolve(self):
        """Assam, AP, Arunachal, Nagaland, Manipur and J&K were not loaded."""
        for code in ("1", "12", "13", "14", "18", "28"):
            n = self.db.execute(text(
                "select count(*) from constituency c join states s "
                "on s.state_id = c.state_id where s.state_code = :c"),
                {"c": code}).scalar()
            self.assertEqual(n, 0, "state_code %s" % code)

    def test_every_duplicate_english_name_is_refused_unscoped(self):
        """No duplicated AC name may resolve without a scope."""
        names = [r[0] for r in self.db.execute(text(
            'select lower("Constituency") from constituency '
            "group by 1 having count(*) > 1 order by 1"))]
        self.assertGreaterEqual(len(names), 80)
        for name in names:
            r = cr.resolve(self.db, name)
            self.assertFalse(r.resolved,
                             "%r resolved without a scope" % name)
            self.assertIsNone(r.match, "%r produced a match" % name)

    def test_counts_unchanged_after_the_whole_class_ran(self):
        one = lambda s: self.db.execute(text(s)).scalar()  # noqa: E731
        self.assertEqual(one("select count(*) from voters"), 8)
        self.assertEqual(one("select count(*) from constituency"), 3551)
        self.assertEqual(one("select count(*) from districts"), 784)
        self.assertEqual(one("select count(*) from states"), 36)


if __name__ == "__main__":
    unittest.main(verbosity=2)
