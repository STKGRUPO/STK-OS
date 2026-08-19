# PRD FUNCIONAL — STK OS V1

## 1. Visão do produto

O **STK OS** será a plataforma operacional central do Grupo STK.

A V1 deve reunir:

- CRM das três unidades do Grupo;
- contratos e faturamento operacional da MR;
- dados necessários às primeiras automações;
- integração com n8n;
- capacidade para agentes de IA consultar e alterar informações;
- rastreabilidade completa das ações humanas e automáticas.

A plataforma deverá ser construída desde o início para reduzir progressivamente atividades operacionais executadas por Thiago e Stelli que não dependam de julgamento, conhecimento técnico exclusivo ou relacionamento pessoal.

O objetivo não é apenas digitalizar tarefas.

O objetivo é permitir que **processos inteiros possam ser executados de maneira autônoma** depois de validados.

---

# 2. Unidades de negócio

O sistema deverá trabalhar com três unidades:

### MR Engenharia e Consultoria
- Ambiental;
- Assuntos Regulatórios.

### STK Lab
- relacionamento comercial;
- atendimento;
- orçamento;
- agendamento;
- acompanhamento do cliente.

Dados clínicos e resultados laboratoriais continuarão fora do STK OS quando pertencerem ao sistema técnico do laboratório.

### Stelli
- B2C;
- B2B/Varejo.

Todo registro deverá identificar a unidade correspondente.

Também deverá existir uma visão consolidada:

**Grupo STK**

---

# 3. Usuário da V1

Na V1 existirá apenas:

**Thiago**

Permissão:

**Administrador total**

Pode:

- visualizar tudo;
- cadastrar;
- alterar;
- excluir quando permitido;
- configurar;
- acessar as três unidades;
- visualizar financeiro;
- consultar logs;
- visualizar automações;
- alterar status de fluxos;
- acessar configurações.

A estrutura deverá estar preparada para múltiplos usuários e permissões futuras, mas isso não será desenvolvido como prioridade da V1.

---

# 4. Princípio AI First

Todo processo deverá ser analisado utilizando a seguinte pergunta:

> Se Thiago ou Stelli fossem retirados completamente desta tarefa amanhã, o que o sistema e a IA precisariam saber, acessar, decidir e executar para entregar o mesmo resultado?

Cada fluxo deverá definir:

1. gatilho;
2. dados necessários;
3. fontes;
4. regras determinísticas;
5. decisões que exigem IA;
6. ações possíveis;
7. sistemas envolvidos;
8. exceções;
9. KPI;
10. critério de autonomia.

---

# 5. Modelo operacional de automação

Arquitetura funcional:

**EVENTO**
↓  
**n8n**
↓  
**REGRAS**
+
**IA quando necessária**
↓  
**STK OS / sistema relacionado**
↓  
**AÇÃO**
↓  
**REGISTRO**
↓  
**MÉTRICAS / EXCEÇÃO**

O n8n será tratado como **orquestrador dos workflows**.

O STK OS será a principal fonte de estado dos processos comerciais e dos dados operacionais incluídos na V1.

A IA será utilizada somente quando houver necessidade de:

- interpretar;
- classificar;
- resumir;
- analisar;
- gerar conteúdo;
- selecionar caminhos com base em contexto.

Regras objetivas, cálculos, conferências e validações deverão utilizar lógica determinística sempre que possível.

---

# 6. Níveis de maturidade dos workflows

Todo workflow deverá possuir um status:

### DESENVOLVIMENTO
Ainda sendo construído.

### TESTE
Executa em ambiente controlado.

### VALIDAÇÃO
Executa processo real, mas determinadas ações ainda exigem aprovação.

### AUTÔNOMO
Executa sozinho dentro das condições previamente validadas.

### SUSPENSO
Fluxo temporariamente impedido de executar.

A meta não será manter aprovação humana permanentemente.

Após atingir os critérios de confiabilidade definidos, o workflow deverá passar para **AUTÔNOMO**.

---

# 7. Núcleo de dados do CRM

## 7.1 Pessoa

Campos mínimos:

- ID;
- nome;
- CPF quando necessário;
- telefone;
- WhatsApp;
- e-mail;
- cidade;
- UF;
- origem;
- unidade relacionada;
- responsável;
- observações;
- status;
- data de criação;
- data de atualização.

O sistema deverá verificar duplicidade principalmente por:

- telefone;
- e-mail;
- CPF quando disponível.

---

# 8. Empresa

Campos:

- ID;
- razão social;
- nome fantasia;
- CNPJ;
- telefone;
- e-mail geral;
- e-mail financeiro;
- endereço;
- cidade;
- UF;
- site;
- unidade relacionada;
- responsável;
- status;
- observações;
- data de criação;
- data de atualização.

Uma empresa poderá possuir várias pessoas vinculadas.

---

# 9. Relacionamento Pessoa × Empresa

Deverá permitir vincular pessoas a empresas.

Exemplos:

- proprietário;
- financeiro;
- administrativo;
- responsável técnico;
- compras;
- RH;
- gerente;
- outro.

Uma pessoa poderá futuramente estar vinculada a mais de uma empresa.

---

# 10. Negócio / Oportunidade

Campos mínimos:

- ID;
- unidade;
- pessoa;
- empresa quando aplicável;
- título;
- produto/serviço;
- pipeline;
- etapa;
- status;
- valor;
- moeda;
- origem;
- responsável;
- data de entrada;
- data prevista de fechamento;
- próxima ação;
- data da próxima ação;
- última interação;
- motivo de perda;
- observações;
- data de criação;
- data de atualização.

Status deverá ser separado da etapa:

- aberto;
- ganho;
- perdido.

---

# 11. Histórico de etapas

Toda mudança deverá criar registro permanente contendo:

- negócio;
- etapa anterior;
- nova etapa;
- usuário/agente responsável;
- data e hora;
- origem da alteração;
- observação quando aplicável.

Esse histórico será utilizado para calcular posteriormente:

- conversão;
- tempo em cada etapa;
- ciclo de venda;
- pontos de perda;
- gargalos.

---

# 12. Atividades e interações

O STK OS deverá registrar:

- WhatsApp;
- e-mail;
- ligação;
- reunião;
- proposta;
- follow-up;
- tarefa;
- atendimento;
- observação;
- interação automática;
- ação executada por IA.

Campos:

- tipo;
- data;
- responsável;
- pessoa;
- empresa;
- negócio;
- conteúdo/resumo;
- origem;
- próximo passo;
- executado por humano ou agente;
- workflow relacionado.

---

# 13. Próxima ação

Todo negócio aberto deverá possuir:

- próxima ação;
- data;
- responsável.

O sistema deverá sinalizar:

- ações vencidas;
- negócios sem próxima ação;
- negócios parados acima do limite definido.

Posteriormente, workflows poderão criar ou executar automaticamente essas ações.

---

# 14. Motivos de perda

Negócio perdido obrigatoriamente deverá possuir motivo.

Lista inicial editável:

- preço;
- sem retorno;
- decidiu não contratar;
- concorrente;
- prazo;
- solução não adequada;
- adiamento;
- orçamento não aprovado;
- outro.

---

# 15. Origem dos leads

Todo lead deverá possuir origem.

Exemplos:

- indicação;
- Instagram;
- WhatsApp;
- Google;
- site;
- cliente da base;
- parceiro;
- campanha;
- evento;
- outbound;
- outro.

---

# 16. Pipeline MR

Etapas iniciais:

1. Lead
2. Qualificação
3. Demanda identificada
4. Proposta
5. Follow-up
6. Negociação
7. Ganho
8. Perdido

Após ganho, o cliente deixa o pipeline comercial e poderá possuir:

- contrato;
- projeto/serviço;
- pós-venda;
- oportunidade futura.

Produtos/serviços serão classificados posteriormente em Ambiental e Regulatório.

---

# 17. Pipeline STK Lab

Etapas iniciais:

1. Novo contato
2. Necessidade identificada
3. Orçamento
4. Aguardando cliente
5. Agendamento
6. Confirmado
7. Compareceu
8. Atendimento concluído
9. Pós-atendimento

O objetivo é permitir medir:

- contatos;
- orçamentos;
- conversão;
- agendamentos;
- comparecimento;
- abandono;
- tempo de resposta.

---

# 18. Pipeline Stelli B2C

Etapas:

1. Lead
2. Necessidade identificada
3. Produto recomendado
4. Lista de espera/oferta
5. Follow-up
6. Pagamento
7. Onboarding
8. Entrega
9. Pós-venda
10. Próxima oferta

Produtos iniciais:

- Pirâmide do Vestir™;
- Laboratório PV;
- Coloração Pessoal;
- produtos digitais futuros.

---

# 19. Pipeline Stelli B2B

Etapas:

1. Lead empresa
2. Qualificação
3. Diagnóstico
4. Proposta
5. Follow-up
6. Negociação
7. Ganho
8. Perdido
9. Execução
10. Renovação/nova oportunidade

Serviços:

- VM recorrente;
- treinamento;
- montagem de loja;
- projetos especiais;
- outras soluções B2B.

---

# 20. Contratos — MR

A V1 deverá possuir cadastro de contratos porque ele será a base do faturamento recorrente.

Campos:

- ID;
- empresa;
- unidade;
- serviço;
- número interno;
- data de início;
- data de término;
- renovação;
- status;
- valor;
- periodicidade;
- dia de faturamento;
- condição de pagamento;
- emissão de NF;
- emissão de boleto;
- descrição padrão da NFS-e;
- e-mail financeiro;
- observações;
- suspensão de faturamento;
- última competência faturada;
- data de criação;
- atualização.

Status:

- ativo;
- suspenso;
- encerrado;
- em renovação.

---

# 21. Faturamento MR

Entidade específica para registrar cada competência faturada.

Campos:

- ID;
- contrato;
- empresa;
- competência;
- valor;
- status;
- número da NF;
- data da emissão;
- arquivo/link;
- e-mail enviado;
- data do envio;
- boleto;
- vencimento;
- pagamento;
- data de pagamento;
- workflow;
- exceção;
- observações.

Regra fundamental:

**contrato + competência deve ser único.**

O sistema não poderá permitir faturamento duplicado da mesma competência.

---

# 22. Workflow prioritário 01 — Faturamento recorrente MR

## Gatilho

Dia 1º de cada mês.

## Processo

n8n inicia  
→ consulta contratos ativos  
→ identifica contratos elegíveis  
→ verifica periodicidade  
→ verifica competência  
→ verifica duplicidade  
→ valida dados obrigatórios  
→ envia solicitação ao mecanismo de emissão de NF  
→ recebe confirmação  
→ registra NF  
→ obtém documento  
→ envia pelo Outlook  
→ registra envio  
→ gera resumo final.

## V1

Integrar inicialmente com o mecanismo já existente no sistema financeiro Python.

## Evolução

Substituir ou integrar diretamente com o serviço de emissão quando isso estiver tecnicamente validado.

## Futura extensão Itaú

Após a emissão:

→ gerar boleto  
→ salvar boleto  
→ enviar NF + boleto  
→ consultar pagamento  
→ baixar recebimento  
→ iniciar cobrança se vencido.

---

# 23. Workflow prioritário 02 — Lead automático do Grupo

## Gatilhos possíveis

- WhatsApp;
- formulário;
- site;
- integração;
- outros canais.

## Processo

n8n recebe lead  
→ consulta CRM  
→ verifica duplicidade  
→ cria ou atualiza contato  
→ IA identifica unidade  
→ IA identifica interesse  
→ cria negócio  
→ associa produto/serviço  
→ cria próxima ação  
→ registra origem  
→ inicia fluxo comercial correspondente.

Meta:

**nenhum lead sem cadastro ou acompanhamento.**

---

# 24. Workflow prioritário 03 — Atendimento STK Lab

Objetivo:

retirar Thiago do atendimento rotineiro.

## Fluxo

WhatsApp  
→ n8n recebe mensagem  
→ identifica contato  
→ CRM consulta histórico  
→ IA identifica intenção  
→ consulta base autorizada  
→ responde dúvidas permitidas  
→ gera orçamento quando aplicável  
→ oferece/agrega informações de agenda quando disponível  
→ registra interação  
→ atualiza etapa do funil  
→ cria próxima ação.

Possíveis intenções:

- preço;
- exame;
- preparo;
- horário;
- endereço;
- pagamento;
- agendamento;
- confirmação;
- dúvida geral.

Exceções devem ser encaminhadas para humano.

A meta é que casos normais se tornem **autônomos** após validação.

---

# 25. Workflow prioritário 04 — E-mail e documentos MR

## Gatilho

Novo e-mail recebido.

## Processo

Outlook  
→ n8n  
→ identifica remetente  
→ consulta cliente  
→ IA classifica mensagem  
→ identifica processo/assunto  
→ resume conteúdo  
→ registra interação  
→ identifica necessidade de ação  
→ cria tarefa ou executa workflow correspondente.

Categorias iniciais:

- cliente;
- órgão público;
- documento;
- solicitação;
- cobrança;
- exigência;
- informação;
- proposta;
- outro.

Evolução futura:

- armazenamento automático;
- associação a processo;
- análise de vencimento;
- cobrança documental;
- preparação de resposta.

---

# 26. Integrações previstas

## V1 prioritárias

- STK OS;
- n8n;
- OpenAI/IA;
- Outlook;
- sistema financeiro Python;
- WhatsApp quando definido o provedor.

