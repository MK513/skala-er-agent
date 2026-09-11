"""Validated runtime options. Credentials remain in environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ER_", extra="ignore")

    main_model: str = Field(default="gpt-5-mini", min_length=1)
    main_reasoning_effort: str = "low"
    main_max_output_tokens: int = Field(default=4000, ge=256, le=16000)
    classifier_model: str = Field(default="gpt-4o-mini", min_length=1)
    classifier_temperature: float = Field(default=0, ge=0, le=2)
    classifier_max_tokens: int = Field(default=200, ge=64, le=2000)
    request_timeout: float = Field(default=5, gt=0, le=60)
    model_timeout: float = Field(default=60, gt=0, le=180)
