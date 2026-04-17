"""
agente_pesquisa.py - Agente de Pesquisa de Produto no Mercado Livre
====================================================================
Recebe um produto selecionado no dashboard (checkbox) e faz análise
completa de mercado: preços, vendas, concorrentes, margem sugerida.

Autor: Claude para QUBO
Data: 2026-04
"""

import json
import time
import logging
import re
from pathlib import Path
from typing import Optional

from db import get_conn, USAR_POSTGRES

logger = logging.getLogger(__name__)


def limpar_termo_busca(descricao: str) -> str:
    """
    Limpa a descrição do produto para gerar um termo de busca eficaz no ML.
    Remove medidas, números, símbolos e palavras desnecessárias.
    Mantém marca, modelo e palavras-chave relevantes.
    """
    t = descricao.upper()
    
    # Remove medidas (50mm, 1.5kg, 220V, etc.)
    t = re.sub(r'\d+[.,]?\d*\s*(MM|CM|M|KG|G|ML|L|UN|PCS|PÇS|PC|UND|V|W|HP|HZ|A)\b', '', t, flags=re.IGNORECASE)
    
    # Remove dimensões (50x780, 30X40)
    t = re.sub(r'\b\d+\s*[Xx×]\s*\d+\b', '', t)
    
    # Remove números 2+ dígitos soltos
    t = re.sub(r'\b\d{2,}\b', '', t)
    
    # Remove palavras comuns/ruído
    t = re.sub(r'\b(COM|PARA|POR|SEM|DOS|DAS|DEL|UMA|UNS|NAS|NOS|TIPO|REF|COD|MODELO|UNID|COR|TAM|DE|DA|DO|E|A|O)\b', '', t, flags=re.IGNORECASE)
    
    # Remove símbolos
    t = re.sub(r'[+\-*/()[\]{}#@&%$!;:=\'"]+', ' ', t)
    
    t = re.sub(r'\s+', ' ', t).strip()
    
    # Filtra palavras com 3+ chars, máximo 5 palavras
    palavras = [p for p in t.split() if len(p) >= 3]
    if len(palavras) > 5:
        palavras = palavras[:5]
    
    return ' '.join(palavras)


