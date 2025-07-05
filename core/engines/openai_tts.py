"""
engines/openai_tts.py - OpenAI Text-to-Speech Engine

Responsibilities:
- Synthesize text using OpenAI TTS API (designed as fallback engine)
- Simple, reliable voice synthesis
- Minimal text processing (OpenAI handles longer texts well)
- Voice ID validation and error handling
- Fast generation for fallback scenarios
"""

import requests
import tempfile
import uuid
from pathlib import Path

from core.utils import ENV, logger, ROOT

# ============================================
# CONFIGURABLE SETTINGS
# ============================================

# OpenAI TTS settings
MODEL = "tts-1-hd"  # High-definition model for better quality
SPEED = 1.0  # Speech speed (0.25 to 4.0)
RESPONSE_FORMAT = "wav"  # Output format

# Available OpenAI voices
AVAILABLE_VOICES = [
    "alloy",    # Neutral, balanced
    "echo",     # Slightly more masculine
    "fable",    # British accent, softer
    "onyx",     # Deep, masculine
    "nova",     # Young, energetic
    "shimmer"   # Soft, feminine
]

# Fallback voice mapping by gender
GENDER_VOICE_MAP = {
    "female": "nova",    # Young, energetic female voice
    "male": "onyx"       # Deep, masculine voice
}

# API settings
API_TIMEOUT = 45  # Request timeout in seconds
MAX_TEXT_LENGTH = 4000  # OpenAI TTS limit

# Temporary files
TEMP_DIR = ROOT / "core" / ".temp" / "openai"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

