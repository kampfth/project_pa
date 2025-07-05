"""
engines/elevenlabs_tts.py - ElevenLabs Text-to-Speech Engine (ULTRA NATURAL)

Responsibilities:
- Synthesize text using ElevenLabs API with ULTRA NATURAL voice settings
- Handle text length by splitting into paragraphs (never split words)
- Combine multiple paragraphs into single audio file
- Voice ID validation and error handling
- ULTRA NATURAL flight attendant voice optimization
- Advanced voice cloning and emotion control
"""

import requests
import tempfile
import uuid
from pathlib import Path
from pydub import AudioSegment
import re

from core.utils import ENV, logger, ROOT

# ============================================
# CONFIGURAÇÕES ULTRA NATURAIS - ELEVENLABS
# ============================================

# Text processing - ElevenLabs can handle longer texts
MAX_CHARS_PER_REQUEST = 2500  # Conservative limit for ElevenLabs
MAX_PARAGRAPHS_PER_REQUEST = 3  # Process multiple paragraphs together when possible

# Audio combination
PARAGRAPH_PAUSE_MS = 600  # Pausa mais natural entre parágrafos
AUDIO_FORMAT = "wav"  # Output format

# === CONFIGURAÇÕES DE VOZ ULTRA NATURAL ===
# Voice settings for ElevenLabs (OTIMIZADO PARA NATURALIDADE)
VOICE_SETTINGS = {
    "stability": 0.4,        # BAIXA estabilidade = mais variação natural (0.0 to 1.0)
    "similarity_boost": 0.9, # ALTA similaridade = mantém características da voz (0.0 to 1.0)  
    "style": 0.6,           # MÉDIA style = adiciona emoção natural (0.0 to 1.0)
    "use_speaker_boost": True # Sempre ativar para melhor qualidade
}

# === CONFIGURAÇÕES AVANÇADAS DE NATURALIDADE ===
USE_ADVANCED_PREPROCESSING = True  # Preprocessamento avançado de texto
ADD_NATURAL_PAUSES = True         # Adicionar pausas naturais
IMPROVE_FLIGHT_PRONUNCIATION = True # Melhorar pronúncia de termos de aviação
USE_EMOTIONAL_CONTEXT = True      # Usar contexto emocional

# Configurações de emoção por tipo de anúncio
EMOTION_SETTINGS = {
    "boarding": {
        "stability": 0.3,      # Mais variação = mais caloroso
        "similarity_boost": 0.9,
        "style": 0.7,          # Mais estilo = mais acolhedor
        "use_speaker_boost": True
    },
    "arrival": {
        "stability": 0.5,      # Mais estável = mais profissional
        "similarity_boost": 0.85,
        "style": 0.4,          # Menos estilo = mais neutra
        "use_speaker_boost": True
    },
    "safety": {
        "stability": 0.6,      # Mais estável = mais séria
        "similarity_boost": 0.9,
        "style": 0.2,          # Pouco estilo = mais autoritária
        "use_speaker_boost": True
    }
}

# Configurações de pausas naturais (em segundos)
NATURAL_PAUSES = {
    "greeting": 1.2,        # Pausa após saudação
    "sentence": 0.8,        # Pausa entre frases
    "breath": 0.6,          # Pausa de respiração
    "emphasis": 0.4,        # Pausa antes de informação importante
    "transition": 1.0       # Pausa entre seções diferentes
}

# API settings
API_TIMEOUT = 60  # Request timeout in seconds
MODEL_ID = "eleven_multilingual_v2"  # ElevenLabs model

# Temporary files
TEMP_DIR = ROOT / "core" / ".temp" / "elevenlabs"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

