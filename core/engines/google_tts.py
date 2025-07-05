"""
engines/google_tts.py - Google Cloud Text-to-Speech Engine (BULLETPROOF VERSION)

Responsibilities:
- BULLETPROOF voice forcing for accent preservation
- Automatic fallback system for all errors
- Support both Cloud SDK and REST API
- Handle text length limitations by splitting into segments
- SPECIAL HANDLING: English voice type uses native language (no forcing)
"""

import os
import requests
import base64
import re
import time
import uuid
from pathlib import Path
from pydub import AudioSegment

from core.utils import ENV, logger, ROOT

# ============================================
# CONFIGURAÇÕES AJUSTÁVEIS - BULLETPROOF
# ============================================

# Text processing
MAX_BYTES_PER_REQUEST = 800  # Google TTS character limit

# === VOICE SETTINGS ===
SPEAKING_RATE = 1.1  # Ligeiramente mais rápido
VOLUME_GAIN = 0.0  # Volume neutro

# === BULLETPROOF VOICE FORCING ===
ENABLE_VOICE_FORCING = True  # Ativar forçamento de voz
AUTO_FALLBACK_ON_ERROR = True  # Fallback automático
MAX_FALLBACK_ATTEMPTS = 3  # Máximo de tentativas

# === EXCEÇÕES DE VOICE FORCING ===
ENGLISH_VOICE_FORCING = False  # NÃO forçar para voice type "english"
# Se True: voz brasileira fala inglês (com sotaque)
# Se False: voz americana fala inglês (nativo)

# === VOICE-LANGUAGE MAPPING ===
VOICE_LANGUAGE_MAP = {
    # Tailandês
    "th-TH-Chirp3-HD-Laomedeia": "th-TH",
    "th-TH-Standard-A": "th-TH",
    "th-TH-Neural2-C": "th-TH",
    
    # Chinês
    "cmn-CN-Chirp3-HD-Leda": "cmn-CN",
    "zh-CN-Standard-A": "zh-CN", 
    "zh-CN-Neural2-A": "zh-CN",
    "zh-TW-Standard-A": "zh-TW",
    
    # Árabe
    "ar-XA-Chirp3-HD-Achird": "ar-XA",
    "ar-XA-Standard-A": "ar-XA",
    "ar-XA-Neural2-A": "ar-XA",
    
    # Português
    "pt-BR-Standard-A": "pt-BR",
    "pt-BR-Neural2-A": "pt-BR",
    "pt-BR-Chirp3-HD-Sigma": "pt-BR",
    "pt-BR-Chirp3-HD-Laomedeia": "pt-BR",
    
    # Francês
    "fr-FR-Standard-A": "fr-FR",
    "fr-FR-Neural2-A": "fr-FR",
    "fr-FR-Chirp3-HD-Alpha": "fr-FR",
    
    # Coreano
    "ko-KR-Standard-A": "ko-KR",
    "ko-KR-Neural2-A": "ko-KR",
    "ko-KR-Chirp3-HD-Aoede": "ko-KR",
    
    # Turco
    "tr-TR-Chirp3-HD-Achernar": "tr-TR",
    
    # Inglês (referência)
    "en-US-Chirp3-HD-Luna": "en-US",
    "en-GB-Chirp3-HD-Gacrux": "en-GB",
    "en-AU-Chirp-HD-O": "en-AU"
}

# === FALLBACK CHAIN CONFIGURATION ===
FALLBACK_STRATEGIES = [
    {"ssml": True, "voice_forcing": True},   # Tentativa 1: SSML + Voice Forcing
    {"ssml": False, "voice_forcing": True},  # Tentativa 2: Texto puro + Voice Forcing  
    {"ssml": False, "voice_forcing": False}  # Tentativa 3: Texto puro + idioma original
]

# === TEXT PROCESSING ===
CONVERT_FLIGHT_NUMBERS = True  # Converter números de voo
BASIC_PRONUNCIATION_FIX = True  # Correções básicas de pronúncia

