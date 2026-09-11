"""Hierarchy + voter filtering against the real data — READ ONLY.

Skipped unless explicitly enabled, so the default run stays hermetic:

    PRAMAAN_LIVE_DB_TESTS=1 venv/Scripts/python.exe -m unittest \
        tests.test_geo_voter_filters_live -v

Every connection sets `SET TRANSACTION READ ONLY` and asserts it is `on`
before querying; teardown rolls back. No INSERT, UPDATE or DELETE appears in
this file. The voters table is only counted and read — never written.
"""

import os
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.routes import geo
from app.services.vote_service import apply_voter_filters, get_base_query

LIVE = os.getenv("PRAMAAN_LIVE_DB_TESTS") == "1"

UP_STATE_ID = 9
LUCKNOW_DISTRICT_ID = 127
LUCKNOW_LGD_CODE = "162"

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


class _SuperAdmin:
    """Minimal stand-in for the authenticated user get_base_query expects."""
    role = "superadmin"
    id = None
    constituency_id = None
    district_id = None
    mandal_id = None
    booth_id = None


@unittest.skipUnless(LIVE, "set PRAMAAN_LIVE_DB_TESTS=1 to run read-only "
                           "checks against the production database")
class LiveGeoAndVoterFilterTestCase(unittest.TestCase):
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
        self.user = _SuperAdmin()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _filter(self, **kw):
        q = apply_voter_filters(get_base_query(self.db, self.user), **kw)
        return q.count()

    # -- Task 15: production state ---------------------------------------
    def test_reference_counts(self):
        one = lambda s: self.db.execute(text(s)).scalar()  # noqa: E731
        self.assertEqual(one("select count(*) from states"), 36)
        self.assertEqual(one("select count(*) from districts"), 784)
        self.assertEqual(one("select count(*) from constituency"), 3551)
        self.assertEqual(one("select count(*) from voters"), 8)

    def test_legacy_ids_intact(self):
        ids = [r[0] for r in self.db.execute(text(
            "select id from constituency where id <= 21 order by id"))]
        self.assertEqual(ids, list(range(13, 22)))
        n = self.db.execute(text(
            "select count(*) from districts "
            "where district_id between 79 and 153")).scalar()
        self.assertEqual(n, 75)

    def test_voter_pks_unchanged(self):
        rows = [(str(r[0]), r[1]) for r in self.db.execute(text(
            "select id, assembly_constituency_id from voters "
            "order by assembly_constituency_id, id"))]
        self.assertEqual(rows, EXPECTED_VOTER_PKS)

    def test_voter_reference_distribution(self):
        rows = dict(self.db.execute(text(
            "select assembly_constituency_id, count(*) from voters "
            "group by 1")).all())
        self.assertEqual(rows, {14: 3, 16: 5})

    # -- Task 8: hierarchy on real data -----------------------------------
    def test_states_query_returns_36(self):
        rows = self.db.execute(geo._states_query(self.db)).scalars().all()
        self.assertEqual(len(rows), 36)
        names = [s.state_name_en for s in rows]
        self.assertEqual(names, sorted(names))

    def test_uttar_pradesh_state_code(self):
        rows = self.db.execute(geo._states_query(self.db)).scalars().all()
        up = [s for s in rows if s.state_name_en == "Uttar Pradesh"]
        self.assertEqual(len(up), 1)
        self.assertEqual(up[0].state_code, "9")
        self.assertEqual(up[0].state_id, UP_STATE_ID)

    def test_up_districts_are_75_and_all_belong_to_up(self):
        rows = self.db.execute(
            geo._districts_query(self.db, state_id=UP_STATE_ID)).all()
        self.assertEqual(len(rows), 75)
        for district, _code, _name in rows:
            self.assertEqual(district.state_id, UP_STATE_ID)

    def test_lucknow_lgd_code(self):
        rows = self.db.execute(
            geo._districts_query(self.db, state_id=UP_STATE_ID,
                                 search="Lucknow")).all()
        self.assertEqual(len(rows), 1)
        district = rows[0][0]
        self.assertEqual(district.district_id, LUCKNOW_DISTRICT_ID)
        self.assertEqual(district.lgd_district_code, LUCKNOW_LGD_CODE)

    def test_lucknow_has_nine_acs_numbered_168_to_176(self):
        rows = self.db.execute(
            geo._constituencies_query(
                self.db, district_id=LUCKNOW_DISTRICT_ID)).all()
        self.assertEqual(len(rows), 9)
        nums = [c.ac_number for c, _s, _d in rows]
        self.assertEqual(nums, list(range(168, 177)))
        ids = sorted(c.id for c, _s, _d in rows)
        self.assertEqual(ids, list(range(13, 22)))

    def test_no_cross_district_or_cross_state_leakage(self):
        rows = self.db.execute(
            geo._constituencies_query(
                self.db, district_id=LUCKNOW_DISTRICT_ID)).all()
        for c, _s, _d in rows:
            self.assertEqual(c.district_id, LUCKNOW_DISTRICT_ID)
            self.assertEqual(c.state_id, UP_STATE_ID)
            self.assertEqual(c.lgd_district_code, LUCKNOW_LGD_CODE)

    def test_hierarchy_invariants_across_every_state(self):
        """district.state_id == state, and ac.state_id == its district's."""
        bad = self.db.execute(text(
            "select count(*) from constituency c "
            "join districts d on d.district_id = c.district_id "
            "where c.state_id <> d.state_id")).scalar()
        self.assertEqual(bad, 0)
        orphan_districts = self.db.execute(text(
            "select count(*) from districts d "
            "left join states s on s.state_id = d.state_id "
            "where s.state_id is null")).scalar()
        self.assertEqual(orphan_districts, 0)

    def test_state_scoped_constituencies_never_leak(self):
        for state_id, expected in ((UP_STATE_ID, 403), (7, 70), (11, 31)):
            rows = self.db.execute(
                geo._constituencies_query(self.db, state_id=state_id)).all()
            self.assertEqual(len(rows), expected, state_id)
            for c, _s, _d in rows:
                self.assertEqual(c.state_id, state_id)

    # -- Task 9: voter filtering ------------------------------------------
    def test_unfiltered_voter_count_unchanged(self):
        self.assertEqual(self._filter(), 8)

    def test_filter_by_legacy_constituency_id(self):
        self.assertEqual(self._filter(assembly_constituency_id=14), 3)
        self.assertEqual(self._filter(assembly_constituency_id=16), 5)

    def test_filter_by_lucknow_district(self):
        self.assertEqual(self._filter(district_id=LUCKNOW_DISTRICT_ID), 8)

    def test_filter_by_ac_number_172_returns_three(self):
        """AC 172 is Lucknow North = legacy constituency.id 14."""
        self.assertEqual(self._filter(ac_number=172), 3)

    def test_filter_by_ac_number_174_returns_five(self):
        """AC 174 is Lucknow Central = legacy constituency.id 16."""
        self.assertEqual(self._filter(ac_number=174), 5)

    def test_filter_by_state(self):
        self.assertEqual(self._filter(state_id=UP_STATE_ID), 8)
        self.assertEqual(self._filter(state_code="9"), 8)

    def test_combined_filters_are_anded_and_do_not_leak(self):
        self.assertEqual(
            self._filter(state_id=UP_STATE_ID,
                         district_id=LUCKNOW_DISTRICT_ID,
                         ac_number=174), 5)
        self.assertEqual(
            self._filter(state_id=UP_STATE_ID,
                         district_id=LUCKNOW_DISTRICT_ID,
                         assembly_constituency_id=14), 3)
        # contradictory combination yields nothing rather than leaking
        self.assertEqual(
            self._filter(assembly_constituency_id=14, ac_number=174), 0)

    def test_no_voter_appears_under_another_states_constituency(self):
        """Every other State/UT must return zero voters."""
        codes = [r[0] for r in self.db.execute(text(
            "select state_code from states order by state_id"))]
        for code in codes:
            expected = 8 if code == "9" else 0
            self.assertEqual(self._filter(state_code=code), expected, code)

    def test_ac_number_in_another_state_returns_no_voters(self):
        """AC 172 exists in other States/UTs too; none holds these voters."""
        others = [r[0] for r in self.db.execute(text(
            "select s.state_id from states s join constituency c "
            "on c.state_id = s.state_id where c.ac_number = 172 "
            "and s.state_id <> 9"))]
        self.assertGreater(len(others), 0, "expected AC 172 in other states")
        for state_id in others:
            self.assertEqual(
                self._filter(state_id=state_id, ac_number=172), 0, state_id)

    def test_legacy_assembly_constituency_id_is_not_the_ac_number(self):
        """Filtering by id 172 must NOT return the AC-172 voters."""
        self.assertEqual(self._filter(assembly_constituency_id=172), 0)
        self.assertEqual(self._filter(ac_number=172), 3)

    # -- final re-check ----------------------------------------------------
    def test_counts_unchanged_after_the_whole_class_ran(self):
        one = lambda s: self.db.execute(text(s)).scalar()  # noqa: E731
        self.assertEqual(one("select count(*) from voters"), 8)
        self.assertEqual(one("select count(*) from constituency"), 3551)
        self.assertEqual(one("select count(*) from districts"), 784)
        self.assertEqual(one("select count(*) from states"), 36)


if __name__ == "__main__":
    unittest.main(verbosity=2)
