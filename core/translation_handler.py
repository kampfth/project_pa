"""
core/translation_handler.py - Sistema corrigido com logs detalhados

CORREÇÕES:
1. USAR duration_text do SimBrief (não recalcular)
2. LOGS MUITO DETALHADOS para debugging
3. Aviação formal: "one hour" não "an hour"
"""

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime

from core.utils import ROOT, ENV, logger, get_openai_client

# ============================================
# CONFIGURAÇÕES OPENAI
# ============================================

# Modelo OpenAI otimizado
OPENAI_MODEL = "gpt-4o"  # Modelo mais avançado para traduções de qualidade
OPENAI_TEMPERATURE = 0.1  # Baixa variabilidade para consistência
OPENAI_MAX_TOKENS = 1000
OPENAI_TIMEOUT = 30

# System prompt para OpenAI
OPENAI_SYSTEM_PROMPT = """You are a professional airline flight attendant translator. 

Your role is to translate boarding announcements with:
- Professional aviation tone
- Accurate terminology
- Formal but warm style
- Perfect grammar
- NO word repetitions or duplications

Always provide ONLY the translation, no explanations."""

# User prompt template
OPENAI_USER_PROMPT = """Translate this airline boarding announcement to {target_language}.

Context: {airline_name} flight {flight_number} to {dest_city}

Requirements:
- Professional flight attendant tone
- Formal language appropriate for aviation
- Accurate aviation terminology
- NO word duplications
- Natural flow for spoken announcement

Text to translate:
{text}

Provide only the translation:"""

# ============================================
# CONFIGURAÇÕES GERAIS
# ============================================

# Cache settings
CACHE_ENABLED = True
CACHE_NEVER_EXPIRES = True  # Cache permanente
CACHE_DIR = ROOT / "data" / "cache" / "translations"

# Template settings
PROMPTS_DIR = ROOT / "data" / "prompts"
AIRLINE_FILE = ROOT / "data" / "airline_profiles.json"

# Quality control
ENABLE_DUPLICATION_FIX = True
MAX_TRANSLATION_ATTEMPTS = 2

# Detailed logging
ENABLE_DETAILED_LOGS = True
LOG_TEMPLATE_CONTENT = True
LOG_TRANSLATION_CONTENT = True
LOG_VARIABLE_SUBSTITUTION = True

# Criar diretórios necessários
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================
# LOGGING DETALHADO
# ============================================

def log_detailed(step: str, content: str = "", data: dict = None):
    """Log detalhado para debugging"""
    if not ENABLE_DETAILED_LOGS:
        return
    
    logger.info(f"🔍 DETAILED LOG: {step}")
    if content:
        logger.info(f"📄 Content: {content}")
    if data:
        logger.info(f"📊 Data: {json.dumps(data, indent=2, ensure_ascii=False)}")

def log_template_processing(template_name: str, template_content: str, variables: dict, result: str):
    """Log específico para processamento de template"""
    if not LOG_TEMPLATE_CONTENT:
        return
    
    logger.info(f"📝 TEMPLATE PROCESSING: {template_name}")
    logger.info(f"📄 Template content (first 200 chars): {template_content[:200]}...")
    logger.info(f"🔧 Variables used:")
    for key, value in variables.items():
        logger.info(f"    {key}: '{value}'")
    logger.info(f"✅ Result (first 200 chars): {result[:200]}...")

def log_translation_process(language: str, original: str, translated: str, cached: bool = False):
    """Log específico para tradução"""
    if not LOG_TRANSLATION_CONTENT:
        return
    
    cache_status = "CACHED" if cached else "NEW"
    logger.info(f"🌍 TRANSLATION TO {language}: {cache_status}")
    logger.info(f"📥 Original: {original[:150]}...")
    logger.info(f"📤 Translated: {translated[:150]}...")

# ============================================
# FUNÇÃO PRINCIPAL
# ============================================

