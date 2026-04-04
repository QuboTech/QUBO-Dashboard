"""
varredura_inteligente.py - Sistema de atualização rápida
Só atualiza preços e adiciona produtos novos (não reprocessa tudo)
"""
import logging
from typing import List, Dict, Tuple
from pathlib import Path
from models import Produto, MudancaPreco, ArquivoProcessado
from data_manager import DataManager
from pdf_processor import PDFProcessor
from comparador import ComparadorInteligente

logger = logging.getLogger(__name__)

class VarreduraInteligente:
    """Varredura inteligente que só atualiza o necessário"""
    
    def __init__(self):
        self.data_manager = DataManager()
        self.pdf_processor = PDFProcessor()
        self.comparador = ComparadorInteligente(self.data_manager.df_produtos)
    
    def varredura_completa_primeira_vez(self, pasta: str) -> Dict:
        """
        Primeira varredura - Processa tudo
        Use quando ainda não tem dados
        """
        logger.info("🔍 VARREDURA COMPLETA (Primeira vez)")
        logger.info("   Isso vai demorar... mas só precisa fazer uma vez!")
        
        pdfs = self.pdf_processor.listar_pdfs_em_pasta(pasta)
        
        total_produtos = 0
        arquivos_processados = 0
        
        for i, pdf_path in enumerate(pdfs, 1):
            logger.info(f"\n[{i}/{len(pdfs)}] Processando: {pdf_path.name}")
            
            if self.data_manager.arquivo_ja_processado(str(pdf_path)):
                logger.info("   ⏭️  Já processado, pulando...")
                continue
            
            produtos, arquivo = self.pdf_processor.processar_arquivo(
                str(pdf_path),
                pdf_path.parent.name
            )
            
            if produtos:
                self.data_manager.adicionar_produtos(produtos)
                self.data_manager.registrar_arquivo_processado(arquivo)
                self.data_manager.salvar_excel()
                
                total_produtos += len(produtos)
                arquivos_processados += 1
                
                logger.info(f"   ✅ {len(produtos)} produtos extraídos")
        
        return {
            'total_produtos': total_produtos,
            'arquivos_processados': arquivos_processados,
            'modo': 'completa'
        }
    
    def varredura_atualizacao_rapida(self, pasta: str) -> Dict:
        """
        Varredura rápida - Só atualiza preços e novos produtos
        
        Funcionamento:
        1. Verifica quais arquivos mudaram (hash MD5)
        2. Reprocessa APENAS esses arquivos
        3. Compara com dados existentes
        4. Atualiza apenas preços que mudaram
        5. Adiciona apenas produtos novos
        
        MUITO MAIS RÁPIDO! ⚡
        """
        logger.info("\n" + "⚡ " + "=" * 68)
        logger.info("  VARREDURA RÁPIDA - Só Atualiza Mudanças")
        logger.info("=" * 70 + "\n")
        
        pdfs = self.pdf_processor.listar_pdfs_em_pasta(pasta)
        
        # Identifica arquivos que mudaram
        arquivos_modificados = []
        arquivos_novos = []
        
        logger.info("🔍 Verificando quais arquivos mudaram...")
        
        for pdf_path in pdfs:
            if not self.data_manager.arquivo_ja_processado(str(pdf_path)):
                arquivos_novos.append(pdf_path)
            elif self.data_manager.arquivo_foi_modificado(str(pdf_path)):
                arquivos_modificados.append(pdf_path)
        
        total_processar = len(arquivos_novos) + len(arquivos_modificados)
        
        if total_processar == 0:
            logger.info("\n✅ Nenhum arquivo novo ou modificado!")
            logger.info("   Sua base está atualizada! 🎉\n")
            return {
                'produtos_novos': 0,
                'produtos_atualizados': 0,
                'mudancas_preco': 0,
                'arquivos_processados': 0,
                'modo': 'rapida',
                'mensagem': 'Nada para atualizar'
            }
        
        logger.info(f"\n📊 Arquivos para processar:")
        logger.info(f"   🆕 Novos: {len(arquivos_novos)}")
        logger.info(f"   🔄 Modificados: {len(arquivos_modificados)}")
        logger.info(f"   ⏭️  Inalterados: {len(pdfs) - total_processar}")
        logger.info(f"\n⚡ Processando apenas {total_processar} arquivos...\n")
        
        total_produtos_novos = 0
        total_produtos_atualizados = 0
        total_mudancas_preco = 0
        
        # Processa arquivos novos
        for i, pdf_path in enumerate(arquivos_novos, 1):
            logger.info(f"\n🆕 [{i}/{len(arquivos_novos)}] NOVO: {pdf_path.name}")
            
            produtos, arquivo = self.pdf_processor.processar_arquivo(
                str(pdf_path),
                pdf_path.parent.name
            )
            
            if produtos:
                self.data_manager.adicionar_produtos(produtos)
                self.data_manager.registrar_arquivo_processado(arquivo)
                total_produtos_novos += len(produtos)
                logger.info(f"   ✅ {len(produtos)} produtos adicionados")
        
        # Processa arquivos modificados (aqui que a mágica acontece!)
        for i, pdf_path in enumerate(arquivos_modificados, 1):
            logger.info(f"\n🔄 [{i}/{len(arquivos_modificados)}] MODIFICADO: {pdf_path.name}")
            
            produtos, arquivo = self.pdf_processor.processar_arquivo(
                str(pdf_path),
                pdf_path.parent.name
            )
            
            if produtos:
                # Compara com dados existentes
                comparador = ComparadorInteligente(self.data_manager.df_produtos)
                novos, atualizados, mudancas = comparador.comparar_produtos(produtos)
                
                # Adiciona novos
                if novos:
                    self.data_manager.adicionar_produtos(novos)
                    total_produtos_novos += len(novos)
                    logger.info(f"   ✨ {len(novos)} produtos NOVOS")
                
                # Atualiza existentes (só preços!)
                if atualizados:
                    self.data_manager.atualizar_produtos(atualizados)
                    total_produtos_atualizados += len(atualizados)
                    logger.info(f"   🔄 {len(atualizados)} produtos ATUALIZADOS")
                
                # Registra mudanças de preço
                if mudancas:
                    self.data_manager.registrar_mudancas_preco(mudancas)
                    total_mudancas_preco += len(mudancas)
                    logger.info(f"   💰 {len(mudancas)} mudanças de PREÇO")
                    
                    # Mostra as mudanças mais significativas
                    mudancas_importantes = sorted(
                        mudancas, 
                        key=lambda m: abs(m.percentual_mudanca), 
                        reverse=True
                    )[:3]
                    
                    for m in mudancas_importantes:
                        simbolo = "📈" if m.percentual_mudanca > 0 else "📉"
                        logger.info(
                            f"      {simbolo} {m.codigo}: "
                            f"R$ {m.preco_antigo:.2f} → R$ {m.preco_novo:.2f} "
                            f"({m.percentual_mudanca:+.1f}%)"
                        )
                
                # Atualiza registro do arquivo
                self.data_manager.registrar_arquivo_processado(arquivo)
        
        # Salva tudo
        self.data_manager.remover_duplicatas()
        self.data_manager.salvar_excel()
        
        # Relatório final
        logger.info("\n" + "=" * 70)
        logger.info("📊 RESULTADO DA VARREDURA RÁPIDA")
        logger.info("=" * 70)
        logger.info(f"✨ Produtos novos: {total_produtos_novos}")
        logger.info(f"🔄 Produtos atualizados: {total_produtos_atualizados}")
        logger.info(f"💰 Mudanças de preço: {total_mudancas_preco}")
        logger.info(f"📁 Arquivos processados: {total_processar}")
        logger.info("=" * 70 + "\n")
        
        return {
            'produtos_novos': total_produtos_novos,
            'produtos_atualizados': total_produtos_atualizados,
            'mudancas_preco': total_mudancas_preco,
            'arquivos_processados': total_processar,
            'modo': 'rapida'
        }
    
    def decidir_modo_automatico(self, pasta: str) -> str:
        """
        Decide automaticamente qual modo usar
        
        Returns:
            'completa' ou 'rapida'
        """
        if self.data_manager.df_produtos.empty:
            return 'completa'
        
        if len(self.data_manager.cache_arquivos) == 0:
            return 'completa'
        
        return 'rapida'
    
    def executar_varredura_inteligente(self, pasta: str, forcar_completa: bool = False) -> Dict:
        """
        Executa varredura de forma inteligente
        
        Args:
            pasta: Pasta para varrer
            forcar_completa: Se True, força varredura completa
            
        Returns:
            Dicionário com resultados
        """
        if forcar_completa:
            return self.varredura_completa_primeira_vez(pasta)
        
        modo = self.decidir_modo_automatico(pasta)
        
        if modo == 'completa':
            logger.info("📋 Base vazia - Fazendo varredura completa...")
            return self.varredura_completa_primeira_vez(pasta)
        else:
            return self.varredura_atualizacao_rapida(pasta)