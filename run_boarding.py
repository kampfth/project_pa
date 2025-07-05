"""
run_boarding.py - Main script for boarding announcement generation

Orchestrates the complete flow:
1. Fetch SimBrief flight data
2. Generate texts and translations
3. Synthesize TTS audio with proper context
4. Combine and finalize audio
5. Clean temporary files COMPLETELY
"""

import sys
import json
import glob
from pathlib import Path

# ============================================
# CONFIGURAÇÕES AJUSTÁVEIS
# ============================================

# Configurações de contexto
ANNOUNCEMENT_CONTEXT = "boarding"  # Context for TTS cache separation

# Configurações de limpeza
CLEANUP_INDIVIDUAL_FILES = True  # Remove individual audio files after combination
CLEANUP_TEMP_FILES = True  # Remove temp files during process
CLEANUP_OLD_LOGS = True  # Clear logs on startup

# Configurações de arquivo
FINAL_AUDIO_NAME = "boarding_pa.wav"  # Final audio filename
TEMPLATE_NAME = "welcome"  # Template to use from prompts/

# Configurações de interface
SHOW_STARTUP_INFO = True  # Show detailed startup screen
SHOW_ENV_STATUS = False  # Show environment status by default
CLEAR_SCREEN_ON_START = True  # Clear screen on startup

# Configurações de saída
SHOW_DETAILED_RESULTS = True  # Show detailed final results
SHOW_AUDIO_INFO = True  # Show duration/size info for final audio
PAUSE_BEFORE_EXIT = True  # Wait for Enter before exit

# ============================================
# IMPORTS
# ============================================

from core.utils import ENV, logger, clear_logs, clear_temp_files, show_env_status, get_project_info, ROOT
from core.simbrief_handler import generate as fetch_simbrief_data, SimbriefHandler
from core.translation_handler import build_texts

def show_startup_info():
    """Show startup information with improved visual design"""
    if not SHOW_STARTUP_INFO:
        return
    
    # Clear screen for clean interface
    if CLEAR_SCREEN_ON_START:
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
    
    print("╔" + "═"*70 + "╗")
    print("║" + " "*25 + "🎙️ SPEECH PA SYSTEM 🎙️" + " "*23 + "║")
    print("║" + " "*20 + "Boarding Announcement Generator" + " "*19 + "║") 
    print("╚" + "═"*70 + "╝")
    print()
    
    # Project info with better formatting
    info = get_project_info()
    
    print("📊 SYSTEM STATUS")
    print("─" * 50)
    
    # API Status with colored indicators
    apis = [
        ("OpenAI", info['has_openai']),
        ("ElevenLabs", info['has_eleven_labs']),
        ("Google TTS", info['has_google_tts'])
    ]
    
    for name, status in apis:
        indicator = "🟢" if status else "🔴"
        status_text = "Ready" if status else "Not configured"
        print(f"{indicator} {name:<12}: {status_text}")
    
    print()
    print(f"👤 SimBrief User: {info['default_simbrief_user'] or 'Not set'}")
    print(f"🔑 Environment vars: {info['env_variables_loaded']} loaded")
    print(f"🎯 Context: {ANNOUNCEMENT_CONTEXT}")
    print()
    print("═" * 50)

def complete_cleanup():
    """COMPLETE cleanup: Remove ALL temporary files and logs"""
    if not CLEANUP_TEMP_FILES:
        return
        
    logger.info("Starting complete boarding cleanup")
    
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
                "final_announcement_raw.wav"
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
    
    # 4. Remove temp directories and files
    try:
        temp_items = [
            ROOT / "output" / "temp",
            ROOT / "data" / "translation.txt"  # Translation report
        ]
        
        for temp_path in temp_items:
            if temp_path.exists():
                if temp_path.is_dir():
                    import shutil
                    shutil.rmtree(temp_path)
                else:
                    temp_path.unlink()
                logger.info(f"Removed {temp_path.name}")
    except Exception as e:
        logger.warning(f"Error removing temp items: {e}")
    
    # 5. Remove any leftover text files in root
    try:
        for txt_file in ROOT.glob("*.txt"):
            try:
                txt_file.unlink()
                logger.info(f"Removed root text file: {txt_file.name}")
            except:
                pass
    except Exception as e:
        logger.warning(f"Error cleaning root text files: {e}")
    
    logger.info("Complete boarding cleanup finished")

