from .models import MarketData

def save_df_to_db(df):
    for _, row in df.iterrows():

        date_value = row.get("Date")
        if hasattr(date_value, "to_pydatetime"):
            date_value = date_value.to_pydatetime()

        MarketData.objects.update_or_create(
            stock=row.get("Stock"),
            date=date_value,
            defaults={
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "ha_open": row.get("HA_Open"),
                "ha_high": row.get("HA_High"),
                "ha_low": row.get("HA_Low"),
                "ha_close": row.get("HA_Close"),
                "ema_high": row.get("EMA_HIGH"),
                "ema_low": row.get("EMA_LOW"),
                "signal": row.get("signal"),
            }
        )

    print("[DB] Data saved successfully")