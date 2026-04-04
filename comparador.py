"""
comparador.py - Sistema inteligente de comparação de produtos e preços
VERSÃO CORRIGIDA - Completa e funcional
"""
import pandas as pd
import logging
from typing import List, Dict, Tuple
from datetime import datetime
from models import Produto, MudancaPreco
from config import Config

logger = logging.getLogger(__name__)

class ComparadorInteligente:
    """Compara produtos e detecta mudanças"""
    
    def __init__(self, df_base: pd.DataFrame = None):
        """
        Inicializa comparador
        
        Args:
            df_base: DataFrame com produtos existentes
        """
        self.df_base = df_base if df_base is not None else pd.DataFrame()
        self.produtos_por_chave = self._indexar_produtos()
    
    def _indexar_produtos(self) -> Dict[str, Dict]:
        """Cria índice de produtos por chave única"""
        if self.df_base.empty:
            return {}
        
        indice = {}
        for _, row in self.df_base.iterrows():
            chave = self._gerar_chave(row.get('fornecedor', ''), row.get('codigo', ''))
            indice[chave] = row.to_dict()
        
        return indice
    
    def _gerar_chave(self, fornecedor: str, codigo: str) -> str:
        """Gera chave única para produto"""
        return f"{str(fornecedor).lower().strip()}_{str(codigo).lower().strip()}"
    
    def comparar_produtos(
        self, 
        produtos_novos: List[Produto]
    ) -> Tuple[List[Produto], List[Produto], List[MudancaPreco]]:
        """
        Compara produtos novos com base existente
        
        Args:
            produtos_novos: Lista de produtos extraídos
            
        Returns:
            Tupla com:
            - Lista de produtos realmente novos
            - Lista de produtos atualizados
            - Lista de mudanças de preço detectadas
        """
        produtos_novos_lista = []
        produtos_atualizados = []
        mudancas_preco = []
        
        logger.info(f"🔍 Comparando {len(produtos_novos)} produtos...")
        
        for produto in produtos_novos:
            chave = self._gerar_chave(produto.fornecedor, produto.codigo)
            
            if chave in self.produtos_por_chave:
                # Produto já existe - verifica mudanças
                produto_anterior = self.produtos_por_chave[chave]
                
                preco_anterior = float(produto_anterior.get('preco_unitario', 0))
                preco_novo = float(produto.preco_unitario)
                
                # Detecta mudança de preço (tolerância de 0.01 para flutuações)
                if abs(preco_novo - preco_anterior) > 0.01:
                    mudanca = MudancaPreco(
                        fornecedor=produto.fornecedor,
                        codigo=produto.codigo,
                        descricao=produto.descricao,
                        preco_antigo=preco_anterior,
                        preco_novo=preco_novo,
                        percentual_mudanca=0.0,  # Será calculado no __post_init__
                        arquivo_origem=produto.Arquivo_Origem
                    )
                    
                    mudancas_preco.append(mudanca)
                    produtos_atualizados.append(produto)
                    
                    logger.info(
                        f"   💰 Mudança: {produto.codigo} | "
                        f"R$ {preco_anterior:.2f} → R$ {preco_novo:.2f} "
                        f"({mudanca.percentual_mudanca:+.1f}%)"
                    )
            else:
                # Produto novo
                produtos_novos_lista.append(produto)
                logger.info(f"   ✨ Novo: {produto.codigo} - {produto.descricao[:50]}")
        
        logger.info("\n" + "=" * 70)
        logger.info(f"📊 RESULTADO DA COMPARAÇÃO:")
        logger.info(f"   • Produtos novos: {len(produtos_novos_lista)}")
        logger.info(f"   • Produtos atualizados: {len(produtos_atualizados)}")
        logger.info(f"   • Mudanças de preço: {len(mudancas_preco)}")
        logger.info("=" * 70 + "\n")
        
        return produtos_novos_lista, produtos_atualizados, mudancas_preco
    
    def gerar_relatorio_mudancas(
        self, 
        mudancas: List[MudancaPreco]
    ) -> pd.DataFrame:
        """
        Gera relatório formatado de mudanças de preço
        
        Args:
            mudancas: Lista de mudanças detectadas
            
        Returns:
            DataFrame com relatório
        """
        if not mudancas:
            return pd.DataFrame()
        
        dados = []
        for m in mudancas:
            dados.append({
                'Fornecedor': m.fornecedor,
                'Código': m.codigo,
                'Descrição': m.descricao,
                'Preço Anterior': f'R$ {m.preco_antigo:.2f}',
                'Preço Novo': f'R$ {m.preco_novo:.2f}',
                'Variação': f'{m.percentual_mudanca:+.2f}%',
                'Tipo': m.tipo_mudanca(),
                'Data': m.data_mudanca[:10],
                'Arquivo': m.arquivo_origem
            })
        
        df = pd.DataFrame(dados)
        
        # Ordena por percentual de mudança (maiores primeiro)
        df['_sort'] = [m.percentual_mudanca for m in mudancas]
        df = df.sort_values('_sort', ascending=False)
        df = df.drop('_sort', axis=1)
        
        return df
    
    def identificar_produtos_removidos(
        self, 
        produtos_novos: List[Produto],
        fornecedor: str = None
    ) -> List[Dict]:
        """
        Identifica produtos que não aparecem mais no catálogo
        
        Args:
            produtos_novos: Lista de produtos do novo catálogo
            fornecedor: Filtrar por fornecedor específico
            
        Returns:
            Lista de produtos que foram removidos
        """
        if self.df_base.empty:
            return []
        
        # Cria conjunto de chaves dos produtos novos
        chaves_novas = {
            self._gerar_chave(p.fornecedor, p.codigo) 
            for p in produtos_novos
        }
        
        produtos_removidos = []
        
        for chave, produto_anterior in self.produtos_por_chave.items():
            # Filtra por fornecedor se especificado
            if fornecedor and produto_anterior.get('fornecedor', '').lower() != fornecedor.lower():
                continue
            
            if chave not in chaves_novas:
                produtos_removidos.append(produto_anterior)
        
        if produtos_removidos:
            logger.warning(f"⚠️  {len(produtos_removidos)} produtos não encontrados no novo catálogo")
        
        return produtos_removidos
    
    def estatisticas_comparacao(
        self,
        produtos_novos: List[Produto],
        produtos_atualizados: List[Produto],
        mudancas_preco: List[MudancaPreco]
    ) -> Dict:
        """
        Gera estatísticas da comparação
        
        Returns:
            Dicionário com estatísticas
        """
        aumentos = [m for m in mudancas_preco if m.percentual_mudanca > 0]
        reducoes = [m for m in mudancas_preco if m.percentual_mudanca < 0]
        
        stats = {
            'produtos_novos': len(produtos_novos),
            'produtos_atualizados': len(produtos_atualizados),
            'total_mudancas': len(mudancas_preco),
            'aumentos_preco': len(aumentos),
            'reducoes_preco': len(reducoes),
            'maior_aumento': max([m.percentual_mudanca for m in aumentos], default=0),
            'maior_reducao': min([m.percentual_mudanca for m in reducoes], default=0),
            'media_aumento': sum([m.percentual_mudanca for m in aumentos]) / len(aumentos) if aumentos else 0,
            'media_reducao': sum([m.percentual_mudanca for m in reducoes]) / len(reducoes) if reducoes else 0
        }
        
        return stats