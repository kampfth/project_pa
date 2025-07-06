"""
simbrief_handler.py - Gerenciador de dados do SimBrief

Integração com airports.json para resolução de cidades.
Mantém OpenAI como fallback para aeroportos não encontrados.
"""

import requests
import xml.etree.ElementTree as ET
import json
import tempfile
import os
import re
import string
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Import com fallback para execução direta
try:
    from core.utils import ROOT, logger, seconds_to_words, spaced_digits, greeting, ENV
except ImportError:
    # Fallback para execução direta do arquivo
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from core.utils import ROOT, logger, seconds_to_words, spaced_digits, greeting, ENV

# Caminhos
DATA_DIR = ROOT / "data"
AIRPORTS_FILE = DATA_DIR / "airports.json"
CACHE_FILE = DATA_DIR / "cache" / "destination_list.json"
AIRLINE_FILE = DATA_DIR / "airline_profiles.json"

# Pasta temp controlada (dentro do projeto)
TEMP_DIR = ROOT / "core" / ".temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Global variable for airports database
AIRPORTS_DB = None

# Cliente OpenAI para resolução de cidades (fallback)
try:
    from openai import OpenAI
    client = OpenAI(api_key=ENV.get("OPENAI_API_KEY"))
except Exception as e:
    client = None
    logger.warning("OpenAI not configured: %s", e)

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
        logger.info("Loading airports database...")
        with open(AIRPORTS_FILE, 'r', encoding='utf-8') as f:
            AIRPORTS_DB = json.load(f)
        
        logger.info(f"Loaded {len(AIRPORTS_DB)} airports from database")
        return AIRPORTS_DB
        
    except Exception as e:
        logger.error(f"Error loading airports database: {e}")
        AIRPORTS_DB = {}
        return AIRPORTS_DB

def get_city_from_airports_db(icao: str) -> str:
    """
    Resolve cidade usando airports.json
    
    Args:
        icao: Airport ICAO code
        
    Returns:
        str: City name or None if not found
    """
    airports_db = load_airports_database()
    
    if not airports_db:
        return None
    
    icao_upper = icao.upper()
    airport = airports_db.get(icao_upper)
    
    if airport and airport.get("city"):
        city = airport["city"]
        logger.debug(f"Airport {icao} → {city} (from airports.json)")
        return city
    
    return None

def ask_city(icao: str) -> str:
    """
    Resolve city for airport ICAO via OpenAI (fallback)
    
    Args:
        icao: Airport ICAO code
        
    Returns:
        str: City name or "UNKNOWN"
    """
    if not client:
        logger.warning(f"OpenAI not available for {icao}")
        return "UNKNOWN"
    
    logger.debug(f"Resolving city via OpenAI for airport {icao}")
    
    try:
        prompt = f"Give ONLY the city name (no extra words) where airport ICAO {icao} is located."
        
        resp = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": prompt}], 
            max_tokens=16
        )
        
        city = resp.choices[0].message.content.strip()
        city = re.split(r'[\n,]', city)[0].strip(string.punctuation + " ")
        
        result = city or "UNKNOWN"
        logger.debug(f"OpenAI resolved {icao} → {result}")
        return result
        
    except Exception as e:
        logger.warning(f"OpenAI city resolution failed for {icao}: {e}")
        return "UNKNOWN"

def resolve_city(icao: str) -> str:
    """
    Resolve city with airports.json primary, OpenAI fallback, local cache
    
    Args:
        icao: Airport ICAO code
        
    Returns:
        str: City name
    """
    # 1. Try airports.json first
    city = get_city_from_airports_db(icao)
    if city:
        return city
    
    # 2. Check local cache for OpenAI results
    cache = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text())
        except Exception as e:
            logger.warning(f"Error loading cache: {e}")
            cache = {}
    
    # Check if already cached from previous OpenAI calls
    if icao in cache:
        logger.debug(f"Using cached OpenAI result for {icao}: {cache[icao]}")
        return cache[icao]
    
    # 3. Fallback to OpenAI
    logger.info(f"Airport {icao} not found in database, using OpenAI fallback")
    city = ask_city(icao)
    
    # 4. Save OpenAI result to cache
    cache[icao] = city
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        CACHE_FILE.write_text(json.dumps(cache, indent=2))
        logger.debug(f"Cached OpenAI result {icao} → {city}")
    except Exception as e:
        logger.warning(f"Error saving cache: {e}")
    
    return city

def airline_name(icao: str) -> str:
    """
    Get airline name from airline_profiles.json
    
    Args:
        icao: Airline ICAO code
        
    Returns:
        str: Airline name or empty string
    """
    if not AIRLINE_FILE.exists():
        logger.warning(f"Airline profiles file not found: {AIRLINE_FILE}")
        return ""
    
    try:
        table = json.loads(AIRLINE_FILE.read_text())
        
        if icao in table and table[icao].get("name"):
            name = table[icao]["name"]
            logger.debug(f"Found airline {icao}: {name}")
            return name
        else:
            logger.warning(f"Airline {icao} not found in profiles")
            return ""
            
    except Exception as e:
        logger.warning(f"Error reading airline_profiles.json: {e}")
        return ""

def clean_airport_name(name: str) -> str:
    """
    Limpa nome do aeroporto removendo partes desnecessárias
    
    Args:
        name: Nome bruto do aeroporto
        
    Returns:
        str: Nome limpo
    """
    if not name:
        return ""
    
    # Remover tudo após / ou - ou (
    name = re.split(r"[/-]|\(", name)[0]
    
    # Remover "International" ou "Intl"
    name = re.sub(r"\b(Intl|International)\b", "", name, flags=re.I)
    
    # Remover espaços duplos e limpar pontuação
    name = re.sub(r"\s{2,}", " ", name).strip(string.punctuation + " ")
    
    return name

