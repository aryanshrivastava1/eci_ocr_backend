from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from app.db.base import Base


class Constituency(Base):
    __tablename__ = "constituency"

    # Legacy database surrogate key and the table's primary key. It MUST stay:
    # voters.assembly_constituency_id stores this value and is half the voters
    # composite primary key, and it is exposed as the `ac_id` query parameter
    # on PUT /voters/{voter_id}. The authoritative AC identity is carried
    # alongside as (state_id, ac_number) — it never replaces this key.
    id = Column(Integer, primary_key=True, index=True)

    constituency = Column("Constituency", String, nullable=False, index=True)
    # Nullable since migration 0001: the ECI 2008 Order carries no district
    # attribution for Delhi and no unambiguous LGD successor for some headings.
    district = Column("District", String, nullable=True, index=True)
    # Nullable since migration 0001: the ECI source contains zero Devanagari,
    # so nationwide rows have no Hindi name. NULL, never '' — the OCR resolver
    # matches on this column and '' would poison it.
    constituency_hindi = Column("Constituency_Hindi", String, nullable=True, index=True)

    district_id = Column(Integer, ForeignKey("districts.district_id"), nullable=True)

    # Authoritative ECI/LGD identity, added by migration 0001.
    state_id = Column(Integer, ForeignKey("states.state_id"), nullable=False, index=True)
    ac_number = Column(Integer, nullable=False, index=True)
    # Kept for audit: the LGD District Code the ECI district heading resolved
    # to. NULL when the heading had no unambiguous LGD successor, in which case
    # district_id is NULL too rather than silently guessed.
    lgd_district_code = Column(String, nullable=True)

    source = Column(String, nullable=True)
    source_version = Column(String, nullable=True)
    # exact | mapped | needs_review | no_district_in_source — the confidence of
    # the ECI district heading -> LGD district mapping.
    mapping_confidence = Column(String, nullable=True)

    __table_args__ = (
        # Enforced in the database as the partial unique index
        # ux_constituency_state_ac. Constituency NAMES are deliberately not
        # unique: the same AC name recurs across states.
        UniqueConstraint("state_id", "ac_number", name="ux_constituency_state_ac"),
    )
