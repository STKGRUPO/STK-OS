# Visão geral da arquitetura

O STK OS V1 começa como monólito modular:

```text
Next.js → FastAPI → PostgreSQL
              ├── identidade e autorização
              ├── organização
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

## Limites desta entrega

Não existem módulos de CRM, contrato, faturamento, NFS-e, Outlook, n8n, IA ou MCP. Diretórios reservados por decisão explícita contêm somente documentação de fronteira.

