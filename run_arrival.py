"""
run_arrival.py - Simplified arrival announcement generator

Complete flow: SimBrief → Weather → Text → TTS → Final Audio
Optimized for silent .pyw execution (no CMD windows)
WITH COMPLETE CLEANUP and proper TTS context separation
"""

import sys
import json
import os
import glob
from pathlib import Path
from datetime import datetime

# ============================================
# CONFIGURAÇÕES AJUSTÁVEIS
# ============================================

# Configurações de contexto
ANNOUNCEMENT_CONTEXT = "arrival"  # Context for TTS cache separation

# Configurações de limpeza
CLEANUP_INDIVIDUAL_FILES = True  # Remove individual audio files after combination
CLEANUP_TEMP_FILES = True  # Remove temp files during process
CLEANUP_OLD_LOGS = True  # Clear logs on startup

# Configurações de arquivo
FINAL_AUDIO_NAME = "arrival_pa.wav"  # Final audio filename
TEMPLATE_NAME = "arrival"  # Template to use from prompts/

# Configurações de cache de texto
TEXT_CACHE_ENABLED = True  # Enable text caching
TEXT_CACHE_DURATION_DAYS = 100  # Cache duration for static text

# Configurações de saída
SAVE_TEXT_SUMMARY = False  # Save text summary to file
SHOW_AUDIO_INFO = True  # Show duration/size info for final audio

# ============================================
# IMPORTS E CONFIGURAÇÃO DE SUBPROCESS
# ============================================

# Suppress all subprocess windows for .pyw execution
if sys.executable.endswith('pythonw.exe'):
    import subprocess
    # Monkey patch subprocess to always hide windows
    original_popen_init = subprocess.Popen.__init__
    
    def silent_popen_init(self, *args, **kwargs):
        # Force all subprocesses to be hidden
        if os.name == 'nt':  # Windows only
            if 'creationflags' not in kwargs:
                kwargs['creationflags'] = 0
            kwargs['creationflags'] |= subprocess.CREATE_NO_WINDOW
        return original_popen_init(self, *args, **kwargs)
    
    subprocess.Popen.__init__ = silent_popen_init

from core.utils import ENV, logger, clear_logs, clear_temp_files, ROOT
from core.simbrief_handler import SimbriefHandler
from core.weather_handler import get_airport_weather

# Cache directories
TEXT_CACHE_DIR = ROOT / "data" / "cache" / "txt" / ANNOUNCEMENT_CONTEXT
TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def show_startup():
    """Show startup info - Silent version for .pyw"""
    # Don't clear screen in .pyw mode to avoid CMD window
    if __name__ == "__main__":
        # Only clear if running directly, not as .pyw
        import os
        if not sys.executable.endswith('pythonw.exe'):
            os.system('cls' if os.name == 'nt' else 'clear')
        
        print("╔" + "═"*50 + "╗")
        print("║" + " "*15 + "🛬 ARRIVAL PA SYSTEM 🛬" + " "*14 + "║")
        print("╚" + "═"*50 + "╝")
        print()

def complete_cleanup():
    """COMPLETE cleanup for arrival: Remove ALL temporary files and logs"""
    if not CLEANUP_TEMP_FILES:
        return
        
    logger.info("Starting complete arrival cleanup")
    
    # 1. Clear logs if enabled
    if CLEANUP_OLD_LOGS:
        clear_logs()
    
    # 2. Remove all temp files in core/.temp
    try:
        import shutil
        core_temp = ROOT / "core" / ".temp"
        if core_temp.exists():
            shutil.rmtree(core_temp)
            logger.info("Removed core/.temp directory")
    except Exception as e:
        logger.warning(f"Error removing core/.temp: {e}")
    
    # 3. Remove individual audio files in output/ if enabled
    if CLEANUP_INDIVIDUAL_FILES:
        try:
            output_dir = ROOT / "output"
            individual_files = [
                "english.wav",
                "native.wav", 
                "destination.wav",
                "final_announcement.wav",
                "final_announcement_raw.wav",
                "arrival_announcement.wav"
            ]
            
            removed_count = 0
            for filename in individual_files:
                file_path = output_dir / filename
                if file_path.exists():
                    file_path.unlink()
                    removed_count += 1
                    logger.info(f"Removed {filename}")
            
            if removed_count > 0:
                logger.info(f"Cleaned {removed_count} individual audio files")
        
        except Exception as e:
            logger.warning(f"Error cleaning output files: {e}")
    
    # 4. Remove temp directories
    try:
        temp_dirs = [
            ROOT / "output" / "temp",
            ROOT / "data" / "translation.txt"  # Translation report
        ]
        
        for temp_path in temp_dirs:
            if temp_path.exists():
                if temp_path.is_dir():
                    import shutil
                    shutil.rmtree(temp_path)
                else:
                    temp_path.unlink()
                logger.info(f"Removed {temp_path.name}")
    except Exception as e:
        logger.warning(f"Error removing temp directories: {e}")
    
    logger.info("Complete arrival cleanup finished")

