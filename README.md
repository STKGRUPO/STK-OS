# STK OS

Implementação executável do STK OS V1 até a Etapa 6: fundação, CRM, contratos versionados, billing core e emissão idempotente de NFS-e por serviço fiscal privado.

## Escopo atual

- monorepo com Next.js, FastAPI e worker do mesmo backend;
- PostgreSQL 18 local e migrations SQL reproduzíveis;
- modelo `Grupo → Entidade Jurídica → Estabelecimento Fiscal → Unidade de Negócio`;
- administrador e service accounts com autenticação e autorização por capacidade;
- correlação, auditoria append-only, idempotência, inbox, outbox e exceções;
- health checks e logging estruturado com redação de campos sensíveis;
- pessoas e empresas canônicas no Grupo, com vínculos multiunidade;
- métodos de contato, vínculos pessoa–empresa e catálogos comerciais;
- pipelines, oportunidades, participantes, histórico de etapas, atividades e tarefas;
- próxima ação derivada da tarefa aberta mais próxima;
- API, Kanban responsivo, busca, visão 360° e importação pequena/auditável.
- contratos com identidade administrativa separada de versões temporais imutáveis;
- snapshots de valor, recorrência, vencimentos, reajuste, emissor, serviços e contatos;
- consulta histórica, atual, futura e por data arbitrária;
- suspensão, retomada, rescisão e renovação como eventos operacionais append-only;
- workspace web de contratos com filtros, diferenças entre versões e ações protegidas por capacidade.
- competência mensal `YYYY-MM` com timezone empresarial explícito;
- execuções e obrigações únicas por contrato/competência, seguras sob repetição e concorrência;
- valor bruto em `Decimal`, snapshot financeiro imutável e SHA-256 canônico;
- bloqueios/exceções rastreáveis, auditoria, outbox e workspace financeiro mínimo.
- billing items de contrato recorrente, serviço recorrente sem contrato e serviço pontual;
- serviço fiscal Python privado com DPS v1.01, XMLDSIG, mTLS SEFIN e A1 em secret mount;
- uma intenção fiscal por billing item, lease, tentativas auditáveis e reconciliação por DPS;
- referências privadas a XML/DANFSe e download autenticado pelo backend;
- emissão avulsa baseada exclusivamente em cliente canônico do CRM.

Cobrança, boleto, recebimento, cancelamento/substituição, envio ao cliente, Outlook, n8n, IA e MCP não fazem parte desta etapa.

## Pré-requisitos

- Node.js 24+
- pnpm 11+
- Python 3.12+
- Docker com Compose para o PostgreSQL local

## Início rápido

1. Copie `.env.example` para `.env` e preencha somente valores locais.
2. Execute `docker compose -f infrastructure/local/compose.yaml up -d`.
3. Crie o ambiente Python: `python -m venv .venv`.
4. Ative-o e instale: `python -m pip install -r apps/api/requirements.lock`, `python -m pip install --no-deps -e apps/api` e `python -m pip install --no-deps -e apps/fiscal-service`.
5. Rode `python scripts/database.py migrate` e `python scripts/database.py seed`.
6. Crie as identidades locais: `python scripts/bootstrap_identity.py`.
7. Instale o frontend: `pnpm install --frozen-lockfile`.
8. Provisione os mounts de secrets descritos em `apps/fiscal-service/README.md`.
9. Inicie o serviço fiscal com `pnpm fiscal:dev`, a API com `pnpm api:dev` e o frontend com `pnpm web:dev`.

O guia completo está em [docs/runbooks/desenvolvimento-local.md](docs/runbooks/desenvolvimento-local.md).

## Qualidade

```text
pnpm quality
```

O comando executa lint, testes e build das aplicações. Os testes de integração PostgreSQL usam `STK_TEST_DATABASE_URL`; sem essa variável, apenas a suíte que exige banco real é ignorada explicitamente.

## Documentos normativos

Em caso de refinamento, prevalece `docs/Parecer-Tecnico-Marco-0-STK-OS-V1.md`. Novas decisões técnicas são registradas em `docs/adr`.
