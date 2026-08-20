# Relatório de implementação — Etapas 0 e 1

**Data:** 19 de agosto de 2026  
**Escopo:** somente baseline/fundação e identidade/trilha de controle.

## 1. Implementado

- monorepo local na branch `main`, convenções, CI, segurança e dependências travadas;
- frontend Next.js mínimo e backend FastAPI modular, ambos iniciando localmente;
- PostgreSQL 18 via Compose, runner de migrations com SHA-256 e seeds sintéticos;
- `Grupo → Entidade Jurídica → Estabelecimento Fiscal → Unidade de Negócio`;
- administrador, service account, JWT curto, Argon2 e capacidades por papel;
- correlação, logging JSON seguro, auditoria append-only, idempotência, inbox, outbox, exceções e health checks;
- OpenAPI e schemas de eventos versionados.

## 2. Estrutura final

```text
apps/{web,api,worker}
automations/n8n
contracts/{api,events}
database/{migrations,seeds,policies}
docs/{adr,architecture,domain,relatorios,runbooks,security}
infrastructure/{local,staging,production}
integrations
scripts
tests (em apps/api/tests nesta fundação)
```

Os diretórios de integrações, n8n e worker contêm somente a fronteira aprovada; nenhuma funcionalidade futura foi antecipada.

## 3. Migrations

1. `001_foundation.sql`: organização, identidade, autorização e trilha de controle.
2. `002_append_only_guards.sql`: bloqueios de `UPDATE` e `DELETE` da auditoria e documentação das invariantes.

Seed `001_synthetic_organization.sql`: grupo, três entidades conceituais, quatro estabelecimentos e unidades MR, STK Lab e Stelli, todos sem CNPJ real.

## 4. Testes e resultados

- Ruff lint/format: aprovado;
- pytest: 15 aprovados, nenhum ignorado, 95,59% de cobertura e zero warnings;
- teste PostgreSQL real: aprovado contra PostgreSQL 18.4 em container local;
- ESLint: aprovado sem warnings;
- Next.js: build de produção aprovado;
- prova HTTP: API `200` com correlação e frontend `200`;
- secret scan: aprovado;
- peer dependencies e lockfile pnpm: aprovados.

## 5. ADRs

1. monólito modular;
2. modelo organizacional e fiscal;
3. identidade local portável;
4. migrations SQL reproduzíveis;
5. trilha de controle transacional.

## 6. Pendências técnicas

- criar remoto oficial e configurar proteção de `main`;
- definir provedor de identidade, hosting, RLS/grants, backup/restore e observabilidade antes do ambiente compartilhado/produção;
- executar os Gates A–E apenas nos momentos definidos pelo parecer.

## 7. Riscos encontrados

- autenticação local é adequada à fundação, mas não substitui MFA/provedor gerenciado em produção;
- RLS e grants dependem do provedor e precisam de revisão antes de expor qualquer Data API.

## 8. Decisões da implementação

- PostgreSQL 18.4 local; versões não beta;
- identidade local isolada atrás da API para não bloquear a decisão Supabase/OIDC;
- SQL ordenado com checksum em vez de criação automática de schema;
- comando de alteração de unidade usado como prova autenticada e idempotente, gerando auditoria e outbox atomicamente;
- aprovação explícita apenas do script transitivo `unrs-resolver@1.12.2`; demais scripts de dependências permanecem bloqueados;
- `output: standalone` não foi antecipado porque o provedor de deploy ainda não foi escolhido.

## 9. Parecer de avanço

# ETAPAS 0 E 1 APROVADAS — PODE AVANÇAR PARA ETAPA 2

Migrations, seed repetível, checksums, proteções append-only, constraints e o fluxo autenticado foram exercitados contra PostgreSQL 18.4 real. O relatório de evidências está em `validacao-postgresql-etapas-0-1.md`.

Nenhum item da Etapa 2 foi iniciado.
