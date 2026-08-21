# STK Fiscal Service

Serviço privado headless da Etapa 6. É o único processo autorizado a montar a
sessão mTLS e ler o A1 provisionado pelo secret manager. Não possui rotas de
frontend, cadastro, contrato ou n8n.

O deploy inclui `apps/api/src` no `PYTHONPATH` para reutilizar o pacote fiscal
puro (`engine`, DPS, XMLDSIG e cliente SEFIN), sem importar routers do backend.

Secrets montados, fora do Git:

- `/run/secrets/stk-fiscal-service/token` — autenticação M2M do backend;
- `/run/secrets/stk-fiscal/<certificate-key-id>/certificate.pem`;
- `/run/secrets/stk-fiscal/<certificate-key-id>/private-key.pem`;
- `password` opcional no mesmo diretório.

Execução local controlada:

```powershell
$env:PYTHONPATH="apps/api/src;apps/fiscal-service/src"
python -m uvicorn stk_fiscal_service.main:app --host 127.0.0.1 --port 8010
```
