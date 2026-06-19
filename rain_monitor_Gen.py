#!/usr/bin/env python3
#Northcliff Rain Monitor 1_0 - Gen
import asyncio
import json
import logging
import time
import urllib.request

LOG = logging.getLogger(__name__)


class RainMonitor:
    def __init__(self, bom_geohash, poll_interval=1800, rain_chance_threshold=50, rain_clear_delay=3600):
        self.bom_geohash = bom_geohash
        self.poll_interval = poll_interval
        self.rain_chance_threshold = rain_chance_threshold
        self.rain_clear_delay = rain_clear_delay
        self._raining = False
        self._last_rain_time = None

    async def _fetch_forecast(self):
        loop = asyncio.get_event_loop()
        url = f"https://api.weather.bom.gov.au/v1/locations/{self.bom_geohash}/forecasts/hourly"
        def _do_fetch():
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://www.bom.gov.au/"
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        try:
            response = await loop.run_in_executor(None, _do_fetch)
            return response.get("data", [])
        except Exception:
            LOG.exception("Failed to fetch BOM forecast for geohash %s", self.bom_geohash)
            return []

    def _current_hour_chance(self, forecast_data):
        return forecast_data[0].get("rain", {}).get("chance", 0) if forecast_data else 0

    async def monitor(self, on_rain_start, on_rain_stop=None):
        while True:
            try:
                forecast_data = await self._fetch_forecast()
                if forecast_data:
                    now = time.time()
                    chance = self._current_hour_chance(forecast_data)
                    raining = chance >= self.rain_chance_threshold
                    LOG.info("Rain Check: %d%% chance this hour - State: %s",
                             chance, "Raining" if self._raining else "Clear")
                    if raining:
                        self._last_rain_time = now
                        if not self._raining:
                            self._raining = True
                            LOG.info("Rain forecast: %d%% chance this hour (threshold %d%%)",
                                     chance, self.rain_chance_threshold)
                            await on_rain_start(forecast_data[0])
                    elif self._raining and self._last_rain_time is not None:
                        if now - self._last_rain_time > self.rain_clear_delay:
                            self._raining = False
                            LOG.info("Rain chance dropped below %d%% - all clear", self.rain_chance_threshold)
                            if on_rain_stop:
                                await on_rain_stop(forecast_data[0])
                else:
                    LOG.warning("No BOM forecast data for geohash %s", self.bom_geohash)
            except Exception:
                LOG.exception("Unexpected error in rain monitor poll")
            await asyncio.sleep(self.poll_interval)