def rename_final_audio():
    """Rename arrival audio to standardized name"""
    try:
        output_dir = ROOT / "output"
        
        # Try both possible names
        possible_names = ["arrival_announcement.wav", "final_announcement.wav"]
        old_path = None
        
        for name in possible_names:
            candidate = output_dir / name
            if candidate.exists():
                old_path = candidate
                break
        
        if old_path:
            new_path = output_dir / FINAL_AUDIO_NAME
            
            # Remove existing file if it exists
            if new_path.exists():
                new_path.unlink()
            
            # Rename
            old_path.rename(new_path)
            logger.info(f"Renamed {old_path.name} to {FINAL_AUDIO_NAME}")
            return new_path
        
        return None
    except Exception as e:
        logger.error(f"Error renaming final audio: {e}")
        return None

def get_flight_data(username: str) -> dict:
    """Get SimBrief flight data"""
    print(f"🔍 Fetching flight data for: {username}")
    
    handler = SimbriefHandler(username)
    data = handler.fetch_flight_data()
    
    print(f"✅ {data['airline_name']} {data['flight_number']} → {data['dest_city']}")
    return data

def get_weather_data(dest_icao: str) -> dict:
    """Get weather data for destination"""
    print(f"🌡️ Getting weather for: {dest_icao}")
    
    weather = get_airport_weather(dest_icao)
    
    print(f"✅ {weather['temperature']}, {weather['local_time']}")
    return weather

def generate_texts(simbrief_data: dict, weather_data: dict) -> dict:
    """Generate arrival texts with intelligent caching"""
    print("📝 Generating arrival texts")
    
    # Load template
    template_path = ROOT / "data" / "prompts" / f"{TEMPLATE_NAME}.txt"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    template = template_path.read_text(encoding="utf-8")
    
    # Split dynamic/static
    parts = template.split('\n\n', 1)
    dynamic_part = parts[0].strip()
    static_part = parts[1].strip() if len(parts) > 1 else ""
    
    # Substitute variables in dynamic part
    variables = {
        "dest_city": simbrief_data["dest_city"],
        "local_time": weather_data["local_time"],
        "temperature": weather_data["temperature"],
        "airline_name": simbrief_data["airline_name"]
    }
    
    try:
        dynamic_processed = dynamic_part.format(**variables)
    except KeyError as e:
        raise ValueError(f"Missing variable in template: {e}")
    
    english_text = f"{dynamic_processed}\n\n{static_part}".strip()
    texts = {"en": english_text}
    
    # Get airline config for translations
    airline_config = load_airline_config(simbrief_data["icao"])
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
            dynamic_translated = translate_text(dynamic_processed, lang, gender)
            
            # Get static (cached)
            static_translated = get_static_cached(static_part, lang, gender)
            
            texts[lang] = f"{dynamic_translated}\n\n{static_translated}".strip()
    
    print(f"✅ Generated: {', '.join(texts.keys())}")
    return texts

def load_airline_config(icao: str) -> dict:
    """Load airline configuration from profiles"""
    config_file = ROOT / "data" / "airline_profiles.json"
    
    try:
        config = json.loads(config_file.read_text())
        return config.get(icao, {})
    except Exception as e:
        logger.warning(f"Error loading airline config: {e}")
        return {}

def get_static_cached(static_text: str, lang: str, gender: str) -> str:
    """Get cached static translation with context awareness"""
    if not static_text or lang in ["en", "en-US"] or not TEXT_CACHE_ENABLED:
        return static_text
    
    # Cache file with context separation
    cache_file = TEXT_CACHE_DIR / f"{lang}_{gender}_static.txt"
    
    # Try cache first
    if cache_file.exists():
        try:
            # Check cache age
            import time
            from datetime import datetime, timedelta
            
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age <= timedelta(days=TEXT_CACHE_DURATION_DAYS):
                cached_text = cache_file.read_text(encoding="utf-8")
                logger.debug(f"Using cached static text for {lang}_{gender}")
                return cached_text
            else:
                logger.debug(f"Cache expired for {lang}_{gender}, regenerating")
                cache_file.unlink()
        except Exception as e:
            logger.warning(f"Error reading cache: {e}")
    
    # Generate new translation
    translated = translate_text(static_text, lang, gender)
    
    # Save to cache
    try:
        cache_file.write_text(translated, encoding="utf-8")
        logger.debug(f"Cached static text for {lang}_{gender}")
    except Exception as e:
        logger.warning(f"Error saving to cache: {e}")
    
    return translated

