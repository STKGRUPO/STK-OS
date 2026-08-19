# MARCO 0 — DECISÕES TÉCNICAS E DE NEGÓCIO
## STK OS — V1

**Status:** atualização após Revisão Técnica do Codex  
**Objetivo:** resolver as decisões bloqueantes antes do início da implementação.

---

# 1. Decisão de escopo da V1

O escopo da primeira versão foi **reduzido deliberadamente**.

A V1 deverá provar três núcleos:

### 1. CRM do Grupo STK
CRM único para:

- MR Engenharia e Consultoria;
- STK Lab;
- Stelli.

A V1 deverá permitir cadastro e gestão de:

- pessoas;
- empresas;
- contatos;
- oportunidades;
- pipelines;
- atividades;
- tarefas;
- próxima ação;
- histórico;
- origem;
- produtos/serviços.

### 2. Contratos + Financeiro Operacional da MR

Inclui:

- contratos;
- histórico/versionamento contratual;
- regras de faturamento;
- competência;
- entidade emissora;
- emissão de NFS-e por integração com o sistema Python existente;
- envio de documentos por Outlook;
- status da emissão;
- logs e exceções.

### 3. Infraestrutura de Automação

Inclui desde a fundação:

- API do STK OS;
- integração com n8n;
- inbox/outbox;
- idempotência;
- logs;
- exceções;
- service accounts;
- auditoria.

---

# 2. Itens retirados da primeira entrega

Não serão requisitos para colocar a V1 em produção:

- atendimento por IA do STK Lab;
- orçamento automático do Lab;
- agendamento automático pelo WhatsApp;
- triagem automática de e-mails da MR;
- captura automática de todos os canais comerciais;
- MCP;
- ERP;
- boletos Itaú;
- cobrança automática;
- módulos Ambiental/Regulatório;
- operação clínica/laboratorial;
- IA própria da Stelli.

Esses itens deverão ser possíveis posteriormente **sem reconstrução da fundação**.

---

# 3. STK Lab na V1

O STK Lab entra inicialmente apenas como uma unidade dentro do CRM.

Objetivo:

- registrar leads;
- controlar oportunidades;
- registrar interesse/orçamento;
- manter próxima ação;
- registrar histórico comercial.

O projeto de atendimento com IA no WhatsApp está sendo avaliado paralelamente.

Quando validado, o fluxo poderá ser conectado posteriormente:

**WhatsApp → n8n → IA de atendimento → API STK OS → CRM**

Portanto, o atendimento por IA **não deverá bloquear a construção da V1**.

O STK OS não deverá armazenar resultados, laudos ou informações clínicas desnecessárias.

---

# 4. Estrutura organizacional e jurídica

O modelo deverá distinguir:

**Grupo → Entidade Jurídica → Unidade de Negócio / Estabelecimento**

## Grupo

**Grupo STK**

## Entidade Jurídica 1

**STK SOLUÇÕES EMPRESARIAIS LTDA**  
CNPJ: **19.140.295/0001-20**

Opera com o título **MR Engenharia e Consultoria**.

Possui filial:

**STK LAB**  
CNPJ: **19.140.295/0002-00**

A alteração contratual confirma que MR e STK Lab pertencem à mesma sociedade, sendo o STK Lab uma filial da STK Soluções Empresariais.

## Entidade Jurídica 2

**ST SERVIÇOS E APOIO ADMINISTRATIVO LTDA**  
CNPJ: **39.813.375/0001-06**.

Função no STK OS:

**entidade jurídica/emissora de apoio vinculada à operação da MR.**

Não deverá ser tratada como quarta unidade comercial do Grupo.

A ST Serviços não é utilizada para faturamento do STK Lab.

## Entidade Jurídica 3

**STELLI CARPEGGIANI FARHERR ROCHA**  
CNPJ: **34.444.229/0001-37**  
Nome fantasia cadastrado: **Capricci Stelli Farherr**.

Unidade de negócio:

**Stelli**

---

# 5. Regra de entidade emissora

Todo contrato faturável da MR deverá possuir explicitamente:

**entidade jurídica emissora**

Exemplos:

- STK Soluções Empresariais Ltda.;
- ST Serviços e Apoio Administrativo Ltda.

O sistema **não deverá escolher automaticamente a entidade emissora com base em tributação**.

A entidade será definida previamente na configuração administrativa/contratual.

Mudanças deverão possuir:

- data de vigência;
- responsável;
- justificativa;
- histórico.

