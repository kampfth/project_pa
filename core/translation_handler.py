"""
core/translation_handler.py - Intelligent text generation and translation

Responsibilities:
- Generate personalized announcement texts with flight data
- Handle intelligent translations with proper flight number pronunciation
- Manage template processing and variable substitution
- Support multiple languages with aviation-specific formatting
"""

import json
import re
from pathlib import Path
from datetime import datetime

from core.utils import ROOT, ENV, logger, get_openai_client

# ============================================
# CONFIGURAÇÕES AJUSTÁVEIS
# ============================================

# Translation settings
TRANSLATION_MODEL = "gpt-4o-mini"
TRANSLATION_TEMPERATURE = 0.2
MAX_TRANSLATION_TOKENS = 800

# Flight number pronunciation
CONVERT_FLIGHT_NUMBERS_TO_DIGITS = True  # "1582" -> "one five eight two"
USE_SMART_TIME_FORMATTING = True         # Proper singular/plural for time

# Translation quality
APPLY_GRAMMAR_FIXES = True
USE_FORMAL_LANGUAGE = True

# Cache settings
ENABLE_TRANSLATION_CACHE = True
CACHE_DURATION_HOURS = 24

# ============================================
# PATHS CONFIGURATION
# ============================================

PROMPTS_DIR = ROOT / "data" / "prompts"
AIRLINE_FILE = ROOT / "data" / "airline_profiles.json"
CACHE_DIR = ROOT / "data" / "cache" / "translations"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================
# GLOBAL FLIGHT NUMBER CONVERSION
# ============================================

DIGIT_WORDS = {
    '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
    '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'
}

def build_texts(simbrief_data: dict) -> dict:
    """
    Build announcement texts for all configured languages
    
    Args:
        simbrief_data: Flight data from SimBrief
        
    Returns:
        dict: Texts by language code {"en": "text", "pt-BR": "text", ...}
    """
    logger.info("Starting text generation and translation")
    logger.debug(f"SimBrief data keys: {list(simbrief_data.keys())}")
    
    try:
        # Load airline configuration
        airline_config = load_airline_config(simbrief_data["icao"])
        logger.info(f"Airline config loaded for {simbrief_data['icao']}")
        
        # Determine template type
        template_name = determine_template_type()
        logger.info(f"Using template: {template_name}")
        
        # Process template with variables
        english_text = load_and_process_template(template_name, simbrief_data)
        logger.info(f"English template processed successfully")
        
        # Start with English
        texts = {"en": english_text}
        
        # Get target languages
        target_languages = get_target_languages(airline_config)
        logger.info(f"Target languages: {target_languages}")
        
        # Generate translations
        for language in target_languages:
            if language not in ["en", "en-US"]:
                try:
                    logger.info(f"Translating to {language}")
                    translated_text = translate_with_global_formatting(
                        english_text, language, airline_config, simbrief_data
                    )
                    texts[language] = translated_text
                    logger.info(f"Translation to {language} completed")
                    
                except Exception as e:
                    logger.error(f"Translation failed for {language}: {e}")
                    logger.exception(f"Translation error for {language}")
        
        logger.info(f"Text generation completed for: {list(texts.keys())}")
        return texts
        
    except Exception as e:
        logger.error(f"Text generation failed: {e}")
        logger.exception("Text generation error")
        raise

