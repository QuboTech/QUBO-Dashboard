"""
file_watcher.py - Monitor automático de pasta com detecção de mudanças
"""
import time
import logging
from pathlib import Path
from typing import List, Callable, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from config import Config
from data_manager import DataManager
from pdf_processor import PDFProcessor
from comparador import ComparadorInteligente
from models import RelatorioProcessamento

logger = logging.getLogger(__name__)

class PDFHandler(FileSystemEventHandler):
    """Handler para eventos de arquivos PDF"""
    
    def __init__(self, callback: Callable):
        super().__init__()
        self.callback = callback
        self.arquivos_pendentes = set()
        self.ultimo_evento = {}
    
    def on_created(self, event: FileSystemEvent):
        """Quando arquivo é criado"""
        if not event.is_directory and event.src_path.endswith('.pdf'):
            logger.info(f"🆕 Novo arquivo detectado: {Path(event.src_path).name}")
            self._agendar_processamento(event.src_path)
    
    def on_modified(self, event: FileSystemEvent):
        """Quando arquivo é modificado"""
        if not event.is_directory and event.src_path.endswith('.pdf'):
            # Evita processar o mesmo arquivo múltiplas vezes em curto período
            agora = time.time()
            ultimo = self.ultimo_evento.get(event.src_path, 0)
            
            if agora - ultimo > 5:  # 5 segundos de cooldown
                logger.info(f"📝 Arquivo modificado: {Path(event.src_path).name}")
                self._agendar_processamento(event.src_path)
                self.ultimo_evento[event.src_path] = agora
    
    def _agendar_processamento(self, caminho: str):
        """Agenda arquivo para processamento"""
        self.arquivos_pendentes.add(caminho)
        # Aguarda um pouco para garantir que arquivo foi completamente salvo
        time.sleep(2)
        self.callback(caminho)
        self.arquivos_pendentes.discard(caminho)


