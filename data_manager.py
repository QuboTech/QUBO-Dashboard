"""
data_manager.py - Gerenciador central de dados e persistência
"""
import pandas as pd
import json
import logging
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
from config import Config
from models import Produto, ArquivoProcessado, MudancaPreco

logger = logging.getLogger(__name__)

class DataManager:
    """Gerencia persistência de dados"""
    
    def __init__(self):
        self.caminho_excel = Config.PASTA_DADOS / Config.ARQUIVO_EXCEL
        self.caminho_cache = Config.PASTA_DADOS / Config.ARQUIVO_CACHE
        self.caminho_historico = Config.PASTA_DADOS / Config.ARQUIVO_HISTORICO
        
        self.df_produtos = self._carregar_excel()
        self.cache_arquivos = self._carregar_cache()
        self.historico_precos = self._carregar_historico()
    
    # ==================== EXCEL ====================
    
    def _carregar_excel(self) -> pd.DataFrame:
        """Carrega dados do Excel existente"""
        if not self.caminho_excel.exists():
            logger.info("📋 Criando nova base de dados...")
            return pd.DataFrame(columns=Config.COLUNAS_PADRAO)
        
        try:
            logger.info(f"📋 Carregando base existente: {self.caminho_excel}")
            df = pd.read_excel(self.caminho_excel)
            
            # Garante colunas padrão
            for col in Config.COLUNAS_PADRAO:
                if col not in df.columns:
                    df[col] = ""
            
            logger.info(f"   ✓ {len(df)} produtos carregados")
            return df
            
        except Exception as e:
            logger.error(f"Erro ao carregar Excel: {e}")
            return pd.DataFrame(columns=Config.COLUNAS_PADRAO)
    
    def salvar_excel(self, df: pd.DataFrame = None) -> bool:
        """
        Salva dados no Excel
        
        Args:
            df: DataFrame para salvar (usa self.df_produtos se None)
            
        Returns:
            True se salvou com sucesso
        """
        if df is None:
            df = self.df_produtos
        
        try:
            # Garante ordem das colunas
            df = df[Config.COLUNAS_PADRAO]
            
            # Salva
            df.to_excel(self.caminho_excel, index=False)
            logger.info(f"💾 Excel salvo: {len(df)} produtos")
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao salvar Excel: {e}")
            return False
    
    # ==================== CACHE ====================
    
    def _carregar_cache(self) -> Dict[str, ArquivoProcessado]:
        """Carrega cache de arquivos processados"""
        if not self.caminho_cache.exists():
            return {}
        
        try:
            with open(self.caminho_cache, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            cache = {}
            for nome, info in dados.items():
                cache[nome] = ArquivoProcessado(**info)
            
            logger.info(f"📦 Cache carregado: {len(cache)} arquivos")
            return cache
            
        except Exception as e:
            logger.error(f"Erro ao carregar cache: {e}")
            return {}
    
    def salvar_cache(self) -> bool:
        """Salva cache de arquivos processados"""
        try:
            dados = {
                nome: arquivo.to_dict() 
                for nome, arquivo in self.cache_arquivos.items()
            }
            
            with open(self.caminho_cache, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Cache salvo: {len(dados)} arquivos")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao salvar cache: {e}")
            return False
    
    def arquivo_ja_processado(self, caminho: str) -> bool:
        """Verifica se arquivo já foi processado"""
        nome = Path(caminho).name
        return nome in self.cache_arquivos
    
    def arquivo_foi_modificado(self, caminho: str) -> bool:
        """Verifica se arquivo foi modificado desde último processamento"""
        nome = Path(caminho).name
        
        if nome not in self.cache_arquivos:
            return True
        
        hash_anterior = self.cache_arquivos[nome].hash_md5
        hash_atual = ArquivoProcessado.calcular_hash(caminho)
        
        return hash_atual != hash_anterior
    
    def registrar_arquivo_processado(self, arquivo: ArquivoProcessado):
        """Registra arquivo como processado"""
        self.cache_arquivos[arquivo.nome] = arquivo
        self.salvar_cache()
    
    # ==================== HISTÓRICO DE PREÇOS ====================
    
    def _carregar_historico(self) -> Dict[str, List[Dict]]:
        """Carrega histórico de mudanças de preço"""
        if not self.caminho_historico.exists():
            return {}
        
        try:
            with open(self.caminho_historico, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar histórico: {e}")
            return {}
    
    def salvar_historico(self) -> bool:
        """Salva histórico de preços"""
        try:
            with open(self.caminho_historico, 'w', encoding='utf-8') as f:
                json.dump(self.historico_precos, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar histórico: {e}")
            return False
    
    def registrar_mudancas_preco(self, mudancas: List[MudancaPreco]):
        """Registra mudanças de preço no histórico"""
        for mudanca in mudancas:
            chave = f"{mudanca.fornecedor}_{mudanca.codigo}"
            
            if chave not in self.historico_precos:
                self.historico_precos[chave] = []
            
            self.historico_precos[chave].append(mudanca.to_dict())
        
        if mudancas:
            self.salvar_historico()
            logger.info(f"📈 {len(mudancas)} mudanças registradas no histórico")
    
    def obter_historico_produto(self, fornecedor: str, codigo: str) -> List[Dict]:
        """Obtém histórico de preços de um produto"""
        chave = f"{fornecedor}_{codigo}"
        return self.historico_precos.get(chave, [])
    
    # ==================== OPERAÇÕES COM PRODUTOS ====================
    
    def adicionar_produtos(self, produtos: List[Produto]) -> int:
        """
        Adiciona novos produtos ao DataFrame
        
        Returns:
            Número de produtos adicionados
        """
        if not produtos:
            return 0
        
        novos_dados = [p.to_dict() for p in produtos]
        df_novos = pd.DataFrame(novos_dados)
        
        # Garante colunas padrão
        for col in Config.COLUNAS_PADRAO:
            if col not in df_novos.columns:
                df_novos[col] = ""
        
        self.df_produtos = pd.concat([self.df_produtos, df_novos], ignore_index=True)
        
        logger.info(f"➕ {len(produtos)} produtos adicionados")
        return len(produtos)
    
    def atualizar_produtos(self, produtos: List[Produto]) -> int:
        """
        Atualiza produtos existentes
        
        Returns:
            Número de produtos atualizados
        """
        if not produtos or self.df_produtos.empty:
            return 0
        
        contador = 0
        
        for produto in produtos:
            # Localiza produto na base
            mask = (
                (self.df_produtos['fornecedor'].str.lower() == produto.fornecedor.lower()) &
                (self.df_produtos['codigo'].str.lower() == produto.codigo.lower())
            )
            
            if mask.any():
                # Atualiza campos
                self.df_produtos.loc[mask, 'preco_unitario'] = produto.preco_unitario
                self.df_produtos.loc[mask, 'descricao'] = produto.descricao
                self.df_produtos.loc[mask, 'qtd_caixa'] = produto.qtd_caixa if produto.qtd_caixa else ""
                self.df_produtos.loc[mask, 'data_processamento'] = produto.data_processamento
                self.df_produtos.loc[mask, 'hash_arquivo'] = produto.hash_arquivo
                
                contador += 1
        
        if contador > 0:
            logger.info(f"🔄 {contador} produtos atualizados")
        
        return contador
    
    def remover_duplicatas(self) -> int:
        """
        Remove produtos duplicados
        
        Returns:
            Número de duplicatas removidas
        """
        if self.df_produtos.empty:
            return 0
        
        tamanho_antes = len(self.df_produtos)
        
        self.df_produtos = self.df_produtos.drop_duplicates(
            subset=['fornecedor', 'codigo'],
            keep='last'
        )
        
        removidas = tamanho_antes - len(self.df_produtos)
        
        if removidas > 0:
            logger.info(f"🗑️  {removidas} duplicatas removidas")
        
        return removidas
    
    def exportar_para_csv(self, caminho: Optional[str] = None) -> bool:
        """Exporta dados para CSV"""
        try:
            caminho_csv = caminho or Config.PASTA_DADOS / "produtos.csv"
            self.df_produtos.to_csv(caminho_csv, index=False, encoding='utf-8-sig')
            logger.info(f"📄 Exportado para: {caminho_csv}")
            return True
        except Exception as e:
            logger.error(f"Erro ao exportar CSV: {e}")
            return False
    
    def gerar_relatorio_resumo(self) -> Dict:
        """Gera relatório resumido dos dados"""
        if self.df_produtos.empty:
            return {}
        
        return {
            'total_produtos': len(self.df_produtos),
            'fornecedores': self.df_produtos['fornecedor'].nunique(),
            'arquivos_processados': len(self.cache_arquivos),
            'ultima_atualizacao': self.df_produtos['data_processamento'].max(),
            'produtos_por_fornecedor': self.df_produtos['fornecedor'].value_counts().to_dict()
        }