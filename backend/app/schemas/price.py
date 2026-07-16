from pydantic import BaseModel

from app.models.price import Period


class PriceCreate(BaseModel):
    period: Period
