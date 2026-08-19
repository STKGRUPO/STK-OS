# Parecer Técnico — Marco 0 do STK OS V1

**Data:** 19 de agosto de 2026  
**Documentos considerados:** PRD STK OS V1, Relatório de Revisão Técnica e Marco 0 — Decisões Técnicas e de Negócio.  
**Escopo deste parecer:** prontidão para iniciar a implementação da fundação; nenhuma implementação foi realizada.

## 1. Parecer executivo

O Marco 0 resolveu suficientemente os bloqueios arquiteturais que impediam o início do projeto.

Foram corretamente fechadas as decisões de maior impacto:

- redução da primeira entrega para CRM, contratos/faturamento MR e infraestrutura de automação;
- backend como dono das regras, transações e integridade;
- n8n restrito à orquestração;
- API antes de MCP;
- Pessoa e Empresa canônicas no Grupo, com vínculos multiunidade;
- separação entre status e etapa de oportunidade;
- próxima ação derivada de tarefa;
- preservação do sistema Python e integração por adaptador idempotente;
- entidade emissora configurada no contrato, sem decisão tributária automática;
- faturamento por contrato + competência com unicidade no banco;
- atendimento com IA do Lab retirado do caminho crítico;
- stack coerente com o tamanho e a equipe do projeto.

O novo escopo é tecnicamente coerente e permite construir um monólito modular sem dívida arquitetural grave. Não existe mais decisão de negócio indispensável que impeça criar o repositório, o banco inicial, o backend, a autenticação, a auditoria e o CRM.

Há decisões que precisam ser fechadas **antes do módulo financeiro** e outras **antes da produção**, mas elas não devem paralisar a fundação.

# APROVADO PARA IMPLEMENTAÇÃO

A aprovação é para iniciar a construção controlada da V1. Ela não autoriza colocar a emissão fiscal autônoma em produção antes das inspeções e gates descritos neste parecer.

---

## 2. Avaliação das decisões bloqueantes anteriores

| Decisão | Situação após o Marco 0 | Observação |
|---|---|---|
| Backend versus n8n | Resolvida | backend possui regras e invariantes; n8n usa comandos autenticados |
| CRM multiunidade | Resolvida | pessoas e empresas globais; vínculos separados por unidade |
| Status versus etapa | Resolvida | ganho/perdido não são etapas; execução futura fica fora do pipeline comercial |
| Próxima ação | Resolvida | derivada da tarefa futura aberta |
| Escopo da primeira entrega | Resolvida | CRM + contratos/faturamento MR + fundação; uma automação ponta a ponta |
| API versus MCP | Resolvida | API primeiro; MCP adiado |
| Sistema Python | Resolvida em princípio | preservar e envolver em adaptador; detalhes dependem de inspeção |
| Entidade emissora | Resolvida em negócio | seleção explícita e versionada; exige um pequeno refinamento de modelagem |
| Regra inicial de competência | Suficiente para começar | sem pró-rata, início no mês seguinte, valor congelado; arredondamento ainda precisa ser definido antes do financeiro |
| Retenções e regras fiscais | Resolvida para V1 | continuam no Python; STK OS não duplica lógica fiscal |
| Stack | Suficiente para começar | tecnologias-base escolhidas; contratação e hosting podem ser decididos por gate |
| Segurança/LGPD do Lab | Suficiente para V1 | Lab é apenas CRM comercial e dados clínicos ficam fora; política operacional ainda será necessária antes da automação do Lab |
| Autonomia | Resolvida conceitualmente | ciclo, sombra e suspensão definidos; métricas e limites serão definidos por workflow |
| Outlook | Parcial, sem bloquear fundação | caixa indicada; tenant, Graph e permissão precisam ser validados antes da integração |
| n8n Cloud versus self-hosted | Adiável | não interfere no domínio nem na API; decidir antes do ambiente integrado |

---

## 3. Coerência do novo corte de escopo

O corte é correto porque produz uma V1 vertical, não apenas um conjunto de telas:

1. o CRM fornece cadastros, contratos e contatos;
2. o núcleo financeiro transforma contrato vigente em obrigação mensal única;
3. a API e a infraestrutura de eventos conectam os sistemas;
4. o Python executa a emissão fiscal já validada;
5. o Outlook realiza a entrega;
6. auditoria, reconciliação e exceções fecham o ciclo.

Esse recorte prova as capacidades essenciais do STK OS:

- ser fonte oficial de estado;
- aplicar regra transacional;
- operar por interface e API;
- integrar um legado sem reescrita;
- resistir a repetição e falha parcial;
- evoluir um processo real para autonomia.

Também foi acertado retirar atendimento Lab, triagem de e-mail, todos os canais de lead, boleto e MCP. Nenhum desses itens é necessário para validar a fundação. Incluí-los agora multiplicaria fornecedores, dados pessoais, exceções e superfícies de segurança antes de o núcleo estar comprovado.

### Limite que deve ser preservado

“Possível futuramente sem reconstrução” não significa criar tabelas, telas ou abstrações para todas as visões futuras. A fundação precisa oferecer apenas:

- organização, entidade/estabelecimento e unidade;
- usuários/service accounts e autorização;
- API de comandos;
- eventos, auditoria e exceções;
- módulos bem separados.

Não construir agora agenda genérica, agente genérico, engine universal de workflow, prontuário, recebíveis bancários ou plataforma SaaS multiempresa.

---

## 4. Único refinamento arquitetural necessário

O documento usa “entidade jurídica emissora”, mas o identificador fiscal utilizado na emissão é o **estabelecimento inscrito no CNPJ**, que pode ser matriz ou filial.

O modelo recomendado deve distinguir:

- **Grupo:** Grupo STK;
- **Entidade jurídica:** pessoa jurídica/sociedade;
- **Estabelecimento fiscal:** matriz ou filial, com CNPJ completo e dados de emissão;
- **Unidade de negócio:** MR, STK Lab ou Stelli;
- **marca/nome operacional:** quando necessário para exibição.

Aplicação ao caso descrito:

- STK Soluções Empresariais é uma entidade jurídica;
- seu estabelecimento matriz está associado à operação MR;
- STK Lab é uma unidade de negócio ligada ao estabelecimento filial;
- ST Serviços é outra entidade jurídica com seu estabelecimento matriz e pode atuar como emissor de contratos MR;
- Stelli possui sua entidade/estabelecimento e a unidade comercial Stelli.

Portanto, o contrato e sua versão devem referenciar `issuer_establishment_id`, não apenas uma unidade nem um nome textual de empresa. Essa é uma decisão técnica derivada dos fatos já fornecidos; **não exige interromper o projeto para nova decisão de negócio**, salvo se algum dos CNPJs informados não puder efetivamente emitir os serviços correspondentes.

---

## 5. Bloqueios indispensáveis para começar

### Decisões de negócio bloqueantes

**Nenhuma.** O Marco 0 contém informação suficiente para iniciar a fundação e o CRM.

### Preparações operacionais mínimas

Antes do primeiro commit de produção, apenas estas providências práticas são necessárias:

1. definir o repositório oficial e quem possui acesso administrativo;
2. adotar os nomes canônicos dos módulos e entidades do domínio;
3. registrar as decisões do Marco 0 como baseline versionada;
4. confirmar que nenhum secret, certificado, dado clínico ou dado real será colocado no repositório;
5. escolher a estratégia inicial de desenvolvimento local: PostgreSQL/Supabase local compatível com migrações reproduzíveis.

Esses itens são setup do trabalho, não novas decisões estratégicas.

---

## 6. Gates que não bloqueiam a fundação

### Gate A — antes de finalizar o modelo financeiro

- regra de arredondamento do valor anual dividido por 12;
- tratamento de centavos residuais;
- definição exata de `competência` e timezone operacional;
- comportamento no mês de encerramento, suspensão e retomada;
- antecedência e vigência de alteração contratual;
- regra para reprocessamento, cancelamento e substituição;
- conjunto de dados obrigatórios por entidade emissora;
- responsáveis autorizados a alterar versões contratuais.

O backend e o CRM podem começar antes disso. O gerador de itens financeiros não deve ser considerado concluído enquanto essas regras não estiverem formalizadas com exemplos.

### Gate B — antes de integrar o Python

- inspeção do código e do ambiente atual;
- definição da fronteira do adaptador;
- capacidade de idempotência;
- estados e erros observáveis;
- proteção do certificado e das credenciais;
- ambiente seguro de teste;
- estratégia para retorno incerto e reconciliação.

### Gate C — antes de integrar Outlook/n8n

- confirmação literal da mailbox;
- tenant e permissões do Microsoft Graph;
- service accounts e secrets separados;
- decisão n8n Cloud/self-hosted;
- retenção/redação dos dados de execução;
- assinatura/autenticação de webhooks e callbacks.

### Gate D — antes da produção

