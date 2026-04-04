"""
multi_extractor.py - Extrator Multi-Provider com Fallback Automático
=====================================================================
Suporta: Groq → Mistral → Together AI → OpenRouter (com fallback automático)
Substitui: groq_extractor.py

COMO CONFIGURAR (no .env):
  GROQ_API_KEY=gsk_...           (obrigatório pelo menos 1 provider)
  MISTRAL_API_KEY=...            (grátis: console.mistral.ai)
  TOGETHER_API_KEY=...           (grátis $25: api.together.xyz)
  OPENROUTER_API_KEY=...         (grátis: openrouter.ai/keys)

COMO USAR:
  Troque o import no pdf_processor.py:
     DE:  from groq_extractor import GroqExtractor
     PARA: from multi_extractor import MultiExtractor as GroqExtractor
  Pronto! O resto do sistema funciona igual.

Autor: Claude para QUBO
Data: 2026-02
"""

import os
import json
import time
import logging
import hashlib
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURAÇÃO DOS PROVIDERS
# ============================================================

@dataclass
class ProviderStats:
    """Estatísticas de uso por provider/key"""
    requests_hoje: int = 0
    tokens_hoje: int = 0
    erros_consecutivos: int = 0
    ultima_data: str = ""
    ultimo_uso: str = ""
    bloqueada: bool = False
    
    def resetar_diario(self):
        self.requests_hoje = 0
        self.tokens_hoje = 0
        self.erros_consecutivos = 0
        self.bloqueada = False
        self.ultima_data = str(date.today())


class BaseProvider:
    """Classe base para providers de LLM"""
    
    nome: str = "base"
    
    def extrair_texto(self, texto: str, fornecedor: str) -> List[dict]:
        raise NotImplementedError
    
    def esta_disponivel(self) -> bool:
        raise NotImplementedError


# ============================================================
# PROVIDER: GROQ
# ============================================================