## Preparadas para próxima etapa

- Itaú;
- Kiwify;
- Cora;
- Sialab;
- Instagram/Meta;
- sites/formulários;
- sistemas MR Ambiental/Regulatório.

---

# 27. MCP e API

O sistema deverá nascer preparado para operação por agentes.

Ações importantes deverão possuir interface programática.

Exemplos:

- consultar pessoa;
- criar pessoa;
- atualizar pessoa;
- consultar empresa;
- criar empresa;
- criar negócio;
- atualizar negócio;
- mover etapa;
- registrar interação;
- definir próxima ação;
- consultar contratos;
- consultar faturamentos;
- registrar NF;
- registrar envio;
- consultar histórico.

A implementação técnica de API/MCP será definida posteriormente pelo Codex.

O requisito funcional é:

> tudo que um usuário autorizado consegue realizar operacionalmente no sistema deverá, quando seguro e adequado, poder ser realizado programaticamente por workflow ou agente.

---

# 28. Auditoria e logs

Toda ação relevante deverá registrar:

- data/hora;
- usuário ou agente;
- entidade;
- ação;
- antes;
- depois;
- origem;
- workflow;
- resultado.

Workflows deverão registrar:

- início;
- término;
- sucesso;
- falha;
- exceção;
- intervenção humana;
- duração.

---

# 29. Dashboard executivo

## Grupo

- novos leads;
- oportunidades abertas;
- valor em pipeline;
- negócios ganhos;
- negócios perdidos;
- conversão;
- tarefas vencidas;
- negócios parados.

Filtros:

- período;
- unidade;
- origem;
- produto;
- pipeline.

---

# 30. Dashboard MR

Além do CRM:

- contratos ativos;
- contratos próximos do vencimento;
- faturamentos previstos;
- faturados;
- NFs emitidas;
- valor faturado;
- falhas de faturamento;
- pendências.

---

# 31. Dashboard STK Lab

- contatos;
- orçamentos;
- agendamentos;
- conversão orçamento → agendamento;
- comparecimento;
- tempo de primeira resposta;
- atendimentos realizados;
- abandonos.

---

# 32. Dashboard Stelli

- leads;
- B2C/B2B;
- produto procurado;
- lista de espera;
- vendas;
- conversão;
- clientes novos;
- clientes antigos;
- reativação;
- próxima oferta.

---

# 33. Dashboard de automação

Deverá mostrar:

- workflows ativos;
- status de maturidade;
- execuções;
- sucesso;
- erro;
- exceções;
- intervenções humanas;
- percentual autônomo.

Objetivo futuro:

medir quanto da operação está sendo realizada sem intervenção manual.

---

# 34. Indicador de capacidade liberada

Quando possível, cada workflow deverá possuir:

- tempo médio manual anterior;
- volume mensal;
- tempo automatizado;
- horas liberadas;
- custo da automação;
- impacto financeiro estimado.

Objetivo:

medir ROI das automações e evitar tecnologia sem utilização ou benefício real.

---

# 35. Requisitos de experiência

A interface deverá ser:

- simples;
- rápida;
- limpa;
- responsiva;
- adequada para desktop e celular;
- com poucos cliques;
- orientada a ação.

Tela principal do CRM:

**Kanban**

Cada cartão deverá mostrar no mínimo:

- negócio;
- pessoa/empresa;
- valor;
- serviço;
- última interação;
- dias na etapa;
- próxima ação.

Arrastar deverá alterar etapa e criar histórico.

---

# 36. Busca global

O sistema deverá permitir buscar:

- pessoa;
- empresa;
- telefone;
- e-mail;
- CNPJ;
- contrato;
- negócio.

A busca deverá levar rapidamente ao histórico completo do relacionamento.

---

# 37. Visão 360° do cliente

Pessoa ou empresa deverá possuir uma página única contendo:

- dados cadastrais;
- negócios;
- contratos;
- interações;
- propostas;
- tarefas;
- faturamentos quando aplicável;
- histórico;
- próximas ações.

Objetivo:

não precisar procurar informação em várias telas para entender o relacionamento.

---

# 38. Dados históricos e migração

As bases atuais estão distribuídas entre:

- WhatsApp;
- Excel;
- Outlook;
- Kiwify;
- Sialab;
- Cora;
- Instagram;
- controles internos.

A V1 deverá estar preparada para importação.

Não será obrigatório migrar tudo antes do início dos testes.

Prioridade:

1. clientes ativos;
2. contratos ativos;
3. leads em andamento;
4. bases de reativação;
5. histórico relevante.