def build_texts(simbrief_data: dict) -> dict:
    """
    Gera textos para todos os idiomas configurados
    
    Args:
        simbrief_data: Dados do voo do SimBrief
        
    Returns:
        dict: Textos por idioma {"en": "texto", "pt-BR": "texto"}
    """
    try:
        logger.info("=" * 60)
        logger.info("🌍 INICIANDO GERAÇÃO DE TEXTOS COM LOGS DETALHADOS")
        logger.info("=" * 60)
        
        # Log dos dados SimBrief recebidos
        log_detailed("SimBrief Data Received", data=simbrief_data)
        
        # 1. Carregar configuração da companhia
        logger.info("📋 Step 1: Carregando configuração da companhia")
        airline_config = load_airline_config(simbrief_data["icao"])
        log_detailed("Airline Config Loaded", data=airline_config)
        
        # 2. Determinar tipo de template
        logger.info("📄 Step 2: Determinando tipo de template")
        template_type = get_template_type()
        logger.info(f"✅ Template type determined: {template_type}")
        
        # 3. Processar template em inglês
        logger.info("🔤 Step 3: Processando template em inglês")
        english_text = process_english_template(template_type, simbrief_data)
        logger.info(f"✅ English template processed successfully")
        logger.info(f"📏 English text length: {len(english_text)} characters")
        
        # 4. Começar com inglês
        texts = {"en": english_text}
        
        # 5. Obter idiomas alvo
        logger.info("🎯 Step 4: Obtendo idiomas alvo")
        target_languages = get_target_languages(airline_config)
        logger.info(f"🌐 Target languages: {target_languages}")
        
        # 6. Traduzir para outros idiomas
        logger.info("🔄 Step 5: Iniciando traduções")
        for language in target_languages:
            if language not in ["en", "en-US"]:
                try:
                    logger.info(f"🌍 Translating to {language}")
                    translated = translate_text(english_text, language, simbrief_data)
                    texts[language] = translated
                    logger.info(f"✅ Translation to {language} completed successfully")
                    logger.info(f"📏 {language} text length: {len(translated)} characters")
                except Exception as e:
                    logger.error(f"❌ Translation error for {language}: {e}")
                    logger.exception(f"Translation exception for {language}")
        
        logger.info("=" * 60)
        logger.info(f"🎉 GERAÇÃO DE TEXTOS CONCLUÍDA")
        logger.info(f"📊 Languages generated: {list(texts.keys())}")
        logger.info(f"📏 Total texts: {len(texts)}")
        
        # Log conteúdo final de cada idioma
        for lang, text in texts.items():
            logger.info(f"📝 {lang.upper()} FINAL TEXT:")
            logger.info(f"   Length: {len(text)} chars")
            logger.info(f"   Preview: {text[:100]}...")
        
        logger.info("=" * 60)
        
        return texts
        
    except Exception as e:
        logger.error(f"💥 ERRO CRÍTICO na geração de textos: {e}")
        logger.exception("Stack trace completo:")
        raise

# ============================================
# FUNÇÕES DE SUPORTE
# ============================================

