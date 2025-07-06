"""
engines/google_tts.py - Google Cloud Text-to-Speech Engine (CORRIGIDO)

CORREÇÕES APLICADAS:
- SSML DESABILITADO por padrão (evita erro de suporte)
- VOICE FORCING DESABILITADO (permite voz PT-BR falar inglês)
- Voice ID usado EXATAMENTE como configurado (sem conversões)
- Suporte para cross-language (voz brasileira falando inglês)
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
# CONFIGURAÇÕES CORRIGIDAS - SEM VOICE FORCING
# ============================================

# Text processing
MAX_BYTES_PER_REQUEST = 800  # Google TTS character limit

# === VOICE SETTINGS ===
SPEAKING_RATE = 1.1  # Ligeiramente mais rápido
VOLUME_GAIN = 0.0  # Volume neutro

# === CORREÇÕES PRINCIPAIS ===
ENABLE_VOICE_FORCING = False  # ❌ DESABILITADO - permite voz PT falar inglês
AUTO_FALLBACK_ON_ERROR = True  # ✅ Fallback automático
MAX_FALLBACK_ATTEMPTS = 3  # Máximo de tentativas
USE_SSML_BY_DEFAULT = False  # ❌ DESABILITADO - evita erro de suporte

# === CONFIGURAÇÕES DE ESTRATÉGIA ===
FALLBACK_STRATEGIES = [
    {"ssml": False, "voice_forcing": False},  # Tentativa 1: Texto puro + Voice ID exato
    {"ssml": False, "voice_forcing": False},  # Tentativa 2: Mesmo (retry)
    {"ssml": False, "voice_forcing": False}   # Tentativa 3: Mesmo (última chance)
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
    Google Cloud Text-to-Speech Engine (CORRIGIDO)
    Permite voz portuguesa falar inglês sem voice forcing
    """
    
    def __init__(self):
        self.api_key = ENV.get("GOOGLE_TTS_API")
        self.use_cloud_sdk = False
        self.client = None
        
        # Try to initialize Cloud SDK
        self._try_initialize_cloud_sdk()
        
        # Log initialization method
        if self.use_cloud_sdk:
            logger.info("Google TTS initialized with Cloud SDK (Cross-Language Mode)")
        elif self.api_key:
            logger.info("Google TTS initialized with REST API (Cross-Language Mode)")
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
        CORREÇÃO: Validação mais permissiva
        
        Args:
            voice_id: Google voice ID (e.g., "pt-BR-Chirp3-HD-Laomedeia")
            
        Returns:
            bool: True if voice is valid
        """
        if not voice_id:
            return False
        
        # Basic format validation for Google voice IDs
        # Format: language-country-model-quality-name
        # Example: pt-BR-Chirp3-HD-Laomedeia
        
        parts = voice_id.split('-')
        if len(parts) < 2:
            logger.warning(f"Invalid Google voice ID format: {voice_id}")
            return False
        
        # Extract language code
        language_code = f"{parts[0]}-{parts[1]}"
        
        # CORREÇÃO: Validação mais permissiva - aceita mais idiomas
        valid_languages = [
            "en-US", "en-GB", "en-AU", "th-TH", "zh-CN", "zh-TW", 
            "ja-JP", "ko-KR", "ar-XA", "fr-FR", "de-DE", "es-ES",
            "pt-BR", "it-IT", "ru-RU", "hi-IN", "tr-TR", "cmn-CN"
        ]
        
        if language_code not in valid_languages:
            logger.warning(f"Unsupported language in voice ID: {language_code}")
            # CORREÇÃO: Não falha, apenas avisa
            logger.info(f"Attempting to use voice anyway: {voice_id}")
        
        logger.debug(f"Voice ID accepted: {voice_id}")
        return True
    
    def synthesize(self, text: str, language: str, voice_id: str) -> Path:
        """
        CROSS-LANGUAGE synthesis - voz PT pode falar inglês
        
        Args:
            text: Text to synthesize (pode ser inglês)
            language: Language code (pode ser diferente da voz)
            voice_id: Google voice identifier (ex: pt-BR-Chirp3-HD-Laomedeia)
            
        Returns:
            Path: Generated WAV file path
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")
        
        if not self.is_available():
            raise RuntimeError("Google TTS not configured")
        
        if not self.validate_voice_id(voice_id):
            raise ValueError(f"Invalid voice ID: {voice_id}")
        
        logger.info(f"Google TTS (Cross-Language): Starting synthesis")
        logger.info(f"  Voice: {voice_id}")
        logger.info(f"  Text Language: {language}")
        logger.info(f"  Cross-Language Mode: Voice PT pode falar qualquer idioma")
        logger.debug(f"  Text length: {len(text)} chars, {len(text.encode('utf-8'))} bytes")
        
        # Try synthesis with fallback chain (SEM VOICE FORCING)
        last_error = None
        
        for attempt, strategy in enumerate(FALLBACK_STRATEGIES, 1):
            try:
                logger.info(f"Attempt {attempt}/{len(FALLBACK_STRATEGIES)}: Cross-language synthesis")
                
                # CORREÇÃO: NÃO forçar idioma, usar voice_id exato
                effective_voice_id = voice_id  # Usar exatamente como configurado
                effective_language = self._extract_voice_language(voice_id)  # Extrair idioma da voz
                
                logger.debug(f"Using Voice ID: {effective_voice_id}")
                logger.debug(f"Voice Language: {effective_language}")
                logger.debug(f"Text Language: {language}")
                
                # Process text based on strategy
                processed_text = self._process_text_for_strategy(text, language, strategy)
                
                # Check if text needs splitting
                if len(processed_text.encode('utf-8')) <= MAX_BYTES_PER_REQUEST:
                    # Single request
                    logger.debug("Text within limit, single synthesis")
                    audio_bytes = self._synthesize_single_cross_language(
                        processed_text, effective_voice_id, effective_language, strategy
                    )
                    return self._save_audio_bytes(audio_bytes, f"attempt_{attempt}")
                else:
                    # Multiple segments
                    logger.info("Text exceeds limit, splitting into segments")
                    return self._synthesize_segments_cross_language(
                        processed_text, effective_voice_id, effective_language, strategy
                    )
                    
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt < len(FALLBACK_STRATEGIES):
                    logger.info(f"Trying next attempt...")
                continue
        
        # All attempts failed
        error_msg = f"All synthesis attempts failed. Last error: {last_error}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    def _extract_voice_language(self, voice_id: str) -> str:
        """
        Extrai idioma da voice ID para usar com Google TTS
        
        Args:
            voice_id: ex. pt-BR-Chirp3-HD-Laomedeia
            
        Returns:
            str: ex. pt-BR
        """
        try:
            parts = voice_id.split('-')
            if len(parts) >= 2:
                extracted_lang = f"{parts[0]}-{parts[1]}"
                logger.debug(f"Extracted language from voice: {extracted_lang}")
                return extracted_lang
        except Exception as e:
            logger.warning(f"Could not extract language from {voice_id}: {e}")
        
        # Fallback
        return "pt-BR"
    
    def _process_text_for_strategy(self, text: str, language: str, strategy: dict) -> str:
        """
        Process text according to synthesis strategy (SEM SSML por padrão)
        
        Args:
            text: Original text
            language: Text language
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
            
            # CORREÇÃO: NÃO adicionar SSML por padrão
            if strategy.get("ssml", False) and USE_SSML_BY_DEFAULT:
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
        """Add simple SSML wrapper (DESABILITADO)"""
        try:
            # CORREÇÃO: SSML muito básico ou desabilitado
            return f'<speak><prosody rate="{SPEAKING_RATE}">{text}</prosody></speak>'
            
        except Exception as e:
            logger.warning(f"SSML addition failed: {e}")
            return text
    
    def _synthesize_single_cross_language(self, text: str, voice_id: str, voice_language: str, strategy: dict) -> bytes:
        """Synthesize single text with cross-language support"""
        if self.use_cloud_sdk:
            return self._synthesize_cloud_sdk_cross_language(text, voice_id, voice_language, strategy)
        else:
            return self._synthesize_rest_api_cross_language(text, voice_id, voice_language, strategy)
    
    def _synthesize_cloud_sdk_cross_language(self, text: str, voice_id: str, voice_language: str, strategy: dict) -> bytes:
        """Cloud SDK synthesis with cross-language support"""
        from google.cloud import texttospeech
        
        logger.debug(f"Cloud SDK cross-language synthesis: {voice_language} voice + any text")
        
        # CORREÇÃO: Determinar input type SEM SSML por padrão
        if strategy.get("ssml", False) and USE_SSML_BY_DEFAULT and text.strip().startswith('<speak>'):
            synthesis_input = texttospeech.SynthesisInput(ssml=text)
            logger.debug("Using SSML input")
        else:
            synthesis_input = texttospeech.SynthesisInput(text=text)
            logger.debug("Using text input (no SSML)")
        
        # CORREÇÃO: Usar voice_id EXATO e language da voz
        voice = texttospeech.VoiceSelectionParams(
            language_code=voice_language,  # Idioma da voz (ex: pt-BR)
            name=voice_id                  # Voice ID exato (ex: pt-BR-Chirp3-HD-Laomedeia)
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
        
        logger.debug(f"Cloud SDK cross-language synthesis successful: {len(response.audio_content)} bytes")
        return response.audio_content
    
    def _synthesize_rest_api_cross_language(self, text: str, voice_id: str, voice_language: str, strategy: dict) -> bytes:
        """REST API synthesis with cross-language support"""
        logger.debug(f"REST API cross-language synthesis: {voice_language} voice")
        
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={self.api_key}"
        
        # CORREÇÃO: Determinar input type SEM SSML por padrão
        if strategy.get("ssml", False) and USE_SSML_BY_DEFAULT and text.strip().startswith('<speak>'):
            input_data = {"ssml": text}
            logger.debug("Using SSML input")
        else:
            input_data = {"text": text}
            logger.debug("Using text input (no SSML)")
        
        # CORREÇÃO: Build request body com voice_id EXATO
        body = {
            "input": input_data,
            "voice": {
                "languageCode": voice_language,  # Idioma da voz (ex: pt-BR)
                "name": voice_id                 # Voice ID exato
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
        
        logger.debug(f"API Request: voice={voice_id}, languageCode={voice_language}")
        
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
        logger.debug(f"REST API cross-language synthesis successful: {len(audio_bytes)} bytes")
        return audio_bytes
    
    def _synthesize_segments_cross_language(self, text: str, voice_id: str, voice_language: str, strategy: dict) -> Path:
        """Synthesize multiple segments with cross-language support"""
        # Split text into segments
        segments = self._split_text_smart(text)
        logger.info(f"Processing {len(segments)} segments with cross-language")
        
        # Synthesize each segment
        segment_files = []
        
        for i, segment in enumerate(segments):
            logger.debug(f"Synthesizing segment {i+1}/{len(segments)}")
            
            try:
                audio_bytes = self._synthesize_single_cross_language(segment, voice_id, voice_language, strategy)
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
        filename = f"google_cross_lang_{prefix}_{uuid.uuid4().hex[:8]}.wav"
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
        filename = f"google_cross_lang_{prefix}_{uuid.uuid4().hex[:8]}.wav"
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
            "name": "Google Cloud Text-to-Speech (Cross-Language)",
            "engine_id": "google",
            "available": self.is_available(),
            "method": method,
            "max_chars": MAX_BYTES_PER_REQUEST,
            "features": ["cross_language_synthesis", "no_voice_forcing", "no_ssml_default", "pt_voice_speaks_english"],
            "settings": {
                "speaking_rate": SPEAKING_RATE,
                "voice_forcing": ENABLE_VOICE_FORCING,  # False
                "ssml_default": USE_SSML_BY_DEFAULT,   # False
                "cross_language": True,
                "fallback_attempts": len(FALLBACK_STRATEGIES)
            }
        }

# Test function when run directly
if __name__ == "__main__":
    import sys
    
    print("🧪 Testing Google TTS Engine (Cross-Language Version)...")
    
    # Test configuration
    test_voice = "pt-BR-Chirp3-HD-Laomedeia"  # Voz portuguesa
    test_text_pt = "Bom dia, senhoras e senhores passageiros."
    test_text_en = "Good evening, ladies and gentlemen. Welcome aboard."
    
    try:
        # Initialize engine
        engine = GoogleTTS()
        
        print(f"🔧 Engine info: {engine.get_engine_info()}")
        print(f"✅ Available: {engine.is_available()}")
        print(f"✅ Voice validation: {engine.validate_voice_id(test_voice)}")
        print(f"🌍 Cross-language: PT voice can speak English")
        
        if engine.is_available():
            print(f"\n🔊 Testing cross-language synthesis...")
            print(f"Voice: {test_voice} (portuguesa)")
            
            # Test 1: Portuguese text with Portuguese voice
            print(f"\nTest 1: PT voice speaking PT text")
            audio_file_pt = engine.synthesize(test_text_pt, "pt-BR", test_voice)
            print(f"✅ PT→PT: {audio_file_pt}")
            
            # Test 2: English text with Portuguese voice (CROSS-LANGUAGE)
            print(f"\nTest 2: PT voice speaking EN text (cross-language)")
            audio_file_en = engine.synthesize(test_text_en, "en", test_voice)
            print(f"✅ PT→EN: {audio_file_en}")
            
            print(f"\n🎉 Cross-language synthesis working!")
            print(f"Portuguese voice successfully spoke both PT and EN texts")
            
        else:
            print("❌ Engine not available - check configuration")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        logger.exception("Google TTS cross-language test failed")
        sys.exit(1)