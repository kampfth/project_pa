"""
play_boarding.pyw - Reproduz boarding_pa.wav TOTALMENTE SILENCIOSO

Executa player\speech_pa.exe para reproduzir o áudio sem janelas
"""

import sys
import os
import subprocess
from pathlib import Path
import time

# ============================================
# CONFIGURAÇÃO SILENCIOSA TOTAL
# ============================================

# Força execução silenciosa
COMPLETELY_SILENT = True
NO_CONSOLE_OUTPUT = True
NO_POPUPS = True
NO_PLAYER_WINDOW = True

# Configurações do player
PLAYER_EXE = "player\\speech_pa.exe"
AUDIO_FILE = "output\\boarding_pa.wav"
PLAYER_TIMEOUT = 300  # 5 minutos máximo

# ============================================
# SUPRESSÃO DE OUTPUT
# ============================================

# Redirecionar TODOS os outputs para null
if COMPLETELY_SILENT:
    if sys.stdout is not None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is not None:
        sys.stderr = open(os.devnull, 'w')

# ============================================
# FUNÇÕES SILENCIOSAS
# ============================================

def silent_log(message: str):
    """Log silencioso (opcional - pode ser removido)"""
    try:
        # Apenas para debugging - pode comentar esta linha
        # print(f"[SILENT] {message}")
        pass
    except:
        pass

def check_files_exist() -> bool:
    """Verifica se player e áudio existem"""
    try:
        script_dir = Path(__file__).parent
        player_path = script_dir / PLAYER_EXE
        audio_path = script_dir / AUDIO_FILE
        
        if not player_path.exists():
            silent_log(f"Player not found: {player_path}")
            return False
        
        if not audio_path.exists():
            silent_log(f"Audio file not found: {audio_path}")
            return False
        
        silent_log("Player and audio file found")
        return True
        
    except:
        return False

def play_audio_silent() -> bool:
    """Reproduz áudio silenciosamente usando speech_pa.exe"""
    try:
        script_dir = Path(__file__).parent
        player_path = script_dir / PLAYER_EXE
        audio_path = script_dir / AUDIO_FILE
        
        # Comando para reprodução silenciosa
        # -nodisp: sem display de vídeo
        # -autoexit: sai automaticamente no final
        # -v quiet: output mínimo (se suportado)
        cmd = [
            str(player_path),
            "-nodisp",
            "-autoexit", 
            "-v", "quiet",
            str(audio_path)
        ]
        
        silent_log(f"Starting player: {player_path}")
        silent_log(f"Playing: {audio_path}")
        
        # Executar com supressão total de output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            cwd=str(script_dir)
        )
        
        # Aguardar conclusão com timeout
        try:
            process.wait(timeout=PLAYER_TIMEOUT)
            silent_log("Audio playback completed successfully")
            return True
        except subprocess.TimeoutExpired:
            silent_log("Audio playback timeout - terminating")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            return False
        
    except Exception as e:
        silent_log(f"Error playing audio: {e}")
        return False

def play_audio_fallback() -> bool:
    """Fallback usando Windows Media Player (COM)"""
    try:
        import win32com.client
        
        script_dir = Path(__file__).parent
        audio_path = script_dir / AUDIO_FILE
        
        # Usar Windows Media Player via COM
        mp = win32com.client.Dispatch("WMPlayer.OCX")
        mp.URL = str(audio_path.absolute())
        mp.controls.play()
        
        # Aguardar reprodução (estimativa)
        time.sleep(10)  # Ajustar conforme duração típica
        
        mp.controls.stop()
        mp = None
        
        silent_log("Fallback playback completed")
        return True
        
    except Exception as e:
        silent_log(f"Fallback playback failed: {e}")
        return False

def play_audio_simple_fallback() -> bool:
    """Fallback simples usando playsound"""
    try:
        import playsound
        
        script_dir = Path(__file__).parent
        audio_path = script_dir / AUDIO_FILE
        
        playsound.playsound(str(audio_path), block=True)
        
        silent_log("Simple fallback playback completed")
        return True
        
    except Exception as e:
        silent_log(f"Simple fallback failed: {e}")
        return False

# ============================================
# PROCESSO PRINCIPAL
# ============================================

def silent_play_boarding():
    """Processo principal de reprodução silenciosa"""
    try:
        silent_log("Starting silent boarding playback")
        
        # Verificar se arquivos existem
        if not check_files_exist():
            silent_log("Required files not found")
            return False
        
        # Tentar reprodução com speech_pa.exe
        success = play_audio_silent()
        
        if success:
            silent_log("Boarding audio played successfully")
            return True
        
        # Fallback 1: Windows Media Player
        silent_log("Trying Windows Media Player fallback")
        success = play_audio_fallback()
        
        if success:
            silent_log("Boarding audio played via fallback")
            return True
        
        # Fallback 2: playsound
        silent_log("Trying simple fallback")
        success = play_audio_simple_fallback()
        
        if success:
            silent_log("Boarding audio played via simple fallback")
            return True
        
        silent_log("All playback methods failed")
        return False
        
    except Exception as e:
        silent_log(f"Critical error in playback: {e}")
        return False

# ============================================
# MAIN SILENCIOSO
# ============================================

def silent_main():
    """Main function COMPLETAMENTE SILENCIOSA"""
    try:
        # Executar reprodução silenciosa
        success = silent_play_boarding()
        
        if success:
            silent_log("SILENT BOARDING PLAYBACK COMPLETED")
        else:
            silent_log("SILENT BOARDING PLAYBACK FAILED")
        
    except Exception as e:
        silent_log(f"Critical error in silent main: {e}")

# ============================================
# EXECUÇÃO SILENCIOSA
# ============================================

if __name__ == "__main__":
    try:
        silent_main()
    except:
        # Falha completamente silenciosa
        pass
    
    # Script termina silenciosamente sem pause