- Supabase/plano/região contratados e validados;
- RLS e grants revisados;
- backup do banco e dos documentos;
- teste de restauração;
- MFA e menor privilégio;
- observabilidade e alertas;
- política de retenção e resposta a incidentes;
- importação ensaiada e reconciliada;
- testes de carga proporcionais ao volume;
- runbook de falhas e responsáveis.

### Gate E — antes da autonomia

- execução em sombra;
- testes de repetição e concorrência;
- zero emissão duplicada;
- reconciliação com o emissor;
- métricas e janela mínima de validação;
- exceções operáveis;
- kill switch;
- aprovação explícita do dono de negócio para a versão implantada.

---

## 7. Pontos que podem ser resolvidos durante a implementação

| Ponto | Momento-limite |
|---|---|
| Supabase definitivo e plano | antes do ambiente compartilhado/produção; desenvolvimento pode usar stack local compatível |
| Supabase Auth versus equivalente | antes de consolidar autenticação do ambiente compartilhado |
| n8n Cloud versus self-hosted | antes do primeiro fluxo integrado |
| provedor de hospedagem do FastAPI | antes do staging |
| política completa de múltiplos usuários | V2; V1 precisa apenas do schema e de um administrador |
| dashboard executivo completo | após semântica e dados confiáveis |
| thresholds de autonomia | durante validação do faturamento |
| retenção fina por categoria | antes de produção; não impede tabelas iniciais |
| modelo de custo/ROI | após existir telemetria real |
| canais de lead | após estabilização da V1 |
| Google Calendar e automação Lab | projeto posterior |
| MCP | quando existir consumidor e caso de uso real |
| boleto/Itaú | V2 ou posterior, com modelo próprio de recebíveis |

O princípio é adiar a escolha do fornecedor quando ela não muda o domínio, mas não adiar invariantes. Hosting pode esperar; unicidade de competência não.

---

## 8. Ordem exata de implementação

### Etapa 0 — baseline e arquitetura executável

1. criar o repositório oficial e regras de proteção da branch principal;
2. versionar PRD, Marco 0 e decisões arquiteturais;
3. definir convenções, ambientes e tratamento de secrets;
4. criar esqueleto do monorepo, automação de qualidade e documentação;
5. preparar PostgreSQL local e migrações reproduzíveis;
6. criar frontend e backend mínimos apenas para provar o ciclo local e de testes.

**Critério de saída:** qualquer desenvolvedor/agente autorizado consegue reproduzir o ambiente sem credenciais produtivas.

### Etapa 1 — identidade, organização e trilha de controle

1. Grupo, entidade jurídica, estabelecimento fiscal e unidade de negócio;
2. usuário administrador e service accounts;
3. autenticação e autorização básica;
4. IDs de correlação;
5. auditoria append-only;
6. convenção de idempotência;
7. tabelas de inbox, outbox e exceções;
8. health checks e logging seguro.

**Critério de saída:** uma ação autenticada pode alterar um registro de teste, gerar auditoria e produzir evento sem expor secret.

### Etapa 2 — CRM vertical mínimo

1. pessoas e métodos de contato;
2. empresas;
3. vínculos pessoa–empresa;
4. vínculos com unidades;
5. produtos/serviços, origens e motivos de perda;
6. pipelines e etapas;
7. oportunidades e participantes;
8. histórico de etapas;
9. atividades e tarefas;
10. próxima ação derivada;
11. API, telas, busca e visão 360°;
12. importação pequena e auditável.

**Critério de saída:** as três unidades operam o CRM sem duplicação obrigatória de pessoa/empresa.

### Etapa 3 — inspeção do sistema Python

A inspeção ocorre depois de a fundação/API estabelecerem padrões, mas antes de congelar o contrato de emissão e concluir o modelo financeiro. Não alterar o sistema nessa etapa.

**Critério de saída:** relatório técnico do legado, mapa do fluxo atual, riscos, estados, credenciais, estratégia de idempotência e contrato proposto do adaptador.

### Etapa 4 — contratos versionados

1. contrato e vínculo com empresa/unidade;
2. versões contratuais com vigência;
3. entidade/estabelecimento emissor por versão;
4. regras de faturamento;
5. catálogo de serviços contratados;
6. contatos financeiros;
7. reajuste e histórico;
8. suspensão, retomada, renovação e encerramento;
9. telas e API.

**Critério de saída:** é possível reconstruir qual configuração valia em qualquer competência sem sobrescrever história.

### Etapa 5 — núcleo de faturamento

