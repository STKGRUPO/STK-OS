# Validação PostgreSQL — Etapas 0 e 1

**Data:** 19 de agosto de 2026
**Escopo:** somente o critério de saída pendente das Etapas 0 e 1.

## Banco utilizado

- PostgreSQL 18.4, imagem `postgres:18.4-alpine`;
- container `stk-os-local-postgres-1`, saudável;
- banco principal local `stk_os` e banco descartável `stk_os_test`;
- porta isolada `55432`, pois um PostgreSQL 18 nativo já utiliza `5432`;
- somente usuário, senha e dados sintéticos locais.

## Migrations e seed

- `001_foundation.sql` aplicada primeiro;
- `002_append_only_guards.sql` aplicada depois;
- dois checksums SHA-256 conferidos pelo runner;
- `001_synthetic_organization.sql` executado duas vezes sem duplicação;
- contagens finais: 1 grupo, 3 entidades jurídicas, 4 estabelecimentos fiscais, 3 unidades de negócio, 5 permissões e 2 papéis;
- `scripts/database.py verify`: `verified 2 migrations`.

## Invariantes verificadas

- 17 tabelas fundacionais criadas;
- `UPDATE` e `DELETE` da auditoria bloqueados pelos triggers append-only;
- unicidades de grupo, estrutura organizacional, inbox e idempotência rejeitam duplicatas;
- checks de status, severidade, tipos de ator/estabelecimento e formatos fiscais ativos;
- auditoria, inbox, outbox, idempotência e exceções aceitam registros sintéticos válidos;
- login humano e de serviço, health readiness, comando idempotente e deduplicação de inbox aprovados por API contra PostgreSQL real.

## Testes

- pytest: 15 aprovados, nenhum skip e nenhum warning;
- cobertura: 95,59%;
- Ruff e verificação de formatação: aprovados;
- ESLint: aprovado;
- build Next.js: aprovado;
- secret scan: aprovado;
- `pnpm quality`: aprovado integralmente com `STK_TEST_DATABASE_URL` real.

## Falhas e correções

1. PostgreSQL 18 rejeitou o volume em `/var/lib/postgresql/data`. O mount foi corrigido para `/var/lib/postgresql`; o volume ainda vazio foi recriado.
2. A porta 5432 era atendida por PostgreSQL nativo. O Compose e o padrão local foram isolados na porta configurável `55432`, sem parar ou alterar o serviço existente.
3. Uma consulta de evidência usou alias inválido no `ORDER BY`; a consulta foi corrigida e repetida sem mudança no banco.
4. O teste PostgreSQL isolado passou, mas não alcançou sozinho a cobertura global de 80%; a validação oficial foi repetida com a suíte completa e atingiu 95,59%.

Nenhum dado real de cliente, CNPJ real, certificado, token ou credencial de produção foi utilizado.

# ETAPAS 0 E 1 APROVADAS — PODE AVANÇAR PARA ETAPA 2

A aprovação não inicia automaticamente a Etapa 2.
