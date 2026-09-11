# app/schemas/voter.py

from pydantic import BaseModel


class VoterCreate(BaseModel):
    name: str
    epic: str | None = None
    mobile: str | None = None
    address: str | None = None
    serial_number: int | None = None
    part_number_and_name: str | None = None

    assembly_constituency_name: str

    district: str | None = None
    state: str | None = None

    # Authoritative identifiers, both optional and both additive — existing
    # callers that send only names keep working. Supplying either makes
    # constituency resolution unambiguous, which matters because 83 English AC
    # names are duplicated across States/UTs.
    #   state_code        = LGD State Code as TEXT, e.g. "9" for Uttar Pradesh
    #   district_lgd_code = LGD District Code as TEXT, e.g. "162" for Lucknow
    state_code: str | None = None
    district_lgd_code: str | None = None
