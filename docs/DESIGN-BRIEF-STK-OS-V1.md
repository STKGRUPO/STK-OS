# DESIGN BRIEF — STK OS V1

**Status:** direção visual e de experiência aprovada para preparação do pacote visual sanitizado ao Lovable  
**Data:** 20 de agosto de 2026  
**Direção:** Curadoria C + A — Executive Flow OS + acabamento premium

## 1. Visão do produto

O STK OS não deve parecer um ERP tradicional, um CRM genérico ou um dashboard cheio de indicadores. A experiência deve transmitir que o sistema conhece o contexto do negócio, trabalha em segundo plano e apresenta ao usuário somente o que exige atenção, decisão ou ação.

Princípio central:

> **O sistema sabe tudo. A tela mostra só o que importa agora.**

A experiência deve ser calma, premium, rápida, confiável e orientada à decisão.

## 2. Direção escolhida — C + A

### C — Executive Flow OS

Responsável pela experiência:

- atenção antes de navegação;
- exceções antes de dashboards;
- comando antes de procura manual;
- contexto antes de menus profundos;
- IA embutida no fluxo, não em um chatbot separado;
- automação invisível quando tudo está funcionando;
- problemas sobem automaticamente para a atenção do usuário;
- informações detalhadas ficam nos módulos correspondentes.

### A — Premium Calm UI

Responsável pelo acabamento visual:

- muita clareza e respiro;
- tipografia refinada e legível;
- hierarquia visual forte;
- sidebar discreta;
- poucas cores;
- cards com presença leve;
- tabelas densas, porém organizadas;
- sombras mínimas;
- ícones consistentes;
- movimentos sutis e funcionais;
- evitar aparência de ERP brasileiro ou template SaaS genérico.

## 3. Referências conceituais

As referências são usadas por princípio, não para cópia visual:

- **Attio:** CRM moderno, contexto, registros canônicos e IA integrada ao trabalho;
- **Linear:** calma visual, consistência, velocidade e hierarquia;
- **Raycast:** comando universal, teclado e execução rápida;
- **Superhuman:** foco, triagem e redução de fricção;
- **Mercury:** serenidade visual e leitura executiva;
- **Ramp:** operação financeira e saúde de integrações em áreas próprias, sem poluir a Home.

O STK OS deve ter identidade própria e não reproduzir marca, layout ou componentes proprietários dessas referências.

## 4. Assinatura do produto — Ctrl+K

O `Ctrl+K` é uma característica central do STK OS e deve permanecer disponível no topo de todas as telas.

Visualmente existe **uma única barra universal**.

Exemplo de placeholder:

> **Buscar, perguntar ou comandar o STK OS...**   `Ctrl + K`   🎙

Não mostrar permanentemente as opções Buscar, Executar, Perguntar e Falar como abas, botões ou modos selecionáveis.

Essas quatro capacidades existem internamente e a intenção deve ser inferida pelo sistema a partir do comando digitado ou falado.

Exemplos futuros:

- “Abra o contrato da Alpha.”
- “Quais oportunidades estão sem próxima ação?”
- “Como está o faturamento da MR?”
- “Crie uma tarefa para amanhã.”
- “O que precisa da minha atenção esta semana?”

Ações sensíveis, destrutivas, financeiras ou irreversíveis exigem confirmação apropriada antes da execução.

O Ctrl+K não deve virar um grande chatbot. Ele é uma camada universal de navegação, consulta e comando.

## 5. Estrutura global

### Seletor de contexto

No topo da sidebar:

- Grupo STK
- MR
- STK Lab
- Stelli

Ao trocar o contexto, os módulos passam a refletir aquela unidade quando aplicável.

### Sidebar principal

1. Início
2. CRM
3. Contratos
4. Financeiro
5. Tarefas
6. Automações

MR, STK Lab e Stelli não aparecem como módulos paralelos na sidebar.

A sidebar deve ser visualmente mais discreta que a área principal, permitindo que o conteúdo seja o foco.

## 6. Home — Início

A Home deve responder em poucos segundos:

1. Onde estou?
2. O que precisa da minha atenção?
3. O que está próximo?
4. Como está o negócio em alto nível?

### Cabeçalho

Mostrar:

- título `Início`;
- data atual em português;
- saudação humana e objetiva.

Exemplo:

