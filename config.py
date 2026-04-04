"""
config.py - Configurações centralizadas do sistema
VERSÃO CORRIGIDA - Sem validação obrigatória Gemini
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()

class Config:
    """Configurações gerais do sistema"""
    
    # API (Gemini descontinuado, mantém dummy para compatibilidade)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "dummy")
    GEMINI_MODEL = "gemini-2.0-flash-lite-001"
    
    # Processamento
    PAGINAS_POR_LOTE = int(os.getenv("PAGINAS_POR_LOTE", 6))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", 10))
    QUOTA_WAIT_TIME = int(os.getenv("QUOTA_WAIT_TIME", 600))
    
    # Caminhos
    BASE_DIR = Path(__file__).parent
    PASTA_DADOS = BASE_DIR / "data"
    PASTA_MONITORADA = os.getenv("PASTA_MONITORADA", "")
    
    # Arquivos
    ARQUIVO_EXCEL = os.getenv("ARQUIVO_EXCEL", "RELATORIO_AUTOMATICO.xlsx")
    ARQUIVO_CACHE = os.getenv("ARQUIVO_CACHE", "cache_processados.json")
    ARQUIVO_HISTORICO = os.getenv("ARQUIVO_HISTORICO", "historico_precos.json")
    ARQUIVO_LOG = os.getenv("ARQUIVO_LOG", "sistema.log")
    
    # Monitoramento
    INTERVALO_VERIFICACAO = int(os.getenv("INTERVALO_VERIFICACAO", 60))
    
    # Colunas do Excel
    COLUNAS_PADRAO = [
        "fornecedor",
        "Pasta_Origem", 
        "codigo",
        "descricao",
        "preco_unitario",
        "qtd_caixa",
        "Arquivo_Origem",
        "data_processamento",
        "hash_arquivo"
    ]
    
    # Validação
    CAMPOS_OBRIGATORIOS = ["codigo", "descricao", "preco_unitario"]
    
    @classmethod
    def criar_diretorios(cls):
        """Cria diretórios necessários"""
        cls.PASTA_DADOS.mkdir(exist_ok=True)
    
    @classmethod
    def validar_config(cls):
        """Valida configurações essenciais"""
        # Não valida mais Gemini (descontinuado)
        # Apenas garante que diretórios existem
        cls.criar_diretorios()
        return True

# Inicialização
Config.criar_diretorios()
