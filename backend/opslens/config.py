import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    parquet: Path
    ai_provider: str | None
    anthropic_key: str | None
    openai_key: str | None
    anthropic_model: str
    openai_model: str
    rate_limit_per_min: int
    cors_origins: list[str]


def get_settings() -> Settings:
    data_dir = Path(os.environ.get("OPSLENS_DATA_DIR", ROOT / "data"))
    return Settings(
        data_dir=data_dir,
        parquet=data_dir / "processed" / "transactions.parquet",
        ai_provider=(os.environ.get("AI_PROVIDER") or "").lower() or None,
        anthropic_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        openai_key=os.environ.get("OPENAI_API_KEY") or None,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        rate_limit_per_min=int(os.environ.get("RATE_LIMIT_PER_MIN", "20")),
        cors_origins=[o for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o],
    )
