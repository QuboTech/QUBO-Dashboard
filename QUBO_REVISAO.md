# QUBO Dashboard v4 — Revisão Completa & Roadmap

> **Data:** Abril 2026  
> **URL:** https://qubo-dashboard.onrender.com  
> **Login:** gustavo / qubo2026  
> **GitHub:** https://github.com/QuboTech/QUBO-Dashboard  
> **Banco:** Supabase PostgreSQL — `waivneiqdbioclwkpync`

---

## 📦 STACK DO SISTEMA

| Componente | Tecnologia | Status |
|---|---|---|
| Backend | Flask Python 3.14 | ✅ |
| Banco de dados | Supabase PostgreSQL | ✅ |
| Deploy | Render (free tier) | ✅ |
| Código-fonte | GitHub (QuboTech/QUBO-Dashboard) | ✅ |
| IA — Extração PDF | Groq (27 keys) + Mistral + fallbacks | ✅ |
| IA — Agentes | Groq llama/mixtral | ✅ |
| ML OAuth | Mercado Livre API v2 | ✅ |
| File Watcher | Python watchdog — Tarefa Windows | ✅ |
| Autenticação | Flask Session + SHA256 | ✅ |
| Multi-tenant | tenant_id por usuário | ✅ |

---

## ✅ O QUE FOI CONSTRUÍDO

### 1. Infraestrutura

- **Deploy no Render** com auto-deploy via GitHub push
- **Banco Supabase** com tabelas `produtos`, `ml_tokens`, `config`
- **Multi-tenant** — cada usuário vê só os seus próprios dados
- **Login com senha** via variáveis de ambiente no Render
- **Token ML salvo no Supabase** — persiste entre redeploys, renova automaticamente

### 2. Dashboard Principal (`/`)

- **Tabela de produtos** com paginação, filtros e busca
- **Stats em tempo real**: total, fornecedores, viáveis, não viáveis, pendentes, escolhidos
- **Filtros**: fornecedor, produto, status, custo mín/máx, por página
- **Colunas editáveis inline**: Preço ML, Taxa %, Peso, Embalagem
- **Recálculo automático** ao editar qualquer campo de custo
- **Alíquota de imposto** global configurável
- **Botão Recalcular Tudo** — aplica nova alíquota a todos
- **Exportação Excel** no formato da planilha oficial ML
- **Escolhidos** — marcar/desmarcar produtos com ⭐
- **Deletar produto** individualmente

### 3. Cálculo de Viabilidade (Planilha Oficial ML)

- **110 faixas de frete** reais (preço × peso)
- **Taxa ML por categoria** buscada via API em tempo real
- **Taxa fixa R$6,25** para produtos < R$79,90
- **Imposto** configurável globalmente
- **Margem %** e **Margem R$** calculados corretamente
- **Status**: Viável (≥20%) / Não Viável / Pendente

### 4. Página de Configurações (`/config`) — v4

- **ML Auth**: status da conexão, link para autorizar, campo para código TG-xxx
- **Upload de PDF**: arrasta ou clica, processa com IA, salva no Supabase
- **Pasta de monitoramento**: configura caminho local, verifica PDFs pendentes
- **Info do sistema**: URL, banco, credenciais

### 5. Página Escolhidos (`/escolhidos`)

- Lista todos os produtos marcados com ⭐
- Exportação Excel separada

### 6. File Watcher (Local no PC)

- **Instalado como Tarefa do Windows** (`QUBO_FileWatcher`)
- Inicia automaticamente no login do Windows
- Reinicia automaticamente se travar
- Monitora pasta `1 -SISTEMA CATALOGOS AUTOMATICO`
- Renomeia PDFs para `.enviado` após processar
- Envia para Supabase via `DATABASE_URL`

### 7. Extração de PDF (Multi-camadas)

- **Camada 1**: Groq (rápido, gratuito, 27 keys em rodízio)
- **Camada 2**: Mistral (fallback)
- **Camada 3**: Together AI (fallback)
- **Camada 4**: OpenRouter (fallback)
- Extrai: código, descrição, preço unitário, quantidade
- Ignora linhas de cabeçalho, totais e ruídos

### 8. 7 Agentes de IA

| Agente | Botão | O que faz |
|---|---|---|
| 🤖 Pesquisa de Produto | Roxo | Análise completa de mercado |
| 💰 Precificação Inteligente | Verde | 3 cenários de preço (agressivo/competitivo/premium) |
| 📈 Viabilidade de Produto | Azul | Score 0-100, insights, demanda de mercado |
| 📊 Alerta Diário | Amarelo | Vendas, perguntas abertas, reputação |
| 🔥 Tendências ML | Rosa | Top produtos em alta + cruzamento com catálogo |
| 🏥 Saúde dos Anúncios | Ciano | Críticos, em risco, sem visitas |
| 🔍 Busca ML | Cinza | Preço médio + taxa real por categoria |

