"""
core/utils.py - Utilitários com circular import CORRIGIDO

CORREÇÃO CRÍTICA: Removidas importações que causam circular import
"""

import os
import logging
import string
import sys
from pathlib import Path
from datetime import datetime

# ============================================
# CONFIGURAÇÃO DE CAMINHOS
# ============================================

# Caminho raiz do projeto (pasta pai de core/) - DEFINIDO PRIMEIRO
ROOT = Path(__file__).resolve().parents[1]

# Diretórios importantes
CONFIG_DIR = ROOT / "core" / ".config"
ENV_FILE = CONFIG_DIR / "api_keys.env"
LOG_DIR = ROOT / "logs"
TEMP_DIR = ROOT / "core" / ".temp"

# Criar diretórios essenciais
for directory in [LOG_DIR, TEMP_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ============================================
# CONFIGURAÇÃO DE LOGGING MELHORADA
# ============================================

# Configurações de logging
LOG_LEVEL = logging.DEBUG  # Permitir todos os níveis
CONSOLE_LOG_LEVEL = logging.INFO  # Console menos verboso
FILE_LOG_LEVEL = logging.DEBUG  # Arquivo mais detalhado
LOG_FORMAT_CONSOLE = "%(levelname)s - %(message)s"
LOG_FORMAT_FILE = "[%(asctime)s] %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"

# Cores para console (apenas em sistemas que suportam)
COLORS = {
    'DEBUG': '\033[36m',    # Cyan
    'INFO': '\033[32m',     # Green
    'WARNING': '\033[33m',  # Yellow
    'ERROR': '\033[31m',    # Red
    'CRITICAL': '\033[35m', # Magenta
    'RESET': '\033[0m'      # Reset
}

class ColoredConsoleHandler(logging.StreamHandler):
    """Handler de console com cores para melhor visibilidade"""
    
    def emit(self, record):
        try:
            # Adicionar cor se suportado
            if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
                color = COLORS.get(record.levelname, '')
                reset = COLORS['RESET']
                record.levelname = f"{color}{record.levelname}{reset}"
            
            super().emit(record)
        except Exception:
            self.handleError(record)

def setup_logger():
    """
    Configura sistema de logging melhorado com console E arquivo
    """
    # Criar diretório de logs
    LOG_DIR.mkdir(exist_ok=True)
    
    # Configurar logger principal
    logger = logging.getLogger("boarding_pa")
    logger.setLevel(LOG_LEVEL)
    
    # Evitar duplicação de handlers
    if logger.handlers:
        logger.handlers.clear()
    
    # === HANDLER PARA ARQUIVO (DETALHADO) ===
    log_file = LOG_DIR / f"{datetime.utcnow().date()}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(FILE_LOG_LEVEL)
    
    file_formatter = logging.Formatter(LOG_FORMAT_FILE, "%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # === HANDLER PARA CONSOLE (VISUAL) ===
    console_handler = ColoredConsoleHandler()
    console_handler.setLevel(CONSOLE_LOG_LEVEL)
    
    console_formatter = logging.Formatter(LOG_FORMAT_CONSOLE)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger

# Logger global melhorado
logger = setup_logger()

# ============================================
# CARREGAMENTO DE VARIÁVEIS DE AMBIENTE
# ============================================

ENV = {}

def load_env_variables():
    """
    Carrega variáveis de ambiente do arquivo .env
    """
    global ENV
    ENV = {}
    
    if ENV_FILE.exists():
        try:
            for line in ENV_FILE.read_text().splitlines():
                line = line.strip()
                
                # Ignorar linhas vazias e comentários
                if not line or line.startswith("#"):
                    continue
                
                # Processar linha key=value
                if "=" in line:
                    key, value = line.split("=", 1)
                    ENV[key.strip()] = value.strip()
            
            logger.info(f"Loaded {len(ENV)} environment variables")
            
        except Exception as e:
            logger.error(f"Error loading environment file: {e}")
    else:
        logger.warning(f"Environment file not found: {ENV_FILE}")
        logger.info("Create it with your API keys!")

# Carregar variáveis na importação do módulo
load_env_variables()

# ============================================
# HELPERS PARA NÚMEROS E TEMPO
# ============================================

# Mapeamento de números para palavras
_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", 
    "seventeen", "eighteen", "nineteen"
)

_TENS = ("twenty", "thirty", "forty", "fifty")

def _num_word(n: int) -> str:
    """
    Converte número (0-59) para palavra em inglês
    
    Args:
        n: Número a converter
        
    Returns:
        str: Número por extenso
    """
    if n < 20:
        return _ONES[n]
    
    ten, one = divmod(n, 10)
    word = _TENS[ten - 2]
    
    if one:
        word += "-" + _ONES[one]
    
    return word

def spaced_digits(num: str) -> str:
    """
    Converte dígitos individuais para palavras separadas
    Ex: "200" → "two zero zero"
    
    Args:
        num: String numérica
        
    Returns:
        str: Dígitos falados separadamente
    """
    if not num:
        return ""
    
    # Converter cada dígito para palavra
    words = []
    for char in str(num):
        if char.isdigit():
            words.append(_ONES[int(char)])
    
    result = " ".join(words)
    logger.debug(f"Converted flight number: {num} -> {result}")
    return result

def seconds_to_words(seconds: int) -> str:
    """
    Converte duração em segundos para formato falado
    Ex: 7200 → "two hours", 5400 → "one hour and thirty minutes"
    
    Args:
        seconds: Duração em segundos
        
    Returns:
        str: Duração por extenso
    """
    if seconds <= 0:
        return "zero minutes"
    
    # Calcular horas e minutos
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    
    # Adicionar horas se houver
    if hours > 0:
        hour_word = _num_word(hours)
        if hours == 1:
            parts.append(f"{hour_word} hour")
        else:
            parts.append(f"{hour_word} hours")
    
    # Adicionar minutos se houver
    if minutes > 0:
        minute_word = _num_word(minutes)
        if minutes == 1:
            parts.append(f"{minute_word} minute")
        else:
            parts.append(f"{minute_word} minutes")
    
    # Juntar com "and" se houver ambos
    if len(parts) == 2:
        result = " and ".join(parts)
    elif len(parts) == 1:
        result = parts[0]
    else:
        result = "zero minutes"
    
    logger.debug(f"Converted duration: {seconds}s -> {result}")
    return result

def greeting(hour: int) -> str:
    """
    Determina saudação baseada na hora do dia
    
    Args:
        hour: Hora no formato 24h (0-23)
        
    Returns:
        str: Saudação apropriada
    """
    if 5 <= hour < 12:
        result = "Good morning"
    elif 12 <= hour < 18:
        result = "Good afternoon"
    else:
        result = "Good evening"
    
    logger.debug(f"Determined greeting for hour {hour}: {result}")
    return result

# ============================================
# CLIENTE OPENAI MELHORADO (SEM IMPORTS PROBLEMÁTICOS)
# ============================================

def get_openai_client():
    """
    Cria cliente OpenAI se API key estiver disponível
    
    Returns:
        OpenAI client ou None se não configurado
    """
    try:
        # Import local para evitar circular import
        from openai import OpenAI
        
        api_key = ENV.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OpenAI API key not found in environment")
            return None
        
        client = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized successfully")
        return client
        
    except ImportError:
        logger.error("OpenAI library not installed")
        return None
    except Exception as e:
        logger.error(f"Error initializing OpenAI client: {e}")
        logger.exception("OpenAI client initialization failed")
        return None

# ============================================
# FUNÇÕES DE LOGGING ESPECIALIZADAS
# ============================================

def log_step_start(step_name: str, details: str = ""):
    """Log início de step principal"""
    logger.info(f"=" * 50)
    logger.info(f"STARTING: {step_name}")
    if details:
        logger.info(f"Details: {details}")
    logger.info(f"=" * 50)

def log_step_complete(step_name: str, result: str = ""):
    """Log conclusão de step principal"""
    logger.info(f"COMPLETED: {step_name}")
    if result:
        logger.info(f"Result: {result}")

def log_step_error(step_name: str, error: Exception):
    """Log erro em step principal"""
    logger.error(f"FAILED: {step_name}")
    logger.error(f"Error: {str(error)}")
    logger.exception(f"Stack trace for {step_name}")

def log_api_call(api_name: str, endpoint: str, status: str = "starting"):
    """Log chamadas de API"""
    if status == "starting":
        logger.debug(f"API CALL: {api_name} -> {endpoint}")
    elif status == "success":
        logger.info(f"API SUCCESS: {api_name}")
    elif status == "error":
        logger.error(f"API ERROR: {api_name} -> {endpoint}")

def log_file_operation(operation: str, file_path: Path, details: str = ""):
    """Log operações de arquivo"""
    logger.debug(f"FILE {operation.upper()}: {file_path}")
    if details:
        logger.debug(f"  Details: {details}")

# ============================================
# UTILITÁRIOS DE LIMPEZA MELHORADOS
# ============================================

def clear_logs():
    """
    Limpa arquivo de logs do dia atual
    Usado para começar execução com logs limpos
    """
    try:
        today_log = LOG_DIR / f"{datetime.utcnow().date()}.log"
        if today_log.exists():
            today_log.write_text("", encoding="utf-8")
            logger.info("Logs cleared for new execution")
    except Exception as e:
        logger.warning(f"Error clearing logs: {e}")

def clear_temp_files(silent: bool = True):
    """
    Remove TODA a pasta .temp e recria vazia
    
    Args:
        silent: Se True, não loga operações de limpeza
        
    Returns:
        int: Número de arquivos removidos
    """
    cleaned_count = 0
    
    try:
        # Remover pasta .temp completamente se existir
        if TEMP_DIR.exists():
            import shutil
            
            # Contar arquivos antes de remover
            for temp_file in TEMP_DIR.rglob("*"):
                if temp_file.is_file():
                    cleaned_count += 1
            
            # Remover toda a pasta
            shutil.rmtree(TEMP_DIR)
            
            if not silent and cleaned_count > 0:
                logger.info(f"Cleaned {cleaned_count} temporary files")
        
        # Recriar pasta vazia
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        
    except Exception as e:
        if not silent:
            logger.warning(f"Error during temp cleanup: {e}")
            logger.exception("Temp cleanup error details")
    
    return cleaned_count

def show_env_status():
    """
    Mostra status das variáveis de ambiente carregadas
    """
    print("\n" + "="*50)
    print("🔑 ENVIRONMENT VARIABLES STATUS")
    print("="*50)
    
    required_vars = [
        "OPENAI_API_KEY",
        "ELEVEN_API_KEY", 
        "GOOGLE_TTS_API",
        "SIMBRIEF_USER"
    ]
    
    for var in required_vars:
        if var in ENV and ENV[var]:
            # Mostrar apenas primeiros/últimos caracteres da chave
            value = ENV[var]
            if len(value) > 10:
                masked = f"{value[:4]}...{value[-4:]}"
            else:
                masked = "***"
            print(f"✅ {var}: {masked}")
        else:
            print(f"❌ {var}: Not set")
    
    print("="*50)

# ============================================
# INFORMAÇÕES DO PROJETO
# ============================================

def get_project_info():
    """
    Retorna informações básicas do projeto
    """
    return {
        "name": "Boarding PA Generator",
        "root_path": str(ROOT),
        "config_path": str(CONFIG_DIR),
        "log_path": str(LOG_DIR),
        "env_variables_loaded": len(ENV),
        "has_openai": bool(ENV.get("OPENAI_API_KEY")),
        "has_eleven_labs": bool(ENV.get("ELEVEN_API_KEY")),
        "has_google_tts": bool(ENV.get("GOOGLE_TTS_API")),
        "default_simbrief_user": ENV.get("SIMBRIEF_USER", "Not set")
    }

# ============================================
# TESTE RÁPIDO
# ============================================

if __name__ == "__main__":
    print("🧪 Testing fixed utils.py (no circular import)...")
    
    # Testar logging melhorado
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.warning("This is a WARNING message") 
    logger.error("This is an ERROR message")
    
    # Testar variáveis de ambiente
    show_env_status()
    
    # Testar conversões
    print(f"\n🔢 Number conversions:")
    print(f"spaced_digits('200'): '{spaced_digits('200')}'")
    print(f"seconds_to_words(7200): '{seconds_to_words(7200)}'")
    print(f"seconds_to_words(5400): '{seconds_to_words(5400)}'")
    print(f"greeting(8): '{greeting(8)}'")
    print(f"greeting(14): '{greeting(14)}'")
    print(f"greeting(20): '{greeting(20)}'")
    
    # Testar OpenAI
    client = get_openai_client()
    print(f"\n🤖 OpenAI client: {'✅ Available' if client else '❌ Not available'}")
    
    # Informações do projeto
    info = get_project_info()
    print(f"\n📁 Project info:")
    for key, value in info.items():
        print(f"  {key}: {value}")
    
    print("\n✅ Fixed utils test completed - no circular import!")