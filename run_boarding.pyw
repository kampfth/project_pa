"""
run_boarding.pyw - Script boarding TOTALMENTE SILENCIOSO

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

# ============================================
# CONFIGURAÇÃO SILENCIOSA TOTAL
# ============================================

# Força execução silenciosa
COMPLETELY_SILENT = True
NO_CONSOLE_OUTPUT = True
NO_POPUPS = True
NO_LOADING_ICONS = True

# Configurações específicas .pyw
CONTEXT = "boarding"
FINAL_AUDIO_NAME = "boarding_pa.wav"
TEMPLATE_NAME = "welcome"

# Cleanup settings
CLEANUP_INDIVIDUAL_FILES = True
CLEANUP_TEMP_FILES = True
AUTO_CLEANUP = True

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
from core.translation_handler import build_texts
from core.tts_manager import generate_audio_files
from core.post_processor import process_announcement

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
                "final_announcement.wav", "final_announcement_raw.wav"
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
        old_path = output_dir / "final_announcement.wav"
        new_path = output_dir / FINAL_AUDIO_NAME
        
        if old_path.exists():
            if new_path.exists():
                new_path.unlink()
            old_path.rename(new_path)
            silent_log(f"Audio renamed to {FINAL_AUDIO_NAME}")
            return new_path
        
        return None
    except:
        return None

# ============================================
# PROCESSO PRINCIPAL SILENCIOSO
# ============================================

def silent_boarding_process(username: str):
    """
    Processo de boarding COMPLETAMENTE SILENCIOSO
    
    Args:
        username: SimBrief username
    """
    try:
        silent_log(f"Starting silent boarding process for: {username}")
        
        # Step 1: SimBrief data
        try:
            handler = SimbriefHandler(username)
            simbrief_data = handler.fetch_flight_data()
            silent_log("SimBrief data fetched successfully")
        except Exception as e:
            silent_error("SimBrief fetch failed", e)
            return False
        
        # Step 2: Text generation
        try:
            texts = build_texts(simbrief_data)
            silent_log(f"Texts generated: {list(texts.keys())}")
        except Exception as e:
            silent_error("Text generation failed", e)
            return False
        
        # Step 3: TTS generation (silencioso)
        try:
            # Suprimir outputs do TTS
            audio_files = generate_audio_files(texts, simbrief_data, context=CONTEXT)
            silent_log(f"Audio files generated: {list(audio_files.keys())}")
        except Exception as e:
            silent_error("TTS generation failed", e)
            return False
        
        # Step 4: Post-processing (silencioso)
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
        
        # Step 5: Finalization
        try:
            final_audio = silent_rename_audio()
            if final_audio:
                silent_log(f"Final audio created: {final_audio.name}")
            
            if AUTO_CLEANUP:
                silent_cleanup()
            
            silent_log("Silent boarding process completed successfully")
            return True
            
        except Exception as e:
            silent_error("Finalization failed", e)
            return False
        
    except Exception as e:
        silent_error("Critical error in silent process", e)
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
        success = silent_boarding_process(username)
        
        if success:
            silent_log("SILENT BOARDING COMPLETED SUCCESSFULLY")
        else:
            silent_error("SILENT BOARDING FAILED")
        
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