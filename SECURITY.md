# Segurança

## Regras obrigatórias

- Nunca versionar secrets, certificados, tokens, dumps ou payloads reais.
- Nunca usar credenciais produtivas no desenvolvimento.
- Nunca inserir dados reais de clientes, dados clínicos ou documentos pessoais em fixtures.
- Usar identidades distintas para usuários humanos e integrações.
- Registrar somente metadados mínimos e redigir campos sensíveis dos logs.

## Configuração

`.env.example` contém apenas nomes de variáveis. Arquivos `.env` são locais e ignorados pelo Git. Em ambientes compartilhados, os valores devem vir do gerenciador de secrets do provedor.

## Reporte

Incidentes ou suspeitas devem ser comunicados diretamente ao administrador do Grupo STK, sem anexar secrets ou payloads sensíveis ao ticket. Antes de produção serão obrigatórios runbook de incidente, responsáveis e política de retenção aprovados.

