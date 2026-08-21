# Faturamento recorrente

## Fronteira

O STK OS é a fonte oficial da obrigação contratual por competência. A Etapa 5 determina contrato elegível, versão, emissor e valor bruto, congela um snapshot e publica um evento interno. Não calcula tributos, não cria payload fiscal, não usa certificado e não emite NFS-e.

## Competência

A representação externa é `YYYY-MM`. No PostgreSQL, `competence_month` é a data do primeiro dia desse mês e possui constraint de normalização. Datas de contrato são civis; timestamps de auditoria são absolutos. O timezone operacional configurado é `America/Sao_Paulo`, nunca o timezone do navegador ou servidor.

## Geração

Uma execução considera todos os contratos da organização e unidade e persiste um resultado por contrato:

- `created`: uma obrigação nova foi criada;
- `reused`: a obrigação já existia e foi reutilizada;
- `not_eligible`: nenhuma obrigação foi criada, com código e motivo permanentes.

A execução é única por organização, unidade e competência. O processamento de um contrato pode gerar item bloqueado e exceção sem impedir os demais.

## Elegibilidade determinística

- cadastro contratual deve estar ativo;
- o contrato precisa ter iniciado até o primeiro dia da competência;
- contrato iniciado depois do primeiro dia começa a faturar no mês seguinte;
- a situação operacional no primeiro dia deve ser ativa;
- se houver suspensão, retomada ou encerramento depois do primeiro dia, o item é bloqueado porque o Gate A não definiu o efeito dentro do mês;
- se houver versão nova depois do primeiro dia, o item é bloqueado pelo mesmo motivo;
- não existe pró-rata nem retroatividade inferida.

## Valor

Valores usam `Decimal`/`numeric(18,2)`. Para preço mensal com cobrança mensal, o valor publicado é o valor bruto. Para valor anual com cobrança mensal, a divisão por 12 só produz item pronto quando é exata em centavos. Resíduo gera `GATE_A_ANNUAL_ROUNDING_PENDING`, valor bruto nulo e nenhuma distribuição silenciosa.

## Estados

- `blocked`: obrigação criada, mas impedida por dado inválido ou decisão pendente;
- `ready`: obrigação contratual íntegra e apta a uma futura solicitação fiscal;
- `requested`: reservado para solicitação fiscal real da Etapa 6;
- `completed`: reservado para conclusão fiscal real da Etapa 6;
- `cancelled`: reservado para comando de cancelamento lógico ainda dependente do Gate A.

Não existe estado `invoice_issued` nesta etapa.

## Snapshot e hash

O snapshot canônico v1 contém competência/timezone, contrato, versão e seu hash, cliente, unidade, emissor, preço, serviços, contatos financeiros e bloqueios. Decimais e datas são serializados como strings. SHA-256 usa JSON com chaves ordenadas e separadores canônicos. PostgreSQL impede alterações nos campos financeiros, snapshot e hash.

## Idempotência, concorrência e eventos

O comando usa idempotência técnica e uma chave de negócio permanente. Um lock consultivo serializa a geração e constraints únicas protegem lote e obrigação. `billing.item.ready.v1`, `billing.item.blocked.v1` e `billing.run.completed.v1` são gravados na outbox na mesma transação; nenhum consumidor fiscal é chamado.

## Gate A preservado

Permanecem sem comportamento automático: arredondamento/resíduo, efeito intra-competência, retroatividade excepcional, correção de obrigação, cancelamento/estorno e autorização ampliada de editores financeiros. O reprocessamento disponível apenas retorna a operação congelada e nunca reescreve história.
