# Glossário do domínio

- **Grupo (`organization`)**: agrupamento consolidado do STK OS.
- **Entidade Jurídica (`legal_entity`)**: pessoa jurídica/sociedade.
- **Estabelecimento Fiscal (`fiscal_establishment`)**: matriz ou filial inscrita fiscalmente; futuro emissor de documentos.
- **Unidade de Negócio (`business_unit`)**: operação comercial, como MR, STK Lab ou Stelli. Não substitui estabelecimento fiscal.
- **Ator (`actor`)**: identidade auditável humana ou de serviço.
- **Service account**: ator não humano com credencial e capacidades mínimas.
- **Correlação**: UUID que conecta requisição, logs, auditoria e eventos.
- **Idempotência**: repetição da mesma intenção com a mesma chave produz o mesmo resultado lógico.
- **Inbox**: registro durável e deduplicado de evento recebido.
- **Outbox**: evento criado na mesma transação da mudança de negócio, aguardando entrega.
- **Exceção**: falha ou caso que exige tratamento controlado.

