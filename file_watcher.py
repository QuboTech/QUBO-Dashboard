"""
file_watcher.py - Monitor de Pasta com Auto-Processamento de PDFs
=================================================================
Monitora uma pasta local. Quando detecta PDF novo:
1. Extrai produtos com IA (multi_extractor)
2. Salva no banco (local SQLite ou Supabase via DATABASE_URL)
3. Renomeia o PDF para .enviado (nunca reprocessa)

Uso:
    python file_watcher.py                  # roda uma vez e sai
    python file_watcher.py --watch          # fica monitorando continuamente

Autor: Claude para QUBO
Data: 2026-04
"""

import os
import sys
import time
import logging
import sqlite3
import json
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

PASTA = os.getenv('PASTA_MONITORADA', '')
DATABASE_URL = os.getenv('DATABASE_URL', '')
DB_PATH = Path('data/viabilidade.db')
EXTENSAO_ENVIADO = '.enviado'


def get_conn():
    """Conexão com banco correto (Postgres ou SQLite)"""
    if DATABASE_URL and DATABASE_URL.startswith('postgresql'):
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        DB_PATH.parent.mkdir(exist_ok=True)
        return sqlite3.connect(DB_PATH)


def garantir_tabela():
    conn = get_conn()
    cur = conn.cursor()
    if DATABASE_URL and DATABASE_URL.startswith('postgresql'):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id SERIAL PRIMARY KEY,
                codigo TEXT DEFAULT '',
                fornecedor TEXT DEFAULT '',
                descricao TEXT DEFAULT '',
                custo REAL DEFAULT 0,
                preco_ml REAL DEFAULT 0,
                taxa_categoria REAL DEFAULT 0.165,
                peso_kg REAL DEFAULT 0,
                custo_embalagem REAL DEFAULT 0,
                custo_frete REAL DEFAULT 0,
                taxa_fixa_ml REAL DEFAULT 0,
                imposto_valor REAL DEFAULT 0,
                custo_total REAL DEFAULT 0,
                margem_percentual REAL DEFAULT 0,
                margem_reais REAL DEFAULT 0,
                viavel INTEGER DEFAULT 0,
                link_ml TEXT DEFAULT '',
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
                pagina_origem INTEGER DEFAULT 0,
                data_analise TEXT DEFAULT '',
                arquivo_origem TEXT DEFAULT ''
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT, fornecedor TEXT, descricao TEXT, custo REAL,
                data_analise TEXT, arquivo_origem TEXT, pagina_origem INTEGER DEFAULT 0
            )
        """)
    conn.commit()
    conn.close()


def salvar_produtos(produtos, fornecedor, nome_arquivo):
    """Salva lista de produtos no banco"""
    conn = get_conn()
    cur = conn.cursor()
    salvos = 0
    
    is_pg = DATABASE_URL and DATABASE_URL.startswith('postgresql')
    ph = '%s' if is_pg else '?'

    for p in produtos:
        try:
            cur.execute(
                f"""INSERT INTO produtos (codigo, fornecedor, descricao, custo, data_analise, arquivo_origem)
                   VALUES ({ph},{ph},{ph},{ph},{ph},{ph})""",
                (p.codigo, fornecedor, p.descricao, p.preco_unitario,
                 datetime.now().isoformat(), nome_arquivo)
            )
            salvos += 1
        except Exception as e:
            logger.warning(f"   ⚠️ Erro ao salvar produto: {e}")

    conn.commit()
    conn.close()
    return salvos


def processar_pdf(caminho_pdf: Path) -> bool:
    """
    Processa um PDF:
    1. Extrai produtos
    2. Salva no banco
    3. Renomeia para .enviado
    Retorna True se sucesso.
    """
    try:
        from multi_extractor import MultiExtractor
        extractor = MultiExtractor()
    except Exception as e:
        logger.error(f"❌ Erro ao carregar extrator: {e}")
        return False

    # Fornecedor = nome do arquivo sem extensão
    fornecedor = caminho_pdf.stem
    nome_arquivo = caminho_pdf.name

    logger.info(f"📄 Processando: {nome_arquivo}")

    try:
        produtos, info = extractor.extrair_de_pdf(str(caminho_pdf), fornecedor)
    except Exception as e:
        logger.error(f"   ❌ Erro na extração: {e}")
        return False

    if not produtos:
        logger.warning(f"   ⚠️ Nenhum produto encontrado em {nome_arquivo}")
        # Mesmo sem produtos, renomeia para não tentar de novo
        _renomear_enviado(caminho_pdf)
        return True

    salvos = salvar_produtos(produtos, fornecedor, nome_arquivo)
    logger.info(f"   ✅ {salvos} produtos salvos no banco")

    # Renomeia para .enviado
    _renomear_enviado(caminho_pdf)
    return True


def _renomear_enviado(caminho: Path):
    """Renomeia arquivo para .enviado para não reprocessar"""
    novo_nome = caminho.with_suffix(EXTENSAO_ENVIADO)
    try:
        caminho.rename(novo_nome)
        logger.info(f"   📁 Renomeado → {novo_nome.name}")
    except Exception as e:
        logger.warning(f"   ⚠️ Não foi possível renomear: {e}")


def listar_pdfs_pendentes(pasta: Path):
    """Lista PDFs que ainda não foram processados (.enviado)"""
    if not pasta.exists():
        logger.error(f"❌ Pasta não encontrada: {pasta}")
        return []
    
    # Busca PDFs em subpastas também
    pdfs = list(pasta.rglob('*.pdf')) + list(pasta.rglob('*.PDF'))
    
    # Filtra os que já foram enviados (verificação extra por segurança)
    pendentes = [p for p in pdfs if not p.with_suffix(EXTENSAO_ENVIADO).exists()]
    
    return pendentes


def rodar_uma_vez(pasta: Path):
    """Processa todos os PDFs pendentes e sai"""
    garantir_tabela()
    pdfs = listar_pdfs_pendentes(pasta)
    
    if not pdfs:
        logger.info("✅ Nenhum PDF pendente encontrado.")
        return
    
    logger.info(f"📂 {len(pdfs)} PDF(s) pendente(s) em {pasta}")
    
    ok = 0
    erros = 0
    for pdf in pdfs:
        if processar_pdf(pdf):
            ok += 1
        else:
            erros += 1
    
    logger.info(f"\n🎉 Concluído: {ok} processados, {erros} erros")


def rodar_monitorando(pasta: Path, intervalo: int = 30):
    """Fica monitorando a pasta continuamente"""
    garantir_tabela()
    logger.info(f"👁️  Monitorando: {pasta}")
    logger.info(f"⏱️  Verificando a cada {intervalo}s — CTRL+C para parar\n")
    
    while True:
        try:
            pdfs = listar_pdfs_pendentes(pasta)
            if pdfs:
                logger.info(f"🆕 {len(pdfs)} PDF(s) novo(s) detectado(s)!")
                for pdf in pdfs:
                    processar_pdf(pdf)
            time.sleep(intervalo)
        except KeyboardInterrupt:
            logger.info("\n⏹️  Monitoramento encerrado.")
            break


def main():
    parser = argparse.ArgumentParser(description='Monitor de PDFs QUBO')
    parser.add_argument('--watch', action='store_true',
                        help='Monitorar continuamente (default: processa uma vez e sai)')
    parser.add_argument('--pasta', type=str, default=PASTA,
                        help='Pasta a monitorar (default: PASTA_MONITORADA do .env)')
    parser.add_argument('--intervalo', type=int, default=30,
                        help='Segundos entre verificações no modo watch (default: 30)')
    args = parser.parse_args()

    if not args.pasta:
        logger.error("❌ Configure PASTA_MONITORADA no .env ou use --pasta")
        sys.exit(1)

    pasta = Path(args.pasta)
    banco = 'Postgres (Supabase)' if DATABASE_URL else 'SQLite local'
    logger.info(f"🗄️  Banco: {banco}")

    if args.watch:
        rodar_monitorando(pasta, args.intervalo)
    else:
        rodar_uma_vez(pasta)


if __name__ == '__main__':
    main()