def translate_text(text: str, target_lang: str, gender: str) -> str:
    """Translate text via OpenAI with consistent parameters"""
    from core.utils import get_openai_client
    
    client = get_openai_client()
    if not client:
        logger.warning(f"OpenAI not available for translation to {target_lang}")
        return text
    
    prompt = f"""Translate to {target_lang}.
Style: formal, courteous {gender} flight-attendant speech.
Keep details exact; add culturally correct formal particles.

Text: \"\"\"{text}\"\"\""""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.2
        )
        
        translated = response.choices[0].message.content.strip()
        
        # Remove surrounding quotes
        while ((translated.startswith('"') and translated.endswith('"')) or 
               (translated.startswith("'") and translated.endswith("'"))):
            translated = translated[1:-1].strip()
        
        # Remove quote blocks
        if translated.startswith('"""') and translated.endswith('"""'):
            translated = translated[3:-3].strip()
        
        return translated
        
    except Exception as e:
        logger.error(f"Translation failed for {target_lang}: {e}")
        return text

def generate_tts(texts: dict, simbrief_data: dict) -> dict:
    """Generate TTS audio with arrival context"""
    print("🔊 Generating TTS audio")
    
    try:
        from core.tts_manager import generate_audio_files
        
        # Pass arrival context to prevent cache conflicts with boarding
        audio_files = generate_audio_files(texts, simbrief_data, context=ANNOUNCEMENT_CONTEXT)
        
        if audio_files:
            print(f"✅ Generated: {', '.join(audio_files.keys())}")
        else:
            print("⚠️ No audio files generated")
        
        return audio_files
    except Exception as e:
        print(f"❌ TTS failed: {e}")
        logger.error(f"TTS generation failed: {e}")
        return {}

def process_audio(audio_files: dict, simbrief_data: dict) -> Path:
    """Process and combine audio - Silent mode optimized"""
    print("🎬 Processing final audio")
    
    if not audio_files:
        print("⚠️ No audio to process")
        return None
    
    try:
        # Import here to ensure subprocess patching is applied
        from core.post_processor import process_announcement
        
        # Suppress PyDub/ffmpeg output in silent mode
        if sys.executable.endswith('pythonw.exe'):
            # Redirect stderr to devnull to suppress ffmpeg output
            import os
            import contextlib
            
            # Create context manager to suppress output
            @contextlib.contextmanager
            def suppress_output():
                with open(os.devnull, 'w') as devnull:
                    old_stdout = sys.stdout
                    old_stderr = sys.stderr
                    try:
                        sys.stdout = devnull
                        sys.stderr = devnull
                        yield
                    finally:
                        sys.stdout = old_stdout
                        sys.stderr = old_stderr
            
            # Process with suppressed output
            with suppress_output():
                result = process_announcement(audio_files, simbrief_data)
        else:
            # Normal processing
            result = process_announcement(audio_files, simbrief_data)
        
        if result["success"]:
            final_file = result["final_file"]
            
            # Rename to arrival-specific
            arrival_file = final_file.parent / "arrival_announcement.wav"
            if final_file.exists():
                import shutil
                shutil.move(str(final_file), str(arrival_file))
                final_file = arrival_file
            
            print(f"✅ Final audio: {final_file.name}")
            return final_file
        
    except Exception as e:
        print(f"❌ Audio processing failed: {e}")
        logger.error(f"Audio processing failed: {e}")
    
    return None

def save_summary(texts: dict, simbrief_data: dict, weather_data: dict) -> Path:
    """Save text summary to output directory"""
    if not SAVE_TEXT_SUMMARY:
        return None
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    filename = f"arrival_{simbrief_data['icao']}_{simbrief_data['flight_number']}_{timestamp}.txt"
    output_file = ROOT / "output" / filename
    
    content = f"""ARRIVAL ANNOUNCEMENT - {simbrief_data['airline_name']} {simbrief_data['flight_number']}
Destination: {simbrief_data['dest_city']} ({simbrief_data['dest_icao']})
Weather: {weather_data['temperature']}, {weather_data['local_time']}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Context: {ANNOUNCEMENT_CONTEXT}

"""
    
    for lang, text in texts.items():
        content += f"{lang.upper()}:\n{'-'*20}\n{text}\n\n"
    
    # Ensure output directory exists
    output_file.parent.mkdir(exist_ok=True)
    output_file.write_text(content, encoding="utf-8")
    print(f"📄 Summary: {filename}")
    return output_file

