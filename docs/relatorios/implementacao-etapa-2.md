# Implementação da Etapa 2 — CRM vertical mínimo

**Data:** 19 de agosto de 2026

## Escopo entregue

- pessoas e empresas canônicas no Grupo;
- contatos e vínculos pessoa–empresa/unidade;
- produtos/serviços, origens e motivos de perda;
- quatro pipelines comerciais para MR, STK Lab e Stelli B2C/B2B;
- oportunidades, participantes e produtos relacionados;
- histórico de etapas append-only;
- atividades, tarefas e próxima ação derivada;
- API idempotente com auditoria/outbox;
- Kanban responsivo, busca e visão 360°;
- importação de até cem linhas, com evidência por hash e revisão de contato ambíguo.

## Banco e migrations

- `003_crm_vertical.sql`: schema, constraints, índices e coerência pipeline/etapa/unidade;
- `004_crm_append_only_guards.sql`: proteção do histórico de etapas e linhas de importação;
- `002_synthetic_crm_reference.sql`: permissões, catálogos e pipelines somente sintéticos.

As quatro migrations foram aplicadas e verificadas por checksum no PostgreSQL 18.4 local. O seed completo foi repetido sem duplicação.

## Validação

- pytest com PostgreSQL real: 21 testes aprovados, 89,24% de cobertura, nenhum skip ou warning;
- invariantes PostgreSQL: multiunidade, unicidades, perda com motivo, coerência de etapa e guards append-only aprovados;
- prova HTTP real: login, três unidades, cadastro canônico, oportunidade, próxima ação, mudança de etapa, Kanban, busca e visão 360° aprovados;
- inspeção visual: desktop e viewport móvel aprovados, sem erros/warnings no console;
- OpenAPI regenerada.
- `pnpm quality`: aprovado integralmente após a documentação final.

## Falhas encontradas e correções

1. A busca reduzia termos alfanuméricos com dígitos ao componente numérico. A normalização agora aplica dígitos somente a consultas com formato de telefone/documento.
2. O marcador visual `Enter` da busca não era um controle acessível. Foi substituído por botão de submissão e revalidado no navegador.
3. O cache gerado `.next` ficou bloqueado na primeira reconstrução; somente o cache recuperável foi recriado e o build passou.

## Limites preservados

Nenhum contrato, faturamento, sistema Python, NFS-e, Outlook, n8n, IA, MCP ou dado clínico foi implementado. Nenhum dado, certificado ou secret de produção foi utilizado.

## Parecer

# ETAPA 2 APROVADA — PODE AVANÇAR PARA ETAPA 3

A aprovação não inicia automaticamente a inspeção do sistema Python prevista para a Etapa 3.