class GroqProvider(BaseProvider):
    """Provider Groq com rotação inteligente de keys por organização"""
    
    nome = "groq"
    
    def __init__(self):
        self.organizacoes = self._carregar_keys_por_org()
        self.org_atual = 0
        self.model = "llama-3.3-70b-versatile"
        
        total_keys = sum(len(org['keys']) for org in self.organizacoes)
        logger.info(f"🟢 Groq: {total_keys} keys em {len(self.organizacoes)} organização(ões)")
    
    def _carregar_keys_por_org(self) -> List[dict]:
        """
        Carrega keys e agrupa por organização.
        IMPORTANTE: Keys na mesma conta Groq compartilham quota!
        Usamos deduplicação por prefixo para estimar organizações.
        """
        keys_unicas = []
        keys_vistas = set()
        
        # Primeira key
        key = os.getenv('GROQ_API_KEY', '').strip()
        if key and key not in keys_vistas:
            keys_unicas.append(key)
            keys_vistas.add(key)
        
        # Keys 2 a 50 (expandido de 20 para 50)
        for i in range(2, 51):
            key = os.getenv(f'GROQ_API_KEY_{i}', '').strip()
            if key and key not in keys_vistas:
                keys_unicas.append(key)
                keys_vistas.add(key)
        
        if not keys_unicas:
            return []
        
        # Agrupa keys por "organização" estimada
        # Keys da mesma org tendem a ter prefixos similares
        # Como não temos como saber com certeza, tratamos como
        # uma única org para ser conservador com a quota
        # O usuário pode configurar GROQ_ORG_COUNT no .env
        org_count = int(os.getenv('GROQ_ORG_COUNT', '3'))
        
        # Distribui keys entre orgs
        organizacoes = []
        keys_por_org = max(1, len(keys_unicas) // org_count)
        
        for i in range(0, len(keys_unicas), keys_por_org):
            chunk = keys_unicas[i:i + keys_por_org]
            if chunk:
                organizacoes.append({
                    'keys': chunk,
                    'key_atual': 0,
                    'tokens_usados': 0,
                    'limite_tokens': 100_000,  # Free tier por org
                    'bloqueada': False
                })
        
        return organizacoes
    
    def esta_disponivel(self) -> bool:
        """Verifica se há alguma org disponível"""
        return any(not org['bloqueada'] for org in self.organizacoes)
    
    def _get_org_disponivel(self) -> Optional[dict]:
        """Encontra próxima organização disponível"""
        for _ in range(len(self.organizacoes)):
            org = self.organizacoes[self.org_atual]
            if not org['bloqueada']:
                return org
            self.org_atual = (self.org_atual + 1) % len(self.organizacoes)
        return None
    
    def _get_client_da_org(self, org: dict):
        """Cria client Groq com a key atual da org"""
        from groq import Groq
        key = org['keys'][org['key_atual']]
        return Groq(api_key=key)
    
    def _rotacionar_key_na_org(self, org: dict):
        """Avança para próxima key na mesma org"""
        org['key_atual'] = (org['key_atual'] + 1) % len(org['keys'])
    
    def _bloquear_org(self, org: dict):
        """Marca org como bloqueada (quota esgotada)"""
        org['bloqueada'] = True
        logger.warning(f"⚠️  Groq org bloqueada (quota esgotada)")
        self.org_atual = (self.org_atual + 1) % len(self.organizacoes)
    
    def extrair_texto(self, texto: str, fornecedor: str) -> List[dict]:
        """Extrai produtos via Groq API"""
        org = self._get_org_disponivel()
        if not org:
            logger.warning("⚠️  Todas as orgs Groq esgotadas")
            return None  # None = provider indisponível, [] = sem produtos
        
        prompt = self._montar_prompt(texto)
        
        # Tenta com retry na org atual
        for tentativa in range(3):
            try:
                client = self._get_client_da_org(org)
                
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Você é extrator de catálogos. Retorna APENAS JSON válido, sem explicações."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,
                    max_tokens=4000
                )
                
                resposta = response.choices[0].message.content
                
                if not resposta or not resposta.strip():
                    self._rotacionar_key_na_org(org)
                    time.sleep(1)
                    continue
                
                # Estima tokens usados
                tokens_usados = getattr(response.usage, 'total_tokens', 0) if response.usage else 2000
                org['tokens_usados'] += tokens_usados
                
                return self._parsear_json(resposta)
                
            except Exception as e:
                erro = str(e).lower()
                
                if 'rate_limit' in erro or '429' in erro:
                    # Quota da org esgotada
                    self._bloquear_org(org)
                    
                    # Tenta outra org
                    org = self._get_org_disponivel()
                    if not org:
                        return None
                    continue
                    
                elif '401' in erro or 'authentication' in erro:
                    # Key inválida, tenta próxima
                    self._rotacionar_key_na_org(org)
                    continue
                    
                else:
                    logger.warning(f"⚠️  Groq erro: {str(e)[:80]}")
                    if tentativa < 2:
                        time.sleep(2)
                        continue
                    return None
        
        return None
    
    def _montar_prompt(self, texto: str) -> str:
        """Prompt otimizado para extração — mais curto = menos tokens"""
        return f"""Extraia TODOS os produtos do texto abaixo.

REGRAS:
- Extraia código, descrição e preço de cada produto
- Preço: converta vírgula para ponto (10,50 → 10.50). Se não achar, use 0.0
- Código: pode ser SKU, REF, COD, etc
- NÃO invente produtos
- Se não houver produtos, retorne []

FORMATO JSON (sem markdown, sem explicação):
[{{"codigo": "ABC123", "descricao": "Produto X 100g", "preco_unitario": 10.50}}]

TEXTO DO CATÁLOGO:
{texto[:5000]}

JSON:"""
    
    def _parsear_json(self, resposta: str) -> List[dict]:
        """Parseia resposta JSON da LLM"""
        try:
            resposta = resposta.strip()
            resposta = resposta.replace("```json", "").replace("```", "").strip()
            
            # Encontra o array JSON
            if '[' in resposta:
                resposta = resposta[resposta.index('['):]
            if ']' in resposta:
                resposta = resposta[:resposta.rindex(']') + 1]
            
            dados = json.loads(resposta)
            
            if isinstance(dados, dict):
                dados = dados.get('produtos', [dados])
            
            if not isinstance(dados, list):
                return []
            
            return dados
            
        except json.JSONDecodeError:
            logger.warning("⚠️  JSON inválido na resposta")
            return []