class FileWatcher:
    """Monitor de pasta com processamento automático"""
    
    def __init__(self, pasta_monitorada: str = None):
        self.pasta_monitorada = pasta_monitorada or Config.PASTA_MONITORADA
        self.data_manager = DataManager()
        self.pdf_processor = PDFProcessor()
        self.observer = None
        self.ativo = False
        
        if not self.pasta_monitorada:
            raise ValueError("Pasta para monitorar não foi configurada")
        
        pasta_path = Path(self.pasta_monitorada)
        if not pasta_path.exists():
            raise FileNotFoundError(f"Pasta não encontrada: {self.pasta_monitorada}")
    
    def processar_arquivo_automatico(self, caminho: str):
        """
        Processa arquivo automaticamente quando detectada mudança
        
        Args:
            caminho: Caminho do arquivo a processar
        """
        logger.info("\n" + "🔄 " + "=" * 68)
        logger.info("PROCESSAMENTO AUTOMÁTICO INICIADO")
        logger.info("=" * 70)
        
        try:
            caminho_path = Path(caminho)
            
            # Verifica se precisa processar
            if self.data_manager.arquivo_ja_processado(caminho):
                if not self.data_manager.arquivo_foi_modificado(caminho):
                    logger.info(f"⏭️  Arquivo não foi modificado, pulando...")
                    return
                else:
                    logger.info(f"🔄 Arquivo foi modificado, reprocessando...")
            
            # Processa arquivo
            produtos, arquivo_processado = self.pdf_processor.processar_arquivo(
                caminho,
                fornecedor=caminho_path.parent.name
            )
            
            if not produtos:
                logger.warning("⚠️  Nenhum produto extraído")
                return
            
            # Compara com base existente
            comparador = ComparadorInteligente(self.data_manager.df_produtos)
            novos, atualizados, mudancas = comparador.comparar_produtos(produtos)
            
            # Atualiza base de dados
            if novos:
                self.data_manager.adicionar_produtos(novos)
            
            if atualizados:
                self.data_manager.atualizar_produtos(atualizados)
            
            if mudancas:
                self.data_manager.registrar_mudancas_preco(mudancas)
                self._exibir_mudancas_preco(mudancas)
            
            # Salva tudo
            self.data_manager.remover_duplicatas()
            self.data_manager.salvar_excel()
            
            # Registra arquivo como processado
            if arquivo_processado:
                self.data_manager.registrar_arquivo_processado(arquivo_processado)
            
            logger.info("\n✅ Processamento automático concluído com sucesso!\n")
            
        except Exception as e:
            logger.error(f"❌ Erro no processamento automático: {e}", exc_info=True)
    
    def _exibir_mudancas_preco(self, mudancas: List):
        """Exibe mudanças de preço de forma destacada"""
        if not mudancas:
            return
        
        logger.info("\n" + "💰 " + "=" * 68)
        logger.info("MUDANÇAS DE PREÇO DETECTADAS")
        logger.info("=" * 70)
        
        for m in mudancas[:10]:  # Mostra até 10 mudanças
            simbolo = "📈" if m.percentual_mudanca > 0 else "📉"
            logger.info(
                f"{simbolo} {m.codigo} - {m.descricao[:40]}\n"
                f"   R$ {m.preco_antigo:.2f} → R$ {m.preco_novo:.2f} "
                f"({m.percentual_mudanca:+.1f}%)"
            )
        
        if len(mudancas) > 10:
            logger.info(f"\n   ... e mais {len(mudancas) - 10} mudanças")
        
        logger.info("=" * 70 + "\n")
    
    def varredura_inicial(self) -> RelatorioProcessamento:
        """
        Faz varredura inicial da pasta
        
        Returns:
            Relatório do processamento
        """
        logger.info("\n" + "🔍 " + "=" * 68)
        logger.info("VARREDURA INICIAL DA PASTA")
        logger.info("=" * 70)
        
        relatorio = RelatorioProcessamento(
            data_inicio=time.strftime("%Y-%m-%d %H:%M:%S")
        )
        
        try:
            # Lista todos os PDFs
            pdfs = self.pdf_processor.listar_pdfs_em_pasta(self.pasta_monitorada)
            
            if not pdfs:
                logger.warning("⚠️  Nenhum arquivo PDF encontrado na pasta")
                relatorio.finalizar()
                return relatorio
            
            logger.info(f"\n📋 Encontrados {len(pdfs)} arquivos PDF")
            logger.info("Verificando quais precisam ser processados...\n")
            
            # Identifica arquivos novos ou modificados
            arquivos_processar = []
            
            for pdf_path in pdfs:
                if not self.data_manager.arquivo_ja_processado(str(pdf_path)):
                    arquivos_processar.append((pdf_path, "NOVO"))
                    relatorio.arquivos_novos += 1
                elif self.data_manager.arquivo_foi_modificado(str(pdf_path)):
                    arquivos_processar.append((pdf_path, "MODIFICADO"))
                    relatorio.arquivos_atualizados += 1
            
            if not arquivos_processar:
                logger.info("✅ Todos os arquivos já estão processados e atualizados!")
                relatorio.finalizar()
                return relatorio
            
            logger.info(f"🔄 {len(arquivos_processar)} arquivos precisam ser processados\n")
            
            # Processa cada arquivo
            for i, (pdf_path, status) in enumerate(arquivos_processar, 1):
                logger.info(f"\n[{i}/{len(arquivos_processar)}] {status}: {pdf_path.name}")
                
                try:
                    self.processar_arquivo_automatico(str(pdf_path))
                    relatorio.arquivos_processados += 1
                    
                except Exception as e:
                    erro = f"{pdf_path.name}: {str(e)}"
                    relatorio.adicionar_erro(erro)
                    logger.error(f"❌ Erro: {e}")
                
                # Pequena pausa entre arquivos
                time.sleep(2)
            
            relatorio.finalizar()
            self._exibir_relatorio_final(relatorio)
            
            return relatorio
            
        except Exception as e:
            logger.error(f"❌ Erro na varredura: {e}", exc_info=True)
            relatorio.adicionar_erro(f"Erro geral: {str(e)}")
            relatorio.finalizar()
            return relatorio
    
    def _exibir_relatorio_final(self, relatorio: RelatorioProcessamento):
        """Exibe relatório final do processamento"""
        logger.info("\n" + "📊 " + "=" * 68)
        logger.info("RELATÓRIO FINAL")
        logger.info("=" * 70)
        logger.info(f"Início: {relatorio.data_inicio}")
        logger.info(f"Fim: {relatorio.data_fim}")
        logger.info(f"\n📁 Arquivos:")
        logger.info(f"   • Processados: {relatorio.arquivos_processados}")
        logger.info(f"   • Novos: {relatorio.arquivos_novos}")
        logger.info(f"   • Atualizados: {relatorio.arquivos_atualizados}")
        
        if relatorio.erros:
            logger.info(f"\n❌ Erros: {len(relatorio.erros)}")
            for erro in relatorio.erros[:5]:
                logger.info(f"   • {erro}")
        
        logger.info("=" * 70 + "\n")
    
    def iniciar_monitoramento(self):
        """Inicia monitoramento contínuo da pasta"""
        logger.info("\n" + "👀 " + "=" * 68)
        logger.info("MONITOR DE PASTA ATIVADO")
        logger.info("=" * 70)
        logger.info(f"📁 Monitorando: {self.pasta_monitorada}")
        logger.info(f"⏱️  Verificação: A cada alteração de arquivo")
        logger.info("=" * 70 + "\n")
        
        event_handler = PDFHandler(self.processar_arquivo_automatico)
        self.observer = Observer()
        self.observer.schedule(event_handler, self.pasta_monitorada, recursive=True)
        self.observer.start()
        self.ativo = True
        
        try:
            while self.ativo:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n⏹️  Encerrando monitor...")
            self.parar_monitoramento()
    
    def parar_monitoramento(self):
        """Para o monitoramento"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.ativo = False
            logger.info("✅ Monitor encerrado")