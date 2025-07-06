"""
run_arrival.pyw - Script arrival TOTALMENTE SILENCIOSO

- Sem popup windows
- Sem console output  
- Sem ícone de loading
- Apenas logs para arquivo
- Execução invisível completa
"""

import sys
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime

# ============================================
# CONFIGURAÇÃO SILENCIOSA TOTAL
# ============================================

# Força execução silenciosa
COMPLETELY_SILENT = True
NO_CONSOLE_OUTPUT = True
NO_POPUPS = True
NO_LOADING_ICONS = True

# Configurações específicas .pyw
CONTEXT = "arrival"
FINAL_AUDIO_NAME = "arrival_pa.wav"
TEMPLATE_NAME = "arrival"

# Cleanup settings
CLEANUP_INDIVIDUAL_FILES = True
CLEANUP_TEMP_FILES = True
AUTO_CLEANUP = True

# Cache settings
TEXT_CACHE_ENABLED = True
TEXT_CACHE_DURATION_DAYS = 100  # Cache permanente

# ============================================
# SUPRESSÃO DE OUTPUT SILENCIOSA
# ============================================

# Redirecionar TODOS os outputs para null
if COMPLETELY_SILENT:
    # Suprimir stdout e stderr
    if sys.stdout is not None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is not None:
        sys.stderr = open(os.devnull, 'w')

# Monkey patch subprocess para NUNCA mostrar windows
if NO_POPUPS:
    original_popen_init = subprocess.Popen.__init__
    
    def silent_popen_init(self, *args, **kwargs):
        # Força supressão de TODAS as janelas
        if os.name == 'nt':  # Windows
            if 'creationflags' not in kwargs:
                kwargs['creationflags'] = 0
            kwargs['creationflags'] |= subprocess.CREATE_NO_WINDOW
            # Força pipes para suprimir output
            if 'stdout' not in kwargs:
                kwargs['stdout'] = subprocess.DEVNULL
            if 'stderr' not in kwargs:
                kwargs['stderr'] = subprocess.DEVNULL
        return original_popen_init(self, *args, **kwargs)
    
    subprocess.Popen.__init__ = silent_popen_init

# ============================================
# IMPORTS (APÓS SUPRESSÃO)
# ============================================

from core.utils import ENV, logger, clear_logs, clear_temp_files, ROOT
from core.simbrief_handler import SimbriefHandler
from core.weather_handler import get_airport_weather
from core.tts_manager import generate_audio_files
from core.post_processor import process_announcement

# Cache directories
TEXT_CACHE_DIR = ROOT / "data" / "cache" / "txt" / CONTEXT
TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================
# FUNÇÕES SILENCIOSAS
# ============================================

def silent_log(message: str):
    """Log apenas para arquivo, NUNCA para console"""
    try:
        logger.info(f"[SILENT] {message}")
    except:
        pass  # Falha silenciosa

def silent_error(message: str, exception=None):
    """Error logging silencioso"""
    try:
        logger.error(f"[SILENT ERROR] {message}")
        if exception:
            logger.exception("Silent exception:")
    except:
        pass  # Falha silenciosa

def silent_cleanup():
    """Cleanup totalmente silencioso"""
    try:
        if CLEANUP_TEMP_FILES:
            clear_temp_files(silent=True)
        
        if CLEANUP_INDIVIDUAL_FILES:
            output_dir = ROOT / "output"
            individual_files = [
                "english.wav", "native.wav", "destination.wav",
                "final_announcement.wav", "final_announcement_raw.wav",
                "arrival_announcement.wav"
            ]
            
            for filename in individual_files:
                try:
                    file_path = output_dir / filename
                    if file_path.exists():
                        file_path.unlink()
                except:
                    pass  # Falha silenciosa
        
        silent_log("Silent cleanup completed")
        
    except:
        pass  # Falha silenciosa

