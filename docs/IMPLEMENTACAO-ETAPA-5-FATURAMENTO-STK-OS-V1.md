# Implementação da Etapa 5 — Núcleo de Faturamento — STK OS V1

- Data de conclusão: 2026-08-20
- Escopo: domínio determinístico de faturamento recorrente
- Resultado: aprovado

## 1. Resultado executivo

A Etapa 5 implementa a geração segura de obrigações financeiras mensais a partir do contrato e da versão vigente. O sistema responde quais contratos foram considerados, quais estavam elegíveis, o valor bruto, o estabelecimento emissor, a versão contratual e o estado de cada obrigação.

Nenhuma NFS-e foi emitida. Não foram implementados cálculo tributário, retenções, payload fiscal, certificado, assinatura, comunicação SEFIN/NFS-e, PDF/XML, Outlook, n8n, boleto, Itaú, cobrança, IA, MCP ou Serviço Fiscal Python.

## 2. O que foi implementado

- competência mensal explícita `YYYY-MM`;
- persistência como primeiro dia do mês, validada por constraint;
- timezone IANA configurável, com baseline `America/Sao_Paulo`;
- execução única por organização, unidade e competência;
- obrigação única por contrato e competência;
- seleção de contratos e versão temporal válida;
- elegibilidade por início, suspensão, retomada e encerramento;
- emissor vindo exclusivamente da versão contratual;
- valor bruto em `Decimal`/`numeric`, nunca `float`;
- snapshot imutável, representação canônica e SHA-256;
- máquina de estados financeira pequena e sem estados fiscais falsos;
- auditoria, correlação, causação, idempotência e outbox transacionais;
- exceções bloqueadas por contrato sem invalidar o lote;
- registro do motivo de contratos não elegíveis;
- APIs de geração, consulta, filtros, resumo, exceções e reprocessamento seguro;
- interface mínima funcional para execução e inspeção operacional;
- capacidades `billing:read`, `billing:generate`, `billing:review` e `billing:reprocess`.

## 3. Migration

`database/migrations/006_billing_core.sql` cria:

- `billing_runs`;
- `billing_items`;
- `billing_run_contracts`;
- índices de consulta por competência, unidade, cliente e estado;
- constraints de competência normalizada, estados, integridade e unicidade;
- triggers de isolamento organizacional e consistência entre lote, contrato, versão e emissor;
- trigger de imutabilidade do snapshot financeiro;
- transições de estado permitidas;
- proteção append-only contra exclusão de obrigação e mutação/exclusão do resultado por contrato.

As seis migrations e os seeds sintéticos foram aplicados e reaplicados em PostgreSQL 18.6 real descartável. Nenhuma base principal ou produtiva foi alterada.

## 4. Modelo

### `billing_runs`

Identifica a operação lógica por organização, unidade e competência. Guarda tipo, status, timezone, versão da regra, ator, correlação, causação, métricas e início/conclusão.

### `billing_items`

Guarda contrato, versão, competência, unidade, cliente, emissor, moeda, valor bruto, snapshot, hash, estado, bloqueio, ator, correlação, causação e timestamps.

### `billing_run_contracts`

Congela o resultado de cada contrato considerado:

- `created`: obrigação criada;
- `reused`: obrigação existente reutilizada;
- `not_eligible`: obrigação não criada, com código e explicação.

Esse registro permite explicar por que um contrato não entrou no faturamento sem transformar inelegibilidade normal em falsa exceção financeira.

## 5. APIs

- `POST /api/v1/billing/runs`
- `GET /api/v1/billing/runs`
- `GET /api/v1/billing/runs/{run_id}`
- `POST /api/v1/billing/runs/{run_id}/reprocess`
- `GET /api/v1/billing/items`
- `GET /api/v1/billing/items/{item_id}`
- `GET /api/v1/billing/exceptions`
- `GET /api/v1/billing/summary`

Os filtros cobrem competência, unidade, cliente, status e execução. O detalhe do item retorna snapshot, hash, auditoria e eventos relacionados. O OpenAPI foi regenerado em `contracts/api/openapi.json`.

## 6. Máquina de estados