---

# 6. Regra de faturamento contratual da MR

Não haverá cálculo de pró-rata como regra normal.

### Contrato iniciado no final do mês

Não é cobrado o primeiro período parcial.

O faturamento inicia no mês seguinte.

### Parcela mensal

Quando o contrato possuir valor anual:

**Valor bruto mensal = Valor total anual ÷ 12**

O valor da competência deve ser congelado no momento da geração do faturamento.

---

# 7. Reajuste contratual

O índice utilizado atualmente como referência é:

**IPCA**

Porém, o sistema não deverá hardcodar IPCA como única possibilidade.

A regra deverá permitir:

- IPCA;
- percentual fixo;
- outro índice;
- reajuste manual autorizado.

Cada alteração deverá registrar:

- valor anterior;
- novo valor;
- índice;
- percentual;
- data-base;
- vigência;
- responsável;
- justificativa.

O contrato deverá trabalhar com **versões**, não sobrescrever informações históricas.

---

# 8. Alterações contratuais

O sistema deverá permitir alterações posteriores como:

- inclusão de serviço;
- exclusão;
- mudança de valor;
- mudança de entidade emissora;
- suspensão;
- retomada;
- renovação;
- encerramento;
- mudança de condições.

A alteração nunca deve reescrever retroativamente competências já faturadas.

---

# 9. Retenções e regras fiscais

As NFS-e da MR possuem retenções tributárias e existem também tributos posteriormente recolhidos pela empresa.

A lógica atual já está implementada no sistema financeiro Python.

### Decisão

**Não duplicar essa lógica no CRM/STK OS na V1.**

O STK OS deverá manter:

- contrato;
- entidade emissora;
- competência;
- valor contratual;
- solicitação de emissão;
- status;
- resultado da emissão;
- identificação da NF;
- documentos;
- envio.

A lógica fiscal e de retenções continuará inicialmente no sistema Python.

Somente após inspeção técnica será decidido se alguma parte deverá migrar futuramente para o backend.

---

# 10. Sistema financeiro Python existente

O sistema atual deverá ser **preservado**.

Ele já realiza emissão de NFS-e e possui lógica fiscal validada operacionalmente.

O Codex deverá inspecionar antes de propor qualquer reescrita.

A arquitetura-alvo preferencial é envolver o sistema atual em um **adaptador/API idempotente**.

Não utilizar como integração principal:

- automação de interface;
- arquivo compartilhado;
- acesso direto ao banco interno.

---

# 11. Primeiro workflow autônomo

O primeiro fluxo real do STK OS será:

# Faturamento Recorrente MR

### Gatilho

Primeiro dia de cada mês.

### Processo

Scheduler  
→ solicita ao backend a abertura da competência  
→ backend consulta contratos ativos  
→ aplica regras de elegibilidade  
→ considera entidade emissora configurada  
→ cria itens únicos contrato + competência  
→ valida dados obrigatórios  
→ disponibiliza itens prontos  
→ n8n chama o adaptador Python  
→ Python emite a NFS-e  
→ resultado retorna  
→ backend registra a NF  
→ n8n envia ao cliente pelo Outlook  
→ backend registra entrega  
→ execução é reconciliada  
→ exceções são apresentadas ao administrador.

### Regra crítica

`contrato + competência` deve possuir unicidade garantida pelo banco.

Executar novamente o workflow não pode emitir uma segunda NF para a mesma obrigação.

---

# 12. Papel do backend

Foi aceita a recomendação da Revisão Técnica:

> **O backend do STK OS é o dono das regras de negócio e da integridade dos dados.**

O backend será responsável por:

- autorização;
- transações;
- elegibilidade;
- cálculo contratual;
- transições;
- idempotência;
- deduplicação;
- invariantes;
- auditoria oficial;
- políticas de autonomia;
- validação das ações realizadas por automações.

O n8n **não será backend implícito**.

---

# 13. Papel do n8n

O n8n será o **orquestrador**.

Responsabilidades adequadas:

- scheduler;
- eventos;
- conectores;
- Outlook;
- APIs externas;
- chamadas de IA;
- polling;
- callbacks;
- notificações;
- coordenação das etapas assíncronas;
- tratamento operacional de falhas.

O n8n não deverá:

- calcular valor contratual;
- decidir entidade emissora;
- garantir unicidade;
- alterar diretamente tabelas críticas;
- ser fonte oficial de auditoria;
- controlar permissões;
- decidir regras fiscais.

