"""
ml_buscador.py - Integração Mercado Livre com OAuth Completo
==============================================================
- OAuth Authorization Code (login do usuário)
- Refresh automático de token (6h validade)
- Busca de produtos (search)
- Cálculo de taxas reais (listing_prices)
- Busca de preço médio

Autor: Claude para QUBO
Data: 2026-02
"""
import os
import json
import time
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

TOKEN_FILE = Path("data/ml_token.json")
TOKEN_FILE.parent.mkdir(exist_ok=True)


def _salvar_token_db(token_data: dict, tenant_id: str = 'qubo'):
    """Salva token no Supabase (1 row por tenant, id = tenant_slug)."""
    try:
        from db import get_conn, USAR_POSTGRES
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        if USAR_POSTGRES:
            cur.execute(f"""
                INSERT INTO ml_tokens (id, access_token, refresh_token, user_id, expires_at, salvo_em, tenant_id)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT (id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    user_id = EXCLUDED.user_id,
                    expires_at = EXCLUDED.expires_at,
                    salvo_em = EXCLUDED.salvo_em,
                    tenant_id = EXCLUDED.tenant_id
            """, (
                tenant_id,
                token_data.get('access_token'),
                token_data.get('refresh_token'),
                str(token_data.get('user_id', '')),
                token_data.get('expires_at'),
                token_data.get('salvo_em', datetime.now().isoformat()),
                tenant_id
            ))
        else:
            cur.execute(f"""
                INSERT OR REPLACE INTO ml_tokens (id, access_token, refresh_token, user_id, expires_at, salvo_em, tenant_id)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """, (
                tenant_id,
                token_data.get('access_token'),
                token_data.get('refresh_token'),
                str(token_data.get('user_id', '')),
                token_data.get('expires_at'),
                token_data.get('salvo_em', datetime.now().isoformat()),
                tenant_id
            ))
        conn.commit(); conn.close()
        logger.info(f"✅ ML: Token salvo no banco (tenant={tenant_id})")
    except Exception as e:
        logger.warning(f"⚠️ ML: Erro ao salvar token no banco: {e}")


def _carregar_token_db(tenant_id: str = 'qubo') -> dict:
    """Carrega token do banco para um tenant específico."""
    try:
        from db import get_conn, USAR_POSTGRES
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"SELECT access_token, refresh_token, user_id, expires_at FROM ml_tokens WHERE id = {ph}", (tenant_id,))
        row = cur.fetchone()
        # Fallback legacy: se não encontrou OU a linha existe porém sem access_token,
        # e for o tenant qubo, tenta a linha legada 'principal' (compat pré-multi-tenant).
        if tenant_id == 'qubo' and (not row or not row[0]):
            cur.execute(f"SELECT access_token, refresh_token, user_id, expires_at FROM ml_tokens WHERE id = {ph}", ('principal',))
            legacy = cur.fetchone()
            if legacy and legacy[0]:
                row = legacy
                logger.info("🟡 ML: token carregado via fallback 'principal' (migração principal→qubo ainda não aplicada)")
        conn.close()
        if row:
            return {
                'access_token': row[0],
                'refresh_token': row[1],
                'user_id': row[2],
                'expires_at': row[3]
            }
    except Exception as e:
        logger.warning(f"⚠️ ML: Erro ao carregar token do banco: {e}")
    return {}

CLIENT_ID = os.getenv("ML_CLIENT_ID", "5055987535998228")
CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET", "pUQOnnKVNgnPuwutwMKXxQ2LcoLPjYpz")
REDIRECT_URI = "https://www.google.com"
AUTH_URL = (
    f"https://auth.mercadolivre.com.br/authorization"
    f"?response_type=code"
    f"&client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URI}"
    f"&scope=offline_access+read+write"  # offline_access garante o refresh_token
)


