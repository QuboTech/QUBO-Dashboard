"""
agente_perguntas.py - Perguntas e Respostas do Mercado Livre
=============================================================
Lista perguntas recebidas (filtro: sem resposta por padrão).
Permite responder diretamente pelo dashboard.

Autor: Claude para QUBO
Data: 2026-04
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


def listar_perguntas(token_ml: str, user_id: str,
                     apenas_nao_respondidas: bool = True,
                     limite: int = 50) -> dict:
    """
    Lista perguntas recebidas pelo vendedor.

    Parâmetros:
        token_ml: access token ML
        user_id: seller user_id
        apenas_nao_respondidas: filtrar só pendentes (default True)
        limite: máximo de perguntas (default 50)
    """
    if not token_ml or not user_id:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        params = {
            'seller_id': user_id,
            'api_version': 4,
            'limit': limite,
            'sort_fields': 'date_created',
            'sort_types': 'DESC',
        }
        if apenas_nao_respondidas:
            params['status'] = 'UNANSWERED'

        resp = requests.get(
            'https://api.mercadolibre.com/questions/search',
            headers=headers,
            params=params,
            timeout=15
        )

        if resp.status_code == 401:
            return {'ok': False, 'erro': 'Token ML expirado. Reconecte.'}
        if resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão para ler perguntas.'}
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro API ML: {resp.status_code}'}

        data = resp.json()
        pergs_raw = data.get('questions', [])
        total = data.get('total', len(pergs_raw))

        perguntas = []
        for q in pergs_raw:
            status = q.get('status', '')
            respondida = status == 'ANSWERED'

            # Data formatada
            data_criacao = q.get('date_created', '')
            if data_criacao:
                try:
                    dt = datetime.strptime(data_criacao[:19], '%Y-%m-%dT%H:%M:%S')
                    data_fmt = dt.strftime('%d/%m %H:%M')
                except Exception:
                    data_fmt = data_criacao[:10]
            else:
                data_fmt = ''

            # Resposta (se houver)
            resposta = q.get('answer')
            resp_texto = resposta.get('text', '') if resposta else ''
            resp_data = ''
            if resposta and resposta.get('date_created'):
                try:
                    dt2 = datetime.strptime(resposta['date_created'][:19], '%Y-%m-%dT%H:%M:%S')
                    resp_data = dt2.strftime('%d/%m %H:%M')
                except Exception:
                    pass

            perguntas.append({
                'id': q.get('id'),
                'item_id': q.get('item_id', ''),
                'item_titulo': q.get('item_title', q.get('item_id', '')),
                'texto': q.get('text', ''),
                'data': data_fmt,
                'status': status,
                'respondida': respondida,
                'resposta_texto': resp_texto,
                'resposta_data': resp_data,
                'from_user': q.get('from', {}).get('nickname', 'Comprador'),
                'icone': '✅' if respondida else '❓',
                'cor': '#4ade80' if respondida else '#fbbf24',
            })

        nao_respondidas = sum(1 for p in perguntas if not p['respondida'])

        return {
            'ok': True,
            'total': total,
            'nao_respondidas': nao_respondidas,
            'perguntas': perguntas,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }

    except Exception as e:
        logger.error(f"❌ Erro em listar_perguntas: {e}")
        return {'ok': False, 'erro': str(e)}


def responder_pergunta(token_ml: str, question_id: int, resposta: str) -> dict:
    """
    Envia resposta a uma pergunta específica.
    """
    if not token_ml:
        return {'ok': False, 'erro': 'ML não conectado'}
    if not resposta or len(resposta.strip()) < 5:
        return {'ok': False, 'erro': 'Resposta muito curta (mín. 5 caracteres)'}

    headers = {
        'Authorization': f'Bearer {token_ml}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    try:
        resp = requests.post(
            f'https://api.mercadolibre.com/answers',
            headers=headers,
            json={'question_id': question_id, 'text': resposta.strip()},
            timeout=15
        )

        if resp.status_code in (200, 201):
            return {'ok': True, 'msg': 'Resposta enviada com sucesso!'}
        elif resp.status_code == 401:
            return {'ok': False, 'erro': 'Token ML expirado. Reconecte.'}
        elif resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão para responder perguntas.'}
        elif resp.status_code == 404:
            return {'ok': False, 'erro': 'Pergunta não encontrada.'}
        else:
            erro_body = resp.json() if resp.text else {}
            return {'ok': False, 'erro': erro_body.get('message', f'Erro {resp.status_code}')}

    except Exception as e:
        logger.error(f"❌ Erro em responder_pergunta: {e}")
        return {'ok': False, 'erro': str(e)}