def load_airline_config(icao: str) -> dict:
    """Load and validate airline configuration"""
    logger.debug(f"Loading airline config for: {icao}")
    
    if not AIRLINE_FILE.exists():
        logger.error(f"Airline profiles file not found: {AIRLINE_FILE}")
        raise FileNotFoundError(f"Airline profiles not found: {AIRLINE_FILE}")
    
    try:
        with open(AIRLINE_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if icao not in config:
            logger.error(f"ICAO {icao} not found. Available: {list(config.keys())}")
            raise ValueError(f"Airline {icao} not found in profiles")
        
        airline_config = config[icao]
        logger.debug(f"Config loaded for {icao}: {list(airline_config.keys())}")
        return airline_config
        
    except Exception as e:
        logger.error(f"Error loading airline config: {e}")
        raise

def determine_template_type() -> str:
    """Determine template type from call stack"""
    import inspect
    
    for frame_info in inspect.stack():
        filename = frame_info.filename.lower()
        if 'arrival' in filename:
            logger.debug("Detected arrival context")
            return "arrival"
        elif 'boarding' in filename:
            logger.debug("Detected boarding context")
            return "welcome"
    
    logger.debug("Defaulting to welcome template")
    return "welcome"

def load_and_process_template(template_name: str, simbrief_data: dict) -> str:
    """Load template and process with safe variable substitution"""
    logger.info(f"Loading template: {template_name}")
    
    template_path = PROMPTS_DIR / f"{template_name}.txt"
    
    if not template_path.exists():
        logger.error(f"Template not found: {template_path}")
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    try:
        template = template_path.read_text(encoding="utf-8")
        logger.debug(f"Template loaded, length: {len(template)} chars")
        
        # Prepare variables
        variables = prepare_template_variables(simbrief_data)
        logger.info(f"Variables prepared: {list(variables.keys())}")
        
        # Safe template processing
        processed_text = safe_format_template(template, variables, template_name)
        logger.info(f"Template processed successfully")
        
        return processed_text
        
    except Exception as e:
        logger.error(f"Template processing failed: {e}")
        raise

def prepare_template_variables(simbrief_data: dict) -> dict:
    """Prepare all template variables with intelligent formatting"""
    logger.debug("Preparing template variables")
    
    variables = {}
    
    # === CORE VARIABLES ===
    variables["greeting"] = determine_greeting()
    variables["dest_city"] = simbrief_data.get("dest_city", "destination")
    variables["airline_name"] = simbrief_data.get("airline_name", "our airline")
    
    # === FLIGHT NUMBER WITH DIGIT CONVERSION ===
    flight_number = simbrief_data.get("flight_number", "unknown")
    variables["flight_number"] = convert_flight_number_to_digits(flight_number)
    
    # === TIME FORMATTING ===
    if "local_time" in simbrief_data:
        variables["local_time"] = format_time_intelligently(simbrief_data["local_time"])
    
    # === TEMPERATURE ===
    if "temperature" in simbrief_data:
        variables["temperature"] = simbrief_data["temperature"]
    
    # === DURATION ===
    if "duration_seconds" in simbrief_data:
        variables["duration"] = format_duration_intelligently(simbrief_data["duration_seconds"])
    
    logger.debug(f"Variables prepared: {variables}")
    return variables

def determine_greeting() -> str:
    """Determine greeting based on current time"""
    try:
        current_hour = datetime.now().hour
        
        if 5 <= current_hour < 12:
            return "Good morning"
        elif 12 <= current_hour < 18:
            return "Good afternoon"
        else:
            return "Good evening"
            
    except Exception:
        return "Good evening"

def convert_flight_number_to_digits(flight_number: str) -> str:
    """
    Convert flight number to spoken digits (GLOBAL)
    Examples: "1582" -> "one five eight two"
              "200" -> "two zero zero"
    """
    if not CONVERT_FLIGHT_NUMBERS_TO_DIGITS:
        return flight_number
    
    try:
        # Extract only the numeric part
        numeric_part = re.search(r'\d+', str(flight_number))
        if not numeric_part:
            return flight_number
        
        number = numeric_part.group()
        
        # Convert each digit to word
        digit_words = []
        for digit in number:
            digit_words.append(DIGIT_WORDS.get(digit, digit))
        
        converted = ' '.join(digit_words)
        logger.debug(f"Flight number converted: {flight_number} -> {converted}")
        return converted
        
    except Exception as e:
        logger.warning(f"Flight number conversion failed: {e}")
        return flight_number

def format_time_intelligently(time_str: str) -> str:
    """Format time with proper singular/plural grammar"""
    if not USE_SMART_TIME_FORMATTING:
        return time_str
    
    try:
        # Extract hours and minutes
        time_pattern = r'(\d+)\s*(?:hour|hours)?\s*(?:and|e)?\s*(\d+)\s*(?:minute|minutes)?'
        match = re.search(time_pattern, time_str)
        
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            
            hour_word = "hour" if hours == 1 else "hours"
            minute_word = "minute" if minutes == 1 else "minutes"
            
            if hours > 0 and minutes > 0:
                return f"{hours} {hour_word} and {minutes} {minute_word}"
            elif hours > 0:
                return f"{hours} {hour_word}"
            elif minutes > 0:
                return f"{minutes} {minute_word}"
        
        return time_str
        
    except Exception:
        return time_str

def format_duration_intelligently(duration_seconds: int) -> str:
    """Format flight duration with proper grammar"""
    try:
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        
        hour_word = "hour" if hours == 1 else "hours"
        minute_word = "minute" if minutes == 1 else "minutes"
        
        if hours > 0 and minutes > 0:
            return f"{hours} {hour_word} and {minutes} {minute_word}"
        elif hours > 0:
            return f"{hours} {hour_word}"
        elif minutes > 0:
            return f"{minutes} {minute_word}"
        else:
            return "less than a minute"
            
    except Exception:
        return "unknown duration"

def safe_format_template(template: str, variables: dict, template_name: str) -> str:
    """Safely format template with comprehensive error handling"""
    try:
        # Find all required variables in template
        required_vars = re.findall(r'\{([^}]+)\}', template)
        logger.debug(f"Required variables in template: {required_vars}")
        
        # Check for missing variables
        missing_vars = [var for var in required_vars if var not in variables]
        if missing_vars:
            logger.error(f"Missing variables in template {template_name}: {missing_vars}")
            logger.error(f"Available variables: {list(variables.keys())}")
            raise ValueError(f"Missing variables: {missing_vars}")
        
        # Format template
        formatted = template.format(**variables)
        logger.debug(f"Template formatted successfully")
        return formatted
        
    except KeyError as e:
        logger.error(f"KeyError in template {template_name}: {e}")
        raise ValueError(f"Missing variable in template: {e}")
    except Exception as e:
        logger.error(f"Template formatting error: {e}")
        raise

def get_target_languages(airline_config: dict) -> list:
    """Get target languages ensuring both native and English are included"""
    native_lang = airline_config.get("language", "en")
    
    if isinstance(native_lang, str):
        languages = [native_lang]
    elif isinstance(native_lang, list):
        languages = native_lang[:]
    else:
        languages = ["en"]
    
    # ALWAYS ensure English is included for international flights
    if "en" not in languages and "en-US" not in languages:
        languages.append("en")
    
    logger.debug(f"Target languages determined: {languages}")
    return languages

def translate_with_global_formatting(text: str, target_language: str, airline_config: dict, simbrief_data: dict) -> str:
    """
    Translate text with global aviation formatting standards
    """
    logger.info(f"Translating to {target_language} with global formatting")
    
    # Check cache
    if ENABLE_TRANSLATION_CACHE:
        cached = get_cached_translation(text, target_language)
        if cached:
            logger.info(f"Using cached translation for {target_language}")
            return cached
    
    # Get OpenAI client
    client = get_openai_client()
    if not client:
        logger.error(f"OpenAI not available for {target_language}")
        return text
    
    # Build translation prompt
    prompt = build_global_translation_prompt(text, target_language, airline_config, simbrief_data)
    
    try:
        response = client.chat.completions.create(
            model=TRANSLATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TRANSLATION_TOKENS,
            temperature=TRANSLATION_TEMPERATURE
        )
        
        translated = response.choices[0].message.content.strip()
        
        # Apply global post-processing
        translated = apply_global_post_processing(translated, target_language)
        
        # Cache translation
        if ENABLE_TRANSLATION_CACHE:
            cache_translation(text, target_language, translated)
        
        logger.info(f"Translation to {target_language} completed")
        return translated
        
    except Exception as e:
        logger.error(f"Translation failed for {target_language}: {e}")
        return text

def build_global_translation_prompt(text: str, target_language: str, airline_config: dict, simbrief_data: dict) -> str:
    """Build aviation-standard translation prompt"""
    
    gender = airline_config.get("genre_native", "female")
    airline_name = simbrief_data.get("airline_name", "the airline")
    dest_city = simbrief_data.get("dest_city", "destination")
    
    prompt = f"""Translate this aviation announcement to {target_language}.

CONTEXT:
- Airline: {airline_name}
- Destination: {dest_city}
- Voice: {gender} flight attendant

AVIATION TRANSLATION REQUIREMENTS:
1. Use formal, professional aviation language
2. Keep flight numbers as individual digits (never change "one five eight two")
3. Use proper time expressions with correct singular/plural
4. Maintain exact same information and meaning
5. Use respectful, courteous tone appropriate for aviation
6. Follow aviation industry standards for {target_language}

CRITICAL RULES:
- Flight numbers must remain as spoken digits
- Time expressions must be grammatically correct
- Use formal pronouns and address passengers respectfully
- Keep all safety and procedural information accurate

TEXT TO TRANSLATE:
\"\"\"{text}\"\"\""""

    # Add language-specific aviation standards
    if target_language == "pt-BR":
        prompt += """

PORTUGUESE AVIATION STANDARDS:
- Use "senhoras e senhores passageiros" for formal address
- Time: "são X horas e Y minutos" (plural) or "é 1 hora" (singular)
- Flight numbers: keep as individual digits (um cinco oito dois)
- Use formal "vocês" treatment throughout
- Aviation terminology: "voo", "tripulação", "comandante", "portão"
"""
    
    elif target_language == "es-ES":
        prompt += """

SPANISH AVIATION STANDARDS:
- Use "señoras y señores pasajeros" for formal address
- Use formal "ustedes" form throughout
- Keep flight numbers as individual digits
- Proper Spanish aviation terminology
"""
    
    elif target_language == "fr-FR":
        prompt += """

FRENCH AVIATION STANDARDS:
- Use "mesdames et messieurs" for formal address
- Use formal "vous" form throughout
- Keep flight numbers as individual digits
- Proper French aviation terminology
"""
    
    return prompt

def apply_global_post_processing(text: str, target_language: str) -> str:
    """Apply global post-processing fixes for all languages"""
    if not APPLY_GRAMMAR_FIXES:
        return text
    
    # Remove quote wrapping
    processed = text.strip()
    while ((processed.startswith('"') and processed.endswith('"')) or 
           (processed.startswith("'") and processed.endswith("'"))):
        processed = processed[1:-1].strip()
    
    # Remove quote blocks
    if processed.startswith('"""') and processed.endswith('"""'):
        processed = processed[3:-3].strip()
    
    # Language-specific fixes
    if target_language == "pt-BR":
        processed = apply_portuguese_global_fixes(processed)
    elif target_language == "es-ES":
        processed = apply_spanish_global_fixes(processed)
    elif target_language == "fr-FR":
        processed = apply_french_global_fixes(processed)
    
    return processed

def apply_portuguese_global_fixes(text: str) -> str:
    """Apply Portuguese aviation-specific fixes"""
    fixes = [
        # Time expressions
        (r'\bhora local e (\d+) horas?\b', r'horário local são \1 horas'),
        (r'\bhora local e (\d+) hora\b', r'horário local é \1 hora'),
        (r'\bé (\d+) horas e (\d+) minutos?\b', r'são \1 horas e \2 minutos'),
        (r'\bé (\d+) hora e (\d+) minutos?\b', r'é \1 hora e \2 minutos'),
        
        # Ensure proper address
        (r'\bSenhoras e senhores\b', r'Senhoras e senhores passageiros'),
        
        # Fix common aviation terms
        (r'\bcinto de segurança\b', r'cinto de segurança'),
        (r'\bcompartimentos superiores\b', r'compartimentos superiores'),
    ]
    
    for pattern, replacement in fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text

def apply_spanish_global_fixes(text: str) -> str:
    """Apply Spanish aviation-specific fixes"""
    # Add Spanish-specific fixes as needed
    return text

def apply_french_global_fixes(text: str) -> str:
    """Apply French aviation-specific fixes"""
    # Add French-specific fixes as needed
    return text

def get_cached_translation(text: str, target_language: str) -> str:
    """Get cached translation if available"""
    if not ENABLE_TRANSLATION_CACHE:
        return None
    
    try:
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
        cache_file = CACHE_DIR / f"{target_language}_{text_hash}.txt"
        
        if cache_file.exists():
            from datetime import datetime, timedelta
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            
            if cache_age <= timedelta(hours=CACHE_DURATION_HOURS):
                return cache_file.read_text(encoding="utf-8")
            else:
                cache_file.unlink()
        
        return None
        
    except Exception:
        return None

def cache_translation(text: str, target_language: str, translation: str):
    """Cache translation for future use"""
    if not ENABLE_TRANSLATION_CACHE:
        return
    
    try:
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
        cache_file = CACHE_DIR / f"{target_language}_{text_hash}.txt"
        cache_file.write_text(translation, encoding="utf-8")
        
    except Exception:
        pass