class MLAuth:
    """Gerencia autenticação OAuth com Mercado Livre (por tenant)"""

    def __init__(self, tenant_id: str = 'qubo'):
        self.tenant_id = tenant_id or 'qubo'
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        self.user_id = None
        self._carregar_token()

    def _carregar_token(self):
        # 1. Tenta Supabase primeiro (persiste entre deploys)
        data = _carregar_token_db(self.tenant_id)
        
        # 2. Fallback para arquivo local
        if not data and TOKEN_FILE.exists():
            try:
                data = json.loads(TOKEN_FILE.read_text())
            except Exception:
                data = {}
        
        if data:
            try:
                self.access_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                self.user_id = data.get('user_id')
                exp = data.get('expires_at')
                if exp:
                    self.expires_at = datetime.fromisoformat(exp)
                if self.access_token:
                    logger.info(f"🟢 ML: Token carregado (user_id: {self.user_id})")
                    if self._token_expirado():
                        logger.info("🔄 ML: Token expirado, renovando automaticamente...")
                        self._renovar_token()
            except Exception as e:
                logger.warning(f"⚠️ ML: Erro ao carregar token: {e}")
    
    def _salvar_token(self, data):
        self.access_token = data.get('access_token')
        self.refresh_token = data.get('refresh_token')
        self.user_id = data.get('user_id')
        expires_in = data.get('expires_in', 21600)
        self.expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
        token_data = {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'user_id': self.user_id,
            'expires_at': self.expires_at.isoformat(),
            'salvo_em': datetime.now().isoformat()
        }
        # Salva no Supabase (persiste entre deploys) — escopado por tenant
        _salvar_token_db(token_data, self.tenant_id)
        # Salva também em arquivo local (fallback) — só pra Qubo (compat)
        if self.tenant_id == 'qubo':
            try:
                TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
            except Exception:
                pass
        logger.info(f"✅ ML: Token salvo no Supabase + local (expira em {expires_in//3600}h)")
    
    def _token_expirado(self):
        if not self.expires_at:
            # Sem data de expiração: assume válido e deixa a API decidir (401 se expirado)
            return False
        return datetime.now() >= self.expires_at

    def esta_autenticado(self):
        if not self.access_token:
            return False
        if self._token_expirado():
            if not self.refresh_token:
                # Sem refresh_token: token expirou mas não dá pra renovar → pede novo login
                logger.warning("⚠️ ML: Token expirado e sem refresh_token. Reconecte em ML Auth.")
                return False
            return self._renovar_token()
        return True
    
    def get_auth_url(self):
        return AUTH_URL
    
    def trocar_codigo(self, code):
        try:
            response = requests.post(
                'https://api.mercadolibre.com/oauth/token',
                headers={'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded'},
                data={
                    'grant_type': 'authorization_code',
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'code': code,
                    'redirect_uri': REDIRECT_URI
                },
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                self._salvar_token(data)
                return {'ok': True, 'user_id': data.get('user_id')}
            else:
                erro = response.json() if response.text else {}
                msg = erro.get('message', erro.get('error', f'Status {response.status_code}'))
                return {'ok': False, 'erro': msg}
        except Exception as e:
            return {'ok': False, 'erro': str(e)}
    
    def _renovar_token(self):
        if not self.refresh_token:
            return False
        try:
            response = requests.post(
                'https://api.mercadolibre.com/oauth/token',
                headers={'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded'},
                data={
                    'grant_type': 'refresh_token',
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'refresh_token': self.refresh_token
                },
                timeout=15
            )
            if response.status_code == 200:
                self._salvar_token(response.json())
                logger.info("✅ ML: Token renovado com sucesso")
                return True
            else:
                body = response.text[:200] if response.text else ''
                logger.warning(f"⚠️ ML: Falha ao renovar ({response.status_code}): {body}")
                # NÃO apaga o access_token — ele pode ainda ser válido (ex: refresh_token inválido)
                # Só marca como inválido se o servidor diz explicitamente que o access_token expirou (401)
                if response.status_code == 401:
                    self.access_token = None
                self.refresh_token = None  # refresh_token inválido, descarta
                return False
        except Exception as e:
            logger.error(f"❌ ML: Erro ao renovar: {e}")
            return False

    def get_headers(self):
        if self._token_expirado() and self.refresh_token:
            self._renovar_token()
        return {'Authorization': f'Bearer {self.access_token}', 'Accept': 'application/json'}


class MLBuscador:
    """Busca produtos e calcula taxas no Mercado Livre (tenant-aware)"""

    def __init__(self, tenant_id: str = 'qubo'):
        self.tenant_id = tenant_id or 'qubo'
        self.auth = MLAuth(tenant_id=self.tenant_id)
        self.base_url = "https://api.mercadolibre.com"
    
    def esta_autenticado(self):
        return self.auth.esta_autenticado()
    
    def get_auth_url(self):
        return self.auth.get_auth_url()
    
    def trocar_codigo(self, code):
        return self.auth.trocar_codigo(code)
    
    def buscar_produto(self, termo, limite=10):
        if not self.auth.esta_autenticado():
            return {'encontrado': False, 'erro': 'Não autenticado no ML'}
        try:
            response = requests.get(
                f"{self.base_url}/sites/MLB/search",
                headers=self.auth.get_headers(),
                params={'q': termo, 'limit': limite},
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                resultados = data.get('results', [])
                return {
                    'encontrado': len(resultados) > 0,
                    'total': data.get('paging', {}).get('total', 0),
                    'resultados': [{
                        'id': r.get('id'), 'titulo': r.get('title'),
                        'preco': r.get('price', 0), 'link': r.get('permalink', ''),
                        'categoria': r.get('category_id', ''),
                        'frete_gratis': r.get('shipping', {}).get('free_shipping', False),
                    } for r in resultados]
                }
            elif response.status_code == 401:
                self.auth._renovar_token()
                return {'encontrado': False, 'erro': 'Token expirado, tente novamente'}
            else:
                return {'encontrado': False, 'erro': f'Erro {response.status_code}'}
        except Exception as e:
            return {'encontrado': False, 'erro': str(e)}
    
    def buscar_preco_medio(self, termo, limite=10):
        resultado = self.buscar_produto(termo, limite)
        if not resultado.get('encontrado'):
            return resultado
        precos = [r['preco'] for r in resultado['resultados'] if r['preco'] > 0]
        if not precos:
            return {'encontrado': False, 'erro': 'Sem preços válidos'}
        return {
            'encontrado': True,
            'preco_medio': round(sum(precos) / len(precos), 2),
            'preco_min': min(precos),
            'preco_max': max(precos),
            'total_encontrados': len(precos),
            'link_top': resultado['resultados'][0].get('link', ''),
            'categoria_top': resultado['resultados'][0].get('categoria', ''),
        }
    
    def calcular_taxa_ml(self, preco, category_id=None, listing_type='gold_special'):
        """Calcula taxa real do ML via API listing_prices"""
        if not self.auth.esta_autenticado():
            return {'ok': False, 'erro': 'Não autenticado'}
        try:
            params = {'price': preco, 'listing_type_id': listing_type, 'currency_id': 'BRL'}
            if category_id:
                params['category_id'] = category_id
            
            response = requests.get(
                f"{self.base_url}/sites/MLB/listing_prices",
                headers=self.auth.get_headers(),
                params=params,
                timeout=15
            )
            if response.status_code == 200:
                dados = response.json()
                if isinstance(dados, list):
                    for item in dados:
                        if item.get('listing_type_id') == listing_type:
                            return self._parsear_taxa(item, preco)
                    if dados:
                        return self._parsear_taxa(dados[0], preco)
                elif isinstance(dados, dict) and 'sale_fee_amount' in dados:
                    return self._parsear_taxa(dados, preco)
                return {'ok': False, 'erro': 'Formato inesperado'}
            elif response.status_code == 401:
                self.auth._renovar_token()
                return {'ok': False, 'erro': 'Token expirado'}
            else:
                return {'ok': False, 'erro': f'Erro {response.status_code}'}
        except Exception as e:
            return {'ok': False, 'erro': str(e)}
    
    def _parsear_taxa(self, item, preco):
        sale_fee = item.get('sale_fee_amount', 0)
        details = item.get('sale_fee_details', {})
        pct_fee = details.get('percentage_fee', 0)
        fixed_fee = details.get('fixed_fee', 0)
        if not pct_fee and sale_fee and preco:
            pct_fee = round((sale_fee / preco) * 100, 1)
        return {
            'ok': True,
            'listing_type': item.get('listing_type_id', ''),
            'listing_name': item.get('listing_type_name', ''),
            'taxa_total': round(sale_fee, 2),
            'taxa_percentual': pct_fee,
            'taxa_fixa': round(fixed_fee, 2),
        }
    
    def buscar_taxa_por_produto(self, termo, preco=None, listing_type='gold_special'):
        """Busca produto → pega categoria → calcula taxa real"""
        busca = self.buscar_produto(termo, limite=3)
        if not busca.get('encontrado'):
            return {'ok': False, 'erro': 'Não encontrado no ML'}
        categoria = busca['resultados'][0].get('categoria', '')
        if not preco:
            preco = busca['resultados'][0].get('preco', 100)
        taxa = self.calcular_taxa_ml(preco, category_id=categoria, listing_type=listing_type)
        if taxa.get('ok'):
            taxa['categoria'] = categoria
            taxa['produto_ref'] = busca['resultados'][0].get('titulo', '')
        return taxa
