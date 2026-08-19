# Modelo de ameaças inicial

## Ativos

- credenciais humanas e de serviço;
- estrutura organizacional;
- trilha de auditoria;
- mensagens de inbox/outbox e contexto de exceções.

## Ameaças e controles

| Ameaça | Controle inicial |
|---|---|
| Secret no Git | `.gitignore`, `.env.example` sem valores e verificação automatizada |
| Escalada de privilégio | autorização por capacidade no backend |
| Repetição de comando | chave de idempotência vinculada ao ator e hash da requisição |
| Evento externo duplicado | unicidade por origem + ID externo na inbox |
| Perda entre estado e publicação | outbox na mesma transação |
| Alteração da auditoria | tabela append-only e trigger de bloqueio |
| Vazamento em logs | formatter estruturado, allowlist e redação |
| Falsificação de correlação | UUID validado ou gerado pelo backend |

Antes de produção ainda são necessários MFA, cofre de secrets, RLS/grants revisados, rate limit, backup/restore, observabilidade e resposta a incidentes.

