"""
core/post_processor.py - Audio post-processing and effects

Responsibilities:
- Combine multiple voice type audios according to priority order
- Apply professional aviation radio effects (highpass, compression, saturation, etc.)
- Generate final announcement file with authentic radio sound
- Create backups and manage file organization
- AUTOMATIC CLEANUP of individual audio files
"""

import json
import math
import shutil
from pathlib import Path
from datetime import datetime
from pydub import AudioSegment
from pydub.generators import WhiteNoise

from core.utils import ROOT, logger

# ============================================
# CONFIGURAÇÕES DE EFEITOS DE RÁDIO AVIAÇÃO
# ============================================

# Audio combination settings
VOICE_PAUSE_MS = 1200  # Pausa entre diferentes tipos de voz (nativo → inglês)

# === CONTROLE PRINCIPAL ===
APPLY_CABIN_EFFECTS = True    # Ativar/desativar todos os efeitos de rádio

# === FILTRO PASSA-ALTA (Corta sons graves) ===
HIGHPASS_ENABLED = True       # Ativar filtro passa-alta
HIGHPASS_FREQ = 800          # Frequência de corte (remove graves abaixo desta frequência)
HIGHPASS_SLOPE_1 = 18        # Intensidade do primeiro corte (mais alto = corte mais agressivo)
HIGHPASS_SLOPE_2 = 6         # Intensidade do segundo corte (adiciona mais corte)

# === FILTRO PASSA-BAIXA (Corta sons agudos) ===
LOWPASS_ENABLED = True       # Ativar filtro passa-baixa
LOWPASS_FREQ = 3000         # Frequência de corte (remove agudos acima desta frequência)
LOWPASS_SLOPE = 12          # Intensidade do corte dos agudos

# === COMPRESSÃO (Deixa o volume mais uniforme) ===
COMPRESSION_ENABLED = True   # Ativar compressão
COMPRESSION_RATIO = 10.0    # Força da compressão (10.0 = muito forte, deixa tudo no mesmo volume)
COMPRESSION_THRESHOLD = -12  # A partir de que volume começa a comprimir

# === SATURAÇÃO (Adiciona distorção de rádio) ===
SATURATION_ENABLED = True    # Ativar saturação
SATURATION_AMOUNT = 0.20    # Quantidade de distorção (0.20 = 20% de distorção)

# === RUÍDO DE TRANSMISSÃO (Chiado de rádio) ===
NOISE_ENABLED = True        # Ativar ruído de fundo
NOISE_AMPLITUDE = 0.15      # Intensidade do chiado (18% - 10% menos que os 20% original)
NOISE_MIX_RATIO = 0.04      # Proporção de mistura do chiado com a voz

# === VOLUME FINAL ===
LOUDNORM_ENABLED = True     # Ativar normalização de volume
TARGET_LUFS = -14           # Volume final (-14 = bem alto, como aviação urgente)
TARGET_PEAK = -2.0          # Pico máximo permitido

# === NOISE GATE (Corta ruído quando não tem voz) ===
NOISE_GATE_ENABLED = False   # Desativado (pode cortar partes da fala)
NOISE_GATE_THRESHOLD = -40  # Threshold para cortar ruído

# File management
FINAL_FILENAME = "final_announcement.wav"
RAW_FILENAME = "final_announcement_raw.wav"
AUTO_CLEANUP_INDIVIDUAL = True  # Limpar arquivos individuais automaticamente

# Audio format settings
AUDIO_FORMAT = "wav"
SAMPLE_RATE = 24000

# Processing options
SHOW_PROCESSING_SUMMARY = True  # Mostrar resumo detalhado do processamento
LOG_AUDIO_INFO = True           # Registrar informações detalhadas do áudio

# ============================================
# PATHS CONFIGURATION
# ============================================

OUTPUT_DIR = ROOT / "output"
AIRLINE_FILE = ROOT / "data" / "airline_profiles.json"