- `blocked`: obrigação preservada, mas impedida por dado inválido ou regra pendente;
- `ready`: obrigação íntegra para futura solicitação fiscal;
- `requested`: reservado à solicitação fiscal real da Etapa 6;
- `completed`: reservado à conclusão fiscal real da Etapa 6;
- `cancelled`: reservado a futuro comando de cancelamento lógico aprovado.

Nesta etapa o gerador cria somente `blocked` ou `ready`. `ready` não significa nota emitida. Não existe estado `invoice_issued`.

## 7. Invariantes

- `UNIQUE (contract_id, competence_month)`;
- `UNIQUE (organization_id, business_unit_id, competence_month)` para execução lógica;
- competência persistida somente no primeiro dia do mês;
- contrato, unidade, cliente, versão, emissor e ator pertencem ao mesmo escopo;
- snapshot, hash, valor, competência, versão, emissor e vínculo contratual são imutáveis;
- exclusão de obrigação é proibida;
- transições regressivas ou falsas são rejeitadas;
- contrato iniciado depois do primeiro dia não é elegível na competência parcial;
- contrato suspenso ou encerrado durante todo o mês não é elegível;
- evento ou versão dentro do mês bloqueia o item sem pró-rata inventado;
- nenhuma mudança futura altera obrigação já gerada.

## 8. Snapshot

O snapshot `billing-item-snapshot.v1` inclui:

- competência, início/fim civil e timezone;
- contrato e situação operacional no início do mês;
- versão, vigência e hash da configuração contratual;
- cliente e unidade;
- estabelecimento emissor;
- moeda, modelo, frequência, valor contratual e valor bruto;
- serviços ativos e configuração relevante;
- contatos financeiros congelados;
- bloqueios aplicáveis.

Datas e decimais usam strings. O JSON é serializado com chaves ordenadas e separadores canônicos antes do SHA-256. Alteração contratual futura não recalcula nem substitui o snapshot.

## 9. Idempotência e concorrência

A geração possui quatro camadas:

1. chave HTTP por ator/comando, com detecção de payload divergente;
2. retenção técnica de dez anos para comandos financeiros;
3. lock consultivo transacional por organização/unidade/competência;
4. constraints únicas permanentes no PostgreSQL.

Repetir a mesma chave e payload devolve a mesma resposta. Reutilizar a chave com payload diferente retorna conflito. Uma chave nova para a mesma operação reutiliza o mesmo lote e as mesmas obrigações.

O teste PostgreSQL abriu dois workers/conexões concorrentes tentando inserir a mesma obrigação. Exatamente um criou o registro e o outro recebeu `UniqueViolation`; permaneceu uma única linha. O lock de geração evita trabalho duplicado, e a constraint continua sendo a última defesa.

O reprocessamento permitido nesta etapa recupera a execução congelada de forma idempotente. Ele não corrige, cancela, substitui ou reescreve obrigação, pois essas políticas ainda dependem do Gate A.

## 10. Elegibilidade e valor

- a versão usada é aquela válida no primeiro dia da competência;
- início durante o mês não gera parcial e começa no mês seguinte;
- estado operacional ativo no primeiro dia é exigido;
- suspensão, retomada ou encerramento dentro do mês bloqueia por decisão pendente;
- alteração de versão dentro do mês bloqueia pelo mesmo motivo;
- preço mensal/cobrança mensal usa o valor publicado;
- valor anual/cobrança mensal usa anual÷12 somente quando exato em centavos;
- resíduo produz `GATE_A_ANNUAL_ROUNDING_PENDING`, sem arredondamento ou distribuição inventada;
- IPCA e índices externos não são calculados;
- emissor nunca é escolhido por imposto, custo, heurística ou IA.

## 11. Auditoria, outbox e exceções

Cada obrigação criada registra auditoria oficial e evento versionado na mesma transação:

- `billing.item.ready.v1`;
- `billing.item.blocked.v1`;
- `billing.run.completed.v1`.

O evento pronto contém somente IDs, competência, valor, moeda, emissor, estado e hash; não carrega o snapshot completo nem payload sensível. Nenhum consumidor externo é chamado.

Itens bloqueados também criam exceção operacional com IDs e códigos de bloqueio. Uma falha contratual não aborta o processamento dos demais contratos.

## 12. Frontend

O workspace “Faturar” permite:

- escolher competência e unidade;
- gerar/reutilizar a execução;
- visualizar valor previsto, obrigações, prontos e bloqueados;
- filtrar por cliente e status;
- ver cliente, contrato, unidade, emissor, competência, valor e exceção;
- inspecionar contratos considerados e motivos de não elegibilidade;
- abrir versão usada, snapshot, hash, histórico, auditoria e outbox.

A interface é funcional e responsiva, sem gráficos ou acabamento premium antecipado.

## 13. Testes e cobertura

Foram cobertos:

- competência mensal explícita;
- contrato elegível e iniciado parcialmente;
- versão correta por competência e mudança futura;
- emissor por versão;
- preço mensal e anual exato;
- resíduo anual bloqueado sem arredondamento;
- suspensão intra-competência;
- suspensão, retomada e encerramento em meses completos;
- snapshot e SHA-256;
- imutabilidade histórica;
- repetição da mesma competência;
- mesma chave com payload igual e divergente;
- reprocessamento seguro;
- concorrência com dois workers PostgreSQL;
- organização/unidade e capacidades;
- auditoria, outbox e exceções;
- migration, triggers e constraints reais.

Resultado final de `pnpm quality` contra PostgreSQL 18.6 real:

- Ruff lint: aprovado;
- Ruff format check: 36 arquivos formatados;
- pytest: **37 aprovados, 0 falhas, 0 skips, 0 warnings**;
- cobertura total: **89,43%**;
- módulo de faturamento: **85%**;
- ESLint: aprovado sem warnings;
- TypeScript e build Next.js: aprovados;
- secret scan: aprovado.

## 14. Problemas encontrados e correções

1. O Python não estava no `PATH` da sessão; foi usado o executável da virtualenv do repositório e o `PATH` foi ajustado somente para o gate.
2. A instância PostgreSQL instalada exigia credencial local não disponível no repositório. Foi criado um cluster PostgreSQL 18.6 temporário, isolado e sem dados reais; ele foi encerrado e removido após cada validação.
3. O sandbox bloqueou o token restrito necessário para iniciar o PostgreSQL temporário. A execução foi autorizada fora do sandbox somente para esse processo isolado.
4. O primeiro gate completo encontrou `EPERM` em cache `.next`. Somente o cache recuperável foi removido; o build passou na repetição.
5. O secret scan rejeitou valores padrão, embora não secretos, em `.env.example`. As chaves voltaram a ficar vazias e os defaults permanecem no código e na documentação.
6. SQLite remove timezone de timestamps ao persistir. A serialização da API passou a normalizar timestamps sem offset para UTC, preservando respostas idempotentes idênticas nos testes.

## 15. Decisões de Gate A ainda pendentes

- regra de arredondamento de anual÷12;
- distribuição de centavos residuais;
- regra definitiva para versão contratual que começa dentro da competência;
- suspensão, retomada e encerramento dentro da competência;
- retroatividade excepcional;
- correção ou substituição de obrigação já criada;
- cancelamento e eventual estorno lógico;
- autorização/segregação de editores e operadores financeiros;
- semântica de reprocessamento que pretenda alterar estado financeiro.

A infraestrutura não assume nenhuma dessas regras. Casos intra-competência e resíduos são bloqueados; correção/cancelamento/estorno não possuem comando.

## 16. Riscos para a Etapa 6

- `ready` deve ser consumido por criação idempotente de solicitação fiscal, nunca interpretado como nota emitida;
- a Etapa 6 precisa de sua própria unicidade, máquina de estados, lease e reconciliação antes de qualquer efeito externo;
- timeout após envio não pode causar nova emissão sem consulta ao provedor;
- vínculo estabelecimento→credencial deve ser rígido e isolado;
- snapshot/hash desta etapa devem integrar o contrato da solicitação fiscal;
- callback deve passar por inbox autenticada e deduplicada;
- nenhum evento atual autoriza chamada direta ao legado ou à SEFIN;
- cancelamento, substituição e retorno incerto continuam dependentes de desenho e autorização próprios.

## 17. Parecer

Todos os critérios autorizados para a Etapa 5 foram demonstrados. O domínio gera competências mensais e obrigações únicas, determinísticas, auditáveis e seguras sob repetição e concorrência, preservando explicitamente as decisões ainda pendentes. Nenhuma responsabilidade da Etapa 6 foi iniciada.

# ETAPA 5 APROVADA — PODE AVANÇAR PARA ETAPA 6