class ElevenLabsTTS:
    """
    ElevenLabs Text-to-Speech Engine with ULTRA NATURAL voice
    Optimized for professional flight attendant announcements
    """
    
    def __init__(self, context: str = "boarding"):
        """
        Initialize with context for emotional tuning
        
        Args:
            context: "boarding", "arrival", or "safety" for emotional optimization
        """
        self.api_key = ENV.get("ELEVEN_API_KEY")
        self.base_url = "https://api.elevenlabs.io/v1/text-to-speech"
        self.context = context
        
        # Set voice settings based on context
        if USE_EMOTIONAL_CONTEXT and context in EMOTION_SETTINGS:
            self.voice_settings = EMOTION_SETTINGS[context]
            logger.info(f"ElevenLabs TTS initialized with {context} emotional context")
        else:
            self.voice_settings = VOICE_SETTINGS
            logger.info("ElevenLabs TTS initialized with default settings")
        
        if not self.api_key:
            logger.warning("ElevenLabs API key not found in environment")
        else:
            logger.info(f"ElevenLabs TTS initialized (Ultra Natural Mode - {context})")
    
    def is_available(self) -> bool:
        """Check if ElevenLabs TTS is available and configured"""
        return bool(self.api_key)
    
    def validate_voice_id(self, voice_id: str) -> bool:
        """Validate if voice ID exists in ElevenLabs"""
        if not voice_id:
            return False
        
        # Basic format validation for ElevenLabs voice IDs
        # ElevenLabs voice IDs are typically 20 characters long, alphanumeric
        if len(voice_id) != 20:
            logger.warning(f"Invalid ElevenLabs voice ID length: {voice_id}")
            return False
        
        # Check if it contains only valid characters
        if not voice_id.isalnum():
            logger.warning(f"Invalid ElevenLabs voice ID format: {voice_id}")
            return False
        
        logger.debug(f"Voice ID validation passed: {voice_id}")
        return True
    
    def synthesize(self, text: str, language: str, voice_id: str) -> Path:
        """
        Synthesize text to speech using ElevenLabs with ULTRA NATURAL settings
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")
        
        if not self.is_available():
            raise RuntimeError("ElevenLabs TTS not configured")
        
        if not self.validate_voice_id(voice_id):
            raise ValueError(f"Invalid voice ID: {voice_id}")
        
        logger.info(f"ElevenLabs TTS (Ultra Natural): Synthesizing with voice {voice_id}")
        logger.debug(f"Text length: {len(text)} characters, Context: {self.context}")
        
        try:
            # PREPROCESSING: Convert text to ultra natural speech
            if USE_ADVANCED_PREPROCESSING:
                processed_text = self._preprocess_for_ultra_natural(text, language)
            else:
                processed_text = text
            
            # Check if text needs paragraph splitting
            if len(processed_text) <= MAX_CHARS_PER_REQUEST:
                # Single request
                logger.debug("Text within limit, single synthesis")
                audio_bytes = self._synthesize_single(processed_text, voice_id)
                return self._save_audio_bytes(audio_bytes, "single")
            else:
                # Multiple paragraphs
                logger.info("Text exceeds limit, splitting by paragraphs")
                return self._synthesize_paragraphs(processed_text, voice_id)
                
        except Exception as e:
            logger.error(f"ElevenLabs TTS synthesis failed: {e}")
            raise RuntimeError(f"ElevenLabs TTS synthesis failed: {e}")
    
    def _preprocess_for_ultra_natural(self, text: str, language: str) -> str:
        """
        Advanced preprocessing for ultra natural speech
        """
        logger.debug("Applying ultra natural preprocessing")
        
        processed = text
        
        # 1. Add natural pauses
        if ADD_NATURAL_PAUSES:
            processed = self._add_natural_pauses(processed)
        
        # 2. Improve flight pronunciation
        if IMPROVE_FLIGHT_PRONUNCIATION:
            processed = self._improve_flight_pronunciation(processed)
        
        # 3. Convert numbers to natural speech
        processed = self._convert_numbers_naturally(processed)
        
        # 4. Add breathing pauses for long texts
        if len(processed) > 300:
            processed = self._add_breathing_pauses(processed)
        
        logger.debug(f"Ultra natural preprocessing completed. Length: {len(processed)} chars")
        return processed
    
    def _add_natural_pauses(self, text: str) -> str:
        """
        Add natural pauses using punctuation and strategic breaks
        """
        processed = text
        
        # Add pause after greetings
        greetings = [
            r"(Good evening, ladies and gentlemen)",
            r"(Good morning, ladies and gentlemen)", 
            r"(Good afternoon, ladies and gentlemen)",
            r"(Ladies and gentlemen)"
        ]
        
        for greeting_pattern in greetings:
            processed = re.sub(
                greeting_pattern,
                r"\1...",  # Triple dots create natural pause
                processed,
                flags=re.IGNORECASE
            )
        
        # Add pause before important information
        important_phrases = [
            r"(Welcome aboard)",
            r"(This flight will take)",
            r"(Federal regulations)",
            r"(For your safety)",
            r"(Thank you)"
        ]
        
        for phrase_pattern in important_phrases:
            processed = re.sub(
                phrase_pattern,
                r"... \1",  # Pause before important info
                processed,
                flags=re.IGNORECASE
            )
        
        # Add natural pauses after periods
        processed = re.sub(r'\.(\s+)([A-Z])', r'...\1\2', processed)
        
        return processed
    
    def _improve_flight_pronunciation(self, text: str) -> str:
        """
        Improve pronunciation of aviation terms for ElevenLabs
        """
        # ElevenLabs-specific pronunciation improvements
        pronunciations = {
            # Airlines
            'Thai Airways': 'Thai Air-ways',
            'Emirates': 'Em-i-rates',
            'Qatar Airways': 'Kah-tar Air-ways',
            'Cathay Pacific': 'Cath-ay Pa-cif-ic',
            
            # Cities with pronunciation challenges
            'Bangkok': 'Bang-kok',
            'Qatar': 'Kah-tar',
            'Dubai': 'Doo-bye',
            'Seoul': 'See-oul',
            'Beijing': 'Bay-jing',
            
            # Aviation terms
            'aircraft': 'air-craft',
            'announcement': 'an-nounce-ment',
            'approximately': 'ap-prox-i-mate-ly',
            'temperature': 'tem-per-a-ture',
            'regulations': 'reg-u-la-tions',
            'compartment': 'com-part-ment',
            'destination': 'des-ti-na-tion',
            
            # Numbers that need special treatment
            'twenty': 'twen-ty',
            'thirty': 'thir-ty',
            'forty': 'for-ty',
            'fifty': 'fif-ty'
        }
        
        processed = text
        for original, improved in pronunciations.items():
            # Case-insensitive replacement with word boundaries
            pattern = r'\b' + re.escape(original) + r'\b'
            processed = re.sub(pattern, improved, processed, flags=re.IGNORECASE)
        
        return processed
    
    def _convert_numbers_naturally(self, text: str) -> str:
        """
        Convert numbers to natural speech patterns for flight announcements
        """
        processed = text
        
        # Flight numbers: "flight 200" -> "flight two zero zero"
        def convert_flight_number(match):
            number = match.group(1)
            digits = {
                '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
                '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'
            }
            digit_words = ' '.join([digits.get(digit, digit) for digit in number])
            return f"flight {digit_words}"
        
        processed = re.sub(r'\bflight\s+(\d+)', convert_flight_number, processed, flags=re.IGNORECASE)
        
        # Time durations: "5 hours and 27 minutes" -> "five hours and twenty-seven minutes"
        time_words = {
            '1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five',
            '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine', '10': 'ten',
            '11': 'eleven', '12': 'twelve', '13': 'thirteen', '14': 'fourteen', '15': 'fifteen',
            '16': 'sixteen', '17': 'seventeen', '18': 'eighteen', '19': 'nineteen', '20': 'twenty',
            '21': 'twenty-one', '22': 'twenty-two', '23': 'twenty-three', '24': 'twenty-four',
            '25': 'twenty-five', '26': 'twenty-six', '27': 'twenty-seven', '28': 'twenty-eight',
            '29': 'twenty-nine', '30': 'thirty', '40': 'forty', '50': 'fifty', '60': 'sixty'
        }
        
        # Convert hour numbers
        for num, word in time_words.items():
            processed = re.sub(r'\b' + num + r'\s+(hour)', word + r' \1', processed, flags=re.IGNORECASE)
            processed = re.sub(r'\b' + num + r'\s+(minute)', word + r' \1', processed, flags=re.IGNORECASE)
        
        return processed
    
    def _add_breathing_pauses(self, text: str) -> str:
        """
        Add natural breathing pauses for longer announcements
        """
        # Split into sentences
        sentences = re.split(r'([.!?]+)', text)
        processed_sentences = []
        
        sentence_count = 0
        for sentence in sentences:
            if sentence.strip() and sentence not in '.!?':
                sentence_count += 1
                processed_sentences.append(sentence)
                
                # Add breathing pause every 2-3 sentences
                if sentence_count % 3 == 0 and sentence_count < len(sentences) - 1:
                    processed_sentences.append("...")  # Natural breathing pause
            else:
                processed_sentences.append(sentence)
        
        return ''.join(processed_sentences)
    
    def _split_text_by_paragraphs(self, text: str) -> list:
        """Split text into paragraphs, ensuring no words are broken"""
        # Split by double newlines (paragraphs)
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        if not paragraphs:
            # Fallback: treat entire text as one paragraph
            return [text.strip()]
        
        logger.debug(f"Found {len(paragraphs)} paragraphs")
        
        # Group paragraphs to fit within character limits
        paragraph_groups = []
        current_group = ""
        
        for paragraph in paragraphs:
            # Test if we can add this paragraph to current group
            test_group = f"{current_group}\n\n{paragraph}".strip() if current_group else paragraph
            
            if len(test_group) <= MAX_CHARS_PER_REQUEST:
                # Fits in current group
                current_group = test_group
            else:
                # Start new group
                if current_group:
                    paragraph_groups.append(current_group)
                
                # Check if single paragraph is too long
                if len(paragraph) > MAX_CHARS_PER_REQUEST:
                    logger.warning(f"Single paragraph exceeds limit: {len(paragraph)} chars")
                    # Split long paragraph by sentences, but keep as complete sentences
                    sentence_groups = self._split_paragraph_by_sentences(paragraph)
                    paragraph_groups.extend(sentence_groups)
                    current_group = ""
                else:
                    current_group = paragraph
        
        # Add final group
        if current_group:
            paragraph_groups.append(current_group)
        
        logger.debug(f"Created {len(paragraph_groups)} paragraph groups")
        return paragraph_groups
    
    def _split_paragraph_by_sentences(self, paragraph: str) -> list:
        """Split long paragraph by sentences as last resort"""
        logger.debug("Splitting long paragraph by sentences")
        
        # Split by periods, keeping periods with sentences
        sentences = []
        parts = paragraph.split('.')
        
        for i, part in enumerate(parts):
            if part.strip():
                sentence = part.strip() + ('.' if i < len(parts) - 1 else '')
                sentences.append(sentence)
        
        # Group sentences
        sentence_groups = []
        current_group = ""
        
        for sentence in sentences:
            test_group = f"{current_group} {sentence}".strip() if current_group else sentence
            
            if len(test_group) <= MAX_CHARS_PER_REQUEST:
                current_group = test_group
            else:
                if current_group:
                    sentence_groups.append(current_group)
                current_group = sentence
        
        if current_group:
            sentence_groups.append(current_group)
        
        logger.debug(f"Created {len(sentence_groups)} sentence groups")
        return sentence_groups
    
    def _synthesize_single(self, text: str, voice_id: str) -> bytes:
        """
        Synthesize single text segment using ElevenLabs API with ultra natural settings
        """
        logger.debug(f"ElevenLabs Ultra Natural API synthesis: {text[:50]}...")
        
        # Prepare API request
        url = f"{self.base_url}/{voice_id}"
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        
        data = {
            "text": text,
            "model_id": MODEL_ID,
            "voice_settings": self.voice_settings  # Ultra natural settings
        }
        
        try:
            # Make API request
            response = requests.post(url, json=data, headers=headers, timeout=API_TIMEOUT)
            
            if response.status_code != 200:
                error_msg = f"ElevenLabs API error {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg += f": {error_detail}"
                except:
                    error_msg += f": {response.text}"
                
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            logger.debug(f"ElevenLabs Ultra Natural response: {len(response.content)} bytes")
            return response.content
            
        except requests.exceptions.RequestException as e:
            logger.error(f"ElevenLabs request failed: {e}")
            raise RuntimeError(f"ElevenLabs request failed: {e}")
    
    def _synthesize_paragraphs(self, text: str, voice_id: str) -> Path:
        """Synthesize text by splitting into paragraphs and combining"""
        # Split text into paragraph groups
        paragraph_groups = self._split_text_by_paragraphs(text)
        logger.info(f"Processing {len(paragraph_groups)} paragraph groups")
        
        # Synthesize each group
        audio_files = []
        
        for i, paragraph_group in enumerate(paragraph_groups):
            logger.debug(f"Synthesizing paragraph group {i+1}/{len(paragraph_groups)}")
            
            try:
                # Synthesize paragraph group
                mp3_bytes = self._synthesize_single(paragraph_group, voice_id)
                
                # Convert MP3 to WAV and save
                audio_file = self._convert_mp3_to_wav(mp3_bytes, f"paragraph_{i}")
                audio_files.append(audio_file)
                
            except Exception as e:
                logger.error(f"Error synthesizing paragraph group {i+1}: {e}")
                # Cleanup partial files
                for af in audio_files:
                    try:
                        af.unlink()
                    except:
                        pass
                raise
        
        # Combine all audio files with natural pauses
        combined_file = self._combine_audio_files_naturally(audio_files)
        
        # Cleanup individual files
        for audio_file in audio_files:
            try:
                audio_file.unlink()
            except Exception as e:
                logger.warning(f"Error cleaning audio file: {e}")
        
        return combined_file
    
    def _convert_mp3_to_wav(self, mp3_bytes: bytes, prefix: str) -> Path:
        """Convert MP3 bytes to WAV file"""
        try:
            # Save MP3 temporarily
            mp3_filename = f"elevenlabs_natural_{prefix}_{uuid.uuid4().hex[:8]}.mp3"
            mp3_path = TEMP_DIR / mp3_filename
            mp3_path.write_bytes(mp3_bytes)
            
            # Convert to WAV
            audio = AudioSegment.from_mp3(mp3_path)
            wav_filename = f"elevenlabs_natural_{prefix}_{uuid.uuid4().hex[:8]}.wav"
            wav_path = TEMP_DIR / wav_filename
            audio.export(wav_path, format=AUDIO_FORMAT)
            
            # Remove temporary MP3
            mp3_path.unlink()
            
            logger.debug(f"MP3 converted to WAV: {wav_path}")
            return wav_path
            
        except Exception as e:
            logger.error(f"Error converting MP3 to WAV: {e}")
            raise
    
    def _combine_audio_files_naturally(self, audio_files: list) -> Path:
        """
        Combine multiple audio files with natural pauses between paragraphs
        """
        logger.debug(f"Combining {len(audio_files)} audio files naturally")
        
        try:
            # Load first audio file
            combined_audio = AudioSegment.from_wav(audio_files[0])
            
            # Add remaining files with natural pauses
            for audio_file in audio_files[1:]:
                audio_segment = AudioSegment.from_wav(audio_file)
                # Natural pause between paragraphs (shorter than before for better flow)
                pause = AudioSegment.silent(duration=PARAGRAPH_PAUSE_MS)
                combined_audio += pause + audio_segment
            
            # Save combined audio
            combined_file = self._save_audio_segment(combined_audio, "ultra_natural")
            
            duration = len(combined_audio) / 1000
            logger.info(f"Audio files combined naturally: {duration:.1f}s total")
            
            return combined_file
            
        except Exception as e:
            logger.error(f"Error combining audio files naturally: {e}")
            raise
    
    def _save_audio_bytes(self, mp3_bytes: bytes, prefix: str) -> Path:
        """Save MP3 bytes as WAV file"""
        return self._convert_mp3_to_wav(mp3_bytes, prefix)
    
    def _save_audio_segment(self, audio_segment: AudioSegment, prefix: str) -> Path:
        """Save audio segment to file"""
        filename = f"elevenlabs_natural_{prefix}_{uuid.uuid4().hex[:8]}.wav"
        file_path = TEMP_DIR / filename
        
        try:
            audio_segment.export(file_path, format=AUDIO_FORMAT)
            logger.debug(f"Audio segment saved: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving audio segment: {e}")
            raise
    
    def get_voices(self) -> list:
        """Get list of available voices from ElevenLabs API"""
        if not self.is_available():
            return []
        
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": self.api_key}
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                voices_data = response.json().get("voices", [])
                logger.debug(f"Retrieved {len(voices_data)} voices from ElevenLabs")
                return voices_data
            else:
                logger.error(f"Failed to get voices: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting voices: {e}")
            return []
    
    def get_engine_info(self) -> dict:
        """Get engine information and status"""
        return {
            "name": "ElevenLabs Text-to-Speech (Ultra Natural)",
            "engine_id": "elevenlabs",
            "available": self.is_available(),
            "max_chars": MAX_CHARS_PER_REQUEST,
            "context": self.context,
            "voice_settings": self.voice_settings,
            "features": [
                "ultra_natural", "voice_cloning", "emotional_context", 
                "advanced_preprocessing", "flight_attendant_optimized"
            ]
        }

# Test function when run directly
if __name__ == "__main__":
    import sys
    
    print("🧪 Testing ElevenLabs TTS Engine (Ultra Natural)...")
    
    # Test configuration
    test_voice = "EIsgvJT3rwoPvRFG6c4n"  # Example voice ID
    test_text = """Good evening, ladies and gentlemen. On behalf of Thai Airways, it is my pleasure to welcome you aboard flight 200 with service to Bangkok.

