# ADR 0006 — CRM canônico e multiunidade

- Status: aceito
- Data: 2026-08-19

## Contexto

MR, STK Lab e Stelli precisam operar no mesmo CRM. Uma pessoa ou empresa pode se relacionar com mais de uma unidade, e duplicar o cadastro por unidade impediria a visão consolidada e produziria históricos divergentes.

## Decisão

Pessoa e Empresa pertencem ao Grupo e possuem vínculos muitos-para-muitos com unidades. Oportunidade pertence a uma unidade, pipeline e etapa coerentes. Status comercial permanece separado da etapa; perda exige motivo. A próxima ação é derivada da tarefa aberta mais próxima.

Telefone e e-mail são sinais de identidade, não chaves globais de fusão. CPF/CNPJ normalizado, quando informado, é único por organização. Uma importação pode associar documento exato, mas coincidência apenas de contato é enviada para revisão manual.

Mudanças de etapa e linhas de importação são append-only. Escritas da API mantêm idempotência, auditoria e outbox transacionais.

## Consequências

- as três unidades compartilham o mesmo cadastro mestre sem duplicação obrigatória;
- relatórios podem consolidar o Grupo e filtrar unidades;
- fusões ambíguas não acontecem automaticamente;
- ganho/perda não distorce o histórico das etapas;
- contratos e faturamento futuros podem referenciar o CRM sem alterar este modelo.