def fetch_xml(username: str) -> Path:
    """
    Download SimBrief XML for specified user
    
    Args:
        username: SimBrief username
        
    Returns:
        Path: Temporary XML file path
    """
    logger.info(f"Downloading SimBrief data for user: {username}")
    
    # Use controlled temp folder
    import uuid
    temp_filename = f"simbrief_{username}_{uuid.uuid4().hex[:8]}.xml"
    xml_path = TEMP_DIR / temp_filename
    
    url = f"https://www.simbrief.com/api/xml.fetcher.php?username={username}"
    
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        
        xml_path.write_bytes(r.content)
        
        logger.debug(f"XML downloaded: {len(r.content)} bytes → {xml_path}")
        return xml_path
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download SimBrief XML: {e}")
        raise

def parse(xml_path: Path) -> dict:
    """
    Parse SimBrief XML extracting all necessary data
    
    Args:
        xml_path: XML file path
        
    Returns:
        dict: Structured flight data
    """
    logger.info("Parsing and organizing flight data")
    
    try:
        root = ET.parse(xml_path).getroot()
        
        # Extract basic data - exactly like original
        data = {}
        
        # Airline
        data['icao'] = root.findtext('./general/icao_airline', '').upper()
        data['airline_name'] = airline_name(data['icao'])
        
        # Flight number
        data['flight_number'] = root.findtext('./general/flight_number', '')
        data['flight_number_text'] = spaced_digits(data['flight_number'])
        
        # Destination
        dest = root.find('./destination')
        data['dest_icao'] = dest.findtext('icao_code', '').upper()
        data['dest_name'] = clean_airport_name(dest.findtext('name', '').title())
        data['dest_city'] = resolve_city(data['dest_icao'])
        
        # Duration
        dur = int(root.findtext('./times/sched_time_enroute', '0'))
        data['duration_seconds'] = dur
        data['duration_text'] = seconds_to_words(dur)
        
        # Time and greeting
        sched = int(root.findtext('./times/sched_out', '0'))
        tz = int(root.findtext('./times/orig_timezone', '0'))
        hour = (datetime.fromtimestamp(sched, timezone.utc) + timedelta(hours=tz)).hour
        data['greeting'] = greeting(hour)
        
        # Log extracted data
        logger.info(f"Flight data parsed: {data['icao']} {data['flight_number']} → {data['dest_city']}")
        
        return data
        
    except ET.ParseError as e:
        logger.error(f"XML parsing error: {e}")
        raise RuntimeError(f"Invalid XML format: {e}")
    except Exception as e:
        logger.error(f"Error parsing XML: {e}")
        raise RuntimeError(f"XML parsing failed: {e}")

def generate(username: str) -> Path:
    """
    Main function: generate SimBrief data and save to JSON
    
    Args:
        username: SimBrief username
        
    Returns:
        Path: Generated JSON file path
    """
    logger.info(f"Starting SimBrief data generation for: {username}")
    
    xml_path = None
    
    try:
        # 1. Download XML
        xml_path = fetch_xml(username)
        
        # 2. Parse data
        data = parse(xml_path)
        
        # 3. Save JSON - exactly like original
        DATA_DIR.mkdir(exist_ok=True)
        json_path = DATA_DIR / 'simbrief_data.json'
        
        json_path.write_text(json.dumps(data, indent=2))
        
        logger.info(f"SimBrief data saved successfully to: {json_path}")
        
        return json_path
        
    except Exception as e:
        logger.error(f"Error processing data for {username}: {e}")
        raise e
        
    finally:
        # Clean temporary XML file silently
        if xml_path and xml_path.exists():
            try:
                import time
                time.sleep(0.1)
                xml_path.unlink()
            except:
                pass  # Silent cleanup

class SimbriefHandler:
    """
    Wrapper class for compatibility and testing
    Maintains functional interface but allows object-oriented usage
    """
    
    def __init__(self, username: str):
        self.username = username
        logger.debug(f"SimBrief Handler initialized for: {username}")
    
    def fetch_flight_data(self) -> dict:
        """
        Fetch flight data and return as dictionary
        
        Returns:
            dict: Flight data
        """
        json_path = generate(self.username)
        
        # Load and return data
        with open(json_path, 'r') as f:
            return json.load(f)
    
    def get_json_path(self) -> Path:
        """
        Return path where JSON will be/was saved
        
        Returns:
            Path: JSON file path
        """
        return DATA_DIR / 'simbrief_data.json'

# Teste direto quando executado
if __name__ == "__main__":
    import sys
    
    # Usar argumento ou .env
    username = sys.argv[1] if len(sys.argv) > 1 else ENV.get("SIMBRIEF_USER")
    
    if not username:
        print("❌ Username do SimBrief necessário")
        print("💡 Use: python simbrief_handler.py <username>")
        print("💡 Ou configure SIMBRIEF_USER no .env")
        sys.exit(1)
    
    try:
        print(f"🚀 Testando SimBrief Handler para: {username}")
        
        # Teste usando função direta
        json_path = generate(username)
        
        # Carregar e mostrar resultado
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        print("\n" + "="*50)
        print("✅ DADOS EXTRAÍDOS COM SUCESSO")
        print("="*50)
        print(f"✈️ Companhia: {data['airline_name']} ({data['icao']})")
        print(f"🛫 Voo: {data['flight_number']} → {data['flight_number_text']}")
        print(f"🎯 Destino: {data['dest_city']} ({data['dest_name']})")
        print(f"⏱️ Duração: {data['duration_text']}")
        print(f"👋 Saudação: {data['greeting']}")
        print(f"📁 Arquivo: {json_path}")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        logger.exception("Test failed")
        sys.exit(1)