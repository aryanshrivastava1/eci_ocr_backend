from sqlalchemy import Column, ForeignKey, Integer, String

from app.db.base import Base



class Constituency(Base):
    __tablename__ = "constituency"

    id = Column(Integer, primary_key=True, index=True)

    constituency = Column("Constituency", String, nullable=False, index=True)
    district = Column("District", String, nullable=False, index=True)
    constituency_hindi = Column("Constituency_Hindi", String, nullable=False, index=True)

    district_id = Column(Integer, ForeignKey("districts.district_id"))