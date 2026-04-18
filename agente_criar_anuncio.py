"""
agente_criar_anuncio.py - Criar e Editar Anúncios no Mercado Livre
==================================================================
- Sugere categoria ideal pelo título (category predictor)
- Busca atributos obrigatórios da categoria
- Valida anúncio antes de publicar
- Cria anúncio (POST /items)
- Edita anúncio (PUT /items/{id}) — preço, título, descrição, estoque, imagens
- Atualiza descrição (plain text)

Autor: Claude para QUBO
Data: 2026-04
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY PREDICTOR — sugere categoria ideal pelo título
# ─────────────────────────────────────────────────────────────────────────────
def prever_categoria(token_ml: str, titulo: str) -> dict:
    """
    Sugere a melhor categoria ML para um título de produto.
    Funciona mesmo sem token (endpoint é público na maioria dos casos).
    """
    if not titulo or len(titulo) < 4:
        return {'ok': False, 'erro': 'Título muito curto (mín. 4 caracteres)'}

    headers = {'Accept': 'application/json'}
    if token_ml:
        headers['Authorization'] = f'Bearer {token_ml}'

    try:
        resp = requests.get(
            'https://api.mercadolibre.com/sites/MLB/domain_discovery/search',
            headers=headers,
            params={'q': titulo, 'limit': 5},
            timeout=15
        )
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro API ML: {resp.status_code}'}

        dados = resp.json()
        if not dados:
            return {'ok': False, 'erro': 'Nenhuma categoria sugerida'}

        top = dados[0]
        sugestoes = []
        for item in dados[:5]:
            sugestoes.append({
                'category_id': item.get('category_id', ''),
                'category_name': item.get('category_name', ''),
                'domain_id': item.get('domain_id', ''),
                'domain_name': item.get('domain_name', ''),
                'attributes': item.get('attributes', []),
            })

        return {
            'ok': True,
            'top_category_id': top.get('category_id', ''),
            'top_category_name': top.get('category_name', ''),
            'top_domain': top.get('domain_name', ''),
            'sugestoes': sugestoes,
        }
    except Exception as e:
        logger.error(f"❌ Erro em prever_categoria: {e}")
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# ATRIBUTOS DA CATEGORIA — obrigatórios + sugeridos
# ─────────────────────────────────────────────────────────────────────────────
def obter_atributos_categoria(token_ml: str, category_id: str) -> dict:
    """Retorna atributos obrigatórios e opcionais de uma categoria."""
    if not category_id:
        return {'ok': False, 'erro': 'category_id obrigatório'}

    headers = {'Accept': 'application/json'}
    if token_ml:
        headers['Authorization'] = f'Bearer {token_ml}'

    try:
        resp = requests.get(
            f'https://api.mercadolibre.com/categories/{category_id}/attributes',
            headers=headers, timeout=15
        )
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro {resp.status_code}'}

        attrs_raw = resp.json()
        obrigatorios = []
        opcionais = []

        for a in attrs_raw:
            tags = a.get('tags', {}) or {}
            entry = {
                'id': a.get('id'),
                'name': a.get('name'),
                'value_type': a.get('value_type'),
                'values': [v.get('name') for v in (a.get('values') or [])[:20]],
                'hint': a.get('hint'),
            }
            if tags.get('required') or tags.get('catalog_required'):
                obrigatorios.append(entry)
            else:
                opcionais.append(entry)

        return {
            'ok': True,
            'category_id': category_id,
            'total': len(attrs_raw),
            'obrigatorios': obrigatorios[:20],
            'opcionais': opcionais[:20],
        }
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# VALIDAR ANÚNCIO — antes de publicar
# ─────────────────────────────────────────────────────────────────────────────
def validar_anuncio(token_ml: str, payload: dict) -> dict:
    """Valida o payload antes de publicar — retorna erros sem criar."""
    if not token_ml:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {
        'Authorization': f'Bearer {token_ml}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    try:
        resp = requests.post(
            'https://api.mercadolibre.com/items/validate',
            headers=headers, json=payload, timeout=15
        )
        if resp.status_code in (200, 204):
            return {'ok': True, 'msg': 'Anúncio válido — pode publicar'}
        else:
            err = resp.json() if resp.text else {}
            causes = err.get('cause', [])
            msgs = [c.get('message', '') for c in causes] if causes else [err.get('message', f'Erro {resp.status_code}')]
            return {'ok': False, 'erro': ' · '.join(msgs)}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# CRIAR ANÚNCIO
# ─────────────────────────────────────────────────────────────────────────────
def criar_anuncio(token_ml: str, dados: dict) -> dict:
    """
    Cria anúncio novo no ML.

    Parâmetros mínimos em `dados`:
        titulo (str): máx 60 chars
        category_id (str): ex "MLB1574"
        preco (float)
        quantidade (int): estoque disponível
        imagens (list[str]): URLs das imagens (mín 1)
        descricao (str): texto plano
        condicao (str): "new" | "used" (default "new")
        tipo_anuncio (str): "gold_special" (Clássico) | "gold_pro" (Premium), default Clássico
        atributos (dict): attr_id → value (ex {"BRAND": "Nike", "COLOR": "Preto"})
    """
    if not token_ml:
        return {'ok': False, 'erro': 'ML não conectado'}

    # Validações básicas
    titulo = (dados.get('titulo') or '').strip()[:60]
    if not titulo:
        return {'ok': False, 'erro': 'Título obrigatório'}
    if not dados.get('category_id'):
        return {'ok': False, 'erro': 'Categoria obrigatória'}
    if float(dados.get('preco', 0)) <= 0:
        return {'ok': False, 'erro': 'Preço inválido'}
    imagens = dados.get('imagens') or []
    if not imagens:
        return {'ok': False, 'erro': 'Ao menos 1 imagem é obrigatória'}

    # Monta atributos no formato ML
    attrs_fmt = []
    for aid, val in (dados.get('atributos') or {}).items():
        if val:
            attrs_fmt.append({'id': aid, 'value_name': str(val)})

    payload = {
        'title': titulo,
        'category_id': dados['category_id'],
        'price': float(dados['preco']),
        'currency_id': 'BRL',
        'available_quantity': int(dados.get('quantidade', 1)),
        'buying_mode': 'buy_it_now',
        'listing_type_id': dados.get('tipo_anuncio', 'gold_special'),
        'condition': dados.get('condicao', 'new'),
        'pictures': [{'source': url} for url in imagens],
        'attributes': attrs_fmt,
    }

    # Garantia / warranty (opcional)
    if dados.get('garantia'):
        payload['warranty'] = dados['garantia']

    # SKU
    if dados.get('sku'):
        attrs_fmt.append({'id': 'SELLER_SKU', 'value_name': str(dados['sku'])})
        payload['attributes'] = attrs_fmt

    headers = {
        'Authorization': f'Bearer {token_ml}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    try:
        resp = requests.post(
            'https://api.mercadolibre.com/items',
            headers=headers, json=payload, timeout=30
        )

        if resp.status_code in (200, 201):
            item = resp.json()
            item_id = item.get('id')
            link = item.get('permalink', '')

            # Publica descrição (endpoint separado)
            desc = dados.get('descricao', '').strip()
            if desc and item_id:
                try:
                    requests.post(
                        f'https://api.mercadolibre.com/items/{item_id}/description',
                        headers=headers,
                        json={'plain_text': desc[:50000]},
                        timeout=15
                    )
                except Exception:
                    pass

            return {
                'ok': True,
                'item_id': item_id,
                'link': link,
                'status': item.get('status'),
                'msg': f'Anúncio criado: {item_id}',
            }
        elif resp.status_code == 401:
            return {'ok': False, 'erro': 'Token expirado. Reconecte.'}
        elif resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão write_listings.'}
        else:
            err = resp.json() if resp.text else {}
            causes = err.get('cause', [])
            msgs = [c.get('message', '') for c in causes] if causes else [err.get('message', f'Erro {resp.status_code}')]
            return {'ok': False, 'erro': ' · '.join(msgs)}

    except Exception as e:
        logger.error(f"❌ Erro em criar_anuncio: {e}")
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# EDITAR ANÚNCIO — muda campos parciais
# ─────────────────────────────────────────────────────────────────────────────
def editar_anuncio(token_ml: str, item_id: str, alteracoes: dict) -> dict:
    """
    Edita anúncio existente. Campos aceitos:
        titulo, preco, quantidade, imagens, atributos, garantia
    Descrição usa endpoint separado (/items/{id}/description PUT).
    """
    if not token_ml:
        return {'ok': False, 'erro': 'ML não conectado'}
    if not item_id:
        return {'ok': False, 'erro': 'item_id obrigatório'}

    headers = {
        'Authorization': f'Bearer {token_ml}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    payload = {}
    if 'titulo' in alteracoes and alteracoes['titulo']:
        payload['title'] = str(alteracoes['titulo'])[:60]
    if 'preco' in alteracoes and alteracoes['preco']:
        payload['price'] = float(alteracoes['preco'])
    if 'quantidade' in alteracoes and alteracoes['quantidade'] is not None:
        payload['available_quantity'] = int(alteracoes['quantidade'])
    if 'imagens' in alteracoes and alteracoes['imagens']:
        payload['pictures'] = [{'source': url} for url in alteracoes['imagens']]
    if 'garantia' in alteracoes and alteracoes['garantia']:
        payload['warranty'] = alteracoes['garantia']
    if 'atributos' in alteracoes and alteracoes['atributos']:
        payload['attributes'] = [{'id': k, 'value_name': str(v)}
                                  for k, v in alteracoes['atributos'].items() if v]

    try:
        sucesso_msgs = []

        # Atualiza campos gerais
        if payload:
            resp = requests.put(
                f'https://api.mercadolibre.com/items/{item_id}',
                headers=headers, json=payload, timeout=20
            )
            if resp.status_code not in (200, 204):
                err = resp.json() if resp.text else {}
                causes = err.get('cause', [])
                msgs = [c.get('message', '') for c in causes] if causes else [err.get('message', f'Erro {resp.status_code}')]
                return {'ok': False, 'erro': ' · '.join(msgs)}
            sucesso_msgs.append('campos atualizados')

        # Atualiza descrição (endpoint separado)
        if 'descricao' in alteracoes and alteracoes['descricao']:
            resp_d = requests.put(
                f'https://api.mercadolibre.com/items/{item_id}/description',
                headers=headers,
                json={'plain_text': str(alteracoes['descricao'])[:50000]},
                timeout=15
            )
            if resp_d.status_code in (200, 204):
                sucesso_msgs.append('descrição atualizada')

        if not sucesso_msgs:
            return {'ok': False, 'erro': 'Nenhuma alteração fornecida'}

        return {'ok': True, 'msg': 'Anúncio editado: ' + ', '.join(sucesso_msgs)}

    except Exception as e:
        logger.error(f"❌ Erro em editar_anuncio: {e}")
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# CRIAR A PARTIR DE PRODUTO DO BANCO — integra com catálogo do QUBO
# ─────────────────────────────────────────────────────────────────────────────
def criar_a_partir_de_produto(token_ml: str, produto_id: int,
                               preco: float = None,
                               quantidade: int = 1,
                               imagens: list = None,
                               tipo: str = 'gold_special') -> dict:
    """
    Cria anúncio no ML a partir de um produto já cadastrado no banco QUBO.
    Usa descrição como título (truncada), sugere categoria automaticamente.
    """
    from db import get_conn, USAR_POSTGRES

    try:
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"SELECT descricao, custo, preco_ml, peso_kg FROM produtos WHERE id = {ph}", (produto_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return {'ok': False, 'erro': 'Produto não encontrado no banco'}

        descricao, custo, preco_ml_saved, peso = row[0], float(row[1] or 0), float(row[2] or 0), float(row[3] or 0)
        titulo = descricao[:60]

        # Prevê categoria
        cat_resp = prever_categoria(token_ml, titulo)
        if not cat_resp.get('ok'):
            return {'ok': False, 'erro': f'Falha ao prever categoria: {cat_resp.get("erro")}'}

        category_id = cat_resp['top_category_id']
        preco_final = preco or preco_ml_saved
        if not preco_final:
            return {'ok': False, 'erro': 'Defina o preço de venda antes de publicar'}

        return criar_anuncio(token_ml, {
            'titulo': titulo,
            'category_id': category_id,
            'preco': preco_final,
            'quantidade': quantidade,
            'imagens': imagens or [],
            'descricao': descricao,
            'tipo_anuncio': tipo,
        })

    except Exception as e:
        return {'ok': False, 'erro': str(e)}