---

## 🔧 COMO FAZER DEPLOY (Fluxo Completo)

```
1. Editar arquivo em C:\sistema-catalogos\
2. git add -A
3. git commit -m "descrição"
4. git push
5. Render detecta e faz redeploy automático (~2 min)
```

**Ou para forçar redeploy:**
- Render Dashboard → Manual Deploy → Deploy latest commit

**Para atualizar variáveis de ambiente:**
- Render Dashboard → Environment → Edit → Save, rebuild, and deploy

---

## 💡 IDEIAS A IMPLEMENTAR

### Alta Prioridade

#### A. Painel de Importação em Lote
Hoje o upload é um PDF por vez. Seria melhor poder selecionar múltiplos PDFs de uma vez no `/config` e processar todos em sequência com uma barra de progresso.

#### B. Fix do File Watcher Local → Supabase
O PC local não consegue conectar ao Supabase via porta 5432 (DNS bloqueado). Soluções possíveis:
- Usar porta 6543 (Transaction Pooler)
- Usar API REST do Supabase em vez de psycopg2
- Usar endpoint do próprio dashboard: POST `/api/upload-pdf`

#### C. Histórico de Preços ML
Salvar o histórico de preço médio do ML por produto ao longo do tempo. Criar gráfico de tendência. Alertar quando o preço cair mais de 10%.

#### D. Sync com Anúncios Ativos no ML
Cruzar produtos escolhidos com anúncios reais publicados:
- Mostrar se o produto já está publicado
- Mostrar estoque, visitas, vendas do anúncio

### Média Prioridade

#### E. Calculadora de Precificação Avançada
Página dedicada onde o usuário digita custo e simula diferentes preços vendo margem em tempo real. Com slider de preço e gráfico de margem × preço.

#### F. Dashboard de Vendas
Página `/vendas` com:
- Gráfico de vendas por dia/semana/mês
- Top produtos mais vendidos
- Faturamento total e por fornecedor

#### G. Gerenciador de Fornecedores
Página `/fornecedores` com:
- Cadastro de fornecedores com contato, prazo, condições
- Histórico de PDFs importados por fornecedor
- Performance de conversão (% produtos viáveis)

#### H. Alertas por Email
Usando Resend (gratuito até 3k emails/mês):
- Alerta diário automático por email às 8h
- Alerta quando produto sai de "viável" para "inviável"
- Alerta quando concorrente abaixa preço > 15%

#### I. API de Webhooks
Receber notificações do ML em tempo real:
- Nova venda → atualiza dashboard
- Nova pergunta → notificação
- Mudança de reputação → alerta

### Baixa Prioridade / Futuro

#### J. App Mobile (PWA)
Transformar o dashboard em Progressive Web App — instalável no celular. Hoje já funciona no mobile mas sem ícone na tela inicial.

#### K. IA para Título de Anúncio
Agente que sugere o título ideal do anúncio baseado nos top anúncios do ML. Considerando palavras-chave mais usadas pelos líderes.

#### L. Comparador de Fornecedores
Dado o mesmo produto, comparar o preço de diferentes fornecedores e calcular qual oferece melhor margem final.

---

## 🧪 TESTES DE VIABILIDADE FUNCIONAIS

### Bloco 1 — Login e Acesso

| Teste | Procedimento | Esperado |
|---|---|---|
| Login correto | Entrar com `gustavo` / `qubo2026` | Redireciona para `/` |
| Login incorreto | Entrar com senha errada | Mensagem de erro, não redireciona |
| Acesso sem login | Acessar `/` sem estar logado | Redireciona para `/login` |
| Multi-tenant | Criar 2 usuários, verificar isolamento | Cada um vê só os seus produtos |
| Logout | Clicar em Sair | Session limpa, volta para login |

### Bloco 2 — Import de PDF

| Teste | Procedimento | Esperado |
|---|---|---|
| Upload via `/config` | Selecionar PDF válido de catálogo | Toast com qtd produtos extraídos |
| PDF sem produtos | Enviar PDF de contrato/texto | Mensagem "Nenhum produto encontrado" |
| PDF muito grande (>10MB) | Enviar PDF pesado | Timeout ou erro gracioso |
| Nome do fornecedor | Arquivo `Fornecedor ABC.pdf` | Coluna fornecedor = "Fornecedor ABC" |
| Verificar no dashboard | Após upload, acessar `/` | Produtos aparecem na tabela |
| Duplicatas | Enviar mesmo PDF 2x | Verificar se duplica ou ignora |

### Bloco 3 — Cálculo de Viabilidade

