"""
groq_extractor.py - Extrator com ROTAÇÃO de múltiplas chaves Groq
"""
import os
import json
import time
import logging
from pathlib import Path
from typing import List, Tuple
from groq import Groq
from dotenv import load_dotenv
from models import Produto

load_dotenv()

logger = logging.getLogger(__name__)

class GroqExtractor:
    """Extrator com rotação automática de keys Groq"""
    
    def __init__(self):
        # Carrega todas as chaves disponíveis
        self.api_keys = []
        
        # Primeira key
        key = os.getenv('GROQ_API_KEY')
        if key:
            self.api_keys.append(key)
        
        # Keys numeradas (2 a 30)
        for i in range(2, 30):
            key = os.getenv(f'GROQ_API_KEY_{i}')
            if key:
                self.api_keys.append(key)
        
        if not self.api_keys:
            raise ValueError("❌ Nenhuma GROQ_API_KEY encontrada no .env!")
        
        self.key_atual = 0
        self.model = "llama-3.3-70b-versatile"
        
        total_tokens = len(self.api_keys) * 100000
        logger.info(f"✅ Groq com {len(self.api_keys)} chaves ({total_tokens:,} tokens/dia!)")
    
    def _get_client(self):
        """Retorna client com key atual"""
        key = self.api_keys[self.key_atual]
        return Groq(api_key=key)
    
    def _proxima_key(self):
        """Avança para próxima key"""
        self.key_atual = (self.key_atual + 1) % len(self.api_keys)
        logger.info(f"🔄 Trocando para key {self.key_atual + 1}/{len(self.api_keys)}")
    
    def extrair_de_pdf(self, caminho_pdf: str, fornecedor: str = "") -> Tuple[List[Produto], dict]:
        """Extrai produtos com rotação automática de keys"""
        caminho = Path(caminho_pdf)
        
        if not caminho.exists():
            raise FileNotFoundError(f"PDF não encontrado: {caminho_pdf}")
        
        logger.info(f"📄 Processando: {caminho.name}")
        
        # Lê PDF
        try:
            import pypdf
            
            reader = pypdf.PdfReader(str(caminho))
            texto = ""
            
            # Primeiras 20 páginas
            for pagina in reader.pages[:20]:
                texto += pagina.extract_text() + "\n"
            
            if not texto.strip():
                logger.warning("⚠️  PDF vazio")
                return [], {'erro': 'PDF vazio'}
            
        except Exception as e:
            logger.error(f"❌ Erro ao ler PDF: {e}")
            return [], {'erro': str(e)}
        
        # Extrai com retry automático
        logger.info("🤖 Extraindo com Groq...")
        
        prompt = f"""Extraia TODOS os produtos deste catálogo.

Para cada produto:
- codigo: código/referência
- descricao: nome completo
- preco_unitario: preço (só número)

Retorne APENAS o JSON sem explicações:
[{{"codigo": "123", "descricao": "Produto X", "preco_unitario": 10.50}}]

TEXTO:
{texto[:6000]}

JSON:"""

        # Tenta em todas as keys COM retry
        for tentativa_key in range(len(self.api_keys)):
            for retry in range(3):
                try:
                    inicio = time.time()
                    
                    client = self._get_client()
                    
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": "Você é extrator de dados. Retorna APENAS JSON válido, sem explicações."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature=0.1,
                        max_tokens=4000
                    )
                    
                    tempo = time.time() - inicio
                    
                    resposta = response.choices[0].message.content
                    
                    if not resposta or not resposta.strip():
                        logger.warning(f"⚠️  Resposta vazia (retry {retry + 1}/3)")
                        time.sleep(2)
                        continue
                    
                    # Limpa resposta
                    resposta = resposta.strip()
                    resposta = resposta.replace("```json", "").replace("```", "").strip()
                    
                    # Remove texto antes do [
                    if '[' in resposta:
                        resposta = resposta[resposta.index('['):]
                    
                    # Remove texto depois do ]
                    if ']' in resposta:
                        resposta = resposta[:resposta.rindex(']') + 1]
                    
                    # Tenta parsear JSON
                    dados = json.loads(resposta)
                    
                    if not isinstance(dados, list):
                        logger.warning(f"⚠️  JSON não é lista (retry {retry + 1}/3)")
                        time.sleep(2)
                        continue
                    
                    # Converte para produtos
                    produtos = []
                    for item in dados:
                        try:
                            produto = Produto(
                                codigo=str(item.get('codigo', '')),
                                descricao=item.get('descricao', ''),
                                preco_unitario=float(item.get('preco_unitario', 0)),
                                fornecedor=fornecedor or caminho.stem
                            )
                            produtos.append(produto)
                        except:
                            continue
                    
                    if produtos:
                        logger.info(f"✅ {len(produtos)} produtos em {tempo:.1f}s")
                        return produtos, {'total_produtos': len(produtos), 'tempo': tempo}
                    else:
                        logger.warning(f"⚠️  JSON válido mas sem produtos (retry {retry + 1}/3)")
                        time.sleep(2)
                        continue
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"⚠️  JSON inválido: {str(e)[:50]} (retry {retry + 1}/3)")
                    if retry < 2:
                        time.sleep(2)
                        continue
                    
                except Exception as e:
                    erro_str = str(e)
                    
                    # Se quota esgotada, troca key
                    if "rate_limit" in erro_str.lower() or "429" in erro_str:
                        logger.warning(f"⚠️  Key {self.key_atual + 1} esgotada")
                        self._proxima_key()
                        time.sleep(2)
                        break
                    else:
                        logger.error(f"❌ Erro: {str(e)[:100]}")
                        if retry < 2:
                            time.sleep(2)
                            continue
            
            # Se chegou aqui e não retornou, vai pra próxima key
            if tentativa_key < len(self.api_keys) - 1:
                logger.warning(f"🔄 Tentando próxima key...")
                self._proxima_key()
                time.sleep(2)
        
        # Todas esgotadas/falharam
        logger.error("❌ Todas as tentativas falharam")
        return [], {'erro': 'Falha na extração'}


# TESTE
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("\n🧪 TESTANDO GROQ EXTRACTOR")
    print("="*70)
    
    try:
        extractor = GroqExtractor()
        print("✅ Extractor criado!")
        
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    print("="*70)