def load_airline_config(icao: str) -> dict:
    """Carrega configuração da companhia aérea"""
    try:
        logger.info(f"📂 Loading airline config for: {icao}")
        
        if not AIRLINE_FILE.exists():
            raise FileNotFoundError(f"Arquivo de perfis não encontrado: {AIRLINE_FILE}")
        
        with open(AIRLINE_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if icao not in config:
            available_airlines = list(config.keys())
            logger.error(f"❌ Airline {icao} not found. Available: {available_airlines}")
            raise ValueError(f"Companhia {icao} não encontrada")
        
        airline_config = config[icao]
        logger.info(f"✅ Airline config loaded successfully for {icao}")
        
        return airline_config
        
    except Exception as e:
        logger.error(f"💥 Erro ao carregar configuração da companhia: {e}")
        raise

def get_template_type() -> str:
    """Determina o tipo de template baseado no contexto"""
    import inspect
    
    logger.info("🔍 Analyzing call stack to determine template type")
    
    # Verificar stack de chamadas para determinar contexto
    for frame_info in inspect.stack():
        filename = frame_info.filename.lower()
        logger.debug(f"   Checking frame: {filename}")
        if 'arrival' in filename:
            logger.info("✅ Template type: ARRIVAL")
            return "arrival"
        elif 'boarding' in filename:
            logger.info("✅ Template type: BOARDING (welcome)")
            return "welcome"
    
    logger.info("✅ Template type: DEFAULT (welcome)")
    return "welcome"  # Padrão

def process_english_template(template_type: str, simbrief_data: dict) -> str:
    """Processa template em inglês com variáveis"""
    try:
        logger.info(f"📄 Processing English template: {template_type}")
        
        # Carregar template
        template_path = PROMPTS_DIR / f"{template_type}.txt"
        logger.info(f"📂 Template path: {template_path}")
        
        if not template_path.exists():
            raise FileNotFoundError(f"Template não encontrado: {template_path}")
        
        template = template_path.read_text(encoding="utf-8")
        logger.info(f"📏 Template loaded, length: {len(template)} characters")
        
        # Preparar variáveis
        logger.info("🔧 Preparing template variables")
        variables = prepare_variables(simbrief_data)
        
        # Substituir variáveis
        logger.info("🔄 Substituting variables in template")
        processed_text = template.format(**variables)
        
        # Log do processamento do template
        if LOG_TEMPLATE_CONTENT:
            log_template_processing(template_type, template, variables, processed_text)
        
        # Verificar e corrigir duplicações
        if ENABLE_DUPLICATION_FIX:
            logger.info("🔍 Checking for duplications")
            original_length = len(processed_text)
            processed_text = fix_duplications(processed_text)
            if len(processed_text) != original_length:
                logger.info("✅ Duplications fixed")
            else:
                logger.info("✅ No duplications found")
        
        logger.info(f"✅ Template processing completed successfully")
        logger.info(f"📏 Final processed text length: {len(processed_text)} characters")
        
        return processed_text
        
    except Exception as e:
        logger.error(f"💥 Erro ao processar template: {e}")
        logger.exception("Template processing exception:")
        raise

def prepare_variables(simbrief_data: dict) -> dict:
    """Prepara variáveis para o template COM CORREÇÃO DE DURAÇÃO"""
    logger.info("🔧 Preparing template variables")
    
    variables = {}
    
    # Saudação baseada na hora
    hour = datetime.now().hour
    if 5 <= hour < 12:
        variables["greeting"] = "Good morning"
    elif 12 <= hour < 18:
        variables["greeting"] = "Good afternoon"
    else:
        variables["greeting"] = "Good evening"
    
    logger.info(f"👋 Greeting determined: {variables['greeting']}")
    
    # Dados básicos
    variables["dest_city"] = simbrief_data.get("dest_city", "destination")
    variables["airline_name"] = simbrief_data.get("airline_name", "our airline")
    
    # Número do voo (convertido para dígitos falados)
    flight_number = simbrief_data.get("flight_number", "")
    variables["flight_number"] = convert_flight_number(flight_number)
    
    # CORREÇÃO CRÍTICA: USAR duration_text do SimBrief, NÃO recalcular
    if "duration_text" in simbrief_data and simbrief_data["duration_text"]:
        variables["duration"] = simbrief_data["duration_text"]
        logger.info(f"✅ Using SimBrief duration_text: '{variables['duration']}'")
    else:
        # Fallback apenas se duration_text não existir
        duration_seconds = simbrief_data.get("duration_seconds", 0)
        variables["duration"] = format_duration_formal(duration_seconds)
        logger.warning(f"⚠️ duration_text not found, calculated: '{variables['duration']}'")
    
    # Temperatura e hora local (para arrival)
    if "temperature" in simbrief_data:
        variables["temperature"] = simbrief_data["temperature"]
        logger.info(f"🌡️ Temperature: {variables['temperature']}")
    
    if "local_time" in simbrief_data:
        variables["local_time"] = simbrief_data["local_time"]
        logger.info(f"🕐 Local time: {variables['local_time']}")
    
    # Log todas as variáveis preparadas
    if LOG_VARIABLE_SUBSTITUTION:
        logger.info("📋 ALL TEMPLATE VARIABLES PREPARED:")
        for key, value in variables.items():
            logger.info(f"   {key}: '{value}'")
    
    return variables

def convert_flight_number(flight_number: str) -> str:
    """Converte número do voo para dígitos falados"""
    try:
        logger.info(f"🔢 Converting flight number: {flight_number}")
        
        # Extrair apenas números
        numbers = re.findall(r'\d', str(flight_number))
        if not numbers:
            logger.warning(f"⚠️ No digits found in flight number: {flight_number}")
            return flight_number
        
        # Mapear dígitos para palavras
        digit_words = {
            '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
            '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'
        }
        
        spoken_digits = [digit_words[digit] for digit in numbers]
        result = ' '.join(spoken_digits)
        
        logger.info(f"✅ Flight number converted: {flight_number} → {result}")
        return result
        
    except Exception as e:
        logger.error(f"💥 Error converting flight number: {e}")
        return flight_number

def format_duration_formal(duration_seconds: int) -> str:
    """
    Formata duração do voo EM FORMATO FORMAL DE AVIAÇÃO
    CORREÇÃO: Sempre usar "one hour" nunca "an hour"
    """
    try:
        logger.info(f"⏱️ Formatting duration: {duration_seconds} seconds")
        
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        
        logger.info(f"📊 Duration breakdown: {hours} hours, {minutes} minutes")
        
        parts = []
        
        if hours > 0:
            # CORREÇÃO CRÍTICA: Usar números formais, não artigos
            if hours == 1:
                parts.append("one hour")  # ✅ FORMAL: "one hour" não "an hour"
            else:
                hour_words = {
                    2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
                    7: "seven", 8: "eight", 9: "nine", 10: "ten"
                }
                hour_word = hour_words.get(hours, str(hours))
                parts.append(f"{hour_word} hours")
        
        if minutes > 0:
            minute_words = {
                1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
                11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
                16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty",
                21: "twenty-one", 22: "twenty-two", 23: "twenty-three", 24: "twenty-four",
                25: "twenty-five", 26: "twenty-six", 27: "twenty-seven", 28: "twenty-eight",
                29: "twenty-nine", 30: "thirty", 40: "forty", 45: "forty-five", 50: "fifty"
            }
            minute_word = minute_words.get(minutes, str(minutes))
            minute_unit = "minute" if minutes == 1 else "minutes"
            parts.append(f"{minute_word} {minute_unit}")
        
        if len(parts) == 2:
            result = f"{parts[0]} and {parts[1]}"
        elif len(parts) == 1:
            result = parts[0]
        else:
            result = "unknown duration"
        
        logger.info(f"✅ Duration formatted: {result}")
        return result
            
    except Exception as e:
        logger.error(f"💥 Error formatting duration: {e}")
        return "unknown duration"

def get_target_languages(airline_config: dict) -> list:
    """Obtém lista de idiomas alvo"""
    try:
        logger.info("🌐 Determining target languages")
        
        language = airline_config.get("language", "en")
        logger.info(f"📋 Airline language setting: {language}")
        
        if isinstance(language, str):
            languages = [language]
        elif isinstance(language, list):
            languages = language[:]
        else:
            languages = ["en"]
        
        # Garantir que inglês está incluído
        if "en" not in languages and "en-US" not in languages:
            languages.append("en")
            logger.info("✅ Added English to languages list")
        
        logger.info(f"🎯 Final target languages: {languages}")
        return languages
        
    except Exception as e:
        logger.error(f"💥 Error determining target languages: {e}")
        return ["en"]

# ============================================
# SISTEMA DE TRADUÇÃO
# ============================================

def translate_text(text: str, target_language: str, simbrief_data: dict) -> str:
    """
    Traduz texto para idioma alvo
    
    Args:
        text: Texto em inglês
        target_language: Idioma alvo (ex: "pt-BR")
        simbrief_data: Dados do voo
        
    Returns:
        str: Texto traduzido
    """
    try:
        logger.info(f"🌍 Starting translation to {target_language}")
        logger.info(f"📏 Input text length: {len(text)} characters")
        
        # Verificar cache primeiro
        if CACHE_ENABLED:
            logger.info("💾 Checking translation cache")
            cached = get_cached_translation(text, target_language)
            if cached:
                logger.info(f"✅ Found cached translation for {target_language}")
                log_translation_process(target_language, text, cached, cached=True)
                return cached
            else:
                logger.info(f"❌ No cached translation found for {target_language}")
        
        # Obter cliente OpenAI
        logger.info("🤖 Getting OpenAI client")
        client = get_openai_client()
        if not client:
            logger.warning(f"❌ OpenAI not available for {target_language}")
            return text
        
        logger.info("✅ OpenAI client obtained successfully")
        
        # Fazer tradução
        logger.info(f"🔄 Performing translation to {target_language}")
        translated = perform_translation(client, text, target_language, simbrief_data)
        
        # Pós-processamento
        logger.info("🔧 Post-processing translation")
        original_translated = translated
        translated = post_process_translation(translated, target_language)
        
        if translated != original_translated:
            logger.info("✅ Post-processing applied changes")
        else:
            logger.info("✅ No post-processing changes needed")
        
        # Log da tradução
        log_translation_process(target_language, text, translated, cached=False)
        
        # Salvar no cache
        if CACHE_ENABLED:
            logger.info("💾 Saving translation to cache")
            save_to_cache(text, target_language, translated)
        
        logger.info(f"✅ Translation to {target_language} completed successfully")
        return translated
        
    except Exception as e:
        logger.error(f"💥 Translation error for {target_language}: {e}")
        logger.exception(f"Translation exception for {target_language}:")
        return text

def perform_translation(client, text: str, target_language: str, simbrief_data: dict) -> str:
    """Executa a tradução via OpenAI"""
    try:
        logger.info(f"🤖 Calling OpenAI API for {target_language}")
        
        # Preparar prompt
        user_prompt = OPENAI_USER_PROMPT.format(
            target_language=target_language,
            airline_name=simbrief_data.get("airline_name", "the airline"),
            flight_number=simbrief_data.get("flight_number", ""),
            dest_city=simbrief_data.get("dest_city", "destination"),
            text=text
        )
        
        logger.info(f"📝 OpenAI prompt prepared (length: {len(user_prompt)} chars)")
        logger.info(f"🔧 Using model: {OPENAI_MODEL}")
        logger.info(f"🌡️ Temperature: {OPENAI_TEMPERATURE}")
        
        # Chamada para OpenAI
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": OPENAI_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=OPENAI_MAX_TOKENS,
            temperature=OPENAI_TEMPERATURE,
            timeout=OPENAI_TIMEOUT
        )
        
        translated = response.choices[0].message.content.strip()
        
        logger.info(f"✅ OpenAI API call successful")
        logger.info(f"📏 Translation length: {len(translated)} characters")
        logger.info(f"🔍 Translation preview: {translated[:100]}...")
        
        return translated
        
    except Exception as e:
        logger.error(f"💥 OpenAI API call failed: {e}")
        logger.exception("OpenAI API exception:")
        raise

