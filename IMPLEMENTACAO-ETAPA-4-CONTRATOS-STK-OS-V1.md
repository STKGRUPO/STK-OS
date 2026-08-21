# Implementação da Etapa 4 — Contratos versionados — STK OS V1

- Data de conclusão: 2026-08-20
- Escopo: domínio contratual oficial do STK OS
- Resultado: aprovado

## 1. Resultado executivo

A Etapa 4 implementa contratos com identidade administrativa estável e configuração temporal preservada em versões imutáveis. O sistema responde qual configuração era válida em uma data arbitrária, distingue passado, presente e futuro e mantém emissor, valores, serviços e contatos no snapshot correspondente.

Não foram implementados competência financeira, geração de cobrança, parcelas, recebimentos, NFS-e, cálculo fiscal, motor Python, certificados, Outlook, n8n, boleto, Itaú, IA, MCP ou módulos operacionais posteriores.

## 2. Implementação realizada

- criação, listagem e consulta detalhada de contratos;
- primeira versão e versões subsequentes completas;
- agendamento de versão futura;
- consulta da configuração vigente por data arbitrária;
- histórico com vigência final derivada e diferenças entre versões;
- troca de valor, emissor e condições somente por nova versão;
- inclusão e exclusão versionada de serviços do catálogo CRM;
- contatos financeiros versionados por referência ao cadastro canônico;
- suspensão, retomada, encerramento e renovação como eventos operacionais próprios;
- capacidades contratuais e escopo por unidade;
- auditoria, correlação, idempotência e outbox transacionais;
- interface desktop e móvel para validação operacional.

## 3. Modelo de dados

### `contracts`

Identidade administrativa com organização, unidade, cliente canônico, número interno, status administrativo, assinatura, início, tipo, responsável, observações controladas, criador e timestamps.

### `contract_versions`

Snapshot imutável com número sequencial, início de vigência, emissor fiscal estruturado, moeda, modelo de preço, valor `numeric(18,2)`, periodicidade, parcelas informativas para contrato anual, dia de referência, prazo de pagamento, descrição futura de faturamento, campos de reajuste, tipo/motivo da mudança, hash SHA-256, ator e timestamp.

O fim da vigência é derivado como o dia anterior ao início da próxima versão. Não é armazenado e, portanto, não pode divergir da sequência real.

### `contract_version_services`

Snapshot de serviço com referência opcional ao catálogo CRM, descrição contratual, quantidade `numeric`, valor unitário opcional e indicador ativo/inativo.

### `contract_version_contacts`

Referência a método de contato canônico, papel do destinatário, finalidade e canal preferencial. A versão exige exatamente um destinatário financeiro principal.

### `contract_operational_events`

Linha do tempo append-only de `suspended`, `resumed`, `terminated` e `renewed`, com data efetiva, motivo, ator e eventual versão de renovação.

## 4. Migration e dados sintéticos

A migration `database/migrations/005_versioned_contracts.sql` cria tabelas, índices, constraints e gatilhos de domínio. Os gatilhos validam organização/unidade/cliente/atores, emissor, serviços, contatos, sequência temporal, eventos e imutabilidade contra `UPDATE` e `DELETE`.

O seed `002_synthetic_crm_reference.sql` recebeu somente capacidades contratuais sintéticas e suas associações aos papéis existentes. Nenhum dado, credencial ou certificado real foi incluído.

A migration foi executada do zero em PostgreSQL 18.4 real na base descartável `stk_os_test`, cujo nome é validado antes da recriação pelo teste. Migrations e seeds foram reaplicados duas vezes para comprovar reprodutibilidade e idempotência.

## 5. APIs

- `GET /api/v1/contracts/reference-data`
- `POST /api/v1/contracts`
- `GET /api/v1/contracts`
- `GET /api/v1/contracts/{contract_id}`
- `GET /api/v1/contracts/{contract_id}/history`
- `GET /api/v1/contracts/{contract_id}/configuration?date=AAAA-MM-DD`
- `POST /api/v1/contracts/{contract_id}/versions`
- `POST /api/v1/contracts/{contract_id}/schedule`
- `POST /api/v1/contracts/{contract_id}/suspend`
- `POST /api/v1/contracts/{contract_id}/resume`
- `POST /api/v1/contracts/{contract_id}/terminate`
- `POST /api/v1/contracts/{contract_id}/renew`

Todas as escritas exigem `Idempotency-Key`, capacidade adequada, escopo de unidade e ator autenticado. Não existe endpoint de edição direta de versão. O contrato OpenAPI foi regenerado em `contracts/api/openapi.json`.

## 6. Interface

O workspace “Contratos” foi incorporado ao shell existente e oferece:

- filtros por unidade, cliente, status, emissor e data de vigência;
- indicadores de versões vigentes, futuras e contratos suspensos;
- criação da identidade administrativa;
- publicação da primeira versão e de nova versão futura;
- seleção de emissor, modelo, valor, periodicidade, reajuste, serviços e contato;
- drawer com configuração atual, versões futuras e históricas;
- diferenças visuais de valor, emissor e inclusão/exclusão de serviço;
- consulta da configuração por data;
- eventos operacionais e seus formulários explícitos;
- tabela adaptada para cartões em telas móveis.