---

# 39. Segurança funcional

A V1 deverá prever desde a arquitetura:

- autenticação;
- autorização;
- logs;
- proteção contra duplicidade;
- backups;
- isolamento futuro por usuário/unidade;
- dados exportáveis;
- gerenciamento seguro das credenciais das integrações.

Credenciais externas não deverão ficar expostas no frontend.

Detalhamento técnico será validado no Codex.

---

# 40. STK Lab — limite de dados

A V1 não deverá substituir o sistema laboratorial.

O STK OS poderá manter informações comerciais e operacionais necessárias para:

- lead;
- orçamento;
- contato;
- agendamento;
- relacionamento;
- follow-up.

Dados clínicos e resultados de exames não deverão ser replicados indiscriminadamente para o CRM.

---

# 41. Fora do escopo

Ficam explicitamente fora da V1:

- ERP;
- contabilidade completa;
- folha;
- SPED;
- estoque;
- compras;
- patrimônio;
- sistema clínico laboratorial;
- operação ambiental completa;
- operação regulatória completa;
- dezenas de workflows simultâneos;
- IA própria da Stelli;
- plataforma comercial para terceiros.

Esses itens poderão surgir posteriormente.

---

# 42. Fase 1 — Construção

Construir apenas o núcleo necessário para provar o STK OS:

### CRM
- pessoa;
- empresa;
- oportunidade;
- pipeline;
- histórico;
- atividades;
- próxima ação.

### Grupo
- unidades;
- filtros.

### MR Financeiro
- contratos;
- competências;
- faturamentos.

### Integração
- API suficiente para n8n;
- logs básicos.

### Interface
- kanban;
- cadastros;
- visão 360°;
- dashboards básicos.

---

# 43. Fase 1A — Primeiro workflow

**Faturamento recorrente MR**

Escolhido como primeiro workflow determinístico por já existir parte do processo de emissão de NF no sistema Python.

Objetivo:

provar a integração:

**STK OS → n8n → sistema existente → Outlook → STK OS**

---

# 44. Fase 1B — Segundo workflow

**Lead → CRM**

Objetivo:

provar criação automática e operação do CRM por workflow.

---

# 45. Fase 1C — Terceiro workflow

**Atendimento STK Lab**

Objetivo:

provar IA conversacional integrada ao CRM e reduzir diretamente dependência operacional do Thiago.

---

# 46. Fase 1D — Quarto workflow

**Triagem de e-mails MR**

Objetivo:

provar leitura, classificação e geração automática de tarefas/interações.

---

# 47. Critérios de sucesso da V1

A V1 será considerada validada quando:

- CRM único estiver funcionando;
- MR, Lab e Stelli puderem operar separadamente;
- cadastro e histórico forem confiáveis;
- contratos MR puderem ser registrados;
- faturamento por competência possuir controle de duplicidade;
- n8n conseguir consultar e atualizar a plataforma;
- logs permitirem auditar ações;
- pelo menos um workflow real operar de ponta a ponta;
- workflow validado conseguir passar para modo autônomo;
- plataforma não exigir reconstrução para receber os próximos módulos.

---

# 48. Princípio de evolução

Nenhuma funcionalidade deverá ser adicionada apenas porque é tecnicamente possível.

Toda evolução deverá responder:

**Qual problema resolve?**

**Quanto impacto gera?**

**Quem deixará de executar essa tarefa?**

**Qual receita, margem, capacidade ou redução de risco gera?**

**Existe solução pronta melhor?**

**Vale construir ou integrar?**

O STK OS deverá crescer somente quando houver justificativa operacional ou econômica.

---

# 49. Visão futura

A V1 não pretende ser o produto final.

Ela deverá criar a fundação para que futuramente o Grupo STK possa integrar:

- Ambiental;
- Regulatórios;
- condicionantes;
- monitoramento normativo;
- documentos;
- atendimento;
- financeiro;
- vendas;
- contratos;
- automações;
- agentes especializados;
- produtos de IA.

A possibilidade de transformar módulos validados internamente em soluções comercializáveis deverá ser considerada no futuro, mas não deverá aumentar o escopo da V1.

---

# 50. Norte estratégico

O sistema deverá ajudar a responder continuamente:

> O que Thiago ou Stelli ainda estão executando hoje que um processo estruturado, uma automação ou uma IA já poderia executar com qualidade equivalente ou superior?

Quando a resposta indicar que a participação dos sócios não agrega valor específico, essa atividade se torna candidata a automação, delegação ou autonomia.