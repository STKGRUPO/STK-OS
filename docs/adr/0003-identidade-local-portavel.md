# ADR 0003 — Identidade local portável

- Status: aceito para Etapas 0 e 1
- Data: 2026-08-19

## Contexto

Supabase Auth é preferencial, mas o provedor definitivo pode ser decidido antes do ambiente compartilhado. A fundação precisa comprovar autenticação e autorização local sem credenciais externas.

## Decisão

Usar usuários e service accounts locais com hashes Argon2, tokens JWT curtos e capacidades persistidas. A fronteira de autenticação fica isolada no backend para futura integração com um emissor OIDC/Supabase.

## Consequências

O ambiente é reproduzível agora. MFA, rotação gerenciada, revogação distribuída e o provedor de produção permanecem no Gate D.

