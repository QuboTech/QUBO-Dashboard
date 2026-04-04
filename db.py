"""
db.py - Camada de banco de dados com suporte SQLite (local) e Postgres (Render/Supabase)
Detecta automaticamente o ambiente via variável DATABASE_URL.
"""
import os
import sqlite3
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "")
USAR_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql"))

DB_PATH = Path("data/viabilidade.db")


def get_conn():
    """
    Retorna conexão com o banco correto.
    - LOCAL: SQLite (data/viabilidade.db)
    - RENDER: Postgres (Supabase via DATABASE_URL)
    """
    if USAR_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        DB_PATH.parent.mkdir(exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def existe_banco():
    """Verifica se o banco existe e tem a tabela produtos"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        if USAR_POSTGRES:
            cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'produtos')")
            existe = cur.fetchone()[0]
        else:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='produtos'")
            existe = bool(cur.fetchone())
        conn.close()
        return existe
    except Exception:
        return False


def garantir_schema():
    """Cria/atualiza o schema do banco"""
    conn = get_conn()
    cur = conn.cursor()

    if USAR_POSTGRES:
        # Postgres — cria tabela se não existir
        cur.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id SERIAL PRIMARY KEY,
                codigo TEXT DEFAULT '',
                fornecedor TEXT DEFAULT '',
                descricao TEXT DEFAULT '',
                custo REAL DEFAULT 0,
                preco_ml REAL DEFAULT 0,
                taxa_categoria REAL DEFAULT 0.165,
                custo_frete REAL DEFAULT 0,
                taxa_fixa_ml REAL DEFAULT 0,
                peso_kg REAL DEFAULT 0,
                custo_embalagem REAL DEFAULT 0,
                imposto_valor REAL DEFAULT 0,
                custo_total REAL DEFAULT 0,
                margem_percentual REAL DEFAULT 0,
                margem_reais REAL DEFAULT 0,
                viavel INTEGER DEFAULT 0,
                link_ml TEXT DEFAULT '',
                notas TEXT DEFAULT '',
                pagina_origem INTEGER DEFAULT 0,
                tipo_anuncio TEXT DEFAULT 'classico',
                escolhido INTEGER DEFAULT 0,
                custo_full REAL DEFAULT 0,
                custo_ads REAL DEFAULT 0,
                promo_percentual REAL DEFAULT 0,
                margem_alvo REAL DEFAULT 25,
                preco_ideal REAL DEFAULT 0,
                preco_final REAL DEFAULT 0,
                lucro_final REAL DEFAULT 0,
                margem_final REAL DEFAULT 0,
                data_analise TEXT DEFAULT '',
                arquivo_origem TEXT DEFAULT ''
            )
        """)
    else:
        # SQLite — cria tabela base
        cur.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT, fornecedor TEXT, descricao TEXT, custo REAL,
                data_analise TEXT, arquivo_origem TEXT, pagina_origem INTEGER DEFAULT 0
            )
        """)
        # Adiciona colunas novas se não existirem
        cur.execute("PRAGMA table_info(produtos)")
        existentes = {row[1] for row in cur.fetchall()}
        novas = {
            'preco_ml': 'REAL DEFAULT 0',
            'taxa_categoria': 'REAL DEFAULT 0.165',
            'custo_frete': 'REAL DEFAULT 0',
            'taxa_fixa_ml': 'REAL DEFAULT 0',
            'peso_kg': 'REAL DEFAULT 0',
            'custo_embalagem': 'REAL DEFAULT 0',
            'imposto_valor': 'REAL DEFAULT 0',
            'custo_total': 'REAL DEFAULT 0',
            'margem_percentual': 'REAL DEFAULT 0',
            'margem_reais': 'REAL DEFAULT 0',
            'viavel': 'INTEGER DEFAULT 0',
            'link_ml': "TEXT DEFAULT ''",
            'notas': "TEXT DEFAULT ''",
            'tipo_anuncio': "TEXT DEFAULT 'classico'",
            'escolhido': 'INTEGER DEFAULT 0',
            'custo_full': 'REAL DEFAULT 0',
            'custo_ads': 'REAL DEFAULT 0',
            'promo_percentual': 'REAL DEFAULT 0',
            'margem_alvo': 'REAL DEFAULT 25',
            'preco_ideal': 'REAL DEFAULT 0',
            'preco_final': 'REAL DEFAULT 0',
            'lucro_final': 'REAL DEFAULT 0',
            'margem_final': 'REAL DEFAULT 0',
        }
        for col, tipo in novas.items():
            if col not in existentes:
                try:
                    cur.execute(f"ALTER TABLE produtos ADD COLUMN {col} {tipo}")
                except Exception:
                    pass

    conn.commit()
    conn.close()


def dict_row(cur, row):
    """Converte row para dict compatível com SQLite e Postgres"""
    if USAR_POSTGRES:
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))
    else:
        return dict(row)


def placeholder():
    """Retorna placeholder correto para cada banco"""
    return "%s" if USAR_POSTGRES else "?"


print(f"🗄️  Banco: {'Postgres (Supabase)' if USAR_POSTGRES else 'SQLite (local)'}")
