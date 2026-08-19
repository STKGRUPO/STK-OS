# STK OS

Fundação executável do STK OS V1. Este repositório implementa exclusivamente as Etapas 0 e 1 aprovadas no Parecer Técnico do Marco 0: baseline, arquitetura executável, identidade, estrutura organizacional e trilha de controle.

## Escopo atual

- monorepo com Next.js, FastAPI e worker do mesmo backend;
- PostgreSQL 18 local e migrations SQL reproduzíveis;
- modelo `Grupo → Entidade Jurídica → Estabelecimento Fiscal → Unidade de Negócio`;
- administrador e service accounts com autenticação e autorização por capacidade;
- correlação, auditoria append-only, idempotência, inbox, outbox e exceções;
- health checks e logging estruturado com redação de campos sensíveis;
- frontend mínimo para provar a comunicação com a API.

CRM, faturamento, NFS-e, Outlook, n8n, IA e MCP não fazem parte desta rodada.

## Pré-requisitos

- Node.js 24+
- pnpm 11+
- Python 3.12+
- Docker com Compose para o PostgreSQL local

## Início rápido

1. Copie `.env.example` para `.env` e preencha somente valores locais.
2. Execute `docker compose -f infrastructure/local/compose.yaml up -d`.
3. Crie o ambiente Python: `python -m venv .venv`.
4. Ative-o e instale: `python -m pip install -r apps/api/requirements.lock` e depois `python -m pip install --no-deps -e apps/api`.
5. Rode `python scripts/database.py migrate` e `python scripts/database.py seed`.
6. Crie as identidades locais: `python scripts/bootstrap_identity.py`.
7. Instale o frontend: `pnpm install --frozen-lockfile`.
8. Inicie a API com `pnpm api:dev` e o frontend com `pnpm web:dev`.

O guia completo está em [docs/runbooks/desenvolvimento-local.md](docs/runbooks/desenvolvimento-local.md).

## Qualidade

```text
pnpm quality
```

O comando executa lint, testes e build das aplicações. Os testes de integração PostgreSQL usam `STK_TEST_DATABASE_URL`; sem essa variável, apenas a suíte que exige banco real é ignorada explicitamente.

## Documentos normativos

Em caso de refinamento, prevalece `docs/Parecer-Tecnico-Marco-0-STK-OS-V1.md`. Novas decisões técnicas são registradas em `docs/adr`.
