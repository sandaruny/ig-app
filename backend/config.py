from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ig_api_key: str = ""
    ig_username: str = ""
    ig_password: str = ""
    ig_api_url: str = "https://demo-api.ig.com/gateway/deal"
    ig_demo: bool = True

    # Trading defaults
    default_trade_size: float = 1.0
    max_open_positions: int = 10
    analysis_interval_seconds: int = 300  # 5 minutes
    min_confidence: float = 0.55  # Minimum confidence (0-1) to place a trade
    use_min_trade_size: bool = False  # When True, use IG's minimum deal size per pair

    # Currency pairs to monitor (IG epics)
    currency_pairs: list[str] = [
        "CS.D.EURUSD.CFD.IP",
        "CS.D.GBPUSD.CFD.IP",
        "CS.D.USDJPY.CFD.IP",
        "CS.D.AUDUSD.CFD.IP",
        "CS.D.USDCAD.CFD.IP",
        "CS.D.USDCHF.CFD.IP",
        "CS.D.EURGBP.CFD.IP",
        "CS.D.EURJPY.CFD.IP",
        "CS.D.GBPJPY.CFD.IP",
        "CS.D.NZDUSD.CFD.IP",
    ]

    class Config:
        env_file = ".env"


settings = Settings()