# ============================================================
# PROVIDER: MISTRAL
# ============================================================

class MistralProvider(BaseProvider):
    """Provider Mistral AI — free tier generoso (~1B tokens/mês)"""
    
    nome = "mistral"
    
    def __init__(self):
        self.api_key = os.getenv('MISTRAL_API_KEY', '').strip()
        self.model = os.getenv('MISTRAL_MODEL', 'mistral-small-latest')
        self.base_url = "https://api.mistral.ai/v1"
        self.disponivel = bool(self.api_key)
        
        if self.disponivel:
            logger.info(f"🟢 Mistral: Configurado (modelo: {self.model})")
        else:
            logger.info("⚪ Mistral: Não configurado (adicione MISTRAL_API_KEY no .env)")
    
    def esta_disponivel(self) -> bool:
        return self.disponivel
    
    def extrair_texto(self, texto: str, fornecedor: str) -> List[dict]:
        """Extrai produtos via Mistral API"""
        if not self.disponivel:
            return None
        
        import requests
        
        prompt = self._montar_prompt(texto)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Você é extrator de catálogos de produtos. Retorna APENAS JSON válido."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"}
        }
        
        for tentativa in range(3):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 429:
                    logger.warning("⚠️  Mistral rate limit, aguardando...")
                    time.sleep(10 * (tentativa + 1))
                    continue
                
                if response.status_code == 401:
                    logger.error("❌ Mistral: API key inválida")
                    self.disponivel = False
                    return None
                
                response.raise_for_status()
                
                data = response.json()
                resposta = data['choices'][0]['message']['content']
                
                if not resposta or not resposta.strip():
                    time.sleep(2)
                    continue
                
                return self._parsear_json(resposta)
                
            except requests.exceptions.Timeout:
                logger.warning(f"⚠️  Mistral timeout (tentativa {tentativa + 1}/3)")
                time.sleep(5)
                continue
                
            except Exception as e:
                logger.warning(f"⚠️  Mistral erro: {str(e)[:80]}")
                if tentativa < 2:
                    time.sleep(3)
                    continue
                return None
        
        return None
    
    def _montar_prompt(self, texto: str) -> str:
        """Prompt otimizado para Mistral"""
        return f"""Extraia todos os produtos do catálogo abaixo. Retorne um JSON com a chave "produtos" contendo um array.

Cada produto deve ter:
- "codigo": código/referência do produto
- "descricao": nome/descrição completa  
- "preco_unitario": preço numérico (vírgula → ponto, ex: 10,50 → 10.50). Se não encontrar, use 0.0

Retorne SOMENTE o JSON, sem texto adicional.
Se não houver produtos, retorne: {{"produtos": []}}

TEXTO DO CATÁLOGO:
{texto[:6000]}"""
    
    def _parsear_json(self, resposta: str) -> List[dict]:
        """Parseia JSON da resposta Mistral"""
        try:
            resposta = resposta.strip()
            resposta = resposta.replace("```json", "").replace("```", "").strip()
            
            dados = json.loads(resposta)
            
            if isinstance(dados, dict):
                # Mistral com response_format retorna objeto
                dados = dados.get('produtos', dados.get('products', []))
            
            if not isinstance(dados, list):
                return []
            
            return dados
            
        except json.JSONDecodeError:
            # Tenta extrair array solto
            try:
                if '[' in resposta:
                    arr = resposta[resposta.index('['):resposta.rindex(']') + 1]
                    return json.loads(arr)
            except:
                pass
            
            logger.warning("⚠️  Mistral: JSON inválido")
            return []


