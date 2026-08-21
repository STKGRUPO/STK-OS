# Visão geral da arquitetura

O STK OS V1 começa como monólito modular:

```text
Next.js → FastAPI → PostgreSQL
              ├── identidade e autorização
              ├── organização
              ├── CRM
              ├── contratos versionados
              ├── faturamento recorrente
              ├── emissão/reconciliação fiscal
              └── trilha de controle
              │
              └── TLS/M2M → Serviço Fiscal Python privado → mTLS/A1 → SEFIN
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

## Contratos versionados

O contrato mantém uma identidade administrativa estável e snapshots completos de configuração com vigência temporal. A validade final é derivada do início da próxima versão, o que impede lacunas e sobreposições. Valor usa `Decimal`; emissor fiscal, serviços e contatos são referências controladas à estrutura organizacional e ao CRM.

Versões e eventos operacionais são append-only. Suspensão, retomada, rescisão e renovação ficam separados do status administrativo e não reescrevem a configuração histórica. Autorização por capacidade e unidade, idempotência, auditoria e outbox cobrem todas as escritas.

## Núcleo de faturamento

O backend gera uma execução única por organização, unidade e mês civil e uma obrigação única por contrato/competência. A versão contratual válida, o estabelecimento emissor, o valor bruto, serviços e contatos são congelados em snapshot canônico com SHA-256. PostgreSQL serializa a geração por lock consultivo e reforça unicidade e imutabilidade por constraints e triggers.

Itens íntegros ficam `ready` e publicam `billing.item.ready.v1` na outbox. Ambiguidades ou dados inválidos ficam `blocked` com exceção operacional; contratos não elegíveis recebem explicação no lote sem criar obrigação. Uma falha isolada não invalida os demais contratos.

## Serviço fiscal privado

O backend persiste a intenção fiscal e reserva a DPS antes do efeito externo. O serviço privado é o único processo que lê o A1 montado pelo secret manager, assina a DPS em memória e abre a sessão mTLS com a SEFIN. Timeout nunca dispara reemissão automática: a tentativa fica `uncertain` e é consultada por `dps_id` antes de qualquer reenvio. Certificado, senha, XML e PDF não são expostos ao frontend ou a n8n.

## Limites da Etapa 6

Não existem cobrança, boleto, recebimento, cancelamento/substituição, envio da nota ao cliente, Outlook, n8n, IA ou MCP.