| Teste | Procedimento | Esperado |
|---|---|---|
| Produto < R$79 | Preço ML = R$50 | Taxa fixa R$6,25 aparece no custo |
| Produto com frete | Peso 1kg, Preço ML R$120 | Frete calculado da tabela (R$17,96) |
| Margem exata | Custo R$30, Preço ML R$80, Taxa 16.5% | Margem calculada corretamente |
| Recalcular tudo | Mudar alíquota para 6%, clicar Recalcular | Todos os produtos atualizam |
| Produto viável | Margem ≥ 20% | Badge verde "VIÁVEL" |
| Produto inviável | Margem < 20% | Badge vermelho "BAIXO" |

### Bloco 4 — API Mercado Livre

| Teste | Procedimento | Esperado |
|---|---|---|
| ML Auth | Clicar autorizar, colar código | Status "Conectado" em /config |
| Busca ML | Clicar 🔍 em produto | Preenche preço médio e taxa |
| Token expirado | Aguardar 6h, usar agente | Renova automaticamente (sem pedir auth) |
| Produto sem resultado | Buscar termo muito específico | Mensagem "Sem resultados" |
| Alerta Diário | Clicar 📊 Alerta | Modal com vendas, perguntas, reputação |
| Tendências | Clicar 🔥 Tendências | Lista de produtos em alta |

### Bloco 5 — Agentes de IA

| Teste | Procedimento | Esperado |
|---|---|---|
| Precificação | Clicar 💰 em produto com custo | 3 cenários + recomendação |
| Viabilidade | Clicar 📈 em produto | Score 0-100 + insights |
| Pesquisa | Clicar 🤖 em produto | Análise de mercado |
| Saúde | Clicar 🏥 Saúde | Lista anúncios problemáticos |
| Sem ML conectado | Usar agente sem token | Mensagem "ML não conectado. Vá em Configurações" |

### Bloco 6 — File Watcher

| Teste | Procedimento | Esperado |
|---|---|---|
| Tarefa ativa | `Get-ScheduledTask -TaskName "QUBO_FileWatcher"` | State: Running |
| Processar PDF | Colocar PDF na pasta monitorada | PDF processado, renomeado .enviado |
| Restart automático | Matar processo manualmente | Reinicia em < 1 min |
| Log de erros | Ver `data\watcher.log` | Logs de processamento |

### Bloco 7 — Performance e Estabilidade

| Teste | Procedimento | Esperado |
|---|---|---|
| Cold start | Acessar após 30min inativo | Carrega em < 55 segundos |
| 500 produtos | Importar catálogo grande | Tabela renderiza, paginação funciona |
| Múltiplas abas | Abrir em 3 abas simultâneas | Sem conflitos de sessão |
| Exportar Excel | Clicar 📥 Excel com 200+ produtos | Arquivo baixado corretamente |

---

## 📋 PENDÊNCIAS CONHECIDAS

### Bugs Confirmados
- [ ] **File Watcher local → Supabase**: DNS na porta 5432 bloqueado na rede local. Workaround: usar upload pelo `/config`
- [ ] **psycopg2 no PC**: precisa instalar via `python -m pip install psycopg2-binary`

### Melhorias Imediatas (próxima sessão)
- [ ] Testar todos os botões após deploy do v4
- [ ] Confirmar que upload de PDF via `/config` funciona end-to-end
- [ ] Verificar se agentes retornam dados corretos com ML autenticado
- [ ] Confirmar que Token ML renova sozinho após 6h

---

## 🔑 CREDENCIAIS E ACESSOS

| Serviço | Valor |
|---|---|
| Dashboard URL | https://qubo-dashboard.onrender.com |
| Login | gustavo / qubo2026 |
| GitHub | https://github.com/QuboTech/QUBO-Dashboard |
| Render Service | srv-d789am7fte5s738sobjg |
| Supabase Project | waivneiqdbioclwkpync |
| ML Client ID | 5055987535998228 |
| Pasta PDFs | `C:\Users\Luiz Gustavo\OneDrive\Documents\Escalada Econ\Loja QUBO\Fornecedores\1 -SISTEMA CATALOGOS AUTOMATICO` |

---

## 🚀 PRÓXIMA SESSÃO — O QUE FAZER

1. **Instalar v4**: `python C:\sistema-catalogos\instalar_v4.py`
2. **Testar bloco 1** (login)
3. **Testar bloco 2** (upload PDF via /config)
4. **Testar bloco 3** (cálculo viabilidade)
5. **Testar bloco 4** (API ML)
6. **Testar bloco 5** (agentes IA)
7. Se tudo OK → implementar **item B** (fix file watcher local)
8. Depois → implementar **item A** (upload em lote)