Toda escrita relevante deverá ocorrer por comandos autenticados da API.

---

# 14. API antes de MCP

Aceita a recomendação técnica:

**API primeiro.**

MCP fica fora da primeira versão.

A API deverá ser utilizada por:

- frontend;
- n8n;
- sistema Python;
- futuras integrações;
- futuros agentes.

Quando houver um caso real que justifique MCP, será criado um servidor MCP fino sobre essa API.

---

# 15. CRM — pessoas e empresas globais

Pessoa e Empresa deverão ser cadastros canônicos do **Grupo STK**.

Não deverão possuir uma única unidade fixa.

Uma mesma pessoa ou empresa poderá se relacionar com:

- MR;
- STK Lab;
- Stelli.

O vínculo com cada unidade será modelado separadamente.

Oportunidades, contratos e faturamentos terão unidade explicitamente definida.

---

# 16. Pipelines

Aceita a recomendação de separar:

**etapa** de **status do negócio**.

Status:

- aberto;
- ganho;
- perdido.

“Ganho” e “Perdido” não serão etapas.

### MR

A oportunidade comercial termina quando ganha ou perde.

Execução técnica não será tratada como continuação obrigatória do pipeline comercial da V1.

### Stelli

Mesmo princípio.

Entregas, onboarding e customer success poderão ganhar entidade própria no futuro.

### STK Lab

Na V1 será usado apenas para controle comercial de leads e oportunidades.

Não precisamos modelar toda a jornada laboratorial agora.

---

# 17. Próxima ação

Não será mantido um texto duplicado dentro da oportunidade.

A próxima ação será derivada da **tarefa futura aberta mais próxima**.

Toda oportunidade aberta deverá, após implantação inicial, possuir tarefa futura ou exceção justificada.

---

# 18. Stack técnica aceita como base

## Frontend
**React / Next.js**

## Backend
**FastAPI / Python**

A escolha aproveita conhecimento e integração com o atual sistema financeiro.

## Banco
**PostgreSQL gerenciado**

Candidato preferencial atual:

**Supabase**

Região de São Paulo quando disponível/aplicável.

A contratação definitiva somente ocorrerá quando houver necessidade de ambiente.

## Autenticação
Preferencialmente Supabase Auth ou solução equivalente validada.

## Documentos
Storage privado.

## n8n
Orquestração.

A decisão entre:

- n8n Cloud;
- self-hosted;

será feita posteriormente após piloto e análise de custo/manutenção.

## Lovable
Pode acelerar interface/prototipação.

Não será autoridade sobre:

- banco;
- regras financeiras;
- autorização;
- schema;
- backend transacional.

---

# 19. Usuário da V1

Somente:

**Thiago**

Perfil:

**Administrador total**

A estrutura deverá estar preparada para múltiplos usuários futuros, mas a gestão completa de permissões não será requisito de interface da primeira versão.

---

# 20. Outlook

A automação financeira deverá utilizar uma caixa financeira da MR.

Endereço informado para o projeto:

**financeiro@engenhmr.com.br**

O endereço deverá ser validado literalmente durante a configuração do Microsoft 365/Graph antes do primeiro envio de produção.

---

# 21. STK Lab — agenda e IA

A automação de atendimento do Lab não integra o escopo obrigatório da V1.

O piloto será conduzido paralelamente.

Caso a solução de atendimento com IA seja aprovada, ela poderá posteriormente:

- conversar pelo WhatsApp;
- consultar informações aprovadas;
- gerar atendimento/orçamento;
- criar/atualizar lead no STK OS;
- utilizar agenda externa;
- realizar handoff.

Google Calendar é hoje candidato inicial para agenda.

A coletadora poderá receber a agenda e posteriormente inserir as informações necessárias no sistema laboratorial.

Isso evita tornar uma eventual API do sistema laboratorial um bloqueador.

---

# 22. Dados do STK Lab

Na V1 serão armazenados apenas dados comerciais/operacionais mínimos.

Não armazenar indiscriminadamente:

- resultados;
- laudos;
- diagnósticos;
- histórico clínico;
- informações médicas desnecessárias;
- transcrições contendo dados de saúde.

---

# 23. Autonomia

A meta continua sendo:

**fluxos validados operam sem aprovação humana.**

Ciclo:

**Desenvolvimento → Teste → Validação → Autônomo → Suspenso**

Durante validação poderão existir:

- modo sombra;
- aprovação temporária;
- comparação humana.

Depois de validado, casos normais deverão operar automaticamente.

Humano somente em:

- exceção;
- baixa confiança em decisões probabilísticas;
- falha de integração;
- risco fora das regras;
- incidente.

---

# 24. Primeiro corte de implementação

A primeira entrega não precisa provar todo o sonho do STK OS.

Ela precisa provar:

### CRM manual funcional
- pessoas;
- empresas;
- oportunidades;
- pipelines;
- tarefas;
- histórico;
- visão 360°;
- busca.

### Contratos MR
- cadastro;
- versões;
- entidade emissora;
- faturamento.

### Financeiro operacional
- competência;
- item de faturamento;
- solicitação;
- NF;
- documento;
- envio;
- exceção.

### Infraestrutura
- backend;
- PostgreSQL;
- API;
- auditoria;
- inbox/outbox;
- idempotência;
- service accounts;
- n8n.

### Workflow
**Faturamento recorrente MR de ponta a ponta.**

---

# 25. Próximas automações após estabilização

Ordem inicial:

1. Lead → CRM;
2. triagem de e-mail MR;
3. integrações comerciais;
4. atendimento STK Lab, caso o piloto paralelo seja aprovado;
5. Itaú — boleto, baixa e cobrança;
6. demais automações.

Nenhum desses itens bloqueia a V1.

---

# 26. Critério de sucesso

O Marco inicial será considerado bem-sucedido quando:

1. o CRM central funcionar;
2. MR, Lab e Stelli puderem ser filtrados;
3. cadastros não precisarem ser duplicados por unidade;
4. contratos MR estiverem estruturados;
5. entidades emissoras estiverem separadas de unidades comerciais;
6. uma competência mensal puder ser gerada com segurança;
7. emissão de NF ocorrer via integração com o Python existente;
8. Outlook enviar o documento;
9. registros e auditoria forem persistidos no STK OS;
10. nenhuma repetição puder gerar emissão duplicada;
11. exceções puderem ser identificadas e reprocessadas;
12. o fluxo puder evoluir até operação autônoma.

---

# 27. Pontos ainda sujeitos a inspeção técnica

Não são decisões de negócio pendentes, mas devem ser validados antes da integração final:

### Sistema Python
Inspecionar:

- arquitetura atual;
- método de emissão;
- tratamento das retenções;
- armazenamento de certificados;
- credenciais;
- erros;
- concorrência;
- capacidade de idempotência;
- possibilidade de API.

### Microsoft 365
Validar:

- tenant;
- Graph;
- mailbox;
- permissões;
- endereço literal de envio.

### Supabase
Validar:

- plano;
- região;
- backup;
- restore;
- Storage;
- RLS;
- custo.

### n8n
Comparar:

- Cloud;
- self-hosted;
- custo;
- manutenção;
- segurança;
- backup;
- disponibilidade.

Essas validações deverão resultar em decisão explícita antes da produção.

---

# 28. Decisão de governança tecnológica

O STK OS não deverá crescer pela simples existência de novas ferramentas.

Para cada evolução:

1. qual problema resolve?
2. qual impacto?
3. existe ferramenta pronta melhor?
4. construir ou integrar?
5. qual custo?
6. qual manutenção?
7. qual ROI?
8. quem deixa de executar a tarefa?
9. pode tornar-se autônoma?

Esse princípio orientará todas as próximas versões.

---

# 29. Solicitação ao Codex após este Marco 0

Com base neste documento e no PRD original, realizar nova revisão e responder:

1. As decisões bloqueantes de arquitetura estão suficientemente resolvidas para iniciar a implementação?
2. O novo corte de escopo é tecnicamente coerente?
3. Há alguma decisão **realmente bloqueante** restante antes de criar a fundação do projeto?
4. Quais pontos podem ser resolvidos durante a implementação sem impedir o início?
5. Qual deve ser a ordem exata de implementação?
6. Qual deve ser a estrutura inicial do repositório?
7. Qual preparação é necessária antes de inspecionar/integrar o sistema Python existente?

Ao final, emitir novamente um parecer:

**APROVADO PARA IMPLEMENTAÇÃO**

ou

**NÃO APROVADO PARA IMPLEMENTAÇÃO**

Se o parecer continuar negativo, listar **somente os bloqueios indispensáveis para começar**, separando-os claramente de decisões que podem ser tomadas durante o desenvolvimento.

**Ainda não escrever código.**