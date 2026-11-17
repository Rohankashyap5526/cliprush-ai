from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    clip_count: int = Field(default=5, ge=1, le=20)
    min_duration: float = Field(default=15, ge=5, le=120)
    max_duration: float = Field(default=45, ge=10, le=180)
    aspect_ratio: str = Field(default="9:16", pattern="^(9:16|16:9|1:1)$")
    content_type: str = Field(default="hybrid", pattern="^(gaming|podcast|general|hybrid)$")
    caption_style: str = Field(default="bold", pattern="^(bold|karaoke|classic|minimal|none)$")
    caption_position: str = Field(default="bottom", pattern="^(bottom|middle)$")
    reframe: str = Field(default="crop", pattern="^(crop|blur)$")
    quality: str = Field(default="standard", pattern="^(standard|high)$")
    show_hook: bool = True
    language: str | None = Field(default=None, pattern="^[a-z]{2,3}$")  # ISO-639-1/3; None = auto-detect
    guidance: str = Field(default="", max_length=300)


class SourceRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


YouTubeInspectRequest = SourceRequest  # backwards-compatible alias
