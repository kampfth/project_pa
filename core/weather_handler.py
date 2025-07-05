"""
core/weather_handler.py - Clean weather handler for arrival announcements

- METAR data from aviationweather.gov (primary)
- OpenWeather fallback for old METAR (>1.5h) using coordinates FROM AIRPORTS.JSON
- TimezoneDB for local time (always fresh) using timezone FROM AIRPORTS.JSON
- 5min cache for weather only
- TTS-friendly formatting
"""

import json
import requests
import re
import csv
from datetime import datetime, timedelta
from pathlib import Path

from core.utils import ENV, logger, ROOT

# API Configuration
METAR_URL = "https://aviationweather.gov/api/data/metar"
TIMEZONEDB_URL = "http://api.timezonedb.com/v2.1/get-time-zone"
OPENWEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"

TIMEZONEDB_KEY = ENV.get("TIMEZONEDB_API_KEY", "demo")
OPENWEATHER_KEY = ENV.get("OPENWEATHER_API_KEY")

# Cache Configuration
CACHE_DIR = ROOT / "data" / "cache" / "weather"
CACHE_DURATION_MINUTES = 5
TTS_DELAY_SECONDS = 45
METAR_MAX_AGE_HOURS = 1.5

# Airports database
AIRPORTS_FILE = ROOT / "data" / "airports.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Global variable for airports database
AIRPORTS_DB = None

# Manual timezone mapping as fallback
ICAO_TIMEZONES_FALLBACK = {
    "LFPG": "Europe/Paris", "LFPO": "Europe/Paris",
    "EGLL": "Europe/London", "EGKK": "Europe/London",
    "EDDF": "Europe/Berlin", "EHAM": "Europe/Amsterdam",
    "KJFK": "America/New_York", "KLAX": "America/Los_Angeles",
    "KORD": "America/Chicago", "KMIA": "America/New_York",
    "SBGR": "America/Sao_Paulo", "SBGL": "America/Sao_Paulo",
    "VTBS": "Asia/Bangkok", "OTHH": "Asia/Qatar",
    "OMDB": "Asia/Dubai", "VHHH": "Asia/Hong_Kong",
    "WSSS": "Asia/Singapore", "RJAA": "Asia/Tokyo",
}

# TTS numbers
NUMBERS = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
    16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty",
    30: "thirty", 40: "forty", 50: "fifty", 60: "sixty"
}