# ============================================================
# PROVIDER: TOGETHER AI
# ============================================================

class TogetherProvider(BaseProvider):
    """Provider Together AI — $25 free credits, modelos Llama grátis"""
    
    nome = "together"
    
    def __init__(self):
        self.api_key = os.getenv('TOGETHER_API_KEY', '').strip()
        self.model = os.getenv('TOGETHER_MODEL', 'meta-llama/Llama-3.3-70B-Instruct-Turbo')
        self.base_url = "https://api.together.xyz/v1"
        self.disponivel = bool(self.api_key) and self.api_key != 'SUA_KEY_TOGETHER_AQUI'
        
        if self.disponivel:
            logger.info(f"🟢 Together: Configurado (modelo: {self.model})")
        else:
            logger.info("⚪ Together: Não configurado (adicione TOGETHER_API_KEY no .env)")
    
    def esta_disponivel(self) -> bool:
        return self.disponivel
    
    def extrair_texto(self, texto: str, fornecedor: str) -> List[dict]:
        """Extrai produtos via Together AI (OpenAI-compatible)"""
        if not self.disponivel:
            return None
        
        import requests
        
        prompt = f"""Extraia todos os produtos do catálogo abaixo. Retorne um JSON com a chave "produtos" contendo um array.

Cada produto deve ter:
- "codigo": código/referência do produto
- "descricao": nome/descrição completa  
- "preco_unitario": preço numérico (vírgula → ponto, ex: 10,50 → 10.50). Se não encontrar, use 0.0

Retorne SOMENTE o JSON, sem texto adicional.
Se não houver produtos, retorne: {{"produtos": []}}

TEXTO DO CATÁLOGO:
{texto[:6000]}"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Você é extrator de catálogos de produtos. Retorna APENAS JSON válido."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
        }
        
        for tentativa in range(3):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 429:
                    logger.warning("⚠️  Together rate limit, aguardando...")
                    time.sleep(10 * (tentativa + 1))
                    continue
                
                if response.status_code == 401:
                    logger.error("❌ Together: API key inválida")
                    self.disponivel = False
                    return None
                
                response.raise_for_status()
                data = response.json()
                resposta = data['choices'][0]['message']['content']
                
                if not resposta or not resposta.strip():
                    time.sleep(2)
                    continue
                
                return self._parsear_json(resposta)
                
            except requests.exceptions.Timeout:
                logger.warning(f"⚠️  Together timeout (tentativa {tentativa + 1}/3)")
                time.sleep(5)
                continue
            except Exception as e:
                logger.warning(f"⚠️  Together erro: {str(e)[:80]}")
                if tentativa < 2:
                    time.sleep(3)
                    continue
                return None
        return None
    
    def _parsear_json(self, resposta: str) -> List[dict]:
        try:
            resposta = resposta.strip().replace("```json", "").replace("```", "").strip()
            dados = json.loads(resposta)
            if isinstance(dados, dict):
                dados = dados.get('produtos', dados.get('products', []))
            return dados if isinstance(dados, list) else []
        except json.JSONDecodeError:
            try:
                if '[' in resposta:
                    arr = resposta[resposta.index('['):resposta.rindex(']') + 1]
                    return json.loads(arr)
            except:
                pass
            logger.warning("⚠️  Together: JSON inválido")
            return []


# ============================================================
# PROVIDER: OPENROUTER
# ============================================================

class OpenRouterProvider(BaseProvider):
    """Provider OpenRouter — 30+ modelos grátis via API unificada"""
    
    nome = "openrouter"
    
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY', '').strip()
        self.model = os.getenv('OPENROUTER_MODEL', 'meta-llama/llama-3.1-8b-instruct:free')
        self.base_url = "https://openrouter.ai/api/v1"
        self.disponivel = bool(self.api_key) and self.api_key != 'SUA_KEY_OPENROUTER_AQUI'
        
        # Modelos grátis para fallback
        self.modelos_free = [
            'meta-llama/llama-3.1-8b-instruct:free',
            'google/gemma-2-9b-it:free',
            'mistralai/mistral-7b-instruct:free',
            'qwen/qwen-2-7b-instruct:free',
        ]
        
        if self.disponivel:
            logger.info(f"🟢 OpenRouter: Configurado (modelo: {self.model})")
        else:
            logger.info("⚪ OpenRouter: Não configurado (adicione OPENROUTER_API_KEY no .env)")
    
    def esta_disponivel(self) -> bool:
        return self.disponivel
    
    def extrair_texto(self, texto: str, fornecedor: str) -> List[dict]:
        """Extrai produtos via OpenRouter"""
        if not self.disponivel:
            return None
        
        import requests
        
        prompt = f"""Extraia todos os produtos do catálogo abaixo. Retorne um JSON com a chave "produtos" contendo um array.

