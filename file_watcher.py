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
import argparse
import requests
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

PASTA            = os.getenv('PASTA_MONITORADA', '')
DASHBOARD_URL    = os.getenv('DASHBOARD_URL', 'https://qubo-dashboard.onrender.com')
WATCHER_API_KEY  = os.getenv('WATCHER_API_KEY', 'qubo-watcher-2026')
WATCHER_TENANT   = os.getenv('WATCHER_TENANT', 'gustavo')
EXTENSAO_ENVIADO = '.enviado'


def garantir_tabela():
    """No modo HTTP não é necessário criar tabela localmente."""
    pass


def salvar_produtos_via_http(caminho_pdf: Path) -> dict:
    """Envia o PDF para o endpoint do dashboard via HTTP. Retorna dict com ok/erro/salvos."""
    url = f"{DASHBOARD_URL.rstrip('/')}/api/watcher-upload"
    try:
        with open(caminho_pdf, 'rb') as f:
            resp = requests.post(
                url,
                headers={'X-API-Key': WATCHER_API_KEY},
                files={'arquivo': (caminho_pdf.name, f, 'application/pdf')},
                data={'tenant_id': WATCHER_TENANT},
                timeout=120
            )
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 401:
            return {'ok': False, 'erro': 'API key inválida — verifique WATCHER_API_KEY'}
        else:
            return {'ok': False, 'erro': f'HTTP {resp.status_code}: {resp.text[:200]}'}
    except requests.exceptions.Timeout:
        return {'ok': False, 'erro': 'Timeout — dashboard demorou mais de 120s (cold start?)'}
    except requests.exceptions.ConnectionError as e:
        return {'ok': False, 'erro': f'Sem conexão com o dashboard: {e}'}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


def processar_pdf(caminho_pdf: Path) -> bool:
    """
    Processa um PDF:
    1. Envia para o dashboard via HTTP (extração + salvamento no Supabase são feitos lá)
    2. Renomeia para .enviado
    Retorna True se sucesso ou se o arquivo foi processado (mesmo sem produtos).
    """
    nome_arquivo = caminho_pdf.name
    logger.info(f"📄 Enviando: {nome_arquivo} → {DASHBOARD_URL}")

    resultado = salvar_produtos_via_http(caminho_pdf)

    if resultado.get('ok'):
        salvos = resultado.get('produtos_extraidos', 0)
        provider = resultado.get('provider', '?')
        logger.info(f"   ✅ {salvos} produtos salvos (via {provider})")
        _renomear_enviado(caminho_pdf)
        return True
    else:
        erro = resultado.get('erro', 'erro desconhecido')
        # Sem produtos encontrados = arquivo inválido, renomeia para não retentar
        if 'Nenhum produto' in erro:
            logger.warning(f"   ⚠️ {erro}")
            _renomear_enviado(caminho_pdf)
            return True
        # Erros de conexão/timeout: não renomeia, vai tentar de novo
        logger.error(f"   ❌ {erro}")
        return False


def _renomear_enviado(caminho: Path):
    """Renomeia arquivo para <nome>.enviado para não reprocessar.

    Para arquivos sem extensão usa nome + '.enviado' (não with_suffix que
    substituiria nada e daria nome incorreto).
    """
    if caminho.suffix == '':
        novo_nome = caminho.with_name(caminho.name + EXTENSAO_ENVIADO)
    else:
        novo_nome = caminho.with_suffix(EXTENSAO_ENVIADO)
    try:
        caminho.rename(novo_nome)
        logger.info(f"   📁 Renomeado → {novo_nome.name}")
    except Exception as e:
        logger.warning(f"   ⚠️ Não foi possível renomear: {e}")


def _is_pdf(caminho: Path) -> bool:
    """Verifica se o arquivo é um PDF válido pelo magic header (%PDF)."""
    try:
        with open(caminho, 'rb') as f:
            return f.read(4) == b'%PDF'
    except Exception:
        return False


def listar_pdfs_pendentes(pasta: Path):
    """Lista PDFs que ainda não foram processados (.enviado).

    Detecta PDFs tanto pela extensão (.pdf/.PDF) quanto pelo magic header (%PDF)
    para arquivos sem extensão (ex: downloads automáticos).
    """
    if not pasta.exists():
        logger.error(f"❌ Pasta não encontrada: {pasta}")
        return []

    candidatos: list[Path] = []

    # 1) PDFs com extensão correta
    candidatos += list(pasta.rglob('*.pdf'))
    candidatos += list(pasta.rglob('*.PDF'))

    # 2) Arquivos SEM extensão — verifica magic header
    for f in pasta.rglob('*'):
        if f.is_file() and f.suffix == '' and _is_pdf(f):
            candidatos.append(f)

    # Remove duplicatas e arquivos já enviados
    vistos = set()
    pendentes = []
    for p in candidatos:
        if p in vistos:
            continue
        vistos.add(p)
        # Arquivo .enviado tem o mesmo nome com sufixo .enviado
        enviado = p.with_name(p.name + EXTENSAO_ENVIADO)
        if not enviado.exists() and not p.with_suffix(EXTENSAO_ENVIADO).exists():
            pendentes.append(p)

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
    logger.info(f"🌐 Dashboard: {DASHBOARD_URL}")
    logger.info(f"👤 Tenant: {WATCHER_TENANT}")

    if args.watch:
        rodar_monitorando(pasta, args.intervalo)
    else:
        rodar_uma_vez(pasta)


if __name__ == '__main__':
    main()
