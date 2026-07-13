from pydantic import BaseModel


class AppCapabilitiesResponse(BaseModel):
    provider: str
    model: str | None
    translationEnabled: bool
    reason: str | None
    message: str | None
    defaultTargetLanguage: str
    availableModes: list[str]
    openaiConfigured: bool


class AppConfigResponse(BaseModel):
    version: str
    maxUploadSizeMb: int
    maxBatchFiles: int
    supportedExtensions: list[str]
    batchUploadEnabled: bool
    subtitleFormats: list[str]
    translationEnabled: bool
    openaiConfigured: bool
    defaultTargetLanguage: str
    availableModes: list[str]
    provider: str
    model: str | None
    reason: str | None
    message: str | None