def post_process_translation(text: str, target_language: str) -> str:
    """Pós-processamento da tradução"""
    try:
        logger.info(f"🔧 Post-processing translation for {target_language}")
        original_text = text
        
        # Remover aspas se presentes
        text = text.strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()
            logger.info("✅ Removed surrounding quotes")
        if text.startswith("'") and text.endswith("'"):
            text = text[1:-1].strip()
            logger.info("✅ Removed surrounding single quotes")
        
        # Corrigir duplicações
        if ENABLE_DUPLICATION_FIX:
            logger.info("🔍 Checking for duplications in translation")
            before_fix = text
            text = fix_duplications(text)
            if text != before_fix:
                logger.info("✅ Fixed duplications in translation")
            else:
                logger.info("✅ No duplications found in translation")
        
        # Correções específicas por idioma
        if target_language == "pt-BR":
            logger.info("🇧🇷 Applying Portuguese-specific fixes")
            text = fix_portuguese_issues(text)
        
        if text != original_text:
            logger.info("✅ Post-processing made changes")
        else:
            logger.info("✅ No post-processing changes needed")
        
        return text
        
    except Exception as e:
        logger.error(f"💥 Post-processing error: {e}")
        logger.exception("Post-processing exception:")
        return text

def fix_duplications(text: str) -> str:
    """
    Corrige duplicações de palavras como 'passageiros passageiros'
    
    Args:
        text: Texto com possíveis duplicações
        
    Returns:
        str: Texto sem duplicações
    """
    try:
        logger.info("🔍 Checking for word duplications")
        
        # Padrão para detectar palavras repetidas consecutivas
        # Exemplo: "passageiros passageiros" -> "passageiros"
        duplication_pattern = r'\b(\w+)\s+\1\b'
        
        # Encontrar duplicações
        duplications = re.findall(duplication_pattern, text, re.IGNORECASE)
        
        if duplications:
            logger.warning(f"⚠️ Found duplications: {duplications}")
            
            # Corrigir duplicações
            fixed_text = re.sub(duplication_pattern, r'\1', text, flags=re.IGNORECASE)
            
            logger.info("✅ Duplications fixed successfully")
            return fixed_text
        
        logger.info("✅ No duplications found")
        return text
        
    except Exception as e:
        logger.error(f"💥 Error fixing duplications: {e}")
        return text