1. fechar regras do Gate A com casos reais;
2. execução de competência;
3. item único por contrato + competência;
4. snapshot de valor, emissor, destinatário e descrição;
5. máquina de estados de solicitação/NF/entrega;
6. comandos idempotentes;
7. exceções e reprocessamento;
8. testes de concorrência e repetição;
9. painel operacional.

**Critério de saída:** gerar a mesma competência repetidamente não duplica obrigação nem altera snapshot existente.

### Etapa 6 — adaptador Python e documentos

1. implementar somente o adaptador aprovado na inspeção;
2. autenticação entre serviços;
3. idempotência de emissão;
4. callback/polling e retorno incerto;
5. armazenamento privado de NF;
6. hash e referência do documento;
7. reconciliação.

**Critério de saída:** uma emissão de teste possui estado rastreável do pedido ao documento, inclusive quando a resposta falha.

### Etapa 7 — Outlook e n8n

1. validar Microsoft Graph e mailbox;
2. implantar n8n na modalidade escolhida;
3. configurar credenciais separadas;
4. criar scheduler e orquestração do lote;
5. chamar apenas APIs autenticadas do STK OS e do adaptador;
6. enviar documento após confirmação da NF;
7. registrar entrega;
8. implementar alertas e tratamento de exceção.

**Critério de saída:** fluxo ponta a ponta funciona em staging e pode ser reexecutado sem efeito duplicado.

### Etapa 8 — migração, operação e autonomia

1. migrar clientes e contratos ativos com relatório de reconciliação;
2. ensaiar a competência com dados controlados;
3. executar em sombra;
4. operar com aprovação temporária;
5. medir falhas, exceções e intervenção;
6. testar backup/restore e runbooks;
7. promover uma versão e escopo específicos para autônomo;
8. manter suspensão automática/manual.

**Critério de saída:** primeiro workflow autônomo com evidência, não apenas com status configurado.

---

## 9. Estrutura inicial recomendada do repositório

Um monorepo é a escolha mais simples para uma equipe pequena e mantém contratos, migrações e documentação sincronizados.

```text
stk-os/
├── apps/
│   ├── web/                 # React/Next.js
│   ├── api/                 # FastAPI e módulos de domínio
│   └── worker/              # processamento assíncrono do mesmo backend
├── integrations/
│   └── nfse-adapter/        # criado/definido após inspeção do Python
├── automations/
│   └── n8n/                 # exports versionados, documentação e fixtures
├── database/
│   ├── migrations/
│   ├── seeds/               # somente dados sintéticos/de referência
│   └── policies/            # RLS, grants e documentação de acesso
├── contracts/
│   ├── api/                 # OpenAPI gerada/versionada
│   └── events/              # schemas de inbox/outbox
├── tests/
│   ├── contract/
│   ├── integration/
│   ├── end-to-end/
│   └── fixtures/            # dados sintéticos e casos anonimizados
├── infrastructure/
│   ├── local/
│   ├── staging/
│   └── production/
├── docs/
│   ├── architecture/
│   ├── adr/                 # decisões arquiteturais
│   ├── domain/
│   ├── runbooks/
│   ├── security/
│   └── product/
├── scripts/                 # tarefas reproduzíveis, sem secrets
├── .env.example             # nomes de variáveis, nunca valores reais
├── README.md
├── CONTRIBUTING.md
└── SECURITY.md
```

### Regras de estrutura

- `apps/api` e `apps/worker` compartilham o mesmo domínio; não criar dois backends independentes.
- `integrations/nfse-adapter` não deve nascer como reescrita do legado. A forma final depende da inspeção.
- workflows do n8n precisam ser exportados, revisáveis e associados a uma versão do contrato da API.
- migração de banco é a única forma de alterar schema em ambientes compartilhados.
- arquivos `.env`, certificados, dumps e payloads reais ficam fora do Git.
- documentação de domínio e ADRs é parte do produto, não material temporário.
- não criar `shared` genérico; bibliotecas compartilhadas só surgem quando houver uso concreto.

---

## 10. Preparação para inspecionar o sistema Python

### 10.1 Antes de abrir ou executar

1. obter a localização oficial do código e identificar qual versão está realmente em produção;
2. fazer uma cópia/branch de trabalho recuperável sem alterar a instalação produtiva;
3. identificar responsável operacional e janela em que testes são permitidos;
4. separar secrets, certificados, tokens, senhas e dados de clientes do material entregue para análise;
5. preparar acesso read-only ao código, configuração sanitizada e documentação existente;
6. obter exemplos anonimizados de sucesso, rejeição, retenções e falha;
7. confirmar se existe ambiente sandbox/homologação do emissor municipal;
8. proibir chamadas reais durante a primeira inspeção.

