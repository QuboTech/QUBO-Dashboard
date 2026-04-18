"""
agente_espiao.py - Mini-Metrify integrado
==========================================
Espionagem de anúncios públicos do ML (todos os sellers, não só os seus).

Funcionalidades:
  - spy_anuncio()        → snapshot pontual de qualquer MLBxxxx
  - ranking_busca()      → top vendas de uma busca
  - ranking_categoria()  → top vendas de uma categoria
  - adicionar_watch()    → começa a monitorar um anúncio
  - delta_anuncio()      → vendas no período (entre snapshots)
  - snapshot_cron()      → rotina diária (pode ser chamada por cron)

Tabelas criadas:
  - ml_watchlist_itens   (quais anúncios estamos monitorando)
  - ml_snapshots_itens   (histórico de sold_quantity + price)

Benchmark do vendedor: R$ 10 / visita (1000 visitas → R$ 10k em vendas).

Autor: Claude para QUBO
Data: 2026-04
"""

import json
import logging
import re
import requests
from datetime import datetime, timedelta

from db import get_conn, USAR_POSTGRES

logger = logging.getLogger(__name__)

# Benchmark do vendedor: se receita/visita >= 10, meta atingida.
BENCHMARK_REAIS_POR_VISITA = 10.0


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────────────────────────────────────
def garantir_tabelas():
    """Cria ml_watchlist_itens e ml_snapshots_itens se não existirem (multi-tenant)."""
    try:
        conn = get_conn(); cur = conn.cursor()
        if USAR_POSTGRES:
            # Tabela nova já com tenant_id
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ml_watchlist_itens (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT DEFAULT 'qubo',
                    item_id TEXT NOT NULL,
                    apelido TEXT,
                    titulo TEXT,
                    seller_id TEXT,
                    added_ts BIGINT,
                    ativo INTEGER DEFAULT 1
                )
            """)
            # Upgrade de schema existente
            try: cur.execute("ALTER TABLE ml_watchlist_itens ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'qubo'")
            except Exception: pass
            try: cur.execute("ALTER TABLE ml_watchlist_itens ADD COLUMN IF NOT EXISTS id SERIAL")
            except Exception: pass
            # Tenta remover PK antigo (item_id) e recriar em composite unique
            try: cur.execute("ALTER TABLE ml_watchlist_itens DROP CONSTRAINT IF EXISTS ml_watchlist_itens_pkey")
            except Exception: pass
            try: cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_watch_tenant_item ON ml_watchlist_itens(tenant_id, item_id)")
            except Exception: pass

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ml_snapshots_itens (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT DEFAULT 'qubo',
                    item_id TEXT,
                    ts BIGINT,
                    data TEXT,
                    sold_quantity INTEGER,
                    available_quantity INTEGER,
                    price NUMERIC,
                    status TEXT,
                    seller_id TEXT,
                    extra TEXT
                )
            """)
            try: cur.execute("ALTER TABLE ml_snapshots_itens ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'qubo'")
            except Exception: pass
            cur.execute("CREATE INDEX IF NOT EXISTS idx_snap_tenant_item_ts ON ml_snapshots_itens(tenant_id, item_id, ts)")
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ml_watchlist_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT DEFAULT 'qubo',
                    item_id TEXT NOT NULL,
                    apelido TEXT, titulo TEXT, seller_id TEXT,
                    added_ts INTEGER, ativo INTEGER DEFAULT 1
                )
            """)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_watch_tenant_item ON ml_watchlist_itens(tenant_id, item_id)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ml_snapshots_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT DEFAULT 'qubo',
                    item_id TEXT, ts INTEGER, data TEXT,
                    sold_quantity INTEGER, available_quantity INTEGER,
                    price REAL, status TEXT, seller_id TEXT, extra TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_snap_tenant_item_ts ON ml_snapshots_itens(tenant_id, item_id, ts)")
        conn.commit(); conn.close()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao criar tabelas espião: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _extrair_mlb_id(texto: str) -> str:
    """Aceita 'MLB1234', 'MLB-1234', URL completo — retorna 'MLB1234'."""
    if not texto:
        return ''
    t = texto.strip().upper()
    # match MLB seguido de dígitos (com ou sem hífen)
    m = re.search(r'MLB-?(\d+)', t)
    if m:
        return 'MLB' + m.group(1)
    return ''


def _fmt_data(ts: int) -> str:
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%d/%m/%Y %H:%M')
    except Exception:
        return ''


def _headers(token: str = '') -> dict:
    h = {'Accept': 'application/json'}
    if token:
        h['Authorization'] = f'Bearer {token}'
    return h


# ─────────────────────────────────────────────────────────────────────────────
# SPY — detalhes de um anúncio + snapshot automático
# ─────────────────────────────────────────────────────────────────────────────
def spy_anuncio(item_id_ou_url: str, token: str = '', tenant_id: str = 'qubo') -> dict:
    """Consulta anúncio público + registra snapshot automaticamente."""
    item_id = _extrair_mlb_id(item_id_ou_url)
    if not item_id:
        return {'ok': False, 'erro': 'Informe um MLB válido (ex: MLB1234567890 ou URL do anúncio)'}

    try:
        # ── Item ────────────────────────────────────────────────────────
        r = requests.get(
            f'https://api.mercadolibre.com/items/{item_id}',
            headers=_headers(token), timeout=15
        )
        if r.status_code == 404:
            return {'ok': False, 'erro': f'Anúncio {item_id} não encontrado'}
        if r.status_code != 200:
            return {'ok': False, 'erro': f'Erro {r.status_code} ao consultar item'}
        item = r.json()

        sold = int(item.get('sold_quantity') or 0)
        preco = float(item.get('price') or 0)
        estoque = int(item.get('available_quantity') or 0)
        seller_id = str(item.get('seller_id') or '')
        categoria = item.get('category_id', '')
        titulo = item.get('title', '')
        thumb = item.get('thumbnail', '')
        link = item.get('permalink', '')
        status = item.get('status', '')
        cond = item.get('condition', '')
        tipo = item.get('listing_type_id', '')

        # ── Vendedor ────────────────────────────────────────────────────
        vendedor = {'apelido': '', 'nivel': '', 'transacoes': 0, 'cidade': ''}
        if seller_id:
            try:
                rs = requests.get(
                    f'https://api.mercadolibre.com/users/{seller_id}',
                    headers=_headers(token), timeout=10
                )
                if rs.status_code == 200:
                    s = rs.json()
                    rep = s.get('seller_reputation', {}) or {}
                    trans = rep.get('transactions', {}) or {}
                    ratings = trans.get('ratings', {}) or {}
                    vendedor = {
                        'apelido': s.get('nickname', ''),
                        'nivel': rep.get('level_id', ''),
                        'power': rep.get('power_seller_status', '') or '',
                        'transacoes': trans.get('total', 0),
                        'positivas_pct': round((ratings.get('positive', 0) or 0) * 100, 1),
                        'cidade': (s.get('address', {}) or {}).get('city', ''),
                    }
            except Exception:
                pass

        # ── Categoria (nome) ─────────────────────────────────────────────
        cat_nome = ''
        if categoria:
            try:
                rc = requests.get(
                    f'https://api.mercadolibre.com/categories/{categoria}',
                    headers=_headers(token), timeout=8
                )
                if rc.status_code == 200:
                    cat_nome = rc.json().get('name', '')
            except Exception:
                pass

        # ── Snapshot automático ─────────────────────────────────────────
        _salvar_snapshot(item_id, sold, estoque, preco, status, seller_id, tenant_id)

        # ── Delta (se já estava sendo monitorado) ───────────────────────
        delta = _calcular_delta(item_id, sold, preco, dias=7, tenant_id=tenant_id)

        # ── Receita estimada ────────────────────────────────────────────
        receita_acum = round(sold * preco, 2)
        receita_7d = round((delta.get('vendas_7d', 0) or 0) * preco, 2) if delta.get('tem_historico') else None

        # ── Watchlist check ─────────────────────────────────────────────
        monitorado = _esta_monitorado(item_id, tenant_id)

        return {
            'ok': True,
            'item_id': item_id,
            'titulo': titulo,
            'thumbnail': thumb,
            'link': link,
            'status': status,
            'condicao': cond,
            'tipo_anuncio': tipo,
            'category_id': categoria,
            'categoria_nome': cat_nome,
            'preco': preco,
            'vendas_total': sold,
            'estoque': estoque,
            'receita_acum': receita_acum,
            'vendedor': vendedor,
            'delta': delta,
            'receita_7d': receita_7d,
            'monitorado': monitorado,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }
    except Exception as e:
        logger.error(f"❌ spy_anuncio: {e}")
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# SNAPSHOTS + DELTAS
# ─────────────────────────────────────────────────────────────────────────────
def _salvar_snapshot(item_id: str, sold: int, estoque: int, preco: float,
                     status: str, seller_id: str, tenant_id: str = 'qubo'):
    """Registra um ponto histórico (máx 1 por dia por item, por tenant)."""
    try:
        garantir_tabelas()
        ts = int(datetime.utcnow().timestamp())
        data = datetime.utcnow().strftime('%Y-%m-%d')
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"

        # Evita duplicar snapshot no mesmo dia (por tenant)
        cur.execute(
            f"SELECT id FROM ml_snapshots_itens WHERE tenant_id={ph} AND item_id={ph} AND data={ph}",
            (tenant_id, item_id, data)
        )
        existe = cur.fetchone()
        if existe:
            # Atualiza o snapshot do dia (último valor vence)
            cur.execute(f"""
                UPDATE ml_snapshots_itens
                SET ts={ph}, sold_quantity={ph}, available_quantity={ph},
                    price={ph}, status={ph}, seller_id={ph}
                WHERE id={ph}
            """, (ts, sold, estoque, preco, status, seller_id, existe[0]))
        else:
            cur.execute(f"""
                INSERT INTO ml_snapshots_itens
                (tenant_id, item_id, ts, data, sold_quantity, available_quantity, price, status, seller_id, extra)
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """, (tenant_id, item_id, ts, data, sold, estoque, preco, status, seller_id, ''))
        conn.commit(); conn.close()
    except Exception as e:
        logger.warning(f"⚠️ snapshot falhou ({item_id}): {e}")


def _calcular_delta(item_id: str, sold_agora: int, preco_agora: float, dias: int = 7, tenant_id: str = 'qubo') -> dict:
    """Compara com snapshot de N dias atrás. Retorna tem_historico + deltas."""
    try:
        garantir_tabelas()
        ts_alvo = int((datetime.utcnow() - timedelta(days=dias)).timestamp())
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"

        # Snapshot mais próximo de (hoje - N dias)
        cur.execute(f"""
            SELECT sold_quantity, price, ts FROM ml_snapshots_itens
            WHERE tenant_id={ph} AND item_id={ph} AND ts <= {ph}
            ORDER BY ts DESC LIMIT 1
        """, (tenant_id, item_id, ts_alvo))
        r = cur.fetchone()

        # Snapshot mais antigo (para gráfico)
        cur.execute(f"""
            SELECT MIN(ts), COUNT(*) FROM ml_snapshots_itens WHERE tenant_id={ph} AND item_id={ph}
        """, (tenant_id, item_id))
        r_min = cur.fetchone()
        total_snaps = r_min[1] if r_min else 0
        primeira_ts = r_min[0] if r_min else None

        conn.close()

        if not r:
            return {
                'tem_historico': total_snaps > 1,
                'total_snaps': total_snaps,
                'primeiro_snap': _fmt_data(primeira_ts) if primeira_ts else '',
                f'vendas_{dias}d': 0,
                f'preco_diff_{dias}d': 0,
                'aviso': f'Sem snapshot de {dias} dias atrás ainda — monitor precisa rodar mais tempo',
            }

        sold_antes = int(r[0] or 0)
        preco_antes = float(r[1] or 0)
        return {
            'tem_historico': True,
            'total_snaps': total_snaps,
            'primeiro_snap': _fmt_data(primeira_ts),
            f'vendas_{dias}d': max(0, sold_agora - sold_antes),
            f'preco_diff_{dias}d': round(preco_agora - preco_antes, 2),
            f'preco_diff_pct_{dias}d': round(((preco_agora - preco_antes) / preco_antes) * 100, 2) if preco_antes else 0,
            f'preco_anterior_{dias}d': preco_antes,
        }
    except Exception as e:
        return {'tem_historico': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# WATCHLIST
# ─────────────────────────────────────────────────────────────────────────────
def _esta_monitorado(item_id: str, tenant_id: str = 'qubo') -> bool:
    try:
        garantir_tabelas()
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"SELECT ativo FROM ml_watchlist_itens WHERE tenant_id={ph} AND item_id={ph}", (tenant_id, item_id))
        r = cur.fetchone(); conn.close()
        return bool(r and r[0])
    except Exception:
        return False


def adicionar_watch(item_id_ou_url: str, apelido: str = '', token: str = '', tenant_id: str = 'qubo') -> dict:
    item_id = _extrair_mlb_id(item_id_ou_url)
    if not item_id:
        return {'ok': False, 'erro': 'MLB inválido'}
    try:
        garantir_tabelas()
        # Busca título para facilitar lembrar
        titulo = apelido
        seller_id = ''
        try:
            r = requests.get(
                f'https://api.mercadolibre.com/items/{item_id}?attributes=id,title,seller_id',
                headers=_headers(token), timeout=10
            )
            if r.status_code == 200:
                j = r.json()
                if not titulo:
                    titulo = j.get('title', '')[:80]
                seller_id = str(j.get('seller_id') or '')
        except Exception:
            pass

        ts = int(datetime.utcnow().timestamp())
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"SELECT id FROM ml_watchlist_itens WHERE tenant_id={ph} AND item_id={ph}", (tenant_id, item_id))
        if cur.fetchone():
            cur.execute(f"UPDATE ml_watchlist_itens SET ativo=1, apelido={ph}, titulo={ph} WHERE tenant_id={ph} AND item_id={ph}",
                        (apelido, titulo, tenant_id, item_id))
            acao = 'reativado'
        else:
            cur.execute(f"""
                INSERT INTO ml_watchlist_itens (tenant_id, item_id, apelido, titulo, seller_id, added_ts, ativo)
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph},1)
            """, (tenant_id, item_id, apelido, titulo, seller_id, ts))
            acao = 'adicionado'
        conn.commit(); conn.close()

        # Primeiro snapshot imediato
        spy_anuncio(item_id, token, tenant_id)

        return {'ok': True, 'item_id': item_id, 'titulo': titulo, 'acao': acao}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


def remover_watch(item_id: str, tenant_id: str = 'qubo') -> dict:
    item_id = _extrair_mlb_id(item_id)
    if not item_id:
        return {'ok': False, 'erro': 'MLB inválido'}
    try:
        garantir_tabelas()
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"UPDATE ml_watchlist_itens SET ativo=0 WHERE tenant_id={ph} AND item_id={ph}", (tenant_id, item_id))
        conn.commit(); conn.close()
        return {'ok': True, 'item_id': item_id}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


def listar_watchlist(token: str = '', refresh: bool = True, tenant_id: str = 'qubo') -> dict:
    """Lista itens monitorados + snapshot mais recente + deltas (escopado por tenant)."""
    try:
        garantir_tabelas()
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"""
            SELECT item_id, apelido, titulo, seller_id, added_ts
            FROM ml_watchlist_itens WHERE tenant_id={ph} AND ativo=1
            ORDER BY added_ts DESC
        """, (tenant_id,))
        rows = cur.fetchall()
        conn.close()

        itens = []
        for r in rows:
            item_id, apelido, titulo, seller_id, added_ts = r[0], r[1], r[2], r[3], r[4]

            # Refresh: puxa dado atual do ML e salva snapshot novo
            atual = {'sold_quantity': 0, 'price': 0, 'available_quantity': 0}
            if refresh:
                try:
                    resp = requests.get(
                        f'https://api.mercadolibre.com/items/{item_id}?attributes=sold_quantity,price,available_quantity,status,permalink,thumbnail,title',
                        headers=_headers(token), timeout=8
                    )
                    if resp.status_code == 200:
                        atual = resp.json()
                        _salvar_snapshot(
                            item_id,
                            int(atual.get('sold_quantity') or 0),
                            int(atual.get('available_quantity') or 0),
                            float(atual.get('price') or 0),
                            atual.get('status', ''),
                            seller_id,
                            tenant_id,
                        )
                except Exception:
                    pass

            sold = int(atual.get('sold_quantity') or 0)
            preco = float(atual.get('price') or 0)
            delta7 = _calcular_delta(item_id, sold, preco, dias=7, tenant_id=tenant_id)
            delta30 = _calcular_delta(item_id, sold, preco, dias=30, tenant_id=tenant_id)

            itens.append({
                'item_id': item_id,
                'apelido': apelido or '',
                'titulo': titulo or atual.get('title', '') or item_id,
                'seller_id': seller_id,
                'adicionado_em': _fmt_data(added_ts),
                'sold_total': sold,
                'preco': preco,
                'estoque': int(atual.get('available_quantity') or 0),
                'status': atual.get('status', ''),
                'thumbnail': atual.get('thumbnail', ''),
                'link': atual.get('permalink', f'https://www.mercadolivre.com.br/{item_id}'),
                'vendas_7d': delta7.get('vendas_7d', 0),
                'vendas_30d': delta30.get('vendas_30d', 0),
                'preco_diff_7d': delta7.get('preco_diff_7d', 0),
                'tem_historico': delta7.get('tem_historico', False),
                'receita_7d': round((delta7.get('vendas_7d', 0) or 0) * preco, 2),
                'receita_30d': round((delta30.get('vendas_30d', 0) or 0) * preco, 2),
                'receita_acum': round(sold * preco, 2),
            })

        return {'ok': True, 'total': len(itens), 'itens': itens,
                'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M')}
    except Exception as e:
        return {'ok': False, 'erro': str(e), 'itens': []}


# ─────────────────────────────────────────────────────────────────────────────
# RANKINGS — Top vendas de busca / categoria
# ─────────────────────────────────────────────────────────────────────────────
def ranking_busca(query: str, limite: int = 30, token: str = '') -> dict:
    """Top N anúncios por sold_quantity de uma busca no ML."""
    if not query:
        return {'ok': False, 'erro': 'Busca vazia'}
    try:
        params = {'q': query, 'limit': 50}
        r = requests.get('https://api.mercadolibre.com/sites/MLB/search',
                         headers=_headers(token), params=params, timeout=15)
        if r.status_code != 200:
            return {'ok': False, 'erro': f'Erro {r.status_code}'}

        data = r.json()
        results = data.get('results', [])
        itens = _montar_ranking(results, limite)

        return {
            'ok': True,
            'query': query,
            'total_resultados_ml': data.get('paging', {}).get('total', 0),
            'retornados': len(itens),
            'itens': itens,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


def ranking_categoria(category_id: str, limite: int = 30, token: str = '') -> dict:
    """Top N anúncios de uma categoria ordenados por sold_quantity."""
    if not category_id:
        return {'ok': False, 'erro': 'category_id obrigatório'}
    try:
        params = {'category': category_id, 'sort': 'sold_quantity_desc', 'limit': 50}
        r = requests.get('https://api.mercadolibre.com/sites/MLB/search',
                         headers=_headers(token), params=params, timeout=15)
        if r.status_code != 200:
            # Fallback: sort padrão, reordenamos local
            params.pop('sort', None)
            r = requests.get('https://api.mercadolibre.com/sites/MLB/search',
                             headers=_headers(token), params=params, timeout=15)
            if r.status_code != 200:
                return {'ok': False, 'erro': f'Erro {r.status_code}'}

        data = r.json()
        results = data.get('results', [])

        # Nome da categoria
        cat_nome = ''
        try:
            rc = requests.get(f'https://api.mercadolibre.com/categories/{category_id}',
                              headers=_headers(token), timeout=8)
            if rc.status_code == 200:
                cat_nome = rc.json().get('name', '')
        except Exception:
            pass

        itens = _montar_ranking(results, limite)
        return {
            'ok': True,
            'category_id': category_id,
            'categoria_nome': cat_nome,
            'total_resultados_ml': data.get('paging', {}).get('total', 0),
            'retornados': len(itens),
            'itens': itens,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


def _montar_ranking(results: list, limite: int) -> list:
    """Ordena por sold_quantity desc, calcula receita estimada e formata."""
    itens = []
    for r in results:
        sold = int(r.get('sold_quantity') or 0)
        preco = float(r.get('price') or 0)
        seller = r.get('seller', {}) or {}
        itens.append({
            'item_id': r.get('id', ''),
            'titulo': (r.get('title') or '')[:100],
            'preco': preco,
            'vendas_total': sold,
            'receita_acum': round(sold * preco, 2),
            'estoque': int(r.get('available_quantity') or 0),
            'seller_id': str(seller.get('id', '')),
            'seller_apelido': seller.get('nickname', ''),
            'thumbnail': r.get('thumbnail', ''),
            'link': r.get('permalink', ''),
            'free_shipping': (r.get('shipping', {}) or {}).get('free_shipping', False),
            'condicao': r.get('condition', ''),
        })
    itens.sort(key=lambda x: -x['vendas_total'])
    return itens[:limite]


# ─────────────────────────────────────────────────────────────────────────────
# SNAPSHOT CRON — rotina diária (pode ser chamada por scheduler externo)
# ─────────────────────────────────────────────────────────────────────────────
def snapshot_cron(token: str = '', tenant_id: str = None) -> dict:
    """Atualiza snapshot de todos os itens da watchlist. Chamar 1×/dia.
    Se tenant_id=None, roda pra TODOS os tenants (modo batch global)."""
    try:
        garantir_tabelas()
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        if tenant_id:
            cur.execute(f"SELECT tenant_id, item_id FROM ml_watchlist_itens WHERE tenant_id={ph} AND ativo=1", (tenant_id,))
        else:
            cur.execute("SELECT tenant_id, item_id FROM ml_watchlist_itens WHERE ativo=1")
        rows = cur.fetchall()
        conn.close()
        ids = [(r[0], r[1]) for r in rows]

        ok = 0; erros = 0
        for tid, iid in ids:
            try:
                resp = requests.get(
                    f'https://api.mercadolibre.com/items/{iid}?attributes=sold_quantity,price,available_quantity,status,seller_id',
                    headers=_headers(token), timeout=10
                )
                if resp.status_code == 200:
                    j = resp.json()
                    _salvar_snapshot(
                        iid,
                        int(j.get('sold_quantity') or 0),
                        int(j.get('available_quantity') or 0),
                        float(j.get('price') or 0),
                        j.get('status', ''),
                        str(j.get('seller_id') or ''),
                        tid,
                    )
                    ok += 1
                else:
                    erros += 1
            except Exception:
                erros += 1

        return {'ok': True, 'total': len(ids), 'sucesso': ok, 'erros': erros,
                'executado_em': datetime.now().strftime('%d/%m/%Y %H:%M')}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}