def rename_final_audio():
    """Rename final_announcement.wav to standardized name"""
    try:
        output_dir = ROOT / "output"
        old_path = output_dir / "final_announcement.wav"
        new_path = output_dir / FINAL_AUDIO_NAME
        
        if old_path.exists():
            # Remove existing file if it exists
            if new_path.exists():
                new_path.unlink()
            
            # Rename
            old_path.rename(new_path)
            logger.info(f"Renamed final_announcement.wav to {FINAL_AUDIO_NAME}")
            return new_path
        
        return None
    except Exception as e:
        logger.error(f"Error renaming final audio: {e}")
        return None

def run_simbrief_step(username: str) -> dict:
    """Step 1: Fetch SimBrief data"""
    print(f"\n🔍 Fetching SimBrief data for user: {username}")
    
    try:
        logger.info(f"Starting SimBrief data fetch for: {username}")
        
        # Use handler
        handler = SimbriefHandler(username)
        simbrief_data = handler.fetch_flight_data()
        
        # Show summary
        duration_hours = simbrief_data['duration_seconds'] // 3600
        duration_minutes = (simbrief_data['duration_seconds'] % 3600) // 60
        duration_short = f"{duration_hours}h{duration_minutes:02d}min"
        
        print("✅ Flight data downloaded and saved successfully")
        print(f"   {simbrief_data['airline_name']} ({simbrief_data['icao']}) - Flight {simbrief_data['flight_number']} → {simbrief_data['dest_city']} ({duration_short})")
        
        logger.info("SimBrief step completed successfully")
        return simbrief_data
        
    except Exception as e:
        print(f"❌ Error fetching flight data: {e}")
        logger.error(f"SimBrief step failed: {e}")
        raise

def run_translation_step(simbrief_data: dict) -> dict:
    """Step 2: Generate texts and translations"""
    print("\n🌍 Generating texts and translations")
    
    try:
        logger.info("Starting text generation and translation")
        
        texts = build_texts(simbrief_data)
        
        # Show generated languages
        languages = list(texts.keys())
        print(f"✅ Translation: {', '.join(languages)}")
        
        logger.info(f"Translation step completed. Languages: {languages}")
        return texts
        
    except Exception as e:
        print(f"❌ Error generating translations: {e}")
        logger.error(f"Translation step failed: {e}")
        raise

def run_tts_step(texts: dict, simbrief_data: dict) -> dict:
    """Step 3: Text-to-Speech synthesis with proper context"""
    print("\n🔊 Synthesizing voice audio")
    
    try:
        from core.tts_manager import generate_audio_files
        
        logger.info("Starting TTS audio generation")
        
        # Pass boarding context to prevent cache conflicts with arrival
        audio_files = generate_audio_files(texts, simbrief_data, context=ANNOUNCEMENT_CONTEXT)
        
        # Show generated voice types
        if audio_files:
            voice_types = list(audio_files.keys())
            print(f"✅ TTS: {', '.join(voice_types)}")
            logger.info(f"TTS step completed. Generated: {voice_types}")
        else:
            print("⚠️ No audio files generated")
            logger.warning("TTS step completed but no files generated")
        
        return audio_files
        
    except Exception as e:
        print(f"❌ Error generating TTS audio: {e}")
        logger.error(f"TTS step failed: {e}")
        # Don't raise - continue with empty audio_files for now
        return {}

def run_post_processing_step(audio_files: dict, simbrief_data: dict) -> Path:
    """Step 4: Post-processing and audio combination with cabin effects"""
    print("\n🎬 Processing and combining audio")
    
    try:
        from core.post_processor import process_announcement
        
        logger.info("Starting post-processing and audio combination")
        
        if not audio_files:
            print("⚠️ No audio files to process")
            logger.warning("Post-processing skipped - no audio files")
            return None
        
        # Process announcement with cabin effects
        result = process_announcement(audio_files, simbrief_data)
        
        if result["success"]:
            final_file = result["final_file"]
            effects_applied = "with cabin effects" if result["cabin_effects_applied"] else "without effects"
            
            print(f"✅ Post-processing: Final audio created {effects_applied}")
            print(f"   📁 {final_file.name}")
            
            logger.info(f"Post-processing completed successfully: {final_file}")
            return final_file
        else:
            print("❌ Post-processing failed")
            logger.error("Post-processing failed - no success flag")
            return None
        
    except Exception as e:
        print(f"❌ Error in post-processing: {e}")
        logger.error(f"Post-processing step failed: {e}")
        return None

