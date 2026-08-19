# ADR 0004 — Migrations SQL reproduzíveis

- Status: aceito
- Data: 2026-08-19

## Decisão

Usar migrations SQL ordenadas e imutáveis, aplicadas por um runner que registra SHA-256. O schema nunca é alterado automaticamente pela aplicação.

## Consequências

As migrations são transparentes, portáveis para PostgreSQL gerenciado e verificáveis sem depender de um framework. Alterações futuras sempre criam novo arquivo.