def run_full_process(username: str):
    """Execute complete arrival process"""
    try:
        # Detect silent mode
        is_silent = sys.executable.endswith('pythonw.exe')
        
        # Steps
        simbrief_data = get_flight_data(username)
        weather_data = get_weather_data(simbrief_data["dest_icao"])
        texts = generate_texts(simbrief_data, weather_data)
        audio_files = generate_tts(texts, simbrief_data)
        final_audio = process_audio(audio_files, simbrief_data)
        summary = save_summary(texts, simbrief_data, weather_data)
        
        # CLEANUP and RENAME
        if final_audio:
            if not is_silent:
                print("\n🧹 Cleaning up temporary files")
            
            # Rename final audio
            arrival_file = rename_final_audio()
            
            # Remove individual audio files if enabled
            if CLEANUP_INDIVIDUAL_FILES:
                try:
                    output_dir = ROOT / "output"
                    individual_files = ["english.wav", "native.wav", "destination.wav"]
                    
                    for filename in individual_files:
                        file_path = output_dir / filename
                        if file_path.exists():
                            file_path.unlink()
                            logger.info(f"Removed {filename}")
                    
                    if not is_silent:
                        print("✅ Individual audio files cleaned")
                    
                except Exception as e:
                    logger.warning(f"Error cleaning individual files: {e}")
        
        # Results - only show if not silent
        if not is_silent:
            print("\n🎉 COMPLETED!")
            print("=" * 40)
            print(f"Flight: {simbrief_data['airline_name']} {simbrief_data['flight_number']}")
            print(f"Destination: {simbrief_data['dest_city']}")
            print(f"Weather: {weather_data['temperature']}")
            print(f"Time: {weather_data['local_time']}")
            print(f"Languages: {', '.join(texts.keys())}")
            
            # Show final audio info
            arrival_file = ROOT / "output" / FINAL_AUDIO_NAME
            if arrival_file.exists() and SHOW_AUDIO_INFO:
                print(f"Audio: {FINAL_AUDIO_NAME}")
                
                try:
                    from pydub import AudioSegment
                    audio = AudioSegment.from_wav(arrival_file)
                    duration = len(audio) / 1000
                    size = arrival_file.stat().st_size / 1024
                    duration_formatted = f"{int(duration//60):02d}:{int(duration%60):02d}"
                    print(f"   📏 Duration: {duration_formatted} • 📁 Size: {size:.1f} KB")
                except:
                    pass
            elif final_audio:
                print(f"Audio: {final_audio.name}")
            
            if summary:
                print(f"Summary: {summary.name}")
            print("=" * 40)
        
        # Always log completion
        logger.info(f"Arrival generation completed for {username}")
        
    except Exception as e:
        if not sys.executable.endswith('pythonw.exe'):
            print(f"\n❌ ERROR: {e}")
        logger.error(f"Process failed: {e}")
        raise

def main():
    """Main function - Silent mode friendly"""
    try:
        # Detect if running as .pyw (pythonw.exe)
        is_silent_mode = sys.executable.endswith('pythonw.exe')
        
        if not is_silent_mode:
            show_startup()
        
        # Get username
        if len(sys.argv) > 1:
            username = sys.argv[1]
        else:
            username = ENV.get("SIMBRIEF_USER")
        
        if not username:
            if not is_silent_mode:
                print("❌ SimBrief username required!")
                print("Usage: python run_arrival.py <username>")
            else:
                # Silent mode - log error instead of print
                logger.error("SimBrief username not provided")
            return
        
        # Cleanup and run (only temp files initially)
        if CLEANUP_TEMP_FILES:
            clear_temp_files(silent=True)
        
        if not is_silent_mode:
            print(f"🚀 Starting arrival generation for: {username}\n")
        
        run_full_process(username)
        
    except KeyboardInterrupt:
        if not sys.executable.endswith('pythonw.exe'):
            print("\n⏹️ Interrupted")
        logger.info("Process interrupted")
    except Exception as e:
        if not sys.executable.endswith('pythonw.exe'):
            print(f"\n💥 Error: {e}")
        logger.error(f"Process failed: {e}")
    finally:
        # COMPLETE final cleanup
        if not sys.executable.endswith('pythonw.exe'):
            print("\n🧹 Final cleanup...")
        complete_cleanup()
        
        # Only show "Press Enter" if not in silent mode
        if not sys.executable.endswith('pythonw.exe'):
            print("\nPress Enter to exit...")
            input()

if __name__ == "__main__":
    main()