> **Bom dia, Thiago. Aqui está o que mais importa agora.**

### Precisa da sua atenção

É o principal bloco da Home.

Regras:

- máximo de 3 itens destacados na primeira camada;
- somente exceções, decisões ou riscos que realmente demandem ação;
- título curto;
- contexto suficiente;
- ação clara;
- status por texto + ícone, nunca apenas por cor.

Exemplos:

- reajuste contratual a revisar;
- competência financeira bloqueada;
- oportunidade importante sem próxima ação;
- automação crítica com falha;
- prazo operacional relevante.

Se nenhuma ação for necessária, mostrar um estado calmo de controle, sem preencher a tela com tarefas normais.

### Próximos 7 dias

Manter na Home.

É uma visão de agenda/prazos, não uma lista genérica de tarefas.

Mostrar poucos itens, em ordem temporal, com:

- data;
- horário quando existir;
- título;
- contexto/módulo;
- acesso à agenda completa.

### Visão executiva

Resumo compacto, não dashboard analítico.

Máximo recomendado de 3 a 4 KPIs, por exemplo:

- receita prevista;
- pipeline ativo;
- contratos ativos;
- tarefas críticas.

Sem gráfico grande de receita na Home.

Análises, séries históricas e gráficos detalhados pertencem ao módulo Financeiro.

### Prioridades

Pode existir como bloco discreto, desde que não duplique “Precisa da sua atenção”.

Usar para itens operacionais prioritários do usuário, não para criar uma segunda central de alertas.

### Não incluir na Home

Não criar seção permanente “Sistema trabalhando”.

Automações normais não precisam ocupar espaço na Home.

Se uma automação ou integração falhar de maneira relevante, ela sobe para **Precisa da sua atenção**.

## 7. CRM

O CRM deve ser visualmente limpo e rápido.

Prioridades:

- visão de pipeline clara;
- tabelas/listas elegantes;
- Kanban com pouco ruído;
- busca rápida;
- acesso natural à Pessoa 360° e Empresa 360°;
- próxima ação evidente;
- histórico contextual sem excesso de elementos simultâneos.

Referência de sensação: Attio + Linear, sem copiar.

## 8. Cliente / Empresa 360°

A página deve parecer um centro de contexto, não um formulário enorme.

Estrutura sugerida:

- identidade no topo;
- informações essenciais;
- oportunidades;
- atividades;
- tarefas;
- contratos relacionados;
- histórico/timeline.

Usar disclosure progressivo: mostrar primeiro o essencial e aprofundar sob demanda.

## 9. Contratos

Contratos são um módulo próprio e canônico.

A interface deve permitir compreender rapidamente:

- cliente;
- unidade;
- situação operacional;
- versão atual;
- próxima alteração programada;
- emissor;
- serviços;
- contatos financeiros;
- histórico de versões/eventos.

A versão atual deve ser visualmente dominante. Histórico e versões futuras devem ser acessíveis sem competir com o presente.

## 10. Financeiro

A Home do Financeiro pode ser mais analítica que a Home geral.

Direção:

- competência selecionada claramente;
- valor previsto;
- quantidade de obrigações;
- prontas;
- bloqueadas;
- valor bloqueado;
- exceções prioritárias;
- distribuição por unidade quando em contexto Grupo STK;
- gráficos somente quando suportarem decisão.

O Financeiro pode usar maior densidade informacional, mas deve manter a calma visual do sistema.

Estados financeiros devem ser inequívocos e textuais.

## 11. Tarefas

Tarefas são a to-do operacional do STK OS, mas sempre ligadas a contexto quando possível.

Uma tarefa pode estar vinculada a:

- cliente;
- oportunidade;
- contrato;
- processo;
- responsável;
- prazo.

A tela deve priorizar:

- Hoje;
- Atrasadas;
- Próximas;
- Sem data;
- Concluídas.

Evitar listas excessivamente ornamentadas.

## 12. Automações

Automações não devem parecer uma tela técnica para desenvolvedor por padrão.

Taxonomia visual desejada:

- **Fluxos**
- **Integrações**
- **Execuções**
- **Saúde**

Exemplos futuros de integrações:

- NFS-e;
- Outlook;
- n8n;
- Itaú;
- WhatsApp;
- serviços de IA.

Usuário comum vê estados operacionais claros.

Detalhes técnicos/API ficam restritos a perfis administrativos adequados.