def silent_rename_audio():
    """Renomeia audio final silenciosamente"""
    try:
        output_dir = ROOT / "output"
        
        # Tenta ambos os nomes possíveis
        possible_names = ["arrival_announcement.wav", "final_announcement.wav"]
        old_path = None
        
        for name in possible_names:
            candidate = output_dir / name
            if candidate.exists():
                old_path = candidate
                break
        
        if old_path:
            new_path = output_dir / FINAL_AUDIO_NAME
            if new_path.exists():
                new_path.unlink()
            old_path.rename(new_path)
            silent_log(f"Audio renamed to {FINAL_AUDIO_NAME}")
            return new_path
        
        return None
    except:
        return None

# ============================================
# FUNÇÕES ESPECÍFICAS ARRIVAL
# ============================================

def silent_load_airline_config(icao: str) -> dict:
    """Carrega config da airline silenciosamente"""
    try:
        config_file = ROOT / "data" / "airline_profiles.json"
        config = json.loads(config_file.read_text())
        return config.get(icao, {})
    except:
        return {}

def silent_get_static_cached(static_text: str, lang: str, gender: str) -> str:
    """Obtém texto estático do cache (permanente)"""
    try:
        if not static_text or lang in ["en", "en-US"] or not TEXT_CACHE_ENABLED:
            return static_text
        
        cache_file = TEXT_CACHE_DIR / f"{lang}_{gender}_static.txt"
        
        if cache_file.exists():
            cached_text = cache_file.read_text(encoding="utf-8")
            silent_log(f"Using cached static text for {lang}_{gender}")
            return cached_text
        
        # Se não tem cache, traduz e salva
        translated = silent_translate_text(static_text, lang, gender)
        
        try:
            cache_file.write_text(translated, encoding="utf-8")
            silent_log(f"Cached static text for {lang}_{gender}")
        except:
            pass
        
        return translated
        
    except:
        return static_text

def silent_translate_text(text: str, target_lang: str, gender: str) -> str:
    """Traduz texto silenciosamente"""
    try:
        from core.utils import get_openai_client
        
        client = get_openai_client()
        if not client:
            return text
        
        prompt = f"""Translate to {target_lang}.
Style: formal, courteous {gender} flight-attendant speech.
Keep details exact; add culturally correct formal particles.

Text: \"\"\"{text}\"\"\""""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.2
        )
        
        translated = response.choices[0].message.content.strip()
        
        # Remove quotes
        while ((translated.startswith('"') and translated.endswith('"')) or 
               (translated.startswith("'") and translated.endswith("'"))):
            translated = translated[1:-1].strip()
        
        if translated.startswith('"""') and translated.endswith('"""'):
            translated = translated[3:-3].strip()
        
        return translated
        
    except:
        return text

def silent_generate_texts(simbrief_data: dict, weather_data: dict) -> dict:
    """Gera textos de arrival silenciosamente"""
    try:
        # Load template
        template_path = ROOT / "data" / "prompts" / f"{TEMPLATE_NAME}.txt"
        if not template_path.exists():
            silent_error(f"Template not found: {template_path}")
            return {"en": "Template not found"}
        
        template = template_path.read_text(encoding="utf-8")
        
        # Split dynamic/static
        parts = template.split('\n\n', 1)
        dynamic_part = parts[0].strip()
        static_part = parts[1].strip() if len(parts) > 1 else ""
        
        # Substitute variables
        variables = {
            "dest_city": simbrief_data["dest_city"],
            "local_time": weather_data["local_time"],
            "temperature": weather_data["temperature"],
            "airline_name": simbrief_data["airline_name"]
        }
        
        try:
            dynamic_processed = dynamic_part.format(**variables)
        except KeyError as e:
            silent_error(f"Missing variable in template: {e}")
            return {"en": "Template variable error"}
        
        english_text = f"{dynamic_processed}\n\n{static_part}".strip()
        texts = {"en": english_text}
        
        # Get translations
        airline_config = silent_load_airline_config(simbrief_data["icao"])
        languages = airline_config.get("language", "en")
        
        if isinstance(languages, str):
            lang_list = [languages]
        elif isinstance(languages, list):
            lang_list = languages
        else:
            lang_list = ["en"]
        
        # Add translations
        for lang in lang_list:
            if lang not in ["en", "en-US"]:
                gender = airline_config.get("genre_native", "female")
                
                # Translate dynamic (fresh)
                dynamic_translated = silent_translate_text(dynamic_processed, lang, gender)
                
                # Get static (cached)
                static_translated = silent_get_static_cached(static_part, lang, gender)
                
                texts[lang] = f"{dynamic_translated}\n\n{static_translated}".strip()
        
        silent_log(f"Generated texts: {list(texts.keys())}")
        return texts
        
    except Exception as e:
        silent_error("Text generation failed", e)
        return {"en": "Text generation error"}

