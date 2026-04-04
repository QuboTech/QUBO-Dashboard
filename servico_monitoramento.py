"""
servico_monitoramento.py - Serviço que roda em background 24/7
Inicia automaticamente com o Windows
"""
import sys
import time
import logging
from pathlib import Path

# Adiciona pasta do projeto ao PATH
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from file_watcher import FileWatcher

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(Config.PASTA_DADOS / 'servico.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def executar_servico():
    """Executa o serviço de monitoramento"""
    logger.info("=" * 70)
    logger.info("🤖 SERVIÇO DE MONITORAMENTO INICIADO")
    logger.info("=" * 70)
    
    if not Config.PASTA_MONITORADA:
        logger.error("❌ Pasta não configurada!")
        logger.error("   Configure PASTA_MONITORADA no arquivo .env")
        return
    
    logger.info(f"📁 Monitorando: {Config.PASTA_MONITORADA}")
    logger.info("👀 Sistema ativo 24/7")
    logger.info("=" * 70)
    
    try:
        watcher = FileWatcher(Config.PASTA_MONITORADA)
        
        # Faz varredura inicial
        logger.info("\n🔍 Fazendo varredura inicial...")
        watcher.varredura_inicial()
        
        logger.info("\n✅ Varredura inicial concluída!")
        logger.info("👀 Monitoramento ativo. Pressione Ctrl+C para parar.\n")
        
        # Inicia monitoramento
        watcher.iniciar_monitoramento()
        
    except KeyboardInterrupt:
        logger.info("\n⏹️  Serviço encerrado pelo usuário")
    except Exception as e:
        logger.error(f"\n❌ Erro no serviço: {e}", exc_info=True)

if __name__ == "__main__":
    executar_servico()