"""
sistema_master.py - Sistema Master de Processamento V2
======================================================
Processa PDFs, extrai produtos, salva no banco
CORRIGIDO: Removidos imports mortos (Gemini), compatível com multi_extractor

Autor: Claude para QUBO
"""
import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import logging

# Importa módulos existentes
from pdf_processor import PDFProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Arquivo de controle de PDFs já processados
PROCESSADOS_FILE = Path("data/pdfs_processados.json")


def carregar_processados() -> set:
    """Carrega lista de PDFs já processados"""
    if PROCESSADOS_FILE.exists():
        try:
            with open(PROCESSADOS_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except:
            return set()
    return set()


def salvar_processados(processados: set):
    """Salva lista de PDFs processados"""
    PROCESSADOS_FILE.parent.mkdir(exist_ok=True)
    with open(PROCESSADOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(processados), f, indent=2, ensure_ascii=False)


class BancoDados:
    """Gerencia banco SQLite"""
    
    def __init__(self):
        self.db_path = Path("data/viabilidade.db")
        self.db_path.parent.mkdir(exist_ok=True)
        self.criar_tabelas()
    
    def criar_tabelas(self):
        """Cria estrutura do banco"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT,
                fornecedor TEXT,
                descricao TEXT,
                custo REAL,
                preco_ml REAL DEFAULT 0,
                taxa_categoria REAL DEFAULT 16.5,
                custo_frete REAL DEFAULT 0,
                margem_percentual REAL DEFAULT 0,
                margem_reais REAL DEFAULT 0,
                viavel INTEGER DEFAULT 0,
                link_ml TEXT DEFAULT '',
                notas TEXT DEFAULT '',
                data_analise TEXT,
                arquivo_origem TEXT,
                pagina_origem INTEGER DEFAULT 0
            )
        """)
        
        # Índices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_codigo ON produtos(codigo)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fornecedor ON produtos(fornecedor)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_viavel ON produtos(viavel)")
        
        conn.commit()
        conn.close()
    
    def salvar_produto(self, produto: dict):
        """Salva produto no banco"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO produtos 
            (codigo, fornecedor, descricao, custo, data_analise, arquivo_origem, pagina_origem)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            produto.get('codigo', ''),
            produto.get('fornecedor', ''),
            produto.get('descricao', ''),
            produto.get('custo', 0),
            datetime.now().isoformat(),
            produto.get('arquivo_origem', ''),
            produto.get('pagina_origem', 0)
        ))
        
        conn.commit()
        conn.close()
    
    def obter_estatisticas(self):
        """Estatísticas gerais"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM produtos")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT fornecedor) FROM produtos")
        fornecedores = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total': total,
            'fornecedores': fornecedores
        }


