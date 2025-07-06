"""
tts_manager.py - Text-to-Speech coordination system MELHORADO

CORREÇÕES APLICADAS:
- Fallback automático habilitado
- Tratamento robusto de engines NULL
- Logging detalhado para debugging
- Validação melhorada de voice IDs
- Sistema de retry para falhas temporárias
"""

import json
import shutil
import uuid
from pathlib import Path
from pydub import AudioSegment

from core.utils import ROOT, logger, log_step_start, log_step_complete, log_step_error, log_api_call

# ============================================
# CONFIGURABLE SETTINGS - MELHORADOS
# ============================================

# Fallback configuration - HABILITADO POR PADRÃO
OPENAI_FALLBACK_ENABLED = True  # CORREÇÃO: Habilitado para recuperar falhas
FALLBACK_VOICE = "nova"  # OpenAI voice for fallback
FALLBACK_GENDER = "female"  # Gender hint for fallback

# Engine retry settings
MAX_RETRY_ATTEMPTS = 2  # Retry failed engines
RETRY_DELAY_SECONDS = 1  # Delay between retries

# Audio timing (milliseconds)
AUDIO_PAUSE_MS = 700  # Pause between dynamic and static parts
SEGMENT_PAUSE_MS = 500  # Pause between text segments (Google TTS)

# Engine timeouts (seconds)
ENGINE_TIMEOUT = 60  # Timeout for TTS API calls

# Audio quality settings
AUDIO_FORMAT = "wav"  # Output format
SAMPLE_RATE = 24000  # Audio sample rate

# Cache settings
CACHE_ENABLED = True  # Enable/disable caching
CACHE_DURATION_DAYS = 30  # Cache expiration in days

# Validation settings
STRICT_VOICE_VALIDATION = False  # CORREÇÃO: Menos restritiva
ALLOW_ENGINE_NULL = True  # CORREÇÃO: Permitir engines null com fallback

# ============================================
# PATHS CONFIGURATION
# ============================================

# Data directories
AIRLINE_FILE = ROOT / "data" / "airline_profiles.json"
CACHE_BASE = ROOT / "data" / "cache" / "tts"

# Output directories
OUTPUT_DIR = ROOT / "output"
TEMP_DIR = OUTPUT_DIR / "temp"

# Create necessary directories
for directory in [OUTPUT_DIR, TEMP_DIR, CACHE_BASE]:
    directory.mkdir(parents=True, exist_ok=True)

