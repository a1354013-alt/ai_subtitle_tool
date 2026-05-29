from pydantic import BaseModel


class AppConfigResponse(BaseModel):
    maxUploadSizeMb: int
    maxBatchFiles: int
    supportedExtensions: list[str]
    batchUploadEnabled: bool
    subtitleFormats: list[str]
    translationEnabled: bool
    openaiConfigured: bool
    defaultTargetLanguage: str
    availableModes: list[str]

