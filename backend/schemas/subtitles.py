from pydantic import BaseModel, Field


class SubtitleEditRequest(BaseModel):
    content: str
    format: str = Field(..., description="Target subtitle format: 'ass' or 'srt'")

