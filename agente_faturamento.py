"""
agente_faturamento.py - Faturamento e Cobranças do Mercado Livre
================================================================
Consulta o extrato de cobranças do período atual e anteriores.
Mostra comissões, frete subsidiado, promoções e saldo.

Autor: Claude para QUBO
Data: 2026-04
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


def listar_periodos(token_ml: str) -> dict:
    """Lista os períodos de faturamento disponíveis."""
    if not token_ml:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}
    try:
        resp = requests.get(
            'https://api.mercadolibre.com/billing/integration/periods',
            headers=headers, timeout=15
        )
        if resp.status_code == 401:
            return {'ok': False, 'erro': 'Token expirado. Reconecte.'}
        if resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão para ler faturamento.'}
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro API ML: {resp.status_code}'}

        periodos = resp.json() if isinstance(resp.json(), list) else resp.json().get('periods', [])
        return {'ok': True, 'periodos': periodos[:6]}  # últimos 6 períodos
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


def obter_faturamento(token_ml: str, user_id: str, periodo_key: str = "") -> dict:
    """
    Obtém resumo de faturamento de um período.
    Se periodo_key vazio, tenta o período atual.
    """
    if not token_ml or not user_id:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        # ── 1. Descobre período ────────────────────────────────────────
        if not periodo_key:
            per_resp = listar_periodos(token_ml)
            if not per_resp.get('ok') or not per_resp.get('periodos'):
                # Fallback: tenta buscar via movimentos de conta
                return _fallback_extrato(token_ml, user_id)
            # Primeiro período = mais recente
            periodo_key = per_resp['periodos'][0].get('key', '')
            if not periodo_key:
                return _fallback_extrato(token_ml, user_id)

        # ── 2. Busca resumo do período ────────────────────────────────
        resp = requests.get(
            f'https://api.mercadolibre.com/billing/integration/periods/key/{periodo_key}/summary/details',
            headers=headers, timeout=20
        )

        if resp.status_code == 404:
            return _fallback_extrato(token_ml, user_id)
        if resp.status_code == 401:
            return {'ok': False, 'erro': 'Token expirado. Reconecte.'}
        if resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão para ler faturamento.'}
        if resp.status_code != 200:
            return _fallback_extrato(token_ml, user_id)

        summary = resp.json()

        # ── 3. Processa dados ─────────────────────────────────────────
        linhas = []
        total_cobrado = 0.0
        total_credito = 0.0

        # O formato varia — tenta diferentes estruturas
        grupos = summary if isinstance(summary, list) else summary.get('groups', summary.get('details', []))

        for grupo in (grupos or []):
            nome = grupo.get('label', grupo.get('name', grupo.get('group', '')))
            valor = float(grupo.get('total', grupo.get('amount', 0)) or 0)
            tipo = 'credito' if valor > 0 else 'debito'
            if valor < 0:
                total_cobrado += abs(valor)
            else:
                total_credito += valor

            if nome and valor != 0:
                linhas.append({
                    'nome': nome,
                    'valor': round(valor, 2),
                    'tipo': tipo,
                    'cor': '#4ade80' if valor > 0 else '#f87171',
                })

        saldo = total_credito - total_cobrado

        return {
            'ok': True,
            'periodo_key': periodo_key,
            'total_cobrado': round(total_cobrado, 2),
            'total_credito': round(total_credito, 2),
            'saldo': round(saldo, 2),
            'linhas': linhas,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }

    except Exception as e:
        logger.error(f"❌ Erro em obter_faturamento: {e}")
        return _fallback_extrato(token_ml, user_id)


def _fallback_extrato(token_ml: str, user_id: str) -> dict:
    """
    Fallback: usa /users/{user_id}/account/balance para saldo da conta ML.
    """
    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}
    try:
        resp = requests.get(
            f'https://api.mercadolibre.com/users/{user_id}/mercadopago/account/balance',
            headers=headers, timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            saldo = data.get('available_balance', data.get('total', 0))
            return {
                'ok': True,
                'periodo_key': 'conta',
                'total_cobrado': 0,
                'total_credito': float(saldo or 0),
                'saldo': float(saldo or 0),
                'linhas': [{'nome': 'Saldo disponível MercadoPago', 'valor': float(saldo or 0), 'tipo': 'credito', 'cor': '#4ade80'}],
                'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
                'nota': 'Dados do saldo MP (faturamento ML requer permissão billing)',
            }
    except Exception:
        pass

    return {
        'ok': False,
        'erro': 'Faturamento indisponível. Verifique se o app tem permissão "read_billing" no ML.',
    }