def run_full_process(username: str):
    """Execute complete generation process"""
    try:
        logger.info(f"Starting full boarding process for user: {username}")
        
        # Step 1: SimBrief
        simbrief_data = run_simbrief_step(username)
        
        # Step 2: Translation
        texts = run_translation_step(simbrief_data)
        
        # Step 3: TTS with boarding context
        audio_files = run_tts_step(texts, simbrief_data)
        
        # Step 4: Post-processing
        final_audio = run_post_processing_step(audio_files, simbrief_data)
        
        # Step 5: RENAME and CLEANUP
        if final_audio:
            print("\n🧹 Cleaning up temporary files")
            
            # Rename final audio
            boarding_file = rename_final_audio()
            
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
                    
                    print("✅ Individual audio files cleaned")
                    
                except Exception as e:
                    logger.warning(f"Error cleaning individual files: {e}")
        
        # Final result
        if SHOW_DETAILED_RESULTS:
            print("\n🎉 PROCESS COMPLETED!")
            print("=" * 50)
            print(f"✈️ {simbrief_data['airline_name']} {simbrief_data['flight_number']} → {simbrief_data['dest_city']}")
            print(f"📄 Texts: {', '.join(texts.keys())}")
            print(f"🎯 Context: {ANNOUNCEMENT_CONTEXT}")
            
            if final_audio:
                # Show final audio info
                boarding_file = ROOT / "output" / FINAL_AUDIO_NAME
                if boarding_file.exists() and SHOW_AUDIO_INFO:
                    print(f"🎵 Final audio: {FINAL_AUDIO_NAME}")
                    
                    # Show audio info if available
                    try:
                        from pydub import AudioSegment
                        audio = AudioSegment.from_wav(boarding_file)
                        duration = len(audio) / 1000
                        size = boarding_file.stat().st_size / 1024
                        duration_formatted = f"{int(duration//60):02d}:{int(duration%60):02d}"
                        
                        print(f"   📏 Duration: {duration_formatted} • 📁 Size: {size:.1f} KB")
                    except:
                        pass
                else:
                    print(f"🎵 Final audio: {final_audio.name}")
            else:
                print("🎵 Final audio: Not generated")
            
            print("=" * 50)
        
        logger.info("Full boarding process completed successfully")
        
    except Exception as e:
        print(f"\n❌ PROCESS ERROR: {e}")
        logger.error(f"Full boarding process failed: {e}")
        raise

def main():
    """Main function"""
    try:
        # Show startup info
        show_startup_info()
        
        # Check environment variables if requested
        if "--env" in sys.argv or SHOW_ENV_STATUS:
            show_env_status()
            if "--env" in sys.argv:
                return
        
        # Get username
        if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
            username = sys.argv[1]
        else:
            username = ENV.get("SIMBRIEF_USER")
        
        if not username:
            print("\n❌ SimBrief username not provided!")
            print("💡 Options:")
            print("   • Pass as argument: python run_boarding.py <username>")
            print("   • Configure SIMBRIEF_USER in .env file")
            print("   • Use: python run_boarding.py --env to check API status")
            return
        
        # Initial cleanup (only temp files, not final outputs)
        if CLEANUP_TEMP_FILES:
            clear_temp_files(silent=True)
        
        # Execute main process
        print(f"\n🚀 STARTING GENERATION FOR: {username}")
        run_full_process(username)
        
        print("\n✅ Process completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⏹️ Process interrupted by user")
        logger.info("Process interrupted by user")
        
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        logger.exception("Unexpected error in main process")
        
    finally:
        # COMPLETE final cleanup
        print("\n🧹 Final cleanup...")
        complete_cleanup()
        
        if PAUSE_BEFORE_EXIT:
            print("\nPress Enter to exit...")
            input()

if __name__ == "__main__":
    main()