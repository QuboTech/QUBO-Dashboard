"""
pdf_processor.py - Processador inteligente de PDFs em lotes
ATUALIZADO: Usa MultiExtractor ao invés de GroqExtractor puro
"""
import pypdf
import os
import time
import logging
from typing import List, Optional
from pathlib import Path
from config import Config
from models import Produto, ArquivoProcessado

# ============================================================
# TROCA PRINCIPAL: MultiExtractor no lugar do GroqExtractor
# ============================================================
try:
    from multi_extractor import MultiExtractor as Extractor
    _USANDO_MULTI = True
except ImportError:
    from groq_extractor import GroqExtractor as Extractor
    _USANDO_MULTI = False

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Processador de arquivos PDF"""
    
    def __init__(self):
        self.extrator = Extractor()
        if _USANDO_MULTI:
            logger.info("🚀 Usando MultiExtractor (Groq + Mistral)")
        else:
            logger.info("⚠️  Usando GroqExtractor legado (instale multi_extractor.py para melhor performance)")
    
    def processar_arquivo(
        self, 
        caminho: str, 
        fornecedor: Optional[str] = None
    ) -> tuple[List[Produto], ArquivoProcessado]:
        """
        Processa um arquivo PDF completo
        
        Args:
            caminho: Caminho do arquivo PDF
            fornecedor: Nome do fornecedor (opcional)
            
        Returns:
            Tupla com (lista de produtos, info do arquivo processado)
        """
        caminho_path = Path(caminho)
        
        if not caminho_path.exists():
            logger.error(f"Arquivo não encontrado: {caminho}")
            return [], None
        
        logger.info("=" * 70)
        logger.info(f"📄 PROCESSANDO: {caminho_path.name}")
        logger.info("=" * 70)
        
        try:
            # Calcula hash do arquivo
            hash_arquivo = ArquivoProcessado.calcular_hash(caminho)
            
            # Lê informações do PDF
            leitor = pypdf.PdfReader(caminho)
            total_paginas = len(leitor.pages)
            
            logger.info(f"   Total de páginas: {total_paginas}")
            logger.info(f"   Processando em lotes de {Config.PAGINAS_POR_LOTE} páginas...")
            
            produtos_totais = []
            
            # Processa em lotes
            for inicio in range(0, total_paginas, Config.PAGINAS_POR_LOTE):
                fim = min(inicio + Config.PAGINAS_POR_LOTE, total_paginas)
                
                logger.info(f"\n   📖 Lote: Páginas {inicio + 1} a {fim}")
                
                # Cria PDF temporário do lote
                caminho_lote = self._criar_lote_temp(leitor, inicio, fim)
                
                try:
                    # Extrai produtos do lote
                    produtos_lote, info = self.extrator.extrair_de_pdf(
                        caminho_lote, 
                        fornecedor or caminho_path.parent.name
                    )
                    
                    if produtos_lote:
                        # Adiciona informações de origem
                        for idx, produto in enumerate(produtos_lote):
                            produto.Arquivo_Origem = caminho_path.name
                            produto.Pasta_Origem = caminho_path.parent.name
                            produto.hash_arquivo = hash_arquivo
                            # Calcula página aproximada
                            try:
                                produto.pagina_origem = inicio + (idx // 10) + 1
                            except AttributeError:
                                pass  # Campo pode não existir no model antigo

                        produtos_totais.extend(produtos_lote)
                        
                        # Log com info do provider usado
                        provider_info = info.get('provider', '?') if isinstance(info, dict) else '?'
                        logger.info(f"      ✓ {len(produtos_lote)} produtos extraídos (via {provider_info})")
                    else:
                        logger.warning(f"      ⚠ Nenhum produto encontrado neste lote")
                    
                finally:
                    # Remove arquivo temporário
                    self._remover_temp(caminho_lote)
                
                # Pequena pausa entre lotes
                time.sleep(1)
            
            # Cria registro do arquivo processado
            arquivo_processado = ArquivoProcessado(
                nome=caminho_path.name,
                caminho=str(caminho_path),
                hash_md5=hash_arquivo,
                data_processamento=time.strftime("%Y-%m-%d %H:%M:%S"),
                total_produtos=len(produtos_totais),
                pasta_origem=caminho_path.parent.name
            )
            
            logger.info("\n" + "=" * 70)
            logger.info(f"✅ CONCLUÍDO: {len(produtos_totais)} produtos extraídos")
            
            # Mostra stats do multi-extractor se disponível
            if _USANDO_MULTI and hasattr(self.extrator, 'obter_estatisticas'):
                logger.info(self.extrator.obter_estatisticas())
            
            logger.info("=" * 70 + "\n")
            
            return produtos_totais, arquivo_processado
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar arquivo: {e}", exc_info=True)
            return [], None
    
    def _criar_lote_temp(
        self, 
        leitor: pypdf.PdfReader, 
        inicio: int, 
        fim: int
    ) -> str:
        """Cria arquivo PDF temporário com páginas específicas"""
        nome_temp = f"temp_lote_{int(time.time() * 1000)}.pdf"
        caminho_temp = Config.PASTA_DADOS / nome_temp
        
        escritor = pypdf.PdfWriter()
        for i in range(inicio, fim):
            escritor.add_page(leitor.pages[i])
        
        with open(caminho_temp, "wb") as f:
            escritor.write(f)
        
        return str(caminho_temp)
    
    def _remover_temp(self, caminho: str):
        """Remove arquivo temporário"""
        try:
            if os.path.exists(caminho):
                os.remove(caminho)
        except Exception as e:
            logger.warning(f"Não foi possível remover arquivo temporário: {e}")
    
    def verificar_arquivo_mudou(
        self, 
        caminho: str, 
        hash_anterior: str
    ) -> bool:
        """Verifica se arquivo foi modificado"""
        if not os.path.exists(caminho):
            return False
        
        hash_atual = ArquivoProcessado.calcular_hash(caminho)
        return hash_atual != hash_anterior
    
    def listar_pdfs_em_pasta(self, caminho_pasta: str) -> List[Path]:
        """Lista todos os PDFs em uma pasta e subpastas"""
        pasta = Path(caminho_pasta)
        
        if not pasta.exists():
            logger.error(f"Pasta não encontrada: {caminho_pasta}")
            return []
        
        pdfs = list(pasta.rglob("*.pdf"))
        logger.info(f"📁 Encontrados {len(pdfs)} arquivos PDF na pasta")
        
        return pdfs