def fix_portuguese_issues(text: str) -> str:
    """Correções específicas para português"""
    try:
        logger.info("🇧🇷 Applying Portuguese-specific corrections")
        
        # Correções comuns
        fixes = [
            # Termos de aviação
            (r'\bcompanhia aérea\b', r'companhia'),
            (r'\bvôo\b', r'voo'),
            
            # Duplicações específicas do português
            (r'\bsenhoras senhoras\b', r'senhoras'),
            (r'\bsenhores senhores\b', r'senhores'),
            (r'\bpassageiros passageiros\b', r'passageiros'),
        ]
        
        fixes_applied = 0
        for pattern, replacement in fixes:
            original = text
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            if text != original:
                fixes_applied += 1
                logger.info(f"✅ Applied Portuguese fix: {pattern} → {replacement}")
        
        if fixes_applied > 0:
            logger.info(f"✅ Applied {fixes_applied} Portuguese-specific fixes")
        else:
            logger.info("✅ No Portuguese-specific fixes needed")
        
        return text
        
    except Exception as e:
        logger.error(f"💥 Error in Portuguese fixes: {e}")
        return text

# ============================================
# SISTEMA DE CACHE
# ============================================

def get_cache_filename(target_language: str) -> str:
    """Gera nome de arquivo de cache descritivo"""
    template_type = get_template_type()
    filename = f"{target_language}_static_{template_type}.txt"
    logger.debug(f"💾 Cache filename: {filename}")
    return filename