for i in range(21, 60):
    if i not in NUMBERS:
        tens = (i // 10) * 10
        ones = i % 10
        NUMBERS[i] = f"{NUMBERS[tens]}-{NUMBERS[ones]}"

def number_to_words(num: int) -> str:
    return NUMBERS.get(num, str(num))

def load_airports_database():
    """
    Carrega airports.json na memória uma única vez
    
    Returns:
        dict: Database de aeroportos ou dicionário vazio se erro
    """
    global AIRPORTS_DB
    
    if AIRPORTS_DB is not None:
        return AIRPORTS_DB
    
    if not AIRPORTS_FILE.exists():
        logger.warning(f"Airports database not found: {AIRPORTS_FILE}")
        AIRPORTS_DB = {}
        return AIRPORTS_DB
    
    try:
        logger.info("Loading airports database for weather...")
        with open(AIRPORTS_FILE, 'r', encoding='utf-8') as f:
            AIRPORTS_DB = json.load(f)
        
        logger.debug(f"Loaded {len(AIRPORTS_DB)} airports from database")
        return AIRPORTS_DB
        
    except Exception as e:
        logger.error(f"Error loading airports database: {e}")
        AIRPORTS_DB = {}
        return AIRPORTS_DB

def get_airport_info(icao: str) -> dict:
    """
    Get airport information from airports.json
    
    Args:
        icao: Airport ICAO code
        
    Returns:
        dict: Airport info with lat, lon, tz or empty dict
    """
    airports_db = load_airports_database()
    
    if not airports_db:
        return {}
    
    icao_upper = icao.upper()
    airport = airports_db.get(icao_upper, {})
    
    return airport

class WeatherHandler:
    def __init__(self):
        logger.info("Weather handler initialized (METAR + TimezoneDB + OpenWeather fallback + airports.json)")
    
    def get_weather_data(self, dest_icao: str) -> dict:
        """Get weather data with complete fallback chain"""
        logger.info(f"Getting weather for {dest_icao}")
        
        # Check cache first (5min)
        cached = self._get_cache(dest_icao)
        if cached:
            logger.debug(f"Using cached data for {dest_icao}")
            return cached
        
        # Get temperature and local time
        temp_celsius = self._get_temperature_with_fallback(dest_icao)
        local_time = self._get_local_time_with_fallback(dest_icao)
        
        # Format for TTS
        temperature_text = self._format_temperature(temp_celsius, dest_icao)
        time_text = self._format_time(local_time)
        
        result = {
            "temperature": temperature_text,
            "local_time": time_text,
            "raw_temp": temp_celsius,
            "timestamp": datetime.now().isoformat()
        }
        
        # Cache result
        self._save_cache(dest_icao, result)
        
        logger.info(f"Weather for {dest_icao}: {temperature_text}, {time_text}")
        return result
    
    def _get_temperature_with_fallback(self, icao: str) -> float:
        """Get temperature: METAR → OpenWeather fallback using airports.json coordinates"""
        try:
            temp, age = self._get_metar_temperature(icao)
            if age <= METAR_MAX_AGE_HOURS:
                return temp
            else:
                logger.warning(f"METAR too old ({age:.1f}h), using fallback")
        except Exception as e:
            logger.warning(f"METAR failed: {e}, using fallback")
        
        return self._get_openweather_temperature(icao)
    
    def _get_metar_temperature(self, icao: str) -> tuple:
        """Get temperature from METAR"""
        params = {"ids": icao.upper(), "format": "raw", "hours": "3"}
        response = requests.get(METAR_URL, params=params, timeout=15)
        response.raise_for_status()
        
        metar = response.text.strip()
        if not metar or "No METAR" in metar:
            raise ValueError(f"No METAR for {icao}")
        
        # Parse temperature
        temp_match = re.search(r'(\d{2})/\d{2}', metar)
        if temp_match:
            temperature = float(temp_match.group(1))
        else:
            neg_match = re.search(r'M(\d{2})/M?\d{2}', metar)
            if neg_match:
                temperature = -float(neg_match.group(1))
            else:
                raise ValueError(f"Temperature not found in METAR")
        
        # Calculate age
        age_hours = self._parse_metar_age(metar)
        return temperature, age_hours
    
    def _parse_metar_age(self, metar: str) -> float:
        """Parse METAR timestamp and calculate age"""
        try:
            time_match = re.search(r'(\d{2})(\d{2})(\d{2})Z', metar)
            if not time_match:
                return 0.0
            
            day = int(time_match.group(1))
            hour = int(time_match.group(2))
            minute = int(time_match.group(3))
            
            now = datetime.utcnow()
            metar_time = datetime(now.year, now.month, day, hour, minute)
            
            # Handle month boundary
            if day > now.day:
                if now.month == 1:
                    metar_time = metar_time.replace(year=now.year - 1, month=12)
                else:
                    metar_time = metar_time.replace(month=now.month - 1)
            
            age = (now - metar_time).total_seconds() / 3600
            return max(0, age)
        except:
            return 0.0
    
    def _get_openweather_temperature(self, icao: str) -> float:
        """Get temperature from OpenWeather using coordinates FROM AIRPORTS.JSON"""
        if not OPENWEATHER_KEY:
            raise RuntimeError("OpenWeather API key not configured")
        
        # Get coordinates from airports.json
        airport_info = get_airport_info(icao)
        
        if not airport_info or not airport_info.get("lat") or not airport_info.get("lon"):
            raise ValueError(f"No coordinates for {icao} in airports database")
        
        lat = airport_info["lat"]
        lon = airport_info["lon"]
        
        params = {
            "lat": lat,
            "lon": lon,
            "appid": OPENWEATHER_KEY,
            "units": "metric"
        }
        
        response = requests.get(OPENWEATHER_URL, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        logger.debug(f"OpenWeather temperature for {icao}: {data['main']['temp']}°C")
        return float(data["main"]["temp"])
    
    def _get_local_time_with_fallback(self, icao: str) -> datetime:
        """Get local time: airports.json timezone → TimezoneDB → OpenWeather → manual"""
        # Try airports.json timezone first
        airport_info = get_airport_info(icao)
        airport_timezone = airport_info.get("tz") if airport_info else None
        
        if airport_timezone:
            try:
                return self._get_timezonedb_time_with_tz(airport_timezone)
            except Exception as e:
                logger.warning(f"TimezoneDB failed with airports.json timezone {airport_timezone}: {e}")
        
        # Fallback to manual timezone detection + TimezoneDB
        try:
            manual_timezone = self._get_timezone_fallback(icao)
            return self._get_timezonedb_time_with_tz(manual_timezone)
        except Exception as e:
            logger.warning(f"TimezoneDB failed: {e}")
        
        # Fallback to OpenWeather if coordinates available
        if airport_info and airport_info.get("lat") and airport_info.get("lon"):
            try:
                return self._get_openweather_time(icao, airport_info)
            except Exception as e:
                logger.warning(f"OpenWeather timezone failed: {e}")
        
        # Final fallback to manual calculation
        return self._get_manual_time(icao)
    
    def _get_timezonedb_time_with_tz(self, timezone: str) -> datetime:
        """Get time from TimezoneDB with specific timezone"""
        params = {
            "key": TIMEZONEDB_KEY,
            "format": "json",
            "by": "zone",
            "zone": timezone
        }
        
        response = requests.get(TIMEZONEDB_URL, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        if data.get("status") != "OK":
            raise ValueError(f"TimezoneDB error: {data.get('message')}")
        
        formatted_time = data.get("formatted", "")
        if not formatted_time:
            raise ValueError("No formatted time in response")
        
        dt = datetime.strptime(formatted_time, "%Y-%m-%d %H:%M:%S")
        return dt + timedelta(seconds=TTS_DELAY_SECONDS)
    
    def _get_openweather_time(self, icao: str, airport_info: dict) -> datetime:
        """Get time from OpenWeather timezone using airports.json coordinates"""
        if not OPENWEATHER_KEY:
            raise RuntimeError("OpenWeather API key not configured")
        
        lat = airport_info["lat"]
        lon = airport_info["lon"]
        
        params = {
            "lat": lat,
            "lon": lon,
            "appid": OPENWEATHER_KEY
        }
        
        response = requests.get(OPENWEATHER_URL, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        timezone_offset = data.get("timezone", 0)
        
        utc_now = datetime.utcnow()
        return utc_now + timedelta(seconds=timezone_offset + TTS_DELAY_SECONDS)
    
    def _get_manual_time(self, icao: str) -> datetime:
        """Manual time fallback using ICAO prefixes"""
        offsets = {
            "LF": 1, "EG": 0, "ED": 1, "SB": -3, "K": -5,
            "VT": 7, "OT": 3, "OM": 4
        }
        
        offset_hours = 0
        for prefix, hours in offsets.items():
            if icao.upper().startswith(prefix):
                offset_hours = hours
                break
        
        utc_now = datetime.utcnow()
        return utc_now + timedelta(hours=offset_hours, seconds=TTS_DELAY_SECONDS)
    
    def _get_timezone_fallback(self, icao: str) -> str:
        """Get timezone string for ICAO using manual fallback"""
        icao_upper = icao.upper()
        
        # Try manual mapping first
        if icao_upper in ICAO_TIMEZONES_FALLBACK:
            return ICAO_TIMEZONES_FALLBACK[icao_upper]
        
        # Try prefixes
        for length in [2, 1]:
            if len(icao_upper) >= length:
                prefix = icao_upper[:length]
                if prefix in ICAO_TIMEZONES_FALLBACK:
                    return ICAO_TIMEZONES_FALLBACK[prefix]
        
        return "UTC"
    
    def _format_temperature(self, temp_celsius: float, icao: str) -> str:
        """Format temperature for TTS"""
        if icao.upper().startswith("K"):
            temp_f = (temp_celsius * 9/5) + 32
            temp_rounded = round(temp_f)
            unit = "degrees Fahrenheit"
        else:
            temp_rounded = round(temp_celsius)
            unit = "degrees Celsius"
        
        if temp_rounded < 0:
            temp_words = f"minus {number_to_words(abs(temp_rounded))}"
        else:
            temp_words = number_to_words(temp_rounded)
        
        return f"{temp_words} {unit}"
    
    def _format_time(self, dt: datetime) -> str:
        """Format time for TTS - 'ten hours and three minutes' format"""
        hour = dt.hour
        minute = dt.minute
        
        hour_words = number_to_words(hour)
        
        if minute == 0:
            if hour == 1:
                return f"{hour_words} hour"
            else:
                return f"{hour_words} hours"
        else:
            minute_words = number_to_words(minute)
            
            hour_part = f"{hour_words} hour" if hour == 1 else f"{hour_words} hours"
            minute_part = f"{minute_words} minute" if minute == 1 else f"{minute_words} minutes"
            
            return f"{hour_part} and {minute_part}"
    
    def _get_cache(self, icao: str) -> dict:
        """Check cached data (5min)"""
        try:
            cache_file = CACHE_DIR / f"weather_{icao.upper()}.json"
            
            if not cache_file.exists():
                return None
            
            data = json.loads(cache_file.read_text())
            cache_time = datetime.fromisoformat(data["timestamp"])
            
            if datetime.now() - cache_time < timedelta(minutes=CACHE_DURATION_MINUTES):
                return data
            
            cache_file.unlink()  # Remove expired cache
            return None
        except:
            return None
    
    def _save_cache(self, icao: str, data: dict):
        """Save data to cache"""
        try:
            cache_file = CACHE_DIR / f"weather_{icao.upper()}.json"
            cache_file.write_text(json.dumps(data, indent=2))
        except:
            pass

def get_airport_weather(dest_icao: str) -> dict:
    """Main function - get weather data for airport"""
    handler = WeatherHandler()
    return handler.get_weather_data(dest_icao)

if __name__ == "__main__":
    print("🧪 Testing Weather Handler...")
    
    for icao in ["LFPG", "KJFK", "SBGR", "EGLL"]:
        try:
            print(f"\n🌡️ {icao}:")
            data = get_airport_weather(icao)
            print(f"✅ {data['temperature']}")
            print(f"✅ {data['local_time']}")
        except Exception as e:
            print(f"❌ {e}")