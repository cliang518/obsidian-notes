from pydantic import BaseModel, Field


class LlmProviderBase(BaseModel):
    provider_key: str = Field(..., min_length=2, max_length=100)
    display_name: str = Field(..., min_length=2, max_length=255)
    provider_type: str = Field(..., min_length=2, max_length=100)
    base_url: str = ""
    default_model: str = ""
    api_key_env_name: str = ""
    enabled: bool = True
    notes: str = ""


class LlmProviderUpsert(LlmProviderBase):
    pass


class LlmProviderOut(LlmProviderBase):
    id: int
    api_key_present: bool = False

    class Config:
        from_attributes = True