# ============================================
# PROCESSO PRINCIPAL SILENCIOSO
# ============================================

def silent_arrival_process(username: str):
    """
    Processo de arrival COMPLETAMENTE SILENCIOSO
    
    Args:
        username: SimBrief username
    """
    try:
        silent_log(f"Starting silent arrival process for: {username}")
        
        # Step 1: SimBrief data
        try:
            handler = SimbriefHandler(username)
            simbrief_data = handler.fetch_flight_data()
            silent_log("SimBrief data fetched successfully")
        except Exception as e:
            silent_error("SimBrief fetch failed", e)
            return False
        
        # Step 2: Weather data
        try:
            weather_data = get_airport_weather(simbrief_data["dest_icao"])
            silent_log("Weather data fetched successfully")
        except Exception as e:
            silent_error("Weather fetch failed", e)
            return False
        
        # Step 3: Text generation
        try:
            texts = silent_generate_texts(simbrief_data, weather_data)
            silent_log(f"Texts generated: {list(texts.keys())}")
        except Exception as e:
            silent_error("Text generation failed", e)
            return False
        
        # Step 4: TTS generation (silencioso)
        try:
            audio_files = generate_audio_files(texts, simbrief_data, context=CONTEXT)
            silent_log(f"Audio files generated: {list(audio_files.keys())}")
        except Exception as e:
            silent_error("TTS generation failed", e)
            return False
        
        # Step 5: Post-processing (silencioso)
        try:
            result = process_announcement(audio_files, simbrief_data)
            if result.get("success"):
                silent_log("Post-processing completed successfully")
            else:
                silent_error("Post-processing failed")
                return False
        except Exception as e:
            silent_error("Post-processing failed", e)
            return False
        
        # Step 6: Finalization
        try:
            final_audio = silent_rename_audio()
            if final_audio:
                silent_log(f"Final audio created: {final_audio.name}")
            
            if AUTO_CLEANUP:
                silent_cleanup()
            
            silent_log("Silent arrival process completed successfully")
            return True
            
        except Exception as e:
            silent_error("Finalization failed", e)
            return False
        
    except Exception as e:
        silent_error("Critical error in silent arrival process", e)
        return False

# ============================================
# MAIN SILENCIOSO
# ============================================

def silent_main():
    """Main function COMPLETAMENTE SILENCIOSA"""
    try:
        # Cleanup inicial silencioso
        if CLEANUP_TEMP_FILES:
            clear_temp_files(silent=True)
        
        # Obter username
        username = None
        
        # Tentar argumentos da linha de comando
        if len(sys.argv) > 1:
            username = sys.argv[1]
        
        # Tentar variável de ambiente
        if not username:
            username = ENV.get("SIMBRIEF_USER")
        
        # Se não tem username, falha silenciosa
        if not username:
            silent_error("No SimBrief username provided")
            return
        
        # Executar processo silencioso
        success = silent_arrival_process(username)
        
        if success:
            silent_log("SILENT ARRIVAL COMPLETED SUCCESSFULLY")
        else:
            silent_error("SILENT ARRIVAL FAILED")
        
    except Exception as e:
        silent_error("Critical error in silent main", e)
    
    finally:
        # Cleanup final sempre
        try:
            silent_cleanup()
        except:
            pass

# ============================================
# EXECUÇÃO SILENCIOSA
# ============================================

if __name__ == "__main__":
    try:
        silent_main()
    except:
        # Falha completamente silenciosa
        pass
    
    # NUNCA mostrar qualquer output ou esperar input
    # Script termina silenciosamente