# Audio settings
SEGMENT_PAUSE_MS = 500  # Pausa entre segmentos
AUDIO_FORMAT = "wav"
SAMPLE_RATE = 24000

# Temporary files
TEMP_DIR = ROOT / "core" / ".temp" / "google"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

class GoogleTTS:
    """
    Google Cloud Text-to-Speech Engine (BULLETPROOF VERSION)
    Guaranteed to work with voice forcing and comprehensive fallbacks
    """
    
    def __init__(self):
        self.api_key = ENV.get("GOOGLE_TTS_API")
        self.use_cloud_sdk = False
        self.client = None
        
        # Try to initialize Cloud SDK
        self._try_initialize_cloud_sdk()
        
        # Log initialization method
        if self.use_cloud_sdk:
            logger.info("Google TTS initialized with Cloud SDK (Bulletproof Mode)")
        elif self.api_key:
            logger.info("Google TTS initialized with REST API (Bulletproof Mode)")
        else:
            logger.warning("Google TTS not configured (no SDK or API key)")
    
    def _try_initialize_cloud_sdk(self):
        """Try to initialize Google Cloud SDK if available"""
        try:
            from google.cloud import texttospeech
            
            # Check for credentials
            credentials_env = ENV.get("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            
            if credentials_env:
                self.client = texttospeech.TextToSpeechClient()
                self.use_cloud_sdk = True
                logger.debug("Google Cloud SDK client initialized")
            else:
                logger.debug("Google Cloud credentials not found, using REST API")
                
        except ImportError:
            logger.debug("Google Cloud SDK not installed, using REST API")
        except Exception as e:
            logger.warning(f"Google Cloud SDK initialization failed: {e}")
    
    def is_available(self) -> bool:
        """Check if Google TTS is available and configured"""
        return self.use_cloud_sdk or bool(self.api_key)
    
    def validate_voice_id(self, voice_id: str) -> bool:
        """
        Validate if voice ID exists and is available
        
        Args:
            voice_id: Google voice ID (e.g., "th-TH-Chirp3-HD-Laomedeia")
            
        Returns:
            bool: True if voice is valid
        """
        if not voice_id:
            return False
        
        # Basic format validation for Google voice IDs
        # Format: language-country-model-quality-name
        # Example: th-TH-Chirp3-HD-Laomedeia
        
        parts = voice_id.split('-')
        if len(parts) < 2:
            logger.warning(f"Invalid Google voice ID format: {voice_id}")
            return False
        
        # Extract language code
        language_code = f"{parts[0]}-{parts[1]}"
        
        # Common language codes validation
        valid_languages = [
            "en-US", "en-GB", "en-AU", "th-TH", "zh-CN", "zh-TW", 
            "ja-JP", "ko-KR", "ar-XA", "fr-FR", "de-DE", "es-ES",
            "pt-BR", "it-IT", "ru-RU", "hi-IN", "tr-TR"
        ]
        
        if language_code not in valid_languages:
            logger.warning(f"Unsupported language in voice ID: {language_code}")
            return False
        
        logger.debug(f"Voice ID validation passed: {voice_id}")
        return True
    
    def synthesize(self, text: str, language: str, voice_id: str) -> Path:
        """
        BULLETPROOF synthesis with comprehensive fallback system
        
        Args:
            text: Text to synthesize
            language: Language code (will be forced if voice forcing enabled)
            voice_id: Google voice identifier
            
        Returns:
            Path: Generated WAV file path
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")
        
        if not self.is_available():
            raise RuntimeError("Google TTS not configured")
        
        if not self.validate_voice_id(voice_id):
            raise ValueError(f"Invalid voice ID: {voice_id}")
        
        logger.info(f"Google TTS (Bulletproof): Starting synthesis")
        logger.info(f"  Voice: {voice_id}")
        logger.info(f"  Requested Language: {language}")
        logger.debug(f"  Text length: {len(text)} chars, {len(text.encode('utf-8'))} bytes")
        
        # Try synthesis with fallback chain
        last_error = None
        
        for attempt, strategy in enumerate(FALLBACK_STRATEGIES, 1):
            try:
                logger.info(f"Attempt {attempt}/{len(FALLBACK_STRATEGIES)}: {strategy}")
                
                # Determine effective language (forced or original)
                effective_language = self._get_effective_language(voice_id, language, strategy["voice_forcing"])
                
                # Process text based on strategy
                processed_text = self._process_text_for_strategy(text, effective_language, strategy)
                
                # Check if text needs splitting
                if len(processed_text.encode('utf-8')) <= MAX_BYTES_PER_REQUEST:
                    # Single request
                    logger.debug("Text within limit, single synthesis")
                    audio_bytes = self._synthesize_single_with_strategy(
                        processed_text, voice_id, effective_language, strategy
                    )
                    return self._save_audio_bytes(audio_bytes, f"attempt_{attempt}")
                else:
                    # Multiple segments
                    logger.info("Text exceeds limit, splitting into segments")
                    return self._synthesize_segments_with_strategy(
                        processed_text, voice_id, effective_language, strategy
                    )
                    
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt < len(FALLBACK_STRATEGIES):
                    logger.info(f"Trying next fallback strategy...")
                continue
        
        # All attempts failed
        error_msg = f"All synthesis attempts failed. Last error: {last_error}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    def _get_effective_language(self, voice_id: str, requested_language: str, use_voice_forcing: bool) -> str:
        """
        Determine effective language based on voice forcing strategy
        WITH SPECIAL HANDLING FOR ENGLISH
        
        Args:
            voice_id: Voice identifier
            requested_language: Originally requested language
            use_voice_forcing: Whether to force voice language
            
        Returns:
            str: Effective language code to use
        """
        # SPECIAL CASE: English language should use native voice (no forcing)
        if requested_language in ["en", "en-US", "en-GB", "en-AU"]:
            if not ENGLISH_VOICE_FORCING:
                logger.debug(f"English voice type: using native language {requested_language} (no forcing)")
                return requested_language
            else:
                logger.debug(f"English voice type: applying voice forcing")
                # Continue with normal voice forcing logic
        
        if not use_voice_forcing or not ENABLE_VOICE_FORCING:
            return requested_language
        
        # Check explicit mapping first
        if voice_id in VOICE_LANGUAGE_MAP:
            forced_lang = VOICE_LANGUAGE_MAP[voice_id]
            logger.debug(f"Voice forcing: {voice_id} → {forced_lang} (mapped)")
            return forced_lang
        
        # Auto-extract from voice ID
        try:
            parts = voice_id.split('-')
            if len(parts) >= 2:
                extracted_lang = f"{parts[0]}-{parts[1]}"
                logger.debug(f"Voice forcing: {voice_id} → {extracted_lang} (extracted)")
                return extracted_lang
        except Exception as e:
            logger.warning(f"Could not extract language from {voice_id}: {e}")
        
        # Fallback to requested language
        logger.debug(f"Voice forcing failed, using requested: {requested_language}")
        return requested_language
    
    def _process_text_for_strategy(self, text: str, language: str, strategy: dict) -> str:
        """
        Process text according to synthesis strategy
        
        Args:
            text: Original text
            language: Effective language
            strategy: Strategy configuration
            
        Returns:
            str: Processed text
        """
        try:
            processed = text
            
            # Basic flight number conversion
            if CONVERT_FLIGHT_NUMBERS:
                processed = self._convert_flight_numbers(processed)
            
            # Basic pronunciation fixes
            if BASIC_PRONUNCIATION_FIX:
                processed = self._apply_basic_pronunciation_fixes(processed)
            
            # Add SSML if strategy requires it
            if strategy.get("ssml", False):
                processed = self._add_simple_ssml(processed)
            
            return processed
            
        except Exception as e:
            logger.warning(f"Text processing failed, using original: {e}")
            return text
    
    def _convert_flight_numbers(self, text: str) -> str:
        """Convert flight numbers to spoken format"""
        try:
            number_words = {
                '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
                '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'
            }
            
            def convert_flight_number(match):
                number = match.group(1)
                digit_words = ' '.join([number_words.get(digit, digit) for digit in number])
                return f"flight {digit_words}"
            
            flight_pattern = r'\bflight\s+(\d+)'
            return re.sub(flight_pattern, convert_flight_number, text, flags=re.IGNORECASE)
            
        except Exception as e:
            logger.warning(f"Flight number conversion failed: {e}")
            return text
    
    def _apply_basic_pronunciation_fixes(self, text: str) -> str:
        """Apply basic pronunciation improvements"""
        try:
            replacements = {
                'Bangkok': 'Bang-kok',
                'Dubai': 'Doo-bye',
                'Qatar': 'Ka-tar'
            }
            
            processed = text
            for original, improved in replacements.items():
                processed = re.sub(re.escape(original), improved, processed, flags=re.IGNORECASE)
            
            return processed
            
        except Exception as e:
            logger.warning(f"Pronunciation fixes failed: {e}")
            return text
    
    def _add_simple_ssml(self, text: str) -> str:
        """Add simple SSML wrapper"""
        try:
            # Very basic SSML - just rate control
            return f'<speak><prosody rate="{SPEAKING_RATE}">{text}</prosody></speak>'
            
        except Exception as e:
            logger.warning(f"SSML addition failed: {e}")
            return text
    
    def _synthesize_single_with_strategy(self, text: str, voice_id: str, language: str, strategy: dict) -> bytes:
        """Synthesize single text with specific strategy"""
        if self.use_cloud_sdk:
            return self._synthesize_cloud_sdk_with_strategy(text, voice_id, language, strategy)
        else:
            return self._synthesize_rest_api_with_strategy(text, voice_id, language, strategy)
    
    def _synthesize_cloud_sdk_with_strategy(self, text: str, voice_id: str, language: str, strategy: dict) -> bytes:
        """Cloud SDK synthesis with strategy"""
        from google.cloud import texttospeech
        
        logger.debug(f"Cloud SDK synthesis: {language} + {voice_id}")
        
        # Determine input type based on strategy
        if strategy.get("ssml", False) and text.strip().startswith('<speak>'):
            synthesis_input = texttospeech.SynthesisInput(ssml=text)
            logger.debug("Using SSML input")
        else:
            synthesis_input = texttospeech.SynthesisInput(text=text)
            logger.debug("Using text input")
        
        voice = texttospeech.VoiceSelectionParams(
            language_code=language,
            name=voice_id
        )
        
        # Minimal audio config for maximum compatibility
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE,
            speaking_rate=SPEAKING_RATE
        )
        
        # Add volume gain if supported and needed
        if VOLUME_GAIN != 0.0:
            try:
                audio_config.volume_gain_db = VOLUME_GAIN
            except:
                logger.debug("Volume gain not supported, skipping")
        
        # Perform synthesis
        response = self.client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        logger.debug(f"Cloud SDK synthesis successful: {len(response.audio_content)} bytes")
        return response.audio_content
    
    def _synthesize_rest_api_with_strategy(self, text: str, voice_id: str, language: str, strategy: dict) -> bytes:
        """REST API synthesis with strategy"""
        logger.debug(f"REST API synthesis: {language} + {voice_id}")
        
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={self.api_key}"
        
        # Determine input type based on strategy
        if strategy.get("ssml", False) and text.strip().startswith('<speak>'):
            input_data = {"ssml": text}
            logger.debug("Using SSML input")
        else:
            input_data = {"text": text}
            logger.debug("Using text input")
        
        # Build request body
        body = {
            "input": input_data,
            "voice": {
                "languageCode": language,
                "name": voice_id
            },
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": SAMPLE_RATE,
                "speakingRate": SPEAKING_RATE
            }
        }
        
        # Add volume gain if needed
        if VOLUME_GAIN != 0.0:
            body["audioConfig"]["volumeGainDb"] = VOLUME_GAIN
        
        response = requests.post(url, json=body, timeout=30)
        
        if response.status_code != 200:
            error_msg = f"REST API error {response.status_code}: {response.text}"
            logger.debug(error_msg)
            raise RuntimeError(error_msg)
        
        data = response.json()
        audio_content = data.get('audioContent')
        
        if not audio_content:
            raise RuntimeError("No audio content in response")
        
        audio_bytes = base64.b64decode(audio_content)
        logger.debug(f"REST API synthesis successful: {len(audio_bytes)} bytes")
        return audio_bytes
    
    def _synthesize_segments_with_strategy(self, text: str, voice_id: str, language: str, strategy: dict) -> Path:
        """Synthesize multiple segments with strategy"""
        # Split text into segments
        segments = self._split_text_smart(text)
        logger.info(f"Processing {len(segments)} segments")
        
        # Synthesize each segment
        segment_files = []
        
        for i, segment in enumerate(segments):
            logger.debug(f"Synthesizing segment {i+1}/{len(segments)}")
            
            try:
                audio_bytes = self._synthesize_single_with_strategy(segment, voice_id, language, strategy)
                segment_file = self._save_audio_bytes(audio_bytes, f"segment_{i}")
                segment_files.append(segment_file)
                
            except Exception as e:
                logger.error(f"Error synthesizing segment {i+1}: {e}")
                # Cleanup partial files
                for sf in segment_files:
                    try:
                        sf.unlink()
                    except:
                        pass
                raise
        
        # Combine segments
        combined_file = self._combine_segments(segment_files)
        
        # Cleanup segment files
        for segment_file in segment_files:
            try:
                segment_file.unlink()
            except Exception as e:
                logger.warning(f"Error cleaning segment file: {e}")
        
        return combined_file
    
    def _split_text_smart(self, text: str) -> list:
        """Split text into segments that fit within Google TTS limits"""
        if len(text.encode('utf-8')) <= MAX_BYTES_PER_REQUEST:
            return [text]
        
        logger.debug(f"Splitting text: {len(text.encode('utf-8'))} bytes")
        
        # Strategy 1: Split by double newlines (paragraphs)
        if '\n\n' in text:
            segments = [s.strip() for s in text.split('\n\n') if s.strip()]
            if all(len(s.encode('utf-8')) <= MAX_BYTES_PER_REQUEST for s in segments):
                logger.debug(f"Split by paragraphs: {len(segments)} segments")
                return segments
        
        # Strategy 2: Split by single newlines
        if '\n' in text:
            segments = [s.strip() for s in text.split('\n') if s.strip()]
            if all(len(s.encode('utf-8')) <= MAX_BYTES_PER_REQUEST for s in segments):
                logger.debug(f"Split by lines: {len(segments)} segments")
                return segments
        
        # Strategy 3: Split by sentences (periods)
        if '.' in text:
            sentences = []
            parts = text.split('.')
            for i, part in enumerate(parts):
                if part.strip():
                    sentence = part.strip() + ('.' if i < len(parts) - 1 else '')
                    if len(sentence.encode('utf-8')) <= MAX_BYTES_PER_REQUEST:
                        sentences.append(sentence)
                    else:
                        # Sentence too long, split by words
                        sentences.extend(self._split_by_words(sentence))
            
            if sentences:
                logger.debug(f"Split by sentences: {len(sentences)} segments")
                return sentences
        
        # Strategy 4: Split by words (last resort)
        logger.warning("Using word-level splitting (last resort)")
        return self._split_by_words(text)
    
    def _split_by_words(self, text: str) -> list:
        """Split text by words to fit within byte limits"""
        words = text.split()
        segments = []
        current_segment = ""
        
        for word in words:
            test_segment = f"{current_segment} {word}".strip()
            
            if len(test_segment.encode('utf-8')) <= MAX_BYTES_PER_REQUEST:
                current_segment = test_segment
            else:
                if current_segment:
                    segments.append(current_segment)
                current_segment = word
        
        if current_segment:
            segments.append(current_segment)
        
        logger.debug(f"Split by words: {len(segments)} segments")
        return segments
    
    def _combine_segments(self, segment_files: list) -> Path:
        """Combine audio segments with pauses"""
        logger.debug(f"Combining {len(segment_files)} segments")
        
        try:
            # Load first segment
            combined_audio = AudioSegment.from_wav(segment_files[0])
            
            # Add remaining segments with pauses
            for segment_file in segment_files[1:]:
                segment_audio = AudioSegment.from_wav(segment_file)
                pause = AudioSegment.silent(duration=SEGMENT_PAUSE_MS)
                combined_audio += pause + segment_audio
            
            # Save combined audio
            combined_file = self._save_audio_segment(combined_audio, "combined")
            
            duration = len(combined_audio) / 1000
            logger.info(f"Segments combined: {duration:.1f}s total")
            
            return combined_file
            
        except Exception as e:
            logger.error(f"Error combining segments: {e}")
            raise
    
    def _save_audio_bytes(self, audio_bytes: bytes, prefix: str) -> Path:
        """Save audio bytes to temporary file"""
        filename = f"google_bulletproof_{prefix}_{uuid.uuid4().hex[:8]}.wav"
        file_path = TEMP_DIR / filename
        
        try:
            file_path.write_bytes(audio_bytes)
            logger.debug(f"Audio saved: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving audio bytes: {e}")
            raise
    
    def _save_audio_segment(self, audio_segment: AudioSegment, prefix: str) -> Path:
        """Save audio segment to temporary file"""
        filename = f"google_bulletproof_{prefix}_{uuid.uuid4().hex[:8]}.wav"
        file_path = TEMP_DIR / filename
        
        try:
            audio_segment.export(file_path, format=AUDIO_FORMAT)
            logger.debug(f"Audio segment saved: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving audio segment: {e}")
            raise
    
    def get_engine_info(self) -> dict:
        """Get engine information and status"""
        method = "Cloud SDK" if self.use_cloud_sdk else "REST API" if self.api_key else "Not configured"
        
        return {
            "name": "Google Cloud Text-to-Speech (Bulletproof)",
            "engine_id": "google",
            "available": self.is_available(),
            "method": method,
            "max_chars": MAX_BYTES_PER_REQUEST,
            "features": ["bulletproof_synthesis", "voice_forcing", "comprehensive_fallbacks", "english_native_mode"],
            "settings": {
                "speaking_rate": SPEAKING_RATE,
                "voice_forcing": ENABLE_VOICE_FORCING,
                "english_voice_forcing": ENGLISH_VOICE_FORCING,
                "fallback_attempts": len(FALLBACK_STRATEGIES),
                "mapped_voices": len(VOICE_LANGUAGE_MAP)
            }
        }

# Test function when run directly
if __name__ == "__main__":
    import sys
    
    print("🧪 Testing Google TTS Engine (Bulletproof Version)...")
    
    # Test configuration
    test_voice = "en-US-Chirp3-HD-Luna"
    test_text = "Good evening, ladies and gentlemen. Welcome aboard flight two zero zero to Bangkok."
    
    try:
        # Initialize engine
        engine = GoogleTTS()
        
        print(f"🔧 Engine info: {engine.get_engine_info()}")
        print(f"✅ Available: {engine.is_available()}")
        print(f"✅ Voice validation: {engine.validate_voice_id(test_voice)}")
        print(f"🇺🇸 English voice forcing: {ENGLISH_VOICE_FORCING}")
        
        if engine.is_available():
            print(f"🔊 Synthesizing test text...")
            
            audio_file = engine.synthesize(test_text, "en-US", test_voice)
            
            print(f"✅ Synthesis completed!")
            print(f"📁 Output file: {audio_file}")
            
            # Get audio info
            audio = AudioSegment.from_wav(audio_file)
            duration = len(audio) / 1000
            size = audio_file.stat().st_size / 1024
            
            print(f"📊 Duration: {duration:.1f}s")
            print(f"📊 Size: {size:.1f} KB")
            
        else:
            print("❌ Engine not available - check configuration")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        logger.exception("Google TTS test failed")
        sys.exit(1)