def analisar_produto_ml(produto_id: int, token_ml: str, custo_produto: float = 0) -> dict:
    """
    Analisa um produto no Mercado Livre.
    
    Retorna análise completa:
    - Faixa de preços dos concorrentes
    - sold_quantity dos top anúncios
    - Vendedor destaque
    - Margem estimada com taxa ML
    - Sugestão de preço de entrada
    """
    import requests
    
    try:
        # Busca dados do produto no banco
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"SELECT * FROM produtos WHERE id = {ph}", (produto_id,))
        row = cur.fetchone()
        if row:
            cols = [d[0] for d in cur.description]
            produto = dict(zip(cols, row))
        else:
            produto = {}
        conn.close()
        
        if not produto:
            return {'ok': False, 'erro': 'Produto não encontrado no banco'}
        
        descricao = produto.get('descricao', '')
        custo = custo_produto or produto.get('custo', 0) or 0
        
        termo = limpar_termo_busca(descricao)
        
        if not termo or len(termo) < 3:
            return {'ok': False, 'erro': 'Não foi possível gerar termo de busca'}
        
        # ── 1. Busca no ML (pública por padrão, sem exigir token) ──────
        # A API de busca pública funciona sem autenticação.
        # Token é opcional: melhora os dados de taxa se disponível.
        resp = requests.get(
            'https://api.mercadolibre.com/sites/MLB/search',
            params={'q': termo, 'limit': 20},
            timeout=15
        )

        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro na API ML: {resp.status_code}'}

        # Headers para endpoints que precisam de auth (taxa real)
        headers = {'Authorization': f'Bearer {token_ml}'} if token_ml else {}
        
        data = resp.json()
        resultados = data.get('results', [])
        total_ml = data.get('paging', {}).get('total', 0)
        
        if not resultados:
            return {'ok': False, 'erro': f'Nenhum resultado para "{termo}"'}
        
        # ── 2. Analisa preços e vendas ───────────────────────────────
        precos = []
        vendas_totais = 0
        anuncios_analisados = []
        categoria_top = ''
        
        for item in resultados:
            preco = item.get('price', 0)
            vendas = item.get('sold_quantity', 0)
            precos.append(preco)
            vendas_totais += vendas
            
            anuncios_analisados.append({
                'titulo': item.get('title', ''),
                'preco': preco,
                'vendas': vendas,
                'vendedor': item.get('seller', {}).get('nickname', ''),
                'link': item.get('permalink', ''),
                'condicao': item.get('condition', ''),
                'tipo': item.get('listing_type_id', '').replace('gold_', '').replace('_', ' ').title()
            })
            
            if not categoria_top:
                categoria_top = item.get('category_id', '')
        
        # Ordena por vendas para mostrar os mais vendidos
        anuncios_analisados.sort(key=lambda x: x['vendas'], reverse=True)
        
        preco_min = min(precos)
        preco_max = max(precos)
        preco_medio = sum(precos) / len(precos)
        preco_mediano = sorted(precos)[len(precos) // 2]
        
        # ── 3. Busca taxa ML real da categoria (só com token válido) ────
        taxa_percentual = 16.5  # Default

        if categoria_top and headers:  # só busca taxa se tem token válido
            try:
                resp_taxa = requests.get(
                    'https://api.mercadolibre.com/sites/MLB/listing_prices',
                    headers=headers,
                    params={
                        'price': preco_mediano,
                        'category_id': categoria_top,
                        'currency_id': 'BRL'
                    },
                    timeout=10
                )
                
                if resp_taxa.status_code == 200:
                    taxa_data = resp_taxa.json()
                    # Extrai taxa do tipo "gold_special" (clássico) ou "gold_pro" (premium)
                    for listing in taxa_data:
                        if listing.get('listing_type_id') in ('gold_special', 'gold_pro'):
                            for comp in listing.get('sale_fee_components', []):
                                if comp.get('type') == 'fee':
                                    taxa_percentual = comp.get('ratio', 0.165) * 100
                                    break
                            break
            except Exception:
                pass  # Mantém taxa default
        
        # ── 4. Calcula margem e sugestão de preço ───────────────────
        taxa_decimal = taxa_percentual / 100
        
        def margem_simples(custo, preco):
            """Margem sem frete (estimativa rápida)"""
            if not preco or preco <= 0:
                return 0
            taxa_fixa = 6.25 if preco < 79 else 0
            custo_ml = preco * taxa_decimal + taxa_fixa
            lucro = preco - custo - custo_ml
            return round((lucro / preco) * 100, 1)
        
        # Preço sugerido: mediano com margem >= 20%
        preco_sugerido = 0
        if custo > 0:
            # Calcula preço para 25% de margem
            preco_sugerido = round(custo / (1 - taxa_decimal - 0.25), 2)
        
        margem_no_minimo = margem_simples(custo, preco_min) if custo > 0 else None
        margem_no_medio = margem_simples(custo, preco_medio) if custo > 0 else None
        margem_no_mediano = margem_simples(custo, preco_mediano) if custo > 0 else None
        
        # ── 5. Identifica vendedor destaque ─────────────────────────
        vendedor_destaque = None
        if anuncios_analisados:
            top = anuncios_analisados[0]
            vendedor_destaque = {
                'nome': top['vendedor'],
                'preco': top['preco'],
                'vendas': top['vendas'],
                'link': top['link']
            }
        
        return {
            'ok': True,
            'produto_id': produto_id,
            'produto_nome': descricao,
            'termo_buscado': termo,
            'custo': custo,
            
            # Mercado
            'total_anuncios_ml': total_ml,
            'anuncios_analisados': len(anuncios_analisados),
            
            # Preços
            'preco_min': round(preco_min, 2),
            'preco_max': round(preco_max, 2),
            'preco_medio': round(preco_medio, 2),
            'preco_mediano': round(preco_mediano, 2),
            
            # Vendas (acumulado histórico dos top anúncios)
            'vendas_totais_top20': vendas_totais,
            'media_vendas_por_anuncio': round(vendas_totais / max(len(anuncios_analisados), 1), 0),
            
            # Taxa
            'taxa_percentual': round(taxa_percentual, 1),
            'categoria_id': categoria_top,
            
            # Margens (se custo informado)
            'margem_no_minimo': margem_no_minimo,
            'margem_no_medio': margem_no_medio,
            'margem_no_mediano': margem_no_mediano,
            'preco_sugerido_25pct': preco_sugerido if custo > 0 else None,
            
            # Top anúncios
            'top_anuncios': anuncios_analisados[:5],
            'vendedor_destaque': vendedor_destaque,
        }
    
    except Exception as e:
        logger.error(f"❌ Erro no agente de pesquisa: {e}")
        return {'ok': False, 'erro': str(e)}