class PostProcessor:
    """
    Audio post-processor for boarding announcements
    Combines multiple voice types and applies professional aviation radio effects
    """
    
    def __init__(self):
        logger.info("Post-processor initialized with heavy compression radio effects")
    
    def process_announcement(self, audio_files: dict, simbrief_data: dict) -> dict:
        """
        Main processing function: combine audios and apply radio effects
        
        Args:
            audio_files: Dictionary of generated audio files {"voice_type": Path}
            simbrief_data: Flight data for configuration
            
        Returns:
            dict: Processing results with final file path
        """
        icao = simbrief_data.get("icao")
        if not icao:
            raise ValueError("ICAO not found in flight data")
        
        logger.info(f"Starting post-processing for {icao}")
        
        try:
            # 1. Load airline configuration
            airline_config = self._load_airline_config(icao)
            
            # 2. Combine audios according to priority order
            raw_combined_path = self._combine_voice_types(
                audio_files, airline_config, simbrief_data
            )
            
            # 3. Apply radio effects if enabled
            if APPLY_CABIN_EFFECTS:
                final_path = self._apply_radio_effects(raw_combined_path)
                # Clean up raw file after effects
                if raw_combined_path.exists():
                    raw_combined_path.unlink()
                    logger.debug("Removed intermediate raw file")
            else:
                # Just rename raw file to final
                final_path = OUTPUT_DIR / FINAL_FILENAME
                shutil.move(str(raw_combined_path), str(final_path))
                logger.info("Radio effects disabled - using clean audio")
            
            # 4. Generate processing report
            result = {
                "success": True,
                "final_file": final_path,
                "individual_files": audio_files,
                "cabin_effects_applied": APPLY_CABIN_EFFECTS,
                "processing_time": datetime.now().isoformat()
            }
            
            # 5. Show summary
            if SHOW_PROCESSING_SUMMARY:
                self._show_processing_summary(result, simbrief_data)
            
            # 6. AUTOMATIC CLEANUP - Remove individual audio files
            if AUTO_CLEANUP_INDIVIDUAL:
                self._cleanup_individual_files(audio_files)
            
            logger.info("Post-processing completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Post-processing failed: {e}")
            raise
    
    def _load_airline_config(self, icao: str) -> dict:
        """Load airline configuration for priority order"""
        if not AIRLINE_FILE.exists():
            raise FileNotFoundError(f"Airline profiles not found: {AIRLINE_FILE}")
        
        try:
            config = json.loads(AIRLINE_FILE.read_text())
            
            if icao not in config:
                raise ValueError(f"Airline {icao} not found in profiles")
            
            return config[icao]
            
        except Exception as e:
            raise RuntimeError(f"Error loading airline config: {e}")
    
    def _combine_voice_types(self, audio_files: dict, airline_config: dict, simbrief_data: dict) -> Path:
        """Combine voice type audios according to priority order"""
        priority_order = airline_config.get("priority_order", [])
        
        if not priority_order:
            raise ValueError("No priority order configured for airline")
        
        logger.info(f"Combining voice types in order: {priority_order}")
        
        # Filter available files in priority order
        available_files = []
        for voice_type in priority_order:
            if voice_type in audio_files and audio_files[voice_type].exists():
                available_files.append((voice_type, audio_files[voice_type]))
                logger.debug(f"Added to combination: {voice_type}")
            else:
                logger.warning(f"Missing voice type: {voice_type}")
        
        if not available_files:
            raise ValueError("No audio files available for combination")
        
        # Start with first audio
        combined_audio = AudioSegment.from_wav(available_files[0][1])
        if LOG_AUDIO_INFO:
            logger.debug(f"Base audio: {available_files[0][0]} ({len(combined_audio)/1000:.1f}s)")
        
        # Add remaining audios with pauses
        for i, (voice_type, file_path) in enumerate(available_files[1:], 1):
            # Add pause between voice types
            pause = AudioSegment.silent(duration=VOICE_PAUSE_MS)
            combined_audio += pause
            
            # Add next audio
            next_audio = AudioSegment.from_wav(file_path)
            combined_audio += next_audio
            
            if LOG_AUDIO_INFO:
                logger.debug(f"Added audio {i}: {voice_type} ({len(next_audio)/1000:.1f}s)")
        
        # Save raw combined file
        raw_path = OUTPUT_DIR / RAW_FILENAME
        combined_audio.export(raw_path, format=AUDIO_FORMAT)
        
        # Log combination info
        total_duration = len(combined_audio) / 1000
        voice_list = [vt for vt, _ in available_files]
        
        logger.info(f"Combined audio created:")
        logger.info(f"  Duration: {total_duration:.1f}s")
        logger.info(f"  Voice types: {' → '.join(voice_list)}")
        logger.info(f"  File: {raw_path}")
        
        return raw_path
    
    def _apply_radio_effects(self, raw_audio_path: Path) -> Path:
        """
        Apply professional aviation radio effects (Heavy Compression style)
        """
        logger.info("Applying heavy compression aviation radio effects")
        
        try:
            # Load raw audio
            audio = AudioSegment.from_wav(raw_audio_path)
            original_duration = len(audio) / 1000
            
            if LOG_AUDIO_INFO:
                logger.debug(f"Original audio: {original_duration:.1f}s")
            
            # 1. High-pass filtering (remove low frequencies)
            if HIGHPASS_ENABLED:
                audio = self._apply_highpass_filters(audio)
            
            # 2. Low-pass filtering (remove high frequencies)  
            if LOWPASS_ENABLED and LOWPASS_FREQ:
                audio = self._apply_lowpass_filter(audio)
            
            # 3. Heavy compression (reduce dynamic range)
            if COMPRESSION_ENABLED and COMPRESSION_RATIO and COMPRESSION_RATIO > 1.0:
                audio = self._apply_compression(audio)
            
            # 4. Saturation (add harmonics)
            if SATURATION_ENABLED and SATURATION_AMOUNT and SATURATION_AMOUNT > 0:
                audio = self._apply_saturation(audio)
            
            # 5. Noise gate (remove background noise)
            if NOISE_GATE_ENABLED and NOISE_GATE_THRESHOLD:
                audio = self._apply_noise_gate(audio)
            
            # 6. Add transmission noise
            if NOISE_ENABLED and NOISE_AMPLITUDE and NOISE_AMPLITUDE > 0:
                audio = self._add_transmission_noise(audio)
            
            # 7. Final loudness normalization
            if LOUDNORM_ENABLED:
                audio = self._apply_loudness_normalization(audio)
            
            # 8. Export final file
            final_path = OUTPUT_DIR / FINAL_FILENAME
            audio.export(final_path, format=AUDIO_FORMAT)
            
            # Log effects summary
            final_duration = len(audio) / 1000
            file_size = final_path.stat().st_size / 1024
            final_peak = audio.max_dBFS
            
            logger.info("Heavy compression radio effects applied:")
            if HIGHPASS_ENABLED:
                logger.info(f"  High-pass: {HIGHPASS_FREQ}Hz (corta graves)")
            if LOWPASS_ENABLED and LOWPASS_FREQ:
                logger.info(f"  Low-pass: {LOWPASS_FREQ}Hz (corta agudos)")
            if COMPRESSION_ENABLED and COMPRESSION_RATIO and COMPRESSION_RATIO > 1.0:
                logger.info(f"  Heavy compression: {COMPRESSION_RATIO}:1 (volume uniforme)")
            if SATURATION_ENABLED and SATURATION_AMOUNT and SATURATION_AMOUNT > 0:
                logger.info(f"  Saturation: {SATURATION_AMOUNT*100:.0f}% (distorção)")
            if NOISE_ENABLED and NOISE_AMPLITUDE and NOISE_AMPLITUDE > 0:
                logger.info(f"  Radio noise: {NOISE_AMPLITUDE*100:.0f}% (chiado reduzido)")
            if LOUDNORM_ENABLED:
                logger.info(f"  Volume: {TARGET_LUFS} LUFS (alto)")
            logger.info(f"  Final: {final_duration:.1f}s, {file_size:.1f} KB, peak {final_peak:.1f} dBFS")
            logger.info(f"  Output: {final_path}")
            
            return final_path
            
        except Exception as e:
            logger.error(f"Error applying radio effects: {e}")
            raise RuntimeError(f"Radio effects failed: {e}")
    
    def _apply_highpass_filters(self, audio: AudioSegment) -> AudioSegment:
        """Apply high-pass filters to cut low frequencies (bass)"""
        logger.debug(f"Cutting bass frequencies below {HIGHPASS_FREQ}Hz")
        
        # Apply first filter
        if HIGHPASS_SLOPE_1 > 0:
            num_filters_1 = max(1, HIGHPASS_SLOPE_1 // 6)  # Each filter ≈ 6dB/octave
            for i in range(num_filters_1):
                audio = audio.high_pass_filter(HIGHPASS_FREQ)
            if LOG_AUDIO_INFO:
                logger.debug(f"  Applied {num_filters_1} filters for bass cut")
        
        # Apply second filter
        if HIGHPASS_SLOPE_2 > 0:
            num_filters_2 = max(1, HIGHPASS_SLOPE_2 // 6)
            for i in range(num_filters_2):
                audio = audio.high_pass_filter(HIGHPASS_FREQ)
            if LOG_AUDIO_INFO:
                logger.debug(f"  Applied {num_filters_2} additional bass cut filters")
        
        return audio
    
    def _apply_lowpass_filter(self, audio: AudioSegment) -> AudioSegment:
        """Apply low-pass filter to cut high frequencies (treble)"""
        logger.debug(f"Cutting treble frequencies above {LOWPASS_FREQ}Hz")
        
        num_filters = max(1, LOWPASS_SLOPE // 6)  # Each filter ≈ 6dB/octave
        for i in range(num_filters):
            audio = audio.low_pass_filter(LOWPASS_FREQ)
        
        if LOG_AUDIO_INFO:
            logger.debug(f"  Applied {num_filters} treble cut filters")
        
        return audio
    
    def _apply_compression(self, audio: AudioSegment) -> AudioSegment:
        """Apply heavy compression to make volume more uniform"""
        logger.debug(f"Applying heavy compression: {COMPRESSION_RATIO}:1")
        
        # Heavy compression simulation
        current_peak = audio.max_dBFS
        
        if current_peak > COMPRESSION_THRESHOLD:
            # Calculate heavy gain reduction
            overage = current_peak - COMPRESSION_THRESHOLD
            gain_reduction = overage * (1 - (1 / COMPRESSION_RATIO))
            
            # Apply gain reduction
            audio = audio - gain_reduction
            
            if LOG_AUDIO_INFO:
                logger.debug(f"  Heavy compression reduced gain by {gain_reduction:.1f}dB")
        
        return audio
    
    def _apply_saturation(self, audio: AudioSegment) -> AudioSegment:
        """Apply saturation for radio transmission character"""
        logger.debug(f"Adding radio distortion: {SATURATION_AMOUNT*100:.0f}%")
        
        try:
            # Increase gain to push into saturation range
            saturation_gain = SATURATION_AMOUNT * 12  # 0.20 = ~2.4dB gain
            saturated = audio + saturation_gain
            
            # Apply soft limiting to create harmonic distortion
            max_allowed = -3.0  # Soft ceiling
            if saturated.max_dBFS > max_allowed:
                over_limit = saturated.max_dBFS - max_allowed
                saturated = saturated - over_limit
            
            # Blend original and saturated
            blend_ratio = SATURATION_AMOUNT
            audio = audio.overlay(saturated - saturated.max_dBFS + audio.max_dBFS, 
                                position=0, loop=False, times=1, gain_during_overlay=-20*math.log10(1-blend_ratio))
            
            if LOG_AUDIO_INFO:
                logger.debug(f"  Applied {SATURATION_AMOUNT*100:.0f}% radio distortion")
        
        except Exception as e:
            logger.warning(f"Saturation failed, skipping: {e}")
        
        return audio
    
    def _apply_noise_gate(self, audio: AudioSegment) -> AudioSegment:
        """Apply noise gate to remove background noise during silence"""
        logger.debug(f"Applying noise gate at {NOISE_GATE_THRESHOLD}dB")
        
        try:
            # Find RMS level
            current_rms = audio.dBFS
            
            if current_rms < NOISE_GATE_THRESHOLD:
                # Apply gate reduction
                gate_reduction = min(-12, NOISE_GATE_THRESHOLD - current_rms)
                audio = audio + gate_reduction
                
                if LOG_AUDIO_INFO:
                    logger.debug(f"  Applied gate reduction: {gate_reduction:.1f}dB")
        
        except Exception as e:
            logger.warning(f"Noise gate failed, skipping: {e}")
        
        return audio
    
    def _add_transmission_noise(self, audio: AudioSegment) -> AudioSegment:
        """Add white noise to simulate radio static (reduced amount)"""
        logger.debug(f"Adding reduced radio static: {NOISE_AMPLITUDE*100:.0f}%")
        
        try:
            # Generate white noise matching audio duration
            noise = WhiteNoise().to_audio_segment(duration=len(audio))
            
            # Set noise level (reduced by 10% from original 20%)
            noise_dbfs = 20 * math.log10(NOISE_AMPLITUDE) if NOISE_AMPLITUDE > 0 else -60
            noise = noise + noise_dbfs
            
            # Apply mix ratio
            noise_weighted = noise + (20 * math.log10(NOISE_MIX_RATIO))
            
            # Mix with original audio
            audio = audio.overlay(noise_weighted)
            
            if LOG_AUDIO_INFO:
                logger.debug(f"  Mixed {NOISE_MIX_RATIO*100:.1f}% reduced radio static")
        
        except Exception as e:
            logger.warning(f"Transmission noise failed, skipping: {e}")
        
        return audio
    
    def _apply_loudness_normalization(self, audio: AudioSegment) -> AudioSegment:
        """Apply final loudness normalization to target volume"""
        logger.debug(f"Setting final volume to {TARGET_LUFS} LUFS (high volume)")
        
        # 1. Peak limiting
        current_peak = audio.max_dBFS
        if current_peak > TARGET_PEAK:
            peak_reduction = TARGET_PEAK - current_peak
            audio = audio + peak_reduction
            if LOG_AUDIO_INFO:
                logger.debug(f"  Peak limited: {peak_reduction:.1f} dB")
        
        # 2. Loudness normalization (simplified LUFS approximation)
        target_dbfs = TARGET_LUFS + 14  # Rough LUFS to dBFS conversion
        current_rms = audio.dBFS
        
        if abs(current_rms) > 60:  # Avoid normalizing near-silence
            loudness_gain = target_dbfs - current_rms
            # Limit gain to prevent excessive amplification
            loudness_gain = max(min(loudness_gain, 12), -12)
            audio = audio + loudness_gain
            if LOG_AUDIO_INFO:
                logger.debug(f"  Volume boost: {loudness_gain:.1f} dB")
        
        # 3. Final safety limiting
        final_peak = audio.max_dBFS
        if final_peak > -1.0:
            safety_limit = -1.0 - final_peak
            audio = audio + safety_limit
            if LOG_AUDIO_INFO:
                logger.debug(f"  Safety limit: {safety_limit:.1f} dB")
        
        return audio
    
    def _cleanup_individual_files(self, audio_files: dict):
        """Automatically cleanup individual audio files after processing"""
        logger.info("Starting automatic cleanup of individual audio files")
        
        cleaned_count = 0
        for voice_type, file_path in audio_files.items():
            try:
                if file_path and file_path.exists():
                    file_path.unlink()
                    logger.debug(f"Removed individual file: {file_path.name}")
                    cleaned_count += 1
            except Exception as e:
                logger.warning(f"Error removing {voice_type} file: {e}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned {cleaned_count} individual audio files")
        else:
            logger.debug("No individual files to clean")
        
        # Also clean any temp directories in output/
        try:
            temp_dir = OUTPUT_DIR / "temp"
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.debug("Removed output/temp directory")
        except Exception as e:
            logger.warning(f"Error removing temp directory: {e}")
    
    def _show_processing_summary(self, result: dict, simbrief_data: dict):
        """Show processing summary information"""
        final_file = result["final_file"]
        
        if final_file and final_file.exists():
            # Get file info
            file_size = final_file.stat().st_size / 1024
            
            # Get audio info
            try:
                audio = AudioSegment.from_wav(final_file)
                duration = len(audio) / 1000
                duration_formatted = f"{int(duration//60):02d}:{int(duration%60):02d}"
                final_peak = audio.max_dBFS
            except:
                duration = 0
                duration_formatted = "00:00"
                final_peak = 0
            
            logger.info("=" * 60)
            logger.info("HEAVY COMPRESSION AVIATION RADIO ANNOUNCEMENT")
            logger.info("=" * 60)
            logger.info(f"Airline: {simbrief_data.get('airline_name', 'Unknown')}")
            logger.info(f"Flight: {simbrief_data.get('flight_number', 'Unknown')}")
            logger.info(f"Destination: {simbrief_data.get('dest_city', 'Unknown')}")
            logger.info("-" * 30)
            logger.info(f"Voice types: {len(result['individual_files'])}")
            logger.info(f"Duration: {duration_formatted} ({duration:.1f}s)")
            logger.info(f"File size: {file_size:.1f} KB")
            logger.info(f"Peak level: {final_peak:.1f} dBFS")
            
            # Radio effects summary
            if result['cabin_effects_applied']:
                logger.info("-" * 30)
                logger.info("HEAVY COMPRESSION EFFECTS APPLIED:")
                logger.info(f"  🔽 Bass cut: {HIGHPASS_FREQ}Hz (remove low frequencies)")
                logger.info(f"  🔽 Treble cut: {LOWPASS_FREQ}Hz (remove high frequencies)")
                logger.info(f"  🔧 Heavy compression: {COMPRESSION_RATIO}:1 (uniform volume)")
                logger.info(f"  🎛️ Radio distortion: {SATURATION_AMOUNT*100:.0f}%")
                logger.info(f"  📻 Static noise: {NOISE_AMPLITUDE*100:.0f}% (reduced)")
                logger.info(f"  🔊 Final volume: {TARGET_LUFS} LUFS (high)")
            else:
                logger.info("Radio effects: DISABLED (clean audio)")
            
            logger.info("-" * 30)
            logger.info(f"Final file: {final_file.name}")
            logger.info("=" * 60)

# Main function for external use
def process_announcement(audio_files: dict, simbrief_data: dict) -> dict:
    """
    Process boarding announcement with heavy compression radio effects
    
    Args:
        audio_files: Individual voice type audio files
        simbrief_data: Flight data
        
    Returns:
        dict: Processing results
    """
    processor = PostProcessor()
    return processor.process_announcement(audio_files, simbrief_data)

# Test function when run directly
if __name__ == "__main__":
    import sys
    
    print("🧪 Testing Post-Processor with Heavy Compression Effects...")
    
    # Show current configuration
    print("\n📻 HEAVY COMPRESSION CONFIGURATION:")
    print("=" * 50)
    print(f"Radio effects: {'ON' if APPLY_CABIN_EFFECTS else 'OFF'}")
    print(f"Bass cut: {HIGHPASS_FREQ}Hz (removes low frequencies)")
    print(f"Treble cut: {LOWPASS_FREQ}Hz (removes high frequencies)")
    print(f"Heavy compression: {COMPRESSION_RATIO}:1 (makes volume uniform)")
    print(f"Radio distortion: {SATURATION_AMOUNT*100:.0f}%")
    print(f"Static noise: {NOISE_AMPLITUDE*100:.0f}% (reduced from 20%)")
    print(f"Final volume: {TARGET_LUFS} LUFS (high volume)")
    
    # Mock data for testing
    mock_audio_files = {
        "english": Path("output/english.wav"),
        "native": Path("output/native.wav")
    }
    
    mock_simbrief = {
        "icao": "THA",
        "airline_name": "Thai Airways",
        "flight_number": "200",
        "dest_city": "Bangkok"
    }
    
    try:
        print(f"\n🎬 Processing announcement with heavy compression...")
        
        # Check if test files exist
        existing_files = {k: v for k, v in mock_audio_files.items() if v.exists()}
        
        if not existing_files:
            print("❌ No test audio files found in output/")
            print("💡 Generate audio files first with TTS system")
            sys.exit(1)
        
        result = process_announcement(existing_files, mock_simbrief)
        
        if result["success"]:
            print("✅ HEAVY COMPRESSION PROCESSING COMPLETED!")
            print(f"📁 Final file: {result['final_file']}")
            print(f"📻 Heavy compression effects: Applied")
            if AUTO_CLEANUP_INDIVIDUAL:
                print("🧹 Individual files automatically cleaned")
        else:
            print("❌ Processing failed")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        logger.exception("Post-processor heavy compression test failed")
        sys.exit(1)