class SistemaMaster:
    """Sistema Master - Orquestra tudo"""
    
    def __init__(self):
        self.pdf_processor = PDFProcessor()
        self.db = BancoDados()
        self.processados = carregar_processados()
        
        print("\n" + "=" * 70)
        print("  🔥 SISTEMA MASTER - VIABILIDADE QUBO v2")
        print("=" * 70)
    
    def processar_pasta(self, pasta: str):
        """Processa todos PDFs da pasta (pula já processados)"""
        pasta_path = Path(pasta)
        
        if not pasta_path.exists():
            print(f"\n❌ Pasta não encontrada: {pasta}")
            return
        
        # Lista PDFs
        pdfs = list(pasta_path.rglob("*.pdf"))
        
        if not pdfs:
            print(f"\n⚠️  Nenhum PDF encontrado em: {pasta}")
            return
        
        # Filtra pendentes
        pendentes = [p for p in pdfs if str(p) not in self.processados]
        ja_processados = len(pdfs) - len(pendentes)
        
        print(f"\n📄 {len(pdfs)} PDFs encontrados")
        print(f"   ✅ {ja_processados} já processados (pulando)")
        print(f"   ⏳ {len(pendentes)} pendentes")
        print(f"📁 Pasta: {pasta}\n")
        
        if not pendentes:
            print("✅ Todos os PDFs já foram processados!")
            print("   Para reprocessar, delete: data/pdfs_processados.json")
            return
        
        total_produtos = 0
        
        # Processa cada PDF pendente
        for i, pdf_path in enumerate(pendentes, 1):
            print(f"\n{'=' * 70}")
            print(f"[{i}/{len(pendentes)}] {pdf_path.name}")
            print(f"  Fornecedor: {pdf_path.parent.name}")
            print("=" * 70)
            
            try:
                # Extrai produtos
                produtos, info = self.pdf_processor.processar_arquivo(
                    str(pdf_path),
                    fornecedor=pdf_path.parent.name
                )
                
                if not produtos:
                    print("⚠️  Nenhum produto extraído")
                    # Marca como processado mesmo sem produtos (para não tentar de novo)
                    self.processados.add(str(pdf_path))
                    salvar_processados(self.processados)
                    continue
                
                print(f"\n✅ {len(produtos)} produtos extraídos")
                
                # Salva no banco
                print("💾 Salvando no banco...")
                
                for j, produto in enumerate(produtos, 1):
                    produto_dict = {
                        'codigo': produto.codigo,
                        'descricao': produto.descricao,
                        'custo': produto.preco_unitario,
                        'fornecedor': produto.fornecedor,
                        'arquivo_origem': pdf_path.name,
                        'pagina_origem': getattr(produto, 'pagina_origem', 0)
                    }
                    
                    self.db.salvar_produto(produto_dict)
                    
                    if j % 25 == 0:
                        print(f"   {j}/{len(produtos)} salvos...")
                
                total_produtos += len(produtos)
                print(f"✅ {len(produtos)} produtos salvos no banco!")
                
                # Marca como processado
                self.processados.add(str(pdf_path))
                salvar_processados(self.processados)
                
            except Exception as e:
                print(f"❌ Erro ao processar: {e}")
                logger.error(f"Erro: {e}", exc_info=True)
                continue
        
        # Estatísticas finais
        print("\n" + "=" * 70)
        print("📊 PROCESSAMENTO CONCLUÍDO")
        print("=" * 70)
        
        stats = self.db.obter_estatisticas()
        
        print(f"\n   Processados agora: {total_produtos} produtos")
        print(f"   Total no banco: {stats['total']} produtos")
        print(f"   Fornecedores: {stats['fornecedores']}")
        print(f"   Banco: {self.db.db_path.absolute()}")
        
        print("\n💡 Abra o dashboard para ver os produtos:")
        print("   python dashboard_web.py")
        
        print("\n" + "=" * 70)


# EXECUÇÃO
if __name__ == "__main__":
    print("\n🚀 SISTEMA MASTER - PROCESSAMENTO EM LOTE v2")
    
    # PASTA MONITORADA
    PASTA = r"C:\Users\Luiz Gustavo\OneDrive\Documents\Escalada Econ\Loja QUBO\Fornecedores\1 -SISTEMA CATALOGOS AUTOMATICO"
    
    # Verifica pasta
    if not Path(PASTA).exists():
        print(f"\n❌ Pasta não existe!")
        print(f"   Configure em: {__file__}")
        input("\nPressione ENTER...")
        sys.exit(1)
    
    # Confirma
    processados = carregar_processados()
    print(f"\n📁 Pasta: {PASTA}")
    print(f"📋 PDFs já processados: {len(processados)}")
    print(f"\n⚠️  Vai processar apenas PDFs PENDENTES!")
    
    confirma = input("\n🚀 Continuar? (S/N): ")
    
    if confirma.upper() != 'S':
        print("\n❌ Cancelado")
        sys.exit(0)
    
    # RODA!
    sistema = SistemaMaster()
    sistema.processar_pasta(PASTA)
    
    print("\n✅ SISTEMA CONCLUÍDO!")
    
    input("\nPressione ENTER para sair...")
