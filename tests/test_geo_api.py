"""Hierarchical geo APIs — hermetic tests.

    venv/Scripts/python.exe -m unittest discover -s tests -t . -v

An in-memory SQLite database and a minimal FastAPI app carrying only the geo
router. `app.main` is deliberately NOT imported: importing it would run
`Base.metadata.create_all(bind=engine)` against the production database. These
tests never open DATABASE_URL and never create a voters table.

The fixture mirrors the real hierarchy: Uttar Pradesh (state_code "9") ->
Lucknow (lgd_district_code "162") -> AC 168..176, plus a second State/UT and a
second district so cross-scope leakage is actually detectable.
"""

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.routes import geo
from app.db.session import get_db
from app.models.constituency import Constituency
from app.models.districts import District
from app.models.states import State

STATES = [
    (9, "9", "Uttar Pradesh"),
    (10, "10", "Bihar"),
    (7, "7", "Delhi"),
]

# (district_id, state_id, lgd_district_code, name_en, name_hi)
DISTRICTS = [
    (127, 9, "162", "Lucknow", "लखनऊ"),
    (121, 9, "157", "Kanpur Nagar", "कानपुर नगर"),
    (92, 9, "129", "Bara Banki", "बाराबंकी"),
    (2404, 10, "217", "Samastipur", None),
    (2400, 10, "213", "Purbi Champaran", None),
]

# (id, state_id, ac_number, name_en, name_hi, district_id, lgd_district_code)
CONSTITUENCIES = [
    # the 9 legacy Lucknow rows — ids 13..21, ECI AC 168..176
    (20, 9, 168, "Malihabad", "मलिहाबाद", 127, "162"),
    (13, 9, 169, "Bakshi Kaa Talab", "बक्शी का तालाब", 127, "162"),
    (21, 9, 170, "Sarojini Nagar", "सरोजिनी नगर", 127, "162"),
    (17, 9, 171, "Lucknow West", "लखनऊ पश्चिम", 127, "162"),
    (14, 9, 172, "Lucknow North", "लखनऊ उत्तर", 127, "162"),
    (15, 9, 173, "Lucknow East", "लखनऊ पूर्व", 127, "162"),
    (16, 9, 174, "Lucknow Central", "लखनऊ मध्य", 127, "162"),
    (18, 9, 175, "Lucknow Cantonment", "लखनऊ छावनी", 127, "162"),
    (19, 9, 176, "Mohanlalganj", "मोहनलालगंज", 127, "162"),
    # another UP district, to prove district scoping excludes it
    (10999, 9, 211, "Kalyanpur", None, 121, "157"),
    (11000, 9, 268, "Barabanki", None, 92, "129"),
    # another State/UT
    (11382, 10, 131, "Kalyanpur", None, 2404, "217"),
    (11354, 10, 16, "Kalyanpur", None, 2400, "213"),
    # a row with no district attribution, as Delhi's 70 rows have
    (30001, 7, 1, "Nerela", None, None, None),
]


class GeoApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # StaticPool + check_same_thread=False: one shared in-memory database
        # across the TestClient's worker thread. Without it each connection
        # gets its own empty ":memory:".
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
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

        app = FastAPI()
        app.include_router(geo.router, prefix="/geo", tags=["Geo"])

        def _override_db():
            session = cls.Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: object()
        cls.client = TestClient(app)

    def data(self, resp):
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["success"])
        return body["data"]

    # -- A ---------------------------------------------------------------
    def test_A_states_endpoint_returns_all_states(self):
        d = self.data(self.client.get("/geo/states"))
        self.assertEqual(d["total"], len(STATES))
        self.assertEqual(len(d["states"]), len(STATES))
        for s in d["states"]:
            self.assertEqual(
                set(s), {"state_id", "state_code", "state_name_en",
                         "state_name_hi"})

    def test_A2_states_are_ordered_by_english_name(self):
        d = self.data(self.client.get("/geo/states"))
        names = [s["state_name_en"] for s in d["states"]]
        self.assertEqual(names, sorted(names))

    def test_A3_state_name_hi_is_null_not_fabricated(self):
        d = self.data(self.client.get("/geo/states"))
        self.assertTrue(all(s["state_name_hi"] is None for s in d["states"]))

    # -- B ---------------------------------------------------------------
    def test_B_uttar_pradesh_present_with_state_code_9(self):
        d = self.data(self.client.get("/geo/states"))
        up = [s for s in d["states"] if s["state_name_en"] == "Uttar Pradesh"]
        self.assertEqual(len(up), 1)
        self.assertEqual(up[0]["state_code"], "9")
        self.assertEqual(up[0]["state_id"], 9)

    # -- C ---------------------------------------------------------------
    def test_C_districts_scoped_to_state(self):
        d = self.data(self.client.get("/geo/districts", params={"state_id": 9}))
        self.assertEqual(d["total"], 3)
        for row in d["districts"]:
            self.assertEqual(row["state_id"], 9, row)
            self.assertEqual(row["state_code"], "9")

    def test_C2_other_state_districts_absent(self):
        d = self.data(self.client.get("/geo/districts", params={"state_id": 9}))
        names = {row["district_name_en"] for row in d["districts"]}
        self.assertNotIn("Samastipur", names)
        self.assertNotIn("Purbi Champaran", names)

    def test_C3_district_response_fields(self):
        d = self.data(self.client.get("/geo/districts", params={"state_id": 9}))
        for row in d["districts"]:
            for key in ("district_id", "lgd_district_code", "district_name_en",
                        "district_name_hi", "state_id"):
                self.assertIn(key, row)

    def test_C4_unknown_state_id_is_404(self):
        r = self.client.get("/geo/districts", params={"state_id": 999999})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "STATE_NOT_FOUND")

    # -- D ---------------------------------------------------------------
    def test_D_lucknow_has_lgd_code_162(self):
        d = self.data(self.client.get("/geo/districts", params={"state_id": 9}))
        luc = [r for r in d["districts"] if r["district_name_en"] == "Lucknow"]
        self.assertEqual(len(luc), 1)
        self.assertEqual(luc[0]["lgd_district_code"], "162")
        self.assertEqual(luc[0]["district_id"], 127)
        self.assertEqual(luc[0]["district_name_hi"], "लखनऊ")

    # -- E ---------------------------------------------------------------
    def test_E_lucknow_returns_exactly_nine_constituencies(self):
        d = self.data(self.client.get("/geo/constituencies",
                                      params={"district_id": 127}))
        self.assertEqual(d["total"], 9)
        self.assertEqual(len(d["constituencies"]), 9)

    # -- F ---------------------------------------------------------------
    def test_F_ac_numbers_are_168_to_176_ascending(self):
        d = self.data(self.client.get("/geo/constituencies",
                                      params={"district_id": 127}))
        nums = [c["ac_number"] for c in d["constituencies"]]
        self.assertEqual(nums, list(range(168, 177)))

    def test_F2_id_is_exposed_separately_and_is_not_the_ac_number(self):
        """AC 168 is database id 20 — the two must not be conflated."""
        d = self.data(self.client.get("/geo/constituencies",
                                      params={"district_id": 127}))
        first = d["constituencies"][0]
        self.assertEqual(first["ac_number"], 168)
        self.assertEqual(first["id"], 20)
        self.assertNotEqual(first["id"], first["ac_number"])
        self.assertEqual(sorted(c["id"] for c in d["constituencies"]),
                         list(range(13, 22)))

    def test_F3_constituency_response_fields(self):
        d = self.data(self.client.get("/geo/constituencies",
                                      params={"district_id": 127}))
        for c in d["constituencies"]:
            for key in ("id", "state_id", "district_id", "lgd_district_code",
                        "ac_number", "constituency", "constituency_hindi",
                        "reservation"):
                self.assertIn(key, c)

    # -- G ---------------------------------------------------------------
    def test_G_no_constituency_from_another_district(self):
        d = self.data(self.client.get("/geo/constituencies",
                                      params={"district_id": 127}))
        for c in d["constituencies"]:
            self.assertEqual(c["district_id"], 127, c)
            self.assertEqual(c["lgd_district_code"], "162", c)
        names = {c["constituency"] for c in d["constituencies"]}
        self.assertNotIn("Kalyanpur", names)
        self.assertNotIn("Barabanki", names)

    def test_G2_no_constituency_from_another_state(self):
        d = self.data(self.client.get("/geo/constituencies",
                                      params={"state_id": 9}))
        for c in d["constituencies"]:
            self.assertEqual(c["state_id"], 9, c)
        self.assertEqual(d["total"], 11)

    def test_G3_unknown_district_id_is_404(self):
        r = self.client.get("/geo/constituencies",
                            params={"district_id": 999999})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "DISTRICT_NOT_FOUND")

    def test_G4_state_and_district_are_anded_no_cross_scope_result(self):
        """A Bihar district under state_id 9 must yield nothing, not a leak."""
        d = self.data(self.client.get(
            "/geo/constituencies",
            params={"state_id": 9, "district_id": 2404}))
        self.assertEqual(d["total"], 0)
        self.assertEqual(d["constituencies"], [])

    # -- hierarchy invariants (Task 8) ------------------------------------
    def test_hierarchy_invariants_hold_for_every_state(self):
        states = self.data(self.client.get("/geo/states"))["states"]
        for st in states:
            districts = self.data(self.client.get(
                "/geo/districts", params={"state_id": st["state_id"]}
            ))["districts"]
            for dist in districts:
                # State -> District
                self.assertEqual(dist["state_id"], st["state_id"])
                acs = self.data(self.client.get(
                    "/geo/constituencies",
                    params={"district_id": dist["district_id"]},
                ))["constituencies"]
                for ac in acs:
                    # District -> AC
                    self.assertEqual(ac["district_id"], dist["district_id"])
                    # AC -> State
                    self.assertEqual(ac["state_id"], dist["state_id"])

    def test_ac_numbers_unique_within_a_state(self):
        for st in (9, 10, 7):
            acs = self.data(self.client.get(
                "/geo/constituencies", params={"state_id": st}
            ))["constituencies"]
            nums = [c["ac_number"] for c in acs]
            self.assertEqual(len(nums), len(set(nums)), st)

    # -- K : backward compatibility ---------------------------------------
    def test_K_districts_without_state_id_still_works(self):
        d = self.data(self.client.get("/geo/districts"))
        self.assertEqual(d["total"], len(DISTRICTS))
        self.assertIn("districts", d)

    def test_K2_legacy_district_fields_still_present(self):
        d = self.data(self.client.get("/geo/districts"))
        for key in ("district_id", "district_name_en", "district_name_hi",
                    "mandal_id"):
            self.assertIn(key, d["districts"][0])

    def test_K3_constituencies_without_filters_still_works(self):
        d = self.data(self.client.get("/geo/constituencies"))
        self.assertEqual(d["total"], len(CONSTITUENCIES))

    def test_K4_legacy_constituency_fields_still_present(self):
        d = self.data(self.client.get("/geo/constituencies",
                                      params={"district_id": 127}))
        for key in ("id", "constituency", "constituency_hindi", "district",
                    "district_id"):
            self.assertIn(key, d["constituencies"][0])

    def test_K5_filters_endpoint_still_returns_its_original_keys(self):
        d = self.data(self.client.get("/geo/filters"))
        self.assertIn("districts", d)
        self.assertIn("constituencies", d)
        self.assertIn("states", d)          # additive
        self.assertEqual(len(d["districts"]), len(DISTRICTS))
        self.assertEqual(len(d["constituencies"]), len(CONSTITUENCIES))

    def test_K6_filters_endpoint_can_be_scoped(self):
        d = self.data(self.client.get("/geo/filters", params={"state_id": 9}))
        self.assertEqual(len(d["districts"]), 3)
        self.assertEqual(len(d["constituencies"]), 11)
        self.assertEqual(len(d["states"]), len(STATES))

    def test_K7_district_id_filter_on_constituencies_unchanged(self):
        """The pre-existing query parameter keeps its exact meaning."""
        d = self.data(self.client.get("/geo/constituencies",
                                      params={"district_id": 121}))
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["constituencies"][0]["constituency"], "Kalyanpur")

    # -- L : search is parent-scoped --------------------------------------
    def test_L_district_search_is_scoped_to_the_state(self):
        d = self.data(self.client.get(
            "/geo/districts", params={"state_id": 10, "search": "Luck"}))
        self.assertEqual(d["total"], 0)
        d = self.data(self.client.get(
            "/geo/districts", params={"state_id": 9, "search": "Luck"}))
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["districts"][0]["district_name_en"], "Lucknow")

    def test_L2_district_search_matches_hindi(self):
        d = self.data(self.client.get(
            "/geo/districts", params={"state_id": 9, "search": "लखनऊ"}))
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["districts"][0]["lgd_district_code"], "162")

    def test_L3_constituency_search_is_scoped_to_the_district(self):
        """'Kalyanpur' exists in UP and Bihar but not in Lucknow."""
        d = self.data(self.client.get(
            "/geo/constituencies",
            params={"district_id": 127, "search": "Kalyanpur"}))
        self.assertEqual(d["total"], 0)
        d = self.data(self.client.get(
            "/geo/constituencies",
            params={"district_id": 121, "search": "Kalyanpur"}))
        self.assertEqual(d["total"], 1)

    def test_L4_constituency_search_is_scoped_to_the_state(self):
        d = self.data(self.client.get(
            "/geo/constituencies", params={"state_id": 9, "search": "Kalyanpur"}))
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["constituencies"][0]["state_id"], 9)
        d = self.data(self.client.get(
            "/geo/constituencies", params={"state_id": 10, "search": "Kalyanpur"}))
        self.assertEqual(d["total"], 2)
        for c in d["constituencies"]:
            self.assertEqual(c["state_id"], 10)

    def test_L5_constituency_search_matches_hindi(self):
        d = self.data(self.client.get(
            "/geo/constituencies",
            params={"district_id": 127, "search": "लखनऊ"}))
        # लखनऊ उत्तर / पूर्व / मध्य / पश्चिम / छावनी
        self.assertEqual(d["total"], 5)
        for c in d["constituencies"]:
            self.assertEqual(c["district_id"], 127)

    def test_L6_ac_number_filter(self):
        d = self.data(self.client.get(
            "/geo/constituencies", params={"state_id": 9, "ac_number": 174}))
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["constituencies"][0]["id"], 16)
        self.assertEqual(d["constituencies"][0]["constituency"],
                         "Lucknow Central")

    def test_L7_state_search(self):
        d = self.data(self.client.get("/geo/states", params={"search": "9"}))
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["states"][0]["state_name_en"], "Uttar Pradesh")

    # -- rows with no district attribution --------------------------------
    def test_null_district_row_is_reachable_by_state(self):
        d = self.data(self.client.get("/geo/constituencies",
                                      params={"state_id": 7}))
        self.assertEqual(d["total"], 1)
        self.assertIsNone(d["constituencies"][0]["district_id"])

    # -- safety ------------------------------------------------------------
    def test_no_voters_table_exists_in_the_test_database(self):
        from sqlalchemy import text
        db = self.Session()
        try:
            names = sorted(r[0] for r in db.execute(
                text("select name from sqlite_master where type='table'")))
        finally:
            db.close()
        self.assertNotIn("voters", names)
        self.assertEqual(names, ["constituency", "districts", "states"])

    def test_test_database_is_in_memory(self):
        self.assertEqual(str(self.engine.url), "sqlite://")


if __name__ == "__main__":
    unittest.main(verbosity=2)