class OpenAITTS:
    """
    OpenAI Text-to-Speech Engine
    Designed as reliable fallback with simple operation
    """
    
    def __init__(self):
        self.api_key = ENV.get("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1/audio/speech"
        
        if not self.api_key:
            logger.warning("OpenAI API key not found in environment")
        else:
            logger.info("OpenAI TTS initialized")
    
    def is_available(self) -> bool:
        """
        Check if OpenAI TTS is available and configured
        
        Returns:
            bool: True if available
        """
        return bool(self.api_key)
    
    def validate_voice_id(self, voice_id: str) -> bool:
        """
        Validate if voice ID is valid for OpenAI TTS
        
        Args:
            voice_id: OpenAI voice ID or auto-select keyword
            
        Returns:
            bool: True if voice is valid
        """
        if not voice_id:
            return False
        
        # Accept standard OpenAI voices
        if voice_id.lower() in AVAILABLE_VOICES:
            return True
        
        # Accept gender-based auto-selection
        if voice_id.lower() in ["auto_female", "auto_male"]:
            return True
        
        # Accept fallback indicator
        if voice_id.lower() in ["fallback", "auto"]:
            return True
        
        logger.warning(f"Unknown OpenAI voice ID: {voice_id}")
        return False
    
    def _resolve_voice_id(self, voice_id: str, text: str = "", gender_hint: str = "female") -> str:
        """
        Resolve voice ID to actual OpenAI voice name
        
        Args:
            voice_id: Input voice ID (may be auto-select)
            text: Text context (unused for OpenAI)
            gender_hint: Gender hint for auto-selection
            
        Returns:
            str: Actual OpenAI voice name
        """
        # Direct voice mapping
        if voice_id.lower() in AVAILABLE_VOICES:
            return voice_id.lower()
        
        # Gender-based auto-selection
        if voice_id.lower() in ["auto_female", "fallback_female"]:
            return GENDER_VOICE_MAP["female"]
        
        if voice_id.lower() in ["auto_male", "fallback_male"]:
            return GENDER_VOICE_MAP["male"]
        
        # Generic fallback
        if voice_id.lower() in ["fallback", "auto"]:
            return GENDER_VOICE_MAP.get(gender_hint.lower(), "nova")
        
        # Unknown voice - use gender hint
        logger.warning(f"Unknown voice {voice_id}, using gender hint: {gender_hint}")
        return GENDER_VOICE_MAP.get(gender_hint.lower(), "nova")
    
    def synthesize(self, text: str, language: str, voice_id: str, gender_hint: str = "female") -> Path:
        """
        Synthesize text to speech using OpenAI TTS
        
        Args:
            text: Text to synthesize
            language: Language code (informational for OpenAI)
            voice_id: OpenAI voice identifier or auto-select
            gender_hint: Gender hint for voice auto-selection
            
        Returns:
            Path: Generated WAV file path
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")
        
        if not self.is_available():
            raise RuntimeError("OpenAI TTS not configured")
        
        # Resolve actual voice name
        actual_voice = self._resolve_voice_id(voice_id, text, gender_hint)
        
        logger.info(f"OpenAI TTS: Synthesizing with voice {actual_voice}")
        logger.debug(f"Text length: {len(text)} characters")
        
        # Check text length
        if len(text) > MAX_TEXT_LENGTH:
            logger.warning(f"Text length {len(text)} exceeds OpenAI limit {MAX_TEXT_LENGTH}, truncating")
            text = text[:MAX_TEXT_LENGTH]
        
        try:
            # Single request - OpenAI handles longer texts well
            audio_bytes = self._synthesize_single(text, actual_voice)
            return self._save_audio_bytes(audio_bytes, "openai")
                
        except Exception as e:
            logger.error(f"OpenAI TTS synthesis failed: {e}")
            raise RuntimeError(f"OpenAI TTS synthesis failed: {e}")
    
    def _synthesize_single(self, text: str, voice: str) -> bytes:
        """
        Synthesize single text using OpenAI TTS API
        
        Args:
            text: Text to synthesize
            voice: OpenAI voice name
            
        Returns:
            bytes: Audio data in WAV format
        """
        logger.debug(f"OpenAI API synthesis: {text[:50]}...")
        
        # Prepare API request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": MODEL,
            "input": text,
            "voice": voice,
            "response_format": RESPONSE_FORMAT,
            "speed": SPEED
        }
        
        try:
            # Make API request
            response = requests.post(
                self.base_url, 
                json=data, 
                headers=headers, 
                timeout=API_TIMEOUT
            )
            
            if response.status_code != 200:
                error_msg = f"OpenAI TTS API error {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg += f": {error_detail}"
                except:
                    error_msg += f": {response.text}"
                
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            logger.debug(f"OpenAI API response: {len(response.content)} bytes")
            return response.content
            
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenAI request failed: {e}")
            raise RuntimeError(f"OpenAI request failed: {e}")
    
    def _save_audio_bytes(self, audio_bytes: bytes, prefix: str) -> Path:
        """
        Save audio bytes to temporary file
        
        Args:
            audio_bytes: Audio data
            prefix: Filename prefix
            
        Returns:
            Path: Saved file path
        """
        filename = f"openai_{prefix}_{uuid.uuid4().hex[:8]}.wav"
        file_path = TEMP_DIR / filename
        
        try:
            file_path.write_bytes(audio_bytes)
            logger.debug(f"Audio saved: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving audio bytes: {e}")
            raise
    
    def get_available_voices(self) -> list:
        """
        Get list of available voices
        
        Returns:
            list: List of voice identifiers with descriptions
        """
        return [
            {"id": "alloy", "description": "Neutral, balanced voice"},
            {"id": "echo", "description": "Slightly masculine voice"},
            {"id": "fable", "description": "British accent, softer voice"},
            {"id": "onyx", "description": "Deep, masculine voice"},
            {"id": "nova", "description": "Young, energetic voice"},
            {"id": "shimmer", "description": "Soft, feminine voice"},
            {"id": "auto_female", "description": "Auto-select female voice"},
            {"id": "auto_male", "description": "Auto-select male voice"},
            {"id": "fallback", "description": "Default fallback voice"}
        ]
    
    def get_engine_info(self) -> dict:
        """
        Get engine information and status
        
        Returns:
            dict: Engine information
        """
        return {
            "name": "OpenAI Text-to-Speech",
            "engine_id": "openai",
            "available": self.is_available(),
            "model": MODEL,
            "max_chars": MAX_TEXT_LENGTH,
            "available_voices": len(AVAILABLE_VOICES),
            "features": ["multilingual", "fast_generation", "fallback_optimized", "gender_auto_select"]
        }
    
    def create_fallback_synthesis(self, text: str, voice_type: str = "female") -> Path:
        """
        Quick fallback synthesis with minimal configuration
        
        Args:
            text: Text to synthesize
            voice_type: "female" or "male" for voice selection
            
        Returns:
            Path: Generated audio file
        """
        logger.info(f"Creating fallback synthesis ({voice_type})")
        
        # Use appropriate fallback voice
        fallback_voice = GENDER_VOICE_MAP.get(voice_type.lower(), "nova")
        
        try:
            return self.synthesize(text, "en", fallback_voice, voice_type)
        except Exception as e:
            logger.error(f"Fallback synthesis failed: {e}")
            raise

# Convenience functions for fallback scenarios
def create_quick_fallback(text: str, gender: str = "female") -> Path:
    """
    Quick fallback TTS synthesis
    
    Args:
        text: Text to synthesize
        gender: "female" or "male"
        
    Returns:
        Path: Audio file path
    """
    engine = OpenAITTS()
    return engine.create_fallback_synthesis(text, gender)

def synthesize(text: str, lang: str, voice_id: str) -> Path:
    """
    Standard synthesis function for compatibility
    
    Args:
        text: Text to synthesize
        lang: Language code
        voice_id: Voice identifier
        
    Returns:
        Path: Generated audio file
    """
    engine = OpenAITTS()
    return engine.synthesize(text, lang, voice_id)

# Test function when run directly
if __name__ == "__main__":
    import sys
    
    print("🧪 Testing OpenAI TTS Engine...")
    
    # Test configuration
    test_voices = ["nova", "onyx", "auto_female", "fallback"]
    test_text = "Good evening, ladies and gentlemen. Welcome aboard flight two zero zero to Bangkok."
    
    try:
        # Initialize engine
        engine = OpenAITTS()
        
        print(f"🔧 Engine info: {engine.get_engine_info()}")
        print(f"✅ Available: {engine.is_available()}")
        
        if engine.is_available():
            print(f"\n🎭 Available voices:")
            for voice in engine.get_available_voices():
                print(f"  • {voice['id']}: {voice['description']}")
            
            # Test voice validation
            print(f"\n🔍 Voice validation tests:")
            for voice in test_voices:
                valid = engine.validate_voice_id(voice)
                print(f"  • {voice}: {'✅' if valid else '❌'}")
            
            # Test synthesis with fallback voice
            print(f"\n🔊 Testing fallback synthesis...")
            
            audio_file = engine.create_fallback_synthesis(test_text, "female")
            
            print(f"✅ Fallback synthesis completed!")
            print(f"📁 Output file: {audio_file}")
            
            # Get audio info
            size = audio_file.stat().st_size / 1024
            print(f"📊 Size: {size:.1f} KB")
            
        else:
            print("❌ Engine not available - check API key configuration")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        logger.exception("OpenAI TTS test failed")
        sys.exit(1)