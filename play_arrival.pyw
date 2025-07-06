"""
play_arrival.pyw - WAIT & PLAY arrival_pa.wav TOTALMENTE SILENCIOSO

FUNCIONAMENTO:
1. Verifica se arrival_pa.wav existe
2. Se NÃO existe: AGUARDA até aparecer
3. Quando aparecer: REPRODUZ automaticamente
4. Tudo silencioso, sem janelas

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
AUDIO_FILE = "output\\arrival_pa.wav"
PLAYER_TIMEOUT = 300  # 5 minutos máximo para reprodução

# CONFIGURAÇÕES DE WAIT & PLAY
WAIT_FOR_FILE = True  # Aguardar arquivo aparecer
MAX_WAIT_TIME = 1800  # 30 minutos máximo de espera
CHECK_INTERVAL = 2    # Verificar a cada 2 segundos
MIN_FILE_SIZE = 1024  # Arquivo deve ter pelo menos 1KB (evitar arquivo vazio)

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

def check_player_exists() -> bool:
    """Verifica se player existe"""
    try:
        script_dir = Path(__file__).parent
        player_path = script_dir / PLAYER_EXE
        
        if not player_path.exists():
            silent_log(f"Player not found: {player_path}")
            return False
        
        silent_log("Player found")
        return True
        
    except:
        return False

def check_audio_exists() -> bool:
    """Verifica se áudio existe e tem tamanho adequado"""
    try:
        script_dir = Path(__file__).parent
        audio_path = script_dir / AUDIO_FILE
        
        if not audio_path.exists():
            return False
        
        # Verificar se arquivo tem tamanho mínimo (não está vazio/sendo criado)
        file_size = audio_path.stat().st_size
        if file_size < MIN_FILE_SIZE:
            silent_log(f"Audio file too small: {file_size} bytes")
            return False
        
        silent_log(f"Audio file found: {file_size} bytes")
        return True
        
    except:
        return False

def wait_for_audio_file() -> bool:
    """
    AGUARDA o arquivo arrival_pa.wav aparecer
    
    Returns:
        bool: True se arquivo apareceu, False se timeout
    """
    try:
        silent_log("Starting WAIT mode for arrival_pa.wav")
        
        start_time = time.time()
        elapsed_time = 0
        
        while elapsed_time < MAX_WAIT_TIME:
            # Verificar se arquivo existe
            if check_audio_exists():
                silent_log(f"Audio file appeared after {elapsed_time:.1f} seconds")
                
                # Aguardar mais um pouco para garantir que arquivo foi completamente escrito
                time.sleep(1)
                
                # Verificar novamente
                if check_audio_exists():
                    silent_log("Audio file confirmed ready")
                    return True
            
            # Aguardar antes da próxima verificação
            time.sleep(CHECK_INTERVAL)
            
            elapsed_time = time.time() - start_time
            
            # Log de progresso a cada 30 segundos
            if int(elapsed_time) % 30 == 0 and elapsed_time > 0:
                silent_log(f"Still waiting... {elapsed_time:.0f}s elapsed")
        
        silent_log(f"Wait timeout after {MAX_WAIT_TIME} seconds")
        return False
        
    except Exception as e:
        silent_log(f"Error during wait: {e}")
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
        
        # Aguardar reprodução (estimativa para arrival - geralmente mais curto)
        time.sleep(8)  # Arrival announcements são tipicamente mais curtos
        
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

def play_audio_with_fallbacks() -> bool:
    """Tenta reproduzir áudio com todos os métodos disponíveis"""
    try:
        silent_log("Starting audio playback")
        
        # Tentar reprodução com speech_pa.exe
        success = play_audio_silent()
        
        if success:
            silent_log("Arrival audio played successfully")
            return True
        
        # Fallback 1: Windows Media Player
        silent_log("Trying Windows Media Player fallback")
        success = play_audio_fallback()
        
        if success:
            silent_log("Arrival audio played via fallback")
            return True
        
        # Fallback 2: playsound
        silent_log("Trying simple fallback")
        success = play_audio_simple_fallback()
        
        if success:
            silent_log("Arrival audio played via simple fallback")
            return True
        
        silent_log("All playback methods failed")
        return False
        
    except Exception as e:
        silent_log(f"Error in playback: {e}")
        return False

# ============================================
# PROCESSO PRINCIPAL WAIT & PLAY
# ============================================

def silent_wait_and_play():
    """
    Processo principal: WAIT & PLAY
    
    1. Verifica se player existe
    2. Verifica se áudio existe
    3. Se não existe: AGUARDA até aparecer
    4. Quando aparecer: REPRODUZ
    """
    try:
        silent_log("Starting WAIT & PLAY arrival mode")
        
        # Step 1: Verificar se player existe
        if not check_player_exists():
            silent_log("Player not found - cannot continue")
            return False
        
        # Step 2: Verificar se áudio já existe
        if check_audio_exists():
            silent_log("Audio file already exists - playing immediately")
            return play_audio_with_fallbacks()
        
        # Step 3: Áudio não existe - AGUARDAR
        if WAIT_FOR_FILE:
            silent_log("Audio file not found - entering WAIT mode")
            
            # Aguardar arquivo aparecer
            audio_appeared = wait_for_audio_file()
            
            if not audio_appeared:
                silent_log("Audio file never appeared - giving up")
                return False
            
            # Step 4: Arquivo apareceu - REPRODUZIR
            silent_log("Audio file detected - starting playback")
            return play_audio_with_fallbacks()
        
        else:
            silent_log("Audio file not found and WAIT disabled")
            return False
        
    except Exception as e:
        silent_log(f"Critical error in wait & play: {e}")
        return False

# ============================================
# MAIN SILENCIOSO
# ============================================

def silent_main():
    """Main function COMPLETAMENTE SILENCIOSA"""
    try:
        silent_log("=== WAIT & PLAY ARRIVAL STARTED ===")
        
        # Executar wait & play
        success = silent_wait_and_play()
        
        if success:
            silent_log("=== WAIT & PLAY ARRIVAL COMPLETED SUCCESSFULLY ===")
        else:
            silent_log("=== WAIT & PLAY ARRIVAL FAILED ===")
        
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