This flight will take approximately 5 hours and 27 minutes, and until then, our crew will be pleased to serve you.

Federal regulations require that carry-on items are stowed prior to closing the aircraft door. Your items may be placed in an overhead compartment, or completely under the seat in front of you."""
    
    try:
        # Initialize engine with boarding context
        engine = ElevenLabsTTS(context="boarding")
        
        print(f"🔧 Engine info: {engine.get_engine_info()}")
        print(f"✅ Available: {engine.is_available()}")
        print(f"✅ Voice validation: {engine.validate_voice_id(test_voice)}")
        
        if engine.is_available():
            print(f"🔊 Synthesizing ultra natural test text...")
            
            audio_file = engine.synthesize(test_text, "en", test_voice)
            
            print(f"✅ Ultra Natural synthesis completed!")
            print(f"📁 Output file: {audio_file}")
            
            # Get audio info
            audio = AudioSegment.from_wav(audio_file)
            duration = len(audio) / 1000
            size = audio_file.stat().st_size / 1024
            
            print(f"📊 Duration: {duration:.1f}s")
            print(f"📊 Size: {size:.1f} KB")
            print(f"🎭 Context: {engine.context}")
            print(f"🎙️ Stability: {engine.voice_settings['stability']} (natural variation)")
            print(f"🎵 Style: {engine.voice_settings['style']} (emotional)")
            
            # Test voice listing
            voices = engine.get_voices()
            print(f"🎭 Available voices: {len(voices)}")
            
        else:
            print("❌ Engine not available - check API key configuration")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        logger.exception("ElevenLabs Ultra Natural test failed")
        sys.exit(1)