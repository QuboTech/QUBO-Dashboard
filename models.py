"""
models.py - Modelos de dados do sistema
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict
from datetime import datetime
import hashlib

@dataclass
class Produto:
    """Representa um produto extraído"""
    codigo: str
    descricao: str
    preco_unitario: float
    fornecedor: str = ""
    qtd_caixa: Optional[float] = None
    Pasta_Origem: str = ""
    Arquivo_Origem: str = ""
    data_processamento: str = field(default_factory=lambda: datetime.now().isoformat())
    hash_arquivo: str = ""
    
    def __post_init__(self):
        """Validação e normalização automática"""
        self.codigo = str(self.codigo).strip()
        self.descricao = str(self.descricao).strip()
        
        # Normaliza preço
        try:
            preco_str = str(self.preco_unitario).replace(',', '.')
            self.preco_unitario = float(preco_str)
        except:
            self.preco_unitario = 0.0
        
        # Normaliza quantidade
        if self.qtd_caixa:
            try:
                self.qtd_caixa = float(self.qtd_caixa)
            except:
                self.qtd_caixa = None
    
    def to_dict(self) -> Dict:
        """Converte para dicionário"""
        return asdict(self)
    
    def validar(self) -> tuple[bool, List[str]]:
        """Valida dados do produto - Versão balanceada"""
        erros = []
        
        if not self.codigo:
            erros.append("Código vazio")
        
        if not self.descricao:
            erros.append("Descrição vazia")
        
        # Aceita preço zero (IA pode não ter encontrado)
        # Mas marca como warning se for zero
        if self.preco_unitario < 0:
            erros.append("Preço negativo")
        
        return (len(erros) == 0, erros)
    
    def chave_unica(self) -> str:
        """Gera chave única para identificação"""
        return f"{self.fornecedor}_{self.codigo}".lower()


@dataclass
class ArquivoProcessado:
    """Representa um arquivo já processado"""
    nome: str
    caminho: str
    hash_md5: str
    data_processamento: str
    total_produtos: int
    pasta_origem: str
    
    @staticmethod
    def calcular_hash(caminho: str) -> str:
        """Calcula hash MD5 do arquivo"""
        hash_md5 = hashlib.md5()
        try:
            with open(caminho, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except:
            return ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MudancaPreco:
    """Representa uma mudança de preço detectada"""
    fornecedor: str
    codigo: str
    descricao: str
    preco_antigo: float
    preco_novo: float
    percentual_mudanca: float
    data_mudanca: str = field(default_factory=lambda: datetime.now().isoformat())
    arquivo_origem: str = ""
    
    def __post_init__(self):
        if self.preco_antigo > 0:
            self.percentual_mudanca = ((self.preco_novo - self.preco_antigo) / self.preco_antigo) * 100
        else:
            self.percentual_mudanca = 0.0
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def tipo_mudanca(self) -> str:
        """Retorna tipo de mudança"""
        if self.percentual_mudanca > 0:
            return "AUMENTO"
        elif self.percentual_mudanca < 0:
            return "REDUÇÃO"
        return "SEM_MUDANÇA"


@dataclass
class RelatorioProcessamento:
    """Relatório de uma sessão de processamento"""
    data_inicio: str
    data_fim: str = ""
    arquivos_processados: int = 0
    arquivos_novos: int = 0
    arquivos_atualizados: int = 0
    produtos_extraidos: int = 0
    produtos_novos: int = 0
    mudancas_preco: int = 0
    erros: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def finalizar(self):
        """Marca relatório como finalizado"""
        self.data_fim = datetime.now().isoformat()
    
    def adicionar_erro(self, erro: str):
        """Adiciona erro ao relatório"""
        self.erros.append(f"{datetime.now().strftime('%H:%M:%S')} - {erro}")