Cada produto deve ter:
- "codigo": código/referência do produto
- "descricao": nome/descrição completa  
- "preco_unitario": preço numérico (vírgula → ponto, ex: 10,50 → 10.50). Se não encontrar, use 0.0

Retorne SOMENTE o JSON, sem texto adicional.
Se não houver produtos, retorne: {{"produtos": []}}

TEXTO DO CATÁLOGO:
{texto[:5000]}"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://qubo.com.br",
            "X-Title": "QUBO Catalog System"
        }
        
        # Tenta modelos em sequência
        modelos_tentar = [self.model] + [m for m in self.modelos_free if m != self.model]
        
        for modelo in modelos_tentar[:3]:
            try:
                payload = {
                    "model": modelo,
                    "messages": [
                        {"role": "system", "content": "Você é extrator de catálogos de produtos. Retorna APENAS JSON válido."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4000,
                }
                
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 429:
                    logger.warning(f"⚠️  OpenRouter rate limit ({modelo}), tentando próximo...")
                    time.sleep(5)
                    continue
                
                if response.status_code == 401:
                    logger.error("❌ OpenRouter: API key inválida")
                    self.disponivel = False
                    return None
                
                response.raise_for_status()
                data = response.json()
                resposta = data['choices'][0]['message']['content']
                
                if not resposta or not resposta.strip():
                    continue
                
                resultado = self._parsear_json(resposta)
                if resultado:
                    return resultado
                    
            except Exception as e:
                logger.warning(f"⚠️  OpenRouter ({modelo}): {str(e)[:60]}")
                continue
        
        return None
    
    def _parsear_json(self, resposta: str) -> List[dict]:
        try:
            resposta = resposta.strip().replace("```json", "").replace("```", "").strip()
            dados = json.loads(resposta)
            if isinstance(dados, dict):
                dados = dados.get('produtos', dados.get('products', []))
            return dados if isinstance(dados, list) else []
        except json.JSONDecodeError:
            try:
                if '[' in resposta:
                    arr = resposta[resposta.index('['):resposta.rindex(']') + 1]
                    return json.loads(arr)
            except:
                pass
            logger.warning("⚠️  OpenRouter: JSON inválido")
            return []


# ============================================================
# MULTI-EXTRACTOR PRINCIPAL
# ============================================================

class MultiExtractor:
    """
    Extrator multi-provider com fallback automático.
    
    Ordem de prioridade: Groq → Mistral → Together AI → OpenRouter
    Se um provider falhar, tenta o próximo automaticamente.
    
    Drop-in replacement para GroqExtractor — mesma interface.
    """
    
    def __init__(self):
        self.providers: List[BaseProvider] = []
        self.stats_file = Path("data/multi_extractor_stats.json")
        self.stats_file.parent.mkdir(exist_ok=True)
        
        # Inicializa providers em ordem de prioridade
        self._init_providers()
        
        if not self.providers:
            raise ValueError("❌ Nenhum provider configurado! Adicione GROQ_API_KEY ou MISTRAL_API_KEY no .env")
        
        # Carrega estatísticas
        self.session_stats = {
            'inicio': datetime.now().isoformat(),
            'por_provider': {},
            'total_produtos': 0,
            'total_requests': 0,
            'fallbacks': 0
        }
        
        self._log_status()
    
    def _init_providers(self):
        """Inicializa todos os providers disponíveis"""
        # 1. Groq (mais rápido, mas quota limitada)
        try:
            groq = GroqProvider()
            if groq.organizacoes:
                self.providers.append(groq)
        except Exception as e:
            logger.warning(f"⚠️  Groq não disponível: {e}")
        
        # 2. Mistral (free tier generoso)
        try:
            mistral = MistralProvider()
            if mistral.esta_disponivel():
                self.providers.append(mistral)
        except Exception as e:
            logger.warning(f"⚠️  Mistral não disponível: {e}")
        
        # 3. Together AI (Llama grátis + $25 créditos)
        try:
            together = TogetherProvider()
            if together.esta_disponivel():
                self.providers.append(together)
        except Exception as e:
            logger.warning(f"⚠️  Together não disponível: {e}")
        
        # 4. OpenRouter (30+ modelos grátis)
        try:
            openrouter = OpenRouterProvider()
            if openrouter.esta_disponivel():
                self.providers.append(openrouter)
        except Exception as e:
            logger.warning(f"⚠️  OpenRouter não disponível: {e}")
    
    def _log_status(self):
        """Log do status inicial"""
        logger.info("=" * 60)
        logger.info("🚀 MULTI-EXTRACTOR INICIALIZADO")
        logger.info(f"   Providers ativos: {len(self.providers)}")
        for p in self.providers:
            logger.info(f"   ✅ {p.nome}")
        logger.info("=" * 60)
    
    def extrair_de_pdf(self, caminho_pdf: str, fornecedor: str = "") -> Tuple[List, dict]:
        """
        Extrai produtos de um PDF usando multi-provider.
        
        COMPATÍVEL com a interface do GroqExtractor original.
        
        Args:
            caminho_pdf: Caminho do arquivo PDF
            fornecedor: Nome do fornecedor
            
        Returns:
            Tupla (lista_de_Produto, dict_info)
        """
        from models import Produto
        
        caminho = Path(caminho_pdf)
        
        if not caminho.exists():
            raise FileNotFoundError(f"PDF não encontrado: {caminho_pdf}")
        
        logger.info(f"📄 Processando: {caminho.name}")
        
        # 1. Extrai texto do PDF
        texto = self._extrair_texto_pdf(str(caminho))
        
        if not texto:
            logger.warning("⚠️  PDF vazio ou ilegível")
            return [], {'erro': 'PDF vazio'}
        
        logger.info(f"   📝 {len(texto)} caracteres extraídos")
        
        # 2. Tenta cada provider em ordem
        inicio = time.time()
        provider_usado = None
        dados_brutos = None
        
        for provider in self.providers:
            if not provider.esta_disponivel():
                logger.info(f"   ⏭️  {provider.nome}: indisponível, pulando...")
                continue
            
            logger.info(f"   🤖 Tentando: {provider.nome}...")
            
            resultado = provider.extrair_texto(texto, fornecedor)
            
            if resultado is None:
                # Provider falhou (quota, erro, etc) — tenta próximo
                logger.info(f"   ↪️  {provider.nome} falhou, tentando próximo...")
                self.session_stats['fallbacks'] += 1
                continue
            
            if isinstance(resultado, list):
                dados_brutos = resultado
                provider_usado = provider.nome
                break
        
        tempo = time.time() - inicio
        self.session_stats['total_requests'] += 1
        
        if dados_brutos is None or len(dados_brutos) == 0:
            logger.warning(f"   ❌ Nenhum provider conseguiu extrair produtos")
            return [], {'erro': 'Falha na extração', 'tempo': tempo}
        
        # 3. Converte para objetos Produto
        produtos = []
        for item in dados_brutos:
            try:
                produto = Produto(
                    codigo=str(item.get('codigo', '')),
                    descricao=str(item.get('descricao', '')),
                    preco_unitario=float(item.get('preco_unitario', 0)),
                    fornecedor=fornecedor or caminho.stem
                )
                
                # Validação básica
                if produto.codigo or produto.descricao:
                    produtos.append(produto)
            except Exception:
                continue
        
        # 4. Atualiza stats
        self.session_stats['total_produtos'] += len(produtos)
        if provider_usado not in self.session_stats['por_provider']:
            self.session_stats['por_provider'][provider_usado] = {'requests': 0, 'produtos': 0}
        self.session_stats['por_provider'][provider_usado]['requests'] += 1
        self.session_stats['por_provider'][provider_usado]['produtos'] += len(produtos)
        
        if produtos:
            logger.info(f"   ✅ {len(produtos)} produtos via {provider_usado} em {tempo:.1f}s")
        
        return produtos, {
            'total_produtos': len(produtos),
            'tempo': tempo,
            'provider': provider_usado
        }
    
    def _extrair_texto_pdf(self, caminho: str) -> str:
        """Extrai texto limpo do PDF"""
        try:
            import pypdf
            
            reader = pypdf.PdfReader(caminho)
            textos = []
            
            # Limita a 20 páginas por chamada
            for pagina in reader.pages[:20]:
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    textos.append(texto_pagina.strip())
            
            texto_completo = "\n".join(textos)
            
            # Limpeza básica
            texto_completo = self._limpar_texto(texto_completo)
            
            return texto_completo
            
        except Exception as e:
            logger.error(f"❌ Erro ao ler PDF: {e}")
            return ""
    
    def _limpar_texto(self, texto: str) -> str:
        """Remove ruído do texto extraído do PDF"""
        import re
        
        linhas = texto.split('\n')
        linhas_limpas = []
        
        for linha in linhas:
            linha = linha.strip()
            
            # Pula linhas vazias
            if not linha:
                continue
            
            # Pula linhas muito curtas (ruído)
            if len(linha) < 3:
                continue
            
            # Pula headers/footers comuns
            skip_patterns = [
                'página', 'page', 'telefone:', 'tel:', 'fone:',
                'www.', 'http', '@', 'cnpj', 'cpf',
                'todos os direitos', 'all rights',
            ]
            
            linha_lower = linha.lower()
            if any(p in linha_lower for p in skip_patterns) and len(linha) < 80:
                continue
            
            linhas_limpas.append(linha)
        
        return '\n'.join(linhas_limpas)
    
    def obter_estatisticas(self) -> str:
        """Retorna relatório de uso da sessão"""
        stats = self.session_stats
        
        linhas = [
            "",
            "=" * 60,
            "📊 ESTATÍSTICAS MULTI-EXTRACTOR",
            "=" * 60,
            f"   Início: {stats['inicio'][:19]}",
            f"   Total requests: {stats['total_requests']}",
            f"   Total produtos: {stats['total_produtos']}",
            f"   Fallbacks: {stats['fallbacks']}",
            "",
            "   Por provider:",
        ]
        
        for provider, data in stats['por_provider'].items():
            linhas.append(f"     • {provider}: {data['requests']} req, {data['produtos']} produtos")
        
        linhas.append("")
        linhas.append("   Providers disponíveis:")
        for p in self.providers:
            status = "✅" if p.esta_disponivel() else "❌"
            linhas.append(f"     {status} {p.nome}")
        
        linhas.append("=" * 60)
        
        return "\n".join(linhas)


# ============================================================
# COMPATIBILIDADE — Alias para uso como drop-in replacement
# ============================================================

# Isso permite trocar o import sem mudar o resto do código:
#   from multi_extractor import MultiExtractor as GroqExtractor
GroqExtractor = MultiExtractor


# ============================================================
# TESTE
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    print("\n🧪 TESTANDO MULTI-EXTRACTOR")
    print("=" * 60)
    
    try:
        extractor = MultiExtractor()
        print(extractor.obter_estatisticas())
        print("\n✅ Multi-extractor criado com sucesso!")
        
    except Exception as e:
        print(f"\n❌ Erro: {e}")
    
    print("=" * 60)
