# Desenvolvimento local

## Configuração

1. Copie `.env.example` para `.env`.
2. Use apenas valores locais e sintéticos.
3. Defina `STK_DATABASE_URL=postgresql+psycopg://stk_os:stk_os_local_only@localhost:55432/stk_os`.
4. Gere um segredo JWT local aleatório; nunca reutilize em outro ambiente.

## Banco

```text
docker compose -f infrastructure/local/compose.yaml up -d
python scripts/database.py migrate
python scripts/database.py seed
```

`migrate` aplica arquivos em ordem, registra nome e SHA-256 e recusa uma migration já aplicada cujo conteúdo foi alterado. `seed` usa somente registros sintéticos e pode ser repetido.

## Identidades

Preencha as variáveis `STK_BOOTSTRAP_*` localmente e execute:

```text
python scripts/bootstrap_identity.py
```

O script cria/atualiza um administrador e uma service account sem imprimir senhas ou hashes.

## Aplicações

```text
pnpm api:dev
pnpm web:dev
```

- API: `http://127.0.0.1:8000`
- documentação OpenAPI: `http://127.0.0.1:8000/docs`
- frontend: `http://127.0.0.1:3000`

## Verificação

```text
pnpm quality
```

Para testes com PostgreSQL real, defina `STK_TEST_DATABASE_URL` apontando para um banco descartável local. Nunca use banco compartilhado ou produtivo.
