# Contribuindo

## Fluxo

1. Crie uma branch curta a partir de `main`.
2. Não altere schema fora de `database/migrations`.
3. Inclua testes para invariantes e falhas relevantes.
4. Rode `pnpm quality` antes de abrir revisão.
5. Registre decisões estruturais em ADR.

## Convenções

- Python: Ruff, tipos explícitos nas fronteiras e módulos por capacidade.
- TypeScript: modo estrito e ESLint.
- Banco: nomes em `snake_case`, UUIDs internos e timestamps UTC.
- API: comandos autenticados; nenhuma escrita direta por frontend ou orquestrador.
- Commits: mensagens imperativas e mudanças pequenas/coesas.

## Branch principal

Ao configurar o remoto oficial, `main` deve exigir pull request, ao menos uma aprovação, checks de qualidade e bloqueio de force-push/deleção. A configuração remota não pode ser aplicada por este repositório local.