A validação no navegador integrado cobriu desktop 1440×900 e móvel 390×844. Login, listagem, drawer, consulta de v1 e v2 por data e formulários foram inspecionados sem erros ou avisos de console.

## 7. Invariantes implementadas

- primeira versão obrigatoriamente `initial`, número 1 e na data inicial do contrato;
- versões seguintes sequenciais e com início estritamente crescente;
- ausência de lacunas ou sobreposição pela vigência final derivada;
- mudança retroativa normal rejeitada; correção histórica futura deve ser explícita;
- versões, serviços, contatos e eventos operacionais append-only;
- valor monetário tratado como `Decimal`/`numeric`, nunca `float`;
- emissor sempre é estabelecimento fiscal ativo da mesma organização;
- cliente pertence à organização e tem vínculo ativo com a unidade;
- serviço de catálogo pertence à organização e unidade do contrato;
- contato pertence ao cliente ou a pessoa com vínculo ativo com ele;
- exatamente um contato financeiro principal por snapshot;
- suspensão, retomada e encerramento seguem ordem cronológica e estado válido;
- renovação referencia uma versão `renewal` com a mesma data efetiva;
- permissões e vínculos de papel limitados à unidade são respeitados;
- toda escrita relevante registra auditoria e outbox na mesma transação.

## 8. Testes e cobertura

Foram adicionados testes de criação, primeira versão, repetição idempotente, versão futura, vigência por data, valor, emissor, serviço incluído/excluído, histórico, renovação, suspensão, retomada, encerramento, autorização, escopo por unidade, auditoria, `Decimal`, rejeição de sobreposição e ausência de rota de sobrescrita.

O teste PostgreSQL comprova ainda isolamento organizacional no banco, constraints, gatilhos append-only e precisão numérica.

Resultado final de `pnpm quality`:

- Ruff lint: aprovado;
- Ruff format check: aprovado;
- pytest: **28 aprovados, 0 falhas, 0 skips**;
- cobertura total: **89,36%** (mínimo exigido: 80%);
- módulo de contratos: **83%**;
- ESLint: aprovado com zero warnings;
- TypeScript e build Next.js de produção: aprovados;
- secret scan: aprovado.

## 9. Falhas encontradas e correções

- uma fixture com segunda entidade jurídica alterou a ordenação esperada por teste legado; o código sintético foi ajustado sem mudar a regra do produto;
- a primeira execução final do gate encontrou somente formatação Ruff na validação de responsável; a formatação canônica foi aplicada e o gate completo foi repetido;
- o navegador local abriu inicialmente pela origem `127.0.0.1`, bloqueada pelo Next em modo dev; a validação foi repetida pela origem publicada `localhost`;
- a primeira inspeção móvel revelou tabela larga com rolagem horizontal; ela foi convertida em cartões responsivos e validada novamente;
- o gerador OpenAPI emitia CRLF no Windows; passou a fixar LF para evitar aviso de normalização no Git.

## 10. ADRs e documentação

- `docs/adr/0007-contratos-versionados.md`: decisão sobre snapshots temporais, vigência derivada, imutabilidade e eventos;
- `docs/domain/contratos-versionados.md`: agregados, estados, linha do tempo, isolamento e consulta futura;
- `docs/domain/glossario.md`: novos termos do domínio;
- `docs/architecture/visao-geral.md`: módulo contratual e limites da etapa;
- `README.md`: escopo executável atualizado para a Etapa 4.

## 11. Pendências e riscos

- correção histórica excepcional não está implementada; exige desenho futuro de autorização elevada e evidência obrigatória;
- status administrativo `archived` está preparado no modelo, mas não recebeu comando de arquivamento nesta entrega;
- importação de contratos não foi construída, conforme escopo;
- a base local principal existente apresentou drift prévio de checksum nas migrations 003/004. Ela foi preservada sem reparo destrutivo. A validação oficial usou uma base PostgreSQL real descartável reconstruída integralmente com os arquivos atuais; antes de promover em um ambiente com esse drift, sua origem deverá ser reconciliada operacionalmente.

Esses pontos não comprometem o domínio nem a execução em uma base limpa, mas devem permanecer visíveis no planejamento posterior.

## 12. Decisões que permanecem para o Gate A financeiro

- definição formal de competência e timezone/data de corte;
- política de geração, aprovação, reprocessamento e cancelamento de obrigações;
- regra aprovada para contrato anual cobrado mensalmente, incluindo arredondamento;
- pró-rata de início, suspensão, retomada e encerramento;
- comportamento quando versão futura ou evento ocorre dentro de uma competência;
- modelo e imutabilidade do snapshot financeiro depois de gerado;
- política excepcional de correção histórica e seus efeitos em snapshots existentes;
- estados e segregação de funções do fluxo financeiro;
- tratamento de inadimplência, recebimento, cobrança e conciliação;
- fronteira posterior com solicitação fiscal e serviço Python privado, sem antecipar sua integração.

**ETAPA 4 APROVADA — PODE AVANÇAR PARA ETAPA 5**
