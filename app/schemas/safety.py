from pydantic import BaseModel, ConfigDict


class SupportResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    contact: str
    note: str


class SafetyResponse(BaseModel):
    category: str
    message: str
    resources: list[SupportResourceOut]
