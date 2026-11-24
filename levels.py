"""Previous UTC day/week/four-hour reference levels."""
import pandas as pd

def levels_at(hourly, candle_time):
    """Calculate levels using only completed hourly bars before candle_time."""
    t = pd.Timestamp(candle_time)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    day = t.normalize()
    week = day - pd.Timedelta(days=day.weekday())
    block4h = t.floor("4h")
    index = hourly.index
    windows = [
        ("PDH", "PDL", day - pd.Timedelta(days=1), day, day.strftime("%Y-%m-%d")),
        ("PWH", "PWL", week - pd.Timedelta(days=7), week, week.strftime("%G-W%V")),
        ("P4H HIGH", "P4H LOW", block4h - pd.Timedelta(hours=4), block4h,
         (block4h - pd.Timedelta(hours=4)).strftime("%Y-%m-%d %H:%M UTC")),
    ]
    out = []
    for high_name, low_name, start, end, period in windows:
        bars = hourly[(index >= start) & (index < end)]
        if not bars.empty:
            out.append((high_name, float(bars["high"].max()), period))
            out.append((low_name, float(bars["low"].min()), period))
    return out