class TTSManager:
    """
    Main TTS coordination system with robust error handling
    """
    
    def __init__(self, context: str = "boarding"):
        """
        Initialize TTS Manager with context for proper cache separation
        
        Args:
            context: "boarding" or "arrival" for cache separation
        """
        self.context = context
        self.engines = {}
        self.temp_files = []  # Track temporary files for cleanup
        
        logger.info(f"TTS Manager initialized for {context} with fallback enabled")
        self._initialize_engines()
    
    def _initialize_engines(self):
        """Initialize available TTS engines with detailed logging"""
        log_step_start("TTS Engine Initialization")
        
        try:
            # Import engines from core.engines
            from core.engines.google_tts import GoogleTTS
            from core.engines.elevenlabs_tts import ElevenLabsTTS
            from core.engines.openai_tts import OpenAITTS
            
            # Initialize engines with error handling
            self.engines = {}
            
            # Google TTS
            try:
                google_engine = GoogleTTS()
                self.engines["google"] = google_engine
                logger.info(f"Google TTS: {'Available' if google_engine.is_available() else 'Not configured'}")
            except Exception as e:
                logger.error(f"Google TTS initialization failed: {e}")
            
            # ElevenLabs TTS
            try:
                eleven_engine = ElevenLabsTTS()
                self.engines["elevenlabs"] = eleven_engine
                logger.info(f"ElevenLabs TTS: {'Available' if eleven_engine.is_available() else 'Not configured'}")
            except Exception as e:
                logger.error(f"ElevenLabs TTS initialization failed: {e}")
            
            # OpenAI TTS
            try:
                openai_engine = OpenAITTS()
                self.engines["openai"] = openai_engine
                logger.info(f"OpenAI TTS: {'Available' if openai_engine.is_available() else 'Not configured'}")
            except Exception as e:
                logger.error(f"OpenAI TTS initialization failed: {e}")
            
            # Check availability
            available_engines = []
            for name, engine in self.engines.items():
                if engine.is_available():
                    available_engines.append(name)
                else:
                    logger.warning(f"Engine {name} not available")
            
            log_step_complete("TTS Engine Initialization", f"Available: {', '.join(available_engines)}")
            
        except ImportError as e:
            log_step_error("TTS Engine Initialization", e)
            self.engines = {}
    
    def generate_audio_files(self, texts: dict, simbrief_data: dict) -> dict:
        """
        Generate TTS audio files for all configured voice types with robust error handling
        
        Args:
            texts: Dictionary of texts by language {"en": "text", "th-TH": "text"}
            simbrief_data: Flight data from SimBrief
            
        Returns:
            dict: Generated audio files {"native": Path, "english": Path}
        """
        icao = simbrief_data.get("icao")
        if not icao:
            raise ValueError("ICAO code not found in flight data")
        
        log_step_start("TTS Audio Generation", f"Airline: {icao}, Context: {self.context}")
        
        try:
            # Clean temp directory
            self._clean_temp_directory()
            
            # Load airline configuration
            airline_config = self._load_airline_config(icao)
            
            # Get voice types and priority
            priority_order = airline_config.get("priority_order", [])
            tts_engines = airline_config.get("tts_engines", {})
            
            if not priority_order:
                logger.warning(f"No priority order configured for {icao}")
                return {}
            
            logger.info(f"Processing voice types: {priority_order}")
            
            # Generate audio for each voice type
            generated_files = {}
            
            for voice_type in priority_order:
                try:
                    logger.info(f"Processing voice type: {voice_type}")
                    
                    audio_path = self._process_voice_type_with_retry(
                        voice_type, texts, tts_engines, simbrief_data
                    )
                    
                    if audio_path:
                        generated_files[voice_type] = audio_path
                        logger.info(f"✅ Generated {voice_type} audio: {audio_path.name}")
                    else:
                        logger.warning(f"❌ Failed to generate {voice_type} audio")
                
                except Exception as e:
                    logger.error(f"Error generating {voice_type} audio: {e}")
                    logger.exception(f"Stack trace for {voice_type}")
            
            # Move final files and cleanup
            final_files = self._finalize_output(generated_files)
            
            log_step_complete("TTS Audio Generation", f"Generated {len(final_files)} files")
            return final_files
            
        except Exception as e:
            log_step_error("TTS Audio Generation", e)
            raise
        
        finally:
            self._cleanup_temp_files()
    
    def _process_voice_type_with_retry(self, voice_type: str, texts: dict, tts_engines: dict, simbrief_data: dict) -> Path:
        """Process single voice type with retry logic"""
        for attempt in range(MAX_RETRY_ATTEMPTS + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt} for {voice_type}")
                    import time
                    time.sleep(RETRY_DELAY_SECONDS)
                
                return self._process_voice_type(voice_type, texts, tts_engines, simbrief_data)
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {voice_type}: {e}")
                
                if attempt < MAX_RETRY_ATTEMPTS:
                    continue
                else:
                    # Final attempt - try fallback
                    if OPENAI_FALLBACK_ENABLED:
                        logger.info(f"Trying OpenAI fallback for {voice_type}")
                        try:
                            return self._try_fallback(voice_type, texts, simbrief_data)
                        except Exception as fallback_error:
                            logger.error(f"Fallback also failed for {voice_type}: {fallback_error}")
                    
                    return None
    
    def _load_airline_config(self, icao: str) -> dict:
        """Load airline configuration from profiles with validation"""
        if not AIRLINE_FILE.exists():
            raise FileNotFoundError(f"Airline profiles not found: {AIRLINE_FILE}")
        
        try:
            config = json.loads(AIRLINE_FILE.read_text())
            
            if icao not in config:
                raise ValueError(f"Airline {icao} not found in profiles")
            
            airline_config = config[icao]
            logger.debug(f"Loaded configuration for {icao}")
            
            # Log engine configuration for debugging
            tts_engines = airline_config.get("tts_engines", {})
            for voice_type, engine_config in tts_engines.items():
                engine_name = engine_config.get("engine")
                logger.debug(f"{voice_type} -> engine: {engine_name}")
            
            return airline_config
            
        except Exception as e:
            raise RuntimeError(f"Error loading airline config: {e}")
    
    def _process_voice_type(self, voice_type: str, texts: dict, tts_engines: dict, simbrief_data: dict) -> Path:
        """Process single voice type with enhanced validation"""
        logger.debug(f"Processing voice type: {voice_type}")
        
        # Get voice configuration
        if voice_type not in tts_engines:
            raise ValueError(f"Voice type {voice_type} not configured")
        
        voice_config = tts_engines[voice_type]
        
        # Determine engine and voice ID with NULL handling
        engine_name = voice_config.get("engine")
        
        # CORREÇÃO: Handle NULL engine with fallback
        if not engine_name or engine_name.lower() == "null":
            if ALLOW_ENGINE_NULL and OPENAI_FALLBACK_ENABLED:
                logger.warning(f"Engine is NULL for {voice_type}, using OpenAI fallback")
                return self._try_fallback(voice_type, texts, simbrief_data)
            else:
                raise ValueError(f"No engine specified for {voice_type} and fallback disabled")
        
        # Get voice ID based on engine
        voice_id_map = {
            "google": "google_id",
            "elevenlabs": "elevenlabs_id",
            "openai": "openai_id"
        }
        
        voice_id_key = voice_id_map.get(engine_name)
        if not voice_id_key:
            raise ValueError(f"Unknown engine: {engine_name}")
        
        voice_id = voice_config.get(voice_id_key)
        if not voice_id or voice_id.lower() == "null":
            # Try fallback voice IDs
            fallback_ids = ["google_id", "elevenlabs_id", "openai_id"]
            for fallback_key in fallback_ids:
                if fallback_key != voice_id_key:
                    fallback_voice_id = voice_config.get(fallback_key)
                    if fallback_voice_id and fallback_voice_id.lower() != "null":
                        # Switch to fallback engine
                        fallback_engine = fallback_key.replace("_id", "")
                        if fallback_engine in self.engines:
                            logger.warning(f"Using fallback: {fallback_engine} with voice {fallback_voice_id}")
                            engine_name = fallback_engine
                            voice_id = fallback_voice_id
                            break
            
            if not voice_id or voice_id.lower() == "null":
                if OPENAI_FALLBACK_ENABLED:
                    logger.warning(f"No valid voice ID for {voice_type}, using OpenAI fallback")
                    return self._try_fallback(voice_type, texts, simbrief_data)
                else:
                    raise ValueError(f"No voice ID configured for {engine_name} in {voice_type}")
        
        # Determine text and language
        text, language = self._determine_text_and_language(voice_type, texts, simbrief_data)
        
        if not text:
            raise ValueError(f"No text available for {voice_type}")
        
        # Get engine
        if engine_name not in self.engines:
            raise ValueError(f"Engine {engine_name} not available")
        
        engine = self.engines[engine_name]
        
        # Validate voice ID with engine (less strict)
        if not STRICT_VOICE_VALIDATION:
            logger.debug(f"Skipping strict voice validation for {voice_id}")
        elif hasattr(engine, 'validate_voice_id') and not engine.validate_voice_id(voice_id):
            logger.warning(f"Voice ID validation failed for {voice_id}, continuing anyway")
        
        # Log API call
        log_api_call(engine_name, f"synthesize {voice_type}")
        
        # Process dynamic and static parts with context
        try:
            result = self._process_dynamic_static_audio(
                text, language, voice_id, engine, voice_type
            )
            log_api_call(engine_name, f"synthesize {voice_type}", "success")
            return result
        except Exception as e:
            log_api_call(engine_name, f"synthesize {voice_type}", "error")
            raise
    
    def _determine_text_and_language(self, voice_type: str, texts: dict, simbrief_data: dict) -> tuple:
        """Determine which text and language to use for voice type"""
        logger.debug(f"Determining text for voice type: {voice_type}")
        
        # Map voice types to language preferences
        if voice_type == "english":
            # Prefer English
            if "en" in texts:
                logger.debug(f"Using English text for {voice_type}")
                return texts["en"], "en"
            elif "en-US" in texts:
                logger.debug(f"Using en-US text for {voice_type}")
                return texts["en-US"], "en-US"
        
        elif voice_type == "native":
            # Use airline's native language
            airline_config = self._load_airline_config(simbrief_data["icao"])
            native_lang = airline_config.get("language", "en")
            
            if native_lang in texts:
                logger.debug(f"Using native language {native_lang} for {voice_type}")
                return texts[native_lang], native_lang
        
        elif voice_type == "destination":
            # Use destination country language (if available)
            # For now, fallback to English
            if "en" in texts:
                logger.debug(f"Using English for destination voice type")
                return texts["en"], "en"
        
        # Fallback to first available text
        if texts:
            first_lang = list(texts.keys())[0]
            logger.debug(f"Using fallback language {first_lang} for {voice_type}")
            return texts[first_lang], first_lang
        
        return None, None
    
    def _process_dynamic_static_audio(self, text: str, language: str, voice_id: str, engine, voice_type: str) -> Path:
        """Process dynamic and static audio parts with context-aware caching"""
        logger.debug(f"Processing dynamic/static audio for {voice_type} (context: {self.context})")
        
        # Split text into dynamic and static parts
        dynamic_text, static_text = self._split_dynamic_static(text)
        
        # Generate dynamic audio
        logger.debug(f"Generating dynamic audio: {len(dynamic_text)} chars")
        dynamic_audio_path = engine.synthesize(dynamic_text, language, voice_id)
        self.temp_files.append(dynamic_audio_path)
        
        # Get or generate static audio (cached with context)
        static_audio_path = None
        if static_text:
            logger.debug(f"Processing static audio: {len(static_text)} chars")
            static_audio_path = self._get_static_audio_cached(
                static_text, language, voice_id, engine, voice_type
            )
            
            if static_audio_path:
                self.temp_files.append(static_audio_path)
        
        # Combine dynamic and static with pause
        combined_path = self._combine_audio_parts(
            dynamic_audio_path, static_audio_path, voice_type
        )
        
        return combined_path
    
    def _split_dynamic_static(self, text: str) -> tuple:
        """
        Split text into dynamic and static parts
        
        Dynamic: Primeira parte com variáveis (saudação + info do voo)
        Static: Resto do texto (instruções de segurança + agradecimento)
        """
        # Split by double newline (paragraphs)
        parts = text.split('\n\n', 1)
        
        if len(parts) == 2:
            # Primeira parte = dinâmica (saudação + info)
            dynamic = parts[0].strip()
            # Resto = estática (segurança + agradecimento)
            static = parts[1].strip()
            
            logger.debug(f"Text split correctly:")
            logger.debug(f"  Dynamic: {len(dynamic)} chars - {dynamic[:50]}...")
            logger.debug(f"  Static: {len(static)} chars - {static[:50]}...")
            
        else:
            # Se não tem \n\n, tudo é dinâmico
            dynamic = text.strip()
            static = ""
            logger.debug(f"No paragraph break found, all text is dynamic")
        
        return dynamic, static
    
    def _get_static_audio_cached(self, static_text: str, language: str, voice_id: str, engine, voice_type: str) -> Path:
        """
        Get cached static audio with context separation (boarding vs arrival)
        
        Args:
            static_text: Static text part
            language: Language code
            voice_id: Voice identifier
            engine: TTS engine
            voice_type: Voice type for cache organization
            
        Returns:
            Path: Static audio file (or None if no static text)
        """
        if not static_text.strip() or not CACHE_ENABLED:
            return None
        
        # Determine engine name
        engine_name = engine.__class__.__name__.lower().replace('tts', '')
        
        # Safe voice ID for filename
        safe_voice_id = voice_id.replace("/", "_").replace("\\", "_")
        
        # Cache path with CONTEXT separation
        cache_path = CACHE_BASE / engine_name / language / safe_voice_id / f"{self.context}_static.wav"
        
        # Check if cached version exists and is not expired
        if cache_path.exists():
            try:
                # Check cache age (optional)
                import time
                from datetime import datetime, timedelta
                
                cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
                if cache_age > timedelta(days=CACHE_DURATION_DAYS):
                    logger.debug(f"Cache expired for {cache_path}")
                    cache_path.unlink()
                else:
                    logger.debug(f"Using cached static audio: {cache_path}")
                    
                    # Copy to temp for processing
                    temp_static = TEMP_DIR / f"{voice_type}_static_{uuid.uuid4().hex[:8]}.wav"
                    shutil.copy2(cache_path, temp_static)
                    return temp_static
            except Exception as e:
                logger.warning(f"Error checking cache: {e}")
        
        # Generate new static audio
        logger.debug(f"Generating new static audio for cache (context: {self.context})")
        
        static_audio_path = engine.synthesize(static_text, language, voice_id)
        
        # Save to cache with context
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(static_audio_path, cache_path)
            logger.debug(f"Static audio cached: {cache_path}")
        except Exception as e:
            logger.warning(f"Failed to cache static audio: {e}")
        
        return static_audio_path
    
    def _combine_audio_parts(self, dynamic_path: Path, static_path: Path, voice_type: str) -> Path:
        """Combine dynamic and static audio with pause"""
        logger.debug(f"Combining audio parts for {voice_type}")
        
        try:
            # Load dynamic audio
            dynamic_audio = AudioSegment.from_wav(dynamic_path)
            
            # If no static audio, return dynamic only
            if not static_path or not static_path.exists():
                combined_path = TEMP_DIR / f"{voice_type}_combined_{uuid.uuid4().hex[:8]}.wav"
                dynamic_audio.export(combined_path, format=AUDIO_FORMAT)
                self.temp_files.append(combined_path)
                return combined_path
            
            # Load static audio
            static_audio = AudioSegment.from_wav(static_path)
            
            # Create pause
            pause = AudioSegment.silent(duration=AUDIO_PAUSE_MS)
            
            # Combine: dynamic + pause + static
            combined_audio = dynamic_audio + pause + static_audio
            
            # Export combined audio
            combined_path = TEMP_DIR / f"{voice_type}_combined_{uuid.uuid4().hex[:8]}.wav"
            combined_audio.export(combined_path, format=AUDIO_FORMAT)
            
            # Track for cleanup
            self.temp_files.append(combined_path)
            
            # Log timing info
            total_duration = len(combined_audio) / 1000
            logger.debug(f"Combined audio: {total_duration:.1f}s total")
            
            return combined_path
            
        except Exception as e:
            logger.error(f"Error combining audio parts: {e}")
            raise
    
    def _try_fallback(self, voice_type: str, texts: dict, simbrief_data: dict) -> Path:
        """Try OpenAI fallback for failed voice type with enhanced logging"""
        logger.info(f"🔄 Attempting OpenAI fallback for {voice_type}")
        
        if "openai" not in self.engines:
            raise RuntimeError("OpenAI engine not available for fallback")
        
        openai_engine = self.engines["openai"]
        if not openai_engine.is_available():
            raise RuntimeError("OpenAI engine not configured for fallback")
        
        # Determine text and language
        text, language = self._determine_text_and_language(voice_type, texts, simbrief_data)
        
        if not text:
            raise ValueError(f"No text available for fallback {voice_type}")
        
        # Use OpenAI engine with fallback voice
        logger.info(f"Using OpenAI fallback: voice={FALLBACK_VOICE}, language={language}")
        
        return self._process_dynamic_static_audio(
            text, language, FALLBACK_VOICE, openai_engine, f"{voice_type}_fallback"
        )
    
    def _finalize_output(self, generated_files: dict) -> dict:
        """Move generated files to final output directory with detailed logging"""
        logger.info("Moving files to final output directory")
        
        final_files = {}
        
        for voice_type, temp_path in generated_files.items():
            if temp_path and temp_path.exists():
                # Final path
                final_path = OUTPUT_DIR / f"{voice_type}.wav"
                
                # Move file
                try:
                    shutil.move(str(temp_path), str(final_path))
                    final_files[voice_type] = final_path
                    
                    # Log file info
                    file_size = final_path.stat().st_size / 1024  # KB
                    audio_duration = len(AudioSegment.from_wav(final_path)) / 1000  # seconds
                    
                    logger.info(f"✅ Final {voice_type}: {file_size:.1f} KB, {audio_duration:.1f}s")
                    
                except Exception as e:
                    logger.error(f"Error moving {voice_type} file: {e}")
        
        return final_files
    
    def _clean_temp_directory(self):
        """Clean temp directory before processing"""
        if TEMP_DIR.exists():
            try:
                shutil.rmtree(TEMP_DIR)
                TEMP_DIR.mkdir(parents=True, exist_ok=True)
                logger.debug("Temp directory cleaned")
            except Exception as e:
                logger.warning(f"Error cleaning temp directory: {e}")
    
    def _cleanup_temp_files(self):
        """Cleanup tracked temporary files and temp directory"""
        # Clean tracked files
        for temp_file in self.temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception as e:
                logger.warning(f"Error cleaning temp file {temp_file}: {e}")
        
        self.temp_files.clear()
        
        # Remove temp directory
        if TEMP_DIR.exists():
            try:
                shutil.rmtree(TEMP_DIR)
                logger.debug("Temp directory removed")
            except Exception as e:
                logger.warning(f"Error removing temp directory: {e}")

