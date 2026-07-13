from pydantic import BaseModel


class AdminCreate(BaseModel):
    family_name: str
    first_name: str
    phone_number: str
    email: str
