# 🚀 GUIA RÁPIDO — Migração para Multi-Extractor

## O QUE MUDOU

O sistema agora usa **múltiplos providers de IA** (Groq + Mistral) com fallback automático.
Quando o Groq esgota a quota, ele automaticamente muda para Mistral — sem parar!

---

## PASSO A PASSO (5 minutos)

### 1️⃣ CRIAR CONTA MISTRAL (grátis)

1. Acesse: **https://console.mistral.ai/**
2. Crie conta com seu email
3. Vá em **API Keys** → **Create New Key**
4. Copie a key (começa com algo tipo `sk-...`)

### 2️⃣ COPIAR ARQUIVOS NOVOS

Copie estes 3 arquivos para `C:\sistema-catalogos\`:

```
multi_extractor.py     ← NOVO (extrator multi-provider)
pdf_processor.py       ← ATUALIZADO (usa multi_extractor)
.env                   ← ATUALIZADO (com Mistral + keys deduplicadas)
```

⚠️ **BACKUP**: Antes de substituir, faça backup dos arquivos antigos!

### 3️⃣ CONFIGURAR O .ENV

Abra o novo `.env` e cole sua key Mistral na linha:
```
MISTRAL_API_KEY=sua_key_aqui
```

### 4️⃣ INSTALAR DEPENDÊNCIA

```bash
cd C:\sistema-catalogos
python -m pip install requests
```
(provavelmente já está instalado, mas por garantia)

### 5️⃣ TESTAR

```bash
python multi_extractor.py
```

Deve mostrar:
```
🚀 MULTI-EXTRACTOR INICIALIZADO
   Providers ativos: 2
   ✅ groq
   ✅ mistral
```

### 6️⃣ RODAR O SISTEMA NORMALMENTE

```bash
python sistema_master.py
```

Agora ele vai:
1. Tentar Groq primeiro (mais rápido)
2. Quando Groq esgotar → muda para Mistral automaticamente
3. Mistral tem ~1 BILHÃO de tokens/mês grátis = processa tudo de uma vez!

---

## ❓ FAQ

**P: Preciso mudar o `sistema_master.py`?**
R: NÃO! O `pdf_processor.py` atualizado já faz a troca automática.

**P: O dashboard continua funcionando?**
R: SIM, exatamente igual. Nada muda no dashboard.

**P: E se eu não criar a conta Mistral?**
R: Funciona igual ao antes, só com Groq. A Mistral é opcional (mas muito recomendada).

**P: Posso usar os dois ao mesmo tempo?**
R: SIM! É exatamente isso que o multi_extractor faz. Groq esgotou → Mistral assume.

---

## 🔧 PROBLEMAS NO .ENV ANTIGO

O `.env` antigo tinha estes problemas que foram corrigidos:
- ❌ Markdown misturado no final do arquivo
- ❌ Keys duplicadas (11=12, 19=20, 23=24) → removidas
- ❌ Faltava configuração Mistral
- ❌ Faltava GROQ_ORG_COUNT (controle de quota por organização)

---

## 📊 COMPARAÇÃO DE CAPACIDADE

| Configuração          | Tokens/dia     | Processa tudo? |
|-----------------------|----------------|----------------|
| Antes (só Groq 3 org) | ~300K          | ❌ Não          |
| Agora (Groq + Mistral)| ~300K + ~33M*  | ✅ Sim!         |

*Mistral free tier: ~1B tokens/mês ÷ 30 dias ≈ 33M tokens/dia
