# STK OS — pacote visual sanitizado

## Objetivo

Esta pasta é uma sandbox exclusivamente visual do STK OS. Ela existe para trabalho de identidade visual, layout, UX, responsividade, componentes, estados, acessibilidade de apresentação, microinterações e acabamento premium.

Todos os nomes, e-mails, contratos, valores, datas, tarefas, oportunidades e eventos desta pasta são fictícios e foram criados somente para demonstrar a experiência.

## Direção da experiência

A arquitetura visual segue o conceito **Executive Flow OS**: atenção, contexto, comando e exceção. O acabamento é premium minimalista, com alta legibilidade, espaço visual, hierarquia clara, cards discretos, sombras mínimas e cor usada com propósito.

Princípio central: **“O sistema sabe tudo. A tela mostra só o que importa agora.”**

## Navegação incluída

- Início: saudação, data, “Precisa da sua atenção”, próximos sete dias, visão executiva e prioridade do dia;
- CRM: Kanban, pessoas, empresas, oportunidades e exemplo de Cliente 360°;
- Contratos: lista canônica, detalhe, estados independentes, versão atual, histórico, versão futura, serviços, contatos e eventos;
- Financeiro: competência, faturamento previsto, itens prontos, bloqueados, exceção e detalhe visual da obrigação;
- Tarefas: todas, hoje, atrasadas, próximas, prioridade, responsável e vínculo contextual;
- Automações: experiência conceitual para Fluxos, Integrações, Execuções e Saúde;
- seletor global de contexto: Grupo, Unidade A, Unidade B e Unidade C;
- comando universal global por `Ctrl+K` ou `Cmd+K`.

## Componentes e comportamentos

O pacote contém App Shell, sidebar, seletor de contexto, comando universal, page headers, badges, cards de atenção, métricas compactas, tabelas responsivas, Kanban, lista de tarefas, timeline, estados vazios, drawers, toast e diálogo de confirmação.

O comando universal possui resultados e navegação mockados. Para revisar estados visuais, digite `carregando`, `vazio`, `erro`, `sucesso` ou `permissão`. Não existe IA, voz, agente ou execução real.

A ação “Gerar competência” abre somente uma confirmação demonstrativa. Ela não calcula, grava ou envia nada. “Pronto” identifica apenas um item visualmente preparado para uma funcionalidade futura.

## Dados fictícios

Os fixtures ficam em `mock-data/fixtures.ts`. Use somente dados sintéticos semelhantes aos já fornecidos. Não substitua os mocks por dados reais, exportações, documentos, logs ou informações de clientes.

## Restrições obrigatórias

O trabalho no Lovable deve permanecer estritamente no frontend desta pasta.

É proibido:

- criar camadas de dados, serviços, conexões ou persistência;
- substituir os mocks por qualquer fonte externa ou persistente;
- implementar regras, cálculos, autorizações ou operações de domínio;
- transformar funcionalidades futuras em recursos reais;
- implementar automação, voz, agente ou comando real;
- adicionar credenciais, configurações privadas, dados pessoais ou comerciais reais;
- importar código, dados ou configuração de fora desta pasta;
- alterar entidades, estados oficiais ou decisões internas do produto;
- copiar interface ou branding proprietário de terceiros.

## Entrega esperada do Lovable

Devolver somente alterações visuais dentro desta pasta: CSS, tokens, layout, spacing, tipografia, componentes, responsividade, acessibilidade de apresentação, estados e microinterações. Mocks devem continuar locais, explícitos e removíveis. Nenhuma conexão externa deve ser criada.

O diretório autorizado para trabalho e devolução é exclusivamente:

`lovable-visual-sandbox/`
