# app/models/voter.py

from sqlalchemy import Column, PrimaryKeyConstraint, String, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db.base import Base


class Voter(Base):
    __tablename__ = "voters"

    id = Column(UUID(as_uuid=True), default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    name = Column(Text)
    epic = Column(String, index=True)
    mobile = Column(String)

    address = Column(Text)
    serial_number = Column(Integer)
    part_number_and_name = Column(Text)

    assembly_constituency_id = Column(Integer, index=True)
    assembly_constituency_name = Column(String)

    district = Column(String)
    state = Column(String)
    mandal_id = Column(Integer, nullable=True)
    district_id = Column(Integer, nullable=True)
    booth_id = Column(Integer, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("id", "assembly_constituency_id"),
    )