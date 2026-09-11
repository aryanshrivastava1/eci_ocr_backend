from sqlalchemy import Column, ForeignKey, Integer, String

from app.db.base import Base


class District(Base):
    __tablename__ = "districts"

    # Legacy database surrogate key. Preserved: existing rows keep ids 79-153
    # and voters.district_id references these values.
    district_id = Column(Integer, primary_key=True)

    district_name_en = Column(String)
    district_name_hi = Column(String)
    mandala_id = Column(Integer)

    # Authoritative LGD identity, added by migration 0001. district names are
    # NOT unique across states, so lgd_district_code is the real identity.
    state_id = Column(Integer, ForeignKey("states.state_id"), nullable=False, index=True)
    lgd_district_code = Column(String, nullable=False, unique=True, index=True)

    source = Column(String, nullable=True)
    source_version = Column(String, nullable=True)