Falhas críticas podem aparecer na Home em “Precisa da sua atenção”. Operação normal permanece dentro de Automações.

## 13. Linguagem visual

### Tema principal

Light theme como padrão inicial.

- fundo geral: off-white/cinza muito claro;
- painéis: branco ou neutro muito leve;
- sidebar: neutro levemente mais escuro/dimmed que o conteúdo;
- texto principal: grafite profundo;
- texto secundário: cinza médio;
- uma única cor primária STK para interação/destaque;
- verde, amarelo e vermelho reservados a significado de status.

Dark mode pode existir futuramente, mas não define a identidade inicial.

### Tipografia

- sans-serif moderna;
- legibilidade acima de personalidade;
- títulos fortes sem exagero;
- corpos compactos e confortáveis;
- evitar excesso de tamanhos/pesos.

### Cards

- bordas discretas;
- raio moderado;
- sombras mínimas ou inexistentes;
- uso de espaço para separar conteúdo em vez de caixas pesadas;
- evitar “card para tudo”.

### Ícones

- uma única família visual;
- simples;
- traço consistente;
- nenhum excesso decorativo.

### Movimento

- rápido e sutil;
- usado para orientar transição/estado;
- nunca ornamental;
- respeitar preferência de redução de movimento.

## 14. Densidade e hierarquia

Regra central:

> **Progressive disclosure.**

A primeira camada mostra o essencial; detalhes aparecem por clique, drawer, expansão ou navegação.

Evitar simultaneamente na mesma tela:

- excesso de cards;
- muitos gráficos;
- muitas cores;
- filtros permanentes sem necessidade;
- grandes blocos de texto;
- múltiplas áreas competindo por atenção.

A Home deve parecer mais vazia do que um ERP convencional — deliberadamente.

## 15. Responsividade

Prioridade de design:

1. desktop/notebook;
2. tablet;
3. mobile.

No mobile:

- preservar status e ações críticas;
- transformar tabelas em layouts adequados;
- manter acesso ao comando universal;
- não simplesmente reduzir a versão desktop.

## 16. Acessibilidade

Obrigatório:

- navegação por teclado;
- foco visível;
- contraste adequado;
- rótulos textuais para estados;
- ícones acompanhados de contexto quando necessário;
- modais/drawers acessíveis;
- nenhuma informação crítica apenas por cor;
- alvo de clique confortável.

## 17. O que evitar

O STK OS não deve ter:

- estética de ERP legado;
- aparência de painel administrativo genérico;
- sidebar superlotada;
- chat de IA flutuante como protagonista;
- quatro abas Buscar/Executar/Perguntar/Falar no Ctrl+K;
- gráfico só para ocupar espaço;
- arco-íris de status;
- sombras pesadas;
- gradientes excessivos;
- cards para todo campo;
- telas com 20 informações de igual prioridade;
- menus técnicos expostos ao usuário comum;
- animações decorativas;
- textos com aparência robótica.

## 18. Critérios de aceite visual

Uma tela só deve ser considerada aprovada se:

1. o usuário entende sua finalidade em até poucos segundos;
2. a ação principal é evidente;
3. o contexto Grupo/MR/Lab/Stelli está claro;
4. o Ctrl+K está acessível sem dominar visualmente a tela;
5. as informações mais importantes têm prioridade real;
6. detalhes secundários não competem com decisões;
7. a tela mantém coerência com as demais;
8. não há ruído visual desnecessário;
9. estados são claros e acessíveis;
10. o resultado parece um produto premium, não um template.

## 19. Direção final aprovada

Após comparação com alternativas de CRM, command centers, produtos financeiros e interfaces agentic, a recomendação permanece **Curadoria C + A**.

Não foi identificada uma direção alternativa que supere o conjunto para o objetivo do STK OS. O refinamento recomendado é incorporar ao C + A quatro aprendizados:

1. **IA contextual e agente embutido**, sem chat separado como centro da experiência;
2. **navegação mais calma e consistente**, com sidebar visualmente discreta;
3. **comando universal orientado por intenção**, sem seleção manual de modo;
4. **saúde de integrações concentrada em Automações**, levando à Home apenas falhas relevantes.

A identidade resultante deve ser reconhecível como:

> **STK OS — um sistema executivo orientado por atenção, contexto e comando.**