# Main function for external use
def generate_audio_files(texts: dict, simbrief_data: dict, context: str = "boarding") -> dict:
    """
    Generate TTS audio files for boarding/arrival announcement with robust error handling
    
    Args:
        texts: Dictionary of texts by language
        simbrief_data: Flight data from SimBrief
        context: "boarding" or "arrival" for cache separation
        
    Returns:
        dict: Generated audio files {"voice_type": Path}
    """
    manager = TTSManager(context=context)
    return manager.generate_audio_files(texts, simbrief_data)

# Test function when run directly
if __name__ == "__main__":
    import sys
    
    print("🧪 Testing Enhanced TTS Manager...")
    
    # Mock data for testing
    mock_texts = {
        "en": "Good evening, ladies and gentlemen. Welcome aboard flight two zero zero to Bangkok.",
        "th-TH": "สวัสดีตอนเย็นค่ะ ท่านผู้โดยสาร ยินดีต้อนรับสู่เที่ยวบินสองศูนย์ศูนย์ ไปกรุงเทพฯ ค่ะ"
    }
    
    mock_simbrief = {
        "icao": "THA",
        "airline_name": "Thai Airways",
        "flight_number": "200",
        "dest_city": "Bangkok"
    }
    
    try:
        print("🔊 Generating TTS audio files with enhanced error handling...")
        
        audio_files = generate_audio_files(mock_texts, mock_simbrief, "boarding")
        
        print("\n✅ ENHANCED TTS GENERATION COMPLETED:")
        print("=" * 50)
        
        for voice_type, path in audio_files.items():
            print(f"🎵 {voice_type}: {path}")
        
        print("=" * 50)
        print(f"🎯 Generated {len(audio_files)} audio files")
        
        if len(audio_files) == 0:
            print("⚠️  No audio files generated - check logs for details")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        logger.exception("Enhanced TTS Manager test failed")
        sys.exit(1)