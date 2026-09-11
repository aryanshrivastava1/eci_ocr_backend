from sqlalchemy import Column, Integer, String

from app.db.base import Base


class State(Base):
    """LGD State/UT.

    state_id is the authoritative LGD State Code as an integer, and state_code
    is the same code as TEXT (the form the reference CSVs and the rest of the
    pipeline use). Uttar Pradesh is "9". Postal abbreviations, ISO codes and
    Census codes are deliberately not used as the identifier.
    """

    __tablename__ = "states"

    state_id = Column(Integer, primary_key=True)
    state_code = Column(String, nullable=False, unique=True, index=True)
    state_name_en = Column(String, nullable=False)
    # NULL until an authoritative Hindi source exists. The LGD "local language"
    # column is a Latin transliteration, not Devanagari, so it is not copied
    # here and no Hindi is fabricated.
    state_name_hi = Column(String, nullable=True)

    source = Column(String, nullable=True)
    source_version = Column(String, nullable=True)
