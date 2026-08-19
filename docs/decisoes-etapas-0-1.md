# Decisões das Etapas 0 e 1

- PostgreSQL local: imagem `postgres:18.4-alpine`, compatível com PostgreSQL gerenciado.
- Backend: FastAPI 0.141.x e SQLAlchemy 2.0.x em Python 3.12.
- Frontend: Next.js 16.3.x com React 19.2.x e TypeScript estrito.
- Identidade local: Argon2 + JWT; provedor gerenciado fica para o Gate D.
- IDs: UUID v4 gerados pela aplicação; timestamps UTC.
- Autorização: capacidades associadas a papéis, tanto para usuário como service account.
- Auditoria: append-only no banco e sem payload sensível integral.
- Idempotência: header `Idempotency-Key`, escopo por ator e comando, hash do corpo e resposta persistida.
- Eventos: inbox/outbox persistentes; nenhum broker ou engine genérica nesta etapa.
- Dados iniciais: somente entidades conceituais e sem CNPJ/documento real.