### 10.2 Inventário técnico

Registrar:

- versão de Python e sistema operacional;
- dependências e forma de instalação;
- entrypoints, interface atual e agendamentos;
- banco/arquivos usados para estado;
- provedores e endpoints externos;
- certificado digital, sem copiar a chave privada;
- formato de entrada e saída;
- geração, localização e retenção de documentos;
- logs e tratamento de erros;
- concorrência e travas;
- mecanismo atual para impedir duplicidade;
- forma de consulta/cancelamento/substituição;
- implantação, backup e procedimento de recuperação;
- testes existentes e cobertura dos casos fiscais.

### 10.3 Mapa comportamental

Construir uma tabela com pelo menos:

- caso de negócio;
- entrada necessária;
- validação executada;
- chamada externa;
- efeito persistido;
- resposta de sucesso;
- erros transitórios;
- erros permanentes;
- retorno incerto;
- ação humana atual;
- possibilidade de repetição segura.

O objetivo é descobrir o comportamento real, não inferir pelo nome das funções.

### 10.4 Casos de aceitação do adaptador

Antes de mudar o legado, definir os resultados esperados:

- mesma chave repetida retorna a mesma emissão;
- duas chamadas concorrentes não emitem duas NFs;
- timeout após envio não leva a nova emissão sem reconciliação;
- rejeição fiscal é distinguida de indisponibilidade;
- documento pertence à NF correta e possui integridade verificável;
- retorno nunca expõe certificado ou secret;
- consulta de status pode ser repetida;
- logs usam correlação do STK OS;
- mudança de emissor não reaproveita credencial errada;
- falha do callback pode ser recuperada por polling.

### 10.5 Saída esperada da inspeção

A inspeção deve produzir, ainda sem reescrever a lógica fiscal:

1. diagrama do fluxo atual;
2. inventário de riscos e dependências;
3. avaliação de operabilidade e segurança;
4. decisão entre wrapper no mesmo processo, serviço separado ou pequena extração;
5. contrato de API e estados;
6. estratégia de idempotência e reconciliação;
7. plano de testes/homologação;
8. mudanças mínimas necessárias no legado;
9. critérios objetivos que, somente se falharem, justificariam reescrita futura.

---

## 11. Ajustes recomendados ao Marco 0

O documento pode ser considerado aprovado com estas correções editoriais/arquiteturais, que não bloqueiam o início:

1. trocar “entidade jurídica emissora” por “estabelecimento fiscal emissor” no modelo técnico, preservando o termo de negócio na interface se desejado;
2. registrar que alterações contratuais possuem vigência futura e não mudam snapshots já gerados;
3. acrescentar arredondamento e centavos residuais à lista de regras a fechar antes do faturamento;
4. dizer explicitamente que logs do n8n não constituem auditoria oficial e podem ter retenção diferente;
5. deixar claro que “tratamento operacional de falhas” no n8n não inclui decidir correção de estado; o backend registra e autoriza reprocessamento;
6. substituir “a coletadora poderá inserir informações no sistema laboratorial” por um requisito futuro sujeito a autorização e procedimento próprio, para não cristalizar operação manual como integração arquitetural;
7. registrar que autonomia sempre se aplica a uma versão, ambiente, unidade e conjunto de ações, nunca ao nome abstrato do workflow.

---

## 12. Conclusão

O Marco 0 cumpriu sua função. O projeto deixou de ser uma visão ampla com fronteiras ambíguas e passou a ter um primeiro produto tecnicamente executável.

Não há razão para manter o parecer anterior negativo quanto ao **início da implementação**. Os pontos ainda abertos possuem momento-limite claro e podem ser resolvidos sem bloquear o CRM e a fundação.

O controle de avanço deve usar três aprovações diferentes:

- **agora:** aprovado para implementar fundação e CRM;
- **após inspeções:** aprovado para integrar Python, Outlook e n8n;
- **após validação operacional:** aprovado para faturamento autônomo em produção.

# APROVADO PARA IMPLEMENTAÇÃO

Condições de governança:

- seguir a ordem deste parecer;
- não antecipar itens retirados da V1;
- não concluir o financeiro antes do Gate A;
- não integrar o Python antes da inspeção;
- não promover autonomia antes de reconciliação, testes de repetição e kill switch;
- registrar decisões novas em ADRs e manter o Marco 0 como baseline.