def get_cached_translation(text: str, target_language: str) -> str:
    """Obtém tradução do cache se disponível"""
    try:
        cache_file = CACHE_DIR / get_cache_filename(target_language)
        logger.debug(f"💾 Checking cache file: {cache_file}")
        
        if cache_file.exists():
            cached_content = cache_file.read_text(encoding="utf-8")
            logger.info(f"✅ Found cached translation: {cache_file.name}")
            return cached_content
        
        logger.info(f"❌ No cache file found: {cache_file.name}")
        return None
        
    except Exception as e:
        logger.error(f"💥 Error reading cache: {e}")
        return None

def save_to_cache(original_text: str, target_language: str, translated_text: str):
    """Salva tradução no cache permanentemente"""
    try:
        cache_file = CACHE_DIR / get_cache_filename(target_language)
        cache_file.write_text(translated_text, encoding="utf-8")
        
        logger.info(f"✅ Translation saved to cache: {cache_file.name}")
        logger.info(f"📏 Cached content length: {len(translated_text)} characters")
        
    except Exception as e:
        logger.error(f"💥 Error saving to cache: {e}")

# ============================================
# TESTE E DEBUG
# ============================================

if __name__ == "__main__":
    # Teste simples
    print("🧪 Testando sistema de tradução com logs detalhados")
    
    # Dados de teste
    test_simbrief = {
        "icao": "TAM",
        "airline_name": "LATAM Brasil",
        "flight_number": "4172",
        "dest_city": "Porto Alegre",
        "duration_seconds": 5220,
        "duration_text": "one hour and twenty-seven minutes"  # TESTE CRÍTICO
    }
    
    try:
        # Testar geração de textos
        texts = build_texts(test_simbrief)
        
        print(f"✅ Textos gerados: {list(texts.keys())}")
        
        for lang, text in texts.items():
            print(f"\n{lang.upper()}:")
            print("-" * 40)
            print(text[:200] + "..." if len(text) > 200 else text)
        
        print("\n✅ Teste concluído com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        import traceback
        traceback.print_exc()