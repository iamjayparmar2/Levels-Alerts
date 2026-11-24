"""Public market candle adapters used by the alert scanner."""
import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]

def _utc(df):
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
    return df.sort_index()

def _closed(df, minutes, now):
    return df[df.index + pd.Timedelta(minutes=minutes) <= now]

def _ccxt(sym, timeframe, limit):
    import ccxt
    exchange = getattr(ccxt, sym["exchange"])({"enableRateLimit": True})
    rows = exchange.fetch_ohlcv(sym["symbol"], timeframe, limit=limit)
    df = pd.DataFrame(rows, columns=["ts"] + COLS)
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    return df

def _yf(symbol, interval, period):
    import yfinance as yf
    df = yf.download(symbol, interval=interval, period=period, progress=False, auto_adjust=False, threads=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    return _utc(df[COLS].dropna(subset=["open", "high", "low", "close"]))

def get_data(sym, now=None):
    """Return hourly history and closed touch-timeframe candles."""
    now = now or pd.Timestamp.now(tz="UTC")
    minutes = int(sym.get("chart_minutes", 5))
    if sym["source"] == "ccxt":
        touch = _ccxt(sym, f"{minutes}m", limit=300)
        hourly = _ccxt(sym, "1h", limit=1000)
    elif sym["source"] == "yfinance":
        touch = _yf(sym["symbol"], f"{minutes}m", "5d")
        hourly = _yf(sym["symbol"], "1h", "60d")
    else:
        raise ValueError(f"Unknown source: {sym['source']}")
    return hourly, _closed(touch, minutes, now)
