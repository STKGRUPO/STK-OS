# Visão geral da arquitetura

O STK OS V1 começa como monólito modular:

```text
Next.js → FastAPI → PostgreSQL
              ├── identidade e autorização
              ├── organização
              ├── CRM
              └── trilha de controle
```

O backend é o único dono das regras, autorização, invariantes e transações. Ações com efeito registram auditoria e outbox na mesma transação. Entradas externas futuras serão persistidas na inbox antes do processamento.

## Domínio organizacional

```text
Grupo
└── Entidade Jurídica
    └── Estabelecimento Fiscal
        └── Unidade de Negócio
```

Uma unidade pertence a um estabelecimento fiscal operacional. Vínculos futuros podem representar outros estabelecimentos emissores sem confundir identidade fiscal com a unidade comercial.

## CRM vertical

Pessoa e Empresa são cadastros canônicos do Grupo. O relacionamento com MR, STK Lab e Stelli é muitos-para-muitos, sem duplicar o cadastro mestre. Oportunidade, pipeline, tarefa e atividade têm unidade explícita.

Status (`open`, `won`, `lost`) não é etapa. Toda mudança de etapa grava histórico append-only na mesma transação. A próxima ação é uma projeção da tarefa aberta mais próxima, não um texto duplicado na oportunidade.

## Limites desta entrega

Não existem módulos de contrato, faturamento, NFS-e, Outlook, n8n, IA ou MCP. A inspeção do sistema Python pertence à Etapa 3 e não foi antecipada.
